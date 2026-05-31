"""Report writers for diagnostic price-quality gates."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.price_quality_models import PriceQualityGateReport


def report_to_dict(report: PriceQualityGateReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: PriceQualityGateReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: PriceQualityGateReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Price Quality Gate Report",
        "",
        "> Warning: Price-quality gating is diagnostic only. It is not a trading signal.",
        "",
        f"- Report ID: `{report.report_id}`",
        f"- Created at: `{report.created_at}`",
        f"- Dataset path: `{report.dataset_path}`",
        "",
        "## Config",
        "",
        "| Setting | Value |",
        "| --- | ---: |",
    ]
    for key, value in asdict(report.config).items():
        lines.append(f"| `{key}` | `{value}` |")

    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Input Rows | Passed Rows | Failed Rows | Pass Rate | Input Tokens | Passed Tokens |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| {report.input_row_count} | {report.passed_row_count} | {report.failed_row_count} | "
            f"{_fmt(report.pass_rate)} | {report.token_count_input} | {report.token_count_passed} |",
            "",
            "## Failure Reasons",
            "",
            "| Reason | Count |",
            "| --- | ---: |",
        ]
    )
    _append_counter_rows(lines, report.failure_reason_counts)
    lines.extend(["", "## Entry Sources Before", "", "| Source | Count |", "| --- | ---: |"])
    _append_counter_rows(lines, report.entry_source_counts_input)
    lines.extend(["", "## Entry Sources After", "", "| Source | Count |", "| --- | ---: |"])
    _append_counter_rows(lines, report.entry_source_counts_passed)
    lines.extend(["", "## Label Quality Before", "", "| Quality | Count |", "| --- | ---: |"])
    _append_counter_rows(lines, report.label_quality_counts_input)
    lines.extend(["", "## Label Quality After", "", "| Quality | Count |", "| --- | ---: |"])
    _append_counter_rows(lines, report.label_quality_counts_passed)
    lines.extend(["", "## Warnings", "", *[f"- `{flag}`" for flag in report.warning_flags], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _append_counter_rows(lines: list[str], counts: dict[str, int]) -> None:
    if not counts:
        lines.append("| none | 0 |")
        return
    for key, count in counts.items():
        lines.append(f"| `{key}` | {count} |")


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
