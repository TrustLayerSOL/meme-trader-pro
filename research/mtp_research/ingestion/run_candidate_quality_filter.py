"""CLI for offline candidate quality filtering."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter local candidates for evidence quality.")
    parser.add_argument("--registry-path")
    parser.add_argument("--exclude-mock", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-pool-address", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--source")
    parser.add_argument("--venue")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    registry = CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry()
    candidates = registry.load_all()
    real_candidates = [candidate for candidate in candidates if not is_mock_candidate(candidate)]
    mock_candidates = [candidate for candidate in candidates if is_mock_candidate(candidate)]
    passing = filter_candidates(
        candidates,
        exclude_mock=args.exclude_mock,
        require_pool_address=args.require_pool_address,
        min_liquidity_usd=args.min_liquidity_usd,
        source=args.source,
        venue=args.venue,
    )
    if args.limit is not None:
        passing = passing[: args.limit]

    print(f"total_candidates={len(candidates)}")
    print(f"real_candidates={len(real_candidates)}")
    print(f"mock_candidates={len(mock_candidates)}")
    print(f"candidates_with_pool_address={sum(1 for candidate in candidates if candidate.pool_address)}")
    print(f"candidates_with_creator_wallet={sum(1 for candidate in candidates if candidate.creator_wallet)}")
    print(f"candidates_passing_filters={len(passing)}")
    for candidate in passing[:10]:
        print(
            "candidate "
            f"token_mint={candidate.token_mint} "
            f"source={candidate.source} "
            f"venue={candidate.venue} "
            f"pool_address={candidate.pool_address} "
            f"liquidity_usd={candidate.liquidity_usd}"
        )
    print("network_calls=0")
    return 0


def filter_candidates(
    candidates: list[LaunchCandidate],
    exclude_mock: bool = True,
    require_pool_address: bool = True,
    min_liquidity_usd: float | None = None,
    source: str | None = None,
    venue: str | None = None,
) -> list[LaunchCandidate]:
    filtered: list[LaunchCandidate] = []
    for candidate in candidates:
        if exclude_mock and is_mock_candidate(candidate):
            continue
        if require_pool_address and not candidate.pool_address:
            continue
        if min_liquidity_usd is not None and (
            candidate.liquidity_usd is None or candidate.liquidity_usd < min_liquidity_usd
        ):
            continue
        if source and candidate.source != source:
            continue
        if venue and candidate.venue != venue:
            continue
        filtered.append(candidate)
    return filtered


def is_mock_candidate(candidate: LaunchCandidate) -> bool:
    metadata = candidate.metadata_json or {}
    return bool(
        metadata.get("is_mock")
        or metadata.get("example_only")
        or candidate.source in {"mock", "manual_example"}
        or candidate.venue in {"mock", "manual_example"}
    )


if __name__ == "__main__":
    raise SystemExit(main())
