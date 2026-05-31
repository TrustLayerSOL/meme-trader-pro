import json
from pathlib import Path

from research.mtp_research.validation.run_dataset_sufficiency_report import main


def test_run_dataset_sufficiency_report_writes_markdown_and_json(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    dataset_path.write_text(
        json.dumps(
            {
                "row_id": "r1",
                "snapshot_id": "s1",
                "outcome_id": "o1",
                "token_mint": "token-a",
                "snapshot_ts": 100,
                "window_name": "1m",
                "window_seconds": 60,
                "horizon_name": "5m",
                "horizon_seconds": 300,
                "entry_price": 1.0,
                "forward_return": 0.1,
                "label_quality": "good",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_dataset_sufficiency_report",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "total_rows=1" in output
    assert "rows_with_entry_price=1" in output
    assert list(output_dir.glob("dataset_sufficiency_*.md"))
    assert list(output_dir.glob("dataset_sufficiency_*.json"))
