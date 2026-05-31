"""Models for diagnostic walk-forward review reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def make_diagnostic_walk_forward_review_id(
    prefix: str = "diagnostic_walk_forward_review",
) -> str:
    digest = sha256(datetime.now(timezone.utc).isoformat().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DiagnosticRuleWalkForwardFinding:
    rule_id: str
    rule_name: str
    valid_test_fold_count: int = 0
    total_test_selected_count: int = 0
    avg_test_selected_count: float | None = None
    avg_test_net_return: float | None = None
    median_test_net_return: float | None = None
    positive_test_fold_rate: float | None = None
    avg_test_win_rate: float | None = None
    avg_test_profit_factor: float | None = None
    avg_test_cumulative_net_return: float | None = None
    worst_test_cumulative_net_return: float | None = None
    avg_test_max_drawdown: float | None = None
    consistency_score: float | None = None
    fallback_dependency_warning: bool = False
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticWalkForwardReview:
    review_id: str
    created_at: str
    dataset_path: str
    walk_forward_result_path: str | None = None
    fold_config_name: str | None = None
    row_count: int = 0
    token_count: int = 0
    time_span_seconds: int | None = None
    nearest_fallback_row_count: int = 0
    rules_tested: int = 0
    rules_with_valid_folds: int = 0
    findings: list[DiagnosticRuleWalkForwardFinding] = field(default_factory=list)
    best_rule_by_consistency: str | None = None
    best_rule_by_avg_test_net: str | None = None
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
