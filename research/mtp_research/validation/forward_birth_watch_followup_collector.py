"""Bounded follow-up collector for Pump.fun birth-watch mints.

The collector is read-only against chain data and writes observation rows only.
It does not trade, validate, backtest, optimize, or generate strategy logic.
"""

from __future__ import annotations

from collections import deque
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from research.mtp_research.validation.forward_efficient_mover_observer import (
    OUTPUT_FILES,
    PUMP_FUN_PROGRAM_ID,
    RAW_SOURCE_FILES,
    ForwardObserverConfig,
    PumpFunCreateScannerCandidateSource,
    append_jsonl,
    build_birth_watch_candidate_from_create_candidate,
    build_live_event_candidate,
    build_observation_rows,
    guardrails,
    normalize_pumpfun_transaction_event,
    read_jsonl,
    resolve_forward_sol_usd_price,
    resolve_helius_rpc_url,
    safe_float,
    _post_json_rpc,
)
from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner


REPORT_ID = "forward_birth_watch_followup_collector_v0"
REPORT_DIR = "birth_watch_followup_collector"
SUMMARY_JSON = "birth_watch_followup_collection_summary.json"
SUMMARY_MD = "birth_watch_followup_collection_summary.md"
RAW_FOLLOWUP_FILE = "helius_birth_watch_followup_raw.jsonl"
BIRTH_WATCH_MINTS_FILE = "birth_watch_mints.jsonl"
BIRTH_FOLLOWUP_PATHS_FILE = "birth_followup_paths.jsonl"
BIRTH_FOLLOWUP_EVENTS_FILE = "birth_followup_events.jsonl"
BIRTH_FOLLOWUP_STATUS_FILE = "birth_followup_status.json"


class BirthWatchCandidateSource(Protocol):
    def availability(self) -> dict[str, Any]:
        ...

    def fetch_candidates(self) -> list[dict[str, Any]]:
        ...


class BirthWatchFollowupFetcher(Protocol):
    requests_used: int
    raw_transactions: list[dict[str, Any]]

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
        followup_addresses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        ...


@dataclass
class BirthWatchTarget:
    observation_id: str
    mint: str
    observed_at: float | None
    launch_time: float | None
    creator: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "mint": self.mint,
            "observed_at": self.observed_at,
            "launch_time": self.launch_time,
            "creator": self.creator,
        }


class MockBirthWatchFollowupFetcher:
    def __init__(self, events_by_mint: dict[str, list[dict[str, Any]]], *, requests_used: int = 0) -> None:
        self.events_by_mint = {mint: [dict(row) for row in rows] for mint, rows in events_by_mint.items()}
        self.requests_used = requests_used
        self.raw_transactions: list[dict[str, Any]] = []
        self.fetch_calls = 0

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
        followup_addresses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        return [dict(row) for row in self.events_by_mint.get(mint, [])[:transactions_per_mint]]


class MockBirthWatchCandidateSource:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = [dict(row) for row in candidates]
        self.requests_used = 0
        self.fetch_calls = 0

    def availability(self) -> dict[str, Any]:
        return {"source": "mock_birth_watch_candidate_source", "available": True, "read_only": True}

    def fetch_candidates(self) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        return [dict(row) for row in self.candidates]


def rpc_url_to_websocket_url(rpc_url: str | None) -> str | None:
    if not rpc_url:
        return None
    if rpc_url.startswith("https://"):
        return "wss://" + rpc_url[len("https://") :]
    if rpc_url.startswith("http://"):
        return "ws://" + rpc_url[len("http://") :]
    if rpc_url.startswith("wss://") or rpc_url.startswith("ws://"):
        return rpc_url
    return None


