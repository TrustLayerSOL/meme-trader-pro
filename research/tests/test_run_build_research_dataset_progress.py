from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_build_research_dataset import main


def _snapshot(token: str, snapshot_id: str = "snapshot-1") -> FeatureSnapshot:
    return FeatureSnapshot(snapshot_id, token, 100, "1m", 60)


def _label(token: str, outcome_id: str = "outcome-1", snapshot_id: str = "snapshot-1") -> OutcomeLabel:
    return OutcomeLabel(
        outcome_id=outcome_id,
        snapshot_id=snapshot_id,
        token_mint=token,
        snapshot_ts=100,
        horizon_name="1m",
        horizon_seconds=60,
        entry_price=1.0,
        forward_return=0.1,
        label_quality="sparse",
    )


def _real_candidate(token: str) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token,
        source="dexscreener",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address=f"pool-{token}",
        liquidity_usd=20000,
    )


def test_research_dataset_dry_run_summary_does_not_write(tmp_path: Path, monkeypatch, capsys) -> None:
    features_path = tmp_path / "features.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1"))
    OutcomeLabelStore(outcomes_path).upsert(_label("mint-1"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_build_research_dataset",
            "--features-path",
            str(features_path),
            "--outcomes-path",
            str(outcomes_path),
            "--dataset-path",
            str(dataset_path),
            "--dry-run-summary",
            "--progress-every",
            "1",
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "dry_run_summary=True" in output
    assert "progress snapshots_processed=1" in output
    assert not dataset_path.exists()


def test_research_dataset_stop_after_labels_limits_work(tmp_path: Path, monkeypatch) -> None:
    features_path = tmp_path / "features.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1", "snapshot-1"))
    FeatureSnapshotStore(features_path).upsert(_snapshot("mint-1", "snapshot-2"))
    OutcomeLabelStore(outcomes_path).upsert(_label("mint-1", "outcome-1", "snapshot-1"))
    OutcomeLabelStore(outcomes_path).upsert(_label("mint-1", "outcome-2", "snapshot-2"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_build_research_dataset",
            "--features-path",
            str(features_path),
            "--outcomes-path",
            str(outcomes_path),
            "--dataset-path",
            str(dataset_path),
            "--stop-after-labels",
            "1",
        ],
    )

    assert main() == 0

    assert len(ResearchDatasetStore(dataset_path).load_all()) == 1


def test_research_dataset_real_only_filters_mock_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    CandidateRegistry("data/normalized/candidate_registry.jsonl").upsert(_real_candidate("real-mint"))
    features_path = tmp_path / "features.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    FeatureSnapshotStore(features_path).upsert(_snapshot("real-mint", "snapshot-real"))
    FeatureSnapshotStore(features_path).upsert(_snapshot("mock-mint", "snapshot-mock"))
    OutcomeLabelStore(outcomes_path).upsert(_label("real-mint", "outcome-real", "snapshot-real"))
    OutcomeLabelStore(outcomes_path).upsert(_label("mock-mint", "outcome-mock", "snapshot-mock"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_build_research_dataset",
            "--features-path",
            str(features_path),
            "--outcomes-path",
            str(outcomes_path),
            "--dataset-path",
            str(dataset_path),
            "--real-only",
        ],
    )

    assert main() == 0

    assert "token_count=1" in capsys.readouterr().out
    rows = ResearchDatasetStore(dataset_path).load_all()
    assert {row.token_mint for row in rows} == {"real-mint"}
