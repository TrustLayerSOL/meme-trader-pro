from pathlib import Path

from research.mtp_research.validation.walk_forward_models import (
    WalkForwardConfig,
    WalkForwardValidationResult,
)
from research.mtp_research.validation.walk_forward_store import WalkForwardValidationStore


def _result(validation_id: str = "validation-1", fold_count: int = 1) -> WalkForwardValidationResult:
    return WalkForwardValidationResult(
        validation_id=validation_id,
        created_at="2026-05-30T00:00:00+00:00",
        config=WalkForwardConfig("cfg", 10, 5, 5),
        dataset_path="dataset.jsonl",
        row_count=10,
        filtered_row_count=10,
        fold_count=fold_count,
        rules_tested=1,
    )


def test_inserts_result(tmp_path: Path) -> None:
    store = WalkForwardValidationStore(tmp_path / "results.jsonl")
    assert store.upsert(_result()) == "inserted"
    assert store.path.exists()


def test_updates_existing_result_by_validation_id(tmp_path: Path) -> None:
    store = WalkForwardValidationStore(tmp_path / "results.jsonl")
    store.upsert(_result(fold_count=1))
    assert store.upsert(_result(fold_count=2)) == "updated"
    assert store.get_by_validation_id("validation-1").fold_count == 2


def test_upsert_many_counts_inserted_and_updated(tmp_path: Path) -> None:
    store = WalkForwardValidationStore(tmp_path / "results.jsonl")
    store.upsert(_result("validation-1"))
    counts = store.upsert_many([_result("validation-1"), _result("validation-2")])
    assert counts == {"inserted": 1, "updated": 1}


def test_load_all_returns_results_and_get_by_validation_id_works(tmp_path: Path) -> None:
    store = WalkForwardValidationStore(tmp_path / "results.jsonl")
    store.upsert(_result("validation-1"))
    store.upsert(_result("validation-2"))
    assert [result.validation_id for result in store.load_all()] == ["validation-1", "validation-2"]
    assert store.get_by_validation_id("validation-2").validation_id == "validation-2"
