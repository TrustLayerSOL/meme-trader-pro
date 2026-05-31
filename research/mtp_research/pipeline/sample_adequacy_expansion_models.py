"""Models for sample adequacy evidence expansion plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from research.mtp_research.pipeline.time_span_backfill_models import TimeSpanBackfillPlan
from research.mtp_research.validation.thesis_models import SampleAdequacyReport


@dataclass
class SampleAdequacyExpansionPlan:
    plan_id: str
    created_at: str
    sample_adequacy: SampleAdequacyReport
    time_span_plan: TimeSpanBackfillPlan
    sample_adequate: bool = False
    token_shortfall: int = 0
    time_span_shortfall_seconds: int = 0
    selected_count_shortfall: int = 0
    recommended_next_action: str = "unknown"
    recommended_bounded_command: str | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_sample_adequacy_expansion_plan_id(
    prefix: str = "sample_adequacy_expansion_plan",
) -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
