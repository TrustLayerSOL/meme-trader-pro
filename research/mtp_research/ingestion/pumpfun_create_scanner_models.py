"""Models for bounded Pump.fun create-instruction scanning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class PumpFunCreateCandidate:
    signature: str
    slot: int | None = None
    block_time: int | None = None
    token_mint: str | None = None
    bonding_curve: str | None = None
    associated_bonding_curve: str | None = None
    creator_wallet: str | None = None
    instruction_index: int | None = None
    account_count: int = 0
    instruction_discriminator: str | None = None
    extraction_confidence: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PumpFunCreateScanBatch:
    batch_index: int
    signatures_seen: int = 0
    transactions_hydrated: int = 0
    direct_pumpfun_instruction_count: int = 0
    create_candidate_count: int = 0
    cursor_before: str | None = None
    next_cursor_before: str | None = None
    elapsed_seconds: float | None = None
    warning_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PumpFunCreateScanReport:
    report_id: str
    created_at: str
    program_id: str
    executed: bool = False
    max_batches: int = 0
    signatures_per_batch: int = 0
    hydrate_limit_per_batch: int = 0
    signatures_seen_total: int = 0
    transactions_hydrated_total: int = 0
    direct_pumpfun_instruction_count: int = 0
    create_candidate_count: int = 0
    candidates: list[PumpFunCreateCandidate] = field(default_factory=list)
    batches: list[PumpFunCreateScanBatch] = field(default_factory=list)
    viability: str = "unknown"
    recommended_next_action: str = "unknown"
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["batches"] = [batch.to_dict() for batch in self.batches]
        return payload


def make_pumpfun_create_scan_report_id(prefix: str = "pumpfun_create_scan") -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(created.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
