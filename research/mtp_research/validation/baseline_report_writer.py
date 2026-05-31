"""Writers for baseline edge reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.baseline_report_models import BaselineEdgeReport


def report_to_dict(report: BaselineEdgeReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: BaselineEdgeReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_report_markdown(report: BaselineEdgeReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Baseline Edge Report v0",
        "",
        f"- Created at: `{report.created_at}`",
        f"- Dataset path: `{report.dataset_path}`",
        f"- Row count: `{report.row_count}`",
        f"- Filtered row count: `{report.filtered_row_count}`",
        f"- Token count: `{report.token_count}`",
        f"- Window counts: `{report.window_counts}`",
        f"- Horizon counts: `{report.horizon_counts}`",
        f"- Label quality counts: `{report.label_quality_counts}`",
        "",
        "## Warning Flags",
        "",
        *[f"- `{flag}`" for flag in report.warning_flags],
        "",
        "## Top Findings",
        "",
    ]
    lines.extend([f"- {finding}" for finding in report.top_findings] or ["- None"])

    for feature_report in report.feature_reports:
        lines.extend(
            [
                "",
                f"## Feature: `{feature_report.feature_name}`",
                "",
                f"- Rows: `{feature_report.row_count}`",
                f"- Buckets: `{feature_report.bucket_count}`",
                f"- Best bucket: `{feature_report.best_bucket_name}`",
                f"- Worst bucket: `{feature_report.worst_bucket_name}`",
                f"- Avg return spread: `{format_percent(feature_report.spread_avg_forward_return)}`",
                f"- Warning flags: `{feature_report.warning_flags}`",
                "",
                "| Bucket | Bounds | Rows | Tokens | Avg Fwd Return | Median Fwd Return | Win Rate | Avg Runup | Avg Drawdown | Rug Drop Rate | No Future Liquidity Rate | Warnings |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for result in feature_report.bucket_results:
            bucket = result.bucket
            summary = result.outcome_summary
            bounds = f"{format_number(bucket.lower_bound)} to {format_number(bucket.upper_bound)}"
            lines.append(
                "| "
                f"{bucket.bucket_name} | {bounds} | {bucket.row_count} | {bucket.token_count} | "
                f"{format_percent(summary.avg_forward_return)} | "
                f"{format_percent(summary.median_forward_return)} | "
                f"{format_percent(summary.win_rate)} | "
                f"{format_percent(summary.avg_max_runup)} | "
                f"{format_percent(summary.avg_max_drawdown)} | "
                f"{format_percent(summary.rug_like_drop_rate)} | "
                f"{format_percent(summary.no_future_liquidity_rate)} | "
                f"{', '.join(result.warning_flags)} |"
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
    return f"{value:.4f}"
