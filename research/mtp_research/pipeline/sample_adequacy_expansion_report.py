"""Report writers for sample adequacy evidence expansion plans."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.mtp_research.pipeline.sample_adequacy_expansion_models import (
    SampleAdequacyExpansionPlan,
)


PLAN_WARNING = "This is a bounded evidence expansion plan. It does not call Helius or trade."


def expansion_plan_to_dict(plan: SampleAdequacyExpansionPlan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["warning"] = PLAN_WARNING
    return payload


def write_expansion_plan_json(plan: SampleAdequacyExpansionPlan, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(expansion_plan_to_dict(plan), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_expansion_plan_markdown(plan: SampleAdequacyExpansionPlan, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = plan.sample_adequacy
    lines = [
        "# Sample Adequacy Evidence Expansion Plan",
        "",
        f"> Warning: {PLAN_WARNING}",
        "",
        f"- Plan ID: `{plan.plan_id}`",
        f"- Created at: `{plan.created_at}`",
        f"- Sample adequate: `{plan.sample_adequate}`",
        f"- Recommended next action: `{plan.recommended_next_action}`",
        f"- Recommended bounded command: `{plan.recommended_bounded_command}`",
        "",
        "## Sample Adequacy",
        "",
        f"- Real token count: `{sample.real_token_count}`",
        f"- Time span seconds: `{sample.time_span_seconds}`",
        f"- Valid test fold count: `{sample.valid_test_fold_count}`",
        f"- Total selected test count: `{sample.total_test_selected_count}`",
        f"- Adequate for rejection: `{sample.adequate_for_rejection}`",
        f"- Adequate for promotion: `{sample.adequate_for_promotion}`",
        f"- Recommended data expansion: `{sample.recommended_data_expansion}`",
        "",
        "## Shortfalls",
        "",
        f"- Token shortfall: `{plan.token_shortfall}`",
        f"- Time span shortfall seconds: `{plan.time_span_shortfall_seconds}`",
        f"- Selected count shortfall: `{plan.selected_count_shortfall}`",
        "",
        "## Bounded Backfill Plan Items",
        "",
        "| Token | Target | Role | Reason | Signature Limit | Transaction Limit |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for item in plan.time_span_plan.plan_items:
        lines.append(
            f"| `{item.token_mint}` | `{item.target_address}` | {item.role} | "
            f"{item.reason} | {item.recommended_signature_limit} | "
            f"{item.recommended_transaction_limit} |"
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
