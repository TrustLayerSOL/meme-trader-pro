"""Evaluate thesis status from local walk-forward validation summaries."""

from __future__ import annotations

from collections import defaultdict

from research.mtp_research.validation.thesis_models import (
    ThesisDecision,
    ThesisEvaluationSummary,
    ThesisReference,
    SampleAdequacyReport,
    make_thesis_decision_id,
    utc_now_iso,
)
from research.mtp_research.validation.walk_forward_models import (
    RuleWalkForwardSummary,
    WalkForwardValidationResult,
)


class ThesisEvaluator:
    """Conservative thesis workflow evaluator."""

    def __init__(
        self,
        min_total_test_selected_count: int = 50,
        min_positive_test_fold_rate: float = 0.6,
        min_avg_test_net_return: float = 0.0,
        min_consistency_score: float = 0.0,
        sample_adequacy_report: SampleAdequacyReport | None = None,
    ):
        self.min_total_test_selected_count = min_total_test_selected_count
        self.min_positive_test_fold_rate = min_positive_test_fold_rate
        self.min_avg_test_net_return = min_avg_test_net_return
        self.min_consistency_score = min_consistency_score
        self.sample_adequacy_report = sample_adequacy_report

    def map_rules_to_theses(
        self,
        theses: list[ThesisReference],
        rule_summaries: list[RuleWalkForwardSummary],
    ) -> dict[str, list[RuleWalkForwardSummary]]:
        output: dict[str, list[RuleWalkForwardSummary]] = {thesis.thesis_id: [] for thesis in theses}
        by_id = {thesis.thesis_id: thesis for thesis in theses}
        for summary in rule_summaries:
            explicit = summary.metadata_json.get("thesis_id")
            if explicit and explicit in by_id:
                output[explicit].append(summary)
                continue
            for thesis in theses:
                if summary.rule_id in thesis.linked_rule_ids:
                    output[thesis.thesis_id].append(summary)
        return output

    def evaluate_thesis(
        self,
        thesis: ThesisReference,
        linked_summaries: list[RuleWalkForwardSummary],
        validation_result: WalkForwardValidationResult | None = None,
    ) -> ThesisEvaluationSummary:
        warning_flags = [
            "research_decision_not_trading_instruction",
            "live_trading_disabled",
            "requires_human_review",
        ]
        if validation_result is not None:
            warning_flags.append("heuristic_trade_labels_v0")
        if thesis.status == "planned" and thesis.known_gaps:
            warning_flags.append("planned_thesis_missing_data")

        if not linked_summaries:
            warning_flags.append("no_linked_validation_results")
            return ThesisEvaluationSummary(
                thesis_id=thesis.thesis_id,
                name=thesis.name,
                status=thesis.status,
                recommended_status="needs_more_data",
                warning_flags=warning_flags,
                metadata_json={"known_gaps": thesis.known_gaps},
            )

        best_by_consistency = max(
            linked_summaries,
            key=lambda item: item.consistency_score if item.consistency_score is not None else -1.0,
        )
        best_by_return = max(
            linked_summaries,
            key=lambda item: item.avg_test_net_return if item.avg_test_net_return is not None else -1.0,
        )
        best_by_fold_rate = max(
            linked_summaries,
            key=lambda item: item.positive_test_fold_rate if item.positive_test_fold_rate is not None else -1.0,
        )
        total_selected = sum(summary.total_test_selected_count for summary in linked_summaries)
        linked_validation_count = 1 if validation_result is not None else 0
        best_avg = best_by_return.avg_test_net_return
        best_rate = best_by_fold_rate.positive_test_fold_rate
        best_consistency = best_by_consistency.consistency_score

        recommended_status = "needs_more_data"
        if total_selected < self.min_total_test_selected_count:
            warning_flags.append("insufficient_test_sample")
        elif best_avg is not None and best_rate is not None and (best_avg <= 0 or best_rate < 0.5):
            recommended_status = "rejected_or_rework"
        elif (
            best_avg is not None
            and best_rate is not None
            and best_avg > self.min_avg_test_net_return
            and best_rate >= self.min_positive_test_fold_rate
        ):
            recommended_status = "watchlist"

        major_flags = {"insufficient_test_sample", "planned_thesis_missing_data", "no_linked_validation_results"}
        if (
            recommended_status == "watchlist"
            and thesis.status in {"active", "watchlist"}
            and best_consistency is not None
            and best_consistency > self.min_consistency_score
            and not major_flags.intersection(warning_flags)
        ):
            recommended_status = "paper_candidate"

        diagnostic_raw_recommendation = recommended_status
        if self.sample_adequacy_report and recommended_status in {
            "rejected_or_rework",
            "watchlist",
            "paper_candidate",
        }:
            if not (
                self.sample_adequacy_report.adequate_for_rejection
                and self.sample_adequacy_report.adequate_for_promotion
            ):
                recommended_status = "needs_more_data"
                warning_flags.extend(
                    [
                        "insufficient_sample_for_demotion_or_promotion",
                        "diagnostic_sample_only",
                    ]
                )
                warning_flags.extend(self.sample_adequacy_report.warning_flags)

        return ThesisEvaluationSummary(
            thesis_id=thesis.thesis_id,
            name=thesis.name,
            status=thesis.status,
            linked_rule_count=len({summary.rule_id for summary in linked_summaries}),
            linked_validation_count=linked_validation_count,
            best_consistency_score=best_consistency,
            best_avg_test_net_return=best_avg,
            best_positive_test_fold_rate=best_rate,
            total_test_selected_count=total_selected,
            recommended_status=recommended_status,
            warning_flags=sorted(set(warning_flags)),
            metadata_json={
                "linked_rule_ids": [summary.rule_id for summary in linked_summaries],
                "supporting_validation_id": validation_result.validation_id if validation_result else None,
                "diagnostic_raw_recommendation": diagnostic_raw_recommendation,
                "sample_adequacy_report": (
                    self.sample_adequacy_report.to_dict()
                    if self.sample_adequacy_report
                    else None
                ),
            },
        )

    def evaluate_all(
        self,
        theses: list[ThesisReference],
        validation_results: list[WalkForwardValidationResult],
    ) -> list[ThesisEvaluationSummary]:
        summaries_by_thesis: dict[str, list[RuleWalkForwardSummary]] = defaultdict(list)
        validation_ids_by_thesis: dict[str, list[str]] = defaultdict(list)
        for validation_result in validation_results:
            mapped = self.map_rules_to_theses(theses, validation_result.rule_summaries)
            for thesis_id, summaries in mapped.items():
                if summaries:
                    summaries_by_thesis[thesis_id].extend(summaries)
                    validation_ids_by_thesis[thesis_id].append(validation_result.validation_id)
        output = []
        for thesis in theses:
            validation_result = None
            if validation_ids_by_thesis[thesis.thesis_id]:
                validation_result = next(
                    result for result in validation_results
                    if result.validation_id == validation_ids_by_thesis[thesis.thesis_id][-1]
                )
            summary = self.evaluate_thesis(
                thesis,
                summaries_by_thesis[thesis.thesis_id],
                validation_result=validation_result,
            )
            summary.linked_validation_count = len(set(validation_ids_by_thesis[thesis.thesis_id]))
            output.append(summary)
        return output

    def summary_to_decision(
        self,
        thesis: ThesisReference,
        summary: ThesisEvaluationSummary,
    ) -> ThesisDecision:
        reason = (
            f"Recommended {summary.recommended_status} from "
            f"{summary.linked_rule_count} linked rules, "
            f"{summary.linked_validation_count} validation results, "
            f"and {summary.total_test_selected_count} selected test rows."
        )
        return ThesisDecision(
            decision_id=make_thesis_decision_id(thesis.thesis_id),
            thesis_id=thesis.thesis_id,
            created_at=utc_now_iso(),
            prior_status=thesis.status,
            recommended_status=summary.recommended_status,
            confidence=_confidence_for_status(summary),
            reason=reason,
            supporting_rule_ids=list(summary.metadata_json.get("linked_rule_ids", [])),
            supporting_validation_ids=[
                value for value in [summary.metadata_json.get("supporting_validation_id")]
                if value
            ],
            warning_flags=list(summary.warning_flags),
            metadata_json={"summary": summary.to_dict()},
        )


def _confidence_for_status(summary: ThesisEvaluationSummary) -> float:
    if summary.recommended_status == "paper_candidate":
        return 0.65
    if summary.recommended_status == "watchlist":
        return 0.55
    if summary.recommended_status == "rejected_or_rework":
        return 0.50
    return 0.35
