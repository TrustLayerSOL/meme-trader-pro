"""Descriptive T010 funding lineage thesis cycle."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


THESIS_ID = "T010"
THESIS_NAME = "FUNDING LINEAGE"
ALLOWED_CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}
REPORT_JSON = "T010_funding_lineage_summary.json"
REPORT_MD = "T010_funding_lineage_summary.md"
FUNDING_FEATURES = [
    "creator_has_prior_funding_trace",
    "funding_source_available",
    "candidate_funding_wallet",
    "funding_source_confidence",
    "funding_age_seconds",
    "funding_amount_sol",
    "funding_amount_token",
    "launches_sharing_funder",
    "creator_funder_reuse_count",
    "common_funder_candidate_id",
    "repeated_funder_flag",
]


def build_t010_funding_lineage_report(
    *,
    funding_link_path: Path | str,
    outcomes_path: Path | str,
    migration_labels_path: Path | str | None = None,
    t005_summary_path: Path | str | None = None,
    t008_summary_path: Path | str | None = None,
    t009_summary_path: Path | str | None = None,
) -> dict[str, Any]:
    funding_rows_raw = _read_table(funding_link_path)
    outcomes_by_mint = {_mint(row): row for row in _read_jsonl(outcomes_path) if _mint(row)}
    migration_by_mint = _migration_context(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    excluded_future = [
        row for row in funding_rows_raw if _float_or_none(row.get("funding_age_seconds")) is not None and _float_or_none(row.get("funding_age_seconds")) < 0
    ]
    funding_rows = [row for row in funding_rows_raw if row not in excluded_future]
    launch_rows = [
        _build_launch_row(row, outcomes_by_mint.get(_mint(row), {}), migration_by_mint.get(_mint(row), {}))
        for row in funding_rows
        if _mint(row)
    ]
    launch_rows = [row for row in launch_rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None]
    launch_rows.sort(key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    feature_audit = _feature_coverage_audit(launch_rows)
    bucket_counts = _bucket_counts(launch_rows)
    bucket_tables = _bucket_tables(launch_rows)
    main_comparisons = _main_comparisons(bucket_tables, launch_rows)
    robustness = _robustness_checks(launch_rows)
    prior = _prior_result_comparison(
        main_comparisons=main_comparisons,
        t005_summary=_read_json(t005_summary_path),
        t008_summary=_read_json(t008_summary_path),
        t009_summary=_read_json(t009_summary_path),
    )
    warnings = _warning_flags(launch_rows, excluded_future)
    classification = _classify(launch_rows, main_comparisons, robustness, warnings)
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do creators with identifiable and/or repeated pre-launch funders produce launches "
            "with different FDV-proxy lifecycle outcomes than creators without identifiable or repeated funders?"
        ),
        "hypothesis": "Creator pre-launch funding lineage may have descriptive relationship with FDV-proxy lifecycle outcomes.",
        "dataset": {
            "dataset_scope": "funding_link_pilot_coverage_universe",
            "funding_link_path": str(funding_link_path),
            "outcomes_path": str(outcomes_path),
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "launch_count": len(launch_rows),
            "raw_funding_rows": len(funding_rows_raw),
            "future_funding_rows_excluded": len(excluded_future),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "fixed_bucket_features": [
                "funding_source_available",
                "repeated_funder_flag",
                "launches_sharing_funder_bucket",
                "creator_funder_reuse_count_bucket",
                "funding_age_bucket",
            ],
            "funding_amount_view": "rank_quantile_only_if_available",
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
        },
        "methodology_flags": [
            "research_only",
            "descriptive_historical_thesis",
            "no_thesis_promotion",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
            "unsupported_labels_avoided",
        ],
        "funding_link_coverage": _funding_coverage(launch_rows),
        "feature_coverage_audit": feature_audit,
        "bucket_counts": bucket_counts,
        "bucket_tables": bucket_tables,
        "main_comparisons": main_comparisons,
        "robustness_checks": robustness,
        "prior_result_comparison": prior,
        "launch_rows": launch_rows,
        "final_classification": classification,
        "warning_flags": warnings,
        "limitations": _limitations(warnings),
        "larger_funding_link_rollout_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "chronological_robustness_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(
            funding_link_path,
            outcomes_path,
            migration_labels_path,
            t005_summary_path,
            t008_summary_path,
            t009_summary_path,
        ),
    }


def write_t010_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    markdown_path = output / REPORT_MD
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_row(funding: dict[str, Any], outcome: dict[str, Any], migration: dict[str, Any]) -> dict[str, Any]:
    features = _features(funding)
    return {
        "launch_id": funding.get("launch_id") or outcome.get("launch_id"),
        "token_mint": _mint(funding),
        "mint": _mint(funding),
        "creator": funding.get("creator"),
        "launch_ts": _int_or_none(funding.get("launch_ts") or outcome.get("launch_ts")),
        "features": features,
        "funding_buckets": _funding_buckets(features),
        "outcomes": _outcomes(outcome, migration),
        "metadata_json": {
            "candidate_funding_signature": funding.get("candidate_funding_signature"),
            "candidate_funding_time": funding.get("candidate_funding_time"),
            "funding_source_reason": funding.get("funding_source_reason"),
            "funding_source_missing_reason": funding.get("funding_source_missing_reason"),
            "leakage_rule": "funding_age_seconds_must_be_non_negative",
        },
    }


def _features(row: dict[str, Any]) -> dict[str, Any]:
    wallet = _none_if_missing(row.get("candidate_funding_wallet"))
    sharing = _int_or_none(row.get("launches_sharing_funder")) or 0
    reuse = _int_or_none(row.get("creator_funder_reuse_count")) or 0
    return {
        "creator_has_prior_funding_trace": bool(row.get("creator_has_prior_funding_trace")),
        "funding_source_available": bool(wallet),
        "candidate_funding_wallet": wallet,
        "funding_source_confidence": _float_or_none(row.get("funding_source_confidence")),
        "funding_age_seconds": _float_or_none(row.get("funding_age_seconds")),
        "funding_amount_sol": _float_or_none(row.get("funding_amount_sol")),
        "funding_amount_token": _none_if_missing(row.get("funding_amount_token")),
        "launches_sharing_funder": sharing,
        "creator_funder_reuse_count": reuse,
        "common_funder_candidate_id": _none_if_missing(row.get("common_funder_candidate_id")),
        "repeated_funder_flag": bool(wallet) and sharing > 1,
    }


def _funding_buckets(features: dict[str, Any]) -> dict[str, str]:
    sharing = _int_or_none(features.get("launches_sharing_funder")) or 0
    reuse = _int_or_none(features.get("creator_funder_reuse_count")) or 0
    age = _float_or_none(features.get("funding_age_seconds"))
    return {
        "funding_source_available": "available" if features.get("funding_source_available") else "unavailable",
        "repeated_funder_flag": "repeated_funder" if features.get("repeated_funder_flag") else "no_repeated_funder",
        "launches_sharing_funder_bucket": "5_plus" if sharing >= 5 else "2_to_4" if sharing >= 2 else "0_or_1",
        "creator_funder_reuse_count_bucket": "2_plus" if reuse >= 2 else "1" if reuse == 1 else "0",
        "funding_age_bucket": _funding_age_bucket(age),
    }


def _funding_age_bucket(age: float | None) -> str:
    if age is None:
        return "unavailable"
    if age < 3600:
        return "less_than_1h"
    if age < 21600:
        return "1h_to_6h"
    return "6h_to_24h"


def _outcomes(outcome: dict[str, Any], migration: dict[str, Any]) -> dict[str, Any]:
    return {
        "fdv_proxy_runup_120m": _nested_float(outcome, "runups", "max_runup_120m"),
        "fdv_proxy_drawdown_120m": _nested_float(outcome, "drawdowns", "max_drawdown_120m"),
        "price_available_120m": bool(outcome.get("price_available_120m") or outcome.get("has_price_at_120m")),
        "liquidity_proxy_available_120m": bool(
            outcome.get("has_liquidity_proxy_at_120m") or outcome.get("liquidity_survival_120m")
        ),
        "migration_or_graduation_observed": bool(migration.get("migration_or_graduation_observed")),
        "true_market_cap_available": bool(outcome.get("true_market_cap_available") or outcome.get("market_cap_available")),
    }


def _feature_coverage_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    audit = {field: _coverage(rows, field) for field in FUNDING_FEATURES}
    audit["confidence_distribution"] = dict(
        Counter(str(row["features"].get("funding_source_confidence")) for row in rows)
    )
    return audit


def _funding_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in rows if row["features"].get("funding_source_available")]
    repeated = [row for row in rows if row["features"].get("repeated_funder_flag")]
    return {
        "launches_analyzed": len(rows),
        "funding_source_available_count": len(available),
        "funding_source_available_pct": _pct(len(available), len(rows)),
        "repeated_funder_count": len(repeated),
        "repeated_funder_pct": _pct(len(repeated), len(rows)),
        "unique_repeated_funders": len({row["features"].get("candidate_funding_wallet") for row in repeated}),
    }


def _bucket_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    keys = [
        "funding_source_available",
        "repeated_funder_flag",
        "launches_sharing_funder_bucket",
        "creator_funder_reuse_count_bucket",
        "funding_age_bucket",
    ]
    output = {}
    for key in keys:
        counts = Counter(row["funding_buckets"][key] for row in rows)
        output[key] = dict(sorted(counts.items()))
    return output


def _bucket_tables(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    features = [
        "funding_source_available",
        "repeated_funder_flag",
        "launches_sharing_funder_bucket",
        "creator_funder_reuse_count_bucket",
        "funding_age_bucket",
    ]
    return {feature: _table_for_bucket(rows, feature) for feature in features}


def _table_for_bucket(rows: list[dict[str, Any]], bucket_key: str) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["funding_buckets"][bucket_key]].append(row)
    return [
        {"bucket": bucket, **_group_outcomes(grouped[bucket])}
        for bucket in sorted(grouped)
    ]


def _group_outcomes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = [_outcome_value(row, "fdv_proxy_runup_120m") for row in rows]
    drawdowns = [_outcome_value(row, "fdv_proxy_drawdown_120m") for row in rows]
    runups = [value for value in runups if value is not None]
    drawdowns = [value for value in drawdowns if value is not None]
    return {
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "median_fdv_proxy_runup_120m": _median_or_none(runups),
        "median_fdv_proxy_drawdown_120m": _median_or_none(drawdowns),
        "price_available_120m_rate": _rate(rows, "price_available_120m"),
        "liquidity_proxy_available_120m_rate": _rate(rows, "liquidity_proxy_available_120m"),
        "migration_or_graduation_observed_count": sum(
            1 for row in rows if row["outcomes"].get("migration_or_graduation_observed")
        ),
    }


def _main_comparisons(bucket_tables: dict[str, list[dict[str, Any]]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "funding_source_available_vs_unavailable": _compare_bucket(
            bucket_tables["funding_source_available"], "available", "unavailable"
        ),
        "repeated_funder_vs_no_repeated_funder": _compare_bucket(
            bucket_tables["repeated_funder_flag"], "repeated_funder", "no_repeated_funder"
        ),
        "high_shared_funder_vs_low_shared_funder": _compare_bucket(
            bucket_tables["launches_sharing_funder_bucket"], "5_plus", "0_or_1"
        ),
        "recent_funding_vs_older_funding": _compare_bucket(
            bucket_tables["funding_age_bucket"], "less_than_1h", "6h_to_24h"
        ),
        "higher_funding_amount_vs_lower_funding_amount": _amount_quantile_comparison(rows),
    }


def _compare_bucket(table: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    by_bucket = {row["bucket"]: row for row in table}
    left_table = by_bucket.get(left, _group_outcomes([]))
    right_table = by_bucket.get(right, _group_outcomes([]))
    return {
        "left_group": left,
        "right_group": right,
        "left": left_table,
        "right": right_table,
        "median_runup_delta": _delta(left_table, right_table, "median_fdv_proxy_runup_120m"),
        "median_drawdown_delta": _delta(left_table, right_table, "median_fdv_proxy_drawdown_120m"),
        "left_outperformed_descriptively": _outperformed(left_table, right_table),
    }


def _amount_quantile_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if _feature_value(row, "funding_amount_sol") is not None]
    if len(usable) < 20:
        return {"usable": False, "reason": "insufficient_funding_amount_coverage"}
    usable.sort(key=lambda row: (_feature_value(row, "funding_amount_sol") or 0, row["token_mint"]))
    n = len(usable)
    lower = usable[: n // 3]
    higher = usable[(2 * n) // 3 :]
    left = _group_outcomes(higher)
    right = _group_outcomes(lower)
    return {
        "usable": True,
        "left_group": "higher_funding_amount_quantile",
        "right_group": "lower_funding_amount_quantile",
        "left": left,
        "right": right,
        "median_runup_delta": _delta(left, right, "median_fdv_proxy_runup_120m"),
        "median_drawdown_delta": _delta(left, right, "median_fdv_proxy_drawdown_120m"),
        "left_outperformed_descriptively": _outperformed(left, right),
    }


def _robustness_checks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "exclude_low_confidence_funding_links": _exclude_low_confidence(rows),
        "exclude_dominant_funder": _exclude_dominant_funder(rows),
        "exclude_top_1pct_fdv_proxy_runups": _trimmed_comparison(rows, 0.99),
        "exclude_top_5pct_fdv_proxy_runups": _trimmed_comparison(rows, 0.95),
        "chronological_halves": _chronological_halves(rows),
        "creator_concentration_by_funder_bucket": _creator_concentration(rows),
        "prior_migration_dominance": _prior_migration_dominance(rows),
    }


def _exclude_low_confidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kept = [
        row for row in rows
        if not row["features"].get("funding_source_available")
        or (_feature_value(row, "funding_source_confidence") or 0) >= 0.7
    ]
    return _robust_comparison_summary(kept)


def _exclude_dominant_funder(rows: list[dict[str, Any]]) -> dict[str, Any]:
    funders = [row["features"].get("candidate_funding_wallet") for row in rows if row["features"].get("candidate_funding_wallet")]
    if not funders:
        return {"usable": False, "reason": "no_funders"}
    dominant, count = Counter(funders).most_common(1)[0]
    kept = [row for row in rows if row["features"].get("candidate_funding_wallet") != dominant]
    return {"dominant_funder": dominant, "dominant_funder_launch_count": count, **_robust_comparison_summary(kept)}


def _trimmed_comparison(rows: list[dict[str, Any]], pct: float) -> dict[str, Any]:
    runups = sorted([_outcome_value(row, "fdv_proxy_runup_120m") for row in rows if _outcome_value(row, "fdv_proxy_runup_120m") is not None])
    if not runups:
        return {"usable": False, "reason": "no_fdv_proxy_runups"}
    cutoff = runups[max(0, min(len(runups) - 1, int(len(runups) * pct) - 1))]
    kept = [row for row in rows if (_outcome_value(row, "fdv_proxy_runup_120m") or 0) <= cutoff]
    return {"cutoff": cutoff, **_robust_comparison_summary(kept)}


def _chronological_halves(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    mid = len(ordered) // 2
    return {
        "first_half": _robust_comparison_summary(ordered[:mid]),
        "second_half": _robust_comparison_summary(ordered[mid:]),
    }


def _robust_comparison_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tables = _bucket_tables(rows)
    return {
        "usable": len(rows) >= 20,
        "launch_count": len(rows),
        "repeated_funder_vs_no_repeated_funder": _compare_bucket(
            tables["repeated_funder_flag"], "repeated_funder", "no_repeated_funder"
        ),
    }


def _creator_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for bucket in ["repeated_funder", "no_repeated_funder"]:
        subset = [row for row in rows if row["funding_buckets"]["repeated_funder_flag"] == bucket]
        counts = Counter(row.get("creator") or "unknown" for row in subset)
        top = counts.most_common(3)
        output[bucket] = {
            "launch_count": len(subset),
            "top_creator_share": (top[0][1] / len(subset)) if subset and top else None,
            "top_creators": [{"creator": creator, "launch_count": count} for creator, count in top],
        }
    return output


def _prior_migration_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    repeated = [row for row in rows if row["features"].get("repeated_funder_flag")]
    with_migration = [row for row in repeated if row["outcomes"].get("migration_or_graduation_observed")]
    return {
        "repeated_funder_launch_count": len(repeated),
        "migration_or_graduation_observed_count": len(with_migration),
        "migration_or_graduation_observed_pct": _pct(len(with_migration), len(repeated)),
    }


def _prior_result_comparison(
    *,
    main_comparisons: dict[str, Any],
    t005_summary: dict[str, Any] | None,
    t008_summary: dict[str, Any] | None,
    t009_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    funding_delta = main_comparisons["repeated_funder_vs_no_repeated_funder"].get("median_runup_delta")
    return {
        "T005": t005_summary.get("final_classification", "weak_signal") if t005_summary else "weak_signal",
        "T008": _t008_classification(t008_summary),
        "T009": t009_summary.get("final_classification", "no_signal") if t009_summary else "no_signal",
        "funding_lineage_runup_delta": funding_delta,
        "funding_lineage_beats_T005_descriptively": _beats_prior_abs_delta(funding_delta, t005_summary, "T005"),
        "funding_lineage_beats_T008_descriptively": _beats_prior_abs_delta(funding_delta, t008_summary, "T008"),
        "funding_lineage_beats_T009_descriptively": _beats_prior_abs_delta(funding_delta, t009_summary, "T009"),
        "comparison_note": "Qualitative descriptive comparison only; no validation or promotion is made.",
    }


def _t008_classification(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "unstable_weak_signal"
    return summary.get("robustness_classification") or summary.get("final_classification") or "unstable_weak_signal"


def _beats_prior_abs_delta(delta: float | None, summary: dict[str, Any] | None, prior: str) -> bool | None:
    if delta is None:
        return None
    if prior == "T009" and summary:
        prior_delta = summary.get("t005_baseline_comparison", {}).get("t009_fast_broad_runup_delta")
        prior_delta = _float_or_none(prior_delta)
        return abs(delta) > abs(prior_delta) if prior_delta is not None else None
    if prior == "T005" and summary:
        prior_delta = _max_feature_report_spread(summary.get("feature_reports", {}))
        return abs(delta) > abs(prior_delta) if prior_delta is not None else None
    if prior == "T008" and summary:
        prior_delta = _bucket_table_spread(summary.get("full_sample_primary_bucket_table", []))
        return abs(delta) > abs(prior_delta) if prior_delta is not None else None
    return None


def _max_feature_report_spread(feature_reports: dict[str, Any]) -> float | None:
    spreads = []
    for report in feature_reports.values():
        spread = _bucket_table_spread(report.get("bucket_tables", []))
        if spread is not None:
            spreads.append(spread)
    return max(spreads) if spreads else None


def _bucket_table_spread(table: list[dict[str, Any]]) -> float | None:
    values = [_float_or_none(row.get("median_fdv_proxy_runup_120m")) for row in table]
    values = [value for value in values if value is not None]
    return max(values) - min(values) if values else None


def _warning_flags(rows: list[dict[str, Any]], excluded_future: list[dict[str, Any]]) -> list[str]:
    warnings = {"true_market_cap_claims_blocked", "funding_link_pilot_scope_only"}
    if excluded_future:
        warnings.add("future_funding_rows_excluded")
    coverage = _funding_coverage(rows)
    if coverage["funding_source_available_pct"] < 50:
        warnings.add("partial_funding_source_coverage")
    if len(rows) < 100:
        warnings.add("small_sample_for_descriptive_thesis")
    return sorted(warnings)


def _classify(
    rows: list[dict[str, Any]],
    main: dict[str, Any],
    robustness: dict[str, Any],
    warnings: list[str],
) -> str:
    if len(rows) < 100:
        return "data_limited"
    primary = main["repeated_funder_vs_no_repeated_funder"]
    available = main["funding_source_available_vs_unavailable"]
    if not primary.get("left_outperformed_descriptively") and not available.get("left_outperformed_descriptively"):
        return "no_signal"
    robust_primary = robustness["exclude_top_5pct_fdv_proxy_runups"]["repeated_funder_vs_no_repeated_funder"]
    if primary.get("left_outperformed_descriptively") and robust_primary.get("left_outperformed_descriptively"):
        return "descriptive_signal_present"
    return "weak_signal"


def _limitations(warnings: list[str]) -> list[str]:
    limitations = [
        "Funding lineage is limited to the 50-creator, 667-launch pilot universe.",
        "FDV proxy outcomes are used; true market-cap claims remain blocked.",
        "This is descriptive only and does not create a trading rule.",
        "Repeated funders are deterministic candidate funders, not unsupported manipulation labels.",
    ]
    if "partial_funding_source_coverage" in warnings:
        limitations.append("Funding source coverage is partial; unavailable rows are not assumed clean or unfunded.")
    if "future_funding_rows_excluded" in warnings:
        limitations.append("Rows with negative funding age were excluded to preserve the no-future-leakage rule.")
    return limitations


def _next_recommendation(classification: str) -> str:
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "Run a larger bounded funding-link rollout and separate chronological robustness review before any validation."
    if classification == "no_signal":
        return "Park funding-lineage thesis promotion and review whether broader data sources are justified."
    return "Expand funding-link coverage before interpreting T010."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "launch_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    repeated = report["main_comparisons"]["repeated_funder_vs_no_repeated_funder"]
    lines = [
        "# T010 Funding Lineage",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launches analyzed: `{report['dataset']['launch_count']}`",
        f"- Funding source coverage: `{report['funding_link_coverage']['funding_source_available_pct']}`%",
        f"- Repeated funder coverage: `{report['funding_link_coverage']['repeated_funder_pct']}`%",
        f"- Repeated funder outperformed no repeated funder: `{repeated.get('left_outperformed_descriptively')}`",
        f"- Median runup delta: `{repeated.get('median_runup_delta')}`",
        "",
        "## Bucket Counts",
        "",
    ]
    for feature, counts in report["bucket_counts"].items():
        lines.append(f"- `{feature}`: `{counts}`")
    lines.extend(["", "## Prior Result Comparison", ""])
    for key, value in report["prior_result_comparison"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No thesis promotion was made.",
            "- No backtest or walk-forward validation was run.",
            "- No trading rules were generated.",
            "- No profitability claims were made.",
            "",
            "## Warning Flags",
            "",
        ]
    )
    lines.extend(f"- `{flag}`" for flag in report["warning_flags"])
    lines.extend(["", "## Next Recommendation", "", report["next_recommendation"], ""])
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T010 FUNDING LINEAGE STATUS",
            "",
            "## Thesis Description",
            "",
            report["hypothesis"],
            "",
            "## Dataset",
            "",
            f"- Dataset used: `{report['dataset']['dataset_scope']}`",
            f"- Launch count: `{report['dataset']['launch_count']}`",
            f"- Funding-link coverage: `{report['funding_link_coverage']}`",
            "",
            "## Feature Coverage",
            "",
            f"- Candidate funding wallet: `{report['feature_coverage_audit']['candidate_funding_wallet']}`",
            f"- Funding age seconds: `{report['feature_coverage_audit']['funding_age_seconds']}`",
            f"- Launches sharing funder: `{report['feature_coverage_audit']['launches_sharing_funder']}`",
            "",
            "## Classification",
            "",
            f"- Classification: `{report['final_classification']}`",
            f"- Larger funding-link rollout recommended: `{report['larger_funding_link_rollout_recommended']}`",
            f"- Chronological robustness recommended: `{report['chronological_robustness_recommended']}`",
            "",
            "## Comparison To T005/T008/T009",
            "",
            f"- T005: `{report['prior_result_comparison']['T005']}`",
            f"- T008: `{report['prior_result_comparison']['T008']}`",
            f"- T009: `{report['prior_result_comparison']['T009']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Guardrails",
            "",
            "- No thesis promotion was made.",
            "- No validation, backtest, walk-forward, paper/live trading, trading logic, optimization, grid search, or ML workflow was run.",
            "- No trading rules were generated.",
            "",
            "## Outputs",
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
        ]
    )


def _reproducible_command(
    funding_link_path: Path | str,
    outcomes_path: Path | str,
    migration_labels_path: Path | str | None,
    t005_summary_path: Path | str | None,
    t008_summary_path: Path | str | None,
    t009_summary_path: Path | str | None,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.validation.run_funding_lineage_thesis",
        f'--funding-link-path "{funding_link_path}"',
        f'--outcomes-path "{outcomes_path}"',
    ]
    if migration_labels_path:
        parts.append(f'--migration-labels-path "{migration_labels_path}"')
    if t005_summary_path:
        parts.append(f'--t005-summary-path "{t005_summary_path}"')
    if t008_summary_path:
        parts.append(f'--t008-summary-path "{t008_summary_path}"')
    if t009_summary_path:
        parts.append(f'--t009-summary-path "{t009_summary_path}"')
    return " ".join(parts)


def _read_table(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if p.suffix == ".parquet":
        try:
            import pandas as pd

            return pd.read_parquet(p).to_dict(orient="records")
        except Exception:
            fallback = p.with_suffix(".jsonl")
            if fallback.exists():
                return _read_jsonl(fallback)
            raise
    return _read_jsonl(p)


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


def _read_json(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _migration_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for row in rows:
        mint = _mint(row)
        if not mint:
            continue
        output[mint] = {
            "migration_or_graduation_observed": bool(
                row.get("pumpfun_migrate_event_observed")
                or row.get("graduated_to_pumpswap")
                or row.get("migrated_to_raydium")
                or row.get("dex_pair_detected")
            )
        }
    return output


def _coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if _feature_any(row, field) is not None)
    total = len(rows)
    return {"available_rows": available, "missing_rows": total - available, "coverage_pct": _pct(available, total)}


def _feature_any(row: dict[str, Any], field: str) -> Any:
    value = (row.get("features") or {}).get(field)
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return None
    return value


def _feature_value(row: dict[str, Any], field: str) -> float | None:
    return _float_or_none((row.get("features") or {}).get(field))


def _outcome_value(row: dict[str, Any], field: str) -> float | None:
    return _float_or_none((row.get("outcomes") or {}).get(field))


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row["outcomes"].get(field)) / len(rows)


def _delta(left: dict[str, Any], right: dict[str, Any], field: str) -> float | None:
    lval = _float_or_none(left.get(field))
    rval = _float_or_none(right.get(field))
    if lval is None or rval is None:
        return None
    return lval - rval


def _outperformed(left: dict[str, Any], right: dict[str, Any]) -> bool | None:
    runup_delta = _delta(left, right, "median_fdv_proxy_runup_120m")
    if runup_delta is None:
        return None
    drawdown_delta = _delta(left, right, "median_fdv_proxy_drawdown_120m")
    return runup_delta > 0 and (drawdown_delta is None or drawdown_delta >= 0)


def _nested_float(row: dict[str, Any], parent: str, child: str) -> float | None:
    value = row.get(parent)
    if isinstance(value, dict):
        return _float_or_none(value.get(child))
    return None


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _float_or_none(value: Any) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 6) if total else 0.0


def _none_if_missing(value: Any) -> Any:
    return None if _is_missing(value) else value


def _is_missing(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(value != value)
    except Exception:
        return False
