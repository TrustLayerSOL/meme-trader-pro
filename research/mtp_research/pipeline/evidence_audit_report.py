"""Writers for offline evidence audit reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.pipeline.evidence_audit_models import EvidenceAuditReport


def report_to_dict(report: EvidenceAuditReport) -> dict[str, Any]:
    return asdict(report)


def write_report_json(report: EvidenceAuditReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report_markdown(report: EvidenceAuditReport, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown(report), encoding="utf-8")
    return path


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _markdown(report: EvidenceAuditReport) -> str:
    lines = [
        "# Evidence Run Audit",
        "",
        f"- created_at: `{report.created_at}`",
        f"- report_id: `{report.report_id}`",
        f"- bottleneck_stage: `{report.bottleneck_stage or 'n/a'}`",
        "",
        "## Top Warnings",
        "",
    ]
    lines.extend(_bullet_list(report.top_warnings))
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(_bullet_list(report.recommended_next_actions))
    lines.extend(["", "## Target Quality", ""])
    target = report.target_quality
    if target is None:
        lines.append("- n/a")
    else:
        lines.extend(
            [
                f"- target_count: `{target.target_count}`",
                f"- role_counts: `{target.role_counts}`",
                f"- targets_with_token_mint: `{target.targets_with_token_mint}`",
                f"- targets_with_pool_role: `{target.targets_with_pool_role}`",
                f"- targets_with_creator_role: `{target.targets_with_creator_role}`",
                f"- targets_with_wallet_role: `{target.targets_with_wallet_role}`",
                f"- mint_only_candidate_count: `{target.mint_only_candidate_count}`",
                f"- candidates_with_pool_address: `{target.candidates_with_pool_address}`",
                f"- candidates_with_creator_wallet: `{target.candidates_with_creator_wallet}`",
                f"- warning_flags: `{target.warning_flags}`",
            ]
        )
    lines.extend(["", "## Store Counts", "", "| Store | Rows | Exists | Size Bytes | Warnings |", "|---|---:|---|---:|---|"])
    for count in report.store_counts:
        lines.append(
            f"| {count.name} | {count.row_count} | {count.exists} | {count.file_size_bytes} | {', '.join(count.warning_flags)} |"
        )
    lines.extend(["", "## Dropoffs", "", "| From | To | From Count | To Count | Retained | Dropped | Warnings |", "|---|---|---:|---:|---:|---:|---|"])
    for dropoff in report.dropoffs:
        lines.append(
            f"| {dropoff.from_stage} | {dropoff.to_stage} | {dropoff.from_count} | {dropoff.to_count} | "
            f"{format_percent(dropoff.retained_ratio)} | {dropoff.dropped_count} | {', '.join(dropoff.warning_flags)} |"
        )
    lines.extend(["", "## Event Type Counts", ""])
    lines.extend(_key_value_lines(report.event_type_counts))
    lines.extend(["", "## Label Quality Counts", ""])
    lines.extend(_key_value_lines(report.label_quality_counts))
    lines.extend(["", "## Thesis Recommendation Counts", ""])
    lines.extend(_key_value_lines(report.thesis_recommendation_counts))
    lines.extend(["", "This report is diagnostic only and is not a trading signal.", ""])
    return "\n".join(lines)


def _bullet_list(values: list[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _key_value_lines(values: dict[str, int]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {key}: `{value}`" for key, value in sorted(values.items())]
