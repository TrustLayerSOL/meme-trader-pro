from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_inspect_rule_selected_rows import main


def test_selected_row_inspection_prints_expected_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    ResearchDatasetStore(dataset_path).upsert(
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
            possible_buy_count=2,
            possible_sell_count=0,
            buy_sell_imbalance=0.8,
            unique_actor_count=3,
            confidence_weighted_net_flow=1,
            entry_price_source="exact_snapshot",
            forward_return=0.1,
            max_runup=0.2,
            max_drawdown=-0.1,
            label_quality="sparse",
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_inspect_rule_selected_rows",
            "--dataset-path",
            str(dataset_path),
            "--rule-id",
            "buy_imbalance_basic",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "token_mint=mint-1" in output
    assert "buy_sell_imbalance=0.8" in output
    assert "network_calls=0" in output
