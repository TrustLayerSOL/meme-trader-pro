from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MigrationEvidenceLevel(str, Enum):
    LEVEL_A = "LEVEL_A"
    LEVEL_B = "LEVEL_B"
    LEVEL_C = "LEVEL_C"
    CANDIDATE = "CANDIDATE"
    NONE = "NONE"


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class EvidenceRecord:
    signature: str
    slot: int | None
    observed_at: float
    commitment: str
    source_lane: str
    source_route: str
    mint: str | None = None
    pool: str | None = None
    evidence_level: MigrationEvidenceLevel | str = MigrationEvidenceLevel.NONE
    raw_tx_hash: str | None = None
    raw_tx_json: dict[str, Any] | None = None
    rule_hits: list[str] = field(default_factory=list)
    confidence: float | None = None

    def to_json_row(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "slot": self.slot,
            "observed_at": self.observed_at,
            "commitment": self.commitment,
            "source_lane": self.source_lane,
            "source_route": self.source_route,
            "mint": self.mint,
            "pool": self.pool,
            "evidence_level": _enum_value(self.evidence_level),
            "raw_tx_hash": self.raw_tx_hash,
            "raw_tx_json": self.raw_tx_json,
            "rule_hits": list(self.rule_hits),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class AccountSnapshotRecord:
    pubkey: str
    slot: int | None
    commitment: str
    observed_at: float
    snapshot_hash: str
    raw_snapshot_json: dict[str, Any] | None = None

    def dedupe_key(self) -> tuple[str, int | None, str]:
        return (self.pubkey, self.slot, self.commitment)

    def to_json_row(self) -> dict[str, Any]:
        return {
            "pubkey": self.pubkey,
            "slot": self.slot,
            "commitment": self.commitment,
            "observed_at": self.observed_at,
            "snapshot_hash": self.snapshot_hash,
            "raw_snapshot_json": self.raw_snapshot_json,
        }


@dataclass(frozen=True)
class LifecycleTransitionRecord:
    mint: str
    previous_state: str
    next_state: str
    signature: str
    observed_at: float
    reason: str

    def dedupe_key(self) -> tuple[str, str, str, str]:
        return (self.mint, self.next_state, self.signature, self.reason)

    def to_json_row(self) -> dict[str, Any]:
        return {
            "mint": self.mint,
            "previous_state": self.previous_state,
            "next_state": self.next_state,
            "signature": self.signature,
            "observed_at": self.observed_at,
            "reason": self.reason,
        }
