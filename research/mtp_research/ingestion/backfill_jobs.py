"""Backfill target and result models for v3 historical ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


def make_target_id(address: str, role: str, token_mint: str | None = None) -> str:
    """Build a deterministic target id without exposing raw addresses as filenames."""

    normalized = "|".join(
        [
            address.strip(),
            role.strip() or "unknown",
            (token_mint or "").strip(),
        ]
    )
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{role or 'unknown'}-{digest}"


@dataclass
class BackfillTarget:
    """A bounded historical backfill target."""

    target_id: str
    address: str
    role: str
    token_mint: str | None = None
    source: str = "manual"
    status: str = "pending"
    priority: int = 100
    cursor_before: str | None = None
    discovered_signatures: int = 0
    fetched_transactions: int = 0
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackfillJobResult:
    """Summary of one target backfill run."""

    target: BackfillTarget
    signatures_seen: int
    transactions_fetched: int
    transactions_inserted: int
    transactions_updated: int
    next_before: str | None
    status: str
    metadata_json: dict[str, Any] = field(default_factory=dict)
