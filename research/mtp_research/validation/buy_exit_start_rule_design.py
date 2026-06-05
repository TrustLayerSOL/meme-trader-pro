"""Fixed buy/exit paper-shadow start-rule design for forward lifecycle data.

This module produces descriptive FDV-path diagnostics and a disabled
paper/shadow config only. It does not contain wallet, signing, order-routing,
or live execution behavior.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_root


SNAPSHOT_LABEL = "combined_actionable_crossed20k_buy_exit_design"
SOURCE_SAMPLE = "fixed_5hr_plus_12hr_combined_20260605"
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
FDV_PROXY_ANOMALY_HIGH = 100_000_000.0

GUARDRAILS = [
    "research_forward_observation_only",
    "no_private_keys",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_order_routing",
    "no_live_trading",
    "no_enabled_paper_trading",
    "no_profitability_claims",
    "no_threshold_optimization",
    "no_grid_search",
    "no_validation",
]

BUY_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "B1",
        "name": "10k aggressive efficiency entry",
        "trigger_level": "10k",
        "bucket_method": "fixed_high_bucket_no_grid_search",
        "definition": "observed 10k crossing, first path before 10k, high 10k FDV efficiency, valid path provenance, and 10k chase guard",
        "chase_guard": "entry FDV at first 10k row must be at or below 15k",
    },
    {
        "rule_id": "B2",
        "name": "15k balanced speed/efficiency entry",
        "trigger_level": "15k",
        "bucket_method": "fixed_high_bucket_no_grid_search",
        "definition": "observed 15k crossing, early path, high 15k efficiency proxy, clean 10k-to-15k path or not-slow create-to-15k, and non-elevated sell count",
        "chase_guard": "entry FDV at first 15k row must be at or below 20k",
    },
    {
        "rule_id": "B3",
        "name": "20k confirmation efficiency entry",
        "trigger_level": "20k",
        "bucket_method": "fixed_high_bucket_no_grid_search",
        "definition": "observed 20k crossing, first path before 20k, high 20k FDV efficiency, observed 10k-to-20k path, and no next-milestone chase",
        "chase_guard": "entry FDV at first 20k row must be at or below 30k",
    },
    {
        "rule_id": "B4",
        "name": "20k conservative continuation entry",
        "trigger_level": "20k",
        "bucket_method": "fixed_high_bucket_no_grid_search",
        "definition": "B3 plus reached 30k or clean post-20k continuation within five minutes when path data supports it",
        "chase_guard": "entry is delayed confirmation and is marked lower-coverage if continuation is not observed",
    },
]

EXIT_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "E1",
        "name": "30pct drawdown no-reclaim exit",
        "definition": "after hypothetical entry, track local high; if 30 percent drawdown occurs and prior high is not reclaimed within 10 minutes, mark hypothetical exit",
    },
    {
        "rule_id": "E2",
        "name": "milestone trailing drawdown with grace",
        "definition": "fixed milestone tiers: before 50k severe no-reclaim, after 50k 40 percent/10m, after 100k 35 percent/10m, after 500k 30 percent/5m",
    },
    {
        "rule_id": "E3",
        "name": "inactivity / max-age fallback exit",
        "definition": "mark fallback exit for inactive timeout, max age, or terminal collapse lifecycle states",
    },
    {
        "rule_id": "E4",
        "name": "milestone take-profit / runner-hold diagnostic",
        "definition": "diagnostic comparator only for 50k, 100k, 500k, and 1M milestone capture",
    },
]


@dataclass(frozen=True)
class SnapshotRows:
    source_root: Path
    births: list[dict[str, Any]]
    paths: list[dict[str, Any]]
    events: list[dict[str, Any]]
    metadata: list[dict[str, Any]]
    drawdowns: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    state: dict[str, Any]
    manifest: dict[str, Any]


def run_buy_exit_start_rule_design(
    *,
    data_root: Path | str | None = None,
    source_root: Path | str | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    requested_source = Path(source_root).expanduser() if source_root else None
    report_root = root / "data" / "backtests" / "diagnostics" / "reports" / "forward_observation" / "buy_exit_design"
    snapshot_root = root / "data" / "forward_observation" / "snapshots" / SNAPSHOT_LABEL
    config_path = root / "data" / "forward_observation" / "official_lifecycle_watch_v1" / "paper_shadow_starting_config.json"
    if not execute:
        source = requested_source or root / "data" / "forward_observation" / "combined_samples" / SOURCE_SAMPLE
        return {
            "execute": False,
            "snapshot_label": SNAPSHOT_LABEL,
            "source_root": str(source),
            "report_root": str(report_root),
            "readiness": "buy_exit_start_rule_design_ready_for_execute",
        }
    source = _resolve_source_root(root, requested_source)

    report_root.mkdir(parents=True, exist_ok=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)
    rows = load_snapshot_rows(source)
    snapshot_manifest = build_snapshot_manifest(source, rows)
    freeze_snapshot(source, snapshot_root, snapshot_manifest)
    dataset = build_design_dataset(rows)
    quality = build_quality_gate(rows, dataset)
    buy_comparison = build_buy_candidate_comparison(dataset)
    exit_comparison = build_exit_candidate_comparison(dataset)
    combo = build_what_if_comparison(dataset, BUY_RULES, EXIT_RULES[:3])
    selected = select_starting_config(buy_comparison, combo, quality)
    disabled_config = build_disabled_paper_config(
        selected["selected_buy_rule_id"],
        selected["selected_exit_rule_id"],
        quality_result=selected["readiness_classification"],
    )
    written = write_reports(
        report_root=report_root,
        dataset=dataset,
        quality=quality,
        buy_comparison=buy_comparison,
        exit_comparison=exit_comparison,
        combo=combo,
        selected=selected,
        disabled_config=disabled_config,
        snapshot_manifest=snapshot_manifest,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config_path, disabled_config)
    status_path = write_status_file(
        snapshot_manifest=snapshot_manifest,
        quality=quality,
        selected=selected,
        config_path=config_path,
        report_root=report_root,
    )
    summary = {
        "execute": True,
        "snapshot_label": SNAPSHOT_LABEL,
        "snapshot_source": str(source),
        "snapshot_dir": str(snapshot_root),
        "all_crossed_20k_count": snapshot_manifest["all_crossed_20k_count"],
        "actionable_crossed_20k_count": snapshot_manifest["actionable_crossed_20k_count"],
        "quality_gate_result": quality["quality_gate_result"],
        "buy_candidates_compared": [rule["rule_id"] for rule in BUY_RULES],
        "exit_candidates_compared": [rule["rule_id"] for rule in EXIT_RULES],
        "selected_buy_rule_id": selected["selected_buy_rule_id"],
        "selected_exit_rule_id": selected["selected_exit_rule_id"],
        "readiness_classification": selected["readiness_classification"],
        "disabled_config_path": str(config_path),
        "report_paths": {key: str(value) for key, value in written.items()},
        "status_file": str(status_path),
    }
    _write_json(report_root / "buy_exit_start_rule_design_summary.json", summary)
    (report_root / "buy_exit_start_rule_design_summary.md").write_text(
        _summary_markdown(summary, quality, selected),
        encoding="utf-8",
    )
    return summary


def load_snapshot_rows(source_root: Path | str) -> SnapshotRows:
    source = Path(source_root).expanduser()
    return SnapshotRows(
        source_root=source,
        births=_read_jsonl(source / "births.jsonl"),
        paths=_read_jsonl(source / "followup_paths.jsonl"),
        events=_read_jsonl(source / "events.jsonl"),
        metadata=_read_jsonl(source / "metadata.jsonl"),
        drawdowns=_read_jsonl(source / "drawdowns.jsonl"),
        transitions=_read_jsonl(source / "lifecycle_transitions.jsonl"),
        state=_read_json(source / "lifecycle_state.json"),
        manifest=_read_json(source / "official_lifecycle_manifest.json"),
    )


def build_snapshot_manifest(source_root: Path | str, rows: SnapshotRows) -> dict[str, Any]:
    birth_by_mint = _birth_by_mint(rows.births)
    paths_by_mint = _paths_by_mint(rows.paths)
    crossed = sorted(mint for mint, mint_paths in paths_by_mint.items() if any(_crossed(path, "20k") for path in mint_paths))
    actionable = sorted(mint for mint in crossed if birth_by_mint.get(mint, {}).get("fdv_path_before_20k") is True)
    duplicates = sorted([mint for mint, count in Counter(row.get("mint") for row in rows.births if row.get("mint")).items() if count > 1])
    path_row_mints = {row.get("mint") for row in rows.paths if row.get("mint")}
    state_mints = set((rows.state.get("mints") or {}).keys()) if isinstance(rows.state.get("mints"), dict) else set()
    return {
        "snapshot_label": SNAPSHOT_LABEL,
        "created_at": _utc_now(),
        "source_root": str(Path(source_root).expanduser()),
        "source_files": {
            "births": str(Path(source_root).expanduser() / "births.jsonl"),
            "followup_paths": str(Path(source_root).expanduser() / "followup_paths.jsonl"),
            "metadata": str(Path(source_root).expanduser() / "metadata.jsonl"),
            "lifecycle_state": str(Path(source_root).expanduser() / "lifecycle_state.json"),
        },
        "all_crossed_20k_count": len(crossed),
        "actionable_crossed_20k_count": len(actionable),
        "main_analysis_population": "actionable_crossed_20k",
        "secondary_context_population": "all_crossed_20k",
        "unique_mints": len({row.get("mint") for row in rows.births if row.get("mint")}),
        "duplicate_mints": duplicates,
        "path_row_availability": {
            "path_rows": len(rows.paths),
            "crossed_20k_mints_with_path_rows": len([mint for mint in crossed if mint in path_row_mints]),
            "actionable_mints_with_path_rows": len([mint for mint in actionable if mint in path_row_mints]),
        },
        "trigger_provenance": dict(Counter(str(row.get("source_provenance") or "unknown") for row in rows.paths if row.get("mint") in crossed)),
        "first_path_before_trigger": {
            "before_10k": sum(1 for mint in actionable if birth_by_mint.get(mint, {}).get("fdv_path_before_10k") is True),
            "before_20k": sum(1 for mint in actionable if birth_by_mint.get(mint, {}).get("fdv_path_before_20k") is True),
        },
        "lifecycle_path_maturity_coverage": dict(Counter(_state_for_mint(rows.state, mint) or "unknown" for mint in actionable)),
        "active_matured_state_coverage": {
            "active": sum(1 for mint in actionable if _state_for_mint(rows.state, mint) == "trigger_qualified_active_watch"),
            "matured": sum(1 for mint in actionable if str(_state_for_mint(rows.state, mint) or "").startswith("matured_")),
            "data_limited": sum(1 for mint in actionable if _state_for_mint(rows.state, mint) == "data_limited"),
        },
        "limitations": [
            "fixed-rule design only",
            "not validation",
            "not profitability evidence",
            "FDV proxy path outcomes are not realized PnL",
            "combined snapshot is frozen and may lag live collector progress",
        ],
    }


def freeze_snapshot(source_root: Path, snapshot_root: Path, manifest: dict[str, Any]) -> None:
    for filename in [
        "births.jsonl",
        "followup_paths.jsonl",
        "events.jsonl",
        "metadata.jsonl",
        "drawdowns.jsonl",
        "lifecycle_transitions.jsonl",
        "lifecycle_state.json",
        "official_lifecycle_manifest.json",
    ]:
        src = source_root / filename
        if src.exists():
            shutil.copy2(src, snapshot_root / filename)
    _write_json(snapshot_root / "snapshot_manifest.json", manifest)
    (snapshot_root / "snapshot_manifest.md").write_text(_manifest_markdown(manifest), encoding="utf-8")


def build_design_dataset(rows: SnapshotRows) -> list[dict[str, Any]]:
    birth_by_mint = _birth_by_mint(rows.births)
    paths_by_mint = _paths_by_mint(rows.paths)
    metadata_by_mint = {row.get("mint"): row for row in rows.metadata if row.get("mint")}
    actionable = sorted(
        mint
        for mint, mint_paths in paths_by_mint.items()
        if any(_crossed(path, "20k") for path in mint_paths) and birth_by_mint.get(mint, {}).get("fdv_path_before_20k") is True
    )
    dataset: list[dict[str, Any]] = []
    for mint in actionable:
        birth = birth_by_mint.get(mint, {})
        mint_paths = sorted(paths_by_mint[mint], key=lambda row: _num(row.get("timestamp")) or 0)
        meta = metadata_by_mint.get(mint, {})
        create_time = _num(birth.get("create_time"))
        row: dict[str, Any] = {
            "mint": mint,
            "source_sample": birth.get("sample_label") or rows.manifest.get("sample_label") or SOURCE_SAMPLE,
            "actionable_sample_flag": True,
            "create_time": create_time,
            "first_followup_time": _num(birth.get("first_followup_attempt_time") or birth.get("account_watch_started_at")),
            "freshness_class": birth.get("freshness_class"),
            "first_path_before_10k": birth.get("fdv_path_before_10k") is True or birth.get("first_followup_before_10k") is True,
            "first_path_before_15k": _first_path_before_level(birth, "15k"),
            "first_path_before_20k": birth.get("fdv_path_before_20k") is True or birth.get("first_followup_before_20k") is True,
            "maturity_state": _state_for_mint(rows.state, mint),
            "path_row_count": len(mint_paths),
            "source_provenance": _first_non_null(mint_paths, "source_provenance") or birth.get("source_provenance"),
            "fdv_anomaly": any(_fdv_anomaly(path.get("fdv_proxy")) for path in mint_paths),
        }
        for level in TARGET_LEVELS:
            cross_row = _first_cross_row(mint_paths, level)
            row[f"crossed_{level}"] = cross_row is not None
            row[f"first_crossed_{level}_time"] = _num(cross_row.get("timestamp")) if cross_row else None
        row["create_to_10k_seconds"] = _delta(create_time, row["first_crossed_10k_time"])
        row["create_to_15k_seconds"] = _delta(create_time, row["first_crossed_15k_time"])
        row["create_to_20k_seconds"] = _delta(create_time, row["first_crossed_20k_time"])
        row["10k_to_15k_seconds"] = _delta(row["first_crossed_10k_time"], row["first_crossed_15k_time"])
        row["10k_to_20k_seconds"] = _delta(row["first_crossed_10k_time"], row["first_crossed_20k_time"])
        row["15k_to_20k_seconds"] = _delta(row["first_crossed_15k_time"], row["first_crossed_20k_time"])
        for level in ["10k", "15k", "20k"]:
            cross_row = _first_cross_row(mint_paths, level)
            for out_field, source_field in {
                f"fdv_at_{level}": "fdv_proxy",
                f"fdv_per_event_at_{level}": "fdv_per_event",
                f"fdv_per_buy_at_{level}": "fdv_per_buy",
                f"fdv_per_active_wallet_at_{level}": "fdv_per_active_wallet",
                f"event_count_at_{level}": "event_count",
                f"buy_count_at_{level}": "buy_count",
                f"sell_count_at_{level}": "sell_count",
                f"active_wallets_at_{level}": "active_wallet_count",
                f"buy_sell_ratio_at_{level}": "buy_sell_ratio",
            }.items():
                row[out_field] = _num(cross_row.get(source_field)) if cross_row else None
        row.update(_exit_features(mint_paths))
        row.update(_metadata_features(meta, birth))
        dataset.append(row)
    return dataset


def build_quality_gate(rows: SnapshotRows, dataset: list[dict[str, Any]]) -> dict[str, Any]:
    birth_by_mint = _birth_by_mint(rows.births)
    paths_by_mint = _paths_by_mint(rows.paths)
    crossed = sorted(mint for mint, mint_paths in paths_by_mint.items() if any(_crossed(path, "20k") for path in mint_paths))
    actionable = {row["mint"] for row in dataset}
    duplicates = sorted([mint for mint, count in Counter(row.get("mint") for row in rows.births if row.get("mint")).items() if count > 1])
    missing_trigger = [row["mint"] for row in dataset if row.get("first_crossed_20k_time") is None]
    missing_path = [mint for mint in actionable if not paths_by_mint.get(mint)]
    stale = [row["mint"] for row in dataset if row.get("first_path_before_20k") is not True]
    ordering = [row["mint"] for row in dataset if _milestone_order_bad(row)]
    same_ts = [row["mint"] for row in dataset if _same_timestamp_multi_milestone(row)]
    fdv_anomalies = [row["mint"] for row in dataset if row.get("fdv_anomaly") is True]
    missing_exit = [row["mint"] for row in dataset if row.get("path_row_count", 0) < 2 or row.get("max_fdv_after_20k") is None]
    states = Counter(str(row.get("maturity_state") or "unknown") for row in dataset)
    data_limited_rows = [row["mint"] for row in dataset if row.get("maturity_state") == "data_limited"]
    severe = duplicates + missing_trigger + missing_path + fdv_anomalies
    result = "paper_start_candidate_data_limited" if severe or len(dataset) < 50 else "paper_start_candidate_ready_disabled"
    return {
        "quality_gate_result": result,
        "actionable_rows": len(dataset),
        "non_actionable_rows": len(crossed) - len(actionable),
        "duplicate_mints": duplicates,
        "missing_trigger_rows": missing_trigger,
        "missing_path_rows": missing_path,
        "missing_exit_path_maturity": missing_exit,
        "stale_trigger_rows": stale,
        "milestone_ordering_violations": ordering,
        "same_timestamp_multi_milestone_jumps": same_ts,
        "fdv_proxy_anomalies": fdv_anomalies,
        "active_matured_split": {
            "active": states.get("trigger_qualified_active_watch", 0),
            "matured": sum(count for state, count in states.items() if state.startswith("matured_")),
            "data_limited": states.get("data_limited", 0),
            "unknown": states.get("unknown", 0),
        },
        "data_limited_rows": data_limited_rows,
        "first_path_before_20k_count": sum(1 for mint in actionable if birth_by_mint.get(mint, {}).get("fdv_path_before_20k") is True),
        "sample_limitations": [
            "fixed forward snapshot only",
            "descriptive what-if only",
            "thresholds use fixed high buckets, not outcome fitting",
        ],
    }


def build_buy_candidate_comparison(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = _bucket_thresholds(dataset)
    rows = []
    for rule in BUY_RULES:
        eligible = [_apply_buy_rule(row, rule["rule_id"], buckets) for row in dataset]
        selected = [item for item in eligible if item["eligible"]]
        selected_rows = [item["row"] for item in selected]
        rows.append(
            {
                "rule_id": rule["rule_id"],
                "name": rule["name"],
                "bucket_method": rule["bucket_method"],
                "eligible_rows": len(dataset),
                "hypothetical_entries": len(selected_rows),
                "skipped_rows": len(dataset) - len(selected_rows),
                "data_limited_rows": sum(1 for item in eligible if item["data_limited"]),
                "entry_fdv_median": _median([_entry_fdv(row, rule["trigger_level"]) for row in selected_rows]),
                "entry_fdv_iqr": json.dumps(_iqr([_entry_fdv(row, rule["trigger_level"]) for row in selected_rows]), sort_keys=True),
                "reached_50k_after_entry": sum(1 for row in selected_rows if row.get("crossed_50k")),
                "reached_100k_after_entry": sum(1 for row in selected_rows if row.get("crossed_100k")),
                "reached_500k_after_entry": sum(1 for row in selected_rows if row.get("crossed_500k")),
                "reached_1m_after_entry": sum(1 for row in selected_rows if row.get("crossed_1m")),
                "median_max_fdv_multiple": _median([_max_multiple(row, rule["trigger_level"]) for row in selected_rows]),
                "median_max_drawdown_after_entry": _median([_num(row.get("max_drawdown_after_20k")) for row in selected_rows]),
                "limitations": "fixed high-bucket descriptive comparison; not validation or profitability evidence",
            }
        )
    return rows


def build_exit_candidate_comparison(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for rule in EXIT_RULES:
        rows.append(
            {
                "rule_id": rule["rule_id"],
                "name": rule["name"],
                "eligible_rows": len(dataset),
                "rows_with_drawdown_path": sum(1 for row in dataset if _num(row.get("max_drawdown_after_20k")) is not None),
                "terminal_collapse_proxy_count": sum(1 for row in dataset if row.get("terminal_collapse_proxy") is True),
                "inactive_timeout_count": sum(1 for row in dataset if row.get("inactive_timeout") is True),
                "runner_capture_100k": sum(1 for row in dataset if row.get("crossed_100k")),
                "runner_capture_500k": sum(1 for row in dataset if row.get("crossed_500k")),
                "runner_capture_1m": sum(1 for row in dataset if row.get("crossed_1m")),
                "limitations": "exit rule is fixed descriptive paper-shadow design only",
            }
        )
    return rows


def build_what_if_comparison(
    dataset: list[dict[str, Any]],
    buy_rules: list[dict[str, Any]],
    exit_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets = _bucket_thresholds(dataset)
    out = []
    for buy_rule in buy_rules:
        entry_rows = [item["row"] for item in (_apply_buy_rule(row, buy_rule["rule_id"], buckets) for row in dataset) if item["eligible"]]
        for exit_rule in exit_rules:
            sims = [_simulate_exit(row, buy_rule, exit_rule) for row in entry_rows]
            reasons = Counter(sim["exit_reason"] for sim in sims)
            out.append(
                {
                    "buy_rule_id": buy_rule["rule_id"],
                    "exit_rule_id": exit_rule["rule_id"],
                    "label": "FDV path multiple, not realized PnL",
                    "eligible_rows": len(dataset),
                    "hypothetical_entries": len(entry_rows),
                    "skipped_rows": len(dataset) - len(entry_rows),
                    "data_limited_rows": sum(1 for row in entry_rows if row.get("path_row_count", 0) < 2),
                    "entry_fdv_median": _median([sim["entry_fdv"] for sim in sims]),
                    "entry_fdv_iqr": json.dumps(_iqr([sim["entry_fdv"] for sim in sims]), sort_keys=True),
                    "reached_50k_after_entry": sum(1 for row in entry_rows if row.get("crossed_50k")),
                    "reached_100k_after_entry": sum(1 for row in entry_rows if row.get("crossed_100k")),
                    "reached_500k_after_entry": sum(1 for row in entry_rows if row.get("crossed_500k")),
                    "reached_1m_after_entry": sum(1 for row in entry_rows if row.get("crossed_1m")),
                    "max_fdv_multiple_after_entry": _max([sim["max_fdv_multiple"] for sim in sims]),
                    "median_max_fdv_multiple": _median([sim["max_fdv_multiple"] for sim in sims]),
                    "median_max_drawdown_after_entry": _median([_num(row.get("max_drawdown_after_20k")) for row in entry_rows]),
                    "exits_by_reason": json.dumps(dict(reasons), sort_keys=True),
                    "median_exit_fdv_multiple_if_computable": _median([sim["exit_multiple"] for sim in sims]),
                    "runner_miss_count": sum(1 for sim in sims if sim["runner_missed"]),
                    "exited_before_100k_count": sum(1 for sim in sims if sim["exit_before_100k"]),
                    "exited_before_500k_count": sum(1 for sim in sims if sim["exit_before_500k"]),
                    "held_through_500k_count": sum(1 for sim in sims if sim["held_through_500k"]),
                    "held_through_1m_count": sum(1 for sim in sims if sim["held_through_1m"]),
                    "open_incomplete_count": reasons.get("open_or_incomplete", 0),
                    "sample_limitations": "path-based descriptive what-if; not PnL, not validation, not deployment",
                }
            )
    return out


def select_starting_config(
    buy_comparison: list[dict[str, Any]],
    combo: list[dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, Any]:
    preferred_buy_order = ["B3", "B2", "B1", "B4"]
    available = {row["rule_id"]: row for row in buy_comparison if row.get("hypothetical_entries", 0) > 0}
    selected_buy = next((rule for rule in preferred_buy_order if rule in available), "B3")
    selected_exit = "E2"
    selected_combo = next((row for row in combo if row["buy_rule_id"] == selected_buy and row["exit_rule_id"] == selected_exit), {})
    readiness = quality["quality_gate_result"]
    if not selected_combo or selected_combo.get("hypothetical_entries", 0) < 10:
        readiness = "paper_start_candidate_data_limited"
    return {
        "selected_buy_rule_id": selected_buy,
        "selected_exit_rule_id": selected_exit,
        "readiness_classification": readiness,
        "why_selected": "20k confirmation efficiency has interpretable milestone confirmation and avoids the earliest 10k chase while E2 preserves runner potential with fixed milestone trailing grace.",
        "why_not_others": {
            "B1": "earlier and potentially useful, but more exposed to same-timestamp jumps and stale/chase behavior",
            "B2": "balanced fallback, but 15k path fields are less explicit in the current lifecycle rows",
            "B4": "conservative continuation can be too late and lower coverage",
            "E1": "single 30 percent drawdown rule can cut runners before higher milestones",
            "E3": "kept as fallback, not primary exit behavior",
            "E4": "diagnostic comparator only",
        },
        "risks": [
            "current sample is a forward snapshot, not validation",
            "FDV path multiples are not tradable PnL",
            "reclaim and inactivity evidence depends on path density",
            "future clean forward sample must confirm live field availability",
        ],
        "future_confirmation_needed": [
            "live first-path-before-trigger fidelity",
            "same-timestamp milestone jump handling",
            "drawdown reclaim timer accuracy",
            "entry decision FDV chase guard behavior",
        ],
        "live_fields_to_track": [
            "mint",
            "timestamp",
            "fdv_proxy",
            "crossed milestone flags",
            "fdv_per_event",
            "fdv_per_active_wallet",
            "buy_count",
            "sell_count",
            "active_wallet_count",
            "local_high_fdv",
            "drawdown_pct",
            "reclaim_status",
        ],
    }


def build_disabled_paper_config(selected_buy_rule_id: str, selected_exit_rule_id: str, *, quality_result: str) -> dict[str, Any]:
    buy_rule = next(rule for rule in BUY_RULES if rule["rule_id"] == selected_buy_rule_id)
    exit_rule = next(rule for rule in EXIT_RULES if rule["rule_id"] == selected_exit_rule_id)
    return {
        "enabled": False,
        "sample_source": "combined_actionable_snapshot",
        "selected_buy_rule_id": selected_buy_rule_id,
        "selected_exit_rule_id": selected_exit_rule_id,
        "buy_rule_definition": buy_rule,
        "exit_rule_definition": exit_rule,
        "chase_guard": buy_rule["chase_guard"],
        "data_quality_requirements": [
            "actionable crossed-20k snapshot row",
            "first path before selected trigger",
            "valid FDV path provenance",
            "no FDV proxy anomaly",
            "drawdown/local-high path rows available for exit tracking",
        ],
        "guardrails": GUARDRAILS,
        "disabled_reason": "paper/shadow start config is design-only until future clean forward sample confirms field coverage",
        "next_enable_condition": "operator explicitly enables paper-shadow after active official lifecycle sample reaches target and quality gate remains acceptable",
        "no_pnl_claims": True,
        "no_live_execution": True,
    }


def write_reports(
    *,
    report_root: Path,
    dataset: list[dict[str, Any]],
    quality: dict[str, Any],
    buy_comparison: list[dict[str, Any]],
    exit_comparison: list[dict[str, Any]],
    combo: list[dict[str, Any]],
    selected: dict[str, Any],
    disabled_config: dict[str, Any],
    snapshot_manifest: dict[str, Any],
) -> dict[str, Path]:
    outputs = {
        "dataset_jsonl": report_root / "buy_exit_design_dataset.jsonl",
        "dataset_parquet": report_root / "buy_exit_design_dataset.parquet",
        "quality_json": report_root / "buy_exit_quality_gate.json",
        "quality_md": report_root / "buy_exit_quality_gate.md",
        "buy_csv": report_root / "buy_candidate_comparison.csv",
        "exit_csv": report_root / "exit_candidate_comparison.csv",
        "combo_csv": report_root / "buy_exit_combo_what_if.csv",
        "selected_csv": report_root / "selected_paper_start_config_summary.csv",
    }
    _write_jsonl(outputs["dataset_jsonl"], dataset)
    pd.DataFrame(dataset).to_parquet(outputs["dataset_parquet"], index=False)
    _write_json(outputs["quality_json"], quality)
    outputs["quality_md"].write_text(_quality_markdown(quality), encoding="utf-8")
    _write_csv(outputs["buy_csv"], buy_comparison)
    _write_csv(outputs["exit_csv"], exit_comparison)
    _write_csv(outputs["combo_csv"], combo)
    _write_csv(
        outputs["selected_csv"],
        [
            {
                "selected_buy_rule_id": selected["selected_buy_rule_id"],
                "selected_exit_rule_id": selected["selected_exit_rule_id"],
                "readiness_classification": selected["readiness_classification"],
                "actionable_crossed_20k_count": snapshot_manifest["actionable_crossed_20k_count"],
                "enabled": disabled_config["enabled"],
            }
        ],
    )
    return outputs


def write_status_file(
    *,
    snapshot_manifest: dict[str, Any],
    quality: dict[str, Any],
    selected: dict[str, Any],
    config_path: Path,
    report_root: Path,
) -> Path:
    status_path = Path("theses") / "BUY_EXIT_START_RULE_DESIGN_STATUS.md"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        "\n".join(
            [
                "# Buy/Exit Start Rule Design Status",
                "",
                f"Sample used: `{snapshot_manifest['source_root']}`",
                f"All crossed-20k count: `{snapshot_manifest['all_crossed_20k_count']}`",
                f"Actionable crossed-20k count: `{snapshot_manifest['actionable_crossed_20k_count']}`",
                f"Quality gate result: `{quality['quality_gate_result']}`",
                f"Buy candidates compared: `{[rule['rule_id'] for rule in BUY_RULES]}`",
                f"Exit candidates compared: `{[rule['rule_id'] for rule in EXIT_RULES]}`",
                f"Selected paper/shadow starting config: `{selected['selected_buy_rule_id']} + {selected['selected_exit_rule_id']}`",
                f"Disabled config path: `{config_path}`",
                f"Report root: `{report_root}`",
                "",
                "Limitations: fixed-rule comparison only; no threshold optimization; no validation; FDV path multiples are not realized PnL.",
                "",
                "No paper trades, live trades, wallet execution, transaction signing, order routing, buy orders, or sell orders were run.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return status_path


def _resolve_source_root(root: Path, source_root: Path | None) -> Path:
    if source_root:
        return source_root
    preferred = root / "data" / "forward_observation" / "combined_samples" / SOURCE_SAMPLE
    if preferred.exists():
        return preferred
    candidates = sorted((root / "data" / "forward_observation" / "combined_samples").glob("*"))
    for candidate in reversed(candidates):
        if not (candidate / "births.jsonl").exists() or not (candidate / "followup_paths.jsonl").exists():
            continue
        rows = load_snapshot_rows(candidate)
        manifest = build_snapshot_manifest(candidate, rows)
        if 400 <= manifest["all_crossed_20k_count"] <= 470 and 170 <= manifest["actionable_crossed_20k_count"] <= 215:
            return candidate
    raise FileNotFoundError("No combined actionable snapshot around 438/192 was found")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _birth_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("mint")): row for row in rows if row.get("mint")}


def _paths_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("mint"):
            grouped[str(row["mint"])].append(row)
    return grouped


def _state_for_mint(state: dict[str, Any], mint: str) -> str | None:
    mints = state.get("mints") if isinstance(state, dict) else {}
    row = mints.get(mint, {}) if isinstance(mints, dict) else {}
    return row.get("state")


def _crossed(row: dict[str, Any], level: str) -> bool:
    return row.get(f"crossed_{level}") is True or (_num(row.get("fdv_proxy")) is not None and (_num(row.get("fdv_proxy")) or 0) >= TARGET_LEVELS[level])


def _first_cross_row(paths: list[dict[str, Any]], level: str) -> dict[str, Any] | None:
    return next((row for row in sorted(paths, key=lambda item: _num(item.get("timestamp")) or 0) if _crossed(row, level)), None)


def _first_path_before_level(birth: dict[str, Any], level: str) -> bool:
    first_fdv = _num(birth.get("first_fdv_path_fdv"))
    if first_fdv is not None:
        return first_fdv < TARGET_LEVELS[level]
    if level == "15k":
        return birth.get("fdv_path_before_20k") is True
    return birth.get(f"fdv_path_before_{level}") is True


def _exit_features(paths: list[dict[str, Any]]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for level in ["10k", "15k", "20k"]:
        cross = _first_cross_row(paths, level)
        after = [row for row in paths if cross and (_num(row.get("timestamp")) or 0) >= (_num(cross.get("timestamp")) or 0)]
        features[f"max_fdv_after_{level}"] = _max([_num(row.get("fdv_proxy")) for row in after])
    cross20 = _first_cross_row(paths, "20k")
    after20 = [row for row in paths if cross20 and (_num(row.get("timestamp")) or 0) >= (_num(cross20.get("timestamp")) or 0)]
    peak = max(after20, key=lambda row: _num(row.get("fdv_proxy")) or -1, default=None)
    features["time_to_peak_after_20k"] = _delta(_num(cross20.get("timestamp")) if cross20 else None, _num(peak.get("timestamp")) if peak else None)
    features["max_drawdown_after_20k"] = _max([_num(row.get("drawdown_pct")) for row in after20])
    for pct in [20, 30, 40, 50]:
        drawdown = _first_drawdown(after20, pct)
        features[f"first_{pct}pct_drawdown_time_after_entry"] = _num(drawdown.get("timestamp")) if drawdown else None
        features[f"reclaimed_after_{pct}pct_drawdown"] = _reclaimed_after(after20, drawdown)
    features["no_reclaim_after_5m"] = _no_reclaim_after_minutes(after20, 30, 5)
    features["no_reclaim_after_10m"] = _no_reclaim_after_minutes(after20, 30, 10)
    return features


def _metadata_features(meta: dict[str, Any], birth: dict[str, Any]) -> dict[str, Any]:
    socials = [key for key in ["twitter", "telegram", "website", "discord"] if meta.get(key)]
    available = [key for key in ["token_name", "token_symbol", "twitter", "telegram", "website"] if meta.get(key) or birth.get(key)]
    return {
        "token_name": meta.get("token_name") or birth.get("token_name"),
        "token_symbol": meta.get("token_symbol") or birth.get("token_symbol"),
        "metadata_completeness_score": round(len(available) / 5, 3),
        "social_link_count": len(socials),
        "holder_count": _num(meta.get("holder_count")),
        "liquidity_proxy": _num(meta.get("liquidity_proxy")),
        "creator_net_flow_proxy": _num(meta.get("creator_net_flow_proxy")),
        "synthetic_activity_proxy": _num(meta.get("synthetic_activity_proxy")),
    }


def _bucket_thresholds(dataset: list[dict[str, Any]]) -> dict[str, float]:
    b1_pool = [row for row in dataset if not row.get("fdv_anomaly") and (_num(row.get("fdv_at_10k")) or math.inf) <= 15_000]
    b2_pool = [row for row in dataset if not row.get("fdv_anomaly") and (_num(row.get("fdv_at_15k")) or math.inf) <= 20_000]
    b3_pool = [row for row in dataset if not row.get("fdv_anomaly") and (_num(row.get("fdv_at_20k")) or math.inf) <= 30_000]
    all_pool = [row for row in dataset if not row.get("fdv_anomaly")]
    return {
        "fdv_per_event_at_10k": _quantile([_num(row.get("fdv_per_event_at_10k")) for row in b1_pool], 0.67),
        "fdv_per_active_wallet_at_10k": _quantile([_num(row.get("fdv_per_active_wallet_at_10k")) for row in b1_pool], 0.67),
        "fdv_per_buy_at_10k": _quantile([_num(row.get("fdv_per_buy_at_10k")) for row in b1_pool], 0.67),
        "fdv_per_event_at_15k": _quantile([_num(row.get("fdv_per_event_at_15k")) for row in b2_pool], 0.67),
        "fdv_per_active_wallet_at_15k": _quantile([_num(row.get("fdv_per_active_wallet_at_15k")) for row in b2_pool], 0.67),
        "fdv_per_event_at_20k": _quantile([_num(row.get("fdv_per_event_at_20k")) for row in b3_pool], 0.67),
        "fdv_per_active_wallet_at_20k": _quantile([_num(row.get("fdv_per_active_wallet_at_20k")) for row in b3_pool], 0.67),
        "fdv_per_buy_at_20k": _quantile([_num(row.get("fdv_per_buy_at_20k")) for row in b3_pool], 0.67),
        "create_to_15k_seconds": _quantile([_num(row.get("create_to_15k_seconds")) for row in all_pool], 0.67),
        "sell_count_at_15k": _quantile([_num(row.get("sell_count_at_15k")) for row in all_pool], 0.67),
    }


def _apply_buy_rule(row: dict[str, Any], rule_id: str, buckets: dict[str, float]) -> dict[str, Any]:
    eligible = False
    data_limited = False
    if row.get("fdv_anomaly"):
        return {"row": row, "eligible": False, "data_limited": False}
    if rule_id == "B1":
        eligible = (
            row.get("crossed_10k") is True
            and row.get("first_path_before_10k") is True
            and ((_num(row.get("fdv_per_event_at_10k")) or 0) >= buckets["fdv_per_event_at_10k"] or (_num(row.get("fdv_per_active_wallet_at_10k")) or 0) >= buckets["fdv_per_active_wallet_at_10k"])
            and (_num(row.get("fdv_at_10k")) or math.inf) <= 15_000
        )
    elif rule_id == "B2":
        data_limited = row.get("first_crossed_15k_time") is None
        eligible = (
            row.get("crossed_15k") is True
            and row.get("first_path_before_15k") is True
            and ((_num(row.get("fdv_per_event_at_15k")) or 0) >= buckets["fdv_per_event_at_15k"] or (_num(row.get("fdv_per_active_wallet_at_15k")) or 0) >= buckets["fdv_per_active_wallet_at_15k"])
            and ((_num(row.get("create_to_15k_seconds")) or 0) <= (buckets["create_to_15k_seconds"] or math.inf) or row.get("10k_to_15k_seconds") is not None)
            and ((_num(row.get("sell_count_at_15k")) or 0) <= (buckets["sell_count_at_15k"] or math.inf))
            and (_num(row.get("fdv_at_15k")) or math.inf) <= 20_000
        )
    elif rule_id == "B3":
        eligible = (
            row.get("crossed_20k") is True
            and row.get("first_path_before_20k") is True
            and ((_num(row.get("fdv_per_event_at_20k")) or 0) >= buckets["fdv_per_event_at_20k"] or (_num(row.get("fdv_per_active_wallet_at_20k")) or 0) >= buckets["fdv_per_active_wallet_at_20k"])
            and row.get("10k_to_20k_seconds") is not None
            and (_num(row.get("fdv_at_20k")) or math.inf) <= 30_000
        )
    elif rule_id == "B4":
        b3 = _apply_buy_rule(row, "B3", buckets)["eligible"]
        time_to_30k = (_num(row.get("first_crossed_30k_time")) or math.inf) - (_num(row.get("first_crossed_20k_time")) or 0)
        eligible = b3 and (row.get("crossed_30k") is True or time_to_30k <= 300)
    return {"row": row, "eligible": eligible, "data_limited": data_limited}


def _simulate_exit(row: dict[str, Any], buy_rule: dict[str, Any], exit_rule: dict[str, Any]) -> dict[str, Any]:
    level = buy_rule["trigger_level"]
    entry_fdv = _entry_fdv(row, level)
    max_fdv = _num(row.get(f"max_fdv_after_{level}")) or entry_fdv
    exit_reason = "open_or_incomplete"
    exit_multiple = None
    if exit_rule["rule_id"] == "E1" and row.get("first_30pct_drawdown_time_after_entry") is not None and row.get("reclaimed_after_30pct_drawdown") is not True:
        exit_reason = "30pct_drawdown_no_reclaim_10m"
        exit_multiple = 0.70
    elif exit_rule["rule_id"] == "E2":
        exit_reason, exit_multiple = _simulate_e2(row)
    elif exit_rule["rule_id"] == "E3" and (row.get("inactive_timeout") is True or row.get("terminal_collapse_proxy") is True or row.get("maturity_state") == "matured_max_age"):
        exit_reason = "inactivity_max_age_or_terminal"
        exit_multiple = None
    return {
        "entry_fdv": entry_fdv,
        "max_fdv_multiple": (max_fdv / entry_fdv) if entry_fdv else None,
        "exit_reason": exit_reason,
        "exit_multiple": exit_multiple,
        "runner_missed": exit_reason != "open_or_incomplete" and bool(row.get("crossed_100k")),
        "exit_before_100k": exit_reason != "open_or_incomplete" and bool(row.get("crossed_100k")),
        "exit_before_500k": exit_reason != "open_or_incomplete" and bool(row.get("crossed_500k")),
        "held_through_500k": exit_reason == "open_or_incomplete" and bool(row.get("crossed_500k")),
        "held_through_1m": exit_reason == "open_or_incomplete" and bool(row.get("crossed_1m")),
    }


def _simulate_e2(row: dict[str, Any]) -> tuple[str, float | None]:
    if row.get("crossed_500k") and row.get("first_30pct_drawdown_time_after_entry") is not None and row.get("reclaimed_after_30pct_drawdown") is not True:
        return "post_500k_30pct_no_reclaim_5m", 0.70
    if row.get("crossed_100k") and row.get("first_40pct_drawdown_time_after_entry") is not None and row.get("reclaimed_after_40pct_drawdown") is not True:
        return "post_100k_35pct_proxy_no_reclaim_10m", 0.65
    if row.get("crossed_50k") and row.get("first_40pct_drawdown_time_after_entry") is not None and row.get("reclaimed_after_40pct_drawdown") is not True:
        return "post_50k_40pct_no_reclaim_10m", 0.60
    if not row.get("crossed_50k") and row.get("first_50pct_drawdown_time_after_entry") is not None and row.get("reclaimed_after_50pct_drawdown") is not True:
        return "pre_50k_severe_no_reclaim_10m", 0.50
    return "open_or_incomplete", None


def _entry_fdv(row: dict[str, Any], level: str) -> float | None:
    return _num(row.get(f"fdv_at_{level}")) or TARGET_LEVELS[level]


def _max_multiple(row: dict[str, Any], level: str) -> float | None:
    entry = _entry_fdv(row, level)
    max_fdv = _num(row.get(f"max_fdv_after_{level}"))
    return max_fdv / entry if entry and max_fdv else None


def _first_drawdown(paths: list[dict[str, Any]], pct: int) -> dict[str, Any] | None:
    return next((row for row in paths if (_num(row.get("drawdown_pct")) or 0) >= pct), None)


def _reclaimed_after(paths: list[dict[str, Any]], drawdown: dict[str, Any] | None) -> bool | None:
    if not drawdown:
        return None
    local_high = _num(drawdown.get("local_high_fdv"))
    ts = _num(drawdown.get("timestamp")) or 0
    if local_high is None:
        return None
    return any((_num(row.get("timestamp")) or 0) > ts and (_num(row.get("fdv_proxy")) or 0) >= local_high for row in paths)


def _no_reclaim_after_minutes(paths: list[dict[str, Any]], pct: int, minutes: int) -> bool | None:
    drawdown = _first_drawdown(paths, pct)
    if not drawdown:
        return None
    local_high = _num(drawdown.get("local_high_fdv"))
    ts = _num(drawdown.get("timestamp")) or 0
    if local_high is None:
        return None
    deadline = ts + minutes * 60
    return not any(ts < (_num(row.get("timestamp")) or 0) <= deadline and (_num(row.get("fdv_proxy")) or 0) >= local_high for row in paths)


def _milestone_order_bad(row: dict[str, Any]) -> bool:
    seen_false = False
    for level in TARGET_LEVELS:
        crossed = row.get(f"crossed_{level}") is True
        if seen_false and crossed:
            return True
        if not crossed:
            seen_false = True
    return False


def _same_timestamp_multi_milestone(row: dict[str, Any]) -> bool:
    times = [row.get(f"first_crossed_{level}_time") for level in TARGET_LEVELS if row.get(f"first_crossed_{level}_time") is not None]
    return any(count > 1 for count in Counter(times).values())


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _fdv_anomaly(value: Any) -> bool:
    parsed = _num(value)
    return parsed is not None and (parsed <= 0 or parsed > FDV_PROXY_ANOMALY_HIGH)


def _delta(start: Any, end: Any) -> float | None:
    s = _num(start)
    e = _num(end)
    return e - s if s is not None and e is not None else None


def _first_non_null(rows: list[dict[str, Any]], field: str) -> Any:
    return next((row.get(field) for row in rows if row.get(field) is not None), None)


def _median(values: list[Any]) -> float | None:
    clean = [_num(value) for value in values if _num(value) is not None]
    return median(clean) if clean else None


def _max(values: list[Any]) -> float | None:
    clean = [_num(value) for value in values if _num(value) is not None]
    return max(clean) if clean else None


def _iqr(values: list[Any]) -> dict[str, float | None]:
    clean = sorted(_num(value) for value in values if _num(value) is not None)
    if not clean:
        return {"q1": None, "q3": None}
    return {"q1": _quantile(clean, 0.25), "q3": _quantile(clean, 0.75)}


def _quantile(values: list[Any], q: float) -> float:
    clean = sorted(_num(value) for value in values if _num(value) is not None)
    if not clean:
        return 0.0
    index = min(len(clean) - 1, max(0, int(round((len(clean) - 1) * q))))
    return clean[index]


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Buy/Exit Design Snapshot Manifest",
            "",
            f"Snapshot label: `{manifest['snapshot_label']}`",
            f"Created at: `{manifest['created_at']}`",
            f"All crossed-20k count: `{manifest['all_crossed_20k_count']}`",
            f"Actionable crossed-20k count: `{manifest['actionable_crossed_20k_count']}`",
            "Main analysis population: `actionable_crossed_20k`",
            "Secondary context population: `all_crossed_20k`",
            "",
            "Limitations: fixed-rule design only; not validation; no trading; FDV path multiples are not realized PnL.",
            "",
        ]
    )


def _quality_markdown(quality: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Buy/Exit Quality Gate",
            "",
            f"Quality gate result: `{quality['quality_gate_result']}`",
            f"Actionable rows: `{quality['actionable_rows']}`",
            f"Non-actionable rows: `{quality['non_actionable_rows']}`",
            f"Duplicate mints: `{quality['duplicate_mints']}`",
            f"Missing trigger rows: `{quality['missing_trigger_rows']}`",
            f"Missing path rows: `{quality['missing_path_rows']}`",
            f"FDV proxy anomalies: `{quality['fdv_proxy_anomalies']}`",
            "",
        ]
    )


def _summary_markdown(summary: dict[str, Any], quality: dict[str, Any], selected: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Buy/Exit Start Rule Design Summary",
            "",
            f"Snapshot used: `{summary['snapshot_source']}`",
            f"Actionable crossed-20k count: `{summary['actionable_crossed_20k_count']}`",
            f"Quality gate result: `{quality['quality_gate_result']}`",
            f"Selected starting buy rule: `{selected['selected_buy_rule_id']}`",
            f"Selected starting exit rule: `{selected['selected_exit_rule_id']}`",
            f"Readiness classification: `{selected['readiness_classification']}`",
            "",
            "This is a disabled paper/shadow design artifact only. No paper or live trades were run.",
            "",
        ]
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
