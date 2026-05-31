"""Models for diagnostic clean-vs-fallback validation review."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


DIAGNOSTIC_FALLBACK_WARNING = (
    "diagnostic fallback dataset; not valid for live trading or thesis promotion without human review."
)


@dataclass
class DiagnosticDatasetSummary:
    name: str
    dataset_path: str
    row_count: int = 0
    token_count: int = 0
    rows_with_forward_return: int = 0
    rows_with_nearest_fallback_entry: int = 0
    sparse_or_better_rows: int = 0
    good_rows: int = 0
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    entry_price_source_counts: dict[str, int] = field(default_factory=dict)
    horizon_counts: dict[str, int] = field(default_factory=dict)
    window_counts: dict[str, int] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticRuleComparison:
    rule_id: str
    clean_selected_count: int = 0
    diagnostic_selected_count: int = 0
    selected_count_gain: int = 0
    clean_avg_net_return: float | None = None
    diagnostic_avg_net_return: float | None = None
    clean_win_rate: float | None = None
    diagnostic_win_rate: float | None = None
    diagnostic_nearest_fallback_selected_count: int = 0
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class DiagnosticWalkForwardComparison:
    rule_id: str
    clean_valid_test_fold_count: int = 0
    diagnostic_valid_test_fold_count: int = 0
    clean_total_test_selected_count: int = 0
    diagnostic_total_test_selected_count: int = 0
    clean_avg_test_net_return: float | None = None
    diagnostic_avg_test_net_return: float | None = None
    clean_positive_test_fold_rate: float | None = None
    diagnostic_positive_test_fold_rate: float | None = None
    clean_consistency_score: float | None = None
    diagnostic_consistency_score: float | None = None
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class DiagnosticThesisComparison:
    thesis_id: str
    clean_recommended_status: str | None = None
    diagnostic_recommended_status: str | None = None
    changed: bool = False
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class DiagnosticValidationReview:
    review_id: str
    created_at: str
    clean_dataset: DiagnosticDatasetSummary
    diagnostic_dataset: DiagnosticDatasetSummary
    row_gain: int = 0
    forward_return_row_gain: int = 0
    nearest_fallback_row_count: int = 0
    rule_comparisons: list[DiagnosticRuleComparison] = field(default_factory=list)
    walk_forward_comparisons: list[DiagnosticWalkForwardComparison] = field(default_factory=list)
    thesis_comparisons: list[DiagnosticThesisComparison] = field(default_factory=list)
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_diagnostic_validation_review_id(prefix: str = "diagnostic_validation_review") -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
