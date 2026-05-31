from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_stage31_outlier_review_cycle import main


def test_run_stage31_cycle_cli_runs_offline_with_temp_data(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    events_path = tmp_path / "events.jsonl"
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
            unique_actor_count=3,
            confidence_weighted_net_flow=1,
            buy_sell_imbalance=0.8,
            entry_price=1.0,
            entry_price_ts=100,
            entry_price_source="exact_snapshot",
            end_price=2.2,
            end_price_ts=1_000,
            forward_return=1.2,
            label_quality="sparse",
        )
    )
    NormalizedEventStore(events_path).upsert_many(
        [
            NormalizedEvent(f"event-{idx}", f"sig-{idx}", None, ts, "trade", "mint-1", price_quote=price)
            for idx, (ts, price) in enumerate([(100, 1.0), (200, 1.5), (500, 2.0), (1_000, 2.2)])
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_stage31_outlier_review_cycle",
            "--dataset-path",
            str(dataset_path),
            "--events-path",
            str(events_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "final_recommendation=" in output
    assert "network_calls=0" in output
