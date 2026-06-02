"""Axiom-style historical structural feature parity mapper.

This module maps real-time token dashboard concepts into neutral, replay-safe
historical MemeTraderPro fields. It is planning-only: no network calls, no
thesis execution, and no trading logic.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "axiom_historical_parity_v0"
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "axiom_historical_parity",
)
DEFAULT_STATUS_PATH = Path("theses/AXIOM_HISTORICAL_PARITY_STATUS.md")


@dataclass(frozen=True)
class AxiomHistoricalFieldMapRow:
    axiom_concept: str
    historical_field: str
    current_availability: str
    coverage: str
    source: str
    local_or_offline: str
    helius_needed: str
    dexscreener_needed: str
    priority: str
    entry_or_exit_side: str
    blocker: str
    feasibility_classification: str


def build_axiom_historical_parity_report(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    field_map = [asdict(row) for row in _field_map_rows()]
    summary = _summary(field_map)
    report = {
        "report_id": REPORT_ID,
        "report_type": "axiom_historical_parity_mapping",
        "readiness_classification": "axiom_historical_parity_plan_ready",
        "methodology_flags": [
            "research_only",
            "mapping_and_prioritization_only",
            "not_a_thesis",
            "no_thesis_promotion",
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
            "no_network_calls",
        ],
        "current_enrichment_state": _current_enrichment_state(),
        "milestones": [
            "launch",
            "valuation_proxy_10k",
            "valuation_proxy_15k",
            "valuation_proxy_20k",
            "valuation_proxy_30k",
            "valuation_proxy_50k",
            "valuation_proxy_100k",
            "valuation_proxy_500k",
            "valuation_proxy_1m",
            "pre_collapse",
        ],
        "field_map": field_map,
        "summary": summary,
        "historical_reconstruction_feasibility": _historical_reconstruction_feasibility(),
        "pilot_prioritization": _pilot_prioritization(),
        "recommended_next_execution": _recommended_next_execution(),
        "helius_budget_policy": _helius_budget_policy(),
        "what_not_to_do_next": [
            "do_not_execute_this_plan_without_a_separate_bounded_run_request",
            "do_not_run_a_thesis_from_this_mapping_sprint",
            "do_not_compare_structural_fields_to_outcomes_yet",
            "do_not_build_trading_rules",
            "do_not_use_true_market_cap_labels_until true_market_cap_source_exists".replace(" ", "_"),
            "do_not_run_uncapped_helius_collection",
        ],
    }
    paths = write_axiom_historical_parity_outputs(report, output_dir=output_dir, status_path=status_path)
    return report, paths


def write_axiom_historical_parity_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "axiom_historical_field_map.csv"
    json_path = output / "axiom_historical_parity_summary.json"
    md_path = output / "axiom_historical_parity_summary.md"
    status = Path(status_path)

    _write_csv(report["field_map"], csv_path)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, csv_path, json_path, md_path), encoding="utf-8")
    return {
        "field_map_csv_path": csv_path,
        "summary_json_path": json_path,
        "summary_markdown_path": md_path,
        "status_path": status,
    }


def _row(
    concept: str,
    field: str,
    availability: str,
    coverage: str,
    source: str,
    offline: str,
    helius: str,
    dexscreener: str,
    priority: str,
    side: str,
    blocker: str,
    feasibility: str,
) -> AxiomHistoricalFieldMapRow:
    return AxiomHistoricalFieldMapRow(
        axiom_concept=concept,
        historical_field=field,
        current_availability=availability,
        coverage=coverage,
        source=source,
        local_or_offline=offline,
        helius_needed=helius,
        dexscreener_needed=dexscreener,
        priority=priority,
        entry_or_exit_side=side,
        blocker=blocker,
        feasibility_classification=feasibility,
    )


def _field_map_rows() -> list[AxiomHistoricalFieldMapRow]:
    rows: list[AxiomHistoricalFieldMapRow] = []
    add = rows.append

    for field in [
        "top_holder_share_at_milestone",
        "top_10_holder_share_at_milestone",
        "top_holder_addresses_at_milestone",
        "top_10_holder_addresses_at_milestone",
        "top_holder_balance_at_milestone",
        "top_10_balances_at_milestone",
    ]:
        add(_row("top_holder_structure", field, "pilot_available", "25_mints_75_milestones_pilot_100pct_proxy_coverage", "mint_transaction_balance_delta_replay_v0", "yes", "yes_to_scale_or_validate", "no", "P0", "both", "not_confirmed_full_chain_snapshot", "ready_with_helius_pilot"))
    for field in ["top_holder_change_after_trigger", "top_10_holder_change_after_trigger"]:
        add(_row("top_holder_structure", field, "derivable_after_join", "requires_trigger_window_join", "top_holder_replay_plus_trigger_windows", "yes", "yes_to_scale", "no", "P0", "exit_side", "needs_scaled_replay_and_trigger_join", "ready_with_join"))

    for field in [
        "creator_holder_share_at_milestone",
        "creator_balance_at_milestone",
        "creator_sell_count_after_trigger",
        "creator_net_flow_after_trigger",
        "creator_distribution_proxy",
    ]:
        add(_row("creator_holdings", field, "available_from_observed_delta_replay", "strict_holder_state_rollout_ready", "holder_state_replay_and_normalized_events", "yes", "no_for_proxy_yes_for_full_chain_validation", "no", "P0", "both", "proxy_not_full_chain_state", "ready_with_join"))

    for field in [
        "early_buyer_concentration_proxy",
        "first_5_buyer_share",
        "first_10_buyer_share",
        "first_20_buyer_share",
    ]:
        add(_row("early_buyer_timing", field, "available", "event_classification_coverage_100pct_for_lifecycle_events", "classified_lifecycle_events", "yes", "no", "no", "P0", "entry_side", "none", "ready_now"))
    for field in [
        "first_block_buyer_share",
        "first_10s_buyer_share",
        "early_buyer_share_before_20k",
    ]:
        add(_row("early_buyer_timing", field, "derivable", "event_classification_coverage_100pct_for_lifecycle_events", "classified_lifecycle_events_and_price_milestones", "yes", "no", "no", "P0", "entry_side", "needs_standard_join_for_trigger_specific_fields", "ready_with_join"))

    for field in [
        "creator_linked_wallet_proxy",
        "creator_linked_buyer_count",
        "creator_linked_top10_share",
        "shared_funder_with_creator_flag",
        "creator_to_buyer_transfer_link_proxy",
        "creator_to_top_holder_transfer_link_proxy",
    ]:
        add(_row("creator_linked_wallets", field, "partial", "funding_lineage_partial_needs_data", "creator_transfer_history_and_top_holder_replay", "partial", "yes", "no", "P0", "entry_side", "needs_creator_funder_transfer_graph_pilot", "ready_with_helius_pilot"))

    for field in [
        "bundle_proxy_share",
        "time_linked_funding_group_count",
        "same_funder_group_count",
        "similar_amount_funding_group_count",
        "synchronized_buyer_group_count",
        "largest_cluster_share_proxy",
    ]:
        add(_row("bundle_proxy", field, "partial", "entity_proxy_ready_but_funding_groups_incomplete", "entity_proxy_rollout_and_funding_lineage_pilot", "partial", "yes_for_funding_groups", "no", "P0", "entry_side", "needs_creator_funder_transfer_graph_pilot", "ready_with_helius_pilot"))

    for field in [
        "lp_burned_flag",
        "lp_burn_time",
        "canonical_pool_status",
        "pool_creation_time",
        "lp_status_source",
        "lp_status_confidence",
    ]:
        add(_row("liquidity_pool_status", field, "sparse_or_unverified", "migration_pool_observability_sparse", "pool_creation_and_migration_labels", "partial", "possibly", "possibly", "P1", "both", "needs_pool_authority_or_visibility_source_decision", "needs_parser_repair"))

    for field in [
        "holder_count_at_milestone",
        "holder_growth",
        "holder_churn",
        "holder_retention",
        "holders_per_10k_fdv",
        "fdv_per_holder",
    ]:
        add(_row("holder_distribution", field, "available_from_observed_delta_replay", "strict_cohort_holder_state_ready", "holder_state_rollout_and_fdv_proxy_outcomes", "yes", "no_for_proxy_yes_for_full_chain_validation", "no", "P0", "both", "proxy_not_full_chain_state", "ready_with_join"))

    for field in [
        "pro_trader_proxy_count",
        "wallet_prior_100k_runner_count",
        "wallet_prior_500k_runner_count",
        "wallet_prior_1m_runner_count",
        "wallet_prior_failure_count",
        "wallet_runner_hit_rate_proxy",
        "wallet_quality_proxy",
    ]:
        add(_row("wallet_quality", field, "pilot_available", "1000_wallets_880_with_prior_history_117_launches_covered", "early_buyer_wallet_history_pilot", "partial", "yes_to_scale", "no", "P0", "entry_side", "needs_scaleup_and_runner_label_join", "ready_with_helius_pilot"))

    for field in [
        "dex_paid_flag",
        "dex_boost_status",
        "dex_profile_status",
        "dex_order_status",
        "first_dexscreener_seen_time",
        "visibility_lag_from_launch",
    ]:
        add(_row("dex_visibility", field, "not_currently_reliable", "unknown", "dexscreener_visibility_enrichment", "no", "no", "yes", "P2", "entry_side", "needs_dexscreener_source_policy_and_cache", "blocked"))

    for field in [
        "shared_funding_proxy",
        "common_funder_candidate_id",
        "launches_sharing_funder",
        "wallets_sharing_funder_count",
        "shared_funder_with_creator",
        "shared_funder_with_top_holder",
    ]:
        add(_row("shared_funding", field, "partial", "funding_link_pilot_partial_needs_data", "pre_launch_funding_and_creator_transfer_graph", "partial", "yes", "no", "P0", "entry_side", "needs_creator_funder_transfer_graph_pilot", "ready_with_helius_pilot"))

    for field in [
        "time_linked_funding_proxy",
        "funding_time_cluster_count",
        "similar_funding_amount_cluster_count",
        "funding_age_seconds",
        "funding_amount_sol",
        "funding_cluster_confidence",
    ]:
        add(_row("time_linked_funding", field, "partial", "funding_amount_and_age_available_where_prior_funding_trace_exists", "pre_launch_funding_pilot_and_creator_transfer_graph", "partial", "yes", "no", "P0", "entry_side", "needs_creator_funder_transfer_graph_pilot", "ready_with_helius_pilot"))

    for field in [
        "wallet_buy_amount",
        "wallet_sell_amount",
        "wallet_remaining_balance",
        "wallet_realized_pnl_proxy",
        "wallet_unrealized_position_proxy",
        "wallet_exit_timing",
        "wallet_hold_through_milestone_flag",
    ]:
        add(_row("wallet_position_table", field, "derivable", "lifecycle_events_available_but_wallet_history_scale_needed_for_prior_behavior", "classified_events_price_series_and_wallet_history_pilot", "yes", "yes_for_history_scale", "no", "P0", "both", "pnl_proxy_requires_price_quality_gate", "ready_with_local_raw_replay"))

    return rows


def _summary(field_map: list[dict[str, str]]) -> dict[str, Any]:
    concepts = sorted({row["axiom_concept"] for row in field_map})
    by_feasibility = _count_by(field_map, "feasibility_classification")
    by_priority = _count_by(field_map, "priority")
    helius_fields = [row["historical_field"] for row in field_map if row["helius_needed"] in {"yes", "yes_to_scale", "yes_to_scale_or_validate", "yes_for_funding_groups", "yes_for_history_scale"}]
    blocked_fields = [row["historical_field"] for row in field_map if row["feasibility_classification"] == "blocked"]
    ready_now = [
        row["historical_field"]
        for row in field_map
        if row["feasibility_classification"] in {"ready_now", "ready_with_join", "ready_with_local_raw_replay"}
    ]
    return {
        "axiom_concepts_mapped": len(concepts),
        "historical_fields_mapped": len(field_map),
        "concepts": concepts,
        "by_feasibility": by_feasibility,
        "by_priority": by_priority,
        "ready_now_or_with_local_join_count": len(ready_now),
        "helius_needed_field_count": len(helius_fields),
        "blocked_field_count": len(blocked_fields),
        "ready_now_or_with_local_join_fields": ready_now,
        "helius_needed_fields": helius_fields,
        "blocked_fields": blocked_fields,
    }


def _count_by(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row[key]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _current_enrichment_state() -> dict[str, Any]:
    return {
        "structural_enrichment_master_plan": {
            "readiness": "enrichment_plan_ready_for_combined_offline_and_helius",
            "combined_projected_credits": 70_000,
        },
        "early_buyer_wallet_history_pilot": {
            "commit": "ebac614",
            "network_calls": 1_000,
            "wallets_completed": 1_000,
            "launches_covered": 117,
            "transactions_fetched": 19_769,
            "wallets_with_prior_history": 880,
            "prior_history_coverage_pct": 88.0,
            "readiness": "early_buyer_history_ready_for_review",
        },
        "top_holder_replay_pilot": {
            "commit": "53f5cad",
            "network_calls": 49,
            "mints_completed": 25,
            "milestones_completed": 75,
            "transactions_fetched": 754,
            "replay_proxy_coverage_pct": 100.0,
            "readiness": "top_holder_replay_ready_for_review",
        },
        "creator_funder_transfer_graph_pilot": {
            "status": "not_yet_run",
            "reason": "remaining_highest_value_creator_link_and_funding_cluster_gap",
        },
    }


def _historical_reconstruction_feasibility() -> dict[str, Any]:
    return {
        "top_holder_historical_reconstruction": {
            "can_reconstruct_addresses_from_local_holder_state_replay": "partially",
            "per_wallet_balances_available": "yes_for_observed_delta_replay",
            "helius_token_holder_snapshot_needed": "not_for_proxy_pilot_but_needed_for_full_chain_validation_if_available",
            "historical_token_holder_snapshots_possible_at_milestone_time": "not_assumed_available_from_standard_sources",
            "fallback": "reconstruct_from_mint_transaction_history_balance_deltas",
            "classification": "ready_with_helius_pilot",
        },
        "shared_time_linked_funding_reconstruction": {
            "current_funding_link_can_compute_shared_funders": "partially",
            "creator_funder_transfer_graph_needed": "yes",
            "similar_funding_time_amount_from_preserved_transactions": "yes_where_prior_funding_transactions_are_preserved",
            "classification": "ready_with_helius_pilot",
        },
        "wallet_quality_reconstruction": {
            "early_buyer_wallet_history_pilot_can_produce_features": "yes",
            "pilot_coverage": "1000_wallets_117_launches_880_wallets_with_prior_history",
            "needs_to_scale": "yes_for_broader_launch_coverage",
            "dataset_specific_wallet_quality_proxy_possible": "yes_with_prior_runner_label_join",
            "classification": "ready_with_helius_pilot",
        },
        "creator_linked_wallet_reconstruction": {
            "creator_to_buyer_transfer_detection": "requires_creator_history_graph",
            "creator_to_top_holder_transfer_detection": "requires_creator_plus_top_holder_history_graph",
            "shared_funder_with_creator_detection": "requires_creator_funder_transfer_graph_pilot",
            "classification": "ready_with_helius_pilot",
        },
    }


def _pilot_prioritization() -> list[dict[str, Any]]:
    return [
        {
            "rank": 1,
            "pilot": "creator_funder_transfer_graph_pilot",
            "fields_unlocked": [
                "creator_linked_wallet_proxy",
                "shared_funding_proxy",
                "time_linked_funding_proxy",
                "shared_funder_with_top_holder",
                "creator_to_buyer_transfer_link_proxy",
            ],
            "expected_coverage_gain": "fills_largest_remaining_axiom_parity_gap",
            "estimated_helius_credits": "pilot_cap_25000_or_less",
            "helps_entry": True,
            "helps_exit": False,
            "helps_explain_fdv_efficiency": True,
            "parity_or_deeper": "deeper_historical_data",
            "priority": "P0",
        },
        {
            "rank": 2,
            "pilot": "early_buyer_wallet_history_scaleup",
            "fields_unlocked": [
                "wallet_prior_100k_runner_count",
                "wallet_prior_500k_runner_count",
                "wallet_runner_hit_rate_proxy",
                "wallet_quality_proxy",
            ],
            "expected_coverage_gain": "expands_from_117_launches_to_broader_runner_comparison_set",
            "estimated_helius_credits": "medium_cap_100000_or_less_with_confirmation",
            "helps_entry": True,
            "helps_exit": False,
            "helps_explain_fdv_efficiency": True,
            "parity_or_deeper": "deeper_historical_data",
            "priority": "P0",
        },
        {
            "rank": 3,
            "pilot": "top_holder_milestone_snapshot_pilot_scaleup",
            "fields_unlocked": [
                "top_holder_addresses_at_milestone",
                "top_10_holder_addresses_at_milestone",
                "top_holder_change_after_trigger",
                "top_10_holder_change_after_trigger",
            ],
            "expected_coverage_gain": "scales_successful_25_mint_proxy_pilot",
            "estimated_helius_credits": "pilot_cap_25000_or_less_for_next_step",
            "helps_entry": True,
            "helps_exit": True,
            "helps_explain_fdv_efficiency": True,
            "parity_or_deeper": "parity_plus_historical_behavior",
            "priority": "P0",
        },
        {
            "rank": 4,
            "pilot": "dexscreener_visibility_context",
            "fields_unlocked": [
                "dex_paid_flag",
                "dex_boost_status",
                "dex_profile_status",
                "visibility_lag_from_launch",
            ],
            "expected_coverage_gain": "unknown_until_source_policy_is_defined",
            "estimated_helius_credits": 0,
            "helps_entry": True,
            "helps_exit": False,
            "helps_explain_fdv_efficiency": "possibly",
            "parity_or_deeper": "visible_dashboard_parity",
            "priority": "P2",
        },
        {
            "rank": 5,
            "pilot": "contract_authority_pool_status_context",
            "fields_unlocked": [
                "lp_burned_flag",
                "lp_burn_time",
                "canonical_pool_status",
                "lp_status_confidence",
            ],
            "expected_coverage_gain": "depends_on_pool_authority_source",
            "estimated_helius_credits": "unknown_until_source_decision",
            "helps_entry": True,
            "helps_exit": True,
            "helps_explain_fdv_efficiency": "possibly",
            "parity_or_deeper": "visible_dashboard_parity",
            "priority": "P1",
        },
    ]


def _recommended_next_execution() -> dict[str, Any]:
    return {
        "selection": "B",
        "action": "run_creator_funder_transfer_graph_pilot",
        "execute_now": False,
        "reason": (
            "Top-holder replay and early-buyer wallet history have both produced bounded pilot data. "
            "The largest remaining Axiom-parity gap is creator-linked and funding-cluster structure, "
            "which requires creator and funder transfer graph reconstruction before outcome analysis."
        ),
        "not_selected": {
            "A_top_holder_milestone_snapshot_pilot": "already_has_successful_small_proxy_pilot; scaleup is useful after funding graph gap is closed",
            "C_scale_early_buyer_wallet_history_pilot": "useful but less foundational than shared funding for structural clustering",
            "D_build_local_parity_table_first": "this mapping is the local parity plan; combined audit should follow the next pilot",
            "E_dex_visibility_enrichment": "lower priority and source-policy dependent",
            "F_stop_and_repair_parser_source_gaps": "no blocker found in this mapping sprint",
        },
    }


def _helius_budget_policy() -> dict[str, Any]:
    return {
        "pilot_cap_credits": 25_000,
        "medium_enrichment_cap_credits": 100_000,
        "full_enrichment_cap_credits": 500_000,
        "medium_enrichment_confirmation_threshold_credits": 100_000,
        "blocked_above_credits": 500_000,
        "requires_explicit_execute": True,
        "requires_raw_response_preservation": True,
        "requires_checkpoint_resume": True,
        "stop_on_budget_auth_or_rate_limit_errors": True,
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    recommendation = report["recommended_next_execution"]
    lines = [
        "# Axiom Historical Parity Mapping",
        "",
        "This report maps real-time dashboard-style structural concepts into neutral, replay-safe historical fields for MemeTraderPro.",
        "",
        "## Guardrails",
        "- Research and mapping only.",
        "- No thesis, backtest, validation, paper trading, live trading, strategy generation, optimization, grid search, or ML.",
        "- Neutral proxy field names only.",
        "- True market-cap claims remain blocked; valuation fields use FDV or valuation proxy semantics.",
        "",
        "## Summary",
        f"- Concepts mapped: `{summary['axiom_concepts_mapped']}`",
        f"- Historical fields mapped: `{summary['historical_fields_mapped']}`",
        f"- Ready now or with local joins: `{summary['ready_now_or_with_local_join_count']}`",
        f"- Need Helius to scale or validate: `{summary['helius_needed_field_count']}`",
        f"- Blocked: `{summary['blocked_field_count']}`",
        "",
        "## Feasibility Counts",
    ]
    for key, count in summary["by_feasibility"].items():
        lines.append(f"- {key}: `{count}`")
    lines.extend([
        "",
        "## Pilot Priority",
    ])
    for pilot in report["pilot_prioritization"]:
        lines.append(f"- Rank {pilot['rank']}: `{pilot['pilot']}` - {pilot['expected_coverage_gain']}")
    lines.extend([
        "",
        "## Recommended Next Execution",
        f"- Selection: `{recommendation['selection']}`",
        f"- Action: `{recommendation['action']}`",
        f"- Execute now: `{recommendation['execute_now']}`",
        f"- Reason: {recommendation['reason']}",
        "",
        "## Output",
        "- Field map: `axiom_historical_field_map.csv`",
    ])
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], csv_path: Path, json_path: Path, md_path: Path) -> str:
    summary = report["summary"]
    recommendation = report["recommended_next_execution"]
    ready_fields = ", ".join(summary["ready_now_or_with_local_join_fields"][:12])
    helius_fields = ", ".join(summary["helius_needed_fields"][:12])
    blocked_fields = ", ".join(summary["blocked_fields"])
    return "\n".join([
        "# Axiom Historical Parity Status",
        "",
        "## Why This Matters",
        "The next structural research layer needs historical fields that approximate what real-time token dashboards expose, while keeping MemeTraderPro replay-safe and neutral in its terminology.",
        "",
        "## Current Coverage",
        f"- Concepts mapped: `{summary['axiom_concepts_mapped']}`",
        f"- Historical fields mapped: `{summary['historical_fields_mapped']}`",
        f"- Ready now or with local joins: `{summary['ready_now_or_with_local_join_count']}`",
        f"- Need Helius to scale or validate: `{summary['helius_needed_field_count']}`",
        f"- Blocked: `{summary['blocked_field_count']}`",
        "",
        "## Fields Already Available",
        ready_fields or "None",
        "",
        "## Fields Requiring Helius",
        helius_fields or "None",
        "",
        "## Fields Requiring Parser Or Source Repair",
        blocked_fields or "None",
        "",
        "## Recommended Next Execution Step",
        f"`{recommendation['action']}`",
        "",
        "Do not execute it from this sprint. It needs a separate bounded run request with explicit execute approval.",
        "",
        "## What Should Not Be Done Next",
        "- Do not run a thesis from this mapping sprint.",
        "- Do not compare these fields to outcomes yet.",
        "- Do not build trading rules or alerts.",
        "- Do not run uncapped Helius collection.",
        "- Do not make true market-cap claims.",
        "",
        "## Reports",
        f"- Field map CSV: {csv_path}",
        f"- Summary JSON: {json_path}",
        f"- Summary Markdown: {md_path}",
    ]) + "\n"
