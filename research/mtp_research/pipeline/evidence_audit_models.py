"""Models for offline evidence run diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def make_evidence_audit_report_id(prefix: str = "evidence_audit") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


@dataclass
class EvidenceStoreCount:
    name: str
    path: str
    exists: bool
    row_count: int = 0
    file_size_bytes: int = 0
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class EvidenceDropoff:
    from_stage: str
    to_stage: str
    from_count: int
    to_count: int
    retained_ratio: float | None = None
    dropped_count: int = 0
    warning_flags: list[str] = field(default_factory=list)


@dataclass
class TargetQualitySummary:
    target_count: int = 0
    role_counts: dict[str, int] = field(default_factory=dict)
    targets_with_token_mint: int = 0
    targets_with_pool_role: int = 0
    targets_with_creator_role: int = 0
    targets_with_wallet_role: int = 0
    mint_only_candidate_count: int = 0
    candidates_with_pool_address: int = 0
    candidates_with_creator_wallet: int = 0
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceAuditReport:
    report_id: str
    created_at: str
    store_counts: list[EvidenceStoreCount] = field(default_factory=list)
    dropoffs: list[EvidenceDropoff] = field(default_factory=list)
    target_quality: TargetQualitySummary | None = None
    event_type_counts: dict[str, int] = field(default_factory=dict)
    label_quality_counts: dict[str, int] = field(default_factory=dict)
    thesis_recommendation_counts: dict[str, int] = field(default_factory=dict)
    bottleneck_stage: str | None = None
    top_warnings: list[str] = field(default_factory=list)
    recommended_next_actions: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