class PumpFunCreateWebSocketCandidateSource:
    source_name = "helius_websocket_logs"

    def __init__(
        self,
        config: ForwardObserverConfig | None = None,
        *,
        rpc_url: str | None = None,
        websocket_url: str | None = None,
        timeout_seconds: float = 10.0,
        max_signatures_per_fetch: int = 50,
        rpc_post: Any | None = None,
        ws_connect: Any | None = None,
        scanner: PumpFunCreateScanner | None = None,
    ) -> None:
        self.config = config
        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self.websocket_url = websocket_url or rpc_url_to_websocket_url(self.rpc_url)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.max_signatures_per_fetch = max(1, int(max_signatures_per_fetch))
        self._rpc_post = rpc_post or _post_json_rpc
        self._ws_connect = ws_connect
        self.scanner = scanner or PumpFunCreateScanner()
        self._requests_used = 0
        self.processed_signatures: set[str] = set()
        self._lock = threading.Lock()
        self._signature_queue: deque[str] = deque()
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()
        self._listener_errors = 0

    @property
    def requests_used(self) -> int:
        with self._lock:
            return self._requests_used

    def load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with self._lock:
            self.processed_signatures = {
                str(signature) for signature in checkpoint.get("birth_ws_processed_signatures", []) if signature
            }

    def checkpoint_updates(self) -> dict[str, Any]:
        with self._lock:
            return {"birth_ws_processed_signatures": sorted(self.processed_signatures)}

    def close(self) -> None:
        self._listener_stop.set()
        thread = self._listener_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def availability(self) -> dict[str, Any]:
        if not self.websocket_url or not self.rpc_url:
            return {
                "source": self.source_name,
                "available": False,
                "read_only": True,
                "missing_reason": "live_source_blocked_no_helius_config",
                "source_adapter": "helius_pumpfun_create_websocket_logs",
            }
        return {
            "source": self.source_name,
            "available": True,
            "read_only": True,
            "source_adapter": "helius_pumpfun_create_websocket_logs",
            "candidate_lane": "pumpfun_birth_watch",
            "timeout_seconds": self.timeout_seconds,
            "listener_mode": "persistent_signature_queue",
        }

    def fetch_candidates(self) -> list[dict[str, Any]]:
        if not self.websocket_url or not self.rpc_url:
            return []
        self._ensure_listener_started()
        deadline = time.monotonic() + self.timeout_seconds
        while not self._has_queued_signatures() and time.monotonic() < deadline:
            time.sleep(min(0.05, max(0.01, self.timeout_seconds)))
        if self._has_queued_signatures():
            # Allow same-burst create notifications to land before hydrating.
            settle_deadline = time.monotonic() + min(0.2, self.timeout_seconds)
            while time.monotonic() < settle_deadline and self._queued_signature_count() < self.max_signatures_per_fetch:
                time.sleep(0.01)
        create_signatures = self._drain_signatures()
        candidates: list[dict[str, Any]] = []
        for signature in create_signatures:
            candidate = self._candidate_from_signature(signature)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _ensure_listener_started(self) -> None:
        with self._lock:
            if self._listener_thread is not None and self._listener_thread.is_alive():
                return
            self._listener_stop.clear()
            self._listener_thread = threading.Thread(
                target=self._listen_for_create_signatures,
                name="mtp-pumpfun-create-listener",
                daemon=True,
            )
            self._listener_thread.start()

    def _listen_for_create_signatures(self) -> None:
        connect = self._ws_connect or _websocket_connect
        while not self._listener_stop.is_set():
            subscription_id: int | None = None
            try:
                with connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                    self._increment_requests()
                    websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "mtp-pumpfun-create-logs-subscribe",
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
                            time.sleep(0.01)
                            continue
                        payload = json.loads(message) if isinstance(message, str) else message
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("id") == "mtp-pumpfun-create-logs-subscribe":
                            subscription_id = payload.get("result") if isinstance(payload.get("result"), int) else None
                            continue
                        signature = signature_from_create_logs_notification(payload)
                        if not signature:
                            continue
                        with self._lock:
                            if signature in self.processed_signatures:
                                continue
                            self.processed_signatures.add(signature)
                            self._signature_queue.append(signature)
                    if subscription_id is not None:
                        websocket.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": "mtp-pumpfun-create-logs-unsubscribe",
                                    "method": "logsUnsubscribe",
                                    "params": [subscription_id],
                                }
                            )
                        )
            except Exception:
                with self._lock:
                    self._listener_errors += 1
                time.sleep(min(1.0, self.timeout_seconds))

    def _increment_requests(self, count: int = 1) -> None:
        with self._lock:
            self._requests_used += int(count)

    def _has_queued_signatures(self) -> bool:
        with self._lock:
            return bool(self._signature_queue)

    def _queued_signature_count(self) -> int:
        with self._lock:
            return len(self._signature_queue)

    def _drain_signatures(self) -> list[str]:
        signatures: list[str] = []
        with self._lock:
            while self._signature_queue and len(signatures) < self.max_signatures_per_fetch:
                signatures.append(self._signature_queue.popleft())
        return signatures

    def _legacy_fetch_candidates(self) -> list[dict[str, Any]]:
        if not self.websocket_url or not self.rpc_url:
            return []
        connect = self._ws_connect or _websocket_connect
        deadline = time.monotonic() + self.timeout_seconds
        candidates: list[dict[str, Any]] = []
        create_signatures: list[str] = []
        subscription_id: int | None = None
        try:
            with connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                self._increment_requests()
                websocket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "mtp-pumpfun-create-logs-subscribe",
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [PUMP_FUN_PROGRAM_ID]},
                                {"commitment": "processed"},
                            ],
                        }
                    )
                )
                while time.monotonic() < deadline:
                    remaining = max(0.1, deadline - time.monotonic())
                    try:
                        message = websocket.recv(timeout=remaining)
                    except TimeoutError:
                        break
                    payload = json.loads(message) if isinstance(message, str) else message
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("id") == "mtp-pumpfun-create-logs-subscribe":
                        subscription_id = payload.get("result") if isinstance(payload.get("result"), int) else None
                        continue
                    signature = signature_from_create_logs_notification(payload)
                    if not signature or signature in self.processed_signatures:
                        continue
                    self.processed_signatures.add(signature)
                    create_signatures.append(signature)
                if subscription_id is not None:
                    websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "mtp-pumpfun-create-logs-unsubscribe",
                                "method": "logsUnsubscribe",
                                "params": [subscription_id],
                            }
                        )
                    )
        except Exception:
            return candidates
        for signature in create_signatures:
            candidate = self._candidate_from_signature(signature)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _candidate_from_signature(self, signature: str) -> dict[str, Any] | None:
        tx = self._fetch_transaction(signature)
        if not tx:
            return None
        candidates, _rejected, _unknown, _direct_count = self.scanner._extract_candidates(
            [tx],
            remaining_target=1,
            include_low_confidence=False,
            min_confidence="medium",
        )
        if not candidates:
            return None
        candidate = build_birth_watch_candidate_from_create_candidate(candidates[0])
        candidate["observed_at"] = time.time()
        candidate["source"] = "helius_program_logs_pumpfun_create_websocket"
        candidate["source_adapter"] = "helius_pumpfun_create_websocket_logs"
        return candidate

    def _fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-pumpfun-create-ws-get-transaction",
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
        response = self._rpc_post(self.rpc_url, payload, 10)
        self._increment_requests()
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}


def _websocket_connect(*args: Any, **kwargs: Any) -> Any:
    from websockets.sync.client import connect

    return connect(*args, **kwargs)


def signature_from_create_logs_notification(payload: dict[str, Any]) -> str | None:
    if payload.get("method") != "logsNotification":
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = params.get("result") if isinstance(params.get("result"), dict) else {}
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    if value.get("err") is not None:
        return None
    logs = value.get("logs") if isinstance(value.get("logs"), list) else []
    normalized_logs = [str(log).lower() for log in logs]
    if not any("instruction: create" in log or "instruction: createv2" in log for log in normalized_logs):
        return None
    signature = value.get("signature")
    return str(signature) if signature else None


