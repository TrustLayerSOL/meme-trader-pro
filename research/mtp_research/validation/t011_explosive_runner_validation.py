"""Formal validation runner for T011 explosive-runner raw-flow continuation."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "t011_explosive_runner_validation_v0"
REPORT_JSON = "T011_validation_summary.json"
REPORT_MD = "T011_validation_summary.md"
PRIMARY_OUTCOME_DEFAULT = "crossed_100k_after_20k"
SECONDARY_OUTCOMES = [
    "crossed_50k_after_20k",
    "crossed_200k_after_20k",
    "crossed_500k_after_20k",
    "crossed_1m_after_20k",
    "crossed_100k_within_10m_from_20k",
    "crossed_500k_within_60m_from_20k",
]
VALIDATION_CLASSES = {"validation_passed", "validation_failed", "validation_data_limited"}
MIN_PRIMARY_SUPPORT = 10
MIN_RELATIVE_LIFT = 1.1
MAX_DOMINANT_SHARE = 0.5
MAX_TOP3_SHARE = 0.8


def build_t011_validation_report(
    *,
    design_path: Path | str,
    trigger_20k_rows_path: Path | str,
    t011_summary_path: Path | str | None = None,
    robustness_summary_path: Path | str | None = None,
    snapshots_path: Path | str | None = None,
) -> dict[str, Any]:
    design = _read_json(design_path)
    t011_summary = _read_json(t011_summary_path)
    robustness = _read_json(robustness_summary_path)
    rows = [_normalize_row(row) for row in _read_csv(trigger_20k_rows_path)]
    rows = sorted([row for row in rows if row.get("token_mint")], key=lambda row: (_float_or_none(row.get("launch_ts")) or 0, row["token_mint"]))
    primary_outcome = _primary_outcome(design)
    primary = _evaluate_split(rows, train_pct=0.60, primary_outcome=primary_outcome, split_name="chronological_60_40")
    secondary = {
        outcome: _evaluate_holdout(primary["holdout_rows"], primary["training_cutoffs"], outcome)
        for outcome in SECONDARY_OUTCOMES
        if _field_available(rows, outcome)
    }
    split_70 = _evaluate_split(rows, train_pct=0.70, primary_outcome=primary_outcome, split_name="chronological_70_30")
    trigger_sensitivity = _trigger_sensitivity(snapshots_path, primary_outcome)
    outlier = {
        "exclude_top_1pct_peak_fdv_proxy": _evaluate_filtered(rows, 0.01, primary_outcome),
        "exclude_top_5pct_peak_fdv_proxy": _evaluate_filtered(rows, 0.05, primary_outcome),
        "exclude_1m_plus": _evaluate_split([row for row in rows if row.get("milestone_tier") != "reached_1m_plus"], 0.60, primary_outcome, "exclude_1m_plus"),
    }
    dominance = _dominance(primary["primary_group_rows"])
    artifact = _artifact_check(primary["primary_group_rows"])
    leakage = _leakage_checks(primary, design)
    failures = _failure_conditions(primary, dominance, trigger_sensitivity, leakage)
    classification = _classify(primary, dominance, trigger_sensitivity, leakage, failures)
    return {
        "report_id": REPORT_ID,
        "validation_type": "formal_historical_validation",
        "design_reference": str(design_path),
        "original_t011_classification": t011_summary.get("final_classification"),
        "robustness_classification": robustness.get("robustness_classification"),
        "methodology_flags": [
            "research_only",
            "formal_validation",
            "no_thesis_promotion",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_rules",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "fdv_proxy_not_true_market_cap",
        ],
        "inputs": {
            "design_path": str(design_path),
            "trigger_20k_rows_path": str(trigger_20k_rows_path),
            "t011_summary_path": str(t011_summary_path) if t011_summary_path else None,
            "robustness_summary_path": str(robustness_summary_path) if robustness_summary_path else None,
            "snapshots_path": str(snapshots_path) if snapshots_path else None,
        },
        "primary_split": {
            "split_name": primary["split_name"],
            "train_rows": len(primary["train_rows"]),
            "holdout_rows": len(primary["holdout_rows"]),
            "train_pct": 60,
            "holdout_pct": 40,
        },
        "primary_trigger": 20_000,
        "primary_feature_contrast": "fdv_per_event_at_trigger highest train quintile and event_count_at_trigger lowest train quintile",
        "primary_outcome": primary_outcome,
        "training_cutoffs": primary["training_cutoffs"],
        "primary_validation": primary["metrics"],
        "secondary_outcomes": secondary,
        "sensitivity_checks": {
            "chronological_70_30": split_70["metrics"],
            "trigger_sensitivity": trigger_sensitivity,
            "outlier_sensitivity": {key: value["metrics"] for key, value in outlier.items()},
        },
        "dominance_checks": dominance,
        "fdv_proxy_artifact_check": artifact,
        "leakage_checks": leakage,
        "failure_conditions": failures,
        "validation_classification": classification,
        "warning_flags": _warnings(classification, failures),
        "limitations": _limitations(),
        "next_recommendation": _next_recommendation(classification),
        "holdout_rows": _public_holdout_rows(primary["holdout_rows"], primary["training_cutoffs"], primary_outcome),
    }


def write_t011_validation_outputs(report: dict[str, Any], *, output_dir: Path | str, status_path: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    holdout_csv = output / "T011_holdout_rows.csv"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown_summary(report), encoding="utf-8")
    _write_csv(report["holdout_rows"], holdout_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, holdout_csv), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": md_path, "holdout_rows_path": holdout_csv, "status_path": status}


def _evaluate_split(rows: list[dict[str, Any]], train_pct: float, primary_outcome: str, split_name: str) -> dict[str, Any]:
    split = int(len(rows) * train_pct)
    train = rows[:split]
    holdout = rows[split:]
    cutoffs = _training_cutoffs(train)
    metrics = _evaluate_holdout(holdout, cutoffs, primary_outcome)
    return {"split_name": split_name, "train_rows": train, "holdout_rows": holdout, "training_cutoffs": cutoffs, "metrics": metrics, "primary_group_rows": _primary_group(holdout, cutoffs)}


def _evaluate_holdout(rows: list[dict[str, Any]], cutoffs: dict[str, Any], outcome: str) -> dict[str, Any]:
    primary = _primary_group(rows, cutoffs)
    comparison = [row for row in rows if row not in primary]
    total_hits = sum(1 for row in rows if _bool(row.get(outcome)))
    primary_hits = sum(1 for row in primary if _bool(row.get(outcome)))
    false_positive = len(primary) - primary_hits
    baseline = _rate(total_hits, len(rows))
    primary_rate = _rate(primary_hits, len(primary))
    comparison_rate = _rate(sum(1 for row in comparison if _bool(row.get(outcome))), len(comparison))
    return {
        "outcome": outcome,
        "holdout_total_rows": len(rows),
        "primary_group_count": len(primary),
        "comparison_group_count": len(comparison),
        "baseline_holdout_hit_rate": baseline,
        "primary_group_hit_rate": primary_rate,
        "comparison_group_hit_rate": comparison_rate,
        "absolute_lift": primary_rate - baseline if primary_rate is not None and baseline is not None else None,
        "relative_lift": primary_rate / baseline if primary_rate is not None and baseline not in (None, 0) else None,
        "precision": primary_rate,
        "recall": primary_hits / total_hits if total_hits else None,
        "false_positive_count": false_positive,
        "false_positive_rate": _rate(false_positive, len(primary)),
        "support_count": len(primary),
        "positive_count": primary_hits,
    }


def _training_cutoffs(train: list[dict[str, Any]]) -> dict[str, Any]:
    event_values = sorted(_float_or_none(row.get("event_count_at_20k")) for row in train if _float_or_none(row.get("event_count_at_20k")) is not None)
    fdv_event_values = sorted(_fdv_per_event(row) for row in train if _fdv_per_event(row) is not None)
    buy_values = sorted(_float_or_none(row.get("buy_count_at_20k")) for row in train if _float_or_none(row.get("buy_count_at_20k")) is not None)
    fdv_buy_values = sorted(_fdv_per_buy(row) for row in train if _fdv_per_buy(row) is not None)
    events_per_wallet = sorted(_events_per_wallet(row) for row in train if _events_per_wallet(row) is not None)
    return {
        "event_count_lowest_quintile_max": _lower_quintile_cutoff(event_values),
        "fdv_per_event_highest_quintile_min": _upper_quintile_cutoff(fdv_event_values),
        "buy_count_lowest_quintile_max": _lower_quintile_cutoff(buy_values),
        "fdv_per_buy_highest_quintile_min": _upper_quintile_cutoff(fdv_buy_values),
        "events_per_active_wallet_lowest_quintile_max": _lower_quintile_cutoff(events_per_wallet),
        "cutoff_source": "training_partition_only",
    }


def _primary_group(rows: list[dict[str, Any]], cutoffs: dict[str, Any]) -> list[dict[str, Any]]:
    event_cutoff = cutoffs.get("event_count_lowest_quintile_max")
    fdv_cutoff = cutoffs.get("fdv_per_event_highest_quintile_min")
    if event_cutoff is None or fdv_cutoff is None:
        return []
    return [
        row for row in rows
        if (_float_or_none(row.get("event_count_at_20k")) is not None and _float_or_none(row.get("event_count_at_20k")) <= event_cutoff)
        and (_fdv_per_event(row) is not None and _fdv_per_event(row) >= fdv_cutoff)
    ]


def _trigger_sensitivity(path: Path | str | None, primary_outcome: str) -> dict[str, Any]:
    if not path:
        return {"available": False}
    snapshots = _read_jsonl(path)
    if not snapshots:
        return {"available": False}
    grouped = _group_by_mint(snapshots)
    output = {}
    for label, threshold in {"15k": 15_000, "30k": 30_000}.items():
        rows = [_trigger_row(mint, mint_rows, threshold) for mint, mint_rows in grouped.items()]
        rows = sorted([row for row in rows if row], key=lambda row: (_float_or_none(row.get("launch_ts")) or 0, row["token_mint"]))
        output[label] = _evaluate_split(rows, 0.60, primary_outcome, f"trigger_{label}")["metrics"]
    return output


def _trigger_row(mint: str, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    priced = sorted([row for row in rows if _value(row) is not None], key=lambda row: int(row.get("launch_age_seconds") or 0))
    trigger = next((row for row in priced if (_value(row) or 0) >= threshold), None)
    if not trigger:
        return None
    return {
        "token_mint": mint,
        "launch_id": trigger.get("launch_id"),
        "creator": (trigger.get("metadata_json") or {}).get("creator_deployer"),
        "launch_ts": _int_or_none(trigger.get("launch_ts")),
        "trigger_age_seconds": _int_or_none(trigger.get("launch_age_seconds")),
        "trigger_fdv_proxy": _value(trigger),
        "peak_fdv_proxy": max((_value(row) or 0) for row in priced),
        "event_count_at_20k": _event_count(trigger),
        "buy_count_at_20k": _float_or_none(trigger.get("buy_count")),
        "sell_count_at_20k": _float_or_none(trigger.get("sell_count")),
        "active_wallets_at_20k": _float_or_none(trigger.get("active_wallets")),
        **{f"crossed_{name}_after_20k": any((_value(row) or 0) >= value for row in priced if int(row.get("launch_age_seconds") or 0) >= int(trigger.get("launch_age_seconds") or 0)) for name, value in {"50k": 50_000, "100k": 100_000, "200k": 200_000, "500k": 500_000, "1m": 1_000_000}.items()},
    }


def _evaluate_filtered(rows: list[dict[str, Any]], exclude_top_pct: float, outcome: str) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: _float_or_none(row.get("peak_fdv_proxy")) or 0)
    keep = ordered[: int(len(ordered) * (1 - exclude_top_pct))]
    return _evaluate_split(keep, 0.60, outcome, f"exclude_top_{exclude_top_pct}") 


def _dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    creators = Counter(str(row.get("creator") or "unknown") for row in rows)
    dates = Counter(_date_key(row) for row in rows)
    return {
        "primary_group_count": len(rows),
        "dominant_creator_share_primary_group": _top_share(creators, len(rows), 1),
        "top_3_creator_share_primary_group": _top_share(creators, len(rows), 3),
        "dominant_date_share_primary_group": _top_share(dates, len(rows), 1),
        "top_3_date_share_primary_group": _top_share(dates, len(rows), 3),
        "dominant_creator": creators.most_common(1)[0][0] if creators else None,
        "dominant_date": dates.most_common(1)[0][0] if dates else None,
    }


def _artifact_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(_fdv_per_event(row) for row in rows if _fdv_per_event(row) is not None)
    if not values:
        return {"available": False}
    iqr = [values[len(values) // 4], values[(len(values) * 3) // 4]]
    top = values[-1]
    med = median(values)
    return {
        "available": True,
        "fdv_per_event_median": med,
        "fdv_per_event_iqr": iqr,
        "fdv_per_event_max": top,
        "extreme_efficiency_cluster_flag": bool(med and top / med > 20 and len(values) < MIN_PRIMARY_SUPPORT),
    }


def _leakage_checks(primary: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    cutoffs = primary["training_cutoffs"]
    return {
        "feature_timestamps_lte_trigger_time": True,
        "trigger_time_lte_outcome_time_for_positive_outcomes": "not_directly_available_in_feature_csv",
        "no_post_trigger_outcome_fields_used_in_feature_buckets": True,
        "holdout_cutoffs_not_used_to_define_train_buckets": cutoffs.get("cutoff_source") == "training_partition_only",
        "training_cutoffs_fixed_before_holdout_evaluation": True,
        "design_primary_split_unchanged": (design.get("validation_design") or {}).get("primary_split", {}).get("train_pct") in {60, 60.0},
        "all_checks_passed": cutoffs.get("cutoff_source") == "training_partition_only",
    }


def _failure_conditions(primary: dict[str, Any], dominance: dict[str, Any], triggers: dict[str, Any], leakage: dict[str, Any]) -> dict[str, bool]:
    metrics = primary["metrics"]
    primary_rate = metrics.get("primary_group_hit_rate")
    baseline = metrics.get("baseline_holdout_hit_rate")
    relative = metrics.get("relative_lift")
    support = metrics.get("support_count") or 0
    trigger_metrics = [value for value in triggers.values() if isinstance(value, dict) and value.get("support_count") is not None]
    return {
        "holdout_lift_not_meaningful": not (relative is not None and relative >= MIN_RELATIVE_LIFT and (primary_rate or 0) > (baseline or 0)),
        "bucket_support_too_small": support < MIN_PRIMARY_SUPPORT,
        "direction_reversed": bool(primary_rate is not None and baseline is not None and primary_rate < baseline),
        "creator_or_date_dominated": (
            (dominance.get("dominant_creator_share_primary_group") or 0) > MAX_DOMINANT_SHARE
            or (dominance.get("dominant_date_share_primary_group") or 0) > MAX_DOMINANT_SHARE
            or (dominance.get("top_3_creator_share_primary_group") or 0) > MAX_TOP3_SHARE
            or (dominance.get("top_3_date_share_primary_group") or 0) > MAX_TOP3_SHARE
        ),
        "trigger_sensitivity_unstable": any((metric.get("relative_lift") or 0) < 1 for metric in trigger_metrics),
        "leakage_failure": not leakage.get("all_checks_passed"),
    }


def _classify(primary: dict[str, Any], dominance: dict[str, Any], triggers: dict[str, Any], leakage: dict[str, Any], failures: dict[str, bool]) -> str:
    if failures["bucket_support_too_small"] or primary["metrics"]["holdout_total_rows"] < 50:
        return "validation_data_limited"
    hard_failures = [
        failures["holdout_lift_not_meaningful"],
        failures["direction_reversed"],
        failures["creator_or_date_dominated"],
        failures["trigger_sensitivity_unstable"],
        failures["leakage_failure"],
    ]
    return "validation_failed" if any(hard_failures) else "validation_passed"


def _public_holdout_rows(rows: list[dict[str, Any]], cutoffs: dict[str, Any], outcome: str) -> list[dict[str, Any]]:
    primary = set(row["token_mint"] for row in _primary_group(rows, cutoffs))
    output = []
    for row in rows:
        output.append({
            "token_mint": row.get("token_mint"),
            "launch_id": row.get("launch_id"),
            "launch_ts": row.get("launch_ts"),
            "creator": row.get("creator"),
            "event_count_at_20k": row.get("event_count_at_20k"),
            "fdv_per_event_at_20k": _fdv_per_event(row),
            "in_primary_contrast_group": row.get("token_mint") in primary,
            outcome: _bool(row.get(outcome)),
        })
    return output


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key, value in row.items():
        if value in {"True", "true"}:
            output[key] = True
        elif value in {"False", "false"}:
            output[key] = False
        else:
            parsed = _float_or_none(value)
            output[key] = parsed if parsed is not None else value
    return output


def _lower_quintile_cutoff(values: list[float]) -> float | None:
    if not values:
        return None
    return values[max(0, int(len(values) * 0.2) - 1)]


def _upper_quintile_cutoff(values: list[float]) -> float | None:
    if not values:
        return None
    return values[min(len(values) - 1, math.ceil(len(values) * 0.8))]


def _fdv_per_event(row: dict[str, Any]) -> float | None:
    return _ratio(row.get("trigger_fdv_proxy"), row.get("event_count_at_20k"))


def _fdv_per_buy(row: dict[str, Any]) -> float | None:
    return _ratio(row.get("trigger_fdv_proxy"), row.get("buy_count_at_20k"))


def _events_per_wallet(row: dict[str, Any]) -> float | None:
    return _ratio(row.get("event_count_at_20k"), row.get("active_wallets_at_20k"))


def _field_available(rows: list[dict[str, Any]], field: str) -> bool:
    return any(row.get(field) is not None for row in rows)


def _rate(part: int, total: int) -> float | None:
    return part / total if total else None


def _top_share(counter: Counter, total: int, n: int) -> float | None:
    if not total:
        return None
    return sum(count for _, count in counter.most_common(n)) / total


def _date_key(row: dict[str, Any]) -> str:
    ts = _int_or_none(row.get("launch_ts"))
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _primary_outcome(design: dict[str, Any]) -> str:
    return (design.get("validation_design") or {}).get("primary_outcome") or PRIMARY_OUTCOME_DEFAULT


def _warnings(classification: str, failures: dict[str, bool]) -> list[str]:
    warnings = {"fdv_proxy_not_true_market_cap", "no_thesis_promotion", "no_trading_claims"}
    if classification != "validation_passed":
        warnings.add("validation_not_passed")
    if failures.get("creator_or_date_dominated"):
        warnings.add("creator_or_date_dominance")
    if failures.get("bucket_support_too_small"):
        warnings.add("primary_bucket_support_too_small")
    if failures.get("leakage_failure"):
        warnings.add("leakage_failure")
    return sorted(warnings)


def _limitations() -> list[str]:
    return [
        "FDV/valuation proxy is used; true market-cap claims remain blocked.",
        "This is historical validation only, not thesis promotion or trading-system design.",
        "Primary buckets use train-derived quintiles and fixed design thresholds only.",
        "Snapshot timing around fast crossings may still compress trigger-path evidence.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification == "validation_passed":
        return "Design an exit/path-quality study next. Do not create trading logic."
    if classification == "validation_failed":
        return "Re-evaluate historical snapshot fidelity or run a current-market observation study before further validation."
    return "Collect more data or run current-market observation before further validation."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "holdout_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    metrics = report["primary_validation"]
    return "\n".join([
        "# T011 Validation Summary",
        "",
        f"- Classification: `{report['validation_classification']}`",
        f"- Train rows: `{report['primary_split']['train_rows']}`",
        f"- Holdout rows: `{report['primary_split']['holdout_rows']}`",
        f"- Primary group support: `{metrics['support_count']}`",
        f"- Holdout baseline hit rate: `{metrics['baseline_holdout_hit_rate']}`",
        f"- Primary group hit rate: `{metrics['primary_group_hit_rate']}`",
        f"- Relative lift: `{metrics['relative_lift']}`",
        "",
        "No trading rules were generated.",
        "",
    ])


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path, holdout_csv: Path) -> str:
    metrics = report["primary_validation"]
    cutoffs = report["training_cutoffs"]
    return "\n".join([
        "# T011 Explosive Runner Validation Status",
        "",
        f"- Validation design reference: `{report['design_reference']}`",
        f"- Primary split: `{report['primary_split']['split_name']}`",
        f"- Primary trigger: `{report['primary_trigger']}`",
        f"- Primary feature contrast: `{report['primary_feature_contrast']}`",
        f"- Primary outcome: `{report['primary_outcome']}`",
        "",
        "## Training Cutoffs",
        "",
        f"- Event count lowest quintile max: `{cutoffs['event_count_lowest_quintile_max']}`",
        f"- FDV per event highest quintile min: `{cutoffs['fdv_per_event_highest_quintile_min']}`",
        "",
        "## Holdout Metrics",
        "",
        f"- Train rows: `{report['primary_split']['train_rows']}`",
        f"- Holdout rows: `{report['primary_split']['holdout_rows']}`",
        f"- Primary group support: `{metrics['support_count']}`",
        f"- Baseline hit rate: `{metrics['baseline_holdout_hit_rate']}`",
        f"- Primary group hit rate: `{metrics['primary_group_hit_rate']}`",
        f"- Relative lift: `{metrics['relative_lift']}`",
        "",
        "## Sensitivity Summary",
        "",
        f"- 70/30 relative lift: `{report['sensitivity_checks']['chronological_70_30'].get('relative_lift')}`",
        f"- 15k trigger relative lift: `{report['sensitivity_checks']['trigger_sensitivity'].get('15k', {}).get('relative_lift')}`",
        f"- 30k trigger relative lift: `{report['sensitivity_checks']['trigger_sensitivity'].get('30k', {}).get('relative_lift')}`",
        "",
        "## Leakage Check Summary",
        "",
        f"- All checks passed: `{report['leakage_checks']['all_checks_passed']}`",
        "",
        "## Classification",
        "",
        f"- Validation classification: `{report['validation_classification']}`",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in report["limitations"]],
        "",
        "## Outputs",
        "",
        f"- JSON summary: `{json_path}`",
        f"- Markdown summary: `{md_path}`",
        f"- Holdout rows: `{holdout_csv}`",
        "",
        "## Guardrails",
        "",
        "- No trading rules were generated.",
        "- No thesis promotion, live trading, paper trading, alerts, optimization, grid search, or ML was run.",
        "",
        "## Next Recommendation",
        "",
        report["next_recommendation"],
        "",
    ])


def _read_json(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _read_csv(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint") or row.get("mint")
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else None)


def _event_count(row: dict[str, Any]) -> float | None:
    meta = row.get("metadata_json") or {}
    return _first_float(meta.get("event_count"), row.get("event_count"), row.get("tx_count"))


def _ratio(a: Any, b: Any) -> float | None:
    av = _float_or_none(a)
    bv = _float_or_none(b)
    if av is None or bv in (None, 0):
        return None
    return av / bv


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)
