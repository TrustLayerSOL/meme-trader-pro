"""Models for clean-vs-fallback entry price coverage comparisons."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def make_entry_price_coverage_report_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"entry_price_coverage_{stamp}_{uuid4().hex[:8]}"


@dataclass
class EntryPriceCoverageSummary:
    name: str
    outcome_path: str
    dataset_path: str | None = None
    total_labels: int = 0
    labels_with_entry_price: int = 0
    labels_missing_entry_price: int = 0
    labels_with_forward_return: int = 0
    sparse_or_better_labels: int = 0
    good_labels: int = 0
    no_price_labels: int = 0
    nearest_fallback_labels: int = 0
    entry_price_source_counts: dict[str, int] = field(default_factory=dict)
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryPriceCoverageComparison:
    report_id: str
    created_at: str
    clean_summary: EntryPriceCoverageSummary
    fallback_summary: EntryPriceCoverageSummary
    entry_price_gain: int = 0
    forward_return_gain: int = 0
    sparse_or_better_gain: int = 0
    no_price_reduction: int = 0
    warnings: list[str] = field(default_factory=list)
    recommended_next_actions: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
