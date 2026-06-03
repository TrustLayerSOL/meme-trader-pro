from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_creator_net_flow_efficient_mover_thesis import main


def test_cli_writes_creator_net_flow_thesis(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    feature_comparison = tmp_path / "feature.csv"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "token_mint": "mint-1",
                "creator": "C1",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_500k_but_never_1m",
                "fdv_per_event_at_20k": 6000,
                "fdv_per_buy_at_20k": 8000,
                "fdv_per_active_wallet_at_20k": 3000,
                "event_count_at_20k": 3,
                "buy_count_at_20k": 2,
                "active_wallets_at_20k": 2,
                "creator_net_flow_sol_before_20k": 0.0,
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
                "creator_net_flow_sol_before_20k": 0.5,
            },
        ]
    ).to_parquet(master, index=False)
    pd.DataFrame(
        [
            {
                "feature": "creator_net_flow_sol_before_20k",
                "classification": "continuation_positive_candidate",
                "higher_values_associated_with": "continuation_proxy",
                "effect_size_proxy": 0.9,
                "coverage_pct": 100.0,
            }
        ]
    ).to_csv(feature_comparison, index=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_creator_net_flow_efficient_mover_thesis",
            "--master-path",
            str(master),
            "--feature-comparison-path",
            str(feature_comparison),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=creator_net_flow_efficient_mover_thesis_v0" in output
    assert "validation_runs=0" in output
    assert "efficient_mover_rows=" in output
    assert (output_dir / "creator_net_flow_efficient_mover_thesis_summary.json").exists()
    assert (output_dir / "creator_net_flow_tier_comparison.csv").exists()
    assert status.exists()
