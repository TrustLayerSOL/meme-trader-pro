from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_stage30_price_rule_audit_cycle import main


def test_run_stage30_cycle_cli_runs_offline_with_temp_dataset(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).upsert_many(
        [
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
            ),
            ResearchDatasetRow(
                row_id="row-2",
                snapshot_id="snapshot-2",
                outcome_id="outcome-2",
                token_mint="mint-2",
                snapshot_ts=200,
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
                entry_price_ts=200,
                entry_price_source="nearest_research_fallback",
                forward_return=1.4,
                max_runup=2.0,
                label_quality="sparse",
            ),
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_stage30_price_rule_audit_cycle",
            "--dataset-path",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
            "--skip-dependent-reviews",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "final_recommendation=" in output
    assert "network_calls=0" in output
