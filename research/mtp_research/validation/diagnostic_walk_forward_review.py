"""Diagnostic-only walk-forward review helpers."""

from __future__ import annotations

from typing import Any

from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.backtest.rule_library import default_rule_library
from research.mtp_research.validation.diagnostic_walk_forward_models import (
    DiagnosticRuleWalkForwardFinding,
    DiagnosticWalkForwardReview,
    make_diagnostic_walk_forward_review_id,
    utc_now_iso,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardValidationResult,
)


DIAGNOSTIC_WARNINGS = [
    "diagnostic_fallback_not_for_live_trading",
    "no_thesis_promotion_without_human_review",
]


class DiagnosticWalkForwardReviewer:
    """Summarize best diagnostic walk-forward results without promotion logic."""

    def summarize_dataset(self, rows: list[ResearchDatasetRow]) -> dict[str, Any]:
        timestamps = [row.snapshot_ts for row in rows]
        return {
            "row_count": len(rows),
            "token_count": len({row.token_mint for row in rows}),
            "time_span_seconds": (max(timestamps) - min(timestamps)) if timestamps else None,
            "nearest_fallback_row_count": sum(
                1 for row in rows if row.entry_price_source == "nearest_research_fallback"
            ),
        }

    def build_findings(
        self,
        validation_result: WalkForwardValidationResult,
        dataset_rows: list[ResearchDatasetRow],
    ) -> list[DiagnosticRuleWalkForwardFinding]:
        findings = []
        for summary in validation_result.rule_summaries:
            fallback_warning = self.estimate_fallback_dependency(summary, dataset_rows)
            warning_flags = list(summary.warning_flags)
            if fallback_warning:
                warning_flags.append("fallback_dependency_warning")
            findings.append(
                DiagnosticRuleWalkForwardFinding(
                    rule_id=summary.rule_id,
                    rule_name=summary.rule_name,
                    valid_test_fold_count=summary.valid_test_fold_count,
                    total_test_selected_count=summary.total_test_selected_count,
                    avg_test_selected_count=summary.avg_test_selected_count,
                    avg_test_net_return=summary.avg_test_net_return,
                    median_test_net_return=summary.median_test_net_return,
                    positive_test_fold_rate=summary.positive_test_fold_rate,
                    avg_test_win_rate=summary.avg_test_win_rate,
                    avg_test_profit_factor=summary.avg_test_profit_factor,
                    avg_test_cumulative_net_return=summary.avg_test_cumulative_net_return,
                    worst_test_cumulative_net_return=summary.worst_test_cumulative_net_return,
                    avg_test_max_drawdown=summary.avg_test_max_drawdown,
                    consistency_score=summary.consistency_score,
                    fallback_dependency_warning=fallback_warning,
                    warning_flags=sorted(set(warning_flags)),
                    metadata_json={
                        "source_summary": summary.to_dict(),
                    },
                )
            )
        return findings

    def estimate_fallback_dependency(
        self,
        rule_summary: RuleWalkForwardSummary,
        dataset_rows: list[ResearchDatasetRow],
    ) -> bool:
        rule = next(
            (item for item in default_rule_library() if item.rule_id == rule_summary.rule_id),
            None,
        )
        if rule is None:
            return False
        backtester = RuleBacktester()
        selected_rows = [row for row in dataset_rows if backtester.row_passes_rule(row, rule)]
        if not selected_rows:
            return False
        fallback_count = sum(
            1 for row in selected_rows if row.entry_price_source == "nearest_research_fallback"
        )
        return fallback_count / len(selected_rows) >= 0.5

    def recommend_next_action(self, review: DiagnosticWalkForwardReview) -> str:
        if review.rules_with_valid_folds == 0:
            return "scale_bounded_backfill_for_more_time_span"

        selected_counts = [
            finding.total_test_selected_count
            for finding in review.findings
            if finding.valid_test_fold_count > 0
        ]
        if selected_counts and max(selected_counts) < 50:
            return "scale_bounded_backfill_for_more_samples"

        if any(finding.fallback_dependency_warning for finding in review.findings):
            return "improve_clean_price_inference"

        positive_findings = [
            finding
            for finding in review.findings
            if (finding.positive_test_fold_rate or 0.0) >= 0.6
            and (finding.avg_test_net_return or 0.0) > 0
        ]
        if positive_findings:
            return "inspect_candidate_rule_manually_before_more_scale"

        return "scale_bounded_backfill_or_refine_rules"

    def build_review(
        self,
        dataset_rows: list[ResearchDatasetRow],
        validation_result: WalkForwardValidationResult,
        dataset_path: str,
        result_path: str | None = None,
    ) -> DiagnosticWalkForwardReview:
        summary = self.summarize_dataset(dataset_rows)
        findings = self.build_findings(validation_result, dataset_rows)
        valid_findings = [finding for finding in findings if finding.valid_test_fold_count > 0]
        best_by_consistency = max(
            valid_findings,
            key=lambda item: item.consistency_score if item.consistency_score is not None else -1,
            default=None,
        )
        best_by_avg_test_net = max(
            valid_findings,
            key=lambda item: item.avg_test_net_return if item.avg_test_net_return is not None else -1,
            default=None,
        )
        review = DiagnosticWalkForwardReview(
            review_id=make_diagnostic_walk_forward_review_id(),
            created_at=utc_now_iso(),
            dataset_path=dataset_path,
            walk_forward_result_path=result_path,
            fold_config_name=validation_result.config.config_id,
            row_count=summary["row_count"],
            token_count=summary["token_count"],
            time_span_seconds=summary["time_span_seconds"],
            nearest_fallback_row_count=summary["nearest_fallback_row_count"],
            rules_tested=validation_result.rules_tested,
            rules_with_valid_folds=len(valid_findings),
            findings=findings,
            best_rule_by_consistency=best_by_consistency.rule_id if best_by_consistency else None,
            best_rule_by_avg_test_net=best_by_avg_test_net.rule_id if best_by_avg_test_net else None,
            warning_flags=sorted(set(DIAGNOSTIC_WARNINGS + validation_result.warning_flags)),
            metadata_json={
                "validation_id": validation_result.validation_id,
                "diagnostic_only": True,
            },
        )
        review.recommended_next_action = self.recommend_next_action(review)
        return review
