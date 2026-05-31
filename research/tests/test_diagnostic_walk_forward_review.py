from research.mtp_research.validation.diagnostic_walk_forward_review import (
    DiagnosticWalkForwardReviewer,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
    utc_now_iso,
)


def _row(row_id: str, entry_source: str = "exact_snapshot") -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100 + len(row_id),
        window_name="1m",
        window_seconds=60,
        horizon_name="1m",
        horizon_seconds=60,
        possible_buy_count=2,
        confidence_weighted_net_flow=1.0,
        forward_return=0.2,
        entry_price=1.0,
        entry_price_source=entry_source,
        label_quality="sparse",
    )


def _summary(
    rule_id: str = "positive_flow_basic",
    valid_folds: int = 3,
    selected_count: int = 75,
    avg_return: float | None = 0.05,
    positive_rate: float | None = 0.67,
    consistency: float | None = 0.033,
) -> RuleWalkForwardSummary:
    return RuleWalkForwardSummary(
        rule_id=rule_id,
        rule_name="Positive Flow Basic",
        fold_count=3,
        valid_test_fold_count=valid_folds,
        total_test_selected_count=selected_count,
        avg_test_selected_count=selected_count / 3,
        avg_test_net_return=avg_return,
        median_test_net_return=avg_return,
        positive_test_fold_rate=positive_rate,
        avg_test_win_rate=0.6,
        avg_test_profit_factor=1.5,
        consistency_score=consistency,
    )


def _result(*summaries: RuleWalkForwardSummary) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at=utc_now_iso(),
        config=WalkForwardConfig("best_diagnostic__ultra_short", 900, 300, 300),
        dataset_path="dataset.jsonl",
        row_count=3,
        filtered_row_count=3,
        fold_count=3,
        rules_tested=len(summaries),
        rule_summaries=list(summaries),
    )


def test_build_findings_creates_rule_findings_from_walk_forward_result() -> None:
    review = DiagnosticWalkForwardReviewer().build_review(
        [_row("1"), _row("2")],
        _result(_summary()),
        "dataset.jsonl",
        "walk.jsonl",
    )

    assert review.rules_with_valid_folds == 1
    assert review.findings[0].rule_id == "positive_flow_basic"
    assert review.best_rule_by_consistency == "positive_flow_basic"


def test_recommend_next_action_scales_when_no_valid_folds() -> None:
    review = DiagnosticWalkForwardReviewer().build_review(
        [_row("1")],
        _result(_summary(valid_folds=0, selected_count=0, avg_return=None, positive_rate=None)),
        "dataset.jsonl",
    )

    assert review.recommended_next_action == "scale_bounded_backfill_for_more_time_span"


def test_recommend_next_action_improves_price_when_fallback_dominates() -> None:
    review = DiagnosticWalkForwardReviewer().build_review(
        [_row("1", "nearest_research_fallback"), _row("2", "nearest_research_fallback")],
        _result(_summary()),
        "dataset.jsonl",
    )

    assert review.findings[0].fallback_dependency_warning is True
    assert review.recommended_next_action == "improve_clean_price_inference"


def test_recommend_next_action_manual_inspection_for_positive_diagnostic_evidence() -> None:
    review = DiagnosticWalkForwardReviewer().build_review(
        [_row("1"), _row("2")],
        _result(_summary()),
        "dataset.jsonl",
    )

    assert review.recommended_next_action == "inspect_candidate_rule_manually_before_more_scale"
