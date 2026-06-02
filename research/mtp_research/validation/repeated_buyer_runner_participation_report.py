"""Repeated-buyer runner participation descriptive report."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.explosive_runner_winner_anatomy_report import (
    DEFAULT_SNAPSHOT_PATHS,
    MILESTONES,
    TIER_ORDER,
    write_combined_expanded_snapshots,
)
from research.mtp_research.validation.structural_wallet_anatomy_report import DEFAULT_EVENT_PATHS


REPORT_ID = "repeated_buyer_runner_participation_report_v0"
REPORT_JSON = "repeated_buyer_runner_participation_summary.json"
REPORT_MD = "repeated_buyer_runner_participation_summary.md"
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "repeated_buyer_runner_participation"
)
DEFAULT_STATUS_PATH = Path("theses/REPEATED_BUYER_RUNNER_PARTICIPATION_STATUS.md")

WINDOWS = {
    "before_20k": "entry_side_available_before_20k",
    "at_20k": "entry_side_available_at_20k",
    "before_50k": "post_trigger_only",
    "first_60s": "entry_side_available_before_20k",
    "first_120s": "entry_side_available_before_20k",
}
AGG_FEATURES = [
    "count_early_buyers_with_prior_runner",
    "share_early_buyers_with_prior_runner",
    "count_early_buyers_with_prior_500k_runner",
    "share_early_buyers_with_prior_500k_runner",
    "count_early_buyers_with_prior_1m_runner",
    "share_early_buyers_with_prior_1m_runner",
    "median_buyer_prior_runner_count",
    "max_buyer_prior_runner_count",
    "repeated_buyer_quality_proxy",
]
EFFICIENCY_FEATURES = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
]


def build_repeated_buyer_runner_participation_report(
    *,
    snapshot_paths: list[Path | str],
    event_paths: list[Path | str],
    output_dir: Path | str,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined_path = output / "combined_expanded_lifecycle_snapshots.jsonl"
    combine_summary = write_combined_expanded_snapshots(snapshot_paths, combined_path)
    snapshots = _read_jsonl(combined_path)
    snapshot_by_mint = _group_by_mint(snapshots)
    launch_rows = [_base_launch_row(mint, rows) for mint, rows in sorted(snapshot_by_mint.items())]
    launch_by_mint = {row["mint"]: row for row in launch_rows}
    event_audit = _stream_early_buyer_windows(event_paths, launch_by_mint)
    enriched_launch_rows = _attach_leakage_safe_wallet_history(launch_rows, event_audit["buyer_windows"])
    coverage = _coverage_report(enriched_launch_rows, snapshots, event_audit)
    tier_summary = _tier_summary(enriched_launch_rows)
    window_coverage = _window_coverage(enriched_launch_rows)
    tier_comparison = _tier_comparison(enriched_launch_rows)
    interaction_rows, interaction_summary = _fdv_efficiency_interactions(enriched_launch_rows)
    entry_side_rows = _entry_side_feature_classification()
    strongest = _strongest_differences(tier_comparison)
    recommendation = _recommended_next_action(strongest, coverage, interaction_summary)
    readiness = _readiness(strongest, coverage, interaction_summary)
    report = {
        "report_id": REPORT_ID,
        "report_type": "repeated_buyer_runner_participation_descriptive_report",
        "readiness_classification": readiness,
        "methodology_flags": [
            "research_only",
            "descriptive_discovery_report_only",
            "not_a_thesis_promotion",
            "no_validation_run",
            "no_backtest",
            "no_walk_forward_validation",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_private_key_logic",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_logic",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "neutral_proxy_labels_only",
            "fdv_proxy_not_true_market_cap",
        ],
        "dataset": {
            "snapshot_paths": [str(path) for path in snapshot_paths],
            "event_paths": [str(path) for path in event_paths],
            "combined_snapshot_path": str(combined_path),
            "combine_summary": combine_summary,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "data_audit": event_audit["field_availability"],
        "coverage_report": coverage,
        "milestone_tier_summary": tier_summary,
        "early_buyer_window_coverage": window_coverage,
        "launch_feature_rows": enriched_launch_rows,
        "tier_comparison_summary": tier_comparison,
        "fdv_efficiency_interaction_summary": interaction_summary,
        "entry_side_feature_classification": entry_side_rows,
        "strongest_tier_differences": strongest,
        "recommended_next_action": recommendation,
        "limitations": _limitations(coverage),
    }
    paths = write_repeated_buyer_runner_participation_outputs(
        report,
        tier_rows=tier_comparison,
        interaction_rows=interaction_rows,
        output_dir=output,
        status_path=status_path,
    )
    return report, paths


def write_repeated_buyer_runner_participation_outputs(
    report: dict[str, Any],
    *,
    tier_rows: list[dict[str, Any]],
    interaction_rows: list[dict[str, Any]],
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    tier_csv = output / "repeated_buyer_tier_comparison.csv"
    interaction_csv = output / "fdv_efficiency_repeated_buyer_interaction.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    _write_csv(tier_rows, tier_csv)
    _write_csv(interaction_rows, interaction_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, tier_csv, interaction_csv), encoding="utf-8")
    return {
        "summary_json_path": json_path,
        "summary_markdown_path": md_path,
        "tier_comparison_path": tier_csv,
        "fdv_efficiency_interaction_path": interaction_csv,
        "status_path": status,
    }


def _base_launch_row(mint: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    crossings = {name: _first_crossing(priced, value) for name, value in MILESTONES.items()}
    at_20k = _snapshot_before(priced, _age(crossings["20k"])) if crossings.get("20k") else None
    prior = at_20k.get("_prior_snapshot") if at_20k else None
    fdv = _value(at_20k)
    event_count = _event_count(at_20k)
    buy_count = _float_or_none(at_20k.get("buy_count")) if at_20k else None
    active = _float_or_none(at_20k.get("active_wallets")) if at_20k else None
    launch_ts = _int_or_none(_first_present(*(row.get("launch_ts") for row in rows)))
    return {
        "mint": mint,
        "launch_id": _first_present(*(row.get("launch_id") for row in rows)),
        "creator": _first_present(*(row.get("creator") or row.get("creator_deployer") for row in rows)),
        "launch_ts": launch_ts,
        "launch_date": _launch_date(launch_ts),
        "milestone_tier": _highest_tier(crossings),
        "crossing_20k_age": _age(crossings["20k"]) if crossings.get("20k") else None,
        "crossing_50k_age": _age(crossings["50k"]) if crossings.get("50k") else None,
        "crossing_100k_age": _age(crossings["100k"]) if crossings.get("100k") else None,
        "crossing_500k_age": _age(crossings["500k"]) if crossings.get("500k") else None,
        "crossing_1m_age": _age(crossings["1m"]) if crossings.get("1m") else None,
        "fdv_per_event_at_20k": _ratio(fdv, event_count),
        "fdv_per_buy_at_20k": _ratio(fdv, buy_count),
        "fdv_per_active_wallet_at_20k": _ratio(fdv, active),
        "valuation_growth_per_event_at_20k": _ratio(_delta_value(at_20k, prior), event_count) if at_20k and prior else None,
        "valuation_growth_per_buy_at_20k": _ratio(_delta_value(at_20k, prior), buy_count) if at_20k and prior else None,
    }


def _stream_early_buyer_windows(paths: list[Path | str], launch_by_mint: dict[str, dict[str, Any]]) -> dict[str, Any]:
    buyer_windows: dict[str, dict[str, set[str]]] = {
        mint: {window: set() for window in WINDOWS}
        for mint in launch_by_mint
    }
    total = 0
    field_counts = Counter()
    mints_seen: set[str] = set()
    for path in paths:
        value = Path(path)
        if not value.exists():
            continue
        with value.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                total += 1
                _count_event_fields(event, field_counts)
                mint = _mint(event)
                actor = event.get("actor")
                if not mint or mint not in launch_by_mint or not actor:
                    continue
                mints_seen.add(mint)
                if not _is_buy_event(event):
                    continue
                age = _event_age(event, launch_by_mint[mint].get("launch_ts"))
                if age is None or age < 0:
                    continue
                actor_text = str(actor)
                launch = launch_by_mint[mint]
                if launch.get("crossing_20k_age") is not None and age <= launch["crossing_20k_age"]:
                    buyer_windows[mint]["before_20k"].add(actor_text)
                    buyer_windows[mint]["at_20k"].add(actor_text)
                if launch.get("crossing_50k_age") is not None and age <= launch["crossing_50k_age"]:
                    buyer_windows[mint]["before_50k"].add(actor_text)
                if age <= 60:
                    buyer_windows[mint]["first_60s"].add(actor_text)
                if age <= 120:
                    buyer_windows[mint]["first_120s"].add(actor_text)
    return {
        "event_count": total,
        "event_launches": len(mints_seen),
        "buyer_windows": buyer_windows,
        "field_availability": _event_field_availability(field_counts, total),
    }


def _attach_leakage_safe_wallet_history(
    launch_rows: list[dict[str, Any]],
    buyer_windows: dict[str, dict[str, set[str]]],
) -> list[dict[str, Any]]:
    history: dict[str, Counter] = defaultdict(Counter)
    output = []
    for launch in sorted(launch_rows, key=lambda row: (row.get("launch_ts") or 0, row["mint"])):
        row = dict(launch)
        windows = buyer_windows.get(row["mint"], {window: set() for window in WINDOWS})
        for window, buyers in windows.items():
            row.update(_aggregate_window(window, buyers, history))
        output.append(row)
        update_buyers = set().union(*(windows.get(window, set()) for window in WINDOWS))
        for buyer in update_buyers:
            history[buyer]["launches"] += 1
            if row.get("crossing_20k_age") is not None:
                history[buyer]["trigger_20k"] += 1
            if row.get("crossing_100k_age") is not None:
                history[buyer]["runner_100k"] += 1
            if row.get("crossing_500k_age") is not None:
                history[buyer]["runner_500k"] += 1
            if row.get("crossing_1m_age") is not None:
                history[buyer]["runner_1m"] += 1
            if row["milestone_tier"] in {"never_reached_20k", "reached_20k_but_never_50k"}:
                history[buyer]["failure_proxy"] += 1
    return output


def _aggregate_window(window: str, buyers: set[str], history: dict[str, Counter]) -> dict[str, Any]:
    stats = [history[buyer] for buyer in sorted(buyers)]
    total = len(stats)
    prior_runner_counts = [stat["runner_100k"] for stat in stats]
    count_prior_runner = sum(1 for stat in stats if stat["runner_100k"] > 0)
    count_prior_500k = sum(1 for stat in stats if stat["runner_500k"] > 0)
    count_prior_1m = sum(1 for stat in stats if stat["runner_1m"] > 0)
    max_runner = max(prior_runner_counts) if prior_runner_counts else 0
    median_runner = median(prior_runner_counts) if prior_runner_counts else None
    quality = (
        _ratio(count_prior_runner, total) or 0
    ) + 2 * (_ratio(count_prior_500k, total) or 0) + 3 * (_ratio(count_prior_1m, total) or 0)
    return {
        f"{window}_early_buyer_count": total,
        f"{window}_count_early_buyers_with_prior_runner": count_prior_runner,
        f"{window}_share_early_buyers_with_prior_runner": _ratio(count_prior_runner, total),
        f"{window}_count_early_buyers_with_prior_500k_runner": count_prior_500k,
        f"{window}_share_early_buyers_with_prior_500k_runner": _ratio(count_prior_500k, total),
        f"{window}_count_early_buyers_with_prior_1m_runner": count_prior_1m,
        f"{window}_share_early_buyers_with_prior_1m_runner": _ratio(count_prior_1m, total),
        f"{window}_median_buyer_prior_runner_count": median_runner,
        f"{window}_max_buyer_prior_runner_count": max_runner if total else None,
        f"{window}_repeated_buyer_quality_proxy": quality if total else None,
        f"{window}_median_buyer_prior_launch_participation_count": median([stat["launches"] for stat in stats]) if stats else None,
        f"{window}_median_buyer_prior_failure_participation_count": median([stat["failure_proxy"] for stat in stats]) if stats else None,
    }


def _coverage_report(
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    event_audit: dict[str, Any],
) -> dict[str, Any]:
    total = len(launch_rows)
    before_20k_covered = sum(1 for row in launch_rows if row.get("before_20k_early_buyer_count", 0) > 0)
    repeated_covered = sum(1 for row in launch_rows if (row.get("before_20k_count_early_buyers_with_prior_runner") or 0) > 0)
    return {
        "total_launches": total,
        "snapshot_count": len(snapshots),
        "event_count": event_audit["event_count"],
        "event_launches": event_audit["event_launches"],
        "event_coverage_pct": _pct(event_audit["event_launches"], total),
        "before_20k_early_buyer_coverage_count": before_20k_covered,
        "before_20k_early_buyer_coverage_pct": _pct(before_20k_covered, total),
        "before_20k_repeated_runner_buyer_launch_count": repeated_covered,
        "before_20k_repeated_runner_buyer_coverage_pct": _pct(repeated_covered, total),
        "unique_launch_dates": len({row.get("launch_date") for row in launch_rows if row.get("launch_date")}),
        "date_range": _date_range(row.get("launch_date") for row in launch_rows),
    }


def _window_coverage(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for window in WINDOWS:
        covered = sum(1 for row in launch_rows if row.get(f"{window}_early_buyer_count", 0) > 0)
        repeated = sum(1 for row in launch_rows if (row.get(f"{window}_count_early_buyers_with_prior_runner") or 0) > 0)
        rows.append(
            {
                "window_name": window,
                "launches_with_early_buyers": covered,
                "launches_with_prior_runner_buyers": repeated,
                "early_buyer_coverage_pct": _pct(covered, len(launch_rows)),
                "prior_runner_buyer_coverage_pct": _pct(repeated, len(launch_rows)),
            }
        )
    return rows


def _tier_summary(launch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for tier in TIER_ORDER:
        rows = [row for row in launch_rows if row["milestone_tier"] == tier]
        dates = Counter(row.get("launch_date") for row in rows if row.get("launch_date"))
        creators = Counter(row.get("creator") or "unknown" for row in rows)
        output[tier] = {
            "launch_count": len(rows),
            "unique_date_count": len(dates),
            "top_date_share": _top_share(dates, len(rows), 1),
            "top_creator_share": _top_share(creators, len(rows), 1),
        }
    return output


def _tier_comparison(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    features = [f"{window}_{feature}" for window in WINDOWS for feature in AGG_FEATURES]
    for tier in TIER_ORDER:
        members = [row for row in launch_rows if row["milestone_tier"] == tier]
        for feature in features:
            values = [_float_or_none(row.get(feature)) for row in members]
            numeric = [value for value in values if value is not None]
            rows.append(
                {
                    "comparison_group": "milestone_tier",
                    "milestone_tier": tier,
                    "feature": feature,
                    **_distribution(numeric),
                    "missing_count": len(members) - len(numeric),
                    "coverage_pct": _pct(len(numeric), len(members)),
                }
            )
    for label, positives, negatives in _comparison_groups(launch_rows):
        for feature in features:
            pos_vals = [_float_or_none(row.get(feature)) for row in positives]
            neg_vals = [_float_or_none(row.get(feature)) for row in negatives]
            pos = [value for value in pos_vals if value is not None]
            neg = [value for value in neg_vals if value is not None]
            pos_med = median(pos) if pos else None
            neg_med = median(neg) if neg else None
            rows.append(
                {
                    "comparison_group": label,
                    "milestone_tier": "comparison",
                    "feature": feature,
                    "positive_sample_count": len(pos),
                    "negative_sample_count": len(neg),
                    "positive_median": pos_med,
                    "negative_median": neg_med,
                    "median_difference": pos_med - neg_med if pos_med is not None and neg_med is not None else None,
                    "direction": _direction(pos_med, neg_med),
                    "classification": _difference_classification(pos_med, neg_med, len(pos), len(neg)),
                }
            )
    return rows


def _fdv_efficiency_interactions(launch_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    summary = []
    for feature in EFFICIENCY_FEATURES:
        values = [_float_or_none(row.get(feature)) for row in launch_rows]
        quality_values = [_float_or_none(row.get("before_20k_repeated_buyer_quality_proxy")) for row in launch_rows]
        fdv_cut = _quantile_median(values)
        quality_cut = _quantile_median(quality_values)
        for fdv_bucket, quality_bucket in [
            ("high_fdv_efficiency", "repeated_runner_buyers"),
            ("high_fdv_efficiency", "no_repeated_runner_buyers"),
            ("low_fdv_efficiency", "repeated_runner_buyers"),
            ("low_fdv_efficiency", "no_repeated_runner_buyers"),
        ]:
            members = [
                row for row in launch_rows
                if _bucket(_float_or_none(row.get(feature)), fdv_cut, fdv_bucket.startswith("high"))
                and _bucket(
                    _float_or_none(row.get("before_20k_repeated_buyer_quality_proxy")),
                    quality_cut,
                    quality_bucket == "repeated_runner_buyers",
                )
            ]
            tier_counts = Counter(row["milestone_tier"] for row in members)
            rows.append(
                {
                    "efficiency_feature": feature,
                    "fdv_efficiency_bucket": fdv_bucket,
                    "repeated_buyer_bucket": quality_bucket,
                    "launch_count": len(members),
                    "reached_100k_plus_count": sum(tier_counts[t] for t in {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}),
                    "reached_500k_plus_count": tier_counts["reached_500k_but_never_1m"] + tier_counts["reached_1m_plus"],
                    "reached_1m_plus_count": tier_counts["reached_1m_plus"],
                    "median_repeated_buyer_quality_proxy": _median([row.get("before_20k_repeated_buyer_quality_proxy") for row in members]),
                }
            )
        high_with = next(row for row in rows if row["efficiency_feature"] == feature and row["fdv_efficiency_bucket"] == "high_fdv_efficiency" and row["repeated_buyer_bucket"] == "repeated_runner_buyers")
        high_without = next(row for row in rows if row["efficiency_feature"] == feature and row["fdv_efficiency_bucket"] == "high_fdv_efficiency" and row["repeated_buyer_bucket"] == "no_repeated_runner_buyers")
        summary.append(
            {
                "efficiency_feature": feature,
                "uses_quantile_buckets": True,
                "threshold_was_optimized": False,
                "repeated_buyer_structure_sharpens_signal": (
                    _rate(high_with["reached_500k_plus_count"], high_with["launch_count"])
                    > _rate(high_without["reached_500k_plus_count"], high_without["launch_count"])
                ),
                "high_efficiency_with_repeated_buyer_500k_rate": _rate(high_with["reached_500k_plus_count"], high_with["launch_count"]),
                "high_efficiency_without_repeated_buyer_500k_rate": _rate(high_without["reached_500k_plus_count"], high_without["launch_count"]),
            }
        )
    return rows, summary


def _entry_side_feature_classification() -> list[dict[str, Any]]:
    rows = []
    for window, classification in WINDOWS.items():
        for feature in AGG_FEATURES:
            rows.append(
                {
                    "feature_name": f"{window}_{feature}",
                    "window_name": window,
                    "entry_side_classification": classification,
                    "notes": "descriptive proxy only; no rule or trading claim",
                }
            )
    return rows


def _recommended_next_action(
    strongest: list[dict[str, Any]],
    coverage: dict[str, Any],
    interaction_summary: list[dict[str, Any]],
) -> str:
    sharpened = any(row["repeated_buyer_structure_sharpens_signal"] for row in interaction_summary)
    if coverage["before_20k_repeated_runner_buyer_coverage_pct"] < 0.05:
        return "B. Full structural runner fingerprint report combining repeated buyers + FDV efficiency"
    if sharpened and strongest:
        return "B. Full structural runner fingerprint report combining repeated buyers + FDV efficiency"
    if strongest:
        return "A. Formal repeated-buyer thesis"
    return "E. Park repeated-buyer lane"


def _readiness(strongest: list[dict[str, Any]], coverage: dict[str, Any], interaction_summary: list[dict[str, Any]]) -> str:
    if coverage["before_20k_early_buyer_coverage_pct"] < 0.2:
        return "repeated_buyer_report_needs_enrichment"
    if strongest or any(row["repeated_buyer_structure_sharpens_signal"] for row in interaction_summary):
        return "repeated_buyer_report_ready_for_next_thesis"
    return "repeated_buyer_report_inconclusive"


def _strongest_differences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row for row in rows
        if row.get("comparison_group") != "milestone_tier"
        and row.get("classification") not in {None, "data_limited", "no_clear_difference"}
    ]
    candidates.sort(key=lambda row: abs(_float_or_none(row.get("median_difference")) or 0), reverse=True)
    return candidates[:8]


def _comparison_groups(launch_rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    plus_100 = {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}
    plus_500 = {"reached_500k_but_never_1m", "reached_1m_plus"}
    one_m = {"reached_1m_plus"}
    return [
        ("100k_plus_vs_sub_100k", [row for row in launch_rows if row["milestone_tier"] in plus_100], [row for row in launch_rows if row["milestone_tier"] not in plus_100]),
        ("500k_plus_vs_sub_500k", [row for row in launch_rows if row["milestone_tier"] in plus_500], [row for row in launch_rows if row["milestone_tier"] not in plus_500]),
        ("1m_plus_vs_sub_1m", [row for row in launch_rows if row["milestone_tier"] in one_m], [row for row in launch_rows if row["milestone_tier"] not in one_m]),
        ("1m_plus_vs_100k_only", [row for row in launch_rows if row["milestone_tier"] == "reached_1m_plus"], [row for row in launch_rows if row["milestone_tier"] == "reached_100k_but_never_200k"]),
    ]


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Repeated Buyer Runner Participation Report",
        "",
        f"Readiness: `{report['readiness_classification']}`",
        "",
        "This is a descriptive discovery report only. It does not create trading rules or promote a thesis.",
        "",
        "## Coverage",
        f"- Launches analyzed: {report['coverage_report']['total_launches']}",
        f"- Events audited: {report['coverage_report']['event_count']}",
        f"- Before-20k early-buyer coverage: {report['coverage_report']['before_20k_early_buyer_coverage_pct']:.4f}",
        f"- Before-20k repeated-runner buyer coverage: {report['coverage_report']['before_20k_repeated_runner_buyer_coverage_pct']:.4f}",
        "",
        "## Milestone Tiers",
    ]
    for tier, row in report["milestone_tier_summary"].items():
        lines.append(f"- {tier}: {row['launch_count']} launches")
    lines.extend(["", "## Strongest Tier Differences"])
    if report["strongest_tier_differences"]:
        for row in report["strongest_tier_differences"]:
            lines.append(f"- {row['comparison_group']} / {row['feature']}: {row['direction']} ({row['classification']})")
    else:
        lines.append("- No repeated-buyer tier difference cleared the descriptive filters.")
    lines.extend(["", "## FDV Efficiency Interaction"])
    for row in report["fdv_efficiency_interaction_summary"]:
        lines.append(
            f"- {row['efficiency_feature']}: sharpens={row['repeated_buyer_structure_sharpens_signal']}"
        )
    lines.extend(["", "## Recommended Next Action", report["recommended_next_action"], "", "## Limitations"])
    for item in report["limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path, tier_csv: Path, interaction_csv: Path) -> str:
    return "\n".join(
        [
            "# Repeated Buyer Runner Participation Status",
            "",
            "## Why This Report Was Created",
            "This report checks whether historical runner wallets appear among early buyers before new explosive FDV-proxy runners, and whether that repeated-buyer layer helps explain FDV efficiency.",
            "",
            f"Readiness classification: `{report['readiness_classification']}`",
            "",
            "## Data Coverage",
            f"- Launches analyzed: {report['coverage_report']['total_launches']}",
            f"- Events audited: {report['coverage_report']['event_count']}",
            f"- Early-buyer coverage before 20k: {report['coverage_report']['before_20k_early_buyer_coverage_pct']:.4f}",
            f"- Repeated-runner buyer coverage before 20k: {report['coverage_report']['before_20k_repeated_runner_buyer_coverage_pct']:.4f}",
            "",
            "## Repeated-Buyer Feature Definitions",
            "- Prior history is leakage-safe: only launches with earlier launch_time are counted.",
            "- repeated_buyer_proxy fields aggregate early buyer prior runner participation.",
            "- wallet_quality_proxy fields are descriptive proxies only.",
            "",
            "## Milestone Tier Findings",
            *[f"- {row['comparison_group']} / {row['feature']}: {row['direction']} ({row['classification']})" for row in report["strongest_tier_differences"][:6]],
            "",
            "## Interaction With FDV Efficiency",
            *[f"- {row['efficiency_feature']}: sharpens={row['repeated_buyer_structure_sharpens_signal']}" for row in report["fdv_efficiency_interaction_summary"]],
            "",
            "## Entry-Side vs Exit-Side Summary",
            "- before_20k, first_60s, and first_120s fields are entry-side observable proxies.",
            "- before_50k fields are post-trigger-only for this report.",
            "",
            "## Recommended Next Action",
            report["recommended_next_action"],
            "",
            "## Limitations",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Artifacts",
            f"- Summary JSON: {json_path}",
            f"- Summary Markdown: {md_path}",
            f"- Tier comparison CSV: {tier_csv}",
            f"- FDV interaction CSV: {interaction_csv}",
            "",
        ]
    )


def _limitations(coverage: dict[str, Any]) -> list[str]:
    return [
        "This is not a trading signal, validation result, or thesis promotion.",
        "All valuation fields use FDV proxy, not true market capitalization.",
        "Wallet prior participation is derived from observed lifecycle events only.",
        "Buyer identity coverage depends on deterministic actor fields in normalized events.",
        "Quantile buckets are descriptive and not optimized.",
        f"Before-20k early-buyer coverage is {coverage['before_20k_early_buyer_coverage_pct']:.4f}.",
    ]


def _event_field_availability(counts: Counter, total: int) -> dict[str, dict[str, Any]]:
    fields = {
        "early_buyer_wallet_addresses": counts["actor"],
        "event_actor_wallet_field": counts["actor"],
        "launch_id": counts["launch_id"],
        "mint": counts["mint"],
        "creator": counts["creator"],
        "launch_time": counts["launch_time"],
        "event_time": counts["event_time"],
        "side_buy_sell_classification": counts["side"],
        "wallet_prior_runner_participation_fields": 0,
    }
    return {name: _status_from_count(count, total) for name, count in fields.items()}


def _count_event_fields(event: dict[str, Any], counts: Counter) -> None:
    metadata = event.get("metadata_json") or {}
    raw = metadata.get("raw_record_metadata_json") or {}
    checks = {
        "actor": event.get("actor"),
        "launch_id": event.get("launch_id"),
        "mint": _mint(event),
        "creator": event.get("creator"),
        "launch_time": event.get("launch_ts") or raw.get("launch_ts"),
        "event_time": event.get("block_time"),
        "side": event.get("side") or event.get("event_type"),
    }
    for name, value in checks.items():
        if value not in (None, ""):
            counts[name] += 1


def _status_from_count(count: int, total: int) -> dict[str, Any]:
    if count == total and total:
        status = "available_now"
    elif count:
        status = "partially_available"
    else:
        status = "unavailable"
    return {"status": status, "rows_available": count, "rows_total": total, "coverage_pct": _pct(count, total)}


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


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0) >= threshold:
            return row
    return None


def _snapshot_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _age(row) <= age]
    if not eligible:
        return None
    selected = max(eligible, key=_age)
    prior = [row for row in rows if _age(row) < _age(selected)]
    if prior:
        selected = dict(selected)
        selected["_prior_snapshot"] = max(prior, key=_age)
    return selected


def _highest_tier(crossings: dict[str, dict[str, Any] | None]) -> str:
    if crossings.get("1m"):
        return "reached_1m_plus"
    if crossings.get("500k"):
        return "reached_500k_but_never_1m"
    if crossings.get("200k"):
        return "reached_200k_but_never_500k"
    if crossings.get("100k"):
        return "reached_100k_but_never_200k"
    if crossings.get("50k"):
        return "reached_50k_but_never_100k"
    if crossings.get("20k"):
        return "reached_20k_but_never_50k"
    return "never_reached_20k"


def _comparison_group_name(tier: str) -> str:
    return tier


def _is_buy_event(event: dict[str, Any]) -> bool:
    side = str(event.get("side") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    return side in {"buy", "accumulate"} or event_type in {"token_accumulation"}


def _event_age(event: dict[str, Any], launch_ts: int | None) -> int | None:
    block_time = _int_or_none(event.get("block_time"))
    if block_time is None or launch_ts is None:
        return None
    return block_time - launch_ts


def _bucket(value: float | None, cut: float | None, high: bool) -> bool:
    if value is None or cut is None:
        return False
    return value >= cut if high else value < cut


def _quantile_median(values: list[float | None]) -> float | None:
    vals = sorted(value for value in values if value is not None)
    return median(vals) if vals else None


def _distribution(values: list[float | None]) -> dict[str, Any]:
    vals = sorted(value for value in values if value is not None)
    if not vals:
        return {"sample_count": 0, "median": None, "iqr": None, "p10": None, "p90": None}
    return {
        "sample_count": len(vals),
        "median": median(vals),
        "iqr": [vals[len(vals) // 4], vals[(len(vals) * 3) // 4]],
        "p10": vals[int((len(vals) - 1) * 0.1)],
        "p90": vals[int((len(vals) - 1) * 0.9)],
    }


def _difference_classification(pos_med: float | None, neg_med: float | None, pos_count: int, neg_count: int) -> str:
    if pos_count < 30 or neg_count < 30 or pos_med is None or neg_med is None:
        return "data_limited"
    base = abs(neg_med) if abs(neg_med) > 1e-9 else 1.0
    rel = abs(pos_med - neg_med) / base
    if rel >= 1.0:
        return "strong_descriptive_difference"
    if rel >= 0.35:
        return "moderate_descriptive_difference"
    if rel >= 0.1:
        return "weak_descriptive_difference"
    return "no_clear_difference"


def _direction(pos_med: float | None, neg_med: float | None) -> str | None:
    if pos_med is None or neg_med is None:
        return None
    if pos_med > neg_med:
        return "higher"
    if pos_med < neg_med:
        return "lower"
    return "same"


def _median(values: list[Any]) -> float | None:
    vals = [_float_or_none(value) for value in values]
    vals = [value for value in vals if value is not None]
    return median(vals) if vals else None


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def _top_share(counter: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return sum(count for _, count in counter.most_common(n)) / total


def _date_range(values: Any) -> dict[str, str | None]:
    dates = sorted(value for value in values if value)
    return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _event_count(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    return _first_float(row.get("event_count"), row.get("tx_count"), (row.get("metadata_json") or {}).get("event_count"))


def _value(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    return _first_float(row.get("valuation_proxy_usd"), row.get("fdv_usd"))


def _age(row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    return _int_or_none(row.get("launch_age_seconds") or row.get("snapshot_age_seconds")) or 0


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("token_mint") or row.get("mint")
    return str(value) if value else None


def _launch_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


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


def _delta_value(row: dict[str, Any] | None, prior: dict[str, Any] | None) -> float | None:
    a = _value(row)
    b = _value(prior)
    if a is None or b is None:
        return None
    return a - b


def _ratio(a: Any, b: Any) -> float | None:
    num = _float_or_none(a)
    den = _float_or_none(b)
    if num is None or den in (None, 0):
        return None
    return num / den


def _pct(num: int, den: int) -> float:
    return num / den if den else 0.0
