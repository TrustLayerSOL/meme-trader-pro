"""Efficient-mover continuation versus trap/collapse anatomy report.

Diagnostic-only report that starts broad inside the high FDV-efficiency
universe. It does not run a thesis, validation, backtest, optimization, alerts,
or execution logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "efficient_mover_continuation_anatomy_v0"
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
    "data", "backtests", "diagnostics", "reports", "efficient_mover_continuation_anatomy"
)
DEFAULT_STATUS_PATH = Path("theses/EFFICIENT_MOVER_CONTINUATION_ANATOMY_STATUS.md")

FDV_BASELINE_FEATURES = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "event_count_at_20k",
    "buy_count_at_20k",
    "active_wallets_at_20k",
]
TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
REACHED_500K = {"reached_500k_but_never_1m", "reached_1m_plus"}
REACHED_1M = {"reached_1m_plus"}
FEATURE_FAMILIES = {
    "synthetic_authenticity": {
        "timing": "entry_side",
        "features": [
            "synthetic_activity_proxy",
            "wash_trade_proxy_share_before_20k",
            "circular_buy_sell_wallet_count",
            "rapid_round_trip_count",
            "bot_sniper_proxy_share",
            "coordinated_timing_proxy",
        ],
    },
    "funding_creator_funder_structure": {
        "timing": "entry_side",
        "features": [
            "shared_funding_proxy",
            "time_linked_funding_proxy",
            "launches_sharing_funder",
            "creators_sharing_funder",
            "candidate_funder_confidence",
            "common_funder_candidate_id",
        ],
    },
    "creator_extraction": {
        "timing": "entry_side",
        "features": [
            "creator_extraction_proxy_before_20k",
            "creator_direct_sell_amount_sol",
            "creator_net_flow_sol_before_20k",
            "creator_linked_wallet_net_flow_sol",
        ],
    },
    "wallet_buyer_quality": {
        "timing": "entry_side",
        "features": [
            "smart_money_quality_proxy",
            "early_buyer_with_prior_runner_count",
            "repeated_buyer_quality_proxy",
            "early_buyer_prior_failure_count",
            "early_buyer_with_prior_100k_count",
            "early_buyer_with_prior_500k_count",
            "early_buyer_with_prior_1m_count",
        ],
    },
    "top_holder_concentration": {
        "timing": "entry_side",
        "features": [
            "top_holder_share_proxy",
            "top_10_holder_share_proxy",
            "early_holder_concentration",
            "holder_retention_proxy",
            "holder_churn_proxy",
            "holder_count",
        ],
    },
    "liquidity_executability": {
        "timing": "path_exit_side",
        "features": [
            "estimated_slippage_10_sol_at_20k",
            "estimated_slippage_25_sol_at_20k",
            "estimated_sell_impact_10_sol_at_20k",
            "estimated_sell_impact_25_sol_at_20k",
            "liquidity_depth_proxy",
            "exit_liquidity_proxy",
        ],
    },
    "metadata_visibility_contract": {
        "timing": "entry_side",
        "features": [
            "aggregator_visibility_proxy",
            "dexscreener_boost_present",
            "dexscreener_paid_order_present",
            "metadata_quality_bucket",
            "mint_authority_status",
            "freeze_authority_status",
            "token_2022_flag",
        ],
    },
    "flow_path_secondary": {
        "timing": "path_exit_side",
        "features": [
            "buy_sell_ratio_at_20k",
            "sell_count_at_20k",
            "active_wallets_at_20k",
            "event_count_at_20k",
            "buy_count_at_20k",
            "time_to_100k_from_20k",
            "time_to_500k_from_20k",
            "time_to_1m_from_20k",
        ],
    },
}
METHODOLOGY_FLAGS = [
    "diagnostic_report_only",
    "not_a_thesis",
    "no_thesis_execution",
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
    "fixed_quantile_fdv_efficiency_universe_not_tuned",
]


def build_efficient_mover_continuation_anatomy(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    master = _load_master(master_path, jsonl_fallback)
    bucketed = label_continuation_paths(build_efficient_mover_universe(master))
    efficient = bucketed[bucketed["fdv_baseline_high"] == True].copy()  # noqa: E712
    feature_rows = compare_feature_families(efficient)
    candidates = build_candidate_filters(feature_rows)
    entry_exit = build_entry_vs_exit_rows(feature_rows)
    report = {
        "report_id": REPORT_ID,
        "report_type": "efficient_mover_continuation_trap_anatomy",
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {"master_path": str(master_path), "jsonl_fallback": str(jsonl_fallback)},
        "rows_loaded": int(len(master)),
        "efficient_mover_universe": summarize_efficient_mover_universe(bucketed),
        "continuation_vs_trap_counts": continuation_counts(efficient),
        "continuation_label_semantics": {
            "primary_continuation_proxy": "reached_1m_plus",
            "primary_trap_or_stall_proxy": "efficient_mover_but_failed_to_reach_1m",
            "secondary_collapse_proxy": "failed_to_reach_500k",
            "true_market_cap_available": False,
            "labels_are_descriptive_not_trade_outcomes": True,
        },
        "feature_families": feature_family_coverage(efficient),
        "feature_comparison": feature_rows,
        "candidate_filters": candidates,
        "entry_vs_exit_features": entry_exit,
        "readiness_classification": classify_readiness(feature_rows, candidates, efficient),
        "recommended_next_action": recommend_next_action(feature_rows, candidates, efficient),
        "limitations": [
            "Efficient-mover universe uses fixed FDV-efficiency quantile-style buckets, not optimized thresholds.",
            "Continuation/trap labels are milestone-tier proxies, not trade outcomes.",
            "Path/drawdown fields are sparse or unavailable and remain marked as missing when absent.",
            "FDV/valuation proxy only; true market-cap claims remain blocked.",
            "No thesis, validation, walk-forward validation, backtest, optimization, alerts, or execution logic was run.",
        ],
    }
    _assert_guardrails(report)
    paths = write_outputs(report, feature_rows, candidates, entry_exit, output, Path(status_path))
    return report, paths


def build_efficient_mover_universe(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    required = [feature for feature in FDV_BASELINE_FEATURES[:3] if feature not in result.columns]
    if required:
        raise ValueError(f"fdv_efficiency_fields_missing: {required}")
    result["high_fdv_per_event"] = _high_bucket(_feature_numeric(result["fdv_per_event_at_20k"]))
    result["high_fdv_per_buy"] = _high_bucket(_feature_numeric(result["fdv_per_buy_at_20k"]))
    result["high_fdv_per_active_wallet"] = _high_bucket(_feature_numeric(result["fdv_per_active_wallet_at_20k"]))
    result["low_event_count"] = _low_bucket(_feature_numeric(result.get("event_count_at_20k")))
    result["low_buy_count"] = _low_bucket(_feature_numeric(result.get("buy_count_at_20k")))
    bucket_cols = [
        "high_fdv_per_event",
        "high_fdv_per_buy",
        "high_fdv_per_active_wallet",
        "low_event_count",
        "low_buy_count",
    ]
    result["fdv_baseline_support_count"] = result[bucket_cols].sum(axis=1)
    result["fdv_baseline_high"] = result["fdv_baseline_support_count"] >= 3
    result["fdv_baseline_bucket"] = result["fdv_baseline_high"].map({True: "high_fdv_efficiency", False: "low_medium_fdv_efficiency"})
    return result


def label_continuation_paths(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    tiers = result.get("milestone_tier", pd.Series(index=result.index, dtype=object)).astype(str)
    result["reached_500k"] = tiers.isin(REACHED_500K).map(lambda value: True if value else False).astype(object)
    result["reached_1m"] = tiers.isin(REACHED_1M).map(lambda value: True if value else False).astype(object)
    result["reached_1m_plus"] = result["reached_1m"]
    result["reached_500k_but_never_1m"] = (tiers == "reached_500k_but_never_1m").map(lambda value: True if value else False).astype(object)
    result["failed_to_reach_500k"] = (~tiers.isin(REACHED_500K)).map(lambda value: True if value else False).astype(object)
    result["failed_to_reach_1m"] = (~tiers.isin(REACHED_1M)).map(lambda value: True if value else False).astype(object)
    result["clean_continuation_proxy"] = result["reached_1m"]
    result["trap_or_stall_proxy"] = result["failed_to_reach_1m"]
    result["collapse_proxy"] = result["failed_to_reach_500k"]
    return result


def compare_feature_families(efficient: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if efficient.empty:
        return rows
    continuation = efficient[efficient["clean_continuation_proxy"] == True]  # noqa: E712
    trap = efficient[efficient["trap_or_stall_proxy"] == True]  # noqa: E712
    for family, spec in FEATURE_FAMILIES.items():
        for feature in spec["features"]:
            if feature not in efficient.columns:
                rows.append(_unavailable_feature_row(efficient, family, feature, spec["timing"], "unavailable"))
                continue
            series = _feature_numeric(efficient[feature])
            coverage = _coverage_pct(series)
            if series.notna().sum() < max(3, int(len(efficient) * 0.05)):
                rows.append(_unavailable_feature_row(efficient, family, feature, spec["timing"], "data_limited", coverage=coverage, missing_count=int(series.isna().sum())))
                continue
            cont_values = _feature_numeric(continuation.get(feature, pd.Series(dtype=object))).dropna()
            trap_values = _feature_numeric(trap.get(feature, pd.Series(dtype=object))).dropna()
            cont_median = _median(cont_values)
            trap_median = _median(trap_values)
            effect = _effect_size(cont_values, trap_values)
            direction = _direction(cont_median, trap_median)
            row = {
                "feature_family": family,
                "feature": feature,
                "feature_timing": spec["timing"],
                "coverage_pct": coverage,
                "missing_count": int(series.isna().sum()),
                "continuation_rows": int(cont_values.shape[0]),
                "trap_rows": int(trap_values.shape[0]),
                "continuation_median": cont_median,
                "trap_median": trap_median,
                "continuation_iqr": _iqr(cont_values),
                "trap_iqr": _iqr(trap_values),
                "direction": direction,
                "higher_values_associated_with": _associated_group(cont_median, trap_median),
                "effect_size_proxy": effect,
                "top_date_concentration_pct": _top_share_pct(efficient[series.notna()], "launch_date"),
                "top_creator_concentration_pct": _top_share_pct(efficient[series.notna()], "creator"),
                "entry_side_observable": spec["timing"] == "entry_side",
            }
            row["classification"] = classify_feature_row(row)
            row["interpretation"] = _interpretation(row)
            rows.append(row)
    return sorted(rows, key=lambda row: (_classification_sort(row["classification"]), -abs(row.get("effect_size_proxy") or 0), row["feature_family"], row["feature"]))


def classify_feature_row(row: dict[str, Any]) -> str:
    if row.get("coverage_pct", 0) < 25 or row.get("continuation_rows", 0) < 3 or row.get("trap_rows", 0) < 3:
        return "data_limited"
    if row.get("higher_values_associated_with") == "flat" or abs(row.get("effect_size_proxy") or 0) < 0.1:
        return "no_clear_separation"
    if row.get("top_date_concentration_pct", 0) >= 60 or row.get("top_creator_concentration_pct", 0) >= 60:
        return "data_limited"
    if row.get("feature_timing") == "path_exit_side":
        return "path_exit_candidate"
    associated = row.get("higher_values_associated_with")
    if associated == "continuation_proxy":
        return "continuation_positive_candidate"
    if associated == "trap_proxy":
        return "trap_risk_filter_candidate"
    return "no_clear_separation"


def build_candidate_filters(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = [
        row
        for row in feature_rows
        if row["classification"] in {"continuation_positive_candidate", "trap_risk_filter_candidate", "path_exit_candidate"}
    ]
    usable = sorted(usable, key=lambda row: (_classification_sort(row["classification"]), -abs(row.get("effect_size_proxy") or 0)))
    candidates = []
    for idx, row in enumerate(usable[:8], start=1):
        candidates.append(
            {
                "candidate_id": f"EMC-{idx:03d}",
                "name": _candidate_name(row),
                "feature_family": row["feature_family"],
                "feature": row["feature"],
                "entry_side_path_side_exit_side": row["feature_timing"],
                "classification": row["classification"],
                "why_it_may_matter": row["interpretation"],
                "coverage_pct": row["coverage_pct"],
                "effect_size_proxy": row["effect_size_proxy"],
                "what_would_invalidate_it": "The separation disappears in a formal descriptive design or is explained by date/creator concentration.",
                "missing_data_needed": "higher coverage or direct path/drawdown labels" if row["coverage_pct"] < 70 or row["feature_timing"] != "entry_side" else "none_before_formal_descriptive_design",
                "formal_descriptive_thesis_justified": bool(
                    row["classification"] in {"continuation_positive_candidate", "trap_risk_filter_candidate"}
                    and row["coverage_pct"] >= 50
                    and row["top_date_concentration_pct"] < 60
                    and row["top_creator_concentration_pct"] < 60
                ),
            }
        )
    return candidates


def build_entry_vs_exit_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for timing in ["entry_side", "path_exit_side"]:
        subset = [row for row in feature_rows if row["feature_timing"] == timing]
        rows.append(
            {
                "feature_timing": timing,
                "features": len(subset),
                "continuation_positive_candidates": sum(row["classification"] == "continuation_positive_candidate" for row in subset),
                "trap_risk_filter_candidates": sum(row["classification"] == "trap_risk_filter_candidate" for row in subset),
                "path_exit_candidates": sum(row["classification"] == "path_exit_candidate" for row in subset),
                "data_limited": sum(row["classification"] == "data_limited" for row in subset),
                "unavailable": sum(row["classification"] == "unavailable" for row in subset),
                "no_clear_separation": sum(row["classification"] == "no_clear_separation" for row in subset),
            }
        )
    return rows


def summarize_efficient_mover_universe(bucketed: pd.DataFrame) -> dict[str, Any]:
    efficient = bucketed[bucketed["fdv_baseline_high"] == True]  # noqa: E712
    return {
        "definition": "fixed high FDV-efficiency support_count >= 3 from non-optimized quantile buckets",
        "rows": int(len(efficient)),
        "coverage_pct": _pct(len(efficient), len(bucketed)),
        "tier_distribution": dict(Counter(efficient.get("milestone_tier", pd.Series(dtype=object)).dropna().astype(str).tolist())),
        "date_distribution_top10": dict(Counter(efficient.get("launch_date", pd.Series(dtype=object)).dropna().astype(str).tolist()).most_common(10)),
        "creator_distribution_top10": dict(Counter(efficient.get("creator", pd.Series(dtype=object)).dropna().astype(str).tolist()).most_common(10)),
        "fdv_efficiency_fields": FDV_BASELINE_FEATURES,
    }


def continuation_counts(efficient: pd.DataFrame) -> dict[str, Any]:
    return {
        "efficient_mover_rows": int(len(efficient)),
        "continuation_rows": int((efficient["clean_continuation_proxy"] == True).sum()),  # noqa: E712
        "trap_or_stall_rows": int((efficient["trap_or_stall_proxy"] == True).sum()),  # noqa: E712
        "failed_to_reach_500k_rows": int((efficient["failed_to_reach_500k"] == True).sum()),  # noqa: E712
        "reached_500k_but_never_1m_rows": int((efficient["reached_500k_but_never_1m"] == True).sum()),  # noqa: E712
    }


def feature_family_coverage(efficient: pd.DataFrame) -> dict[str, Any]:
    result = {}
    for family, spec in FEATURE_FAMILIES.items():
        present = [feature for feature in spec["features"] if feature in efficient.columns]
        result[family] = {
            "feature_timing": spec["timing"],
            "features_requested": spec["features"],
            "present": present,
            "absent": [feature for feature in spec["features"] if feature not in present],
            "coverage": {
                feature: _coverage_pct(_feature_numeric(efficient[feature])) for feature in present
            },
        }
    return result


def classify_readiness(feature_rows: list[dict[str, Any]], candidates: list[dict[str, Any]], efficient: pd.DataFrame) -> str:
    formal_ready = [candidate for candidate in candidates if candidate["formal_descriptive_thesis_justified"]]
    path_candidates = [row for row in feature_rows if row["classification"] == "path_exit_candidate"]
    data_limited = [row for row in feature_rows if row["classification"] == "data_limited"]
    counts = continuation_counts(efficient)
    if counts["continuation_rows"] < 20 or counts["trap_or_stall_rows"] < 20:
        return "efficient_mover_anatomy_inconclusive"
    if formal_ready:
        return "efficient_mover_anatomy_ready_for_filter_thesis"
    if path_candidates:
        return "efficient_mover_anatomy_ready_for_exit_path_report"
    if len(data_limited) > len(feature_rows) * 0.5:
        return "efficient_mover_anatomy_needs_more_enrichment"
    return "efficient_mover_anatomy_inconclusive"


def recommend_next_action(feature_rows: list[dict[str, Any]], candidates: list[dict[str, Any]], efficient: pd.DataFrame) -> dict[str, Any]:
    readiness = classify_readiness(feature_rows, candidates, efficient)
    formal_ready = [candidate for candidate in candidates if candidate["formal_descriptive_thesis_justified"]]
    if readiness == "efficient_mover_anatomy_ready_for_filter_thesis" and formal_ready:
        choice = "A"
        action = "run_formal_descriptive_thesis_for_best_risk_or_continuation_filter_candidate"
    elif readiness == "efficient_mover_anatomy_ready_for_exit_path_report":
        choice = "B"
        action = "run_path_drawdown_recovery_vs_collapse_report_inside_efficient_movers"
    elif readiness == "efficient_mover_anatomy_needs_more_enrichment":
        choice = "C"
        action = "improve_coverage_for_sparse_feature_families_first"
    else:
        choice = "E"
        action = "stop_and_manually_review_efficient_mover_anatomy"
    return {
        "choice": choice,
        "action": action,
        "do_not_execute_in_this_sprint": True,
        "what_not_to_do_next": "Do not create rules, optimize thresholds, run validation, or promote a thesis from this diagnostic report.",
    }


def write_outputs(
    report: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    entry_exit: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "efficient_mover_continuation_anatomy_summary.json",
        "summary_markdown_path": output / "efficient_mover_continuation_anatomy_summary.md",
        "feature_comparison_path": output / "efficient_mover_feature_comparison.csv",
        "candidate_filters_path": output / "efficient_mover_candidate_filters.csv",
        "entry_vs_exit_features_path": output / "efficient_mover_entry_vs_exit_features.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_summary_markdown(report), encoding="utf-8")
    pd.DataFrame(feature_rows).to_csv(paths["feature_comparison_path"], index=False)
    pd.DataFrame(candidates).to_csv(paths["candidate_filters_path"], index=False)
    pd.DataFrame(entry_exit).to_csv(paths["entry_vs_exit_features_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Efficient-Mover Continuation Anatomy",
        "",
        f"- Efficient-mover rows: `{report['efficient_mover_universe']['rows']}`",
        f"- Classification: `{report['readiness_classification']}`",
        f"- Recommended next action: `{report['recommended_next_action']['choice']} - {report['recommended_next_action']['action']}`",
        "- Scope: broad descriptive diagnostic only; no thesis, validation, backtest, optimization, alerts, or execution logic.",
        "",
        "## Continuation vs Trap/Stall Counts",
        f"- Continuation proxy rows: `{report['continuation_vs_trap_counts']['continuation_rows']}`",
        f"- Trap/stall proxy rows: `{report['continuation_vs_trap_counts']['trap_or_stall_rows']}`",
        f"- Failed-to-500k collapse proxy rows: `{report['continuation_vs_trap_counts']['failed_to_reach_500k_rows']}`",
        "",
        "## Candidate Filters",
    ]
    for candidate in report["candidate_filters"][:10]:
        lines.append(f"- `{candidate['candidate_id']}` {candidate['name']} ({candidate['classification']})")
    if not report["candidate_filters"]:
        lines.append("- None supported strongly enough by this broad diagnostic.")
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    rows = report["feature_comparison"]
    continuation = [row for row in rows if row["classification"] == "continuation_positive_candidate"]
    risk = [row for row in rows if row["classification"] == "trap_risk_filter_candidate"]
    path = [row for row in rows if row["classification"] == "path_exit_candidate"]
    limited = [row for row in rows if row["classification"] in {"data_limited", "unavailable"}]
    lines = [
        "# Efficient-Mover Continuation Anatomy Status",
        "",
        "This report was created to start broad inside the high FDV-efficiency universe and identify descriptive continuation, trap/stall, or path-side separators without testing a predetermined filter.",
        "",
        "## Efficient-Mover Universe Definition",
        f"- {report['efficient_mover_universe']['definition']}",
        f"- Rows: `{report['efficient_mover_universe']['rows']}`",
        f"- Tier distribution: `{report['efficient_mover_universe']['tier_distribution']}`",
        "",
        "## Continuation vs Trap Labels",
        f"- Primary continuation proxy: `{report['continuation_label_semantics']['primary_continuation_proxy']}`",
        f"- Primary trap/stall proxy: `{report['continuation_label_semantics']['primary_trap_or_stall_proxy']}`",
        f"- Secondary collapse proxy: `{report['continuation_label_semantics']['secondary_collapse_proxy']}`",
        f"- Counts: `{report['continuation_vs_trap_counts']}`",
        "",
        "## Strongest Continuation-Positive Candidates",
    ]
    lines.extend([f"- {row['feature']} ({row['feature_family']}): effect `{row['effect_size_proxy']}`" for row in continuation[:10]] or ["- None with sufficient broad support."])
    lines.extend(["", "## Strongest Risk-Filter Candidates"])
    lines.extend([f"- {row['feature']} ({row['feature_family']}): effect `{row['effect_size_proxy']}`" for row in risk[:10]] or ["- None with sufficient broad support."])
    lines.extend(["", "## Path/Exit Candidates"])
    lines.extend([f"- {row['feature']} ({row['feature_family']}): effect `{row['effect_size_proxy']}`" for row in path[:10]] or ["- None with sufficient broad support."])
    lines.extend(["", "## Data-Limited Fields"])
    lines.extend([f"- {row['feature']} ({row['feature_family']})" for row in limited[:30]] or ["- None."])
    lines.extend(
        [
            "",
            "## Recommended Next Action",
            f"- `{report['recommended_next_action']['choice']} - {report['recommended_next_action']['action']}`",
            "",
            "## Limitations",
        ]
    )
    lines.extend([f"- {item}" for item in report["limitations"]])
    lines.append("")
    return "\n".join(lines)


def _candidate_name(row: dict[str, Any]) -> str:
    prefix = "efficient mover"
    if row["classification"] == "continuation_positive_candidate":
        return f"{prefix} + stronger {row['feature']}"
    if row["classification"] == "trap_risk_filter_candidate":
        return f"{prefix} + lower-risk {row['feature']}"
    return f"{prefix} + path-side {row['feature']}"


def _interpretation(row: dict[str, Any]) -> str:
    associated = row["higher_values_associated_with"]
    if row["classification"] == "path_exit_candidate":
        return "Path-side or exit-side proxy separates continuation versus stall groups but may not be known early enough."
    if associated == "continuation_proxy":
        return "Higher values are descriptively associated with stronger continuation proxy rows inside efficient movers."
    if associated == "trap_proxy":
        return "Higher values are descriptively associated with stall/trap proxy rows inside efficient movers."
    return "No clear descriptive separation in this broad diagnostic."


def _unavailable_feature_row(
    efficient: pd.DataFrame,
    family: str,
    feature: str,
    timing: str,
    classification: str,
    *,
    coverage: float = 0.0,
    missing_count: int | None = None,
) -> dict[str, Any]:
    return {
        "feature_family": family,
        "feature": feature,
        "feature_timing": timing,
        "coverage_pct": coverage,
        "missing_count": int(len(efficient) if missing_count is None else missing_count),
        "continuation_rows": 0,
        "trap_rows": 0,
        "continuation_median": None,
        "trap_median": None,
        "continuation_iqr": None,
        "trap_iqr": None,
        "direction": "unavailable",
        "higher_values_associated_with": "unknown",
        "effect_size_proxy": 0.0,
        "top_date_concentration_pct": 0.0,
        "top_creator_concentration_pct": 0.0,
        "entry_side_observable": timing == "entry_side",
        "classification": classification,
        "interpretation": "Feature is unavailable or too sparse for this broad diagnostic.",
    }


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


def _high_bucket(series: pd.Series) -> pd.Series:
    threshold = series.quantile(2 / 3)
    return series >= threshold


def _low_bucket(series: pd.Series) -> pd.Series:
    threshold = series.quantile(1 / 3)
    return series <= threshold


def _coverage_pct(series: pd.Series) -> float:
    return _pct(int(series.notna().sum()), len(series))


def _median(series: pd.Series) -> float | None:
    return _round_or_none(series.median() if not series.empty else None)


def _iqr(series: pd.Series) -> float | None:
    return _round_or_none((series.quantile(0.75) - series.quantile(0.25)) if len(series) > 1 else None)


def _effect_size(continuation: pd.Series, trap: pd.Series) -> float:
    if continuation.empty or trap.empty:
        return 0.0
    pooled_iqr = pd.concat([continuation, trap]).quantile(0.75) - pd.concat([continuation, trap]).quantile(0.25)
    raw = float(continuation.median() - trap.median())
    if abs(raw) < 1e-12:
        return 0.0
    if pooled_iqr and not pd.isna(pooled_iqr):
        return round(raw / float(pooled_iqr), 4)
    return round(raw, 4)


def _direction(continuation_median: float | None, trap_median: float | None) -> str:
    if continuation_median is None or trap_median is None:
        return "unknown"
    if continuation_median > trap_median:
        return "higher_in_continuation_proxy"
    if continuation_median < trap_median:
        return "higher_in_trap_proxy"
    return "flat"


def _associated_group(continuation_median: float | None, trap_median: float | None) -> str:
    if continuation_median is None or trap_median is None:
        return "unknown"
    if continuation_median > trap_median:
        return "continuation_proxy"
    if trap_median > continuation_median:
        return "trap_proxy"
    return "flat"


def _top_share_pct(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    counts = Counter(str(value) for value in frame[column].dropna().tolist())
    return _pct(counts.most_common(1)[0][1], len(frame)) if counts else 0.0


def _classification_sort(classification: str) -> int:
    order = {
        "continuation_positive_candidate": 0,
        "trap_risk_filter_candidate": 1,
        "path_exit_candidate": 2,
        "no_clear_separation": 3,
        "data_limited": 4,
        "unavailable": 5,
    }
    return order.get(classification, 9)


def _round_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


def _guardrails() -> dict[str, Any]:
    return {
        "thesis_runs": 0,
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
    }


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, default=_json_default).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        if blocked in text:
            raise ValueError(f"unsupported label leaked into report: {blocked}")
    guardrails = report.get("guardrails", {})
    if guardrails.get("thesis_runs") or guardrails.get("validation_runs") or guardrails.get("trading_logic_added"):
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
