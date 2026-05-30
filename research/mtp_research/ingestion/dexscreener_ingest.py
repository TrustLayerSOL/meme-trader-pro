"""DexScreener ingest placeholders for candidate discovery."""

from __future__ import annotations

from datetime import datetime, timezone

from research.mtp_research.ingestion.models import LaunchCandidate


# TODO: Replace with live DexScreener API calls + pagination + deduping when approved.
def fetch_candidates() -> list[LaunchCandidate]:
    """Return deterministic mock DexScreener candidates for local testing."""

    return [
        LaunchCandidate(
            token_mint="8A1d5p9j7sX8M3V5TqV6mJkY9Xc8L2Kqf9Gzv8a2tW7A",
            source="dexscreener",
            first_seen_ts=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
            venue="dexscreener",
            liquidity_usd=125_000.0,
            dexscreener_url="https://dexscreener.com/solana/mock1",
            metadata_json={
                "is_mock": True,
                "mock_source": "dexscreener",
                "ingest_note": "mock data only",
            },
            status="candidate",
        )
    ]
