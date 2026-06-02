from pathlib import Path

from research.mtp_research.validation.run_structural_enrichment_master_plan import main


def test_cli_writes_structural_enrichment_master_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_structural_enrichment_master_plan",
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(tmp_path / "STRUCTURAL_ENRICHMENT_MASTER_PLAN_STATUS.md"),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=structural_enrichment_master_plan_v0" in output
    assert "readiness_classification=enrichment_plan_ready_for_combined_offline_and_helius" in output
    assert "data_families_inventoried=" in output
    assert (output_dir / "structural_enrichment_master_plan_summary.json").exists()
    assert (output_dir / "structural_external_fetch_plan.csv").exists()
