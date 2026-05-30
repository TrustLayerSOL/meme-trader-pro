from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_research_dataset_report import main


def test_run_research_dataset_report_cli_prints_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    ResearchDatasetStore(path=dataset_path).upsert(
        ResearchDatasetRow(
            row_id="row-1",
            snapshot_id="snapshot-1",
            outcome_id="outcome-1",
            token_mint="mint-1",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            horizon_name="1m",
            horizon_seconds=60,
            forward_return=0.2,
            label_quality="sparse",
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_research_dataset_report",
            "--dataset-path",
            str(dataset_path),
            "--min-label-quality",
            "sparse",
            "--require-forward-return",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "row_count=1" in output
    assert "token_count=1" in output
    assert "avg_forward_return=0.2" in output
    assert "positive_forward_return_count=1" in output
