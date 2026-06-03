import json
from pathlib import Path

import pandas as pd

from research.mtp_research.validation.tier1_tier2_enrichment import (
    READINESS_PARTIAL,
    estimate_helius_budget,
    run_tier1_tier2_enrichment,
)


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _sample_inputs(tmp_path: Path) -> dict[str, Path]:
    master = _write_parquet(
        tmp_path / "master.parquet",
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "token_mint": "Mint1",
                "creator": "Creator1",
                "launch_ts": 1_700_000_000,
                "milestone_tier": "reached_100k_but_never_200k",
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 120_000,
                "buy_count_at_20k": 4,
                "sell_count_at_20k": 2,
                "event_count_at_20k": 6,
                "active_wallets_at_20k": 3,
                "top_holder_share_proxy": 0.4,
                "top_10_holder_share_proxy": 0.9,
                "creator_holder_share_proxy": 0.1,
                "candidate_funder": "Funder1",
                "shared_funding_proxy": True,
                "launches_sharing_funder": 2,
                "early_buyer_wallet_count": 3,
                "early_buyer_with_prior_runner_count": 2,
                "early_buyer_with_prior_100k_count": 1,
                "early_buyer_with_prior_500k_count": 0,
                "early_buyer_with_prior_1m_count": 0,
                "early_buyer_prior_failure_count": 1,
                "repeated_actor_overlap_proxy": 0.2,
                "repeated_buyer_overlap_proxy": 0.1,
                "synchronized_participation_proxy": 0.3,
                "circularity_proxy": 0.1,
                "churn_proxy": 0.2,
                "token_name": "Dog AI",
                "token_symbol": "DOGAI",
                "metadata_completeness_score": 0.8,
                "metadata_quality_bucket": "complete",
                "pair_visible_on_dexscreener": True,
            },
            {
                "launch_id": "L2",
                "mint": "Mint2",
                "token_mint": "Mint2",
                "creator": "Creator2",
                "launch_ts": 1_700_010_000,
                "milestone_tier": "reached_20k_but_never_50k",
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 25_000,
            },
        ],
    )
    events = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_010,
                "slot": 1,
                "actor": "Buyer1",
                "side": "buy",
                "event_type": "token_accumulation",
                "base_qty": 100,
                "quote_qty": 2.0,
                "metadata_json": {"liquidity_proxy_sol": 20.0},
            },
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_020,
                "slot": 1,
                "actor": "Buyer2",
                "side": "buy",
                "event_type": "token_accumulation",
                "base_qty": 50,
                "quote_qty": 1.0,
                "metadata_json": {"liquidity_proxy_sol": 21.0},
            },
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_050,
                "slot": 2,
                "actor": "Buyer1",
                "side": "sell",
                "event_type": "token_distribution",
                "base_qty": 95,
                "quote_qty": 1.8,
                "metadata_json": {"liquidity_proxy_sol": 18.0},
            },
            {
                "token_mint": "Mint1",
                "block_time": 1_700_000_070,
                "slot": 3,
                "actor": "Creator1",
                "side": "sell",
                "event_type": "token_distribution",
                "base_qty": 10,
                "quote_qty": 0.5,
                "metadata_json": {"liquidity_proxy_sol": 17.0},
            },
        ],
    )
    holder = _write_parquet(
        tmp_path / "holder.parquet",
        [
            {"launch_id": "L1", "snapshot_age_seconds": 30, "holder_count": 2, "holder_retention_proxy": 1.0, "holder_churn_proxy": 0.0, "new_holder_count": 2, "exited_holder_count": 0},
            {"launch_id": "L1", "snapshot_age_seconds": 180, "holder_count": 3, "holder_retention_proxy": 0.8, "holder_churn_proxy": 0.2, "new_holder_count": 1, "exited_holder_count": 0},
            {"launch_id": "L1", "snapshot_age_seconds": 600, "holder_count": 2, "holder_retention_proxy": 0.6, "holder_churn_proxy": 0.4, "new_holder_count": 0, "exited_holder_count": 1},
        ],
    )
    visibility = _write_parquet(
        tmp_path / "visibility.parquet",
        [{"launch_id": "L1", "dexscreener_profile_present": True, "pair_visible_on_dexscreener": True, "visibility_lag_from_launch": 50, "visibility_confidence": "medium"}],
    )
    metadata = _write_parquet(
        tmp_path / "metadata.parquet",
        [{"launch_id": "L1", "metadata_available": True, "metadata_completeness_score": 0.8, "metadata_quality_bucket": "complete", "website_present": True}],
    )
    topicality = _write_parquet(
        tmp_path / "topicality.parquet",
        [{"launch_id": "L1", "token_name": "Dog AI", "token_symbol": "DOGAI", "narrative_bucket": "animal", "narrative_confidence": "medium"}],
    )
    return {
        "master": master,
        "events": events,
        "holder_state": holder,
        "visibility": visibility,
        "metadata_quality": metadata,
        "topicality": topicality,
    }


