"""Models for Helius historical backfill discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HeliusBackfillRequest:
    """A bounded historical-signature discovery request."""

    address: str
    token_mint: str | None = None
    role: str = "unknown"
    start_time: int | None = None
    end_time: int | None = None
    before: str | None = None
    until: str | None = None
    limit: int = 100
    include_failed: bool = False
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class HeliusTransactionRecord:
    """A normalized transaction-signature row from Helius RPC."""

    signature: str
    slot: int | None
    block_time: int | None
    success: bool | None
    raw_json: dict[str, Any]


@dataclass
class HeliusBackfillResult:
    """Result packet for a historical backfill discovery call."""

    request: HeliusBackfillRequest
    records: list[HeliusTransactionRecord]
    next_before: str | None
    metadata_json: dict[str, Any] = field(default_factory=dict)
