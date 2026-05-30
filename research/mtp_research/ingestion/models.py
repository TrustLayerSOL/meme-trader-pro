"""Core models for v3 candidate registry ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LaunchCandidate:
    """Represents a newly discovered meme-token launch candidate."""

    token_mint: str
    source: str
    first_seen_ts: datetime
    venue: str | None = None
    first_tradeable_ts: datetime | None = None
    pool_address: str | None = None
    creator_wallet: str | None = None
    quote_mint: str | None = None
    liquidity_usd: float | None = None
    market_cap: float | None = None
    dexscreener_url: str | None = None
    jupiter_recent_seen: bool = False
    raydium_seen: bool = False
    pump_seen: bool = False
    status: str = "candidate"
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_mint": self.token_mint,
            "source": self.source,
            "first_seen_ts": self.first_seen_ts.isoformat(),
            "venue": self.venue,
            "first_tradeable_ts": self.first_tradeable_ts.isoformat() if self.first_tradeable_ts else None,
            "pool_address": self.pool_address,
            "creator_wallet": self.creator_wallet,
            "quote_mint": self.quote_mint,
            "liquidity_usd": self.liquidity_usd,
            "market_cap": self.market_cap,
            "dexscreener_url": self.dexscreener_url,
            "jupiter_recent_seen": self.jupiter_recent_seen,
            "raydium_seen": self.raydium_seen,
            "pump_seen": self.pump_seen,
            "status": self.status,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LaunchCandidate":
        return cls(
            token_mint=payload["token_mint"],
            source=payload["source"],
            first_seen_ts=datetime.fromisoformat(payload["first_seen_ts"]),
            venue=payload.get("venue"),
            first_tradeable_ts=(
                datetime.fromisoformat(payload["first_tradeable_ts"])
                if payload.get("first_tradeable_ts")
                else None
            ),
            pool_address=payload.get("pool_address"),
            creator_wallet=payload.get("creator_wallet"),
            quote_mint=payload.get("quote_mint"),
            liquidity_usd=payload.get("liquidity_usd"),
            market_cap=payload.get("market_cap"),
            dexscreener_url=payload.get("dexscreener_url"),
            jupiter_recent_seen=bool(payload.get("jupiter_recent_seen", False)),
            raydium_seen=bool(payload.get("raydium_seen", False)),
            pump_seen=bool(payload.get("pump_seen", False)),
            status=payload.get("status", "candidate"),
            metadata_json=dict(payload.get("metadata_json", {})),
        )

    def _prefer_newer(self, older_value: Any, newer_value: Any) -> Any:
        return newer_value if newer_value is not None else older_value

    def merge_with(self, newer: "LaunchCandidate") -> "LaunchCandidate":
        """Merge a newer candidate record into this one."""

        if self.token_mint != newer.token_mint:
            raise ValueError("Can only merge candidates for the same token_mint")

        merged_metadata = dict(self.metadata_json)
        merged_metadata.update(newer.metadata_json)
        discovered_sources = set(
            merged_metadata.get("discovered_sources", [])
        )
        discovered_sources.add(self.source)
        discovered_sources.add(newer.source)
        merged_metadata["discovered_sources"] = sorted(discovered_sources)

        merged_status = newer.status or self.status

        return LaunchCandidate(
            token_mint=self.token_mint,
            source=self.source,
            first_seen_ts=min(self.first_seen_ts, newer.first_seen_ts),
            venue=self._prefer_newer(self.venue, newer.venue),
            first_tradeable_ts=self._prefer_newer(
                self.first_tradeable_ts,
                newer.first_tradeable_ts,
            ),
            pool_address=self._prefer_newer(self.pool_address, newer.pool_address),
            creator_wallet=self._prefer_newer(self.creator_wallet, newer.creator_wallet),
            quote_mint=self._prefer_newer(self.quote_mint, newer.quote_mint),
            liquidity_usd=self._prefer_newer(self.liquidity_usd, newer.liquidity_usd),
            market_cap=self._prefer_newer(self.market_cap, newer.market_cap),
            dexscreener_url=self._prefer_newer(self.dexscreener_url, newer.dexscreener_url),
            jupiter_recent_seen=self.jupiter_recent_seen or newer.jupiter_recent_seen,
            raydium_seen=self.raydium_seen or newer.raydium_seen,
            pump_seen=self.pump_seen or newer.pump_seen,
            status=merged_status,
            metadata_json=merged_metadata,
        )
