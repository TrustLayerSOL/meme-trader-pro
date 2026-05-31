from research.mtp_research.validation.thesis_evaluator import ThesisEvaluator
from research.mtp_research.validation.thesis_models import SampleAdequacyReport, ThesisReference
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
)


def _thesis(status: str = "active", linked: list[str] | None = None) -> ThesisReference:
    return ThesisReference(
        thesis_id="MTP-T999",
        name="Test Thesis",
        status=status,
        priority="high",
        strategy_family="test",
        linked_rule_ids=linked or ["rule-1"],
        known_gaps=["missing data"] if status == "planned" else [],
    )


def _summary(
    rule_id: str = "rule-1",
    selected: int = 100,
    avg: float | None = 0.05,
    rate: float | None = 0.75,
    consistency: float | None = 0.04,
) -> RuleWalkForwardSummary:
    return RuleWalkForwardSummary(
        rule_id=rule_id,
        rule_name="Rule 1",
        valid_test_fold_count=3,
        total_test_selected_count=selected,
        avg_test_net_return=avg,
        median_test_net_return=avg,
        positive_test_fold_rate=rate,
        consistency_score=consistency,
    )


def _validation(summary: RuleWalkForwardSummary) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at="2026-05-31T00:00:00+00:00",
        config=WalkForwardConfig("cfg", 10, 5, 5),
        dataset_path="dataset.jsonl",
        row_count=100,
        filtered_row_count=100,
        fold_count=3,
        rules_tested=1,
        rule_summaries=[summary],
    )


def test_maps_rule_summaries_to_thesis_by_linked_rule_ids() -> None:
    mapped = ThesisEvaluator().map_rules_to_theses([_thesis()], [_summary()])
    assert mapped["MTP-T999"][0].rule_id == "rule-1"


def test_no_linked_summaries_needs_more_data() -> None:
    summary = ThesisEvaluator().evaluate_thesis(_thesis(), [])
    assert summary.recommended_status == "needs_more_data"
    assert "no_linked_validation_results" in summary.warning_flags


def test_insufficient_sample_needs_more_data() -> None:
    summary = ThesisEvaluator(min_total_test_selected_count=50).evaluate_thesis(_thesis(), [_summary(selected=10)])
    assert summary.recommended_status == "needs_more_data"
    assert "insufficient_test_sample" in summary.warning_flags


def test_negative_or_weak_test_performance_rejected_or_rework() -> None:
    summary = ThesisEvaluator(min_total_test_selected_count=50).evaluate_thesis(_thesis(), [_summary(selected=100, avg=-0.01, rate=0.4)])
    assert summary.recommended_status == "rejected_or_rework"


def test_strong_but_not_enough_for_paper_becomes_watchlist_for_planned() -> None:
    thesis = _thesis(status="planned")
    summary = ThesisEvaluator(min_total_test_selected_count=50).evaluate_thesis(thesis, [_summary(selected=100)])
    assert summary.recommended_status == "watchlist"


def test_paper_candidate_requires_active_or_watchlist_and_criteria() -> None:
    summary = ThesisEvaluator(min_total_test_selected_count=50).evaluate_thesis(_thesis(status="active"), [_summary(selected=100)])
    assert summary.recommended_status == "paper_candidate"


def test_planned_thesis_with_missing_data_stays_needs_more_data_when_no_summaries() -> None:
    summary = ThesisEvaluator().evaluate_thesis(_thesis(status="planned"), [])
    assert summary.recommended_status == "needs_more_data"
    assert "planned_thesis_missing_data" in summary.warning_flags


def test_evaluate_all_and_summary_to_decision_create_warnings() -> None:
    evaluator = ThesisEvaluator(min_total_test_selected_count=50)
    thesis = _thesis(status="active")
    summaries = evaluator.evaluate_all([thesis], [_validation(_summary(selected=100))])
    decision = evaluator.summary_to_decision(thesis, summaries[0])
    assert summaries[0].linked_validation_count == 1
    assert decision.thesis_id == "MTP-T999"
    assert "research_decision_not_trading_instruction" in decision.warning_flags
    assert "live_trading_disabled" in decision.warning_flags
    assert "requires_human_review" in decision.warning_flags


def test_thesis_does_not_get_rejected_when_sample_too_small() -> None:
    adequacy = SampleAdequacyReport(
        real_token_count=3,
        time_span_seconds=8040,
        valid_test_fold_count=4,
        total_test_selected_count=52,
        adequate_for_rejection=False,
        adequate_for_promotion=False,
        warning_flags=["diagnostic_sample_only"],
        recommended_data_expansion="add_more_real_candidates_and_expand_time_span",
    )
    summary = ThesisEvaluator(
        min_total_test_selected_count=50,
        sample_adequacy_report=adequacy,
    ).evaluate_thesis(_thesis(), [_summary(selected=100, avg=-0.01, rate=0.4)])

    assert summary.recommended_status == "needs_more_data"
    assert "insufficient_sample_for_demotion_or_promotion" in summary.warning_flags
    assert "diagnostic_sample_only" in summary.warning_flags
    assert summary.metadata_json["diagnostic_raw_recommendation"] == "rejected_or_rework"


def test_thesis_does_not_get_promoted_when_sample_too_small() -> None:
    adequacy = SampleAdequacyReport(
        real_token_count=3,
        time_span_seconds=8040,
        valid_test_fold_count=4,
        total_test_selected_count=100,
        adequate_for_rejection=False,
        adequate_for_promotion=False,
        warning_flags=["diagnostic_sample_only"],
        recommended_data_expansion="add_more_real_candidates_and_expand_time_span",
    )
    summary = ThesisEvaluator(
        min_total_test_selected_count=50,
        sample_adequacy_report=adequacy,
    ).evaluate_thesis(_thesis(status="active"), [_summary(selected=100)])

    assert summary.recommended_status == "needs_more_data"
    assert summary.metadata_json["diagnostic_raw_recommendation"] == "paper_candidate"
