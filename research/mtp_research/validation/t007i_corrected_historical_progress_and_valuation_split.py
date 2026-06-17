"""T007I historical proxy split for curve-progress vs valuation-confirmation.

This is an offline historical-analysis module. It does not trade, paper trade,
run live collection, or modify Mayhem collector behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


DEFAULT_SNAPSHOT_PATH = Path(
    "/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/"
    "T011_expanded_rerun/combined_expanded_lifecycle_snapshots.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = Path(
    "/Volumes/ORICO/MemeTraderPro/data/backtests/migration_graduation/"
    "combined_migration_graduation_labels_provenance_upgraded.jsonl"
)
DEFAULT_OUTPUT_DIR = Path("outputs/theses/t007i_corrected_historical_progress_and_valuation_split")

DENOMINATORS_USD = [25_000, 30_000, 35_000, 36_000, 40_000, 45_000, 50_000, 60_000, 69_000]
PROGRESS_THRESHOLDS_PCT = [50, 55, 60, 62.5, 65, 67.5, 70, 72.5, 75, 80, 85, 90, 95, 100]
VALUATION_BANDS_USD = [
    15_000,
    20_000,
    25_000,
    30_000,
    35_000,
    36_000,
    40_000,
    45_000,
    50_000,
    55_000,
    60_000,
    69_000,
    75_000,
    100_000,
    150_000,
    250_000,
    500_000,
    1_000_000,
]
VALUATION_TRANSITIONS_USD = [
    (30_000, 40_000),
    (36_000, 50_000),
    (40_000, 60_000),
    (50_000, 100_000),
    (100_000, 250_000),
    (250_000, 500_000),
    (500_000, 1_000_000),
]
VALUATION_STRATEGY_EXAMPLES_USD = [(30_000, 40_000), (36_000, 50_000), (40_000, 60_000), (50_000, 100_000)]


def valuation_threshold_usd(denominator_usd: float, threshold_pct: float) -> float:
    return round(float(denominator_usd) * (float(threshold_pct) / 100.0), 6)


def first_crossing(snapshots: list[dict[str, Any]], threshold_usd: float) -> dict[str, Any] | None:
    for row in sorted(snapshots, key=lambda item: _sort_ts(item.get("snapshot_ts"), missing=math.inf)):
        value = _valuation(row)
        if value is not None and value >= float(threshold_usd):
            return row
    return None


def continuation_to_next_band(snapshots: list[dict[str, Any]], entry_band_usd: float, next_band_usd: float) -> dict[str, Any]:
    entry = first_crossing(snapshots, entry_band_usd)
    if entry is None:
        return {
            "eligible": False,
            "continued": False,
            "entry_ts": None,
            "next_ts": None,
            "seconds_to_next": None,
            "entry_value": None,
            "next_value": None,
            "path_end_value": _last_valuation(snapshots),
        }
    entry_ts = _safe_float(entry.get("snapshot_ts"))
    later = [
        row
        for row in snapshots
        if _sort_ts(row.get("snapshot_ts"), missing=-math.inf) >= (entry_ts if entry_ts is not None else -math.inf)
    ]
    next_crossing = first_crossing(later, next_band_usd)
    if next_crossing is None:
        return {
            "eligible": True,
            "continued": False,
            "entry_ts": entry_ts,
            "next_ts": None,
            "seconds_to_next": None,
            "entry_value": _valuation(entry),
            "next_value": None,
            "path_end_value": _last_valuation(later),
        }
    next_ts = _safe_float(next_crossing.get("snapshot_ts"))
    return {
        "eligible": True,
        "continued": True,
        "entry_ts": entry_ts,
        "next_ts": next_ts,
        "seconds_to_next": None if entry_ts is None or next_ts is None else max(0.0, next_ts - entry_ts),
        "entry_value": _valuation(entry),
        "next_value": _valuation(next_crossing),
        "path_end_value": _last_valuation(later),
    }


def strategy_return(*, entry_value: float, exit_value: float, haircut: float = 0.0) -> float:
    if not entry_value:
        return 0.0
    return round(((float(exit_value) * (1.0 - float(haircut))) - float(entry_value)) / float(entry_value), 6)


def assign_chronological_splits(launches: list[dict[str, Any]], *, discovery_fraction: float = 0.6) -> list[dict[str, Any]]:
    ordered = sorted(launches, key=lambda row: (_sort_ts(row.get("launch_ts"), missing=math.inf), str(row.get("mint") or "")))
    cutoff = int(len(ordered) * float(discovery_fraction))
    result: list[dict[str, Any]] = []
    for idx, row in enumerate(ordered):
        copied = dict(row)
        copied["split"] = "discovery_window" if idx < cutoff else "validation_window"
        result.append(copied)
    return result


def run_analysis(
    *,
    snapshots_path: Path = DEFAULT_SNAPSHOT_PATH,
    migration_labels_path: Path = DEFAULT_MIGRATION_LABELS_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    labels_by_mint, labels_by_launch_id, label_source_counts = _load_migration_labels(migration_labels_path)
    profiles, inventory = _load_launch_profiles(snapshots_path, labels_by_mint, labels_by_launch_id)
    profiles = assign_chronological_splits(profiles)
    usable = [row for row in profiles if row["snapshots"]]
    baseline_rate = _rate(sum(1 for row in usable if row.get("migrated")), len(usable))

    denominator_rows = _denominator_metrics(usable, baseline_rate)
    valuation_rows = _valuation_band_metrics(usable, baseline_rate)
    continuation_rows = _valuation_continuation_metrics(usable)
    strategy_rows = _strategy_sanity_checks(usable)
    split_rows = _validation_split_metrics(usable)

    _write_csv(output_dir / "corrected_denominator_threshold_metrics.csv", denominator_rows)
    _write_csv(output_dir / "valuation_band_metrics.csv", valuation_rows)
    _write_csv(output_dir / "valuation_continuation_metrics.csv", continuation_rows)
    _write_csv(output_dir / "strategy_sanity_checks.csv", strategy_rows)
    _write_csv(output_dir / "validation_split_metrics.csv", split_rows)
    forward_plan = _forward_plan_markdown()
    (output_dir / "forward_dual_thesis_collection_plan.md").write_text(forward_plan, encoding="utf-8")

    top_denominator = _rank_denominator_rows(denominator_rows)
    top_band = _rank_band_rows(valuation_rows)
    summary = {
        "report_id": "T007I_Corrected_Historical_Progress_And_Valuation_Split",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": str(snapshots_path),
        "migration_labels_path": str(migration_labels_path),
        "output_dir": str(output_dir),
        "total_launch_universe": len(profiles),
        "snapshot_launches": inventory["snapshot_launches"],
        "snapshot_rows": inventory["snapshot_rows"],
        "usable_valuation_proxy_launches": len(usable),
        "missing_valuation_proxy_launches": len(profiles) - len(usable),
        "migration_label_positive_count_joined": sum(1 for row in usable if row.get("migrated")),
        "baseline_migration_rate": baseline_rate,
        "migration_label_source_counts": dict(label_source_counts),
        "snapshot_sources": [str(snapshots_path)],
        "valuation_field_used": "valuation_proxy_usd first, fdv_usd fallback",
        "migration_definition_used": "positive row in combined_migration_graduation_labels_provenance_upgraded.jsonl joined by mint or launch_id",
        "old_69k_proxy_caveat": "Old T007 used valuation_proxy_usd / 69000 as a completion proxy; this was not exact reserve-based Pump.fun curve progress.",
        "true_curve_progress_proxy_label": _true_curve_progress_label(denominator_rows),
        "valuation_confirmation_label": _valuation_confirmation_label(valuation_rows, continuation_rows),
        "top_denominator_validation_rows": top_denominator[:10],
        "top_valuation_band_validation_rows": top_band[:10],
        "artifact_paths": {
            "summary_md": str(output_dir / "summary.md"),
            "corrected_denominator_threshold_metrics_csv": str(output_dir / "corrected_denominator_threshold_metrics.csv"),
            "valuation_band_metrics_csv": str(output_dir / "valuation_band_metrics.csv"),
            "valuation_continuation_metrics_csv": str(output_dir / "valuation_continuation_metrics.csv"),
            "strategy_sanity_checks_csv": str(output_dir / "strategy_sanity_checks.csv"),
            "validation_split_metrics_csv": str(output_dir / "validation_split_metrics.csv"),
            "forward_dual_thesis_collection_plan_md": str(output_dir / "forward_dual_thesis_collection_plan.md"),
        },
    }
    (output_dir / "summary.md").write_text(_summary_markdown(summary, denominator_rows, valuation_rows, continuation_rows), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _load_migration_labels(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], Counter]:
    by_mint: dict[str, dict[str, Any]] = {}
    by_launch_id: dict[str, dict[str, Any]] = {}
    source_counts: Counter = Counter()
    if not path.exists():
        return by_mint, by_launch_id, source_counts
    for row in _iter_jsonl(path):
        mint = str(row.get("mint") or "")
        launch_id = str(row.get("launch_id") or "")
        source = str(row.get("migration_source") or "unknown")
        source_counts[source] += 1
        label = {
            "mint": mint,
            "launch_id": launch_id,
            "migration_time": row.get("migration_time"),
            "migration_ts": _parse_time(row.get("migration_time")),
            "migration_source": source,
            "migration_confidence": _safe_float(row.get("migration_confidence")),
            "pumpfun_migrate_event_observed": bool(row.get("pumpfun_migrate_event_observed")),
        }
        if mint:
            by_mint[mint] = label
        if launch_id:
            by_launch_id[launch_id] = label
    return by_mint, by_launch_id, source_counts


def _load_launch_profiles(
    path: Path,
    labels_by_mint: dict[str, dict[str, Any]],
    labels_by_launch_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    snapshot_rows = 0
    valuation_missing_rows = 0
    source_counts: Counter = Counter()
    for row in _iter_jsonl(path):
        snapshot_rows += 1
        mint = str(row.get("token_mint") or row.get("mint") or "")
        launch_id = str(row.get("launch_id") or mint)
        key = mint or launch_id
        if not key:
            continue
        profile = profiles.setdefault(
            key,
            {
                "mint": mint,
                "launch_id": launch_id,
                "launch_ts": _safe_float(row.get("launch_ts")),
                "launch_date": _date_key(_safe_float(row.get("launch_ts"))),
                "snapshots": [],
                "snapshot_rows": 0,
                "valuation_missing_rows": 0,
                "source_files": set(),
            },
        )
        profile["snapshot_rows"] += 1
        if profile.get("launch_ts") is None and _safe_float(row.get("launch_ts")) is not None:
            profile["launch_ts"] = _safe_float(row.get("launch_ts"))
            profile["launch_date"] = _date_key(profile["launch_ts"])
        value = _safe_float(row.get("valuation_proxy_usd"))
        if value is None:
            value = _safe_float(row.get("fdv_usd"))
        if value is None or row.get("valuation_proxy_available") is False:
            profile["valuation_missing_rows"] += 1
            valuation_missing_rows += 1
            continue
        snapshot_ts = _safe_float(row.get("snapshot_ts"))
        if snapshot_ts is None and profile.get("launch_ts") is not None and _safe_float(row.get("launch_age_seconds")) is not None:
            snapshot_ts = float(profile["launch_ts"]) + float(row["launch_age_seconds"])
        profile["snapshots"].append(
            {
                "snapshot_ts": snapshot_ts,
                "launch_age_seconds": _safe_float(row.get("launch_age_seconds")),
                "valuation_proxy_usd": value,
                "valuation_source": row.get("valuation_source") or row.get("price_source") or "unknown",
            }
        )
        source_counts[str(row.get("valuation_source") or row.get("price_source") or "unknown")] += 1
    result: list[dict[str, Any]] = []
    for profile in profiles.values():
        profile["snapshots"].sort(key=lambda item: (_safe_float(item.get("snapshot_ts")) or math.inf))
        label = labels_by_mint.get(profile.get("mint") or "") or labels_by_launch_id.get(profile.get("launch_id") or "")
        profile["migrated"] = label is not None
        profile["migration_ts"] = label.get("migration_ts") if label else None
        profile["migration_source"] = label.get("migration_source") if label else None
        profile["migration_confidence"] = label.get("migration_confidence") if label else None
        profile["max_valuation_proxy_usd"] = max((_valuation(row) or 0.0 for row in profile["snapshots"]), default=None)
        profile["last_valuation_proxy_usd"] = _last_valuation(profile["snapshots"])
        result.append(profile)
    inventory = {
        "snapshot_rows": snapshot_rows,
        "snapshot_launches": len(profiles),
        "valuation_missing_rows": valuation_missing_rows,
        "valuation_source_counts": dict(source_counts),
    }
    return result, inventory


def _denominator_metrics(launches: list[dict[str, Any]], baseline_rate: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for denominator in DENOMINATORS_USD:
        for pct in PROGRESS_THRESHOLDS_PCT:
            threshold = valuation_threshold_usd(denominator, pct)
            crossed = _crossed_launches(launches, threshold)
            rows.append(
                {
                    "thesis": "T007A_true_bonding_curve_progress",
                    "proxy_type": "fdv_denominator_progress_proxy",
                    "denominator_usd": denominator,
                    "threshold_pct": pct,
                    "valuation_threshold_usd": threshold,
                    **_crossing_metric_fields(launches, crossed, baseline_rate),
                }
            )
    return rows


def _valuation_band_metrics(launches: list[dict[str, Any]], baseline_rate: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for band in VALUATION_BANDS_USD:
        crossed = _crossed_launches(launches, band)
        post_max = [_safe_float(row.get("max_valuation_proxy_usd")) for row, _ in crossed]
        rows.append(
            {
                "thesis": "T007B_valuation_confirmation_runner_filter",
                "band_usd": band,
                **_crossing_metric_fields(launches, crossed, baseline_rate),
                "median_post_crossing_max_valuation_usd": _median(post_max),
                "max_post_crossing_valuation_usd": _max(post_max),
            }
        )
    return rows


def _valuation_continuation_metrics(launches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry_band, next_band in VALUATION_TRANSITIONS_USD:
        eligible = []
        continued = []
        seconds = []
        validation_eligible = []
        validation_continued = []
        for launch in launches:
            result = continuation_to_next_band(launch["snapshots"], entry_band, next_band)
            if not result["eligible"]:
                continue
            eligible.append(result)
            if launch.get("split") == "validation_window":
                validation_eligible.append(result)
            if result["continued"]:
                continued.append(result)
                if result["seconds_to_next"] is not None:
                    seconds.append(result["seconds_to_next"])
                if launch.get("split") == "validation_window":
                    validation_continued.append(result)
        rate = _rate(len(continued), len(eligible))
        gross = (next_band / entry_band) - 1.0
        rows.append(
            {
                "entry_band_usd": entry_band,
                "next_band_usd": next_band,
                "launches_crossing_entry_band": len(eligible),
                "continued_to_next_band": len(continued),
                "continuation_rate": rate,
                "failure_no_continuation_rate": 1.0 - rate if len(eligible) else None,
                "validation_period_continuation_rate": _rate(len(validation_continued), len(validation_eligible)),
                "gross_proxy_return_to_next_band": round(gross, 6),
                "rough_net_expectancy_after_5pct_haircut": _expectancy(entry_band, next_band, rate, 0.05),
                "rough_net_expectancy_after_10pct_haircut": _expectancy(entry_band, next_band, rate, 0.10),
                "rough_net_expectancy_after_20pct_haircut": _expectancy(entry_band, next_band, rate, 0.20),
                "median_time_crossing_to_next_band_seconds": _median(seconds),
            }
        )
    return rows


def _strategy_sanity_checks(launches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for denominator in DENOMINATORS_USD:
        for pct in PROGRESS_THRESHOLDS_PCT:
            entry = valuation_threshold_usd(denominator, pct)
            rows.append(_strategy_row(launches, "fdv_denominator_progress_proxy", entry, denominator, denominator, pct))
    for entry, target in VALUATION_STRATEGY_EXAMPLES_USD:
        rows.append(_strategy_row(launches, "valuation_confirmation", entry, target, None, None))
    return rows


def _strategy_row(
    launches: list[dict[str, Any]],
    strategy_type: str,
    entry_threshold: float,
    target_exit: float,
    denominator: float | None,
    pct: float | None,
) -> dict[str, Any]:
    returns_by_haircut: dict[float, list[float]] = {0.0: [], 0.05: [], 0.10: [], 0.20: []}
    time_to_exit: list[float] = []
    wins = 0
    validation_entries = 0
    validation_wins = 0
    entries = 0
    failures = 0
    for launch in launches:
        crossing = first_crossing(launch["snapshots"], entry_threshold)
        if crossing is None:
            continue
        entries += 1
        if launch.get("split") == "validation_window":
            validation_entries += 1
        entry_ts = _safe_float(crossing.get("snapshot_ts"))
        later = [
            row
            for row in launch["snapshots"]
            if _sort_ts(row.get("snapshot_ts"), missing=-math.inf) >= (entry_ts if entry_ts is not None else -math.inf)
        ]
        target = first_crossing(later, target_exit)
        won = target is not None
        if won:
            wins += 1
            if launch.get("split") == "validation_window":
                validation_wins += 1
            exit_value = target_exit
            target_ts = _safe_float(target.get("snapshot_ts"))
            if target_ts is not None and entry_ts is not None:
                time_to_exit.append(max(0.0, target_ts - entry_ts))
        else:
            failures += 1
            exit_value = _last_valuation(later) or 0.0
        for haircut in returns_by_haircut:
            returns_by_haircut[haircut].append(strategy_return(entry_value=entry_threshold, exit_value=exit_value, haircut=haircut))
    return {
        "strategy_type": strategy_type,
        "denominator_usd": denominator,
        "threshold_pct": pct,
        "entry_threshold_usd": entry_threshold,
        "exit_target_usd": target_exit,
        "entries": entries,
        "wins": wins,
        "win_rate": _rate(wins, entries),
        "failures": failures,
        "average_gross_return": _mean(returns_by_haircut[0.0]),
        "median_gross_return": _median(returns_by_haircut[0.0]),
        "average_net_return_after_5pct_haircut": _mean(returns_by_haircut[0.05]),
        "median_net_return_after_5pct_haircut": _median(returns_by_haircut[0.05]),
        "average_net_return_after_10pct_haircut": _mean(returns_by_haircut[0.10]),
        "median_net_return_after_10pct_haircut": _median(returns_by_haircut[0.10]),
        "average_net_return_after_20pct_haircut": _mean(returns_by_haircut[0.20]),
        "median_net_return_after_20pct_haircut": _median(returns_by_haircut[0.20]),
        "median_time_to_exit_seconds": _median(time_to_exit),
        "validation_period_entries": validation_entries,
        "validation_period_win_rate": _rate(validation_wins, validation_entries),
    }


def _validation_split_metrics(launches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in ("discovery_window", "validation_window"):
        split_launches = [row for row in launches if row.get("split") == split]
        baseline = _rate(sum(1 for row in split_launches if row.get("migrated")), len(split_launches))
        for denominator in DENOMINATORS_USD:
            for pct in PROGRESS_THRESHOLDS_PCT:
                threshold = valuation_threshold_usd(denominator, pct)
                crossed = _crossed_launches(split_launches, threshold)
                rows.append(
                    {
                        "split": split,
                        "thesis": "T007A_true_bonding_curve_progress",
                        "denominator_usd": denominator,
                        "threshold_pct": pct,
                        "band_usd": None,
                        "valuation_threshold_usd": threshold,
                        "launches": len(split_launches),
                        "crossing_count": len(crossed),
                        "migration_rate_after_crossing": _rate(_migrated_after_count(crossed), len(crossed)),
                        "baseline_migration_rate": baseline,
                    }
                )
        for band in VALUATION_BANDS_USD:
            crossed = _crossed_launches(split_launches, band)
            rows.append(
                {
                    "split": split,
                    "thesis": "T007B_valuation_confirmation_runner_filter",
                    "denominator_usd": None,
                    "threshold_pct": None,
                    "band_usd": band,
                    "valuation_threshold_usd": band,
                    "launches": len(split_launches),
                    "crossing_count": len(crossed),
                    "migration_rate_after_crossing": _rate(_migrated_after_count(crossed), len(crossed)),
                    "baseline_migration_rate": baseline,
                }
            )
    return rows


def _crossing_metric_fields(
    launches: list[dict[str, Any]],
    crossed: list[tuple[dict[str, Any], dict[str, Any]]],
    baseline_rate: float,
) -> dict[str, Any]:
    crossing_count = len(crossed)
    migrated_after = _migrated_after_count(crossed)
    cond = _rate(migrated_after, crossing_count)
    launch_to_crossing = []
    crossing_to_migration = []
    missing_timing = 0
    migration_before_crossing = 0
    for launch, crossing in crossed:
        crossing_ts = _safe_float(crossing.get("snapshot_ts"))
        launch_ts = _safe_float(launch.get("launch_ts"))
        migration_ts = _safe_float(launch.get("migration_ts"))
        if crossing_ts is not None and launch_ts is not None:
            launch_to_crossing.append(max(0.0, crossing_ts - launch_ts))
        else:
            missing_timing += 1
        if launch.get("migrated") and migration_ts is not None and crossing_ts is not None:
            if migration_ts >= crossing_ts:
                crossing_to_migration.append(migration_ts - crossing_ts)
            else:
                migration_before_crossing += 1
        elif launch.get("migrated"):
            missing_timing += 1
    discovery = [(launch, crossing) for launch, crossing in crossed if launch.get("split") == "discovery_window"]
    validation = [(launch, crossing) for launch, crossing in crossed if launch.get("split") == "validation_window"]
    top_date, top_date_share = _top_concentration(crossed, "day")
    top_week, top_week_share = _top_concentration(crossed, "week")
    top_month, top_month_share = _top_concentration(crossed, "month")
    return {
        "usable_launches": len(launches),
        "launches_crossing_threshold": crossing_count,
        "pct_of_usable_launches_crossing_threshold": _rate(crossing_count, len(launches)),
        "migrating_after_crossing": migrated_after,
        "conditional_migration_rate": cond,
        "baseline_migration_rate": baseline_rate,
        "lift_vs_baseline": None if baseline_rate in (None, 0) or cond is None else round(cond / baseline_rate, 6),
        "failure_rate": None if cond is None else round(1.0 - cond, 6),
        "median_time_launch_to_crossing_seconds": _median(launch_to_crossing),
        "median_time_crossing_to_migration_seconds": _median(crossing_to_migration),
        "p25_crossing_to_migration_seconds": _percentile(crossing_to_migration, 25),
        "p50_crossing_to_migration_seconds": _percentile(crossing_to_migration, 50),
        "p75_crossing_to_migration_seconds": _percentile(crossing_to_migration, 75),
        "p90_crossing_to_migration_seconds": _percentile(crossing_to_migration, 90),
        "missing_timing_counts": missing_timing,
        "migration_before_crossing_count": migration_before_crossing,
        "chronological_validation_migration_rate": _rate(_migrated_after_count(validation), len(validation)),
        "discovery_window_migration_rate": _rate(_migrated_after_count(discovery), len(discovery)),
        "validation_window_migration_rate": _rate(_migrated_after_count(validation), len(validation)),
        "top_date": top_date,
        "top_date_share": top_date_share,
        "top_week": top_week,
        "top_week_share": top_week_share,
        "top_month": top_month,
        "top_month_share": top_month_share,
    }


def _crossed_launches(launches: list[dict[str, Any]], threshold_usd: float) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    crossed = []
    for launch in launches:
        crossing = first_crossing(launch["snapshots"], threshold_usd)
        if crossing is not None:
            crossed.append((launch, crossing))
    return crossed


def _migrated_after_count(crossed: list[tuple[dict[str, Any], dict[str, Any]]]) -> int:
    count = 0
    for launch, crossing in crossed:
        if not launch.get("migrated"):
            continue
        migration_ts = _safe_float(launch.get("migration_ts"))
        crossing_ts = _safe_float(crossing.get("snapshot_ts"))
        if migration_ts is None or crossing_ts is None or migration_ts >= crossing_ts:
            count += 1
    return count


def _rank_denominator_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [row for row in rows if row.get("launches_crossing_threshold", 0) >= 25]
    return sorted(
        ranked,
        key=lambda row: (
            row.get("validation_window_migration_rate") or 0,
            row.get("launches_crossing_threshold") or 0,
            row.get("lift_vs_baseline") or 0,
        ),
        reverse=True,
    )


def _rank_band_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [row for row in rows if row.get("launches_crossing_threshold", 0) >= 25]
    return sorted(
        ranked,
        key=lambda row: (
            row.get("validation_window_migration_rate") or 0,
            row.get("launches_crossing_threshold") or 0,
            row.get("lift_vs_baseline") or 0,
        ),
        reverse=True,
    )


def _true_curve_progress_label(rows: list[dict[str, Any]]) -> str:
    validation_rows = [row for row in rows if row.get("denominator_usd") in (30_000, 35_000, 36_000, 40_000)]
    if not validation_rows:
        return "invalid_due_to_static_snapshot_limitations"
    supported = [row for row in validation_rows if (row.get("launches_crossing_threshold") or 0) >= 25 and (row.get("lift_vs_baseline") or 0) >= 1.25]
    return "forward_test_true_curve_progress" if supported else "weak_proxy_only"


def _valuation_confirmation_label(rows: list[dict[str, Any]], continuation_rows: list[dict[str, Any]]) -> str:
    supported = [
        row
        for row in rows
        if row.get("band_usd") in (30_000, 36_000, 40_000, 45_000, 50_000, 55_000, 60_000)
        and (row.get("launches_crossing_threshold") or 0) >= 25
        and (row.get("lift_vs_baseline") or 0) >= 1.25
    ]
    continuation_supported = [row for row in continuation_rows if (row.get("launches_crossing_entry_band") or 0) >= 25]
    if supported or continuation_supported:
        return "forward_test_valuation_confirmation"
    return "weak_signal_only"


def _summary_markdown(
    summary: dict[str, Any],
    denominator_rows: list[dict[str, Any]],
    valuation_rows: list[dict[str, Any]],
    continuation_rows: list[dict[str, Any]],
) -> str:
    denom_36 = [row for row in denominator_rows if row.get("denominator_usd") == 36_000]
    denom_69 = [row for row in denominator_rows if row.get("denominator_usd") == 69_000]
    band_focus = [row for row in valuation_rows if row.get("band_usd") in (30_000, 36_000, 40_000, 50_000, 60_000, 69_000)]
    lines = [
        "# T007I Corrected Historical Progress And Valuation Split",
        "",
        "This is historical proxy analysis only. It does not trade, paper trade, run live collection, tune thresholds, or touch Mayhem collector behavior.",
        "",
        "## Dataset and labels",
        "",
        f"- Snapshot source: `{summary['snapshot_path']}`",
        f"- Migration labels: `{summary['migration_labels_path']}`",
        f"- Total launch universe: `{summary['total_launch_universe']}`",
        f"- Snapshot rows: `{summary['snapshot_rows']}`",
        f"- Usable valuation/progress proxy launches: `{summary['usable_valuation_proxy_launches']}`",
        f"- Missing valuation proxy launches: `{summary['missing_valuation_proxy_launches']}`",
        f"- Positive migration labels joined: `{summary['migration_label_positive_count_joined']}`",
        f"- Baseline migration label rate: `{_fmt_pct(summary['baseline_migration_rate'])}`",
        f"- Valuation field used: `{summary['valuation_field_used']}`",
        f"- Migration definition: `{summary['migration_definition_used']}`",
        f"- Migration label source counts: `{json.dumps(summary['migration_label_source_counts'], sort_keys=True)}`",
        "",
        "## Old $69k proxy caveat",
        "",
        "The old T007 proxy used `valuation_proxy_usd / 69000` as if it were curve completion. That was not exact Pump.fun reserve-based progress. It mostly selects tokens that already reached higher valuation/FDV proxy levels, so it can accidentally behave like a valuation-confirmation or runner-continuation filter.",
        "",
        "## Corrected denominator proxy result",
        "",
        "All denominator rows are labeled `fdv_denominator_progress_proxy`, not true curve progress. The strongest validation-ranked rows are in `corrected_denominator_threshold_metrics.csv`.",
        "",
        _mini_table(summary["top_denominator_validation_rows"][:8], ["denominator_usd", "threshold_pct", "valuation_threshold_usd", "launches_crossing_threshold", "conditional_migration_rate", "lift_vs_baseline", "validation_window_migration_rate"]),
        "",
        "### $36k denominator focus",
        "",
        _mini_table(_rank_denominator_rows(denom_36)[:8], ["denominator_usd", "threshold_pct", "valuation_threshold_usd", "launches_crossing_threshold", "conditional_migration_rate", "lift_vs_baseline", "validation_window_migration_rate"]),
        "",
        "### Old $69k denominator focus",
        "",
        _mini_table(_rank_denominator_rows(denom_69)[:8], ["denominator_usd", "threshold_pct", "valuation_threshold_usd", "launches_crossing_threshold", "conditional_migration_rate", "lift_vs_baseline", "validation_window_migration_rate"]),
        "",
        "## Raw valuation band result",
        "",
        _mini_table(band_focus, ["band_usd", "launches_crossing_threshold", "conditional_migration_rate", "lift_vs_baseline", "validation_window_migration_rate", "median_time_launch_to_crossing_seconds"]),
        "",
        "## Continuation result",
        "",
        _mini_table(continuation_rows, ["entry_band_usd", "next_band_usd", "launches_crossing_entry_band", "continuation_rate", "validation_period_continuation_rate", "rough_net_expectancy_after_10pct_haircut"]),
        "",
        "## Labels",
        "",
        f"- True curve-progress proxy label: `{summary['true_curve_progress_proxy_label']}`",
        f"- Valuation-confirmation label: `{summary['valuation_confirmation_label']}`",
        "",
        "## Interpretation",
        "",
        "- `$36k` is now explicitly tested as a denominator/completion proxy, but this remains static FDV-denominator proxy work until the forward recorder computes reserve-based progress.",
        "- If the best rows cluster around raw `$40k-$60k` bands or old `$69k` denominator thresholds, the old T007 probably found a valuation-confirmation signal rather than true curve completion.",
        "- True curve progress still deserves forward testing because the streaming collector can now observe live curve state quickly, but historical static snapshots cannot settle the reserve-formula question.",
        "- Valuation confirmation also deserves forward testing in the same collector because it uses the same admitted stream and curve observations; do not create a second collector.",
        "",
        "## Next recommended engineering step",
        "",
        "Implement reserve-based `true_curve_progress` computation in the forward T007 recorder, preserve valuation-band crossings in the same output stream, then run a short source/progress smoke before any longer collection.",
        "",
        "## Artifact paths",
        "",
    ]
    for name, path in summary["artifact_paths"].items():
        lines.append(f"- `{name}`: `{path}`")
    return "\n".join(lines) + "\n"


def _forward_plan_markdown() -> str:
    bands = ", ".join(f"${value:,.0f}" for value in VALUATION_BANDS_USD)
    thresholds = ", ".join(f"{value}%" for value in PROGRESS_THRESHOLDS_PCT if value != 100)
    return f"""# T007 Forward Dual-Thesis Collection Plan

