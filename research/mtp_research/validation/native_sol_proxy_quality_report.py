"""Writers for native SOL proxy quality reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.validation.native_sol_proxy_quality_models import NativeSolProxyQualityReport


def report_to_dict(report: NativeSolProxyQualityReport) -> dict[str, Any]:
    return report.to_dict()


def write_report_json(report: NativeSolProxyQualityReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: NativeSolProxyQualityReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Native SOL Proxy Quality Report",
        "",
        "> Warning: Native SOL proxy quality gating is diagnostic only. It is not a trading signal.",
        "",
        "## Config",
        "",
    ]
    for key, value in report.config.to_dict().items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Native Proxy Row Counts",
            "",
            f"- Dataset path: `{report.dataset_path}`",
            f"- Row count: `{report.row_count}`",
            f"- Native proxy backed: `{report.native_proxy_backed_count}`",
            f"- Non-proxy: `{report.non_proxy_count}`",
            f"- Native proxy passed: `{report.native_proxy_passed_count}`",
            f"- Native proxy failed: `{report.native_proxy_failed_count}`",
            f"- Overall pass rate: `{report.pass_rate}`",
            "",
            "## Failure Reasons",
            "",
            "| Reason | Count |",
            "| --- | ---: |",
        ]
    )
    for reason, count in report.failure_reason_counts.items():
        lines.append(f"| `{reason}` | {count} |")
    lines.extend(["", "## Token Counts", "", "| Token | Count |", "| --- | ---: |"])
    for token, count in report.token_counts.items():
        lines.append(f"| `{token}` | {count} |")
    lines.extend(["", "## Warnings", ""])
    for flag in report.warning_flags:
        lines.append(f"- `{flag}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
