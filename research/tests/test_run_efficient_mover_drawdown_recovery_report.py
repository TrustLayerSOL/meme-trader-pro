from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_efficient_mover_drawdown_recovery_report import main


def test_cli_writes_efficient_mover_drawdown_recovery_report(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    snapshots = tmp_path / "snapshots.jsonl"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "token_mint": "mint-1",
                "creator": "C1",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_1m_plus",
                "fdv_per_event_at_20k": 7000,
                "fdv_per_buy_at_20k": 9000,
                "fdv_per_active_wallet_at_20k": 4500,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 2,
                "active_wallets_at_20k": 2,
            }
        ]
    ).to_parquet(master, index=False)
    pd.DataFrame(
        [
            {"launch_id": "L1", "token_mint": "mint-1", "snapshot_ts": 1000, "valuation_proxy_usd": 20_000, "tx_count": 2, "buy_count": 2, "sell_count": 0, "active_wallets": 2},
            {"launch_id": "L1", "token_mint": "mint-1", "snapshot_ts": 1030, "valuation_proxy_usd": 100_000, "tx_count": 4, "buy_count": 4, "sell_count": 0, "active_wallets": 3},
            {"launch_id": "L1", "token_mint": "mint-1", "snapshot_ts": 1060, "valuation_proxy_usd": 65_000, "tx_count": 6, "buy_count": 4, "sell_count": 2, "active_wallets": 3},
            {"launch_id": "L1", "token_mint": "mint-1", "snapshot_ts": 1090, "valuation_proxy_usd": 105_000, "tx_count": 8, "buy_count": 6, "sell_count": 2, "active_wallets": 4},
        ]
    ).to_json(snapshots, orient="records", lines=True)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_efficient_mover_drawdown_recovery_report",
            "--master-path",
            str(master),
            "--snapshots-path",
            str(snapshots),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=efficient_mover_drawdown_recovery_report_v0" in output
    assert "validation_runs=0" in output
    assert "efficient_mover_rows=" in output
    assert (output_dir / "efficient_mover_drawdown_recovery_summary.json").exists()
    assert (output_dir / "drawdown_events.csv").exists()
    assert status.exists()
