import json
from pathlib import Path

from research.mtp_research.validation.thesis_models import ThesisDecision, ThesisEvaluationSummary
from research.mtp_research.validation.thesis_report import (
    write_thesis_evaluation_json,
    write_thesis_evaluation_markdown,
)


def _summary() -> ThesisEvaluationSummary:
    return ThesisEvaluationSummary(
        thesis_id="MTP-T999",
        name="Test Thesis",
        status="active",
        linked_rule_count=1,
        linked_validation_count=1,
        best_avg_test_net_return=0.05,
        best_positive_test_fold_rate=0.75,
        total_test_selected_count=100,
        recommended_status="watchlist",
        warning_flags=["requires_human_review"],
    )


def _decision() -> ThesisDecision:
    return ThesisDecision(
        decision_id="decision-1",
        thesis_id="MTP-T999",
        created_at="2026-05-31T00:00:00+00:00",
        prior_status="active",
        recommended_status="watchlist",
        confidence=0.55,
        reason="test",
        warning_flags=["requires_human_review"],
    )


def test_markdown_report_writes_warning_block_and_thesis_table(tmp_path: Path) -> None:
    output_path = write_thesis_evaluation_markdown([_summary()], [_decision()], tmp_path / "report.md")
    text = output_path.read_text(encoding="utf-8")
    assert "Warning: thesis decisions are research workflow decisions" in text
    assert "| Thesis | Name | Status | Recommended |" in text
    assert "No thesis is approved for live trading by this report." in text


def test_json_report_writes_summaries_and_decisions(tmp_path: Path) -> None:
    output_path = write_thesis_evaluation_json([_summary()], [_decision()], tmp_path / "report.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summaries"][0]["thesis_id"] == "MTP-T999"
    assert payload["decisions"][0]["decision_id"] == "decision-1"
    assert "No thesis is approved" in payload["warning"]
