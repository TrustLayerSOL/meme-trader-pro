"""Models for bounded evidence expansion decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class RuleExpansionSignal:
    rule_id: str
    rule_name: str
    selected_count: int = 0
    valid_fold_count: int = 0
    positive_fold_rate: float | None = None
    median_net_return: float | None = None
    capped_mean_return: float | None = None
    raw_mean_return: float | None = None
    outlier_return_share: float | None = None
    plausible_outlier_count: int = 0
    suspicious_outlier_count: int = 0
    fallback_dependent_outlier_count: int = 0
    signal_classification: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceExpansionNeed:
    need_type: str
    priority: str = "medium"
    reason: str = ""
    target_value: int | float | None = None
    current_value: int | float | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class BoundedExpansionPlan:
    plan_id: str
    created_at: str
    recommended: bool = False
    candidate_limit: int = 0
    max_signatures_per_target: int = 0
    max_transactions_per_target: int = 0
    stop_after_targets: int | None = None
    min_liquidity_usd: float | None = 10000
    require_pool_address: bool = True
    estimated_signature_requests: int = 0
    estimated_transaction_requests: int = 0
    recommended_command: str | None = None
    rationale: str = ""
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceExpansionDecisionReport:
    report_id: str
    created_at: str
    diagnostic_dataset_path: str
    raw_row_count: int = 0
    diagnostic_row_count: int = 0
    real_token_count: int = 0
    time_span_seconds: int | None = None
    price_coverage_rate: float | None = None
    no_price_label_count: int = 0
    rule_signals: list[RuleExpansionSignal] = field(default_factory=list)
    expansion_needs: list[EvidenceExpansionNeed] = field(default_factory=list)
    bounded_plan: BoundedExpansionPlan | None = None
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_evidence_expansion_decision_report_id(prefix: str = "evidence_expansion_decision") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def make_bounded_expansion_plan_id(prefix: str = "bounded_expansion_plan") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
