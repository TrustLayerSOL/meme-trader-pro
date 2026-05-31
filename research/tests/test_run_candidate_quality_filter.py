from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.ingestion.run_candidate_quality_filter import main


def _seed_registry(path: Path) -> None:
    registry = CandidateRegistry(path)
    registry.upsert(
        LaunchCandidate(
            token_mint="mock-mint",
            source="manual_example",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            metadata_json={"is_mock": True},
        )
    )
    registry.upsert(
        LaunchCandidate(
            token_mint="real-low",
            source="dexscreener_real",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            pool_address="pool-low",
            liquidity_usd=100,
            metadata_json={"is_mock": False},
        )
    )
    registry.upsert(
        LaunchCandidate(
            token_mint="real-good",
            source="dexscreener_real",
            first_seen_ts=datetime(2026, 5, 31, tzinfo=timezone.utc),
            pool_address="pool-good",
            creator_wallet="creator-good",
            liquidity_usd=25_000,
            metadata_json={"is_mock": False},
        )
    )


def test_candidate_quality_filter_excludes_mock_requires_pool_and_min_liquidity(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    registry_path = tmp_path / "registry.jsonl"
    _seed_registry(registry_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_candidate_quality_filter",
            "--registry-path",
            str(registry_path),
            "--exclude-mock",
            "--require-pool-address",
            "--min-liquidity-usd",
            "10000",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "total_candidates=3" in output
    assert "mock_candidates=1" in output
    assert "candidates_passing_filters=1" in output
    assert "candidate token_mint=real-good" in output
    assert "candidate token_mint=real-low" not in output
