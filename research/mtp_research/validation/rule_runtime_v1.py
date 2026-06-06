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
from research.mtp_research.validation.bonding_curve_account_state import (
    BondingCurveAccountStateProbe,
    bonding_curve_resolution_audit,
    write_bonding_curve_first_fdv_probe_summary,
)
from research.mtp_research.validation.rule_runtime_event_bus import RuleRuntimeEventBus


RUNTIME_LABEL = "rule_runtime_v1"
FROZEN_BUY_RULE_ID = "RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER"
FROZEN_EXIT_RULE_ID = "EXIT_NO_RECLAIM_AFTER_30PCT_10M"
VARIANT_A_ID = "FDV_BASELINE_20K"
VARIANT_B_ID = "FDV_CREATOR_HOLDER_AVAILABLE_FILTER"
VARIANT_C_ID = "FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"
RULE_VARIANTS = [VARIANT_A_ID, VARIANT_B_ID, VARIANT_C_ID]
AVAILABLE_RISK_FIELDS = [
    "creator_prior_migration_count",
    "repeated_buyer_count",
    "holder_count_at_10k_proxy",
    "holder_growth_to_20k_proxy",
]
FULL_RISK_FIELDS = [
    "creator_prior_migration_count",
    "repeated_buyer_count",
    "early_buyer_with_prior_100k_count",
    "early_buyer_with_prior_500k_count",
    "early_buyer_with_prior_1m_count",
    "holder_count_at_10k_proxy",
    "holder_growth_to_20k_proxy",
    "social_link_count",
    "topicality_bucket",
]
OPTIONAL_LIVE_FIELDS = sorted(set(AVAILABLE_RISK_FIELDS + FULL_RISK_FIELDS + [
    "early_buyer_prior_failure_count",
    "telegram_url",
    "discord_url",
    "twitter_x_url",
    "website_url",
    "top_holder_share_proxy",
    "creator_funder",
]))
MILESTONES = [10_000, 15_000, 20_000, 50_000, 100_000, 500_000, 1_000_000]
ENTRY_THRESHOLD_FDV = 20_000.0
WATCH_THRESHOLD_FDV = 10_000.0
CONFIRMATION_WINDOW_SECONDS = 120.0
DRAW_DOWN_EXIT_PCT = 0.30
NO_RECLAIM_EXIT_SECONDS = 600.0
SPIKE_REJECTION_RATIO = 3.0
FDV_ANOMALY_HIGH = 100_000_000.0
NEAR_THRESHOLD_FDV = 5_000.0
FIRST_PATH_FAST_ATTEMPT_WINDOW_SECONDS = 15.0
LIGHT_WATCH_TIMEOUT_SECONDS = 60.0
NO_ACTIVITY_ARCHIVE_SECONDS = 120.0
NO_FDV_PATH_ARCHIVE_SECONDS = 120.0
STALE_RETRY_INTERVAL_SECONDS = 30.0
MAX_STALE_RETRIES = 2
TIER_1_MAX_AGE_SECONDS = 600.0
TIER_1_PRESSURE_THRESHOLD = 25
SCHEDULER_MODE = "priority_single_worker"
ARCHIVE_STATES = {
    "archived_no_activity",
    "archived_no_fdv_path_timeout",
    "archived_parser_failure",
    "archived_duplicate",
    "archived_provenance_failure",
}


@dataclass(frozen=True)
class RuleRuntimeConfig:
    data_root: Path | str | None = None
    starting_wallet_usd: float = 300.0
    position_fraction: float = 0.05
    confirmation_window_seconds: float = CONFIRMATION_WINDOW_SECONDS
    allow_unfrozen_efficiency_baseline: bool = True
    repo_root: Path | str | None = None

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
    def paper_rule_variant_decisions_path(self) -> Path:
        return self.runtime_root / "paper_rule_variant_decisions.jsonl"

    @property
    def paper_rule_variant_exits_path(self) -> Path:
        return self.runtime_root / "paper_rule_variant_exits.jsonl"

    @property
    def latency_events_path(self) -> Path:
        return self.runtime_root / "latency_events.jsonl"

    @property
    def pumpfun_create_stream_events_path(self) -> Path:
        return self.runtime_root / "pumpfun_create_stream_events.jsonl"

    @property
    def bonding_curve_account_probe_events_path(self) -> Path:
        return self.runtime_root / "bonding_curve_account_probe_events.jsonl"

    @property
    def pumpfun_transaction_subscribe_raw_path(self) -> Path:
        return self.raw_root / "pumpfun_transaction_subscribe_raw.jsonl"

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

    @property
    def live_adapter_cursor_path(self) -> Path:
        return self.runtime_root / "live_adapter_cursor.json"

    @property
    def smoke_summary_json_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_smoke_summary.json"

    @property
    def smoke_summary_md_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_smoke_summary.md"

    @property
    def live_bus_smoke_summary_json_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_live_bus_smoke_summary.json"

    @property
    def live_bus_smoke_summary_md_path(self) -> Path:
        return self.report_root / "rule_runtime_v1_live_bus_smoke_summary.md"

    @property
    def variant_smoke_summary_json_path(self) -> Path:
        return self.report_root / "rule_runtime_variant_smoke_summary.json"

    @property
    def variant_smoke_summary_md_path(self) -> Path:
        return self.report_root / "rule_runtime_variant_smoke_summary.md"

    @property
    def historical_rule_config_audit_json_path(self) -> Path:
        return self.report_root / "historical_rule_config_load_audit.json"

    @property
    def historical_rule_config_audit_md_path(self) -> Path:
        return self.report_root / "historical_rule_config_load_audit.md"

    @property
    def first_fdv_queue_triage_audit_json_path(self) -> Path:
        return self.report_root / "first_fdv_queue_triage_audit.json"

    @property
    def first_fdv_queue_triage_audit_md_path(self) -> Path:
        return self.report_root / "first_fdv_queue_triage_audit.md"

    @property
    def first_fdv_queue_triage_smoke_summary_json_path(self) -> Path:
        return self.report_root / "first_fdv_queue_triage_smoke_summary.json"

    @property
    def first_fdv_queue_triage_smoke_summary_md_path(self) -> Path:
        return self.report_root / "first_fdv_queue_triage_smoke_summary.md"

    @property
    def birth_coverage_audit_json_path(self) -> Path:
        return self.report_root / "birth_coverage_audit.json"

    @property
    def birth_coverage_audit_md_path(self) -> Path:
        return self.report_root / "birth_coverage_audit.md"

    @property
    def bonding_curve_resolution_audit_json_path(self) -> Path:
        return self.report_root / "bonding_curve_resolution_audit.json"

    @property
    def bonding_curve_resolution_audit_md_path(self) -> Path:
        return self.report_root / "bonding_curve_resolution_audit.md"

    @property
    def bonding_curve_first_fdv_probe_summary_json_path(self) -> Path:
        return self.report_root / "bonding_curve_first_fdv_probe_summary.json"

    @property
    def bonding_curve_first_fdv_probe_summary_md_path(self) -> Path:
        return self.report_root / "bonding_curve_first_fdv_probe_summary.md"

    @property
    def helius_transaction_subscribe_capability_audit_json_path(self) -> Path:
        return self.report_root / "helius_transaction_subscribe_capability_audit.json"

    @property
    def helius_transaction_subscribe_capability_audit_md_path(self) -> Path:
        return self.report_root / "helius_transaction_subscribe_capability_audit.md"

    @property
    def helius_transaction_subscribe_bonding_curve_probe_summary_json_path(self) -> Path:
        return self.report_root / "helius_transaction_subscribe_bonding_curve_probe_summary.json"

    @property
    def helius_transaction_subscribe_bonding_curve_probe_summary_md_path(self) -> Path:
        return self.report_root / "helius_transaction_subscribe_bonding_curve_probe_summary.md"

    @property
    def hot_path_gap_analysis_path(self) -> Path:
        return self.report_root / "hot_path_gap_analysis.md"

    @property
    def status_md_path(self) -> Path:
        if self.repo_root is not None:
            return Path(self.repo_root).expanduser() / "theses" / "RULE_RUNTIME_V1_STATUS.md"
        if self.data_root is None or self.root == data_lake_root():
            return Path.cwd() / "theses" / "RULE_RUNTIME_V1_STATUS.md"
        return self.root / "theses" / "RULE_RUNTIME_V1_STATUS.md"


@dataclass(frozen=True)
class RuleRuntimeLiveAdapterConfig:
    data_root: Path | str | None = None
    source_sample_label: str = "official_lifecycle_watch_v2"
    source_followup_paths_path: Path | str | None = None

    @property
    def root(self) -> Path:
        return Path(self.data_root or data_lake_root()).expanduser()

    @property
    def followup_paths_path(self) -> Path:
        if self.source_followup_paths_path is not None:
            return Path(self.source_followup_paths_path).expanduser()
        return self.root / "data" / "forward_observation" / self.source_sample_label / "followup_paths.jsonl"


class RuleRuntimeLiveAdapter:
    """Read-only adapter over collector follow-up path rows."""

    def __init__(self, config: RuleRuntimeLiveAdapterConfig) -> None:
        self.config = config
        self.runtime_config = RuleRuntimeConfig(data_root=config.data_root)

    def read_new_events(self, *, limit: int | None = None, update_cursor: bool = True) -> list[dict[str, Any]]:
        source_path = self.config.followup_paths_path
        rows = _read_jsonl(source_path)
        cursor = _read_json(self.runtime_config.live_adapter_cursor_path)
        consumed = int(cursor.get("rows_consumed") or 0)
        if consumed > len(rows):
            consumed = 0
        end = len(rows) if limit is None else min(len(rows), consumed + max(0, int(limit)))
        selected = rows[consumed:end]
        events: list[dict[str, Any]] = []
        for offset, row in enumerate(selected, start=consumed):
            normalized = normalize_live_path_row_for_rule_runtime(row, row_index=offset, source_sample_label=self.config.source_sample_label)
            if normalized is not None:
                events.append(normalized)
        if update_cursor:
            _write_json(
                self.runtime_config.live_adapter_cursor_path,
                {
                    "source_followup_paths_path": str(source_path),
                    "source_sample_label": self.config.source_sample_label,
                    "rows_consumed": end,
                    "valid_events_emitted": len(events),
                    "updated_at": _utc_now(),
                    "collector_files_read_only": True,
                },
            )
        return events


class RuleRuntimePriorityScheduler:
    priority_order = [
        "paper_position_open",
        "confirmed_10k_watch",
        "near_threshold_watch",
        "first_fdv_path",
        "fresh_birth_first_path",
        "light_watch",
        "metadata_background",
    ]

    def __init__(self) -> None:
        self._queues: dict[str, deque[dict[str, Any]]] = {name: deque() for name in self.priority_order}

    def add_job(self, job_type: str, payload: dict[str, Any]) -> None:
        if job_type not in self._queues:
            raise ValueError(f"unknown rule runtime job type: {job_type}")
        row = dict(payload)
        self._queues[job_type].append(row)
        if job_type == "first_fdv_path":
            self._queues[job_type] = deque(
                sorted(
                    self._queues[job_type],
                    key=lambda item: (
                        _num(item.get("first_seen_at") or item.get("queued_at") or item.get("timestamp")) or float("inf"),
                        str(item.get("mint") or ""),
                    ),
                )
            )

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

    def process_path_event(self, event: dict[str, Any], *, runtime_mode: str = "file_adapter") -> dict[str, Any]:
        started = time.time()
        runtime_receive_monotonic = time.monotonic()
        state = _load_state(self.config)
        normalized = _normalize_path_event(event)
        normalized["runtime_mode"] = runtime_mode
        normalized["runtime_receive_at"] = time.time()
        normalized["runtime_receive_monotonic_at"] = runtime_receive_monotonic
        mint = normalized["mint"]
        fdv = float(normalized["fdv_proxy"])
        timestamp = float(normalized["timestamp"])
        event_observed_at = float(normalized.get("event_observed_at") or timestamp)
        candidate = state["candidates"].setdefault(mint, _new_candidate(mint, first_seen_at=timestamp))
        previous_state = candidate.get("state")
        previous_tier = int(candidate.get("tier") or 0)
        candidate["first_seen_at"] = min(float(candidate.get("first_seen_at") or timestamp), timestamp)
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

        if fdv <= 0 or fdv >= FDV_ANOMALY_HIGH or normalized.get("fdv_anomaly_flag_from_source") is True:
            candidate["state"] = "rejected_fdv_anomaly"
            candidate["tier"] = -1
            candidate["fdv_anomaly_flag"] = True
            _record_rejection(self.config, candidate, normalized, "rejected_fdv_anomaly", "fdv_anomaly")
            _record_variant_rejections(self.config, candidate, normalized, "fdv_anomaly")
            _finish_event(self.config, state, candidate, normalized, started, previous_state, runtime_mode=runtime_mode)
            return _result(candidate, result)

        candidate["last_fdv_proxy"] = fdv
        candidate["last_path_time"] = timestamp
        candidate["last_activity_time"] = timestamp if _event_has_activity(normalized) else candidate.get("last_activity_time")
        candidate["max_fdv_proxy"] = max(float(candidate.get("max_fdv_proxy") or 0.0), fdv)
        candidate.setdefault("first_fdv_path_time", timestamp)
        if candidate.get("state") in (None, "birth_seen", "light_watch"):
            candidate["state"] = "fdv_path_seen"
            candidate["tier"] = 1

        _update_raw_milestones(candidate, normalized)
        _update_confirmed_milestones(candidate, self.config.confirmation_window_seconds)
        _apply_source_confirmations(candidate, normalized)
        if normalized.get("single_row_spike_flag_from_source") is True:
            candidate["single_row_spike_flag"] = True
        if normalized.get("same_timestamp_major_jump_flag_from_source") is True:
            candidate["same_timestamp_major_jump_flag"] = True
        _update_rejection_flags(candidate)
        _update_state_from_milestones(candidate)
        _record_promotions(state, candidate, previous_state, previous_tier)

        if candidate.get("same_timestamp_major_jump_flag"):
            candidate["state"] = "rejected_same_timestamp_jump"
            candidate["tier"] = -1
            _record_rejection(self.config, candidate, normalized, "rejected_same_timestamp_jump", "same_timestamp_major_jump")
            _record_variant_rejections(self.config, candidate, normalized, "same_timestamp_major_jump")
        elif candidate.get("single_row_spike_flag"):
            candidate["state"] = "rejected_spike"
            candidate["tier"] = -1
            _record_rejection(self.config, candidate, normalized, "rejected_spike", "single_row_fdv_spike")
            _record_variant_rejections(self.config, candidate, normalized, "single_row_spike")
        elif candidate.get("confirmed_crossed_20k") and not candidate.get("paper_buy_created") and not candidate.get("paper_closed"):
            decision = _evaluate_entry(self.config, state, candidate, normalized)
            _append_jsonl(self.config.paper_decisions_path, decision)
            variant_buys = _record_variant_decisions(self.config, state, candidate, normalized, decision)
            if decision["decision"] == "paper_buy":
                _create_paper_buy(self.config, state, candidate, normalized, decision)
                result["paper_buy_created"] = True
            result["variant_paper_buys_created"] = variant_buys
        elif fdv >= ENTRY_THRESHOLD_FDV and not candidate.get("confirmed_crossed_20k"):
            _record_rejection(
                self.config,
                candidate,
                normalized,
                candidate.get("state") or "fdv_path_seen",
                "insufficient_path_evidence_for_confirmed_20k",
            )

        if candidate.get("paper_buy_created") and not candidate.get("paper_closed"):
            sell = _evaluate_exit(self.config, state, candidate, normalized)
            if sell:
                _append_jsonl(self.config.paper_decisions_path, sell)
                _create_paper_sell(self.config, state, candidate, normalized, sell)
                result["paper_sell_created"] = True
        variant_sells = _evaluate_variant_exits(self.config, state, candidate, normalized)
        if variant_sells:
            result["variant_paper_sells_created"] = variant_sells

        _finish_event(self.config, state, candidate, normalized, started, previous_state, runtime_mode=runtime_mode)
        _write_monitor(self.config, state)
        return _result(candidate, result)

    def consume_event_bus(self, bus: RuleRuntimeEventBus, *, max_events: int | None = None) -> dict[str, Any]:
        processed = 0
        buys = 0
        sells = 0
        background_before = int(bus.metrics().get("background_skipped") or 0)
        for event in bus.drain(max_events=max_events):
            result = self.process_path_event(event, runtime_mode="live_bus")
            processed += 1
            buys += int(bool(result.get("paper_buy_created")))
            sells += int(bool(result.get("paper_sell_created")))
        background_after = int(bus.metrics().get("background_skipped") or 0)
        status = rule_runtime_status(self.config)
        return {
            "processed": processed,
            "paper_buys_created": buys,
            "paper_sells_created": sells,
            "background_skipped": background_after - background_before,
            "bus_metrics": bus.metrics(),
            **status,
        }


def initialize_rule_runtime(config: RuleRuntimeConfig, *, reset: bool = False) -> dict[str, Any]:
    config.runtime_root.mkdir(parents=True, exist_ok=True)
    config.raw_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)
    historical_config = load_historical_rule_config(config)
    manifest = _manifest(config)
    manifest["historical_rule_config_loaded"] = bool(historical_config.get("loaded"))
    manifest["historical_rule_config_source"] = historical_config.get("source_path")
    _write_json(config.runtime_manifest_json_path, manifest)
    config.runtime_manifest_md_path.write_text(_manifest_md(manifest), encoding="utf-8")
    if reset or not config.runtime_state_path.exists():
        _write_json(config.runtime_state_path, _initial_state(config))
        for path in [
            config.path_events_path,
            config.paper_trades_path,
            config.paper_decisions_path,
            config.paper_rule_variant_decisions_path,
            config.paper_rule_variant_exits_path,
            config.latency_events_path,
            config.pumpfun_create_stream_events_path,
            config.bonding_curve_account_probe_events_path,
            config.pumpfun_transaction_subscribe_raw_path,
        ]:
            path.write_text("", encoding="utf-8")
        if config.live_adapter_cursor_path.exists():
            config.live_adapter_cursor_path.unlink()
    else:
        for path in [
            config.path_events_path,
            config.paper_trades_path,
            config.paper_decisions_path,
            config.paper_rule_variant_decisions_path,
            config.paper_rule_variant_exits_path,
            config.latency_events_path,
            config.pumpfun_create_stream_events_path,
            config.bonding_curve_account_probe_events_path,
            config.pumpfun_transaction_subscribe_raw_path,
        ]:
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


