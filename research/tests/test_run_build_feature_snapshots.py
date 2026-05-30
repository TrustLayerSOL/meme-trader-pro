from pathlib import Path

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.features.run_build_feature_snapshots import main
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore


def _event(event_id: str, block_time: int) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=block_time,
        event_type="possible_buy",
        token_mint="mint-1",
        venue="unknown_token_swap_candidate",
        actor="actor-1",
        base_qty=1.0,
        quote_qty=2.0,
        metadata_json={"confidence": 0.7},
    )


def test_run_build_feature_snapshots_cli_writes_snapshots(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    events_path = tmp_path / "events.jsonl"
    features_path = tmp_path / "features.jsonl"
    event_store = NormalizedEventStore(path=events_path)
    event_store.upsert_many([_event("e1", 100), _event("e2", 160)])
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_build_feature_snapshots",
            "--events-path",
            str(events_path),
            "--features-path",
            str(features_path),
            "--snapshot-step-sec",
            "60",
            "--max-snapshots",
            "2",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "events_loaded=2" in output
    assert "tokens_seen=1" in output
    assert "snapshot_times_generated=2" in output
    assert "snapshots_inserted=6" in output

    snapshots = FeatureSnapshotStore(path=features_path).load_all()
    assert len(snapshots) == 6
    assert {snapshot.window_name for snapshot in snapshots} == {"1m", "5m", "15m"}
