"""No-LaserStream Pump.fun official lifecycle collector.

Forward-observation only. This module records provisional create-log births
before transaction hydration, hydrates signatures asynchronously, and starts
bounded read-only follow-up for mints that pass the official freshness gate.
"""

from __future__ import annotations

from collections import Counter, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Callable
import json
import threading
import time
import urllib.request

from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
from research.mtp_research.validation.forward_birth_watch_followup_collector import (
    HeliusMintBirthWatchFollowupFetcher,
    rpc_url_to_websocket_url,
    signature_from_create_logs_notification,
)
from research.mtp_research.validation.forward_efficient_mover_observer import (
    PUMP_FUN_PROGRAM_ID,
    build_birth_watch_candidate_from_create_candidate,
    resolve_helius_rpc_url,
    safe_float,
    _post_json_rpc,
)
from research.mtp_research.validation.official_lifecycle_watch import (
    OFFICIAL_SAMPLE_LABEL,
    TARGET_LEVELS,
    OfficialLifecycleConfig,
    OfficialLifecycleStateMachine,
    build_official_lifecycle_quality_audit,
    initialize_official_lifecycle_namespace,
    official_lifecycle_status,
    run_active_lifecycle_followup_cycle,
    _append_jsonl,
    _delta,
    _followup_addresses,
    _mint,
    _num,
    _read_jsonl,
    _row_count,
    _write_json,
)


HYDRATION_PENDING = "pending_hydration"
HYDRATION_CONFIRMED = "hydrated_create_confirmed"
HYDRATION_NOT_CREATE = "hydrated_not_create"
HYDRATION_FAILED = "hydration_failed"
HYDRATION_TIMEOUT = "hydration_timeout"
HYDRATION_STALE = "stale_rejected"
HYDRATION_OFFICIAL = "official_accepted"


@dataclass
class NoLaserstreamCollectorCounters:
    provisional_birth_logs: int = 0
    hydration_results: int = 0
    hydrated_confirmed_creates: int = 0
    official_accepted_births: int = 0
    stale_or_quarantined_births: int = 0
    fdv_path_evidence: int = 0
    metadata_rows_written: int = 0
    holder_snapshots_written: int = 0
    duplicate_signatures: int = 0


class NoLaserstreamCreateLogSource:
    source_adapter = "helius_pumpfun_no_laserstream_logs"

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        websocket_url: str | None = None,
        timeout_seconds: float = 1.0,
        ws_connect: Any | None = None,
    ) -> None:
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self.websocket_url = websocket_url or rpc_url_to_websocket_url(self.rpc_url)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._ws_connect = ws_connect
        self.requests_used = 0
        self._lock = threading.Lock()
        self._log_queue: deque[dict[str, Any]] = deque()
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()
        self._listener_errors = 0

    def availability(self) -> dict[str, Any]:
        if not self.websocket_url:
            return {
                "source": self.source_adapter,
                "available": False,
                "read_only": True,
                "missing_reason": "live_source_blocked_no_helius_websocket_config",
            }
        return {
            "source": self.source_adapter,
            "available": True,
            "read_only": True,
            "laserstream_used": False,
            "listener": "logsSubscribe",
            "listener_mode": "persistent_provisional_log_queue",
            "program_id": PUMP_FUN_PROGRAM_ID,
        }

    def fetch_logs(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.websocket_url:
            return []
        self._ensure_listener_started()
        deadline = time.monotonic() + self.timeout_seconds
        rows: list[dict[str, Any]] = []
        while len(rows) < max(1, int(limit)) and time.monotonic() < deadline:
            with self._lock:
                while self._log_queue and len(rows) < max(1, int(limit)):
                    rows.append(self._log_queue.popleft())
            if rows:
                break
            time.sleep(0.01)
        return rows

    def close(self) -> None:
        self._listener_stop.set()
        thread = self._listener_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _ensure_listener_started(self) -> None:
        with self._lock:
            if self._listener_thread is not None and self._listener_thread.is_alive():
                return
            self._listener_stop.clear()
            self._listener_thread = threading.Thread(
                target=self._listen_for_create_logs,
                name="mtp-no-laserstream-pumpfun-create-listener",
                daemon=True,
            )
            self._listener_thread.start()

    def _listen_for_create_logs(self) -> None:
        connect = self._ws_connect or _websocket_connect
        while not self._listener_stop.is_set():
            subscription_id: int | None = None
            try:
                with connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                    with self._lock:
                        self.requests_used += 1
                    websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "mtp-no-laserstream-pumpfun-create-logs",
                                "method": "logsSubscribe",
                                "params": [
                                    {"mentions": [PUMP_FUN_PROGRAM_ID]},
                                    {"commitment": "processed"},
                                ],
                            }
                        )
                    )
                    while not self._listener_stop.is_set():
                        try:
                            message = websocket.recv(timeout=min(1.0, max(0.1, self.timeout_seconds)))
                        except TimeoutError:
                            continue
                        payload = json.loads(message) if isinstance(message, str) else message
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("id") == "mtp-no-laserstream-pumpfun-create-logs":
                            subscription_id = payload.get("result") if isinstance(payload.get("result"), int) else None
                            continue
                        signature = signature_from_create_logs_notification(payload)
                        if not signature:
                            continue
                        row = _create_log_record_from_payload(payload, signature=signature, observed_at=time.time())
                        with self._lock:
                            self._log_queue.append(row)
                    if subscription_id is not None:
                        websocket.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": "mtp-no-laserstream-pumpfun-create-unsubscribe",
                                    "method": "logsUnsubscribe",
                                    "params": [subscription_id],
                                }
                            )
                        )
            except Exception:
                with self._lock:
                    self._listener_errors += 1
                time.sleep(min(1.0, self.timeout_seconds))


