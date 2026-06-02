"""Expanded descriptive rerun for T010 winner anatomy and T011 raw-flow."""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.explosive_runner_raw_flow_thesis import (
    build_t011_explosive_runner_raw_flow_report,
    write_t011_explosive_runner_raw_flow_outputs,
)
from research.mtp_research.validation.t011_explosive_runner_raw_flow_robustness import (
    build_t011_raw_flow_robustness_report,
    write_t011_raw_flow_robustness_outputs,
)
from research.mtp_research.validation.winner_anatomy_explosive_runner_discovery import (
    build_winner_anatomy_explosive_runner_report,
    write_winner_anatomy_outputs,
)


REPORT_ID = "t011_expanded_rerun_v0"
REPORT_JSON = "T011_expanded_rerun_summary.json"
REPORT_MD = "T011_expanded_rerun_summary.md"
STATUS_PATH = Path("theses/T011_EXPANDED_RERUN_STATUS.md")
MILESTONES = {
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
DEFAULT_SNAPSHOT_PATHS = [
    data_lake_path(
        "data",
        "normalized",
        "launch_lifecycle_collected_valuation_enriched",
        "launch_lifecycle_snapshots_valuation_enriched.jsonl",
    ),
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_pilot",
        "launch_lifecycle_valuation_enriched",
        "launch_lifecycle_snapshots_valuation_enriched.jsonl",
    ),
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_wide_1",
        "launch_lifecycle_valuation_enriched",
        "launch_lifecycle_snapshots_valuation_enriched.jsonl",
    ),
    data_lake_path(
        "data",
        "backtests",
        "explosive_runner_expanded",
        "parallel_deep_2026",
        "launch_lifecycle_valuation_enriched",
        "launch_lifecycle_snapshots_valuation_enriched.jsonl",
    ),
]
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T011_expanded_rerun"
)
DEFAULT_HOLDER_STATE_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.jsonl"
)
DEFAULT_ENTITY_PROXY_PATH = data_lake_path(
    "data", "backtests", "entity_proxy", "entity_proxy_strict_cohort.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data",
    "backtests",
    "migration_graduation",
    "combined_migration_graduation_labels_provenance_upgraded.jsonl",
)
DEFAULT_FUNDING_LINK_PATH = data_lake_path("data", "backtests", "funding_link", "funding_link_pilot.parquet")


def build_t011_expanded_rerun_report(
    *,
    snapshot_paths: list[Path | str],
    output_dir: Path | str,
    status_path: Path | str = STATUS_PATH,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    funding_link_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined_snapshots_path = output / "combined_expanded_lifecycle_snapshots.jsonl"
    combine_summary = write_combined_expanded_snapshots(snapshot_paths, combined_snapshots_path)
    dataset_audit = audit_expanded_snapshots(combined_snapshots_path)

    winner_report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=combined_snapshots_path,
        holder_state_snapshots_path=holder_state_snapshots_path,
        entity_proxy_path=entity_proxy_path,
        migration_labels_path=migration_labels_path,
        funding_link_path=funding_link_path,
    )
    winner_paths = write_winner_anatomy_outputs(
        winner_report,
        output_dir=output / "winner_anatomy",
        status_path=output / "winner_anatomy_status.md",
    )

    t011_report = build_t011_explosive_runner_raw_flow_report(
        snapshots_path=combined_snapshots_path,
        holder_state_snapshots_path=holder_state_snapshots_path,
        entity_proxy_path=entity_proxy_path,
        migration_labels_path=migration_labels_path,
        funding_link_path=funding_link_path,
    )
    t011_paths = write_t011_explosive_runner_raw_flow_outputs(
        t011_report,
        output_dir=output / "raw_flow",
        status_path=output / "raw_flow_status.md",
    )
    robustness_report = None
    robustness_paths: dict[str, Path] = {}
    if t011_report["final_classification"] in {"descriptive_signal_present", "weak_signal"}:
        robustness_report = build_t011_raw_flow_robustness_report(
            t011_summary_path=t011_paths["json_summary_path"],
            trigger_20k_rows_path=t011_paths["trigger_20k_feature_rows_path"],
            tier_table_path=t011_paths["milestone_tier_feature_table_path"],
            snapshots_path=combined_snapshots_path,
        )
        robustness_paths = write_t011_raw_flow_robustness_outputs(
            robustness_report,
            output_dir=output / "robustness",
            status_path=output / "robustness_status.md",
        )

    paths = _copy_requested_tables(output, t011_paths, robustness_paths)
    old_vs_expanded = _old_vs_expanded_comparison(t011_report, robustness_report, dataset_audit)
    report = {
        "report_id": REPORT_ID,
        "review_type": "descriptive_rerun_stability_only",
        "methodology_flags": [
            "research_only",
            "descriptive_rerun_only",
            "no_thesis_promotion",
            "no_backtest",
            "no_walk_forward_validation",
            "no_validation_run",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_rules",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "fdv_proxy_not_true_market_cap",
        ],
        "input_snapshot_paths": [str(path) for path in snapshot_paths],
        "combined_snapshot_path": str(combined_snapshots_path),
        "combine_summary": combine_summary,
        "expanded_dataset_audit": dataset_audit,
        "coverage_gates": _coverage_gates(dataset_audit),
        "winner_anatomy_result": _winner_summary(winner_report),
        "t011_result": _t011_summary(t011_report),
        "robustness_result": _robustness_summary(robustness_report),
        "old_vs_expanded_comparison": old_vs_expanded,
        "validation_recommended": old_vs_expanded["validation_now_justified"],
        "limitations": _limitations(t011_report, robustness_report),
        "next_recommendation": _next_recommendation(old_vs_expanded),
        "internal_report_paths": {
            "winner_anatomy": {key: str(value) for key, value in winner_paths.items()},
            "raw_flow": {key: str(value) for key, value in t011_paths.items()},
            "robustness": {key: str(value) for key, value in robustness_paths.items()},
        },
    }
    paths.update(write_t011_expanded_rerun_outputs(report, output_dir=output, status_path=status_path))
    return report, paths


