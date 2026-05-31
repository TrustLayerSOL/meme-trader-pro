import json
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.pipeline.candidate_seed_loader import (
    load_candidate_seeds,
    seed_registry_from_file,
    write_example_seed_file,
)


def test_writes_example_seed_file(tmp_path: Path) -> None:
    path = write_example_seed_file(tmp_path / "candidate_seeds.jsonl")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["metadata_json"]["example_only"] is True


def test_loads_valid_seed_rows_and_skips_malformed(tmp_path: Path) -> None:
    seed_path = tmp_path / "seeds.jsonl"
    seed_path.write_text(
        "\n".join(
            [
                json.dumps({"token_mint": "mint-1", "source": "manual", "first_seen_ts": "2026-05-31T00:00:00+00:00"}),
                "{bad json",
                json.dumps({"source": "missing_mint"}),
            ]
        ),
        encoding="utf-8",
    )
    candidates = load_candidate_seeds(seed_path)
    assert len(candidates) == 1
    assert candidates[0].token_mint == "mint-1"


def test_seeds_candidate_registry_without_network(tmp_path: Path) -> None:
    seed_path = tmp_path / "seeds.jsonl"
    registry_path = tmp_path / "registry.jsonl"
    seed_path.write_text(
        json.dumps({"token_mint": "mint-1", "source": "manual", "first_seen_ts": "2026-05-31T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    counts = seed_registry_from_file(seed_path, registry_path=registry_path)
    assert counts == {"inserted": 1, "updated": 0, "skipped": 0}
    assert CandidateRegistry(registry_path).get_by_mint("mint-1") is not None
