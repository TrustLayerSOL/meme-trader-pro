"""Models for price proxy coverage diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def make_price_coverage_report_id() -> str:
    return f"price_coverage_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


@dataclass
class PriceCoverageByToken:
    token_mint: str
    event_count: int = 0
    events_with_price_quote: int = 0
    price_coverage_rate: float | None = None
    min_price_quote: float | None = None
    max_price_quote: float | None = None
    first_price_ts: int | None = None
    last_price_ts: int | None = None
    event_type_counts: dict[str, int] = field(default_factory=dict)
    priced_event_type_counts: dict[str, int] = field(default_factory=dict)
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class PriceCoverageReport:
    report_id: str
    created_at: str
    event_count: int = 0
    events_with_price_quote: int = 0
    price_coverage_rate: float | None = None
    token_count: int = 0
    tokens_with_price: int = 0
    event_type_counts: dict[str, int] = field(default_factory=dict)
    priced_event_type_counts: dict[str, int] = field(default_factory=dict)
    by_token: list[PriceCoverageByToken] = field(default_factory=list)
    no_price_label_count: int = 0
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    likely_no_price_causes: dict[str, int] = field(default_factory=dict)
    recommended_next_actions: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
