"""Offline analyzer for bounded evidence expansion decisions."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.validation.evidence_expansion_decision_models import (
    BoundedExpansionPlan,
    EvidenceExpansionDecisionReport,
    EvidenceExpansionNeed,
    RuleExpansionSignal,
    make_bounded_expansion_plan_id,
    make_evidence_expansion_decision_report_id,
    utc_now_iso,
)
from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


class EvidenceExpansionDecisionAnalyzer:
    def build_rule_signals(
        self,
        robust_rule_report_rows_or_data: dict[str, Any] | None,
        outlier_review_data: dict[str, Any] | None,
        diagnostic_walk_forward_review_data: dict[str, Any] | None,
        selected_row_audit_data: dict[str, Any] | None,
    ) -> list[RuleExpansionSignal]:
        robust_data = robust_rule_report_rows_or_data or {}
        outlier_counts = _outlier_counts_by_rule(outlier_review_data or {})
        wf_by_rule = _walk_forward_findings_by_rule(diagnostic_walk_forward_review_data or {})
        audit_by_rule = {
            item.get("rule_id"): item
            for item in (selected_row_audit_data or {}).get("rule_audits", [])
            if item.get("rule_id")
        }
        signals: list[RuleExpansionSignal] = []
        for item in robust_data.get("rule_summaries", []):
            rule_id = item.get("rule_id", "")
            robust = item.get("robust_returns", {})
            capped = item.get("capped_metrics", {})
            wf = wf_by_rule.get(rule_id, {})
            audit = audit_by_rule.get(rule_id, {})
            counts = outlier_counts.get(rule_id, Counter())
            signal = RuleExpansionSignal(
                rule_id=rule_id,
                rule_name=item.get("rule_name", rule_id),
                selected_count=item.get("selected_count", 0),
                valid_fold_count=wf.get("valid_test_fold_count", 0),
                positive_fold_rate=wf.get("positive_test_fold_rate"),
                median_net_return=(
                    wf.get("median_test_net_return")
                    if wf.get("median_test_net_return") is not None
                    else robust.get("median")
                ),
                capped_mean_return=(
                    capped.get("mean")
                    if capped.get("mean") is not None
                    else item.get("capped_mean_return")
                ),
                raw_mean_return=robust.get("mean") if robust.get("mean") is not None else item.get("raw_mean_return"),
                outlier_return_share=audit.get("outlier_return_share"),
                plausible_outlier_count=counts.get("plausible_price_path", 0),
                suspicious_outlier_count=counts.get("suspicious_price_jump", 0) + counts.get("isolated_price_print", 0),
                fallback_dependent_outlier_count=counts.get("fallback_dependent", 0),
                metadata_json={"source": "robust_rule_report"},
            )
            signal.signal_classification = self.classify_rule_signal(signal)
            signal.warning_flags = _signal_warnings(signal)
            signals.append(signal)
        return signals

    def classify_rule_signal(self, signal: RuleExpansionSignal) -> str:
        if signal.outlier_return_share is not None and signal.outlier_return_share > 0.8:
            return "outlier_dependent"
        if (
            signal.median_net_return is not None
            and signal.median_net_return <= 0
            and signal.positive_fold_rate is not None
            and signal.positive_fold_rate < 0.4
        ):
            return "weak_noisy"
        if (
            signal.capped_mean_return is not None
            and signal.capped_mean_return > 0
            and signal.median_net_return is not None
            and signal.median_net_return <= 0
            and signal.plausible_outlier_count > signal.suspicious_outlier_count
        ):
            return "watch_for_more_data"
        if (
            signal.capped_mean_return is not None
            and signal.capped_mean_return <= 0
            and signal.median_net_return is not None
            and signal.median_net_return < 0
            and signal.positive_fold_rate is not None
            and signal.positive_fold_rate < 0.3
            and signal.valid_fold_count >= 10
        ):
            return "reject_later_if_repeats"
        return "unknown"

    def determine_expansion_needs(
        self,
        real_token_count: int,
        time_span_seconds: int | None,
        price_coverage_rate: float | None,
        no_price_label_count: int,
        rule_signals: list[RuleExpansionSignal],
    ) -> list[EvidenceExpansionNeed]:
        needs: list[EvidenceExpansionNeed] = []
        if real_token_count < 50:
            needs.append(EvidenceExpansionNeed("add_more_tokens", "high", "real token count below expansion target", 50, real_token_count))
        if time_span_seconds is None or time_span_seconds < 86400:
            needs.append(EvidenceExpansionNeed("expand_time_span", "high", "diagnostic time span below 24h target", 86400, time_span_seconds))
        if price_coverage_rate is not None and price_coverage_rate < 0.5:
            needs.append(EvidenceExpansionNeed("improve_price_coverage", "medium", "price coverage below 50%", 0.5, price_coverage_rate, metadata_json={"no_price_label_count": no_price_label_count}))
        if rule_signals and all(signal.signal_classification == "weak_noisy" for signal in rule_signals) and real_token_count < 50:
            needs.append(EvidenceExpansionNeed("increase_per_token_depth", "medium", "all current rule signals weak while sample remains below target", 50, real_token_count))
        if any(signal.signal_classification == "outlier_dependent" for signal in rule_signals):
            needs.append(EvidenceExpansionNeed("inspect_rule_rows", "medium", "at least one rule remains outlier dependent"))
        if not needs:
            needs.append(EvidenceExpansionNeed("hold", "low", "no expansion need triggered"))
        return needs

    def build_bounded_plan(
        self,
        needs: list[EvidenceExpansionNeed],
        current_real_token_count: int,
        current_time_span_seconds: int | None,
    ) -> BoundedExpansionPlan:
        recommended = any(need.need_type != "hold" for need in needs)
        candidate_limit = 15 if current_real_token_count < 20 else 10
        signatures = 150
        transactions = 150
        stop_after_targets = 20
        command = (
            "./trading_env/bin/python -m research.mtp_research.pipeline.run_time_span_backfill_execute "
            f"--candidate-limit {candidate_limit} "
            f"--max-signatures-per-target {signatures} "
            f"--max-transactions-per-target {transactions} "
            f"--stop-after-targets {stop_after_targets} "
            "--min-liquidity-usd 10000 --execute"
        )
        return BoundedExpansionPlan(
            plan_id=make_bounded_expansion_plan_id(),
            created_at=utc_now_iso(),
            recommended=recommended,
            candidate_limit=candidate_limit,
            max_signatures_per_target=signatures,
            max_transactions_per_target=transactions,
            stop_after_targets=stop_after_targets,
            min_liquidity_usd=10000,
            require_pool_address=True,
            estimated_signature_requests=stop_after_targets * signatures,
            estimated_transaction_requests=stop_after_targets * transactions,
            recommended_command=command if recommended else None,
            rationale="bounded read-only evidence expansion proposal; review before running",
            warning_flags=["not_executed", "bounded_only"],
            metadata_json={"current_real_token_count": current_real_token_count, "current_time_span_seconds": current_time_span_seconds},
        )

    def recommend_next_action(self, report: EvidenceExpansionDecisionReport) -> str:
        if report.price_coverage_rate is not None and report.price_coverage_rate < 0.25 and report.no_price_label_count > report.diagnostic_row_count:
            return "improve_price_coverage_before_scaling"
        if any(signal.signal_classification == "outlier_dependent" for signal in report.rule_signals):
            return "run_bounded_expansion_with_outlier_separated_reporting"
        if (report.real_token_count < 50 or (report.time_span_seconds or 0) < 86400):
            return "run_bounded_evidence_expansion"
        if report.rule_signals and all(signal.signal_classification in {"weak_noisy", "reject_later_if_repeats"} for signal in report.rule_signals):
            return "conservative_rule_review_without_threshold_optimization"
        return "manual_review"

    def build_report(
        self,
        rows: list[ResearchDatasetRow],
        diagnostic_dataset_path: str,
        raw_row_count: int = 0,
        robust_rule_report_data: dict[str, Any] | None = None,
        outlier_price_path_data: dict[str, Any] | None = None,
        selected_row_audit_data: dict[str, Any] | None = None,
        fold_sufficiency_data: dict[str, Any] | None = None,
        diagnostic_walk_forward_review_data: dict[str, Any] | None = None,
        price_coverage_data: dict[str, Any] | None = None,
        dataset_sufficiency_data: dict[str, Any] | None = None,
    ) -> EvidenceExpansionDecisionReport:
        rule_signals = self.build_rule_signals(
            robust_rule_report_data,
            outlier_price_path_data,
            diagnostic_walk_forward_review_data,
            selected_row_audit_data,
        )
        token_count = len({row.token_mint for row in rows})
        time_span = _time_span(rows)
        price_coverage_rate = _price_coverage_rate(price_coverage_data or {})
        no_price_label_count = _no_price_label_count(price_coverage_data or {})
        needs = self.determine_expansion_needs(token_count, time_span, price_coverage_rate, no_price_label_count, rule_signals)
        plan = self.build_bounded_plan(needs, token_count, time_span)
        report = EvidenceExpansionDecisionReport(
            report_id=make_evidence_expansion_decision_report_id(),
            created_at=utc_now_iso(),
            diagnostic_dataset_path=diagnostic_dataset_path,
            raw_row_count=raw_row_count,
            diagnostic_row_count=len(rows),
            real_token_count=token_count,
            time_span_seconds=time_span,
            price_coverage_rate=price_coverage_rate,
            no_price_label_count=no_price_label_count,
            rule_signals=rule_signals,
            expansion_needs=needs,
            bounded_plan=plan,
            warning_flags=["decision_report_not_trading_signal", "does_not_execute_bounded_command"],
            metadata_json={
                "fold_sufficiency_report_id": (fold_sufficiency_data or {}).get("report_id"),
                "dataset_sufficiency_report_id": (dataset_sufficiency_data or {}).get("report_id"),
            },
        )
        report.recommended_next_action = self.recommend_next_action(report)
        return report


def load_json_report(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def latest_report(output_dirs: list[str | Path], patterns: list[str]) -> Path | None:
    matches: list[Path] = []
    for output_dir in output_dirs:
        base = Path(output_dir)
        for pattern in patterns:
            matches.extend(base.glob(pattern))
    matches = [path for path in matches if path.is_file()]
    return sorted(matches, key=lambda path: path.stat().st_mtime)[-1] if matches else None


def _outlier_counts_by_rule(data: dict[str, Any]) -> dict[str, Counter]:
    output: dict[str, Counter] = {}
    for review in data.get("reviews", []):
        rule_id = review.get("rule_id")
        classification = review.get("outlier_classification")
        if rule_id and classification:
            output.setdefault(rule_id, Counter())[classification] += 1
    return output


def _walk_forward_findings_by_rule(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = data.get("rule_findings") or data.get("findings") or []
    return {
        item.get("rule_id"): item
        for item in findings
        if item.get("rule_id")
    }


def _signal_warnings(signal: RuleExpansionSignal) -> list[str]:
    warnings: list[str] = []
    if signal.signal_classification == "outlier_dependent":
        warnings.append("outlier_dependent_not_validated")
    if signal.signal_classification == "weak_noisy":
        warnings.append("weak_noisy_continue_evidence_collection_only")
    if signal.raw_mean_return is not None and signal.capped_mean_return is not None and signal.raw_mean_return - signal.capped_mean_return > 0.5:
        warnings.append("raw_mean_outlier_sensitive")
    return warnings


def _time_span(rows: list[ResearchDatasetRow]) -> int | None:
    if not rows:
        return None
    timestamps = [row.snapshot_ts for row in rows]
    return max(timestamps) - min(timestamps)


def _price_coverage_rate(data: dict[str, Any]) -> float | None:
    if data.get("price_coverage_rate") is not None:
        return data.get("price_coverage_rate")
    event_count = data.get("event_count")
    priced = data.get("events_with_price_quote")
    if event_count:
        return priced / event_count if priced is not None else None
    return None


def _no_price_label_count(data: dict[str, Any]) -> int:
    return int(data.get("no_price_label_count") or 0)
