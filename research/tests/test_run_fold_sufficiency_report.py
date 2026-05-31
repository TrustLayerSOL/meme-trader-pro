from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_fold_sufficiency_report import main


def _row(row_id: str, snapshot_ts: int) -> ResearchDatasetRow:
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
        end_price=1.1,
        forward_return=0.1,
        possible_buy_count=1,
        confidence_weighted_net_flow=1.0,
        label_quality="sparse",
    )


def test_run_fold_sufficiency_report_cli_writes_reports(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dataset_path = tmp_path / "diagnostics" / "dataset.jsonl"
    output_dir = tmp_path / "diagnostics" / "reports"
    store = ResearchDatasetStore(dataset_path)
    for idx in range(31):
        store.upsert(_row(f"row-{idx}", idx * 60))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fold_sufficiency_report",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "row_count=31" in output
    assert "token_count=1" in output
    assert "best_config_name=" in output
    assert "recommended_next_action=" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("fold_sufficiency_*.md"))
    assert list(output_dir.glob("fold_sufficiency_*.json"))
