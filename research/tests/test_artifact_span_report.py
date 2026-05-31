from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionRecord
from research.mtp_research.validation.artifact_span_report import (
    compare_artifact_spans,
    summarize_feature_span,
    summarize_raw_span,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def test_artifact_span_report_flags_diagnostic_dataset_span_much_smaller_than_raw() -> None:
    raw_records = [
        RawTransactionRecord(
            signature="sig-a",
            slot=1,
            block_time=0,
            success=True,
            token_mint="token-a",
        ),
        RawTransactionRecord(
            signature="sig-b",
            slot=2,
            block_time=10_000,
            success=True,
            token_mint="token-b",
        ),
    ]
    diagnostic_rows = [
        ResearchDatasetRow(
            row_id="row-a",
            snapshot_id="snapshot-a",
            outcome_id="outcome-a",
            token_mint="token-a",
            snapshot_ts=0,
            window_name="1m",
            window_seconds=60,
            horizon_name="1m",
            horizon_seconds=60,
        ),
        ResearchDatasetRow(
            row_id="row-b",
            snapshot_id="snapshot-b",
            outcome_id="outcome-b",
            token_mint="token-a",
            snapshot_ts=100,
            window_name="1m",
            window_seconds=60,
            horizon_name="1m",
            horizon_seconds=60,
        ),
    ]

    report = compare_artifact_spans(
        raw_records=raw_records,
        diagnostic_dataset_rows=diagnostic_rows,
    )

    assert report["raw"]["time_span_seconds"] == 10_000
    assert report["diagnostic_dataset"]["time_span_seconds"] == 100
    assert "diagnostic_dataset_span_much_smaller_than_raw" in report["warning_flags"]


def test_span_summaries_count_rows_tokens_and_time_span() -> None:
    raw_summary = summarize_raw_span(
        [
            RawTransactionRecord("sig-a", 1, 10, True, token_mint="token-a"),
            RawTransactionRecord("sig-b", 2, 30, True, token_mint="token-b"),
        ]
    )
    feature_summary = summarize_feature_span(
        [
            FeatureSnapshot("snap-a", "token-a", 10, "1m", 60),
            FeatureSnapshot("snap-b", "token-b", 70, "1m", 60),
        ]
    )

    assert raw_summary["row_count"] == 2
    assert raw_summary["token_count"] == 2
    assert raw_summary["time_span_seconds"] == 20
    assert feature_summary["row_count"] == 2
    assert feature_summary["time_span_seconds"] == 60
