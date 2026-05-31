import json
from pathlib import Path

from research.mtp_research.validation.selected_row_audit_models import (
    RuleSelectedRowAudit,
    SelectedRowAuditReport,
)
from research.mtp_research.validation.selected_row_audit_report import (
    write_report_json,
    write_report_markdown,
)


def test_selected_row_audit_report_writes_markdown_and_json(tmp_path: Path) -> None:
    report = SelectedRowAuditReport(
        report_id="selected_row_audit-test",
        created_at="2026-01-01T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        audited_rule_ids=["rule-a"],
        row_count=1,
        rule_audits=[RuleSelectedRowAudit(rule_id="rule-a", rule_name="Rule A", selected_count=1)],
        recommended_next_action="manual_review_selected_rows",
    )

    md_path = write_report_markdown(report, tmp_path / "report.md")
    json_path = write_report_json(report, tmp_path / "report.json")

    assert "Selected row audit is diagnostic only" in md_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_id"] == "selected_row_audit-test"
