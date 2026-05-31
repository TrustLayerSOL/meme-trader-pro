import json
from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_price_quality_failure_analysis import main


def _row(row_id: str, token_mint: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": token_mint,
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "entry_price": 1.0,
        "entry_price_ts": 940,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.1,
        "price_points_count": 3,
        "label_quality": "good",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def test_cli_writes_failure_analysis_report(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "research_dataset.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).replace_all(
        [
            _row("fallback", "mint-a", entry_price_source="nearest_research_fallback"),
            _row("stale", "mint-b", entry_price_ts=700),
            _row("clean", "mint-c"),
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_price_quality_failure_analysis",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "failed_row_count=2" in output
    assert "network_calls=0" in output
    reports = sorted(output_dir.glob("price_quality_failure_analysis_*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text())
    assert payload["top_tokens"][0]["failed_row_count"] == 1