def write_combined_expanded_snapshots(snapshot_paths: list[Path | str], output_path: Path | str) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    seen_snapshot_keys: set[tuple[str, int | None, int | None]] = set()
    seen_mints: set[str] = set()
    source_counts: dict[str, dict[str, int]] = {}
    rows_written = 0
    with output.open("w", encoding="utf-8") as out:
        for raw_path in snapshot_paths:
            path = Path(raw_path)
            source_seen = 0
            source_written = 0
            if not path.exists():
                source_counts[str(path)] = {"rows_seen": 0, "rows_written": 0, "missing": 1}
                continue
            for row in _read_rows(path):
                source_seen += 1
                mint = _mint(row)
                if not mint:
                    continue
                key = (mint, _int_or_none(row.get("launch_age_seconds")), _int_or_none(row.get("snapshot_ts")))
                if key in seen_snapshot_keys:
                    continue
                seen_snapshot_keys.add(key)
                seen_mints.add(mint)
                out.write(json.dumps(row, sort_keys=True))
                out.write("\n")
                rows_written += 1
                source_written += 1
            source_counts[str(path)] = {"rows_seen": source_seen, "rows_written": source_written, "missing": 0}
    return {
        "snapshot_rows_written": rows_written,
        "unique_mints": len(seen_mints),
        "source_counts": source_counts,
    }


