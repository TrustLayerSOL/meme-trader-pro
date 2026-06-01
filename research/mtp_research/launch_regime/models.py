"""Models for launch-relative early lifecycle research artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class LaunchRegimeCandidate:
    launch_id: str
    token_mint: str
    launch_ts: int
    launch_time_utc: str
    launch_weekday: str
    launch_hour_local: int
    launch_minute_local: int
    launch_day_of_week: int
    launch_is_weekend: bool
    launch_regime: str
    source: str
    pool_address: str | None = None
    venue: str | None = None
    liquidity_usd: float | None = None
    market_cap: float | None = None
    launch_timestamp_source: str = "unknown"
    launch_timestamp_confidence: int = 0
    launch_timestamp_verified: bool = False
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "launch_id": self.launch_id,
            "token_mint": self.token_mint,
            "launch_ts": self.launch_ts,
            "launch_time_utc": self.launch_time_utc,
            "launch_weekday": self.launch_weekday,
            "launch_hour_local": self.launch_hour_local,
            "launch_minute_local": self.launch_minute_local,
            "launch_day_of_week": self.launch_day_of_week,
            "launch_is_weekend": self.launch_is_weekend,
            "launch_regime": self.launch_regime,
            "source": self.source,
            "pool_address": self.pool_address,
            "venue": self.venue,
            "liquidity_usd": self.liquidity_usd,
            "market_cap": self.market_cap,
            "launch_timestamp_source": self.launch_timestamp_source,
            "launch_timestamp_confidence": self.launch_timestamp_confidence,
            "launch_timestamp_verified": self.launch_timestamp_verified,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LaunchRegimeCandidate":
        return cls(
            launch_id=payload["launch_id"],
            token_mint=payload["token_mint"],
            launch_ts=int(payload["launch_ts"]),
            launch_time_utc=payload["launch_time_utc"],
            launch_weekday=payload["launch_weekday"],
            launch_hour_local=int(payload["launch_hour_local"]),
            launch_minute_local=int(payload["launch_minute_local"]),
            launch_day_of_week=int(payload["launch_day_of_week"]),
            launch_is_weekend=bool(payload["launch_is_weekend"]),
            launch_regime=payload["launch_regime"],
            source=payload["source"],
            pool_address=payload.get("pool_address"),
            venue=payload.get("venue"),
            liquidity_usd=payload.get("liquidity_usd"),
            market_cap=payload.get("market_cap"),
            launch_timestamp_source=payload.get("launch_timestamp_source", "unknown"),
            launch_timestamp_confidence=int(payload.get("launch_timestamp_confidence", 0)),
            launch_timestamp_verified=bool(payload.get("launch_timestamp_verified", False)),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


@dataclass
class LaunchFeatureSnapshot:
    snapshot_id: str
    launch_id: str
    token_mint: str
    pool_address: str | None
    venue: str | None
    launch_regime: str
    launch_ts: int
    snapshot_ts: int
    launch_age_seconds: int
    launch_weekday: str
    launch_hour_local: int
    launch_minute_local: int
    launch_day_of_week: int
    launch_is_weekend: bool
    launch_timestamp_source: str = "unknown"
    launch_timestamp_confidence: int = 0
    launch_timestamp_verified: bool = False
    buy_count: int = 0
    sell_count: int = 0
    buy_sell_imbalance: int = 0
    unique_actors: int = 0
    active_wallets: int = 0
    confidence_weighted_net_flow: float = 0.0
    price_change_since_launch: float | None = None
    tx_count: int = 0
    liquidity_proxy: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class LaunchOutcomeLabel:
    outcome_id: str
    launch_id: str
    token_mint: str
    pool_address: str | None
    venue: str | None
    launch_regime: str
    launch_ts: int
    launch_weekday: str
    launch_hour_local: int
    launch_minute_local: int
    launch_day_of_week: int
    launch_is_weekend: bool
    launch_timestamp_source: str = "unknown"
    launch_timestamp_confidence: int = 0
    launch_timestamp_verified: bool = False
    returns: dict[str, float | None] = field(default_factory=dict)
    runups: dict[str, float | None] = field(default_factory=dict)
    drawdowns: dict[str, float | None] = field(default_factory=dict)
    survived_10m: bool = False
    survived_30m: bool = False
    survived_60m: bool = False
    survived_120m: bool = False
    has_activity_at_or_after_120m: bool = False
    has_price_at_120m: bool = False
    has_liquidity_proxy_at_120m: bool = False
    price_available_120m: bool = False
    liquidity_survival_120m: bool = False
    lifecycle_observed_to_120m: bool = False
    survival_label_quality: str = "unknown"
    no_future_liquidity: bool = True
    died_within_10m: bool = True
    died_within_30m: bool = True
    died_within_60m: bool = True
    died_within_120m: bool = True
    market_cap_available: bool = False
    market_cap_source: str | None = None
    market_cap_missing_reason: str | None = None
    threshold_outcomes_usable: bool = False
    ever_hit_15k: bool | None = None
    ever_hit_35k: bool | None = None
    ever_hit_50k: bool | None = None
    ever_hit_100k: bool | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def make_launch_id(token_mint: str, launch_ts: int) -> str:
    digest = sha256(f"{token_mint}|{launch_ts}".encode("utf-8")).hexdigest()[:16]
    return f"launch-{digest}"


def make_snapshot_id(launch_id: str, launch_age_seconds: int) -> str:
    digest = sha256(f"{launch_id}|{launch_age_seconds}".encode("utf-8")).hexdigest()[:16]
    return f"launch-snapshot-{digest}"


def make_outcome_id(launch_id: str) -> str:
    digest = sha256(launch_id.encode("utf-8")).hexdigest()[:16]
    return f"launch-outcome-{digest}"


def utc_iso_from_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
