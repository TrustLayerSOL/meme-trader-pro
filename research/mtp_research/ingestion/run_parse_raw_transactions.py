"""Parse raw transaction JSONL records into normalized observed events."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.ingestion.basic_transaction_normalizer import (
    transaction_summary_to_observed_event,
)
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.ingestion.solana_transaction_parser import summarize_raw_transaction
from research.mtp_research.ingestion.venue_classifier import classify_venue


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse raw v3 transactions.")
    parser.add_argument("--raw-path")
    parser.add_argument("--events-path")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--signature")
    args = parser.parse_args()

    raw_store = RawTransactionStore(path=args.raw_path) if args.raw_path else RawTransactionStore()
    event_store = (
        NormalizedEventStore(path=args.events_path)
        if args.events_path
        else NormalizedEventStore()
    )

    raw_records = raw_store.load_all()
    if args.signature:
        raw_records = [record for record in raw_records if record.signature == args.signature]
    selected = raw_records[: args.limit]

    events_inserted = 0
    events_updated = 0
    venues_seen: Counter[str] = Counter()

    for record in selected:
        summary = summarize_raw_transaction(record)
        summary.venue_classification = classify_venue(summary)
        event = transaction_summary_to_observed_event(summary)
        result = event_store.upsert(event)
        if result == "inserted":
            events_inserted += 1
        else:
            events_updated += 1
        venues_seen[event.venue or "unknown"] += 1

    print(f"raw_records_processed={len(selected)}")
    print(f"events_inserted={events_inserted}")
    print(f"events_updated={events_updated}")
    print(f"venues_seen={dict(sorted(venues_seen.items()))}")
    print(f"output_path={event_store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
