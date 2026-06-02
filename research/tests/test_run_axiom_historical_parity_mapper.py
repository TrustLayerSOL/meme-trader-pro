from pathlib import Path

from research.mtp_research.validation.run_axiom_historical_parity_mapper import main


def test_cli_writes_axiom_historical_parity_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    output_dir = tmp_path / "reports"
    status_path = tmp_path / "AXIOM_HISTORICAL_PARITY_STATUS.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_axiom_historical_parity_mapper",
            "--output-dir",
            str(output_dir),
            "--status-path",
            str(status_path),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "report_id=axiom_historical_parity_v0" in output
    assert "readiness_classification=axiom_historical_parity_plan_ready" in output
    assert "axiom_concepts_mapped=" in output
    assert "recommended_next_execution=run_creator_funder_transfer_graph_pilot" in output
    assert (output_dir / "axiom_historical_field_map.csv").exists()
    assert (output_dir / "axiom_historical_parity_summary.json").exists()
    assert (output_dir / "axiom_historical_parity_summary.md").exists()
    assert status_path.exists()
