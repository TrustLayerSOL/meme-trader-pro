"""Diagnostic strategy preview for a partial forward lifecycle sample.

This module is retrospective analysis and disabled paper/shadow scaffolding
only. It does not submit orders, sign transactions, route swaps, run
validation, or claim profitability.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_root


SAMPLE_LABEL = "partial_birth_coverage_long_lifecycle_sample"
OFFICIAL_SAMPLE = "official_lifecycle_watch_v1"
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
APPROVED_USES = [
    "tentative_entry_logic_design",
    "tentative_exit_logic_design",
    "path_drawdown_reclaim_analysis",
    "paper_shadow_scaffold_design",
    "field_coverage_audit",
    "collector_improvement_guidance",
]
PROHIBITED_USES = [
    "live_trading",
    "final_signal_claims",
    "final_validation",
    "profitability_claims",
    "birth_to_trigger_conversion_estimates",
    "production_strategy_deployment",
]


@dataclass(frozen=True)
class PartialPreviewPaths:
    source_root: Path
    observation_root: Path
    report_root: Path


def run_partial_forward_strategy_preview(
    *,
    data_root: Path | str | None = None,
    source_root: Path | str | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    paths = PartialPreviewPaths(
        source_root=_resolve_source_root(root, Path(source_root).expanduser() if source_root else None),
        observation_root=root / "data" / "forward_observation" / OFFICIAL_SAMPLE,
        report_root=root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / OFFICIAL_SAMPLE,
    )
    if not execute:
        return {
            "execute": False,
            "sample_label": SAMPLE_LABEL,
            "source_root": str(paths.source_root),
            "report_root": str(paths.report_root),
            "readiness": "partial_strategy_preview_ready_for_execute",
        }

    paths.report_root.mkdir(parents=True, exist_ok=True)
    rows = _load_sample(paths.source_root)
    analysis_rows = build_analysis_dataset(rows)
    manifest = build_sample_manifest(rows, analysis_rows, paths.source_root)
    quality = build_quality_audit(rows, analysis_rows, manifest)
    entry_preview = build_entry_feature_preview(analysis_rows)
    exit_preview = build_exit_path_preview(analysis_rows)
    buy_rules = build_tentative_buy_rules(entry_preview)
    exit_rules = build_tentative_exit_rules(exit_preview)

    written = _write_outputs(paths, manifest, quality, analysis_rows, entry_preview, exit_preview, buy_rules, exit_rules)
    status_path = write_partial_preview_status(paths.report_root, manifest, quality, buy_rules, exit_rules)
    summary = {
        "execute": True,
        "sample_label": SAMPLE_LABEL,
        "source_root": str(paths.source_root),
        "rows_mints_analyzed": len(analysis_rows),
        "quality_warnings": quality["warning_flags"],
        "tentative_buy_candidates": [row["rule_id"] for row in buy_rules],
        "tentative_exit_candidates": [row["exit_rule_id"] for row in exit_rules],
        "paper_shadow_scaffold_status": "paper_shadow_scaffold_ready_disabled",
        "readiness": "data_limited" if quality["severe_data_issue_count"] else "partial_strategy_preview_ready",
        "output_paths": {key: str(value) for key, value in written.items()},
        "status_file": str(status_path),
    }
    _write_json(paths.report_root / "partial_forward_strategy_preview_summary.json", summary)
    (paths.report_root / "partial_forward_strategy_preview_summary.md").write_text(
        _summary_markdown(summary, manifest, quality, buy_rules, exit_rules),
        encoding="utf-8",
    )
    return summary


def build_analysis_dataset(rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    births_by_mint = {row.get("mint"): row for row in rows["births"] if row.get("mint")}
    paths_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    events_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_by_mint = {row.get("mint"): row for row in rows["metadata"] if row.get("mint")}
    drawdowns_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows["paths"]:
        if row.get("mint"):
            paths_by_mint[row["mint"]].append(row)
    for row in rows["events"]:
        if row.get("mint"):
            events_by_mint[row["mint"]].append(row)
    for row in rows["drawdowns"]:
        if row.get("mint"):
            drawdowns_by_mint[row["mint"]].append(row)

    state_mints = rows["state"].get("mints", {}) if isinstance(rows["state"], dict) else {}
    all_mints = sorted(set(births_by_mint) | set(paths_by_mint) | set(events_by_mint) | set(state_mints))
    output: list[dict[str, Any]] = []
    for mint in all_mints:
        birth = births_by_mint.get(mint, {})
        state = state_mints.get(mint, {})
        mint_paths = sorted(paths_by_mint.get(mint, []), key=lambda row: _num(row.get("timestamp")) or 0)
        mint_events = events_by_mint.get(mint, [])
        meta = metadata_by_mint.get(mint, {})
        path_times = [_num(row.get("timestamp")) for row in mint_paths if _num(row.get("timestamp")) is not None]
        fdvs = [_num(row.get("fdv_proxy")) for row in mint_paths if _num(row.get("fdv_proxy")) is not None]
        create_time = _num(birth.get("create_time") or state.get("create_time"))
        first_followup = _num(birth.get("first_followup_attempt_time") or state.get("first_followup_attempt_time"))
        max_fdv = max(fdvs) if fdvs else None
        peak_row = _max_fdv_row(mint_paths)
        row: dict[str, Any] = {
            "mint": mint,
            "creator": birth.get("creator") or state.get("creator"),
            "source": birth.get("source_provenance") or state.get("source_provenance"),
            "create_time": create_time,
            "first_seen_time": _num(birth.get("observed_time") or birth.get("observed_at")),
            "first_followup_time": first_followup,
            "sample_label": SAMPLE_LABEL,
            "lifecycle_state": state.get("state"),
            "maturity_state": state.get("state") if str(state.get("state") or "").startswith("matured_") else None,
            "create_to_first_followup_seconds": _num(birth.get("create_to_first_followup_seconds")),
            "first_path_before_10k": birth.get("first_followup_before_10k"),
            "first_path_before_20k": birth.get("first_followup_before_20k"),
            "freshness_class": birth.get("freshness_class"),
            "path_row_count": len(mint_paths),
            "event_row_count": len(mint_events),
            "path_duration_seconds": (max(path_times) - min(path_times)) if path_times else None,
            "max_fdv_observed": max_fdv,
            "time_to_peak": _delta(create_time, _num(peak_row.get("timestamp")) if peak_row else None),
            "max_drawdown_after_20k": _max_drawdown_after(mint_paths, threshold=20_000),
            "terminal_collapse_proxy": state.get("state") == "matured_terminal_collapse",
            "inactive_timeout_proxy": state.get("state") == "matured_inactive_timeout",
            "matured_reached_1m": state.get("state") == "matured_reached_1m",
            "token_name": meta.get("token_name"),
            "token_symbol": meta.get("token_symbol"),
            "metadata_completeness_score": _metadata_score(meta),
            "social_link_count": _social_link_count(meta),
            "liquidity_proxy": _last_non_null(mint_paths, "liquidity_proxy"),
            "holder_count": _last_non_null(mint_paths, "holder_count"),
            "top_holder_share_proxy": _last_non_null(mint_paths, "top_holder_share_proxy"),
            "creator_net_flow_proxy": _last_non_null(mint_paths, "creator_net_flow_proxy"),
            "synthetic_activity_proxy": _last_non_null(mint_paths, "synthetic_activity_proxy"),
        }
        for level, threshold in TARGET_LEVELS.items():
            crossed_row = _first_cross_row(mint_paths, threshold)
            row[f"crossed_{level}"] = crossed_row is not None
            row[f"first_crossed_{level}_time"] = _num(crossed_row.get("timestamp")) if crossed_row else None
        row["create_to_10k_seconds"] = _delta(create_time, row["first_crossed_10k_time"])
        row["create_to_20k_seconds"] = _delta(create_time, row["first_crossed_20k_time"])
        row["10k_to_20k_seconds"] = _delta(row["first_crossed_10k_time"], row["first_crossed_20k_time"])
        for level in ["10k", "20k"]:
            threshold = TARGET_LEVELS[level]
            crossed_row = _first_cross_row(mint_paths, threshold)
            for field, source in {
                f"fdv_per_event_at_{level}": "fdv_per_event",
                f"fdv_per_buy_at_{level}": "fdv_per_buy",
                f"fdv_per_active_wallet_at_{level}": "fdv_per_active_wallet",
                f"event_count_at_{level}": "event_count",
                f"buy_count_at_{level}": "buy_count",
                f"sell_count_at_{level}": "sell_count",
                f"active_wallets_at_{level}": "active_wallet_count",
                f"buy_sell_ratio_at_{level}": "buy_sell_ratio",
            }.items():
                row[field] = _num(crossed_row.get(source)) if crossed_row else None
        row.update(_drawdown_features(mint_paths, drawdowns_by_mint.get(mint, [])))
        output.append(row)
    return output


def build_sample_manifest(rows: dict[str, list[dict[str, Any]]], analysis_rows: list[dict[str, Any]], source_root: Path) -> dict[str, Any]:
    path_counts = [row.get("path_row_count") or 0 for row in analysis_rows]
    path_durations = [_num(row.get("path_duration_seconds")) for row in analysis_rows if _num(row.get("path_duration_seconds")) is not None]
    state_counts = Counter(row.get("lifecycle_state") or "unknown" for row in analysis_rows)
    return {
        "sample_label": SAMPLE_LABEL,
        "source_root": str(source_root),
        "known_collection_bug_warning": "partial_birth_coverage_not_valid_for_birth_universe_conversion_rates",
        "approved_uses": APPROVED_USES,
        "prohibited_uses": PROHIBITED_USES,
        "birth_rows": len(rows["births"]),
        "births_observed": len({row.get("mint") for row in rows["births"] if row.get("mint")}),
        "unique_mints": len({row["mint"] for row in analysis_rows if row.get("mint")}),
        "mints_with_path_rows": sum(1 for row in analysis_rows if (row.get("path_row_count") or 0) > 0),
        "mints_with_events": sum(1 for row in analysis_rows if (row.get("event_row_count") or 0) > 0),
        "mints_with_metadata": len({row.get("mint") for row in rows["metadata"] if row.get("mint")}),
        "crossed_counts": {level: sum(1 for row in analysis_rows if row.get(f"crossed_{level}") is True) for level in TARGET_LEVELS},
        "state_counts": dict(state_counts),
        "path_row_count": len(rows["paths"]),
        "event_row_count": len(rows["events"]),
        "metadata_row_count": len(rows["metadata"]),
        "median_path_duration_seconds": median(path_durations) if path_durations else None,
        "median_path_rows_per_mint": median(path_counts) if path_counts else 0,
        "missing_fields": _missing_field_summary(analysis_rows),
    }


def build_quality_audit(rows: dict[str, list[dict[str, Any]]], analysis_rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    warnings = ["known_partial_birth_coverage_collection_bug"]
    duplicate_mints = _duplicates([row.get("mint") for row in rows["births"] if row.get("mint")])
    duplicate_observation_ids = _duplicates([row.get("observation_id") for row in rows["births"] if row.get("observation_id")])
    if duplicate_mints:
        warnings.append("duplicate_mint_birth_rows")
    if duplicate_observation_ids:
        warnings.append("duplicate_observation_ids")
    if any(row.get("create_time") is None for row in analysis_rows):
        warnings.append("missing_birth_create_time")
    if any(row.get("first_followup_time") is None for row in analysis_rows):
        warnings.append("missing_first_followup_time")
    if any(_milestone_order_bad(row) for row in analysis_rows):
        warnings.append("milestone_ordering_violation")
    if any((_num(row.get("max_fdv_observed")) or 0) <= 0 for row in analysis_rows if (row.get("path_row_count") or 0) > 0):
        warnings.append("fdv_zero_or_negative")
    crossed = manifest["crossed_counts"]
    if crossed.get("20k", 0) and crossed.get("1m", 0) / crossed["20k"] > 0.20:
        warnings.append("unusually_high_20k_to_1m_ratio_partial_sample")
    first_before_10 = sum(1 for row in analysis_rows if row.get("first_path_before_10k") is True)
    first_before_20 = sum(1 for row in analysis_rows if row.get("first_path_before_20k") is True)
    return {
        "sample_label": SAMPLE_LABEL,
        "source_root": manifest["source_root"],
        "warning_flags": sorted(set(warnings)),
        "severe_data_issue_count": sum(1 for warning in warnings if warning not in {"known_partial_birth_coverage_collection_bug"}),
        "duplicate_mints": duplicate_mints,
        "duplicate_observation_ids": duplicate_observation_ids,
        "milestone_provenance": "observed_path_rows_only",
        "first_path_before_10k_count": first_before_10,
        "first_path_before_20k_count": first_before_20,
        "status_tally_vs_file_counts": "not_comparable_for_quarantined_partial_sample",
        "source_adapter_bias": "Pump.fun WebSocket/RPC hydration only; known missed-birth period",
        "hydration_lag": _hydration_lag_summary(analysis_rows),
        "path_density": {
            "min": min((row.get("path_row_count") or 0 for row in analysis_rows), default=0),
            "median": median([row.get("path_row_count") or 0 for row in analysis_rows]) if analysis_rows else 0,
            "max": max((row.get("path_row_count") or 0 for row in analysis_rows), default=0),
        },
        "strategy_design_status": "data_limited" if len(analysis_rows) < 50 else "tentative_only",
    }


def build_entry_feature_preview(analysis_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = [
        "fdv_per_event_at_10k",
        "fdv_per_buy_at_10k",
        "fdv_per_active_wallet_at_10k",
        "fdv_per_event_at_20k",
        "fdv_per_buy_at_20k",
        "fdv_per_active_wallet_at_20k",
        "create_to_10k_seconds",
        "create_to_20k_seconds",
        "10k_to_20k_seconds",
        "buy_count_at_10k",
        "sell_count_at_10k",
        "event_count_at_10k",
        "active_wallets_at_10k",
        "buy_count_at_20k",
        "sell_count_at_20k",
        "event_count_at_20k",
        "active_wallets_at_20k",
        "buy_sell_ratio_at_10k",
        "buy_sell_ratio_at_20k",
        "metadata_completeness_score",
        "social_link_count",
        "holder_count",
        "top_holder_share_proxy",
        "creator_net_flow_proxy",
        "synthetic_activity_proxy",
    ]
    out = []
    for feature in features:
        values_by_group: dict[str, list[float]] = defaultdict(list)
        all_values = []
        for row in analysis_rows:
            value = _num(row.get(feature))
            if value is None or math.isnan(value):
                continue
            group = _outcome_group(row)
            values_by_group[group].append(value)
            all_values.append(value)
        medians = {group: median(values) for group, values in sorted(values_by_group.items()) if values}
        classification = _feature_classification(feature, medians, len(all_values))
        out.append(
            {
                "feature": feature,
                "coverage": len(all_values),
                "missing": len(analysis_rows) - len(all_values),
                "coverage_pct": round(100 * len(all_values) / len(analysis_rows), 3) if analysis_rows else 0,
                "median_by_outcome_group": json.dumps(medians, sort_keys=True),
                "iqr": json.dumps(_iqr(all_values), sort_keys=True),
                "direction": _direction(medians),
                "effect_proxy": _effect_proxy(medians),
                "classification": classification,
                "official_clean_sample_must_confirm": True,
            }
        )
    return out


def build_exit_path_preview(analysis_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    crossed = [row for row in analysis_rows if row.get("crossed_20k")]
    groups = {
        "reached_100k_plus": [row for row in crossed if row.get("crossed_100k")],
        "reached_500k_plus": [row for row in crossed if row.get("crossed_500k")],
        "reached_1m": [row for row in crossed if row.get("crossed_1m")],
        "terminal_or_stall": [
            row for row in crossed if row.get("terminal_collapse_proxy") or (not row.get("crossed_50k"))
        ],
    }
    features = [
        "max_fdv_observed",
        "time_to_peak",
        "max_drawdown_after_20k",
        "no_reclaim_after_5m",
        "no_reclaim_after_10m",
        "terminal_collapse_proxy",
        "inactive_timeout_proxy",
    ]
    out = []
    for feature in features:
        row = {
            "feature": feature,
            "crossed_20k_count": len(crossed),
            "data_limited": len(crossed) < 30,
            "classification": "data_limited" if len(crossed) < 30 else "path_exit_candidate",
            "official_clean_sample_must_confirm": True,
        }
        for group, group_rows in groups.items():
            values = [_num(item.get(feature)) for item in group_rows if _num(item.get(feature)) is not None]
            row[f"{group}_count"] = len(group_rows)
            row[f"{group}_median"] = median(values) if values else None
        out.append(row)
    return out


def build_tentative_buy_rules(entry_preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": "PBCL_ENTRY_10K_EFFICIENCY_HIGH_BUCKET",
            "name": "10k efficiency high-bucket shadow entry design",
            "entry_trigger_level": "10k",
            "required_freshness": "birth_observed_and_first_path_before_10k_max_delay_5s_preferred",
            "fdv_efficiency_requirement": "upper_bucket_fdv_per_event_or_active_wallet_at_10k_from_partial_sample",
            "chase_guard": "current_fdv_no_more_than_one_bucket_above_trigger_and_recent_trigger_only",
            "basic_risk_guard": "valid_observed_fdv_path_no_source_anomaly_no_missing_trigger_row",
            "reason_for_inclusion": "Tests whether capital-efficient early movement deserves future paper/shadow observation.",
            "limitations": "Derived from partial birth coverage; not validated; no threshold optimization.",
            "official_sample_confirmation_required": True,
        },
        {
            "rule_id": "PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY",
            "name": "20k confirmation efficiency shadow entry design",
            "entry_trigger_level": "20k",
            "required_freshness": "birth_observed_first_path_before_20k",
            "fdv_efficiency_requirement": "upper_bucket_fdv_per_active_wallet_at_20k_optional_fdv_per_buy",
            "chase_guard": "skip_if_far_above_20k_or_trigger_time_stale",
            "basic_risk_guard": "valid_fdv_path_no_provenance_anomaly",
            "reason_for_inclusion": "Uses stronger milestone confirmation while limiting late-chase behavior.",
            "limitations": "Small crossed-20k sample; future clean official sample must confirm.",
            "official_sample_confirmation_required": True,
        },
        {
            "rule_id": "PBCL_ENTRY_15K_SPEED_FLOW_BALANCED",
            "name": "15k speed plus flow balance shadow entry design",
            "entry_trigger_level": "15k",
            "required_freshness": "birth_observed_first_path_before_15k_or_before_20k",
            "fdv_efficiency_requirement": "non-lower-bucket_speed_and_buy_sell_balance",
            "chase_guard": "skip_large_same_timestamp_multimilestone_jumps_until_clean_sample_confirms",
            "basic_risk_guard": "valid_fdv_path_and_basic_event_coverage",
            "reason_for_inclusion": "Captures a middle trigger that may reduce missed 20k moves without using final thresholds.",
            "limitations": "Design only; no paper decision is enabled.",
            "official_sample_confirmation_required": True,
        },
    ]


def build_tentative_exit_rules(exit_preview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "exit_rule_id": "PBCL_EXIT_NO_RECLAIM_10M",
            "name": "No-reclaim after drawdown shadow exit design",
            "applies_after": "after_20k_entry",
            "exit_condition": "observed_drawdown_without_reclaim_after_10m",
            "required_path_evidence": "drawdown row plus subsequent path rows",
            "grace_period": "10m",
            "max_hold_maturity_condition": "matured_max_age_or_inactive_timeout",
            "reason_for_inclusion": "Separates dips that reclaim from stale collapses in path data.",
            "limitation": "Current no-reclaim fields are sparse/proxy-only.",
            "official_sample_confirmation_required": True,
        },
        {
            "exit_rule_id": "PBCL_EXIT_TRAILING_DRAWDOWN_WITH_GRACE",
            "name": "Milestone trailing drawdown with grace shadow exit design",
            "applies_after": "after_50k_or_100k",
            "exit_condition": "large_drawdown_from_local_high_without_reclaim_grace",
            "required_path_evidence": "local_high_fdv and drawdown_pct path evidence",
            "grace_period": "5m_to_10m",
            "max_hold_maturity_condition": "matured_reached_1m_or_inactive_timeout",
            "reason_for_inclusion": "Uses observed local-high path behavior rather than fixed profitability claims.",
            "limitation": "Design only; thresholds are non-optimized buckets.",
            "official_sample_confirmation_required": True,
        },
        {
            "exit_rule_id": "PBCL_EXIT_MAX_AGE_OR_INACTIVE",
            "name": "Inactive/max-age maturity shadow exit design",
            "applies_after": "after_20k_entry",
            "exit_condition": "inactive_timeout_or_max_age_maturity",
            "required_path_evidence": "continued active-watch lifecycle state",
            "grace_period": "collector_configured_inactive_window",
            "max_hold_maturity_condition": "max_observation_age",
            "reason_for_inclusion": "Prevents indefinite paper/shadow watches without claiming real tradability.",
            "limitation": "Depends on active-watch collector completeness.",
            "official_sample_confirmation_required": True,
        },
    ]


def _write_outputs(
    paths: PartialPreviewPaths,
    manifest: dict[str, Any],
    quality: dict[str, Any],
    analysis_rows: list[dict[str, Any]],
    entry_preview: list[dict[str, Any]],
    exit_preview: list[dict[str, Any]],
    buy_rules: list[dict[str, Any]],
    exit_rules: list[dict[str, Any]],
) -> dict[str, Path]:
    outputs = {
        "manifest_json": paths.report_root / "partial_birth_coverage_sample_manifest.json",
        "manifest_md": paths.report_root / "partial_birth_coverage_sample_manifest.md",
        "quality_json": paths.report_root / "partial_sample_quality_audit.json",
        "quality_md": paths.report_root / "partial_sample_quality_audit.md",
        "analysis_jsonl": paths.report_root / "partial_sample_analysis_dataset.jsonl",
        "analysis_parquet": paths.report_root / "partial_sample_analysis_dataset.parquet",
        "entry_csv": paths.report_root / "partial_forward_entry_feature_preview.csv",
        "exit_csv": paths.report_root / "partial_forward_exit_path_preview.csv",
        "buy_csv": paths.report_root / "tentative_buy_rule_candidates.csv",
        "exit_rules_csv": paths.report_root / "tentative_exit_rule_candidates.csv",
        "quality_csv": paths.report_root / "partial_forward_sample_quality.csv",
    }
    _write_json(outputs["manifest_json"], manifest)
    outputs["manifest_md"].write_text(_manifest_markdown(manifest), encoding="utf-8")
    _write_json(outputs["quality_json"], quality)
    outputs["quality_md"].write_text(_quality_markdown(quality), encoding="utf-8")
    _write_jsonl(outputs["analysis_jsonl"], analysis_rows)
    pd.DataFrame(analysis_rows).to_parquet(outputs["analysis_parquet"], index=False)
    _write_csv(outputs["entry_csv"], entry_preview)
    _write_csv(outputs["exit_csv"], exit_preview)
    _write_csv(outputs["buy_csv"], buy_rules)
    _write_csv(outputs["exit_rules_csv"], exit_rules)
    _write_csv(outputs["quality_csv"], [{"metric": key, "value": json.dumps(value) if isinstance(value, (dict, list)) else value} for key, value in quality.items()])
    return outputs


def write_partial_preview_status(
    report_root: Path,
    manifest: dict[str, Any],
    quality: dict[str, Any],
    buy_rules: list[dict[str, Any]],
    exit_rules: list[dict[str, Any]],
) -> Path:
    path = Path("theses") / "PARTIAL_FORWARD_STRATEGY_PREVIEW_STATUS.md"
    text = "\n".join(
        [
            "# Partial Forward Strategy Preview Status",
            "",
            f"Sample label: `{SAMPLE_LABEL}`",
            "",
            "This sample is partial because the forward collector missed a class of Pump.fun births before the parser/hydration fixes. It is usable for tentative path diagnostics only.",
            "",
            f"Births observed: `{manifest['births_observed']}`",
            f"Mints analyzed: `{manifest['unique_mints']}`",
            f"Crossed 20k: `{manifest['crossed_counts'].get('20k', 0)}`",
            f"Crossed 1M: `{manifest['crossed_counts'].get('1m', 0)}`",
            f"Quality warnings: `{quality['warning_flags']}`",
            "",
            "Approved uses: tentative entry/exit design, path analysis, field coverage audit, and disabled paper/shadow scaffold design.",
            "",
            "Prohibited uses: live trading, final validation, profitability claims, final conversion-rate estimates, and production strategy deployment.",
            "",
            "Tentative entry candidates:",
            *[f"- `{row['rule_id']}`: {row['name']}" for row in buy_rules],
            "",
            "Tentative exit candidates:",
            *[f"- `{row['exit_rule_id']}`: {row['name']}" for row in exit_rules],
            "",
            "Paper/shadow scaffold status: `paper_shadow_scaffold_ready_disabled`",
            "",
            "No live trades, paper trades, orders, swaps, alerts, or execution actions were run.",
            "",
            f"Reports: `{report_root}`",
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _load_sample(source_root: Path) -> dict[str, Any]:
    return {
        "births": _read_jsonl(source_root / "births.jsonl"),
        "paths": _read_jsonl(source_root / "followup_paths.jsonl"),
        "events": _read_jsonl(source_root / "events.jsonl"),
        "metadata": _read_jsonl(source_root / "metadata.jsonl"),
        "drawdowns": _read_jsonl(source_root / "drawdowns.jsonl"),
        "transitions": _read_jsonl(source_root / "lifecycle_transitions.jsonl"),
        "state": _read_json(source_root / "lifecycle_state.json"),
        "status": _read_json(source_root / "status.json"),
    }


def _resolve_source_root(data_root: Path, source_root: Path | None) -> Path:
    if source_root:
        return source_root
    quarantine_root = data_root / "data" / "forward_observation" / "quarantined"
    candidates = sorted(quarantine_root.glob(f"{OFFICIAL_SAMPLE}*"))
    if not candidates:
        return data_root / "data" / "forward_observation" / OFFICIAL_SAMPLE
    return max(candidates, key=lambda path: _line_count(path / "followup_paths.jsonl"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8", errors="ignore")) if path.exists() else 0


def _num(value: Any) -> float | None:
    if value is None or value is False:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(start: Any, end: Any) -> float | None:
    a = _num(start)
    b = _num(end)
    if a is None or b is None:
        return None
    return b - a


def _first_cross_row(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in sorted(rows, key=lambda item: _num(item.get("timestamp")) or 0):
        fdv = _num(row.get("fdv_proxy"))
        if fdv is not None and fdv >= threshold:
            return row
    return None


def _max_fdv_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [row for row in rows if _num(row.get("fdv_proxy")) is not None]
    return max(valid, key=lambda row: _num(row.get("fdv_proxy")) or 0) if valid else None


def _max_drawdown_after(rows: list[dict[str, Any]], *, threshold: float) -> float | None:
    crossed = _first_cross_row(rows, threshold)
    if not crossed:
        return None
    crossed_time = _num(crossed.get("timestamp")) or 0
    values = [_num(row.get("drawdown_pct")) for row in rows if (_num(row.get("timestamp")) or 0) >= crossed_time]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _drawdown_features(path_rows: list[dict[str, Any]], drawdown_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted([*path_rows, *drawdown_rows], key=lambda row: _num(row.get("timestamp")) or 0)
    out: dict[str, Any] = {}
    for pct in [20, 30, 40, 50]:
        first = next((row for row in rows if (_num(row.get("drawdown_pct")) or 0) >= pct), None)
        recovered = False
        no_reclaim_5 = None
        no_reclaim_10 = None
        if first:
            first_time = _num(first.get("timestamp")) or 0
            local_high = _num(first.get("local_high_fdv"))
            after = [row for row in rows if (_num(row.get("timestamp")) or 0) > first_time]
            recovered = any(
                row.get("reclaim_status") == "at_or_above_local_high"
                or (local_high is not None and (_num(row.get("fdv_proxy")) or 0) >= local_high)
                for row in after
            )
            no_reclaim_5 = not any((_num(row.get("timestamp")) or 0) <= first_time + 300 and row.get("reclaim_status") == "at_or_above_local_high" for row in after)
            no_reclaim_10 = not any((_num(row.get("timestamp")) or 0) <= first_time + 600 and row.get("reclaim_status") == "at_or_above_local_high" for row in after)
        out[f"first_{pct}pct_drawdown_time"] = _num(first.get("timestamp")) if first else None
        out[f"recovered_after_{pct}pct"] = recovered
        if pct == 30:
            out["no_reclaim_after_5m"] = no_reclaim_5
            out["no_reclaim_after_10m"] = no_reclaim_10
    return out


def _last_non_null(rows: list[dict[str, Any]], key: str) -> Any:
    for row in reversed(rows):
        if row.get(key) is not None:
            return row.get(key)
    return None


def _metadata_score(row: dict[str, Any]) -> float | None:
    if not row:
        return None
    keys = ["token_name", "token_symbol", "metadata_uri", "twitter", "telegram", "website"]
    return sum(1 for key in keys if row.get(key)) / len(keys)


def _social_link_count(row: dict[str, Any]) -> int | None:
    if not row:
        return None
    return sum(1 for key in ["twitter", "telegram", "website", "discord"] if row.get(key))


def _missing_field_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    fields = ["creator", "create_time", "first_followup_time", "token_name", "token_symbol", "holder_count", "top_holder_share_proxy"]
    return {field: sum(1 for row in rows if row.get(field) is None) for field in fields}


def _duplicates(values: list[Any]) -> list[Any]:
    counts = Counter(values)
    return sorted([value for value, count in counts.items() if count > 1])


def _milestone_order_bad(row: dict[str, Any]) -> bool:
    times = [row.get(f"first_crossed_{level}_time") for level in ["10k", "20k", "50k", "100k", "500k", "1m"]]
    nums = [_num(value) for value in times if _num(value) is not None]
    return nums != sorted(nums)


def _hydration_lag_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_num(row.get("create_to_first_followup_seconds")) for row in rows if _num(row.get("create_to_first_followup_seconds")) is not None]
    return {
        "count": len(values),
        "median": median(values) if values else None,
        "max": max(values) if values else None,
        "under_5s": sum(1 for value in values if value <= 5),
    }


def _outcome_group(row: dict[str, Any]) -> str:
    if row.get("crossed_1m"):
        return "crossed_1m"
    if row.get("crossed_500k"):
        return "crossed_500k_not_1m"
    if row.get("crossed_100k"):
        return "crossed_100k_not_500k"
    if row.get("crossed_50k"):
        return "crossed_50k_not_100k"
    if row.get("crossed_20k"):
        return "crossed_20k_not_50k"
    if row.get("crossed_10k"):
        return "crossed_10k_not_20k"
    return "below_10k_or_no_path"


def _feature_classification(feature: str, medians: dict[str, float], coverage: int) -> str:
    if coverage < 10 or len(medians) < 2:
        return "data_limited"
    if feature.startswith("max_drawdown") or "sell_count" in feature:
        return "tentative_risk_filter_candidate"
    if "drawdown" in feature or "reclaim" in feature:
        return "path_exit_candidate"
    spread = _effect_proxy(medians)
    if spread is not None and spread > 0:
        return "tentative_entry_candidate"
    return "no_clear_difference"


def _direction(medians: dict[str, float]) -> str:
    if not medians:
        return "unknown"
    best_group = max(medians, key=medians.get)
    if best_group in {"crossed_1m", "crossed_500k_not_1m", "crossed_100k_not_500k"}:
        return "higher_in_stronger_movers"
    return "mixed_or_lower_in_stronger_movers"


def _effect_proxy(medians: dict[str, float]) -> float | None:
    if len(medians) < 2:
        return None
    vals = list(medians.values())
    return round(max(vals) - min(vals), 6)


def _iqr(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"q1": None, "q3": None}
    sorted_values = sorted(values)
    return {
        "q1": sorted_values[int((len(sorted_values) - 1) * 0.25)],
        "q3": sorted_values[int((len(sorted_values) - 1) * 0.75)],
    }


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Partial Birth Coverage Sample Manifest",
            "",
            f"- Sample label: `{manifest['sample_label']}`",
            f"- Source root: `{manifest['source_root']}`",
            f"- Births observed: `{manifest['births_observed']}`",
            f"- Unique mints: `{manifest['unique_mints']}`",
            f"- Mints with path rows: `{manifest['mints_with_path_rows']}`",
            f"- Path rows: `{manifest['path_row_count']}`",
            f"- Crossed counts: `{manifest['crossed_counts']}`",
            f"- Known warning: `{manifest['known_collection_bug_warning']}`",
        ]
    ) + "\n"


def _quality_markdown(quality: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Partial Sample Quality Audit",
            "",
            f"- Sample label: `{quality['sample_label']}`",
            f"- Warnings: `{quality['warning_flags']}`",
            f"- Severe data issue count: `{quality['severe_data_issue_count']}`",
            f"- Strategy design status: `{quality['strategy_design_status']}`",
            f"- Hydration lag: `{quality['hydration_lag']}`",
        ]
    ) + "\n"


def _summary_markdown(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    quality: dict[str, Any],
    buy_rules: list[dict[str, Any]],
    exit_rules: list[dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "# Partial Forward Strategy Preview",
            "",
            f"- Sample label: `{summary['sample_label']}`",
            f"- Mints analyzed: `{summary['rows_mints_analyzed']}`",
            f"- Crossed 20k: `{manifest['crossed_counts'].get('20k', 0)}`",
            f"- Crossed 1M: `{manifest['crossed_counts'].get('1m', 0)}`",
            f"- Quality warnings: `{quality['warning_flags']}`",
            "",
            "## Tentative Buy Candidates",
            *[f"- `{row['rule_id']}`: {row['name']}" for row in buy_rules],
            "",
            "## Tentative Exit Candidates",
            *[f"- `{row['exit_rule_id']}`: {row['name']}" for row in exit_rules],
            "",
            "No live trades, paper trades, validation, or profitability claims were produced.",
        ]
    ) + "\n"