def load_historical_rule_config(config: RuleRuntimeConfig) -> dict[str, Any]:
    source_root = config.root / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    repaired_config = source_root / "refined_historical_rule_paper_shadow_config_repaired.json"
    refined_config = source_root / "refined_historical_rule_paper_shadow_config.json"
    repaired_summary = (
        config.root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "historical_rule_refinement_repaired"
        / "historical_rule_refinement_repaired_summary.json"
    )
    repair_coverage_md = (
        config.root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "historical_rule_refinement_field_repair"
        / "repair_coverage_summary.md"
    )
    checked = [repaired_config, refined_config, repaired_summary, repair_coverage_md]
    payload: dict[str, Any] = {}
    source_path: Path | None = None
    for path in [repaired_config, refined_config]:
        if path.exists():
            payload = _read_json(path)
            source_path = path
            break
    repaired_context = _read_json(repaired_summary)
    if not payload and repaired_context:
        selected = repaired_context.get("selected_repaired_rule") or {}
        payload = {
            "selected_buy_rule_id": selected.get("buy_rule_id") or FROZEN_BUY_RULE_ID,
            "selected_exit_rule_id": selected.get("exit_rule_id") or FROZEN_EXIT_RULE_ID,
            "base_gate": "confirmed clean 10k watch -> confirmed clean 20k candidate",
            "positive_confirms": ["high_fdv_efficiency_bucket"],
            "risk_rejects": [
                "single-row spikes, same-timestamp major jumps, FDV anomalies, invalid milestone ordering",
            ],
            "required_live_fields": [
                "confirmed_crossed_10k",
                "confirmed_crossed_20k",
                "fdv_per_event_at_20k",
                "fdv_per_buy_at_20k",
                "fdv_per_active_wallet_at_20k",
            ],
            "confirmed_milestones_only": True,
            "raw_milestones_allowed": False,
        }
        source_path = repaired_summary
    required = ["selected_buy_rule_id", "selected_exit_rule_id", "base_gate"]
    missing = [key for key in required if not payload.get(key)]
    loaded = bool(payload) and not missing
    audit = {
        "report_id": "historical_rule_config_load_audit",
        "updated_at": _utc_now(),
        "loaded": loaded,
        "source_path": str(source_path) if source_path else None,
        "paths_checked": [str(path) for path in checked],
        "missing_config": not bool(payload),
        "missing_required_fields": missing,
        "selected_buy_rule_id": payload.get("selected_buy_rule_id") if loaded else None,
        "selected_exit_rule_id": payload.get("selected_exit_rule_id") if loaded else None,
        "base_gate": payload.get("base_gate"),
        "positive_confirms": payload.get("positive_confirms") or [],
        "risk_rejects": payload.get("risk_rejects") or [],
        "required_live_fields": payload.get("required_live_fields") or [],
        "confirmed_milestones_only": payload.get("confirmed_milestones_only") is True,
        "raw_milestones_allowed": payload.get("raw_milestones_allowed") is True,
        "invalidation_criteria": payload.get("invalidation_criteria") or [],
        "repaired_context": repaired_context,
        "repair_coverage_summary_path": str(repair_coverage_md) if repair_coverage_md.exists() else None,
        "paper_only": True,
        "live_trading_enabled": False,
    }
    _write_json(config.historical_rule_config_audit_json_path, audit)
    config.historical_rule_config_audit_md_path.write_text(_historical_rule_config_audit_md(audit), encoding="utf-8")
    return audit


