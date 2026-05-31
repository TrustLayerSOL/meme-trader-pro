"""Diagnostic selected-row audit for exploratory validation rules."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median

from research.mtp_research.backtest.rule_backtest_models import CostAssumptions, RuleDefinition
from research.mtp_research.backtest.rule_backtester import RuleBacktester
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.selected_row_audit_models import (
    RuleSelectedRowAudit,
    SelectedRowAuditRecord,
    SelectedRowAuditReport,
    make_selected_row_audit_report_id,
    utc_now_iso,
)


class SelectedRowAuditor:
    """Audit rows selected by existing rule definitions without changing the rules."""

    def audit_rules(
        self,
        rows: list[ResearchDatasetRow],
        rules: list[RuleDefinition],
        rule_ids: list[str],
        cost_drag: float | None = None,
        stale_entry_threshold_sec: int = 300,
        outlier_return_threshold: float = 1.0,
        top_outlier_n: int = 10,
        dataset_path: str = "",
    ) -> SelectedRowAuditReport:
        rules_by_id = {rule.rule_id: rule for rule in rules}
        audits: list[RuleSelectedRowAudit] = []
        missing_rule_ids: list[str] = []
        for rule_id in rule_ids:
            rule = rules_by_id.get(rule_id)
            if rule is None:
                missing_rule_ids.append(rule_id)
                continue
            audits.append(
                self.audit_rule(
                    rows,
                    rule,
                    cost_drag=cost_drag,
                    stale_entry_threshold_sec=stale_entry_threshold_sec,
                    outlier_return_threshold=outlier_return_threshold,
                    top_outlier_n=top_outlier_n,
                )
            )

        report = SelectedRowAuditReport(
            report_id=make_selected_row_audit_report_id(),
            created_at=utc_now_iso(),
            dataset_path=dataset_path,
            audited_rule_ids=list(rule_ids),
            row_count=len(rows),
            rule_audits=audits,
            warning_flags=["diagnostic_only_not_trading_signal"],
            metadata_json={"missing_rule_ids": missing_rule_ids},
        )
        report.cross_rule_findings = self._cross_rule_findings(audits)
        report.recommended_next_action = self.recommend_next_action(report)
        return report

    def audit_rule(
        self,
        rows: list[ResearchDatasetRow],
        rule: RuleDefinition,
        cost_drag: float | None = None,
        stale_entry_threshold_sec: int = 300,
        outlier_return_threshold: float = 1.0,
        top_outlier_n: int = 10,
    ) -> RuleSelectedRowAudit:
        backtester = RuleBacktester()
        selected_rows = [
            row
            for row in rows
            if backtester.row_passes_rule(row, rule)
        ]
        records = [
            self.row_to_audit_record(
                row,
                rule.rule_id,
                cost_drag=cost_drag,
                stale_entry_threshold_sec=stale_entry_threshold_sec,
                outlier_return_threshold=outlier_return_threshold,
            )
            for row in sorted(selected_rows, key=lambda item: (item.snapshot_ts, item.row_id))
        ]

        forward_returns = [record.forward_return for record in records if record.forward_return is not None]
        net_returns = [
            record.net_return_estimate for record in records if record.net_return_estimate is not None
        ]
        positive_returns = [value for value in forward_returns if value > 0]
        token_counts = dict(sorted(Counter(record.token_mint for record in records).items()))
        fallback_count = sum(
            1 for record in records if record.entry_price_source == "nearest_research_fallback"
        )
        stale_count = sum(
            1 for record in records if "stale_entry_price" in record.warning_flags
        )
        top_positive = sorted(positive_returns, reverse=True)[:top_outlier_n]
        positive_sum = sum(positive_returns)
        outlier_share = (sum(top_positive) / positive_sum) if positive_sum > 0 else None

        audit = RuleSelectedRowAudit(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            selected_count=len(records),
            token_count=len(token_counts),
            positive_count=sum(1 for value in net_returns if value > 0),
            negative_count=sum(1 for value in net_returns if value <= 0),
            win_rate=(
                sum(1 for value in net_returns if value > 0) / len(net_returns)
                if net_returns else None
            ),
            avg_forward_return=mean(forward_returns) if forward_returns else None,
            median_forward_return=median(forward_returns) if forward_returns else None,
            avg_net_return_estimate=mean(net_returns) if net_returns else None,
            median_net_return_estimate=median(net_returns) if net_returns else None,
            top_outlier_count=sum(
                1
                for record in records
                if record.forward_return is not None
                and record.forward_return >= outlier_return_threshold
            ),
            outlier_return_share=outlier_share,
            fallback_entry_count=fallback_count,
            fallback_entry_rate=(fallback_count / len(records)) if records else None,
            stale_entry_count=stale_count,
            stale_entry_rate=(stale_count / len(records)) if records else None,
            token_concentration=token_counts,
            records=records,
            metadata_json={
                "outlier_return_threshold": outlier_return_threshold,
                "top_outlier_n": top_outlier_n,
                "stale_entry_threshold_sec": stale_entry_threshold_sec,
            },
        )
        audit.warning_flags = self.infer_rule_warnings(audit)
        return audit

    def row_to_audit_record(
        self,
        row: ResearchDatasetRow,
        rule_id: str,
        cost_drag: float | None = None,
        stale_entry_threshold_sec: int = 300,
        outlier_return_threshold: float = 1.0,
    ) -> SelectedRowAuditRecord:
        effective_cost_drag = (
            CostAssumptions().total_cost_return_drag()
            if cost_drag is None
            else cost_drag
        )
        staleness = None
        if row.entry_price_ts is not None:
            staleness = abs(row.snapshot_ts - row.entry_price_ts)
        net_return = None
        if row.forward_return is not None:
            net_return = row.forward_return - effective_cost_drag
        record = SelectedRowAuditRecord(
            row_id=row.row_id,
            rule_id=rule_id,
            token_mint=row.token_mint,
            snapshot_ts=row.snapshot_ts,
            window_name=row.window_name,
            horizon_name=row.horizon_name,
            entry_price=row.entry_price,
            entry_price_ts=row.entry_price_ts,
            entry_price_source=row.entry_price_source,
            entry_price_staleness_sec=staleness,
            end_price=row.end_price,
            end_price_ts=row.end_price_ts,
            forward_return=row.forward_return,
            net_return_estimate=net_return,
            max_runup=row.max_runup,
            max_drawdown=row.max_drawdown,
            label_quality=row.label_quality,
            no_future_liquidity=row.no_future_liquidity,
            rug_like_drop=row.rug_like_drop,
            buy_sell_imbalance=row.buy_sell_imbalance,
            possible_buy_count=row.possible_buy_count,
            possible_sell_count=row.possible_sell_count,
            unique_actor_count=row.unique_actor_count,
            confidence_weighted_net_flow=row.confidence_weighted_net_flow,
            avg_event_confidence=row.avg_event_confidence,
            max_event_confidence=row.max_event_confidence,
            metadata_json={
                "snapshot_id": row.snapshot_id,
                "outcome_id": row.outcome_id,
                "cost_drag": effective_cost_drag,
                "outlier_return_threshold": outlier_return_threshold,
                "stale_entry_threshold_sec": stale_entry_threshold_sec,
            },
        )
        record.warning_flags = self.infer_record_warnings(
            record,
            stale_entry_threshold_sec=stale_entry_threshold_sec,
            outlier_return_threshold=outlier_return_threshold,
        )
        return record

    def infer_record_warnings(
        self,
        record: SelectedRowAuditRecord,
        stale_entry_threshold_sec: int = 300,
        outlier_return_threshold: float = 1.0,
    ) -> list[str]:
        warnings: list[str] = []
        if record.forward_return is None:
            warnings.append("missing_forward_return")
        if record.entry_price_source == "nearest_research_fallback":
            warnings.append("nearest_research_fallback_entry")
        if (
            record.entry_price_staleness_sec is not None
            and record.entry_price_staleness_sec > stale_entry_threshold_sec
        ):
            warnings.append("stale_entry_price")
        if record.forward_return is not None and record.forward_return >= outlier_return_threshold:
            warnings.append("extreme_forward_return")
        if record.max_runup is not None and record.max_runup >= outlier_return_threshold:
            warnings.append("extreme_max_runup")
        if record.max_drawdown is not None and record.max_drawdown <= -0.8:
            warnings.append("severe_drawdown")
        if record.no_future_liquidity:
            warnings.append("no_future_liquidity")
        if record.rug_like_drop is True:
            warnings.append("rug_like_drop")
        if record.label_quality not in {"good", "sparse"}:
            warnings.append("low_label_quality")
        if record.avg_event_confidence is not None and record.avg_event_confidence < 0.5:
            warnings.append("low_event_confidence")
        return warnings

    def infer_rule_warnings(self, audit: RuleSelectedRowAudit) -> list[str]:
        warnings: list[str] = []
        if audit.outlier_return_share is not None and audit.outlier_return_share >= 0.5:
            warnings.append("outlier_dominated_average")
        if audit.median_net_return_estimate is not None and audit.median_net_return_estimate < 0:
            warnings.append("low_median_negative")
        if audit.win_rate is not None and audit.win_rate < 0.5:
            warnings.append("low_win_rate")
        if audit.fallback_entry_rate is not None and audit.fallback_entry_rate > 0.5:
            warnings.append("fallback_dependency")
        if audit.selected_count:
            largest_token_count = max(audit.token_concentration.values(), default=0)
            if largest_token_count / audit.selected_count > 0.5:
                warnings.append("token_concentration")
        if audit.stale_entry_rate is not None and audit.stale_entry_rate > 0.25:
            warnings.append("stale_entry_problem")
        return warnings

    def recommend_next_action(self, report: SelectedRowAuditReport) -> str:
        warnings = {flag for audit in report.rule_audits for flag in audit.warning_flags}
        if "outlier_dominated_average" in warnings:
            return "inspect_price_outliers_before_scaling"
        if "fallback_dependency" in warnings:
            return "improve_clean_price_inference"
        if "token_concentration" in warnings:
            return "add_candidate_diversity"
        if {"low_win_rate", "low_median_negative"}.issubset(warnings):
            return "bounded_evidence_expansion_before_rule_changes"
        if "stale_entry_problem" in warnings:
            return "tighten_entry_price_staleness_or_improve_price_series"
        return "manual_review_selected_rows"

    def _cross_rule_findings(self, audits: list[RuleSelectedRowAudit]) -> list[str]:
        findings: list[str] = []
        if audits and all("low_win_rate" in audit.warning_flags for audit in audits):
            findings.append("all_audited_rules_have_low_win_rate")
        if audits and all("low_median_negative" in audit.warning_flags for audit in audits):
            findings.append("all_audited_rules_have_negative_median_net")
        if any("outlier_dominated_average" in audit.warning_flags for audit in audits):
            findings.append("positive_average_may_be_outlier_driven")
        return findings
