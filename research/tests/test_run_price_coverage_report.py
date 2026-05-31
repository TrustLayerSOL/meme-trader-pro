import json
from pathlib import Path

from research.mtp_research.validation.run_price_coverage_report import main


def test_run_price_coverage_report_writes_markdown_and_json(tmp_path: Path, monkeypatch, capsys) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    output_dir = tmp_path / "reports"
    events_path.write_text(
        json.dumps(
            {
                "event_id": "e1",
                "signature": "sig-1",
                "slot": 1,
                "block_time": 100,
                "event_type": "possible_buy",
                "token_mint": "token-a",
                "price_quote": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    outcomes_path.write_text(
        json.dumps(
            {
                "outcome_id": "o1",
                "snapshot_id": "s1",
                "token_mint": "token-a",
                "snapshot_ts": 100,
                "horizon_name": "5m",
                "horizon_seconds": 300,
                "label_quality": "good",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_price_coverage_report",
            "--events-path",
            str(events_path),
            "--outcomes-path",
            str(outcomes_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "event_count=1" in output
    assert "events_with_price_quote=1" in output
    assert list(output_dir.glob("price_coverage_*.md"))
    assert list(output_dir.glob("price_coverage_*.json"))
