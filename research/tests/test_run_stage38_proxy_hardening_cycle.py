from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_stage38_proxy_hardening_cycle import main


METHOD = "transaction_native_sol_quote_over_base_v0"


def test_stage38_proxy_hardening_cycle_runs_offline(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "reports"
    proxy_gated_path = tmp_path / "proxy_gated.jsonl"
    ResearchDatasetStore(dataset_path).replace_all(
        [
            ResearchDatasetRow(
                row_id="row-1",
                snapshot_id="snapshot-1",
                outcome_id="outcome-1",
                token_mint="mint-1",
                snapshot_ts=1_000,
                window_name="1m",
                window_seconds=60,
                horizon_name="15m",
                horizon_seconds=900,
                possible_buy_count=2,
                unique_actor_count=3,
                confidence_weighted_net_flow=1.0,
                buy_sell_imbalance=0.7,
                entry_price=1.0,
                entry_price_ts=1_000,
                entry_price_source="last_before_snapshot",
                forward_return=0.05,
                max_runup=0.1,
                price_points_count=3,
                label_quality="sparse",
            )
        ]
    )
    NormalizedEventStore(events_path).upsert_many(
        [
            NormalizedEvent("a", "sig-a", None, 1_010, "trade", "mint-1", price_quote=1.0, metadata_json={"price_inference_method": METHOD}),
            NormalizedEvent("b", "sig-b", None, 1_020, "trade", "mint-1", price_quote=1.2, metadata_json={"price_inference_method": METHOD}),
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_stage38_proxy_hardening_cycle",
            "--dataset-path",
            str(dataset_path),
            "--events-path",
            str(events_path),
            "--proxy-gated-dataset-path",
            str(proxy_gated_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "native_proxy_backed_count=" in output
    assert "proxy_separated_rule_report_json=" in output
    assert "network_calls=0" in output
