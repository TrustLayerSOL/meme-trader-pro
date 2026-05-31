import json
from pathlib import Path

from research.mtp_research.validation.baseline_report_models import (
    BaselineEdgeReport,
    BucketOutcomeSummary,
    FeatureBucket,
    FeatureBucketResult,
    FeatureReport,
)
from research.mtp_research.validation.baseline_report_writer import (
    format_number,
    format_percent,
    report_to_dict,
    write_report_json,
    write_report_markdown,
)


def _report() -> BaselineEdgeReport:
    return BaselineEdgeReport(
        report_id="baseline-test",
        created_at="2026-05-30T00:00:00+00:00",
        dataset_path="tmp/dataset.jsonl",
        row_count=2,
        filtered_row_count=2,
        token_count=1,
        window_counts={"1m": 2},
        horizon_counts={"5m": 2},
        label_quality_counts={"sparse": 2},
        feature_reports=[
            FeatureReport(
                feature_name="age_sec",
                row_count=2,
                bucket_count=1,
                best_bucket_name="all",
                worst_bucket_name="all",
                bucket_results=[
                    FeatureBucketResult(
                        feature_name="age_sec",
                        window_name="1m",
                        horizon_name="5m",
                        bucket=FeatureBucket(
                            feature_name="age_sec",
                            bucket_name="all",
                            lower_bound=1.0,
                            upper_bound=2.0,
                            row_count=2,
                            token_count=1,
                        ),
                        outcome_summary=BucketOutcomeSummary(
                            row_count=2,
                            token_count=1,
                            avg_forward_return=0.15,
                            median_forward_return=0.15,
                            win_rate=1.0,
                            avg_max_runup=0.25,
                            avg_max_drawdown=-0.05,
                        ),
                        warning_flags=["small_bucket"],
                    )
                ],
                warning_flags=["exploratory_only_not_strategy"],
            )
        ],
        top_findings=["Exploratory finding; requires backtest and walk-forward validation."],
        warning_flags=["exploratory_report_not_trading_signal"],
        metadata_json={"version": "test"},
    )


def test_report_to_dict_serializes_nested_dataclasses() -> None:
    payload = report_to_dict(_report())
    assert payload["report_id"] == "baseline-test"
    assert payload["feature_reports"][0]["bucket_results"][0]["bucket"]["bucket_name"] == "all"


def test_write_report_json_writes_valid_json(tmp_path: Path) -> None:
    output_path = write_report_json(_report(), tmp_path / "report.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_id"] == "baseline-test"


def test_write_report_markdown_writes_readable_markdown_with_flags_and_bucket_table(tmp_path: Path) -> None:
    output_path = write_report_markdown(_report(), tmp_path / "report.md")
    text = output_path.read_text(encoding="utf-8")
    assert "# Baseline Edge Report v0" in text
    assert "## Warning Flags" in text
    assert "| Bucket | Bounds | Rows | Tokens |" in text
    assert "`exploratory_report_not_trading_signal`" in text
    assert "small_bucket" in text


def test_format_helpers_handle_none() -> None:
    assert format_percent(None) == "n/a"
    assert format_number(None) == "n/a"
    assert format_percent(0.1234) == "12.34%"
    assert format_number(1.23456) == "1.2346"
