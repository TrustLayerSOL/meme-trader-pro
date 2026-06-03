from pathlib import Path

import pandas as pd

from research.mtp_research.validation.fdv_efficiency_observability_audit import (
    ACTIONABILITY_BUCKETS,
    REPORT_ID,
    build_fdv_efficiency_observability_audit,
    bucket_actionability_window,
    reconstruct_trigger_observability,
)


def _write_snapshots(path: Path) -> Path:
    rows = [
        {
            "launch_id": "L1",
            "token_mint": "mint-1",
            "launch_ts": 1000,
            "snapshot_ts": 1010,
            "launch_age_seconds": 10,
            "valuation_proxy_usd": 9000,
            "tx_count": 3,
            "buy_count": 2,
            "sell_count": 1,
            "active_wallets": 2,
            "unique_actors": 2,
        },
        {
            "launch_id": "L1",
            "token_mint": "mint-1",
            "launch_ts": 1000,
            "snapshot_ts": 1030,
            "launch_age_seconds": 30,
            "valuation_proxy_usd": 20_000,
            "tx_count": 5,
            "buy_count": 4,
            "sell_count": 1,
            "active_wallets": 3,
            "unique_actors": 3,
        },
        {
            "launch_id": "L1",
            "token_mint": "mint-1",
            "launch_ts": 1000,
            "snapshot_ts": 1100,
            "launch_age_seconds": 100,
            "valuation_proxy_usd": 100_000,
            "tx_count": 8,
            "buy_count": 6,
            "sell_count": 2,
            "active_wallets": 4,
            "unique_actors": 4,
        },
        {
            "launch_id": "L1",
            "token_mint": "mint-1",
            "launch_ts": 1000,
            "snapshot_ts": 1400,
            "launch_age_seconds": 400,
            "valuation_proxy_usd": 500_000,
            "tx_count": 12,
            "buy_count": 9,
            "sell_count": 3,
            "active_wallets": 5,
            "unique_actors": 5,
        },
        {
            "launch_id": "L2",
            "token_mint": "mint-2",
            "launch_ts": 2000,
            "snapshot_ts": 2030,
            "launch_age_seconds": 30,
            "valuation_proxy_usd": 12_000,
            "tx_count": 10,
            "buy_count": 5,
            "sell_count": 5,
            "active_wallets": 8,
            "unique_actors": 8,
        },
        {
            "launch_id": "L2",
            "token_mint": "mint-2",
            "launch_ts": 2000,
            "snapshot_ts": 2060,
            "launch_age_seconds": 60,
            "valuation_proxy_usd": 18_000,
            "tx_count": 15,
            "buy_count": 8,
            "sell_count": 7,
            "active_wallets": 9,
            "unique_actors": 9,
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_json(path, orient="records", lines=True)
    return path


def _write_master(path: Path) -> Path:
    pd.DataFrame(
        [
            {"launch_id": "L1", "token_mint": "mint-1", "milestone_tier": "reached_500k_but_never_1m"},
            {"launch_id": "L2", "token_mint": "mint-2", "milestone_tier": "reached_20k_but_never_50k"},
        ]
    ).to_parquet(path, index=False)
    return path


def test_reconstruct_trigger_observability_is_replay_safe(tmp_path: Path) -> None:
    snapshots = pd.read_json(_write_snapshots(tmp_path / "snapshots.jsonl"), lines=True)
    rows, actionability, latency, summary = reconstruct_trigger_observability(snapshots)

    trigger_20k = next(row for row in rows if row["launch_id"] == "L1" and row["trigger_level"] == "20k")

    assert trigger_20k["observable_at_trigger"] is True
    assert trigger_20k["leakage_safe"] is True
    assert trigger_20k["event_count_at_trigger"] == 5
    assert trigger_20k["buy_count_at_trigger"] == 4
    assert trigger_20k["sell_count_at_trigger"] == 1
    assert trigger_20k["fdv_per_event_at_trigger"] == 4000
    assert trigger_20k["fdv_per_buy_at_trigger"] == 5000
    assert round(trigger_20k["fdv_per_active_wallet_at_trigger"], 4) == round(20_000 / 3, 4)
    assert trigger_20k["feature_window_max_time"] == 1030
    assert trigger_20k["trigger_time"] <= trigger_20k["feature_window_max_time"]

    time_20k_to_100k = next(
        row for row in actionability if row["launch_id"] == "L1" and row["trigger_level"] == "20k" and row["target_level"] == "100k"
    )
    assert time_20k_to_100k["time_to_target_seconds"] == 70
    assert time_20k_to_100k["actionability_bucket"] == "1m_to_2m"

    gap = next(row for row in latency if row["launch_id"] == "L1" and row["trigger_level"] == "20k")
    assert gap["seconds_since_previous_snapshot"] == 20
    assert gap["seconds_to_next_snapshot"] == 70
    assert gap["snapshot_gap_bucket"] == "15s_to_30s"

    assert summary["coverage_by_trigger"]["20k"]["observable_rows"] == 1


def test_actionability_bucket_boundaries_are_deterministic() -> None:
    assert list(ACTIONABILITY_BUCKETS) == [
        "under_5s",
        "5s_to_15s",
        "15s_to_30s",
        "30s_to_60s",
        "1m_to_2m",
        "2m_to_5m",
        "5m_plus",
        "never",
    ]
    assert bucket_actionability_window(None) == "never"
    assert bucket_actionability_window(4) == "under_5s"
    assert bucket_actionability_window(15) == "5s_to_15s"
    assert bucket_actionability_window(30) == "15s_to_30s"
    assert bucket_actionability_window(300) == "2m_to_5m"
    assert bucket_actionability_window(301) == "5m_plus"


def test_build_audit_writes_outputs_and_blocks_trading_language(tmp_path: Path) -> None:
    report, paths = build_fdv_efficiency_observability_audit(
        master_path=_write_master(tmp_path / "master.parquet"),
        snapshots_path=_write_snapshots(tmp_path / "snapshots.jsonl"),
        output_dir=tmp_path / "reports",
        status_path=tmp_path / "FDV_STATUS.md",
    )

    assert report["report_id"] == REPORT_ID
    assert report["rows_analyzed"] == 2
    assert report["guardrails"]["validation_runs"] == 0
    assert report["guardrails"]["trading_logic_added"] is False
    assert report["classification"] in {
        "fdv_efficiency_observable_and_actionable",
        "fdv_efficiency_observable_but_latency_sensitive",
        "fdv_efficiency_observable_too_late",
        "fdv_efficiency_not_observable_with_current_data",
        "data_limited",
    }
    assert paths["summary_json_path"].exists()
    assert paths["summary_md_path"].exists()
    assert paths["trigger_observability_path"].exists()
    assert paths["actionability_windows_path"].exists()
    assert paths["snapshot_latency_path"].exists()
    assert paths["status_path"].exists()
    text = str(report).lower() + paths["status_path"].read_text(encoding="utf-8").lower()
    for blocked in ("buy rule", "sell rule", "paper trading", "live trading", "profitability claim"):
        assert blocked not in text
    assert "no_threshold_optimization" in report["methodology_flags"]
