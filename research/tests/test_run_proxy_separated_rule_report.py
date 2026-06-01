import json
from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_proxy_separated_rule_report import main


METHOD = "transaction_native_sol_quote_over_base_v0"


def _row(row_id: str, token: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": token,
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
        "possible_buy_count": 2,
        "unique_actor_count": 3,
        "confidence_weighted_net_flow": 1.0,
        "buy_sell_imbalance": 0.7,
        "entry_price": 1.0,
        "entry_price_ts": 1_000,
        "entry_price_source": "last_before_snapshot",
        "forward_return": 0.05,
        "max_runup": 0.1,
        "price_points_count": 3,
        "label_quality": "sparse",
    }
    payload.update(overrides)
    return ResearchDatasetRow(**payload)


def test_proxy_separated_report_splits_proxy_and_non_proxy_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).replace_all(
        [
            _row("proxy", "mint-proxy"),
            _row("clean", "mint-clean"),
        ]
    )
    NormalizedEventStore(events_path).upsert_many(
        [
            NormalizedEvent("p1", "sig-p1", None, 1_010, "trade", "mint-proxy", price_quote=1.0, metadata_json={"price_inference_method": METHOD}),
            NormalizedEvent("p2", "sig-p2", None, 1_020, "trade", "mint-proxy", price_quote=1.2, metadata_json={"price_inference_method": METHOD}),
            NormalizedEvent("c1", "sig-c1", None, 1_010, "trade", "mint-clean", price_quote=1.0),
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_proxy_separated_rule_report",
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
    assert "subset_native_sol_proxy_only.row_count=1" in output
    assert "subset_non_native_sol_proxy.row_count=1" in output
    report_path = sorted(output_dir.glob("proxy_separated_rule_*.json"))[0]
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["subsets"]["native_sol_proxy_only"]["row_count"] == 1
    assert payload["subsets"]["non_native_sol_proxy"]["row_count"] == 1
