"""Report writers for time-span backfill plans."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.pipeline.time_span_backfill_models import TimeSpanBackfillPlan


PLAN_WARNING = "This is a backfill planning report. It does not trade."


def plan_to_dict(plan: TimeSpanBackfillPlan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["warning"] = PLAN_WARNING
    return payload


def write_plan_json(plan: TimeSpanBackfillPlan, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan_to_dict(plan), indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_plan_markdown(plan: TimeSpanBackfillPlan, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Time-Span Expansion Backfill Plan v0",
        "",
        f"> Warning: {PLAN_WARNING}",
        "",
        f"- Plan ID: `{plan.plan_id}`",
        f"- Created at: `{plan.created_at}`",
        f"- Candidate count: `{plan.candidate_count}`",
        f"- Real candidate count: `{plan.real_candidate_count}`",
        f"- Target token count: `{plan.target_token_count}`",
        f"- Target pool count: `{plan.target_pool_count}`",
        f"- Estimated signature requests: `{plan.estimated_signature_requests}`",
        f"- Estimated transaction requests: `{plan.estimated_transaction_requests}`",
        f"- Recommended next command: `{plan.recommended_next_command}`",
        "",
        "## Current Coverage",
        "",
        "| Token | Pool | Liquidity USD | Raw TX | Trade Events | Priced Events | Research Rows | Time Span Seconds | Needs Backfill | Warnings |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in plan.coverage_items:
        lines.append(
            f"| `{item.token_mint}` | `{item.pool_address}` | {format_number(item.liquidity_usd)} | "
            f"{item.raw_tx_count} | {item.trade_event_count} | {item.priced_event_count} | "
            f"{item.research_row_count} | {format_number(item.time_span_seconds)} | "
            f"{item.needs_backfill} | {', '.join(item.warning_flags)} |"
        )
    lines.extend(
        [
            "",
            "## Plan Items",
            "",
            "| Token | Target | Role | Reason | Signature Limit | Transaction Limit | Priority |",
            "|---|---|---|---|---:|---:|---:|",
        ]
    )
    for item in plan.plan_items:
        lines.append(
            f"| `{item.token_mint}` | `{item.target_address}` | {item.role} | "
            f"{item.reason} | {item.recommended_signature_limit} | "
            f"{item.recommended_transaction_limit} | {item.priority} |"
        )
    lines.extend(
        [
            "",
            "## Warning Flags",
            "",
            *[f"- `{flag}`" for flag in plan.warning_flags],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
