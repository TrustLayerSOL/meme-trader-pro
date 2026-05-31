from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.run_build_outcome_labels import main


def _snapshot(token: str, ts: int) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"{token}-{ts}",
        token_mint=token,
        snapshot_ts=ts,
        window_name="1m",
        window_seconds=60,
    )


def _event(token: str, event_id: str, ts: int, price: float) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature=event_id,
        slot=1,
        block_time=ts,
        event_type="possible_buy",
        token_mint=token,
        price_quote=price,
    )


def test_run_build_outcome_labels_accepts_snapshot_selection_args(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    features_path = tmp_path / "features.jsonl"
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    FeatureSnapshotStore(path=features_path).upsert_many(
        [_snapshot("token-a", 100), _snapshot("token-a", 200), _snapshot("token-b", 1000)]
    )
    NormalizedEventStore(path=events_path).upsert_many(
        [
            _event("token-a", "a-entry", 100, 1.0),
            _event("token-a", "a-future", 220, 1.2),
            _event("token-b", "b-entry", 1000, 2.0),
            _event("token-b", "b-future", 1100, 2.2),
        ]
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
            "--snapshot-selection-strategy",
            "per_token_even",
            "--max-snapshots-per-token",
            "1",
            "--min-time-gap-seconds",
            "60",
            "--overwrite",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "snapshot_selection_strategy=per_token_even" in output
    assert "snapshot_selection_selected_token_count=2" in output
    assert "snapshot_selection_selected_by_token={'token-a': 1, 'token-b': 1}" in output
