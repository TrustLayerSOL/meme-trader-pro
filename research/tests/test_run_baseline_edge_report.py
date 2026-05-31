from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_baseline_edge_report import main


def _row(row_id: str, feature_value: int, forward_return: float) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100 + feature_value,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        age_sec=feature_value,
        event_count=feature_value,
        forward_return=forward_return,
        max_runup=forward_return + 0.1,
        max_drawdown=-0.1,
        label_quality="sparse",
    )


def test_run_baseline_edge_report_cli_writes_json_and_markdown(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    store = ResearchDatasetStore(path=dataset_path)
    store.upsert(_row("row-1", 1, -0.1))
    store.upsert(_row("row-2", 2, 0.2))
    store.upsert(_row("row-3", 3, 0.4))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_baseline_edge_report",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--feature",
            "age_sec",
            "--min-bucket-size",
            "1",
            "--bucket-count",
            "3",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "rows_loaded=3" in output
    assert "rows_analyzed=3" in output
    assert "features_analyzed=1" in output
    assert "output_markdown_path=" in output
    assert "output_json_path=" in output
    assert len(list(output_dir.glob("*.json"))) == 1
    assert len(list(output_dir.glob("*.md"))) == 1
