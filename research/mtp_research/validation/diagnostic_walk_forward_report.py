"""Report writers for diagnostic walk-forward reviews."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.diagnostic_walk_forward_models import (
    DiagnosticWalkForwardReview,
)


WARNING_TEXT = (
    "This is a diagnostic walk-forward review using nearest-entry fallback labels. "
    "It is not valid for live trading or thesis promotion without human review."
)


def review_to_dict(review: DiagnosticWalkForwardReview) -> dict[str, Any]:
    return asdict(review)


def write_review_json(review: DiagnosticWalkForwardReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review_to_dict(review), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_review_markdown(review: DiagnosticWalkForwardReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Diagnostic Walk-Forward Review",
        "",
        f"> Warning: {WARNING_TEXT}",
        "",
        "## Dataset Summary",
        "",
        f"- Review ID: `{review.review_id}`",
        f"- Dataset path: `{review.dataset_path}`",
        f"- Walk-forward result path: `{review.walk_forward_result_path}`",
        f"- Row count: `{review.row_count}`",
        f"- Token count: `{review.token_count}`",
        f"- Time span seconds: `{review.time_span_seconds}`",
        f"- Nearest fallback row count: `{review.nearest_fallback_row_count}`",
        "",
        "## Fold Config Summary",
        "",
        f"- Fold config: `{review.fold_config_name}`",
        f"- Rules tested: `{review.rules_tested}`",
        f"- Rules with valid folds: `{review.rules_with_valid_folds}`",
        "",
        "## Rule Findings",
        "",
        "| Rule | Valid Folds | Test Selected | Avg Net | Median Net | Positive Fold Rate | Win Rate | Profit Factor | Consistency | Fallback Warning | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for finding in review.findings:
        lines.append(
            "| "
            f"`{finding.rule_id}` | "
            f"{finding.valid_test_fold_count} | "
            f"{finding.total_test_selected_count} | "
            f"{_fmt(finding.avg_test_net_return)} | "
            f"{_fmt(finding.median_test_net_return)} | "
            f"{_fmt(finding.positive_test_fold_rate)} | "
            f"{_fmt(finding.avg_test_win_rate)} | "
            f"{_fmt(finding.avg_test_profit_factor)} | "
            f"{_fmt(finding.consistency_score)} | "
            f"{finding.fallback_dependency_warning} | "
            f"`{finding.warning_flags}` |"
        )
    lines.extend(
        [
            "",
            "## Review Decision",
            "",
            f"- Best rule by consistency: `{review.best_rule_by_consistency}`",
            f"- Best rule by avg test net: `{review.best_rule_by_avg_test_net}`",
            f"- Recommended next action: `{review.recommended_next_action}`",
            f"- Warning flags: `{review.warning_flags}`",
            "",
            "## Metadata",
            "",
            f"- Created at: `{review.created_at}`",
            f"- Metadata: `{review.metadata_json}`",
            f"- JSON path: `{path.with_suffix('.json')}`",
            f"- Markdown path: `{path}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
