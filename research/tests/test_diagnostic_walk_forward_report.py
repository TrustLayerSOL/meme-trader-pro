from pathlib import Path

from research.mtp_research.validation.diagnostic_walk_forward_models import (
    DiagnosticRuleWalkForwardFinding,
    DiagnosticWalkForwardReview,
)
from research.mtp_research.validation.diagnostic_walk_forward_report import (
    WARNING_TEXT,
    write_review_json,
    write_review_markdown,
)


def _review() -> DiagnosticWalkForwardReview:
    return DiagnosticWalkForwardReview(
        review_id="review-1",
        created_at="2026-05-31T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        walk_forward_result_path="walk.jsonl",
        fold_config_name="best",
        row_count=10,
        token_count=2,
        time_span_seconds=900,
        nearest_fallback_row_count=5,
        rules_tested=1,
        rules_with_valid_folds=1,
        findings=[
            DiagnosticRuleWalkForwardFinding(
                rule_id="positive_flow_basic",
                rule_name="Positive Flow Basic",
                valid_test_fold_count=2,
                total_test_selected_count=20,
            )
        ],
        recommended_next_action="improve_clean_price_inference",
    )


def test_report_writer_creates_markdown_and_json(tmp_path: Path) -> None:
    markdown_path = write_review_markdown(_review(), tmp_path / "review.md")
    json_path = write_review_json(_review(), tmp_path / "review.json")

    assert markdown_path.exists()
    assert json_path.exists()
    assert "positive_flow_basic" in json_path.read_text(encoding="utf-8")


def test_report_includes_diagnostic_warning_block(tmp_path: Path) -> None:
    markdown_path = write_review_markdown(_review(), tmp_path / "review.md")

    assert WARNING_TEXT in markdown_path.read_text(encoding="utf-8")
