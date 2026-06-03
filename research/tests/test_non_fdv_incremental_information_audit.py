from pathlib import Path

import pandas as pd

from research.mtp_research.validation.non_fdv_incremental_information_audit import (
    REPORT_ID,
    build_fdv_baseline_buckets,
    build_non_fdv_incremental_information_audit,
    load_feature_groups,
)


def _master(path: Path) -> Path:
    rows = []
    specs = [
        ("weak-a", "reached_20k_but_never_50k", 1000, 2000, 10, 5, 2, 0.1, True, 0.8),
        ("weak-b", "reached_50k_but_never_100k", 1100, 2100, 9, 5, 2, 0.2, True, 0.7),
        ("mid-a", "reached_100k_but_never_200k", 2500, 3500, 8, 5, 3, 0.3, False, 0.4),
        ("mid-b", "reached_200k_but_never_500k", 3000, 4000, 7, 5, 3, 0.4, False, 0.3),
        ("run-a", "reached_500k_but_never_1m", 6000, 8000, 3, 2, 5, 0.8, False, 0.1),
        ("run-b", "reached_1m_plus", 7000, 9000, 2, 2, 6, 0.9, False, 0.0),
    ]
    for idx, (launch_id, tier, fdv_event, fdv_buy, events, buys, wallets, quality, shared, synthetic) in enumerate(specs):
        rows.append(
            {
                "launch_id": launch_id,
                "mint": f"mint-{launch_id}",
                "creator": f"creator-{idx % 3}",
                "launch_date": f"2026-01-0{idx + 1}",
                "milestone_tier": tier,
                "fdv_per_event_at_20k": fdv_event,
                "fdv_per_buy_at_20k": fdv_buy,
                "fdv_per_active_wallet_at_20k": fdv_event / max(wallets, 1),
                "event_count_at_20k": events,
                "buy_count_at_20k": buys,
                "active_wallets_at_20k": wallets,
                "smart_money_quality_proxy": quality,
                "early_buyer_with_prior_runner_count": idx,
                "shared_funding_proxy": shared,
                "launches_sharing_funder": 4 if shared else 0,
                "top_holder_share_proxy": 0.2 + idx * 0.05,
                "synthetic_activity_proxy": synthetic,
                "creator_extraction_proxy_before_20k": synthetic,
                "estimated_slippage_10_sol_at_20k": 0.3 - quality * 0.1,
                "aggregator_visibility_proxy": quality,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_fdv_bucket_construction_is_deterministic(tmp_path: Path) -> None:
    frame = pd.read_parquet(_master(tmp_path / "master.parquet"))
    first = build_fdv_baseline_buckets(frame)
    second = build_fdv_baseline_buckets(frame)

    assert first["high_fdv_per_event"].equals(second["high_fdv_per_event"])
    assert first["high_fdv_per_buy"].sum() > 0
    assert first["low_event_count"].sum() > 0
    assert first["fdv_baseline_high"].sum() > 0


def test_feature_groups_report_missing_fields(tmp_path: Path) -> None:
    frame = pd.read_parquet(_master(tmp_path / "master.parquet"))
    groups = load_feature_groups(frame)

    assert "wallet_buyer_quality" in groups
    assert "smart_money_quality_proxy" in groups["wallet_buyer_quality"]["available"]
    assert "liquidity_executability" in groups
    assert "liquidity_depth_proxy" in groups["liquidity_executability"]["absent"]


def test_non_fdv_audit_outputs_cross_tabs_and_rankings(tmp_path: Path) -> None:
    report, paths = build_non_fdv_incremental_information_audit(
        master_path=_master(tmp_path / "master.parquet"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["rows_analyzed"] == 6
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["fdv_baseline_summary"]
    assert report["non_fdv_feature_rank"]
    assert report["non_fdv_cross_tabs"]
    assert report["candidate_next_fingerprints"]
    assert paths["summary_json_path"].exists()
    assert paths["fdv_baseline_bucket_summary_path"].exists()
    assert paths["non_fdv_feature_incremental_rank_path"].exists()
    assert paths["non_fdv_cross_tabs_path"].exists()
    assert paths["candidate_next_fingerprints_path"].exists()
    assert paths["status_path"].exists()


def test_missing_fields_and_guardrails_do_not_fail(tmp_path: Path) -> None:
    frame = pd.read_parquet(_master(tmp_path / "master.parquet")).drop(columns=["smart_money_quality_proxy"])
    master = tmp_path / "master_missing.parquet"
    frame.to_parquet(master, index=False)
    report, _ = build_non_fdv_incremental_information_audit(
        master_path=master,
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "STATUS.md",
    )

    classifications = {row["classification"] for row in report["non_fdv_feature_rank"]}
    assert "data_limited" in classifications or "unavailable" in classifications
    text = str(report).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        assert blocked not in text
    assert "no_threshold_optimization" in report["methodology_flags"]
    assert report["guardrails"]["thesis_runs"] == 0
