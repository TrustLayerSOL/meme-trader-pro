"""Real bounded DexScreener candidate discovery for v3 research."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.discovery_models import (
    DiscoveryRunConfig,
    DiscoveryRunSummary,
)
from research.mtp_research.ingestion.http_client import SimpleJsonHttpClient
from research.mtp_research.ingestion.models import LaunchCandidate


KNOWN_QUOTE_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KLWjFyWtUFZVzkQKqM",
}


class DexScreenerRealIngestor:
    """Discover real Solana candidates from public DexScreener endpoints."""

    BASE_URL = "https://api.dexscreener.com"

    def __init__(self, http_client: SimpleJsonHttpClient | None = None):
        self.http_client = http_client or SimpleJsonHttpClient()

    def fetch_latest_token_profiles(self, limit: int = 25) -> list[dict[str, Any]]:
        return _as_rows(self.http_client.get_json(f"{self.BASE_URL}/token-profiles/latest/v1"))[:limit]

    def fetch_latest_boosts(self, limit: int = 25) -> list[dict[str, Any]]:
        return _as_rows(self.http_client.get_json(f"{self.BASE_URL}/token-boosts/latest/v1"))[:limit]

    def fetch_top_boosts(self, limit: int = 25) -> list[dict[str, Any]]:
        return _as_rows(self.http_client.get_json(f"{self.BASE_URL}/token-boosts/top/v1"))[:limit]

    def fetch_token_pairs(self, token_address: str) -> list[dict[str, Any]]:
        return _as_rows(self.http_client.get_json(f"{self.BASE_URL}/token-pairs/v1/solana/{token_address}"))

    def fetch_tokens(self, token_addresses: list[str]) -> list[dict[str, Any]]:
        if not token_addresses:
            return []
        joined = ",".join(token_addresses)
        return _as_rows(self.http_client.get_json(f"{self.BASE_URL}/tokens/v1/solana/{joined}"))

    def discover_token_addresses(self, config: DiscoveryRunConfig) -> list[str]:
        rows: list[dict[str, Any]] = []
        if config.include_profiles:
            rows.extend(self.fetch_latest_token_profiles(config.limit))
        if config.include_boosts:
            rows.extend(self.fetch_latest_boosts(config.limit))
        if config.include_top_boosts:
            rows.extend(self.fetch_top_boosts(config.limit))

        addresses: list[str] = []
        seen: set[str] = set()
        allowed = set(config.allowed_chain_ids)
        for row in rows:
            if str(row.get("chainId")) not in allowed:
                continue
            address = row.get("tokenAddress")
            if not address or address in seen:
                continue
            seen.add(address)
            addresses.append(str(address))
            if len(addresses) >= config.limit:
                break
        return addresses

    def pair_to_candidate(
        self,
        pair: dict[str, Any],
        source_hint: str = "dexscreener",
    ) -> LaunchCandidate | None:
        if pair.get("chainId") != "solana":
            return None
        pair_address = pair.get("pairAddress")
        if not pair_address:
            return None

        base = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        quote = pair.get("quoteToken") if isinstance(pair.get("quoteToken"), dict) else {}
        base_address = base.get("address")
        quote_address = quote.get("address")
        if not base_address and not quote_address:
            return None

        if base_address in KNOWN_QUOTE_MINTS and quote_address:
            token_mint = quote_address
            quote_mint = base_address
        else:
            token_mint = base_address
            quote_mint = quote_address
        if not token_mint or str(token_mint).lower().startswith(("mock", "example")):
            return None

        liquidity_usd = _nested_float(pair, "liquidity", "usd")
        market_cap = _float_or_none(pair.get("marketCap"))
        if market_cap is None:
            market_cap = _float_or_none(pair.get("fdv"))
        pair_created_at = pair.get("pairCreatedAt")

        return LaunchCandidate(
            token_mint=str(token_mint),
            source="dexscreener_real",
            first_seen_ts=datetime.now(timezone.utc),
            venue=pair.get("dexId") or source_hint,
            first_tradeable_ts=_millis_to_datetime(pair_created_at),
            pool_address=str(pair_address),
            quote_mint=str(quote_mint) if quote_mint else None,
            liquidity_usd=liquidity_usd,
            market_cap=market_cap,
            dexscreener_url=pair.get("url"),
            metadata_json={
                "is_mock": False,
                "discovery_source": "dexscreener_real",
                "dex_id": pair.get("dexId"),
                "pair_address": pair_address,
                "pair_created_at": pair_created_at,
                "price_usd": pair.get("priceUsd"),
                "volume": pair.get("volume"),
                "txns": pair.get("txns"),
                "boosts": pair.get("boosts"),
                "raw_pair_subset": {
                    "chainId": pair.get("chainId"),
                    "dexId": pair.get("dexId"),
                    "url": pair.get("url"),
                    "pairAddress": pair_address,
                    "baseToken": base,
                    "quoteToken": quote,
                    "liquidity": pair.get("liquidity"),
                    "marketCap": pair.get("marketCap"),
                    "fdv": pair.get("fdv"),
                },
            },
        )

    def build_candidates(self, config: DiscoveryRunConfig) -> list[LaunchCandidate]:
        candidates: list[LaunchCandidate] = []
        if not config.enrich_pairs:
            return candidates

        for token_address in self.discover_token_addresses(config):
            pairs = self.fetch_token_pairs(token_address)
            best_pair = self._best_solana_pair(pairs)
            if not best_pair:
                continue
            candidate = self.pair_to_candidate(best_pair)
            if candidate is None:
                continue
            if config.min_liquidity_usd is not None and (
                candidate.liquidity_usd is None or candidate.liquidity_usd < config.min_liquidity_usd
            ):
                continue
            candidates.append(candidate)
        return candidates

    def run_discovery(
        self,
        config: DiscoveryRunConfig,
        registry: CandidateRegistry | None = None,
    ) -> DiscoveryRunSummary:
        raw_rows = self._discovery_rows(config)
        token_addresses = self._token_addresses_from_rows(raw_rows, config)
        candidates = self.build_candidates(config)
        summary = DiscoveryRunSummary(
            source=config.source,
            dry_run=config.dry_run,
            write=config.write,
            raw_items_seen=len(raw_rows),
            solana_items_seen=sum(1 for row in raw_rows if row.get("chainId") in config.allowed_chain_ids),
            token_addresses_seen=len(token_addresses),
            pair_records_seen=len(candidates),
            candidates_built=len(candidates),
            candidates_after_filters=len(candidates),
            metadata_json={"candidate_summaries": [candidate.to_dict() for candidate in candidates[:5]]},
        )
        if config.write and not config.dry_run and registry is not None:
            for candidate in candidates:
                result = registry.upsert(candidate)
                summary.candidates_inserted += 1 if result == "inserted" else 0
                summary.candidates_updated += 1 if result == "updated" else 0
        elif config.write and config.dry_run:
            summary.warning_flags.append("dry_run_no_write")
        return summary

    def _discovery_rows(self, config: DiscoveryRunConfig) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if config.include_profiles:
            rows.extend(self.fetch_latest_token_profiles(config.limit))
        if config.include_boosts:
            rows.extend(self.fetch_latest_boosts(config.limit))
        if config.include_top_boosts:
            rows.extend(self.fetch_top_boosts(config.limit))
        return rows

    def _token_addresses_from_rows(
        self,
        rows: list[dict[str, Any]],
        config: DiscoveryRunConfig,
    ) -> list[str]:
        addresses: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if row.get("chainId") not in config.allowed_chain_ids:
                continue
            address = row.get("tokenAddress")
            if not address or address in seen:
                continue
            seen.add(address)
            addresses.append(str(address))
            if len(addresses) >= config.limit:
                break
        return addresses

    def _best_solana_pair(self, pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
        solana_pairs = [pair for pair in pairs if pair.get("chainId") == "solana" and pair.get("pairAddress")]
        if not solana_pairs:
            return None
        return max(solana_pairs, key=lambda pair: _nested_float(pair, "liquidity", "usd") or 0.0)


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("pairs", "tokens", "items", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _nested_float(row: dict[str, Any], parent: str, child: str) -> float | None:
    nested = row.get(parent)
    if not isinstance(nested, dict):
        return None
    return _float_or_none(nested.get(child))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _millis_to_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
