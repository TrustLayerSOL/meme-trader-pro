"""Official forward lifecycle watcher state and audit utilities.

This module is forward-observation infrastructure only. It does not contain
private-key logic, wallet execution, order routing, paper/live trading,
validation, backtests, or strategy generation.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_root


OFFICIAL_SAMPLE_LABEL = "official_lifecycle_watch_v1"
QUARANTINED_SAMPLE_LABEL = "pre_lifecycle_watch_forward_sample"
REPORT_ID = "official_lifecycle_watch_v1"
TARGET_LEVELS: dict[str, float] = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
PRE_MATURITY_STATES = {
    "birth_watch",
    "fdv_followup_started",
    "crossed_10k",
    "crossed_15k",
    "crossed_20k",
    "trigger_qualified_active_watch",
}
MATURITY_STATES = {
    "matured_reached_1m",
    "matured_terminal_collapse",
    "matured_inactive_timeout",
    "matured_max_age",
    "matured_manual_stop",
    "data_limited",
}
ALLOWED_STATES = PRE_MATURITY_STATES | MATURITY_STATES
GUARDRAILS = [
    "forward_observation_only",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_transaction_building_for_trading",
    "no_order_routing",
    "no_live_trading",
    "no_paper_trading",
    "no_pnl",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_buy_sell_rules",
    "no_alerts",
    "no_threshold_optimization",
    "no_ml_black_boxes",
    "no_validation",
    "no_backtest",
]
APPROVED_USES = [
    "fresh Pump.fun birth observation",
    "trigger-qualified lifecycle watching",
    "FDV path recording",
    "drawdown and reclaim observation",
    "metadata availability audit",
    "data-quality audit",
]
PROHIBITED_USES = [
    "validation",
    "backtest",
    "paper trading",
    "live trading",
    "private-key use",
    "wallet execution",
    "buy orders",
    "sell orders",
    "swaps",
    "order routing",
    "profitability claims",
    "strategy generation",
]


@dataclass
class OfficialLifecycleConfig:
    data_root: Path | str | None = None
    followup_poll_seconds: float = 2.0
    trigger_qualified_followup_poll_seconds: float = 2.0
    max_active_birth_followups: int = 200
    max_active_trigger_watches: int = 300
    max_observation_age_minutes: int = 240
    inactive_timeout_minutes: int = 30
    maturity_followup_after_20k_minutes: int = 120
    max_birth_to_first_followup_seconds: float = 5.0
    max_helius_credits_per_run: int = 50_000
    global_observation_credit_cap: int = 500_000
    target_crossed_20k: int = 300
    terminal_collapse_pct: float = 70.0

    @property
    def root(self) -> Path:
        return Path(self.data_root or data_lake_root()).expanduser()

    @property
    def observation_root(self) -> Path:
        return self.root / "data" / "forward_observation" / OFFICIAL_SAMPLE_LABEL

    @property
    def raw_root(self) -> Path:
        return self.root / "data" / "raw" / "forward_observation" / OFFICIAL_SAMPLE_LABEL

    @property
    def report_root(self) -> Path:
        return self.root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / OFFICIAL_SAMPLE_LABEL

    @property
    def manifest_json_path(self) -> Path:
        return self.observation_root / "official_lifecycle_manifest.json"

    @property
    def manifest_md_path(self) -> Path:
        return self.observation_root / "official_lifecycle_manifest.md"

    @property
    def state_path(self) -> Path:
        return self.observation_root / "lifecycle_state.json"

    @property
    def births_path(self) -> Path:
        return self.observation_root / "births.jsonl"

    @property
    def followup_paths_path(self) -> Path:
        return self.observation_root / "followup_paths.jsonl"

    @property
    def events_path(self) -> Path:
        return self.observation_root / "events.jsonl"

    @property
    def metadata_path(self) -> Path:
        return self.observation_root / "metadata.jsonl"

    @property
    def stale_births_path(self) -> Path:
        return self.observation_root / "stale_births.jsonl"

    @property
    def drawdowns_path(self) -> Path:
        return self.observation_root / "drawdowns.jsonl"

    @property
    def transitions_path(self) -> Path:
        return self.observation_root / "lifecycle_transitions.jsonl"

    @property
    def status_path(self) -> Path:
        return self.observation_root / "status.json"

    @property
    def helius_ws_raw_path(self) -> Path:
        return self.raw_root / "helius_ws_raw.jsonl"

    @property
    def helius_rpc_raw_path(self) -> Path:
        return self.raw_root / "helius_rpc_raw.jsonl"


def initialize_official_lifecycle_namespace(config: OfficialLifecycleConfig, *, reset: bool = False) -> dict[str, Any]:
    config.observation_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    if reset:
        for path in [
            config.births_path,
            config.followup_paths_path,
            config.events_path,
            config.metadata_path,
            config.stale_births_path,
            config.drawdowns_path,
            config.transitions_path,
            config.status_path,
            config.helius_ws_raw_path,
            config.helius_rpc_raw_path,
        ]:
            if path.exists():
                path.unlink()
        if config.state_path.exists():
            config.state_path.unlink()
    for path in [
        config.births_path,
        config.followup_paths_path,
        config.events_path,
        config.metadata_path,
        config.stale_births_path,
        config.drawdowns_path,
        config.transitions_path,
        config.helius_ws_raw_path,
        config.helius_rpc_raw_path,
    ]:
        path.touch(exist_ok=True)
    if not config.state_path.exists():
        _write_json(config.state_path, _empty_state(config))
    manifest = {
        "report_id": REPORT_ID,
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "starts_from_zero": _row_count(config.births_path) == 0,
        "old_quarantined_sample_excluded": True,
        "excluded_sample_label": QUARANTINED_SAMPLE_LABEL,
        "collection_start_time": _utc_now_iso(),
        "observation_root": str(config.observation_root),
        "raw_root": str(config.raw_root),
        "report_root": str(config.report_root),
        "allowed_uses": APPROVED_USES,
        "prohibited_uses": PROHIBITED_USES,
        "guardrails": GUARDRAILS,
        "trigger_definitions": TARGET_LEVELS,
        "maturity_definitions": {
            "matured_reached_1m": "deterministic observed FDV path crosses 1M",
            "matured_terminal_collapse": "crossed 20k then falls below collapse threshold and fails reclaim window",
            "matured_inactive_timeout": "no meaningful events for configured timeout",
            "matured_max_age": "max observation age reached",
            "matured_manual_stop": "manual operator stop",
            "data_limited": "source/path evidence insufficient",
        },
        "config": {
            "followup_poll_seconds": config.followup_poll_seconds,
            "trigger_qualified_followup_poll_seconds": config.trigger_qualified_followup_poll_seconds,
            "max_active_birth_followups": config.max_active_birth_followups,
            "max_active_trigger_watches": config.max_active_trigger_watches,
            "max_observation_age_minutes": config.max_observation_age_minutes,
            "inactive_timeout_minutes": config.inactive_timeout_minutes,
            "maturity_followup_after_20k_minutes": config.maturity_followup_after_20k_minutes,
            "max_birth_to_first_followup_seconds": config.max_birth_to_first_followup_seconds,
            "max_helius_credits_per_run": config.max_helius_credits_per_run,
            "global_observation_credit_cap": config.global_observation_credit_cap,
        },
        "initial_counts": {
            "births": _row_count(config.births_path),
            "followup_paths": _row_count(config.followup_paths_path),
            "events": _row_count(config.events_path),
            "metadata": _row_count(config.metadata_path),
            "drawdowns": _row_count(config.drawdowns_path),
            "transitions": _row_count(config.transitions_path),
        },
        "network_calls_made": 0,
    }
    _write_json(config.manifest_json_path, manifest)
    config.manifest_md_path.write_text(_manifest_markdown(manifest), encoding="utf-8")
    return manifest


class OfficialLifecycleStateMachine:
    def __init__(self, config: OfficialLifecycleConfig) -> None:
        self.config = config
        initialize_official_lifecycle_namespace(config)
        self.state = _read_state(config)

    def save(self) -> None:
        _write_json(self.config.state_path, self.state)

    def record_birth(self, birth: dict[str, Any]) -> dict[str, Any]:
        mint = _mint(birth)
        if not mint:
            raise ValueError("birth row requires mint")
        now = _num(birth.get("observed_time") or birth.get("observed_at")) or time.time()
        create_time = _num(birth.get("create_time") or birth.get("launch_time") or birth.get("block_time"))
        first_attempt = _num(birth.get("first_followup_attempt_time"))
        state_row = self.state["mints"].get(mint, {})
        previous_state = state_row.get("state")
        row = {
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "observation_id": birth.get("observation_id") or f"official-birth-{mint[:12]}-{int(now)}",
            "mint": mint,
            "creator": birth.get("creator"),
            "pool_address": birth.get("pool_address") or birth.get("bonding_curve"),
            "bonding_curve": birth.get("bonding_curve") or birth.get("pool_address"),
            "associated_bonding_curve": birth.get("associated_bonding_curve"),
            "state": "birth_watch",
            "create_signature": birth.get("create_signature") or birth.get("transaction_signature") or birth.get("signature"),
            "create_time": create_time,
            "observed_time": now,
            "first_followup_attempt_time": first_attempt,
            "create_to_first_followup_seconds": _delta(create_time, first_attempt),
            "first_followup_before_any_trade_if_known": birth.get("first_followup_before_any_trade_if_known"),
            "first_followup_before_10k": birth.get("first_followup_before_10k"),
            "first_followup_before_20k": birth.get("first_followup_before_20k"),
            "freshness_class": _freshness_class(birth, create_time=create_time, first_attempt=first_attempt),
            "source_provenance": birth.get("source_provenance") or birth.get("source") or "mock_verified_pumpfun_create",
            "crossed_levels": [],
            "local_high_fdv": None,
            "last_path_time": None,
            "entered_trigger_qualified_at": None,
            "matured_at": None,
        }
        if state_row:
            row.update({key: value for key, value in state_row.items() if key not in {"state", "crossed_levels"}})
            row["state"] = state_row.get("state", "birth_watch")
            row["crossed_levels"] = state_row.get("crossed_levels", [])
        self.state["mints"][mint] = row
        if not state_row:
            _append_jsonl(self.config.births_path, [row])
            self._transition(mint, previous_state, "birth_watch", now, "verified_pumpfun_create_observed")
        self.save()
        return row

    def record_path(self, path: dict[str, Any]) -> dict[str, Any]:
        mint = _mint(path)
        if not mint:
            raise ValueError("path row requires mint")
        if mint not in self.state["mints"]:
            self.record_birth({"mint": mint, "observed_time": path.get("timestamp"), "source_provenance": "path_without_birth_data_limited"})
        state_row = self.state["mints"][mint]
        timestamp = _num(path.get("timestamp") or path.get("observed_at")) or time.time()
        fdv = _num(path.get("fdv_proxy"))
        previous_state = state_row.get("state")
        crossed_levels = _crossed_levels(fdv)
        prior_crossed = set(state_row.get("crossed_levels", []))
        merged_crossed = sorted(prior_crossed | set(crossed_levels), key=lambda label: TARGET_LEVELS[label])
        local_high = max([value for value in [_num(state_row.get("local_high_fdv")), fdv] if value is not None], default=None)
        drawdown_pct = _drawdown_pct(local_high, fdv)
        new_state = _next_state(previous_state, merged_crossed, fdv, local_high, drawdown_pct)
        if "20k" in merged_crossed and previous_state not in MATURITY_STATES and new_state not in MATURITY_STATES:
            new_state = "trigger_qualified_active_watch"
        if "1m" in merged_crossed:
            new_state = "matured_reached_1m"
        state_row.update(
            {
                "state": new_state,
                "crossed_levels": merged_crossed,
                "local_high_fdv": local_high,
                "last_path_time": timestamp,
            }
        )
        if "20k" in merged_crossed and not state_row.get("entered_trigger_qualified_at"):
            state_row["entered_trigger_qualified_at"] = timestamp
            self.state["counters"]["official_crossed_20k_count"] = int(self.state["counters"].get("official_crossed_20k_count", 0)) + 1
        if new_state in MATURITY_STATES and not state_row.get("matured_at"):
            state_row["matured_at"] = timestamp
        enriched = _path_row(path, state_row, timestamp=timestamp, fdv=fdv, local_high=local_high, drawdown_pct=drawdown_pct)
        _append_jsonl(self.config.followup_paths_path, [enriched])
        _append_jsonl(self.config.drawdowns_path, [_drawdown_row(enriched)])
        if previous_state != new_state:
            self._transition(mint, previous_state, new_state, timestamp, "observed_fdv_path_transition")
        self.save()
        return enriched

    def active_watch_mints(self) -> list[str]:
        active = []
        for mint, row in self.state.get("mints", {}).items():
            state = row.get("state")
            if state in PRE_MATURITY_STATES:
                active.append(mint)
        return sorted(active)

    def _transition(self, mint: str, previous_state: str | None, new_state: str, timestamp: float, reason: str) -> None:
        _append_jsonl(
            self.config.transitions_path,
            [
                {
                    "sample_label": OFFICIAL_SAMPLE_LABEL,
                    "mint": mint,
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "transition_time": timestamp,
                    "transition_reason": reason,
                    "source_provenance": "state_machine",
                }
            ],
        )


def run_active_lifecycle_followup_cycle(
    machine: OfficialLifecycleStateMachine,
    fetcher: Any,
    *,
    signatures_per_mint: int,
    transactions_per_mint: int,
    now: float | None = None,
) -> dict[str, Any]:
    timestamp = now if now is not None else time.time()
    checked = 0
    path_rows = 0
    event_rows = 0
    fdv_mints: set[str] = set()
    for mint in machine.active_watch_mints()[: machine.config.max_active_birth_followups]:
        state_row = machine.state.get("mints", {}).get(mint, {})
        last_attempt = _num(state_row.get("last_followup_attempt_time"))
        if (
            last_attempt is not None
            and timestamp - last_attempt < max(0.0, float(machine.config.followup_poll_seconds))
        ):
            continue
        state_row["last_followup_attempt_time"] = timestamp
        state_row["followup_attempt_count"] = int(state_row.get("followup_attempt_count") or 0) + 1
        machine.save()
        checked += 1
        events = fetcher.fetch_for_mint(
            mint,
            signatures_per_mint=signatures_per_mint,
            transactions_per_mint=transactions_per_mint,
            followup_addresses=_followup_addresses(state_row),
        )
        if events:
            _append_jsonl(
                machine.config.events_path,
                [{**event, "sample_label": OFFICIAL_SAMPLE_LABEL, "mint": mint} for event in events],
            )
            event_rows += len(events)
        for event in events:
            if _num(event.get("fdv_proxy")) is None:
                continue
            fdv_mints.add(mint)
            machine.record_path(
                {
                    "mint": mint,
                    "timestamp": event.get("timestamp") or event.get("observed_at") or event.get("block_time") or timestamp,
                    "fdv_proxy": event.get("fdv_proxy"),
                    "event_count": event.get("event_count") or 1,
                    "buy_count": event.get("buy_count") or (1 if str(event.get("side") or "").lower() == "buy" else 0),
                    "sell_count": event.get("sell_count") or (1 if str(event.get("side") or "").lower() == "sell" else 0),
                    "active_wallet_count": event.get("active_wallet_count") or event.get("active_wallets") or 1,
                    "source_provenance": event.get("source") or "helius_mint_followup_observed_path",
                }
            )
            path_rows += 1
    return {
        "active_mints_checked": checked,
        "path_rows_written": path_rows,
        "event_rows_written": event_rows,
        "mints_with_fdv_followup": len(fdv_mints),
    }


def collect_initial_birth_followups(
    candidates: list[dict[str, Any]],
    fetcher: Any,
    *,
    signatures_per_mint: int,
    transactions_per_mint: int,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    workers = max(1, min(int(max_workers), len(candidates)))

    def _fetch(index_and_candidate: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, candidate = index_and_candidate
        mint = _mint(candidate)
        first_attempt = time.time()
        events = []
        if mint:
            events = fetcher.fetch_for_mint(
                mint,
                signatures_per_mint=signatures_per_mint,
                transactions_per_mint=transactions_per_mint,
                followup_addresses=_followup_addresses(candidate),
            )
        first_fdv = next((_num(event.get("fdv_proxy")) for event in events if _num(event.get("fdv_proxy")) is not None), None)
        return {
            "index": index,
            "mint": mint,
            "candidate": candidate,
            "first_attempt": first_attempt,
            "events": events,
            "first_fdv": first_fdv,
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch, item) for item in enumerate(candidates)]
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda row: row["index"])


def is_official_fresh_birth(candidate: dict[str, Any], first_attempt: float, *, max_delay_seconds: float = 5.0) -> bool:
    create_time = _num(candidate.get("launch_time") or candidate.get("block_time") or candidate.get("create_time"))
    delay = _delta(create_time, first_attempt)
    return delay is not None and delay <= float(max_delay_seconds)


def _stale_birth_row(candidate: dict[str, Any], first_attempt: float, *, max_delay_seconds: float) -> dict[str, Any]:
    create_time = _num(candidate.get("launch_time") or candidate.get("block_time") or candidate.get("create_time"))
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "mint": _mint(candidate),
        "creator": candidate.get("creator"),
        "create_signature": candidate.get("transaction_signature") or candidate.get("signature") or candidate.get("create_signature"),
        "create_time": create_time,
        "observed_time": _num(candidate.get("observed_at")),
        "first_followup_attempt_time": first_attempt,
        "create_to_first_followup_seconds": _delta(create_time, first_attempt),
        "max_birth_to_first_followup_seconds": float(max_delay_seconds),
        "rejection_reason": "first_followup_exceeded_5s_freshness_gate",
        "source_provenance": "helius_pumpfun_create_websocket_logs",
    }


def run_official_lifecycle_smoke(
    config: OfficialLifecycleConfig,
    *,
    target_births: int = 25,
    target_crossed_20k: int = 300,
    execute: bool = False,
) -> dict[str, Any]:
    initialize_official_lifecycle_namespace(config, reset=execute and _row_count(config.births_path) == 0)
    if not execute:
        return {
            "report_id": "official_lifecycle_watch_smoke_v0",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "projected_births": target_births,
            "network_calls_made": 0,
            "estimated_helius_credits_used": 0,
            "readiness_classification": "official_lifecycle_watch_ready_for_100_birth_smoke",
        }
    machine = OfficialLifecycleStateMachine(config)
    births = _mock_births(target_births)
    for birth in births:
        machine.record_birth(birth)
        for path in _mock_paths_for_birth(birth):
            machine.record_path(path)
    _write_status(config, target_crossed_20k=target_crossed_20k, credits_used=0)
    audit, audit_paths = build_official_lifecycle_quality_audit(config)
    status = official_lifecycle_status(config, target_crossed_20k=target_crossed_20k)
    result = {
        "report_id": "official_lifecycle_watch_smoke_v0",
        "execute": True,
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "smoke_births_observed": len(births),
        "under_5s_followup_count": sum(1 for row in births if (_delta(_num(row.get("create_time")), _num(row.get("first_followup_attempt_time"))) or 999) <= 5),
        "active_watches_created": status["trigger_qualified_active_watches"] + status["matured_trigger_qualified"],
        "matured_counts": {
            "matured_reached_1m": status["reached_1m"],
            "matured_terminal_collapse": status["terminal_collapse"],
            "matured_inactive_timeout": status["inactive_timeout"],
            "matured_max_age": status["max_age"],
        },
        "network_calls_made": 0,
        "estimated_helius_credits_used": 0,
        "quality_audit_result": audit,
        "quality_audit_paths": {key: str(value) for key, value in audit_paths.items()},
        "lifecycle_state_file": str(config.state_path),
        "readiness_classification": _readiness_from_audit(audit),
    }
    _write_json(config.report_root / "official_lifecycle_smoke_summary.json", result)
    return result


def run_official_lifecycle_live_smoke(
    config: OfficialLifecycleConfig,
    *,
    target_births: int = 25,
    target_crossed_20k: int = 300,
    max_runtime_minutes: int = 30,
    signatures_per_mint: int = 10,
    transactions_per_mint: int = 10,
    execute: bool = False,
) -> dict[str, Any]:
    initialize_official_lifecycle_namespace(config, reset=execute and _row_count(config.births_path) == 0)
    projected_requests = max(0, int(target_births)) * (1 + max(0, min(int(signatures_per_mint), int(transactions_per_mint))))
    if not execute:
        return {
            "report_id": "official_lifecycle_watch_live_smoke_v0",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "projected_births": target_births,
            "projected_request_equivalent_credits": projected_requests,
            "network_calls_made": 0,
            "estimated_helius_credits_used": 0,
            "readiness_classification": "official_lifecycle_watch_ready_for_100_birth_smoke",
        }
    if projected_requests > int(config.max_helius_credits_per_run):
        return {
            "report_id": "official_lifecycle_watch_live_smoke_v0",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "projected_births": target_births,
            "projected_request_equivalent_credits": projected_requests,
            "network_calls_made": 0,
            "estimated_helius_credits_used": 0,
            "readiness_classification": "official_lifecycle_watch_blocked",
            "warnings": ["projected_requests_exceed_run_credit_cap"],
        }
    from research.mtp_research.validation.forward_birth_watch_followup_collector import (
        HeliusMintBirthWatchFollowupFetcher,
        PumpFunCreateWebSocketCandidateSource,
    )
    from research.mtp_research.validation.forward_efficient_mover_observer import ForwardObserverConfig

    forward_config = ForwardObserverConfig(
        data_root=config.root,
        max_helius_credits=config.max_helius_credits_per_run,
        max_runtime_minutes=max_runtime_minutes,
        enable_birth_watch_candidates=True,
    )
    source = PumpFunCreateWebSocketCandidateSource(
        config=forward_config,
        timeout_seconds=0.25,
        max_signatures_per_fetch=32,
        candidate_hydration_workers=32,
    )
    fetcher = HeliusMintBirthWatchFollowupFetcher(data_root=config.root)
    availability = source.availability()
    if not availability.get("available"):
        return {
            "report_id": "official_lifecycle_watch_live_smoke_v0",
            "execute": False,
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "network_calls_made": 0,
            "estimated_helius_credits_used": 0,
            "readiness_classification": "official_lifecycle_watch_blocked",
            "warnings": [availability.get("missing_reason") or "helius_websocket_source_unavailable"],
        }
    machine = OfficialLifecycleStateMachine(config)
    deadline = time.monotonic() + max(1, int(max_runtime_minutes)) * 60
    births_seen = 0
    warnings: list[str] = []
    while births_seen < max(0, int(target_births)) and time.monotonic() < deadline:
        if _requests_used(source, fetcher) >= int(config.max_helius_credits_per_run):
            warnings.append("max_helius_credits_per_run_reached")
            break
        candidates = source.fetch_candidates()
        if not candidates:
            run_active_lifecycle_followup_cycle(
                machine,
                fetcher,
                signatures_per_mint=signatures_per_mint,
                transactions_per_mint=transactions_per_mint,
            )
            continue
        remaining_births = max(0, int(target_births) - births_seen)
        followup_results = collect_initial_birth_followups(
            candidates[:remaining_births],
            fetcher,
            signatures_per_mint=signatures_per_mint,
            transactions_per_mint=transactions_per_mint,
            max_workers=32,
        )
        for followup in followup_results:
            if births_seen >= int(target_births):
                break
            candidate = followup["candidate"]
            mint = followup["mint"]
            if not mint:
                continue
            first_attempt = followup["first_attempt"]
            if not is_official_fresh_birth(
                candidate,
                first_attempt,
                max_delay_seconds=config.max_birth_to_first_followup_seconds,
            ):
                _append_jsonl(
                    config.stale_births_path,
                    [
                        _stale_birth_row(
                            candidate,
                            first_attempt,
                            max_delay_seconds=config.max_birth_to_first_followup_seconds,
                        )
                    ],
                )
                continue
            events = followup["events"]
            first_fdv = followup["first_fdv"]
            birth_row = {
                "observation_id": candidate.get("observation_id") or f"official-birth-{mint[:12]}-{int(first_attempt)}",
                "mint": mint,
                "creator": candidate.get("creator"),
                "create_signature": candidate.get("transaction_signature") or candidate.get("signature") or candidate.get("create_signature"),
                "pool_address": candidate.get("pool_address") or candidate.get("bonding_curve"),
                "bonding_curve": candidate.get("bonding_curve") or candidate.get("pool_address"),
                "associated_bonding_curve": candidate.get("associated_bonding_curve"),
                "create_time": _num(candidate.get("launch_time") or candidate.get("block_time") or candidate.get("create_time")),
                "observed_time": _num(candidate.get("observed_at")) or first_attempt,
                "first_followup_attempt_time": first_attempt,
                "first_followup_before_any_trade_if_known": len(events) == 0,
                "first_followup_before_10k": first_fdv is None or first_fdv < TARGET_LEVELS["10k"],
                "first_followup_before_20k": first_fdv is None or first_fdv < TARGET_LEVELS["20k"],
                "source_provenance": "helius_pumpfun_create_websocket_logs",
            }
            machine.record_birth(birth_row)
            _append_jsonl(config.helius_ws_raw_path, [{**candidate, "official_sample_label": OFFICIAL_SAMPLE_LABEL}])
            if events:
                _append_jsonl(config.events_path, [{**event, "sample_label": OFFICIAL_SAMPLE_LABEL, "mint": mint} for event in events])
            for event in events:
                if _num(event.get("fdv_proxy")) is None:
                    continue
                machine.record_path(
                    {
                        "mint": mint,
                        "timestamp": event.get("timestamp") or event.get("observed_at") or event.get("block_time") or time.time(),
                        "fdv_proxy": event.get("fdv_proxy"),
                        "event_count": event.get("event_count") or 1,
                        "buy_count": event.get("buy_count") or (1 if str(event.get("side") or "").lower() == "buy" else 0),
                        "sell_count": event.get("sell_count") or (1 if str(event.get("side") or "").lower() == "sell" else 0),
                        "active_wallet_count": event.get("active_wallet_count") or event.get("active_wallets") or 1,
                        "source_provenance": "helius_mint_followup_observed_path",
                    }
                )
            births_seen += 1
        run_active_lifecycle_followup_cycle(
            machine,
            fetcher,
            signatures_per_mint=signatures_per_mint,
            transactions_per_mint=transactions_per_mint,
        )
    if time.monotonic() >= deadline and births_seen < int(target_births):
        warnings.append("max_runtime_minutes_reached")
    raw_transactions = list(getattr(fetcher, "raw_transactions", []))
    if raw_transactions:
        _append_jsonl(config.helius_rpc_raw_path, raw_transactions)
    credits_used = _requests_used(source, fetcher)
    _write_status(config, target_crossed_20k=target_crossed_20k, credits_used=credits_used)
    audit, audit_paths = build_official_lifecycle_quality_audit(config)
    status = official_lifecycle_status(config, target_crossed_20k=target_crossed_20k)
    result = {
        "report_id": "official_lifecycle_watch_live_smoke_v0",
        "execute": True,
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "smoke_births_observed": births_seen,
        "under_5s_followup_count": status["fresh_births_under_5s_followup"],
        "active_watches_created": status["trigger_qualified_active_watches"] + status["matured_trigger_qualified"],
        "matured_counts": {
            "matured_reached_1m": status["reached_1m"],
            "matured_terminal_collapse": status["terminal_collapse"],
            "matured_inactive_timeout": status["inactive_timeout"],
            "matured_max_age": status["max_age"],
        },
        "network_calls_made": credits_used,
        "estimated_helius_credits_used": credits_used,
        "quality_audit_result": audit,
        "quality_audit_paths": {key: str(value) for key, value in audit_paths.items()},
        "lifecycle_state_file": str(config.state_path),
        "readiness_classification": _readiness_from_audit(audit),
        "warnings": sorted(set(warnings)),
    }
    _write_json(config.report_root / "official_lifecycle_live_smoke_summary.json", result)
    return result


def official_lifecycle_status(config: OfficialLifecycleConfig, *, target_crossed_20k: int | None = None) -> dict[str, Any]:
    initialize_official_lifecycle_namespace(config)
    state = _read_state(config)
    births = _read_jsonl(config.births_path)
    paths = _read_jsonl(config.followup_paths_path)
    status_payload = _read_json(config.status_path)
    mints = state.get("mints", {})
    state_counts = Counter(row.get("state") for row in mints.values())
    fresh_under_5 = sum(1 for row in births if (_num(row.get("create_to_first_followup_seconds")) is not None and _num(row.get("create_to_first_followup_seconds")) <= 5))
    first_before_10k = sum(1 for row in births if row.get("first_followup_before_10k") is True)
    first_before_20k = sum(1 for row in births if row.get("first_followup_before_20k") is True)
    crossed_counts = {level: len({row.get("mint") for row in paths if row.get(f"crossed_{level}") is True}) for level in TARGET_LEVELS}
    active = [mint for mint, row in mints.items() if row.get("state") == "trigger_qualified_active_watch"]
    matured_trigger = [mint for mint, row in mints.items() if row.get("entered_trigger_qualified_at") and row.get("state") in MATURITY_STATES]
    target = int(target_crossed_20k or config.target_crossed_20k)
    audit, _ = build_official_lifecycle_quality_audit(config, write_outputs=False)
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "births_observed": len({row.get("mint") for row in births if row.get("mint")}),
        "fresh_births_under_5s_followup": fresh_under_5,
        "births_with_fdv_path": len({row.get("mint") for row in paths if _num(row.get("fdv_proxy")) is not None}),
        "first_path_before_10k": first_before_10k,
        "first_path_before_20k": first_before_20k,
        "crossed_10k": crossed_counts["10k"],
        "crossed_15k": crossed_counts["15k"],
        "crossed_20k": crossed_counts["20k"],
        "trigger_qualified_active_watches": len(active),
        "matured_trigger_qualified": len(matured_trigger),
        "reached_50k": crossed_counts["50k"],
        "reached_100k": crossed_counts["100k"],
        "reached_500k": crossed_counts["500k"],
        "reached_1m": crossed_counts["1m"],
        "terminal_collapse": state_counts["matured_terminal_collapse"],
        "inactive_timeout": state_counts["matured_inactive_timeout"],
        "max_age": state_counts["matured_max_age"],
        "data_limited": state_counts["data_limited"],
        "official_crossed_20k_target_progress": f"{crossed_counts['20k']}/{target}",
        "credits_used": int(status_payload.get("credits_used") or 0),
        "warnings": audit["warnings"],
        "quality_status": audit["quality_status"],
        "recommendation": audit["recommendation"],
    }


def format_official_lifecycle_status(status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Official Lifecycle Watch v1 Status",
            f"Births observed: {status['births_observed']}",
            f"Fresh births with under-5s follow-up: {status['fresh_births_under_5s_followup']}",
            f"Births with FDV path: {status['births_with_fdv_path']}",
            f"First path before 10k: {status['first_path_before_10k']}",
            f"First path before 20k: {status['first_path_before_20k']}",
            f"Crossed 10k: {status['crossed_10k']}",
            f"Crossed 15k: {status['crossed_15k']}",
            f"Crossed 20k: {status['crossed_20k']}",
            f"Trigger-qualified active watches: {status['trigger_qualified_active_watches']}",
            f"Matured trigger-qualified: {status['matured_trigger_qualified']}",
            f"Reached 50k: {status['reached_50k']}",
            f"Reached 100k: {status['reached_100k']}",
            f"Reached 500k: {status['reached_500k']}",
            f"Reached 1M: {status['reached_1m']}",
            f"Terminal collapse: {status['terminal_collapse']}",
            f"Inactive timeout: {status['inactive_timeout']}",
            f"Max age: {status['max_age']}",
            f"Data-limited: {status['data_limited']}",
            f"Official crossed-20k target progress: {status['official_crossed_20k_target_progress']}",
            f"Credits used: {status['credits_used']}",
            f"Warnings: {status['warnings']}",
            f"Quality status: {status['quality_status']}",
            f"Recommendation: {status['recommendation']}",
        ]
    )


def build_official_lifecycle_quality_audit(
    config: OfficialLifecycleConfig,
    *,
    write_outputs: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    initialize_official_lifecycle_namespace(config)
    births = _read_jsonl(config.births_path)
    paths = _read_jsonl(config.followup_paths_path)
    state = _read_state(config)
    mints = state.get("mints", {})
    birth_mints = {row.get("mint") for row in births if row.get("mint")}
    path_mints = {row.get("mint") for row in paths if row.get("mint")}
    crossed_20k_mints = {row.get("mint") for row in paths if row.get("crossed_20k") is True and row.get("mint")}
    active_or_matured = {
        mint
        for mint, row in mints.items()
        if row.get("state") == "trigger_qualified_active_watch" or row.get("state") in MATURITY_STATES
    }
    warnings: list[str] = []
    duplicate_mints = _duplicates([str(row.get("mint")) for row in births if row.get("mint")])
    duplicate_observation_ids = _duplicates([str(row.get("observation_id")) for row in births if row.get("observation_id")])
    if duplicate_mints:
        warnings.append("duplicate_mints")
    if duplicate_observation_ids:
        warnings.append("duplicate_observation_ids")
    if crossed_20k_mints - set(mints):
        warnings.append("crossed_20k_missing_lifecycle_state")
    if crossed_20k_mints - active_or_matured:
        warnings.append("trigger_qualified_mint_not_active_or_matured")
    if any(_num(row.get("fdv_proxy")) is not None and _num(row.get("fdv_proxy")) <= 0 for row in paths):
        warnings.append("fdv_zero_or_negative")
    if _has_high_conversion_ratio(len(crossed_20k_mints), len(birth_mints)):
        warnings.append("high_conversion_ratio_warning")
    if any(not _milestone_order_ok(row) for row in paths):
        warnings.append("milestone_ordering_violation")
    source_counts = dict(Counter(str(row.get("source_provenance") or "unknown") for row in paths))
    density = Counter(row.get("mint") for row in paths if row.get("mint"))
    quality_status = "official_lifecycle_watch_needs_repair" if warnings else "official_lifecycle_watch_ready_for_100_birth_smoke"
    audit = {
        "report_id": "official_lifecycle_quality_audit_v0",
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "network_calls_made": 0,
        "births_observed": len(birth_mints),
        "path_rows": len(paths),
        "events_rows": _row_count(config.events_path),
        "metadata_rows": _row_count(config.metadata_path),
        "drawdown_rows": _row_count(config.drawdowns_path),
        "state_counts": dict(Counter(row.get("state") for row in mints.values())),
        "funnel": {
            "all_fresh_births": len(birth_mints),
            "births_with_fdv_path_evidence": len(path_mints),
            "fresh_births_first_path_before_10k": sum(1 for row in births if row.get("first_followup_before_10k") is True),
            "fresh_births_first_path_before_20k": sum(1 for row in births if row.get("first_followup_before_20k") is True),
            "trigger_qualified_active_watch_mints": sum(1 for row in mints.values() if row.get("state") == "trigger_qualified_active_watch"),
            "matured_trigger_qualified_mints": sum(1 for row in mints.values() if row.get("entered_trigger_qualified_at") and row.get("state") in MATURITY_STATES),
        },
        "dedupe": {
            "duplicate_mints": duplicate_mints,
            "duplicate_observation_ids": duplicate_observation_ids,
        },
        "milestone_provenance": {
            "observed_path_rows_only": not any(str(row.get("source_provenance") or "").lower() in {"later_outcome_label", "outcome_label"} for row in paths),
            "later_outcome_labels": sum(1 for row in paths if str(row.get("source_provenance") or "").lower() in {"later_outcome_label", "outcome_label"}),
        },
        "source_mix": source_counts,
        "path_density": {
            "min": min(density.values()) if density else 0,
            "median": median(density.values()) if density else 0,
            "max": max(density.values()) if density else 0,
        },
        "warnings": sorted(set(warnings)),
        "quality_status": quality_status,
        "recommendation": (
            "Repair lifecycle state/drop warnings before scaled collection."
            if warnings
            else "Run bounded 100-birth official smoke before scaled collection."
        ),
    }
    paths_out: dict[str, Path] = {}
    if write_outputs:
        paths_out = {
            "json": config.report_root / "official_lifecycle_quality_audit.json",
            "markdown": config.report_root / "official_lifecycle_quality_audit.md",
        }
        _write_json(paths_out["json"], audit)
        paths_out["markdown"].write_text(_audit_markdown(audit), encoding="utf-8")
    return audit, paths_out


def _empty_state(config: OfficialLifecycleConfig) -> dict[str, Any]:
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "created_at": _utc_now_iso(),
        "mints": {},
        "counters": {"official_crossed_20k_count": 0},
        "config": {
            "max_active_birth_followups": config.max_active_birth_followups,
            "max_active_trigger_watches": config.max_active_trigger_watches,
        },
    }


def _read_state(config: OfficialLifecycleConfig) -> dict[str, Any]:
    payload = _read_json(config.state_path)
    if not payload:
        payload = _empty_state(config)
    payload.setdefault("mints", {})
    payload.setdefault("counters", {})
    return payload


def _write_status(config: OfficialLifecycleConfig, *, target_crossed_20k: int, credits_used: int) -> None:
    _write_json(
        config.status_path,
        {
            "sample_label": OFFICIAL_SAMPLE_LABEL,
            "updated_at": _utc_now_iso(),
            "target_crossed_20k": target_crossed_20k,
            "credits_used": credits_used,
            "network_calls_made": 0,
        },
    )


def _path_row(
    source: dict[str, Any],
    state_row: dict[str, Any],
    *,
    timestamp: float,
    fdv: float | None,
    local_high: float | None,
    drawdown_pct: float | None,
) -> dict[str, Any]:
    event_count = _num(source.get("event_count"))
    buy_count = _num(source.get("buy_count"))
    sell_count = _num(source.get("sell_count"))
    active_wallet_count = _num(source.get("active_wallet_count") or source.get("active_wallets"))
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "timestamp": timestamp,
        "mint": state_row["mint"],
        "state": state_row["state"],
        "fdv_proxy": fdv,
        "event_count": event_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "active_wallet_count": active_wallet_count,
        "fdv_per_event": _safe_ratio(fdv, event_count),
        "fdv_per_buy": _safe_ratio(fdv, buy_count),
        "fdv_per_active_wallet": _safe_ratio(fdv, active_wallet_count),
        "buy_sell_ratio": _safe_ratio(buy_count, sell_count),
        **{f"crossed_{level}": bool(fdv is not None and fdv >= threshold) for level, threshold in TARGET_LEVELS.items()},
        "local_high_fdv": local_high,
        "drawdown_pct": drawdown_pct,
        "reclaim_status": _reclaim_status(fdv, local_high),
        "source_provenance": source.get("source_provenance") or source.get("source") or "observed_path_row",
    }


def _drawdown_row(path: dict[str, Any]) -> dict[str, Any]:
    drawdown = _num(path.get("drawdown_pct"))
    return {
        "sample_label": OFFICIAL_SAMPLE_LABEL,
        "mint": path.get("mint"),
        "timestamp": path.get("timestamp"),
        "state": path.get("state"),
        "local_high_fdv": path.get("local_high_fdv"),
        "drawdown_pct": drawdown,
        "first_20pct_drawdown_time": path.get("timestamp") if drawdown is not None and drawdown >= 20 else None,
        "first_30pct_drawdown_time": path.get("timestamp") if drawdown is not None and drawdown >= 30 else None,
        "first_40pct_drawdown_time": path.get("timestamp") if drawdown is not None and drawdown >= 40 else None,
        "first_50pct_drawdown_time": path.get("timestamp") if drawdown is not None and drawdown >= 50 else None,
        "reclaim_prior_high_time": path.get("timestamp") if path.get("reclaim_status") == "at_or_above_local_high" else None,
        "new_high_after_drawdown_time": path.get("timestamp") if path.get("reclaim_status") == "at_or_above_local_high" else None,
        "bounce_pct_30s": None,
        "bounce_pct_60s": None,
        "bounce_pct_2m": None,
        "bounce_pct_5m": None,
        "no_reclaim_after_5m": False,
        "no_reclaim_after_10m": False,
        "source_provenance": path.get("source_provenance"),
    }


def _next_state(
    previous_state: str | None,
    crossed_levels: list[str],
    fdv: float | None,
    local_high: float | None,
    drawdown_pct: float | None,
) -> str:
    if previous_state in MATURITY_STATES:
        return previous_state
    if "1m" in crossed_levels:
        return "matured_reached_1m"
    if previous_state == "trigger_qualified_active_watch" and drawdown_pct is not None and drawdown_pct >= 70:
        return "matured_terminal_collapse"
    if "20k" in crossed_levels:
        return "trigger_qualified_active_watch"
    if "15k" in crossed_levels:
        return "crossed_15k"
    if "10k" in crossed_levels:
        return "crossed_10k"
    if fdv is not None:
        return "fdv_followup_started"
    return previous_state or "birth_watch"


def _freshness_class(birth: dict[str, Any], *, create_time: float | None, first_attempt: float | None) -> str:
    if birth.get("freshness_class"):
        return str(birth["freshness_class"])
    delta = _delta(create_time, first_attempt)
    if delta is None:
        return "unknown_freshness"
    if delta <= 5 and birth.get("first_followup_before_any_trade_if_known") is True:
        return "immediate_followup_no_trade_yet"
    if delta <= 5:
        return "true_birth_observed"
    if birth.get("first_followup_already_above_20k"):
        return "first_followup_already_above_20k"
    if birth.get("first_followup_already_above_10k"):
        return "first_followup_already_above_10k"
    if delta <= 60:
        return "near_birth_observed"
    return "first_followup_after_activity"


def _mock_births(count: int) -> list[dict[str, Any]]:
    base = 1_800_000_000
    return [
        {
            "observation_id": f"official-birth-mint-{idx}",
            "mint": f"official-mint-{idx}",
            "creator": f"creator-{idx}",
            "create_signature": f"create-sig-{idx}",
            "create_time": base + idx * 10,
            "observed_time": base + idx * 10 + 1,
            "first_followup_attempt_time": base + idx * 10 + 2,
            "first_followup_before_any_trade_if_known": True,
            "first_followup_before_10k": True,
            "first_followup_before_20k": True,
            "source_provenance": "mock_verified_pumpfun_create",
        }
        for idx in range(1, count + 1)
    ]


def _mock_paths_for_birth(birth: dict[str, Any]) -> list[dict[str, Any]]:
    mint = birth["mint"]
    start = _num(birth["create_time"]) or 0
    idx = int(str(mint).rsplit("-", 1)[-1])
    if idx == 1:
        fdvs = [5_000, 12_000, 22_000, 55_000, 110_000, 520_000, 1_100_000]
    elif idx == 2:
        fdvs = [4_000, 11_000, 21_000, 45_000]
    else:
        fdvs = [3_000, 8_000, 12_000]
    return [
        {
            "mint": mint,
            "timestamp": start + offset * 2,
            "fdv_proxy": fdv,
            "event_count": offset,
            "buy_count": max(1, offset - 1),
            "sell_count": 1 if offset > 2 else 0,
            "active_wallet_count": max(1, offset),
            "source_provenance": "mock_observed_path",
        }
        for offset, fdv in enumerate(fdvs, start=1)
    ]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _row_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _mint(row: dict[str, Any]) -> str:
    return str(row.get("mint") or row.get("token_mint") or "")


def _followup_addresses(row: dict[str, Any]) -> list[str]:
    addresses: list[str] = []
    seen: set[str] = set()
    for key in ["pool_address", "bonding_curve", "associated_bonding_curve"]:
        address = row.get(key)
        if not address:
            continue
        address = str(address)
        if address in seen:
            continue
        seen.add(address)
        addresses.append(address)
    return addresses


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in {None, 0}:
        return None
    return num / den


def _crossed_levels(fdv: float | None) -> list[str]:
    if fdv is None:
        return []
    return [level for level, threshold in TARGET_LEVELS.items() if fdv >= threshold]


def _drawdown_pct(local_high: float | None, fdv: float | None) -> float | None:
    if local_high in {None, 0} or fdv is None:
        return None
    return max(0.0, (local_high - fdv) / local_high * 100)


def _reclaim_status(fdv: float | None, local_high: float | None) -> str:
    if fdv is None or local_high is None:
        return "unknown"
    if fdv >= local_high:
        return "at_or_above_local_high"
    return "below_local_high"


def _duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _has_high_conversion_ratio(crossed_20k: int, births: int) -> bool:
    return births >= 20 and crossed_20k / births > 0.75


def _milestone_order_ok(row: dict[str, Any]) -> bool:
    ordered = ["10k", "20k", "50k", "100k", "500k", "1m"]
    seen_false = False
    for level in ordered:
        crossed = row.get(f"crossed_{level}") is True
        if seen_false and crossed:
            return False
        if not crossed:
            seen_false = True
    return True


def _readiness_from_audit(audit: dict[str, Any]) -> str:
    if audit["warnings"]:
        return "official_lifecycle_watch_needs_repair"
    if audit["births_observed"] >= 100:
        return "official_lifecycle_watch_ready_for_scaled_collection"
    return "official_lifecycle_watch_ready_for_100_birth_smoke"


def _requests_used(source: Any, fetcher: Any) -> int:
    return int(getattr(source, "requests_used", 0) or 0) + int(getattr(fetcher, "requests_used", 0) or 0)


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Official Lifecycle Watch v1 Manifest",
            "",
            f"- Sample label: `{manifest['sample_label']}`",
            f"- Starts from zero: `{manifest['starts_from_zero']}`",
            f"- Old quarantined sample excluded: `{manifest['old_quarantined_sample_excluded']}`",
            f"- Collection start time: `{manifest['collection_start_time']}`",
            "",
            "## Approved Uses",
            *[f"- {item}" for item in APPROVED_USES],
            "",
            "## Prohibited Uses",
            *[f"- {item}" for item in PROHIBITED_USES],
            "",
            "## Guardrails",
            *[f"- `{item}`" for item in GUARDRAILS],
            "",
        ]
    )


def _audit_markdown(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Official Lifecycle Watch v1 Quality Audit",
            "",
            f"- Quality status: `{audit['quality_status']}`",
            f"- Births observed: `{audit['births_observed']}`",
            f"- Path rows: `{audit['path_rows']}`",
            f"- Warnings: `{audit['warnings']}`",
            f"- Recommendation: {audit['recommendation']}",
            "",
            "## Funnel",
            *[f"- {key}: `{value}`" for key, value in audit["funnel"].items()],
            "",
        ]
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
