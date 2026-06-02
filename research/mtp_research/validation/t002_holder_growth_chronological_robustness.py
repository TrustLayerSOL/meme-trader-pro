"""Chronological robustness review for T002 holder-growth tempo v2."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.validation.holder_growth_tempo_thesis import (
    HOLDER_FEATURES,
    build_t002_holder_growth_report,
)


THESIS_ID = "T002"
THESIS_NAME = "Holder Growth Tempo"
ROBUSTNESS_FEATURES = [
    "holder_growth_30s_to_3m",
    "holder_growth_3m_to_10m",
    "holder_growth_10m_to_30m",
    "holder_growth_30s_to_30m",
    "holder_count_30s",
    "holder_count_3m",
    "holder_count_10m",
    "holder_count_30m",
    "holder_retention_proxy",
    "holder_churn_proxy",
]
GROWTH_FEATURES = [
    "holder_growth_30s_to_3m",
    "holder_growth_3m_to_10m",
    "holder_growth_10m_to_30m",
    "holder_growth_30s_to_30m",
]
PRIMARY_FEATURE = "holder_growth_30s_to_30m"
ALLOWED_CLASSIFICATIONS = {
    "stable_weak_signal",
    "unstable_weak_signal",
    "no_robust_signal",
    "data_limited",
}


def build_t002_chronological_robustness_report(
    *,
    candidates_path: Path | str,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    holder_state_snapshots_path: Path | str,
    bucket_count: int = 5,
) -> dict[str, Any]:
    base_report = build_t002_holder_growth_report(
        candidates_path=candidates_path,
        snapshots_path=snapshots_path,
        holder_state_snapshots_path=holder_state_snapshots_path,
        outcomes_path=outcomes_path,
        bucket_count=bucket_count,
    )
    holder_state_rows = _read_jsonl(holder_state_snapshots_path)
    holder_context = _holder_state_context(holder_state_rows)
    rows = [
        _augment_launch_row(row, holder_context.get(row["token_mint"], {}))
        for row in base_report["launch_rows"]
    ]
    rows = sorted(rows, key=lambda row: (_launch_sort_value(row), row.get("token_mint", "")))
    full_summary = _view_summary("full_sample", rows, bucket_count)
    chronological_splits = {
        "halves": _named_view_summaries(_split_evenly(rows, ["first_half", "second_half"]), bucket_count, full_summary),
        "thirds": _named_view_summaries(
            _split_evenly(rows, ["first_third", "middle_third", "final_third"]), bucket_count, full_summary
        ),
        "weekly_buckets": _named_view_summaries(_time_bucket_rows(rows, "week"), bucket_count, full_summary),
        "monthly_buckets": _named_view_summaries(_time_bucket_rows(rows, "month"), bucket_count, full_summary),
    }
    outlier_sensitivity = _outlier_sensitivity(rows, bucket_count, full_summary)
    concentration_sensitivity = _concentration_sensitivity(rows, bucket_count, full_summary)
    classification = _classify_robustness(
        base_report["final_classification"],
        full_summary,
        chronological_splits,
        outlier_sensitivity,
        rows,
    )
    report = {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "review_type": "chronological_robustness_review",
        "original_t002_v2_classification": base_report["final_classification"],
        "robustness_classification": classification,
        "dataset": {
            "candidates_path": str(candidates_path),
            "snapshots_path": str(snapshots_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path),
            "outcomes_path": str(outcomes_path),
            "strict_launch_regime": True,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology_flags": [
            "research_only",
            "robustness_review_only",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_thesis_promotion",
            "no_walk_forward_validation",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
            "holder_state_observed_delta_replay_not_full_chain_state",
        ],
        "chronological_fields": _chronological_field_audit(rows),
        "sample_counts": {
            "launch_count": len(rows),
            "token_count": len({row["token_mint"] for row in rows}),
        },
        "feature_coverage": _feature_coverage(rows),
        "outcome_coverage": _outcome_coverage(rows),
        "full_sample_summary": full_summary,
        "chronological_splits": chronological_splits,
        "outlier_sensitivity": outlier_sensitivity,
        "concentration_sensitivity": concentration_sensitivity,
        "chronological_consistency_result": _chronological_consistency(chronological_splits),
        "outlier_sensitivity_result": _sensitivity_result(outlier_sensitivity),
        "limitations": [
            "This is a descriptive robustness review only.",
            "FDV proxy is not true market cap.",
            "Holder state is observed delta replay, not confirmed full-chain account state.",
            "No thesis promotion or validation design was executed.",
        ],
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(
            candidates_path,
            snapshots_path,
            holder_state_snapshots_path,
            outcomes_path,
            bucket_count,
        ),
    }
    if report["robustness_classification"] not in ALLOWED_CLASSIFICATIONS:
        raise ValueError(f"unsupported robustness classification: {report['robustness_classification']}")
    return report


def write_t002_chronological_robustness_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T002_holder_growth_chronological_robustness_summary.json"
    markdown_path = output / "T002_holder_growth_chronological_robustness_summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _augment_launch_row(row: dict[str, Any], holder_context: dict[str, Any]) -> dict[str, Any]:
    copy = dict(row)
    features = dict(row.get("features") or {})
    holder_counts = holder_context.get("holder_counts_by_age", {})
    features["holder_count_30s"] = holder_counts.get(30)
    features["holder_count_3m"] = holder_counts.get(180)
    features["holder_count_10m"] = holder_counts.get(600)
    features["holder_count_30m"] = holder_counts.get(1800)
    features["holder_retention_proxy"] = _ratio(holder_counts.get(1800), holder_counts.get(180))
    features["holder_churn_proxy"] = _churn_proxy(holder_counts.get(180), holder_counts.get(1800))
    copy["features"] = features
    metadata = dict(copy.get("metadata_json") or {})
    metadata["holder_state_confidence_values"] = holder_context.get("confidence_values", [])
    metadata["has_insufficient_prior_state_snapshot"] = bool(holder_context.get("has_insufficient_prior_state_snapshot"))
    metadata["holder_state_snapshot_count"] = holder_context.get("snapshot_count", 0)
    copy["metadata_json"] = metadata
    return copy


def _holder_state_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "holder_counts_by_age": {},
        "confidence_values": [],
        "has_insufficient_prior_state_snapshot": False,
        "snapshot_count": 0,
    })
    for row in rows:
        mint = row.get("mint") or row.get("token_mint")
        age = _int_or_none(row.get("snapshot_age_seconds") or row.get("launch_age_seconds"))
        if not mint or age is None:
            continue
        entry = grouped[str(mint)]
        entry["snapshot_count"] += 1
        if row.get("holder_count") is not None:
            entry["holder_counts_by_age"][age] = _float_or_none(row.get("holder_count"))
        confidence = row.get("holder_snapshot_confidence") or row.get("holder_snapshot_state")
        if confidence:
            entry["confidence_values"].append(str(confidence))
        state_blob = " ".join(str(row.get(key, "")) for key in ("holder_snapshot_confidence", "holder_snapshot_state", "holder_snapshot_missing_reason"))
        if "insufficient_prior_state" in state_blob:
            entry["has_insufficient_prior_state_snapshot"] = True
    return dict(grouped)


def _view_summary(
    name: str,
    rows: list[dict[str, Any]],
    bucket_count: int,
    full_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "name": name,
        "launch_count": len(rows),
        "feature_coverage": _feature_coverage(rows),
        "outcome_coverage": _outcome_coverage(rows),
        "quantile_reports": {
            feature: _feature_quantile_report(rows, feature, bucket_count)
            for feature in GROWTH_FEATURES
        },
    }
    summary["direction_consistency"] = _direction_consistency(summary, full_summary)
    return summary


def _named_view_summaries(
    grouped_rows: dict[str, list[dict[str, Any]]],
    bucket_count: int,
    full_summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        name: _view_summary(name, split_rows, bucket_count, full_summary)
        for name, split_rows in grouped_rows.items()
    }


def _feature_quantile_report(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> dict[str, Any]:
    usable = sorted(
        [row for row in rows if _float_or_none(row.get("features", {}).get(feature)) is not None],
        key=lambda row: (
            _float_or_none(row.get("features", {}).get(feature)),
            _launch_sort_value(row),
            row.get("token_mint", ""),
        ),
    )
    buckets = _quantile_buckets(usable, bucket_count)
    bucket_rows = [_summarize_bucket(feature, index + 1, bucket) for index, bucket in enumerate(buckets)]
    first = bucket_rows[0]["median_fdv_proxy_runup_120m"] if bucket_rows else None
    last = bucket_rows[-1]["median_fdv_proxy_runup_120m"] if bucket_rows else None
    return {
        "feature": feature,
        "sample_count": len(rows),
        "usable_count": len(usable),
        "missing_count": len(rows) - len(usable),
        "bucket_count": len(bucket_rows),
        "bucket_counts": [bucket["launch_count"] for bucket in bucket_rows],
        "quantile_definitions": "deterministic rank buckets over non-missing values",
        "bucket_tables": bucket_rows,
        "direction": _direction(first, last),
    }


def _quantile_buckets(rows: list[dict[str, Any]], bucket_count: int) -> list[list[dict[str, Any]]]:
    if not rows:
        return []
    count = min(bucket_count, len(rows))
    buckets = [[] for _ in range(count)]
    for index, row in enumerate(rows):
        bucket_index = min(count - 1, int(index * count / len(rows)))
        buckets[bucket_index].append(row)
    return buckets


def _summarize_bucket(feature: str, bucket_number: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    feature_values = [_float_or_none(row.get("features", {}).get(feature)) for row in rows]
    feature_values = [value for value in feature_values if value is not None]
    runups = [_float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) for row in rows]
    drawdowns = [_float_or_none(row.get("outcomes", {}).get("fdv_proxy_drawdown_120m")) for row in rows]
    return {
        "bucket": f"q{bucket_number}",
        "launch_count": len(rows),
        "feature_min": min(feature_values) if feature_values else None,
        "feature_max": max(feature_values) if feature_values else None,
        "median_fdv_proxy_runup_120m": _median(runups),
        "median_fdv_proxy_drawdown_120m": _median(drawdowns),
        "price_available_120m_rate": _true_rate(row.get("outcomes", {}).get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(
            row.get("outcomes", {}).get("liquidity_proxy_available_120m") for row in rows
        ),
    }


def _split_evenly(rows: list[dict[str, Any]], names: list[str]) -> dict[str, list[dict[str, Any]]]:
    grouped = {name: [] for name in names}
    if not rows:
        return grouped
    for index, row in enumerate(rows):
        bucket_index = min(len(names) - 1, int(index * len(names) / len(rows)))
        grouped[names[bucket_index]].append(row)
    return grouped


def _time_bucket_rows(rows: list[dict[str, Any]], kind: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        dt = _launch_datetime(row)
        if not dt:
            grouped["unknown"].append(row)
        elif kind == "week":
            year, week, _ = dt.isocalendar()
            grouped[f"{year}-W{week:02d}"].append(row)
        else:
            grouped[dt.strftime("%Y-%m")].append(row)
    return dict(sorted(grouped.items()))


def _outlier_sensitivity(rows: list[dict[str, Any]], bucket_count: int, full_summary: dict[str, Any]) -> dict[str, Any]:
    runup_values = sorted(
        value for value in (_float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) for row in rows)
        if value is not None
    )
    drawdown_values = sorted(
        value for value in (_float_or_none(row.get("outcomes", {}).get("fdv_proxy_drawdown_120m")) for row in rows)
        if value is not None
    )
    top_1 = _quantile(runup_values, 0.99)
    top_5 = _quantile(runup_values, 0.95)
    low_drawdown = _quantile(drawdown_values, 0.01)
    views = {
        "exclude_top_1pct_fdv_proxy_runups": [
            row for row in rows
            if top_1 is None or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) is None
            or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) < top_1
        ],
        "exclude_top_5pct_fdv_proxy_runups": [
            row for row in rows
            if top_5 is None or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) is None
            or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) < top_5
        ],
        "exclude_extreme_drawdowns": [
            row for row in rows
            if low_drawdown is None or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_drawdown_120m")) is None
            or _float_or_none(row.get("outcomes", {}).get("fdv_proxy_drawdown_120m")) > low_drawdown
        ],
    }
    return {
        name: _view_summary(name, view_rows, bucket_count, full_summary)
        for name, view_rows in views.items()
    }


def _concentration_sensitivity(rows: list[dict[str, Any]], bucket_count: int, full_summary: dict[str, Any]) -> dict[str, Any]:
    day_counts = Counter()
    confidence_counts = Counter()
    insufficient_rows = []
    tx_values = []
    for row in rows:
        dt = _launch_datetime(row)
        day_counts[dt.strftime("%Y-%m-%d") if dt else "unknown"] += 1
        for confidence in row.get("metadata_json", {}).get("holder_state_confidence_values", []):
            confidence_counts[confidence] += 1
        if row.get("metadata_json", {}).get("has_insufficient_prior_state_snapshot"):
            insufficient_rows.append(row)
        tx_value = _float_or_none(row.get("features", {}).get("buyer_growth_10m_to_30m"))
        if tx_value is not None:
            tx_values.append(tx_value)
    tx_cutoff = _quantile(sorted(tx_values), 0.95)
    high_activity = [
        row for row in rows
        if tx_cutoff is not None
        and _float_or_none(row.get("features", {}).get("buyer_growth_10m_to_30m")) is not None
        and _float_or_none(row.get("features", {}).get("buyer_growth_10m_to_30m")) >= tx_cutoff
    ]
    return {
        "launch_day_counts": dict(sorted(day_counts.items())),
        "top_launch_days": dict(day_counts.most_common(10)),
        "holder_state_confidence_counts": dict(sorted(confidence_counts.items())),
        "high_activity_cluster": _view_summary("high_activity_cluster", high_activity, bucket_count, full_summary),
        "insufficient_prior_state_launches": _view_summary(
            "insufficient_prior_state_launches", insufficient_rows, bucket_count, full_summary
        ),
    }


def _direction_consistency(summary: dict[str, Any], full_summary: dict[str, Any] | None) -> dict[str, Any]:
    if full_summary is None:
        return {
            feature: {"consistent_with_full_sample": None}
            for feature in GROWTH_FEATURES
        }
    result = {}
    for feature in GROWTH_FEATURES:
        current = summary["quantile_reports"][feature]["direction"]
        full = full_summary["quantile_reports"][feature]["direction"]
        result[feature] = {
            "full_sample_direction": full,
            "view_direction": current,
            "consistent_with_full_sample": current == full and current != "flat_or_unusable",
        }
    return result


def _direction(first: float | None, last: float | None) -> str:
    if first is None or last is None:
        return "flat_or_unusable"
    if last > first:
        return "higher_growth_higher_runup"
    if last < first:
        return "higher_growth_lower_runup"
    return "flat_or_unusable"


def _classify_robustness(
    original_classification: str,
    full_summary: dict[str, Any],
    chronological_splits: dict[str, Any],
    outlier_sensitivity: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    primary = full_summary["quantile_reports"][PRIMARY_FEATURE]
    if len(rows) < 100 or primary["usable_count"] < 100:
        return "data_limited"
    if primary["direction"] != "higher_growth_higher_runup":
        return "no_robust_signal"
    if original_classification not in {"weak_signal", "descriptive_signal_present"}:
        return "no_robust_signal"
    half_consistent = _consistent_view_count(chronological_splits["halves"], PRIMARY_FEATURE)
    third_consistent = _consistent_view_count(chronological_splits["thirds"], PRIMARY_FEATURE)
    outlier_consistent = _consistent_view_count(outlier_sensitivity, PRIMARY_FEATURE)
    if half_consistent == 2 and third_consistent >= 2 and outlier_consistent >= 2:
        return "stable_weak_signal"
    return "unstable_weak_signal"


def _consistent_view_count(views: dict[str, dict[str, Any]], feature: str) -> int:
    return sum(
        1 for view in views.values()
        if view.get("direction_consistency", {}).get(feature, {}).get("consistent_with_full_sample")
    )


def _chronological_consistency(chronological_splits: dict[str, Any]) -> dict[str, Any]:
    return {
        "halves_consistent_count": _consistent_view_count(chronological_splits["halves"], PRIMARY_FEATURE),
        "thirds_consistent_count": _consistent_view_count(chronological_splits["thirds"], PRIMARY_FEATURE),
        "primary_feature": PRIMARY_FEATURE,
    }


def _sensitivity_result(outlier_sensitivity: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_feature": PRIMARY_FEATURE,
        "outlier_views_consistent_count": _consistent_view_count(outlier_sensitivity, PRIMARY_FEATURE),
        "outlier_view_count": len(outlier_sensitivity),
    }


def _feature_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    coverage = {}
    for feature in ROBUSTNESS_FEATURES:
        available = sum(1 for row in rows if _float_or_none(row.get("features", {}).get(feature)) is not None)
        coverage[feature] = {
            "available_count": available,
            "missing_count": total - available,
            "coverage_pct": (available / total * 100) if total else 0,
        }
    return coverage


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(
            1 for row in rows if _float_or_none(row.get("outcomes", {}).get("fdv_proxy_runup_120m")) is not None
        ),
        "fdv_proxy_drawdown_available": sum(
            1 for row in rows if _float_or_none(row.get("outcomes", {}).get("fdv_proxy_drawdown_120m")) is not None
        ),
        "price_available_120m": sum(1 for row in rows if row.get("outcomes", {}).get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(
            1 for row in rows if row.get("outcomes", {}).get("liquidity_proxy_available_120m")
        ),
    }


def _chronological_field_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [_launch_datetime(row) for row in rows]
    dates = [dt for dt in dates if dt]
    return {
        "block_time_available_count": sum(1 for row in rows if row.get("launch_ts") is not None),
        "launch_date_available_count": len(dates),
        "launch_week_available_count": len(dates),
        "launch_month_available_count": len(dates),
        "min_launch_time_utc": min(dates).isoformat() if dates else None,
        "max_launch_time_utc": max(dates).isoformat() if dates else None,
        "snapshot_timestamp_policy": "feature snapshots are launch-relative and limited to <=30m; outcomes use <=120m FDV proxy",
    }


def _next_recommendation(classification: str) -> str:
    if classification == "stable_weak_signal":
        return "design a formal walk-forward validation plan later; do not promote T002 v2 from this review"
    if classification in {"unstable_weak_signal", "no_robust_signal"}:
        return "park T002 v2 and prioritize manipulation/entity enrichment before further thesis cycles"
    return "collect or repair data before interpreting T002 v2 robustness"


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T002 Holder Growth Tempo v2 Chronological Robustness",
        "",
        f"- Original T002 v2 classification: `{report['original_t002_v2_classification']}`",
        f"- Robustness classification: `{report['robustness_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Primary feature: `{PRIMARY_FEATURE}`",
        "",
        "## Chronological Splits",
        "",
        "| Split | Launches | Primary Direction | Consistent With Full Sample |",
        "|---|---:|---|---|",
    ]
    for group_name in ("halves", "thirds"):
        for name, view in report["chronological_splits"][group_name].items():
            primary = view["quantile_reports"][PRIMARY_FEATURE]
            consistent = view["direction_consistency"][PRIMARY_FEATURE]["consistent_with_full_sample"]
            lines.append(f"| `{name}` | {view['launch_count']} | `{primary['direction']}` | `{consistent}` |")
    lines.extend(["", "## Outlier Sensitivity", ""])
    for name, view in report["outlier_sensitivity"].items():
        primary = view["quantile_reports"][PRIMARY_FEATURE]
        consistent = view["direction_consistency"][PRIMARY_FEATURE]["consistent_with_full_sample"]
        lines.append(f"- `{name}`: launches `{view['launch_count']}`, direction `{primary['direction']}`, consistent `{consistent}`")
    lines.extend(
        [
            "",
            "## Feature Coverage",
            "",
            "| Feature | Available | Missing | Coverage |",
            "|---|---:|---:|---:|",
        ]
    )
    for feature, coverage in report["feature_coverage"].items():
        lines.append(
            f"| `{feature}` | {coverage['available_count']} | {coverage['missing_count']} | "
            f"{coverage['coverage_pct']:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            "## Reproducible Command",
            "",
            "```bash",
            report["reproducible_command"],
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    halves = report["chronological_splits"]["halves"]
    thirds = report["chronological_splits"]["thirds"]
    return "\n".join(
        [
            "# T002 Holder Growth Tempo v2 Robustness Status",
            "",
            "## Original Classification",
            "",
            f"`{report['original_t002_v2_classification']}`",
            "",
            "## Robustness Classification",
            "",
            f"`{report['robustness_classification']}`",
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Holder-state snapshots: `{report['dataset']['holder_state_snapshots_path']}`",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Split Definitions",
            "",
            f"- Chronological halves: `{ {key: value['launch_count'] for key, value in halves.items()} }`",
            f"- Chronological thirds: `{ {key: value['launch_count'] for key, value in thirds.items()} }`",
            "- Weekly and monthly buckets are reported with counts and not overinterpreted when small.",
            "",
            "## Feature Coverage",
            "",
            *[
                f"- `{feature}`: `{coverage['available_count']}` available, `{coverage['coverage_pct']:.2f}%` coverage"
                for feature, coverage in report["feature_coverage"].items()
            ],
            "",
            "## Outcome Coverage",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["outcome_coverage"].items()],
            "",
            "## Outlier Sensitivity Result",
            "",
            f"`{report['outlier_sensitivity_result']}`",
            "",
            "## Chronological Consistency Result",
            "",
            f"`{report['chronological_consistency_result']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "- No thesis promotion was performed.",
            "- No trading rules were generated.",
            "- True market-cap claims remain blocked.",
            "",
        ]
    )


def _reproducible_command(
    candidates_path: Path | str,
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str,
    outcomes_path: Path | str,
    bucket_count: int,
) -> str:
    return " ".join(
        [
            "./trading_env/bin/python -m research.mtp_research.validation.run_t002_holder_growth_chronological_robustness",
            f"--candidates-path \"{candidates_path}\"",
            f"--snapshots-path \"{snapshots_path}\"",
            f"--holder-state-snapshots-path \"{holder_state_snapshots_path}\"",
            f"--outcomes-path \"{outcomes_path}\"",
            f"--bucket-count {bucket_count}",
        ]
    )


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _launch_sort_value(row: dict[str, Any]) -> int:
    value = row.get("launch_ts") or row.get("block_time") or 0
    return _int_or_none(value) or 0


def _launch_datetime(row: dict[str, Any]) -> datetime | None:
    ts = _int_or_none(row.get("launch_ts") or row.get("block_time"))
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _churn_proxy(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, start - end)


def _median(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return median(clean)


def _true_rate(values) -> float | None:
    clean = list(values)
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)


def _quantile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return values[index]
