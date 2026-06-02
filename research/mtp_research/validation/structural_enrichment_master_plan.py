"""Master structural enrichment plan for explosive-runner fingerprint discovery."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "structural_enrichment_master_plan_v0"
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "structural_enrichment_master_plan"
)
DEFAULT_STATUS_PATH = Path("theses/STRUCTURAL_ENRICHMENT_MASTER_PLAN_STATUS.md")
WINNER_REPORT_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "explosive_runner_winner_anatomy_report",
    "explosive_runner_winner_anatomy_report_summary.json",
)
STRUCTURAL_REPORT_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "structural_wallet_anatomy",
    "structural_wallet_anatomy_summary.json",
)
REPEATED_BUYER_REPORT_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "repeated_buyer_runner_participation",
    "repeated_buyer_runner_participation_summary.json",
)


def build_structural_enrichment_master_plan(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    context = _load_context()
    inventory = _build_inventory(context)
    coverage_matrix = [_coverage_row(row, context) for row in inventory]
    priority_rank = _priority_rank(coverage_matrix)
    external_fetch_plan = _external_fetch_plan(coverage_matrix)
    helius_budget_plan = _helius_budget_plan(external_fetch_plan)
    recommended_campaign = _recommended_campaign(priority_rank, helius_budget_plan)
    report = {
        "report_id": REPORT_ID,
        "report_type": "structural_enrichment_master_plan",
        "readiness_classification": "enrichment_plan_ready_for_combined_offline_and_helius",
        "methodology_flags": [
            "research_only",
            "planning_and_implementation_readiness_only",
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
        ],
        "context": context,
        "inventory": inventory,
        "coverage_matrix": coverage_matrix,
        "priority_rank": priority_rank,
        "external_fetch_plan": external_fetch_plan,
        "helius_budget_plan": helius_budget_plan,
        "recommended_campaign": recommended_campaign,
        "one_pass_enrichment_design": _one_pass_design(),
        "budget_policy": _budget_policy(),
        "what_not_to_do_next": [
            "do_not_run_a_new_thesis_from_this_sprint",
            "do_not_treat_fdv_efficiency_as_the_complete_answer",
            "do_not_start_uncapped_collection",
            "do_not_collect_fields_without_named_field_targets",
            "do_not_build_execution_or_alerting_logic",
        ],
    }
    paths = write_structural_enrichment_master_plan_outputs(report, output_dir=output_dir, status_path=status_path)
    return report, paths


def write_structural_enrichment_master_plan_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "structural_enrichment_master_plan_summary.json"
    md_path = output / "structural_enrichment_master_plan_summary.md"
    inventory_csv = output / "structural_data_family_inventory.csv"
    coverage_csv = output / "structural_field_coverage_matrix.csv"
    priority_csv = output / "structural_enrichment_priority_rank.csv"
    external_csv = output / "structural_external_fetch_plan.csv"
    helius_csv = output / "helius_enrichment_budget_plan.csv"
    status = Path(status_path)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    _write_csv(report["inventory"], inventory_csv)
    _write_csv(report["coverage_matrix"], coverage_csv)
    _write_csv(report["priority_rank"], priority_csv)
    _write_csv(report["external_fetch_plan"], external_csv)
    _write_csv(report["helius_budget_plan"], helius_csv)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, inventory_csv, coverage_csv, priority_csv, external_csv, helius_csv), encoding="utf-8")
    return {
        "summary_json_path": json_path,
        "summary_markdown_path": md_path,
        "inventory_csv_path": inventory_csv,
        "coverage_matrix_csv_path": coverage_csv,
        "priority_rank_csv_path": priority_csv,
        "external_fetch_plan_path": external_csv,
        "helius_budget_plan_path": helius_csv,
        "status_path": status,
    }


def _load_context() -> dict[str, Any]:
    winner = _read_json(WINNER_REPORT_PATH)
    structural = _read_json(STRUCTURAL_REPORT_PATH)
    repeated = _read_json(REPEATED_BUYER_REPORT_PATH)
    coverage = structural.get("coverage_report") or winner.get("coverage_report") or {}
    trigger_counts = (winner.get("coverage_report") or {}).get("trigger_counts") or {}
    tiers = (winner.get("milestone_tier_summary") or structural.get("milestone_tier_summary") or {})
    return {
        "total_launches": int(coverage.get("total_launches") or 14_809),
        "snapshot_count": int(coverage.get("snapshot_count") or 177_708),
        "event_count": int(coverage.get("event_count") or 674_173),
        "event_coverage_pct": float(coverage.get("event_coverage_pct") or 0.8113),
        "holder_state_coverage_pct": float(coverage.get("holder_state_coverage_pct") or 0.1013),
        "entity_proxy_coverage_pct": float(coverage.get("entity_proxy_coverage_pct") or 0.1013),
        "funding_link_coverage_pct": float(coverage.get("funding_link_coverage_pct") or 0.0450),
        "early_buyer_coverage_pct": float((repeated.get("coverage_report") or {}).get("before_20k_early_buyer_coverage_pct") or 0.0502),
        "repeated_buyer_coverage_pct": float((repeated.get("coverage_report") or {}).get("before_20k_repeated_runner_buyer_coverage_pct") or 0.0269),
        "trigger_counts": trigger_counts,
        "tier_counts": {tier: int(row.get("launch_count") or 0) for tier, row in tiers.items()},
        "source_reports": {
            "winner_anatomy": str(WINNER_REPORT_PATH),
            "structural_wallet_anatomy": str(STRUCTURAL_REPORT_PATH),
            "repeated_buyer_runner_participation": str(REPEATED_BUYER_REPORT_PATH),
        },
    }


def _build_inventory(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    family_specs = [
        ("valuation_price_path_fdv_efficiency", "visible", "both", "local_ready", "P0", [
            "valuation_proxy_usd_snapshots", "first_crossing_10k", "first_crossing_15k", "first_crossing_20k",
            "first_crossing_50k", "first_crossing_100k", "first_crossing_500k", "first_crossing_1m",
            "peak_fdv_proxy", "time_to_peak", "fdv_per_event", "fdv_per_buy", "fdv_per_active_wallet",
            "fdv_per_holder", "valuation_growth_per_event", "valuation_growth_per_buy", "time_between_milestones",
            "max_favorable_excursion_proxy", "max_adverse_excursion_proxy", "trigger_precision",
        ]),
        ("raw_flow_microstructure", "visible_plus_local", "both", "local_ready", "P0", [
            "event_count", "buy_count", "sell_count", "net_buy_count", "buy_sell_ratio", "buy_acceleration",
            "sell_acceleration", "event_acceleration", "sol_volume_proxy", "token_amount_volume",
            "average_buy_size", "median_buy_size", "largest_buy_size", "buys_per_wallet", "events_per_wallet",
            "first_buy_time", "first_sell_time", "buy_burst_timing", "sell_burst_timing", "churn_before_trigger",
        ]),
        ("holder_state_holder_path", "hidden_if_reconstructed", "both", "partial_local", "P0", [
            "holder_count", "holder_count_at_20k", "holder_count_at_100k", "holder_growth", "holder_acceleration",
            "holder_churn", "net_new_holders", "exited_holder_count", "holder_retention_20k_to_100k",
            "holders_per_10k_fdv", "fdv_per_holder", "holder_count_per_event", "holder_state_confidence",
            "observed_replay_vs_full_chain_snapshot_flag", "holder_state_missing_reason",
        ]),
        ("top_holder_structure", "hidden_if_reconstructed", "both", "needs_helius", "P0", [
            "top_holder_share", "top_10_holder_share", "top_20_holder_share", "top_holder_addresses",
            "top_10_holder_addresses", "top_20_holder_addresses", "top_holder_balance", "top_10_balances",
            "top_holder_change_over_time", "top_10_holder_churn", "top_holder_sell_count_after_trigger",
            "top_holder_prior_runner_participation", "top_holder_wallet_history", "top_holder_creator_link_proxy",
            "top_holder_retention_through_100k", "top_holder_exit_before_terminal_drawdown",
        ]),
        ("creator_dev_structure", "hidden_if_reconstructed", "both", "partial_local", "P0", [
            "creator_address", "creator_holder_share", "creator_balance_over_time", "creator_sell_events_before_20k",
            "creator_sell_events_after_20k", "creator_net_flow_before_20k", "creator_prior_launch_count",
            "creator_prior_migration_count", "creator_prior_100k_runner_count", "creator_prior_500k_runner_count",
            "creator_prior_1m_runner_count", "creator_prior_failure_count", "creator_runner_rate_proxy",
            "creator_linked_wallets", "creator_to_buyer_transfers", "creator_to_top_holder_transfers",
            "creator_related_wallet_proxy_count",
        ]),
        ("funding_lineage", "hidden_if_reconstructed", "entry_side", "partial_local_needs_helius", "P0", [
            "fee_payer", "signer", "funding_source_wallet", "candidate_funding_wallet", "prior_funding_wallet",
            "funding_age_before_launch", "funding_amount_sol", "repeated_funder_flag", "common_funder_candidate_id",
            "launches_sharing_funder", "funder_prior_launch_count", "funder_prior_100k_runner_count",
            "funder_prior_1m_runner_count", "funder_to_creator_cluster_proxy", "funder_to_buyer_relationship_proxy",
            "funding_source_confidence",
        ]),
        ("wallet_history_wallet_quality", "hidden_if_reconstructed", "entry_side", "partial_local_needs_helius", "P0", [
            "early_buyer_wallet_addresses", "early_seller_wallet_addresses", "wallet_first_seen_time", "wallet_age_proxy",
            "buyer_prior_launch_participation", "buyer_prior_20k_trigger_participation", "buyer_prior_100k_runner_participation",
            "buyer_prior_500k_runner_participation", "buyer_prior_1m_runner_participation", "buyer_prior_failure_participation",
            "buyer_prior_hold_through_run_proxy", "buyer_runner_rate_proxy", "buyer_average_entry_timing",
            "wallet_funding_behavior", "wallet_repeated_same_creator_participation", "wallet_quality_proxy",
        ]),
        ("repeated_buyer_group_behavior", "hidden_if_reconstructed", "entry_side", "partial_local", "P0", [
            "repeated_early_buyers_across_launches", "repeated_early_buyers_across_same_creator",
            "repeated_early_buyers_across_same_funder", "repeated_early_buyers_in_prior_100k_runners",
            "repeated_early_buyers_in_prior_500k_runners", "repeated_early_buyers_in_prior_1m_runners",
            "early_buyer_group_overlap", "largest_repeated_buyer_group_size", "largest_repeated_buyer_group_share",
            "group_prior_runner_rate_proxy", "group_churn_behavior", "group_distribution_behavior_after_trigger",
        ]),
        ("cluster_coordination_proxies", "hidden_if_reconstructed", "both", "partial_local_needs_helius", "P1", [
            "repeated_actor_overlap_proxy", "repeated_buyer_overlap_proxy", "synchronized_participation_proxy",
            "circularity_proxy", "churn_proxy", "cluster_size_proxy", "largest_cluster_share_proxy",
            "cluster_count", "cluster_concentration", "cluster_sell_behavior", "same_transaction_multi_wallet_links",
            "common_funder_cluster_links", "transfer_graph_cluster_links", "timing_synchronized_cluster_links",
            "bundle_ids_if_available", "cluster_confidence",
        ]),
        ("distribution_exit_behavior", "hidden_if_reconstructed", "exit_side", "partial_local_needs_helius", "P1", [
            "early_buyer_selling_after_trigger", "creator_selling_after_trigger", "top_holder_selling_after_trigger",
            "top_10_holder_selling_after_trigger", "cluster_selling_after_trigger", "repeated_buyer_selling_after_trigger",
            "net_flow_after_trigger", "sell_pressure_before_30pct_drawdown", "holder_collapse_before_drawdown",
            "active_wallet_collapse_before_drawdown", "top_holder_share_drop_before_collapse", "rebound_vs_terminal_drawdown_labels",
            "time_from_drawdown_to_new_high",
        ]),
        ("migration_graduation_reputation", "visible_plus_hidden", "both", "partial_local", "P1", [
            "pumpfun_migrate_event", "pumpswap_graduation", "raydium_migration", "dexscreener_pair_graduation_proxy",
            "migration_timestamp", "migration_source", "migration_confidence", "prior_migrated_count_by_creator",
            "prior_runner_count_by_creator", "prior_failed_launch_count_by_creator", "prior_success_ratio_proxy",
            "dev_reputation_bucket_proxy", "source_provenance", "migration_label_missing_reason",
        ]),
        ("visibility_attention_context", "visible_external", "entry_side", "needs_dexscreener", "P1", [
            "dexscreener_pair_creation_time", "first_dexscreener_detection_time", "dexscreener_profile_status",
            "dexscreener_boost_status", "active_boost_amount", "paid_order_status", "token_profile_links",
            "website_link_presence", "x_link_presence", "telegram_link_presence", "discord_link_presence",
            "token_image_presence", "visibility_surface_source", "visibility_lag_from_launch",
        ]),
        ("social_narrative_context", "visible_external", "entry_side", "needs_external_source", "P2", [
            "token_name", "token_ticker", "meme_category_theme", "topicality_label", "website_presence",
            "x_presence", "telegram_presence", "discord_presence", "external_mentions_count", "non_creator_mentions",
            "social_creation_time", "social_engagement_proxy", "narrative_trend_match", "image_availability",
            "metadata_reuse_proxy", "narrative_freshness", "social_missing_reason",
        ]),
        ("contract_authority_token_mechanics", "visible_onchain", "entry_side", "needs_parser_or_helius", "P1", [
            "mint_authority_status", "freeze_authority_status", "update_authority_status", "token_program",
            "token_2022_flag", "transfer_fee_extension", "metadata_mutability", "canonical_pool_status",
            "venue", "pool_creation_time", "liquidity_add_remove_events", "authority_revocation_timing",
            "contract_safety_confidence", "authority_missing_reason",
        ]),
        ("data_quality_execution_fidelity", "internal_quality", "both", "local_ready", "P0", [
            "snapshot_spacing", "trigger_precision", "exact_trigger_crossing_vs_nearest_snapshot",
            "forward_path_coverage", "source_confidence", "stale_price_flags", "missing_event_windows",
            "duplicate_events", "indexing_lag", "slippage_liquidity_proxy", "market_cap_vs_fdv_distinction",
            "data_source_provenance", "raw_transaction_availability", "normalized_event_confidence",
            "parser_version", "event_timing_gap_around_trigger", "missing_wallet_history_reason",
        ]),
    ]
    for data_family, visibility, side, availability, priority, fields in family_specs:
        for field in fields:
            rows.append(_inventory_row(data_family, field, visibility, side, availability, priority, context))
    return rows


def _inventory_row(
    data_family: str,
    field_name: str,
    visibility: str,
    side: str,
    availability: str,
    priority: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    external_source = _external_source_for(availability)
    return {
        "data_family": data_family,
        "field_name": field_name,
        "description": field_name.replace("_", " "),
        "why_it_matters": _why_it_matters(data_family),
        "entry_exit_side": side,
        "visible_to_average_axiom_or_dexscreener_user": visibility in {"visible", "visible_external", "visible_onchain"},
        "hidden_or_proprietary_if_reconstructed": visibility.startswith("hidden") or "hidden" in visibility,
        "current_availability": availability,
        "current_coverage": _coverage_for_availability(availability, context),
        "local_source_path": _local_source_for(data_family),
        "external_source_candidate": external_source,
        "helius_can_provide": external_source == "helius",
        "estimated_implementation_complexity": _complexity_for(availability),
        "estimated_compute_storage_api_cost": _cost_for(availability),
        "priority": priority,
        "blocker": _blocker_for(availability),
        "recommended_next_action": _next_action_for(availability, priority),
    }


def _coverage_row(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    coverage = float(row["current_coverage"])
    return {
        **row,
        "coverage_all_launches": coverage,
        "coverage_confirmed_20k_triggers": _group_coverage(row, coverage, context, "20k"),
        "coverage_100k_plus_runners": _group_coverage(row, coverage, context, "100k"),
        "coverage_500k_plus_runners": _group_coverage(row, coverage, context, "500k"),
        "coverage_1m_plus_runners": _group_coverage(row, coverage, context, "1m"),
        "coverage_failed_20k_triggers": coverage,
        "coverage_never_reached_20k": coverage,
        "coverage_class": _coverage_class(coverage),
        "feasibility_classification": _feasibility_for(row["current_availability"]),
        "can_explain_fdv_efficiency": row["data_family"] in {
            "wallet_history_wallet_quality",
            "repeated_buyer_group_behavior",
            "cluster_coordination_proxies",
            "funding_lineage",
            "top_holder_structure",
            "raw_flow_microstructure",
        },
        "helps_entry": row["entry_exit_side"] in {"entry_side", "both"},
        "helps_exit": row["entry_exit_side"] in {"exit_side", "both"},
        "helps_risk_avoidance": row["data_family"] in {
            "top_holder_structure",
            "contract_authority_token_mechanics",
            "distribution_exit_behavior",
            "data_quality_execution_fidelity",
        },
        "likely_proprietary_if_reconstructed": row["hidden_or_proprietary_if_reconstructed"],
        "helius_justified": row["external_source_candidate"] == "helius" and row["priority"] in {"P0", "P1"},
        "estimated_helius_credit_range": _credit_range_for(row),
    }


def _priority_rank(coverage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    family_rows: dict[str, list[dict[str, Any]]] = {}
    for row in coverage_rows:
        family_rows.setdefault(row["data_family"], []).append(row)
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for family, rows in sorted(family_rows.items()):
        priority = min((row["priority"] for row in rows), key=lambda value: order[value])
        output.append(
            {
                "data_family": family,
                "priority": priority,
                "field_count": len(rows),
                "ready_now_count": sum(1 for row in rows if row["feasibility_classification"] == "ready_now"),
                "helius_needed_count": sum(1 for row in rows if row["feasibility_classification"] == "needs_bounded_helius_fetch"),
                "expected_value": _expected_value(priority),
                "urgency": _urgency(priority),
                "recommended_next_action": _family_priority_action(family, priority),
            }
        )
    output.append(
        {
            "data_family": "deferred_full_automation_and_modeling",
            "priority": "P3",
            "field_count": 1,
            "ready_now_count": 0,
            "helius_needed_count": 0,
            "expected_value": "low_for_current_sprint",
            "urgency": "defer",
            "recommended_next_action": "defer real-time monitoring and model-heavy work",
        }
    )
    return sorted(output, key=lambda row: (order[row["priority"]], row["data_family"]))


def _external_fetch_plan(coverage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = [
        {
            "plan_id": "top_holder_milestone_snapshot_pilot",
            "data_family": "top_holder_structure",
            "field_targets": "top_holder_addresses;top_10_holder_addresses;top_holder_wallet_history",
            "source": "helius",
            "method_category": "token_holder_snapshot_or_owner_lookup",
            "target_entities": "mints at 20k/100k/500k/1m milestones",
            "scope": "pilot",
            "estimated_calls": 4_000,
            "estimated_credits": 20_000,
            "priority": "P0",
            "expected_field_coverage_gain": "top holder address coverage from unavailable to pilot coverage",
        },
        {
            "plan_id": "early_buyer_wallet_history_pilot",
            "data_family": "wallet_history_wallet_quality",
            "field_targets": "buyer_prior_runner_participation;buyer_prior_failure_participation;wallet_quality_proxy",
            "source": "helius",
            "method_category": "wallet_transaction_history",
            "target_entities": "early buyers from covered 20k trigger launches",
            "scope": "pilot",
            "estimated_calls": 5_000,
            "estimated_credits": 25_000,
            "priority": "P0",
            "expected_field_coverage_gain": "improve repeated buyer coverage beyond current event-only 5 percent window coverage",
        },
        {
            "plan_id": "creator_funder_transfer_graph_pilot",
            "data_family": "funding_lineage",
            "field_targets": "creator_to_buyer_transfers;creator_to_top_holder_transfers;common_funder_links",
            "source": "helius",
            "method_category": "transaction_details_and_wallet_history",
            "target_entities": "creators, candidate funders, selected early buyers",
            "scope": "pilot",
            "estimated_calls": 6_000,
            "estimated_credits": 25_000,
            "priority": "P0",
            "expected_field_coverage_gain": "expand funding and transfer graph from pilot coverage to targeted structural coverage",
        },
        {
            "plan_id": "dexscreener_visibility_context_pilot",
            "data_family": "visibility_attention_context",
            "field_targets": "profile_status;boost_status;link_presence;visibility_lag_from_launch",
            "source": "dexscreener",
            "method_category": "pair_profile_metadata",
            "target_entities": "mints and pairs",
            "scope": "pilot",
            "estimated_calls": 3_000,
            "estimated_credits": 0,
            "priority": "P1",
            "expected_field_coverage_gain": "visibility context coverage for runner and control cohorts",
        },
    ]
    for row in targets:
        row.update(
            {
                "raw_response_storage_path": str(data_lake_path("data", "raw", "structural_enrichment", row["plan_id"])),
                "parsed_output_path": str(data_lake_path("data", "backtests", "structural_enrichment", f"{row['plan_id']}.jsonl")),
                "checkpoint_path": str(data_lake_path("data", "backtests", "structural_enrichment", "checkpoints", f"{row['plan_id']}.json")),
                "stop_conditions": "auth_error;rate_limit;budget_projection_exceeded;coverage_value_not_proven",
                "reason_field_matters": _why_it_matters(row["data_family"]),
            }
        )
    return targets


def _helius_budget_plan(external_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in external_rows:
        if row["source"] != "helius":
            continue
        credits = int(row["estimated_credits"])
        rows.append(
            {
                "plan_id": row["plan_id"],
                "scope": row["scope"],
                "endpoint_or_method_category": row["method_category"],
                "target_entities": row["target_entities"],
                "estimated_calls": row["estimated_calls"],
                "estimated_credits": credits,
                "budget_gate": _budget_gate(credits),
                "requires_explicit_confirmation": credits > 100_000,
                "blocked_above_500k": credits > 500_000,
                "raw_response_storage_path": row["raw_response_storage_path"],
                "parsed_output_path": row["parsed_output_path"],
                "checkpoint_path": row["checkpoint_path"],
                "stop_conditions": row["stop_conditions"],
                "expected_field_coverage_gain": row["expected_field_coverage_gain"],
                "priority": row["priority"],
            }
        )
    rows.append(
        {
            "plan_id": "full_structural_enrichment_ceiling",
            "scope": "full",
            "endpoint_or_method_category": "multiple_capped_field_target_runs",
            "target_entities": "mints;creators;early_buyers;top_holders;funders;specific_transactions",
            "estimated_calls": 100_000,
            "estimated_credits": 500_000,
            "budget_gate": "full_cap_500000",
            "requires_explicit_confirmation": True,
            "blocked_above_500k": False,
            "raw_response_storage_path": str(data_lake_path("data", "raw", "structural_enrichment")),
            "parsed_output_path": str(data_lake_path("data", "backtests", "structural_enrichment")),
            "checkpoint_path": str(data_lake_path("data", "backtests", "structural_enrichment", "checkpoints")),
            "stop_conditions": "stop_before_500k;stop_on_auth_error;stop_on_rate_limit;stop_on_low_field_yield",
            "expected_field_coverage_gain": "complete P0 hidden structural field layer if pilots prove value",
            "priority": "P0",
        }
    )
    return rows


def _recommended_campaign(priority_rows: list[dict[str, Any]], helius_rows: list[dict[str, Any]]) -> dict[str, Any]:
    p0 = [row for row in priority_rows if row["priority"] == "P0"]
    pilot_credits = sum(int(row["estimated_credits"]) for row in helius_rows if row["scope"] == "pilot")
    return {
        "campaign": "B",
        "name": "P0 offline enrichments plus dry-run Helius planners",
        "why": "Current local fields are enough to keep building visible and event-derived structure, but the final fingerprint needs top-holder addresses, broader wallet history, and transfer/funder graph fields that require capped pilots.",
        "exact_next_implementation_sprint": "Implement P0 offline enrichment tables and dry-run planners for top-holder, early-buyer wallet history, and creator/funder transfer graph pilots.",
        "fields_gained": "trigger precision; flow-size distributions; holder replay joins; repeated-buyer joins; funding pilot joins; dry-run Helius target lists",
        "expected_coverage_improvement": "Raise repeated-buyer and holder/funder structural coverage from low or partial to named pilot cohorts before scaling.",
        "estimated_helius_credits": pilot_credits,
        "expected_storage_impact": "low for offline tables; medium for raw Helius pilot responses",
        "expected_runtime": "minutes for offline planning; pilot runtime depends on rate limits",
        "risks": "field yield may be low; top-holder snapshots may need method refinement; wallet histories can duplicate local event data if targets are not strict",
        "success_criteria": "P0 field coverage improves with deterministic provenance and actual credits stay within pilot cap per run",
        "failure_criteria": "pilot cannot assign fields deterministically, exceeds budget gates, or duplicates local data without new field gain",
        "p0_family_count": len(p0),
    }


def _one_pass_design() -> dict[str, list[str]]:
    return {
        "offline_local_enrichments_first": [
            "flow size distributions from normalized events",
            "trigger precision and snapshot gap fields",
            "holder replay joins at milestone ages",
            "repeated-buyer output joins",
            "funding-link pilot joins",
            "migration provenance joins",
        ],
        "parser_repairs_needed": [
            "per-wallet balance replay exports",
            "buyer/seller actor coverage audit by source file",
            "fee payer and signer joins into structural tables",
            "milestone snapshot join normalization",
        ],
        "bounded_helius_fetches_needed": [
            "top-holder address snapshots at key milestones",
            "wallet histories for selected early buyers",
            "wallet histories for selected top holders",
            "creator and funder transfer graph pilots",
            "transaction details for selected signatures only",
        ],
        "other_external_fetches": [
            "DexScreener profile and boost context",
            "DexScreener pair metadata",
            "social/link metadata only after P0 on-chain fields are stable",
        ],
        "fields_to_defer": [
            "costly broad social scraping",
            "full all-time wallet graph",
            "model-heavy clustering",
            "real-time monitoring",
            "any field not needed for entry or exit fingerprinting",
        ],
    }


def _budget_policy() -> dict[str, Any]:
    return {
        "pilot_cap_credits": 25_000,
        "medium_enrichment_cap_credits": 100_000,
        "full_enrichment_cap_credits": 500_000,
        "requires_confirmation_above_credits": 100_000,
        "blocked_above_credits": 500_000,
        "required_process": [
            "dry_run_planner_first",
            "estimate_credits_before_execution",
            "start_with_pilot",
            "preserve_raw_responses",
            "checkpoint_and_resume",
            "stop_on_budget_auth_or_rate_limit_errors",
            "report_actual_credits_used",
            "scale_only_if_pilot_proves_coverage_value",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Structural Enrichment Master Plan",
        "",
        f"Readiness: `{report['readiness_classification']}`",
        "",
        "This is a planning and implementation-readiness artifact. It does not run a thesis, validation, backtest, or execution workflow.",
        "",
        "## Context",
        f"- Launches: {report['context']['total_launches']}",
        f"- Events: {report['context']['event_count']}",
        f"- Snapshots: {report['context']['snapshot_count']}",
        f"- Repeated-buyer coverage before 20k: {report['context']['repeated_buyer_coverage_pct']:.4f}",
        "",
        "## Inventoried Families",
    ]
    for row in report["priority_rank"]:
        lines.append(f"- {row['priority']} {row['data_family']}: {row['recommended_next_action']}")
    lines.extend(["", "## Recommended Campaign", f"{report['recommended_campaign']['campaign']}. {report['recommended_campaign']['name']}", report["recommended_campaign"]["why"], ""])
    lines.extend(["## Helius Budget Policy"])
    for key, value in report["budget_policy"].items():
        if key.endswith("_credits") or key.startswith("requires") or key.startswith("blocked"):
            lines.append(f"- {key}: {value}")
    lines.extend(["", "## What Not To Do Next"])
    for item in report["what_not_to_do_next"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _status_markdown(
    report: dict[str, Any],
    json_path: Path,
    md_path: Path,
    inventory_csv: Path,
    coverage_csv: Path,
    priority_csv: Path,
    external_csv: Path,
    helius_csv: Path,
) -> str:
    p0 = [row for row in report["priority_rank"] if row["priority"] == "P0"]
    p1 = [row for row in report["priority_rank"] if row["priority"] == "P1"]
    return "\n".join(
        [
            "# Structural Enrichment Master Plan Status",
            "",
            "## Why This Master Plan Was Created",
            "The project needs a complete data layer before asking what separates explosive runners from non-runners. This prevents locking onto the cleanest visible field while hidden structural layers remain incomplete.",
            "",
            "## Current Problem",
            "The current reports show FDV-proxy efficiency and partial repeated-buyer structure, but top-holder addresses, expanded wallet history, funder graph, visibility context, and several exit-side fields remain incomplete.",
            "",
            f"Readiness classification: `{report['readiness_classification']}`",
            "",
            "## P0 Priorities",
            *[f"- {row['data_family']}: {row['recommended_next_action']}" for row in p0],
            "",
            "## P1 Priorities",
            *[f"- {row['data_family']}: {row['recommended_next_action']}" for row in p1],
            "",
            "## What Is Ready Now",
            "- valuation and FDV-proxy efficiency context",
            "- normalized flow and event-derived features",
            "- partial holder replay and entity proxy joins",
            "- partial repeated-buyer and funding-link outputs",
            "",
            "## What Is Blocked Or Partial",
            "- top-holder address behavior",
            "- complete creator/funder transfer graph",
            "- expanded early-buyer wallet history",
            "- visibility and attention context",
            "",
            "## Helius Use",
            "- Use Helius only for named field targets with dry-run planners.",
            "- Do not use Helius for broad uncapped crawling or duplicate local data.",
            f"- Pilot cap: {report['budget_policy']['pilot_cap_credits']} credits.",
            f"- Medium cap: {report['budget_policy']['medium_enrichment_cap_credits']} credits.",
            f"- Full cap: {report['budget_policy']['full_enrichment_cap_credits']} credits.",
            "",
            "## Recommended Next Implementation Sprint",
            report["recommended_campaign"]["exact_next_implementation_sprint"],
            "",
            "## What Not To Do Next",
            *[f"- {item}" for item in report["what_not_to_do_next"]],
            "",
            "## Artifacts",
            f"- Summary JSON: {json_path}",
            f"- Summary Markdown: {md_path}",
            f"- Inventory CSV: {inventory_csv}",
            f"- Coverage CSV: {coverage_csv}",
            f"- Priority CSV: {priority_csv}",
            f"- External Fetch CSV: {external_csv}",
            f"- Helius Budget CSV: {helius_csv}",
            "",
        ]
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _why_it_matters(data_family: str) -> str:
    return {
        "valuation_price_path_fdv_efficiency": "anchors visible runner separation without assuming it is the full fingerprint",
        "raw_flow_microstructure": "captures early flow tempo and pressure behind valuation movement",
        "holder_state_holder_path": "checks whether valuation growth is matched by durable participation",
        "top_holder_structure": "reveals concentration and address-level behavior hidden from basic price charts",
        "creator_dev_structure": "captures creator behavior and creator-linked wallet proxies",
        "funding_lineage": "links launches through funding source structure",
        "wallet_history_wallet_quality": "tests whether prior runner participants recur before new runners",
        "repeated_buyer_group_behavior": "captures repeated group participation before milestones",
        "cluster_coordination_proxies": "summarizes overlap, timing, and graph-like structure without unsupported labels",
        "distribution_exit_behavior": "supports later exit-side anatomy without creating sell rules",
        "migration_graduation_reputation": "captures creator reputation and graduation provenance",
        "visibility_attention_context": "separates on-chain structure from public visibility surface effects",
        "social_narrative_context": "adds off-chain context after core on-chain fields are stable",
        "contract_authority_token_mechanics": "captures token mechanics and authority state that may affect trust",
        "data_quality_execution_fidelity": "prevents false fingerprint claims from timing and source gaps",
    }.get(data_family, "supports broad runner fingerprint discovery")


def _coverage_for_availability(availability: str, context: dict[str, Any]) -> float:
    if availability == "local_ready":
        return 0.8
    if availability == "partial_local":
        return max(context["holder_state_coverage_pct"], context["entity_proxy_coverage_pct"])
    if availability == "partial_local_needs_helius":
        return max(context["funding_link_coverage_pct"], context["repeated_buyer_coverage_pct"])
    if availability == "needs_helius":
        return 0.0
    if availability == "needs_dexscreener":
        return 0.0
    if availability == "needs_external_source":
        return 0.0
    if availability == "needs_parser_or_helius":
        return 0.0
    return 0.0


def _external_source_for(availability: str) -> str:
    return {
        "needs_helius": "helius",
        "partial_local_needs_helius": "helius",
        "needs_dexscreener": "dexscreener",
        "needs_external_source": "external_source_decision",
        "needs_parser_or_helius": "helius_or_local_parser",
    }.get(availability, "")


def _local_source_for(data_family: str) -> str:
    if data_family in {"valuation_price_path_fdv_efficiency", "raw_flow_microstructure", "data_quality_execution_fidelity"}:
        return "expanded lifecycle snapshots and normalized lifecycle events"
    if data_family == "holder_state_holder_path":
        return "holder-state replay sidecar"
    if data_family in {"repeated_buyer_group_behavior", "wallet_history_wallet_quality"}:
        return "repeated-buyer report outputs and normalized events"
    if data_family == "funding_lineage":
        return "funding-link pilot sidecar"
    if data_family == "cluster_coordination_proxies":
        return "entity proxy sidecar"
    if data_family == "migration_graduation_reputation":
        return "migration/graduation labels"
    return ""


def _complexity_for(availability: str) -> str:
    if availability == "local_ready":
        return "low"
    if availability in {"partial_local", "partial_local_needs_helius"}:
        return "medium"
    return "high"


def _cost_for(availability: str) -> str:
    if availability == "local_ready":
        return "low_local_compute"
    if availability == "partial_local":
        return "medium_local_compute"
    if "helius" in availability:
        return "bounded_api_and_storage"
    if "dexscreener" in availability:
        return "bounded_external_fetch"
    return "unknown_external_cost"


def _blocker_for(availability: str) -> str:
    return {
        "local_ready": "",
        "partial_local": "coverage_partial_or_join_needed",
        "partial_local_needs_helius": "coverage_partial_needs_targeted_external_enrichment",
        "needs_helius": "requires_bounded_helius_pilot",
        "needs_dexscreener": "requires_bounded_dexscreener_context_fetch",
        "needs_external_source": "requires_source_decision",
        "needs_parser_or_helius": "requires_parser_repair_or_targeted_external_fetch",
    }.get(availability, "unknown_blocker")


def _next_action_for(availability: str, priority: str) -> str:
    if availability == "local_ready":
        return "implement offline enrichment table"
    if availability == "partial_local":
        return "join existing sidecar and audit coverage"
    if "helius" in availability:
        return "create dry-run Helius planner before any fetch"
    if "dexscreener" in availability:
        return "create bounded visibility context planner"
    if priority == "P3":
        return "defer"
    return "decide source before implementation"


def _feasibility_for(availability: str) -> str:
    return {
        "local_ready": "ready_now",
        "partial_local": "ready_with_join",
        "partial_local_needs_helius": "needs_bounded_helius_fetch",
        "needs_helius": "needs_bounded_helius_fetch",
        "needs_dexscreener": "needs_bounded_dexscreener_fetch",
        "needs_external_source": "needs_new_paid_source",
        "needs_parser_or_helius": "ready_with_parser_repair",
    }.get(availability, "blocked_unknown_source")


def _coverage_class(coverage: float) -> str:
    if coverage >= 0.8:
        return "high"
    if coverage >= 0.3:
        return "medium"
    if coverage >= 0.05:
        return "low"
    if coverage > 0:
        return "sparse"
    return "unavailable"


def _group_coverage(row: dict[str, Any], coverage: float, context: dict[str, Any], milestone: str) -> float:
    if row["data_family"] == "valuation_price_path_fdv_efficiency":
        return 0.8
    if milestone in {"100k", "500k", "1m"} and row["data_family"] in {"wallet_history_wallet_quality", "repeated_buyer_group_behavior"}:
        return context["repeated_buyer_coverage_pct"]
    return coverage


def _credit_range_for(row: dict[str, Any]) -> str:
    if row["external_source_candidate"] != "helius":
        return ""
    if row["priority"] == "P0":
        return "5000-25000 pilot; up to 100000 medium with confirmation if needed"
    return "5000-50000 pilot_or_medium"


def _expected_value(priority: str) -> str:
    return {"P0": "very_high", "P1": "high", "P2": "medium", "P3": "defer"}[priority]


def _urgency(priority: str) -> str:
    return {"P0": "now", "P1": "next", "P2": "later", "P3": "defer"}[priority]


def _family_priority_action(family: str, priority: str) -> str:
    if priority == "P0":
        return "include before final runner fingerprint report"
    if priority == "P1":
        return "include if P0 field coverage is stable"
    if priority == "P2":
        return "defer until core on-chain structure is complete"
    return "defer"


def _budget_gate(credits: int) -> str:
    if credits <= 25_000:
        return "pilot_cap_25000"
    if credits <= 100_000:
        return "medium_cap_100000"
    if credits <= 500_000:
        return "full_cap_500000"
    return "blocked_above_500000"
