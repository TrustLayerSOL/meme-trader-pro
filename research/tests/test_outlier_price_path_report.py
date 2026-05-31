import json
from pathlib import Path

from research.mtp_research.validation.outlier_price_path_models import OutlierPricePathReport
from research.mtp_research.validation.outlier_price_path_report import (
    write_report_json,
    write_report_markdown,
)


def test_outlier_price_path_report_writes_markdown_and_json(tmp_path: Path) -> None:
    report = OutlierPricePathReport(
        report_id="outlier_price_path-test",
        created_at="2026-01-01T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        events_path="events.jsonl",
        reviewed_count=1,
        recommended_next_action="manual_review_required",
    )

    md_path = write_report_markdown(report, tmp_path / "report.md")
    json_path = write_report_json(report, tmp_path / "report.json")

    assert "Outlier price-path review is diagnostic only" in md_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_id"] == "outlier_price_path-test"
