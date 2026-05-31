from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore


def _event(event_id: str, block_time: int | None = 100) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id,
        signature="sig-1",
        slot=1,
        block_time=block_time,
        event_type="transaction_observed",
    )


def test_normalized_event_store_inserts_and_updates_by_event_id(tmp_path: Path) -> None:
    store = NormalizedEventStore(path=tmp_path / "events.jsonl")

    assert store.upsert(_event("event-1", block_time=100)) == "inserted"
    assert store.upsert(_event("event-1", block_time=200)) == "updated"

    stored = store.get_by_event_id("event-1")
    assert stored is not None
    assert stored.block_time == 200
    assert len(store.load_all()) == 1


def test_normalized_event_store_upsert_many_counts_inserted_updated(tmp_path: Path) -> None:
    store = NormalizedEventStore(path=tmp_path / "events.jsonl")
    store.upsert(_event("event-1"))

    counts = store.upsert_many([_event("event-1", block_time=200), _event("event-2")])

    assert counts == {"inserted": 1, "updated": 1}
    events = {event.event_id: event for event in store.load_all()}
    assert len(events) == 2
    assert events["event-1"].block_time == 200
