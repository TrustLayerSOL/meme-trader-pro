from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_selected_row_audit import main


def test_run_selected_row_audit_cli_writes_reports(tmp_path: Path, monkeypatch, capsys) -> None:
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
            possible_buy_count=2,
            possible_sell_count=0,
            unique_actor_count=3,
            confidence_weighted_net_flow=1,
            buy_sell_imbalance=0.8,
            entry_price=1.0,
            entry_price_ts=100,
            entry_price_source="exact_snapshot",
            forward_return=0.2,
            label_quality="sparse",
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_selected_row_audit",
            "--dataset-path",
            str(dataset_path),
            "--rule-id",
            "buy_imbalance_basic",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "buy_imbalance_basic.selected_count=1" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("*.md"))
    assert list(output_dir.glob("*.json"))
