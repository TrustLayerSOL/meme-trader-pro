from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_non_fdv_incremental_information_audit import main


def test_cli_writes_non_fdv_incremental_information_audit(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "creator": "C1",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_20k_but_never_50k",
                "fdv_per_event_at_20k": 1000,
                "fdv_per_buy_at_20k": 2000,
                "fdv_per_active_wallet_at_20k": 500,
                "event_count_at_20k": 10,
                "buy_count_at_20k": 5,
                "active_wallets_at_20k": 2,
                "shared_funding_proxy": True,
            },
            {
                "launch_id": "L2",
                "creator": "C2",
                "launch_date": "2026-01-02",
                "milestone_tier": "reached_1m_plus",
                "fdv_per_event_at_20k": 6000,
                "fdv_per_buy_at_20k": 9000,
                "fdv_per_active_wallet_at_20k": 3000,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 2,
                "active_wallets_at_20k": 5,
                "shared_funding_proxy": False,
            },
        ]
    ).to_parquet(master, index=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_non_fdv_incremental_information_audit",
            "--master-path",
            str(master),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=non_fdv_incremental_information_audit_v0" in output
    assert "rows_analyzed=2" in output
    assert "validation_runs=0" in output
    assert (output_dir / "non_fdv_incremental_information_summary.json").exists()
    assert (output_dir / "non_fdv_feature_incremental_rank.csv").exists()
    assert status.exists()
