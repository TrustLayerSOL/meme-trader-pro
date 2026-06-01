import json

from research.mtp_research.validation.native_sol_proxy_quality_models import (
    NativeSolProxyQualityReport,
)
from research.mtp_research.validation.native_sol_proxy_quality_report import (
    write_report_json,
    write_report_markdown,
)


def test_native_sol_proxy_quality_report_writers_create_json_and_markdown(tmp_path) -> None:
    report = NativeSolProxyQualityReport(
        report_id="native_sol_proxy_quality_test",
        created_at="2026-01-01T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        row_count=2,
        native_proxy_backed_count=1,
        native_proxy_passed_count=0,
        native_proxy_failed_count=1,
        non_proxy_count=1,
        pass_rate=0.5,
        failure_reason_counts={"excessive_forward_return": 1},
        token_counts={"mint-1": 1},
        warning_flags=["diagnostic_only_not_trading_signal"],
    )

    json_path = write_report_json(report, tmp_path / "report.json")
    markdown_path = write_report_markdown(report, tmp_path / "report.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["native_proxy_failed_count"] == 1
    text = markdown_path.read_text(encoding="utf-8")
    assert "Native SOL proxy quality gating is diagnostic only" in text
    assert "excessive_forward_return" in text
