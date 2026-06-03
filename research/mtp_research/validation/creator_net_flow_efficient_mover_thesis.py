"""Creator-net-flow efficient-mover formal descriptive thesis.

Formal descriptive thesis cycle for creator_net_flow_sol_before_20k inside the
fixed high-FDV-efficiency universe. This does not run validation, backtests,
optimization, trading logic, alerts, or thesis promotion.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.efficient_mover_continuation_anatomy import (
    build_efficient_mover_universe,
    label_continuation_paths,
)


REPORT_ID = "creator_net_flow_efficient_mover_thesis_v0"
FEATURE = "creator_net_flow_sol_before_20k"
DEFAULT_FEATURE_COMPARISON_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "efficient_mover_continuation_anatomy",
    "efficient_mover_feature_comparison.csv",
)
DEFAULT_MASTER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.parquet",
)
DEFAULT_MASTER_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "creator_net_flow_efficient_mover_thesis"
)
DEFAULT_STATUS_PATH = Path("theses/CREATOR_NET_FLOW_EFFICIENT_MOVER_THESIS_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
METHODOLOGY_FLAGS = [
    "formal_descriptive_thesis_only",
    "creator_net_flow_efficient_mover_thesis_only",
    "definition_loaded_from_efficient_mover_anatomy_report",
    "no_early_buyer_thesis_execution",
    "no_frp004_execution",
    "no_validation_execution",
    "no_walk_forward_validation",
    "no_backtest",
    "no_paper_trading",
    "no_live_trading",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_order_routing",
    "no_alerts",
    "no_buy_rules",
    "no_sell_rules",
    "no_trading_logic",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
    "fixed_tertile_buckets_not_tuned",
]


def build_creator_net_flow_efficient_mover_thesis(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    feature_comparison_path: Path | str = DEFAULT_FEATURE_COMPARISON_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    definition = load_frozen_definition(feature_comparison_path=feature_comparison_path)
    if definition.get("status") == "definition_missing":
        report = _definition_missing_report(definition, master_path, feature_comparison_path)
        paths = write_outputs(report, [], [], [], output, Path(status_path))
        return report, paths

    master = _load_master(master_path, jsonl_fallback)
    scored = label_continuation_paths(build_efficient_mover_universe(master))
    efficient = scored[scored["fdv_baseline_high"] == True].copy().reset_index(drop=True)  # noqa: E712
    efficient = build_fixed_creator_net_flow_buckets(efficient, bucket_count=3)
    coverage = coverage_audit(master, efficient)
    tier_rows = tier_comparison(efficient, definition)
    bucket_rows = bucket_comparison(efficient, definition)
    robustness = robustness_table(efficient, definition)
    fdv_relationship = fdv_relationship_table(efficient)
    robustness_summary = summarize_robustness(robustness, definition)
    classification = classify_thesis(coverage, bucket_rows, robustness_summary, efficient)
    report = {
        "report_id": REPORT_ID,
        "report_type": "creator_net_flow_efficient_mover_formal_descriptive_thesis",
        "classification": classification,
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {
            "master_path": str(master_path),
            "jsonl_fallback": str(jsonl_fallback),
            "feature_comparison_path": str(feature_comparison_path),
        },
        "frozen_definition": definition,
        "population_definition": "high-FDV-efficiency efficient movers from fixed non-optimized quantile buckets",
        "rows_loaded": int(len(master)),
        "efficient_mover_rows_analyzed": int(len(efficient)),
        "coverage_audit": coverage,
        "descriptive_results": {
            "tier_rows": tier_rows,
            "bucket_rows": bucket_rows,
            "primary_direction_result": primary_direction_result(bucket_rows, definition),
        },
        "robustness_table": robustness,
        "robustness_summary": robustness_summary,
        "fdv_relationship": fdv_relationship,
        "limitations": [
            "Formal descriptive thesis only; no validation, walk-forward validation, backtest, optimization, alerts, or execution logic.",
            "Continuation and trap/stall labels are milestone-tier proxies, not trade outcomes.",
            "FDV/valuation proxy only; true market-cap claims remain blocked.",
            "Creator-net-flow is a structural proxy and should not be interpreted as intent or identity evidence.",
            "The efficient-mover universe inherits snapshot-level observability limitations from prior audits.",
        ],
        "next_recommendation": next_recommendation(classification, robustness_summary),
    }
    _assert_guardrails(report)
    paths = write_outputs(report, tier_rows, robustness, fdv_relationship, output, Path(status_path))
    return report, paths


def load_frozen_definition(*, feature_comparison_path: Path | str = DEFAULT_FEATURE_COMPARISON_PATH) -> dict[str, Any]:
    path = Path(feature_comparison_path)
    if not path.exists():
        return {"status": "definition_missing", "missing_reason": "feature_comparison_path_missing", "feature": FEATURE}
    table = pd.read_csv(path)
    rows = table[table.get("feature", pd.Series(dtype=object)).astype(str) == FEATURE]
    if len(rows) != 1:
        return {"status": "definition_missing", "missing_reason": "creator_net_flow_feature_row_missing_or_duplicated", "feature": FEATURE}
    row = rows.iloc[0].to_dict()
    associated = str(row.get("higher_values_associated_with") or "")
    if associated == "continuation_proxy":
        expected = "higher_creator_net_flow_supports_continuation_proxy"
    elif associated == "trap_proxy":
        expected = "higher_creator_net_flow_supports_trap_proxy"
    else:
        return {
            "status": "definition_missing",
            "missing_reason": "expected_direction_missing_or_ambiguous",
            "feature": FEATURE,
            "raw_feature_row": row,
        }
    return {
        "status": "loaded",
        "feature": FEATURE,
        "expected_direction": expected,
        "higher_values_associated_with": associated,
        "classification": row.get("classification"),
        "effect_size_proxy_from_anatomy": _safe_float(row.get("effect_size_proxy")),
        "coverage_pct_from_anatomy": _safe_float(row.get("coverage_pct")),
        "feature_timing": row.get("feature_timing"),
        "raw_feature_row": row,
        "known_limitations": [
            "Direction is frozen from the efficient-mover continuation anatomy report.",
            "No direction is inferred independently when the prior report is missing or ambiguous.",
        ],
    }


def build_fixed_creator_net_flow_buckets(frame: pd.DataFrame, *, bucket_count: int = 3) -> pd.DataFrame:
    result = frame.copy()
    series = _feature_numeric(result.get(FEATURE, pd.Series([pd.NA] * len(result))))
    result[FEATURE] = series
    labels = ["low", "middle", "high"] if bucket_count == 3 else [f"bucket_{idx + 1}" for idx in range(bucket_count)]
    valid = series.notna()
    result["creator_net_flow_bucket"] = pd.NA
    result["creator_net_flow_bucket_rank"] = pd.NA
    if valid.sum() == 0:
        return result
    pct_rank = series[valid].rank(method="first", pct=True)
    bucket_index = ((pct_rank * bucket_count).apply(lambda value: min(bucket_count - 1, max(0, int(value * bucket_count - 1e-9))))).astype(int)
    result.loc[valid, "creator_net_flow_bucket_rank"] = bucket_index
    result.loc[valid, "creator_net_flow_bucket"] = bucket_index.map({idx: labels[idx] for idx in range(bucket_count)})
    return result


def coverage_audit(master: pd.DataFrame, efficient: pd.DataFrame) -> dict[str, Any]:
    total_enriched = int(len(master))
    high_fdv = int(len(efficient))
    present = FEATURE in efficient.columns
    series = efficient[FEATURE] if present else pd.Series([pd.NA] * len(efficient))
    non_null = int(series.notna().sum())
    by_tier = {}
    for tier in TIER_ORDER:
        subset = efficient[efficient.get("milestone_tier", pd.Series(dtype=object)).astype(str) == tier]
        tier_series = subset[FEATURE] if present and FEATURE in subset.columns else pd.Series(dtype=object)
        by_tier[tier] = {
            "rows": int(len(subset)),
            "non_null_rows": int(tier_series.notna().sum()),
            "coverage_pct": _pct(int(tier_series.notna().sum()), len(subset)),
        }
    return {
        "total_enriched_rows": total_enriched,
        "high_fdv_efficiency_rows": high_fdv,
        "creator_net_flow_non_null_rows": non_null,
        "creator_net_flow_coverage_pct": _pct(non_null, high_fdv),
        "coverage_by_milestone_tier": by_tier,
        "top_date_coverage": _top_counts(efficient.loc[series.notna(), "launch_date"] if present and "launch_date" in efficient else []),
        "top_creator_coverage": _top_counts(efficient.loc[series.notna(), "creator"] if present and "creator" in efficient else []),
        "missing_reason_counts": {"field_missing": high_fdv} if not present else {"null_creator_net_flow_proxy": int(series.isna().sum())},
    }


def tier_comparison(efficient: pd.DataFrame, definition: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for tier in TIER_ORDER:
        subset = efficient[efficient.get("milestone_tier", pd.Series(dtype=object)).astype(str) == tier]
        values = _feature_numeric(subset.get(FEATURE, pd.Series(dtype=object))).dropna()
        rows.append(
            {
                "comparison": "milestone_tier",
                "group": tier,
                "rows": int(len(subset)),
                "non_null_rows": int(len(values)),
                "median_creator_net_flow": _median(values),
                "iqr_creator_net_flow": _iqr(values),
                "continuation_proxy_rate_pct": _pct(int((subset.get("clean_continuation_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "trap_stall_proxy_rate_pct": _pct(int((subset.get("trap_or_stall_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "expected_direction": definition["expected_direction"],
            }
        )
    for label, mask in {
        "continuation_proxy": efficient["clean_continuation_proxy"] == True,  # noqa: E712
        "trap_stall_proxy": efficient["trap_or_stall_proxy"] == True,  # noqa: E712
        "failed_to_reach_500k": efficient["failed_to_reach_500k"] == True,  # noqa: E712
    }.items():
        subset = efficient[mask]
        values = _feature_numeric(subset.get(FEATURE, pd.Series(dtype=object))).dropna()
        rows.append(
            {
                "comparison": "path_proxy",
                "group": label,
                "rows": int(len(subset)),
                "non_null_rows": int(len(values)),
                "median_creator_net_flow": _median(values),
                "iqr_creator_net_flow": _iqr(values),
                "continuation_proxy_rate_pct": _pct(int((subset.get("clean_continuation_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "trap_stall_proxy_rate_pct": _pct(int((subset.get("trap_or_stall_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "expected_direction": definition["expected_direction"],
            }
        )
    return rows


def bucket_comparison(efficient: pd.DataFrame, definition: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket in ["low", "middle", "high"]:
        subset = efficient[efficient.get("creator_net_flow_bucket", pd.Series(dtype=object)).astype(str) == bucket]
        flow = _feature_numeric(subset.get(FEATURE, pd.Series(dtype=object))).dropna()
        rows.append(
            {
                "bucket_method": "fixed_tertiles",
                "creator_net_flow_bucket": bucket,
                "rows": int(len(subset)),
                "median_creator_net_flow": _median(flow),
                "iqr_creator_net_flow": _iqr(flow),
                "continuation_proxy_rows": int((subset.get("clean_continuation_proxy", pd.Series(dtype=bool)) == True).sum()),  # noqa: E712
                "trap_stall_proxy_rows": int((subset.get("trap_or_stall_proxy", pd.Series(dtype=bool)) == True).sum()),  # noqa: E712
                "continuation_proxy_rate_pct": _pct(int((subset.get("clean_continuation_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "trap_stall_proxy_rate_pct": _pct(int((subset.get("trap_or_stall_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "reached_500k_plus_rate_pct": _pct(int((subset.get("reached_500k", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "expected_direction": definition["expected_direction"],
            }
        )
    return rows


def robustness_table(efficient: pd.DataFrame, definition: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    specs = [("full_sample", efficient)]
    ordered = efficient.sort_values(["launch_date", "launch_id"], na_position="last")
    specs.extend(_chronological_splits(ordered, 2, "chronological_half"))
    if len(efficient) >= 90:
        specs.extend(_chronological_splits(ordered, 3, "chronological_third"))
    specs.extend(_exclusion_splits(efficient))
    specs.extend(_contrast_splits(efficient))
    for name, subset in specs:
        rows.append(_robustness_row(name, subset, definition))
    return rows


def fdv_relationship_table(efficient: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for bucket in ["low", "middle", "high"]:
        subset = efficient[efficient.get("creator_net_flow_bucket", pd.Series(dtype=object)).astype(str) == bucket]
        rows.append(
            {
                "creator_net_flow_bucket": bucket,
                "rows": int(len(subset)),
                "median_fdv_per_event_at_20k": _median(_feature_numeric(subset.get("fdv_per_event_at_20k", pd.Series(dtype=object))).dropna()),
                "median_fdv_per_buy_at_20k": _median(_feature_numeric(subset.get("fdv_per_buy_at_20k", pd.Series(dtype=object))).dropna()),
                "median_fdv_per_active_wallet_at_20k": _median(_feature_numeric(subset.get("fdv_per_active_wallet_at_20k", pd.Series(dtype=object))).dropna()),
                "median_fdv_support_count": _median(_feature_numeric(subset.get("fdv_baseline_support_count", pd.Series(dtype=object))).dropna()),
                "continuation_proxy_rate_pct": _pct(int((subset.get("clean_continuation_proxy", pd.Series(dtype=bool)) == True).sum()), len(subset)),  # noqa: E712
                "interpretation": "Checks whether creator-net-flow bucket simply duplicates FDV-efficiency level inside the high-FDV universe.",
            }
        )
    return rows


def summarize_robustness(rows: list[dict[str, Any]], definition: dict[str, Any]) -> dict[str, Any]:
    valid = [row for row in rows if row["status"] == "ok"]
    consistent = [row for row in valid if row["direction_consistent_with_definition"]]
    return {
        "checks_run": len(rows),
        "valid_checks": len(valid),
        "directionally_consistent_checks": len(consistent),
        "directionally_consistent_pct": _pct(len(consistent), len(valid)),
        "expected_direction": definition.get("expected_direction"),
    }


def primary_direction_result(bucket_rows: list[dict[str, Any]], definition: dict[str, Any]) -> dict[str, Any]:
    by_bucket = {row["creator_net_flow_bucket"]: row for row in bucket_rows}
    low = by_bucket.get("low", {})
    high = by_bucket.get("high", {})
    delta = (high.get("continuation_proxy_rate_pct") or 0) - (low.get("continuation_proxy_rate_pct") or 0)
    expected = definition.get("expected_direction")
    consistent = delta > 0 if expected == "higher_creator_net_flow_supports_continuation_proxy" else delta < 0
    return {
        "comparison": "high_vs_low_creator_net_flow_fixed_tertiles",
        "high_bucket_continuation_rate_pct": high.get("continuation_proxy_rate_pct"),
        "low_bucket_continuation_rate_pct": low.get("continuation_proxy_rate_pct"),
        "delta_pct_points": round(delta, 4),
        "direction_consistent_with_definition": bool(consistent),
    }


def classify_thesis(coverage: dict[str, Any], bucket_rows: list[dict[str, Any]], robustness_summary: dict[str, Any], efficient: pd.DataFrame) -> str:
    if coverage["creator_net_flow_coverage_pct"] < 25 or len(efficient) < 50:
        return "data_limited"
    primary = primary_direction_result(bucket_rows, {"expected_direction": robustness_summary["expected_direction"]})
    if not primary["direction_consistent_with_definition"]:
        return "no_signal"
    delta = abs(primary["delta_pct_points"])
    consistency = robustness_summary["directionally_consistent_pct"]
    top_date = _top_share_pct(efficient, "launch_date")
    top_creator = _top_share_pct(efficient, "creator")
    if delta >= 10 and consistency >= 70 and top_date < 60 and top_creator < 60:
        return "descriptive_signal_present"
    if delta >= 5 and consistency >= 50:
        return "weak_signal"
    return "no_signal"


def next_recommendation(classification: str, robustness_summary: dict[str, Any]) -> dict[str, Any]:
    if classification == "descriptive_signal_present":
        action = "run_follow_up_path_drawdown_recovery_report_or_broader_risk_filter_thesis_without_validation"
    elif classification == "weak_signal":
        action = "improve_path_drawdown_and_creator_flow_context_before_any_validation"
    elif classification == "data_limited":
        action = "repair_creator_net_flow_or_efficient_mover_coverage_before_interpretation"
    elif classification == "definition_missing":
        action = "repair_prior_anatomy_definition_before_running_thesis"
    else:
        action = "park_creator_net_flow_as_no_signal_until_better_path_labels_exist"
    return {
        "action": action,
        "do_not_execute_in_this_sprint": True,
        "what_not_to_do_next": "Do not validate, optimize thresholds, create execution logic, or move to paper/live trading from this descriptive thesis.",
    }


def write_outputs(
    report: dict[str, Any],
    tier_rows: list[dict[str, Any]],
    robustness_rows: list[dict[str, Any]],
    fdv_rows: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "creator_net_flow_efficient_mover_thesis_summary.json",
        "summary_markdown_path": output / "creator_net_flow_efficient_mover_thesis_summary.md",
        "tier_comparison_path": output / "creator_net_flow_tier_comparison.csv",
        "robustness_table_path": output / "creator_net_flow_robustness_table.csv",
        "fdv_relationship_path": output / "creator_net_flow_fdv_relationship.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_summary_markdown(report), encoding="utf-8")
    pd.DataFrame(tier_rows).to_csv(paths["tier_comparison_path"], index=False)
    pd.DataFrame(robustness_rows).to_csv(paths["robustness_table_path"], index=False)
    pd.DataFrame(fdv_rows).to_csv(paths["fdv_relationship_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _definition_missing_report(definition: dict[str, Any], master_path: Path | str, feature_comparison_path: Path | str) -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "report_type": "creator_net_flow_efficient_mover_formal_descriptive_thesis",
        "classification": "definition_missing",
        "methodology_flags": METHODOLOGY_FLAGS + ["fail_closed_definition_missing"],
        "guardrails": _guardrails(),
        "source_paths": {"master_path": str(master_path), "feature_comparison_path": str(feature_comparison_path)},
        "frozen_definition": definition,
        "population_definition": "not_run_definition_missing",
        "rows_loaded": 0,
        "efficient_mover_rows_analyzed": 0,
        "coverage_audit": {},
        "descriptive_results": {},
        "robustness_table": [],
        "robustness_summary": {},
        "fdv_relationship": [],
        "limitations": ["Prior anatomy direction missing or ambiguous; thesis failed closed."],
        "next_recommendation": next_recommendation("definition_missing", {}),
    }


def _robustness_row(name: str, subset: pd.DataFrame, definition: dict[str, Any]) -> dict[str, Any]:
    cont = subset[subset["clean_continuation_proxy"] == True]  # noqa: E712
    trap = subset[subset["trap_or_stall_proxy"] == True]  # noqa: E712
    cont_values = _feature_numeric(cont.get(FEATURE, pd.Series(dtype=object))).dropna()
    trap_values = _feature_numeric(trap.get(FEATURE, pd.Series(dtype=object))).dropna()
    status = "ok" if len(cont_values) >= 3 and len(trap_values) >= 3 else "data_limited"
    cont_median = _median(cont_values)
    trap_median = _median(trap_values)
    delta = None if cont_median is None or trap_median is None else round(cont_median - trap_median, 4)
    expected = definition.get("expected_direction")
    consistent = False
    if status == "ok" and delta is not None:
        consistent = delta > 0 if expected == "higher_creator_net_flow_supports_continuation_proxy" else delta < 0
    return {
        "check_name": name,
        "rows": int(len(subset)),
        "continuation_rows": int(len(cont_values)),
        "trap_stall_rows": int(len(trap_values)),
        "continuation_median": cont_median,
        "trap_stall_median": trap_median,
        "median_delta_continuation_minus_trap": delta,
        "direction_consistent_with_definition": bool(consistent),
        "status": status,
    }


def _chronological_splits(frame: pd.DataFrame, parts: int, prefix: str) -> list[tuple[str, pd.DataFrame]]:
    if frame.empty:
        return []
    chunks = []
    size = len(frame)
    for idx in range(parts):
        start = int(idx * size / parts)
        end = int((idx + 1) * size / parts)
        chunks.append((f"{prefix}_{idx + 1}", frame.iloc[start:end].copy()))
    return chunks


def _exclusion_splits(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    splits = []
    if "launch_date" in frame.columns:
        dates = [item for item, _ in Counter(frame["launch_date"].dropna().astype(str)).most_common(3)]
        if dates:
            splits.append(("exclude_top_date", frame[~frame["launch_date"].astype(str).isin(dates[:1])].copy()))
            splits.append(("exclude_top_3_dates", frame[~frame["launch_date"].astype(str).isin(dates[:3])].copy()))
    if "creator" in frame.columns:
        creators = [item for item, _ in Counter(frame["creator"].dropna().astype(str)).most_common(3)]
        if creators:
            splits.append(("exclude_top_creator", frame[~frame["creator"].astype(str).isin(creators[:1])].copy()))
            splits.append(("exclude_top_3_creators", frame[~frame["creator"].astype(str).isin(creators[:3])].copy()))
    critical = ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "fdv_per_active_wallet_at_20k"]
    present = [column for column in critical if column in frame.columns]
    if present:
        splits.append(("exclude_missing_critical_fdv_fields", frame.dropna(subset=present).copy()))
    return splits


def _contrast_splits(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [
        ("contrast_500k_plus_vs_sub_500k", frame.copy()),
        ("contrast_1m_plus_vs_sub_1m", frame.copy()),
        ("contrast_1m_plus_vs_500k_not_1m", frame[frame["milestone_tier"].isin(["reached_1m_plus", "reached_500k_but_never_1m"])].copy()),
    ]


def _load_master(master_path: Path | str, jsonl_fallback: Path | str) -> pd.DataFrame:
    path = Path(master_path)
    fallback = Path(jsonl_fallback)
    if path.exists():
        return pd.read_parquet(path)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    raise FileNotFoundError(f"missing enriched master {path} and fallback {fallback}")


def _feature_numeric(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    if series.dtype == bool:
        return series.astype(float)
    if series.dtype == object:
        mapped = series.map(lambda value: 1.0 if value is True else 0.0 if value is False else value)
        return pd.to_numeric(mapped, errors="coerce").astype("float64")
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _median(series: pd.Series) -> float | None:
    return _round_or_none(series.median() if not series.empty else None)


def _iqr(series: pd.Series) -> float | None:
    return _round_or_none((series.quantile(0.75) - series.quantile(0.25)) if len(series) > 1 else None)


def _top_counts(values: Any, limit: int = 10) -> dict[str, int]:
    return dict(Counter(str(value) for value in pd.Series(values).dropna().tolist()).most_common(limit))


def _top_share_pct(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    counts = Counter(str(value) for value in frame[column].dropna().tolist())
    return _pct(counts.most_common(1)[0][1], len(frame)) if counts else 0.0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Creator Net Flow Efficient-Mover Thesis",
        "",
        f"- Classification: `{report['classification']}`",
        f"- Efficient-mover rows analyzed: `{report['efficient_mover_rows_analyzed']}`",
        f"- Expected direction: `{report['frozen_definition'].get('expected_direction')}`",
        f"- Coverage: `{report.get('coverage_audit', {}).get('creator_net_flow_coverage_pct')}`%",
        "- Scope: formal descriptive thesis only; no validation, backtest, optimization, alerts, or execution logic.",
        "",
        "## Primary Result",
        f"- `{report.get('descriptive_results', {}).get('primary_direction_result')}`",
        "",
        "## Robustness",
        f"- `{report.get('robustness_summary')}`",
    ]
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Creator Net Flow Efficient-Mover Thesis Status",
        "",
        "This thesis was created after the efficient-mover continuation anatomy report identified `creator_net_flow_sol_before_20k` as the strongest formal descriptive candidate inside high-FDV-efficiency tokens.",
        "",
        "## Population Definition",
        f"- {report['population_definition']}",
        "",
        "## Frozen Feature And Direction",
        f"- Feature: `{report['frozen_definition'].get('feature')}`",
        f"- Expected direction: `{report['frozen_definition'].get('expected_direction')}`",
        "",
        "## Coverage",
        f"- `{report.get('coverage_audit')}`",
        "",
        "## Descriptive Results",
        f"- `{report.get('descriptive_results')}`",
        "",
        "## Robustness",
        f"- `{report.get('robustness_summary')}`",
        "",
        "## Classification",
        f"- `{report['classification']}`",
        "",
        "## Next Recommendation",
        f"- `{report['next_recommendation']['action']}`",
        "",
        "## Limitations",
    ]
    lines.extend([f"- {item}" for item in report.get("limitations", [])])
    lines.append("")
    return "\n".join(lines)


def _guardrails() -> dict[str, Any]:
    return {
        "thesis_runs": 1,
        "validation_runs": 0,
        "walk_forward_runs": 0,
        "backtests_run": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "trading_logic_added": False,
        "buy_rules_created": False,
        "sell_rules_created": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
        "alerts_created": False,
        "early_buyer_thesis_runs": 0,
        "frp004_runs": 0,
    }


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, default=_json_default).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        if blocked in text:
            raise ValueError(f"unsupported label leaked into report: {blocked}")
    guardrails = report.get("guardrails", {})
    if guardrails.get("validation_runs") or guardrails.get("trading_logic_added") or guardrails.get("early_buyer_thesis_runs") or guardrails.get("frp004_runs"):
        raise ValueError("guardrail violation")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return str(value)
