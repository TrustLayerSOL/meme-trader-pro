"""Cross-sample runner-pattern synthesis utilities.

This module is descriptive research infrastructure only. It does not contain
private-key logic, wallet execution, transaction building, live trading, paper
trading, validation, backtests, threshold optimization, or strategy deployment.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable

import pandas as pd


LIVE_V2_RELATIVE_ROOT = Path("data/forward_observation/official_lifecycle_watch_v2")
REPORT_RELATIVE_ROOT = Path("data/backtests/diagnostics/reports/forward_observation/cross_sample_pattern_synthesis")
SNAPSHOT_RELATIVE_ROOT = Path("data/forward_observation/snapshots")
STATUS_RELATIVE_PATH = Path("theses/CROSS_SAMPLE_PATTERN_SYNTHESIS_STATUS.md")
SNAPSHOT_FILES = [
    "births.jsonl",
    "provisional_births.jsonl",
    "stale_births.jsonl",
    "hydration_results.jsonl",
    "followup_paths.jsonl",
    "events.jsonl",
    "metadata.jsonl",
    "drawdowns.jsonl",
    "lifecycle_state.json",
    "lifecycle_transitions.jsonl",
    "paper_shadow_labels.jsonl",
    "paper_shadow_exit_labels.jsonl",
    "status.json",
]
MILESTONE_LEVELS = ["10k", "15k", "20k", "30k", "50k", "100k", "200k", "500k", "1m"]
SOCIAL_FIELDS = ["website_url", "twitter_x_url", "telegram_url", "discord_url"]
GUARDRAILS = {
    "collector_left_running": True,
    "no_live_trading": True,
    "no_enabled_paper_trading": True,
    "no_private_key_logic": True,
    "no_wallet_execution": True,
    "no_transaction_signing": True,
    "no_buy_orders": True,
    "no_sell_orders": True,
    "no_swaps": True,
    "no_jupiter_calls": True,
    "no_transaction_building": True,
    "no_order_routing": True,
    "no_real_pnl_claims": True,
    "no_profitability_claims": True,
    "no_strategy_deployment": True,
    "no_alerts": True,
    "no_threshold_optimization": True,
    "no_grid_search": True,
    "no_ml": True,
    "no_validation": True,
    "no_backtest": True,
}
APPROVED_USES = ["descriptive_pattern_discovery", "diagnostic_reporting", "collector_feature_tracking_design"]
PROHIBITED_USES = [
    "live_trading",
    "paper_trading",
    "validation",
    "backtest",
    "threshold_optimization",
    "strategy_deployment",
    "pnl_claims",
]


@dataclass(frozen=True)
class SourceSpec:
    source_dataset: str
    source_class: str
    path: Path
    data_quality_tier: str
    actionability_tier: str
    quarantine_flag: bool
    source_warning_flags: list[str]
    allowed_use: str = "descriptive_context_only"


def snapshot_live_v2_data(
    data_root: Path | str,
    *,
    timestamp: str | None = None,
    collector_left_running: bool | None = None,
) -> dict[str, Any]:
    root = Path(data_root)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_label = f"live_v2_pattern_synthesis_snapshot_{stamp}"
    source_root = root / LIVE_V2_RELATIVE_ROOT
    snapshot_root = root / SNAPSHOT_RELATIVE_ROOT / snapshot_label
    snapshot_root.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, Any]] = []
    row_counts: dict[str, int] = {}
    for name in SNAPSHOT_FILES:
        source = source_root / name
        if not source.exists():
            continue
        dest = snapshot_root / name
        shutil.copy2(source, dest)
        copied.append({"source": str(source), "snapshot": str(dest), "bytes": dest.stat().st_size})
        row_counts[name] = _row_count(dest)

    quality_source_root = root / "data/backtests/diagnostics/reports/forward_observation/official_lifecycle_watch_v2"
    quality_dest_root = snapshot_root / "quality_audits"
    quality_files: list[dict[str, Any]] = []
    if quality_source_root.exists():
        for source in sorted(quality_source_root.glob("*quality*")):
            if source.is_file() and not source.name.startswith("._"):
                quality_dest_root.mkdir(parents=True, exist_ok=True)
                dest = quality_dest_root / source.name
                shutil.copy2(source, dest)
                quality_files.append({"source": str(source), "snapshot": str(dest), "bytes": dest.stat().st_size})

    current_status = _status_counts_from_lifecycle_root(snapshot_root)
    running = _collector_running() if collector_left_running is None else collector_left_running
    manifest = {
        "snapshot_label": snapshot_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collector_left_running": running,
        "source_root": str(source_root),
        "snapshot_root": str(snapshot_root),
        "source_files_copied": copied,
        "quality_audit_files_copied": quality_files,
        "row_counts": row_counts,
        "current_status_counts": current_status,
        "known_limitations": [
            "snapshot_is_copy_while_collector_may_continue_writing",
            "same_timestamp_20k_to_1m_jumps_are_path_informative_not_clean_actionable_entries",
            "quarantined_and_historical_sources_are_descriptive_context_only",
        ],
        "approved_uses": APPROVED_USES,
        "prohibited_uses": PROHIBITED_USES,
    }
    _write_json(snapshot_root / "snapshot_manifest.json", manifest)
    (snapshot_root / "snapshot_manifest.md").write_text(_snapshot_manifest_markdown(manifest), encoding="utf-8")
    return manifest


def run_cross_sample_pattern_synthesis(
    data_root: Path | str,
    *,
    timestamp: str | None = None,
    collector_left_running: bool | None = None,
    status_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(data_root)
    status_base = Path(status_root) if status_root is not None else root
    report_root = root / REPORT_RELATIVE_ROOT
    report_root.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_live_v2_data(root, timestamp=timestamp, collector_left_running=collector_left_running)
    snapshot_root = Path(snapshot["snapshot_root"])

    sources = discover_sources(root, snapshot_root=snapshot_root)
    inventory_rows = [inventory_source(source) for source in sources]
    _write_csv(report_root / "source_inventory.csv", inventory_rows)

    dataset_rows = build_combined_synthesis_dataset(sources)
    dataset_rows = sorted(dataset_rows, key=lambda row: (str(row.get("source_dataset")), str(row.get("mint"))))
    _write_jsonl(report_root / "cross_sample_synthesis_dataset.jsonl", dataset_rows)
    _write_parquet(report_root / "cross_sample_synthesis_dataset.parquet", dataset_rows)

    metadata_rows = build_metadata_social_pattern_audit(dataset_rows)
    high_runner_rows = build_high_runner_pattern_comparison(dataset_rows)
    fall_rows = build_fall_bounce_vs_die_analysis(dataset_rows)
    framework_rows = build_candidate_buy_sell_framework(dataset_rows, high_runner_rows, fall_rows)
    _write_csv(report_root / "metadata_social_pattern_audit.csv", metadata_rows)
    _write_csv(report_root / "high_runner_pattern_comparison.csv", high_runner_rows)
    _write_csv(report_root / "fall_bounce_vs_die_analysis.csv", fall_rows)
    _write_csv(report_root / "candidate_buy_sell_framework.csv", framework_rows)

    summary = build_summary(
        root=root,
        status_root=status_base,
        report_root=report_root,
        snapshot=snapshot,
        inventory_rows=inventory_rows,
        dataset_rows=dataset_rows,
        metadata_rows=metadata_rows,
        high_runner_rows=high_runner_rows,
        fall_rows=fall_rows,
        framework_rows=framework_rows,
    )
    _write_json(report_root / "cross_sample_pattern_synthesis_summary.json", summary)
    (report_root / "cross_sample_pattern_synthesis_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    status_path = status_base / STATUS_RELATIVE_PATH
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(summary), encoding="utf-8")
    return summary


def discover_sources(data_root: Path | str, *, snapshot_root: Path) -> list[SourceSpec]:
    root = Path(data_root)
    sources = [
        SourceSpec(
            source_dataset="official_lifecycle_watch_v2_snapshot",
            source_class="official_lifecycle_v2_snapshot",
            path=snapshot_root,
            data_quality_tier="official_v2_snapshot",
            actionability_tier="official_actionability_available",
            quarantine_flag=False,
            source_warning_flags=[],
            allowed_use="descriptive_official_snapshot",
        )
    ]
    v1 = root / "data/forward_observation/official_lifecycle_watch_v1"
    if v1.exists():
        sources.append(
            SourceSpec(
                source_dataset="official_lifecycle_watch_v1",
                source_class="official_lifecycle_v1",
                path=v1,
                data_quality_tier="legacy_forward",
                actionability_tier="legacy_actionability_context",
                quarantine_flag=False,
                source_warning_flags=["pre_v2_accounting"],
            )
        )
    q_root = root / "data/forward_observation/quarantined"
    if q_root.exists():
        for child in sorted(q_root.iterdir()):
            if child.name.startswith("._") or not child.is_dir():
                continue
            if _looks_like_lifecycle_root(child):
                sources.append(
                    SourceSpec(
                        source_dataset=f"quarantined/{child.name}",
                        source_class="quarantined_forward",
                        path=child,
                        data_quality_tier="quarantined_context",
                        actionability_tier="non_actionable_context",
                        quarantine_flag=True,
                        source_warning_flags=["quarantined"],
                    )
                )
    for path in _historical_candidate_files(root):
        sources.append(
            SourceSpec(
                source_dataset=_relative_dataset_name(root, path),
                source_class=_historical_class(path),
                path=path,
                data_quality_tier="historical_enriched",
                actionability_tier="historical_context",
                quarantine_flag=False,
                source_warning_flags=["historical_or_diagnostic_context"],
            )
        )
    return sources


def inventory_source(source: SourceSpec) -> dict[str, Any]:
    rows = _source_records(source)
    mints = {row.get("mint") for row in rows if row.get("mint")}
    return {
        "source_dataset": source.source_dataset,
        "source_class": source.source_class,
        "path": str(source.path),
        "rows": len(rows),
        "mints": len(mints),
        "crossed_10k": _count_bool(rows, "crossed_10k"),
        "crossed_20k": _count_bool(rows, "crossed_20k"),
        "crossed_50k": _count_bool(rows, "crossed_50k"),
        "crossed_100k": _count_bool(rows, "crossed_100k"),
        "crossed_500k": _count_bool(rows, "crossed_500k"),
        "crossed_1m": _count_bool(rows, "crossed_1m"),
        "actionable_rows": sum(1 for row in rows if row.get("actionable_crossed_20k") is True or row.get("actionability_tier") == "actionable_crossed_20k"),
        "metadata_coverage": _coverage(rows, ["has_website", "has_twitter", "has_telegram", "website_url", "twitter_x_url", "telegram_url"]),
        "path_coverage": _coverage(rows, ["fdv_proxy", "max_fdv_after_20k", "crossed_20k"]),
        "holder_top_holder_coverage": _coverage(rows, ["holder_count", "holder_growth", "top_holder_share_proxy", "top_10_holder_share_proxy"]),
        "creator_funder_coverage": _coverage(rows, ["creator", "creator_net_flow_proxy", "funder", "creator_deployer"]),
        "liquidity_coverage": _coverage(rows, ["liquidity_proxy", "estimated_sell_impact_proxy"]),
        "synthetic_bot_proxy_coverage": _coverage(rows, ["synthetic_activity_proxy", "same_second_buy_count", "same_slot_buy_count", "rapid_round_trip_count"]),
        "drawdown_reclaim_coverage": _coverage(rows, ["drawdown_pct", "terminal_collapse_proxy", "recovered_after_30pct", "reclaim_status"]),
        "limitations": ";".join(source.source_warning_flags),
        "allowed_use": source.allowed_use,
    }


def build_combined_synthesis_dataset(sources: list[SourceSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        if source.path.is_dir() and _looks_like_lifecycle_root(source.path):
            rows.extend(_normalize_lifecycle_source(source))
        else:
            rows.extend(_normalize_tabular_source(source))
    return rows


def build_metadata_social_pattern_audit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for context_name, subset in _contexts(rows).items():
        for group_name, group_rows in _runner_groups(subset).items():
            out.append(
                {
                    "context": context_name,
                    "runner_group": group_name,
                    "mints": len(group_rows),
                    "metadata_coverage": _coverage(group_rows, ["metadata_completeness_score", "token_name", "metadata_uri"]),
                    "has_website_rate": _rate(group_rows, "has_website"),
                    "has_twitter_rate": _rate(group_rows, "has_twitter"),
                    "has_telegram_rate": _rate(group_rows, "has_telegram"),
                    "has_discord_rate": _rate(group_rows, "has_discord"),
                    "median_social_link_count": _median_field(group_rows, "social_link_count"),
                    "median_metadata_completeness_score": _median_field(group_rows, "metadata_completeness_score"),
                    "metadata_early_enough_at_20k_rate": _rate(group_rows, "metadata_available_by_20k"),
                    "interpretation": _metadata_interpretation(group_rows),
                }
            )
    return out


def build_high_runner_pattern_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = [
        ("A_FDV_efficiency", "fdv_per_event_at_20k", "entry_side"),
        ("A_FDV_efficiency", "fdv_per_buy_at_20k", "entry_side"),
        ("A_FDV_efficiency", "fdv_per_active_wallet_at_20k", "entry_side"),
        ("B_speed_timing", "create_to_20k_seconds", "entry_side"),
        ("C_flow_activity", "buy_sell_ratio_at_20k", "entry_side"),
        ("D_metadata_social", "social_link_count", "entry_side_if_early"),
        ("D_metadata_social", "metadata_completeness_score", "entry_side_if_early"),
        ("E_liquidity_microstructure", "liquidity_proxy", "entry_or_exit_side"),
        ("F_holder_top_holder", "top_10_holder_share_proxy", "entry_or_risk_side"),
        ("G_creator_funder", "creator_net_flow_proxy", "context_side"),
        ("H_synthetic_timing", "same_second_buy_count", "risk_filter_side"),
        ("I_drawdown_reclaim", "no_reclaim_after_10m", "exit_side"),
    ]
    rows_out: list[dict[str, Any]] = []
    high = [row for row in rows if row.get("crossed_500k") or row.get("crossed_1m")]
    weak = [row for row in rows if row.get("crossed_20k") and not row.get("crossed_100k")]
    for family, feature, side in features:
        high_values = [_num(row.get(feature)) for row in high if _num(row.get(feature)) is not None]
        weak_values = [_num(row.get(feature)) for row in weak if _num(row.get(feature)) is not None]
        rows_out.append(
            {
                "feature_family": family,
                "feature": feature,
                "coverage": len(high_values) + len(weak_values),
                "high_runner_median": _median(high_values),
                "weak_or_stall_median": _median(weak_values),
                "direction": _direction(_median(high_values), _median(weak_values)),
                "effect_proxy": _effect_proxy(_median(high_values), _median(weak_values)),
                "source_consistency": _source_consistency(rows, feature),
                "actionability_tier": _feature_actionability_tier(feature),
                "historical_and_forward_agree": _historical_forward_agree(rows, feature),
                "entry_or_exit_side": side,
                "classification": _feature_classification(feature, high_values, weak_values, family),
            }
        )
    return rows_out


def build_fall_bounce_vs_die_analysis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for level in [20, 30, 40, 50]:
        drawdown_key = f"first_{level}pct_drawdown_time"
        recovered_key = f"recovered_after_{level}pct"
        event_rows = [row for row in rows if row.get(drawdown_key) is not None or row.get("terminal_collapse_proxy") is True]
        recoverable = [row for row in event_rows if row.get(recovered_key) is True or row.get("reached_next_milestone_after_drawdown") is True]
        terminal = [
            row
            for row in event_rows
            if row.get("terminal_collapse_proxy") is True
            or row.get("inactive_timeout") is True
            or row.get("no_reclaim_after_10m") is True
        ]
        out.append(
            {
                "drawdown_level_pct": level,
                "event_count": len(event_rows),
                "recoverable_count": len(recoverable),
                "terminal_count": len(terminal),
                "median_fdv_efficiency_recoverable": _median_field(recoverable, "fdv_per_event_at_20k"),
                "median_fdv_efficiency_terminal": _median_field(terminal, "fdv_per_event_at_20k"),
                "median_social_links_recoverable": _median_field(recoverable, "social_link_count"),
                "median_social_links_terminal": _median_field(terminal, "social_link_count"),
                "same_timestamp_jump_count": sum(1 for row in event_rows if row.get("same_timestamp_20k_to_1m_jump") is True),
                "interpretation": _drawdown_interpretation(level, recoverable, terminal),
            }
        )
    return out


def build_candidate_buy_sell_framework(
    rows: list[dict[str, Any]],
    high_runner_rows: list[dict[str, Any]],
    fall_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actionable = [row for row in rows if row.get("actionability_tier") == "actionable_crossed_20k"]
    b3_support = sum(1 for row in rows if row.get("B3_pass") is True)
    metadata_coverage = _coverage(rows, ["social_link_count", "metadata_completeness_score"])
    return [
        _framework_row("broad_baseline_actionable_20k", "buy_side", "forward_promising_candidate", len(actionable), "Cleanest broad official entry universe; preserves B labels separately.", "Needs larger official actionable sample before paper-shadow enablement."),
        _framework_row("10k_aggressive_fdv_efficiency", "buy_side", "data_limited", _count_bool(rows, "actionable_crossed_10k"), "Potential early efficient-flow detector before 20k.", "Coverage is sparse and same-timestamp jumps can contaminate timing."),
        _framework_row("15k_balanced_speed_efficiency", "buy_side", "data_limited", _count_bool(rows, "crossed_15k"), "Balances earlier observation with milestone confirmation.", "Requires official collector confirmation; no threshold optimization performed."),
        _framework_row("20k_confirmation_efficiency", "buy_side", "forward_promising_candidate", len(actionable), "Most defensible current buy-side context because actionability is explicit.", "Still descriptive only; no paper/live trading."),
        _framework_row("metadata_social_enhanced_variant", "buy_side", "data_limited" if metadata_coverage < 0.5 else "forward_promising_candidate", int(metadata_coverage * len(rows)), "Metadata/social may add profile context when available early.", "Coverage and timing are not yet enough for a standalone decision layer."),
        _framework_row("risk_filter_variant", "buy_side", "possible_risk_filter", sum(1 for row in rows if row.get("same_timestamp_20k_to_1m_jump")), "Separates coarse same-timestamp jumps and non-actionable context from clean entries.", "Risk filter only; not an optimized threshold."),
        _framework_row("E2_milestone_trailing_drawdown_reclaim_grace", "sell_side", "path_exit_candidate", len(fall_rows), "Exit-side evidence appears only after path develops and drawdowns are visible.", "Label-only; no sell logic enabled."),
        _framework_row("no_reclaim_after_drawdown", "sell_side", "path_exit_candidate", sum(1 for row in rows if row.get("no_reclaim_after_10m") is True), "Terminal rows often show no reclaim after drawdown.", "Requires live official follow-up confirmation."),
        _framework_row("max_age_inactivity", "sell_side", "path_exit_candidate", sum(1 for row in rows if row.get("inactive_timeout") is True), "Useful terminal-state hygiene for stalled mints.", "Exit-side only and descriptive."),
        _framework_row("diagnostic_hold_to_milestone_comparator", "sell_side", "data_limited", sum(1 for row in rows if row.get("crossed_100k") is True), "Comparator for milestone outcomes without PnL.", "Diagnostic only; not a trading rule."),
        _framework_row("fall_bounce_exit_warning", "sell_side", "data_limited", sum(1 for row in rows if row.get("recovered_after_30pct") is True), "Recovery rows should not be treated the same as terminal collapses.", "Needs more official path depth before being promoted."),
    ]


def build_summary(
    *,
    root: Path,
    status_root: Path,
    report_root: Path,
    snapshot: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
    dataset_rows: list[dict[str, Any]],
    metadata_rows: list[dict[str, Any]],
    high_runner_rows: list[dict[str, Any]],
    fall_rows: list[dict[str, Any]],
    framework_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_mints = {row.get("mint") for row in dataset_rows if row.get("mint")}
    actionable = [row for row in dataset_rows if row.get("actionability_tier") == "actionable_crossed_20k"]
    same_timestamp = [row for row in dataset_rows if row.get("same_timestamp_20k_to_1m_jump") is True]
    recommendation = _recommendation(dataset_rows)
    findings = {
        "fdv_efficiency": _finding_from_comparison(high_runner_rows, "fdv_per_event_at_20k"),
        "metadata_social": _metadata_summary(metadata_rows),
        "high_runner_patterns": _high_runner_summary(high_runner_rows),
        "fall_bounce_vs_die": _fall_summary(fall_rows),
        "framework": "Broad actionable 20k remains the most defensible descriptive entry universe; E2/no-reclaim concepts remain exit-side labels only.",
    }
    return {
        "report_id": "cross_sample_pattern_synthesis_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_root": str(report_root),
        "snapshot": snapshot,
        "guardrails": {**GUARDRAILS, "collector_left_running": bool(snapshot["collector_left_running"])},
        "summary": {
            "datasets_combined": len(inventory_rows),
            "rows_analyzed": len(dataset_rows),
            "mints_analyzed": len(unique_mints),
            "actionable_crossed_20k_rows": len(actionable),
            "same_timestamp_20k_to_1m_rows": len(same_timestamp),
        },
        "datasets_combined": [row["source_dataset"] for row in inventory_rows],
        "findings": findings,
        "metadata_social_findings": findings["metadata_social"],
        "high_runner_findings": findings["high_runner_patterns"],
        "fall_bounce_vs_die_findings": findings["fall_bounce_vs_die"],
        "candidate_buy_sell_framework": framework_rows,
        "recommendation": recommendation,
        "paths": {
            "source_inventory": str(report_root / "source_inventory.csv"),
            "dataset_jsonl": str(report_root / "cross_sample_synthesis_dataset.jsonl"),
            "dataset_parquet": str(report_root / "cross_sample_synthesis_dataset.parquet"),
            "metadata_social_pattern_audit": str(report_root / "metadata_social_pattern_audit.csv"),
            "high_runner_pattern_comparison": str(report_root / "high_runner_pattern_comparison.csv"),
            "fall_bounce_vs_die_analysis": str(report_root / "fall_bounce_vs_die_analysis.csv"),
            "candidate_buy_sell_framework": str(report_root / "candidate_buy_sell_framework.csv"),
            "summary_json": str(report_root / "cross_sample_pattern_synthesis_summary.json"),
            "summary_md": str(report_root / "cross_sample_pattern_synthesis_summary.md"),
            "status_file": str(status_root / STATUS_RELATIVE_PATH),
        },
    }


def _normalize_lifecycle_source(source: SourceSpec) -> list[dict[str, Any]]:
    root = source.path
    births = _jsonl(root / "births.jsonl")
    paths = _jsonl(root / "followup_paths.jsonl")
    metadata = _latest_by_mint(_jsonl(root / "metadata.jsonl"))
    state = _read_json(root / "lifecycle_state.json").get("mints", {})
    drawdowns = _jsonl(root / "drawdowns.jsonl")
    births_by_mint = _latest_by_mint(births)
    paths_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in paths:
        mint = _mint(row)
        if mint:
            paths_by_mint[mint].append(row)
    for rows in paths_by_mint.values():
        rows.sort(key=lambda row: (_num(row.get("timestamp")) is None, _num(row.get("timestamp")) or 0))
    drawdowns_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in drawdowns:
        mint = _mint(row)
        if mint:
            drawdowns_by_mint[mint].append(row)
    mints = set(births_by_mint) | set(paths_by_mint) | set(metadata) | set(state)
    rows = []
    for mint in sorted(mints):
        birth = births_by_mint.get(mint, {})
        m_paths = paths_by_mint.get(mint, [])
        meta = metadata.get(mint, {})
        state_row = state.get(mint, {})
        row = _base_row(source, mint)
        row.update(_identity_fields(birth, meta))
        row.update(_lifecycle_milestones(m_paths))
        row.update(_actionability_fields(birth, row, source))
        row.update(_flow_features(birth, m_paths))
        row.update(_metadata_fields(meta))
        row.update(_drawdown_fields(drawdowns_by_mint.get(mint, []), state_row, m_paths))
        row["maturity_state"] = state_row.get("state")
        row["inactive_timeout"] = state_row.get("state") == "matured_inactive_timeout"
        row["terminal_collapse_proxy"] = state_row.get("state") == "matured_terminal_collapse" or row.get("terminal_collapse_proxy") is True
        rows.append(row)
    return rows


def _normalize_tabular_source(source: SourceSpec) -> list[dict[str, Any]]:
    records = _read_table_records(source.path)
    by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        mint = _mint(record)
        if mint:
            by_mint[mint].append(record)
    rows: list[dict[str, Any]] = []
    for mint, records_for_mint in sorted(by_mint.items()):
        merged = _merge_records(records_for_mint)
        row = _base_row(source, mint)
        row.update(_identity_fields(merged, merged))
        for level in MILESTONE_LEVELS:
            row[f"crossed_{level}"] = _boolish(merged.get(f"crossed_{level}") or merged.get(f"reached_{level}"))
            row[f"first_crossed_{level}_time"] = _first_present(merged, [f"first_crossed_{level}_time", f"{level}_time", "timestamp"])
        row["actionable_crossed_20k"] = _boolish(merged.get("actionable_crossed_20k") or merged.get("baseline_all_actionable_20k"))
        row["actionability_tier"] = _actionability_tier(row, source)
        row["max_fdv_after_20k"] = _first_present(merged, ["max_fdv_after_20k", "local_high_fdv", "max_fdv", "fdv_proxy"])
        for key in _normalized_optional_fields():
            if row.get(key) is None:
                row[key] = _first_present(merged, [key])
        row.update(_metadata_fields(merged))
        row["clean_milestone_sequence"] = _clean_sequence(row)
        row["same_timestamp_20k_to_1m_jump"] = _same_timestamp(row.get("first_crossed_20k_time"), row.get("first_crossed_1m_time"))
        rows.append(row)
    return rows


def _base_row(source: SourceSpec, mint: str) -> dict[str, Any]:
    return {
        "mint": mint,
        "source_dataset": source.source_dataset,
        "sample_label": None,
        "data_quality_tier": source.data_quality_tier,
        "actionability_tier": source.actionability_tier,
        "quarantine_flag": source.quarantine_flag,
        "source_warning_flags": "|".join(source.source_warning_flags),
        "creator": None,
        "create_time": None,
        "first_followup_time": None,
        "first_path_time": None,
        "official_accepted_birth": None,
        "first_path_before_10k": None,
        "first_path_before_15k": None,
        "first_path_before_20k": None,
        "actionable_crossed_10k": False,
        "actionable_crossed_20k": False,
        "actionability_failure_reason": None,
        "same_timestamp_20k_to_1m_jump": False,
        "clean_milestone_sequence": False,
    }


def _identity_fields(birth: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_label": birth.get("sample_label") or meta.get("sample_label"),
        "creator": birth.get("creator") or birth.get("creator_deployer") or meta.get("creator"),
        "create_time": _first_present(birth, ["create_time", "launch_time", "block_time"]),
        "first_followup_time": _first_present(birth, ["first_followup_attempt_time", "first_followup_attempt_at"]),
        "first_path_time": _first_present(birth, ["first_fdv_path_time", "first_path_time"]),
        "official_accepted_birth": birth.get("official_accepted_birth"),
    }


def _lifecycle_milestones(paths: list[dict[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for level in MILESTONE_LEVELS:
        level_rows = [path for path in paths if path.get(f"crossed_{level}") is True]
        row[f"crossed_{level}"] = bool(level_rows)
        row[f"first_crossed_{level}_time"] = _first_time(level_rows)
    fdv_paths = [path for path in paths if _num(path.get("fdv_proxy")) is not None]
    row["first_path_time"] = _first_time(fdv_paths)
    row["max_fdv_after_20k"] = max([_num(path.get("fdv_proxy")) for path in paths if _num(path.get("fdv_proxy")) is not None], default=None)
    row["time_to_peak_after_20k"] = _delta(row.get("first_crossed_20k_time"), _time_of_max_fdv(paths))
    row["same_timestamp_20k_to_1m_jump"] = _same_timestamp(row.get("first_crossed_20k_time"), row.get("first_crossed_1m_time"))
    row["clean_milestone_sequence"] = _clean_sequence(row)
    return row


def _actionability_fields(birth: dict[str, Any], row: dict[str, Any], source: SourceSpec) -> dict[str, Any]:
    first_10 = birth.get("fdv_path_before_10k") is True or birth.get("first_followup_before_10k") is True
    first_15 = birth.get("fdv_path_before_15k") is True or first_10
    first_20 = birth.get("fdv_path_before_20k") is True or birth.get("first_followup_before_20k") is True
    out = {
        "first_path_before_10k": first_10,
        "first_path_before_15k": first_15,
        "first_path_before_20k": first_20,
        "actionable_crossed_10k": bool(row.get("crossed_10k") and first_10),
        "actionable_crossed_20k": bool(row.get("crossed_20k") and first_20),
        "actionability_failure_reason": birth.get("actionability_failure_reason"),
    }
    out["actionability_tier"] = _actionability_tier({**row, **out}, source)
    return out


def _flow_features(birth: dict[str, Any], paths: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for level in ["10k", "15k", "20k"]:
        path = _first_crossed_path(paths, level)
        suffix = f"at_{level}"
        out[f"fdv_per_event_{suffix}"] = _num(path.get("fdv_per_event")) if path else None
        out[f"fdv_per_buy_{suffix}"] = _num(path.get("fdv_per_buy")) if path else None
        out[f"fdv_per_active_wallet_{suffix}"] = _num(path.get("fdv_per_active_wallet")) if path else None
        out[f"event_count_{suffix}"] = _num(path.get("event_count")) if path else None
        out[f"buy_count_{suffix}"] = _num(path.get("buy_count")) if path else None
        out[f"sell_count_{suffix}"] = _num(path.get("sell_count")) if path else None
        out[f"active_wallets_{suffix}"] = _num(path.get("active_wallet_count") or path.get("active_wallets")) if path else None
        out[f"buy_sell_ratio_{suffix}"] = _num(path.get("buy_sell_ratio")) if path else _ratio(out[f"buy_count_{suffix}"], out[f"sell_count_{suffix}"])
    create_time = _num(birth.get("create_time") or birth.get("launch_time") or birth.get("block_time"))
    for level in ["10k", "15k", "20k"]:
        out[f"create_to_{level}_seconds"] = _delta(create_time, _first_time([path for path in paths if path.get(f"crossed_{level}") is True]))
    for start, end in [("10k", "20k"), ("20k", "50k"), ("20k", "100k"), ("20k", "500k"), ("20k", "1m")]:
        out[f"{start}_to_{end}_seconds"] = _delta(out.get(f"create_to_{start}_seconds"), out.get(f"create_to_{end}_seconds"))
    return out


def _metadata_fields(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "token_name": row.get("token_name") or row.get("name"),
        "token_symbol": row.get("token_symbol") or row.get("symbol"),
        "metadata_uri": row.get("metadata_uri") or row.get("uri"),
        "image_uri": row.get("image_uri") or row.get("image"),
        "website_url": row.get("website_url") or row.get("website"),
        "twitter_x_url": row.get("twitter_x_url") or row.get("twitter_url") or row.get("x_url"),
        "telegram_url": row.get("telegram_url") or row.get("telegram"),
        "discord_url": row.get("discord_url") or row.get("discord"),
        "metadata_source": row.get("metadata_source") or row.get("source_provenance"),
        "metadata_observed_at": row.get("metadata_observed_at") or row.get("timestamp"),
    }
    out["has_website"] = bool(out["website_url"])
    out["has_twitter"] = bool(out["twitter_x_url"])
    out["has_telegram"] = bool(out["telegram_url"])
    out["has_discord"] = bool(out["discord_url"])
    out["social_link_count"] = sum(1 for field in SOCIAL_FIELDS if out.get(field))
    out["metadata_completeness_score"] = round(
        sum(1 for key in ["token_name", "token_symbol", "metadata_uri", "image_uri", "website_url", "twitter_x_url", "telegram_url", "discord_url"] if out.get(key))
        / 8.0,
        4,
    )
    out["token_name_length"] = len(str(out["token_name"])) if out["token_name"] else None
    out["symbol_length"] = len(str(out["token_symbol"])) if out["token_symbol"] else None
    return out


def _drawdown_fields(drawdowns: list[dict[str, Any]], state_row: dict[str, Any], paths: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for level in [20, 30, 40, 50]:
        hit = [row for row in drawdowns if (_num(row.get("drawdown_pct")) or 0) >= level]
        out[f"first_{level}pct_drawdown_time"] = _first_time(hit)
        out[f"recovered_after_{level}pct"] = any(row.get("reclaim_status") == "at_or_above_local_high" or row.get("recovered") is True for row in drawdowns)
    out["no_reclaim_after_5m"] = any(row.get("reclaim_status") == "no_reclaim_after_5m" for row in drawdowns)
    out["no_reclaim_after_10m"] = any(row.get("reclaim_status") == "no_reclaim_after_10m" for row in drawdowns)
    out["terminal_collapse_proxy"] = state_row.get("state") == "matured_terminal_collapse"
    out["reached_next_milestone_after_drawdown"] = bool(out.get("first_30pct_drawdown_time") and any(path.get("crossed_100k") is True for path in paths))
    return out


def _framework_row(candidate: str, side: str, tier: str, coverage: int, why: str, limitation: str) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "entry_exit_side": side,
        "evidence_tier": tier,
        "coverage": coverage,
        "why_it_may_matter": why,
        "limitation": limitation,
        "must_confirm_in_official_actionable_sample": True,
        "paper_shadow_readiness": "label_only_ready_disabled",
    }


def _recommendation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actionable_count = sum(1 for row in rows if row.get("actionability_tier") == "actionable_crossed_20k")
    metadata_coverage = _coverage(rows, ["metadata_completeness_score"])
    if actionable_count < 100:
        return {
            "recommendation_id": "A",
            "recommendation": "Continue collector and wait for 100 actionable crossed-20k before enabling paper-shadow.",
            "reason": f"Only {actionable_count} actionable crossed-20k rows are available in the combined descriptive snapshot.",
        }
    if metadata_coverage < 0.5:
        return {
            "recommendation_id": "C",
            "recommendation": "Add metadata/holder enrichment before paper-shadow.",
            "reason": "Metadata or holder coverage remains too sparse for profile-enhanced labels.",
        }
    return {
        "recommendation_id": "B",
        "recommendation": "Enable disabled paper-shadow labeling for broad baseline only, no PnL, while collector continues.",
        "reason": "Actionable support is adequate for label-only observation; no execution or PnL should be enabled.",
    }


def _historical_candidate_files(root: Path) -> list[Path]:
    roots = [
        root / "data/backtests/structural_enrichment",
        root / "data/backtests/diagnostics/reports/final_runner_fingerprint",
        root / "data/backtests/diagnostics/reports/non_fdv_incremental_information_audit",
        root / "data/backtests/diagnostics/reports/T011_expanded_rerun",
        root / "data/backtests/diagnostics/reports/efficient_mover_continuation_anatomy",
        root / "data/backtests/diagnostics/reports/efficient_mover_drawdown_recovery",
        root / "data/backtests/diagnostics/reports/forward_observation/pre_lifecycle_watch_pattern_preview",
    ]
    preferred_names = {
        "master_enriched_runner_fingerprint.parquet",
        "master_enriched_runner_fingerprint.jsonl",
        "master_tier1_tier2_enriched_runner_fingerprint.parquet",
        "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
        "combined_aligned_p0_structural_fingerprint_fdv_repaired.parquet",
        "combined_aligned_p0_structural_fingerprint_fdv_repaired.jsonl",
        "combined_expanded_lifecycle_snapshots.jsonl",
        "expanded_trigger_20k_feature_rows.csv",
        "final_runner_candidate_fingerprints.csv",
        "final_runner_feature_family_comparison.csv",
        "non_fdv_feature_incremental_rank.csv",
        "efficient_mover_feature_comparison.csv",
        "efficient_mover_entry_vs_exit_features.csv",
        "drawdown_events.csv",
        "recoverable_vs_terminal_features.csv",
        "pre_lifecycle_broad_behavior_comparison.csv",
        "pre_lifecycle_new_behavior_candidates.csv",
    }
    files: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith("._") and path.suffix in {".jsonl", ".csv", ".parquet"}:
                if path.name in preferred_names:
                    files.append(path)
    return files


def _source_records(source: SourceSpec) -> list[dict[str, Any]]:
    if source.path.is_dir() and _looks_like_lifecycle_root(source.path):
        return _normalize_lifecycle_source(source)
    return _normalize_tabular_source(source)


def _read_table_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.suffix == ".jsonl":
            return _jsonl(path)
        if path.suffix == ".csv":
            frame = pd.read_csv(path)
        elif path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            return []
        return frame.where(pd.notnull(frame), None).to_dict(orient="records")
    except Exception:
        return []


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(_json_safe(row), sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{key: _csv_value(row.get(key)) for key in fieldnames} for row in rows])


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    for column in frame.columns:
        if frame[column].dtype == "object":
            frame[column] = frame[column].map(_parquet_cell)
    frame.to_parquet(path, index=False)


def _snapshot_manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Live v2 Pattern Synthesis Snapshot",
            "",
            f"Snapshot: `{manifest['snapshot_label']}`",
            f"Collector left running: `{manifest['collector_left_running']}`",
            f"Source files copied: `{len(manifest['source_files_copied'])}`",
            f"Row counts: `{manifest['row_counts']}`",
            "",
            "Approved uses: descriptive pattern discovery and diagnostics only.",
            "Prohibited uses: live trading, paper trading, validation, backtests, PnL claims, threshold optimization.",
        ]
    ) + "\n"


def _summary_markdown(summary: dict[str, Any]) -> str:
    findings = summary["findings"]
    recommendation = summary["recommendation"]
    return "\n".join(
        [
            "# Cross-Sample Pattern Synthesis Summary",
            "",
            f"Datasets combined: `{summary['summary']['datasets_combined']}`",
            f"Mints analyzed: `{summary['summary']['mints_analyzed']}`",
            f"Actionable crossed-20k rows: `{summary['summary']['actionable_crossed_20k_rows']}`",
            f"Same-timestamp 20k-to-1M rows: `{summary['summary']['same_timestamp_20k_to_1m_rows']}`",
            "",
            "## Findings",
            f"- FDV efficiency: {findings['fdv_efficiency']}",
            f"- Metadata/social: {findings['metadata_social']}",
            f"- High runners: {findings['high_runner_patterns']}",
            f"- Fall/bounce vs die: {findings['fall_bounce_vs_die']}",
            f"- Framework: {findings['framework']}",
            "",
            "## Recommendation",
            f"{recommendation['recommendation_id']}. {recommendation['recommendation']}",
            f"Reason: {recommendation['reason']}",
            "",
            "No live trading, paper trading, validation, backtest, PnL claim, or threshold optimization was run.",
        ]
    ) + "\n"


def _status_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Cross-Sample Pattern Synthesis Status",
            "",
            "Readiness: `descriptive_synthesis_complete`",
            f"Snapshot: `{summary['snapshot']['snapshot_root']}`",
            f"Datasets combined: `{summary['summary']['datasets_combined']}`",
            f"Mints analyzed: `{summary['summary']['mints_analyzed']}`",
            f"Recommendation: `{summary['recommendation']['recommendation_id']}`",
            "",
            "No live trading, paper trading, private-key logic, transaction building, validation, backtest, PnL claims, or threshold optimization were run.",
        ]
    ) + "\n"


def _status_counts_from_lifecycle_root(root: Path) -> dict[str, Any]:
    paths = _jsonl(root / "followup_paths.jsonl")
    births = _jsonl(root / "births.jsonl")
    birth_by_mint = {_mint(row): row for row in births if _mint(row)}
    crossed_20 = {_mint(row) for row in paths if _mint(row) and row.get("crossed_20k") is True}
    actionable_20 = {mint for mint in crossed_20 if birth_by_mint.get(mint, {}).get("fdv_path_before_20k") is True}
    return {
        "official_accepted_births": len(birth_by_mint),
        "fdv_path_evidence": len({_mint(row) for row in paths if _mint(row) and _num(row.get("fdv_proxy")) is not None}),
        "crossed_10k": len({_mint(row) for row in paths if _mint(row) and row.get("crossed_10k") is True}),
        "crossed_20k": len(crossed_20),
        "actionable_crossed_20k": len(actionable_20),
        "crossed_1m": len({_mint(row) for row in paths if _mint(row) and row.get("crossed_1m") is True}),
    }


def _collector_running() -> bool:
    try:
        output = subprocess.run(["ps", "-axo", "command"], check=False, capture_output=True, text=True).stdout
    except OSError:
        return False
    needles = [
        "run_forward_efficient_mover_observer --mode observe-lifecycle --sample official_lifecycle_watch_v2",
        "run_official_lifecycle_v2_6hr_collector.sh",
        "mtp_v2_6hr",
    ]
    return any(needle in output for needle in needles)


def _looks_like_lifecycle_root(path: Path) -> bool:
    return (path / "followup_paths.jsonl").exists() or (path / "births.jsonl").exists()


def _historical_class(path: Path) -> str:
    parts = set(path.parts)
    if "structural_enrichment" in parts:
        return "historical_enriched"
    if "pre_lifecycle_watch_pattern_preview" in parts:
        return "partial_birth_coverage_forward"
    return "historical_snapshot"


def _relative_dataset_name(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _row_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
    if path.suffix == ".json":
        return 1
    return 0


def _mint(row: dict[str, Any]) -> str | None:
    for key in ["mint", "token_mint", "token_address", "address"]:
        value = row.get(key)
        if value:
            return str(value)
    return None


def _latest_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mint = _mint(row)
        if mint:
            out[mint] = row
    return out


def _merge_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for record in records:
        for key, value in record.items():
            if value is not None and value != "":
                if key not in merged or merged[key] is None or merged[key] == "":
                    merged[key] = value
                elif isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
                    merged[key] = max(merged[key], value)
    return merged


def _normalized_optional_fields() -> list[str]:
    return [
        "liquidity_proxy",
        "estimated_sell_impact_proxy",
        "holder_count",
        "holder_growth",
        "top_holder_share_proxy",
        "top_10_holder_share_proxy",
        "creator_net_flow_proxy",
        "synthetic_activity_proxy",
        "same_second_buy_count",
        "same_slot_buy_count",
        "rapid_round_trip_count",
        "fdv_per_event_at_10k",
        "fdv_per_buy_at_10k",
        "fdv_per_active_wallet_at_10k",
        "fdv_per_event_at_15k",
        "fdv_per_buy_at_15k",
        "fdv_per_active_wallet_at_15k",
        "fdv_per_event_at_20k",
        "fdv_per_buy_at_20k",
        "fdv_per_active_wallet_at_20k",
        "event_count_at_10k",
        "buy_count_at_10k",
        "sell_count_at_10k",
        "active_wallets_at_10k",
        "event_count_at_20k",
        "buy_count_at_20k",
        "sell_count_at_20k",
        "active_wallets_at_20k",
        "buy_sell_ratio_at_10k",
        "buy_sell_ratio_at_20k",
        "terminal_collapse_proxy",
        "inactive_timeout",
        "no_reclaim_after_5m",
        "no_reclaim_after_10m",
    ]


def _first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_crossed_path(paths: list[dict[str, Any]], level: str) -> dict[str, Any] | None:
    matches = [path for path in paths if path.get(f"crossed_{level}") is True]
    if not matches:
        return None
    return sorted(matches, key=lambda path: (_num(path.get("timestamp")) is None, _num(path.get("timestamp")) or 0))[0]


def _first_time(rows: list[dict[str, Any]]) -> float | None:
    values = [_num(row.get("timestamp") or row.get("observed_at") or row.get("block_time")) for row in rows]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _time_of_max_fdv(paths: list[dict[str, Any]]) -> float | None:
    best: tuple[float, float] | None = None
    for path in paths:
        fdv = _num(path.get("fdv_proxy"))
        ts = _num(path.get("timestamp"))
        if fdv is None or ts is None:
            continue
        if best is None or fdv > best[0]:
            best = (fdv, ts)
    return best[1] if best else None


def _actionability_tier(row: dict[str, Any], source: SourceSpec) -> str:
    if source.quarantine_flag:
        return "quarantined_context"
    if row.get("actionable_crossed_20k") is True:
        return "actionable_crossed_20k"
    if row.get("crossed_20k") is True:
        return "crossed_20k_non_actionable"
    if row.get("crossed_10k") is True:
        return "crossed_10k_context"
    return source.actionability_tier


def _clean_sequence(row: dict[str, Any]) -> bool:
    times = [
        _num(row.get("first_crossed_10k_time")),
        _num(row.get("first_crossed_20k_time")),
        _num(row.get("first_crossed_50k_time")),
        _num(row.get("first_crossed_100k_time")),
        _num(row.get("first_crossed_500k_time")),
        _num(row.get("first_crossed_1m_time")),
    ]
    present = [value for value in times if value is not None]
    return bool(present) and present == sorted(present) and not _same_timestamp(row.get("first_crossed_20k_time"), row.get("first_crossed_1m_time"))


def _same_timestamp(left: Any, right: Any) -> bool:
    return _num(left) is not None and _num(right) is not None and _num(left) == _num(right)


def _delta(left: Any, right: Any) -> float | None:
    a = _num(left)
    b = _num(right)
    if a is None or b is None:
        return None
    return b - a


def _ratio(a: Any, b: Any) -> float | None:
    left = _num(a)
    right = _num(b)
    if left is None or right is None or right == 0:
        return None
    return left / right


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "y"}
    return False


def _coverage(rows: list[dict[str, Any]], keys: list[str]) -> float:
    if not rows:
        return 0.0
    covered = 0
    for row in rows:
        if any(row.get(key) not in {None, "", False} for key in keys):
            covered += 1
    return round(covered / len(rows), 4)


def _count_bool(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) is True or _boolish(row.get(key)))


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(key) is True or _boolish(row.get(key))) / len(rows), 4)


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 6) if values else None


def _median_field(rows: list[dict[str, Any]], key: str) -> float | None:
    return _median([value for value in (_num(row.get(key)) for row in rows) if value is not None])


def _contexts(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "all_observed": rows,
        "all_crossed_20k": [row for row in rows if row.get("crossed_20k") is True],
        "actionable_crossed_20k": [row for row in rows if row.get("actionability_tier") == "actionable_crossed_20k"],
        "historical": [row for row in rows if "historical" in str(row.get("data_quality_tier"))],
        "forward": [row for row in rows if "forward" in str(row.get("data_quality_tier")) or "official" in str(row.get("data_quality_tier"))],
    }


def _runner_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "crossed_20k_not_50k": [row for row in rows if row.get("crossed_20k") and not row.get("crossed_50k")],
        "crossed_50k_not_100k": [row for row in rows if row.get("crossed_50k") and not row.get("crossed_100k")],
        "crossed_100k_not_500k": [row for row in rows if row.get("crossed_100k") and not row.get("crossed_500k")],
        "crossed_500k_not_1m": [row for row in rows if row.get("crossed_500k") and not row.get("crossed_1m")],
        "crossed_1m": [row for row in rows if row.get("crossed_1m")],
    }


def _metadata_interpretation(rows: list[dict[str, Any]]) -> str:
    if len(rows) < 10:
        return "metadata_coverage_or_group_support_sparse"
    if _median_field(rows, "social_link_count") and (_median_field(rows, "social_link_count") or 0) >= 2:
        return "social_links_present_in_group"
    return "no_clear_metadata_social_separation"


def _direction(high: float | None, weak: float | None) -> str:
    if high is None or weak is None:
        return "insufficient_coverage"
    if high > weak:
        return "higher_in_high_runners"
    if high < weak:
        return "lower_in_high_runners"
    return "no_median_difference"


def _effect_proxy(high: float | None, weak: float | None) -> float | None:
    if high is None or weak is None:
        return None
    return round(high - weak, 6)


def _source_consistency(rows: list[dict[str, Any]], feature: str) -> str:
    covered_sources = {row.get("source_dataset") for row in rows if _num(row.get(feature)) is not None}
    if len(covered_sources) >= 3:
        return "multi_source_covered"
    if covered_sources:
        return "single_or_limited_source"
    return "not_covered"


def _feature_actionability_tier(feature: str) -> str:
    if feature in {"no_reclaim_after_10m"}:
        return "exit_side_only"
    if feature in {"social_link_count", "metadata_completeness_score"}:
        return "entry_side_if_early_available"
    return "entry_side_candidate"


def _historical_forward_agree(rows: list[dict[str, Any]], feature: str) -> str:
    historical = [row for row in rows if "historical" in str(row.get("data_quality_tier")) and _num(row.get(feature)) is not None]
    forward = [row for row in rows if "historical" not in str(row.get("data_quality_tier")) and _num(row.get(feature)) is not None]
    if historical and forward:
        return "both_have_coverage"
    if historical:
        return "historical_only"
    if forward:
        return "forward_only"
    return "not_available"


def _feature_classification(feature: str, high_values: list[float], weak_values: list[float], family: str) -> str:
    if len(high_values) + len(weak_values) < 10:
        return "data_limited"
    if family == "I_drawdown_reclaim":
        return "path_exit_candidate"
    if "FDV" in family and high_values and weak_values:
        return "strong_cross_sample_candidate"
    if family in {"H_synthetic_timing", "F_holder_top_holder"}:
        return "possible_risk_filter"
    return "forward_promising_candidate"


def _drawdown_interpretation(level: int, recoverable: list[dict[str, Any]], terminal: list[dict[str, Any]]) -> str:
    if not recoverable and not terminal:
        return f"{level}pct_drawdown_support_sparse"
    if len(terminal) > len(recoverable):
        return f"{level}pct_drawdowns_more_often_terminal_or_unreclaimed_in_available_rows"
    return f"{level}pct_drawdowns_include_recoverable_cases; avoid treating every dip as terminal"


def _finding_from_comparison(rows: list[dict[str, Any]], feature: str) -> str:
    match = next((row for row in rows if row.get("feature") == feature), None)
    if not match or match.get("classification") == "data_limited":
        return "FDV efficiency remains visible but coverage is uneven across sources."
    return f"{feature} classified as {match['classification']} with direction {match['direction']}."


def _metadata_summary(rows: list[dict[str, Any]]) -> str:
    crossed_1m = next((row for row in rows if row.get("runner_group") == "crossed_1m" and row.get("context") == "all_observed"), None)
    if not crossed_1m:
        return "Metadata/social coverage is sparse or unavailable."
    return f"Crossed-1M group median social_link_count={crossed_1m.get('median_social_link_count')}; interpretation={crossed_1m.get('interpretation')}."


def _high_runner_summary(rows: list[dict[str, Any]]) -> str:
    strong = [row["feature"] for row in rows if row.get("classification") == "strong_cross_sample_candidate"]
    if strong:
        return f"Strongest descriptive candidates: {', '.join(strong[:4])}."
    return "No high-runner feature has enough clean cross-sample support to call strong."


def _fall_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Drawdown/recovery support is sparse."
    return "; ".join(str(row.get("interpretation")) for row in rows[:2])


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            out[key] = None
        else:
            out[key] = value
    return out


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _parquet_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)