Mayhem remains paused. This plan does not trade, paper trade, change execution logic, tune thresholds, or require two competing collectors.

## One collector, two thesis outputs

The forward recorder should keep one normalized transactionSubscribe launch stream. Every admitted launch should produce both:

- `true_curve_progress`: reserve-based Pump.fun curve progress percent, when formula status is confirmed.
- `valuation_confirmation`: valuation/FDV proxy observed at birth and every curve observation.

## Thesis A: true_curve_progress

Collect:

- Reserve-based progress percent.
- Crossings for {thresholds}.
- Crossing timestamp, slot, and collector received time.
- Migration timestamp, if observed.
- Lead time from crossing to migration.
- Raw reserve fields used by the formula.
- Progress formula version and status.

Required state fields:

- `virtual_token_reserves`
- `virtual_sol_reserves`
- `real_token_reserves`
- `real_sol_reserves`
- `token_total_supply`
- `complete`
- `bonding_curve_account`
- `associated_bonding_curve`, if available

## Thesis B: valuation_confirmation

Collect:

- Valuation/FDV proxy at birth and each curve observation.
- First crossings of {bands}.
- Time from launch to valuation band.
- Time from migration to valuation band when migration is known.
- Continuation to next valuation band.
- Failure/path-end behavior.

## Forward philosophy

