"""Research dataset row models for joined feature/outcome data."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass
class ResearchDatasetRow:
    row_id: str
    snapshot_id: str
    outcome_id: str
    token_mint: str
    snapshot_ts: int
    window_name: str
    window_seconds: int
    horizon_name: str
    horizon_seconds: int
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
    venue_counts: dict[str, int] = field(default_factory=dict)
    event_type_counts: dict[str, int] = field(default_factory=dict)
    feature_metadata_json: dict[str, Any] = field(default_factory=dict)
    outcome_metadata_json: dict[str, Any] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchDatasetRow":
        return cls(
            row_id=payload["row_id"],
            snapshot_id=payload["snapshot_id"],
            outcome_id=payload["outcome_id"],
            token_mint=payload["token_mint"],
            snapshot_ts=payload["snapshot_ts"],
            window_name=payload["window_name"],
            window_seconds=payload["window_seconds"],
            horizon_name=payload["horizon_name"],
            horizon_seconds=payload["horizon_seconds"],
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
            venue_counts=dict(payload.get("venue_counts", {})),
            event_type_counts=dict(payload.get("event_type_counts", {})),
            feature_metadata_json=dict(payload.get("feature_metadata_json", {})),
            outcome_metadata_json=dict(payload.get("outcome_metadata_json", {})),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


def make_research_row_id(snapshot_id: str, outcome_id: str) -> str:
    digest = sha256(f"{snapshot_id}|{outcome_id}".encode("utf-8")).hexdigest()[:16]
    return f"research-row-{digest}"
