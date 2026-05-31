from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.run_build_outcome_labels import main


def _snapshot(token: str, snapshot_id: str = "snapshot-1") -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        token_mint=token,
        snapshot_ts=100,
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


def _real_candidate(token: str) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token,
        source="dexscreener",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address=f"pool-{token}",
        liquidity_usd=20000,
    )


def test_outcome_labels_dry_run_summary_does_not_write(tmp_path: Path, monkeypatch, capsys) -> None:
    features_path = tmp_path / "features.jsonl"
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1"))
    NormalizedEventStore(events_path).upsert_many(
        [_event("mint-1", "entry", 100, 1.0), _event("mint-1", "future", 120, 1.2)]
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
            "--dry-run-summary",
            "--progress-every",
            "1",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "dry_run_summary=True" in output
    assert "progress snapshots_processed=1" in output
    assert not outcomes_path.exists()


def test_outcome_labels_stop_after_snapshots_limits_work(tmp_path: Path, monkeypatch, capsys) -> None:
    features_path = tmp_path / "features.jsonl"
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1", "snapshot-1"))
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1", "snapshot-2"))
    NormalizedEventStore(events_path).upsert(_event("mint-1", "entry", 100, 1.0))
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
            "--stop-after-snapshots",
            "1",
        ],
    )

    assert main() == 0

    assert "selected_snapshot_count=1" in capsys.readouterr().out
    assert len(OutcomeLabelStore(outcomes_path).load_all()) == 3


def test_outcome_labels_real_only_filters_mock_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    registry = CandidateRegistry("data/normalized/candidate_registry.jsonl")
    registry.upsert(_real_candidate("real-mint"))
    features_path = tmp_path / "features.jsonl"
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("real-mint", "snapshot-real"))
    FeatureSnapshotStore(features_path).upsert(_snapshot("mock-mint", "snapshot-mock"))
    NormalizedEventStore(events_path).upsert_many(
        [_event("real-mint", "real-entry", 100, 1.0), _event("mock-mint", "mock-entry", 100, 1.0)]
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
            "--real-only",
        ],
    )

    assert main() == 0

    assert "token_count=1" in capsys.readouterr().out
    labels = OutcomeLabelStore(outcomes_path).load_all()
    assert {label.token_mint for label in labels} == {"real-mint"}
