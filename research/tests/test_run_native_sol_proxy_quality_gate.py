import json
from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_native_sol_proxy_quality_gate import main


METHOD = "transaction_native_sol_quote_over_base_v0"


def _row(row_id: str, **overrides) -> ResearchDatasetRow:
    payload = {
        "row_id": row_id,
        "snapshot_id": f"snapshot-{row_id}",
        "outcome_id": f"outcome-{row_id}",
        "token_mint": "mint-1",
        "snapshot_ts": 1_000,
        "window_name": "1m",
        "window_seconds": 60,
        "horizon_name": "15m",
        "horizon_seconds": 900,
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


def test_cli_writes_proxy_gated_dataset_and_report(tmp_path: Path, monkeypatch, capsys) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    events_path = tmp_path / "events.jsonl"
    output_dataset_path = tmp_path / "proxy_gated.jsonl"
    output_dir = tmp_path / "reports"
    ResearchDatasetStore(dataset_path).replace_all(
        [
            _row("pass"),
            _row("fail", forward_return=3.0),
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
            "run_native_sol_proxy_quality_gate",
            "--dataset-path",
            str(dataset_path),
            "--events-path",
            str(events_path),
            "--output-dataset-path",
            str(output_dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "row_count=2" in output
    assert "native_proxy_backed_count=2" in output
    assert "native_proxy_failed_count=1" in output
    assert output_dataset_path.exists()
    assert len(output_dataset_path.read_text(encoding="utf-8").splitlines()) == 1
    reports = sorted(output_dir.glob("native_sol_proxy_quality_*.json"))
    assert json.loads(reports[0].read_text(encoding="utf-8"))["native_proxy_failed_count"] == 1