def audit_expanded_snapshots(path: Path | str) -> dict[str, Any]:
    rows = list(_read_jsonl(Path(path)))
    grouped = _group_by_mint(rows)
    launch_dates: Counter[str] = Counter()
    trigger_dates: dict[str, Counter[str]] = {name: Counter() for name in ("15k", "20k", "30k")}
    trigger_counts = {name: 0 for name in ("15k", "20k", "30k")}
    milestone_counts = {name: 0 for name in ("50k", "100k", "200k", "500k", "1m")}
    missing_reasons: Counter[str] = Counter()
    forward_covered = 0
    for mint, mint_rows in grouped.items():
        priced = sorted([row for row in mint_rows if _value(row) is not None], key=_age)
        launch_date = _launch_date(mint_rows)
        if launch_date:
            launch_dates[launch_date] += 1
        trigger_20k = _first_crossing(priced, MILESTONES["20k"])
        if trigger_20k and _has_forward_path(trigger_20k, priced):
            forward_covered += 1
        for name in ("15k", "20k", "30k"):
            crossed = _first_crossing(priced, MILESTONES[name])
            if crossed:
                trigger_counts[name] += 1
                if launch_date:
                    trigger_dates[name][launch_date] += 1
        for name in ("50k", "100k", "200k", "500k", "1m"):
            if _first_crossing(priced, MILESTONES[name]):
                milestone_counts[name] += 1
        if not trigger_20k:
            missing_reasons["missing_20k_trigger"] += 1
        elif not _has_forward_path(trigger_20k, priced):
            missing_reasons["missing_forward_path_after_20k"] += 1
    active_20k_counts = list(trigger_dates["20k"].values())
    total_20k = trigger_counts["20k"]
    top_counts = trigger_dates["20k"].most_common()
    return {
        "total_launches": len(grouped),
        "snapshot_count": len(rows),
        "date_range": {
            "start": min(launch_dates) if launch_dates else None,
            "end": max(launch_dates) if launch_dates else None,
        },
        "unique_launch_dates": len(launch_dates),
        "unique_trigger_dates": {name: len(counter) for name, counter in trigger_dates.items()},
        "trigger_counts": trigger_counts,
        "forward_path_coverage": {
            "20k": (forward_covered / total_20k) if total_20k else 0.0,
            "covered_20k_rows": forward_covered,
        },
        "milestone_counts": milestone_counts,
        "missing_reason_counts": dict(sorted(missing_reasons.items())),
        "date_distribution": dict(sorted(trigger_dates["20k"].items())),
        "top_date_share": (top_counts[0][1] / total_20k) if total_20k else 0.0,
        "top3_date_share": (sum(count for _, count in top_counts[:3]) / total_20k) if total_20k else 0.0,
        "median_rows_per_active_20k_date": median(active_20k_counts) if active_20k_counts else 0,
    }


def write_t011_expanded_rerun_outputs(
    report: dict[str, Any], *, output_dir: Path | str, status_path: Path | str
) -> dict[str, Path]:
    output = Path(output_dir)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": md_path, "status_path": status}


def _copy_requested_tables(
    output: Path, t011_paths: dict[str, Path], robustness_paths: dict[str, Path]
) -> dict[str, Path]:
    paths = {
        "expanded_milestone_tier_feature_table_path": output / "expanded_milestone_tier_feature_table.csv",
        "expanded_trigger_20k_feature_rows_path": output / "expanded_trigger_20k_feature_rows.csv",
    }
    shutil.copyfile(t011_paths["milestone_tier_feature_table_path"], paths["expanded_milestone_tier_feature_table_path"])
    shutil.copyfile(t011_paths["trigger_20k_feature_rows_path"], paths["expanded_trigger_20k_feature_rows_path"])
    if robustness_paths:
        paths["expanded_robustness_split_table_path"] = output / "expanded_robustness_split_table.csv"
        shutil.copyfile(robustness_paths["split_table_path"], paths["expanded_robustness_split_table_path"])
    return paths


def _coverage_gates(audit: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "min_30_unique_20k_dates": audit["unique_trigger_dates"]["20k"] >= 30,
        "min_1000_20k_rows": audit["trigger_counts"]["20k"] >= 1000,
        "median_10_rows_per_active_date": audit["median_rows_per_active_20k_date"] >= 10,
        "single_date_not_above_35pct": audit["top_date_share"] <= 0.35,
        "top3_dates_below_60pct": audit["top3_date_share"] <= 0.60,
        "forward_path_coverage_at_least_90pct": audit["forward_path_coverage"]["20k"] >= 0.90,
    }
    return {"passed": all(gates.values()), "gates": gates}


def _winner_summary(report: dict[str, Any]) -> dict[str, Any]:
    tier = report.get("milestone_tier_anatomy", {})
    return {
        "readiness_classification": report.get("readiness_classification"),
        "milestone_counts": report.get("milestone_counts", {}),
        "milestone_tier_counts": report.get("milestone_tier_counts", {}),
        "tier_anatomy": tier,
        "candidate_signal_discovery": report.get("candidate_signal_discovery", {}),
    }


def _t011_summary(report: dict[str, Any]) -> dict[str, Any]:
    primary = report.get("primary_comparisons", {})
    diagnostics = report.get("diagnostics", {})
    return {
        "classification": report.get("final_classification"),
        "trigger_summary": report.get("trigger_summary", {}),
        "milestone_tier_counts": report.get("milestone_tier_counts", {}),
        "primary_comparisons": primary,
        "diagnostics": diagnostics,
        "low_flow_high_fdv_efficiency_survived": _low_flow_high_fdv_survived(primary),
        "chronological_robustness_recommended": report.get("chronological_robustness_recommended"),
        "warning_flags": report.get("warning_flags", []),
    }


