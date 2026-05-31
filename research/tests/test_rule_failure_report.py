from pathlib import Path

from research.mtp_research.validation.rule_failure_models import RuleFailureAnatomy, RuleFailureReview
from research.mtp_research.validation.rule_failure_report import WARNING_TEXT, write_review_json, write_review_markdown


def _review() -> RuleFailureReview:
    return RuleFailureReview(
        review_id="review-1",
        created_at="2026-05-31T00:00:00+00:00",
        dataset_path="dataset.jsonl",
        walk_forward_path="walk.jsonl",
        row_count=10,
        token_count=2,
        time_span_seconds=900,
        nearest_fallback_row_count=5,
        recommended_next_action="scale_candidate_diversity_with_bounded_backfill",
        evidence_scale_recommendation="add_more_real_candidates",
        rule_review_recommendation="inspect selected buy_imbalance_basic rows before changing thresholds",
        rule_anatomies=[
            RuleFailureAnatomy(
                rule_id="buy_imbalance_basic",
                rule_name="Buy Imbalance Basic",
                valid_test_fold_count=4,
                positive_test_fold_rate=0.25,
                total_test_selected_count=52,
                likely_failure_causes=["low_positive_fold_rate"],
            )
        ],
    )


def test_rule_failure_report_writes_markdown_and_json(tmp_path: Path) -> None:
    markdown_path = write_review_markdown(_review(), tmp_path / "review.md")
    json_path = write_review_json(_review(), tmp_path / "review.json")

    assert markdown_path.exists()
    assert json_path.exists()
    assert "buy_imbalance_basic" in json_path.read_text(encoding="utf-8")


def test_rule_failure_report_includes_warning_block(tmp_path: Path) -> None:
    markdown_path = write_review_markdown(_review(), tmp_path / "review.md")

    assert WARNING_TEXT in markdown_path.read_text(encoding="utf-8")
