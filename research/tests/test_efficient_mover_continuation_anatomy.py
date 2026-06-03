from pathlib import Path

import pandas as pd

from research.mtp_research.validation.efficient_mover_continuation_anatomy import (
    REPORT_ID,
    build_efficient_mover_continuation_anatomy,
    build_efficient_mover_universe,
    classify_feature_row,
    label_continuation_paths,
)


def _master(path: Path) -> Path:
    rows = []
    specs = [
        ("weak-a", "reached_20k_but_never_50k", 1000, 1200, 12, 8, 8, 0.9, 0.8, 0.9),
        ("weak-b", "reached_50k_but_never_100k", 1100, 1300, 11, 8, 8, 0.8, 0.7, 0.8),
        ("mid-a", "reached_100k_but_never_200k", 3200, 4200, 8, 5, 6, 0.7, 0.6, 0.7),
        ("mid-b", "reached_200k_but_never_500k", 3300, 4300, 8, 5, 6, 0.6, 0.5, 0.6),
        ("run-a", "reached_500k_but_never_1m", 6200, 8200, 3, 2, 3, 0.2, 0.2, 0.2),
        ("run-b", "reached_1m_plus", 7200, 9200, 2, 2, 3, 0.1, 0.1, 0.1),
    ]
    for idx, (launch_id, tier, fdv_event, fdv_buy, events, buys, wallets, synthetic, extraction, churn) in enumerate(specs):
        rows.append(
            {
                "launch_id": launch_id,
                "token_mint": f"mint-{launch_id}",
                "creator": f"creator-{idx % 2}",
                "launch_date": f"2026-01-0{idx + 1}",
                "milestone_tier": tier,
                "fdv_per_event_at_20k": fdv_event,
                "fdv_per_buy_at_20k": fdv_buy,
                "fdv_per_active_wallet_at_20k": fdv_event / wallets,
                "event_count_at_20k": events,
                "buy_count_at_20k": buys,
                "active_wallets_at_20k": wallets,
                "synthetic_activity_proxy": synthetic,
                "creator_extraction_proxy_before_20k": extraction,
                "smart_money_quality_proxy": 1.0 - synthetic,
                "holder_churn_proxy": churn,
                "estimated_sell_impact_10_sol_at_20k": synthetic,
                "aggregator_visibility_proxy": idx % 2 == 0,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_efficient_mover_universe_uses_fixed_quantile_support(tmp_path: Path) -> None:
    frame = pd.read_parquet(_master(tmp_path / "master.parquet"))
    bucketed = build_efficient_mover_universe(frame)

    assert "fdv_baseline_support_count" in bucketed.columns
    assert "fdv_baseline_bucket" in bucketed.columns
    assert set(bucketed["fdv_baseline_bucket"]) == {"high_fdv_efficiency", "low_medium_fdv_efficiency"}
    assert bucketed["fdv_baseline_high"].sum() == 2


def test_continuation_and_trap_labels_are_descriptive(tmp_path: Path) -> None:
    frame = label_continuation_paths(build_efficient_mover_universe(pd.read_parquet(_master(tmp_path / "master.parquet"))))

    run = frame[frame["milestone_tier"] == "reached_1m_plus"].iloc[0]
    stall = frame[frame["milestone_tier"] == "reached_100k_but_never_200k"].iloc[0]

    assert run["reached_500k"] is True
    assert run["reached_1m"] is True
    assert run["clean_continuation_proxy"] is True
    assert stall["failed_to_reach_500k"] is True
    assert stall["collapse_proxy"] is True
    assert "win" not in str(frame).lower()


def test_build_anatomy_outputs_broad_feature_candidates(tmp_path: Path) -> None:
    report, paths = build_efficient_mover_continuation_anatomy(
        master_path=_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["efficient_mover_universe"]["rows"] == 2
    assert report["continuation_vs_trap_counts"]["continuation_rows"] == 1
    assert report["continuation_vs_trap_counts"]["trap_or_stall_rows"] == 1
    assert report["feature_comparison"]
    assert paths["summary_json_path"].exists()
    assert paths["summary_markdown_path"].exists()
    assert paths["feature_comparison_path"].exists()
    assert paths["candidate_filters_path"].exists()
    assert paths["entry_vs_exit_features_path"].exists()
    assert paths["status_path"].exists()
    text = str(report).lower() + paths["status_path"].read_text(encoding="utf-8").lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        assert blocked not in text
    assert "no_threshold_optimization" in report["methodology_flags"]


def test_candidate_classification_is_deterministic() -> None:
    row = {
        "coverage_pct": 90,
        "continuation_rows": 30,
        "trap_rows": 30,
        "effect_size_proxy": 0.25,
        "top_date_concentration_pct": 10,
        "top_creator_concentration_pct": 10,
        "feature_timing": "entry_side",
        "higher_values_associated_with": "continuation_proxy",
        "feature_family": "wallet_buyer_quality",
        "feature": "smart_money_quality_proxy",
    }

    assert classify_feature_row(row) == "continuation_positive_candidate"
    row["feature_family"] = "synthetic_authenticity"
    row["feature"] = "synthetic_activity_proxy"
    row["higher_values_associated_with"] = "trap_proxy"
    assert classify_feature_row(row) == "trap_risk_filter_candidate"
    row["feature_timing"] = "path_exit_side"
    assert classify_feature_row(row) == "path_exit_candidate"
    row["coverage_pct"] = 10
    assert classify_feature_row(row) == "data_limited"