def _robustness_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {
            "robustness_classification": "not_run_no_descriptive_signal",
            "validation_design_recommended": False,
        }
    return {
        "robustness_classification": report.get("robustness_classification"),
        "trigger_20k_count_analyzed": report.get("trigger_20k_count_analyzed"),
        "validation_design_recommended": report.get("validation_design_recommended"),
        "full_sample_direction": report.get("full_sample_direction", {}),
        "warning_flags": report.get("warning_flags", []),
    }


def _old_vs_expanded_comparison(
    t011_report: dict[str, Any], robustness_report: dict[str, Any] | None, audit: dict[str, Any]
) -> dict[str, Any]:
    classification = t011_report.get("final_classification")
    robustness = robustness_report.get("robustness_classification") if robustness_report else "not_run_no_descriptive_signal"
    survived = _low_flow_high_fdv_survived(t011_report.get("primary_comparisons", {}))
    validation_now = robustness == "robust_descriptive_signal" and audit["unique_trigger_dates"]["20k"] >= 30
    return {
        "old_sample": {
            "trigger_20k_rows": 422,
            "unique_trigger_dates": 3,
            "result": "robust_descriptive_signal",
            "validation_result": "failed_due_date_concentration",
        },
        "expanded_sample": {
            "trigger_20k_rows": audit["trigger_counts"]["20k"],
            "unique_trigger_dates": audit["unique_trigger_dates"]["20k"],
            "top_date_share": audit["top_date_share"],
            "top3_date_share": audit["top3_date_share"],
            "t011_classification": classification,
            "robustness_classification": robustness,
        },
        "low_flow_high_fdv_efficiency_pattern_survived": survived,
        "direction_changed": not survived,
        "support_improved": audit["unique_trigger_dates"]["20k"] > 3 and audit["trigger_counts"]["20k"] > 422,
        "validation_now_justified": validation_now,
        "validation_design_update_recommended": validation_now,
    }


def _low_flow_high_fdv_survived(primary: dict[str, Any]) -> bool:
    comparisons = [
        primary.get("100k_plus_vs_sub_100k", {}),
        primary.get("500k_plus_vs_100k_to_500k", {}),
        primary.get("1m_plus_vs_sub_1m", {}),
    ]
    for item in comparisons:
        deltas = item.get("feature_median_deltas", {})
        event_delta = ((deltas.get("event_count_at_20k") or {}).get("delta"))
        fdv_event_delta = ((deltas.get("fdv_per_event_at_20k") or {}).get("delta"))
        fdv_buy_delta = ((deltas.get("fdv_per_buy_at_20k") or {}).get("delta"))
        low_flow = event_delta is not None and event_delta <= 0
        high_efficiency = (
            (fdv_event_delta is not None and fdv_event_delta >= 0)
            or (fdv_buy_delta is not None and fdv_buy_delta >= 0)
        )
        if low_flow and high_efficiency:
            return True
    return False


def _limitations(t011_report: dict[str, Any], robustness_report: dict[str, Any] | None) -> list[str]:
    limitations = [
        "True market-cap labels remain blocked; this uses FDV/valuation proxy only.",
        "This rerun is descriptive only and does not validate a strategy.",
        "No entry, exit, profitability, or execution claims are made.",
    ]
    limitations.extend(t011_report.get("limitations", []))
    if robustness_report:
        limitations.extend(robustness_report.get("limitations", []))
    return sorted(set(str(item) for item in limitations))


def _next_recommendation(comparison: dict[str, Any]) -> str:
    if comparison["validation_now_justified"]:
        return "Design or rerun T011 validation on the expanded sample with date-balanced holdouts; do not promote before validation."
    if comparison["low_flow_high_fdv_efficiency_pattern_survived"]:
        return "Refine robustness design before validation; the descriptive pattern survived but robustness did not fully justify validation."
    return "Park T011 as unstable/no descriptive signal on the expanded sample."


