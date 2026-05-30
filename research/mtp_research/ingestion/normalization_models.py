"""Early normalized event models for replay-safe research."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


def make_event_id(signature: str, event_type: str, index: int = 0) -> str:
    payload = f"{signature}|{event_type}|{index}"
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{event_type}-{digest}"


@dataclass
class NormalizedEvent:
    """A normalized event derived from raw transaction data."""

    event_id: str
    signature: str
    slot: int | None
    block_time: int | None
    event_type: str
    token_mint: str | None = None
    venue: str | None = None
    actor: str | None = None
    side: str | None = None
    base_qty: float | None = None
    quote_qty: float | None = None
    price_quote: float | None = None
    source: str = "raw_transaction_store"
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "signature": self.signature,
            "slot": self.slot,
            "block_time": self.block_time,
            "event_type": self.event_type,
            "token_mint": self.token_mint,
            "venue": self.venue,
            "actor": self.actor,
            "side": self.side,
            "base_qty": self.base_qty,
            "quote_qty": self.quote_qty,
            "price_quote": self.price_quote,
            "source": self.source,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NormalizedEvent":
        return cls(
            event_id=payload["event_id"],
            signature=payload["signature"],
            slot=payload.get("slot"),
            block_time=payload.get("block_time"),
            event_type=payload["event_type"],
            token_mint=payload.get("token_mint"),
            venue=payload.get("venue"),
            actor=payload.get("actor"),
            side=payload.get("side"),
            base_qty=payload.get("base_qty"),
            quote_qty=payload.get("quote_qty"),
            price_quote=payload.get("price_quote"),
            source=payload.get("source", "raw_transaction_store"),
            metadata_json=dict(payload.get("metadata_json", {})),
        )
