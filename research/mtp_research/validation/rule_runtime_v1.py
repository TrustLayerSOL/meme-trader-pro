"""Paper-only hot-path rule runtime for the frozen historical rule.

This module records simulated decisions only. It does not execute wallets,
orders, swaps, or transactions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
import csv
import html
import json
import time

from research.mtp_research.data_paths import data_lake_root


RUNTIME_LABEL = "rule_runtime_v1"
FROZEN_BUY_RULE_ID = "BROAD_10K_WATCH_20K_BUY"
FROZEN_EXIT_RULE_ID = "EXIT_NO_RECLAIM"
MILESTONES = [10_000, 15_000, 20_000, 50_000, 100_000, 500_000, 1_000_000]
ENTRY_THRESHOLD_FDV = 20_000.0
WATCH_THRESHOLD_FDV = 10_000.0
CONFIRMATION_WINDOW_SECONDS = 120.0
DRAW_DOWN_EXIT_PCT = 0.30
NO_RECLAIM_EXIT_SECONDS = 600.0
SPIKE_REJECTION_RATIO = 3.0
FDV_ANOMALY_HIGH = 100_000_000.0


@dataclass(frozen=True)
class RuleRuntimeConfig:
    data_root: Path | str | None = None
    starting_wallet_usd: float = 300.0
    position_fraction: float = 0.05
    confirmation_window_seconds: float = CONFIRMATION_WINDOW_SECONDS
    allow_unfrozen_efficiency_baseline: bool = True

    @property
    def root(self) -> Path:
        return Path(self.data_root or data_lake_root()).expanduser()

    @property
    def runtime_root(self) -> Path:
        return self.root / "data" / "forward_observation" / RUNTIME_LABEL

    @property
    def raw_root(self) -> Path:
        return self.root / "data" / "raw" / "forward_observation" / RUNTIME_LABEL

    @property
    def report_root(self) -> Path:
        return self.root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / RUNTIME_LABEL

    @property
    def runtime_manifest_json_path(self) -> Path:
        return self.runtime_root / "runtime_manifest.json"

    @property
    def runtime_manifest_md_path(self) -> Path:
        return self.runtime_root / "runtime_manifest.md"

    @property
    def runtime_state_path(self) -> Path:
        return self.runtime_root / "runtime_state.json"

    @property
    def path_events_path(self) -> Path:
        return self.runtime_root / "path_events.jsonl"

    @property
    def paper_trades_path(self) -> Path:
        return self.runtime_root / "paper_trades.jsonl"

    @property
    def paper_decisions_path(self) -> Path:
        return self.runtime_root / "paper_decisions.jsonl"

    @property
    def latency_events_path(self) -> Path:
        return self.runtime_root / "latency_events.jsonl"

    @property
    def monitor_json_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_monitor.json"

    @property
    def monitor_md_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_monitor.md"

    @property
    def monitor_html_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_monitor.html"

    @property
    def trades_csv_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_paper_trades.csv"


class RuleRuntimePriorityScheduler:
    priority_order = [
        "paper_position_open",
        "confirmed_10k_watch",
        "first_fdv_path",
        "light_watch",
        "metadata_background",
    ]

    def __init__(self) -> None:
        self._queues: dict[str, deque[dict[str, Any]]] = {name: deque() for name in self.priority_order}

    def add_job(self, job_type: str, payload: dict[str, Any]) -> None:
        if job_type not in self._queues:
            raise ValueError(f"unknown rule runtime job type: {job_type}")
        self._queues[job_type].append(dict(payload))

    def pop_next_job(self) -> dict[str, Any]:
        for job_type in self.priority_order:
            if self._queues[job_type]:
                row = self._queues[job_type].popleft()
                row.setdefault("job_type", job_type)
                return row
        raise IndexError("rule runtime scheduler is empty")

    def queue_sizes(self) -> dict[str, int]:
        return {name: len(queue) for name, queue in self._queues.items()}


class RuleRuntimeEngine:
    def __init__(self, config: RuleRuntimeConfig) -> None:
        self.config = config
        if not config.runtime_state_path.exists():
            initialize_rule_runtime(config)

    def process_path_event(self, event: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        state = _load_state(self.config)
        normalized = _normalize_path_event(event)
        mint = normalized["mint"]
        fdv = float(normalized["fdv_proxy"])
        timestamp = float(normalized["timestamp"])
        event_observed_at = float(normalized.get("event_observed_at") or timestamp)
        candidate = state["candidates"].setdefault(mint, _new_candidate(mint))
        previous_state = candidate.get("state")
        candidate["path_rows"].append(normalized)
        candidate["path_rows"] = sorted(candidate["path_rows"], key=lambda row: (float(row["timestamp"]), float(row["fdv_proxy"])))
        _append_jsonl(self.config.path_events_path, normalized)

        result = {
            "mint": mint,
            "state": candidate.get("state"),
            "tier": candidate.get("tier"),
            "confirmed_crossed_10k": False,
            "confirmed_crossed_20k": False,
            "single_row_spike_flag": bool(candidate.get("single_row_spike_flag")),
            "same_timestamp_major_jump_flag": bool(candidate.get("same_timestamp_major_jump_flag")),
            "fdv_anomaly_flag": bool(candidate.get("fdv_anomaly_flag")),
            "paper_buy_created": False,
            "paper_sell_created": False,
        }

        if fdv <= 0 or fdv >= FDV_ANOMALY_HIGH:
            candidate["state"] = "rejected_fdv_anomaly"
            candidate["tier"] = -1
            candidate["fdv_anomaly_flag"] = True
            _record_rejection(self.config, candidate, normalized, "rejected_fdv_anomaly", "fdv_anomaly")
            _finish_event(self.config, state, candidate, normalized, started, previous_state)
            return _result(candidate, result)

        candidate["last_fdv_proxy"] = fdv
        candidate["last_path_time"] = timestamp
        candidate["max_fdv_proxy"] = max(float(candidate.get("max_fdv_proxy") or 0.0), fdv)
        if candidate.get("state") in (None, "birth_seen", "light_watch"):
            candidate["state"] = "fdv_path_seen"
            candidate["tier"] = 1

        _update_raw_milestones(candidate, normalized)
        _update_confirmed_milestones(candidate, self.config.confirmation_window_seconds)
        _update_rejection_flags(candidate)
        _update_state_from_milestones(candidate)

        if candidate.get("same_timestamp_major_jump_flag"):
            candidate["state"] = "rejected_same_timestamp_jump"
            candidate["tier"] = -1
            _record_rejection(self.config, candidate, normalized, "rejected_same_timestamp_jump", "same_timestamp_major_jump")
        elif candidate.get("single_row_spike_flag"):
            candidate["state"] = "rejected_spike"
            candidate["tier"] = -1
            _record_rejection(self.config, candidate, normalized, "rejected_spike", "single_row_fdv_spike")
        elif candidate.get("confirmed_crossed_20k") and not candidate.get("paper_buy_created") and not candidate.get("paper_closed"):
            decision = _evaluate_entry(self.config, state, candidate, normalized)
            _append_jsonl(self.config.paper_decisions_path, decision)
            if decision["decision"] == "paper_buy":
                _create_paper_buy(self.config, state, candidate, normalized, decision)
                result["paper_buy_created"] = True

        if candidate.get("paper_buy_created") and not candidate.get("paper_closed"):
            sell = _evaluate_exit(self.config, state, candidate, normalized)
            if sell:
                _append_jsonl(self.config.paper_decisions_path, sell)
                _create_paper_sell(self.config, state, candidate, normalized, sell)
                result["paper_sell_created"] = True

        _finish_event(self.config, state, candidate, normalized, started, previous_state)
        _write_monitor(self.config, state)
        return _result(candidate, result)


def initialize_rule_runtime(config: RuleRuntimeConfig, *, reset: bool = False) -> dict[str, Any]:
    config.runtime_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(config)
    _write_json(config.runtime_manifest_json_path, manifest)
    config.runtime_manifest_md_path.write_text(_manifest_md(manifest), encoding="utf-8")
    if reset or not config.runtime_state_path.exists():
        _write_json(config.runtime_state_path, _initial_state(config))
        for path in [config.path_events_path, config.paper_trades_path, config.paper_decisions_path, config.latency_events_path]:
            path.write_text("", encoding="utf-8")
    else:
        for path in [config.path_events_path, config.paper_trades_path, config.paper_decisions_path, config.latency_events_path]:
            path.touch(exist_ok=True)
    state = _load_state(config)
    _write_monitor(config, state)
    return {
        "runtime_label": RUNTIME_LABEL,
        "runtime_root": str(config.runtime_root),
        "raw_root": str(config.raw_root),
        "report_root": str(config.report_root),
        "paper_trading_enabled": True,
        "live_trading_enabled": False,
        "monitor_html_path": str(config.monitor_html_path),
    }


def run_rule_runtime_once(config: RuleRuntimeConfig, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    engine = RuleRuntimeEngine(config)
    events = events or []
    buys = 0
    sells = 0
    for event in events:
        result = engine.process_path_event(event)
        buys += int(bool(result.get("paper_buy_created")))
        sells += int(bool(result.get("paper_sell_created")))
    status = rule_runtime_status(config)
    return {"processed_events": len(events), "paper_buys_created": buys, "paper_sells_created": sells, **status}


def rule_runtime_status(config: RuleRuntimeConfig) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    state = _load_state(config)
    candidates = state.get("candidates") or {}
    trades = _read_jsonl(config.paper_trades_path)
    latency = _read_jsonl(config.latency_events_path)
    buys = [row for row in trades if row.get("side") == "paper_buy"]
    sells = [row for row in trades if row.get("side") == "paper_sell"]
    queue_sizes = state.get("queue_sizes") or RuleRuntimePriorityScheduler().queue_sizes()
    detection = [_num(row.get("detection_to_rule_latency_ms")) for row in latency]
    age = [_num(row.get("state_age_ms")) for row in latency]
    status = {
        "runtime_label": RUNTIME_LABEL,
        "frozen_buy_rule": FROZEN_BUY_RULE_ID,
        "frozen_exit_rule": FROZEN_EXIT_RULE_ID,
        "live_trading_enabled": False,
        "paper_trading_enabled": True,
        "confirmed_10k_watches": sum(1 for row in candidates.values() if row.get("confirmed_crossed_10k")),
        "confirmed_20k_entry_candidates": sum(1 for row in candidates.values() if row.get("confirmed_crossed_20k")),
        "paper_buys": len(buys),
        "open_paper_positions": len(state.get("open_positions") or {}),
        "paper_sells": len(sells),
        "rejected_spike_candidates": sum(1 for row in candidates.values() if row.get("state") == "rejected_spike"),
        "rejected_same_timestamp_jumps": sum(1 for row in candidates.values() if row.get("state") == "rejected_same_timestamp_jump"),
        "rejected_fdv_anomalies": sum(1 for row in candidates.values() if row.get("fdv_anomaly_flag")),
        "archived_no_activity": sum(1 for row in candidates.values() if row.get("state") == "archived_no_activity"),
        "latency_p50_p90_p99": _percentiles(detection),
        "state_age_p50_p90_p99": _percentiles(age),
        "queue_sizes": queue_sizes,
        "metadata_hot_path_blocked": True,
        "no_real_trade_flag": True,
        "wallet_usd": state.get("wallet_usd"),
        "cash_usd": state.get("cash_usd"),
        "monitor_html_path": str(config.monitor_html_path),
        "paper_trades_path": str(config.paper_trades_path),
        "latency_events_path": str(config.latency_events_path),
        "warnings": state.get("warnings") or [],
    }
    _write_monitor(config, state)
    return status


def archive_stale_candidates(config: RuleRuntimeConfig, *, now: float | None = None, timeout_seconds: float = 120.0) -> dict[str, Any]:
    state = _load_state(config)
    now = float(now if now is not None else time.time())
    archived = 0
    for candidate in (state.get("candidates") or {}).values():
        if candidate.get("state") in {"paper_position_open", "paper_position_closed"}:
            continue
        last_path = _num(candidate.get("last_path_time")) or _num(candidate.get("first_seen_at")) or now
        if now - last_path >= timeout_seconds and not candidate.get("confirmed_crossed_10k"):
            candidate["state"] = "archived_no_activity"
            candidate["tier"] = -1
            archived += 1
    _write_json(config.runtime_state_path, state)
    _write_monitor(config, state)
    return {"archived_no_activity": archived}


def _manifest(config: RuleRuntimeConfig) -> dict[str, Any]:
    return {
        "runtime_label": RUNTIME_LABEL,
        "frozen_buy_rule_id": FROZEN_BUY_RULE_ID,
        "frozen_exit_rule_id": FROZEN_EXIT_RULE_ID,
        "source": "historical_rule_discovery",
        "paper_trading_enabled": True,
        "live_trading_enabled": False,
        "private_keys_allowed": False,
        "raw_milestones_allowed_for_entry": False,
        "single_row_spikes_allowed": False,
        "same_timestamp_major_jump_allowed_for_entry": False,
        "metadata_hot_path_allowed": False,
        "getTransaction_hot_path_required": False,
        "confirmation_window_seconds": float(config.confirmation_window_seconds),
        "starting_wallet_usd": float(config.starting_wallet_usd),
        "position_fraction": float(config.position_fraction),
        "efficiency_threshold_status": "efficiency_unfrozen",
        "broad_baseline_paper_buy_allowed": bool(config.allow_unfrozen_efficiency_baseline),
        "created_at": _utc_now(),
    }


def _manifest_md(manifest: dict[str, Any]) -> str:
    lines = [
        "# Rule Runtime v1 Manifest",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for key, value in manifest.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _initial_state(config: RuleRuntimeConfig) -> dict[str, Any]:
    wallet = _round_money(config.starting_wallet_usd)
    return {
        "runtime_label": RUNTIME_LABEL,
        "wallet_usd": wallet,
        "cash_usd": wallet,
        "starting_wallet_usd": wallet,
        "position_fraction": float(config.position_fraction),
        "candidates": {},
        "open_positions": {},
        "closed_positions": {},
        "rejected_candidates": {},
        "queue_sizes": RuleRuntimePriorityScheduler().queue_sizes(),
        "warnings": ["fdv_efficiency_threshold_unfrozen"],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "guardrails": [
            "paper_only_accounting",
            "live_trading_disabled",
            "metadata_not_hot_path",
            "confirmed_milestones_only_for_entry",
        ],
    }


def _new_candidate(mint: str) -> dict[str, Any]:
    now = time.time()
    return {
        "mint": mint,
        "state": "birth_seen",
        "tier": 0,
        "first_seen_at": now,
        "path_rows": [],
        "raw_milestones": {},
        "confirmed_milestones": {},
        "milestone_first_times": {},
        "confirmed_milestone_times": {},
        "single_row_spike_flag": False,
        "same_timestamp_major_jump_flag": False,
        "fdv_anomaly_flag": False,
        "path_order_valid": True,
        "paper_buy_created": False,
        "paper_closed": False,
        "local_high_fdv": 0.0,
        "drawdowns": {},
    }


def _normalize_path_event(event: dict[str, Any]) -> dict[str, Any]:
    mint = str(event.get("mint") or "").strip()
    if not mint:
        raise ValueError("path event requires mint")
    timestamp = _num(event.get("timestamp"))
    fdv = _num(event.get("fdv_proxy") if event.get("fdv_proxy") is not None else event.get("fdv"))
    if timestamp is None:
        raise ValueError("path event requires timestamp")
    if fdv is None:
        raise ValueError("path event requires fdv_proxy")
    return {
        "mint": mint,
        "timestamp": float(timestamp),
        "event_observed_at": float(_num(event.get("event_observed_at")) or timestamp),
        "fdv_proxy": float(fdv),
        "event_count": int(_num(event.get("event_count")) or 0),
        "buy_count": int(_num(event.get("buy_count")) or 0),
        "sell_count": int(_num(event.get("sell_count")) or 0),
        "active_wallet_count": int(_num(event.get("active_wallet_count")) or 0),
        "data_source": str(event.get("data_source") or "helius_rpc_read_only"),
        "source_event_type": str(event.get("source_event_type") or "fdv_path"),
        "recorded_at": _utc_now(),
    }


def _update_raw_milestones(candidate: dict[str, Any], row: dict[str, Any]) -> None:
    fdv = float(row["fdv_proxy"])
    ts = float(row["timestamp"])
    for level in MILESTONES:
        key = _level_key(level)
        if fdv >= level:
            candidate["raw_milestones"][f"raw_crossed_{key}"] = True
            candidate["milestone_first_times"].setdefault(key, ts)


def _update_confirmed_milestones(candidate: dict[str, Any], window_seconds: float) -> None:
    rows = candidate.get("path_rows") or []
    for level in MILESTONES:
        key = _level_key(level)
        if candidate["confirmed_milestones"].get(f"confirmed_crossed_{key}"):
            continue
        crossing_rows = [row for row in rows if float(row.get("fdv_proxy") or 0.0) >= level]
        for first in crossing_rows:
            first_ts = float(first["timestamp"])
            confirmations = [
                row
                for row in crossing_rows
                if 0 <= float(row["timestamp"]) - first_ts <= window_seconds
            ]
            if len(confirmations) >= 2:
                candidate["confirmed_milestones"][f"confirmed_crossed_{key}"] = True
                candidate["confirmed_milestone_times"][key] = float(confirmations[1]["timestamp"])
                if key in {"10k", "20k"}:
                    candidate[f"confirmed_crossed_{key}"] = True
                break


def _update_rejection_flags(candidate: dict[str, Any]) -> None:
    rows = candidate.get("path_rows") or []
    if not rows:
        return
    _detect_spike(candidate, rows)
    first_times = candidate.get("milestone_first_times") or {}
    major_keys = ["20k", "50k", "100k", "500k", "1m"]
    appeared = [(key, first_times.get(key)) for key in major_keys if first_times.get(key) is not None]
    if len(appeared) >= 2:
        times = [float(ts) for _, ts in appeared]
        if min(times) == max(times):
            candidate["same_timestamp_major_jump_flag"] = True
    if candidate.get("raw_milestones", {}).get("raw_crossed_50k") and not candidate.get("raw_milestones", {}).get("raw_crossed_10k"):
        candidate["same_timestamp_major_jump_flag"] = True


def _detect_spike(candidate: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        fdv = float(row.get("fdv_proxy") or 0.0)
        if fdv < ENTRY_THRESHOLD_FDV:
            continue
        nearby = []
        for neighbor_index in [index - 1, index + 1]:
            if 0 <= neighbor_index < len(rows):
                nearby.append(float(rows[neighbor_index].get("fdv_proxy") or 0.0))
        if not nearby:
            continue
        max_nearby = max(nearby)
        if max_nearby < ENTRY_THRESHOLD_FDV and max_nearby > 0 and fdv >= max_nearby * SPIKE_REJECTION_RATIO:
            candidate["single_row_spike_flag"] = True


def _update_state_from_milestones(candidate: dict[str, Any]) -> None:
    if candidate.get("paper_closed"):
        candidate["state"] = "paper_position_closed"
        candidate["tier"] = 4
    elif candidate.get("paper_buy_created"):
        candidate["state"] = "paper_position_open"
        candidate["tier"] = 4
    elif candidate.get("confirmed_milestones", {}).get("confirmed_crossed_20k"):
        candidate["state"] = "confirmed_20k_entry_candidate"
        candidate["tier"] = 3
        candidate["confirmed_crossed_20k"] = True
    elif candidate.get("confirmed_milestones", {}).get("confirmed_crossed_10k"):
        candidate["state"] = "confirmed_10k_watch"
        candidate["tier"] = 2
        candidate["confirmed_crossed_10k"] = True
    elif candidate.get("path_rows"):
        candidate["state"] = "fdv_path_seen"
        candidate["tier"] = 1
    else:
        candidate["state"] = "light_watch"
        candidate["tier"] = 0


def _evaluate_entry(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    reasons = []
    if not candidate.get("confirmed_milestones", {}).get("confirmed_crossed_10k"):
        reasons.append("missing_confirmed_10k")
    if not candidate.get("confirmed_milestones", {}).get("confirmed_crossed_20k"):
        reasons.append("missing_confirmed_20k")
    for flag, reason in [
        ("single_row_spike_flag", "single_row_spike"),
        ("same_timestamp_major_jump_flag", "same_timestamp_major_jump"),
        ("fdv_anomaly_flag", "fdv_anomaly"),
    ]:
        if candidate.get(flag):
            reasons.append(reason)
    if not config.allow_unfrozen_efficiency_baseline:
        reasons.append("fdv_efficiency_threshold_unfrozen")
    if candidate["mint"] in state.get("open_positions", {}) or candidate.get("paper_buy_created") or candidate.get("paper_closed"):
        reasons.append("duplicate_or_closed_position")
    features = _efficiency_features(row)
    decision = "paper_rejected_entry" if reasons else "paper_buy"
    return {
        "paper_event_id": f"decision_{candidate['mint']}_{int(float(row['timestamp']) * 1000)}",
        "mint": candidate["mint"],
        "timestamp": row["timestamp"],
        "decision": decision,
        "rule_id": FROZEN_BUY_RULE_ID,
        "buy_rule_version": "rule_runtime_v1",
        "paper_buy_fdv": row["fdv_proxy"],
        "confirmed_10k_time": candidate.get("confirmed_milestone_times", {}).get("10k"),
        "confirmed_20k_time": candidate.get("confirmed_milestone_times", {}).get("20k"),
        "rejection_flags": _rejection_flags(candidate),
        "rejection_reason": ",".join(reasons) if reasons else None,
        "efficiency_threshold_status": "efficiency_unfrozen",
        "data_source": row.get("data_source"),
        "no_real_trade": True,
        **features,
    }


def _create_paper_buy(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    wallet_before = float(state.get("wallet_usd") or config.starting_wallet_usd)
    allocation = _round_money(min(float(state.get("cash_usd") or 0.0), wallet_before * float(config.position_fraction)))
    if allocation <= 0:
        return
    fdv = float(row["fdv_proxy"])
    position = {
        "paper_event_id": f"paper_buy_{candidate['mint']}_{int(float(row['timestamp']) * 1000)}",
        "mint": candidate["mint"],
        "timestamp": row["timestamp"],
        "side": "paper_buy",
        "rule_id": FROZEN_BUY_RULE_ID,
        "buy_rule_version": "rule_runtime_v1",
        "paper_buy_fdv": fdv,
        "buy_fdv": fdv,
        "confirmed_10k_time": decision.get("confirmed_10k_time"),
        "confirmed_20k_time": decision.get("confirmed_20k_time"),
        "allocation_usd": allocation,
        "paper_units": allocation / fdv,
        "local_high_fdv": fdv,
        "drawdown_pct": 0.0,
        "rejection_flags": decision.get("rejection_flags") or {},
        "data_source": row.get("data_source"),
        "no_real_trade": True,
        **_efficiency_features(row),
    }
    state["cash_usd"] = _round_money(float(state["cash_usd"]) - allocation)
    state["wallet_usd"] = _round_money(float(state["cash_usd"]) + allocation)
    state["open_positions"][candidate["mint"]] = position
    candidate["paper_buy_created"] = True
    candidate["paper_opened_at"] = row["timestamp"]
    candidate["local_high_fdv"] = fdv
    candidate["state"] = "paper_position_open"
    candidate["tier"] = 4
    _append_jsonl(config.paper_trades_path, position)


def _evaluate_exit(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any] | None:
    position = state.get("open_positions", {}).get(candidate["mint"])
    if not position:
        return None
    fdv = float(row["fdv_proxy"])
    timestamp = float(row["timestamp"])
    local_high = max(float(candidate.get("local_high_fdv") or position.get("local_high_fdv") or 0.0), fdv)
    candidate["local_high_fdv"] = local_high
    position["local_high_fdv"] = local_high
    position["current_fdv"] = fdv
    drawdown_pct = 0.0 if local_high <= 0 else max(0.0, (local_high - fdv) / local_high)
    position["drawdown_pct"] = _round_pct(drawdown_pct)
    candidate["drawdowns"]["current_drawdown_pct"] = _round_pct(drawdown_pct)
    for threshold in [0.20, 0.30, 0.40, 0.50]:
        key = f"first_{int(threshold * 100)}pct_drawdown_time"
        if drawdown_pct >= threshold and key not in candidate["drawdowns"]:
            candidate["drawdowns"][key] = timestamp
            position[key] = timestamp
    if fdv >= local_high:
        candidate["drawdowns"]["reclaim_prior_high_time"] = timestamp
        position["reclaim_prior_high_time"] = timestamp
    drawdown_30_time = _num(candidate["drawdowns"].get("first_30pct_drawdown_time"))
    if drawdown_30_time is not None and timestamp - drawdown_30_time >= NO_RECLAIM_EXIT_SECONDS and fdv < local_high:
        return {
            "paper_event_id": f"paper_sell_{candidate['mint']}_{int(timestamp * 1000)}",
            "mint": candidate["mint"],
            "timestamp": timestamp,
            "decision": "paper_sell",
            "exit_rule_id": FROZEN_EXIT_RULE_ID,
            "exit_reason": "no_reclaim_after_10m_30pct_drawdown",
            "paper_sell_fdv": fdv,
            "local_high_fdv": local_high,
            "drawdown_pct": _round_pct(drawdown_pct),
            "time_since_entry_seconds": _round_seconds(timestamp - float(candidate.get("paper_opened_at") or timestamp)),
            "time_since_drawdown_seconds": _round_seconds(timestamp - drawdown_30_time),
            "reclaimed_prior_high": False,
            "no_real_trade": True,
        }
    return None


def _create_paper_sell(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    position = state["open_positions"].pop(candidate["mint"])
    sell_fdv = float(decision["paper_sell_fdv"])
    proceeds = _round_money(float(position["paper_units"]) * sell_fdv)
    allocation = float(position.get("allocation_usd") or 0.0)
    paper_pl = _round_money(proceeds - allocation)
    sell = {
        **position,
        "paper_event_id": decision["paper_event_id"],
        "timestamp": decision["timestamp"],
        "side": "paper_sell",
        "exit_rule_id": FROZEN_EXIT_RULE_ID,
        "exit_reason": decision["exit_reason"],
        "paper_sell_fdv": sell_fdv,
        "sell_fdv": sell_fdv,
        "local_high_fdv": decision["local_high_fdv"],
        "drawdown_pct": decision["drawdown_pct"],
        "time_since_entry_seconds": decision["time_since_entry_seconds"],
        "time_since_drawdown_seconds": decision["time_since_drawdown_seconds"],
        "reclaimed_prior_high": decision["reclaimed_prior_high"],
        "paper_profit_loss_usd": paper_pl,
        "no_real_trade": True,
    }
    state["cash_usd"] = _round_money(float(state["cash_usd"]) + proceeds)
    state["wallet_usd"] = _round_money(float(state["cash_usd"]))
    state["closed_positions"][candidate["mint"]] = sell
    candidate["paper_closed"] = True
    candidate["state"] = "paper_position_closed"
    candidate["tier"] = 4
    _append_jsonl(config.paper_trades_path, sell)


def _record_rejection(
    config: RuleRuntimeConfig,
    candidate: dict[str, Any],
    row: dict[str, Any],
    state_name: str,
    reason: str,
) -> None:
    decision = {
        "paper_event_id": f"reject_{candidate['mint']}_{int(float(row['timestamp']) * 1000)}_{reason}",
        "mint": candidate["mint"],
        "timestamp": row["timestamp"],
        "decision": "paper_rejected_entry",
        "state": state_name,
        "rule_id": FROZEN_BUY_RULE_ID,
        "paper_buy_fdv": row.get("fdv_proxy"),
        "rejection_reason": reason,
        "rejection_flags": _rejection_flags(candidate),
        "data_source": row.get("data_source"),
        "no_real_trade": True,
    }
    existing = _read_jsonl(config.paper_decisions_path)
    if not any(item.get("paper_event_id") == decision["paper_event_id"] for item in existing):
        _append_jsonl(config.paper_decisions_path, decision)


def _finish_event(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
    started: float,
    previous_state: Any,
) -> None:
    state["updated_at"] = _utc_now()
    state["candidates"][candidate["mint"]] = candidate
    state["queue_sizes"] = _queue_sizes_from_state(state)
    latency = _latency_row(candidate, row, started, previous_state)
    _append_jsonl(config.latency_events_path, latency)
    _write_json(config.runtime_state_path, state)


def _latency_row(candidate: dict[str, Any], row: dict[str, Any], started: float, previous_state: Any) -> dict[str, Any]:
    now = time.time()
    observed = float(row.get("event_observed_at") or row["timestamp"])
    confirmed_times = candidate.get("confirmed_milestone_times") or {}
    return {
        "event_observed_at": observed,
        "candidate_state_update_at": float(row["timestamp"]),
        "confirmed_10k_at": confirmed_times.get("10k"),
        "confirmed_20k_at": confirmed_times.get("20k"),
        "rule_eval_started_at": started,
        "rule_fired_at": float(row["timestamp"]) if candidate.get("paper_buy_created") else None,
        "paper_buy_event_written_at": float(row["timestamp"]) if candidate.get("paper_buy_created") else None,
        "detection_to_rule_latency_ms": _round_ms((now - observed) * 1000.0),
        "state_age_ms": _round_ms((float(row["timestamp"]) - float(candidate.get("first_seen_at") or row["timestamp"])) * 1000.0),
        "rule_eval_latency_ms": _round_ms((time.time() - started) * 1000.0),
        "source_event_type": row.get("source_event_type"),
        "data_source": row.get("data_source"),
        "path_row_count": len(candidate.get("path_rows") or []),
        "confirmation_row_count": sum(1 for item in candidate.get("path_rows") or [] if float(item.get("fdv_proxy") or 0.0) >= ENTRY_THRESHOLD_FDV),
        "previous_state": previous_state,
        "current_state": candidate.get("state"),
        "rejection_reason": _active_rejection_reason(candidate),
    }


def _queue_sizes_from_state(state: dict[str, Any]) -> dict[str, int]:
    sizes = RuleRuntimePriorityScheduler().queue_sizes()
    for row in (state.get("candidates") or {}).values():
        state_name = row.get("state")
        if state_name == "paper_position_open":
            sizes["paper_position_open"] += 1
        elif state_name == "confirmed_10k_watch":
            sizes["confirmed_10k_watch"] += 1
        elif state_name == "fdv_path_seen":
            sizes["first_fdv_path"] += 1
        elif state_name in {"birth_seen", "light_watch"}:
            sizes["light_watch"] += 1
    return sizes


def _write_monitor(config: RuleRuntimeConfig, state: dict[str, Any]) -> None:
    trades = _read_jsonl(config.paper_trades_path)
    decisions = _read_jsonl(config.paper_decisions_path)
    latency = _read_jsonl(config.latency_events_path)
    candidates = state.get("candidates") or {}
    rejected = [row for row in decisions if row.get("decision") == "paper_rejected_entry"]
    open_positions = list((state.get("open_positions") or {}).values())
    closed_positions = list((state.get("closed_positions") or {}).values())
    payload = {
        "updated_at": _utc_now(),
        "runtime_label": RUNTIME_LABEL,
        "wallet_usd": state.get("wallet_usd"),
        "cash_usd": state.get("cash_usd"),
        "paper_trading_enabled": True,
        "live_trading_enabled": False,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "rejected_entries": rejected,
        "candidate_count": len(candidates),
        "confirmed_10k_watches": sum(1 for row in candidates.values() if row.get("confirmed_crossed_10k")),
        "confirmed_20k_entry_candidates": sum(1 for row in candidates.values() if row.get("confirmed_crossed_20k")),
        "paper_buys": len([row for row in trades if row.get("side") == "paper_buy"]),
        "paper_sells": len([row for row in trades if row.get("side") == "paper_sell"]),
        "latency_p50_p90_p99": _percentiles([_num(row.get("detection_to_rule_latency_ms")) for row in latency]),
        "state_age_p50_p90_p99": _percentiles([_num(row.get("state_age_ms")) for row in latency]),
        "queue_sizes": state.get("queue_sizes") or {},
        "no_real_trade": True,
    }
    _write_json(config.monitor_json_path, payload)
    config.monitor_md_path.write_text(_monitor_md(payload), encoding="utf-8")
    config.monitor_html_path.write_text(_monitor_html(payload), encoding="utf-8")
    _write_csv(config.trades_csv_path, trades)


def _monitor_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Rule Runtime v1 Paper Monitor",
        "",
        f"Updated: {payload['updated_at']}",
        f"Wallet: ${payload['wallet_usd']}",
        f"Cash: ${payload['cash_usd']}",
        f"Open paper positions: {len(payload['open_positions'])}",
        f"Closed paper positions: {len(payload['closed_positions'])}",
        f"Rejected entries: {len(payload['rejected_entries'])}",
        "",
        "Paper-only accounting. Live trading is disabled.",
        "",
        "## Open Positions",
    ]
    for row in payload["open_positions"]:
        lines.append(
            f"- {row.get('mint')}: buy FDV ${row.get('paper_buy_fdv')}, current FDV ${row.get('current_fdv')}, local high ${row.get('local_high_fdv')}, drawdown {row.get('drawdown_pct')}"
        )
    lines.append("")
    lines.append("## Closed Positions")
    for row in payload["closed_positions"]:
        lines.append(
            f"- {row.get('mint')}: buy FDV ${row.get('paper_buy_fdv')}, sell FDV ${row.get('paper_sell_fdv')}, reason {row.get('exit_reason')}"
        )
    lines.append("")
    lines.append("## Rejected Entries")
    for row in payload["rejected_entries"]:
        lines.append(f"- {row.get('mint')}: {row.get('rejection_reason')}")
    return "\n".join(lines) + "\n"


def _monitor_html(payload: dict[str, Any]) -> str:
    rows = payload["open_positions"] + payload["closed_positions"] + payload["rejected_entries"]
    table = "\n".join(
        "<tr>"
        f"<td>{_ca_button(row.get('mint'))}</td>"
        f"<td>{html.escape(str(row.get('side') or row.get('decision') or 'open'))}</td>"
        f"<td>{html.escape(str(row.get('paper_buy_fdv') or row.get('buy_fdv') or ''))}</td>"
        f"<td>{html.escape(str(row.get('current_fdv') or ''))}</td>"
        f"<td>{html.escape(str(row.get('paper_sell_fdv') or row.get('sell_fdv') or ''))}</td>"
        f"<td>{html.escape(str(row.get('local_high_fdv') or ''))}</td>"
        f"<td>{html.escape(str(row.get('drawdown_pct') or ''))}</td>"
        f"<td>{html.escape(str(row.get('confirmed_10k_time') or ''))}</td>"
        f"<td>{html.escape(str(row.get('confirmed_20k_time') or ''))}</td>"
        f"<td>{html.escape(str(row.get('rejection_reason') or row.get('exit_reason') or row.get('rule_id') or ''))}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"10\">
<title>Rule Runtime v1 Paper Monitor</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f7f7f4;color:#1f2933}}
.stats{{display:flex;gap:12px;flex-wrap:wrap}} .stat{{background:white;border:1px solid #ddd;border-radius:8px;padding:12px 16px}}
table{{border-collapse:collapse;width:100%;background:white;margin-top:18px}} th,td{{border-bottom:1px solid #e5e7eb;padding:10px;text-align:left;vertical-align:top}}
button.ca{{border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:4px 8px;cursor:pointer;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
.guard{{color:#7a2e0e;margin-top:12px}}
</style><script>
function copyCA(value){{navigator.clipboard.writeText(value).then(function(){{document.getElementById('copy-status').textContent='Copied CA: '+value;}});}}
</script></head><body>
<h1>Rule Runtime v1 Paper Monitor</h1>
<div class=\"stats\"><div class=\"stat\">Wallet<br><b>${payload['wallet_usd']}</b></div><div class=\"stat\">Cash<br><b>${payload['cash_usd']}</b></div><div class=\"stat\">Open<br><b>{len(payload['open_positions'])}</b></div><div class=\"stat\">Closed<br><b>{len(payload['closed_positions'])}</b></div><div class=\"stat\">Rejected<br><b>{len(payload['rejected_entries'])}</b></div><div class=\"stat\">Paper buys<br><b>{payload['paper_buys']}</b></div><div class=\"stat\">Paper sells<br><b>{payload['paper_sells']}</b></div></div>
<p class=\"guard\">Paper-only monitor. Live trading, wallet execution, signing, swaps, and routing are disabled.</p>
<p id=\"copy-status\"><small>Click any CA to copy it.</small></p>
<h2>Latency</h2>
<p>Detection-to-rule p50/p90/p99: {html.escape(str(payload['latency_p50_p90_p99']))}</p>
<h2>Trades and Rejections</h2>
<table><thead><tr><th>CA</th><th>Status</th><th>Buy FDV</th><th>Current FDV</th><th>Sell FDV</th><th>Local High</th><th>Drawdown</th><th>10k Confirmed</th><th>20k Confirmed</th><th>Why</th></tr></thead><tbody>{table}</tbody></table>
<p><small>Updated {payload['updated_at']}. Auto-refreshes every 10 seconds.</small></p>
</body></html>"""


