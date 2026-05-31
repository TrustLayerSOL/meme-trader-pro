"""Sample adequacy checks for diagnostic thesis decisions."""

from __future__ import annotations

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.thesis_models import SampleAdequacyReport
from research.mtp_research.validation.walk_forward_models import WalkForwardValidationResult


class SampleAdequacyAnalyzer:
    """Gate thesis status changes until diagnostic samples are large enough."""

    def __init__(
        self,
        min_real_token_count: int = 10,
        min_time_span_seconds: int = 43_200,
        min_valid_test_folds: int = 10,
        min_total_test_selected_count: int = 100,
        min_independent_batches: int = 1,
    ):
        self.min_real_token_count = min_real_token_count
        self.min_time_span_seconds = min_time_span_seconds
        self.min_valid_test_folds = min_valid_test_folds
        self.min_total_test_selected_count = min_total_test_selected_count
        self.min_independent_batches = min_independent_batches

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        validation_results: list[WalkForwardValidationResult],
    ) -> SampleAdequacyReport:
        timestamps = [row.snapshot_ts for row in rows]
        time_span = (max(timestamps) - min(timestamps)) if timestamps else None
        valid_folds = sum(
            summary.valid_test_fold_count
            for result in validation_results
            for summary in result.rule_summaries
        )
        selected_count = sum(
            summary.total_test_selected_count
            for result in validation_results
            for summary in result.rule_summaries
        )
        token_count = len({row.token_mint for row in rows})
        warning_flags = ["diagnostic_sample_only"]
        if token_count < self.min_real_token_count:
            warning_flags.append("insufficient_real_token_count")
        if (time_span or 0) < self.min_time_span_seconds:
            warning_flags.append("insufficient_time_span")
        if valid_folds < self.min_valid_test_folds:
            warning_flags.append("insufficient_valid_test_folds")
        if selected_count < self.min_total_test_selected_count:
            warning_flags.append("insufficient_selected_test_count")

        adequate = not {
            "insufficient_real_token_count",
            "insufficient_time_span",
            "insufficient_valid_test_folds",
            "insufficient_selected_test_count",
        }.intersection(warning_flags)
        return SampleAdequacyReport(
            real_token_count=token_count,
            time_span_seconds=time_span,
            valid_test_fold_count=valid_folds,
            total_test_selected_count=selected_count,
            adequate_for_rejection=adequate,
            adequate_for_promotion=adequate,
            warning_flags=sorted(set(warning_flags)),
            recommended_data_expansion=self.recommend_data_expansion(
                token_count,
                time_span,
                selected_count,
            ),
        )

    def recommend_data_expansion(
        self,
        token_count: int,
        time_span_seconds: int | None,
        selected_test_count: int,
    ) -> str:
        needs_candidates = token_count < self.min_real_token_count
        needs_span = (time_span_seconds or 0) < self.min_time_span_seconds
        needs_sample = selected_test_count < self.min_total_test_selected_count
        if needs_candidates and needs_span:
            return "add_more_real_candidates_and_expand_time_span"
        if needs_candidates:
            return "add_more_real_candidates"
        if needs_span:
            return "expand_time_span_per_pool"
        if needs_sample:
            return "increase_bounded_backfill_sample"
        return "sample_adequate_continue_review"