def _markdown(report: dict[str, Any]) -> str:
    audit = report["expanded_dataset_audit"]
    t011 = report["t011_result"]
    robust = report["robustness_result"]
    comparison = report["old_vs_expanded_comparison"]
    return "\n".join(
        [
            "# T011 Expanded Rerun Summary",
            "",
            "This is a descriptive stability rerun only. It does not run validation, trading, paper trading, optimization, or thesis promotion.",
            "",
            "## Expanded Dataset",
            "",
            f"- Launches: `{audit['total_launches']}`",
            f"- Date range: `{audit['date_range']['start']}` to `{audit['date_range']['end']}`",
            f"- Unique $20k trigger dates: `{audit['unique_trigger_dates']['20k']}`",
            f"- $20k trigger rows: `{audit['trigger_counts']['20k']}`",
            f"- Forward path coverage: `{audit['forward_path_coverage']['20k']}`",
            f"- Top date share: `{audit['top_date_share']}`",
            f"- Top 3 date share: `{audit['top3_date_share']}`",
            "",
            "## Result",
            "",
            f"- Expanded T011 classification: `{t011['classification']}`",
            f"- Expanded robustness classification: `{robust['robustness_classification']}`",
            f"- Low-flow/high-FDV-efficiency survived: `{comparison['low_flow_high_fdv_efficiency_pattern_survived']}`",
            f"- Validation recommended: `{report['validation_recommended']}`",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
        ]
    )


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path) -> str:
    audit = report["expanded_dataset_audit"]
    comparison = report["old_vs_expanded_comparison"]
    return "\n".join(
        [
            "# T011 Expanded Rerun Status",
            "",
            "## Why This Rerun Was Needed",
            "",
            "The prior T011 validation failed because the holdout collapsed to one date. The expanded sample fixes the date-clustering blocker before any validation rerun is attempted.",
            "",
            "## Expanded Dataset Coverage",
            "",
            f"- Launches: `{audit['total_launches']}`",
            f"- $20k trigger rows: `{audit['trigger_counts']['20k']}`",
            f"- Unique $20k trigger dates: `{audit['unique_trigger_dates']['20k']}`",
            f"- Median rows per active $20k date: `{audit['median_rows_per_active_20k_date']}`",
            f"- Top date share: `{audit['top_date_share']}`",
            f"- Top 3 date share: `{audit['top3_date_share']}`",
            f"- Forward path coverage: `{audit['forward_path_coverage']['20k']}`",
            "",
            "## Winner Anatomy Result",
            "",
            f"- Readiness: `{report['winner_anatomy_result']['readiness_classification']}`",
            f"- Milestone tier counts: `{report['winner_anatomy_result']['milestone_tier_counts']}`",
            "",
            "## Expanded T011 Result",
            "",
            f"- Classification: `{report['t011_result']['classification']}`",
            f"- Robustness classification: `{report['robustness_result']['robustness_classification']}`",
            f"- Low-flow/high-FDV-efficiency survived: `{comparison['low_flow_high_fdv_efficiency_pattern_survived']}`",
            "",
            "## Old vs Expanded",
            "",
            f"- Old $20k trigger rows: `{comparison['old_sample']['trigger_20k_rows']}`",
            f"- Old unique trigger dates: `{comparison['old_sample']['unique_trigger_dates']}`",
            f"- Expanded $20k trigger rows: `{comparison['expanded_sample']['trigger_20k_rows']}`",
            f"- Expanded unique trigger dates: `{comparison['expanded_sample']['unique_trigger_dates']}`",
            f"- Validation recommended: `{comparison['validation_now_justified']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            "## Report Paths",
            "",
            f"- JSON: `{json_path}`",
            f"- Markdown: `{md_path}`",
        ]
    )


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return list(_read_jsonl(path))
    raise ValueError(f"unsupported snapshot input format for expanded rerun: {path}")


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    rows = []
    with value.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return grouped


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0.0) >= threshold:
            return row
    return None


def _has_forward_path(trigger: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    trigger_age = _age(trigger)
    return any(_age(row) > trigger_age for row in rows)


def _launch_date(rows: list[dict[str, Any]]) -> str | None:
    row = min(rows, key=lambda item: _age(item))
    ts = _int_or_none(row.get("launch_ts"))
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("token_mint") or row.get("mint")
    return str(value) if value else None


def _age(row: dict[str, Any]) -> int:
    return _int_or_none(row.get("launch_age_seconds") or row.get("snapshot_age_seconds")) or 0


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") or row.get("fdv_usd"))


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
