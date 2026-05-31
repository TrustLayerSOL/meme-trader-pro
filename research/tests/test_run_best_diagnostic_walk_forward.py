from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_best_diagnostic_walk_forward import main
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


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
        possible_sell_count=0,
        confidence_weighted_net_flow=1.0,
        buy_sell_imbalance=0.75,
        unique_actor_count=3,
        quote_volume=1.0,
        label_quality="sparse",
    )


def test_best_diagnostic_walk_forward_runs_when_valid_config_exists(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dataset_path = tmp_path / "diagnostics" / "dataset.jsonl"
    output_dir = tmp_path / "diagnostics" / "reports"
    store_path = tmp_path / "diagnostics" / "walk_forward.jsonl"
    store = ResearchDatasetStore(dataset_path)
    for idx in range(40):
        store.upsert(_row(f"row-{idx}", idx * 60))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_best_diagnostic_walk_forward",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--store-path",
            str(store_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "walk_forward_ran=True" in output
    assert "network_calls=0" in output
    assert len(WalkForwardValidationStore(store_path).load_all()) == 1
    assert list(output_dir.glob("walk-forward-*.json"))


def test_best_diagnostic_walk_forward_skips_when_no_valid_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dataset_path = tmp_path / "diagnostics" / "dataset.jsonl"
    output_dir = tmp_path / "diagnostics" / "reports"
    store_path = tmp_path / "diagnostics" / "walk_forward.jsonl"
    store = ResearchDatasetStore(dataset_path)
    for idx in range(3):
        store.upsert(_row(f"row-{idx}", idx * 60))

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_best_diagnostic_walk_forward",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--store-path",
            str(store_path),
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "walk_forward_ran=False" in output
    assert not store_path.exists()
    assert list(output_dir.glob("fold_sufficiency_*.json"))
