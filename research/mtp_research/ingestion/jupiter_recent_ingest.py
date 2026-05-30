"""Jupiter recent-token ingest placeholders for candidate discovery."""

from __future__ import annotations

from datetime import datetime, timezone

from research.mtp_research.ingestion.models import LaunchCandidate


# TODO: Replace with Jupiter recent-token endpoint calls (rate-limited + auth) later.
def fetch_candidates() -> list[LaunchCandidate]:
    """Return deterministic mock Jupiter candidate updates for local testing."""

    return [
        LaunchCandidate(
            token_mint="8A1d5p9j7sX8M3V5TqV6mJkY9Xc8L2Kqf9Gzv8a2tW7A",
            source="jupiter_recent",
            first_seen_ts=datetime(2026, 5, 30, 12, 5, 0, tzinfo=timezone.utc),
            jupiter_recent_seen=True,
            quote_mint="So11111111111111111111111111111111111111112",
            metadata_json={
                "is_mock": True,
                "mock_source": "jupiter_recent",
                "jupiter_route_hint": "mock-route-1",
            },
        ),
        LaunchCandidate(
            token_mint="9B2c7s1vL8h4Q9XkF7mN8sE6hC2QmV5Lq7Rj7y5Hn8rV",
            source="jupiter_recent",
            first_seen_ts=datetime(2026, 5, 30, 12, 10, 0, tzinfo=timezone.utc),
            jupiter_recent_seen=True,
            quote_mint="So11111111111111111111111111111111111111112",
            metadata_json={
                "is_mock": True,
                "mock_source": "jupiter_recent",
                "jupiter_route_hint": "mock-route-2",
            },
        ),
    ]
