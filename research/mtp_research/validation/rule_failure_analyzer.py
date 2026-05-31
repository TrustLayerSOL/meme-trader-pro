"""Analyze why diagnostic walk-forward rules are failing."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median

from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.rule_failure_models import (
    RuleFailureAnatomy,
    RuleFailureReview,
    RuleFoldAnatomy,
    make_rule_failure_review_id,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_models import (
    FoldRuleResult,
    RuleWalkForwardSummary,
    WalkForwardValidationResult,
)


BASE_WARNINGS = [
    "diagnostic_only_not_strategy_signal",
    "no_live_trading",
    "no_thesis_promotion",
]


class RuleFailureAnalyzer:
    """Build diagnostic-only failure anatomy from walk-forward results."""

    def build_review(
        self,
        dataset_rows: list[ResearchDatasetRow],
        validation_result: WalkForwardValidationResult,
        dataset_path: str,
        walk_forward_path: str,
    ) -> RuleFailureReview:
        timestamps = [row.snapshot_ts for row in dataset_rows]
        time_span = (max(timestamps) - min(timestamps)) if timestamps else None
        nearest_count = sum(
            1 for row in dataset_rows if row.entry_price_source == "nearest_research_fallback"
        )
        folds_by_id = {fold.fold_id: fold for fold in validation_result.folds}
        enriched_fold_rule_results = []
        for result in validation_result.fold_rule_results:
            fold = folds_by_id.get(result.fold_id)
            if fold is not None:
                result.metadata_json = {
                    **result.metadata_json,
                    "test_start_ts": fold.test_start_ts,
                    "test_end_ts": fold.test_end_ts,
                }
            enriched_fold_rule_results.append(result)
        rule_anatomies = [
            self.analyze_rule(
                summary,
                [
                    result
                    for result in enriched_fold_rule_results
                    if result.rule_id == summary.rule_id
                ],
                dataset_rows,
            )
            for summary in validation_result.rule_summaries
        ]
        review = RuleFailureReview(
            review_id=make_rule_failure_review_id(),
            created_at=utc_now_iso(),
            dataset_path=dataset_path,
            walk_forward_path=walk_forward_path,
            row_count=len(dataset_rows),
            token_count=len({row.token_mint for row in dataset_rows}),
            time_span_seconds=time_span,
            nearest_fallback_row_count=nearest_count,
            rule_anatomies=rule_anatomies,
            warning_flags=sorted(
                set(BASE_WARNINGS + (["fallback_dataset_warning"] if nearest_count else []))
            ),
            metadata_json={
                "validation_id": validation_result.validation_id,
                "diagnostic_only": True,
            },
        )
        for anatomy in review.rule_anatomies:
            anatomy.metadata_json["review_token_count"] = review.token_count
            anatomy.metadata_json["review_time_span_seconds"] = review.time_span_seconds
            anatomy.likely_failure_causes = self.infer_failure_causes(anatomy)
        review.recommended_next_action = self.recommend_next_action(review)
        review.evidence_scale_recommendation = self.recommend_evidence_scale(review)
        review.rule_review_recommendation = self.recommend_rule_review(review)
        return review

    def analyze_rule(
        self,
        rule_summary: RuleWalkForwardSummary,
        fold_rule_results: list[FoldRuleResult],
        dataset_rows: list[ResearchDatasetRow],
    ) -> RuleFailureAnatomy:
        fold_anatomies = [
            self.analyze_fold(rule_summary.rule_id, fold_result, dataset_rows)
            for fold_result in fold_rule_results
        ]
        selected_rows = _selected_rows_for_rule(rule_summary.rule_id, dataset_rows)
        token_counts = Counter(row.token_mint for row in selected_rows)
        losing_token_counts = Counter(
            row.token_mint for row in selected_rows if (row.forward_return or 0.0) <= 0
        )
        fallback_count = sum(
            1 for row in selected_rows if row.entry_price_source == "nearest_research_fallback"
        )
        rug_count = sum(1 for row in selected_rows if row.rug_like_drop is True)
        no_liquidity_count = sum(1 for row in selected_rows if row.no_future_liquidity)
        gross_values = [row.forward_return for row in selected_rows if row.forward_return is not None]
        gross_mean = mean(gross_values) if gross_values else None
        gross_minus_net_gap = (
            gross_mean - rule_summary.avg_test_net_return
            if gross_mean is not None and rule_summary.avg_test_net_return is not None
            else None
        )
        anatomy = RuleFailureAnatomy(
            rule_id=rule_summary.rule_id,
            rule_name=rule_summary.rule_name,
            valid_test_fold_count=rule_summary.valid_test_fold_count,
            positive_test_fold_count=rule_summary.positive_test_fold_count,
            negative_test_fold_count=rule_summary.negative_test_fold_count,
            positive_test_fold_rate=rule_summary.positive_test_fold_rate,
            total_test_selected_count=rule_summary.total_test_selected_count,
            avg_test_selected_count=rule_summary.avg_test_selected_count,
            avg_test_net_return=rule_summary.avg_test_net_return,
            median_test_net_return=rule_summary.median_test_net_return,
            avg_cost_drag=gross_minus_net_gap,
            estimated_gross_minus_net_gap=gross_minus_net_gap,
            token_concentration=dict(token_counts),
            losing_token_counts=dict(losing_token_counts),
            fallback_entry_count=fallback_count,
            fallback_entry_rate=(fallback_count / len(selected_rows)) if selected_rows else None,
            rug_like_drop_count=rug_count,
            no_future_liquidity_count=no_liquidity_count,
            fold_anatomies=fold_anatomies,
            warning_flags=sorted(set(rule_summary.warning_flags)),
            metadata_json={
                "selected_dataset_rows": len(selected_rows),
                "gross_mean_selected_forward_return": gross_mean,
            },
        )
        anatomy.likely_failure_causes = self.infer_failure_causes(anatomy)
        return anatomy

    def analyze_fold(
        self,
        rule_id: str,
        fold_result: FoldRuleResult,
        dataset_rows: list[ResearchDatasetRow],
    ) -> RuleFoldAnatomy:
        selected_rows = [
            row for row in _selected_rows_for_rule(rule_id, dataset_rows)
            if _row_in_test_fold(row, fold_result)
        ]
        fallback_count = sum(
            1 for row in selected_rows if row.entry_price_source == "nearest_research_fallback"
        )
        no_liquidity_count = sum(1 for row in selected_rows if row.no_future_liquidity)
        warning_flags = list(fold_result.warning_flags)
        if fallback_count and selected_rows and fallback_count / len(selected_rows) > 0.5:
            warning_flags.append("fallback_dependency")
        return RuleFoldAnatomy(
            rule_id=rule_id,
            fold_id=fold_result.fold_id,
            fold_index=fold_result.fold_index,
            test_selected_count=fold_result.test_selected_count,
            test_avg_net_return=fold_result.test_avg_net_return,
            test_median_net_return=fold_result.test_median_net_return,
            test_win_rate=fold_result.test_win_rate,
            test_profit_factor=fold_result.test_profit_factor,
            test_rug_like_drop_rate=fold_result.test_rug_like_drop_rate,
            test_no_future_liquidity_rate=(
                no_liquidity_count / len(selected_rows) if selected_rows else None
            ),
            fallback_entry_count=fallback_count,
            fallback_entry_rate=(fallback_count / len(selected_rows)) if selected_rows else None,
            token_counts=dict(Counter(row.token_mint for row in selected_rows)),
            warning_flags=sorted(set(warning_flags)),
            metadata_json={"selected_rows_reconstructed": len(selected_rows)},
        )

    def infer_failure_causes(self, anatomy: RuleFailureAnatomy) -> list[str]:
        causes = []
        if anatomy.total_test_selected_count < 50:
            causes.append("small_sample")
        if anatomy.valid_test_fold_count < 5:
            causes.append("too_few_valid_folds")
        if anatomy.positive_test_fold_rate is not None and anatomy.positive_test_fold_rate < 0.5:
            causes.append("low_positive_fold_rate")
        if anatomy.estimated_gross_minus_net_gap is not None and anatomy.estimated_gross_minus_net_gap >= 0.04:
            causes.append("cost_drag_problem")
        if _dominant_share(anatomy.token_concentration) > 0.6:
            causes.append("token_concentration")
        if anatomy.fallback_entry_rate is not None and anatomy.fallback_entry_rate > 0.5:
            causes.append("fallback_dependency")
        selected_count = max(anatomy.total_test_selected_count, 1)
        if (anatomy.rug_like_drop_count + anatomy.no_future_liquidity_count) / selected_count >= 0.2:
            causes.append("rug_or_liquidity_problem")
        if anatomy.total_test_selected_count >= 250 and (anatomy.avg_test_net_return or 0.0) <= 0:
            causes.append("weak_rule_selectivity")
        if anatomy.total_test_selected_count < 10:
            causes.append("over_narrow_rule")
        if (anatomy.metadata_json.get("review_time_span_seconds") or 0) < 14400:
            causes.append("insufficient_time_span")
        if (anatomy.metadata_json.get("review_token_count") or 0) < 5:
            causes.append("insufficient_token_diversity")
        return sorted(set(causes))

    def recommend_next_action(self, review: RuleFailureReview) -> str:
        if review.token_count < 5:
            return "scale_candidate_diversity_with_bounded_backfill"
        if (review.time_span_seconds or 0) < 14400:
            return "scale_time_span_with_bounded_backfill"
        if _most_rules_have(review, "small_sample"):
            return "scale_bounded_backfill_for_sample_size"
        if _most_rules_have(review, "fallback_dependency"):
            return "improve_clean_price_inference"
        if _most_rules_have(review, "weak_rule_selectivity") or _most_rules_have(review, "cost_drag_problem"):
            return "review_rule_logic_and_cost_assumptions"
        if any(
            anatomy.rule_id == "buy_imbalance_basic"
            and anatomy.valid_test_fold_count > 0
            and (anatomy.avg_test_net_return or 0.0) > 0
            for anatomy in review.rule_anatomies
        ):
            return "manual_thesis_review_before_more_scale"
        return "bounded_backfill_then_retest"

    def recommend_evidence_scale(self, review: RuleFailureReview) -> str:
        low_tokens = review.token_count < 5
        short_span = (review.time_span_seconds or 0) < 14400
        if low_tokens and short_span:
            return "add_candidates_and_time_span"
        if low_tokens:
            return "add_more_real_candidates"
        if short_span:
            return "expand_time_span_per_pool"
        return "bounded_incremental_only"

    def recommend_rule_review(self, review: RuleFailureReview) -> str:
        buy_imbalance = next(
            (anatomy for anatomy in review.rule_anatomies if anatomy.rule_id == "buy_imbalance_basic"),
            None,
        )
        if buy_imbalance and buy_imbalance.valid_test_fold_count > 0 and (
            buy_imbalance.positive_test_fold_rate or 0.0
        ) < 0.5:
            return "inspect selected buy_imbalance_basic rows before changing thresholds"
        if _most_rules_have(review, "cost_drag_problem"):
            return "separate_gross_edge_from_cost_drag"
        if all(anatomy.total_test_selected_count < 10 for anatomy in review.rule_anatomies):
            return "broaden_exploratory_rules_carefully_without_parameter_search"
        return "do_not_optimize_yet_collect_more_evidence"


def _selected_rows_for_rule(rule_id: str, rows: list[ResearchDatasetRow]) -> list[ResearchDatasetRow]:
    rule = next((item for item in default_rule_library() if item.rule_id == rule_id), None)
    if rule is None:
        return []
    backtester = RuleBacktester()
    return [row for row in rows if backtester.row_passes_rule(row, rule)]


def _row_in_test_fold(row: ResearchDatasetRow, fold_result: FoldRuleResult) -> bool:
    start = fold_result.metadata_json.get("test_start_ts")
    end = fold_result.metadata_json.get("test_end_ts")
    if start is None or end is None:
        return True
    return start <= row.snapshot_ts <= end


def _dominant_share(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    return (max(counts.values()) / total) if total else 0.0


def _most_rules_have(review: RuleFailureReview, cause: str) -> bool:
    if not review.rule_anatomies:
        return False
    count = sum(1 for anatomy in review.rule_anatomies if cause in anatomy.likely_failure_causes)
    return count / len(review.rule_anatomies) >= 0.5
