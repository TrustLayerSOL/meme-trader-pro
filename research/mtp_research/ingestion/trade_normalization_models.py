"""Models for conservative trade-event normalization v0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KLWjFyWtUFZVzkQKqM"

KNOWN_QUOTE_MINTS = {WSOL_MINT, USDC_MINT, USDT_MINT}


@dataclass(frozen=True)
class QuoteAsset:
    mint: str
    symbol: str
    decimals: int | None = None


@dataclass
class TradeFlow:
    owner: str | None
    base_mint: str | None
    quote_mint: str | None
    base_delta: float | None
    quote_delta: float | None
    inferred_side: str | None
    confidence: float
    reasons: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeNormalizationResult:
    signature: str
    slot: int | None
    block_time: int | None
    venue: str | None
    flows: list[TradeFlow]
    emitted_events: int
    metadata_json: dict[str, Any] = field(default_factory=dict)


def is_known_quote_mint(mint: str) -> bool:
    return mint in KNOWN_QUOTE_MINTS
