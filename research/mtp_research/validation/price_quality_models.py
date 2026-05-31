"""Models for diagnostic price-quality gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class PriceQualityConfig:
    max_entry_staleness_sec: int = 120
    min_future_price_points: int = 3
    max_price_gap_sec: int = 300
    allow_nearest_fallback: bool = False
    allow_no_future_liquidity: bool = False
    allow_rug_like_drop: bool = True
    min_label_quality: str = "sparse"
    max_forward_return_abs: float | None = None
    max_runup_abs: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceQualityDecision:
    row_id: str
    token_mint: str
    passed: bool
    reasons_failed: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    entry_staleness_sec: int | None = None
    future_price_points: int = 0
    entry_price_source: str | None = None
    label_quality: str = "unknown"
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriceQualityGateReport:
    report_id: str
    created_at: str
    dataset_path: str
    input_row_count: int = 0
    passed_row_count: int = 0
    failed_row_count: int = 0
    pass_rate: float | None = None
    token_count_input: int = 0
    token_count_passed: int = 0
    failure_reason_counts: dict[str, int] = field(default_factory=dict)
    entry_source_counts_input: dict[str, int] = field(default_factory=dict)
    entry_source_counts_passed: dict[str, int] = field(default_factory=dict)
    label_quality_counts_input: dict[str, int] = field(default_factory=dict)
    label_quality_counts_passed: dict[str, int] = field(default_factory=dict)
    config: PriceQualityConfig = field(default_factory=PriceQualityConfig)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_price_quality_gate_report_id(prefix: str = "price_quality_gate") -> str:
    created_at = utc_now_iso()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
