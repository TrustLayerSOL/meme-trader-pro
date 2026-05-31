"""Models for diagnostic selected-row and rule audit reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class SelectedRowAuditRecord:
    row_id: str
    rule_id: str
    token_mint: str
    snapshot_ts: int
    window_name: str
    horizon_name: str
    entry_price: float | None = None
    entry_price_ts: int | None = None
    entry_price_source: str | None = None
    entry_price_staleness_sec: int | None = None
    end_price: float | None = None
    end_price_ts: int | None = None
    forward_return: float | None = None
    net_return_estimate: float | None = None
    max_runup: float | None = None
    max_drawdown: float | None = None
    label_quality: str = "unknown"
    no_future_liquidity: bool = False
    rug_like_drop: bool | None = None
    buy_sell_imbalance: float | None = None
    possible_buy_count: int = 0
    possible_sell_count: int = 0
    unique_actor_count: int = 0
    confidence_weighted_net_flow: float = 0.0
    avg_event_confidence: float | None = None
    max_event_confidence: float | None = None
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleSelectedRowAudit:
    rule_id: str
    rule_name: str
    selected_count: int = 0
    token_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    win_rate: float | None = None
    avg_forward_return: float | None = None
    median_forward_return: float | None = None
    avg_net_return_estimate: float | None = None
    median_net_return_estimate: float | None = None
    top_outlier_count: int = 0
    outlier_return_share: float | None = None
    fallback_entry_count: int = 0
    fallback_entry_rate: float | None = None
    stale_entry_count: int = 0
    stale_entry_rate: float | None = None
    token_concentration: dict[str, int] = field(default_factory=dict)
    warning_flags: list[str] = field(default_factory=list)
    records: list[SelectedRowAuditRecord] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectedRowAuditReport:
    report_id: str
    created_at: str
    dataset_path: str
    audited_rule_ids: list[str] = field(default_factory=list)
    row_count: int = 0
    rule_audits: list[RuleSelectedRowAudit] = field(default_factory=list)
    cross_rule_findings: list[str] = field(default_factory=list)
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


def make_selected_row_audit_report_id(prefix: str = "selected_row_audit") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"{prefix}|{created}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
