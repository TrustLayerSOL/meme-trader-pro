from datetime import datetime, timezone
from pathlib import Path

from research.mtp_research.ingestion.raw_transaction_store import (
    RawTransactionRecord,
    RawTransactionStore,
)


def _record(signature: str, block_time: int | None = 100) -> RawTransactionRecord:
    return RawTransactionRecord(
        signature=signature,
        slot=1,
        block_time=block_time,
        success=True,
        address="address-1",
        fetched_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
        raw_json={"signature": signature},
    )


def test_raw_transaction_store_inserts_and_updates_by_signature(tmp_path: Path) -> None:
    store = RawTransactionStore(path=tmp_path / "helius_transactions.jsonl")

    assert store.upsert(_record("sig-1", block_time=100)) == "inserted"
    assert store.upsert(_record("sig-1", block_time=200)) == "updated"

    stored = store.get_by_signature("sig-1")
    assert stored is not None
    assert stored.block_time == 200
    assert len(store.load_all()) == 1


def test_raw_transaction_store_upsert_many_counts_inserted_updated(tmp_path: Path) -> None:
    store = RawTransactionStore(path=tmp_path / "helius_transactions.jsonl")
    store.upsert(_record("sig-1"))

    counts = store.upsert_many([_record("sig-1"), _record("sig-2")])

    assert counts == {"inserted": 1, "updated": 1}
    assert len(store.load_all()) == 2


def test_raw_transaction_store_upsert_many_writes_batch_once(tmp_path: Path, monkeypatch) -> None:
    store = RawTransactionStore(path=tmp_path / "helius_transactions.jsonl")
    write_calls = 0
    original_write_all = store._write_all

    def counted_write_all(records):
        nonlocal write_calls
        write_calls += 1
        original_write_all(records)

    monkeypatch.setattr(store, "_write_all", counted_write_all)

    counts = store.upsert_many([_record("sig-1"), _record("sig-2"), _record("sig-3")])

    assert counts == {"inserted": 3, "updated": 0}
    assert write_calls == 1
