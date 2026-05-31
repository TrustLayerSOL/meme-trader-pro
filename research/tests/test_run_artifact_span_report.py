from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord, RawTransactionStore
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore
from research.mtp_research.validation.run_artifact_span_report import main


def test_run_artifact_span_report_writes_markdown_and_json(tmp_path: Path, monkeypatch, capsys) -> None:
    raw_path = tmp_path / "raw.jsonl"
    features_path = tmp_path / "features.jsonl"
    diagnostic_dataset_path = tmp_path / "diagnostic_dataset.jsonl"
    output_dir = tmp_path / "reports"

    RawTransactionStore(raw_path).upsert_many(
        [
            RawTransactionRecord("sig-a", 1, 0, True, token_mint="token-a"),
            RawTransactionRecord("sig-b", 2, 10_000, True, token_mint="token-b"),
        ]
    )
    FeatureSnapshotStore(features_path).upsert_many(
        [
            FeatureSnapshot("snap-a", "token-a", 0, "1m", 60),
            FeatureSnapshot("snap-b", "token-b", 10_000, "1m", 60),
        ]
    )
    ResearchDatasetStore(diagnostic_dataset_path).upsert_many(
        [
            ResearchDatasetRow(
                row_id="row-a",
                snapshot_id="snap-a",
                outcome_id="outcome-a",
                token_mint="token-a",
                snapshot_ts=0,
                window_name="1m",
                window_seconds=60,
                horizon_name="1m",
                horizon_seconds=60,
            )
        ]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_artifact_span_report",
            "--raw-path",
            str(raw_path),
            "--features-path",
            str(features_path),
            "--diagnostic-dataset-path",
            str(diagnostic_dataset_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "raw.row_count=2" in output
    assert "feature_snapshots.time_span_seconds=10000" in output
    assert "network_calls=0" in output
    assert list(output_dir.glob("artifact_span_report_*.md"))
    assert list(output_dir.glob("artifact_span_report_*.json"))
