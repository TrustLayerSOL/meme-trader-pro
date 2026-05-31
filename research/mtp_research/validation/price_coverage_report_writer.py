"""Writers for price coverage diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.price_coverage_models import PriceCoverageReport


def report_to_dict(report: PriceCoverageReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: PriceCoverageReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: PriceCoverageReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown(report), encoding="utf-8")
    return path


def _markdown(report: PriceCoverageReport) -> str:
    lines = [
        "# Price Proxy Coverage Report",
        "",
        f"- created_at: `{report.created_at}`",
        f"- report_id: `{report.report_id}`",
        f"- event_count: `{report.event_count}`",
        f"- events_with_price_quote: `{report.events_with_price_quote}`",
        f"- price_coverage_rate: `{_percent(report.price_coverage_rate)}`",
        f"- token_count: `{report.token_count}`",
        f"- tokens_with_price: `{report.tokens_with_price}`",
        "",
        "## Label Quality Counts",
        *_kv(report.label_quality_counts),
        "",
        "## Likely no_price Causes",
        *_kv(report.likely_no_price_causes),
        "",
        "## Event Type Counts",
        *_kv(report.event_type_counts),
        "",
        "## Priced Event Type Counts",
        *_kv(report.priced_event_type_counts),
        "",
        "## Token Coverage",
        "",
        "| token_mint | event_count | priced_events | coverage | first_price_ts | last_price_ts | warnings |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report.by_token:
        lines.append(
            f"| {item.token_mint} | {item.event_count} | {item.events_with_price_quote} | "
            f"{_percent(item.price_coverage_rate)} | {item.first_price_ts or ''} | {item.last_price_ts or ''} | "
            f"{', '.join(item.warning_flags)} |"
        )
    lines.extend(["", "## Recommended Next Actions", *[f"- {action}" for action in report.recommended_next_actions]])
    lines.extend(["", "## Warnings", *[f"- {warning}" for warning in report.warning_flags or ["none"]]])
    lines.extend(["", "This is a diagnostic report, not a trading signal.", ""])
    return "\n".join(lines)


def _kv(values: dict[str, int]) -> list[str]:
    return [f"- {key}: `{value}`" for key, value in sorted(values.items())] or ["- none"]


def _percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"
