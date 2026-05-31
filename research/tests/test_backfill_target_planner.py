from datetime import datetime, timezone

from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.backfill_target_planner import BackfillTargetPlanner


def _candidate(**kwargs) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=kwargs.get("token_mint", "mint-1"),
        source="test",
        first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
        pool_address=kwargs.get("pool_address"),
        creator_wallet=kwargs.get("creator_wallet"),
        metadata_json=kwargs.get("metadata_json", {}),
    )


def test_creates_mint_pool_creator_and_wallet_targets() -> None:
    candidate = _candidate(
        pool_address="pool-1",
        creator_wallet="creator-1",
        metadata_json={"wallets": ["wallet-1"]},
    )
    targets = BackfillTargetPlanner().candidate_to_targets(candidate, roles=["mint", "pool", "creator", "wallet"])
    assert {target.role for target in targets} == {"mint", "pool", "creator", "wallet"}
    assert {target.address for target in targets} == {"mint-1", "pool-1", "creator-1", "wallet-1"}
    assert all(target.token_mint == "mint-1" for target in targets)
    assert all(target.metadata_json["candidate_source"] == "test" for target in targets)


def test_does_not_create_missing_address_targets() -> None:
    targets = BackfillTargetPlanner().candidate_to_targets(_candidate(), roles=["pool", "creator"])
    assert targets == []


def test_dedupes_targets() -> None:
    planner = BackfillTargetPlanner()
    candidate = _candidate(pool_address="same-address")
    targets = planner.candidates_to_targets([candidate, candidate], roles=["pool"])
    assert len(targets) == 1
