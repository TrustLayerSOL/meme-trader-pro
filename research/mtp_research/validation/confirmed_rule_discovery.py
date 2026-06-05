"""Confirmed-only rule-discovery diagnostics for official lifecycle v2 data.

This module rebuilds buy/sell discovery inputs from confirmed FDV path
milestones only. It writes reports and disabled paper/shadow configuration; it
does not contain wallet, signing, swap, routing, or live execution logic.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_root


REPORT_LABEL = "confirmed_rule_discovery"
CONFIRMATION_WINDOW_SECONDS = 120.0
CONFIRMATION_MIN_ROWS = 2
FDV_ANOMALY_HIGH = 100_000_000.0
LEVELS: dict[str, float] = {
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
MAJOR_JUMP_LEVELS = ["20k", "50k", "100k", "500k", "1m"]
BUY_LABELS = ["B1", "B2", "B3", "B4"]
EXIT_LABELS = ["E1", "E2", "E3", "E4"]
GUARDRAILS = [
    "no_private_keys",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_jupiter_calls",
    "no_transaction_building",
    "no_order_routing",
    "no_live_trading",
    "no_real_pnl_claims",
    "no_profitability_claims",
    "no_threshold_optimization",
    "no_grid_search",
    "no_final_validation",
]


@dataclass(frozen=True)
class ConfirmedRuleLayers:
    milestone_rows: list[dict[str, Any]]
    actionability_rows: list[dict[str, Any]]
    rule_label_rows: list[dict[str, Any]]
    exit_label_rows: list[dict[str, Any]]


def build_confirmed_rule_discovery(
    *,
    data_root: Path | str | None = None,
    source_roots: list[Path | str] | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    report_root = root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / REPORT_LABEL
    config_path = root / "data" / "forward_observation" / "official_lifecycle_watch_v2" / "paper_shadow_starting_config.json"
    status_path = Path("theses") / "CONFIRMED_RULE_DISCOVERY_STATUS.md"
    requested_sources = [Path(path).expanduser() for path in source_roots] if source_roots else discover_source_roots(root)
    if not execute:
        return {
            "execute": False,
            "report_root": str(report_root),
            "source_roots": [str(path) for path in requested_sources],
            "readiness": "confirmed_rule_discovery_ready_for_execute",
        }

    report_root.mkdir(parents=True, exist_ok=True)
    all_milestones: list[dict[str, Any]] = []
    all_actionability: list[dict[str, Any]] = []
    all_rule_labels: list[dict[str, Any]] = []
    all_exit_labels: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    for source in requested_sources:
        births = _read_jsonl(source / "births.jsonl")
        paths = _read_jsonl(source / "followup_paths.jsonl")
        state = _read_json(source / "lifecycle_state.json")
        sample_family = _sample_family(source)
        layers = build_confirmed_rule_layers(
            source_root=source,
            births=births,
            paths=paths,
            lifecycle_state=state,
            sample_family=sample_family,
            collector_semantics="official_lifecycle_watch_v2" if sample_family.startswith("v2") else "legacy_or_v1",
        )
        all_milestones.extend(layers.milestone_rows)
        all_actionability.extend(layers.actionability_rows)
        all_rule_labels.extend(layers.rule_label_rows)
        all_exit_labels.extend(layers.exit_label_rows)
        source_summaries.append(_source_summary(source, sample_family, births, paths, layers))

    active_actionability = [row for row in all_actionability if _active_v2(row)]
    active_milestones = [row for row in all_milestones if _active_v2(row)]
    active_labels = [row for row in all_rule_labels if _active_v2(row)]
    active_exits = [row for row in all_exit_labels if _active_v2(row)]
    baseline_stats = build_confirmed_baseline_stats(all_milestones, all_actionability)
    baseline_vs_filter = build_baseline_vs_filter_rows(active_actionability, active_labels, active_exits)
    contaminated = build_contaminated_raw_manifest(source_summaries)
    config = build_paper_shadow_config()
    recommendation = build_recommendation(active_actionability, active_labels)
    summary = build_summary(
        source_summaries=source_summaries,
        active_milestones=active_milestones,
        active_actionability=active_actionability,
        active_labels=active_labels,
        active_exits=active_exits,
        baseline_stats=baseline_stats,
        recommendation=recommendation,
        report_root=report_root,
        config_path=config_path,
        status_path=status_path,
    )

    _write_json(report_root / "contaminated_raw_rule_discovery_manifest.json", contaminated)
    (report_root / "contaminated_raw_rule_discovery_manifest.md").write_text(_contaminated_markdown(contaminated), encoding="utf-8")
    _write_jsonl(report_root / "confirmed_milestone_layer.jsonl", all_milestones)
    _write_jsonl(report_root / "confirmed_actionability_layer.jsonl", all_actionability)
    _write_csv(report_root / "confirmed_baseline_stats.csv", baseline_stats)
    _write_csv(report_root / "confirmed_rule_labels.csv", active_labels)
    _write_csv(report_root / "confirmed_exit_labels.csv", active_exits)
    _write_csv(report_root / "confirmed_baseline_vs_filter_audit.csv", baseline_vs_filter)
    _write_parquet(report_root / "confirmed_milestone_layer.parquet", all_milestones)
    _write_parquet(report_root / "confirmed_actionability_layer.parquet", all_actionability)
    _write_json(report_root / "confirmed_rule_discovery_summary.json", summary)
    (report_root / "confirmed_rule_discovery_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config_path, config)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(summary), encoding="utf-8")
    return summary


def build_confirmed_rule_layers(
    *,
    source_root: Path | str,
    births: list[dict[str, Any]],
    paths: list[dict[str, Any]],
    lifecycle_state: dict[str, Any],
    sample_family: str,
    collector_semantics: str,
) -> ConfirmedRuleLayers:
    source = Path(source_root).expanduser()
    birth_by_mint = {str(row.get("mint")): row for row in births if row.get("mint")}
    paths_by_mint = _paths_by_mint(paths)
    mints = sorted(set(birth_by_mint) | set(paths_by_mint))
    milestone_rows: list[dict[str, Any]] = []
    actionability_rows: list[dict[str, Any]] = []
    rule_label_rows: list[dict[str, Any]] = []
    exit_label_rows: list[dict[str, Any]] = []
    for mint in mints:
        birth = birth_by_mint.get(mint, {})
        mint_paths = paths_by_mint.get(mint, [])
        milestone = build_mint_milestone_row(
            mint=mint,
            source_root=source,
            sample_family=sample_family,
            collector_semantics=collector_semantics,
            paths=mint_paths,
        )
        actionability = build_actionability_row(
            mint=mint,
            source_root=source,
            sample_family=sample_family,
            collector_semantics=collector_semantics,
            birth=birth,
            milestone=milestone,
            lifecycle_state=_state_for_mint(lifecycle_state, mint),
        )
        milestone_rows.append(milestone)
        actionability_rows.append(actionability)
        if actionability["confirmed_actionable_crossed_20k"] is True and sample_family.startswith("v2"):
            label = build_rule_label_row(actionability, milestone, mint_paths)
            rule_label_rows.append(label)
            exit_label_rows.append(build_exit_label_row(label, mint_paths))
    return ConfirmedRuleLayers(milestone_rows, actionability_rows, rule_label_rows, exit_label_rows)


def build_mint_milestone_row(
    *,
    mint: str,
    source_root: Path,
    sample_family: str,
    collector_semantics: str,
    paths: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(paths, key=lambda row: (_num(row.get("timestamp")) is None, _num(row.get("timestamp")) or 0.0))
    row: dict[str, Any] = {
        "mint": mint,
        "sample_family": sample_family,
        "collector_semantics": collector_semantics,
        "source_root": str(source_root),
        "source_file": str(source_root / "followup_paths.jsonl"),
        "path_row_count": len(paths),
        "max_fdv_observed": _max([path.get("fdv_proxy") for path in ordered]),
        "fdv_anomaly_flag": any(_fdv_anomaly(path.get("fdv_proxy")) for path in ordered),
    }
    raw_first_by_level: dict[str, dict[str, Any] | None] = {}
    for level, threshold in LEVELS.items():
        raw_first = _first_raw_cross_row(ordered, level, threshold)
        confirmed = _first_confirmed_cross(ordered, threshold)
        spike = _single_row_spike_flag(ordered, threshold, confirmed)
        raw_first_by_level[level] = raw_first
        row[f"raw_crossed_{level}"] = raw_first is not None
        row[f"confirmed_crossed_{level}"] = confirmed is not None
        row[f"raw_first_crossed_{level}_time"] = _num(raw_first.get("timestamp")) if raw_first else None
        row[f"confirmed_first_crossed_{level}_time"] = _num(confirmed["row"].get("timestamp")) if confirmed else None
        row[f"raw_first_crossed_{level}_fdv"] = _num(raw_first.get("fdv_proxy")) if raw_first else None
        row[f"confirmed_first_crossed_{level}_fdv"] = _num(confirmed["row"].get("fdv_proxy")) if confirmed else None
        row[f"confirmation_method_{level}"] = "two_fdv_rows_within_120s" if confirmed else "unconfirmed"
        row[f"confirmation_row_count_{level}"] = len(confirmed["rows"]) if confirmed else 0
        row[f"confirmation_window_seconds_{level}"] = CONFIRMATION_WINDOW_SECONDS
        row[f"single_row_spike_flag_{level}"] = spike
        row[f"milestone_provenance_{level}"] = "fdv_path_rows"
    row["same_timestamp_jump_flag"] = _same_timestamp_major_jump(raw_first_by_level)
    for level in LEVELS:
        row[f"same_timestamp_jump_flag_{level}"] = row["same_timestamp_jump_flag"]
    return row


def build_actionability_row(
    *,
    mint: str,
    source_root: Path,
    sample_family: str,
    collector_semantics: str,
    birth: dict[str, Any],
    milestone: dict[str, Any],
    lifecycle_state: str | None,
) -> dict[str, Any]:
    official_accepted = birth.get("official_accepted_birth") is not False
    first_before_10k = _first_path_before_level(birth, "10k")
    first_before_15k = _first_path_before_level(birth, "15k")
    first_before_20k = _first_path_before_level(birth, "20k")
    valid_provenance = birth.get("valid_fdv_path_provenance", True) is not False
    valid_ordering = _valid_milestone_ordering(milestone)
    has_spike = milestone.get("single_row_spike_flag_20k") is True
    has_same_jump = milestone.get("same_timestamp_jump_flag") is True
    has_anomaly = milestone.get("fdv_anomaly_flag") is True
    confirmed_20k = milestone.get("confirmed_crossed_20k") is True
    failure = "passed"
    if not sample_family.startswith("v2"):
        failure = "legacy_context_only"
    elif not official_accepted:
        failure = "not_official_accepted_birth"
    elif not confirmed_20k:
        failure = "single_row_spike" if has_spike else "not_confirmed_crossed_20k"
    elif not first_before_20k:
        failure = "first_path_not_before_20k"
    elif not valid_provenance:
        failure = "invalid_fdv_path_provenance"
    elif has_anomaly:
        failure = "fdv_anomaly"
    elif not valid_ordering:
        failure = "invalid_milestone_ordering"
    elif has_same_jump:
        failure = "same_timestamp_major_jump"
    actionable = failure == "passed"
    return {
        "mint": mint,
        "sample_family": sample_family,
        "collector_semantics": collector_semantics,
        "source_root": str(source_root),
        "official_accepted_birth": official_accepted,
        "first_path_before_10k": first_before_10k,
        "first_path_before_15k": first_before_15k,
        "first_path_before_20k": first_before_20k,
        "valid_fdv_path_provenance": valid_provenance,
        "valid_milestone_ordering": valid_ordering,
        "has_spike_anomaly": has_spike,
        "has_same_timestamp_major_jump": has_same_jump,
        "has_fdv_anomaly": has_anomaly,
        "confirmed_crossed_20k": confirmed_20k,
        "confirmed_actionable_crossed_20k": actionable,
        "actionability_failure_reason": failure,
        "lifecycle_state": lifecycle_state,
        "raw_crossed_20k": milestone.get("raw_crossed_20k") is True,
        "raw_crossed_1m": milestone.get("raw_crossed_1m") is True,
        "confirmed_crossed_1m": milestone.get("confirmed_crossed_1m") is True,
    }


def build_rule_label_row(actionability: dict[str, Any], milestone: dict[str, Any], paths: list[dict[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "mint": actionability["mint"],
        "sample_family": actionability["sample_family"],
        "collector_semantics": actionability["collector_semantics"],
        "source_root": actionability["source_root"],
        "baseline_confirmed_actionable_20k": True,
        "confirmed_actionable_crossed_20k": True,
    }
    for level in LEVELS:
        row[f"confirmed_crossed_{level}"] = milestone.get(f"confirmed_crossed_{level}") is True
        row[f"confirmed_first_crossed_{level}_time"] = milestone.get(f"confirmed_first_crossed_{level}_time")
        row[f"confirmed_first_crossed_{level}_fdv"] = milestone.get(f"confirmed_first_crossed_{level}_fdv")
    row["B1_confirmed_pass"] = bool(actionability.get("first_path_before_10k") and milestone.get("confirmed_crossed_10k") and (_num(milestone.get("confirmed_first_crossed_10k_fdv")) or math.inf) <= 15_000)
    row["B2_confirmed_pass"] = bool(actionability.get("first_path_before_15k") and milestone.get("confirmed_crossed_15k") and (_num(milestone.get("confirmed_first_crossed_15k_fdv")) or math.inf) <= 20_000)
    row["B3_confirmed_pass"] = bool(actionability.get("first_path_before_20k") and milestone.get("confirmed_crossed_20k") and (_num(milestone.get("confirmed_first_crossed_20k_fdv")) or math.inf) <= 30_000)
    row["B4_confirmed_pass"] = bool(row["B3_confirmed_pass"] and (milestone.get("confirmed_crossed_30k") or _confirmed_continuation_within(paths, "20k", "30k", 300)))
    for label in BUY_LABELS:
        row[f"{label}_failure_reason"] = "passed" if row[f"{label}_confirmed_pass"] else "confirmed_label_conditions_not_met"
    return row


def build_exit_label_row(label: dict[str, Any], paths: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed_rows = _confirmed_fdv_rows(paths)
    entry_ts = _num(label.get("confirmed_first_crossed_20k_time"))
    after_entry = [row for row in confirmed_rows if entry_ts is not None and (_num(row.get("timestamp")) or 0.0) >= entry_ts]
    entry_fdv = _num(label.get("confirmed_first_crossed_20k_fdv"))
    max_fdv = _max([row.get("fdv_proxy") for row in after_entry])
    e2_exit = _first_e2_exit(after_entry)
    return {
        "mint": label["mint"],
        "sample_family": label["sample_family"],
        "collector_semantics": label["collector_semantics"],
        "source_root": label["source_root"],
        "entry_universe": "baseline_confirmed_actionable_20k",
        "entry_time": entry_ts,
        "entry_fdv": entry_fdv,
        "clean_max_fdv_after_entry": max_fdv,
        "max_confirmed_fdv_multiple_after_entry": (max_fdv / entry_fdv) if max_fdv and entry_fdv else None,
        "confirmed_reached_50k_after_entry": bool(max_fdv is not None and max_fdv >= LEVELS["50k"]),
        "confirmed_reached_100k_after_entry": bool(max_fdv is not None and max_fdv >= LEVELS["100k"]),
        "confirmed_reached_500k_after_entry": bool(max_fdv is not None and max_fdv >= LEVELS["500k"]),
        "confirmed_reached_1m_after_entry": bool(max_fdv is not None and max_fdv >= LEVELS["1m"]),
        "E1_confirmed_exit_label": False,
        "E2_confirmed_exit_label": e2_exit is not None,
        "E3_confirmed_exit_label": False,
        "E4_confirmed_exit_label": False,
        "E2_exit_time": _num(e2_exit.get("timestamp")) if e2_exit else None,
        "E2_exit_fdv": _num(e2_exit.get("fdv_proxy")) if e2_exit else None,
        "E2_exit_reason": "E2_confirmed_milestone_trailing_drawdown" if e2_exit else "open_or_incomplete",
        "open_incomplete": e2_exit is None,
        "exit_event_rows": 1 if e2_exit else 0,
    }


def build_confirmed_baseline_stats(milestones: list[dict[str, Any]], actionability: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    families = sorted({row["sample_family"] for row in milestones})
    action_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in actionability:
        action_by_family[row["sample_family"]].append(row)
    for family in families:
        fam_milestones = [row for row in milestones if row["sample_family"] == family]
        fam_actions = action_by_family[family]
        out: dict[str, Any] = {
            "sample_family": family,
            "basis": "active_rule_basis" if family.startswith("v2") else "supporting_context_only",
            "mint_count": len(fam_milestones),
            "confirmed_actionable_crossed_20k": sum(1 for row in fam_actions if row.get("confirmed_actionable_crossed_20k") is True),
            "spike_suspect_count": sum(1 for row in fam_actions if row.get("has_spike_anomaly") is True),
            "same_timestamp_major_jump_count": sum(1 for row in fam_actions if row.get("has_same_timestamp_major_jump") is True),
        }
        for level in ["20k", "50k", "100k", "500k", "1m"]:
            raw_count = sum(1 for row in fam_milestones if row.get(f"raw_crossed_{level}") is True)
            confirmed_count = sum(1 for row in fam_milestones if row.get(f"confirmed_crossed_{level}") is True)
            out[f"raw_crossed_{level}"] = raw_count
            out[f"confirmed_crossed_{level}"] = confirmed_count
            out[f"raw_to_confirmed_dropoff_{level}"] = raw_count - confirmed_count
        rows.append(out)
    return rows


def build_baseline_vs_filter_rows(actionability: list[dict[str, Any]], labels: list[dict[str, Any]], exits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label_by_mint = {row["mint"]: row for row in labels}
    exit_by_mint = {row["mint"]: row for row in exits}
    populations = ["baseline_confirmed_actionable_20k", "B1_confirmed_pass", "B2_confirmed_pass", "B3_confirmed_pass", "B4_confirmed_pass"]
    out: list[dict[str, Any]] = []
    for population in populations:
        if population == "baseline_confirmed_actionable_20k":
            selected = [row for row in actionability if row.get("confirmed_actionable_crossed_20k") is True]
        else:
            selected = [row for row in actionability if label_by_mint.get(row["mint"], {}).get(population) is True]
        selected_exits = [exit_by_mint[row["mint"]] for row in selected if row["mint"] in exit_by_mint]
        multiples = [_num(row.get("max_confirmed_fdv_multiple_after_entry")) for row in selected_exits]
        out.append(
            {
                "population": population,
                "support_count": len(selected),
                "reached_confirmed_50k": sum(1 for row in selected_exits if row.get("confirmed_reached_50k_after_entry") is True),
                "reached_confirmed_100k": sum(1 for row in selected_exits if row.get("confirmed_reached_100k_after_entry") is True),
                "reached_confirmed_500k": sum(1 for row in selected_exits if row.get("confirmed_reached_500k_after_entry") is True),
                "reached_confirmed_1m": sum(1 for row in selected_exits if row.get("confirmed_reached_1m_after_entry") is True),
                "clean_milestone_sequence_count": sum(1 for row in selected if row.get("valid_milestone_ordering") is True and row.get("has_same_timestamp_major_jump") is False),
                "same_timestamp_jump_excluded_count": sum(1 for row in selected if row.get("has_same_timestamp_major_jump") is True),
                "median_max_confirmed_fdv_multiple_after_entry": _median(multiples),
                "open_incomplete_count": sum(1 for row in selected_exits if row.get("open_incomplete") is True),
                "data_limited_count": sum(1 for row in selected if row.get("lifecycle_state") in {None, "trigger_qualified_active_watch"}),
                "E2_unique_mints_with_exit": sum(1 for row in selected_exits if row.get("E2_confirmed_exit_label") is True),
                "E2_exit_event_rows": sum(int(row.get("exit_event_rows") or 0) for row in selected_exits),
            }
        )
    return out


def build_contaminated_raw_manifest(source_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "created_at": _utc_now(),
        "status": "previous_raw_rule_discovery_contaminated",
        "hunter_false_entry_explanation": "Hunter-style false entry came from a single internal FDV proxy row around 36k; confirmed milestone logic rejects that because nearby rows did not confirm a real 20k crossing.",
        "raw_vs_confirmed_milestone_issue": "raw crossed milestones can be created by one FDV proxy row; confirmed rule discovery requires at least two FDV path rows at or above the milestone within 120 seconds and excludes same-timestamp major jumps from clean progression evidence.",
        "affected_artifacts": [
            "raw crossed counts",
            "raw B-label counts",
            "raw buy/exit combo what-if reports",
            "raw paper entries",
        ],
        "still_useful_for": [
            "collector debugging",
            "broad feature discovery",
            "candidate rule shapes",
        ],
        "prohibited_uses": [
            "final rule selection",
            "live trading",
            "profitability claims",
            "confirmed paper entry logic",
        ],
        "source_summaries": source_summaries,
    }


def build_paper_shadow_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "use_confirmed_milestones_only": True,
        "raw_milestones_allowed_for_entry": False,
        "raw_milestones_allowed_for_exit": False,
        "single_row_spikes_allowed": False,
        "same_timestamp_major_jump_allowed_for_entry": False,
        "entry_universe": "baseline_confirmed_actionable_20k",
        "filter_labels": ["B1_confirmed_pass", "B2_confirmed_pass", "B3_confirmed_pass", "B4_confirmed_pass"],
        "primary_exit_label": "E2_confirmed",
        "paper_entries_enabled": False,
        "paper_exits_enabled": False,
        "live_trading_enabled": False,
        "private_keys_allowed": False,
        "wallet_execution_enabled": False,
        "transaction_signing_enabled": False,
        "swaps_enabled": False,
        "order_routing_enabled": False,
        "created_at": _utc_now(),
    }


def build_recommendation(actionability: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    support = sum(1 for row in actionability if row.get("confirmed_actionable_crossed_20k") is True)
    if support < 30:
        decision = "B_keep_paper_shadow_disabled_until_more_confirmed_actionable_rows_accumulate"
    else:
        decision = "A_enable_paper_shadow_logging_on_baseline_confirmed_actionable_20k_after_user_approval"
    return {
        "decision": decision,
        "support_count": support,
        "B1_confirmed_pass": sum(1 for row in labels if row.get("B1_confirmed_pass") is True),
        "B2_confirmed_pass": sum(1 for row in labels if row.get("B2_confirmed_pass") is True),
        "B3_confirmed_pass": sum(1 for row in labels if row.get("B3_confirmed_pass") is True),
        "B4_confirmed_pass": sum(1 for row in labels if row.get("B4_confirmed_pass") is True),
        "live_trading_recommendation": "disabled",
        "profitability_claim": "none",
    }


def build_summary(
    *,
    source_summaries: list[dict[str, Any]],
    active_milestones: list[dict[str, Any]],
    active_actionability: list[dict[str, Any]],
    active_labels: list[dict[str, Any]],
    active_exits: list[dict[str, Any]],
    baseline_stats: list[dict[str, Any]],
    recommendation: dict[str, Any],
    report_root: Path,
    config_path: Path,
    status_path: Path,
) -> dict[str, Any]:
    raw_20k = sum(1 for row in active_milestones if row.get("raw_crossed_20k") is True)
    confirmed_20k = sum(1 for row in active_milestones if row.get("confirmed_crossed_20k") is True)
    actionable = sum(1 for row in active_actionability if row.get("confirmed_actionable_crossed_20k") is True)
    return {
        "execute": True,
        "created_at": _utc_now(),
        "source_summaries": source_summaries,
        "raw_crossed_20k_count": raw_20k,
        "confirmed_crossed_20k_count": confirmed_20k,
        "confirmed_actionable_crossed_20k_count": actionable,
        "raw_to_confirmed_20k_dropoff": raw_20k - confirmed_20k,
        "raw_crossed_50k_count": sum(1 for row in active_milestones if row.get("raw_crossed_50k") is True),
        "confirmed_crossed_50k_count": sum(1 for row in active_milestones if row.get("confirmed_crossed_50k") is True),
        "raw_crossed_100k_count": sum(1 for row in active_milestones if row.get("raw_crossed_100k") is True),
        "confirmed_crossed_100k_count": sum(1 for row in active_milestones if row.get("confirmed_crossed_100k") is True),
        "raw_crossed_500k_count": sum(1 for row in active_milestones if row.get("raw_crossed_500k") is True),
        "confirmed_crossed_500k_count": sum(1 for row in active_milestones if row.get("confirmed_crossed_500k") is True),
        "raw_crossed_1m_count": sum(1 for row in active_milestones if row.get("raw_crossed_1m") is True),
        "confirmed_crossed_1m_count": sum(1 for row in active_milestones if row.get("confirmed_crossed_1m") is True),
        "spike_suspect_count": sum(1 for row in active_actionability if row.get("has_spike_anomaly") is True),
        "same_timestamp_major_jump_count": sum(1 for row in active_actionability if row.get("has_same_timestamp_major_jump") is True),
        "B1_confirmed_pass_count": recommendation["B1_confirmed_pass"],
        "B2_confirmed_pass_count": recommendation["B2_confirmed_pass"],
        "B3_confirmed_pass_count": recommendation["B3_confirmed_pass"],
        "B4_confirmed_pass_count": recommendation["B4_confirmed_pass"],
        "E2_confirmed_exit_count": sum(1 for row in active_exits if row.get("E2_confirmed_exit_label") is True),
        "E2_confirmed_open_incomplete_count": sum(1 for row in active_exits if row.get("open_incomplete") is True),
        "recommendation": recommendation,
        "guardrails": GUARDRAILS,
        "paper_config_path": str(config_path),
        "report_root": str(report_root),
        "status_file": str(status_path),
        "report_paths": {
            "contaminated_manifest_json": str(report_root / "contaminated_raw_rule_discovery_manifest.json"),
            "contaminated_manifest_md": str(report_root / "contaminated_raw_rule_discovery_manifest.md"),
            "confirmed_milestone_layer_parquet": str(report_root / "confirmed_milestone_layer.parquet"),
            "confirmed_milestone_layer_jsonl": str(report_root / "confirmed_milestone_layer.jsonl"),
            "confirmed_actionability_layer_parquet": str(report_root / "confirmed_actionability_layer.parquet"),
            "confirmed_actionability_layer_jsonl": str(report_root / "confirmed_actionability_layer.jsonl"),
            "confirmed_baseline_stats_csv": str(report_root / "confirmed_baseline_stats.csv"),
            "confirmed_rule_labels_csv": str(report_root / "confirmed_rule_labels.csv"),
            "confirmed_exit_labels_csv": str(report_root / "confirmed_exit_labels.csv"),
            "confirmed_baseline_vs_filter_audit_csv": str(report_root / "confirmed_baseline_vs_filter_audit.csv"),
            "summary_json": str(report_root / "confirmed_rule_discovery_summary.json"),
            "summary_md": str(report_root / "confirmed_rule_discovery_summary.md"),
        },
        "baseline_stats": baseline_stats,
    }


def discover_source_roots(root: Path) -> list[Path]:
    candidates: list[Path] = []
    current = root / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    if (current / "births.jsonl").exists() and (current / "followup_paths.jsonl").exists():
        candidates.append(current)
    quarantine_root = root / "data" / "forward_observation" / "quarantined"
    if quarantine_root.exists():
        for path in sorted(quarantine_root.rglob("official_lifecycle_watch_v2")):
            if (path / "births.jsonl").exists() and (path / "followup_paths.jsonl").exists():
                candidates.append(path)
        for path in sorted(quarantine_root.rglob("official_lifecycle_watch_v1")):
            if (path / "births.jsonl").exists() and (path / "followup_paths.jsonl").exists():
                candidates.append(path)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def _sample_family(source: Path) -> str:
    parts = {part.lower() for part in source.parts}
    if source.name == "official_lifecycle_watch_v2":
        return "v2_current"
    if "official_lifecycle_watch_v2" in parts:
        return "v2_current"
    return "legacy_v1_supporting_context"


def _source_summary(source: Path, sample_family: str, births: list[dict[str, Any]], paths: list[dict[str, Any]], layers: ConfirmedRuleLayers) -> dict[str, Any]:
    return {
        "source_root": str(source),
        "sample_family": sample_family,
        "birth_rows": len(births),
        "path_rows": len(paths),
        "mint_rows": len(layers.milestone_rows),
        "raw_crossed_20k": sum(1 for row in layers.milestone_rows if row.get("raw_crossed_20k") is True),
        "confirmed_crossed_20k": sum(1 for row in layers.milestone_rows if row.get("confirmed_crossed_20k") is True),
        "confirmed_actionable_crossed_20k": sum(1 for row in layers.actionability_rows if row.get("confirmed_actionable_crossed_20k") is True),
    }


def _active_v2(row: dict[str, Any]) -> bool:
    return str(row.get("sample_family") or "").startswith("v2")


def _first_raw_cross_row(paths: list[dict[str, Any]], level: str, threshold: float) -> dict[str, Any] | None:
    return next((row for row in paths if row.get(f"crossed_{level}") is True or (_num(row.get("fdv_proxy")) or 0.0) >= threshold), None)


def _first_confirmed_cross(paths: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    candidates = [row for row in paths if (_num(row.get("fdv_proxy")) or 0.0) >= threshold]
    for row in candidates:
        ts = _num(row.get("timestamp"))
        if ts is None:
            continue
        nearby = [other for other in candidates if _num(other.get("timestamp")) is not None and abs((_num(other.get("timestamp")) or 0.0) - ts) <= CONFIRMATION_WINDOW_SECONDS]
        if len(nearby) >= CONFIRMATION_MIN_ROWS:
            return {"row": row, "rows": nearby}
    return None


def _single_row_spike_flag(paths: list[dict[str, Any]], threshold: float, confirmed: dict[str, Any] | None) -> bool:
    if confirmed is not None:
        return False
    crossing = [row for row in paths if (_num(row.get("fdv_proxy")) or 0.0) >= threshold]
    if len(crossing) != 1:
        return False
    row = crossing[0]
    ts = _num(row.get("timestamp"))
    fdv = _num(row.get("fdv_proxy"))
    if ts is None or fdv is None:
        return True
    nearby = [
        other
        for other in paths
        if other is not row
        and _num(other.get("timestamp")) is not None
        and abs((_num(other.get("timestamp")) or 0.0) - ts) <= CONFIRMATION_WINDOW_SECONDS
        and (_num(other.get("fdv_proxy")) or 0.0) > 0
    ]
    if not nearby:
        return True
    return max((_num(other.get("fdv_proxy")) or 0.0) for other in nearby) < threshold


def _same_timestamp_major_jump(raw_first_by_level: dict[str, dict[str, Any] | None]) -> bool:
    first20 = raw_first_by_level.get("20k")
    if not first20:
        return False
    first20_ts = _num(first20.get("timestamp"))
    if first20_ts is None:
        return False
    for level in ["50k", "100k", "500k", "1m"]:
        row = raw_first_by_level.get(level)
        if row and _num(row.get("timestamp")) == first20_ts:
            return True
    return False


def _valid_milestone_ordering(milestone: dict[str, Any]) -> bool:
    previous = None
    for level in LEVELS:
        ts = _num(milestone.get(f"confirmed_first_crossed_{level}_time"))
        if ts is None:
            continue
        if previous is not None and ts < previous:
            return False
        previous = ts
    return True


def _first_path_before_level(birth: dict[str, Any], level: str) -> bool:
    first_fdv = _num(birth.get("first_fdv_path_fdv"))
    if first_fdv is not None:
        return first_fdv <= LEVELS[level]
    if birth.get(f"fdv_path_before_{level}") is True:
        return True
    if level == "15k" and birth.get("fdv_path_before_20k") is True:
        return True
    return birth.get(f"first_followup_before_{level}") is True


def _confirmed_continuation_within(paths: list[dict[str, Any]], start_level: str, target_level: str, seconds: float) -> bool:
    start = _first_confirmed_cross(paths, LEVELS[start_level])
    target = _first_confirmed_cross(paths, LEVELS[target_level])
    if not start or not target:
        return False
    return (_num(target["row"].get("timestamp")) or math.inf) - (_num(start["row"].get("timestamp")) or 0.0) <= seconds


def _confirmed_fdv_rows(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted([row for row in paths if (_num(row.get("fdv_proxy")) or 0.0) > 0], key=lambda row: _num(row.get("timestamp")) or 0.0)
    confirmed: list[dict[str, Any]] = []
    for row in rows:
        fdv = _num(row.get("fdv_proxy"))
        ts = _num(row.get("timestamp"))
        if fdv is None or ts is None:
            continue
        peers = [
            other
            for other in rows
            if other is not row
            and _num(other.get("timestamp")) is not None
            and abs((_num(other.get("timestamp")) or 0.0) - ts) <= CONFIRMATION_WINDOW_SECONDS
            and (_num(other.get("fdv_proxy")) or 0.0) >= fdv / 3.0
            and (_num(other.get("fdv_proxy")) or 0.0) <= fdv * 3.0
        ]
        if peers:
            confirmed.append(row)
    return confirmed


def _first_e2_exit(paths: list[dict[str, Any]]) -> dict[str, Any] | None:
    local_high = 0.0
    local_high_time = None
    for row in paths:
        fdv = _num(row.get("fdv_proxy"))
        ts = _num(row.get("timestamp"))
        if fdv is None or ts is None:
            continue
        if fdv >= local_high:
            local_high = fdv
            local_high_time = ts
            continue
        if local_high <= 0 or local_high_time is None:
            continue
        drawdown = (local_high - fdv) / local_high
        threshold = 0.50 if local_high < LEVELS["50k"] else 0.40
        if drawdown >= threshold:
            return row
    return None


def _state_for_mint(state: dict[str, Any], mint: str) -> str | None:
    mints = state.get("mints") if isinstance(state, dict) else {}
    row = mints.get(mint, {}) if isinstance(mints, dict) else {}
    return row.get("state") if isinstance(row, dict) else None


def _paths_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("mint"):
            grouped[str(row["mint"])].append(row)
    return grouped


def _fdv_anomaly(value: Any) -> bool:
    parsed = _num(value)
    return parsed is not None and (parsed <= 0 or parsed > FDV_ANOMALY_HIGH)


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _max(values: list[Any]) -> float | None:
    clean = [_num(value) for value in values if _num(value) is not None]
    return max(clean) if clean else None


def _median(values: list[Any]) -> float | None:
    clean = [_num(value) for value in values if _num(value) is not None]
    return median(clean) if clean else None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contaminated_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Contaminated Raw Rule Discovery Manifest",
            "",
            manifest["hunter_false_entry_explanation"],
            "",
            f"Status: `{manifest['status']}`",
            f"Raw issue: {manifest['raw_vs_confirmed_milestone_issue']}",
            f"Affected artifacts: `{manifest['affected_artifacts']}`",
            f"Still useful for: `{manifest['still_useful_for']}`",
            f"Prohibited uses: `{manifest['prohibited_uses']}`",
            "",
        ]
    )


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Confirmed Rule Discovery Summary",
            "",
            f"Raw crossed 20k: `{summary['raw_crossed_20k_count']}`",
            f"Confirmed crossed 20k: `{summary['confirmed_crossed_20k_count']}`",
            f"Confirmed actionable crossed 20k: `{summary['confirmed_actionable_crossed_20k_count']}`",
            f"B1/B2/B3/B4 confirmed pass counts: `{summary['B1_confirmed_pass_count']}/{summary['B2_confirmed_pass_count']}/{summary['B3_confirmed_pass_count']}/{summary['B4_confirmed_pass_count']}`",
            f"E2 confirmed exits: `{summary['E2_confirmed_exit_count']}`",
            f"Recommendation: `{summary['recommendation']['decision']}`",
            "",
            "No live trading, private-key work, wallet execution, transaction signing, swaps, or order routing was added.",
            "",
        ]
    )


def _status_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Confirmed Rule Discovery Status",
            "",
            "This rerun was required because raw FDV proxy rows can create false milestone crossings, including the Hunter-style false paper entry.",
            f"Confirmed milestone definition: at least `{CONFIRMATION_MIN_ROWS}` FDV path rows at or above a milestone within `{CONFIRMATION_WINDOW_SECONDS}` seconds; single-row spikes and same-timestamp major jumps are not clean entry evidence.",
            f"V2 raw crossed 20k: `{summary['raw_crossed_20k_count']}`",
            f"V2 confirmed crossed 20k: `{summary['confirmed_crossed_20k_count']}`",
            f"V2 confirmed actionable crossed 20k: `{summary['confirmed_actionable_crossed_20k_count']}`",
            f"B1/B2/B3/B4 confirmed support: `{summary['B1_confirmed_pass_count']}/{summary['B2_confirmed_pass_count']}/{summary['B3_confirmed_pass_count']}/{summary['B4_confirmed_pass_count']}`",
            f"E2 confirmed exits: `{summary['E2_confirmed_exit_count']}`; open/incomplete: `{summary['E2_confirmed_open_incomplete_count']}`",
            f"Recommendation: `{summary['recommendation']['decision']}`",
            f"Paper config status: disabled confirmed-only config written to `{summary['paper_config_path']}`",
            "Live trading remains disabled. No private-key logic, transaction building, wallet execution, swaps, or order routing is present in this diagnostic layer.",
            f"Report root: `{summary['report_root']}`",
            "",
        ]
    )
