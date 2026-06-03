from pathlib import Path

import pandas as pd

from research.mtp_research.validation.final_runner_fingerprint_report import (
    READINESS_READY,
    build_feature_family_inventory,
    build_final_runner_fingerprint_report,
    load_enriched_master,
)


def _sample_master(path: Path) -> Path:
    rows = []
    tiers = [
        ("weak-a", "reached_20k_but_never_50k", 20_000, 30_000, 18, 6, 12, 3, 0.2, 0.7, 0.4),
        ("weak-b", "reached_50k_but_never_100k", 20_000, 80_000, 16, 6, 10, 4, 0.1, 0.5, 0.3),
        ("runner-a", "reached_500k_but_never_1m", 20_000, 700_000, 6, 5, 1, 6, 0.8, 0.1, 0.05),
        ("runner-b", "reached_1m_plus", 20_000, 1_200_000, 5, 5, 0, 7, 0.9, 0.0, 0.02),
    ]
    for launch_id, tier, trigger, peak, events, buys, sells, wallets, quality, synthetic, extraction in tiers:
        rows.append(
            {
                "launch_id": launch_id,
                "mint": f"mint-{launch_id}",
                "milestone_tier": tier,
                "trigger_fdv_proxy": trigger,
                "peak_fdv_proxy": peak,
                "event_count_at_20k": events,
                "buy_count_at_20k": buys,
                "sell_count_at_20k": sells,
                "active_wallets_at_20k": wallets,
                "fdv_per_event_at_20k": trigger / events,
                "fdv_per_buy_at_20k": trigger / buys,
                "buy_sell_ratio_at_20k": buys / max(1, sells),
                "smart_money_quality_proxy": quality,
                "early_buyer_with_prior_runner_count": int(quality * 10),
                "early_buyer_wallet_count": 10,
                "synthetic_activity_proxy": synthetic,
                "wash_trade_proxy_share_before_20k": synthetic,
                "creator_extraction_proxy_before_20k": extraction,
                "liquidity_sol_proxy_at_20k": 20 + quality,
                "estimated_slippage_10_sol_at_20k": 0.3 - quality * 0.1,
                "holder_retention_proxy": quality,
                "holder_churn_proxy": 1 - quality,
                "top_holder_share_proxy": 0.3,
                "shared_funding_proxy": False,
                "has_liquidity_depth_layer": True,
                "has_synthetic_activity_layer": True,
                "has_creator_extraction_layer": True,
                "has_smart_money_quality_layer": True,
                "has_holder_retention_layer": True,
                "has_bot_sniper_proxy_layer": True,
                "has_metadata_profile_layer": False,
                "has_aggregator_visibility_layer": False,
                "has_lp_control_layer": False,
                "has_priority_fee_layer": False,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_load_enriched_master_uses_parquet_and_jsonl_fallback(tmp_path: Path) -> None:
    parquet = _sample_master(tmp_path / "master.parquet")
    frame = load_enriched_master(parquet)
    assert len(frame) == 4

    jsonl = tmp_path / "master.jsonl"
    frame.to_json(jsonl, orient="records", lines=True)
    assert len(load_enriched_master(tmp_path / "missing.parquet", jsonl_fallback=jsonl)) == 4


def test_feature_family_inventory_marks_unavailable_fields(tmp_path: Path) -> None:
    frame = load_enriched_master(_sample_master(tmp_path / "master.parquet"))
    inventory = build_feature_family_inventory(frame)

    assert "wallet_quality_repeated_buyers" in inventory
    assert "smart_money_quality_proxy" in inventory["wallet_quality_repeated_buyers"]["available_features"]
    assert inventory["unavailable_layers"]["lp_control"]["status"] == "unavailable"
    assert inventory["unavailable_layers"]["priority_fee_contention"]["status"] == "unavailable"
    assert inventory["unavailable_layers"]["true_market_cap"]["status"] == "unavailable"


def test_final_report_schema_guardrails_and_outputs(tmp_path: Path) -> None:
    report, paths = build_final_runner_fingerprint_report(
        master_path=_sample_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "FINAL_STATUS.md",
    )

    assert report["readiness_classification"] == READINESS_READY
    assert report["dataset"]["rows_analyzed"] == 4
    assert report["guardrails"]["thesis_runs"] == 0
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["candidate_fingerprints"]
    assert report["recommendation"]["next_step"] == "ready_for_formal_thesis_selection_from_broad_report"

    for row in report["candidate_fingerprints"]:
        assert {"fingerprint_id", "fingerprint_name", "feature_families_included", "specific_features"} <= set(row)
        text = " ".join(str(value).lower() for value in row.values())
        for blocked in ("insider", "scammer", "manipulator", "wash trader", "guaranteed smart money"):
            assert blocked not in text

    assert paths["summary_json_path"].exists()
    assert paths["summary_markdown_path"].exists()
    assert paths["feature_family_comparison_path"].exists()
    assert paths["candidate_fingerprints_path"].exists()
    assert paths["entry_vs_exit_features_path"].exists()
    assert paths["missing_layer_review_path"].exists()
    assert paths["status_path"].exists()


def test_tier_comparison_has_required_descriptive_schema(tmp_path: Path) -> None:
    report, paths = build_final_runner_fingerprint_report(
        master_path=_sample_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "FINAL_STATUS.md",
    )
    comparison = pd.read_csv(paths["feature_family_comparison_path"])
    required = {
        "feature_family",
        "feature",
        "contrast",
        "coverage_pct",
        "lower_group_median",
        "higher_group_median",
        "direction",
        "effect_size_proxy",
        "direction_stable_across_thresholds",
        "feature_timing",
    }
    assert required <= set(comparison.columns)
    assert report["methodology_flags"].count("no_threshold_optimization") == 1
