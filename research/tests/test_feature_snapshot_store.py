from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore


def _snapshot(
    snapshot_id: str,
    token_mint: str = "mint-1",
    snapshot_ts: int = 100,
    window_seconds: int = 60,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        token_mint=token_mint,
        snapshot_ts=snapshot_ts,
        window_name=f"{window_seconds}s",
        window_seconds=window_seconds,
        event_count=1,
    )


def test_feature_snapshot_store_inserts_snapshot(tmp_path: Path) -> None:
    store = FeatureSnapshotStore(path=tmp_path / "features.jsonl")

    assert store.upsert(_snapshot("snapshot-1")) == "inserted"
    assert store.get_by_snapshot_id("snapshot-1") is not None


def test_feature_snapshot_store_updates_existing_snapshot(tmp_path: Path) -> None:
    store = FeatureSnapshotStore(path=tmp_path / "features.jsonl")
    store.upsert(_snapshot("snapshot-1", snapshot_ts=100))

    assert store.upsert(_snapshot("snapshot-1", snapshot_ts=200)) == "updated"

    stored = store.get_by_snapshot_id("snapshot-1")
    assert stored is not None
    assert stored.snapshot_ts == 200


def test_feature_snapshot_store_upsert_many_counts(tmp_path: Path) -> None:
    store = FeatureSnapshotStore(path=tmp_path / "features.jsonl")
    store.upsert(_snapshot("snapshot-1"))

    counts = store.upsert_many([_snapshot("snapshot-1"), _snapshot("snapshot-2")])

    assert counts == {"inserted": 1, "updated": 1}


def test_feature_snapshot_store_loads_sorted_snapshots(tmp_path: Path) -> None:
    store = FeatureSnapshotStore(path=tmp_path / "features.jsonl")
    store.upsert(_snapshot("b", token_mint="mint-2", snapshot_ts=200, window_seconds=300))
    store.upsert(_snapshot("a", token_mint="mint-1", snapshot_ts=100, window_seconds=60))

    loaded = store.load_all()

    assert [snapshot.snapshot_id for snapshot in loaded] == ["a", "b"]


def test_feature_snapshot_store_get_by_snapshot_id(tmp_path: Path) -> None:
    store = FeatureSnapshotStore(path=tmp_path / "features.jsonl")
    store.upsert(_snapshot("snapshot-1"))

    assert store.get_by_snapshot_id("snapshot-1").snapshot_id == "snapshot-1"
    assert store.get_by_snapshot_id("missing") is None
