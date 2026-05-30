from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.run_build_outcome_labels import main


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id="snapshot-1",
        token_mint="mint-1",
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
    )


def _event(event_id: str, ts: int, price: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=ts,
        event_type="possible_buy",
        token_mint="mint-1",
        actor="actor-1",
        base_qty=1.0,
        quote_qty=2.0,
        price_quote=price,
        metadata_json={"confidence": 0.7},
    )


def test_run_build_outcome_labels_cli_writes_labels(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    features_path = tmp_path / "features.jsonl"
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    FeatureSnapshotStore(path=features_path).upsert(_snapshot())
    NormalizedEventStore(path=events_path).upsert_many(
        [_event("entry", 100, 1.0), _event("future", 120, 1.2)]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_build_outcome_labels",
            "--features-path",
            str(features_path),
            "--events-path",
            str(events_path),
            "--outcomes-path",
            str(outcomes_path),
            "--max-snapshots",
            "1",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "snapshots_loaded=1" in output
    assert "events_loaded=2" in output
    assert "labels_generated=3" in output
    assert "labels_inserted=3" in output

    labels = OutcomeLabelStore(path=outcomes_path).load_all()
    assert len(labels) == 3
    assert {label.horizon_name for label in labels} == {"1m", "5m", "15m"}
