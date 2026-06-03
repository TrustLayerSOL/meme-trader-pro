from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_fdv_efficiency_observability_audit import main


def test_cli_writes_fdv_efficiency_observability_audit(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    snapshots = tmp_path / "snapshots.jsonl"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {"launch_id": "L1", "token_mint": "mint-1", "milestone_tier": "reached_100k_but_never_200k"},
        ]
    ).to_parquet(master, index=False)
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "token_mint": "mint-1",
                "launch_ts": 1000,
                "snapshot_ts": 1030,
                "launch_age_seconds": 30,
                "valuation_proxy_usd": 20_000,
                "tx_count": 4,
                "buy_count": 3,
                "sell_count": 1,
                "active_wallets": 2,
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
            },
        ]
    ).to_json(snapshots, orient="records", lines=True)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fdv_efficiency_observability_audit",
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
    assert "report_id=fdv_efficiency_observability_audit_v0" in output
    assert "rows_analyzed=1" in output
    assert "validation_runs=0" in output
    assert (output_dir / "fdv_efficiency_observability_summary.json").exists()
    assert (output_dir / "fdv_efficiency_trigger_observability.csv").exists()
    assert status.exists()