class HeliusMintBirthWatchFollowupFetcher:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        timeout_sec: int = 10,
        rpc_post: Any | None = None,
        data_root: Path | str | None = None,
    ) -> None:
        self.rpc_url = rpc_url or resolve_helius_rpc_url()
        self.timeout_sec = timeout_sec
        self._rpc_post = rpc_post or _post_json_rpc
        self.valuation_supply_proxy = 1_000_000_000.0
        self.sol_usd_price = resolve_forward_sol_usd_price(data_root)
        self.requests_used = 0
        self.raw_transactions: list[dict[str, Any]] = []
        self.seen_signatures: set[str] = set()

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
        followup_addresses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.rpc_url:
            return []
        signatures = self._fetch_signatures_for_addresses(mint, followup_addresses or [], signatures_per_mint)
        events: list[dict[str, Any]] = []
        for signature in signatures[: max(0, int(transactions_per_mint))]:
            if signature in self.seen_signatures:
                continue
            self.seen_signatures.add(signature)
            tx = self._fetch_transaction(signature)
            if not tx:
                continue
            self.raw_transactions.append(tx)
            event = normalize_pumpfun_transaction_event(
                tx,
                source_adapter="helius_birth_watch_followup",
                program_id=PUMP_FUN_PROGRAM_ID,
                valuation_supply_proxy=self.valuation_supply_proxy,
                sol_usd_price=self.sol_usd_price,
            )
            candidate = build_live_event_candidate(event, include_birth_watch_candidates=False)
            if candidate and str(candidate.get("mint") or candidate.get("token_mint")) == mint and safe_float(candidate.get("fdv_proxy")) is not None:
                candidate["source"] = "helius_birth_watch_followup"
                candidate["freshness_lane"] = "birth_watch"
                candidate["candidate_classification"] = "pumpfun_birth_watch_fdv_followup_observed"
                candidate["status"] = "active"
                events.append(candidate)
        return events

    def _fetch_signatures_for_addresses(self, mint: str, followup_addresses: list[str], limit: int) -> list[str]:
        signatures: list[str] = []
        seen_addresses: set[str] = set()
        seen_signatures: set[str] = set()
        for address in [mint, *followup_addresses]:
            if not address or address in seen_addresses:
                continue
            seen_addresses.add(address)
            for signature in self._fetch_signatures(address, limit):
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                signatures.append(signature)
        return signatures

    def _fetch_signatures(self, mint: str, limit: int) -> list[str]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-birth-watch-followup-get-signatures",
            "method": "getSignaturesForAddress",
            "params": [mint, {"limit": max(1, min(int(limit), 100))}],
        }
        self.requests_used += 1
        try:
            response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        except TimeoutError:
            return []
        rows = response.get("result") if isinstance(response, dict) else None
        if not isinstance(rows, list):
            return []
        return [str(row.get("signature")) for row in rows if isinstance(row, dict) and row.get("signature")]

    def _fetch_transaction(self, signature: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-birth-watch-followup-get-transaction",
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        self.requests_used += 1
        try:
            response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        except TimeoutError:
            return {}
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}


def build_birth_watch_followup_plan(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    max_mints: int = 10,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    request_ceiling: int = 250,
    freshness_run_id: str | None = None,
) -> dict[str, Any]:
    root = Path(data_root).expanduser()
    targets = _select_targets(root, max_mints=max_mints, freshness_run_id=freshness_run_id)
    projected_requests = len(targets) * (1 + max(0, min(int(signatures_per_mint), int(transactions_per_mint))))
    return {
        "report_id": REPORT_ID,
        "execute": False,
        "data_root": str(root),
        "observation_root": str(_observation_root(root)),
        "freshness_run_id": freshness_run_id,
        "selected_mint_count": len(targets),
        "selected_targets": [target.to_dict() for target in targets],
        "signatures_per_mint": int(signatures_per_mint),
        "transactions_per_mint": int(transactions_per_mint),
        "projected_requests": projected_requests,
        "request_ceiling": int(request_ceiling),
        "request_ceiling_status": "within_ceiling" if projected_requests <= int(request_ceiling) else "exceeds_ceiling",
        "network_calls_made": 0,
        "guardrails": guardrails(),
    }


