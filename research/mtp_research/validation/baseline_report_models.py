"""Models for baseline exploratory edge reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class FeatureBucket:
    feature_name: str
    bucket_name: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    row_count: int = 0
    token_count: int = 0
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class BucketOutcomeSummary:
    row_count: int = 0
    token_count: int = 0
    rows_with_forward_return: int = 0
    avg_forward_return: float | None = None
    median_forward_return: float | None = None
    positive_forward_return_count: int = 0
    negative_forward_return_count: int = 0
    win_rate: float | None = None
    avg_max_runup: float | None = None
    median_max_runup: float | None = None
    avg_max_drawdown: float | None = None
    median_max_drawdown: float | None = None
    rug_like_drop_count: int = 0
    rug_like_drop_rate: float | None = None
    no_future_liquidity_count: int = 0
    no_future_liquidity_rate: float | None = None
    survived_horizon_count: int = 0
    survived_horizon_rate: float | None = None
    avg_future_event_count: float | None = None
    avg_future_quote_volume: float | None = None


@dataclass
class FeatureBucketResult:
    feature_name: str
    window_name: str | None
    horizon_name: str | None
    bucket: FeatureBucket
    outcome_summary: BucketOutcomeSummary
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureReport:
    feature_name: str
    row_count: int
    bucket_count: int
    best_bucket_name: str | None = None
    worst_bucket_name: str | None = None
    spread_avg_forward_return: float | None = None
    spread_median_forward_return: float | None = None
    bucket_results: list[FeatureBucketResult] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineEdgeReport:
    report_id: str
    created_at: str
    dataset_path: str
    row_count: int
    filtered_row_count: int
    token_count: int
    window_counts: dict[str, int] = field(default_factory=dict)
    horizon_counts: dict[str, int] = field(default_factory=dict)
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    feature_reports: list[FeatureReport] = field(default_factory=list)
    top_findings: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_report_id(prefix: str = "baseline_edge_report") -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"
