"""Report writers for fold sufficiency diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.fold_sufficiency_analyzer import (
    _total_test_selected_count,
    _total_valid_rule_folds,
)
from research.mtp_research.validation.fold_sufficiency_models import (
    FOLD_SUFFICIENCY_WARNING,
    FoldSufficiencyReport,
)


def report_to_dict(report: FoldSufficiencyReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["diagnostic_warning"] = FOLD_SUFFICIENCY_WARNING
    return payload


def write_report_json(report: FoldSufficiencyReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_report_markdown(report: FoldSufficiencyReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fold Sufficiency Diagnostics v0",
        "",
        f"> Warning: {FOLD_SUFFICIENCY_WARNING}",
        "",
        f"- Report ID: `{report.report_id}`",
        f"- Created at: `{report.created_at}`",
        f"- Dataset path: `{report.dataset_path}`",
        f"- Best config: `{report.best_config_name}`",
        f"- Recommended next action: `{report.recommended_next_action}`",
        "",
        "## Dataset Summary",
        "",
        "| Rows | Tokens | Time Min | Time Max | Time Span |",
        "|---:|---:|---:|---:|---:|",
        f"| {report.row_count} | {report.token_count} | {format_number(report.time_min)} | "
        f"{format_number(report.time_max)} | {format_seconds(report.time_span_seconds)} |",
        "",
        "## Config Comparison",
        "",
        "| Config | Train | Test | Step | Folds | Valid Folds | Total Valid Rule Folds | Total Selected Test Trades | Warnings |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in report.config_results:
        lines.append(
            f"| `{result.config_name}` | {format_seconds(result.train_window_seconds)} | "
            f"{format_seconds(result.test_window_seconds)} | {format_seconds(result.step_seconds)} | "
            f"{result.fold_count} | {result.valid_fold_count} | "
            f"{_total_valid_rule_folds(result)} | {_total_test_selected_count(result)} | "
            f"{', '.join(result.warning_flags)} |"
        )

    for result in report.config_results:
        lines.extend(
            [
                "",
                f"## Config: `{result.config_name}`",
                "",
                "| Rule | Rows Selected | Valid Test Folds | Total Test Selected | Avg Test Selected | Max Test Selected | Warnings |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for rule in result.rule_sufficiency:
            lines.append(
                f"| `{rule.rule_id}` | {rule.rows_selected_total} | {rule.valid_test_fold_count} | "
                f"{rule.total_test_selected_count} | {format_number(rule.avg_test_selected_count)} | "
                f"{rule.max_test_selected_count} | {', '.join(rule.warning_flags)} |"
            )

    lines.extend(
        [
            "",
            "## Warning Flags",
            "",
            *[f"- `{flag}`" for flag in report.warning_flags],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds / 3600:.2f}h"
    return f"{seconds / 86400:.2f}d"


def format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
