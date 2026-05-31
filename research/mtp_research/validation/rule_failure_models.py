"""Models for rule failure anatomy diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def make_rule_failure_review_id(prefix: str = "rule_failure_review") -> str:
    digest = sha256(datetime.now(timezone.utc).isoformat().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuleFoldAnatomy:
    rule_id: str
    fold_id: str
    fold_index: int
    test_selected_count: int = 0
    test_avg_net_return: float | None = None
    test_median_net_return: float | None = None
    test_win_rate: float | None = None
    test_profit_factor: float | None = None
    test_rug_like_drop_rate: float | None = None
    test_no_future_liquidity_rate: float | None = None
    fallback_entry_count: int = 0
    fallback_entry_rate: float | None = None
    token_counts: dict[str, int] = field(default_factory=dict)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleFailureAnatomy:
    rule_id: str
    rule_name: str
    valid_test_fold_count: int = 0
    positive_test_fold_count: int = 0
    negative_test_fold_count: int = 0
    positive_test_fold_rate: float | None = None
    total_test_selected_count: int = 0
    avg_test_selected_count: float | None = None
    avg_test_net_return: float | None = None
    median_test_net_return: float | None = None
    avg_cost_drag: float | None = None
    estimated_gross_minus_net_gap: float | None = None
    token_concentration: dict[str, int] = field(default_factory=dict)
    losing_token_counts: dict[str, int] = field(default_factory=dict)
    fallback_entry_count: int = 0
    fallback_entry_rate: float | None = None
    rug_like_drop_count: int = 0
    no_future_liquidity_count: int = 0
    likely_failure_causes: list[str] = field(default_factory=list)
    fold_anatomies: list[RuleFoldAnatomy] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleFailureReview:
    review_id: str
    created_at: str
    dataset_path: str
    walk_forward_path: str
    row_count: int = 0
    token_count: int = 0
    time_span_seconds: int | None = None
    nearest_fallback_row_count: int = 0
    rule_anatomies: list[RuleFailureAnatomy] = field(default_factory=list)
    recommended_next_action: str = "unknown"
    evidence_scale_recommendation: str = "unknown"
    rule_review_recommendation: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