def run_rule_runtime_once(config: RuleRuntimeConfig, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    engine = RuleRuntimeEngine(config)
    events = events or []
    buys = 0
    sells = 0
    for event in events:
        result = engine.process_path_event(event, runtime_mode="file_adapter")
        buys += int(bool(result.get("paper_buy_created")))
        sells += int(bool(result.get("paper_sell_created")))
    status = rule_runtime_status(config)
    return {"processed_events": len(events), "paper_buys_created": buys, "paper_sells_created": sells, **status}


def run_rule_runtime_live_adapter_once(
    config: RuleRuntimeConfig,
    *,
    adapter_config: RuleRuntimeLiveAdapterConfig | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    adapter = RuleRuntimeLiveAdapter(adapter_config or RuleRuntimeLiveAdapterConfig(data_root=config.root))
    events = adapter.read_new_events(limit=limit)
    result = run_rule_runtime_once(config, events=events)
    return {
        "events_processed": result["processed_events"],
        "paper_buys_created": result["paper_buys_created"],
        "paper_sells_created": result["paper_sells_created"],
        **rule_runtime_status(config),
    }


def run_rule_runtime_smoke(
    config: RuleRuntimeConfig,
    *,
    adapter_config: RuleRuntimeLiveAdapterConfig | None = None,
    max_events: int = 500,
    max_seconds: float = 60.0,
    target_confirmed_10k_watches: int = 1,
    target_confirmed_20k_candidates: int = 1,
) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    started = time.monotonic()
    events_processed = 0
    adapter_config = adapter_config or RuleRuntimeLiveAdapterConfig(data_root=config.root)
    while events_processed < max(0, int(max_events)):
        batch_limit = max(1, min(100, int(max_events) - events_processed))
        result = run_rule_runtime_live_adapter_once(config, adapter_config=adapter_config, limit=batch_limit)
        processed = int(result.get("events_processed") or 0)
        events_processed += processed
        status = rule_runtime_status(config)
        if (
            int(status["confirmed_10k_watches"]) >= int(target_confirmed_10k_watches)
            or int(status["confirmed_20k_entry_candidates"]) >= int(target_confirmed_20k_candidates)
        ):
            break
        if processed == 0:
            break
        if max_seconds <= 0 or time.monotonic() - started >= float(max_seconds):
            break
        time.sleep(0.25)
    status = rule_runtime_status(config)
    summary = _smoke_summary(config, status, events_processed=events_processed, adapter_config=adapter_config)
    _write_json(config.smoke_summary_json_path, summary)
    _write_json(config.variant_smoke_summary_json_path, summary)
    config.smoke_summary_md_path.write_text(_smoke_summary_md(summary), encoding="utf-8")
    config.variant_smoke_summary_md_path.write_text(_smoke_summary_md(summary), encoding="utf-8")
    config.status_md_path.parent.mkdir(parents=True, exist_ok=True)
    config.status_md_path.write_text(_status_md(summary), encoding="utf-8")
    return summary


def first_fdv_queue_triage_audit(config: RuleRuntimeConfig) -> dict[str, Any]:
    if not config.runtime_state_path.exists():
        initialize_rule_runtime(config)
    state = _load_state(config)
    status = rule_runtime_status(config)
    audit = {
        "report_id": "first_fdv_queue_triage_audit",
        "updated_at": _utc_now(),
        "scheduler_mode": SCHEDULER_MODE,
        "parallel_workers_added": False,
        "queue_entries_created_from": "candidate_state",
        "metadata_competes_with_hot_path": False,
        "metadata_hot_path_allowed": False,
        "active_paper_positions_priority": 1,
        "near_threshold_priority": 3,
        "first_fdv_path_priority": 4,
        "queue_processing_model": "single scheduler priority ordering over state-derived candidate queues",
        "aging_rules": {
            "first_path_fast_attempt_window_seconds": FIRST_PATH_FAST_ATTEMPT_WINDOW_SECONDS,
            "light_watch_timeout_seconds": LIGHT_WATCH_TIMEOUT_SECONDS,
            "no_activity_archive_seconds": NO_ACTIVITY_ARCHIVE_SECONDS,
            "no_fdv_path_archive_seconds": NO_FDV_PATH_ARCHIVE_SECONDS,
            "tier_1_max_age_seconds": TIER_1_MAX_AGE_SECONDS,
            "tier_1_pressure_threshold": TIER_1_PRESSURE_THRESHOLD,
            "stale_retry_interval_seconds": STALE_RETRY_INTERVAL_SECONDS,
            "max_stale_retries": MAX_STALE_RETRIES,
        },
        "priority_order": RuleRuntimePriorityScheduler.priority_order,
        "first_fdv_queue": status.get("first_fdv_queue") or {},
        "queue_sizes": status.get("queue_sizes") or {},
        "candidate_count": len(state.get("candidates") or {}),
        "confirmed_milestone_safety": {
            "confirmed_milestones_only": True,
            "raw_20k_only_rejected": True,
            "single_row_spikes_rejected": True,
            "same_timestamp_major_jumps_rejected": True,
            "fdv_anomalies_rejected": True,
            "missing_path_evidence_rejected": True,
        },
        "no_real_trade": True,
    }
    _write_json(config.first_fdv_queue_triage_audit_json_path, audit)
    config.first_fdv_queue_triage_audit_md_path.write_text(_first_fdv_queue_triage_audit_md(audit), encoding="utf-8")
    return audit


def birth_coverage_audit(config: RuleRuntimeConfig, *, source_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(source_root).expanduser() if source_root is not None else config.root / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    provisional = _read_jsonl(root / "provisional_births.jsonl")
    hydration = _read_jsonl(root / "hydration_results.jsonl")
    births = _read_jsonl(root / "births.jsonl")
    stale = _read_jsonl(root / "stale_births.jsonl")
    provisional_count = len(provisional)
    accepted_count = len(births)
    stale_count = len(stale)
    confirmed_create_parses = len(
        _unique_row_ids(
            row
            for row in hydration
            if str(row.get("hydration_status") or row.get("status") or "").lower()
            in {"confirmed", "official", "hydration_confirmed", "hydrated_create_confirmed", "official_accepted"}
        )
    )
    parser_failures = len(_unique_row_ids(row for row in [*hydration, *stale] if _row_has_token(row, ["parser_failure", "parse_failure", "parser"])))
    hydration_failures = len(
        _unique_row_ids(
            row
            for row in hydration
            if _row_has_token(row, ["hydration_failed", "hydration_failure", "failed"])
            and not _row_has_token(row, ["unrecognized_layout", "unrecognized"])
        )
    )
    unrecognized_layouts = len(_unique_row_ids(row for row in [*provisional, *hydration, *stale] if _row_has_token(row, ["unrecognized_layout", "unrecognized"])))
    audit = {
        "report_id": "birth_coverage_audit",
        "updated_at": _utc_now(),
        "source_root": str(root),
        "provisional_birth_logs": provisional_count,
        "confirmed_create_parses": confirmed_create_parses,
        "fresh_accepted_births": accepted_count,
        "stale_quarantined_births": stale_count,
        "parser_failures": parser_failures,
        "hydration_failures": hydration_failures,
        "duplicate_births": _duplicate_row_count(provisional) + _duplicate_row_count(births),
        "unrecognized_layouts": unrecognized_layouts,
        "accepted_birth_rate": _round_num(accepted_count / max(1, provisional_count)),
        "rejected_stale_rate": _round_num(stale_count / max(1, provisional_count)),
        "paper_only": True,
        "live_trading_enabled": False,
        "metadata_hot_path_allowed": False,
    }
    _write_json(config.birth_coverage_audit_json_path, audit)
    config.birth_coverage_audit_md_path.write_text(_birth_coverage_audit_md(audit), encoding="utf-8")
    return audit


def run_first_fdv_queue_triage_smoke(config: RuleRuntimeConfig, *, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    initialize_rule_runtime(config, reset=not config.runtime_state_path.exists())
    bus = RuleRuntimeEventBus()
    events = events or []
    for event in events:
        bus.emit(event)
    result = RuleRuntimeEngine(config).consume_event_bus(bus, max_events=len(events))
    status = rule_runtime_status(config)
    summary = {
        "report_id": "first_fdv_queue_triage_smoke_summary",
        "updated_at": _utc_now(),
        "runtime_mode": "mock_live_bus",
        "scheduler_mode": SCHEDULER_MODE,
        "parallel_workers_added": False,
        "events_processed": int(result.get("processed") or status.get("events_processed") or 0),
        "confirmed_10k_watches": int(status.get("confirmed_10k_watches") or 0),
        "confirmed_20k_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "paper_buys": int(status.get("paper_buys") or 0),
        "paper_sells": int(status.get("paper_sells") or 0),
        "variants": status.get("variants") or {},
        "latency_p50_p90_p99": status.get("latency_p50_p90_p99"),
        "event_to_rule_latency_p50_p90_p99": status.get("event_to_rule_p50_p90_p99"),
        "threshold_status": "baseline-label-mode" if "fdv_efficiency_threshold_unfrozen" in (status.get("warnings") or []) else "frozen",
        "first_fdv_queue": status.get("first_fdv_queue") or {},
        "warnings": status.get("warnings") or [],
        "monitor_path": str(config.monitor_html_path),
        "paper_only": True,
        "live_trading_enabled": False,
        "no_real_trade_flag": True,
    }
    _write_json(config.first_fdv_queue_triage_smoke_summary_json_path, summary)
    config.first_fdv_queue_triage_smoke_summary_md_path.write_text(_first_fdv_queue_triage_smoke_summary_md(summary), encoding="utf-8")
    config.status_md_path.parent.mkdir(parents=True, exist_ok=True)
    config.status_md_path.write_text(_status_md(summary), encoding="utf-8")
    return summary


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
    event_to_rule = [_num(row.get("event_to_rule_ms")) for row in latency]
    bus_to_runtime = [_num(row.get("bus_to_runtime_ms")) for row in latency]
    runtime_eval = [_num(row.get("runtime_eval_ms")) for row in latency]
    runtime_stats = state.get("runtime_stats") or {}
    variants = _variant_status(config, state)
    first_fdv_queue = _first_fdv_queue_summary(config, state, latency)
    first_fdv_probe_sources = _first_fdv_probe_source_summary(state, latency)
    helius_txsub_first_fdv = _helius_transaction_subscribe_first_fdv_status(config, first_fdv_probe_sources)
    warnings = list(state.get("warnings") or [])
    for warning in first_fdv_queue.get("warnings") or []:
        if warning not in warnings:
            warnings.append(warning)
    status = {
        "runtime_label": RUNTIME_LABEL,
        "runtime_mode": runtime_stats.get("last_runtime_mode") or "idle",
        "frozen_buy_rule": FROZEN_BUY_RULE_ID,
        "frozen_exit_rule": FROZEN_EXIT_RULE_ID,
        "live_trading_enabled": False,
        "paper_trading_enabled": True,
        "events_processed": int(runtime_stats.get("events_processed") or 0),
        "live_bus_events": int(runtime_stats.get("live_bus_events") or 0),
        "file_adapter_events": int(runtime_stats.get("file_adapter_events") or 0),
        "confirmed_10k_watches": sum(1 for row in candidates.values() if row.get("confirmed_crossed_10k")),
        "confirmed_20k_entry_candidates": sum(1 for row in candidates.values() if row.get("confirmed_crossed_20k")),
        "paper_buys": len(buys),
        "open_paper_positions": len(state.get("open_positions") or {}),
        "paper_sells": len(sells),
        "variants": variants,
        "first_fdv_queue": first_fdv_queue,
        "first_fdv_probe_sources": first_fdv_probe_sources,
        "helius_transaction_subscribe_first_fdv": helius_txsub_first_fdv,
        "confirmed_20k_variant_candidates": len({row.get("mint") for row in _read_jsonl(config.paper_rule_variant_decisions_path) if row.get("variant_id") == VARIANT_A_ID}),
        "rejected_spike_candidates": sum(1 for row in candidates.values() if row.get("state") == "rejected_spike"),
        "rejected_same_timestamp_jumps": sum(1 for row in candidates.values() if row.get("state") == "rejected_same_timestamp_jump"),
        "rejected_fdv_anomalies": sum(1 for row in candidates.values() if row.get("fdv_anomaly_flag")),
        "archived_no_activity": sum(1 for row in candidates.values() if row.get("state") == "archived_no_activity"),
        "latency_p50_p90_p99": _percentiles(detection),
        "event_to_rule_p50_p90_p99": _percentiles(event_to_rule),
        "bus_to_runtime_p50_p90_p99": _percentiles(bus_to_runtime),
        "runtime_eval_p50_p90_p99": _percentiles(runtime_eval),
        "state_age_p50_p90_p99": _percentiles(age),
        "queue_sizes": queue_sizes,
        "bus_queue_depth": int(runtime_stats.get("bus_queue_depth") or 0),
        "metadata_hot_path_blocked": True,
        "metadata_enrichment_in_first_fdv": False,
        "accountSubscribe_bonding_curve_status": first_fdv_probe_sources.get("accountSubscribe_bonding_curve_status"),
        "active_account_subscriptions": first_fdv_probe_sources.get("active_account_subscriptions"),
        "no_real_trade_flag": True,
        "wallet_usd": state.get("wallet_usd"),
        "cash_usd": state.get("cash_usd"),
        "monitor_html_path": str(config.monitor_html_path),
        "paper_trades_path": str(config.paper_trades_path),
        "paper_rule_variant_decisions_path": str(config.paper_rule_variant_decisions_path),
        "paper_rule_variant_exits_path": str(config.paper_rule_variant_exits_path),
        "latency_events_path": str(config.latency_events_path),
        "warnings": warnings,
    }
    _write_monitor(config, state)
    return status


def run_rule_runtime_mock_live_bus_smoke(config: RuleRuntimeConfig, events: list[dict[str, Any]]) -> dict[str, Any]:
    initialize_rule_runtime(config, reset=not config.runtime_state_path.exists())
    bus = RuleRuntimeEventBus()
    for event in events:
        bus.emit(event)
    result = RuleRuntimeEngine(config).consume_event_bus(bus, max_events=len(events))
    summary = _live_bus_smoke_summary(config, result, collector_result=None, bus_metrics=result.get("bus_metrics") or {})
    _write_live_bus_smoke_reports(config, summary)
    return summary


def run_rule_runtime_live_bus_collector_smoke(
    config: RuleRuntimeConfig,
    *,
    collector_data_root: Path | str,
    target_births: int = 5,
    target_crossed_20k: int = 1,
    max_runtime_seconds: float = 600.0,
    max_helius_credits: int = 10_000,
    signatures_per_mint: int = 7,
    transactions_per_mint: int = 7,
) -> dict[str, Any]:
    from research.mtp_research.validation.no_laserstream_lifecycle_collector import run_no_laserstream_lifecycle_smoke
    from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleV2Config
    from research.mtp_research.validation.forward_efficient_mover_observer import (
        resolve_forward_sol_usd_price,
        resolve_helius_api_key,
        resolve_helius_ws_url,
    )

    initialize_rule_runtime(config, reset=not config.runtime_state_path.exists())
    bus = RuleRuntimeEventBus(max_queue_size=10_000)
    engine = RuleRuntimeEngine(config)
    first_fdv_probe = BondingCurveAccountStateProbe(sol_usd=resolve_forward_sol_usd_price(config.root))
    collector_config = OfficialLifecycleV2Config(
        data_root=Path(collector_data_root).expanduser(),
        max_helius_credits_per_run=max_helius_credits,
        max_active_birth_followups=100,
        max_active_trigger_watches=100,
        metadata_hydration_hot_path=False,
        metadata_hydration_at_birth=False,
        metadata_hydration_after_first_fdv_path=False,
        metadata_hydration_after_milestones=False,
        metadata_backfill_after_maturity=False,
    )

    def on_hot_event(event: dict[str, Any]) -> None:
        if bus.emit(event, block=False):
            result = engine.consume_event_bus(bus, max_events=100)
            _update_runtime_bus_depth(config, int((result.get("bus_metrics") or {}).get("queue_depth") or 0))

    collector_result = run_no_laserstream_lifecycle_smoke(
        collector_config,
        target_births=target_births,
        target_crossed_20k=target_crossed_20k,
        max_runtime_seconds=max_runtime_seconds,
        max_runtime_minutes=max(1, int(max_runtime_seconds // 60) or 1),
        signatures_per_mint=signatures_per_mint,
        transactions_per_mint=transactions_per_mint,
        execute=True,
        enable_metadata_enrichment=False,
        new_birth_collection_minutes=max_runtime_seconds / 60.0,
        post_target_followup_minutes=2,
        rate_limit_backoff_seconds=10,
        hot_path_event_callback=on_hot_event,
        first_fdv_probe=first_fdv_probe,
    )
    final = engine.consume_event_bus(bus, max_events=10_000)
    status = rule_runtime_status(config)
    _record_bonding_curve_probe_stats(config, collector_result.get("bonding_curve_account_state_probe") or first_fdv_probe.metrics())
    status = rule_runtime_status(config)
    summary = _live_bus_smoke_summary(config, status, collector_result=collector_result, bus_metrics=final.get("bus_metrics") or bus.metrics())
    _write_live_bus_smoke_reports(config, summary)
    write_bonding_curve_first_fdv_probe_summary(config, status=status, collector_result=collector_result)
    write_hot_path_gap_analysis(config)
    return summary


def run_helius_transaction_subscribe_bonding_curve_probe_smoke(
    config: RuleRuntimeConfig,
    *,
    collector_data_root: Path | str,
    max_runtime_seconds: float = 600.0,
    target_births: int = 1000,
    target_crossed_20k: int = 999,
    max_helius_credits: int = 10_000,
    signatures_per_mint: int = 7,
    transactions_per_mint: int = 7,
) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    from research.mtp_research.validation.forward_efficient_mover_observer import (
        resolve_forward_sol_usd_price,
        resolve_helius_api_key,
        resolve_helius_ws_url,
    )
    from research.mtp_research.validation.helius_transaction_subscribe_source import (
        HeliusTransactionSubscribeCreateSource,
        helius_transaction_subscribe_capability_audit,
        run_bonding_curve_account_probe_for_create_event,
    )

    initialize_rule_runtime(config, reset=not config.runtime_state_path.exists())
    capability = helius_transaction_subscribe_capability_audit(config)
    recommended = capability.get("recommended_endpoint") if isinstance(capability.get("recommended_endpoint"), dict) else {}
    if not recommended.get("transactionSubscribe_supported"):
        fallback = run_rule_runtime_live_bus_collector_smoke(
            config,
            collector_data_root=collector_data_root,
            target_births=target_births,
            target_crossed_20k=target_crossed_20k,
            max_runtime_seconds=max_runtime_seconds,
            max_helius_credits=max_helius_credits,
            signatures_per_mint=signatures_per_mint,
            transactions_per_mint=transactions_per_mint,
        )
        status = rule_runtime_status(config)
        summary = _helius_transaction_subscribe_bonding_curve_probe_summary(
            config,
            status,
            capability_audit=capability,
            create_events_decoded=0,
            transaction_subscribe_used=False,
            fallback_summary=fallback,
        )
        _write_helius_transaction_subscribe_bonding_curve_probe_reports(config, summary)
        return summary

    bus = RuleRuntimeEventBus(max_queue_size=10_000)
    engine = RuleRuntimeEngine(config)
    runtime_lock = Lock()

    def on_hot_event(event: dict[str, Any]) -> None:
        with runtime_lock:
            if bus.emit(event, block=False):
                result = engine.consume_event_bus(bus, max_events=100)
                _update_runtime_bus_depth(config, int((result.get("bus_metrics") or {}).get("queue_depth") or 0))

    source = HeliusTransactionSubscribeCreateSource(
        config=config,
        websocket_url=_transaction_subscribe_runtime_ws_url(recommended, resolve_helius_api_key=resolve_helius_api_key, resolve_helius_ws_url=resolve_helius_ws_url),
        timeout_seconds=2.0,
    )
    sol_usd = resolve_forward_sol_usd_price(config.root)
    probe_futures = []
    probe_errors: list[dict[str, Any]] = []

    def run_probe(event: dict[str, Any]) -> dict[str, Any]:
        probe = BondingCurveAccountStateProbe(sol_usd=sol_usd)
        return run_bonding_curve_account_probe_for_create_event(config, event, probe=probe, event_callback=on_hot_event)

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="txsub-fdv-probe") as executor:
        def on_create_event(event: dict[str, Any]) -> None:
            event["probe_scheduled_during_stream"] = True
            probe_futures.append(executor.submit(run_probe, dict(event)))

        create_events = source.fetch_create_events(
            max_events=target_births,
            max_seconds=max_runtime_seconds,
            on_create_event=on_create_event,
        )
        for future in as_completed(probe_futures):
            try:
                future.result()
            except Exception as exc:
                probe_errors.append({"error": f"{type(exc).__name__}:{exc}"})
    with runtime_lock:
        final = engine.consume_event_bus(bus, max_events=10_000)
    status = rule_runtime_status(config)
    probe_stats = _bonding_curve_probe_stats_from_rows(config)
    if probe_errors:
        failures = probe_stats.setdefault("failures_by_reason", {})
        failures["probe_worker_exception"] = int(failures.get("probe_worker_exception") or 0) + len(probe_errors)
        probe_stats["failures"] = int(probe_stats.get("failures") or 0) + len(probe_errors)
    _record_bonding_curve_probe_stats(config, probe_stats)
    status = rule_runtime_status(config)
    summary = _helius_transaction_subscribe_bonding_curve_probe_summary(
        config,
        status,
        capability_audit=capability,
        create_events_decoded=len(create_events),
        transaction_subscribe_used=True,
        fallback_summary={},
        bus_metrics=final.get("bus_metrics") or bus.metrics(),
    )
    _write_helius_transaction_subscribe_bonding_curve_probe_reports(config, summary)
    write_hot_path_gap_analysis(config)
    return summary


def write_hot_path_gap_analysis(config: RuleRuntimeConfig) -> Path:
    config.hot_path_gap_analysis_path.parent.mkdir(parents=True, exist_ok=True)
    config.hot_path_gap_analysis_path.write_text(
        "\n".join(
            [
                "# Rule Runtime v1 Hot Path Gap Analysis",
                "",
                "Previous path:",
                "collector event -> enriched path row -> JSONL write -> file adapter read -> runtime event.",
                "",
                "Latency source:",
                "The runtime waited for collector file writes and a later adapter poll/read cycle before rule evaluation.",
                "",
                "New path:",
                "collector event -> enriched path state -> in-memory event bus -> runtime event -> paper decision -> JSONL/report writes.",
                "",
                "File adapter remains available for replay, backfill, repair, and debugging.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config.hot_path_gap_analysis_path


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


def archive_runtime_queue_candidates(
    config: RuleRuntimeConfig,
    *,
    now: float | None = None,
    first_path_fast_attempt_window_seconds: float = FIRST_PATH_FAST_ATTEMPT_WINDOW_SECONDS,
    light_watch_timeout_seconds: float = LIGHT_WATCH_TIMEOUT_SECONDS,
    no_activity_archive_seconds: float = NO_ACTIVITY_ARCHIVE_SECONDS,
    no_fdv_path_archive_seconds: float = NO_FDV_PATH_ARCHIVE_SECONDS,
    tier_1_max_age_seconds: float = TIER_1_MAX_AGE_SECONDS,
    tier_1_retry_interval_seconds: float = STALE_RETRY_INTERVAL_SECONDS,
    tier_1_retry_budget: int = MAX_STALE_RETRIES,
    tier_1_pressure_threshold: int = TIER_1_PRESSURE_THRESHOLD,
) -> dict[str, Any]:
    state = _load_state(config)
    now = float(now if now is not None else time.time())
    stats = _scheduler_stats(state)
    result = {
        "downgrade_count": 0,
        "archived_no_activity": 0,
        "archived_no_fdv_path_timeout": 0,
        "tier_1_retry_scheduled": 0,
        "tier_1_pressure_mode": False,
    }
    active_tier_1 = [
        candidate
        for candidate in (state.get("candidates") or {}).values()
        if candidate.get("state") == "fdv_path_seen" and int(candidate.get("tier") or 0) == 1
    ]
    if len(active_tier_1) >= int(tier_1_pressure_threshold):
        stats["tier_1_pressure_mode"] = True
        result["tier_1_pressure_mode"] = True
    candidates_oldest_first = sorted(
        (state.get("candidates") or {}).values(),
        key=lambda candidate: (
            _num(candidate.get("first_seen_at")) or now,
            str(candidate.get("mint") or ""),
        ),
    )
    for candidate in candidates_oldest_first:
        state_name = candidate.get("state")
        if state_name in ARCHIVE_STATES or state_name in {"paper_position_open", "paper_position_closed", "confirmed_10k_watch", "confirmed_20k_entry_candidate"}:
            continue
        first_seen = _num(candidate.get("first_seen_at")) or now
        last_path = _num(candidate.get("last_path_time"))
        last_activity = _num(candidate.get("last_activity_time"))
        if not candidate.get("path_rows") and now - first_seen >= no_fdv_path_archive_seconds:
            candidate["state"] = "archived_no_fdv_path_timeout"
            candidate["tier"] = -1
            candidate["archive_reason"] = "no_fdv_path_timeout"
            stats["archived_no_fdv_path_timeout"] = int(stats.get("archived_no_fdv_path_timeout") or 0) + 1
            result["archived_no_fdv_path_timeout"] += 1
            continue
        if state_name == "fdv_path_seen" and candidate.get("path_rows"):
            tier_1_age = now - first_seen
            retry_count = int(candidate.get("tier_1_retry_count") or 0)
            last_retry = _num(candidate.get("tier_1_last_retry_at")) or first_seen
            retry_due = tier_1_age >= first_path_fast_attempt_window_seconds and now - last_retry >= tier_1_retry_interval_seconds
            if retry_due and retry_count < int(tier_1_retry_budget):
                retry_count += 1
                candidate["tier_1_retry_count"] = retry_count
                candidate["tier_1_last_retry_at"] = now
                stats["tier_1_retry_count"] = int(stats.get("tier_1_retry_count") or 0) + 1
                result["tier_1_retry_scheduled"] += 1
            if tier_1_age >= float(tier_1_max_age_seconds) or retry_count >= int(tier_1_retry_budget):
                candidate["state"] = "archived_no_activity"
                candidate["tier"] = -1
                candidate["archive_reason"] = "tier_1_retry_budget_exhausted" if retry_count >= int(tier_1_retry_budget) else "tier_1_max_age"
                stats["archived_no_activity"] = int(stats.get("archived_no_activity") or 0) + 1
                stats["tier_1_archive_count"] = int(stats.get("tier_1_archive_count") or 0) + 1
                result["archived_no_activity"] += 1
                continue
        if state_name == "fdv_path_seen" and now - first_seen >= first_path_fast_attempt_window_seconds and last_activity is None:
            candidate["state"] = "light_watch"
            candidate["tier"] = 0
            candidate["downgraded_at"] = now
            candidate["downgrade_reason"] = "no_activity_after_fast_attempt_window"
            candidate["downgraded_from_tier_1"] = True
            stats["downgrade_count"] = int(stats.get("downgrade_count") or 0) + 1
            result["downgrade_count"] += 1
            state_name = "light_watch"
        inactive_since = last_activity or last_path or first_seen
        if state_name in {"light_watch", "fdv_path_seen", "near_threshold_watch", "birth_seen"} and now - inactive_since >= no_activity_archive_seconds:
            candidate["state"] = "archived_no_activity"
            candidate["tier"] = -1
            candidate["archive_reason"] = "no_activity"
            stats["archived_no_activity"] = int(stats.get("archived_no_activity") or 0) + 1
            if state_name == "fdv_path_seen" or candidate.get("downgraded_from_tier_1"):
                stats["tier_1_archive_count"] = int(stats.get("tier_1_archive_count") or 0) + 1
            result["archived_no_activity"] += 1
    state["queue_sizes"] = _queue_sizes_from_state(state)
    state["updated_at"] = _utc_now()
    _write_json(config.runtime_state_path, state)
    _write_monitor(config, state)
    return result


def normalize_live_path_row_for_rule_runtime(
    row: dict[str, Any],
    *,
    row_index: int | None = None,
    source_sample_label: str | None = None,
) -> dict[str, Any] | None:
    mint = str(row.get("mint") or row.get("ca") or "").strip()
    timestamp = _num(row.get("timestamp") or row.get("observed_at") or row.get("block_time"))
    fdv = _num(row.get("fdv_proxy") if row.get("fdv_proxy") is not None else row.get("current_fdv"))
    if not mint or timestamp is None or fdv is None:
        return None
    source_label = str(source_sample_label or row.get("sample_label") or "official_lifecycle_watch_v2")
    provenance = str(row.get("milestone_provenance") or row.get("source_provenance") or row.get("source") or source_label)
    raw_10k = _bool_or_fdv(row.get("raw_crossed_10k", row.get("crossed_10k")), fdv, 10_000)
    raw_20k = _bool_or_fdv(row.get("raw_crossed_20k", row.get("crossed_20k")), fdv, 20_000)
    normalized = {
        "mint": mint,
        "timestamp": float(timestamp),
        "source_event_type": str(row.get("source_event_type") or "collector_followup_path"),
        "event_observed_at": float(_num(row.get("event_observed_at") or row.get("observed_at")) or timestamp),
        "fdv_proxy": float(fdv),
        "event_count": int(_num(row.get("event_count")) or 0),
        "buy_count": int(_num(row.get("buy_count")) or 0),
        "sell_count": int(_num(row.get("sell_count")) or 0),
        "active_wallet_count": int(_num(row.get("active_wallet_count") or row.get("active_wallets")) or 0),
        "path_evidence_count": int(_num(row.get("path_evidence_count")) or ((int(row_index) + 1) if row_index is not None else 1)),
        "raw_crossed_10k": bool(raw_10k),
        "raw_crossed_20k": bool(raw_20k),
        "confirmed_crossed_10k": _bool_or_none(row.get("confirmed_crossed_10k")),
        "confirmed_crossed_20k": _bool_or_none(row.get("confirmed_crossed_20k")),
        "single_row_spike_flag": bool(row.get("single_row_spike_flag") is True),
        "same_timestamp_major_jump_flag": bool(row.get("same_timestamp_major_jump_flag") is True),
        "fdv_anomaly_flag": bool(row.get("fdv_anomaly_flag") is True),
        "milestone_provenance": provenance,
        "data_source": source_label,
    }
    _copy_first_fdv_probe_fields(row, normalized)
    _copy_optional_live_fields(row, normalized)
    return normalized


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


def _historical_rule_config_audit_md(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Historical Rule Config Load Audit",
            "",
            f"- Updated: `{audit['updated_at']}`",
            f"- Loaded: `{audit['loaded']}`",
            f"- Source path: `{audit.get('source_path')}`",
            f"- Selected buy rule: `{audit.get('selected_buy_rule_id')}`",
            f"- Selected exit rule: `{audit.get('selected_exit_rule_id')}`",
            f"- Base gate: `{audit.get('base_gate')}`",
            f"- Confirmed milestones only: `{audit.get('confirmed_milestones_only')}`",
            f"- Raw milestones allowed: `{audit.get('raw_milestones_allowed')}`",
            f"- Missing config: `{audit.get('missing_config')}`",
            f"- Missing required fields: `{audit.get('missing_required_fields')}`",
            "",
            "Paper-only runtime configuration audit. Live trading, private keys, transaction building, swaps, and routing remain disabled.",
        ]
    ) + "\n"


def _first_fdv_queue_triage_audit_md(audit: dict[str, Any]) -> str:
    queue = audit.get("first_fdv_queue") or {}
    return "\n".join(
        [
            "# First FDV Queue Triage Audit",
            "",
            f"- Updated: `{audit['updated_at']}`",
            f"- Scheduler mode: `{audit['scheduler_mode']}`",
            f"- Parallel workers added: `{audit['parallel_workers_added']}`",
            f"- Queue entries created from: `{audit['queue_entries_created_from']}`",
            f"- Metadata competes with hot path: `{audit['metadata_competes_with_hot_path']}`",
            f"- Priority order: `{audit['priority_order']}`",
            f"- Queue sizes: `{audit.get('queue_sizes')}`",
            f"- Queue depth by tier: `{queue.get('queue_depth_by_tier')}`",
            f"- Tier 1 depth: `{queue.get('tier_1_depth')}`",
            f"- Tier 1 oldest age: `{queue.get('tier_1_oldest_age_seconds')}`",
            f"- Tier 1 p50/p90 age: `{queue.get('tier_1_age_p50_p90')}`",
            f"- Tier 1 processed/archive/promotion/retry: `{queue.get('tier_1_processed_count')}` / `{queue.get('tier_1_archive_count')}` / `{queue.get('tier_1_promotion_count')}` / `{queue.get('tier_1_retry_count')}`",
            f"- Archive counts: no_activity `{queue.get('archived_no_activity')}`, no_fdv_path `{queue.get('archived_no_fdv_path_timeout')}`",
            f"- Promotion counts: fdv_path `{queue.get('promoted_to_fdv_path')}`, near_threshold `{queue.get('promoted_to_near_threshold')}`, confirmed_10k `{queue.get('promoted_to_confirmed_10k')}`, paper_position `{queue.get('promoted_to_paper_position')}`",
            f"- First path success rate: `{queue.get('first_path_success_rate')}`",
            f"- First-FDV success/timeout/median latency: `{queue.get('first_fdv_success_rate')}` / `{queue.get('first_fdv_timeout_rate')}` / `{queue.get('first_fdv_median_latency_ms')}`",
            f"- First path latency p50/p90/p99: `{queue.get('first_path_latency_p50_p90_p99')}`",
            "",
            "Paper-only runtime triage audit. No private keys, swaps, routing, or live execution.",
        ]
    ) + "\n"


def _first_fdv_queue_triage_smoke_summary_md(summary: dict[str, Any]) -> str:
    queue = summary.get("first_fdv_queue") or {}
    return "\n".join(
        [
            "# First FDV Queue Triage Smoke Summary",
            "",
            f"- Updated: `{summary['updated_at']}`",
            f"- Runtime mode: `{summary['runtime_mode']}`",
            f"- Scheduler mode: `{summary['scheduler_mode']}`",
            f"- Parallel workers added: `{summary['parallel_workers_added']}`",
            f"- Events processed: `{summary['events_processed']}`",
            f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
            f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys/sells: `{summary['paper_buys']}` / `{summary['paper_sells']}`",
            f"- Queue depth by tier: `{queue.get('queue_depth_by_tier')}`",
            f"- Tier 1 depth: `{queue.get('tier_1_depth')}`",
            f"- Tier 1 oldest age: `{queue.get('tier_1_oldest_age_seconds')}`",
            f"- Tier 1 p50/p90 age: `{queue.get('tier_1_age_p50_p90')}`",
            f"- Tier 1 processed/archive/promotion/retry: `{queue.get('tier_1_processed_count')}` / `{queue.get('tier_1_archive_count')}` / `{queue.get('tier_1_promotion_count')}` / `{queue.get('tier_1_retry_count')}`",
            f"- Archived no activity: `{queue.get('archived_no_activity')}`",
            f"- Archived no FDV path timeout: `{queue.get('archived_no_fdv_path_timeout')}`",
            f"- Promotions: fdv_path `{queue.get('promoted_to_fdv_path')}`, near_threshold `{queue.get('promoted_to_near_threshold')}`, confirmed_10k `{queue.get('promoted_to_confirmed_10k')}`, paper_position `{queue.get('promoted_to_paper_position')}`",
            f"- Latency p50/p90/p99: `{summary.get('latency_p50_p90_p99')}`",
            f"- First-FDV success/timeout/median latency: `{queue.get('first_fdv_success_rate')}` / `{queue.get('first_fdv_timeout_rate')}` / `{queue.get('first_fdv_median_latency_ms')}`",
            f"- First path latency p50/p90/p99: `{queue.get('first_path_latency_p50_p90_p99')}`",
            f"- Monitor path: `{summary.get('monitor_path')}`",
            "",
            "Paper-only. Live trading, private keys, transaction building, swaps, and routing remain disabled.",
        ]
    ) + "\n"


def _birth_coverage_audit_md(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Birth Coverage Audit",
            "",
            f"- Updated: `{audit['updated_at']}`",
            f"- Source root: `{audit['source_root']}`",
            f"- Provisional birth logs: `{audit['provisional_birth_logs']}`",
            f"- Confirmed create parses: `{audit['confirmed_create_parses']}`",
            f"- Fresh accepted births: `{audit['fresh_accepted_births']}`",
            f"- Stale/quarantined births: `{audit['stale_quarantined_births']}`",
            f"- Parser failures: `{audit['parser_failures']}`",
            f"- Hydration failures: `{audit['hydration_failures']}`",
            f"- Duplicate births: `{audit['duplicate_births']}`",
            f"- Unrecognized layouts: `{audit['unrecognized_layouts']}`",
            f"- Accepted birth rate: `{audit['accepted_birth_rate']}`",
            f"- Rejected/stale rate: `{audit['rejected_stale_rate']}`",
            "",
            "Paper-only coverage audit. Metadata and enrichment stay outside the first-FDV hot path.",
        ]
    ) + "\n"


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
        "variant_open_positions": {},
        "variant_closed_positions": {},
        "rejected_candidates": {},
        "queue_sizes": RuleRuntimePriorityScheduler().queue_sizes(),
        "runtime_stats": {
            "last_runtime_mode": "idle",
            "events_processed": 0,
            "live_bus_events": 0,
            "file_adapter_events": 0,
            "bus_queue_depth": 0,
        },
        "scheduler_stats": _default_scheduler_stats(),
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


def _new_candidate(mint: str, *, first_seen_at: float | None = None) -> dict[str, Any]:
    now = float(first_seen_at if first_seen_at is not None else time.time())
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


def _default_scheduler_stats() -> dict[str, Any]:
    return {
        "scheduler_mode": SCHEDULER_MODE,
        "parallel_workers_added": False,
        "downgrade_count": 0,
        "reactivation_count": 0,
        "archived_no_activity": 0,
        "archived_no_fdv_path_timeout": 0,
        "archived_parser_failure": 0,
        "archived_duplicate": 0,
        "archived_provenance_failure": 0,
        "promoted_to_fdv_path": 0,
        "promoted_to_near_threshold": 0,
        "promoted_to_confirmed_10k": 0,
        "promoted_to_paper_position": 0,
        "tier_1_processed_count": 0,
        "tier_1_archive_count": 0,
        "tier_1_promotion_count": 0,
        "tier_1_retry_count": 0,
        "tier_1_pressure_mode": False,
        "http_429_count": 0,
        "helius_rpc_request_count": None,
        "bonding_curve_account_state_failures": 0,
        "bonding_curve_account_state_failure_reasons": {},
        "account_subscribe_bonding_curve_status": "accountSubscribe_bonding_curve_not_implemented",
        "active_account_subscriptions": 0,
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
    normalized = {
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
        "observed_at": float(_num(event.get("observed_at")) or timestamp),
        "monotonic_observed_at": _num(event.get("monotonic_observed_at")),
        "bus_emit_at": event.get("bus_emit_at"),
        "bus_emit_monotonic_at": _num(event.get("bus_emit_monotonic_at")),
        "path_evidence_count": int(_num(event.get("path_evidence_count")) or 1),
        "raw_crossed_10k": _bool_or_none(event.get("raw_crossed_10k")),
        "raw_crossed_20k": _bool_or_none(event.get("raw_crossed_20k")),
        "confirmed_crossed_10k_from_source": _bool_or_none(event.get("confirmed_crossed_10k")),
        "confirmed_crossed_20k_from_source": _bool_or_none(event.get("confirmed_crossed_20k")),
        "single_row_spike_flag_from_source": bool(event.get("single_row_spike_flag") is True),
        "same_timestamp_major_jump_flag_from_source": bool(event.get("same_timestamp_major_jump_flag") is True),
        "fdv_anomaly_flag_from_source": bool(event.get("fdv_anomaly_flag") is True),
        "milestone_provenance": event.get("milestone_provenance"),
        "recorded_at": _utc_now(),
    }
    _copy_first_fdv_probe_fields(event, normalized)
    _copy_optional_live_fields(event, normalized)
    return normalized


def _copy_first_fdv_probe_fields(source: dict[str, Any], target: dict[str, Any]) -> None:
    for key in [
        "fdv_source",
        "fdv_source_confidence",
        "fdv_probe_method",
        "bonding_curve",
        "observed_to_bonding_curve_resolved_ms",
        "bonding_curve_resolved_to_getAccountInfo_ms",
        "getAccountInfo_latency_ms",
        "decode_latency_ms",
        "observed_to_first_fdv_account_state_ms",
        "first_fdv_source",
        "create_observed_at",
        "probe_started_at",
        "first_curve_state_at",
        "first_fdv_emitted_at",
        "observed_to_probe_started_ms",
        "probe_started_to_first_curve_state_ms",
        "observed_to_first_fdv_emitted_ms",
        "probe_attempt_count",
        "account_not_found_retry_count",
        "account_not_found_recovered_by_retry",
        "first_failure_reason",
        "retry_delays_ms",
    ]:
        if key in source:
            target[key] = source.get(key)
    if target.get("first_fdv_source") is None and target.get("fdv_source"):
        target["first_fdv_source"] = target.get("fdv_source")


def _copy_optional_live_fields(source: dict[str, Any], target: dict[str, Any]) -> None:
    for key in OPTIONAL_LIVE_FIELDS:
        if key in source:
            target[key] = source.get(key)
    if "holder_count_at_10k" in source and "holder_count_at_10k_proxy" not in target:
        target["holder_count_at_10k_proxy"] = source.get("holder_count_at_10k")
    if "holder_growth_to_20k" in source and "holder_growth_to_20k_proxy" not in target:
        target["holder_growth_to_20k_proxy"] = source.get("holder_growth_to_20k")
    if "social_link_count" not in target and any(
        key in source for key in ["telegram_url", "discord_url", "twitter_x_url", "website_url"]
    ):
        target["social_link_count"] = sum(
            1
            for key in ["telegram_url", "discord_url", "twitter_x_url", "website_url"]
            if source.get(key)
        )


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


def _apply_source_confirmations(candidate: dict[str, Any], row: dict[str, Any]) -> None:
    if not _source_allows_confirmed_milestone_flags(row):
        return
    timestamp = float(row["timestamp"])
    if row.get("confirmed_crossed_10k_from_source") is True:
        candidate["confirmed_milestones"]["confirmed_crossed_10k"] = True
        candidate["confirmed_milestone_times"].setdefault("10k", timestamp)
        candidate["confirmed_crossed_10k"] = True
    if row.get("confirmed_crossed_20k_from_source") is True:
        candidate["confirmed_milestones"]["confirmed_crossed_20k"] = True
        candidate["confirmed_milestone_times"].setdefault("20k", timestamp)
        candidate["confirmed_crossed_20k"] = True


def _source_allows_confirmed_milestone_flags(row: dict[str, Any]) -> bool:
    source = str(row.get("fdv_source") or "").lower()
    confidence = str(row.get("fdv_source_confidence") or "").lower()
    if source == "transaction_delta":
        return False
    if confidence in {"low", "none"}:
        return False
    return True


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
        candidate["tier"] = 3
        candidate["confirmed_crossed_10k"] = True
    elif float(candidate.get("max_fdv_proxy") or 0.0) >= NEAR_THRESHOLD_FDV:
        candidate["state"] = "near_threshold_watch"
        candidate["tier"] = 2
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
        "ca": candidate["mint"],
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
        "threshold_status": "baseline_label_mode" if not reasons else "rejected",
        "efficiency_threshold_warning": "fdv_efficiency_threshold_unfrozen_baseline_mode" if not reasons else None,
        "fdv_efficiency_bucket_labels": _efficiency_bucket_labels(features),
        "data_source": row.get("data_source"),
        "milestone_provenance": row.get("milestone_provenance"),
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
        "ca": candidate["mint"],
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
        "milestone_provenance": row.get("milestone_provenance"),
        "threshold_status": "baseline_label_mode",
        "efficiency_threshold_warning": "fdv_efficiency_threshold_unfrozen_baseline_mode",
        "fdv_efficiency_bucket_labels": _efficiency_bucket_labels(_efficiency_features(row)),
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


def _record_variant_decisions(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
    base_decision: dict[str, Any],
) -> int:
    created = 0
    candidate.setdefault("variant_decisions_created", [])
    for variant_id in RULE_VARIANTS:
        if variant_id in candidate["variant_decisions_created"]:
            continue
        decision = _variant_decision_row(config, candidate, row, base_decision, variant_id)
        _append_jsonl(config.paper_rule_variant_decisions_path, decision)
        candidate["variant_decisions_created"].append(variant_id)
        if decision["variant_status"] == "paper_buy":
            _create_variant_position(config, state, candidate, row, decision)
            created += 1
    return created


def _record_variant_rejections(
    config: RuleRuntimeConfig,
    candidate: dict[str, Any],
    row: dict[str, Any],
    reason: str,
) -> None:
    existing = {
        item.get("decision_id")
        for item in _read_jsonl(config.paper_rule_variant_decisions_path)
    }
    for variant_id in RULE_VARIANTS:
        decision_id = f"variant_decision_{variant_id}_{candidate['mint']}_{int(float(row['timestamp']) * 1000)}"
        if decision_id in existing:
            continue
        features = _efficiency_features(row)
        decision = {
            "decision_id": decision_id,
            "mint": candidate["mint"],
            "ca": candidate["mint"],
            "timestamp": row["timestamp"],
            "base_rule_id": FROZEN_BUY_RULE_ID,
            "exit_rule_id": FROZEN_EXIT_RULE_ID,
            "variant_id": variant_id,
            "variant_status": "rejected",
            "paper_buy_allowed": False,
            "paper_buy_emitted": False,
            "confirmed_10k_time": candidate.get("confirmed_milestone_times", {}).get("10k"),
            "confirmed_20k_time": candidate.get("confirmed_milestone_times", {}).get("20k"),
            "paper_buy_fdv": row.get("fdv_proxy"),
            "fdv_efficiency_bucket": _overall_efficiency_bucket(features),
            "fdv_efficiency_threshold_status": "fdv_threshold_unfrozen",
            "risk_filter_status": "rejected",
            "missing_required_fields": [],
            "rejection_reason": reason,
            "no_real_trade": True,
            **features,
            **_risk_field_values(row),
        }
        _append_jsonl(config.paper_rule_variant_decisions_path, decision)


def _variant_decision_row(
    config: RuleRuntimeConfig,
    candidate: dict[str, Any],
    row: dict[str, Any],
    base_decision: dict[str, Any],
    variant_id: str,
) -> dict[str, Any]:
    features = _efficiency_features(row)
    base_reasons = [
        item
        for item in str(base_decision.get("rejection_reason") or "").split(",")
        if item
    ]
    missing: list[str] = []
    risk_status = "not_required"
    status = "paper_buy" if not base_reasons else "rejected"
    paper_buy_allowed = not base_reasons
    rejection_reason = ",".join(base_reasons) if base_reasons else None
    if variant_id == VARIANT_B_ID and not base_reasons:
        available = [field for field in AVAILABLE_RISK_FIELDS if _field_has_value(row, field)]
        missing = [field for field in AVAILABLE_RISK_FIELDS if not _field_has_value(row, field)]
        if not available:
            status = "not_evaluable"
            paper_buy_allowed = False
            risk_status = "missing"
            rejection_reason = "available_risk_fields_missing"
        elif _has_negative_risk_value(row, available):
            status = "rejected"
            paper_buy_allowed = False
            risk_status = "risk_filter_available_fail"
            rejection_reason = "available_risk_filter_fail"
        else:
            risk_status = "risk_filter_available_pass"
    elif variant_id == VARIANT_C_ID and not base_reasons:
        missing = [field for field in FULL_RISK_FIELDS if not _field_has_value(row, field)]
        if missing:
            status = "not_evaluable"
            paper_buy_allowed = False
            risk_status = "missing"
            rejection_reason = "full_risk_fields_missing"
        elif _has_negative_risk_value(row, FULL_RISK_FIELDS):
            status = "rejected"
            paper_buy_allowed = False
            risk_status = "risk_filter_full_fail"
            rejection_reason = "full_risk_filter_fail"
        else:
            risk_status = "risk_filter_full_pass"
    elif variant_id == VARIANT_A_ID:
        risk_status = "not_required" if not base_reasons else "rejected"
    decision = {
        "decision_id": f"variant_decision_{variant_id}_{candidate['mint']}_{int(float(row['timestamp']) * 1000)}",
        "mint": candidate["mint"],
        "ca": candidate["mint"],
        "timestamp": row["timestamp"],
        "base_rule_id": FROZEN_BUY_RULE_ID,
        "exit_rule_id": FROZEN_EXIT_RULE_ID,
        "variant_id": variant_id,
        "variant_status": status,
        "paper_buy_allowed": bool(paper_buy_allowed),
        "paper_buy_emitted": status == "paper_buy",
        "confirmed_10k_time": candidate.get("confirmed_milestone_times", {}).get("10k"),
        "confirmed_20k_time": candidate.get("confirmed_milestone_times", {}).get("20k"),
        "paper_buy_fdv": row.get("fdv_proxy"),
        "fdv_efficiency_bucket": _overall_efficiency_bucket(features),
        "fdv_efficiency_threshold_status": "fdv_threshold_unfrozen",
        "risk_filter_status": risk_status,
        "missing_required_fields": missing,
        "rejection_reason": rejection_reason,
        "no_real_trade": True,
        **features,
        **_risk_field_values(row),
    }
    return decision


def _create_variant_position(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    state.setdefault("variant_open_positions", {})
    key = _variant_position_key(decision["variant_id"], candidate["mint"])
    if key in state["variant_open_positions"]:
        return
    fdv = float(row["fdv_proxy"])
    state["variant_open_positions"][key] = {
        "position_id": f"variant_position_{key}_{int(float(row['timestamp']) * 1000)}",
        "variant_id": decision["variant_id"],
        "mint": candidate["mint"],
        "ca": candidate["mint"],
        "entry_time": row["timestamp"],
        "paper_buy_fdv": fdv,
        "local_high_fdv": fdv,
        "drawdown_pct": 0.0,
        "first_30pct_drawdown_time": None,
        "reclaim_timer_started_at": None,
        "reclaim_prior_high_time": None,
        "paper_sell_emitted": False,
        "base_rule_id": FROZEN_BUY_RULE_ID,
        "exit_rule_id": FROZEN_EXIT_RULE_ID,
        "no_real_trade": True,
    }


def _evaluate_variant_exits(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    candidate: dict[str, Any],
    row: dict[str, Any],
) -> int:
    state.setdefault("variant_open_positions", {})
    state.setdefault("variant_closed_positions", {})
    fdv = float(row["fdv_proxy"])
    timestamp = float(row["timestamp"])
    closed = 0
    for key, position in list(state["variant_open_positions"].items()):
        if position.get("mint") != candidate["mint"]:
            continue
        local_high = max(float(position.get("local_high_fdv") or 0.0), fdv)
        position["local_high_fdv"] = local_high
        position["current_fdv"] = fdv
        drawdown_pct = 0.0 if local_high <= 0 else max(0.0, (local_high - fdv) / local_high)
        position["drawdown_pct"] = _round_pct(drawdown_pct)
        if fdv >= local_high:
            position["reclaim_prior_high_time"] = timestamp
        if drawdown_pct >= DRAW_DOWN_EXIT_PCT and position.get("first_30pct_drawdown_time") is None:
            position["first_30pct_drawdown_time"] = timestamp
            position["reclaim_timer_started_at"] = timestamp
        drawdown_time = _num(position.get("first_30pct_drawdown_time"))
        if drawdown_time is None or timestamp - drawdown_time < NO_RECLAIM_EXIT_SECONDS or fdv >= local_high:
            continue
        exit_row = {
            "paper_event_id": f"variant_paper_sell_{position['variant_id']}_{candidate['mint']}_{int(timestamp * 1000)}",
            "variant_id": position["variant_id"],
            "mint": candidate["mint"],
            "ca": candidate["mint"],
            "timestamp": timestamp,
            "base_rule_id": FROZEN_BUY_RULE_ID,
            "exit_rule_id": FROZEN_EXIT_RULE_ID,
            "paper_buy_fdv": position.get("paper_buy_fdv"),
            "paper_sell_fdv": fdv,
            "local_high_fdv": local_high,
            "drawdown_pct": _round_pct(drawdown_pct),
            "first_30pct_drawdown_time": drawdown_time,
            "reclaim_timer_started_at": position.get("reclaim_timer_started_at"),
            "reclaim_prior_high_time": position.get("reclaim_prior_high_time"),
            "no_reclaim_after_10m": True,
            "paper_sell_emitted": True,
            "exit_reason": "no_reclaim_after_10m_30pct_drawdown",
            "time_since_entry_seconds": _round_seconds(timestamp - float(position.get("entry_time") or timestamp)),
            "no_real_trade": True,
        }
        _append_jsonl(config.paper_rule_variant_exits_path, exit_row)
        position.update(exit_row)
        position["paper_sell_emitted"] = True
        state["variant_closed_positions"][key] = position
        del state["variant_open_positions"][key]
        closed += 1
    return closed


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
    *,
    runtime_mode: str,
) -> None:
    state["updated_at"] = _utc_now()
    state["candidates"][candidate["mint"]] = candidate
    state["queue_sizes"] = _queue_sizes_from_state(state)
    latency = _latency_row(candidate, row, started, previous_state, runtime_mode=runtime_mode)
    stats = state.setdefault("runtime_stats", {})
    stats["last_runtime_mode"] = runtime_mode
    stats["events_processed"] = int(stats.get("events_processed") or 0) + 1
    if runtime_mode == "live_bus":
        stats["live_bus_events"] = int(stats.get("live_bus_events") or 0) + 1
        stats["bus_queue_depth"] = int(stats.get("bus_queue_depth") or 0)
    elif runtime_mode == "file_adapter":
        stats["file_adapter_events"] = int(stats.get("file_adapter_events") or 0) + 1
    _append_jsonl(config.latency_events_path, latency)
    _write_json(config.runtime_state_path, state)


def _latency_row(candidate: dict[str, Any], row: dict[str, Any], started: float, previous_state: Any, *, runtime_mode: str) -> dict[str, Any]:
    now = time.time()
    observed = float(row.get("event_observed_at") or row["timestamp"])
    bus_emit_monotonic = _num(row.get("bus_emit_monotonic_at"))
    observed_monotonic = _num(row.get("monotonic_observed_at"))
    receive_monotonic = _num(row.get("runtime_receive_monotonic_at")) or time.monotonic()
    event_to_bus_ms = _round_ms(max(0.0, (bus_emit_monotonic - observed_monotonic) * 1000.0)) if bus_emit_monotonic is not None and observed_monotonic is not None else None
    bus_to_runtime_ms = _round_ms(max(0.0, (receive_monotonic - bus_emit_monotonic) * 1000.0)) if bus_emit_monotonic is not None else None
    runtime_eval_ms = _round_ms((time.time() - started) * 1000.0)
    event_to_rule_ms = (
        _round_ms(max(0.0, (time.monotonic() - observed_monotonic) * 1000.0)) if observed_monotonic is not None else _round_ms((now - observed) * 1000.0)
    )
    confirmed_times = candidate.get("confirmed_milestone_times") or {}
    return {
        "runtime_mode": runtime_mode,
        "event_observed_at": observed,
        "source_event_observed_at": observed,
        "bus_emit_at": row.get("bus_emit_at"),
        "runtime_receive_at": row.get("runtime_receive_at"),
        "candidate_state_update_at": float(row["timestamp"]),
        "confirmed_10k_at": confirmed_times.get("10k"),
        "confirmed_20k_at": confirmed_times.get("20k"),
        "rule_eval_started_at": started,
        "rule_eval_finished_at": time.time(),
        "rule_fired_at": float(row["timestamp"]) if candidate.get("paper_buy_created") else None,
        "paper_buy_event_written_at": float(row["timestamp"]) if candidate.get("paper_buy_created") else None,
        "paper_event_written_at": float(row["timestamp"]) if candidate.get("paper_buy_created") or candidate.get("paper_closed") else None,
        "event_to_bus_ms": event_to_bus_ms,
        "bus_to_runtime_ms": bus_to_runtime_ms,
        "runtime_eval_ms": runtime_eval_ms,
        "event_to_rule_ms": event_to_rule_ms,
        "event_to_paper_write_ms": event_to_rule_ms if candidate.get("paper_buy_created") or candidate.get("paper_closed") else None,
        "detection_to_rule_latency_ms": _round_ms((now - observed) * 1000.0),
        "state_age_ms": _round_ms(max(0.0, float(row["timestamp"]) - float(candidate.get("first_seen_at") or row["timestamp"])) * 1000.0),
        "rule_eval_latency_ms": runtime_eval_ms,
        "source_event_type": row.get("source_event_type"),
        "data_source": row.get("data_source"),
        "fdv_source": row.get("fdv_source") or row.get("data_source"),
        "fdv_source_confidence": row.get("fdv_source_confidence"),
        "fdv_probe_method": row.get("fdv_probe_method"),
        "first_fdv_source": row.get("first_fdv_source") or row.get("fdv_source") or row.get("data_source"),
        "observed_to_bonding_curve_resolved_ms": row.get("observed_to_bonding_curve_resolved_ms"),
        "bonding_curve_resolved_to_getAccountInfo_ms": row.get("bonding_curve_resolved_to_getAccountInfo_ms"),
        "getAccountInfo_latency_ms": row.get("getAccountInfo_latency_ms"),
        "decode_latency_ms": row.get("decode_latency_ms"),
        "observed_to_first_fdv_account_state_ms": row.get("observed_to_first_fdv_account_state_ms"),
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
        if state_name in ARCHIVE_STATES:
            continue
        if state_name == "paper_position_open":
            sizes["paper_position_open"] += 1
        elif state_name == "confirmed_10k_watch":
            sizes["confirmed_10k_watch"] += 1
        elif state_name == "near_threshold_watch":
            sizes["near_threshold_watch"] += 1
        elif state_name == "fdv_path_seen":
            sizes["first_fdv_path"] += 1
        elif state_name in {"birth_seen", "light_watch"}:
            if state_name == "birth_seen":
                sizes["fresh_birth_first_path"] += 1
            else:
                sizes["light_watch"] += 1
    return sizes


def _record_promotions(state: dict[str, Any], candidate: dict[str, Any], previous_state: Any, previous_tier: int) -> None:
    stats = _scheduler_stats(state)
    state_name = candidate.get("state")
    tier = int(candidate.get("tier") or 0)
    promotions = candidate.setdefault("promotions_recorded", [])
    if candidate.get("path_rows") and "fdv_path_seen" not in promotions:
        promotions.append("fdv_path_seen")
        stats["promoted_to_fdv_path"] = int(stats.get("promoted_to_fdv_path") or 0) + 1
        stats["tier_1_processed_count"] = int(stats.get("tier_1_processed_count") or 0) + 1
        stats["tier_1_promotion_count"] = int(stats.get("tier_1_promotion_count") or 0) + 1
    if tier >= 2 and "near_threshold_watch" not in promotions:
        promotions.append("near_threshold_watch")
        stats["promoted_to_near_threshold"] = int(stats.get("promoted_to_near_threshold") or 0) + 1
    if state_name == "confirmed_10k_watch" and "confirmed_10k_watch" not in promotions:
        promotions.append("confirmed_10k_watch")
        stats["promoted_to_confirmed_10k"] = int(stats.get("promoted_to_confirmed_10k") or 0) + 1
    if state_name == "paper_position_open" and "paper_position_open" not in promotions:
        promotions.append("paper_position_open")
        stats["promoted_to_paper_position"] = int(stats.get("promoted_to_paper_position") or 0) + 1
    if previous_state in ARCHIVE_STATES and state_name not in ARCHIVE_STATES:
        stats["reactivation_count"] = int(stats.get("reactivation_count") or 0) + 1


def _event_has_activity(row: dict[str, Any]) -> bool:
    return any(int(_num(row.get(key)) or 0) > 0 for key in ["event_count", "buy_count", "sell_count", "active_wallet_count"])


def _scheduler_stats(state: dict[str, Any]) -> dict[str, Any]:
    stats = state.setdefault("scheduler_stats", {})
    for key, value in _default_scheduler_stats().items():
        stats.setdefault(key, value)
    return stats


def _variant_status(
    config: RuleRuntimeConfig,
    state: dict[str, Any],
    *,
    variant_decisions: list[dict[str, Any]] | None = None,
    variant_exits: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    decisions = variant_decisions if variant_decisions is not None else _read_jsonl(config.paper_rule_variant_decisions_path)
    exits = variant_exits if variant_exits is not None else _read_jsonl(config.paper_rule_variant_exits_path)
    open_positions = state.get("variant_open_positions") or {}
    summary: dict[str, dict[str, Any]] = {}
    for variant_id in RULE_VARIANTS:
        variant_rows = [row for row in decisions if row.get("variant_id") == variant_id]
        exit_rows = [row for row in exits if row.get("variant_id") == variant_id]
        summary[variant_id] = {
            "paper_buys": sum(1 for row in variant_rows if row.get("variant_status") == "paper_buy"),
            "paper_sells": sum(1 for row in exit_rows if row.get("paper_sell_emitted") is True),
            "open_positions": sum(1 for row in open_positions.values() if row.get("variant_id") == variant_id),
            "rejected": sum(1 for row in variant_rows if row.get("variant_status") == "rejected"),
            "not_evaluable": sum(1 for row in variant_rows if row.get("variant_status") == "not_evaluable"),
            "label_only": sum(1 for row in variant_rows if row.get("variant_status") == "label_only"),
            "missing_fields": sum(len(row.get("missing_required_fields") or []) for row in variant_rows),
        }
    return summary


def _first_fdv_queue_summary(config: RuleRuntimeConfig, state: dict[str, Any], latency_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = time.time()
    candidates = state.get("candidates") or {}
    stats = _scheduler_stats(state)
    tier_names = {
        0: "tier_0_light_watch",
        1: "tier_1_fdv_path_seen",
        2: "tier_2_near_threshold_watch",
        3: "tier_3_confirmed_10k_watch",
        4: "tier_4_paper_position_open",
    }
    depth_by_tier = {name: 0 for name in tier_names.values()}
    ages_by_tier: dict[str, list[float]] = {name: [] for name in tier_names.values()}
    with_first_fdv_path = 0
    first_path_latencies: list[float | None] = []
    active_candidates = []
    for candidate in candidates.values():
        first_seen = _num(candidate.get("first_seen_at")) or now
        if candidate.get("path_rows"):
            with_first_fdv_path += 1
            first_path = _num(candidate.get("first_fdv_path_time"))
            if first_path is not None:
                first_path_latencies.append(max(0.0, (first_path - first_seen) * 1000.0))
        state_name = candidate.get("state")
        if state_name in ARCHIVE_STATES:
            continue
        active_candidates.append(candidate)
        tier = int(candidate.get("tier") or 0)
        name = tier_names.get(tier, "tier_0_light_watch")
        depth_by_tier[name] += 1
        ages_by_tier[name].append(max(0.0, now - first_seen))
    tier_1_rows = [
        row
        for row in active_candidates
        if int(row.get("tier") or 0) == 1 and row.get("state") == "fdv_path_seen"
    ]
    tier_1_rows_oldest_first = sorted(
        tier_1_rows,
        key=lambda row: (
            _num(row.get("first_seen_at")) or now,
            str(row.get("mint") or ""),
        ),
    )
    tier_1_ages = [max(0.0, now - (_num(row.get("first_seen_at")) or now)) for row in tier_1_rows_oldest_first]
    tier_1_age_percentiles = _percentiles(tier_1_ages)
    tier_1_depth = len(tier_1_rows_oldest_first)
    tier_1_processed_count = int(stats.get("tier_1_processed_count") or stats.get("promoted_to_fdv_path") or 0)
    tier_1_archive_count = int(stats.get("tier_1_archive_count") or 0)
    tier_1_promotion_count = int(stats.get("tier_1_promotion_count") or stats.get("promoted_to_fdv_path") or 0)
    tier_1_retry_count = int(stats.get("tier_1_retry_count") or 0)
    no_path_timeouts = int(stats.get("archived_no_fdv_path_timeout") or 0)
    first_fdv_latency = _percentiles(first_path_latencies)
    first_fdv_success_rate = _round_num(with_first_fdv_path / max(1, len(candidates))) if candidates else 0.0
    first_fdv_timeout_rate = _round_num(no_path_timeouts / max(1, with_first_fdv_path + no_path_timeouts))
    tier_1_pressure_mode = bool(stats.get("tier_1_pressure_mode")) or tier_1_depth >= TIER_1_PRESSURE_THRESHOLD
    total_active = sum(depth_by_tier.values())
    oldest_by_tier = {tier: (_round_seconds(max(values)) if values else None) for tier, values in ages_by_tier.items()}
    avg_by_tier = {tier: (_round_seconds(sum(values) / len(values)) if values else None) for tier, values in ages_by_tier.items()}
    warnings: list[str] = []
    if tier_1_pressure_mode:
        warnings.append("first_fdv_queue_growth_warning")
    if (oldest_by_tier["tier_1_fdv_path_seen"] or 0) > TIER_1_MAX_AGE_SECONDS:
        warnings.append("oldest_first_fdv_job_above_timeout")
    if depth_by_tier["tier_2_near_threshold_watch"] > 0 and depth_by_tier["tier_1_fdv_path_seen"] > 100:
        warnings.append("near_threshold_starvation_warning")
    if depth_by_tier["tier_4_paper_position_open"] > 0 and depth_by_tier["tier_1_fdv_path_seen"] > 100:
        warnings.append("paper_position_starvation_warning")
    return {
        "scheduler_mode": SCHEDULER_MODE,
        "queue_depth_total": total_active,
        "queue_depth_by_tier": depth_by_tier,
        "oldest_queued_age_seconds_by_tier": oldest_by_tier,
        "average_queued_age_seconds_by_tier": avg_by_tier,
        "archived_no_activity": int(stats.get("archived_no_activity") or 0),
        "archived_no_fdv_path_timeout": int(stats.get("archived_no_fdv_path_timeout") or 0),
        "archived_parser_failure": int(stats.get("archived_parser_failure") or 0),
        "archived_duplicate": int(stats.get("archived_duplicate") or 0),
        "archived_provenance_failure": int(stats.get("archived_provenance_failure") or 0),
        "promoted_to_fdv_path": int(stats.get("promoted_to_fdv_path") or 0),
        "promoted_to_near_threshold": int(stats.get("promoted_to_near_threshold") or 0),
        "promoted_to_confirmed_10k": int(stats.get("promoted_to_confirmed_10k") or 0),
        "promoted_to_paper_position": int(stats.get("promoted_to_paper_position") or 0),
        "tier_1_depth": tier_1_depth,
        "tier_1_oldest_age_seconds": _round_seconds(max(tier_1_ages)) if tier_1_ages else None,
        "tier_1_age_p50_p90": {
            "p50": tier_1_age_percentiles.get("p50"),
            "p90": tier_1_age_percentiles.get("p90"),
        },
        "tier_1_processed_count": tier_1_processed_count,
        "tier_1_archive_count": tier_1_archive_count,
        "tier_1_promotion_count": tier_1_promotion_count,
        "tier_1_retry_count": tier_1_retry_count,
        "tier_1_retry_budget": MAX_STALE_RETRIES,
        "tier_1_max_age_seconds": TIER_1_MAX_AGE_SECONDS,
        "tier_1_pressure_threshold": TIER_1_PRESSURE_THRESHOLD,
        "tier_1_pressure_mode": tier_1_pressure_mode,
        "tier_1_next_mints_oldest_first": [str(row.get("mint") or "") for row in tier_1_rows_oldest_first[:10]],
        "promotion_rate": _round_num(tier_1_promotion_count / max(1, tier_1_processed_count)),
        "archive_rate": _round_num(tier_1_archive_count / max(1, tier_1_processed_count)),
        "first_path_success_rate": first_fdv_success_rate,
        "first_fdv_success_rate": first_fdv_success_rate,
        "first_fdv_timeout_rate": first_fdv_timeout_rate,
        "first_fdv_median_latency_ms": first_fdv_latency.get("p50"),
        "first_path_latency_p50_p90_p99": _percentiles(first_path_latencies),
        "downgrade_count": int(stats.get("downgrade_count") or 0),
        "reactivation_count": int(stats.get("reactivation_count") or 0),
        "helius_rpc_request_count": stats.get("helius_rpc_request_count"),
        "http_429_count": int(stats.get("http_429_count") or 0),
        "metadata_hot_path_allowed": False,
        "metadata_enrichment_in_first_fdv": False,
        "warnings": warnings,
    }


def _first_fdv_probe_source_summary(state: dict[str, Any], latency_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stats = _scheduler_stats(state)
    source_rows = [
        row
        for row in latency_rows
        if row.get("fdv_source") or row.get("first_fdv_source") or row.get("source_event_type")
    ]
    source_mix: dict[str, int] = {}
    for row in source_rows:
        source = str(row.get("first_fdv_source") or row.get("fdv_source") or row.get("data_source") or "unknown")
        source_mix[source] = int(source_mix.get(source) or 0) + 1
    account_state_successes = sum(1 for row in source_rows if (row.get("first_fdv_source") or row.get("fdv_source")) == "bonding_curve_account_state")
    transaction_delta_successes = sum(1 for row in source_rows if (row.get("first_fdv_source") or row.get("fdv_source")) == "transaction_delta")
    confirmed_path_state_successes = sum(1 for row in source_rows if (row.get("first_fdv_source") or row.get("fdv_source")) == "confirmed_path_state")
    unknown_successes = sum(
        1
        for row in source_rows
        if str(row.get("first_fdv_source") or row.get("fdv_source") or row.get("data_source") or "unknown") in {"", "unknown"}
    )
    return {
        "bonding_curve_account_state_successes": account_state_successes,
        "bonding_curve_account_state_failures": int(stats.get("bonding_curve_account_state_failures") or 0),
        "bonding_curve_account_state_failure_reasons": stats.get("bonding_curve_account_state_failure_reasons") or {},
        "transaction_delta_successes": transaction_delta_successes,
        "confirmed_path_state_successes": confirmed_path_state_successes,
        "unknown_successes": unknown_successes,
        "source_mix": dict(sorted(source_mix.items())),
        "getAccountInfo_p50_p90_p99": _percentiles([_num(row.get("getAccountInfo_latency_ms")) for row in source_rows]),
        "decode_p50_p90_p99": _percentiles([_num(row.get("decode_latency_ms")) for row in source_rows]),
        "observed_to_first_fdv_account_state_p50_p90_p99": _percentiles(
            [_num(row.get("observed_to_first_fdv_account_state_ms")) for row in source_rows]
        ),
        "observed_to_bonding_curve_resolved_p50_p90_p99": _percentiles(
            [_num(row.get("observed_to_bonding_curve_resolved_ms")) for row in source_rows]
        ),
        "bonding_curve_resolved_to_getAccountInfo_p50_p90_p99": _percentiles(
            [_num(row.get("bonding_curve_resolved_to_getAccountInfo_ms")) for row in source_rows]
        ),
        "accountSubscribe_bonding_curve_status": stats.get("account_subscribe_bonding_curve_status") or "accountSubscribe_bonding_curve_not_implemented",
        "active_account_subscriptions": int(stats.get("active_account_subscriptions") or 0),
        "metadata_hot_path_allowed": False,
    }


def _helius_transaction_subscribe_first_fdv_status(config: RuleRuntimeConfig, source_summary: dict[str, Any]) -> dict[str, Any]:
    create_rows = _read_jsonl(config.pumpfun_create_stream_events_path)
    probe_rows = _read_jsonl(config.bonding_curve_account_probe_events_path)
    audit = _read_json(config.helius_transaction_subscribe_capability_audit_json_path)
    recommended = audit.get("recommended_endpoint") if isinstance(audit.get("recommended_endpoint"), dict) else {}
    probe_failures = [row for row in probe_rows if row.get("probe_status") != "success"]
    failure_reasons: dict[str, int] = {}
    for row in probe_failures:
        reason = str(row.get("probe_error") or "unknown")
        failure_reasons[reason] = int(failure_reasons.get(reason) or 0) + 1
    warnings: list[str] = []
    if audit and not recommended.get("transactionSubscribe_supported"):
        warnings.append("transactionSubscribe_unsupported_fallback_to_logs")
    if probe_failures:
        warnings.append("bonding_curve_account_probe_failures_present")
    account_not_found_retries = int(sum(_num(row.get("account_not_found_retry_count")) or 0 for row in probe_rows))
    account_not_found_recovered = sum(1 for row in probe_rows if row.get("account_not_found_recovered_by_retry") is True)
    account_not_found_final_failures = sum(1 for row in probe_rows if row.get("account_not_found_final_failure") is True)
    return {
        "transactionSubscribe_supported": bool(recommended.get("transactionSubscribe_supported")),
        "endpoint_used": recommended.get("name"),
        "create_events_decoded": sum(1 for row in create_rows if row.get("parser_status") == "decoded"),
        "curve_pda_verified": sum(1 for row in create_rows if row.get("bonding_curve_verified") is True),
        "curve_account_probes_started": len(probe_rows),
        "probes_started_during_stream": sum(1 for row in probe_rows if row.get("probe_scheduled_during_stream") is True),
        "curve_account_probes_succeeded": sum(1 for row in probe_rows if row.get("probe_status") == "success"),
        "curve_account_probes_failed": len(probe_failures),
        "first_attempt_successes": sum(1 for row in probe_rows if row.get("probe_status") == "success" and int(_num(row.get("probe_attempt_count")) or 1) == 1),
        "account_not_found_retries": account_not_found_retries,
        "account_not_found_recovered_by_retry": account_not_found_recovered,
        "account_not_found_final_failures": account_not_found_final_failures,
        "account_not_found_retry_recovery_rate": _round_num(account_not_found_recovered / max(1, account_not_found_recovered + account_not_found_final_failures)),
        "first_fdv_from_bonding_curve_account_state": int(source_summary.get("bonding_curve_account_state_successes") or 0),
        "first_fdv_from_transaction_delta": int(source_summary.get("transaction_delta_successes") or 0),
        "first_fdv_from_unknown": int(source_summary.get("unknown_successes") or 0),
        "getAccountInfo_p50_p90_p99": _percentiles([_num(row.get("getAccountInfo_latency_ms")) for row in probe_rows]),
        "accountSubscribe_p50_p90_p99": _percentiles([_num(row.get("accountSubscribe_latency_ms")) for row in probe_rows]),
        "observed_to_probe_started_p50_p90_p99": _percentiles([_num(row.get("observed_to_probe_started_ms")) for row in probe_rows]),
        "probe_started_to_first_curve_state_p50_p90_p99": _percentiles(
            [_num(row.get("probe_started_to_first_curve_state_ms")) for row in probe_rows]
        ),
        "observed_to_first_fdv_p50_p90_p99": _percentiles([_num(row.get("observed_to_first_fdv_emitted_ms")) for row in probe_rows]),
        "observed_to_first_fdv_account_state_p50_p90_p99": source_summary.get("observed_to_first_fdv_account_state_p50_p90_p99"),
        "decode_failures": failure_reasons.get("decode_failed", 0),
        "probe_failures_by_reason": failure_reasons,
        "http_429": int(source_summary.get("http_429_count") or 0),
        "accountSubscribe_bonding_curve_status": source_summary.get("accountSubscribe_bonding_curve_status"),
        "warnings": warnings,
    }


def _write_monitor(config: RuleRuntimeConfig, state: dict[str, Any]) -> None:
    trades = _read_jsonl(config.paper_trades_path)
    decisions = _read_jsonl(config.paper_decisions_path)
    variant_decisions = _read_jsonl(config.paper_rule_variant_decisions_path)
    variant_exits = _read_jsonl(config.paper_rule_variant_exits_path)
    latency = _read_jsonl(config.latency_events_path)
    candidates = state.get("candidates") or {}
    rejected = [row for row in decisions if row.get("decision") == "paper_rejected_entry"]
    open_positions = list((state.get("open_positions") or {}).values())
    closed_positions = list((state.get("closed_positions") or {}).values())
    payload = {
        "updated_at": _utc_now(),
        "runtime_label": RUNTIME_LABEL,
        "runtime_mode": (state.get("runtime_stats") or {}).get("last_runtime_mode") or "idle",
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
        "variants": _variant_status(config, state, variant_decisions=variant_decisions, variant_exits=variant_exits),
        "first_fdv_queue": _first_fdv_queue_summary(config, state, latency),
        "first_fdv_probe_sources": _first_fdv_probe_source_summary(state, latency),
        "helius_transaction_subscribe_first_fdv": _helius_transaction_subscribe_first_fdv_status(
            config,
            _first_fdv_probe_source_summary(state, latency),
        ),
        "variant_decisions": variant_decisions,
        "variant_exits": variant_exits,
        "live_bus_events": int((state.get("runtime_stats") or {}).get("live_bus_events") or 0),
        "file_adapter_events": int((state.get("runtime_stats") or {}).get("file_adapter_events") or 0),
        "latency_p50_p90_p99": _percentiles([_num(row.get("detection_to_rule_latency_ms")) for row in latency]),
        "event_to_rule_p50_p90_p99": _percentiles([_num(row.get("event_to_rule_ms")) for row in latency]),
        "bus_to_runtime_p50_p90_p99": _percentiles([_num(row.get("bus_to_runtime_ms")) for row in latency]),
        "runtime_eval_p50_p90_p99": _percentiles([_num(row.get("runtime_eval_ms")) for row in latency]),
        "state_age_p50_p90_p99": _percentiles([_num(row.get("state_age_ms")) for row in latency]),
        "queue_sizes": state.get("queue_sizes") or {},
        "bus_queue_depth": int((state.get("runtime_stats") or {}).get("bus_queue_depth") or 0),
        "last_paper_decision": decisions[-1] if decisions else None,
        "last_rejection_reason": next((row.get("rejection_reason") for row in reversed(decisions) if row.get("rejection_reason")), None),
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
        f"Runtime mode: {payload.get('runtime_mode')}",
        f"Live bus events: {payload.get('live_bus_events')}",
        f"Closed paper positions: {len(payload['closed_positions'])}",
        f"Rejected entries: {len(payload['rejected_entries'])}",
        "",
        "## Rule Runtime v1 Variants",
    ]
    for variant_id, row in (payload.get("variants") or {}).items():
        lines.append(
            f"- {variant_id}: buys {row.get('paper_buys')}, sells {row.get('paper_sells')}, open {row.get('open_positions')}, rejected {row.get('rejected')}, not evaluable {row.get('not_evaluable')}, missing fields {row.get('missing_fields')}"
        )
    queue = payload.get("first_fdv_queue") or {}
    lines.extend([
        "",
        "## First FDV Queue",
        f"- Scheduler mode: {queue.get('scheduler_mode')}",
        f"- Queue depth total: {queue.get('queue_depth_total')}",
        f"- Queue depth by tier: {queue.get('queue_depth_by_tier')}",
        f"- Oldest queued age by tier: {queue.get('oldest_queued_age_seconds_by_tier')}",
        f"- Tier 1 depth: {queue.get('tier_1_depth')}",
        f"- Tier 1 oldest age: {queue.get('tier_1_oldest_age_seconds')}",
        f"- Tier 1 p50/p90 age: {queue.get('tier_1_age_p50_p90')}",
        f"- Tier 1 processed count: {queue.get('tier_1_processed_count')}",
        f"- Tier 1 archive count: {queue.get('tier_1_archive_count')}",
        f"- Tier 1 promotion count: {queue.get('tier_1_promotion_count')}",
        f"- Tier 1 retry count: {queue.get('tier_1_retry_count')}",
        f"- Tier 1 pressure mode: {queue.get('tier_1_pressure_mode')}",
        f"- Archived no activity: {queue.get('archived_no_activity')}",
        f"- Archived no FDV path timeout: {queue.get('archived_no_fdv_path_timeout')}",
        f"- Promotions: fdv_path={queue.get('promoted_to_fdv_path')}, near_threshold={queue.get('promoted_to_near_threshold')}, confirmed_10k={queue.get('promoted_to_confirmed_10k')}, paper_position={queue.get('promoted_to_paper_position')}",
        f"- First path success rate: {queue.get('first_path_success_rate')}",
        f"- First-FDV success rate: {queue.get('first_fdv_success_rate')}",
        f"- First-FDV timeout rate: {queue.get('first_fdv_timeout_rate')}",
        f"- First-FDV median latency: {queue.get('first_fdv_median_latency_ms')}",
        f"- First path latency p50/p90/p99: {queue.get('first_path_latency_p50_p90_p99')}",
    ])
    sources = payload.get("first_fdv_probe_sources") or {}
    txsub = payload.get("helius_transaction_subscribe_first_fdv") or {}
    lines.extend(
        [
            "",
            "## First-FDV Probe Sources",
            f"- Bonding curve account-state successes: {sources.get('bonding_curve_account_state_successes')}",
            f"- Bonding curve account-state failures: {sources.get('bonding_curve_account_state_failures')}",
            f"- Transaction delta successes: {sources.get('transaction_delta_successes')}",
            f"- Confirmed path-state successes: {sources.get('confirmed_path_state_successes')}",
            f"- Unknown successes: {sources.get('unknown_successes')}",
            f"- Source mix: {sources.get('source_mix')}",
            f"- getAccountInfo p50/p90/p99: {sources.get('getAccountInfo_p50_p90_p99')}",
            f"- Decode p50/p90/p99: {sources.get('decode_p50_p90_p99')}",
            f"- Observed to account-state FDV p50/p90/p99: {sources.get('observed_to_first_fdv_account_state_p50_p90_p99')}",
            f"- accountSubscribe status: {sources.get('accountSubscribe_bonding_curve_status')}",
            f"- Active account subscriptions: {sources.get('active_account_subscriptions')}",
        ]
    )
    lines.extend(
        [
            "",
            "## Helius transactionSubscribe First-FDV",
            f"- transactionSubscribe supported: {txsub.get('transactionSubscribe_supported')}",
            f"- endpoint used: {txsub.get('endpoint_used')}",
            f"- create events decoded: {txsub.get('create_events_decoded')}",
            f"- curve PDA verified: {txsub.get('curve_pda_verified')}",
            f"- curve account probes started: {txsub.get('curve_account_probes_started')}",
            f"- probes started during stream: {txsub.get('probes_started_during_stream')}",
            f"- curve account probes succeeded: {txsub.get('curve_account_probes_succeeded')}",
            f"- curve account probes failed: {txsub.get('curve_account_probes_failed')}",
            f"- first-attempt successes: {txsub.get('first_attempt_successes')}",
            f"- account-not-found retries: {txsub.get('account_not_found_retries')}",
            f"- account-not-found recovered by retry: {txsub.get('account_not_found_recovered_by_retry')}",
            f"- account-not-found final failures: {txsub.get('account_not_found_final_failures')}",
            f"- account-not-found retry recovery rate: {txsub.get('account_not_found_retry_recovery_rate')}",
            f"- first FDV from bonding curve account-state: {txsub.get('first_fdv_from_bonding_curve_account_state')}",
            f"- first FDV from transaction delta: {txsub.get('first_fdv_from_transaction_delta')}",
            f"- observed to probe started p50/p90/p99: {txsub.get('observed_to_probe_started_p50_p90_p99')}",
            f"- probe started to first curve state p50/p90/p99: {txsub.get('probe_started_to_first_curve_state_p50_p90_p99')}",
            f"- observed to first FDV p50/p90/p99: {txsub.get('observed_to_first_fdv_p50_p90_p99')}",
            f"- getAccountInfo p50/p90/p99: {txsub.get('getAccountInfo_p50_p90_p99')}",
            f"- accountSubscribe p50/p90/p99: {txsub.get('accountSubscribe_p50_p90_p99')}",
            f"- warnings: {txsub.get('warnings')}",
        ]
    )
    lines.extend([
        "",
        "Paper-only accounting. Live trading is disabled.",
        "",
        "## Open Positions",
    ])
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
    variant_cards = "\n".join(
        "<div class=\"variant\">"
        f"<h3>{html.escape(str(variant_id))}</h3>"
        f"<p>Buys <b>{row.get('paper_buys')}</b> | Sells <b>{row.get('paper_sells')}</b> | Open <b>{row.get('open_positions')}</b></p>"
        f"<p>Rejected <b>{row.get('rejected')}</b> | Not evaluable <b>{row.get('not_evaluable')}</b> | Missing fields <b>{row.get('missing_fields')}</b></p>"
        "</div>"
        for variant_id, row in (payload.get("variants") or {}).items()
    )
    queue = payload.get("first_fdv_queue") or {}
    sources = payload.get("first_fdv_probe_sources") or {}
    txsub = payload.get("helius_transaction_subscribe_first_fdv") or {}
    queue_cards = "\n".join(
        f"<div class=\"stat\">{html.escape(str(tier))}<br><b>{html.escape(str(depth))}</b></div>"
        for tier, depth in (queue.get("queue_depth_by_tier") or {}).items()
    )
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
.variants{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:12px}} .variant{{background:white;border:1px solid #ddd;border-radius:8px;padding:12px 16px}}
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
<p>Runtime mode: {html.escape(str(payload['runtime_mode']))}</p>
<p>Live bus events: {html.escape(str(payload['live_bus_events']))}; file adapter events: {html.escape(str(payload['file_adapter_events']))}; bus queue depth: {html.escape(str(payload['bus_queue_depth']))}</p>
<p>Event-to-rule p50/p90/p99: {html.escape(str(payload['event_to_rule_p50_p90_p99']))}</p>
<p>Bus-to-runtime p50/p90/p99: {html.escape(str(payload['bus_to_runtime_p50_p90_p99']))}</p>
<p>Runtime eval p50/p90/p99: {html.escape(str(payload['runtime_eval_p50_p90_p99']))}</p>
<p>Last rejection reason: {html.escape(str(payload['last_rejection_reason'] or ''))}</p>
<h2>Rule Runtime v1 Variants</h2>
<div class=\"variants\">{variant_cards}</div>
<h2>First FDV Queue</h2>
<div class=\"stats\">{queue_cards}</div>
<p>Scheduler mode: {html.escape(str(queue.get('scheduler_mode')))}; total depth: {html.escape(str(queue.get('queue_depth_total')))}</p>
<p>Oldest age by tier: {html.escape(str(queue.get('oldest_queued_age_seconds_by_tier')))}</p>
<p>Tier 1 depth: {html.escape(str(queue.get('tier_1_depth')))}; oldest age: {html.escape(str(queue.get('tier_1_oldest_age_seconds')))}; p50/p90 age: {html.escape(str(queue.get('tier_1_age_p50_p90')))}</p>
<p>Tier 1 processed: {html.escape(str(queue.get('tier_1_processed_count')))}; archives: {html.escape(str(queue.get('tier_1_archive_count')))}; promotions: {html.escape(str(queue.get('tier_1_promotion_count')))}; retries: {html.escape(str(queue.get('tier_1_retry_count')))}; pressure mode: {html.escape(str(queue.get('tier_1_pressure_mode')))}</p>
<p>Archived no activity: {html.escape(str(queue.get('archived_no_activity')))}; archived no FDV path timeout: {html.escape(str(queue.get('archived_no_fdv_path_timeout')))}</p>
<p>Promotions: FDV path {html.escape(str(queue.get('promoted_to_fdv_path')))}, near-threshold {html.escape(str(queue.get('promoted_to_near_threshold')))}, confirmed 10k {html.escape(str(queue.get('promoted_to_confirmed_10k')))}, paper position {html.escape(str(queue.get('promoted_to_paper_position')))}</p>
<p>First-FDV success rate: {html.escape(str(queue.get('first_fdv_success_rate')))}; timeout rate: {html.escape(str(queue.get('first_fdv_timeout_rate')))}; median latency ms: {html.escape(str(queue.get('first_fdv_median_latency_ms')))}</p>
<p>First path success rate: {html.escape(str(queue.get('first_path_success_rate')))}; first path latency p50/p90/p99: {html.escape(str(queue.get('first_path_latency_p50_p90_p99')))}</p>
<h2>First-FDV Probe Sources</h2>
<p>Bonding curve account-state successes: {html.escape(str(sources.get('bonding_curve_account_state_successes')))}; failures: {html.escape(str(sources.get('bonding_curve_account_state_failures')))}</p>
<p>Source mix: {html.escape(str(sources.get('source_mix')))}</p>
<p>getAccountInfo p50/p90/p99: {html.escape(str(sources.get('getAccountInfo_p50_p90_p99')))}</p>
<p>Decode p50/p90/p99: {html.escape(str(sources.get('decode_p50_p90_p99')))}</p>
<p>Observed to account-state FDV p50/p90/p99: {html.escape(str(sources.get('observed_to_first_fdv_account_state_p50_p90_p99')))}</p>
<p>accountSubscribe status: {html.escape(str(sources.get('accountSubscribe_bonding_curve_status')))}; active subscriptions: {html.escape(str(sources.get('active_account_subscriptions')))}</p>
<h2>Helius transactionSubscribe First-FDV</h2>
<p>transactionSubscribe supported: {html.escape(str(txsub.get('transactionSubscribe_supported')))}; endpoint used: {html.escape(str(txsub.get('endpoint_used')))}</p>
<p>Create events decoded: {html.escape(str(txsub.get('create_events_decoded')))}; curve PDA verified: {html.escape(str(txsub.get('curve_pda_verified')))}</p>
	<p>Curve probes started/during-stream/succeeded/failed: {html.escape(str(txsub.get('curve_account_probes_started')))} / {html.escape(str(txsub.get('probes_started_during_stream')))} / {html.escape(str(txsub.get('curve_account_probes_succeeded')))} / {html.escape(str(txsub.get('curve_account_probes_failed')))}</p>
	<p>First-attempt successes: {html.escape(str(txsub.get('first_attempt_successes')))}; account-not-found retries: {html.escape(str(txsub.get('account_not_found_retries')))}</p>
	<p>Account-not-found recovered by retry: {html.escape(str(txsub.get('account_not_found_recovered_by_retry')))}; final failures: {html.escape(str(txsub.get('account_not_found_final_failures')))}; recovery rate: {html.escape(str(txsub.get('account_not_found_retry_recovery_rate')))}</p>
	<p>First FDV source counts: account-state {html.escape(str(txsub.get('first_fdv_from_bonding_curve_account_state')))}, transaction-delta {html.escape(str(txsub.get('first_fdv_from_transaction_delta')))}, unknown {html.escape(str(txsub.get('first_fdv_from_unknown')))}</p>
	<p>Observed to probe started p50/p90/p99: {html.escape(str(txsub.get('observed_to_probe_started_p50_p90_p99')))}</p>
	<p>Probe started to first curve state p50/p90/p99: {html.escape(str(txsub.get('probe_started_to_first_curve_state_p50_p90_p99')))}</p>
	<p>Observed to first FDV p50/p90/p99: {html.escape(str(txsub.get('observed_to_first_fdv_p50_p90_p99')))}</p>
	<p>accountSubscribe p50/p90/p99: {html.escape(str(txsub.get('accountSubscribe_p50_p90_p99')))}; warnings: {html.escape(str(txsub.get('warnings')))}</p>
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


def _efficiency_bucket_labels(features: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key in ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "fdv_per_active_wallet_at_20k"]:
        value = _num(features.get(key))
        if value is None:
            labels[key] = "missing"
        elif value >= 10_000:
            labels[key] = "very_high"
        elif value >= 5_000:
            labels[key] = "high"
        elif value >= 2_000:
            labels[key] = "medium"
        else:
            labels[key] = "low"
    return labels


def _overall_efficiency_bucket(features: dict[str, Any]) -> str:
    labels = _efficiency_bucket_labels(features)
    values = set(labels.values())
    if "very_high" in values:
        return "very_high"
    if "high" in values:
        return "high"
    if "medium" in values:
        return "medium"
    if values == {"missing"}:
        return "missing"
    return "low"


def _risk_field_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "creator_prior_migration_count": row.get("creator_prior_migration_count"),
        "repeated_buyer_count": row.get("repeated_buyer_count"),
        "holder_count_at_10k_proxy": row.get("holder_count_at_10k_proxy"),
        "holder_growth_to_20k_proxy": row.get("holder_growth_to_20k_proxy"),
        "early_buyer_with_prior_100k_count": row.get("early_buyer_with_prior_100k_count"),
        "early_buyer_with_prior_500k_count": row.get("early_buyer_with_prior_500k_count"),
        "early_buyer_with_prior_1m_count": row.get("early_buyer_with_prior_1m_count"),
        "social_link_count": row.get("social_link_count"),
        "topicality_bucket": row.get("topicality_bucket"),
    }


def _field_has_value(row: dict[str, Any], field: str) -> bool:
    value = row.get(field)
    return value is not None and value != ""


def _has_negative_risk_value(row: dict[str, Any], fields: list[str]) -> bool:
    for field in fields:
        value = _num(row.get(field))
        if value is not None and value < 0:
            return True
    return False


def _variant_position_key(variant_id: str, mint: str) -> str:
    return f"{variant_id}|{mint}"


def _smoke_summary(
    config: RuleRuntimeConfig,
    status: dict[str, Any],
    *,
    events_processed: int,
    adapter_config: RuleRuntimeLiveAdapterConfig,
) -> dict[str, Any]:
    threshold_status = "baseline-label-mode" if "fdv_efficiency_threshold_unfrozen" in (status.get("warnings") or []) else "frozen"
    return {
        "report_id": "rule_runtime_v1_smoke_summary",
        "runtime_label": RUNTIME_LABEL,
        "updated_at": _utc_now(),
        "source_followup_paths_path": str(adapter_config.followup_paths_path),
        "collector_files_read_only": True,
        "events_processed": int(events_processed),
        "confirmed_10k_watches": int(status.get("confirmed_10k_watches") or 0),
        "confirmed_20k_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "paper_buys": int(status.get("paper_buys") or 0),
        "paper_sells": int(status.get("paper_sells") or 0),
        "variants": status.get("variants") or {},
        "first_fdv_queue": status.get("first_fdv_queue") or {},
        "first_fdv_probe_sources": status.get("first_fdv_probe_sources") or {},
        "helius_transaction_subscribe_first_fdv": status.get("helius_transaction_subscribe_first_fdv") or {},
        "helius_transaction_subscribe_first_fdv": status.get("helius_transaction_subscribe_first_fdv") or {},
        "variant_a_paper_buys": int((status.get("variants") or {}).get(VARIANT_A_ID, {}).get("paper_buys") or 0),
        "variant_a_paper_sells": int((status.get("variants") or {}).get(VARIANT_A_ID, {}).get("paper_sells") or 0),
        "variant_b_paper_buys": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("paper_buys") or 0),
        "variant_b_paper_sells": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("paper_sells") or 0),
        "variant_b_not_evaluable": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("not_evaluable") or 0),
        "variant_c_paper_buys": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("paper_buys") or 0),
        "variant_c_paper_sells": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("paper_sells") or 0),
        "variant_c_not_evaluable": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("not_evaluable") or 0),
        "rejected_spikes": int(status.get("rejected_spike_candidates") or 0),
        "rejected_same_timestamp_jumps": int(status.get("rejected_same_timestamp_jumps") or 0),
        "rejected_fdv_anomalies": int(status.get("rejected_fdv_anomalies") or 0),
        "latency_p50_p90_p99": status.get("latency_p50_p90_p99"),
        "monitor_path": str(config.monitor_html_path),
        "threshold_status": threshold_status,
        "paper_only": True,
        "live_trading_enabled": False,
        "no_real_trade_flag": True,
        "warnings": status.get("warnings") or [],
    }


def _smoke_summary_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Rule Runtime v1 Smoke Summary",
            "",
            f"- Updated: `{summary['updated_at']}`",
            f"- Events processed: `{summary['events_processed']}`",
            f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
            f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys: `{summary['paper_buys']}`",
            f"- Paper sells: `{summary['paper_sells']}`",
            f"- Variant A buys/sells: `{summary.get('variant_a_paper_buys')}` / `{summary.get('variant_a_paper_sells')}`",
            f"- Variant B buys/sells/not-evaluable: `{summary.get('variant_b_paper_buys')}` / `{summary.get('variant_b_paper_sells')}` / `{summary.get('variant_b_not_evaluable')}`",
            f"- Variant C buys/sells/not-evaluable: `{summary.get('variant_c_paper_buys')}` / `{summary.get('variant_c_paper_sells')}` / `{summary.get('variant_c_not_evaluable')}`",
            f"- Rejected spikes: `{summary['rejected_spikes']}`",
            f"- Rejected same-timestamp jumps: `{summary['rejected_same_timestamp_jumps']}`",
            f"- Rejected FDV anomalies: `{summary['rejected_fdv_anomalies']}`",
            f"- Latency p50/p90/p99: `{summary['latency_p50_p90_p99']}`",
            f"- Threshold status: `{summary['threshold_status']}`",
            f"- Monitor path: `{summary['monitor_path']}`",
            "",
            "Paper-only. Live trading, private keys, transaction building, swaps, and routing remain disabled.",
        ]
    ) + "\n"


def _live_bus_smoke_summary(
    config: RuleRuntimeConfig,
    status: dict[str, Any],
    *,
    collector_result: dict[str, Any] | None,
    bus_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report_id": "rule_runtime_v1_live_bus_smoke_summary",
        "runtime_label": RUNTIME_LABEL,
        "updated_at": _utc_now(),
        "runtime_mode": status.get("runtime_mode") or "live_bus",
        "events_processed": int(status.get("events_processed") or 0),
        "live_bus_events": int(status.get("live_bus_events") or 0),
        "file_adapter_events": int(status.get("file_adapter_events") or 0),
        "confirmed_10k_watches": int(status.get("confirmed_10k_watches") or 0),
        "confirmed_20k_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "paper_buys": int(status.get("paper_buys") or 0),
        "paper_sells": int(status.get("paper_sells") or 0),
        "variants": status.get("variants") or {},
        "first_fdv_queue": status.get("first_fdv_queue") or {},
        "variant_a_paper_buys": int((status.get("variants") or {}).get(VARIANT_A_ID, {}).get("paper_buys") or 0),
        "variant_a_paper_sells": int((status.get("variants") or {}).get(VARIANT_A_ID, {}).get("paper_sells") or 0),
        "variant_b_paper_buys": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("paper_buys") or 0),
        "variant_b_paper_sells": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("paper_sells") or 0),
        "variant_b_not_evaluable": int((status.get("variants") or {}).get(VARIANT_B_ID, {}).get("not_evaluable") or 0),
        "variant_c_paper_buys": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("paper_buys") or 0),
        "variant_c_paper_sells": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("paper_sells") or 0),
        "variant_c_not_evaluable": int((status.get("variants") or {}).get(VARIANT_C_ID, {}).get("not_evaluable") or 0),
        "rejected_spikes": int(status.get("rejected_spike_candidates") or 0),
        "rejected_same_timestamp_jumps": int(status.get("rejected_same_timestamp_jumps") or 0),
        "rejected_fdv_anomalies": int(status.get("rejected_fdv_anomalies") or 0),
        "event_to_rule_latency_p50_p90_p99": status.get("event_to_rule_p50_p90_p99"),
        "bus_to_runtime_latency_p50_p90_p99": status.get("bus_to_runtime_p50_p90_p99"),
        "runtime_eval_latency_p50_p90_p99": status.get("runtime_eval_p50_p90_p99"),
        "bus_queue_depth": int(bus_metrics.get("queue_depth") or status.get("bus_queue_depth") or 0),
        "bus_metrics": bus_metrics,
        "monitor_path": str(config.monitor_html_path),
        "threshold_status": "baseline-label-mode" if "fdv_efficiency_threshold_unfrozen" in (status.get("warnings") or []) else "frozen",
        "paper_only": True,
        "live_trading_enabled": False,
        "no_real_trade_flag": True,
        "collector_result": collector_result or {},
        "warnings": status.get("warnings") or [],
    }


