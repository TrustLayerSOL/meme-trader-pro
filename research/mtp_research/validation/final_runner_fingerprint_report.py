"""Final broad descriptive runner-fingerprint report.

This module is descriptive only. It compares replay-safe enriched proxy fields
across FDV-proxy milestone tiers and writes candidate fingerprint ideas for
future formal thesis design. It does not validate, backtest, optimize, or
generate trading rules.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "final_runner_fingerprint_report_v0"
READINESS_READY = "final_fingerprint_ready_for_formal_thesis_selection"
READINESS_NEEDS_LAYER = "final_fingerprint_needs_specific_missing_layer"
READINESS_INCONCLUSIVE = "final_fingerprint_inconclusive"

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
    "data", "backtests", "diagnostics", "reports", "final_runner_fingerprint"
)
DEFAULT_STATUS_PATH = Path("theses/FINAL_RUNNER_FINGERPRINT_REPORT_STATUS.md")

TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
CONTRASTS = [
    ("sub_100k_vs_100k_plus", {"reached_20k_but_never_50k", "reached_50k_but_never_100k"}, {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}),
    ("sub_500k_vs_500k_plus", {"reached_20k_but_never_50k", "reached_50k_but_never_100k", "reached_100k_but_never_200k", "reached_200k_but_never_500k"}, {"reached_500k_but_never_1m", "reached_1m_plus"}),
    ("sub_1m_vs_1m_plus", {"reached_20k_but_never_50k", "reached_50k_but_never_100k", "reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m"}, {"reached_1m_plus"}),
    ("100k_only_vs_500k_plus", {"reached_100k_but_never_200k"}, {"reached_500k_but_never_1m", "reached_1m_plus"}),
    ("500k_not_1m_vs_1m_plus", {"reached_500k_but_never_1m"}, {"reached_1m_plus"}),
]
MILESTONE_LEVEL = {
    "reached_20k_but_never_50k": 20_000,
    "reached_50k_but_never_100k": 50_000,
    "reached_100k_but_never_200k": 100_000,
    "reached_200k_but_never_500k": 200_000,
    "reached_500k_but_never_1m": 500_000,
    "reached_1m_plus": 1_000_000,
}

METHODOLOGY_FLAGS = [
    "descriptive_fingerprint_report_only",
    "not_a_thesis",
    "no_thesis_promotion",
    "no_validation_run",
    "no_backtest",
    "no_walk_forward_validation",
    "no_live_trading",
    "no_paper_trading",
    "no_auto_buy_sell",
    "no_wallet_execution",
    "no_order_routing",
    "no_alerts",
    "no_buy_rules",
    "no_sell_rules",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
]


FEATURE_FAMILIES: dict[str, dict[str, Any]] = {
    "visible_fdv_flow": {
        "label": "Visible FDV / flow",
        "timing": "entry_side",
        "features": [
            "fdv_per_event_at_20k",
            "fdv_per_buy_at_20k",
            "fdv_per_active_wallet_at_20k",
            "event_count_at_20k",
            "buy_count_at_20k",
            "sell_count_at_20k",
            "active_wallets_at_20k",
            "buy_sell_ratio_at_20k",
            "first_minute_usd_volume",
            "first_60s_buy_count",
            "first_60s_unique_buyers",
            "whale_buy_sequence_proxy",
            "pair_migration_liquidity_delay_proxy",
        ],
    },
    "holder_concentration": {
        "label": "Holder / concentration",
        "timing": "entry_side",
        "features": [
            "holder_count_at_20k",
            "holder_count_proxy",
            "top_holder_share_proxy",
            "top_10_holder_share_proxy",
            "creator_holder_share_proxy",
            "early_holder_concentration",
            "holder_retention_proxy",
            "holder_churn_proxy",
            "top_holder_behavior_proxy_available",
        ],
    },
    "wallet_quality_repeated_buyers": {
        "label": "Wallet quality / repeated buyers",
        "timing": "entry_side",
        "features": [
            "smart_money_quality_proxy",
            "early_buyer_wallet_count",
            "early_buyer_with_prior_runner_count",
            "early_buyer_with_prior_100k_count",
            "early_buyer_with_prior_500k_count",
            "early_buyer_with_prior_1m_count",
            "early_buyer_prior_failure_count",
            "repeated_buyer_quality_proxy",
            "smart_money_wallet_share_before_20k",
            "smart_money_failure_history_share",
        ],
    },
    "creator_deployer": {
        "label": "Creator / deployer",
        "timing": "entry_side",
        "features": [
            "creator_prior_migration_or_graduation_count",
            "deployer_prior_migration_count",
            "creator_extraction_proxy_before_20k",
            "creator_direct_sell_amount_sol",
            "creator_direct_buy_amount_sol",
            "creator_realized_pnl_proxy",
            "creator_wallet_relation_proxy_count",
            "creator_linked_share_proxy",
        ],
    },
    "funding_structure": {
        "label": "Funding structure",
        "timing": "entry_side",
        "features": [
            "candidate_funder_available",
            "shared_funding_proxy",
            "time_linked_funding_proxy",
            "launches_sharing_funder",
            "creators_sharing_funder",
            "repeated_funder_flag",
            "creator_funder_reuse_count",
            "funding_age_seconds",
            "funding_amount_sol",
        ],
    },
    "liquidity_executability": {
        "label": "Liquidity / executability",
        "timing": "path_side",
        "features": [
            "liquidity_sol_proxy_at_20k",
            "liquidity_token_proxy_at_20k",
            "exit_liquidity_proxy_at_20k",
            "estimated_slippage_10_sol_at_20k",
            "estimated_slippage_25_sol_at_20k",
            "estimated_sell_impact_10_sol_at_20k",
            "liquidity_growth_20k_to_100k",
            "liquidity_drop_before_collapse",
        ],
    },
    "synthetic_activity_authenticity": {
        "label": "Synthetic activity / authenticity",
        "timing": "entry_side",
        "features": [
            "synthetic_activity_proxy",
            "wash_trade_proxy_share_before_20k",
            "wash_trade_proxy_count_before_20k",
            "same_wallet_round_trip_count",
            "rapid_round_trip_count",
            "matched_size_round_trip_count",
            "circularity_proxy",
            "churn_proxy",
            "synchronized_participation_proxy",
        ],
    },
    "bot_sniper_timing": {
        "label": "Bot/sniper/coordinated timing",
        "timing": "entry_side",
        "features": [
            "bot_sniper_proxy_share",
            "first_5_buyer_share",
            "first_10_buyer_share",
            "first_20_buyer_share",
            "first_10s_buyer_share",
            "first_30s_buyer_share",
            "same_slot_buy_count",
            "same_second_buy_count",
            "coordinated_timing_proxy",
            "bundle_proxy_share",
        ],
    },
    "contract_authority": {
        "label": "Contract / authority",
        "timing": "entry_side",
        "features": [
            "contract_authority_context_available",
            "mint_authority_known",
            "freeze_authority_known",
            "decimals",
            "supply",
            "true_market_cap_available",
        ],
    },
    "metadata_visibility": {
        "label": "Metadata / visibility",
        "timing": "path_side",
        "features": [
            "metadata_available",
            "metadata_completeness_score",
            "profile_complete_flag",
            "website_present",
            "twitter_present",
            "telegram_present",
            "social_link_count",
            "pair_visible_on_dexscreener",
            "dexscreener_profile_present",
            "visibility_lag_from_launch",
            "aggregator_visibility_proxy",
            "topicality_flag",
        ],
    },
}

MISSING_LAYER_REVIEW = [
    {
        "missing_layer": "LP control / LP ownership",
        "status": "blocked",
        "why_it_matters": "Could separate durable pool control from removable or concentrated LP structures.",
        "worth_pursuing_before_formal_selection": "yes_if_lp_specific_fingerprint_is_selected",
        "can_ignore_for_now": "yes_for_non_lp_candidate_fingerprints",
        "best_source": "historical LP-token account state and pool authority transactions",
    },
    {
        "missing_layer": "Priority fee / compute-budget contention",
        "status": "blocked",
        "why_it_matters": "Could distinguish contested launches and high-speed entry pressure from ordinary flow.",
        "worth_pursuing_before_formal_selection": "no",
        "can_ignore_for_now": "yes",
        "best_source": "raw transactions with fee and compute-budget instruction extraction",
    },
    {
        "missing_layer": "True market cap",
        "status": "blocked",
        "why_it_matters": "Would validate whether FDV-proxy outcomes map to real diluted supply/value.",
        "worth_pursuing_before_formal_selection": "yes_before_any_market_cap_claim",
        "can_ignore_for_now": "yes_for_fdv_proxy_descriptive_work",
        "best_source": "historical supply/burn-aware supply snapshots plus price source",
    },
    {
        "missing_layer": "Confirmed full-chain historical holder state",
        "status": "partial",
        "why_it_matters": "Observed replay holder state can miss holders not observed in the local event stream.",
        "worth_pursuing_before_formal_selection": "yes_for_holder_concentration_thesis",
        "can_ignore_for_now": "yes_for_non_holder_first_pass",
        "best_source": "historical token account owner balance snapshots or replay from complete transfer history",
    },
    {
        "missing_layer": "Visibility / social / topicality",
        "status": "sparse",
        "why_it_matters": "Can help distinguish externally visible attention from purely on-chain mechanics.",
        "worth_pursuing_before_formal_selection": "no",
        "can_ignore_for_now": "yes",
        "best_source": "DexScreener profile/pair cache, token metadata, social metadata snapshots",
    },
    {
        "missing_layer": "Jito bundle truth",
        "status": "blocked",
        "why_it_matters": "Could confirm or reject bundle/coordinated-entry proxies.",
        "worth_pursuing_before_formal_selection": "no",
        "can_ignore_for_now": "yes",
        "best_source": "bundle-aware archival source or transaction-level bundle attribution",
    },
]


def load_enriched_master(path: Path | str = DEFAULT_MASTER_PATH, *, jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH) -> pd.DataFrame:
    parquet = Path(path)
    fallback = Path(jsonl_fallback)
    if parquet.exists():
        return pd.read_parquet(parquet)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    raise FileNotFoundError(f"missing enriched master: {parquet} and fallback {fallback}")


def build_feature_family_inventory(frame: pd.DataFrame) -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    for family, spec in FEATURE_FAMILIES.items():
        available = [feature for feature in spec["features"] if feature in frame.columns and frame[feature].notna().any()]
        present = [feature for feature in spec["features"] if feature in frame.columns]
        inventory[family] = {
            "label": spec["label"],
            "timing": spec["timing"],
            "present_features": present,
            "available_features": available,
            "missing_features": [feature for feature in spec["features"] if feature not in present],
            "coverage_summary": {
                feature: _coverage_pct(frame[feature]) for feature in present
            },
            "interpretation_status": "sparse_do_not_overinterpret" if family == "metadata_visibility" and len(available) < 3 else "available",
        }
    inventory["unavailable_layers"] = {
        "lp_control": {"status": "unavailable", "reason": "lp ownership/control fields have zero usable coverage"},
        "priority_fee_contention": {"status": "unavailable", "reason": "priority fee and compute-budget fields have zero usable coverage"},
        "true_market_cap": {"status": "unavailable", "reason": "true market cap remains blocked; use FDV-proxy only"},
    }
    return inventory


def build_final_runner_fingerprint_report(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame = load_enriched_master(master_path, jsonl_fallback=jsonl_fallback)
    frame = frame[frame["milestone_tier"].isin(TIER_ORDER)].copy()
    inventory = build_feature_family_inventory(frame)
    tier_counts = _tier_counts(frame)
    field_coverage = _field_coverage(frame)
    missing_reasons = _missing_reason_counts(frame)
    tier_comparison = _tier_comparison(frame, inventory)
    entry_exit = _entry_exit_features(tier_comparison)
    commonalities = _strongest_commonalities(tier_comparison)
    candidate_fingerprints = _candidate_fingerprints(tier_comparison, inventory)
    missing_layers = MISSING_LAYER_REVIEW
    readiness = _readiness(frame, candidate_fingerprints)
    recommendation = _recommendation(readiness, candidate_fingerprints, missing_layers)
    report = {
        "report_id": REPORT_ID,
        "readiness_classification": readiness,
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "dataset": {
            "master_path": str(master_path),
            "jsonl_fallback": str(jsonl_fallback),
            "rows_analyzed": int(len(frame)),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "milestone_tier_counts": tier_counts,
        "field_coverage": field_coverage,
        "missing_reason_counts": missing_reasons,
        "feature_family_inventory": inventory,
        "layer_coverage_summary": _layer_coverage_summary(frame),
        "strongest_broad_commonalities": commonalities,
        "candidate_fingerprints": candidate_fingerprints,
        "missing_layer_review": missing_layers,
        "recommendation": recommendation,
        "limitations": _limitations(frame, inventory),
    }
    paths = _write_outputs(report, tier_comparison, candidate_fingerprints, entry_exit, missing_layers, output, Path(status_path))
    return report, paths


def _tier_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = frame["milestone_tier"].value_counts(dropna=False).to_dict()
    return {tier: int(counts.get(tier, 0)) for tier in TIER_ORDER}


def _field_coverage(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        column: {"covered_rows": int(frame[column].notna().sum()), "total_rows": int(len(frame)), "coverage_pct": _coverage_pct(frame[column])}
        for column in frame.columns
    }


def _missing_reason_counts(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    result = {}
    for column in [col for col in frame.columns if "missing_reason" in col]:
        values = [str(value) if _present(value) else "none" for value in frame[column].tolist()]
        result[column] = dict(Counter(values))
    return result


def _layer_coverage_summary(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    layer_flags = [col for col in frame.columns if col.startswith("has_") and col.endswith("_layer")]
    summary = {}
    for flag in sorted(layer_flags):
        covered = int(frame[flag].fillna(False).astype(bool).sum())
        summary[flag] = {"covered_rows": covered, "total_rows": int(len(frame)), "coverage_pct": round(covered / len(frame) * 100, 4) if len(frame) else 0.0}
    return summary


def _tier_comparison(frame: pd.DataFrame, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    numeric = frame.copy()
    for family, spec in inventory.items():
        if family == "unavailable_layers":
            continue
        for feature in spec["present_features"]:
            series = _numeric_series(numeric[feature])
            if series.notna().sum() == 0:
                continue
            tier_medians = {
                tier: _median(series[numeric["milestone_tier"] == tier])
                for tier in TIER_ORDER
            }
            directions = []
            for contrast, lower_tiers, higher_tiers in CONTRASTS:
                lower = _numeric_series(series[numeric["milestone_tier"].isin(lower_tiers)]).dropna()
                higher = _numeric_series(series[numeric["milestone_tier"].isin(higher_tiers)]).dropna()
                lower_median = _median(lower)
                higher_median = _median(higher)
                direction = _direction(lower_median, higher_median)
                if direction != "flat_or_unknown":
                    directions.append(direction)
                rows.append(
                    {
                        "feature_family": family,
                        "feature_family_label": spec["label"],
                        "feature": feature,
                        "contrast": contrast,
                        "coverage_count": int(series.notna().sum()),
                        "total_rows": int(len(frame)),
                        "coverage_pct": _coverage_pct(series),
                        "lower_group_median": lower_median,
                        "higher_group_median": higher_median,
                        "lower_group_iqr": _iqr(lower),
                        "higher_group_iqr": _iqr(higher),
                        "direction": direction,
                        "effect_size_proxy": _effect_size(lower_median, higher_median, lower, higher),
                        "direction_stable_across_thresholds": False,
                        "coverage_sufficient": bool(series.notna().sum() >= _minimum_coverage_count(len(frame))),
                        "feature_timing": spec["timing"],
                        "tier_medians_json": json.dumps(tier_medians, sort_keys=True, default=_json_default),
                        "interpretation_note": _interpretation_note(feature, spec["timing"], series),
                    }
                )
            stable = len(directions) >= 3 and Counter(directions).most_common(1)[0][1] >= 3
            for row in rows[-len(CONTRASTS):]:
                row["direction_stable_across_thresholds"] = stable
    return rows


def _entry_exit_features(comparison: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for row in comparison:
        if row["contrast"] != "sub_500k_vs_500k_plus" or not row["coverage_sufficient"]:
            continue
        selected.append(
            {
                "feature_family": row["feature_family"],
                "feature": row["feature"],
                "feature_timing": row["feature_timing"],
                "direction": row["direction"],
                "effect_size_proxy": row["effect_size_proxy"],
                "usable_for": _usable_for(row["feature_timing"]),
                "caveat": row["interpretation_note"],
            }
        )
    return sorted(selected, key=lambda r: abs(_num(r["effect_size_proxy"]) or 0), reverse=True)[:80]


def _minimum_coverage_count(total_rows: int) -> int:
    if total_rows < 10:
        return max(1, total_rows // 2)
    return int(max(10, total_rows * 0.05))


def _strongest_commonalities(comparison: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = [
        row for row in comparison
        if row["contrast"] in {"sub_100k_vs_100k_plus", "sub_500k_vs_500k_plus", "sub_1m_vs_1m_plus"}
        and row["coverage_sufficient"]
        and row["direction"] != "flat_or_unknown"
    ]
    usable = sorted(usable, key=lambda row: abs(_num(row["effect_size_proxy"]) or 0), reverse=True)
    result = []
    seen = set()
    for row in usable:
        key = (row["feature_family"], row["feature"])
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "feature_family": row["feature_family"],
                "feature": row["feature"],
                "strongest_contrast": row["contrast"],
                "direction": row["direction"],
                "effect_size_proxy": row["effect_size_proxy"],
                "feature_timing": row["feature_timing"],
                "interpretation": _commonality_text(row),
            }
        )
        if len(result) >= 12:
            break
    return result


def _candidate_fingerprints(comparison: list[dict[str, Any]], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    by_feature = {row["feature"]: row for row in comparison if row["contrast"] == "sub_500k_vs_500k_plus" and row["coverage_sufficient"]}
    candidates = [
        _fingerprint(
            "FRP-001",
            "Efficient visible expansion with better wallet-quality proxy",
            "Higher FDV-proxy efficiency and better early buyer history appear together in stronger runners.",
            ["visible_fdv_flow", "wallet_quality_repeated_buyers"],
            ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "smart_money_quality_proxy", "early_buyer_with_prior_runner_count"],
            by_feature,
            "entry_side",
        ),
        _fingerprint(
            "FRP-002",
            "Efficient expansion with lower synthetic-activity pressure",
            "Stronger runners look less dependent on repetitive or round-trip-like activity in available local proxies.",
            ["visible_fdv_flow", "synthetic_activity_authenticity", "liquidity_executability"],
            ["fdv_per_event_at_20k", "synthetic_activity_proxy", "wash_trade_proxy_share_before_20k", "liquidity_sol_proxy_at_20k"],
            by_feature,
            "entry_side_and_path_side",
        ),
        _fingerprint(
            "FRP-003",
            "Wallet-quality positive with lower creator-extraction proxy",
            "Better early buyer quality paired with lower observed creator sell/extraction proxy deserves a formal descriptive design.",
            ["wallet_quality_repeated_buyers", "creator_deployer"],
            ["smart_money_quality_proxy", "early_buyer_with_prior_100k_count", "creator_extraction_proxy_before_20k", "creator_direct_sell_amount_sol"],
            by_feature,
            "entry_side",
        ),
        _fingerprint(
            "FRP-004",
            "Junk-risk screen from synthetic activity, shared funding, and extraction proxies",
            "Some proxies look more useful as risk filters than positive runner signals.",
            ["synthetic_activity_authenticity", "funding_structure", "creator_deployer"],
            ["synthetic_activity_proxy", "shared_funding_proxy", "launches_sharing_funder", "creator_extraction_proxy_before_20k"],
            by_feature,
            "entry_side",
            deserves=False,
        ),
    ]
    return [row for row in candidates if row["coverage"]["usable_feature_count"] > 0]


def _fingerprint(
    fingerprint_id: str,
    name: str,
    description: str,
    families: list[str],
    features: list[str],
    by_feature: dict[str, dict[str, Any]],
    timing: str,
    *,
    deserves: bool = True,
) -> dict[str, Any]:
    used = [feature for feature in features if feature in by_feature]
    coverage = {
        "usable_feature_count": len(used),
        "features_with_sufficient_coverage": used,
        "median_coverage_pct": _median([by_feature[feature]["coverage_pct"] for feature in used]) if used else 0.0,
    }
    directions = {feature: by_feature[feature]["direction"] for feature in used}
    strongest = sorted(used, key=lambda feature: abs(_num(by_feature[feature]["effect_size_proxy"]) or 0), reverse=True)
    return {
        "fingerprint_id": fingerprint_id,
        "fingerprint_name": name,
        "description": description,
        "feature_families_included": ";".join(families),
        "specific_features": ";".join(used),
        "expected_direction": json.dumps(directions, sort_keys=True),
        "entry_side_vs_path_side_vs_exit_side": timing,
        "coverage": coverage,
        "milestone_tiers_where_strongest": "500k_plus_or_1m_plus_contrasts",
        "limitations": "Descriptive FDV-proxy comparison only; no validation, no trading rule, no market-cap claim.",
        "missing_fields": "LP control; priority fee; true market cap; confirmed full-chain holder state where relevant",
        "why_it_may_matter": description,
        "what_would_invalidate_it": "The same direction disappears after formal leakage-safe thesis design, stronger missing-layer data, or broader cohort checks.",
        "deserves_formal_descriptive_thesis_design_later": bool(deserves and len(used) >= 2),
        "strongest_features": ";".join(strongest[:3]),
    }


def _readiness(frame: pd.DataFrame, fingerprints: list[dict[str, Any]]) -> str:
    if len(frame) == 0 or not fingerprints:
        return READINESS_INCONCLUSIVE
    formal = [row for row in fingerprints if row["deserves_formal_descriptive_thesis_design_later"]]
    return READINESS_READY if formal else READINESS_NEEDS_LAYER


def _recommendation(readiness: str, fingerprints: list[dict[str, Any]], missing_layers: list[dict[str, Any]]) -> dict[str, Any]:
    if readiness == READINESS_READY:
        top = [row["fingerprint_id"] for row in fingerprints if row["deserves_formal_descriptive_thesis_design_later"]][:3]
        return {
            "next_step": "ready_for_formal_thesis_selection_from_broad_report",
            "recommended_option": "A",
            "top_candidate_fingerprints": top,
            "what_not_to_do_next": "Do not run paper/live trading, optimization, alerts, or strategy generation.",
            "data_upgrade_before_selection": "Not required for non-LP/non-priority-fee fingerprints; required before any LP-control or priority-fee thesis.",
        }
    if readiness == READINESS_NEEDS_LAYER:
        return {
            "next_step": "need_one_specific_missing_data_layer_before_thesis_selection",
            "recommended_option": "B",
            "top_candidate_fingerprints": [],
            "what_not_to_do_next": "Do not force formal thesis selection from sparse proxy families.",
            "data_upgrade_before_selection": missing_layers[0]["missing_layer"],
        }
    return {
        "next_step": "inconclusive_broaden_source_universe",
        "recommended_option": "D",
        "top_candidate_fingerprints": [],
        "what_not_to_do_next": "Do not draw runner-fingerprint conclusions from this sample.",
        "data_upgrade_before_selection": "broader cohort or stronger core enrichment",
    }


def _limitations(frame: pd.DataFrame, inventory: dict[str, Any]) -> list[str]:
    notes = [
        "All outcome language is FDV-proxy only; true market cap remains blocked.",
        "This is descriptive comparison only, not a thesis, validation, backtest, or trading-rule generator.",
        "LP control and priority-fee contention are unavailable in the current enriched master.",
    ]
    if inventory["metadata_visibility"]["interpretation_status"] == "sparse_do_not_overinterpret":
        notes.append("Metadata and visibility coverage is sparse and should not be overinterpreted.")
    if _coverage_pct(frame.get("holder_retention_proxy", pd.Series(dtype=float))) < 50:
        notes.append("Holder retention is partial and based on observed replay proxies, not confirmed full-chain account state.")
    return notes


def _write_outputs(
    report: dict[str, Any],
    comparison: list[dict[str, Any]],
    fingerprints: list[dict[str, Any]],
    entry_exit: list[dict[str, Any]],
    missing_layers: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "final_runner_fingerprint_summary.json",
        "summary_markdown_path": output / "final_runner_fingerprint_summary.md",
        "feature_family_comparison_path": output / "final_runner_feature_family_comparison.csv",
        "candidate_fingerprints_path": output / "final_runner_candidate_fingerprints.csv",
        "entry_vs_exit_features_path": output / "final_runner_entry_vs_exit_features.csv",
        "missing_layer_review_path": output / "final_runner_missing_layer_review.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_markdown_summary(report), encoding="utf-8")
    pd.DataFrame(comparison).to_csv(paths["feature_family_comparison_path"], index=False)
    pd.DataFrame([_flatten_fingerprint(row) for row in fingerprints]).to_csv(paths["candidate_fingerprints_path"], index=False)
    pd.DataFrame(entry_exit).to_csv(paths["entry_vs_exit_features_path"], index=False)
    pd.DataFrame(missing_layers).to_csv(paths["missing_layer_review_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# Final Runner Fingerprint Summary",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Rows analyzed: `{report['dataset']['rows_analyzed']}`",
        "- Scope: descriptive fingerprint report only; no thesis, validation, backtest, paper/live trading, optimization, or trading logic.",
        "",
        "## Strongest Broad Commonalities",
    ]
    for row in report["strongest_broad_commonalities"][:10]:
        lines.append(f"- `{row['feature']}` ({row['feature_family']}): {row['interpretation']}")
    lines.extend(["", "## Candidate Fingerprints"])
    for row in report["candidate_fingerprints"]:
        lines.append(f"- `{row['fingerprint_id']}` {row['fingerprint_name']}: {row['description']}")
    lines.extend(["", "## Recommendation", "", f"- Next step: `{report['recommendation']['next_step']}`", ""])
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Final Runner Fingerprint Report Status",
        "",
        "This report was created to summarize broad descriptive runner fingerprints from the enriched FDV-proxy master dataset before formal thesis selection.",
        "",
        f"- Dataset used: `{report['dataset']['master_path']}`",
        f"- Rows analyzed: `{report['dataset']['rows_analyzed']}`",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Recommendation: `{report['recommendation']['next_step']}`",
        "",
        "## Coverage Summary",
    ]
    for flag, values in report["layer_coverage_summary"].items():
        lines.append(f"- {flag}: `{values['covered_rows']} / {values['total_rows']}` ({values['coverage_pct']}%)")
    lines.extend(["", "## Major Commonalities"])
    for row in report["strongest_broad_commonalities"][:8]:
        lines.append(f"- `{row['feature']}`: {row['interpretation']}")
    lines.extend(["", "## Candidate Fingerprints"])
    for row in report["candidate_fingerprints"]:
        lines.append(f"- `{row['fingerprint_id']}` {row['fingerprint_name']}")
    lines.extend(["", "## Missing Layers"])
    for row in report["missing_layer_review"]:
        lines.append(f"- {row['missing_layer']}: `{row['status']}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            *[f"- {note}" for note in report["limitations"]],
            "",
            "No thesis, validation, backtest, paper/live trading, alerts, buy/sell rules, wallet execution, optimization, or strategy logic was run.",
            "",
        ]
    )
    return "\n".join(lines)


def _flatten_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["coverage"] = json.dumps(row["coverage"], sort_keys=True, default=_json_default)
    return result


def _guardrails() -> dict[str, Any]:
    return {
        "thesis_runs": 0,
        "validation_runs": 0,
        "backtests_run": 0,
        "walk_forward_runs": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "alerts_added": False,
        "trading_logic_added": False,
        "buy_rules_created": False,
        "sell_rules_created": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
    }


def _coverage_pct(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return 0.0
    return round(float(series.notna().sum()) / len(series) * 100, 4)


def _numeric_series(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _median(series: Any) -> Any:
    if isinstance(series, list):
        series = pd.Series(series)
    s = _numeric_series(series).dropna()
    return float(s.median()) if not s.empty else None


def _iqr(series: pd.Series) -> Any:
    s = _numeric_series(series).dropna()
    if s.empty:
        return None
    return float(s.quantile(0.75) - s.quantile(0.25))


def _direction(lower: Any, higher: Any) -> str:
    if lower is None or higher is None:
        return "flat_or_unknown"
    if abs(float(higher) - float(lower)) < 1e-12:
        return "flat_or_unknown"
    return "higher_in_stronger_runners" if float(higher) > float(lower) else "lower_in_stronger_runners"


def _effect_size(lower_median: Any, higher_median: Any, lower: pd.Series, higher: pd.Series) -> Any:
    if lower_median is None or higher_median is None:
        return None
    spread = pd.concat([_numeric_series(lower), _numeric_series(higher)]).dropna()
    scale = float(spread.quantile(0.75) - spread.quantile(0.25)) if len(spread) else 0.0
    if scale == 0:
        scale = max(abs(float(lower_median)), abs(float(higher_median)), 1.0)
    return round((float(higher_median) - float(lower_median)) / scale, 6)


def _interpretation_note(feature: str, timing: str, series: pd.Series) -> str:
    if _coverage_pct(series) < 10:
        return "sparse_coverage_do_not_overinterpret"
    if timing == "entry_side":
        return "entry_side_observable_proxy"
    if timing == "path_side":
        return "path_side_or_exit_side_context_proxy"
    return "descriptive_proxy"


def _usable_for(timing: str) -> str:
    if timing == "entry_side":
        return "candidate_formal_entry_side_thesis_design"
    if timing == "path_side":
        return "path_or_exit_analysis_only"
    return "descriptive_context_only"


def _commonality_text(row: dict[str, Any]) -> str:
    return (
        f"{row['direction']} for `{row['contrast']}` with effect-size proxy "
        f"`{row['effect_size_proxy']}` and coverage `{row['coverage_pct']}%`."
    )


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() not in {"", "none", "nan", "null"}


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
