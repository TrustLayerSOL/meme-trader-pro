"""Bounded follow-up collector for Pump.fun birth-watch mints.

The collector is read-only against chain data and writes observation rows only.
It does not trade, validate, backtest, optimize, or generate strategy logic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from research.mtp_research.validation.forward_efficient_mover_observer import (
    OUTPUT_FILES,
    PUMP_FUN_PROGRAM_ID,
    RAW_SOURCE_FILES,
    ForwardObserverConfig,
    append_jsonl,
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


REPORT_ID = "forward_birth_watch_followup_collector_v0"
REPORT_DIR = "birth_watch_followup_collector"
SUMMARY_JSON = "birth_watch_followup_collection_summary.json"
SUMMARY_MD = "birth_watch_followup_collection_summary.md"
RAW_FOLLOWUP_FILE = "helius_birth_watch_followup_raw.jsonl"


class BirthWatchFollowupFetcher(Protocol):
    requests_used: int
    raw_transactions: list[dict[str, Any]]

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
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
    ) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        return [dict(row) for row in self.events_by_mint.get(mint, [])[:transactions_per_mint]]


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
    ) -> list[dict[str, Any]]:
        if not self.rpc_url:
            return []
        signatures = self._fetch_signatures(mint, signatures_per_mint)
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

    def _fetch_signatures(self, mint: str, limit: int) -> list[str]:
        payload = {
            "jsonrpc": "2.0",
            "id": "mtp-birth-watch-followup-get-signatures",
            "method": "getSignaturesForAddress",
            "params": [mint, {"limit": max(1, min(int(limit), 100))}],
        }
        response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        self.requests_used += 1
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
        response = self._rpc_post(self.rpc_url, payload, self.timeout_sec)
        self.requests_used += 1
        result = response.get("result") if isinstance(response, dict) else None
        return result if isinstance(result, dict) else {}


def build_birth_watch_followup_plan(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    max_mints: int = 10,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    request_ceiling: int = 250,
) -> dict[str, Any]:
    root = Path(data_root).expanduser()
    targets = _select_targets(root, max_mints=max_mints)
    projected_requests = len(targets) * (1 + max(0, min(int(signatures_per_mint), int(transactions_per_mint))))
    return {
        "report_id": REPORT_ID,
        "execute": False,
        "data_root": str(root),
        "observation_root": str(_observation_root(root)),
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


def _select_targets(root: Path, *, max_mints: int) -> list[BirthWatchTarget]:
    obs = _observation_root(root)
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
                observed_at=safe_float(row.get("observed_at") or row.get("first_seen_time")),
                launch_time=safe_float(row.get("launch_time")),
                creator=row.get("creator"),
            )
        )
    targets.sort(key=lambda item: (item.observed_at if item.observed_at is not None else float("inf"), item.mint))
    return targets[: max(0, int(max_mints))]


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
