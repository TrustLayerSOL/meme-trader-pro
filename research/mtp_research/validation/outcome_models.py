"""Outcome label models for v3 validation datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class OutcomeHorizon:
    name: str
    seconds: int


@dataclass
class TokenPricePoint:
    token_mint: str
    ts: int
    price_quote: float
    source_event_id: str | None = None
    source_signature: str | None = None
    venue: str | None = None
    confidence: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomeLabel:
    outcome_id: str
    snapshot_id: str
    token_mint: str
    snapshot_ts: int
    horizon_name: str
    horizon_seconds: int
    entry_price: float | None = None
    entry_price_ts: int | None = None
    entry_price_source: str | None = None
    end_price: float | None = None
    end_price_ts: int | None = None
    forward_return: float | None = None
    max_runup: float | None = None
    max_drawdown: float | None = None
    price_points_count: int = 0
    future_event_count: int = 0
    future_possible_buy_count: int = 0
    future_possible_sell_count: int = 0
    future_token_accumulation_count: int = 0
    future_token_distribution_count: int = 0
    future_unique_actor_count: int = 0
    future_quote_volume: float = 0.0
    future_base_volume: float = 0.0
    survived_horizon: bool | None = None
    rug_like_drop: bool | None = None
    no_future_liquidity: bool = False
    label_quality: str = "unknown"
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "snapshot_id": self.snapshot_id,
            "token_mint": self.token_mint,
            "snapshot_ts": self.snapshot_ts,
            "horizon_name": self.horizon_name,
            "horizon_seconds": self.horizon_seconds,
            "entry_price": self.entry_price,
            "entry_price_ts": self.entry_price_ts,
            "entry_price_source": self.entry_price_source,
            "end_price": self.end_price,
            "end_price_ts": self.end_price_ts,
            "forward_return": self.forward_return,
            "max_runup": self.max_runup,
            "max_drawdown": self.max_drawdown,
            "price_points_count": self.price_points_count,
            "future_event_count": self.future_event_count,
            "future_possible_buy_count": self.future_possible_buy_count,
            "future_possible_sell_count": self.future_possible_sell_count,
            "future_token_accumulation_count": self.future_token_accumulation_count,
            "future_token_distribution_count": self.future_token_distribution_count,
            "future_unique_actor_count": self.future_unique_actor_count,
            "future_quote_volume": self.future_quote_volume,
            "future_base_volume": self.future_base_volume,
            "survived_horizon": self.survived_horizon,
            "rug_like_drop": self.rug_like_drop,
            "no_future_liquidity": self.no_future_liquidity,
            "label_quality": self.label_quality,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeLabel":
        return cls(
            outcome_id=payload["outcome_id"],
            snapshot_id=payload["snapshot_id"],
            token_mint=payload["token_mint"],
            snapshot_ts=payload["snapshot_ts"],
            horizon_name=payload["horizon_name"],
            horizon_seconds=payload["horizon_seconds"],
            entry_price=payload.get("entry_price"),
            entry_price_ts=payload.get("entry_price_ts"),
            entry_price_source=payload.get("entry_price_source"),
            end_price=payload.get("end_price"),
            end_price_ts=payload.get("end_price_ts"),
            forward_return=payload.get("forward_return"),
            max_runup=payload.get("max_runup"),
            max_drawdown=payload.get("max_drawdown"),
            price_points_count=payload.get("price_points_count", 0),
            future_event_count=payload.get("future_event_count", 0),
            future_possible_buy_count=payload.get("future_possible_buy_count", 0),
            future_possible_sell_count=payload.get("future_possible_sell_count", 0),
            future_token_accumulation_count=payload.get("future_token_accumulation_count", 0),
            future_token_distribution_count=payload.get("future_token_distribution_count", 0),
            future_unique_actor_count=payload.get("future_unique_actor_count", 0),
            future_quote_volume=payload.get("future_quote_volume", 0.0),
            future_base_volume=payload.get("future_base_volume", 0.0),
            survived_horizon=payload.get("survived_horizon"),
            rug_like_drop=payload.get("rug_like_drop"),
            no_future_liquidity=payload.get("no_future_liquidity", False),
            label_quality=payload.get("label_quality", "unknown"),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


def make_outcome_id(snapshot_id: str, horizon_name: str) -> str:
    payload = f"{snapshot_id}|{horizon_name}"
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"outcome-{digest}"
