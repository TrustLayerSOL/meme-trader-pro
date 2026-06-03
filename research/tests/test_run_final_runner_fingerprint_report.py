from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_final_runner_fingerprint_report import main


def test_cli_writes_final_runner_fingerprint_report(tmp_path: Path, monkeypatch, capsys) -> None:
    master = tmp_path / "master.parquet"
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "milestone_tier": "reached_20k_but_never_50k",
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 35_000,
                "event_count_at_20k": 10,
                "fdv_per_event_at_20k": 2_000,
                "smart_money_quality_proxy": 0.1,
            },
            {
                "launch_id": "L2",
                "mint": "Mint2",
                "milestone_tier": "reached_1m_plus",
                "trigger_fdv_proxy": 20_000,
                "peak_fdv_proxy": 1_200_000,
                "event_count_at_20k": 4,
                "fdv_per_event_at_20k": 5_000,
                "smart_money_quality_proxy": 0.8,
            },
        ]
    ).to_parquet(master, index=False)
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "FINAL_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_final_runner_fingerprint_report",
            "--master-path",
            str(master),
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=final_runner_fingerprint_report_v0" in output
    assert "rows_analyzed=2" in output
    assert "thesis_runs=0" in output
    assert (output_dir / "final_runner_fingerprint_summary.json").exists()
    assert (output_dir / "final_runner_candidate_fingerprints.csv").exists()
    assert status_path.exists()
