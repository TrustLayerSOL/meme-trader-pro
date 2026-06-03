"""Selection/design report for combined aligned P0 structural fingerprints."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "combined_p0_fingerprint_selection_design_v0"
DEFAULT_INPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "combined_aligned_p0_fingerprint"
)
DEFAULT_SUMMARY_PATH = DEFAULT_INPUT_DIR / "combined_aligned_p0_fingerprint_summary.json"
DEFAULT_TIER_FEATURE_COMPARISON_PATH = DEFAULT_INPUT_DIR / "combined_p0_tier_feature_comparison.csv"
DEFAULT_ENTRY_VS_EXIT_FEATURES_PATH = DEFAULT_INPUT_DIR / "combined_p0_entry_vs_exit_features.csv"
DEFAULT_CANDIDATE_FINGERPRINTS_PATH = DEFAULT_INPUT_DIR / "combined_p0_candidate_fingerprints.csv"
DEFAULT_COMBINED_DATASET_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "combined_aligned_p0_structural_fingerprint.parquet"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "combined_p0_fingerprint_selection"
)
DEFAULT_STATUS_PATH = Path("theses/COMBINED_P0_FINGERPRINT_SELECTION_STATUS.md")

HIGH_TIERS = {"reached_500k_but_never_1m", "reached_1m_plus"}
LOW_TIERS = {"reached_20k_but_never_50k", "reached_50k_but_never_100k"}
MID_TIERS = {"reached_100k_but_never_200k", "reached_200k_but_never_500k"}
TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
VISIBLE_FEATURES = [
    "fdv_per_event_at_20k",
    "fdv_per_buy_at_20k",
    "fdv_per_active_wallet_at_20k",
    "active_wallets_at_20k",
    "event_count_at_20k",
    "buy_count_at_20k",
    "sell_count_at_20k",
    "buy_sell_ratio_at_20k",
]
REPEATED_BUYER_FEATURES = [
    "repeated_buyer_quality_proxy",
    "early_buyer_with_prior_runner_count",
    "early_buyer_with_prior_100k_count",
    "early_buyer_with_prior_500k_count",
    "early_buyer_with_prior_1m_count",
    "early_buyer_prior_failure_count",
]
TOP_HOLDER_FEATURES = ["top_holder_share_proxy", "top_10_holder_share_proxy", "top_holder_replay_confidence"]
FUNDER_FEATURES = [
    "launches_sharing_funder",
    "creators_sharing_funder",
    "shared_funding_proxy",
    "time_linked_funding_proxy",
    "candidate_funder_confidence",
    "common_funder_candidate_id",
]
CREATOR_LINK_FEATURES = ["creator_to_early_buyer_link_proxy", "creator_to_top_holder_link_proxy"]
REVIEW_FEATURES = VISIBLE_FEATURES + REPEATED_BUYER_FEATURES + TOP_HOLDER_FEATURES + FUNDER_FEATURES + CREATOR_LINK_FEATURES
UNSUPPORTED_TERMS = ("insider", "scammer", "wash trader", "manipulator")


def build_combined_p0_fingerprint_selection_design(
    *,
    summary_path: Path | str = DEFAULT_SUMMARY_PATH,
    tier_feature_comparison_path: Path | str = DEFAULT_TIER_FEATURE_COMPARISON_PATH,
    entry_vs_exit_features_path: Path | str = DEFAULT_ENTRY_VS_EXIT_FEATURES_PATH,
    candidate_fingerprints_path: Path | str = DEFAULT_CANDIDATE_FINGERPRINTS_PATH,
    combined_dataset_path: Path | str = DEFAULT_COMBINED_DATASET_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    summary = _read_json(Path(summary_path))
    tier_rows = _read_csv(Path(tier_feature_comparison_path))
    entry_exit_rows = _read_csv(Path(entry_vs_exit_features_path))
    conceptual_fingerprints = _read_csv(Path(candidate_fingerprints_path))
    structural_rows = _read_records(Path(combined_dataset_path))

    source_confirmation = _source_confirmation(summary, structural_rows)
    entry_side_features = _entry_side_features(entry_exit_rows)
    direction_rows = _feature_direction_rows(tier_rows, structural_rows)
    selected, deferred = _select_candidate_fingerprints(direction_rows, structural_rows, entry_side_features)
    thesis_stubs = _thesis_design_stubs(selected)
    readiness = _readiness_classification(selected)
    immediate_next_action = _immediate_next_action(selected, readiness)
    report = {
        "report_id": REPORT_ID,
        "report_type": "combined_p0_fingerprint_selection_design",
        "readiness_classification": readiness,
        "methodology_flags": [
            "design_sprint_only",
            "no_thesis_execution",
            "no_validation_execution",
            "no_backtest",
            "no_walk_forward_validation",
            "no_paper_trading",
            "no_live_trading",
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
            "no_network_calls",
        ],
        "source_paths": {
            "summary_path": str(summary_path),
            "tier_feature_comparison_path": str(tier_feature_comparison_path),
            "entry_vs_exit_features_path": str(entry_vs_exit_features_path),
            "candidate_fingerprints_path": str(candidate_fingerprints_path),
            "combined_dataset_path": str(combined_dataset_path),
        },
        "source_report_confirmation": source_confirmation,
        "conceptual_candidate_fingerprint_note": _conceptual_note(conceptual_fingerprints),
        "available_visible_features": _available_features(structural_rows, VISIBLE_FEATURES),
        "available_hidden_structural_features": _available_features(
            structural_rows, REPEATED_BUYER_FEATURES + TOP_HOLDER_FEATURES + FUNDER_FEATURES + CREATOR_LINK_FEATURES
        ),
        "feature_direction_groups": _direction_groups(direction_rows),
        "selected_candidate_fingerprints": selected,
        "rejected_or_deferred_fingerprints": deferred,
        "thesis_design_stubs": thesis_stubs,
        "immediate_next_action": immediate_next_action,
        "limitations": [
            "true_market_cap_claims_remain_blocked",
            "fdv_or_valuation_proxy_only",
            "selection_design_only_no_formal_test",
            "candidate_support_uses_descriptive_above_median_proxies_not_optimized_thresholds",
            "leftover_sample_is_kept_separate_because_it_is_date_concentrated",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(
        report=report,
        direction_rows=direction_rows,
        selected=selected + deferred,
        thesis_stubs=thesis_stubs,
        output_dir=Path(output_dir),
        status_path=Path(status_path),
    )
    return report, paths


def classify_feature_direction(high_tier_median: float | None, low_tier_median: float | None) -> str:
    if high_tier_median is None or low_tier_median is None:
        return "coverage_limited"
    if math.isclose(high_tier_median, low_tier_median, rel_tol=1e-9, abs_tol=1e-9):
        return "flat_or_not_useful"
    if high_tier_median > low_tier_median:
        return "higher_in_higher_tiers"
    return "lower_in_higher_tiers"


def _source_confirmation(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = summary.get("coverage_audit", {}) if isinstance(summary, dict) else {}
    tier_counts = summary.get("milestone_tier_counts", {}) if isinstance(summary, dict) else {}
    if not coverage and rows:
        coverage = {
            "total_unique_launches": len(rows),
            "all_three_p0_launches": sum(1 for row in rows if _bool(row.get("has_all_three_p0_layers"))),
            "balanced_sample_rows": sum(1 for row in rows if _bool(row.get("is_balanced_sample"))),
            "leftover_sample_rows": sum(1 for row in rows if _bool(row.get("is_leftover_sample"))),
        }
    if not tier_counts and rows:
        tier_counts = dict(Counter(str(row.get("milestone_tier") or "unknown") for row in rows))
    return {
        "unique_launch_count": _int(coverage.get("total_unique_launches"), len(rows)),
        "all_three_p0_row_count": _int(coverage.get("all_three_p0_launches"), 0),
        "balanced_sample_count": _int(coverage.get("balanced_sample_rows"), 0),
        "leftover_sample_count": _int(coverage.get("leftover_sample_rows"), 0),
        "milestone_tier_counts": tier_counts,
    }


def _feature_direction_rows(tier_rows: list[dict[str, Any]], structural_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    subsets = ["balanced_sample", "leftover_sample", "combined_sample"]
    for subset in subsets:
        subset_rows = _subset_structural_rows(structural_rows, subset)
        for feature in REVIEW_FEATURES:
            high_values = _tier_medians(tier_rows, subset, feature, HIGH_TIERS)
            low_values = _tier_medians(tier_rows, subset, feature, LOW_TIERS)
            high_median = _median_or_none(high_values)
            low_median = _median_or_none(low_values)
            direction = classify_feature_direction(high_median, low_median)
            coverage = _feature_coverage(subset_rows, feature)
            if coverage["coverage_pct"] == 0:
                direction = "coverage_limited"
            output.append(
                {
                    "evidence_subset": subset,
                    "feature": feature,
                    "feature_family": _feature_family(feature),
                    "high_tier_median": high_median,
                    "low_tier_median": low_median,
                    "direction": direction,
                    "available_rows": coverage["available_rows"],
                    "missing_rows": coverage["missing_rows"],
                    "coverage_pct": coverage["coverage_pct"],
                    "balanced_vs_leftover_conflict": False,
                }
            )
    by_feature = {}
    for row in output:
        by_feature.setdefault(row["feature"], {})[row["evidence_subset"]] = row
    for feature, rows_by_subset in by_feature.items():
        balanced = rows_by_subset.get("balanced_sample", {}).get("direction")
        leftover = rows_by_subset.get("leftover_sample", {}).get("direction")
        conflict = _directions_conflict(balanced, leftover)
        for row in rows_by_subset.values():
            row["balanced_vs_leftover_conflict"] = conflict
    return output


def _select_candidate_fingerprints(
    direction_rows: list[dict[str, Any]], structural_rows: list[dict[str, Any]], entry_side_features: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [
        {
            "fingerprint_id": "FP001",
            "fingerprint_name": "Efficient Expansion With Clean Funding Structure",
            "plain_english_description": "High early valuation efficiency paired with lower shared/time-linked funding proxies.",
            "visible_features": ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "fdv_per_active_wallet_at_20k", "active_wallets_at_20k"],
            "hidden_structural_features": [
                "shared_funding_proxy",
                "time_linked_funding_proxy",
                "launches_sharing_funder",
                "creators_sharing_funder",
            ],
            "expected_directions": {
                "fdv_per_event_at_20k": "higher",
                "fdv_per_buy_at_20k": "higher",
                "fdv_per_active_wallet_at_20k": "higher",
                "active_wallets_at_20k": "not_zero",
                "shared_funding_proxy": "lower",
                "time_linked_funding_proxy": "lower",
                "launches_sharing_funder": "lower",
                "creators_sharing_funder": "lower",
            },
            "entry_side_or_exit_side": "entry_side",
            "why_it_may_matter": "It separates efficient early expansion from launches with stronger shared funding proxy patterns.",
            "what_could_invalidate_it": "If balanced and leftover samples disagree, or if efficiency fields are too sparse for formal buckets.",
            "data_still_missing": "true_market_cap;full_holder_addresses",
        },
        {
            "fingerprint_id": "FP002",
            "fingerprint_name": "Efficient Expansion With Proven Buyer Quality",
            "plain_english_description": "High early valuation efficiency paired with stronger repeated-buyer wallet quality proxies.",
            "visible_features": ["fdv_per_event_at_20k", "fdv_per_buy_at_20k", "active_wallets_at_20k"],
            "hidden_structural_features": [
                "repeated_buyer_quality_proxy",
                "early_buyer_with_prior_runner_count",
                "early_buyer_prior_failure_count",
            ],
            "expected_directions": {
                "fdv_per_event_at_20k": "higher",
                "fdv_per_buy_at_20k": "higher",
                "active_wallets_at_20k": "not_zero",
                "repeated_buyer_quality_proxy": "higher",
                "early_buyer_with_prior_runner_count": "higher",
                "early_buyer_prior_failure_count": "not_elevated",
            },
            "entry_side_or_exit_side": "entry_side",
            "why_it_may_matter": "It tests whether early participants with prior runner history are more informative than raw activity.",
            "what_could_invalidate_it": "If repeated-buyer quality is flat after balanced-only support review.",
            "data_still_missing": "wallet_quality_labels_are_proxy_only",
        },
        {
            "fingerprint_id": "FP003",
            "fingerprint_name": "Efficient Expansion With Concentrated Stable Holder Structure",
            "plain_english_description": "High early valuation efficiency paired with stronger top-holder replay structure and low shared funding risk proxies.",
            "visible_features": ["fdv_per_event_at_20k", "fdv_per_active_wallet_at_20k"],
            "hidden_structural_features": ["top_holder_share_proxy", "top_10_holder_share_proxy", "shared_funding_proxy"],
            "expected_directions": {
                "fdv_per_event_at_20k": "higher",
                "fdv_per_active_wallet_at_20k": "higher",
                "top_holder_share_proxy": "higher",
                "top_10_holder_share_proxy": "stable_or_high",
                "shared_funding_proxy": "lower",
            },
            "entry_side_or_exit_side": "entry_side_with_holder_replay_proxy_caveat",
            "why_it_may_matter": "Some explosive moves may have concentrated but stable holder structure instead of broad participation.",
            "what_could_invalidate_it": "If top-holder replay is an artifact of observed deltas rather than durable holder behavior.",
            "data_still_missing": "confirmed_full_chain_holder_snapshots;top_holder_addresses",
        },
        {
            "fingerprint_id": "FP004",
            "fingerprint_name": "Junk Risk Filter Fingerprint",
            "plain_english_description": "Higher shared/time-linked funding proxies and weaker efficiency, framed as a risk filter candidate.",
            "visible_features": ["fdv_per_event_at_20k", "fdv_per_buy_at_20k"],
            "hidden_structural_features": [
                "shared_funding_proxy",
                "time_linked_funding_proxy",
                "launches_sharing_funder",
                "creators_sharing_funder",
                "early_buyer_prior_failure_count",
            ],
            "expected_directions": {
                "fdv_per_event_at_20k": "lower",
                "fdv_per_buy_at_20k": "lower",
                "shared_funding_proxy": "higher",
                "time_linked_funding_proxy": "higher",
                "launches_sharing_funder": "higher",
                "creators_sharing_funder": "higher",
                "early_buyer_prior_failure_count": "higher",
            },
            "entry_side_or_exit_side": "risk_filter_design_only",
            "why_it_may_matter": "It may define a negative-control risk pattern rather than a positive runner fingerprint.",
            "what_could_invalidate_it": "If high shared/time-linked funding proxy appears in high tiers after balanced-only formal review.",
            "data_still_missing": "none_for_proxy_design;true_financing_lineage_would_improve_interpretability",
        },
    ]
    selected = []
    deferred = []
    direction_lookup = {(row["evidence_subset"], row["feature"]): row for row in direction_rows}
    for candidate in candidates:
        enriched = _enrich_candidate(candidate, structural_rows, direction_lookup, entry_side_features)
        if enriched["formal_thesis_recommendation"] in {"ready_for_formal_descriptive_thesis", "needs_more_support_analysis"}:
            selected.append(enriched)
        else:
            deferred.append(enriched)
    selected = sorted(selected, key=lambda row: (row["formal_thesis_recommendation"] != "ready_for_formal_descriptive_thesis", row["fingerprint_id"]))[:3]
    selected_ids = {row["fingerprint_id"] for row in selected}
    deferred = [row for row in candidates if row["fingerprint_id"] not in selected_ids]
    deferred = [_enrich_candidate(row, structural_rows, direction_lookup, entry_side_features) for row in deferred]
    return selected, deferred


def _enrich_candidate(
    candidate: dict[str, Any],
    structural_rows: list[dict[str, Any]],
    direction_lookup: dict[tuple[str, str], dict[str, Any]],
    entry_side_features: set[str],
) -> dict[str, Any]:
    features = candidate["visible_features"] + candidate["hidden_structural_features"]
    coverage = _candidate_coverage(structural_rows, features)
    balanced_support = _candidate_support(structural_rows, candidate, subset="balanced_sample")
    leftover_support = _candidate_support(structural_rows, candidate, subset="leftover_sample")
    combined_support = _candidate_support(structural_rows, candidate, subset="combined_sample")
    strongest_tiers = _strongest_tiers(structural_rows, features)
    directions = {feature: (direction_lookup.get(("combined_sample", feature)) or {}).get("direction", "coverage_limited") for feature in features}
    conflicts = [
        feature
        for feature in features
        if (direction_lookup.get(("combined_sample", feature)) or {}).get("balanced_vs_leftover_conflict")
    ]
    observed_fit = _direction_fit(candidate["expected_directions"], directions)
    entry_observable = all(feature in entry_side_features or feature in candidate["hidden_structural_features"] for feature in features)
    if coverage["coverage_pct"] < 50:
        recommendation = "needs_more_enrichment"
    elif conflicts:
        recommendation = "needs_more_support_analysis"
    elif observed_fit >= 0.55 and entry_observable:
        recommendation = "ready_for_formal_descriptive_thesis"
    else:
        recommendation = "needs_more_support_analysis"
    enriched = {
        **candidate,
        "visible_features": ";".join(candidate["visible_features"]),
        "hidden_structural_features": ";".join(candidate["hidden_structural_features"]),
        "expected_directions": json.dumps(candidate["expected_directions"], sort_keys=True),
        "data_coverage": coverage,
        "balanced_sample_support": balanced_support,
        "leftover_sample_support": leftover_support,
        "combined_sample_support": combined_support,
        "milestone_tiers_where_it_appears_strongest": ";".join(strongest_tiers) if strongest_tiers else "not_computed",
        "direction_fit_ratio": round(observed_fit, 4),
        "balanced_leftover_conflicts": ";".join(conflicts),
        "should_become_formal_descriptive_thesis": recommendation == "ready_for_formal_descriptive_thesis",
        "requires_more_enrichment_first": recommendation == "needs_more_enrichment",
        "formal_thesis_recommendation": recommendation,
        "support_note": "support_recomputed_with_non_optimized_above_median_descriptive_proxy",
    }
    return enriched


def _candidate_support(rows: list[dict[str, Any]], candidate: dict[str, Any], *, subset: str) -> dict[str, Any]:
    subset_rows = _subset_structural_rows(rows, subset)
    if not subset_rows:
        return {"support_mode": "not_computed", "reason": "no_subset_rows", "row_count": 0}
    visible = candidate["visible_features"]
    hidden = candidate["hidden_structural_features"]
    expected = candidate["expected_directions"]
    feature_medians = {feature: _median_or_none([_number(row.get(feature)) for row in subset_rows]) for feature in visible + hidden}
    support = 0
    eligible = 0
    high_tier_support = 0
    for row in subset_rows:
        checks = []
        for feature in visible + hidden:
            value = _number(row.get(feature))
            baseline = feature_medians.get(feature)
            if value is None or baseline is None:
                continue
            checks.append(_matches_direction(value, baseline, expected.get(feature)))
        if checks:
            eligible += 1
            if sum(1 for ok in checks if ok) / len(checks) >= 0.6:
                support += 1
                if str(row.get("milestone_tier")) in HIGH_TIERS:
                    high_tier_support += 1
    return {
        "support_mode": "descriptive_above_median_proxy",
        "row_count": len(subset_rows),
        "eligible_rows": eligible,
        "support_rows": support,
        "high_tier_support_rows": high_tier_support,
        "support_pct": _pct(support, eligible),
    }


def _matches_direction(value: float, baseline: float, direction: str | None) -> bool:
    if direction in {"higher", "stable_or_high"}:
        return value >= baseline
    if direction in {"lower", "not_elevated"}:
        return value <= baseline
    if direction == "not_zero":
        return value > 0
    return True


def _direction_fit(expected: dict[str, str], observed: dict[str, str]) -> float:
    comparable = 0
    matched = 0
    for feature, expected_direction in expected.items():
        direction = observed.get(feature)
        if direction in {None, "coverage_limited", "flat_or_not_useful"}:
            continue
        comparable += 1
        if expected_direction in {"higher", "stable_or_high", "not_zero"} and direction == "higher_in_higher_tiers":
            matched += 1
        elif expected_direction in {"lower", "not_elevated"} and direction == "lower_in_higher_tiers":
            matched += 1
    return matched / comparable if comparable else 0.0


def _thesis_design_stubs(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stubs = []
    for row in selected:
        stubs.append(
            {
                "fingerprint_id": row["fingerprint_id"],
                "thesis_name": f"{row['fingerprint_id']} {row['fingerprint_name']}",
                "research_question": f"Does {row['fingerprint_name']} separate higher milestone tiers from lower milestone tiers descriptively?",
                "feature_set": f"{row['visible_features']};{row['hidden_structural_features']}",
                "expected_direction": row["expected_directions"],
                "primary_comparison_tiers": "reached_500k_but_never_1m/reached_1m_plus versus reached_20k_but_never_50k/reached_50k_but_never_100k",
                "primary_outcome_or_milestone_target": "milestone_tier and FDV_proxy_path_only",
                "data_requirements": "combined aligned P0 structural fingerprint dataset; balanced and leftover evidence separated",
                "guardrails": "descriptive thesis only; no validation; no trading logic; no threshold search",
                "invalidation_criteria": row["what_could_invalidate_it"],
                "needs_robustness_before_validation": True,
            }
        )
    return stubs


def _immediate_next_action(selected: list[dict[str, Any]], readiness: str) -> str:
    if readiness == "fingerprint_selection_ready_for_formal_thesis" and selected:
        first = selected[0]["fingerprint_id"]
        if first == "FP001":
            return "A. Run formal descriptive thesis for Fingerprint 1."
        if first == "FP002":
            return "B. Run formal descriptive thesis for Fingerprint 2."
        if first == "FP003":
            return "C. Run formal descriptive thesis for Fingerprint 3."
    if readiness == "fingerprint_selection_needs_support_audit":
        return "D. Do one more support/coverage audit before any thesis."
    if readiness == "fingerprint_selection_needs_enrichment":
        return "E. Do one more enrichment pass before any thesis."
    return "F. Stop and review manually."


def _readiness_classification(selected: list[dict[str, Any]]) -> str:
    ready = [row for row in selected if row["formal_thesis_recommendation"] == "ready_for_formal_descriptive_thesis"]
    support = [row for row in selected if row["formal_thesis_recommendation"] == "needs_more_support_analysis"]
    enrichment = [row for row in selected if row["formal_thesis_recommendation"] == "needs_more_enrichment"]
    if ready:
        return "fingerprint_selection_ready_for_formal_thesis"
    if support:
        return "fingerprint_selection_needs_support_audit"
    if enrichment:
        return "fingerprint_selection_needs_enrichment"
    return "fingerprint_selection_inconclusive"


def _direction_groups(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    combined = [row for row in rows if row["evidence_subset"] == "combined_sample"]
    groups: dict[str, list[str]] = {
        "higher_in_higher_tiers": [],
        "lower_in_higher_tiers": [],
        "flat_or_not_useful": [],
        "coverage_limited": [],
        "conflicting_between_balanced_and_leftover": [],
    }
    for row in combined:
        groups.setdefault(row["direction"], []).append(row["feature"])
        if row["balanced_vs_leftover_conflict"]:
            groups["conflicting_between_balanced_and_leftover"].append(row["feature"])
    return {key: sorted(set(value)) for key, value in groups.items()}


def _write_outputs(
    *,
    report: dict[str, Any],
    direction_rows: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    thesis_stubs: list[dict[str, Any]],
    output_dir: Path,
    status_path: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json_path": output_dir / "combined_p0_fingerprint_selection_summary.json",
        "summary_md_path": output_dir / "combined_p0_fingerprint_selection_summary.md",
        "selection_table_path": output_dir / "fingerprint_candidate_selection_table.csv",
        "feature_direction_table_path": output_dir / "fingerprint_feature_direction_table.csv",
        "thesis_design_stubs_path": output_dir / "fingerprint_thesis_design_stubs.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    paths["summary_md_path"].write_text(_markdown(report), encoding="utf-8")
    _write_csv(direction_rows, paths["feature_direction_table_path"])
    _write_csv(_flatten_candidates(selected), paths["selection_table_path"])
    _write_csv(thesis_stubs, paths["thesis_design_stubs_path"])
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _flatten_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for row in rows:
        flat = {}
        for key, value in row.items():
            flat[key] = json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        flattened.append(flat)
    return flattened


def _markdown(report: dict[str, Any]) -> str:
    source = report["source_report_confirmation"]
    selected = report["selected_candidate_fingerprints"]
    return "\n".join(
        [
            "# Combined P0 Fingerprint Selection Design",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Unique launches reviewed: `{source['unique_launch_count']}`",
            f"- All-three P0 rows: `{source['all_three_p0_row_count']}`",
            f"- Selected fingerprints: `{', '.join(row['fingerprint_id'] for row in selected)}`",
            f"- Immediate next action: {report['immediate_next_action']}",
            "",
            "This is a design document only. It does not run a thesis, validation, backtest, or trading workflow.",
        ]
    ) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    source = report["source_report_confirmation"]
    selected = report["selected_candidate_fingerprints"]
    deferred = report["rejected_or_deferred_fingerprints"]
    visible = report["feature_direction_groups"].get("higher_in_higher_tiers", [])
    hidden = [feature for feature in visible if feature not in VISIBLE_FEATURES]
    return "\n".join(
        [
            "# Combined P0 Fingerprint Selection Status",
            "",
            "## Why Selection Design Was Created",
            "The combined aligned P0 report is ready for formal thesis selection, but candidate fingerprints needed to be frozen before any formal test.",
            "",
            "## Source Report Used",
            f"- Unique launches: `{source['unique_launch_count']}`",
            f"- All-three P0 rows: `{source['all_three_p0_row_count']}`",
            f"- Balanced sample rows: `{source['balanced_sample_count']}`",
            f"- Leftover sample rows: `{source['leftover_sample_count']}`",
            "",
            "## Selected Candidate Fingerprints",
            *[f"- `{row['fingerprint_id']}`: {row['fingerprint_name']} ({row['formal_thesis_recommendation']})" for row in selected],
            "",
            "## Rejected Or Deferred Fingerprints",
            *[f"- `{row['fingerprint_id']}`: {row['fingerprint_name']} ({row['formal_thesis_recommendation']})" for row in deferred],
            "",
            "## Ingredients",
            f"- Strongest visible ingredients: `{[feature for feature in visible if feature in VISIBLE_FEATURES]}`",
            f"- Strongest hidden structural ingredients: `{hidden}`",
            "",
            "## Entry-Side Vs Exit-Side",
            "All selected candidates are framed as entry-side or entry-side-with-proxy-caveat designs. No exit logic was created.",
            "",
            "## Immediate Next Action",
            report["immediate_next_action"],
            "",
            "## Limitations",
            *[f"- `{item}`" for item in report["limitations"]],
        ]
    ) + "\n"


def _conceptual_note(rows: list[dict[str, Any]]) -> dict[str, Any]:
    zero_support = sum(1 for row in rows if _number(row.get("sample_support")) == 0)
    return {
        "source_candidate_rows": len(rows),
        "rows_with_zero_sample_support": zero_support,
        "interpretation": "previous_candidate_fingerprints_treated_as_conceptual_only",
    }


def _available_features(rows: list[dict[str, Any]], features: list[str]) -> list[dict[str, Any]]:
    return [{"feature": feature, **_feature_coverage(rows, feature)} for feature in features]


def _candidate_coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    if not rows:
        return {"available_rows": 0, "missing_rows": 0, "coverage_pct": 0.0}
    available = sum(1 for row in rows if any(_has_value(row.get(feature)) for feature in features))
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _feature_coverage(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    available = sum(1 for row in rows if _has_value(row.get(feature)))
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _strongest_tiers(rows: list[dict[str, Any]], features: list[str]) -> list[str]:
    scored = []
    for tier in TIER_ORDER:
        tier_rows = [row for row in rows if str(row.get("milestone_tier")) == tier]
        vals = []
        for row in tier_rows:
            vals.extend(_number(row.get(feature)) for feature in features)
        numeric = [value for value in vals if value is not None]
        if numeric:
            scored.append((median(numeric), tier))
    return [tier for _score, tier in sorted(scored, reverse=True)[:3]]


def _tier_medians(tier_rows: list[dict[str, Any]], subset: str, feature: str, tiers: set[str]) -> list[float]:
    values = []
    for row in tier_rows:
        if row.get("evidence_subset") != subset or row.get("feature") != feature or row.get("milestone_tier") not in tiers:
            continue
        value = _number(row.get("median"))
        sample_count = _number(row.get("sample_count"))
        if value is not None and (sample_count is None or sample_count > 0):
            values.append(value)
    return values


def _directions_conflict(left: str | None, right: str | None) -> bool:
    if left in {None, "coverage_limited"} or right in {None, "coverage_limited"}:
        return False
    return left != right and "flat_or_not_useful" not in {left, right}


def _entry_side_features(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("feature_name"))
        for row in rows
        if str(row.get("feature_side")) == "entry_side" and _bool(row.get("available_now", True))
    }


def _subset_structural_rows(rows: list[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
    if subset == "balanced_sample":
        return [row for row in rows if _bool(row.get("is_balanced_sample")) and not _bool(row.get("is_leftover_sample"))]
    if subset == "leftover_sample":
        return [row for row in rows if _bool(row.get("is_leftover_sample"))]
    return rows


def _feature_family(feature: str) -> str:
    if feature in VISIBLE_FEATURES:
        return "visible_fdv_proxy"
    if feature in REPEATED_BUYER_FEATURES:
        return "repeated_buyer_proxy"
    if feature in TOP_HOLDER_FEATURES:
        return "top_holder_behavior_proxy"
    if feature in FUNDER_FEATURES:
        return "funder_link_proxy"
    if feature in CREATOR_LINK_FEATURES:
        return "creator_link_proxy"
    return "structural_proxy"


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path).to_dict("records")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix == ".json":
        payload = _read_json(path)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
    if path.suffix == ".csv":
        return _read_csv(path)
    return []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, sort_keys=True, default=str).lower()
    for term in UNSUPPORTED_TERMS:
        if term in text:
            raise ValueError(f"Unsupported label found in report: {term}")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "none", "nan", "null"}:
        return False
    return True


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _int(value: Any, default: int) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _median_or_none(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return median(numeric) if numeric else None


def _pct(num: int, den: int) -> float:
    return round(num / den * 100, 4) if den else 0.0