def _write_live_bus_smoke_reports(config: RuleRuntimeConfig, summary: dict[str, Any]) -> None:
    _write_json(config.live_bus_smoke_summary_json_path, summary)
    _write_json(config.variant_smoke_summary_json_path, summary)
    config.live_bus_smoke_summary_md_path.write_text(_live_bus_smoke_summary_md(summary), encoding="utf-8")
    config.variant_smoke_summary_md_path.write_text(_live_bus_smoke_summary_md(summary), encoding="utf-8")
    config.status_md_path.parent.mkdir(parents=True, exist_ok=True)
    config.status_md_path.write_text(_status_md(summary), encoding="utf-8")


def _helius_transaction_subscribe_bonding_curve_probe_summary(
    config: RuleRuntimeConfig,
    status: dict[str, Any],
    *,
    capability_audit: dict[str, Any],
    create_events_decoded: int,
    transaction_subscribe_used: bool,
    fallback_summary: dict[str, Any],
    bus_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    txsub = status.get("helius_transaction_subscribe_first_fdv") or {}
    queue = status.get("first_fdv_queue") or {}
    return {
        "report_id": "helius_transaction_subscribe_bonding_curve_probe_summary",
        "runtime_label": RUNTIME_LABEL,
        "updated_at": _utc_now(),
        "transactionSubscribe_supported": bool(txsub.get("transactionSubscribe_supported")),
        "transactionSubscribe_used": bool(transaction_subscribe_used),
        "endpoint_used": txsub.get("endpoint_used"),
        "decoded_create_events": int(create_events_decoded),
        "events_processed": int(status.get("events_processed") or 0),
        "accepted_births": int(create_events_decoded) if transaction_subscribe_used else int((fallback_summary.get("collector_result") or {}).get("official_accepted_births") or 0),
        "bonding_curve_probes_started": int(txsub.get("curve_account_probes_started") or 0),
        "probes_started_during_stream": int(txsub.get("probes_started_during_stream") or 0),
        "bonding_curve_probes_succeeded": int(txsub.get("curve_account_probes_succeeded") or 0),
        "bonding_curve_probes_failed": int(txsub.get("curve_account_probes_failed") or 0),
        "first_attempt_successes": int(txsub.get("first_attempt_successes") or 0),
        "account_not_found_retries": int(txsub.get("account_not_found_retries") or 0),
        "account_not_found_recovered_by_retry": int(txsub.get("account_not_found_recovered_by_retry") or 0),
        "account_not_found_final_failures": int(txsub.get("account_not_found_final_failures") or 0),
        "account_not_found_retry_recovery_rate": txsub.get("account_not_found_retry_recovery_rate"),
        "first_fdv_source_mix": (status.get("first_fdv_probe_sources") or {}).get("source_mix") or {},
        "observed_to_probe_started_p50_p90_p99": txsub.get("observed_to_probe_started_p50_p90_p99"),
        "probe_started_to_first_curve_state_p50_p90_p99": txsub.get("probe_started_to_first_curve_state_p50_p90_p99"),
        "observed_to_first_fdv_p50_p90_p99": txsub.get("observed_to_first_fdv_p50_p90_p99"),
        "observed_to_first_fdv_account_state_p50_p90_p99": txsub.get("observed_to_first_fdv_account_state_p50_p90_p99"),
        "first_path_latency_p50_p90_p99": queue.get("first_path_latency_p50_p90_p99"),
        "first_fdv_queue_total": queue.get("queue_depth_total"),
        "tier_1_depth": queue.get("tier_1_depth"),
        "confirmed_10k_watches": int(status.get("confirmed_10k_watches") or 0),
        "confirmed_20k_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "confirmed_20k_entry_candidates": int(status.get("confirmed_20k_entry_candidates") or 0),
        "paper_buys": int(status.get("paper_buys") or 0),
        "paper_sells": int(status.get("paper_sells") or 0),
        "rejected_spikes": int(status.get("rejected_spike_candidates") or 0),
        "rejected_same_timestamp_jumps": int(status.get("rejected_same_timestamp_jumps") or 0),
        "rejected_fdv_anomalies": int(status.get("rejected_fdv_anomalies") or 0),
        "http_429": int(queue.get("http_429_count") or 0),
        "helius_calls_or_credits": queue.get("helius_rpc_request_count"),
        "accountSubscribe_implemented": False,
        "accountSubscribe_status": txsub.get("accountSubscribe_bonding_curve_status"),
        "getAccountInfo_probe_implemented": True,
        "getAccountInfo_p50_p90_p99": txsub.get("getAccountInfo_p50_p90_p99"),
        "accountSubscribe_p50_p90_p99": txsub.get("accountSubscribe_p50_p90_p99"),
        "capability_audit": capability_audit,
        "fallback_summary": fallback_summary,
        "bus_metrics": bus_metrics or {},
        "monitor_path": str(config.monitor_html_path),
        "paper_only": True,
        "live_trading_enabled": False,
        "no_new_paid_source": True,
        "warnings": txsub.get("warnings") or [],
        "helius_transaction_subscribe_first_fdv": txsub,
        "first_fdv_queue": queue,
        "first_fdv_probe_sources": status.get("first_fdv_probe_sources") or {},
        "variants": status.get("variants") or {},
        "threshold_status": "baseline-label-mode" if "fdv_efficiency_threshold_unfrozen" in (status.get("warnings") or []) else "frozen",
    }


def _write_helius_transaction_subscribe_bonding_curve_probe_reports(config: RuleRuntimeConfig, summary: dict[str, Any]) -> None:
    _write_json(config.helius_transaction_subscribe_bonding_curve_probe_summary_json_path, summary)
    config.helius_transaction_subscribe_bonding_curve_probe_summary_md_path.write_text(
        _helius_transaction_subscribe_bonding_curve_probe_summary_md(summary),
        encoding="utf-8",
    )
    config.status_md_path.parent.mkdir(parents=True, exist_ok=True)
    config.status_md_path.write_text(_status_md(summary), encoding="utf-8")


def _helius_transaction_subscribe_bonding_curve_probe_summary_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Helius transactionSubscribe Bonding-Curve Probe Summary",
            "",
            f"- Updated: `{summary['updated_at']}`",
            f"- transactionSubscribe supported: `{summary['transactionSubscribe_supported']}`",
            f"- transactionSubscribe used: `{summary['transactionSubscribe_used']}`",
            f"- Endpoint used: `{summary.get('endpoint_used')}`",
            f"- Decoded create events: `{summary['decoded_create_events']}`",
            f"- Accepted births: `{summary['accepted_births']}`",
            f"- Bonding curve probes started/during-stream/succeeded/failed: `{summary['bonding_curve_probes_started']}` / `{summary['probes_started_during_stream']}` / `{summary['bonding_curve_probes_succeeded']}` / `{summary['bonding_curve_probes_failed']}`",
            f"- First-attempt successes: `{summary['first_attempt_successes']}`",
            f"- Account-not-found retries: `{summary['account_not_found_retries']}`",
            f"- Account-not-found recovered by retry: `{summary['account_not_found_recovered_by_retry']}`",
            f"- Account-not-found final failures: `{summary['account_not_found_final_failures']}`",
            f"- Account-not-found retry recovery rate: `{summary['account_not_found_retry_recovery_rate']}`",
            f"- First FDV source mix: `{summary['first_fdv_source_mix']}`",
            f"- Observed to probe started p50/p90/p99: `{summary['observed_to_probe_started_p50_p90_p99']}`",
            f"- Probe started to first curve state p50/p90/p99: `{summary['probe_started_to_first_curve_state_p50_p90_p99']}`",
            f"- Observed to first FDV p50/p90/p99: `{summary['observed_to_first_fdv_p50_p90_p99']}`",
            f"- Observed to account-state FDV p50/p90/p99: `{summary['observed_to_first_fdv_account_state_p50_p90_p99']}`",
            f"- First path latency p50/p90/p99: `{summary['first_path_latency_p50_p90_p99']}`",
            f"- Queue total / Tier 1 depth: `{summary['first_fdv_queue_total']}` / `{summary['tier_1_depth']}`",
            f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
            f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys/sells: `{summary['paper_buys']}` / `{summary['paper_sells']}`",
            f"- Rejections spike/jump/anomaly: `{summary['rejected_spikes']}` / `{summary['rejected_same_timestamp_jumps']}` / `{summary['rejected_fdv_anomalies']}`",
            f"- HTTP 429: `{summary['http_429']}`",
            f"- accountSubscribe implemented: `{summary['accountSubscribe_implemented']}`",
            f"- getAccountInfo probe implemented: `{summary['getAccountInfo_probe_implemented']}`",
            f"- Monitor path: `{summary['monitor_path']}`",
            f"- Warnings: `{summary['warnings']}`",
            "",
            "Paper-only. Live trading, private keys, transaction building, swaps, and routing remain disabled.",
        ]
    ) + "\n"


