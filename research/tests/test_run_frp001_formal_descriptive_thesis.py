from pathlib import Path

import pandas as pd

from research.mtp_research.validation.run_frp001_formal_descriptive_thesis import main


def test_cli_runs_frp001_only_and_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    candidates = tmp_path / "candidates.csv"
    master = tmp_path / "master.parquet"
    output_dir = tmp_path / "reports"
    status = tmp_path / "STATUS.md"
    pd.DataFrame(
        [
            {
                "fingerprint_id": "FRP-001",
                "fingerprint_name": "Efficient visible expansion with better wallet-quality proxy",
                "description": "Higher FDV-proxy efficiency and better early buyer history appear together.",
                "feature_families_included": "visible_fdv_flow;wallet_quality_repeated_buyers",
                "specific_features": "fdv_per_event_at_20k;smart_money_quality_proxy",
                "expected_direction": '{"fdv_per_event_at_20k": "higher_in_stronger_runners", "smart_money_quality_proxy": "flat_or_unknown"}',
                "entry_side_vs_path_side_vs_exit_side": "entry_side",
                "coverage": '{"usable_feature_count": 2}',
                "missing_fields": "true market cap",
                "limitations": "descriptive only",
                "what_would_invalidate_it": "direction disappears",
            }
        ]
    ).to_csv(candidates, index=False)
    pd.DataFrame(
        [
            {
                "launch_id": "L1",
                "mint": "Mint1",
                "creator": "Creator1",
                "launch_date": "2026-01-01",
                "milestone_tier": "reached_20k_but_never_50k",
                "fdv_per_event_at_20k": 1000,
                "smart_money_quality_proxy": 0.1,
            },
            {
                "launch_id": "L2",
                "mint": "Mint2",
                "creator": "Creator2",
                "launch_date": "2026-01-02",
                "milestone_tier": "reached_1m_plus",
                "fdv_per_event_at_20k": 5000,
                "smart_money_quality_proxy": 0.7,
            },
        ]
    ).to_parquet(master, index=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_frp001_formal_descriptive_thesis",
            "--candidate-fingerprints-path",
            str(candidates),
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
    assert "report_id=frp001_formal_descriptive_thesis_v0" in output
    assert "fingerprint_id=FRP-001" in output
    assert "rows_analyzed=2" in output
    assert "validation_runs=0" in output
    assert (output_dir / "FRP001_formal_descriptive_thesis_summary.json").exists()
    assert (output_dir / "FRP001_tier_support_table.csv").exists()
    assert status.exists()