class NoLaserstreamCreateHydrator:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        rpc_post: Any | None = None,
        scanner: PumpFunCreateScanner | None = None,
        timeout_seconds: int = 10,
        hydration_retry_attempts: int = 3,
        hydration_retry_pause_seconds: float = 0.25,
    ) -> None:
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self._rpc_post = rpc_post or _post_json_rpc
        self.scanner = scanner or PumpFunCreateScanner()
        self.timeout_seconds = int(timeout_seconds)
        self.hydration_retry_attempts = max(1, int(hydration_retry_attempts))
        self.hydration_retry_pause_seconds = max(0.0, float(hydration_retry_pause_seconds))
        self.requests_used = 0

    def hydrate(self, provisional: dict[str, Any]) -> dict[str, Any]:
        signature = str(provisional.get("signature") or "")
        started = time.time()
        if not self.rpc_url or not signature:
            return {
                **_hydration_base(provisional, started_at=started),
                "hydration_status": HYDRATION_FAILED,
                "missing_reason": "missing_rpc_url_or_signature",
            }
        tx: dict[str, Any] = {}
        last_error: str | None = None
        for attempt in range(1, self.hydration_retry_attempts + 1):
            try:
                tx = self._fetch_transaction(signature)
            except TimeoutError:
                last_error = "get_transaction_timeout"
                tx = {}
            except Exception as exc:
                last_error = f"get_transaction_failed:{type(exc).__name__}"
                tx = {}
            if tx:
                break
            if attempt < self.hydration_retry_attempts:
                time.sleep(self.hydration_retry_pause_seconds)
        if not tx:
            return {
                **_hydration_base(provisional, started_at=started),
                "hydration_status": HYDRATION_TIMEOUT if last_error == "get_transaction_timeout" else HYDRATION_FAILED,
                "missing_reason": last_error or "get_transaction_empty_result",
            }
        candidates, rejected, unknown, direct_count = self.scanner._extract_candidates(
            [tx],
            remaining_target=1,
            include_low_confidence=False,
            min_confidence="medium",
        )
        if not candidates:
            return {
                **_hydration_base(provisional, started_at=started),
                "hydration_status": HYDRATION_NOT_CREATE,
                "missing_reason": "no_verified_create_candidate",
                "direct_pumpfun_instruction_count": direct_count,
                "rejected_create_like_count": len(rejected),
                "unknown_pumpfun_instruction_count": len(unknown),
            }
        candidate = build_birth_watch_candidate_from_create_candidate(candidates[0])
        candidate["observed_at"] = provisional.get("log_observed_at")
        candidate["source"] = "helius_program_logs_pumpfun_create_websocket"
        candidate["source_adapter"] = "helius_pumpfun_no_laserstream_logs"
        candidate["create_signature"] = signature
        candidate["transaction_signature"] = signature
        candidate.setdefault("launch_time", candidate.get("block_time") or provisional.get("block_time"))
        metadata = _metadata_from_candidate(candidate)
        return {
            **_hydration_base(provisional, started_at=started),
            "hydration_status": HYDRATION_CONFIRMED,
            "hydration_completed_at": time.time(),
            "candidate": candidate,
            "mint": _mint(candidate),
            "creator": candidate.get("creator"),
            "bonding_curve": candidate.get("bonding_curve") or candidate.get("pool_address"),
            "associated_bonding_curve": candidate.get("associated_bonding_curve"),
            "token_name": candidate.get("token_name") or candidate.get("name"),
            "token_symbol": candidate.get("token_symbol") or candidate.get("symbol"),
            "metadata_uri": candidate.get("metadata_uri") or candidate.get("uri"),
            "parse_confidence": candidate.get("parse_confidence") or candidate.get("confidence") or "medium",
            "metadata": metadata,
        }

    def _fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-no-laserstream-create-get-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
        }
        response = self._rpc_post(self.rpc_url, payload, self.timeout_seconds)
        self.requests_used += 1
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}


