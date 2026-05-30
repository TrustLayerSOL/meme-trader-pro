from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.outcome_models import OutcomeLabel
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_build_research_dataset import main


def test_run_build_research_dataset_cli_writes_rows(tmp_path: Path, monkeypatch, capsys) -> None:
    features_path = tmp_path / "features.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    dataset_path = tmp_path / "dataset.jsonl"
    FeatureSnapshotStore(path=features_path).upsert(
        FeatureSnapshot(
            snapshot_id="snapshot-1",
            token_mint="mint-1",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            event_count=2,
        )
    )
    OutcomeLabelStore(path=outcomes_path).upsert(
        OutcomeLabel(
            outcome_id="outcome-1",
            snapshot_id="snapshot-1",
            token_mint="mint-1",
            snapshot_ts=100,
            horizon_name="1m",
            horizon_seconds=60,
            entry_price=1.0,
            forward_return=0.2,
            label_quality="sparse",
        )
    )
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
            "--min-label-quality",
            "sparse",
            "--require-forward-return",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert "snapshots_loaded=1" in output
    assert "outcome_labels_loaded=1" in output
    assert "rows_after_filters=1" in output
    assert "rows_inserted=1" in output
    rows = ResearchDatasetStore(path=dataset_path).load_all()
    assert len(rows) == 1
    assert rows[0].forward_return == 0.2
