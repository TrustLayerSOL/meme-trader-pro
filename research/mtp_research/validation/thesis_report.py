"""Report writers for thesis evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.validation.thesis_models import (
    ThesisDecision,
    ThesisEvaluationSummary,
)


def write_thesis_evaluation_markdown(
    summaries: list[ThesisEvaluationSummary],
    decisions: list[ThesisDecision],
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    decisions_by_thesis = {decision.thesis_id: decision for decision in decisions}
    lines = [
        "# Thesis Evaluation Report v0",
        "",
        "> Warning: thesis decisions are research workflow decisions, not trading instructions.",
        "> No thesis is approved for live trading by this report.",
        "",
        "## Thesis Summary",
        "",
        "| Thesis | Name | Status | Recommended | Linked Rules | Validations | Best Avg Test Net | Positive Fold Rate | Test Selected | Warnings |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for summary in summaries:
        lines.append(
            f"| `{summary.thesis_id}` | {summary.name} | {summary.status} | "
            f"{summary.recommended_status} | {summary.linked_rule_count} | "
            f"{summary.linked_validation_count} | {format_percent(summary.best_avg_test_net_return)} | "
            f"{format_percent(summary.best_positive_test_fold_rate)} | "
            f"{summary.total_test_selected_count} | {', '.join(summary.warning_flags)} |"
        )
    lines.extend(["", "## Decision Details", ""])
    for summary in summaries:
        decision = decisions_by_thesis.get(summary.thesis_id)
        if decision is None:
            continue
        lines.extend(
            [
                f"### {summary.thesis_id} - {summary.name}",
                "",
                f"- Prior status: `{decision.prior_status}`",
                f"- Recommended status: `{decision.recommended_status}`",
                f"- Confidence: `{format_number(decision.confidence)}`",
                f"- Reason: {decision.reason}",
                f"- Supporting rules: `{decision.supporting_rule_ids}`",
                f"- Supporting validations: `{decision.supporting_validation_ids}`",
                f"- Warnings: `{decision.warning_flags}`",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_thesis_evaluation_json(
    summaries: list[ThesisEvaluationSummary],
    decisions: list[ThesisDecision],
    output_path: Path | str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "summaries": [summary.to_dict() for summary in summaries],
        "decisions": [decision.to_dict() for decision in decisions],
        "warning": "No thesis is approved for live trading by this report.",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"
