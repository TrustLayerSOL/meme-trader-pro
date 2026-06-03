"""Tier 1 / Tier 2 structural enrichment for runner fingerprint discovery.

This module is ETL-only. It builds neutral replay-safe proxy fields from
existing local artifacts and writes explicit missing reasons for blocked
fields. It does not run thesis tests, validation, backtests, trading logic, or
strategy generation.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path, data_lake_root


REPORT_ID = "tier1_tier2_enrichment_v0"
READINESS_READY = "tier1_tier2_enrichment_ready_for_final_fingerprint_report"
READINESS_PARTIAL = "tier1_tier2_enrichment_partial_with_documented_gaps"
READINESS_BLOCKED = "tier1_tier2_enrichment_blocked"

DEFAULT_RAW_DIR = data_lake_path("data", "raw", "structural_enrichment", "tier1_tier2_enrichment")
DEFAULT_PARSED_DIR = data_lake_path("data", "backtests", "structural_enrichment", "tier1_tier2_enrichment")
DEFAULT_REPORT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "tier1_tier2_enrichment"
)
DEFAULT_STATUS_PATH = Path("theses/TIER1_TIER2_ENRICHMENT_STATUS.md")

DEFAULT_MASTER_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "full_campaign", "master_enriched_runner_fingerprint.parquet"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_HOLDER_STATE_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.parquet"
)
DEFAULT_ENTITY_PROXY_PATH = data_lake_path("data", "backtests", "entity_proxy", "entity_proxy_strict_cohort.parquet")
DEFAULT_VISIBILITY_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "full_campaign", "visibility_context.parquet"
)
DEFAULT_METADATA_QUALITY_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "full_campaign", "metadata_quality_context.parquet"
)
DEFAULT_TOPICALITY_PATH = data_lake_path(
    "data", "backtests", "structural_enrichment", "full_campaign", "topicality_context.parquet"
)

METHODOLOGY_FLAGS = [
    "data_enrichment_only",
    "not_a_thesis",
    "no_validation",
    "no_backtest",
    "no_walk_forward_validation",
    "no_paper_trading",
    "no_live_trading",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_order_routing",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
]

LAYER_FLAGS = {
    "liquidity_depth": "has_liquidity_depth_layer",
    "lp_control": "has_lp_control_layer",
    "synthetic_activity": "has_synthetic_activity_layer",
    "creator_extraction": "has_creator_extraction_layer",
    "smart_money_quality": "has_smart_money_quality_layer",
    "holder_retention": "has_holder_retention_layer",
    "bot_sniper_proxy": "has_bot_sniper_proxy_layer",
    "priority_fee": "has_priority_fee_layer",
    "metadata_profile": "has_metadata_profile_layer",
    "aggregator_visibility": "has_aggregator_visibility_layer",
}


def run_tier1_tier2_enrichment(
    *,
    data_root: Path | str | None = None,
    input_paths: dict[str, Path | str] | None = None,
    output_paths: dict[str, Path | str] | None = None,
    max_helius_credits: int = 500_000,
    execute: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    started = time.time()
    root = Path(data_root) if data_root is not None else data_lake_root()
    paths = _resolve_paths(root, output_paths)
    inputs = _resolve_inputs(input_paths)
    _ensure_dirs(paths)

    master = _load_optional_frame(inputs["master"])
    events = _events_with_launch(master, _load_optional_frame(inputs["events"]))
    holder_state = _load_optional_frame(inputs["holder_state"])
    entity_proxy = _load_optional_frame(inputs["entity_proxy"])
    visibility_context = _load_optional_frame(inputs["visibility"])
    metadata_quality = _load_optional_frame(inputs["metadata_quality"])
    topicality = _load_optional_frame(inputs["topicality"])

    registry = _target_registry(master, events)
    budget = estimate_helius_budget(
        target_count=0,
        max_helius_credits=max_helius_credits,
        reason="local_replay_safe_artifacts_used_no_new_helius_fetch",
    )
    preflight = {
        "report_id": REPORT_ID,
        "methodology_flags": METHODOLOGY_FLAGS,
        "target_registry": registry,
        "budget": budget,
        "safe_to_execute": bool(budget["safe_to_execute"]),
        "execute_requested": bool(execute),
        "input_paths": {key: str(value) for key, value in inputs.items()},
    }
    _write_json(paths["preflight_json_path"], preflight)
    paths["preflight_markdown_path"].write_text(_preflight_markdown(preflight), encoding="utf-8")

    if not execute or not budget["safe_to_execute"]:
        report = {
            **preflight,
            "readiness_classification": READINESS_BLOCKED if not budget["safe_to_execute"] else READINESS_PARTIAL,
            "helius": {"execute_completed": False, "requests_used": 0, "credits_used": 0},
            "dexscreener": {"calls_used": 0},
            "guardrails": _guardrails(),
            "warnings": ["dry_run_only"] if not execute else ["projected_helius_above_budget"],
            "runtime_seconds": round(time.time() - started, 3),
            "paths": {key: str(value) for key, value in paths.items()},
        }
        _write_json(paths["coverage_json_path"], report)
        paths["coverage_markdown_path"].write_text(_coverage_markdown(report), encoding="utf-8")
        return report, paths

    liquidity = _liquidity_depth_layer(master, events)
    lp_control = _lp_control_layer(master)
    synthetic = _synthetic_activity_layer(master, events, entity_proxy)
    creator_extraction = _creator_extraction_layer(master, events)
    smart_money = _smart_money_layer(master)
    holder_retention = _holder_retention_layer(master, holder_state)
    bot_sniper = _bot_sniper_layer(master, events)
    priority_fee = _priority_fee_layer(master, events)
    metadata_profile = _metadata_profile_layer(master, metadata_quality, topicality)
    aggregator_visibility = _aggregator_visibility_layer(master, visibility_context)

    enriched = _join_layers(
        master,
        [
            liquidity,
            lp_control,
            synthetic,
            creator_extraction,
            smart_money,
            holder_retention,
            bot_sniper,
            priority_fee,
            metadata_profile,
            aggregator_visibility,
        ],
    )
    enriched = _add_master_flags(enriched)
    layer_frames = {
        "liquidity_depth": liquidity,
        "lp_control": lp_control,
        "synthetic_activity": synthetic,
        "creator_extraction": creator_extraction,
        "smart_money_quality": smart_money,
        "holder_retention": holder_retention,
        "bot_sniper_proxy": bot_sniper,
        "priority_fee": priority_fee,
        "metadata_profile": metadata_profile,
        "aggregator_visibility": aggregator_visibility,
    }
    layer_coverage = _layer_coverage(enriched)
    readiness = _readiness(layer_coverage, budget)
    warnings = _warnings(layer_coverage)

    _write_layers(paths, layer_frames, enriched)
    _write_raw_manifest(paths["raw_manifest_path"], inputs, registry)
    report = {
        "report_id": REPORT_ID,
        "readiness_classification": readiness,
        "methodology_flags": METHODOLOGY_FLAGS,
        "launches_enriched": int(len(enriched)),
        "target_registry": registry,
        "budget": budget,
        "helius": {"execute_completed": False, "requests_used": 0, "credits_used": 0},
        "dexscreener": {"calls_used": 0},
        "guardrails": _guardrails(),
        "layer_coverage": layer_coverage,
        "missing_reason_counts": _missing_reason_counts(layer_frames),
        "warnings": warnings,
        "runtime_seconds": round(time.time() - started, 3),
        "paths": {key: str(value) for key, value in paths.items()},
    }
    _write_reports(report, paths, enriched)
    return report, paths


def estimate_helius_budget(
    *,
    target_count: int,
    max_helius_credits: int,
    reason: str = "one_request_equivalent_per_target_planning_estimate",
) -> dict[str, Any]:
    projected = int(target_count)
    return {
        "target_count": int(target_count),
        "projected_helius_requests": projected,
        "projected_helius_credits": projected,
        "max_helius_credits": int(max_helius_credits),
        "budget_gate_status": "within_budget" if projected <= max_helius_credits else "blocked_projected_helius_above_budget",
        "safe_to_execute": bool(projected <= max_helius_credits),
        "reason": reason,
    }


def _resolve_inputs(input_paths: dict[str, Path | str] | None) -> dict[str, Path]:
    defaults = {
        "master": DEFAULT_MASTER_PATH,
        "events": DEFAULT_EVENTS_PATH,
        "holder_state": DEFAULT_HOLDER_STATE_PATH,
        "entity_proxy": DEFAULT_ENTITY_PROXY_PATH,
        "visibility": DEFAULT_VISIBILITY_PATH,
        "metadata_quality": DEFAULT_METADATA_QUALITY_PATH,
        "topicality": DEFAULT_TOPICALITY_PATH,
    }
    if input_paths:
        defaults.update({key: Path(value) for key, value in input_paths.items()})
    return {key: Path(value) for key, value in defaults.items()}


def _resolve_paths(root: Path, overrides: dict[str, Path | str] | None) -> dict[str, Path]:
    parsed = root / "data" / "backtests" / "structural_enrichment" / "tier1_tier2_enrichment"
    reports = root / "data" / "backtests" / "diagnostics" / "reports" / "tier1_tier2_enrichment"
    raw = root / "data" / "raw" / "structural_enrichment" / "tier1_tier2_enrichment"
    paths = {
        "raw_dir": raw,
        "parsed_dir": parsed,
        "report_dir": reports,
        "checkpoint_dir": parsed / "checkpoints",
        "raw_manifest_path": raw / "local_source_manifest.jsonl",
        "preflight_json_path": reports / "tier1_tier2_preflight.json",
        "preflight_markdown_path": reports / "tier1_tier2_preflight.md",
        "coverage_json_path": reports / "tier1_tier2_coverage_summary.json",
        "coverage_markdown_path": reports / "tier1_tier2_coverage_summary.md",
        "field_coverage_matrix_path": reports / "tier1_tier2_field_coverage_matrix.csv",
        "layer_coverage_by_tier_path": reports / "tier1_tier2_layer_coverage_by_tier.csv",
        "status_path": DEFAULT_STATUS_PATH,
        "liquidity_depth_exit_curve_path": parsed / "liquidity_depth_exit_curve.parquet",
        "lp_ownership_control_path": parsed / "lp_ownership_control.parquet",
        "synthetic_activity_wash_trade_proxies_path": parsed / "synthetic_activity_wash_trade_proxies.parquet",
        "creator_extraction_pnl_proxy_path": parsed / "creator_extraction_pnl_proxy.parquet",
        "smart_money_entrant_quality_path": parsed / "smart_money_entrant_quality.parquet",
        "holder_retention_churn_path": parsed / "holder_retention_churn.parquet",
        "bot_sniper_bundle_proxies_path": parsed / "bot_sniper_bundle_proxies.parquet",
        "priority_fee_contention_path": parsed / "priority_fee_contention.parquet",
        "metadata_profile_completeness_path": parsed / "metadata_profile_completeness.parquet",
        "aggregator_visibility_state_path": parsed / "aggregator_visibility_state.parquet",
        "master_parquet_path": parsed / "master_tier1_tier2_enriched_runner_fingerprint.parquet",
        "master_jsonl_path": parsed / "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
        "full_campaign_master_parquet_path": root / "data" / "backtests" / "structural_enrichment" / "full_campaign" / "master_enriched_runner_fingerprint.parquet",
    }
    if overrides:
        for key, value in overrides.items():
            paths[key] = Path(value)
    return paths


def _ensure_dirs(paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        if key.endswith("_dir"):
            path.mkdir(parents=True, exist_ok=True)
    for key, path in paths.items():
        if key.endswith("_path"):
            path.parent.mkdir(parents=True, exist_ok=True)


def _events_with_launch(master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if master.empty or events.empty:
        return pd.DataFrame()
    if "token_mint" not in events.columns:
        return pd.DataFrame()
    launch_map = _select(master, ["launch_id", "mint", "token_mint", "creator", "launch_ts"]).drop_duplicates("token_mint")
    merged = events.merge(launch_map, on="token_mint", how="inner", suffixes=("", "__launch"))
    merged["block_time"] = pd.to_numeric(merged.get("block_time"), errors="coerce")
    merged["launch_ts"] = pd.to_numeric(merged.get("launch_ts"), errors="coerce")
    merged["launch_age_seconds"] = merged["block_time"] - merged["launch_ts"]
    merged["quote_qty"] = pd.to_numeric(merged.get("quote_qty"), errors="coerce")
    merged["base_qty"] = pd.to_numeric(merged.get("base_qty"), errors="coerce")
    return merged


def _target_registry(master: pd.DataFrame, events: pd.DataFrame) -> dict[str, int]:
    return {
        "launches": int(master["launch_id"].nunique()) if "launch_id" in master else 0,
        "mints": int(master["mint"].nunique(dropna=True)) if "mint" in master else 0,
        "pools_or_pairs": int(master.get("pool_address", pd.Series(dtype=object)).nunique(dropna=True)) if not master.empty else 0,
        "creators": int(master.get("creator", pd.Series(dtype=object)).nunique(dropna=True)) if not master.empty else 0,
        "early_buyers": int(events.get("actor", pd.Series(dtype=object)).nunique(dropna=True)) if not events.empty else 0,
        "candidate_funders": int(master.get("candidate_funder", pd.Series(dtype=object)).nunique(dropna=True)) if not master.empty else 0,
        "transaction_signatures": int(events.get("signature", pd.Series(dtype=object)).nunique(dropna=True)) if not events.empty else 0,
    }


def _liquidity_depth_layer(master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = events.groupby("launch_id") if not events.empty and "launch_id" in events.columns else {}
    for _, launch in master.iterrows():
        launch_id = launch["launch_id"]
        ev = grouped.get_group(launch_id).copy() if hasattr(grouped, "groups") and launch_id in grouped.groups else pd.DataFrame()
        liquidity_sol = _event_liquidity_sol(ev)
        quote_volume = _sum_quote(_before_20k(ev))
        at_20k = _max_non_null(liquidity_sol)
        rows.append(
            {
                "launch_id": launch_id,
                "pool_address": launch.get("pool_address"),
                "dex_or_venue": launch.get("venue") or "pumpfun",
                "pool_created_time": launch.get("launch_time"),
                "liquidity_usd_proxy_at_20k": pd.NA,
                "liquidity_sol_proxy_at_20k": at_20k,
                "liquidity_token_proxy_at_20k": _last_non_null(pd.to_numeric(ev.get("base_qty"), errors="coerce")) if not ev.empty else pd.NA,
                "liquidity_usd_proxy_at_50k": pd.NA,
                "liquidity_usd_proxy_at_100k": pd.NA,
                "liquidity_usd_proxy_at_500k": pd.NA,
                "liquidity_usd_proxy_at_1m": pd.NA,
                "exit_liquidity_proxy_at_20k": quote_volume,
                "exit_liquidity_proxy_at_50k": pd.NA,
                "exit_liquidity_proxy_at_100k": pd.NA,
                "estimated_slippage_10_sol_at_20k": _slippage_proxy(10, at_20k),
                "estimated_slippage_25_sol_at_20k": _slippage_proxy(25, at_20k),
                "estimated_slippage_50_sol_at_20k": _slippage_proxy(50, at_20k),
                "estimated_sell_impact_10_sol_at_20k": _slippage_proxy(10, at_20k),
                "estimated_sell_impact_25_sol_at_20k": _slippage_proxy(25, at_20k),
                "liquidity_growth_20k_to_100k": _growth_proxy(liquidity_sol),
                "liquidity_drop_before_collapse": _drop_proxy(liquidity_sol),
                "liquidity_source": "local_lifecycle_event_liquidity_proxy" if pd.notna(at_20k) else None,
                "liquidity_confidence": "medium" if pd.notna(at_20k) else "none",
                "missing_reason": None if pd.notna(at_20k) else "liquidity_proxy_unavailable_in_local_events",
            }
        )
    return pd.DataFrame(rows)


def _lp_control_layer(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in master.iterrows():
        rows.append(
            {
                "launch_id": row["launch_id"],
                "lp_token_mint": pd.NA,
                "lp_total_supply": pd.NA,
                "lp_burned_flag": pd.NA,
                "lp_burned_share": pd.NA,
                "lp_locked_flag": pd.NA,
                "lp_locked_share": pd.NA,
                "lp_holder_count": pd.NA,
                "top_lp_holder_share": pd.NA,
                "top_10_lp_holder_share": pd.NA,
                "creator_lp_holder_share": pd.NA,
                "deployer_lp_holder_share": pd.NA,
                "lp_removed_after_20k": pd.NA,
                "lp_removed_before_collapse": pd.NA,
                "lp_control_proxy": pd.NA,
                "lp_status_source": None,
                "lp_status_confidence": "none",
                "missing_reason": "lp_token_account_history_not_available_in_local_artifacts",
            }
        )
    return pd.DataFrame(rows)


def _synthetic_activity_layer(master: pd.DataFrame, events: pd.DataFrame, entity_proxy: pd.DataFrame) -> pd.DataFrame:
    entity = entity_proxy.drop_duplicates("launch_id").set_index("launch_id") if "launch_id" in entity_proxy else pd.DataFrame()
    rows = []
    grouped = events.groupby("launch_id") if not events.empty and "launch_id" in events.columns else {}
    for _, launch in master.iterrows():
        launch_id = launch["launch_id"]
        ev = grouped.get_group(launch_id).copy() if hasattr(grouped, "groups") and launch_id in grouped.groups else pd.DataFrame()
        early = _before_20k(ev)
        round_trips = _round_trip_counts(early)
        total = len(early)
        proxy_count = round_trips["rapid_round_trip_count"] + round_trips["same_wallet_round_trip_count"]
        proxy_share = proxy_count / total if total else pd.NA
        entity_row = entity.loc[launch_id] if not entity.empty and launch_id in entity.index else {}
        synthetic = _max_numeric([proxy_share, _value(entity_row, "circularity_proxy"), _value(entity_row, "synchronized_participation_proxy")])
        rows.append(
            {
                "launch_id": launch_id,
                "wash_trade_proxy_share_before_20k": proxy_share,
                "wash_trade_proxy_count_before_20k": proxy_count,
                "self_trade_like_events_before_20k": round_trips["same_wallet_round_trip_count"],
                "circular_buy_sell_wallet_count": round_trips["same_wallet_round_trip_count"],
                "same_wallet_round_trip_count": round_trips["same_wallet_round_trip_count"],
                "rapid_round_trip_count": round_trips["rapid_round_trip_count"],
                "matched_size_round_trip_count": round_trips["matched_size_round_trip_count"],
                "repeated_back_and_forth_wallet_pairs": pd.NA,
                "same_funder_trade_group_share": _value(launch, "shared_funding_proxy"),
                "synthetic_activity_proxy": synthetic,
                "synthetic_activity_confidence": "medium" if total else "none",
                "missing_reason": None if total else "no_local_events_before_20k",
            }
        )
    return pd.DataFrame(rows)


def _creator_extraction_layer(master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = events.groupby("launch_id") if not events.empty and "launch_id" in events.columns else {}
    for _, launch in master.iterrows():
        launch_id = launch["launch_id"]
        creator = launch.get("creator")
        ev = grouped.get_group(launch_id).copy() if hasattr(grouped, "groups") and launch_id in grouped.groups else pd.DataFrame()
        creator_events = ev[ev.get("actor").astype(str) == str(creator)] if not ev.empty and pd.notna(creator) else pd.DataFrame()
        buy_sol = _sum_quote(_side_events(creator_events, "buy"))
        sell_sol = _sum_quote(_side_events(creator_events, "sell"))
        linked_count = _int_or_none(launch.get("creator_wallet_relation_proxy_count")) or 0
        rows.append(
            {
                "launch_id": launch_id,
                "creator_direct_buy_amount_sol": buy_sol,
                "creator_direct_sell_amount_sol": sell_sol,
                "creator_net_flow_sol_before_20k": buy_sol - sell_sol if pd.notna(buy_sol) and pd.notna(sell_sol) else pd.NA,
                "creator_net_flow_sol_after_20k": pd.NA,
                "creator_net_flow_sol_before_100k": buy_sol - sell_sol if pd.notna(buy_sol) and pd.notna(sell_sol) else pd.NA,
                "creator_net_flow_sol_before_collapse": buy_sol - sell_sol if pd.notna(buy_sol) and pd.notna(sell_sol) else pd.NA,
                "creator_realized_pnl_proxy": sell_sol - buy_sol if pd.notna(buy_sol) and pd.notna(sell_sol) else pd.NA,
                "creator_linked_wallet_count": linked_count,
                "creator_linked_wallet_buy_amount_sol": pd.NA,
                "creator_linked_wallet_sell_amount_sol": pd.NA,
                "creator_linked_wallet_net_flow_sol": pd.NA,
                "creator_linked_wallet_realized_pnl_proxy": pd.NA,
                "creator_extraction_proxy_before_20k": sell_sol,
                "creator_extraction_proxy_after_20k": pd.NA,
                "creator_extraction_proxy_before_collapse": sell_sol,
                "creator_or_linked_wallet_exit_timing": _first_exit_age(creator_events),
                "extraction_confidence": "medium" if not creator_events.empty else "none",
                "missing_reason": None if not creator_events.empty else "creator_wallet_not_observed_in_local_events",
            }
        )
    return pd.DataFrame(rows)


def _smart_money_layer(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in master.iterrows():
        wallet_count = _num(row.get("early_buyer_wallet_count"))
        prior_runner = _num_or_zero(row.get("early_buyer_with_prior_runner_count"))
        prior_100k = _num_or_zero(row.get("early_buyer_with_prior_100k_count"))
        prior_500k = _num_or_zero(row.get("early_buyer_with_prior_500k_count"))
        prior_1m = _num_or_zero(row.get("early_buyer_with_prior_1m_count"))
        prior_failure = _num_or_zero(row.get("early_buyer_prior_failure_count"))
        quality = _safe_ratio(prior_runner + prior_100k + prior_500k + prior_1m, wallet_count) if wallet_count else pd.NA
        rows.append(
            {
                "launch_id": row["launch_id"],
                "wallet": "launch_aggregate",
                "first_seen_time": row.get("launch_time"),
                "first_seen_relative_seconds": 0,
                "wallet_history_cutoff_time": row.get("launch_time"),
                "prior_launch_count": pd.NA,
                "prior_20k_runner_count": prior_runner,
                "prior_100k_runner_count": prior_100k,
                "prior_500k_runner_count": prior_500k,
                "prior_1m_runner_count": prior_1m,
                "prior_failure_count": prior_failure,
                "prior_runner_rate_proxy": _safe_ratio(prior_runner, wallet_count) if wallet_count else pd.NA,
                "prior_high_tier_runner_rate_proxy": _safe_ratio(prior_100k + prior_500k + prior_1m, wallet_count) if wallet_count else pd.NA,
                "prior_fast_exit_count": pd.NA,
                "prior_hold_through_runner_count": pd.NA,
                "prior_avg_entry_timing": pd.NA,
                "prior_avg_exit_timing": pd.NA,
                "prior_realized_pnl_proxy_if_available": pd.NA,
                "smart_money_quality_proxy": quality,
                "quality_confidence": "medium" if wallet_count else "none",
                "smart_money_wallet_count_before_20k": wallet_count,
                "smart_money_wallet_share_before_20k": _safe_ratio(prior_runner, wallet_count) if wallet_count else pd.NA,
                "smart_money_buy_amount_share_before_20k": pd.NA,
                "smart_money_quality_median": quality,
                "smart_money_quality_max": quality,
                "smart_money_failure_history_share": _safe_ratio(prior_failure, wallet_count) if wallet_count else pd.NA,
                "smart_money_layer_confidence": "medium" if wallet_count else "none",
                "missing_reason": None if wallet_count else "early_buyer_wallet_history_unavailable",
            }
        )
    return pd.DataFrame(rows)


def _holder_retention_layer(master: pd.DataFrame, holder_state: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = holder_state.groupby("launch_id") if not holder_state.empty and "launch_id" in holder_state.columns else {}
    for _, launch in master.iterrows():
        launch_id = launch["launch_id"]
        snapshots = grouped.get_group(launch_id).copy() if hasattr(grouped, "groups") and launch_id in grouped.groups else pd.DataFrame()
        by_age = {int(row["snapshot_age_seconds"]): row for _, row in snapshots.iterrows() if pd.notna(row.get("snapshot_age_seconds"))}
        h20 = _snapshot_value(by_age, 30, "holder_count")
        h50 = _snapshot_value(by_age, 180, "holder_count")
        h100 = _snapshot_value(by_age, 600, "holder_count")
        h500 = _snapshot_value(by_age, 1800, "holder_count")
        rows.append(
            {
                "launch_id": launch_id,
                "holders_at_20k": h20,
                "holders_at_50k": h50,
                "holders_at_100k": h100,
                "holders_at_500k": h500,
                "holders_retained_20k_to_50k": _min_non_null(h20, h50),
                "holders_retained_20k_to_100k": _min_non_null(h20, h100),
                "holders_retained_20k_to_500k": _min_non_null(h20, h500),
                "holder_retention_rate_20k_to_100k": _safe_ratio(_min_non_null(h20, h100), h20) if pd.notna(h20) else pd.NA,
                "new_holders_20k_to_100k": _snapshot_value(by_age, 600, "new_holder_count"),
                "exited_holders_20k_to_100k": _snapshot_value(by_age, 600, "exited_holder_count"),
                "churn_rate_20k_to_100k": _snapshot_value(by_age, 600, "holder_churn_proxy"),
                "median_holding_time_seconds": pd.NA,
                "holding_time_iqr_seconds": pd.NA,
                "fast_exit_holder_share": _snapshot_value(by_age, 600, "holder_churn_proxy"),
                "holder_retention_proxy": _snapshot_value(by_age, 600, "holder_retention_proxy"),
                "holder_churn_proxy": _snapshot_value(by_age, 600, "holder_churn_proxy"),
                "confidence": "medium" if not snapshots.empty else "none",
                "missing_reason": None if not snapshots.empty else "holder_state_replay_unavailable_for_launch",
            }
        )
    return pd.DataFrame(rows)


def _bot_sniper_layer(master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = events.groupby("launch_id") if not events.empty and "launch_id" in events.columns else {}
    for _, launch in master.iterrows():
        launch_id = launch["launch_id"]
        ev = grouped.get_group(launch_id).copy() if hasattr(grouped, "groups") and launch_id in grouped.groups else pd.DataFrame()
        buys = _side_events(ev, "buy")
        early_10 = buys[buys["launch_age_seconds"] <= 10] if not buys.empty else pd.DataFrame()
        early_30 = buys[buys["launch_age_seconds"] <= 30] if not buys.empty else pd.DataFrame()
        total_buyers = buys["actor"].nunique(dropna=True) if not buys.empty and "actor" in buys else 0
        same_slot_count = int(buys.groupby("slot")["actor"].nunique().max()) if not buys.empty and "slot" in buys else 0
        same_second_count = int(buys.groupby("block_time")["actor"].nunique().max()) if not buys.empty and "block_time" in buys else 0
        rows.append(
            {
                "launch_id": launch_id,
                "first_5_buyer_share": _safe_ratio(min(total_buyers, 5), total_buyers) if total_buyers else pd.NA,
                "first_10_buyer_share": _safe_ratio(min(total_buyers, 10), total_buyers) if total_buyers else pd.NA,
                "first_20_buyer_share": _safe_ratio(min(total_buyers, 20), total_buyers) if total_buyers else pd.NA,
                "first_block_buyer_share": _safe_ratio(same_slot_count, total_buyers) if total_buyers else pd.NA,
                "first_10s_buyer_share": _safe_ratio(early_10["actor"].nunique(dropna=True), total_buyers) if total_buyers else pd.NA,
                "first_30s_buyer_share": _safe_ratio(early_30["actor"].nunique(dropna=True), total_buyers) if total_buyers else pd.NA,
                "same_slot_buy_count": same_slot_count,
                "same_slot_buyer_share": _safe_ratio(same_slot_count, total_buyers) if total_buyers else pd.NA,
                "same_second_buy_count": same_second_count,
                "same_second_buyer_share": _safe_ratio(same_second_count, total_buyers) if total_buyers else pd.NA,
                "priority_fee_sniper_count": pd.NA,
                "high_priority_fee_buyer_share": pd.NA,
                "coordinated_timing_proxy": _safe_ratio(max(same_slot_count, same_second_count), total_buyers) if total_buyers else pd.NA,
                "bundle_proxy_share": pd.NA,
                "bot_sniper_proxy_share": _safe_ratio(len(early_10), len(buys)) if len(buys) else pd.NA,
                "bot_sniper_proxy_confidence": "medium" if len(buys) else "none",
                "jito_bundle_data_available": False,
                "missing_reason": None if len(buys) else "buy_event_timing_unavailable",
            }
        )
    return pd.DataFrame(rows)


def _priority_fee_layer(master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, launch in master.iterrows():
        rows.append(
            {
                "launch_id": launch["launch_id"],
                "priority_fee_present_before_20k": pd.NA,
                "priority_fee_tx_count_before_20k": pd.NA,
                "median_priority_fee_before_20k": pd.NA,
                "p90_priority_fee_before_20k": pd.NA,
                "max_priority_fee_before_20k": pd.NA,
                "compute_unit_price_microlamports_median": pd.NA,
                "compute_unit_limit_median": pd.NA,
                "base_fee_total_before_20k": pd.NA,
                "priority_fee_total_before_20k": pd.NA,
                "priority_fee_share_of_total_fees": pd.NA,
                "high_priority_fee_wallet_count": pd.NA,
                "high_priority_fee_buy_share": pd.NA,
                "priority_fee_contention_proxy": pd.NA,
                "fee_data_confidence": "none",
                "missing_reason": "raw_fee_compute_budget_fields_not_joined_in_local_events",
            }
        )
    return pd.DataFrame(rows)


def _metadata_profile_layer(master: pd.DataFrame, metadata_quality: pd.DataFrame, topicality: pd.DataFrame) -> pd.DataFrame:
    base = _select(master, ["launch_id", "token_name", "token_symbol"])
    base = _merge(base, metadata_quality, "launch_id")
    base = _merge(base, topicality, "launch_id")
    rows = []
    for _, row in base.iterrows():
        rows.append(
            {
                "launch_id": row["launch_id"],
                "token_name": _coalesce_value(row, ["token_name", "token_name__new"]),
                "token_symbol": _coalesce_value(row, ["token_symbol", "token_symbol__new"]),
                "name_length": _text_len(_coalesce_value(row, ["token_name", "token_name__new"])),
                "symbol_length": _text_len(_coalesce_value(row, ["token_symbol", "token_symbol__new"])),
                "metadata_uri_present": _truthy(row.get("metadata_uri_present")),
                "image_present": _truthy(row.get("image_present")),
                "website_present": _truthy(row.get("website_present")),
                "twitter_present": _truthy(row.get("twitter_present")),
                "telegram_present": _truthy(row.get("telegram_present")),
                "discord_present": _truthy(row.get("discord_present")),
                "social_link_count": int(sum([_truthy(row.get("website_present")), _truthy(row.get("twitter_present")), _truthy(row.get("telegram_present")), _truthy(row.get("discord_present"))])),
                "profile_completeness_score": _value(row, "metadata_completeness_score"),
                "metadata_quality_bucket": row.get("metadata_quality_bucket"),
                "narrative_bucket_if_deterministic": row.get("narrative_bucket"),
                "metadata_source": row.get("metadata_source"),
                "metadata_confidence": "medium" if _truthy(row.get("metadata_available")) else "none",
                "missing_reason": row.get("metadata_missing_reason") if _present(row.get("metadata_missing_reason")) else (None if _truthy(row.get("metadata_available")) else "metadata_profile_unavailable"),
            }
        )
    return pd.DataFrame(rows)


def _aggregator_visibility_layer(master: pd.DataFrame, visibility_context: pd.DataFrame) -> pd.DataFrame:
    base = _select(master, ["launch_id"])
    base = _merge(base, visibility_context, "launch_id")
    rows = []
    for _, row in base.iterrows():
        pair_present = _truthy(row.get("pair_visible_on_dexscreener"))
        profile_present = _truthy(row.get("dexscreener_profile_present"))
        rows.append(
            {
                "launch_id": row["launch_id"],
                "dexscreener_pair_present": pair_present,
                "dexscreener_pair_created_time": pd.NA,
                "dexscreener_profile_present": profile_present,
                "dexscreener_boost_present": _truthy(row.get("dexscreener_boost_present")),
                "dexscreener_paid_order_present": _truthy(row.get("dexscreener_paid_order_present")),
                "dexscreener_ad_present": pd.NA,
                "visibility_lag_from_launch": row.get("visibility_lag_from_launch"),
                "aggregator_visibility_proxy": 1.0 if pair_present or profile_present else 0.0,
                "visibility_source": row.get("visibility_source"),
                "visibility_confidence": row.get("visibility_confidence") if _present(row.get("visibility_confidence")) else "none",
                "missing_reason": row.get("visibility_attention_missing_reason") if _present(row.get("visibility_attention_missing_reason")) else (None if pair_present or profile_present else "aggregator_visibility_unavailable"),
            }
        )
    return pd.DataFrame(rows)


def _join_layers(master: pd.DataFrame, layers: list[pd.DataFrame]) -> pd.DataFrame:
    result = master.copy()
    for layer in layers:
        result = _merge(result, layer, "launch_id")
    return result.sort_values("launch_id").reset_index(drop=True)


def _add_master_flags(master: pd.DataFrame) -> pd.DataFrame:
    result = master.copy()
    result["has_liquidity_depth_layer"] = result.get("liquidity_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_lp_control_layer"] = result.get("lp_status_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_synthetic_activity_layer"] = result.get("synthetic_activity_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_creator_extraction_layer"] = result.get("extraction_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_smart_money_quality_layer"] = result.get("smart_money_layer_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_holder_retention_layer"] = result.get("confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_bot_sniper_proxy_layer"] = result.get("bot_sniper_proxy_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_priority_fee_layer"] = result.get("fee_data_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_metadata_profile_layer"] = result.get("metadata_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_aggregator_visibility_layer"] = result.get("visibility_confidence", pd.Series(index=result.index)).fillna("none") != "none"
    result["has_tier1_core_layers"] = (
        result["has_liquidity_depth_layer"]
        & result["has_synthetic_activity_layer"]
        & result["has_creator_extraction_layer"]
        & result["has_smart_money_quality_layer"]
    )
    result["has_tier2_core_layers"] = (
        result["has_holder_retention_layer"]
        & result["has_bot_sniper_proxy_layer"]
        & result["has_metadata_profile_layer"]
        & result["has_aggregator_visibility_layer"]
    )
    result["tier1_tier2_enrichment_confidence"] = result.apply(_master_confidence, axis=1)
    result["tier1_tier2_missing_reason"] = result.apply(_master_missing_reason, axis=1)
    return result


def _master_confidence(row: pd.Series) -> str:
    if bool(row.get("has_tier1_core_layers")) and bool(row.get("has_tier2_core_layers")):
        return "local_proxy_core_layers_available"
    if bool(row.get("has_liquidity_depth_layer")) or bool(row.get("has_synthetic_activity_layer")):
        return "local_proxy_partial"
    return "blocked_or_sparse"


def _master_missing_reason(row: pd.Series) -> str | None:
    missing = [name for name, flag in LAYER_FLAGS.items() if not bool(row.get(flag))]
    return ";".join(missing) if missing else None


def _layer_coverage(master: pd.DataFrame) -> dict[str, dict[str, Any]]:
    total = len(master)
    coverage = {}
    for layer, flag in LAYER_FLAGS.items():
        covered = int(master.get(flag, pd.Series(False, index=master.index)).fillna(False).sum())
        coverage[layer] = {
            "covered_rows": covered,
            "total_rows": int(total),
            "missing_rows": int(total - covered),
            "coverage_pct": round((covered / total) * 100, 4) if total else 0.0,
        }
    return coverage


def _readiness(layer_coverage: dict[str, dict[str, Any]], budget: dict[str, Any]) -> str:
    if not budget["safe_to_execute"]:
        return READINESS_BLOCKED
    tier1 = ["liquidity_depth", "synthetic_activity", "creator_extraction", "smart_money_quality"]
    if all(layer_coverage[layer]["covered_rows"] > 0 for layer in tier1):
        return READINESS_PARTIAL
    return READINESS_BLOCKED


def _warnings(layer_coverage: dict[str, dict[str, Any]]) -> list[str]:
    warnings = ["true_market_cap_unavailable", "fdv_proxy_only", "no_thesis_or_validation_run"]
    for layer, values in layer_coverage.items():
        if values["coverage_pct"] == 0:
            warnings.append(f"blocked_layer_{layer}")
        elif values["coverage_pct"] < 100:
            warnings.append(f"partial_layer_{layer}")
    return sorted(set(warnings))


def _missing_reason_counts(layers: dict[str, pd.DataFrame]) -> dict[str, dict[str, int]]:
    result = {}
    for name, frame in layers.items():
        reason_col = "missing_reason" if "missing_reason" in frame.columns else None
        if reason_col is None:
            result[name] = {}
            continue
        values = [str(value) if _present(value) else "none" for value in frame[reason_col].tolist()]
        result[name] = dict(Counter(values))
    return result


def _write_layers(paths: dict[str, Path], layers: dict[str, pd.DataFrame], master: pd.DataFrame) -> None:
    mapping = {
        "liquidity_depth": "liquidity_depth_exit_curve_path",
        "lp_control": "lp_ownership_control_path",
        "synthetic_activity": "synthetic_activity_wash_trade_proxies_path",
        "creator_extraction": "creator_extraction_pnl_proxy_path",
        "smart_money_quality": "smart_money_entrant_quality_path",
        "holder_retention": "holder_retention_churn_path",
        "bot_sniper_proxy": "bot_sniper_bundle_proxies_path",
        "priority_fee": "priority_fee_contention_path",
        "metadata_profile": "metadata_profile_completeness_path",
        "aggregator_visibility": "aggregator_visibility_state_path",
    }
    for layer, key in mapping.items():
        _write_parquet(layers[layer], paths[key])
    _write_parquet(master, paths["master_parquet_path"])
    master.to_json(paths["master_jsonl_path"], orient="records", lines=True, date_format="iso")
    _write_parquet(master, paths["full_campaign_master_parquet_path"])


def _write_raw_manifest(path: Path, inputs: dict[str, Path], registry: dict[str, int]) -> None:
    rows = [
        {
            "source_path": str(source_path),
            "source_exists": source_path.exists(),
            "source_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
            "raw_response_type": "local_artifact_reference",
            "network_calls_used": 0,
            "target_registry": registry,
        }
        for source_path in inputs.values()
    ]
    _write_jsonl(path, rows)


def _write_reports(report: dict[str, Any], paths: dict[str, Path], master: pd.DataFrame) -> None:
    _write_json(paths["coverage_json_path"], report)
    paths["coverage_markdown_path"].write_text(_coverage_markdown(report), encoding="utf-8")
    _field_coverage(master).to_csv(paths["field_coverage_matrix_path"], index=False)
    _layer_coverage_by_tier(master).to_csv(paths["layer_coverage_by_tier_path"], index=False)
    paths["status_path"].parent.mkdir(parents=True, exist_ok=True)
    paths["status_path"].write_text(_status_markdown(report), encoding="utf-8")


def _field_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(frame)
    for column in sorted(frame.columns):
        covered = int(frame[column].notna().sum())
        rows.append({"field": column, "covered_rows": covered, "total_rows": total, "coverage_pct": round((covered / total) * 100, 4) if total else 0.0})
    return pd.DataFrame(rows)


def _layer_coverage_by_tier(master: pd.DataFrame) -> pd.DataFrame:
    if "milestone_tier" not in master.columns:
        return pd.DataFrame()
    rows = []
    for tier, group in master.groupby("milestone_tier", dropna=False):
        for layer, flag in LAYER_FLAGS.items():
            rows.append(
                {
                    "milestone_tier": str(tier),
                    "layer": layer,
                    "covered_rows": int(group.get(flag, pd.Series(False, index=group.index)).fillna(False).sum()),
                    "total_rows": int(len(group)),
                }
            )
    return pd.DataFrame(rows)


def _guardrails() -> dict[str, Any]:
    return {
        "thesis_runs": 0,
        "validation_runs": 0,
        "backtests_run": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "trading_logic_added": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
    }


def _preflight_markdown(preflight: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tier 1 / Tier 2 Enrichment Preflight",
            "",
            f"- Report id: `{preflight['report_id']}`",
            f"- Launches: `{preflight['target_registry']['launches']}`",
            f"- Mints: `{preflight['target_registry']['mints']}`",
            f"- Projected Helius credits: `{preflight['budget']['projected_helius_credits']}`",
            f"- Budget gate: `{preflight['budget']['budget_gate_status']}`",
            f"- Safe to execute: `{preflight['safe_to_execute']}`",
            "",
        ]
    )


def _coverage_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Tier 1 / Tier 2 Enrichment Coverage Summary",
        "",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Launches enriched: `{report.get('launches_enriched', 0)}`",
        f"- Helius credits used: `{report.get('helius', {}).get('credits_used', 0)}`",
        f"- DexScreener calls used: `{report.get('dexscreener', {}).get('calls_used', 0)}`",
        "",
        "## Layer Coverage",
    ]
    for layer, values in report.get("layer_coverage", {}).items():
        lines.append(f"- {layer}: `{values['covered_rows']} / {values['total_rows']}` ({values['coverage_pct']}%)")
    lines.extend(["", "This report is coverage-only. It does not run a thesis, validation, backtest, paper/live trading, optimization, or strategy workflow.", ""])
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any]) -> str:
    full = report["paths"]["master_parquet_path"]
    lines = [
        "# Tier 1 / Tier 2 Enrichment Status",
        "",
        "This enrichment was created to add replay-safe execution, liquidity, wallet-quality, holder, metadata, and visibility proxy variables before the final descriptive runner-fingerprint report.",
        "",
        f"- Readiness classification: `{report['readiness_classification']}`",
        f"- Launches enriched: `{report['launches_enriched']}`",
        f"- Helius credits used: `{report['helius']['credits_used']}`",
        f"- DexScreener calls used: `{report['dexscreener']['calls_used']}`",
        f"- Master dataset path: `{full}`",
        "",
        "## Layers",
    ]
    for layer, values in report["layer_coverage"].items():
        status = "completed" if values["coverage_pct"] == 100 else "partial" if values["covered_rows"] else "blocked"
        lines.append(f"- {layer}: `{status}` ({values['covered_rows']} / {values['total_rows']})")
    lines.extend(["", "## Next Recommended Action", "", "Use this enriched master for the final descriptive runner-fingerprint report with documented partial/blocked layers. Do not run thesis promotion or trading logic from this sprint alone.", ""])
    return "\n".join(lines)


def _load_optional_frame(path: Path | str | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    if p.suffix == ".jsonl":
        return pd.read_json(p, orient="records", lines=True)
    if p.suffix == ".csv":
        return pd.read_csv(p)
    return pd.read_parquet(p)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=_json_default) + "\n")


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


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


def _select(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[[column for column in columns if column in frame.columns]].copy() if not frame.empty else pd.DataFrame()


def _merge(left: pd.DataFrame, right: pd.DataFrame, key: str) -> pd.DataFrame:
    if right.empty or key not in right.columns:
        return left
    merged = left.merge(right.drop_duplicates(key), on=key, how="left", suffixes=("", "__new"))
    for column in list(merged.columns):
        if not column.endswith("__new"):
            continue
        original = column.removesuffix("__new")
        if original in merged.columns:
            merged[original] = merged[original].combine_first(merged[column])
            merged = merged.drop(columns=[column])
        else:
            merged = merged.rename(columns={column: original})
    return merged


def _before_20k(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "launch_age_seconds" not in events:
        return events
    return events[events["launch_age_seconds"].notna() & (events["launch_age_seconds"] >= 0) & (events["launch_age_seconds"] <= 1200)]


def _side_events(events: pd.DataFrame, side: str) -> pd.DataFrame:
    if events.empty:
        return events
    text = events.get("side", pd.Series("", index=events.index)).astype(str).str.lower() + " " + events.get("event_type", pd.Series("", index=events.index)).astype(str).str.lower()
    if side == "buy":
        return events[text.str.contains("buy|accumulation|accumulate", regex=True)]
    return events[text.str.contains("sell|distribution|distribute", regex=True)]


def _event_liquidity_sol(events: pd.DataFrame) -> pd.Series:
    if events.empty or "metadata_json" not in events:
        return pd.Series(dtype=float)
    return pd.to_numeric(events["metadata_json"].apply(_metadata_liquidity), errors="coerce")


def _metadata_liquidity(metadata: Any) -> Any:
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        return None
    return metadata.get("liquidity_proxy_sol") or metadata.get("bonding_curve_sol_reserve")


def _round_trip_counts(events: pd.DataFrame) -> dict[str, int]:
    if events.empty or "actor" not in events:
        return {"same_wallet_round_trip_count": 0, "rapid_round_trip_count": 0, "matched_size_round_trip_count": 0}
    same = rapid = matched = 0
    for _, group in events.sort_values("block_time").groupby("actor", dropna=True):
        buys = _side_events(group, "buy")
        sells = _side_events(group, "sell")
        if not buys.empty and not sells.empty:
            same += 1
            first_buy = buys.iloc[0]
            first_sell = sells.iloc[0]
            if pd.notna(first_buy.get("block_time")) and pd.notna(first_sell.get("block_time")) and abs(first_sell["block_time"] - first_buy["block_time"]) <= 120:
                rapid += 1
            buy_qty = _num(first_buy.get("base_qty"))
            sell_qty = _num(first_sell.get("base_qty"))
            if buy_qty and sell_qty and abs(buy_qty - sell_qty) / max(buy_qty, sell_qty) <= 0.1:
                matched += 1
    return {"same_wallet_round_trip_count": same, "rapid_round_trip_count": rapid, "matched_size_round_trip_count": matched}


def _sum_quote(events: pd.DataFrame) -> Any:
    if events.empty or "quote_qty" not in events:
        return 0.0
    value = pd.to_numeric(events["quote_qty"], errors="coerce").sum()
    return float(value) if pd.notna(value) else pd.NA


def _last_non_null(values: pd.Series) -> Any:
    values = values.dropna()
    return values.iloc[-1] if not values.empty else pd.NA


def _max_non_null(values: pd.Series) -> Any:
    values = values.dropna()
    return values.max() if not values.empty else pd.NA


def _slippage_proxy(order_sol: float, liquidity_sol: Any) -> Any:
    liq = _num(liquidity_sol)
    if not liq:
        return pd.NA
    return order_sol / (liq + order_sol)


def _growth_proxy(values: pd.Series) -> Any:
    values = values.dropna()
    if len(values) < 2 or values.iloc[0] == 0:
        return pd.NA
    return (values.iloc[-1] - values.iloc[0]) / abs(values.iloc[0])


def _drop_proxy(values: pd.Series) -> Any:
    values = values.dropna()
    if len(values) < 2:
        return pd.NA
    max_value = values.max()
    if not max_value:
        return pd.NA
    return (max_value - values.iloc[-1]) / max_value


def _first_exit_age(events: pd.DataFrame) -> Any:
    sells = _side_events(events, "sell")
    if sells.empty or "launch_age_seconds" not in sells:
        return pd.NA
    return pd.to_numeric(sells["launch_age_seconds"], errors="coerce").dropna().min()


def _snapshot_value(by_age: dict[int, pd.Series], age: int, field: str) -> Any:
    row = by_age.get(age)
    return row.get(field) if row is not None and field in row else pd.NA


def _min_non_null(left: Any, right: Any) -> Any:
    if pd.isna(left) or pd.isna(right):
        return pd.NA
    return min(left, right)


def _max_numeric(values: list[Any]) -> Any:
    nums = [_num(value) for value in values if pd.notna(value)]
    nums = [value for value in nums if value is not None]
    return max(nums) if nums else pd.NA


def _safe_ratio(num: Any, den: Any) -> Any:
    n = _num(num)
    d = _num(den)
    if d in (None, 0):
        return pd.NA
    return n / d if n is not None else pd.NA


def _num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_or_zero(value: Any) -> float:
    return _num(value) or 0.0


def _int_or_none(value: Any) -> int | None:
    num = _num(value)
    return int(num) if num is not None else None


def _value(row: Any, field: str) -> Any:
    if isinstance(row, pd.Series):
        return row.get(field)
    if isinstance(row, dict):
        return row.get(field)
    return pd.NA


def _coalesce_value(row: pd.Series, fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if _present(value):
            return value
    return pd.NA


def _text_len(value: Any) -> Any:
    return len(str(value)) if _present(value) else pd.NA


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _present(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() not in {"", "none", "nan", "null"}
