from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_walk_forward_validation import main
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def _row(row_id: str, snapshot_ts: int, forward_return: float) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        end_price=1.0 + forward_return,
        forward_return=forward_return,
        possible_buy_count=1,
        confidence_weighted_net_flow=1.0,
        label_quality="sparse",
    )


def test_run_walk_forward_validation_cli_writes_store_and_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    store_path = tmp_path / "walk_forward.jsonl"
    dataset_store = ResearchDatasetStore(dataset_path)
    for ts in range(0, 26):
        dataset_store.upsert(_row(f"row-{ts}", ts, 0.1 if ts < 15 else -0.05))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_walk_forward_validation",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--store-path",
            str(store_path),
            "--rule-id",
            "positive_flow_basic",
            "--horizon-name",
            "5m",
            "--window-name",
            "1m",
            "--train-window-seconds",
            "10",
            "--test-window-seconds",
            "5",
            "--step-seconds",
            "5",
            "--min-train-rows",
            "1",
            "--min-test-rows",
            "1",
            "--entry-fee-bps",
            "0",
            "--exit-fee-bps",
            "0",
            "--slippage-bps",
            "0",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "rows_loaded=26" in output
    assert "rows_analyzed=26" in output
    assert "folds_generated=" in output
    assert "rules_tested=1" in output
    assert len(WalkForwardValidationStore(store_path).load_all()) == 1
    assert len(list(output_dir.glob("*.json"))) == 1
    assert len(list(output_dir.glob("*.md"))) == 1
