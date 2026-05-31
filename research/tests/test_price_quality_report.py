import json

from research.mtp_research.validation.price_quality_models import (
    PriceQualityConfig,
    PriceQualityGateReport,
)
from research.mtp_research.validation.price_quality_report import (
    report_to_dict,
    write_report_json,
    write_report_markdown,
)


def _report() -> PriceQualityGateReport:
    return PriceQualityGateReport(
        report_id="price-quality-test",
        created_at="2026-05-31T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        input_row_count=2,
        passed_row_count=1,
        failed_row_count=1,
        pass_rate=0.5,
        token_count_input=2,
        token_count_passed=1,
        failure_reason_counts={"stale_entry_price": 1},
        entry_source_counts_input={"last_before_snapshot": 2},
        entry_source_counts_passed={"last_before_snapshot": 1},
        label_quality_counts_input={"sparse": 2},
        label_quality_counts_passed={"sparse": 1},
        config=PriceQualityConfig(max_entry_staleness_sec=120),
        warning_flags=["diagnostic_only_not_trading_signal"],
    )


def test_report_to_dict_serializes_config() -> None:
    payload = report_to_dict(_report())

    assert payload["report_id"] == "price-quality-test"
    assert payload["config"]["max_entry_staleness_sec"] == 120
    assert payload["failure_reason_counts"]["stale_entry_price"] == 1


def test_write_report_json_and_markdown(tmp_path) -> None:
    json_path = write_report_json(_report(), tmp_path / "report.json")
    markdown_path = write_report_markdown(_report(), tmp_path / "report.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["passed_row_count"] == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Price-quality gating is diagnostic only" in markdown
    assert "stale_entry_price" in markdown
