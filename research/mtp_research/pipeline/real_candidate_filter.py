"""Helpers for separating real discovery candidates from mock/test rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate


MOCK_SOURCES = {"mock", "manual_example"}
MOCK_VENUES = {"mock"}


def is_mock_candidate(candidate: LaunchCandidate) -> bool:
    return is_mock_candidate_row(candidate.to_dict())


def is_mock_candidate_row(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata_json")
    metadata = metadata if isinstance(metadata, dict) else {}
    token_mint = str(row.get("token_mint") or "")
    pool_address = str(row.get("pool_address") or "")
    dexscreener_url = str(row.get("dexscreener_url") or "")
    return bool(
        metadata.get("is_mock")
        or metadata.get("example_only")
        or row.get("source") in MOCK_SOURCES
        or row.get("venue") in MOCK_VENUES
        or token_mint.startswith("Mock")
        or pool_address.startswith("Mock")
        or "mock" in dexscreener_url.lower()
    )


def is_real_candidate(candidate: LaunchCandidate) -> bool:
    return not is_mock_candidate(candidate)


def candidate_has_evidence_target(candidate: LaunchCandidate) -> bool:
    return bool(candidate.pool_address or candidate.creator_wallet or candidate.token_mint)


def filter_real_candidates(
    candidates: list[LaunchCandidate],
    require_pool_address: bool = True,
    min_liquidity_usd: float | None = None,
) -> list[LaunchCandidate]:
    filtered: list[LaunchCandidate] = []
    for candidate in candidates:
        if is_mock_candidate(candidate):
            continue
        if require_pool_address and not candidate.pool_address:
            continue
        if min_liquidity_usd is not None and (
            candidate.liquidity_usd is None or candidate.liquidity_usd < min_liquidity_usd
        ):
            continue
        filtered.append(candidate)
    return filtered


def real_token_mints_from_registry(
    registry_path: Path | str | None = None,
    require_pool_address: bool = True,
    min_liquidity_usd: float | None = None,
) -> set[str]:
    registry = CandidateRegistry(registry_path) if registry_path else CandidateRegistry()
    return {
        candidate.token_mint
        for candidate in filter_real_candidates(
            registry.load_all(),
            require_pool_address=require_pool_address,
            min_liquidity_usd=min_liquidity_usd,
        )
    }