Do not create two collectors. The same admitted launch stream and curve observations are sufficient to test both theses. Add fields and outputs so downstream analysis can split the two theses without changing collection behavior.
"""


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("._"):
                continue
            yield json.loads(line)


def _valuation(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else row.get("valuation_proxy_usd"))


def _last_valuation(snapshots: list[dict[str, Any]]) -> float | None:
    valid = [row for row in sorted(snapshots, key=lambda item: _sort_ts(item.get("snapshot_ts"), missing=-math.inf)) if _valuation(row) is not None]
    return _valuation(valid[-1]) if valid else None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _sort_ts(value: Any, *, missing: float) -> float:
    number = _safe_float(value)
    return missing if number is None else number


def _parse_time(value: Any) -> float | None:
    if value is None or value == "":
        return None
    numeric = _safe_float(value)
    if numeric is not None:
        return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _date_key(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def _week_key(ts: float | None) -> str | None:
    if ts is None:
        return None
    iso = datetime.fromtimestamp(ts, timezone.utc).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _month_key(ts: float | None) -> str | None:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return f"{dt.year}-{dt.month:02d}"


def _top_concentration(crossed: list[tuple[dict[str, Any], dict[str, Any]]], grain: str) -> tuple[str | None, float | None]:
    counter: Counter = Counter()
    for launch, _crossing in crossed:
        ts = _safe_float(launch.get("launch_ts"))
        key = _date_key(ts) if grain == "day" else _week_key(ts) if grain == "week" else _month_key(ts)
        if key:
            counter[key] += 1
    if not counter:
        return None, None
    key, count = counter.most_common(1)[0]
    return key, _rate(count, len(crossed))


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _median(values: list[Any]) -> float | None:
    clean = [_safe_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    return round(float(median(clean)), 6) if clean else None


def _mean(values: list[Any]) -> float | None:
    clean = [_safe_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    return round(sum(clean) / len(clean), 6) if clean else None


def _max(values: list[Any]) -> float | None:
    clean = [_safe_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    return round(max(clean), 6) if clean else None


def _percentile(values: list[Any], percentile: float) -> float | None:
    clean = sorted(value for value in (_safe_float(value) for value in values) if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return round(clean[0], 6)
    rank = (len(clean) - 1) * (float(percentile) / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return round(clean[int(rank)], 6)
    return round(clean[lo] + (clean[hi] - clean[lo]) * (rank - lo), 6)


def _expectancy(entry: float, target: float, continuation_rate: float | None, haircut: float) -> float | None:
    if continuation_rate is None:
        return None
    win_return = ((float(target) * (1.0 - haircut)) - float(entry)) / float(entry)
    return round((continuation_rate * win_return) + ((1.0 - continuation_rate) * -1.0), 6)


def _fmt_pct(value: Any) -> str:
    number = _safe_float(value)
    return "n/a" if number is None else f"{number * 100:.2f}%"


def _mini_table(rows: list[dict[str, Any]], fields: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = ["|" + "|".join(fields) + "|", "|" + "|".join("---" for _ in fields) + "|"]
    for row in rows:
        lines.append("|" + "|".join(str(row.get(field, "")) for field in fields) + "|")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run T007I corrected historical progress and valuation split.")
    parser.add_argument("--snapshots-path", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--migration-labels-path", type=Path, default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    summary = run_analysis(snapshots_path=args.snapshots_path, migration_labels_path=args.migration_labels_path, output_dir=args.output_dir)
    print("report_id=T007I_Corrected_Historical_Progress_And_Valuation_Split")
    print(f"output_dir={summary['output_dir']}")
    print(f"total_launch_universe={summary['total_launch_universe']}")
    print(f"usable_valuation_proxy_launches={summary['usable_valuation_proxy_launches']}")
    print(f"baseline_migration_rate={summary['baseline_migration_rate']}")
    print(f"true_curve_progress_proxy_label={summary['true_curve_progress_proxy_label']}")
    print(f"valuation_confirmation_label={summary['valuation_confirmation_label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
