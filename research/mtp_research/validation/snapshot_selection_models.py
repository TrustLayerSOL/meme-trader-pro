"""Snapshot selection models for offline validation rebuilds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SnapshotSelectionConfig:
    strategy: str = "head"
    max_snapshots: int | None = None
    max_snapshots_per_token: int | None = None
    min_time_gap_seconds: int | None = None
    token_mints: list[str] = field(default_factory=list)
    real_only: bool = False
    min_liquidity_usd: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotSelectionSummary:
    strategy: str
    input_snapshot_count: int = 0
    selected_snapshot_count: int = 0
    input_token_count: int = 0
    selected_token_count: int = 0
    input_time_min: int | None = None
    input_time_max: int | None = None
    input_time_span_seconds: int | None = None
    selected_time_min: int | None = None
    selected_time_max: int | None = None
    selected_time_span_seconds: int | None = None
    selected_by_token: dict[str, int] = field(default_factory=dict)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
