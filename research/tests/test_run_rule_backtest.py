from pathlib import Path

from research.mtp_research.backtest.run_rule_backtest import main
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def _row(row_id: str, value: int, forward_return: float) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100 + value,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        end_price=1.0 + forward_return,
        forward_return=forward_return,
        possible_buy_count=value,
        possible_sell_count=0,
        confidence_weighted_net_flow=float(value),
        buy_sell_imbalance=0.75,
        unique_actor_count=value,
        quote_volume=float(value),
        label_quality="sparse",
    )


def test_run_rule_backtest_cli_writes_store_and_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    store_path = tmp_path / "results.jsonl"
    dataset_store = ResearchDatasetStore(dataset_path)
    dataset_store.upsert(_row("row-1", 1, 0.10))
    dataset_store.upsert(_row("row-2", 2, -0.05))
    dataset_store.upsert(_row("row-3", 3, 0.20))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_rule_backtest",
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
            "--min-rows",
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
    assert "rows_loaded=3" in output
    assert "rules_run=1" in output
    assert "result_store_path=" in output
    assert store_path.exists()
    assert len(list(output_dir.glob("*.json"))) == 1
    assert len(list(output_dir.glob("*.md"))) == 2
