from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_efficient_mover_continuation_anatomy import main


def test_cli_writes_efficient_mover_continuation_anatomy(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "token_mint": "mint-1",
                "creator": "C1",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_20k_but_never_50k",
                "fdv_per_event_at_20k": 1000,
                "fdv_per_buy_at_20k": 1000,
                "fdv_per_active_wallet_at_20k": 500,
                "event_count_at_20k": 10,
                "buy_count_at_20k": 7,
                "active_wallets_at_20k": 5,
            },
            {
                "launch_id": "L2",
                "token_mint": "mint-2",
                "creator": "C2",
                "launch_date": "2026-01-02",
                "milestone_tier": "reached_1m_plus",
                "fdv_per_event_at_20k": 7000,
                "fdv_per_buy_at_20k": 9000,
                "fdv_per_active_wallet_at_20k": 4500,
                "event_count_at_20k": 2,
                "buy_count_at_20k": 2,
                "active_wallets_at_20k": 2,
                "synthetic_activity_proxy": 0.1,
            },
        ]
    ).to_parquet(master, index=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_efficient_mover_continuation_anatomy",
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
    assert "report_id=efficient_mover_continuation_anatomy_v0" in output
    assert "validation_runs=0" in output
    assert "efficient_mover_rows=" in output
    assert (output_dir / "efficient_mover_continuation_anatomy_summary.json").exists()
    assert (output_dir / "efficient_mover_feature_comparison.csv").exists()
    assert status.exists()
