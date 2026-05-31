"""Report writers for outlier price-path review."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.validation.outlier_price_path_models import OutlierPricePathReport


WARNING_TEXT = "Outlier price-path review is diagnostic only. It is not a trading signal."


def report_to_dict(report: OutlierPricePathReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: OutlierPricePathReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: OutlierPricePathReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Outlier Price-Path Review",
        "",
        f"> Warning: {WARNING_TEXT}",
        "",
        "## Summary",
        "",
        f"- Reviewed count: `{report.reviewed_count}`",
        f"- Classification counts: `{report.classification_counts}`",
        f"- Token counts: `{report.token_counts}`",
        f"- Recommended next action: `{report.recommended_next_action}`",
        f"- Warning flags: `{report.warning_flags}`",
        "",
        "## Reviewed Rows",
        "",
        "| Rule | Token | Snapshot | Forward | Runup | Drawdown | Entry Source | Points | Classification | Warnings |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for review in report.reviews:
        lines.append(
            "| "
            f"`{review.rule_id}` | `{review.token_mint}` | {review.snapshot_ts} | "
            f"{_fmt(review.forward_return)} | {_fmt(review.max_runup)} | {_fmt(review.max_drawdown)} | "
            f"`{review.entry_price_source}` | {review.local_price_points_total} | "
            f"`{review.outlier_classification}` | `{review.warning_flags}` |"
        )
    lines.extend(["", "## Price-Path Summaries", ""])
    for review in report.reviews:
        first_point = review.price_path_points[0] if review.price_path_points else None
        lines.extend(
            [
                f"### `{review.row_id}`",
                "",
                f"- Rule: `{review.rule_id}`",
                f"- First price point: `{first_point.price_quote if first_point else None}` at `{first_point.ts if first_point else None}`",
                f"- Entry price: `{review.entry_price}` at `{review.entry_price_ts}`",
                f"- End price: `{review.end_price}` at `{review.end_price_ts}`",
                f"- Local min/max: `{review.price_path_min}` / `{review.price_path_max}`",
                f"- Recomputed return: `{_fmt(review.price_path_return_recomputed)}`",
                f"- Max gap seconds: `{review.max_gap_between_price_points_sec}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