class NoLaserstreamMetadataResolver:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        rpc_post: Any | None = None,
        timeout_seconds: int = 8,
        urlopen: Any | None = None,
    ) -> None:
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self._rpc_post = rpc_post or _post_json_rpc
        self.timeout_seconds = int(timeout_seconds)
        self._urlopen = urlopen or urllib.request.urlopen
        self.requests_used = 0

    def resolve(self, mint: str, candidate_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = {
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "mint": mint,
            "metadata_source": None,
            "token_name": None,
            "token_symbol": None,
            "metadata_uri": None,
            "metadata_missing_reason": None,
        }
        candidate_metadata = candidate_metadata or {}
        if candidate_metadata.get("token_name") or candidate_metadata.get("token_symbol") or candidate_metadata.get("metadata_uri"):
            row.update(candidate_metadata)
            row["metadata_source"] = "pumpfun_create_transaction"
            return row
        das = self._resolve_helius_das(mint)
        if das:
            row.update(das)
            row["metadata_source"] = "helius_das"
            return row
        uri = candidate_metadata.get("metadata_uri")
        if uri:
            public_metadata = self._resolve_public_uri(str(uri))
            if public_metadata:
                row.update(public_metadata)
                row["metadata_uri"] = uri
                row["metadata_source"] = "public_metadata_uri"
                return row
        row["metadata_missing_reason"] = "metadata_unavailable_from_create_das_or_uri"
        return row

    def _resolve_helius_das(self, mint: str) -> dict[str, Any] | None:
        if not self.rpc_url or not mint:
            return None
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-no-laserstream-get-asset",
            "method": "getAsset",
            "params": {"id": mint},
        }
        try:
            response = self._rpc_post(self.rpc_url, payload, self.timeout_seconds)
            self.requests_used += 1
        except Exception:
            return None
        result = response.get("result") if isinstance(response, dict) else None
        if not isinstance(result, dict):
            return None
        content = result.get("content") if isinstance(result.get("content"), dict) else {}
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        links = content.get("links") if isinstance(content.get("links"), dict) else {}
        return {
            "token_name": metadata.get("name") or content.get("metadata", {}).get("name") if isinstance(content.get("metadata"), dict) else metadata.get("name"),
            "token_symbol": metadata.get("symbol") or (content.get("metadata", {}).get("symbol") if isinstance(content.get("metadata"), dict) else None),
            "metadata_uri": links.get("metadata") or content.get("json_uri"),
        }

    def _resolve_public_uri(self, uri: str) -> dict[str, Any] | None:
        try:
            with self._urlopen(uri, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.requests_used += 1
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return {
            "token_name": payload.get("name"),
            "token_symbol": payload.get("symbol"),
            "metadata_uri": uri,
        }


class NoLaserstreamHydrationQueue:
    def __init__(
        self,
        *,
        hydrator: Any,
        max_workers: int = 16,
        hydration_timeout_seconds: float = 12.0,
    ) -> None:
        self.hydrator = hydrator
        self.hydration_timeout_seconds = max(0.1, float(hydration_timeout_seconds))
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)))
        self._futures: dict[Future, dict[str, Any]] = {}

    @property
    def pending_count(self) -> int:
        return len(self._futures)

    def submit(self, provisional: dict[str, Any]) -> None:
        future = self.executor.submit(self.hydrator.hydrate, dict(provisional))
        self._futures[future] = dict(provisional)

    def drain_completed(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for future in list(self._futures):
            if len(rows) >= max(1, int(limit)):
                break
            if not future.done():
                continue
            provisional = self._futures.pop(future)
            try:
                row = future.result(timeout=0)
            except TimeoutError:
                row = {
                    **_hydration_base(provisional, started_at=provisional.get("hydration_started_at")),
                    "hydration_status": HYDRATION_TIMEOUT,
                    "missing_reason": "hydration_timeout",
                }
            except Exception as exc:
                row = {
                    **_hydration_base(provisional, started_at=provisional.get("hydration_started_at")),
                    "hydration_status": HYDRATION_FAILED,
                    "missing_reason": f"hydration_failed:{type(exc).__name__}",
                }
            row = _merge_provisional_context(provisional, row)
            rows.append(row)
        return rows

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


def run_no_laserstream_lifecycle_smoke(
    config: OfficialLifecycleConfig,
    *,
    target_births: int = 50,
    target_crossed_20k: int = 300,
    max_runtime_seconds: float | None = None,
    max_runtime_minutes: int = 45,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    execute: bool = False,
    source: Any | None = None,
    hydrator: Any | None = None,
    fetcher: Any | None = None,
    metadata_resolver: Any | None = None,
    now_fn: Callable[[], float] | None = None,
) -> dict[str, Any]:
    initialize_official_lifecycle_namespace(config, reset=execute and _row_count(config.births_path) == 0)
    write_no_laserstream_bottleneck_audit(config)
    projected_requests = max(0, int(target_births)) * (1 + max(0, min(int(signatures_per_mint), int(transactions_per_mint))) + 1)
    if not execute:
        return {
            "report_id": "no_laserstream_official_lifecycle_smoke_v1",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "projected_births": target_births,
            "projected_request_equivalent_credits": projected_requests,
            "readiness_classification": "no_laserstream_collector_ready_for_100_birth_run",
            "network_calls_made": 0,
        }
    if projected_requests > int(config.max_helius_credits_per_run):
        return {
            "report_id": "no_laserstream_official_lifecycle_smoke_v1",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "projected_births": target_births,
            "projected_request_equivalent_credits": projected_requests,
            "readiness_classification": "no_laserstream_collector_blocked",
            "warnings": ["projected_requests_exceed_run_credit_cap"],
            "network_calls_made": 0,
        }
    source = source or NoLaserstreamCreateLogSource(timeout_seconds=1.0)
    availability = source.availability() if hasattr(source, "availability") else {"available": True}
    if not availability.get("available", True):
        return {
            "report_id": "no_laserstream_official_lifecycle_smoke_v1",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "readiness_classification": "no_laserstream_collector_blocked",
            "warnings": [availability.get("missing_reason") or "no_laserstream_source_unavailable"],
            "network_calls_made": 0,
        }
    hydrator = hydrator or NoLaserstreamCreateHydrator()
    fetcher = fetcher or HeliusMintBirthWatchFollowupFetcher(data_root=config.root)
    metadata_resolver = metadata_resolver or NoLaserstreamMetadataResolver()
    now_fn = now_fn or time.time
    queue = NoLaserstreamHydrationQueue(hydrator=hydrator, max_workers=32)
    machine = OfficialLifecycleStateMachine(config)
    counters = NoLaserstreamCollectorCounters()
    seen_signatures: set[str] = {str(row.get("signature")) for row in _read_jsonl(config.provisional_births_path) if row.get("signature")}
    deadline = time.monotonic() + float(max_runtime_seconds if max_runtime_seconds is not None else max(1, int(max_runtime_minutes)) * 60)
    warnings: list[str] = []
    try:
        while counters.official_accepted_births < max(0, int(target_births)) and time.monotonic() < deadline:
            if _requests_used(source, hydrator, fetcher, metadata_resolver) >= int(config.max_helius_credits_per_run):
                warnings.append("max_helius_credits_per_run_reached")
                break
            log_rows = source.fetch_logs(limit=max(1, int(target_births) - counters.official_accepted_births))
            for raw_log in log_rows:
                signature = str(raw_log.get("signature") or "")
                if not signature or signature in seen_signatures:
                    counters.duplicate_signatures += 1
                    continue
                seen_signatures.add(signature)
                provisional = _provisional_birth_row(raw_log, now_fn=now_fn)
                _append_jsonl(config.pumpfun_create_logs_raw_path, [raw_log])
                _append_jsonl(config.provisional_births_path, [provisional])
                counters.provisional_birth_logs += 1
                queue.submit(provisional)
            completed = queue.drain_completed(limit=100)
            for hydration in completed:
                _append_jsonl(config.hydration_results_path, [hydration])
                counters.hydration_results += 1
                if hydration.get("hydration_status") != HYDRATION_CONFIRMED:
                    counters.stale_or_quarantined_births += 1
                    _append_jsonl(
                        config.stale_births_path,
                        [
                            _stale_from_hydration(
                                hydration,
                                reason=str(hydration.get("missing_reason") or hydration.get("hydration_status") or "hydration_quarantined"),
                            )
                        ],
                    )
                    continue
                counters.hydrated_confirmed_creates += 1
                candidate = hydration.get("candidate") if isinstance(hydration.get("candidate"), dict) else {}
                mint = _mint(candidate) or str(hydration.get("mint") or "")
                first_attempt = now_fn()
                if not mint:
                    counters.stale_or_quarantined_births += 1
                    _append_jsonl(config.stale_births_path, [_stale_from_hydration(hydration, reason="missing_mint_after_hydration")])
                    continue
                observed_delay = _delta(_num(hydration.get("log_observed_at")), first_attempt)
                if observed_delay is None or observed_delay > float(config.max_birth_to_first_followup_seconds):
                    counters.stale_or_quarantined_births += 1
                    _append_jsonl(config.stale_births_path, [_stale_from_hydration(hydration, first_attempt=first_attempt)])
                    _append_jsonl(config.hydration_results_path, [{**hydration, "hydration_status": HYDRATION_STALE}])
                    continue
                events = fetcher.fetch_for_mint(
                    mint,
                    signatures_per_mint=signatures_per_mint,
                    transactions_per_mint=transactions_per_mint,
                    followup_addresses=_followup_addresses(candidate),
                )
                first_fdv = next((safe_float(event.get("fdv_proxy")) for event in events if safe_float(event.get("fdv_proxy")) is not None), None)
                birth_row = _official_birth_row(
                    hydration,
                    candidate,
                    first_attempt=first_attempt,
                    first_fdv=first_fdv,
                    events=events,
                    config=config,
                )
                machine.record_birth(birth_row)
                _append_jsonl(config.hydration_results_path, [{**hydration, "hydration_status": HYDRATION_OFFICIAL}])
                counters.official_accepted_births += 1
                metadata = metadata_resolver.resolve(mint, hydration.get("metadata") if isinstance(hydration.get("metadata"), dict) else None)
                _append_jsonl(config.metadata_path, [metadata])
                counters.metadata_rows_written += 1
                if events:
                    _append_jsonl(config.events_path, [{**event, "sample_label": OFFICIAL_SAMPLE_LABEL, "mint": mint} for event in events])
                for event in events:
                    if safe_float(event.get("fdv_proxy")) is None:
                        continue
                    path = machine.record_path(
                        {
                            "mint": mint,
                            "timestamp": event.get("timestamp") or event.get("observed_at") or event.get("block_time") or first_attempt,
                            "fdv_proxy": event.get("fdv_proxy"),
                            "event_count": event.get("event_count") or 1,
                            "buy_count": event.get("buy_count") or (1 if str(event.get("side") or "").lower() == "buy" else 0),
                            "sell_count": event.get("sell_count") or (1 if str(event.get("side") or "").lower() == "sell" else 0),
                            "active_wallet_count": event.get("active_wallet_count") or event.get("active_wallets") or 1,
                            "holder_count_proxy": event.get("holder_count_proxy") or event.get("holder_count"),
                            "top_holder_share_proxy": event.get("top_holder_share_proxy"),
                            "top_10_holder_share_proxy": event.get("top_10_holder_share_proxy"),
                            "source_provenance": event.get("source") or "helius_no_laserstream_targeted_followup",
                        }
                    )
                    counters.fdv_path_evidence += 1
                    holder_snapshot = _holder_snapshot_from_event(event, path)
                    if holder_snapshot:
                        _append_jsonl(config.holder_snapshots_path, [holder_snapshot])
                        counters.holder_snapshots_written += 1
            run_active_lifecycle_followup_cycle(
                machine,
                fetcher,
                signatures_per_mint=signatures_per_mint,
                transactions_per_mint=transactions_per_mint,
            )
            if not log_rows and not completed:
                time.sleep(0.05)
        if time.monotonic() >= deadline and counters.official_accepted_births < int(target_births):
            warnings.append("max_runtime_minutes_reached")
    finally:
        queue.close()
        if hasattr(source, "close"):
            source.close()
    credits = _requests_used(source, hydrator, fetcher, metadata_resolver)
    _write_json(
        config.status_path,
        {
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "updated_at": _utc_now_iso(),
            "target_crossed_20k": target_crossed_20k,
            "credits_used": credits,
            "network_calls_made": credits,
            "hydration_queue_size": queue.pending_count,
            "followup_queue_size": len(machine.active_watch_mints()),
        },
    )
    audit, audit_paths = build_official_lifecycle_quality_audit(config)
    status = official_lifecycle_status(config, target_crossed_20k=target_crossed_20k)
    readiness = no_laserstream_readiness(config, status=status, audit=audit)
    result = {
        "report_id": "no_laserstream_official_lifecycle_smoke_v1",
        "execute": True,
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "source": availability,
        "provisional_birth_logs": counters.provisional_birth_logs,
        "hydration_results": counters.hydration_results,
        "hydrated_confirmed_creates": counters.hydrated_confirmed_creates,
        "official_accepted_births": counters.official_accepted_births,
        "stale_or_quarantined_births": counters.stale_or_quarantined_births,
        "stale_rate": _safe_rate(counters.stale_or_quarantined_births, counters.provisional_birth_logs),
        "under_5s_followup_count": status["fresh_births_under_5s_followup"],
        "fdv_path_evidence_count": status["births_with_fdv_path"],
        "crossed_10k": status["crossed_10k"],
        "crossed_20k": status["crossed_20k"],
        "metadata_rows_written": counters.metadata_rows_written,
        "holder_snapshots_written": counters.holder_snapshots_written,
        "estimated_helius_credits_used": credits,
        "network_calls_made": credits,
        "quality_audit_result": audit,
        "quality_audit_paths": {key: str(value) for key, value in audit_paths.items()},
        "lifecycle_state_file": str(config.state_path),
        "readiness_classification": readiness,
        "warnings": sorted(set(warnings + audit.get("warnings", []))),
    }
    _write_json(config.report_root / "no_laserstream_official_lifecycle_smoke_summary.json", result)
    return result


def write_no_laserstream_bottleneck_audit(config: OfficialLifecycleConfig) -> tuple[dict[str, Any], dict[str, Path]]:
    initialize_official_lifecycle_namespace(config)
    audit = {
        "report_id": "no_laserstream_bottleneck_audit_v1",
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "current_v1_bottleneck": {
            "logs_subscribe_receive_path": "PumpFunCreateWebSocketCandidateSource._listen_for_create_signatures",
            "signature_hydration_path": "getTransaction confirmed -> PumpFunCreateScanner._extract_candidates",
            "mint_details_discovery": "post-hydration create parser",
            "provisional_birth_rows_written": False,
            "official_birth_rows_written": "after hydration and parser success",
            "first_followup_starts": "after hydrated candidate returns to official lifecycle runner",
            "birth_registration_waits_for_hydration": True,
            "hydration_batches_wait_for_slow_signatures": False,
            "account_subscribe_or_transaction_subscribe_used": False,
            "targeted_followup_starts_before_hydration": False,
        },
        "v2_target_architecture": {
            "birth_registration_waits_for_hydration": False,
            "provisional_birth_rows_written": True,
            "hydration_mode": "concurrent_stream_completed_results",
            "first_followup_timer_source": "log_observed_at",
            "stale_rows_excluded_from_official_sample": True,
            "account_watch_fallback": "targeted_getSignaturesForAddress_getTransaction_polling",
            "laserstream_used": False,
        },
        "outputs": {
            "provisional_births": str(config.provisional_births_path),
            "raw_create_logs": str(config.pumpfun_create_logs_raw_path),
            "hydration_results": str(config.hydration_results_path),
            "stale_births": str(config.stale_births_path),
            "metadata": str(config.metadata_path),
            "holder_snapshots": str(config.holder_snapshots_path),
        },
        "recommendation": "Use no-LaserStream provisional birth registration, async hydration, and targeted follow-up smoke before any larger run.",
    }
    paths = {
        "json": config.report_root / "no_laserstream_bottleneck_audit.json",
        "markdown": config.report_root / "no_laserstream_bottleneck_audit.md",
    }
    _write_json(paths["json"], audit)
    paths["markdown"].write_text(_bottleneck_markdown(audit), encoding="utf-8")
    return audit, paths


def no_laserstream_readiness(
    config: OfficialLifecycleConfig,
    *,
    status: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> str:
    status = status or official_lifecycle_status(config)
    audit = audit or build_official_lifecycle_quality_audit(config, write_outputs=False)[0]
    warnings = list(audit.get("warnings", []))
    accepted = int(status.get("fresh_births_under_5s_followup") or 0)
    births = int(status.get("births_observed") or 0)
    late_stale = _late_stale_count(config)
    stale_rate = _safe_rate(late_stale, _confirmed_create_count(config))
    if warnings:
        return "no_laserstream_collector_needs_account_watch_repair"
    if accepted >= 50 and births >= 50 and status.get("births_with_fdv_path", 0) > 0:
        return "no_laserstream_collector_ready_for_100_birth_run"
    if stale_rate is not None and stale_rate > 0.25:
        return "no_laserstream_collector_partial_high_stale_rate"
    if births > 0:
        return "no_laserstream_collector_ready_for_100_birth_run"
    return "no_laserstream_collector_blocked"


def extended_no_laserstream_status(config: OfficialLifecycleConfig, *, target_crossed_20k: int | None = None) -> dict[str, Any]:
    status = official_lifecycle_status(config, target_crossed_20k=target_crossed_20k)
    provisional = _read_jsonl(config.provisional_births_path)
    hydration = _read_jsonl(config.hydration_results_path)
    stale = _read_jsonl(config.stale_births_path)
    births = _read_jsonl(config.births_path)
    observed_latencies = [_num(row.get("observed_to_first_followup_seconds")) for row in births]
    observed_latencies = [value for value in observed_latencies if value is not None]
    chain_latencies = [_num(row.get("chain_create_to_first_followup_seconds") or row.get("create_to_first_followup_seconds")) for row in births]
    chain_latencies = [value for value in chain_latencies if value is not None]
    status.update(
        {
            "provisional_birth_logs": len({row.get("signature") for row in provisional if row.get("signature")}),
            "hydrated_confirmed_creates": len(
                {
                    row.get("signature")
                    for row in hydration
                    if row.get("signature") and row.get("hydration_status") in {HYDRATION_CONFIRMED, HYDRATION_OFFICIAL}
                }
            ),
            "stale_or_quarantined_births": len(stale),
            "stale_rate": _safe_rate(_late_stale_count(config), _confirmed_create_count(config)),
            "median_observed_to_first_followup": median(observed_latencies) if observed_latencies else None,
            "max_observed_to_first_followup": max(observed_latencies) if observed_latencies else None,
            "median_chain_create_to_first_followup": median(chain_latencies) if chain_latencies else None,
            "max_chain_create_to_first_followup": max(chain_latencies) if chain_latencies else None,
            "hydration_queue_size": _read_status_field(config, "hydration_queue_size", 0),
            "followup_queue_size": _read_status_field(config, "followup_queue_size", 0),
            "readiness_classification": no_laserstream_readiness(config, status=status),
        }
    )
    return status


def format_no_laserstream_status(status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## No-LaserStream Official Lifecycle Watch v1",
            f"Provisional birth logs: {status.get('provisional_birth_logs', 0)}",
            f"Hydrated confirmed creates: {status.get('hydrated_confirmed_creates', 0)}",
            f"Official under-5 accepted births: {status.get('fresh_births_under_5s_followup', 0)}",
            f"Stale/quarantined births: {status.get('stale_or_quarantined_births', 0)}",
            f"Stale rate: {status.get('stale_rate')}",
            f"Median observed-to-first-followup: {status.get('median_observed_to_first_followup')}",
            f"Max observed-to-first-followup: {status.get('max_observed_to_first_followup')}",
            f"Median chain-create-to-first-followup: {status.get('median_chain_create_to_first_followup')}",
            f"Max chain-create-to-first-followup: {status.get('max_chain_create_to_first_followup')}",
            f"FDV path evidence: {status.get('births_with_fdv_path', 0)}",
            f"Crossed 10k: {status.get('crossed_10k', 0)}",
            f"Crossed 20k: {status.get('crossed_20k', 0)}",
            f"Trigger-qualified active watches: {status.get('trigger_qualified_active_watches', 0)}",
            f"Matured: {status.get('matured_trigger_qualified', 0)}",
            f"Reached 50k / 100k / 500k / 1M: {status.get('reached_50k', 0)} / {status.get('reached_100k', 0)} / {status.get('reached_500k', 0)} / {status.get('reached_1m', 0)}",
            f"Warnings: {status.get('warnings', [])}",
            f"Credits used: {status.get('credits_used', 0)}",
            f"Active watchers: {status.get('trigger_qualified_active_watches', 0)}",
            f"Hydration queue size: {status.get('hydration_queue_size', 0)}",
            f"Follow-up queue size: {status.get('followup_queue_size', 0)}",
            f"Quality status: {status.get('quality_status')}",
            f"Readiness classification: {status.get('readiness_classification')}",
            f"Recommendation: {status.get('recommendation')}",
        ]
    )


def _create_log_record_from_payload(payload: dict[str, Any], *, signature: str, observed_at: float) -> dict[str, Any]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = params.get("result") if isinstance(params.get("result"), dict) else {}
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    return {
        "signature": signature,
        "program_id": PUMP_FUN_PROGRAM_ID,
        "log_observed_at": observed_at,
        "slot": context.get("slot"),
        "block_time": value.get("blockTime") or value.get("block_time"),
        "logs": value.get("logs") if isinstance(value.get("logs"), list) else [],
        "source_adapter": "helius_pumpfun_no_laserstream_logs",
        "raw_payload": payload,
    }


def _provisional_birth_row(raw_log: dict[str, Any], *, now_fn: Callable[[], float]) -> dict[str, Any]:
    signature = str(raw_log.get("signature") or "")
    observed = _num(raw_log.get("log_observed_at")) or now_fn()
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "provisional_birth_id": f"provisional-{signature[:16]}-{int(observed * 1000)}",
        "signature": signature,
        "program_id": raw_log.get("program_id") or PUMP_FUN_PROGRAM_ID,
        "log_observed_at": observed,
        "slot": raw_log.get("slot"),
        "block_time": raw_log.get("block_time"),
        "source_adapter": raw_log.get("source_adapter") or "helius_pumpfun_no_laserstream_logs",
        "hydration_status": HYDRATION_PENDING,
        "hydration_started_at": now_fn(),
        "hydration_completed_at": None,
        "mint": None,
        "creator": None,
        "bonding_curve": None,
        "associated_bonding_curve": None,
        "token_name": None,
        "token_symbol": None,
        "metadata_uri": None,
        "parse_confidence": None,
        "missing_reason": None,
        "first_followup_scheduled_at": observed,
        "first_followup_attempt_at": None,
        "official_freshness_accepted": False,
    }