def _live_bus_smoke_summary_md(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Rule Runtime v1 Live Bus Smoke Summary",
            "",
            f"- Updated: `{summary['updated_at']}`",
            f"- Runtime mode: `{summary['runtime_mode']}`",
            f"- Events processed: `{summary['events_processed']}`",
            f"- Live bus events: `{summary['live_bus_events']}`",
            f"- File adapter events: `{summary['file_adapter_events']}`",
            f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
            f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
            f"- Paper buys: `{summary['paper_buys']}`",
            f"- Paper sells: `{summary['paper_sells']}`",
            f"- Variant A buys/sells: `{summary.get('variant_a_paper_buys')}` / `{summary.get('variant_a_paper_sells')}`",
            f"- Variant B buys/sells/not-evaluable: `{summary.get('variant_b_paper_buys')}` / `{summary.get('variant_b_paper_sells')}` / `{summary.get('variant_b_not_evaluable')}`",
            f"- Variant C buys/sells/not-evaluable: `{summary.get('variant_c_paper_buys')}` / `{summary.get('variant_c_paper_sells')}` / `{summary.get('variant_c_not_evaluable')}`",
            f"- Rejected spikes: `{summary['rejected_spikes']}`",
            f"- Rejected same-timestamp jumps: `{summary['rejected_same_timestamp_jumps']}`",
            f"- Rejected FDV anomalies: `{summary['rejected_fdv_anomalies']}`",
            f"- Event-to-rule p50/p90/p99: `{summary['event_to_rule_latency_p50_p90_p99']}`",
            f"- Bus-to-runtime p50/p90/p99: `{summary['bus_to_runtime_latency_p50_p90_p99']}`",
            f"- Runtime eval p50/p90/p99: `{summary['runtime_eval_latency_p50_p90_p99']}`",
            f"- Bus queue depth: `{summary['bus_queue_depth']}`",
            f"- First-FDV probe sources: `{summary.get('first_fdv_probe_sources')}`",
            f"- Threshold status: `{summary['threshold_status']}`",
            f"- Monitor path: `{summary['monitor_path']}`",
            "",
            "Paper-only. Live trading, private keys, transaction building, swaps, and routing remain disabled.",
        ]
    ) + "\n"


