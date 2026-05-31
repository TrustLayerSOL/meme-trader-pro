from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.rule_failure_analyzer import RuleFailureAnalyzer
from research.mtp_research.validation.walk_forward_models import (
    FoldRuleResult,
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardValidationResult,
    utc_now_iso,
)


def _row(
    row_id: str,
    token: str = "mint-1",
    snapshot_ts: int = 100,
    entry_source: str = "exact_snapshot",
    forward_return: float = 0.1,
) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint=token,
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="1m",
        horizon_seconds=60,
        possible_buy_count=2,
        possible_sell_count=0,
        buy_sell_imbalance=0.8,
        unique_actor_count=3,
        quote_volume=10,
        confidence_weighted_net_flow=1,
        entry_price_source=entry_source,
        entry_price=1,
        forward_return=forward_return,
        max_drawdown=-0.1,
        rug_like_drop=False,
        no_future_liquidity=False,
        label_quality="sparse",
    )


def _summary(
    rule_id: str = "buy_imbalance_basic",
    selected_count: int = 20,
    valid_folds: int = 2,
    positive_rate: float | None = 0.25,
    avg_net: float | None = -0.05,
) -> RuleWalkForwardSummary:
    return RuleWalkForwardSummary(
        rule_id=rule_id,
        rule_name="Buy Imbalance Basic",
        valid_test_fold_count=valid_folds,
        positive_test_fold_count=1,
        negative_test_fold_count=3,
        positive_test_fold_rate=positive_rate,
        total_test_selected_count=selected_count,
        avg_test_selected_count=selected_count / max(valid_folds, 1),
        avg_test_net_return=avg_net,
        median_test_net_return=avg_net,
    )


def _result(summary: RuleWalkForwardSummary) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id="validation-1",
        created_at=utc_now_iso(),
        config=WalkForwardConfig("best", 900, 300, 300),
        dataset_path="dataset.jsonl",
        row_count=10,
        filtered_row_count=10,
        fold_count=1,
        rules_tested=1,
        folds=[WalkForwardFold("fold-1", 0, 0, 99, 100, 500)],
        fold_rule_results=[
            FoldRuleResult(
                fold_id="fold-1",
                fold_index=0,
                rule_id=summary.rule_id,
                rule_name=summary.rule_name,
                test_selected_count=summary.total_test_selected_count,
                test_avg_net_return=summary.avg_test_net_return,
            )
        ],
        rule_summaries=[summary],
    )


def test_analyzer_detects_small_sample_and_low_positive_fold_rate() -> None:
    review = RuleFailureAnalyzer().build_review(
        [_row("1"), _row("2")],
        _result(_summary()),
        "dataset.jsonl",
        "walk.jsonl",
    )

    causes = review.rule_anatomies[0].likely_failure_causes
    assert "small_sample" in causes
    assert "low_positive_fold_rate" in causes


def test_analyzer_detects_insufficient_token_diversity_and_time_span() -> None:
    review = RuleFailureAnalyzer().build_review(
        [_row("1", snapshot_ts=100), _row("2", snapshot_ts=200)],
        _result(_summary(selected_count=80, valid_folds=6)),
        "dataset.jsonl",
        "walk.jsonl",
    )

    causes = review.rule_anatomies[0].likely_failure_causes
    assert "insufficient_token_diversity" in causes
    assert "insufficient_time_span" in causes


def test_analyzer_detects_fallback_dependency() -> None:
    rows = [_row(str(index), entry_source="nearest_research_fallback") for index in range(4)]
    review = RuleFailureAnalyzer().build_review(
        rows,
        _result(_summary(selected_count=80, valid_folds=6)),
        "dataset.jsonl",
        "walk.jsonl",
    )

    assert "fallback_dependency" in review.rule_anatomies[0].likely_failure_causes


def test_analyzer_recommends_add_candidates_when_token_count_low() -> None:
    review = RuleFailureAnalyzer().build_review(
        [_row("1"), _row("2")],
        _result(_summary(selected_count=80, valid_folds=6)),
        "dataset.jsonl",
        "walk.jsonl",
    )

    assert review.recommended_next_action == "scale_candidate_diversity_with_bounded_backfill"
    assert review.evidence_scale_recommendation == "add_candidates_and_time_span"


def test_analyzer_recommends_expand_time_span_when_span_short() -> None:
    rows = [_row(str(index), token=f"mint-{index}", snapshot_ts=100 + index) for index in range(5)]
    review = RuleFailureAnalyzer().build_review(
        rows,
        _result(_summary(selected_count=80, valid_folds=6)),
        "dataset.jsonl",
        "walk.jsonl",
    )

    assert review.recommended_next_action == "scale_time_span_with_bounded_backfill"
    assert review.evidence_scale_recommendation == "expand_time_span_per_pool"
