"""Run all candidate registry ingestors and persist merged results."""

from __future__ import annotations

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.dexscreener_ingest import (
    fetch_candidates as fetch_dexscreener_candidates,
)
from research.mtp_research.ingestion.jupiter_recent_ingest import (
    fetch_candidates as fetch_jupiter_candidates,
)
from research.mtp_research.ingestion.raydium_ingest import (
    fetch_candidates as fetch_raydium_candidates,
)


def main() -> None:
    registry = CandidateRegistry()
    candidates = [
        *fetch_dexscreener_candidates(),
        *fetch_jupiter_candidates(),
        *fetch_raydium_candidates(),
    ]

    inserted = 0
    updated = 0
    for candidate in candidates:
        result = registry.upsert(candidate)
        if result == "inserted":
            inserted += 1
        else:
            updated += 1

    total = len(registry.load_all())
    print(f"inserted={inserted}")
    print(f"updated={updated}")
    print(f"total={total}")
    print(f"output_path={registry.path}")


if __name__ == "__main__":
    main()