def _status_md(summary: dict[str, Any]) -> str:
    lines = [
        "# RULE_RUNTIME_V1_STATUS",
        "",
        f"- Runtime label: `{RUNTIME_LABEL}`",
        f"- Frozen buy rule: `{FROZEN_BUY_RULE_ID}`",
        f"- Frozen exit rule: `{FROZEN_EXIT_RULE_ID}`",
        f"- Paper-only: `{summary['paper_only']}`",
        f"- Live trading enabled: `{summary['live_trading_enabled']}`",
        f"- Events processed: `{summary['events_processed']}`",
        f"- Confirmed 10k watches: `{summary['confirmed_10k_watches']}`",
        f"- Confirmed 20k candidates: `{summary['confirmed_20k_candidates']}`",
        f"- Paper buys: `{summary['paper_buys']}`",
        f"- Paper sells: `{summary['paper_sells']}`",
        f"- Threshold status: `{summary['threshold_status']}`",
        f"- Monitor: `{summary['monitor_path']}`",
    ]
    variants = summary.get("variants") or {}
    if variants:
        lines.extend(["", "## Rule Runtime v1 Variants"])
        for variant_id, row in variants.items():
            lines.append(
                f"- `{variant_id}`: buys `{row.get('paper_buys')}`, sells `{row.get('paper_sells')}`, open `{row.get('open_positions')}`, rejected `{row.get('rejected')}`, not_evaluable `{row.get('not_evaluable')}`, missing_fields `{row.get('missing_fields')}`"
            )
    queue = summary.get("first_fdv_queue") or {}
    if queue:
        lines.extend(
            [
                "",
                "## First FDV Queue",
                f"- Scheduler mode: `{queue.get('scheduler_mode')}`",
                f"- Queue depth total: `{queue.get('queue_depth_total')}`",
                f"- Queue depth by tier: `{queue.get('queue_depth_by_tier')}`",
                f"- Tier 1 depth: `{queue.get('tier_1_depth')}`",
                f"- Tier 1 oldest age: `{queue.get('tier_1_oldest_age_seconds')}`",
                f"- Tier 1 p50/p90 age: `{queue.get('tier_1_age_p50_p90')}`",
                f"- Tier 1 processed count: `{queue.get('tier_1_processed_count')}`",
                f"- Tier 1 archive count: `{queue.get('tier_1_archive_count')}`",
                f"- Tier 1 promotion count: `{queue.get('tier_1_promotion_count')}`",
                f"- Tier 1 retry count: `{queue.get('tier_1_retry_count')}`",
                f"- Tier 1 pressure mode: `{queue.get('tier_1_pressure_mode')}`",
                f"- Archived no activity: `{queue.get('archived_no_activity')}`",
                f"- Archived no FDV path timeout: `{queue.get('archived_no_fdv_path_timeout')}`",
                f"- Promoted to FDV path: `{queue.get('promoted_to_fdv_path')}`",
                f"- Promoted to near-threshold: `{queue.get('promoted_to_near_threshold')}`",
                f"- Promoted to confirmed 10k: `{queue.get('promoted_to_confirmed_10k')}`",
                f"- Promoted to paper position: `{queue.get('promoted_to_paper_position')}`",
                f"- First path success rate: `{queue.get('first_path_success_rate')}`",
                f"- First-FDV success rate: `{queue.get('first_fdv_success_rate')}`",
                f"- First-FDV timeout rate: `{queue.get('first_fdv_timeout_rate')}`",
                f"- First-FDV median latency: `{queue.get('first_fdv_median_latency_ms')}`",
                f"- First path latency p50/p90/p99: `{queue.get('first_path_latency_p50_p90_p99')}`",
            ]
        )
    sources = summary.get("first_fdv_probe_sources") or {}
    if sources:
        lines.extend(
            [
                "",
                "## First-FDV Probe Sources",
                f"- Bonding curve account-state successes: `{sources.get('bonding_curve_account_state_successes')}`",
                f"- Bonding curve account-state failures: `{sources.get('bonding_curve_account_state_failures')}`",
                f"- Transaction delta successes: `{sources.get('transaction_delta_successes')}`",
                f"- Confirmed path-state successes: `{sources.get('confirmed_path_state_successes')}`",
                f"- Unknown successes: `{sources.get('unknown_successes')}`",
                f"- Source mix: `{sources.get('source_mix')}`",
                f"- getAccountInfo p50/p90/p99: `{sources.get('getAccountInfo_p50_p90_p99')}`",
                f"- Decode p50/p90/p99: `{sources.get('decode_p50_p90_p99')}`",
                f"- Observed to account-state FDV p50/p90/p99: `{sources.get('observed_to_first_fdv_account_state_p50_p90_p99')}`",
                f"- accountSubscribe status: `{sources.get('accountSubscribe_bonding_curve_status')}`",
                f"- Active account subscriptions: `{sources.get('active_account_subscriptions')}`",
            ]
        )
    txsub = summary.get("helius_transaction_subscribe_first_fdv") or {}
    if txsub:
        lines.extend(
            [
                "",
                "## Helius transactionSubscribe First-FDV",
                f"- transactionSubscribe supported: `{txsub.get('transactionSubscribe_supported')}`",
                f"- endpoint used: `{txsub.get('endpoint_used')}`",
                f"- create events decoded: `{txsub.get('create_events_decoded')}`",
                f"- curve PDA verified: `{txsub.get('curve_pda_verified')}`",
                f"- curve account probes started: `{txsub.get('curve_account_probes_started')}`",
                f"- probes started during stream: `{txsub.get('probes_started_during_stream')}`",
                f"- curve account probes succeeded: `{txsub.get('curve_account_probes_succeeded')}`",
                f"- curve account probes failed: `{txsub.get('curve_account_probes_failed')}`",
                f"- first-attempt successes: `{txsub.get('first_attempt_successes')}`",
                f"- account-not-found retries: `{txsub.get('account_not_found_retries')}`",
                f"- account-not-found recovered by retry: `{txsub.get('account_not_found_recovered_by_retry')}`",
                f"- account-not-found final failures: `{txsub.get('account_not_found_final_failures')}`",
                f"- account-not-found retry recovery rate: `{txsub.get('account_not_found_retry_recovery_rate')}`",
                f"- first FDV from bonding curve account-state: `{txsub.get('first_fdv_from_bonding_curve_account_state')}`",
                f"- first FDV from transaction delta: `{txsub.get('first_fdv_from_transaction_delta')}`",
                f"- first FDV from unknown: `{txsub.get('first_fdv_from_unknown')}`",
                f"- observed to probe started p50/p90/p99: `{txsub.get('observed_to_probe_started_p50_p90_p99')}`",
                f"- probe started to first curve state p50/p90/p99: `{txsub.get('probe_started_to_first_curve_state_p50_p90_p99')}`",
                f"- observed to first FDV p50/p90/p99: `{txsub.get('observed_to_first_fdv_p50_p90_p99')}`",
                f"- getAccountInfo p50/p90/p99: `{txsub.get('getAccountInfo_p50_p90_p99')}`",
                f"- accountSubscribe p50/p90/p99: `{txsub.get('accountSubscribe_p50_p90_p99')}`",
                f"- warnings: `{txsub.get('warnings')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def _update_runtime_bus_depth(config: RuleRuntimeConfig, depth: int) -> None:
    state = _load_state(config)
    stats = state.setdefault("runtime_stats", {})
    stats["bus_queue_depth"] = int(depth)
    _write_json(config.runtime_state_path, state)


def _bonding_curve_probe_stats_from_rows(config: RuleRuntimeConfig) -> dict[str, Any]:
    rows = _read_jsonl(config.bonding_curve_account_probe_events_path)
    failures_by_reason: dict[str, int] = {}
    for row in rows:
        if row.get("probe_status") == "success":
            continue
        reason = str(row.get("probe_error") or "unknown")
        failures_by_reason[reason] = int(failures_by_reason.get(reason) or 0) + 1
    return {
        "successes": sum(1 for row in rows if row.get("probe_status") == "success"),
        "failures": sum(1 for row in rows if row.get("probe_status") != "success"),
        "failures_by_reason": dict(sorted(failures_by_reason.items())),
        "requests_used": int(sum(_num(row.get("helius_rpc_request_count")) or 0 for row in rows)),
        "http_429_count": int(sum(_num(row.get("http_429_count")) or 0 for row in rows)),
    }


def _record_bonding_curve_probe_stats(config: RuleRuntimeConfig, probe_stats: dict[str, Any]) -> None:
    state = _load_state(config)
    stats = _scheduler_stats(state)
    failures = int(probe_stats.get("failures") or 0)
    stats["bonding_curve_account_state_failures"] = failures
    stats["bonding_curve_account_state_failure_reasons"] = probe_stats.get("failures_by_reason") or {}
    requests_used = probe_stats.get("requests_used")
    if requests_used is not None:
        current = _num(stats.get("helius_rpc_request_count")) or 0
        stats["helius_rpc_request_count"] = int(max(current, int(requests_used or 0)))
    stats["http_429_count"] = int(stats.get("http_429_count") or 0) + int(probe_stats.get("http_429_count") or 0)
    _write_json(config.runtime_state_path, state)


def _transaction_subscribe_runtime_ws_url(
    recommended: dict[str, Any],
    *,
    resolve_helius_api_key: Any,
    resolve_helius_ws_url: Any,
) -> str:
    if recommended.get("name") == "helius_beta":
        api_key = resolve_helius_api_key(load_project_dotenv=True)
        if api_key:
            return f"wss://beta.helius-rpc.com/?api-key={api_key}"
    return resolve_helius_ws_url(load_project_dotenv=True)


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


def _row_id(row: dict[str, Any], fallback: int) -> str:
    for key in ["signature", "observation_id", "mint", "ca"]:
        value = row.get(key)
        if value:
            return str(value)
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    for key in ["signature", "observation_id", "mint", "ca"]:
        value = candidate.get(key)
        if value:
            return str(value)
    return f"row-{fallback}"


def _unique_row_ids(rows: Any) -> set[str]:
    return {_row_id(row, index) for index, row in enumerate(rows) if isinstance(row, dict)}


def _duplicate_row_count(rows: list[dict[str, Any]]) -> int:
    ids = [_row_id(row, index) for index, row in enumerate(rows)]
    return max(0, len(ids) - len(set(ids)))


def _row_has_token(row: dict[str, Any], tokens: list[str]) -> bool:
    haystack = " ".join(
        str(value).lower()
        for value in [
            row.get("hydration_status"),
            row.get("status"),
            row.get("missing_reason"),
            row.get("reason"),
            row.get("layout_status"),
            row.get("error"),
        ]
        if value is not None
    )
    return any(token in haystack for token in tokens)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


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
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    state.setdefault("variant_open_positions", {})
    state.setdefault("variant_closed_positions", {})
    state.setdefault("open_positions", {})
    state.setdefault("closed_positions", {})
    state.setdefault("candidates", {})
    state.setdefault("runtime_stats", {})
    _scheduler_stats(state)
    return state


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _bool_or_fdv(value: Any, fdv: float, threshold: float) -> bool:
    parsed = _bool_or_none(value)
    if parsed is not None:
        return parsed
    return float(fdv) >= float(threshold)


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