def test_helius_budget_cap_enforced() -> None:
    assert estimate_helius_budget(target_count=10, max_helius_credits=500_000)["safe_to_execute"] is True
    assert estimate_helius_budget(target_count=600_000, max_helius_credits=500_000)["safe_to_execute"] is False


def test_tier1_tier2_enrichment_writes_required_layers_and_master(tmp_path: Path) -> None:
    inputs = _sample_inputs(tmp_path)
    report, paths = run_tier1_tier2_enrichment(
        data_root=tmp_path / "orico",
        input_paths=inputs,
        output_paths={"status_path": tmp_path / "status.md"},
        execute=True,
    )

    assert report["readiness_classification"] == READINESS_PARTIAL
    assert report["helius"]["requests_used"] == 0
    assert report["guardrails"]["thesis_runs"] == 0
    assert report["target_registry"]["launches"] == 2
    assert report["target_registry"]["mints"] == 2

    required_layers = [
        "liquidity_depth_exit_curve_path",
        "lp_ownership_control_path",
        "synthetic_activity_wash_trade_proxies_path",
        "creator_extraction_pnl_proxy_path",
        "smart_money_entrant_quality_path",
        "holder_retention_churn_path",
        "bot_sniper_bundle_proxies_path",
        "priority_fee_contention_path",
        "metadata_profile_completeness_path",
        "aggregator_visibility_state_path",
        "master_parquet_path",
        "master_jsonl_path",
        "preflight_json_path",
        "coverage_json_path",
        "raw_manifest_path",
    ]
    for key in required_layers:
        assert paths[key].exists(), key

    liquidity = pd.read_parquet(paths["liquidity_depth_exit_curve_path"])
    assert {"liquidity_usd_proxy_at_20k", "estimated_slippage_10_sol_at_20k", "missing_reason"} <= set(liquidity.columns)
    assert liquidity.loc[liquidity["launch_id"] == "L1", "liquidity_sol_proxy_at_20k"].iloc[0] == 21.0

    lp = pd.read_parquet(paths["lp_ownership_control_path"])
    assert {"lp_burned_flag", "lp_control_proxy", "missing_reason"} <= set(lp.columns)

    synthetic = pd.read_parquet(paths["synthetic_activity_wash_trade_proxies_path"])
    assert {"wash_trade_proxy_share_before_20k", "synthetic_activity_proxy"} <= set(synthetic.columns)
    assert synthetic.loc[synthetic["launch_id"] == "L1", "rapid_round_trip_count"].iloc[0] >= 1

    extraction = pd.read_parquet(paths["creator_extraction_pnl_proxy_path"])
    assert {"creator_direct_sell_amount_sol", "creator_extraction_proxy_before_20k"} <= set(extraction.columns)
    assert extraction.loc[extraction["launch_id"] == "L1", "creator_direct_sell_amount_sol"].iloc[0] == 0.5

    smart = pd.read_parquet(paths["smart_money_entrant_quality_path"])
    assert {"smart_money_wallet_share_before_20k", "smart_money_quality_median"} <= set(smart.columns)

    holder = pd.read_parquet(paths["holder_retention_churn_path"])
    assert {"holder_retention_rate_20k_to_100k", "holder_churn_proxy"} <= set(holder.columns)

    bot = pd.read_parquet(paths["bot_sniper_bundle_proxies_path"])
    assert {"first_10s_buyer_share", "bot_sniper_proxy_share", "jito_bundle_data_available"} <= set(bot.columns)
    assert bool(bot["jito_bundle_data_available"].iloc[0]) is False

    fee = pd.read_parquet(paths["priority_fee_contention_path"])
    assert {"priority_fee_contention_proxy", "fee_data_confidence"} <= set(fee.columns)

    metadata = pd.read_parquet(paths["metadata_profile_completeness_path"])
    assert {"profile_completeness_score", "metadata_quality_bucket"} <= set(metadata.columns)

    visibility = pd.read_parquet(paths["aggregator_visibility_state_path"])
    assert {"aggregator_visibility_proxy", "visibility_source"} <= set(visibility.columns)

    master = pd.read_parquet(paths["master_parquet_path"])
    assert {"has_liquidity_depth_layer", "has_tier1_core_layers", "tier1_tier2_missing_reason"} <= set(master.columns)
    assert len(master) == 2


def test_outputs_do_not_use_unsupported_label_columns(tmp_path: Path) -> None:
    inputs = _sample_inputs(tmp_path)
    _, paths = run_tier1_tier2_enrichment(
        data_root=tmp_path / "orico",
        input_paths=inputs,
        output_paths={"status_path": tmp_path / "status.md"},
        execute=True,
    )
    blocked_terms = {"insider", "scammer", "manipulator", "wash_trader"}
    master = pd.read_parquet(paths["master_parquet_path"])
    joined_columns = " ".join(master.columns).lower()
    assert not any(term in joined_columns for term in blocked_terms)