def _ca_button(mint: Any) -> str:
    if not mint:
        return ""
    value = str(mint)
    return (
        f"<button class=\"ca\" onclick=\"copyCA('{html.escape(value, quote=True)}')\" "
        f"title=\"Copy contract address\">{html.escape(value)}</button>"
    )


def _efficiency_features(row: dict[str, Any]) -> dict[str, Any]:
    fdv = float(row.get("fdv_proxy") or 0.0)
    event_count = int(row.get("event_count") or 0)
    buy_count = int(row.get("buy_count") or 0)
    active_wallet_count = int(row.get("active_wallet_count") or 0)
    return {
        "fdv_per_event_at_20k": _round_num(fdv / event_count) if event_count else None,
        "fdv_per_buy_at_20k": _round_num(fdv / buy_count) if buy_count else None,
        "fdv_per_active_wallet_at_20k": _round_num(fdv / active_wallet_count) if active_wallet_count else None,
        "event_count_at_20k": event_count,
        "buy_count_at_20k": buy_count,
        "active_wallet_count_at_20k": active_wallet_count,
    }


def _rejection_flags(candidate: dict[str, Any]) -> dict[str, bool]:
    return {
        "single_row_spike_flag": bool(candidate.get("single_row_spike_flag")),
        "same_timestamp_major_jump_flag": bool(candidate.get("same_timestamp_major_jump_flag")),
        "fdv_anomaly_flag": bool(candidate.get("fdv_anomaly_flag")),
    }


