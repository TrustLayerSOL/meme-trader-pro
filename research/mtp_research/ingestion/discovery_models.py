"""Models for bounded real candidate discovery runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiscoveryRunConfig:
    source: str
    limit: int = 25
    dry_run: bool = True
    write: bool = False
    include_profiles: bool = True
    include_boosts: bool = True
    include_top_boosts: bool = True
    enrich_pairs: bool = True
    min_liquidity_usd: float | None = None
    allowed_chain_ids: list[str] = field(default_factory=lambda: ["solana"])
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryRunSummary:
    source: str
    dry_run: bool
    write: bool
    raw_items_seen: int = 0
    solana_items_seen: int = 0
    token_addresses_seen: int = 0
    pair_records_seen: int = 0
    candidates_built: int = 0
    candidates_after_filters: int = 0
    candidates_inserted: int = 0
    candidates_updated: int = 0
    skipped_mock_or_invalid: int = 0
    warning_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)
