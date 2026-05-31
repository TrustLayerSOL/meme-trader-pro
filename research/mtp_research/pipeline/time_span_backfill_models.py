"""Models for time-span expansion backfill planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class TokenEvidenceCoverage:
    token_mint: str
    pool_address: str | None = None
    venue: str | None = None
    source: str | None = None
    liquidity_usd: float | None = None
    raw_tx_count: int = 0
    normalized_event_count: int = 0
    trade_event_count: int = 0
    priced_event_count: int = 0
    feature_snapshot_count: int = 0
    outcome_label_count: int = 0
    research_row_count: int = 0
    first_block_time: int | None = None
    last_block_time: int | None = None
    time_span_seconds: int | None = None
    has_pool_target: bool = False
    needs_backfill: bool = True
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeSpanBackfillPlanItem:
    token_mint: str
    pool_address: str | None
    target_address: str
    role: str
    reason: str
    recommended_signature_limit: int
    recommended_transaction_limit: int
    current_time_span_seconds: int | None = None
    current_raw_tx_count: int = 0
    priority: int = 100
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeSpanBackfillPlan:
    plan_id: str
    created_at: str
    candidate_count: int = 0
    real_candidate_count: int = 0
    coverage_items: list[TokenEvidenceCoverage] = field(default_factory=list)
    plan_items: list[TimeSpanBackfillPlanItem] = field(default_factory=list)
    target_token_count: int = 0
    target_pool_count: int = 0
    estimated_signature_requests: int = 0
    estimated_transaction_requests: int = 0
    recommended_next_command: str | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_time_span_backfill_plan_id(prefix: str = "time_span_backfill_plan") -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
