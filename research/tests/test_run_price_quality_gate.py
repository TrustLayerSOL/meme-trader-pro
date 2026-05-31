import json

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_price_quality_gate import main


def _row(row_id: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": f"mint-{row_id}",
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "entry_price": 1.0,
        "entry_price_ts": 950,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.05,
        "max_runup": 0.1,
        "price_points_count": 3,
        "label_quality": "sparse",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def test_cli_writes_gated_dataset_and_reports(tmp_path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dataset_path = tmp_path / "gated.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).replace_all(
        [
            _row("pass"),
            _row("fail", entry_price_source="nearest_research_fallback"),
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_price_quality_gate",
            "--dataset-path",
            str(dataset_path),
            "--output-dataset-path",
            str(output_dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "input_row_count=2" in output
    assert "passed_row_count=1" in output
    assert output_dataset_path.exists()
    assert len(output_dataset_path.read_text(encoding="utf-8").splitlines()) == 1
    reports = sorted(output_dir.glob("price_quality_gate_*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["passed_row_count"] == 1
