from pathlib import Path

from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.outcome_models import OutcomeLabel


def _label(
    outcome_id: str,
    token_mint: str = "mint-1",
    snapshot_ts: int = 100,
    horizon_seconds: int = 60,
) -> OutcomeLabel:
    return OutcomeLabel(
        outcome_id=outcome_id,
        snapshot_id="snapshot-1",
        token_mint=token_mint,
        snapshot_ts=snapshot_ts,
        horizon_name=f"{horizon_seconds}s",
        horizon_seconds=horizon_seconds,
        label_quality="sparse",
    )


def test_outcome_label_store_inserts_label(tmp_path: Path) -> None:
    store = OutcomeLabelStore(path=tmp_path / "outcomes.jsonl")

    assert store.upsert(_label("outcome-1")) == "inserted"
    assert store.get_by_outcome_id("outcome-1") is not None


def test_outcome_label_store_updates_existing_label(tmp_path: Path) -> None:
    store = OutcomeLabelStore(path=tmp_path / "outcomes.jsonl")
    store.upsert(_label("outcome-1", snapshot_ts=100))

    assert store.upsert(_label("outcome-1", snapshot_ts=200)) == "updated"
    assert store.get_by_outcome_id("outcome-1").snapshot_ts == 200


def test_outcome_label_store_upsert_many_counts(tmp_path: Path) -> None:
    store = OutcomeLabelStore(path=tmp_path / "outcomes.jsonl")
    store.upsert(_label("outcome-1"))

    counts = store.upsert_many([_label("outcome-1"), _label("outcome-2")])

    assert counts == {"inserted": 1, "updated": 1}


def test_outcome_label_store_loads_sorted_labels(tmp_path: Path) -> None:
    store = OutcomeLabelStore(path=tmp_path / "outcomes.jsonl")
    store.upsert(_label("b", token_mint="mint-2", snapshot_ts=200, horizon_seconds=300))
    store.upsert(_label("a", token_mint="mint-1", snapshot_ts=100, horizon_seconds=60))

    loaded = store.load_all()

    assert [label.outcome_id for label in loaded] == ["a", "b"]


def test_outcome_label_store_get_by_outcome_id(tmp_path: Path) -> None:
    store = OutcomeLabelStore(path=tmp_path / "outcomes.jsonl")
    store.upsert(_label("outcome-1"))

    assert store.get_by_outcome_id("outcome-1").outcome_id == "outcome-1"
    assert store.get_by_outcome_id("missing") is None
