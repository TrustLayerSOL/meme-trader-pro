from research.mtp_research.validation.evidence_expansion_decision import (
    EvidenceExpansionDecisionAnalyzer,
)
from research.mtp_research.validation.evidence_expansion_decision_models import (
    RuleExpansionSignal,
)


def test_classify_rule_signal_identifies_weak_noisy() -> None:
    signal = RuleExpansionSignal(
        rule_id="rule-1",
        rule_name="Rule 1",
        median_net_return=-0.01,
        positive_fold_rate=0.25,
    )

    assert EvidenceExpansionDecisionAnalyzer().classify_rule_signal(signal) == "weak_noisy"


def test_classify_rule_signal_identifies_outlier_dependent() -> None:
    signal = RuleExpansionSignal(
        rule_id="rule-1",
        rule_name="Rule 1",
        outlier_return_share=0.9,
    )

    assert EvidenceExpansionDecisionAnalyzer().classify_rule_signal(signal) == "outlier_dependent"


def test_classify_rule_signal_identifies_watch_for_more_data() -> None:
    signal = RuleExpansionSignal(
        rule_id="rule-1",
        rule_name="Rule 1",
        capped_mean_return=0.02,
        median_net_return=0.0,
        plausible_outlier_count=3,
        suspicious_outlier_count=1,
    )

    assert EvidenceExpansionDecisionAnalyzer().classify_rule_signal(signal) == "watch_for_more_data"


def test_determine_expansion_needs_adds_tokens_span_and_price_coverage() -> None:
    needs = EvidenceExpansionDecisionAnalyzer().determine_expansion_needs(
        real_token_count=10,
        time_span_seconds=3600,
        price_coverage_rate=0.4,
        no_price_label_count=100,
        rule_signals=[],
    )

    need_types = {need.need_type for need in needs}
    assert "add_more_tokens" in need_types
    assert "expand_time_span" in need_types
    assert "improve_price_coverage" in need_types


def test_bounded_plan_is_never_unbounded_and_includes_execute_command() -> None:
    analyzer = EvidenceExpansionDecisionAnalyzer()
    needs = analyzer.determine_expansion_needs(
        real_token_count=10,
        time_span_seconds=3600,
        price_coverage_rate=0.8,
        no_price_label_count=0,
        rule_signals=[],
    )

    plan = analyzer.build_bounded_plan(needs, current_real_token_count=10, current_time_span_seconds=3600)

    assert plan.recommended is True
    assert plan.candidate_limit == 15
    assert plan.stop_after_targets == 20
    assert plan.estimated_signature_requests == 3000
    assert "--execute" in (plan.recommended_command or "")
