"""Raydium mock ingest placeholders for candidate discovery."""

from __future__ import annotations

from datetime import datetime, timezone

from research.mtp_research.ingestion.models import LaunchCandidate


def fetch_candidates() -> list[LaunchCandidate]:
    """This returns deterministic mock data for tests only. Real discovery lives in dexscreener_real_ingest.py."""

    return [
        LaunchCandidate(
            token_mint="9B2c7s1vL8h4Q9XkF7mN8sE6hC2QmV5Lq7Rj7y5Hn8rV",
            source="raydium",
            first_seen_ts=datetime(2026, 5, 30, 12, 15, 0, tzinfo=timezone.utc),
            venue="raydium",
            pool_address="4b5jRj8D8WjX6x1QmZ8L2bR4Kf3jvQ9pDq3X8kW3nYz8",
            raydium_seen=True,
            quote_mint="So11111111111111111111111111111111111111112",
            metadata_json={
                "is_mock": True,
                "mock_source": "raydium",
                "pool_discovery_hint": "mock-raydium-pool-1",
            },
        )
    ]
