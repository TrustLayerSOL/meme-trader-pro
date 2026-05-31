import json
from pathlib import Path

from research.mtp_research.validation.evidence_expansion_decision_models import (
    EvidenceExpansionDecisionReport,
)
from research.mtp_research.validation.evidence_expansion_decision_report import (
    write_report_json,
    write_report_markdown,
)


def test_evidence_expansion_decision_report_writes_markdown_and_json(tmp_path: Path) -> None:
    report = EvidenceExpansionDecisionReport(
        report_id="evidence_expansion_decision-test",
        created_at="2026-01-01T00:00:00+00:00",
        diagnostic_dataset_path="dataset.jsonl",
        diagnostic_row_count=1,
        recommended_next_action="run_bounded_evidence_expansion",
    )

    md_path = write_report_markdown(report, tmp_path / "report.md")
    json_path = write_report_json(report, tmp_path / "report.json")

    assert "not a trading signal" in md_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["report_id"] == "evidence_expansion_decision-test"
