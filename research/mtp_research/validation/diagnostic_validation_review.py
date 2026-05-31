"""Build diagnostic clean-vs-nearest-fallback validation reviews."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestResult
from research.mtp_research.validation.diagnostic_validation_models import (
    DIAGNOSTIC_FALLBACK_WARNING,
    DiagnosticDatasetSummary,
    DiagnosticRuleComparison,
    DiagnosticThesisComparison,
    DiagnosticValidationReview,
    DiagnosticWalkForwardComparison,
    make_diagnostic_validation_review_id,
)
from research.mtp_research.validation.research_dataset_builder import _quality_rank
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.thesis_models import ThesisDecision
from research.mtp_research.validation.walk_forward_models import WalkForwardValidationResult


class DiagnosticValidationReviewer:
    """Compare canonical clean validation against diagnostic nearest-entry fallback validation."""

    def summarize_dataset(
        self,
        rows: list[ResearchDatasetRow],
        name: str,
        dataset_path: str,
    ) -> DiagnosticDatasetSummary:
        return DiagnosticDatasetSummary(
            name=name,
            dataset_path=dataset_path,
            row_count=len(rows),
            token_count=len({row.token_mint for row in rows}),
            rows_with_forward_return=sum(1 for row in rows if row.forward_return is not None),
            rows_with_nearest_fallback_entry=sum(
                1 for row in rows
                if row.entry_price_source == "nearest_research_fallback"
            ),
            sparse_or_better_rows=sum(
                1 for row in rows
                if _quality_rank(row.label_quality) >= _quality_rank("sparse")
            ),
            good_rows=sum(1 for row in rows if row.label_quality == "good"),
            label_quality_counts=_counter(row.label_quality for row in rows),
            entry_price_source_counts=_counter(row.entry_price_source or "missing" for row in rows),
            horizon_counts=_counter(row.horizon_name for row in rows),
            window_counts=_counter(row.window_name for row in rows),
            metadata_json={"summary_version": "diagnostic_dataset_summary_v0"},
        )

    def compare_rule_results(
        self,
        clean_results: list[RuleBacktestResult],
        diagnostic_results: list[RuleBacktestResult],
    ) -> list[DiagnosticRuleComparison]:
        clean_by_rule = _latest_rule_result_by_rule_id(clean_results)
        diagnostic_by_rule = _latest_rule_result_by_rule_id(diagnostic_results)
        output = []
        for rule_id in sorted(set(clean_by_rule) | set(diagnostic_by_rule)):
            clean = clean_by_rule.get(rule_id)
            diagnostic = diagnostic_by_rule.get(rule_id)
            clean_selected = clean.summary.selected_count if clean else 0
            diagnostic_selected = diagnostic.summary.selected_count if diagnostic else 0
            nearest_count = _selected_nearest_fallback_count(diagnostic)
            gain = diagnostic_selected - clean_selected
            warning_flags = []
            if gain > 0 and nearest_count >= max(1, int(gain * 0.5)):
                warning_flags.append("gain_depends_on_nearest_fallback")
            if diagnostic_selected == 0:
                warning_flags.append("no_diagnostic_selected_rows")
            output.append(
                DiagnosticRuleComparison(
                    rule_id=rule_id,
                    clean_selected_count=clean_selected,
                    diagnostic_selected_count=diagnostic_selected,
                    selected_count_gain=gain,
                    clean_avg_net_return=clean.summary.avg_net_return if clean else None,
                    diagnostic_avg_net_return=diagnostic.summary.avg_net_return if diagnostic else None,
                    clean_win_rate=clean.summary.win_rate if clean else None,
                    diagnostic_win_rate=diagnostic.summary.win_rate if diagnostic else None,
                    diagnostic_nearest_fallback_selected_count=nearest_count,
                    warning_flags=warning_flags,
                )
            )
        return output

    def compare_walk_forward(
        self,
        clean_results: list[WalkForwardValidationResult],
        diagnostic_results: list[WalkForwardValidationResult],
    ) -> list[DiagnosticWalkForwardComparison]:
        clean = _latest_walk_forward_result(clean_results)
        diagnostic = _latest_walk_forward_result(diagnostic_results)
        clean_by_rule = {summary.rule_id: summary for summary in clean.rule_summaries} if clean else {}
        diagnostic_by_rule = {summary.rule_id: summary for summary in diagnostic.rule_summaries} if diagnostic else {}
        output = []
        for rule_id in sorted(set(clean_by_rule) | set(diagnostic_by_rule)):
            clean_summary = clean_by_rule.get(rule_id)
            diagnostic_summary = diagnostic_by_rule.get(rule_id)
            warning_flags = []
            if (
                diagnostic_summary
                and diagnostic_summary.valid_test_fold_count > 0
                and diagnostic_summary.total_test_selected_count < 20
            ):
                warning_flags.append("diagnostic_evidence_still_small_sample")
            if diagnostic_summary and diagnostic_summary.valid_test_fold_count == 0:
                warning_flags.append("diagnostic_no_valid_test_folds")
            output.append(
                DiagnosticWalkForwardComparison(
                    rule_id=rule_id,
                    clean_valid_test_fold_count=clean_summary.valid_test_fold_count if clean_summary else 0,
                    diagnostic_valid_test_fold_count=(
                        diagnostic_summary.valid_test_fold_count if diagnostic_summary else 0
                    ),
                    clean_total_test_selected_count=clean_summary.total_test_selected_count if clean_summary else 0,
                    diagnostic_total_test_selected_count=(
                        diagnostic_summary.total_test_selected_count if diagnostic_summary else 0
                    ),
                    clean_avg_test_net_return=clean_summary.avg_test_net_return if clean_summary else None,
                    diagnostic_avg_test_net_return=(
                        diagnostic_summary.avg_test_net_return if diagnostic_summary else None
                    ),
                    clean_positive_test_fold_rate=(
                        clean_summary.positive_test_fold_rate if clean_summary else None
                    ),
                    diagnostic_positive_test_fold_rate=(
                        diagnostic_summary.positive_test_fold_rate if diagnostic_summary else None
                    ),
                    clean_consistency_score=clean_summary.consistency_score if clean_summary else None,
                    diagnostic_consistency_score=(
                        diagnostic_summary.consistency_score if diagnostic_summary else None
                    ),
                    warning_flags=warning_flags,
                )
            )
        return output

    def compare_thesis_decisions(
        self,
        clean_decisions: list[ThesisDecision],
        diagnostic_decisions: list[ThesisDecision],
    ) -> list[DiagnosticThesisComparison]:
        clean_by_thesis = _latest_thesis_decision_by_thesis_id(clean_decisions)
        diagnostic_by_thesis = _latest_thesis_decision_by_thesis_id(diagnostic_decisions)
        output = []
        for thesis_id in sorted(set(clean_by_thesis) | set(diagnostic_by_thesis)):
            clean = clean_by_thesis.get(thesis_id)
            diagnostic = diagnostic_by_thesis.get(thesis_id)
            clean_status = clean.recommended_status if clean else None
            diagnostic_status = diagnostic.recommended_status if diagnostic else None
            changed = clean_status != diagnostic_status
            warning_flags = []
            if changed:
                warning_flags.append("diagnostic_only_status_change")
            output.append(
                DiagnosticThesisComparison(
                    thesis_id=thesis_id,
                    clean_recommended_status=clean_status,
                    diagnostic_recommended_status=diagnostic_status,
                    changed=changed,
                    warning_flags=warning_flags,
                )
            )
        return output

    def recommend_next_action(self, review: DiagnosticValidationReview) -> str:
        if review.diagnostic_dataset.rows_with_forward_return < 200:
            return "scale_bounded_backfill_after_price_diagnostics"
        if any(item.changed for item in review.thesis_comparisons):
            return "human_review_before_any_promotion"
        if _nearest_fallback_dominates_gains(review):
            return "improve_clean_price_inference_before_scaling"
        if (
            review.forward_return_row_gain > 0
            and not any(item.diagnostic_valid_test_fold_count > 0 for item in review.walk_forward_comparisons)
        ):
            return "scale_bounded_backfill_or_adjust_fold_windows"
        if (
            any(item.diagnostic_valid_test_fold_count > 0 for item in review.walk_forward_comparisons)
            and all(item.diagnostic_recommended_status == "needs_more_data" for item in review.thesis_comparisons)
        ):
            return "inspect_rule_selection_and_min_sample_thresholds"
        return "continue_evidence_population_cautiously"

    def build_review(
        self,
        clean_dataset_rows: list[ResearchDatasetRow],
        diagnostic_dataset_rows: list[ResearchDatasetRow],
        clean_rule_results: list[RuleBacktestResult],
        diagnostic_rule_results: list[RuleBacktestResult],
        clean_walk_forward_results: list[WalkForwardValidationResult],
        diagnostic_walk_forward_results: list[WalkForwardValidationResult],
        clean_thesis_decisions: list[ThesisDecision],
        diagnostic_thesis_decisions: list[ThesisDecision],
        clean_dataset_path: str,
        diagnostic_dataset_path: str,
    ) -> DiagnosticValidationReview:
        clean_summary = self.summarize_dataset(clean_dataset_rows, "clean", clean_dataset_path)
        diagnostic_summary = self.summarize_dataset(
            diagnostic_dataset_rows,
            "diagnostic_nearest300",
            diagnostic_dataset_path,
        )
        review = DiagnosticValidationReview(
            review_id=make_diagnostic_validation_review_id(),
            created_at=datetime.now(timezone.utc).isoformat(),
            clean_dataset=clean_summary,
            diagnostic_dataset=diagnostic_summary,
            row_gain=diagnostic_summary.row_count - clean_summary.row_count,
            forward_return_row_gain=(
                diagnostic_summary.rows_with_forward_return - clean_summary.rows_with_forward_return
            ),
            nearest_fallback_row_count=diagnostic_summary.rows_with_nearest_fallback_entry,
            rule_comparisons=self.compare_rule_results(clean_rule_results, diagnostic_rule_results),
            walk_forward_comparisons=self.compare_walk_forward(
                clean_walk_forward_results,
                diagnostic_walk_forward_results,
            ),
            thesis_comparisons=self.compare_thesis_decisions(
                clean_thesis_decisions,
                diagnostic_thesis_decisions,
            ),
            warning_flags=[
                DIAGNOSTIC_FALLBACK_WARNING,
                "nearest_fallback_research_only",
                "canonical_clean_dataset_remains_source_of_truth",
            ],
            metadata_json={"review_version": "diagnostic_validation_review_v0"},
        )
        review.recommended_next_action = self.recommend_next_action(review)
        return review


def _counter(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _latest_rule_result_by_rule_id(results: list[RuleBacktestResult]) -> dict[str, RuleBacktestResult]:
    output: dict[str, RuleBacktestResult] = {}
    for result in sorted(results, key=lambda item: (item.created_at, item.result_id)):
        output[result.rule.rule_id] = result
    return output


def _latest_walk_forward_result(
    results: list[WalkForwardValidationResult],
) -> WalkForwardValidationResult | None:
    if not results:
        return None
    return sorted(results, key=lambda item: (item.created_at, item.validation_id))[-1]


def _latest_thesis_decision_by_thesis_id(decisions: list[ThesisDecision]) -> dict[str, ThesisDecision]:
    output: dict[str, ThesisDecision] = {}
    for decision in sorted(decisions, key=lambda item: (item.created_at, item.decision_id)):
        output[decision.thesis_id] = decision
    return output


def _selected_nearest_fallback_count(result: RuleBacktestResult | None) -> int:
    if result is None:
        return 0
    return sum(
        1 for trade in result.selected_trades
        if trade.metadata_json.get("entry_price_source") == "nearest_research_fallback"
    )


def _nearest_fallback_dominates_gains(review: DiagnosticValidationReview) -> bool:
    positive_gain = sum(max(0, item.selected_count_gain) for item in review.rule_comparisons)
    fallback_selected = sum(item.diagnostic_nearest_fallback_selected_count for item in review.rule_comparisons)
    return positive_gain > 0 and fallback_selected >= max(1, int(positive_gain * 0.5))
