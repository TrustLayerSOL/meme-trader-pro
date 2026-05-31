"""Models for evidence population pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class EvidenceRunConfig:
    run_id: str
    candidate_limit: int = 10
    max_signatures_per_target: int = 100
    max_transactions_per_target: int = 100
    include_failed: bool = False
    dry_run: bool = True
    require_execute_flag: bool = True
    roles: list[str] = field(default_factory=lambda: ["mint", "pool", "creator"])
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRunSummary:
    run_id: str
    created_at: str
    dry_run: bool
    candidates_seen: int = 0
    candidates_selected: int = 0
    targets_planned: int = 0
    signatures_seen: int = 0
    transactions_fetched: int = 0
    raw_transactions_inserted: int = 0
    raw_transactions_updated: int = 0
    normalized_events_inserted: int = 0
    normalized_events_updated: int = 0
    trade_events_inserted: int = 0
    trade_events_updated: int = 0
    feature_snapshots_inserted: int = 0
    feature_snapshots_updated: int = 0
    outcome_labels_inserted: int = 0
    outcome_labels_updated: int = 0
    research_rows_inserted: int = 0
    research_rows_updated: int = 0
    warning_flags: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_evidence_run_id(prefix: str = "evidence_run") -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
