"""Non-FDV incremental information audit.

Diagnostic-only report that asks whether non-FDV proxy variables add
descriptive separation beyond fixed FDV-efficiency buckets. It does not run a
thesis, validation, backtest, optimization, or trading logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "non_fdv_incremental_information_audit_v0"
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
    "data", "backtests", "diagnostics", "reports", "non_fdv_incremental_information_audit"
)
DEFAULT_STATUS_PATH = Path("theses/NON_FDV_INCREMENTAL_INFORMATION_AUDIT_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
HIGH_100K = {
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
}
HIGH_500K = {"reached_500k_but_never_1m", "reached_1m_plus"}
HIGH_1M = {"reached_1m_plus"}
CONTRASTS = [
    ("100k_plus_vs_sub_100k", HIGH_100K),
    ("500k_plus_vs_sub_500k", HIGH_500K),
    ("1m_plus_vs_sub_1m", HIGH_1M),
    (
        "1m_plus_vs_100k_to_1m",
        HIGH_1M,
        {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m"},
    ),
]

FDV_BASELINE_FEATURES = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "event_count_at_20k",
    "buy_count_at_20k",
    "active_wallets_at_20k",
]

FEATURE_GROUPS = {
    "wallet_buyer_quality": [
        "smart_money_quality_proxy",
        "early_buyer_with_prior_runner_count",
        "early_buyer_with_prior_100k_count",
        "early_buyer_with_prior_500k_count",
        "early_buyer_with_prior_1m_count",
        "early_buyer_prior_failure_count",
        "repeated_buyer_quality_proxy",
    ],
    "funding_creator_funder_structure": [
        "shared_funding_proxy",
        "time_linked_funding_proxy",
        "launches_sharing_funder",
        "creators_sharing_funder",
        "candidate_funder_confidence",
        "common_funder_candidate_id",
    ],
    "top_holder_concentration": [
        "top_holder_share_proxy",
        "top_10_holder_share_proxy",
        "early_holder_concentration",
        "holder_count",
        "holder_retention_proxy",
        "holder_churn_proxy",
    ],
    "synthetic_authenticity": [
        "synthetic_activity_proxy",
        "wash_trade_proxy_share_before_20k",
        "circular_buy_sell_wallet_count",
        "rapid_round_trip_count",
        "bot_sniper_proxy_share",
        "coordinated_timing_proxy",
    ],
    "creator_extraction": [
        "creator_extraction_proxy_before_20k",
        "creator_direct_sell_amount_sol",
        "creator_net_flow_sol_before_20k",
        "creator_linked_wallet_net_flow_sol",
    ],
    "liquidity_executability": [
        "liquidity_depth_proxy",
        "exit_liquidity_proxy",
        "estimated_slippage_10_sol_at_20k",
        "estimated_slippage_25_sol_at_20k",
        "estimated_sell_impact_10_sol_at_20k",
        "estimated_sell_impact_25_sol_at_20k",
    ],
    "contract_metadata_visibility": [
        "mint_authority_status",
        "freeze_authority_status",
        "token_2022_flag",
        "metadata_quality_bucket",
        "aggregator_visibility_proxy",
        "dexscreener_boost_present",
        "dexscreener_paid_order_present",
    ],
}

ENTRY_SIDE_GROUPS = {
    "wallet_buyer_quality",
    "funding_creator_funder_structure",
    "top_holder_concentration",
    "synthetic_authenticity",
    "creator_extraction",
    "contract_metadata_visibility",
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
    "fixed_tertile_buckets_not_tuned",
]


def build_non_fdv_incremental_information_audit(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = _load_master(master_path, jsonl_fallback)
    if "milestone_tier" not in frame.columns:
        raise ValueError("milestone_tier_missing")
    missing_fdv = [feature for feature in FDV_BASELINE_FEATURES[:3] if feature not in frame.columns]
    if missing_fdv:
        raise ValueError(f"fdv_baseline_missing: {missing_fdv}")
    frame = frame[frame["milestone_tier"].isin(TIER_ORDER)].copy().reset_index(drop=True)
    bucketed = build_fdv_baseline_buckets(frame)
    groups = load_feature_groups(bucketed)
    baseline = _fdv_baseline_summary(bucketed)
    rank_rows, cross_tabs = _incremental_audit(bucketed, groups)
    candidates = _candidate_fingerprints(rank_rows)
    report = {
        "report_id": REPORT_ID,
        "report_type": "non_fdv_incremental_information_audit",
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {"master_path": str(master_path), "jsonl_fallback": str(jsonl_fallback)},
        "rows_analyzed": int(len(bucketed)),
        "fdv_baseline_features": FDV_BASELINE_FEATURES,
        "fdv_baseline_summary": baseline,
        "feature_groups": groups,
        "non_fdv_feature_rank": rank_rows,
        "non_fdv_cross_tabs": cross_tabs,
        "candidate_next_fingerprints": candidates,
        "recommendation": _recommendation(rank_rows, candidates),
        "limitations": [
            "FDV/valuation proxy only; true market-cap claims remain blocked.",
            "Diagnostic cross-tabs only; no thesis, validation, backtest, optimization, or trading logic.",
            "Non-FDV features with sparse coverage are classified as data_limited or unavailable.",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, baseline, rank_rows, cross_tabs, candidates, output, Path(status_path))
    return report, paths


def build_fdv_baseline_buckets(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["high_fdv_per_event"] = _high_bucket(result.get("fdv_per_event_at_20k"))
    result["high_fdv_per_buy"] = _high_bucket(result.get("fdv_per_buy_at_20k"))
    result["high_fdv_per_active_wallet"] = _high_bucket(result.get("fdv_per_active_wallet_at_20k"))
    result["low_event_count"] = _low_bucket(result.get("event_count_at_20k"))
    result["low_buy_count"] = _low_bucket(result.get("buy_count_at_20k"))
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


def load_feature_groups(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    groups = {}
    for family, features in FEATURE_GROUPS.items():
        present = [feature for feature in features if feature in frame.columns]
        available = [feature for feature in present if frame[feature].notna().any()]
        groups[family] = {
            "features_requested": features,
            "present": present,
            "available": available,
            "absent": [feature for feature in features if feature not in present],
            "coverage": {
                feature: _coverage_pct(frame[feature]) for feature in present
            },
            "feature_timing": "entry_side" if family in ENTRY_SIDE_GROUPS else "path_or_exit_side",
        }
    return groups


def _fdv_baseline_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for bucket in ["high_fdv_efficiency", "low_medium_fdv_efficiency"]:
        subset = frame[frame["fdv_baseline_bucket"] == bucket]
        rows.append(_rate_row("fdv_baseline_bucket", bucket, subset))
    for contrast in _contrast_specs():
        high = frame[frame["milestone_tier"].isin(contrast["high_tiers"])]
        low = frame[frame["milestone_tier"].isin(contrast["low_tiers"])]
        rows.append(
            {
                "category": "fdv_baseline_separation",
                "bucket": contrast["name"],
                "rows": int(len(frame)),
                "high_fdv_rate_high_group_pct": _pct(int(high["fdv_baseline_high"].sum()), len(high)),
                "high_fdv_rate_low_group_pct": _pct(int(low["fdv_baseline_high"].sum()), len(low)),
                "separation_pct_points": round(_pct(int(high["fdv_baseline_high"].sum()), len(high)) - _pct(int(low["fdv_baseline_high"].sum()), len(low)), 4),
            }
        )
    return rows


def _incremental_audit(frame: pd.DataFrame, groups: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rank_rows = []
    cross_tabs = []
    for family, spec in groups.items():
        for feature in spec["features_requested"]:
            if feature not in frame.columns:
                rank_rows.append(_unavailable_rank_row(family, feature, "unavailable"))
                continue
            series = _feature_numeric(frame[feature])
            coverage = _coverage_pct(series)
            if series.notna().sum() < _minimum_rows(len(frame)):
                rank_rows.append(_unavailable_rank_row(family, feature, "data_limited", coverage=coverage))
                continue
            high_feature = _high_bucket(series)
            if _risk_like(feature, family):
                high_feature = _low_bucket(series)
            frame_feature = frame.copy()
            frame_feature["non_fdv_feature_support"] = high_feature
            rows = _cross_tab_rows(frame_feature, family, feature, spec)
            cross_tabs.extend(rows)
            rank_rows.append(_rank_feature(frame_feature, family, feature, spec, rows, coverage))
    return sorted(rank_rows, key=lambda row: (row["classification_sort"], -abs(row["incremental_separation_pct_points"])), reverse=False), cross_tabs


def _cross_tab_rows(frame: pd.DataFrame, family: str, feature: str, spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for fdv_bucket in ["high_fdv_efficiency", "low_medium_fdv_efficiency"]:
        for feature_bucket, support in [("high_non_fdv_feature", True), ("low_non_fdv_feature", False)]:
            subset = frame[(frame["fdv_baseline_bucket"] == fdv_bucket) & (frame["non_fdv_feature_support"] == support)]
            row = _rate_row("cross_tab", f"{fdv_bucket}+{feature_bucket}", subset)
            row.update(
                {
                    "feature_family": family,
                    "feature": feature,
                    "coverage_pct": _coverage_pct(frame[feature]),
                    "missing_count": int(frame[feature].isna().sum()),
                    "top_date_share_pct": _top_share_pct(subset, "launch_date"),
                    "top_creator_share_pct": _top_share_pct(subset, "creator"),
                    "feature_timing": spec["feature_timing"],
                }
            )
            rows.append(row)
    return rows


def _rank_feature(frame: pd.DataFrame, family: str, feature: str, spec: dict[str, Any], cross_rows: list[dict[str, Any]], coverage: float) -> dict[str, Any]:
    high_fdv_high_feature = next((row for row in cross_rows if row["bucket"] == "high_fdv_efficiency+high_non_fdv_feature"), {})
    high_fdv_low_feature = next((row for row in cross_rows if row["bucket"] == "high_fdv_efficiency+low_non_fdv_feature"), {})
    low_fdv_high_feature = next((row for row in cross_rows if row["bucket"] == "low_medium_fdv_efficiency+high_non_fdv_feature"), {})
    high_fdv_increment = (high_fdv_high_feature.get("500k_plus_rate_pct") or 0) - (high_fdv_low_feature.get("500k_plus_rate_pct") or 0)
    exception_rate = low_fdv_high_feature.get("500k_plus_rate_pct") or 0
    consistency = _contrast_consistency(frame, feature)
    classification = _classify_feature(family, feature, coverage, high_fdv_increment, consistency, spec["feature_timing"])
    return {
        "feature_family": family,
        "feature": feature,
        "coverage_pct": coverage,
        "consistency_across_contrasts": consistency,
        "incremental_separation_pct_points": round(high_fdv_increment, 4),
        "low_medium_fdv_exception_500k_plus_rate_pct": exception_rate,
        "classification": classification,
        "classification_sort": _classification_sort(classification),
        "interpretability": _interpretability(feature, family),
        "entry_side_usability": spec["feature_timing"] == "entry_side",
        "risk_filter_usefulness": _risk_like(feature, family),
        "likely_visible_to_average_traders": family in {"contract_metadata_visibility", "liquidity_executability"},
        "proprietary_or_hidden": family not in {"contract_metadata_visibility", "liquidity_executability"},
        "needs_more_enrichment": coverage < 70,
    }


def _candidate_fingerprints(rank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = [row for row in rank_rows if row["classification"] in {"adds_incremental_information", "possible_risk_filter"}]
    usable = sorted(usable, key=lambda row: abs(row["incremental_separation_pct_points"]), reverse=True)
    candidates = []
    for idx, row in enumerate(usable[:3], start=1):
        candidates.append(
            {
                "fingerprint_id": f"NFDV-{idx:03d}",
                "fingerprint_name": f"FDV efficiency plus {row['feature']} {row['classification']}",
                "fdv_baseline_component": "fixed_high_fdv_efficiency_bucket",
                "non_fdv_incremental_component": row["feature"],
                "feature_family": row["feature_family"],
                "entry_side_or_exit_side": "entry_side" if row["entry_side_usability"] else "path_or_exit_side",
                "why_it_may_matter": "Adds descriptive separation beyond fixed FDV-efficiency buckets." if row["classification"] == "adds_incremental_information" else "May identify weak or noisy rows as a risk-filter proxy.",
                "coverage_pct": row["coverage_pct"],
                "what_would_invalidate_it": "The incremental separation disappears in formal descriptive thesis design or broader cohort checks.",
                "missing_data_to_improve": "higher feature coverage and missing reason repair" if row["needs_more_enrichment"] else "none_before_formal_descriptive_design",
                "ready_for_formal_descriptive_thesis": bool(row["coverage_pct"] >= 50 and row["classification"] == "adds_incremental_information"),
            }
        )
    return candidates


def _recommendation(rank_rows: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    adds = [row for row in rank_rows if row["classification"] == "adds_incremental_information"]
    risk = [row for row in rank_rows if row["classification"] == "possible_risk_filter"]
    if adds:
        next_step = "consider_formal_descriptive_design_for_top_non_fdv_incremental_feature"
    elif risk:
        next_step = "consider_risk_filter_descriptive_design_or_improve_feature_coverage"
    else:
        next_step = "no_non_fdv_incremental_information_found_beyond_fdv_efficiency"
    return {
        "next_step": next_step,
        "features_adding_incremental_information": [row["feature"] for row in adds],
        "risk_filter_candidates": [row["feature"] for row in risk],
        "candidate_fingerprint_count": len(candidates),
        "what_not_to_do_next": "Do not create trading rules, optimize thresholds, run validation, or promote a thesis from this diagnostic audit.",
    }


def _load_master(master_path: Path | str, jsonl_fallback: Path | str) -> pd.DataFrame:
    path = Path(master_path)
    fallback = Path(jsonl_fallback)
    if path.exists():
        return pd.read_parquet(path)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    raise FileNotFoundError(f"missing enriched master {path} and fallback {fallback}")


def _contrast_specs() -> list[dict[str, Any]]:
    specs = []
    for item in CONTRASTS:
        if len(item) == 2:
            name, high_tiers = item
            low_tiers = set(TIER_ORDER) - set(high_tiers)
        else:
            name, high_tiers, low_tiers = item
        specs.append({"name": name, "high_tiers": set(high_tiers), "low_tiers": set(low_tiers)})
    return specs


def _contrast_consistency(frame: pd.DataFrame, feature: str) -> float:
    values = []
    series = _feature_numeric(frame[feature])
    for contrast in _contrast_specs():
        high = series[frame["milestone_tier"].isin(contrast["high_tiers"])].dropna()
        low = series[frame["milestone_tier"].isin(contrast["low_tiers"])].dropna()
        if high.empty or low.empty:
            continue
        values.append(float(high.median()) != float(low.median()))
    return _pct(sum(1 for value in values if value), len(values))


def _classify_feature(family: str, feature: str, coverage: float, increment: float, consistency: float, timing: str) -> str:
    if coverage == 0:
        return "unavailable"
    if coverage < 25:
        return "data_limited"
    if timing != "entry_side":
        return "path_or_exit_side_only"
    if increment >= 5 and consistency >= 50:
        return "adds_incremental_information"
    if _risk_like(feature, family) and increment >= 2:
        return "possible_risk_filter"
    if coverage < 50:
        return "data_limited"
    return "no_incremental_information"


def _unavailable_rank_row(family: str, feature: str, classification: str, *, coverage: float = 0.0) -> dict[str, Any]:
    return {
        "feature_family": family,
        "feature": feature,
        "coverage_pct": coverage,
        "consistency_across_contrasts": 0.0,
        "incremental_separation_pct_points": 0.0,
        "low_medium_fdv_exception_500k_plus_rate_pct": 0.0,
        "classification": classification,
        "classification_sort": _classification_sort(classification),
        "interpretability": "missing_or_sparse",
        "entry_side_usability": family in ENTRY_SIDE_GROUPS,
        "risk_filter_usefulness": _risk_like(feature, family),
        "likely_visible_to_average_traders": False,
        "proprietary_or_hidden": True,
        "needs_more_enrichment": True,
    }


def _classification_sort(classification: str) -> int:
    order = {
        "adds_incremental_information": 0,
        "possible_risk_filter": 1,
        "path_or_exit_side_only": 2,
        "no_incremental_information": 3,
        "data_limited": 4,
        "unavailable": 5,
    }
    return order.get(classification, 9)


def _interpretability(feature: str, family: str) -> str:
    if family == "wallet_buyer_quality":
        return "medium_proxy_based"
    if family == "funding_creator_funder_structure":
        return "medium_structural_proxy"
    if family == "liquidity_executability":
        return "medium_path_side_proxy"
    if family == "contract_metadata_visibility":
        return "high_when_available"
    return "medium"


def _risk_like(feature: str, family: str) -> bool:
    return (
        family in {"synthetic_authenticity", "creator_extraction", "funding_creator_funder_structure"}
        or "failure" in feature
        or "churn" in feature
        or "sell" in feature
    )


def _rate_row(category: str, bucket: str, subset: pd.DataFrame) -> dict[str, Any]:
    return {
        "category": category,
        "bucket": bucket,
        "rows": int(len(subset)),
        "100k_plus_rate_pct": _pct(int(subset["milestone_tier"].isin(HIGH_100K).sum()), len(subset)),
        "500k_plus_rate_pct": _pct(int(subset["milestone_tier"].isin(HIGH_500K).sum()), len(subset)),
        "1m_plus_rate_pct": _pct(int(subset["milestone_tier"].isin(HIGH_1M).sum()), len(subset)),
        "tier_distribution_json": json.dumps(dict(Counter(subset["milestone_tier"].tolist())), sort_keys=True),
    }


def _high_bucket(series: Any) -> pd.Series:
    numeric = _feature_numeric(series)
    threshold = numeric.quantile(2 / 3)
    return numeric >= threshold


def _low_bucket(series: Any) -> pd.Series:
    numeric = _feature_numeric(series)
    threshold = numeric.quantile(1 / 3)
    return numeric <= threshold


def _feature_numeric(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    if series.dtype == bool:
        return series.astype(float)
    if series.dtype == object:
        mapped = series.map(lambda value: 1.0 if value is True else 0.0 if value is False else value)
        return pd.to_numeric(mapped, errors="coerce").astype("float64")
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _coverage_pct(series: pd.Series) -> float:
    return _pct(int(series.notna().sum()), len(series))


def _minimum_rows(total_rows: int) -> int:
    if total_rows < 20:
        return max(1, total_rows // 3)
    return max(20, int(total_rows * 0.05))


def _top_share_pct(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    counts = Counter(str(value) for value in frame[column].dropna().tolist())
    return _pct(counts.most_common(1)[0][1], len(frame)) if counts else 0.0


def _write_outputs(
    report: dict[str, Any],
    baseline_rows: list[dict[str, Any]],
    rank_rows: list[dict[str, Any]],
    cross_tabs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "non_fdv_incremental_information_summary.json",
        "summary_markdown_path": output / "non_fdv_incremental_information_summary.md",
        "fdv_baseline_bucket_summary_path": output / "fdv_baseline_bucket_summary.csv",
        "non_fdv_feature_incremental_rank_path": output / "non_fdv_feature_incremental_rank.csv",
        "non_fdv_cross_tabs_path": output / "non_fdv_cross_tabs.csv",
        "candidate_next_fingerprints_path": output / "candidate_next_fingerprints.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_summary_markdown(report), encoding="utf-8")
    pd.DataFrame(baseline_rows).to_csv(paths["fdv_baseline_bucket_summary_path"], index=False)
    pd.DataFrame(rank_rows).to_csv(paths["non_fdv_feature_incremental_rank_path"], index=False)
    pd.DataFrame(cross_tabs).to_csv(paths["non_fdv_cross_tabs_path"], index=False)
    pd.DataFrame(candidates).to_csv(paths["candidate_next_fingerprints_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Non-FDV Incremental Information Audit",
        "",
        f"- Rows analyzed: `{report['rows_analyzed']}`",
        f"- Recommendation: `{report['recommendation']['next_step']}`",
        "- Scope: diagnostic only; no thesis, validation, backtest, trading logic, or optimization.",
        "",
        "## Features Adding Incremental Information",
    ]
    adds = [row for row in report["non_fdv_feature_rank"] if row["classification"] == "adds_incremental_information"]
    for row in adds[:10]:
        lines.append(f"- `{row['feature']}` ({row['feature_family']}): {row['incremental_separation_pct_points']} pct points")
    if not adds:
        lines.append("- None found under fixed descriptive buckets.")
    lines.extend(["", "## Candidate Next Fingerprints"])
    for row in report["candidate_next_fingerprints"]:
        lines.append(f"- `{row['fingerprint_id']}` {row['fingerprint_name']}")
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    adds = [row for row in report["non_fdv_feature_rank"] if row["classification"] == "adds_incremental_information"]
    risk = [row for row in report["non_fdv_feature_rank"] if row["classification"] == "possible_risk_filter"]
    data_limited = [row for row in report["non_fdv_feature_rank"] if row["classification"] in {"data_limited", "unavailable"}]
    no_info = [row for row in report["non_fdv_feature_rank"] if row["classification"] == "no_incremental_information"]
    lines = [
        "# Non-FDV Incremental Information Audit Status",
        "",
        "This audit was created after FRP-001 showed that visible FDV-efficiency separated strongly while the wallet-quality component was coverage-limited.",
        "",
        f"- Rows analyzed: `{report['rows_analyzed']}`",
        f"- Recommendation: `{report['recommendation']['next_step']}`",
        "",
        "## FDV Baseline Result",
    ]
    for row in report["fdv_baseline_summary"][:6]:
        lines.append(f"- {row.get('bucket')}: `{row}`")
    lines.extend(["", "## Non-FDV Families Audited"])
    for family, spec in report["feature_groups"].items():
        lines.append(f"- {family}: available `{len(spec['available'])}`, absent `{len(spec['absent'])}`")
    lines.extend(["", "## Features Adding Information"])
    lines.extend([f"- {row['feature']} ({row['feature_family']})" for row in adds] or ["- None under fixed descriptive buckets."])
    lines.extend(["", "## Risk-Filter Candidates"])
    lines.extend([f"- {row['feature']} ({row['feature_family']})" for row in risk] or ["- None under fixed descriptive buckets."])
    lines.extend(["", "## Features Without Incremental Information"])
    lines.extend([f"- {row['feature']} ({row['feature_family']})" for row in no_info[:20]] or ["- None."])
    lines.extend(["", "## Data-Limited Fields"])
    lines.extend([f"- {row['feature']} ({row['feature_family']})" for row in data_limited[:30]] or ["- None."])
    lines.extend(["", "## Candidate Next Fingerprints"])
    lines.extend([f"- {row['fingerprint_id']}: {row['fingerprint_name']}" for row in report["candidate_next_fingerprints"]] or ["- None forced."])
    lines.extend(
        [
            "",
            "## What Not To Do Next",
            f"- {report['recommendation']['what_not_to_do_next']}",
            "",
            "No thesis, validation, walk-forward validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, ML, or strategy logic was run.",
            "",
        ]
    )
    return "\n".join(lines)


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
    }


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, default=_json_default).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        if blocked in text:
            raise ValueError(f"unsupported label leaked into report: {blocked}")
    guardrails = report.get("guardrails", {})
    if guardrails.get("thesis_runs") or guardrails.get("validation_runs") or guardrails.get("trading_logic_added"):
        raise ValueError("guardrail violation")


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


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