def _hydration_base(provisional: dict[str, Any], *, started_at: Any) -> dict[str, Any]:
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "provisional_birth_id": provisional.get("provisional_birth_id"),
        "signature": provisional.get("signature"),
        "program_id": provisional.get("program_id") or PUMP_FUN_PROGRAM_ID,
        "log_observed_at": provisional.get("log_observed_at"),
        "slot": provisional.get("slot"),
        "block_time": provisional.get("block_time"),
        "source_adapter": provisional.get("source_adapter") or "helius_pumpfun_no_laserstream_logs",
        "hydration_started_at": started_at,
        "hydration_completed_at": time.time(),
    }


def _merge_provisional_context(provisional: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    for key in [
        "provisional_birth_id",
        "signature",
        "program_id",
        "log_observed_at",
        "slot",
        "block_time",
        "source_adapter",
        "hydration_started_at",
    ]:
        if merged.get(key) is None and provisional.get(key) is not None:
            merged[key] = provisional.get(key)
    if merged.get("hydration_completed_at") is None:
        merged["hydration_completed_at"] = time.time()
    return merged


def _official_birth_row(
    hydration: dict[str, Any],
    candidate: dict[str, Any],
    *,
    first_attempt: float,
    first_fdv: float | None,
    events: list[dict[str, Any]],
    config: OfficialLifecycleConfig,
) -> dict[str, Any]:
    observed = _num(hydration.get("log_observed_at"))
    chain_create_time = _num(candidate.get("launch_time") or candidate.get("block_time") or hydration.get("block_time"))
    mint = _mint(candidate) or str(hydration.get("mint") or "")
    return {
        "observation_id": candidate.get("observation_id") or f"official-birth-{mint[:12]}-{int(first_attempt)}",
        "mint": mint,
        "creator": candidate.get("creator") or hydration.get("creator"),
        "create_signature": hydration.get("signature"),
        "pool_address": candidate.get("pool_address") or candidate.get("bonding_curve") or hydration.get("bonding_curve"),
        "bonding_curve": candidate.get("bonding_curve") or candidate.get("pool_address") or hydration.get("bonding_curve"),
        "associated_bonding_curve": candidate.get("associated_bonding_curve") or hydration.get("associated_bonding_curve"),
        "create_time": chain_create_time,
        "observed_time": observed,
        "first_followup_scheduled_at": observed,
        "first_followup_attempt_time": first_attempt,
        "first_followup_attempt_at": first_attempt,
        "create_to_first_followup_seconds": _delta(chain_create_time, first_attempt),
        "chain_create_to_first_followup_seconds": _delta(chain_create_time, first_attempt),
        "observed_to_first_followup_seconds": _delta(observed, first_attempt),
        "first_followup_blocked_by_missing_mint": False,
        "first_followup_before_any_trade_if_known": len(events) == 0,
        "first_followup_before_10k": first_fdv is None or first_fdv < TARGET_LEVELS["10k"],
        "first_followup_before_20k": first_fdv is None or first_fdv < TARGET_LEVELS["20k"],
        "official_freshness_accepted": True,
        "account_watch_started_at": first_attempt,
        "account_watch_source": "targeted_rpc_polling",
        "last_account_update_at": first_attempt if events else None,
        "last_signature_seen": next((event.get("signature") for event in events if event.get("signature")), None),
        "followup_path_rows": sum(1 for event in events if safe_float(event.get("fdv_proxy")) is not None),
        "fdv_path_available": any(safe_float(event.get("fdv_proxy")) is not None for event in events),
        "active_watch_state": "birth_watch",
        "source_provenance": "helius_pumpfun_no_laserstream_logs",
        "max_birth_to_first_followup_seconds": config.max_birth_to_first_followup_seconds,
    }


def _stale_from_hydration(
    hydration: dict[str, Any],
    *,
    first_attempt: float | None = None,
    reason: str = "observed_to_first_followup_exceeded_5s_freshness_gate",
) -> dict[str, Any]:
    observed = _num(hydration.get("log_observed_at"))
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "provisional_birth_id": hydration.get("provisional_birth_id"),
        "signature": hydration.get("signature"),
        "mint": hydration.get("mint"),
        "creator": hydration.get("creator"),
        "create_signature": hydration.get("signature"),
        "create_time": hydration.get("block_time"),
        "observed_time": observed,
        "first_followup_attempt_time": first_attempt,
        "observed_to_first_followup_seconds": _delta(observed, first_attempt),
        "hydration_status": hydration.get("hydration_status"),
        "stale_reason": reason,
        "rejection_reason": reason,
        "is_late_confirmed_create": hydration.get("hydration_status") == HYDRATION_CONFIRMED
        and reason == "observed_to_first_followup_exceeded_5s_freshness_gate",
        "source_provenance": "helius_pumpfun_no_laserstream_logs",
    }


