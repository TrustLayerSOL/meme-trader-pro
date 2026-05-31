"""Models for research thesis tracking and decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class SampleAdequacyReport:
    real_token_count: int = 0
    time_span_seconds: int | None = None
    valid_test_fold_count: int = 0
    total_test_selected_count: int = 0
    adequate_for_rejection: bool = False
    adequate_for_promotion: bool = False
    warning_flags: list[str] = field(default_factory=list)
    recommended_data_expansion: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ThesisReference:
    thesis_id: str
    name: str
    status: str
    priority: str
    strategy_family: str
    current_stage: str = "research"
    linked_rule_ids: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)
    required_data_sources: list[str] = field(default_factory=list)
    promotion_criteria: list[str] = field(default_factory=list)
    rejection_criteria: list[str] = field(default_factory=list)
    known_gaps: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ThesisDecision:
    decision_id: str
    thesis_id: str
    created_at: str
    prior_status: str
    recommended_status: str
    confidence: float
    reason: str
    supporting_rule_ids: list[str] = field(default_factory=list)
    supporting_validation_ids: list[str] = field(default_factory=list)
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ThesisDecision":
        return cls(
            decision_id=payload["decision_id"],
            thesis_id=payload["thesis_id"],
            created_at=payload["created_at"],
            prior_status=payload["prior_status"],
            recommended_status=payload["recommended_status"],
            confidence=payload["confidence"],
            reason=payload["reason"],
            supporting_rule_ids=list(payload.get("supporting_rule_ids", [])),
            supporting_validation_ids=list(payload.get("supporting_validation_ids", [])),
            warning_flags=list(payload.get("warning_flags", [])),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class ThesisEvaluationSummary:
    thesis_id: str
    name: str
    status: str
    linked_rule_count: int = 0
    linked_validation_count: int = 0
    best_consistency_score: float | None = None
    best_avg_test_net_return: float | None = None
    best_positive_test_fold_rate: float | None = None
    total_test_selected_count: int = 0
    recommended_status: str = "needs_more_data"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def make_thesis_decision_id(thesis_id: str) -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{normalize_thesis_id(thesis_id)}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"thesis-decision-{digest}"


def normalize_thesis_id(value: str) -> str:
    return value.strip().upper()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
