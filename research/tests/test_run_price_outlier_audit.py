from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_price_outlier_audit import main


def test_run_price_outlier_audit_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).upsert(
        ResearchDatasetRow(
            row_id="row-1",
            snapshot_id="snapshot-1",
            outcome_id="outcome-1",
            token_mint="mint-1",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            horizon_name="15m",
            horizon_seconds=900,
            entry_price_source="nearest_research_fallback",
            forward_return=1.2,
            max_runup=1.5,
            label_quality="sparse",
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_price_outlier_audit",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "extreme_forward_return_rows=1" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("price_outlier_audit_*.md"))
    assert list(output_dir.glob("price_outlier_audit_*.json"))
