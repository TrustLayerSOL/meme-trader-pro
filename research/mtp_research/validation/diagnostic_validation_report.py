"""Report writers for diagnostic validation review."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.diagnostic_validation_models import (
    DIAGNOSTIC_FALLBACK_WARNING,
    DiagnosticValidationReview,
)


def review_to_dict(review: DiagnosticValidationReview) -> dict[str, Any]:
    return asdict(review)


def write_review_json(review: DiagnosticValidationReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = review_to_dict(review)
    payload["diagnostic_warning"] = DIAGNOSTIC_FALLBACK_WARNING
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_review_markdown(review: DiagnosticValidationReview, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Diagnostic Validation Review v0",
        "",
        f"> Warning: {DIAGNOSTIC_FALLBACK_WARNING}",
        "> Diagnostic nearest-entry fallback is research-only. Do not use for live trading or thesis promotion without human review.",
        "",
        f"- Review ID: `{review.review_id}`",
        f"- Created at: `{review.created_at}`",
        f"- Recommended next action: `{review.recommended_next_action}`",
        "",
        "## Clean vs Diagnostic Dataset",
        "",
        "| Dataset | Path | Rows | Tokens | Forward Return Rows | Nearest Fallback Rows | Sparse+ Rows | Good Rows | Entry Sources |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for summary in [review.clean_dataset, review.diagnostic_dataset]:
        lines.append(
            f"| {summary.name} | `{summary.dataset_path}` | {summary.row_count} | "
            f"{summary.token_count} | {summary.rows_with_forward_return} | "
            f"{summary.rows_with_nearest_fallback_entry} | {summary.sparse_or_better_rows} | "
            f"{summary.good_rows} | `{summary.entry_price_source_counts}` |"
        )

    lines.extend(
        [
            "",
            "## Rule Comparison",
            "",
            "| Rule | Clean Selected | Diagnostic Selected | Gain | Diagnostic Nearest Fallback Selected | Clean Avg Net | Diagnostic Avg Net | Clean Win Rate | Diagnostic Win Rate | Warnings |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in review.rule_comparisons:
        lines.append(
            f"| `{item.rule_id}` | {item.clean_selected_count} | {item.diagnostic_selected_count} | "
            f"{item.selected_count_gain} | {item.diagnostic_nearest_fallback_selected_count} | "
            f"{format_percent(item.clean_avg_net_return)} | {format_percent(item.diagnostic_avg_net_return)} | "
            f"{format_percent(item.clean_win_rate)} | {format_percent(item.diagnostic_win_rate)} | "
            f"{', '.join(item.warning_flags)} |"
        )

    lines.extend(
        [
            "",
            "## Walk-Forward Comparison",
            "",
            "| Rule | Clean Valid Folds | Diagnostic Valid Folds | Clean Test Selected | Diagnostic Test Selected | Clean Avg Test Net | Diagnostic Avg Test Net | Clean Positive Fold Rate | Diagnostic Positive Fold Rate | Warnings |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in review.walk_forward_comparisons:
        lines.append(
            f"| `{item.rule_id}` | {item.clean_valid_test_fold_count} | "
            f"{item.diagnostic_valid_test_fold_count} | {item.clean_total_test_selected_count} | "
            f"{item.diagnostic_total_test_selected_count} | "
            f"{format_percent(item.clean_avg_test_net_return)} | "
            f"{format_percent(item.diagnostic_avg_test_net_return)} | "
            f"{format_percent(item.clean_positive_test_fold_rate)} | "
            f"{format_percent(item.diagnostic_positive_test_fold_rate)} | "
            f"{', '.join(item.warning_flags)} |"
        )

    lines.extend(
        [
            "",
            "## Thesis Comparison",
            "",
            "| Thesis | Clean Status | Diagnostic Status | Changed | Warnings |",
            "|---|---|---|---|---|",
        ]
    )
    for item in review.thesis_comparisons:
        lines.append(
            f"| `{item.thesis_id}` | {item.clean_recommended_status} | "
            f"{item.diagnostic_recommended_status} | {item.changed} | "
            f"{', '.join(item.warning_flags)} |"
        )

    lines.extend(
        [
            "",
            "## Warning Flags",
            "",
            *[f"- `{flag}`" for flag in review.warning_flags],
            "",
            "## Paths Used",
            "",
            f"- Clean dataset: `{review.clean_dataset.dataset_path}`",
            f"- Diagnostic dataset: `{review.diagnostic_dataset.dataset_path}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"