def _active_rejection_reason(candidate: dict[str, Any]) -> str | None:
    if candidate.get("fdv_anomaly_flag"):
        return "fdv_anomaly"
    if candidate.get("single_row_spike_flag"):
        return "single_row_fdv_spike"
    if candidate.get("same_timestamp_major_jump_flag"):
        return "same_timestamp_major_jump"
    return None


def _result(candidate: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    result.update(
        {
            "state": candidate.get("state"),
            "tier": candidate.get("tier"),
            "confirmed_crossed_10k": bool(candidate.get("confirmed_crossed_10k")),
            "confirmed_crossed_20k": bool(candidate.get("confirmed_crossed_20k")),
            "single_row_spike_flag": bool(candidate.get("single_row_spike_flag")),
            "same_timestamp_major_jump_flag": bool(candidate.get("same_timestamp_major_jump_flag")),
            "fdv_anomaly_flag": bool(candidate.get("fdv_anomaly_flag")),
        }
    )
    return result


def _level_key(level: int) -> str:
    if level >= 1_000_000:
        return "1m"
    return f"{int(level / 1000)}k"


def _percentiles(values: list[float | None]) -> dict[str, float | None]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return {"p50": None, "p90": None, "p99": None}
    return {"p50": _round_num(median(clean)), "p90": _round_num(_nearest_percentile(clean, 0.90)), "p99": _round_num(_nearest_percentile(clean, 0.99))}


def _nearest_percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return values[index]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp",
        "side",
        "mint",
        "allocation_usd",
        "paper_buy_fdv",
        "paper_sell_fdv",
        "local_high_fdv",
        "drawdown_pct",
        "paper_profit_loss_usd",
        "rule_id",
        "exit_rule_id",
        "exit_reason",
        "no_real_trade",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _load_state(config: RuleRuntimeConfig) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        return _initial_state(config)
    return json.loads(config.runtime_state_path.read_text(encoding="utf-8"))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _round_num(value: float) -> float:
    return round(float(value), 6)


def _round_pct(value: float) -> float:
    return round(float(value), 6)


def _round_ms(value: float) -> float:
    return round(float(value), 3)


def _round_seconds(value: float) -> float:
    return round(float(value), 3)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
