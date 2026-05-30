"""Feature snapshot models for v3 backtest inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class FeatureWindow:
    name: str
    seconds: int


@dataclass
class FeatureSnapshot:
    snapshot_id: str
    token_mint: str
    snapshot_ts: int
    window_name: str
    window_seconds: int
    age_sec: int | None = None
    venue: str | None = None
    event_count: int = 0
    possible_buy_count: int = 0
    possible_sell_count: int = 0
    token_accumulation_count: int = 0
    token_distribution_count: int = 0
    unique_actor_count: int = 0
    base_volume: float = 0.0
    quote_volume: float = 0.0
    net_base_flow: float = 0.0
    net_quote_flow: float = 0.0
    buy_sell_imbalance: float | None = None
    confidence_weighted_buy_flow: float = 0.0
    confidence_weighted_sell_flow: float = 0.0
    confidence_weighted_net_flow: float = 0.0
    avg_event_confidence: float | None = None
    max_event_confidence: float | None = None
    venue_counts: dict[str, int] = field(default_factory=dict)
    event_type_counts: dict[str, int] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "token_mint": self.token_mint,
            "snapshot_ts": self.snapshot_ts,
            "window_name": self.window_name,
            "window_seconds": self.window_seconds,
            "age_sec": self.age_sec,
            "venue": self.venue,
            "event_count": self.event_count,
            "possible_buy_count": self.possible_buy_count,
            "possible_sell_count": self.possible_sell_count,
            "token_accumulation_count": self.token_accumulation_count,
            "token_distribution_count": self.token_distribution_count,
            "unique_actor_count": self.unique_actor_count,
            "base_volume": self.base_volume,
            "quote_volume": self.quote_volume,
            "net_base_flow": self.net_base_flow,
            "net_quote_flow": self.net_quote_flow,
            "buy_sell_imbalance": self.buy_sell_imbalance,
            "confidence_weighted_buy_flow": self.confidence_weighted_buy_flow,
            "confidence_weighted_sell_flow": self.confidence_weighted_sell_flow,
            "confidence_weighted_net_flow": self.confidence_weighted_net_flow,
            "avg_event_confidence": self.avg_event_confidence,
            "max_event_confidence": self.max_event_confidence,
            "venue_counts": self.venue_counts,
            "event_type_counts": self.event_type_counts,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureSnapshot":
        return cls(
            snapshot_id=payload["snapshot_id"],
            token_mint=payload["token_mint"],
            snapshot_ts=payload["snapshot_ts"],
            window_name=payload["window_name"],
            window_seconds=payload["window_seconds"],
            age_sec=payload.get("age_sec"),
            venue=payload.get("venue"),
            event_count=payload.get("event_count", 0),
            possible_buy_count=payload.get("possible_buy_count", 0),
            possible_sell_count=payload.get("possible_sell_count", 0),
            token_accumulation_count=payload.get("token_accumulation_count", 0),
            token_distribution_count=payload.get("token_distribution_count", 0),
            unique_actor_count=payload.get("unique_actor_count", 0),
            base_volume=payload.get("base_volume", 0.0),
            quote_volume=payload.get("quote_volume", 0.0),
            net_base_flow=payload.get("net_base_flow", 0.0),
            net_quote_flow=payload.get("net_quote_flow", 0.0),
            buy_sell_imbalance=payload.get("buy_sell_imbalance"),
            confidence_weighted_buy_flow=payload.get("confidence_weighted_buy_flow", 0.0),
            confidence_weighted_sell_flow=payload.get("confidence_weighted_sell_flow", 0.0),
            confidence_weighted_net_flow=payload.get("confidence_weighted_net_flow", 0.0),
            avg_event_confidence=payload.get("avg_event_confidence"),
            max_event_confidence=payload.get("max_event_confidence"),
            venue_counts=dict(payload.get("venue_counts", {})),
            event_type_counts=dict(payload.get("event_type_counts", {})),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


def make_snapshot_id(token_mint: str, snapshot_ts: int, window_name: str) -> str:
    payload = f"{token_mint}|{snapshot_ts}|{window_name}"
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"feature_snapshot-{digest}"
