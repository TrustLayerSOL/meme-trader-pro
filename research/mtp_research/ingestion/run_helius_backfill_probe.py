"""CLI probe for Helius historical signature discovery."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.helius_models import HeliusBackfillRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Helius getSignaturesForAddress.")
    parser.add_argument("address")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--include-failed", action="store_true")
    args = parser.parse_args()

    try:
        adapter = HeliusHistoricalAdapter.from_env()
    except ValueError as exc:
        print(str(exc))
        return 1

    result = adapter.fetch_signatures_for_address(
        HeliusBackfillRequest(
            address=args.address,
            limit=args.limit,
            include_failed=args.include_failed,
        )
    )

    first_signature = result.records[0].signature if result.records else None
    last_signature = result.records[-1].signature if result.records else None

    print(f"address={args.address}")
    print(f"records={len(result.records)}")
    print(f"first_signature={first_signature}")
    print(f"last_signature={last_signature}")
    print(f"next_before={result.next_before}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
