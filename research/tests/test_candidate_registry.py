from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate


def _candidate(
    token_mint: str,
    first_seen_ts: datetime,
    metadata: dict,
    *,
    jupiter_recent_seen: bool = False,
    raydium_seen: bool = False,
) -> LaunchCandidate:
    return LaunchCandidate(
        token_mint=token_mint,
        source="test",
        first_seen_ts=first_seen_ts,
        jupiter_recent_seen=jupiter_recent_seen,
        raydium_seen=raydium_seen,
        metadata_json=metadata,
    )


def test_add_new_token(tmp_path: Path) -> None:
    registry = CandidateRegistry(path=tmp_path / "candidate_registry.jsonl")
    result = registry.upsert(
        _candidate(
            "mint-new-01",
            datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
            {"source": "first"},
        )
    )
    assert result == "inserted"
    assert registry.get_by_mint("mint-new-01") is not None


def test_upsert_existing_token_preserves_merge(tmp_path: Path) -> None:
    registry = CandidateRegistry(path=tmp_path / "candidate_registry.jsonl")
    first = _candidate(
        "mint-upsert-01",
        datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
        {"alpha": 1, "flag": "old"},
        jupiter_recent_seen=True,
    )
    second = _candidate(
        "mint-upsert-01",
        datetime(2026, 5, 30, 12, 5, 0, tzinfo=timezone.utc),
        {"flag": "new", "beta": 2},
        raydium_seen=True,
    )

    registry.upsert(first)
    registry.upsert(second)

    loaded = registry.get_by_mint("mint-upsert-01")
    assert loaded is not None
    assert loaded.jupiter_recent_seen is True
    assert loaded.raydium_seen is True
    assert loaded.metadata_json["alpha"] == 1
    assert loaded.metadata_json["beta"] == 2
    assert loaded.metadata_json["flag"] == "new"
    assert loaded.status == "candidate"


def test_preserve_earliest_first_seen_ts(tmp_path: Path) -> None:
    registry = CandidateRegistry(path=tmp_path / "candidate_registry.jsonl")
    older = _candidate(
        "mint-time-01",
        datetime(2026, 5, 30, 12, 10, 0, tzinfo=timezone.utc),
        {"first": True},
    )
    newer = _candidate(
        "mint-time-01",
        datetime(2026, 5, 30, 12, 15, 0, tzinfo=timezone.utc),
        {"first": False},
    )

    registry.upsert(newer)
    registry.upsert(older)

    stored = registry.get_by_mint("mint-time-01")
    assert stored is not None
    assert stored.first_seen_ts == datetime(2026, 5, 30, 12, 10, 0, tzinfo=timezone.utc)


def test_load_all_and_get_by_mint(tmp_path: Path) -> None:
    registry = CandidateRegistry(path=tmp_path / "candidate_registry.jsonl")
    registry.upsert(_candidate("mint-a", datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc), {"a": 1}))
    registry.upsert(_candidate("mint-b", datetime(2026, 5, 30, 12, 1, 0, tzinfo=timezone.utc), {"b": 2}))

    all_candidates = registry.load_all()
    assert len(all_candidates) == 2
    assert {c.token_mint for c in all_candidates} == {"mint-a", "mint-b"}
    assert registry.get_by_mint("mint-b") is not None


def test_jsonl_file_created(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "candidate_registry.jsonl"
    registry = CandidateRegistry(path=path)
    registry.upsert(_candidate("mint-file", datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc), {}))

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