def _metadata_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_name": candidate.get("token_name") or candidate.get("name"),
        "token_symbol": candidate.get("token_symbol") or candidate.get("symbol"),
        "metadata_uri": candidate.get("metadata_uri") or candidate.get("uri"),
    }


def _holder_snapshot_from_event(event: dict[str, Any], path: dict[str, Any]) -> dict[str, Any] | None:
    fdv = safe_float(path.get("fdv_proxy"))
    if fdv is None:
        return None
    level = _snapshot_level(fdv, path.get("state"))
    if level is None:
        return None
    holder_count = (
        safe_float(event.get("holder_count_proxy"))
        or safe_float(event.get("holder_count"))
        or safe_float(event.get("active_wallet_count"))
        or safe_float(event.get("active_wallets"))
    )
    top_holder = safe_float(event.get("top_holder_share_proxy"))
    top_10 = safe_float(event.get("top_10_holder_share_proxy"))
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "mint": path.get("mint"),
        "snapshot_level": level,
        "snapshot_time": path.get("timestamp"),
        "fdv_proxy": fdv,
        "holder_count_proxy": holder_count,
        "top_holder_share_proxy": top_holder,
        "top_10_holder_share_proxy": top_10,
        "holder_snapshot_source": "observed_followup_event_proxy",
        "holder_snapshot_confidence": "proxy" if holder_count is not None else "missing",
        "holder_snapshot_missing_reason": None if holder_count is not None else "holder_proxy_not_available_from_followup_event",
        "not_full_chain_holder_state": True,
    }