def run_birth_watch_followup_collection(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    max_mints: int = 10,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    request_ceiling: int = 250,
    freshness_run_id: str | None = None,
    execute: bool = False,
    fetcher: BirthWatchFollowupFetcher | None = None,
    observed_at: int | None = None,
) -> dict[str, Any]:
    root = Path(data_root).expanduser()
    config = ForwardObserverConfig(data_root=root)
    config.observation_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    plan = build_birth_watch_followup_plan(
        root,
        max_mints=max_mints,
        signatures_per_mint=signatures_per_mint,
        transactions_per_mint=transactions_per_mint,
        request_ceiling=request_ceiling,
        freshness_run_id=freshness_run_id,
    )
    result = {
        **plan,
        "execute": bool(execute),
        "rows_written": 0,
        "path_rows_written": 0,
        "event_rows_written": 0,
        "metadata_rows_written": 0,
        "holder_rows_written": 0,
        "drawdown_rows_written": 0,
        "raw_transactions_written": 0,
        "mints_with_fdv_followup": 0,
        "mints_with_trigger_followup": 0,
        "warnings": [],
    }
    if not execute:
        _write_report(config, result)
        return result
    if plan["request_ceiling_status"] != "within_ceiling":
        result["warnings"].append("projected_requests_exceed_request_ceiling")
        _write_report(config, result)
        return result
    selected_fetcher = fetcher or HeliusMintBirthWatchFollowupFetcher(data_root=root)
    start_requests = int(getattr(selected_fetcher, "requests_used", 0))
    fdv_mints: set[str] = set()
    trigger_mints: set[str] = set()
    now = int(observed_at or time.time())
    for target_payload in plan["selected_targets"]:
        target = BirthWatchTarget(**target_payload)
        events = selected_fetcher.fetch_for_mint(
            target.mint,
            signatures_per_mint=signatures_per_mint,
            transactions_per_mint=transactions_per_mint,
        )
        rows_to_write = []
        for event in events:
            fdv = safe_float(event.get("fdv_proxy"))
            if fdv is None:
                continue
            event = {
                **event,
                "mint": target.mint,
                "token_mint": target.mint,
                "freshness_lane": "birth_watch",
                "source": event.get("source") or "helius_birth_watch_followup",
                "event_type": event.get("event_type") or "pumpfun_trade",
            }
            rows = build_observation_rows(
                event,
                start_trigger=10_000.0,
                observation_id=target.observation_id,
                observed_at=now,
            )
            rows_to_write.append(rows)
            fdv_mints.add(target.mint)
            if fdv >= 10_000.0:
                trigger_mints.add(target.mint)
        for rows in rows_to_write:
            append_jsonl(config.observation_root / OUTPUT_FILES["paths"], [rows["path"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["events"], rows["events"])
            append_jsonl(config.observation_root / OUTPUT_FILES["metadata"], [rows["metadata"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["holders"], [rows["holders"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["drawdowns"], [rows["drawdown"]])
            result["path_rows_written"] += 1
            result["event_rows_written"] += len(rows["events"])
            result["metadata_rows_written"] += 1
            result["holder_rows_written"] += 1
            result["drawdown_rows_written"] += 1
    raw_transactions = list(getattr(selected_fetcher, "raw_transactions", []))
    if raw_transactions:
        append_jsonl(config.raw_root / RAW_FOLLOWUP_FILE, raw_transactions)
        result["raw_transactions_written"] = len(raw_transactions)
    result["network_calls_made"] = max(0, int(getattr(selected_fetcher, "requests_used", 0)) - start_requests)
    result["mints_with_fdv_followup"] = len(fdv_mints)
    result["mints_with_trigger_followup"] = len(trigger_mints)
    result["rows_written"] = (
        result["path_rows_written"]
        + result["event_rows_written"]
        + result["metadata_rows_written"]
        + result["holder_rows_written"]
        + result["drawdown_rows_written"]
    )
    if result["network_calls_made"] > int(request_ceiling):
        result["warnings"].append("actual_requests_exceeded_request_ceiling")
    _write_report(config, result)
    return result


def run_immediate_birth_followup_observation(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    target_births: int = 25,
    followup_duration_seconds: int = 120,
    first_pass_delay_seconds: float = 0.0,
    followup_poll_seconds: float = 2.0,
    max_followup_passes_per_mint: int = 60,
    max_active_birth_followups: int = 100,
    max_runtime_minutes: int = 30,
    max_helius_credits: int = 50_000,
    birth_candidate_source_method: str = "websocket_logs",
    birth_scan_max_batches: int = 1,
    birth_scan_signatures_per_batch: int = 10,
    birth_scan_hydrate_limit_per_batch: int = 10,
    birth_scan_max_signatures_total: int = 10,
    birth_scan_min_confidence: str = "medium",
    birth_scan_cursor_before: str | None = None,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    execute: bool = False,
    candidate_source: BirthWatchCandidateSource | None = None,
    fetcher: BirthWatchFollowupFetcher | None = None,
    freshness_run_id: str | None = None,
    time_fn: Any | None = None,
    sleep_fn: Any | None = None,
) -> dict[str, Any]:
    root = Path(data_root).expanduser()
    config = ForwardObserverConfig(
        data_root=root,
        source="helius-pumpfun-create-scanner",
        target_candidates=target_births,
        max_runtime_minutes=max_runtime_minutes,
        max_helius_credits=max_helius_credits,
        enable_birth_watch_candidates=True,
        birth_scan_max_batches=birth_scan_max_batches,
        birth_scan_signatures_per_batch=birth_scan_signatures_per_batch,
        birth_scan_hydrate_limit_per_batch=birth_scan_hydrate_limit_per_batch,
        birth_scan_target_create_candidates=target_births,
        birth_scan_max_signatures_total=birth_scan_max_signatures_total,
        birth_scan_min_confidence=birth_scan_min_confidence,
        birth_scan_cursor_before=birth_scan_cursor_before,
    )
    config.observation_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    now_fn = time_fn or time.time
    sleeper = sleep_fn or time.sleep
    run_id = freshness_run_id or f"birth-followup-{int(time.time())}"
    if candidate_source is not None:
        source = candidate_source
    elif birth_candidate_source_method == "websocket_logs":
        source = PumpFunCreateWebSocketCandidateSource(config)
    else:
        source = PumpFunCreateScannerCandidateSource(config)
    checkpoint_path = config.observation_root / OUTPUT_FILES["checkpoint"]
    checkpoint = {}
    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            checkpoint = {}
    if hasattr(source, "load_checkpoint"):
        source.load_checkpoint(checkpoint)
    source_availability = source.availability()
    result: dict[str, Any] = {
        "report_id": "forward_birth_watch_immediate_followup_v0",
        "execute": bool(execute),
        "mode": "observe-births-with-immediate-followup",
        "data_root": str(root),
        "observation_root": str(config.observation_root),
        "target_births": int(target_births),
        "followup_duration_seconds": int(followup_duration_seconds),
        "followup_poll_seconds": float(followup_poll_seconds),
        "max_followup_passes_per_mint": int(max_followup_passes_per_mint),
        "max_active_birth_followups": int(max_active_birth_followups),
        "max_runtime_minutes": int(max_runtime_minutes),
        "max_helius_credits": int(max_helius_credits),
        "birth_candidate_source_method": birth_candidate_source_method,
        "freshness_run_id": run_id,
        "birth_scan_max_batches": int(birth_scan_max_batches),
        "birth_scan_signatures_per_batch": int(birth_scan_signatures_per_batch),
        "birth_scan_hydrate_limit_per_batch": int(birth_scan_hydrate_limit_per_batch),
        "birth_scan_max_signatures_total": int(birth_scan_max_signatures_total),
        "birth_scan_min_confidence": birth_scan_min_confidence,
        "source_availability": source_availability,
        "smoke_birth_count": 0,
        "immediate_followup_started_count": 0,
        "first_followup_path_rows": 0,
        "true_near_birth_observed_count": 0,
        "first_followup_before_10k_count": 0,
        "first_followup_before_any_trade_if_known_count": 0,
        "first_followup_before_20k_count": 0,
        "first_followup_after_activity_count": 0,
        "first_followup_already_above_10k_count": 0,
        "first_followup_already_above_20k_count": 0,
        "crossed_10k_count": 0,
        "crossed_20k_count": 0,
        "trigger_qualified_true_near_birth_mints": 0,
        "target_trigger_qualified_true_near_birth_mints": 300,
        "network_calls_made": 0,
        "estimated_helius_credits_used": 0,
        "warnings": [],
        "guardrails": guardrails(),
        "output_files": {
            "birth_watch_mints": str(config.observation_root / BIRTH_WATCH_MINTS_FILE),
            "birth_followup_paths": str(config.observation_root / BIRTH_FOLLOWUP_PATHS_FILE),
            "birth_followup_events": str(config.observation_root / BIRTH_FOLLOWUP_EVENTS_FILE),
            "birth_followup_status": str(config.observation_root / BIRTH_FOLLOWUP_STATUS_FILE),
        },
    }
    if not execute:
        result["readiness_classification"] = (
            "freshness_repair_ready_for_100_birth_smoke" if source_availability.get("available") else "freshness_repair_blocked"
        )
        _write_immediate_status(config, result)
        return result
    if not source_availability.get("available"):
        result["warnings"].append("birth_candidate_source_unavailable")
        result["readiness_classification"] = "freshness_repair_blocked"
        _write_immediate_status(config, result)
        return result

    selected_fetcher = fetcher or HeliusMintBirthWatchFollowupFetcher(data_root=root)
    start_monotonic = time.monotonic()
    overall_deadline = start_monotonic + max(0, int(max_runtime_minutes)) * 60
    seen_mints = {
        str(row.get("mint") or row.get("token_mint") or "")
        for row in read_jsonl(config.observation_root / BIRTH_WATCH_MINTS_FILE)
        if row.get("mint") or row.get("token_mint")
    }
    seen_mints.update(
        str(row.get("mint") or row.get("token_mint") or "")
        for row in read_jsonl(config.observation_root / OUTPUT_FILES["candidates"])
        if row.get("mint") or row.get("token_mint")
    )
    while result["smoke_birth_count"] < int(target_births):
        if time.monotonic() >= overall_deadline:
            result["warnings"].append("max_runtime_minutes_reached")
            break
        if result["network_calls_made"] >= int(max_helius_credits):
            result["warnings"].append("max_helius_credits_reached")
            break
        before_source_requests = int(getattr(source, "requests_used", 0))
        candidate_rows = [row for row in source.fetch_candidates() if _is_birth_candidate(row)]
        result["network_calls_made"] += max(0, int(getattr(source, "requests_used", 0)) - before_source_requests)
        if result["network_calls_made"] >= int(max_helius_credits):
            result["warnings"].append("max_helius_credits_reached")
            break
        birth_candidates = []
        for row in candidate_rows:
            mint = str(row.get("mint") or row.get("token_mint") or "")
            if not mint or mint in seen_mints:
                continue
            birth_candidates.append(row)
            seen_mints.add(mint)
            if len(birth_candidates) >= max(0, min(int(target_births) - result["smoke_birth_count"], int(max_active_birth_followups))):
                break
        if not birth_candidates:
            if followup_poll_seconds > 0:
                if time.monotonic() + followup_poll_seconds > overall_deadline:
                    result["warnings"].append("max_runtime_minutes_reached")
                    break
                sleeper(followup_poll_seconds)
            continue
        for candidate in birth_candidates:
            if time.monotonic() >= overall_deadline:
                result["warnings"].append("max_runtime_minutes_reached")
                break
            mint = str(candidate.get("mint") or candidate.get("token_mint") or "")
            if not mint:
                continue
            observation_id = str(candidate.get("observation_id") or f"birth-{mint[:12]}-{int(now_fn())}")
            create_time = safe_float(candidate.get("launch_time") or candidate.get("block_time") or candidate.get("transaction_time"))
            create_observed_at = safe_float(candidate.get("observed_at") or candidate.get("first_seen_time") or now_fn())
            birth_observed_at = int(create_observed_at or now_fn())
            birth_rows = build_observation_rows(candidate, start_trigger=10_000.0, observation_id=observation_id, observed_at=birth_observed_at)
            append_jsonl(config.observation_root / OUTPUT_FILES["candidates"], [birth_rows["candidate"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["paths"], [birth_rows["path"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["events"], birth_rows["events"])
            append_jsonl(config.observation_root / OUTPUT_FILES["metadata"], [birth_rows["metadata"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["holders"], [birth_rows["holders"]])
            append_jsonl(config.observation_root / OUTPUT_FILES["drawdowns"], [birth_rows["drawdown"]])
            append_jsonl(config.raw_root / "source_candidates.jsonl", [{**candidate, "observed_at": birth_observed_at, "observation_id": observation_id}])

            if first_pass_delay_seconds > 0:
                sleeper(first_pass_delay_seconds)
            first_attempt_time = float(now_fn())
            result["smoke_birth_count"] += 1
            result["immediate_followup_started_count"] += 1
            target = BirthWatchTarget(
                observation_id=observation_id,
                mint=mint,
                observed_at=create_observed_at,
                launch_time=create_time,
                creator=candidate.get("creator"),
            )
            first_event: dict[str, Any] | None = None
            pass_count = 0
            followup_deadline = first_attempt_time + max(0, int(followup_duration_seconds))
            while pass_count < max(1, int(max_followup_passes_per_mint)):
                if time.monotonic() >= overall_deadline:
                    result["warnings"].append("max_runtime_minutes_reached")
                    break
                if result["network_calls_made"] >= int(max_helius_credits):
                    result["warnings"].append("max_helius_credits_reached")
                    break
                pass_count += 1
                before_fetch_requests = int(getattr(selected_fetcher, "requests_used", 0))
                events = selected_fetcher.fetch_for_mint(
                    mint,
                    signatures_per_mint=signatures_per_mint,
                    transactions_per_mint=transactions_per_mint,
                )
                result["network_calls_made"] += max(0, int(getattr(selected_fetcher, "requests_used", 0)) - before_fetch_requests)
                first_event = _first_fdv_event(events, mint)
                if first_event is not None:
                    break
                if float(now_fn()) >= followup_deadline:
                    break
                if followup_poll_seconds > 0:
                    if time.monotonic() + followup_poll_seconds > overall_deadline:
                        result["warnings"].append("max_runtime_minutes_reached")
                        break
                    sleeper(followup_poll_seconds)
            freshness_record = _build_freshness_record(
                candidate=candidate,
                target=target,
                first_attempt_time=first_attempt_time,
                first_event=first_event,
                pass_count=pass_count,
                freshness_run_id=run_id,
            )
            append_jsonl(config.observation_root / BIRTH_WATCH_MINTS_FILE, [freshness_record])
            if first_event is not None:
                event = {
                    **first_event,
                    "mint": mint,
                    "token_mint": mint,
                    "freshness_lane": "birth_watch",
                    "source": first_event.get("source") or "helius_birth_watch_immediate_followup",
                    "event_type": first_event.get("event_type") or "pumpfun_trade",
                }
                observed_at = int(safe_float(event.get("block_time") or event.get("timestamp") or event.get("observed_at")) or now_fn())
                rows = build_observation_rows(event, start_trigger=10_000.0, observation_id=observation_id, observed_at=observed_at)
                rows["path"].update(_freshness_path_fields(freshness_record))
                rows["events"][0].update(_freshness_event_fields(freshness_record))
                append_jsonl(config.observation_root / OUTPUT_FILES["paths"], [rows["path"]])
                append_jsonl(config.observation_root / OUTPUT_FILES["events"], rows["events"])
                append_jsonl(config.observation_root / OUTPUT_FILES["metadata"], [rows["metadata"]])
                append_jsonl(config.observation_root / OUTPUT_FILES["holders"], [rows["holders"]])
                append_jsonl(config.observation_root / OUTPUT_FILES["drawdowns"], [rows["drawdown"]])
                append_jsonl(config.observation_root / BIRTH_FOLLOWUP_PATHS_FILE, [rows["path"]])
                append_jsonl(config.observation_root / BIRTH_FOLLOWUP_EVENTS_FILE, rows["events"])
                result["first_followup_path_rows"] += 1
            if result["smoke_birth_count"] >= int(target_births):
                break
    raw_transactions = list(getattr(selected_fetcher, "raw_transactions", []))
    if raw_transactions:
        append_jsonl(config.raw_root / RAW_FOLLOWUP_FILE, raw_transactions)
    result["estimated_helius_credits_used"] = result["network_calls_made"]
    if result["estimated_helius_credits_used"] > int(max_helius_credits):
        result["warnings"].append("max_helius_credits_exceeded")
    checkpoint_payload = {
        **checkpoint,
        "updated_at": int(time.time()),
        "immediate_followup_mode": True,
        "immediate_followup_network_calls_made": result["network_calls_made"],
    }
    if hasattr(source, "checkpoint_updates"):
        checkpoint_payload.update(source.checkpoint_updates())
    (config.observation_root / OUTPUT_FILES["checkpoint"]).write_text(
        json.dumps(checkpoint_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _update_immediate_freshness_counts(config, result)
    _write_immediate_status(config, result)
    return result


def _select_targets(root: Path, *, max_mints: int, freshness_run_id: str | None = None) -> list[BirthWatchTarget]:
    obs = _observation_root(root)
    if freshness_run_id:
        candidates = [
            row
            for row in read_jsonl(obs / BIRTH_WATCH_MINTS_FILE)
            if row.get("freshness_run_id") == freshness_run_id and (row.get("mint") or row.get("token_mint"))
        ]
    else:
        candidates = [row for row in read_jsonl(obs / "candidates.jsonl") if _is_birth_candidate(row)]
    paths_by_mint: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(obs / "candidate_paths.jsonl"):
        mint = str(row.get("mint") or row.get("token_mint") or "")
        if mint:
            paths_by_mint.setdefault(mint, []).append(row)
    targets = []
    for row in candidates:
        mint = str(row.get("mint") or row.get("token_mint") or "")
        if not mint or _has_followup_fdv(paths_by_mint.get(mint, [])):
            continue
        targets.append(
            BirthWatchTarget(
                observation_id=str(row.get("observation_id") or ""),
                mint=mint,
                observed_at=safe_float(row.get("observed_at") or row.get("first_seen_time") or row.get("create_observed_at")),
                launch_time=safe_float(row.get("launch_time") or row.get("create_time")),
                creator=row.get("creator"),
            )
        )
    targets.sort(key=lambda item: (item.observed_at if item.observed_at is not None else float("inf"), item.mint))
    return targets[: max(0, int(max_mints))]


def _first_fdv_event(events: list[dict[str, Any]], mint: str) -> dict[str, Any] | None:
    fdv_events = [
        row
        for row in events
        if str(row.get("mint") or row.get("token_mint") or "") == mint and safe_float(row.get("fdv_proxy")) is not None
    ]
    fdv_events.sort(key=lambda row: safe_float(row.get("block_time") or row.get("timestamp") or row.get("observed_at")) or float("inf"))
    return dict(fdv_events[0]) if fdv_events else None


def _build_freshness_record(
    *,
    candidate: dict[str, Any],
    target: BirthWatchTarget,
    first_attempt_time: float,
    first_event: dict[str, Any] | None,
    pass_count: int,
    freshness_run_id: str | None = None,
) -> dict[str, Any]:
    create_time = safe_float(target.launch_time or candidate.get("block_time") or candidate.get("transaction_time") or candidate.get("observed_at"))
    create_observed_at = safe_float(target.observed_at or candidate.get("observed_at") or candidate.get("first_seen_time"))
    path_time = safe_float(first_event.get("block_time") or first_event.get("timestamp") or first_event.get("observed_at")) if first_event else None
    fdv = safe_float(first_event.get("fdv_proxy")) if first_event else None
    event_count = safe_float(first_event.get("event_count")) if first_event else None
    buys = safe_float(first_event.get("buy_count")) if first_event else None
    sells = safe_float(first_event.get("sell_count")) if first_event else None
    active_wallets = safe_float(first_event.get("active_wallets")) if first_event else None
    freshness_class = _freshness_class(create_time=create_time, first_path_time=path_time, first_fdv=fdv)
    return {
        "observation_id": target.observation_id,
        "freshness_run_id": freshness_run_id,
        "mint": target.mint,
        "token_mint": target.mint,
        "creator": target.creator,
        "source": candidate.get("source"),
        "source_adapter": candidate.get("source_adapter"),
        "create_signature": candidate.get("transaction_signature"),
        "create_time": create_time,
        "create_observed_at": create_observed_at,
        "first_followup_attempt_time": first_attempt_time,
        "first_followup_path_time": path_time,
        "first_followup_fdv_proxy": fdv,
        "first_followup_event_count": event_count,
        "first_followup_buy_count": buys,
        "first_followup_sell_count": sells,
        "first_followup_active_wallets": active_wallets,
        "seconds_create_to_create_observed": _delta(create_time, create_observed_at),
        "seconds_create_to_first_followup_attempt": _delta(create_time, first_attempt_time),
        "seconds_create_observed_to_first_followup_attempt": _delta(create_observed_at, first_attempt_time),
        "seconds_create_to_first_followup_path": _delta(create_time, path_time),
        "followup_started_immediately": _delta(create_time, first_attempt_time) is not None
        and (_delta(create_time, first_attempt_time) or 0) <= 5,
        "first_followup_before_any_trade_if_known": fdv is None,
        "first_followup_before_10k": fdv is not None and fdv < 10_000,
        "first_followup_before_15k": fdv is not None and fdv < 15_000,
        "first_followup_before_20k": fdv is not None and fdv < 20_000,
        "first_followup_already_above_10k": fdv is not None and fdv >= 10_000,
        "first_followup_already_above_20k": fdv is not None and fdv >= 20_000,
        "first_followup_already_above_50k": fdv is not None and fdv >= 50_000,
        "freshness_class": freshness_class,
        "followup_passes": pass_count,
    }


def _freshness_class(*, create_time: float | None, first_path_time: float | None, first_fdv: float | None) -> str:
    if first_fdv is None:
        return "immediate_followup_no_trade_yet"
    if first_fdv >= 50_000:
        return "first_followup_already_above_50k"
    if first_fdv >= 20_000:
        return "first_followup_already_above_20k"
    if first_fdv >= 10_000:
        return "first_followup_already_above_10k"
    if create_time is None or first_path_time is None:
        return "unknown_freshness"
    seconds = first_path_time - create_time
    if seconds <= 15:
        return "true_birth_observed"
    if seconds <= 60:
        return "near_birth_observed"
    return "immediate_followup_after_first_trade"


def _freshness_path_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "create_signature": record.get("create_signature"),
        "freshness_run_id": record.get("freshness_run_id"),
        "create_time": record.get("create_time"),
        "first_followup_attempt_time": record.get("first_followup_attempt_time"),
        "first_followup_path_time": record.get("first_followup_path_time"),
        "seconds_create_to_create_observed": record.get("seconds_create_to_create_observed"),
        "seconds_create_to_first_followup_attempt": record.get("seconds_create_to_first_followup_attempt"),
        "seconds_create_observed_to_first_followup_attempt": record.get("seconds_create_observed_to_first_followup_attempt"),
        "seconds_create_to_first_followup_path": record.get("seconds_create_to_first_followup_path"),
        "followup_started_immediately": record.get("followup_started_immediately"),
        "first_followup_before_any_trade_if_known": record.get("first_followup_before_any_trade_if_known"),
        "first_followup_before_10k": record.get("first_followup_before_10k"),
        "first_followup_before_15k": record.get("first_followup_before_15k"),
        "first_followup_before_20k": record.get("first_followup_before_20k"),
        "first_followup_already_above_10k": record.get("first_followup_already_above_10k"),
        "first_followup_already_above_20k": record.get("first_followup_already_above_20k"),
        "first_followup_already_above_50k": record.get("first_followup_already_above_50k"),
        "freshness_class": record.get("freshness_class"),
    }


def _freshness_event_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "create_signature": record.get("create_signature"),
        "create_time": record.get("create_time"),
        "freshness_class": record.get("freshness_class"),
    }


def _update_immediate_freshness_counts(config: ForwardObserverConfig, result: dict[str, Any]) -> None:
    records = read_jsonl(config.observation_root / BIRTH_WATCH_MINTS_FILE)
    paths = read_jsonl(config.observation_root / BIRTH_FOLLOWUP_PATHS_FILE)
    run_id = result.get("freshness_run_id") or _latest_freshness_run_id(records)
    active_records = [row for row in records if row.get("freshness_run_id") == run_id] if run_id else records
    active_paths = [row for row in paths if row.get("freshness_run_id") == run_id] if run_id else paths
    records = active_records
    paths = active_paths
    result["freshness_run_id"] = run_id
    result["smoke_birth_count"] = len(records)
    result["immediate_followup_started_count"] = sum(1 for row in records if row.get("first_followup_attempt_time") is not None)
    result["first_followup_path_rows"] = len(paths)
    result["true_near_birth_observed_count"] = sum(
        1 for row in records if row.get("freshness_class") in {"true_birth_observed", "near_birth_observed"}
    )
    result["first_followup_before_10k_count"] = sum(1 for row in records if row.get("first_followup_before_10k") is True)
    result["first_followup_before_any_trade_if_known_count"] = sum(
        1 for row in records if row.get("first_followup_before_any_trade_if_known") is True
    )
    result["first_followup_before_20k_count"] = sum(1 for row in records if row.get("first_followup_before_20k") is True)
    result["first_followup_after_activity_count"] = sum(
        1
        for row in records
        if row.get("freshness_class") in {"immediate_followup_after_first_trade", "first_followup_after_activity"}
    )
    result["first_followup_already_above_10k_count"] = sum(1 for row in records if row.get("first_followup_already_above_10k") is True)
    result["first_followup_already_above_20k_count"] = sum(1 for row in records if row.get("first_followup_already_above_20k") is True)
    result["crossed_10k_count"] = sum(1 for row in paths if row.get("crossed_10k") is True)
    result["crossed_20k_count"] = sum(1 for row in paths if row.get("crossed_20k") is True)
    result["trigger_qualified_true_near_birth_mints"] = len(
        {
            row.get("mint")
            for row in records
            if row.get("freshness_class") in {"true_birth_observed", "near_birth_observed"}
            and any(path.get("mint") == row.get("mint") and path.get("crossed_10k") is True for path in paths)
        }
    )
    attempt_seconds = [safe_float(row.get("seconds_create_to_first_followup_attempt")) for row in records]
    observed_to_attempt_seconds = [safe_float(row.get("seconds_create_observed_to_first_followup_attempt")) for row in records]
    path_seconds = [safe_float(row.get("seconds_create_to_first_followup_path")) for row in records]
    attempt_seconds = [value for value in attempt_seconds if value is not None]
    observed_to_attempt_seconds = [value for value in observed_to_attempt_seconds if value is not None]
    path_seconds = [value for value in path_seconds if value is not None]
    result["median_seconds_create_to_first_followup_attempt"] = _median(attempt_seconds)
    result["median_seconds_create_observed_to_first_followup_attempt"] = _median(observed_to_attempt_seconds)
    result["median_seconds_create_to_first_path"] = _median(path_seconds)
    result["attempt_within_5s_pct"] = _pct_le(attempt_seconds, 5)
    result["observed_to_attempt_within_5s_pct"] = _pct_le(observed_to_attempt_seconds, 5)
    result["attempt_within_15s_pct"] = _pct_le(attempt_seconds, 15)
    result["attempt_within_30s_pct"] = _pct_le(attempt_seconds, 30)
    result["attempt_within_60s_pct"] = _pct_le(attempt_seconds, 60)
    result["path_within_5s_pct"] = _pct_le(path_seconds, 5)
    result["path_within_15s_pct"] = _pct_le(path_seconds, 15)
    result["path_within_30s_pct"] = _pct_le(path_seconds, 30)
    result["path_within_60s_pct"] = _pct_le(path_seconds, 60)
    median_attempt = safe_float(result.get("median_seconds_create_to_first_followup_attempt"))
    has_fresh_observation = (
        result["true_near_birth_observed_count"] > 0
        or result["first_followup_before_any_trade_if_known_count"] > 0
    )
    has_pretrigger_evidence = (
        result["first_followup_before_10k_count"] > 0
        or result["first_followup_before_any_trade_if_known_count"] > 0
    )
    if result["smoke_birth_count"] <= 0:
        result["readiness_classification"] = "freshness_repair_blocked"
    elif (
        has_fresh_observation
        and has_pretrigger_evidence
        and median_attempt is not None
        and median_attempt <= 5
        and (result.get("attempt_within_5s_pct") or 0) >= 0.95
    ):
        result["readiness_classification"] = "freshness_repair_ready_for_100_birth_smoke"
    else:
        result["readiness_classification"] = "freshness_repair_needs_timing_improvement"


def _write_immediate_status(config: ForwardObserverConfig, result: dict[str, Any]) -> None:
    if result.get("execute"):
        _update_immediate_freshness_counts(config, result)
    status = {
        "report_id": result["report_id"],
        "mode": result["mode"],
        "freshness_run_id": result.get("freshness_run_id"),
        "birth_watch_mints": result.get("smoke_birth_count", 0),
        "immediate_followup_started": result.get("immediate_followup_started_count", 0),
        "first_followup_path_rows": result.get("first_followup_path_rows", 0),
        "true_near_birth_observed": result.get("true_near_birth_observed_count", 0),
        "first_followup_before_10k": result.get("first_followup_before_10k_count", 0),
        "first_followup_before_any_trade_if_known": result.get("first_followup_before_any_trade_if_known_count", 0),
        "first_followup_before_20k": result.get("first_followup_before_20k_count", 0),
        "first_followup_after_activity": result.get("first_followup_after_activity_count", 0),
        "first_followup_already_above_10k": result.get("first_followup_already_above_10k_count", 0),
        "first_followup_already_above_20k": result.get("first_followup_already_above_20k_count", 0),
        "crossed_10k": result.get("crossed_10k_count", 0),
        "crossed_20k": result.get("crossed_20k_count", 0),
        "trigger_qualified_true_near_birth_mints": result.get("trigger_qualified_true_near_birth_mints", 0),
        "target_trigger_qualified_true_near_birth_mints": result.get("target_trigger_qualified_true_near_birth_mints", 300),
        "freshness_repair_status": result.get("readiness_classification"),
        "median_seconds_create_to_first_followup_attempt": result.get("median_seconds_create_to_first_followup_attempt"),
        "median_seconds_create_observed_to_first_followup_attempt": result.get(
            "median_seconds_create_observed_to_first_followup_attempt"
        ),
        "median_seconds_create_to_first_path": result.get("median_seconds_create_to_first_path"),
        "attempt_within_5s_pct": result.get("attempt_within_5s_pct"),
        "observed_to_attempt_within_5s_pct": result.get("observed_to_attempt_within_5s_pct"),
        "attempt_within_15s_pct": result.get("attempt_within_15s_pct"),
        "attempt_within_30s_pct": result.get("attempt_within_30s_pct"),
        "attempt_within_60s_pct": result.get("attempt_within_60s_pct"),
        "path_within_5s_pct": result.get("path_within_5s_pct"),
        "path_within_15s_pct": result.get("path_within_15s_pct"),
        "path_within_30s_pct": result.get("path_within_30s_pct"),
        "path_within_60s_pct": result.get("path_within_60s_pct"),
        "network_calls_made": result.get("network_calls_made", 0),
        "estimated_helius_credits_used": result.get("estimated_helius_credits_used", 0),
        "warnings": result.get("warnings", []),
        "output_files": result.get("output_files", {}),
    }
    (config.observation_root / BIRTH_FOLLOWUP_STATUS_FILE).write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / 2


def _pct_le(values: list[float], threshold: float) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value <= threshold) / len(values), 6)


def _latest_freshness_run_id(records: list[dict[str, Any]]) -> str | None:
    for row in reversed(records):
        run_id = row.get("freshness_run_id")
        if run_id:
            return str(run_id)
    return None


def _is_birth_candidate(row: dict[str, Any]) -> bool:
    return (
        row.get("freshness_lane") == "birth_watch"
        or row.get("candidate_classification") == "pumpfun_birth_candidate_observed"
        or row.get("event_type") == "pumpfun_create"
    )


def _has_followup_fdv(paths: list[dict[str, Any]]) -> bool:
    for row in paths:
        if row.get("event_type") == "pumpfun_create":
            continue
        if safe_float(row.get("fdv_proxy")) is not None:
            return True
    return False


def _observation_root(root: Path) -> Path:
    return root / "data" / "forward_observation" / "efficient_movers"


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _write_report(config: ForwardObserverConfig, payload: dict[str, Any]) -> None:
    report_dir = config.report_root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / SUMMARY_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (report_dir / SUMMARY_MD).write_text(_markdown(payload), encoding="utf-8")


def _markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Birth-watch Follow-up Collection",
            "",
            "- Guardrail: observation-only; no trading, backtest, validation, optimization, or strategy work.",
            f"- Execute: `{payload.get('execute')}`",
            f"- Selected mints: `{payload.get('selected_mint_count')}`",
            f"- Projected requests: `{payload.get('projected_requests')}`",
            f"- Request ceiling: `{payload.get('request_ceiling')}`",
            f"- Network calls made: `{payload.get('network_calls_made')}`",
            f"- Rows written: `{payload.get('rows_written')}`",
            f"- Mints with FDV follow-up: `{payload.get('mints_with_fdv_followup')}`",
            f"- Mints with trigger follow-up: `{payload.get('mints_with_trigger_followup')}`",
            f"- Warnings: `{payload.get('warnings', [])}`",
        ]
    ) + "\n"
