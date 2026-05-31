"""Report writers for walk-forward validation results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.validation.walk_forward_models import WalkForwardValidationResult


def result_to_dict(result: WalkForwardValidationResult) -> dict[str, Any]:
    return result.to_dict()


def write_result_json(result: WalkForwardValidationResult, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_dict(result), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_result_markdown(result: WalkForwardValidationResult, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = result.config
    lines = [
        "# Walk-Forward Validation Report v0",
        "",
        f"- Created at: `{result.created_at}`",
        f"- Validation ID: `{result.validation_id}`",
        f"- Dataset path: `{result.dataset_path}`",
        f"- Row count: `{result.row_count}`",
        f"- Filtered row count: `{result.filtered_row_count}`",
        f"- Fold count: `{result.fold_count}`",
        f"- Rules tested: `{result.rules_tested}`",
        "",
        "## Config",
        "",
        f"- Config ID: `{cfg.config_id}`",
        f"- Train window seconds: `{cfg.train_window_seconds}`",
        f"- Test window seconds: `{cfg.test_window_seconds}`",
        f"- Step seconds: `{cfg.step_seconds}`",
        f"- Gap seconds: `{cfg.gap_seconds}`",
        f"- Minimum train rows: `{cfg.min_train_rows}`",
        f"- Minimum test rows: `{cfg.min_test_rows}`",
        f"- Window: `{cfg.window_name}`",
        f"- Horizon: `{cfg.horizon_name}`",
        f"- Minimum label quality: `{cfg.min_label_quality}`",
        "",
        "## Warning Flags",
        "",
        *[f"- `{flag}`" for flag in result.warning_flags],
        "",
        "## Top Findings",
        "",
    ]
    lines.extend([f"- {finding}" for finding in result.top_findings] or ["- None"])
    lines.extend(
        [
            "",
            "## Folds",
            "",
            "| Fold | Train Start | Train End | Test Start | Test End | Train Rows | Test Rows |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for fold in result.folds:
        lines.append(
            f"| `{fold.fold_id}` | {fold.train_start_ts} | {fold.train_end_ts} | "
            f"{fold.test_start_ts} | {fold.test_end_ts} | {fold.train_row_count} | {fold.test_row_count} |"
        )
    lines.extend(
        [
            "",
            "## Rule Summaries",
            "",
            "| Rule | Valid Test Folds | Test Selected | Avg Test Net | Median Test Net | Positive Fold Rate | Avg Test Win Rate | Avg Test Profit Factor | Avg Test Cumulative Net | Avg Test Max Drawdown | Consistency Score | Warnings |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for summary in result.rule_summaries:
        lines.append(
            f"| `{summary.rule_id}` {summary.rule_name} | {summary.valid_test_fold_count} | "
            f"{summary.total_test_selected_count} | {format_percent(summary.avg_test_net_return)} | "
            f"{format_percent(summary.median_test_net_return)} | "
            f"{format_percent(summary.positive_test_fold_rate)} | "
            f"{format_percent(summary.avg_test_win_rate)} | "
            f"{format_number(summary.avg_test_profit_factor)} | "
            f"{format_percent(summary.avg_test_cumulative_net_return)} | "
            f"{format_percent(summary.avg_test_max_drawdown)} | "
            f"{format_number(summary.consistency_score)} | "
            f"{', '.join(summary.warning_flags)} |"
        )
    lines.extend(
        [
            "",
            "## Fold Rule Details",
            "",
            "| Fold | Rule | Train Selected | Test Selected | Train Avg Net | Test Avg Net | Train Win Rate | Test Win Rate | Warnings |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for fold_result in result.fold_rule_results:
        lines.append(
            f"| `{fold_result.fold_id}` | `{fold_result.rule_id}` | "
            f"{fold_result.train_selected_count} | {fold_result.test_selected_count} | "
            f"{format_percent(fold_result.train_avg_net_return)} | "
            f"{format_percent(fold_result.test_avg_net_return)} | "
            f"{format_percent(fold_result.train_win_rate)} | "
            f"{format_percent(fold_result.test_win_rate)} | "
            f"{', '.join(fold_result.warning_flags)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    return f"{value:.6f}"