def _snapshot_level(fdv: float, state: Any) -> str | None:
    for label in ["1m", "500k", "100k", "50k", "20k", "10k"]:
        if fdv >= TARGET_LEVELS[label]:
            return label
    if str(state or "").startswith("matured_"):
        return "maturity"
    return None


def _bottleneck_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# No-LaserStream Bottleneck Audit",
        "",
        f"Report ID: `{audit['report_id']}`",
        "",
        "## Current Bottleneck",
    ]
    for key, value in audit["current_v1_bottleneck"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## V2 Target Architecture"])
    for key, value in audit["v2_target_architecture"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Outputs"])
    for key, value in audit["outputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", f"Recommendation: {audit['recommendation']}", ""])
    return "\n".join(lines)


def _read_status_field(config: OfficialLifecycleConfig, key: str, default: Any) -> Any:
    if not config.status_path.exists():
        return default
    try:
        payload = json.loads(config.status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return payload.get(key, default) if isinstance(payload, dict) else default


def _late_stale_count(config: OfficialLifecycleConfig) -> int:
    return len(
        {
            row.get("signature")
            for row in _read_jsonl(config.stale_births_path)
            if row.get("signature")
            and (
                row.get("is_late_confirmed_create") is True
                or (
                    row.get("hydration_status") == HYDRATION_CONFIRMED
                    and row.get("stale_reason") == "observed_to_first_followup_exceeded_5s_freshness_gate"
                )
            )
        }
    )


def _confirmed_create_count(config: OfficialLifecycleConfig) -> int:
    hydration = _read_jsonl(config.hydration_results_path)
    signatures = {
        row.get("signature")
        for row in hydration
        if row.get("signature") and row.get("hydration_status") in {HYDRATION_CONFIRMED, HYDRATION_OFFICIAL, HYDRATION_STALE}
    }
    return len(signatures)


def _requests_used(*objects: Any) -> int:
    return sum(int(getattr(obj, "requests_used", 0) or 0) for obj in objects)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _websocket_connect(*args: Any, **kwargs: Any) -> Any:
    from websockets.sync.client import connect

    return connect(*args, **kwargs)
