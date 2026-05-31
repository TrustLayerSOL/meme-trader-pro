"""Report writers for evidence expansion decisions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.evidence_expansion_decision_models import (
    EvidenceExpansionDecisionReport,
)


WARNING_TEXT = "This is an evidence expansion decision report. It is not a trading signal."


def report_to_dict(report: EvidenceExpansionDecisionReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: EvidenceExpansionDecisionReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: EvidenceExpansionDecisionReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    plan = report.bounded_plan
    lines = [
        "# Evidence Expansion Decision Report",
        "",
        f"> Warning: {WARNING_TEXT}",
        "",
        "## Current Evidence",
        "",
        f"- Raw rows: `{report.raw_row_count}`",
        f"- Diagnostic dataset rows: `{report.diagnostic_row_count}`",
        f"- Real token count: `{report.real_token_count}`",
        f"- Time span seconds: `{report.time_span_seconds}`",
        f"- Price coverage rate: `{_fmt(report.price_coverage_rate)}`",
        f"- No-price labels: `{report.no_price_label_count}`",
        "",
        "## Rule Signals",
        "",
        "| Rule | Classification | Median Net | Capped Mean | Raw Mean | Positive Fold Rate | Outlier Share | Plausible | Suspicious | Warnings |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for signal in report.rule_signals:
        lines.append(
            "| "
            f"`{signal.rule_id}` | `{signal.signal_classification}` | "
            f"{_fmt(signal.median_net_return)} | {_fmt(signal.capped_mean_return)} | "
            f"{_fmt(signal.raw_mean_return)} | {_fmt(signal.positive_fold_rate)} | "
            f"{_fmt(signal.outlier_return_share)} | {signal.plausible_outlier_count} | "
            f"{signal.suspicious_outlier_count} | `{signal.warning_flags}` |"
        )
    lines.extend(["", "## Expansion Needs", ""])
    lines.extend(
        [
            "| Need | Priority | Current | Target | Reason |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for need in report.expansion_needs:
        lines.append(
            f"| `{need.need_type}` | `{need.priority}` | {need.current_value or ''} | {need.target_value or ''} | {need.reason} |"
        )
    lines.extend(["", "## Bounded Plan", ""])
    if plan is None:
        lines.append("- No bounded plan generated.")
    else:
        lines.extend(
            [
                f"- Recommended: `{plan.recommended}`",
                f"- Candidate limit: `{plan.candidate_limit}`",
                f"- Max signatures per target: `{plan.max_signatures_per_target}`",
                f"- Max transactions per target: `{plan.max_transactions_per_target}`",
                f"- Stop after targets: `{plan.stop_after_targets}`",
                f"- Estimated signature requests: `{plan.estimated_signature_requests}`",
                f"- Estimated transaction requests: `{plan.estimated_transaction_requests}`",
                f"- Recommended command: `{plan.recommended_command}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Final Recommendation",
            "",
            f"- Recommended next action: `{report.recommended_next_action}`",
            "",
            "## Safety Notes",
            "",
            "- No thesis promotion.",
            "- No live trading.",
            "- No unbounded Helius.",
            "- Recommended command is not executed by this report.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
