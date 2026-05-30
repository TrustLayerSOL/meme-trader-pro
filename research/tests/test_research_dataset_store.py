from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def _row(row_id: str, token_mint: str = "mint-1", snapshot_ts: int = 100) -> ResearchDatasetRow:
    return ResearchDatasetRow(
        row_id=row_id,
        snapshot_id="snapshot-1",
        outcome_id="outcome-1",
        token_mint=token_mint,
        snapshot_ts=snapshot_ts,
        window_name="1m",
        window_seconds=60,
        horizon_name="1m",
        horizon_seconds=60,
    )


def test_research_dataset_store_inserts_row(tmp_path: Path) -> None:
    store = ResearchDatasetStore(path=tmp_path / "dataset.jsonl")
    assert store.upsert(_row("row-1")) == "inserted"
    assert store.get_by_row_id("row-1") is not None


def test_research_dataset_store_updates_existing_row(tmp_path: Path) -> None:
    store = ResearchDatasetStore(path=tmp_path / "dataset.jsonl")
    store.upsert(_row("row-1", snapshot_ts=100))
    assert store.upsert(_row("row-1", snapshot_ts=200)) == "updated"
    assert store.get_by_row_id("row-1").snapshot_ts == 200


def test_research_dataset_store_upsert_many_counts(tmp_path: Path) -> None:
    store = ResearchDatasetStore(path=tmp_path / "dataset.jsonl")
    store.upsert(_row("row-1"))
    assert store.upsert_many([_row("row-1"), _row("row-2")]) == {"inserted": 1, "updated": 1}


def test_research_dataset_store_loads_sorted_rows(tmp_path: Path) -> None:
    store = ResearchDatasetStore(path=tmp_path / "dataset.jsonl")
    store.upsert(_row("b", token_mint="mint-2", snapshot_ts=200))
    store.upsert(_row("a", token_mint="mint-1", snapshot_ts=100))
    assert [row.row_id for row in store.load_all()] == ["a", "b"]


def test_research_dataset_store_get_by_row_id(tmp_path: Path) -> None:
    store = ResearchDatasetStore(path=tmp_path / "dataset.jsonl")
    store.upsert(_row("row-1"))
    assert store.get_by_row_id("row-1").row_id == "row-1"
    assert store.get_by_row_id("missing") is None
