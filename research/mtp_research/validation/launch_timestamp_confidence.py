"""Launch timestamp confidence classification for lifecycle research."""

from __future__ import annotations

from typing import Any


VERIFIED_PAIR_CREATION = "verified_pair_creation"
VERIFIED_BONDING_CURVE_CREATION = "verified_bonding_curve_creation"
VERIFIED_MINT_CREATION = "verified_mint_creation"
VERIFIED_FIRST_TRADE = "verified_first_trade"
INFERRED_FIRST_NORMALIZED_EVENT = "inferred_first_normalized_event"
INFERRED_REGISTRY_FIRST_SEEN = "inferred_registry_first_seen"
UNKNOWN = "unknown"

_RANKS = {
    UNKNOWN: 0,
    INFERRED_REGISTRY_FIRST_SEEN: 10,
    INFERRED_FIRST_NORMALIZED_EVENT: 20,
    VERIFIED_FIRST_TRADE: 50,
    VERIFIED_MINT_CREATION: 70,
    VERIFIED_BONDING_CURVE_CREATION: 80,
    VERIFIED_PAIR_CREATION: 90,
}

_VERIFIED = {
    VERIFIED_PAIR_CREATION,
    VERIFIED_BONDING_CURVE_CREATION,
    VERIFIED_MINT_CREATION,
    VERIFIED_FIRST_TRADE,
}


def classify_launch_timestamp_source(row_or_metadata: dict[str, Any] | None) -> str:
    payload = row_or_metadata or {}
    metadata = payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else payload

    explicit = metadata.get("launch_timestamp_source") or metadata.get("launch_timestamp_confidence")
    if explicit in _RANKS:
        return explicit

    quality = metadata.get("launch_timestamp_quality")
    if quality == "first_observed_event_not_verified_pair_creation":
        return INFERRED_FIRST_NORMALIZED_EVENT
    if quality in {"verified_pair_creation", "pair_creation"}:
        return VERIFIED_PAIR_CREATION
    if quality in {"verified_bonding_curve_creation", "bonding_curve_creation"}:
        return VERIFIED_BONDING_CURVE_CREATION
    if quality in {"verified_mint_creation", "mint_creation"}:
        return VERIFIED_MINT_CREATION
    if quality in {"verified_first_trade", "first_trade"}:
        return VERIFIED_FIRST_TRADE

    source = payload.get("source") or metadata.get("source")
    if source == "normalized_event_first_seen":
        return INFERRED_FIRST_NORMALIZED_EVENT
    if source:
        return INFERRED_REGISTRY_FIRST_SEEN
    return UNKNOWN


def confidence_rank(source: str) -> int:
    return _RANKS.get(source, 0)


def is_verified_launch_timestamp(source: str) -> bool:
    return source in _VERIFIED
