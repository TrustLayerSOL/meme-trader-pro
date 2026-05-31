from research.mtp_research.backtest.rule_backtest_models import (
    RuleBacktestConfig,
    RuleBacktestResult,
    RuleBacktestSummary,
    RuleDefinition,
    SelectedTrade,
)
from research.mtp_research.validation.diagnostic_validation_models import (
    DiagnosticValidationReview,
)
from research.mtp_research.validation.diagnostic_validation_review import DiagnosticValidationReviewer
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.thesis_models import ThesisDecision
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardConfig,
    WalkForwardValidationResult,
)


def _row(row_id: str, quality: str = "sparse", source: str | None = None) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id=f"snapshot-{row_id}",
        outcome_id=f"outcome-{row_id}",
        token_mint="mint-1",
        snapshot_ts=100,
        window_name="1m",
        window_seconds=60,
        horizon_name="5m",
        horizon_seconds=300,
        entry_price=1.0,
        entry_price_source=source,
        forward_return=0.1,
        label_quality=quality,
    )


def _rule_result(rule_id: str, selected: int, nearest: int = 0) -> RuleBacktestResult:
    trades = [
        SelectedTrade(
            row_id=f"row-{idx}",
            token_mint="mint-1",
            snapshot_ts=idx,
            window_name="1m",
            horizon_name="5m",
            entry_price=1.0,
            end_price=1.1,
            gross_forward_return=0.1,
            net_forward_return=0.1,
            max_runup=0.2,
            max_drawdown=-0.1,
            rug_like_drop=False,
            no_future_liquidity=False,
            label_quality="sparse",
            metadata_json={
                "entry_price_source": "nearest_research_fallback" if idx < nearest else "exact_snapshot"
            },
        )
        for idx in range(selected)
    ]
    return RuleBacktestResult(
        result_id=f"result-{rule_id}-{selected}-{nearest}",
        created_at="2026-05-31T00:00:00+00:00",
        rule=RuleDefinition(rule_id=rule_id, name=rule_id),
        config=RuleBacktestConfig(config_id="cfg"),
        summary=RuleBacktestSummary(
            selected_count=selected,
            rows_with_return=selected,
            avg_net_return=0.1,
            win_rate=1.0,
        ),
        selected_trades=trades,
    )


def _walk_result(rule_id: str, valid_folds: int, selected: int) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id=f"wf-{rule_id}-{valid_folds}-{selected}",
        created_at="2026-05-31T00:00:00+00:00",
        config=WalkForwardConfig("cfg", 10, 5, 5),
        dataset_path="dataset.jsonl",
        row_count=selected,
        filtered_row_count=selected,
        fold_count=valid_folds,
        rules_tested=1,
        rule_summaries=[
            RuleWalkForwardSummary(
                rule_id=rule_id,
                rule_name=rule_id,
                valid_test_fold_count=valid_folds,
                total_test_selected_count=selected,
                avg_test_net_return=0.05,
                positive_test_fold_rate=0.75,
                consistency_score=0.04,
            )
        ],
    )


def _decision(thesis_id: str, status: str) -> ThesisDecision:
    return ThesisDecision(
        decision_id=f"decision-{thesis_id}-{status}",
        thesis_id=thesis_id,
        created_at="2026-05-31T00:00:00+00:00",
        prior_status="active",
        recommended_status=status,
        confidence=0.35,
        reason="test",
    )


def test_summarize_dataset_counts_nearest_fallback_and_quality() -> None:
    reviewer = DiagnosticValidationReviewer()
    summary = reviewer.summarize_dataset(
        [
            _row("row-1", "good", "nearest_research_fallback"),
            _row("row-2", "sparse", "exact_snapshot"),
            _row("row-3", "no_price", None),
        ],
        "diagnostic",
        "dataset.jsonl",
    )

    assert summary.row_count == 3
    assert summary.rows_with_nearest_fallback_entry == 1
    assert summary.sparse_or_better_rows == 2
    assert summary.good_rows == 1
    assert summary.entry_price_source_counts["nearest_research_fallback"] == 1


def test_compare_rule_results_calculates_gain_and_fallback_warning() -> None:
    comparisons = DiagnosticValidationReviewer().compare_rule_results(
        [_rule_result("rule-1", 2)],
        [_rule_result("rule-1", 5, nearest=3)],
    )

    assert comparisons[0].selected_count_gain == 3
    assert comparisons[0].diagnostic_nearest_fallback_selected_count == 3
    assert "gain_depends_on_nearest_fallback" in comparisons[0].warning_flags


def test_compare_walk_forward_matches_rules_and_fold_metrics() -> None:
    comparisons = DiagnosticValidationReviewer().compare_walk_forward(
        [_walk_result("rule-1", 0, 0)],
        [_walk_result("rule-1", 2, 12)],
    )

    assert comparisons[0].rule_id == "rule-1"
    assert comparisons[0].clean_valid_test_fold_count == 0
    assert comparisons[0].diagnostic_valid_test_fold_count == 2
    assert comparisons[0].diagnostic_total_test_selected_count == 12


def test_compare_thesis_decisions_marks_status_changes() -> None:
    comparisons = DiagnosticValidationReviewer().compare_thesis_decisions(
        [_decision("MTP-T001", "needs_more_data")],
        [_decision("MTP-T001", "watchlist")],
    )

    assert comparisons[0].changed is True
    assert "diagnostic_only_status_change" in comparisons[0].warning_flags


def test_recommend_next_action_handles_low_diagnostic_rows() -> None:
    reviewer = DiagnosticValidationReviewer()
    review = DiagnosticValidationReview(
        review_id="review",
        created_at="now",
        clean_dataset=reviewer.summarize_dataset([], "clean", "clean.jsonl"),
        diagnostic_dataset=reviewer.summarize_dataset([_row("row-1")], "diagnostic", "diag.jsonl"),
    )

    assert reviewer.recommend_next_action(review) == "scale_bounded_backfill_after_price_diagnostics"


def test_recommend_next_action_handles_fallback_dominated_gains() -> None:
    reviewer = DiagnosticValidationReviewer()
    review = reviewer.build_review(
        clean_dataset_rows=[_row(f"clean-{idx}") for idx in range(220)],
        diagnostic_dataset_rows=[
            _row(f"diag-{idx}", source="nearest_research_fallback" if idx < 120 else "exact_snapshot")
            for idx in range(240)
        ],
        clean_rule_results=[_rule_result("rule-1", 10)],
        diagnostic_rule_results=[_rule_result("rule-1", 30, nearest=20)],
        clean_walk_forward_results=[_walk_result("rule-1", 1, 10)],
        diagnostic_walk_forward_results=[_walk_result("rule-1", 1, 30)],
        clean_thesis_decisions=[_decision("MTP-T001", "needs_more_data")],
        diagnostic_thesis_decisions=[_decision("MTP-T001", "needs_more_data")],
        clean_dataset_path="clean.jsonl",
        diagnostic_dataset_path="diag.jsonl",
    )

    assert review.recommended_next_action == "improve_clean_price_inference_before_scaling"
