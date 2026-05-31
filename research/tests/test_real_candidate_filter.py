from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.real_candidate_filter import (
    candidate_has_evidence_target,
    filter_real_candidates,
    is_mock_candidate,
    is_mock_candidate_row,
    real_token_mints_from_registry,
)


def _candidate(**kwargs) -> LaunchCandidate:
    payload = {
        "token_mint": "real-mint",
        "source": "dexscreener_real",
        "first_seen_ts": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "pool_address": "real-pool",
        "liquidity_usd": 20_000,
        "metadata_json": {"is_mock": False},
    }
    payload.update(kwargs)
    return LaunchCandidate(**payload)


def test_mock_candidate_detection_works() -> None:
    assert is_mock_candidate(_candidate(metadata_json={"is_mock": True}))
    assert is_mock_candidate(_candidate(token_mint="MockMint111", metadata_json={}))
    assert is_mock_candidate(_candidate(dexscreener_url="https://dexscreener.com/solana/mock1", metadata_json={}))
    assert is_mock_candidate_row({"source": "manual_example", "metadata_json": {}})
    assert not is_mock_candidate(_candidate())


def test_filter_real_candidates_excludes_mocks_and_requires_pool() -> None:
    candidates = [
        _candidate(token_mint="mock", metadata_json={"is_mock": True}),
        _candidate(token_mint="no-pool", pool_address=None),
        _candidate(token_mint="low-liq", liquidity_usd=100),
        _candidate(token_mint="good"),
    ]

    filtered = filter_real_candidates(candidates, require_pool_address=True, min_liquidity_usd=10_000)

    assert [candidate.token_mint for candidate in filtered] == ["good"]
    assert candidate_has_evidence_target(filtered[0])


def test_real_token_mints_from_registry_returns_only_real_candidates(tmp_path: Path) -> None:
    registry = CandidateRegistry(tmp_path / "registry.jsonl")
    registry.upsert(_candidate(token_mint="mock", metadata_json={"is_mock": True}))
    registry.upsert(_candidate(token_mint="good"))

    assert real_token_mints_from_registry(tmp_path / "registry.jsonl") == {"good"}
