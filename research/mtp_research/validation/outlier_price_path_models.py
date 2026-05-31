"""Models for manual outlier price-path review reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class PricePathPoint:
    token_mint: str
    ts: int
    price_quote: float
    event_id: str | None = None
    event_type: str | None = None
    signature: str | None = None
    actor: str | None = None
    side: str | None = None
    base_qty: float | None = None
    quote_qty: float | None = None
    confidence: float | None = None
    entry_distance_sec: int | None = None
    end_distance_sec: int | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutlierPricePathReview:
    row_id: str
    rule_id: str
    token_mint: str
    snapshot_ts: int
    horizon_name: str
    horizon_seconds: int
    entry_price: float | None = None
    entry_price_ts: int | None = None
    entry_price_source: str | None = None
    end_price: float | None = None
    end_price_ts: int | None = None
    forward_return: float | None = None
    max_runup: float | None = None
    max_drawdown: float | None = None
    local_price_points_before: int = 0
    local_price_points_after: int = 0
    local_price_points_total: int = 0
    nearest_price_before_ts: int | None = None
    nearest_price_after_ts: int | None = None
    max_gap_between_price_points_sec: int | None = None
    price_path_min: float | None = None
    price_path_max: float | None = None
    price_path_return_recomputed: float | None = None
    outlier_classification: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    price_path_points: list[PricePathPoint] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutlierPricePathReport:
    report_id: str
    created_at: str
    dataset_path: str
    events_path: str
    reviewed_rule_ids: list[str] = field(default_factory=list)
    reviewed_count: int = 0
    plausible_count: int = 0
    suspicious_count: int = 0
    unusable_count: int = 0
    fallback_dependent_count: int = 0
    isolated_price_print_count: int = 0
    classification_counts: dict[str, int] = field(default_factory=dict)
    token_counts: dict[str, int] = field(default_factory=dict)
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    reviews: list[OutlierPricePathReview] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_outlier_price_path_report_id(prefix: str = "outlier_price_path") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
