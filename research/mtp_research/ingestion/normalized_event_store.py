"""JSONL-backed normalized event store."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.ingestion.normalization_models import NormalizedEvent


class NormalizedEventStore:
    """Persist normalized events and upsert them by event id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/normalized/events.jsonl"))

    def load_all(self) -> list[NormalizedEvent]:
        if not self.path.exists():
            return []

        events: list[NormalizedEvent] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    events.append(NormalizedEvent.from_dict(json.loads(text)))
        return events

    def get_by_event_id(self, event_id: str) -> NormalizedEvent | None:
        for event in self.load_all():
            if event.event_id == event_id:
                return event
        return None

    def upsert(self, event: NormalizedEvent) -> str:
        events = self.load_all()
        for idx, existing in enumerate(events):
            if existing.event_id == event.event_id:
                events[idx] = event
                self._write_all(events)
                return "updated"

        events.append(event)
        self._write_all(events)
        return "inserted"

    def upsert_many(self, events: list[NormalizedEvent]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        if not events:
            return counts

        existing_events = {event.event_id: event for event in self.load_all()}
        for event in events:
            if event.event_id in existing_events:
                counts["updated"] += 1
            else:
                counts["inserted"] += 1
            existing_events[event.event_id] = event
        self._write_all(list(existing_events.values()))
        return counts

    def _write_all(self, events: list[NormalizedEvent]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_events = sorted(
            events,
            key=lambda event: (
                event.block_time is None,
                event.block_time or 0,
                event.slot is None,
                event.slot or 0,
                event.event_id,
            ),
        )

        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for event in sorted_events:
                f.write(json.dumps(event.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
