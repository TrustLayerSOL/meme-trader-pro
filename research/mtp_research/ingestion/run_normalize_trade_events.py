"""Normalize v0 trade event candidates from raw transactions."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.ingestion.solana_transaction_parser import summarize_raw_transaction
from research.mtp_research.ingestion.trade_event_normalizer import TradeEventNormalizer
from research.mtp_research.ingestion.venue_classifier import classify_venue


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize v0 trade event candidates.")
    parser.add_argument("--raw-path")
    parser.add_argument("--events-path")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--signature")
    parser.add_argument("--token-mint")
    parser.add_argument("--only-missing-signatures", action="store_true")
    parser.add_argument("--progress-every", type=int)
    args = parser.parse_args()

    raw_store = RawTransactionStore(path=args.raw_path) if args.raw_path else RawTransactionStore()
    event_store = (
        NormalizedEventStore(path=args.events_path)
        if args.events_path
        else NormalizedEventStore()
    )
    normalizer = TradeEventNormalizer()

    raw_records = raw_store.load_all()
    raw_records_seen = len(raw_records)
    if args.signature:
        raw_records = [record for record in raw_records if record.signature == args.signature]
    raw_records_skipped_existing = 0
    if args.only_missing_signatures:
        existing_signatures = {event.signature for event in event_store.load_all()}
        before_count = len(raw_records)
        raw_records = [record for record in raw_records if record.signature not in existing_signatures]
        raw_records_skipped_existing = before_count - len(raw_records)
    selected = raw_records[: args.limit]

    trade_events_inserted = 0
    trade_events_updated = 0
    event_type_counts: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()
    all_events = []

    for index, record in enumerate(selected, start=1):
        summary = summarize_raw_transaction(record)
        summary.venue_classification = classify_venue(summary)
        result = normalizer.normalize_summary(summary, target_token_mint=args.token_mint)
        events = [
            normalizer.flow_to_normalized_event(summary, flow, index)
            for index, flow in enumerate(result.flows)
        ]
        all_events.extend(events)
        for event in events:
            event_type_counts[event.event_type] += 1
            venue_counts[event.venue or "unknown"] += 1
        if args.progress_every and index % args.progress_every == 0:
            print(f"progress raw_records_processed={index}")
    counts = event_store.upsert_many(all_events)
    trade_events_inserted += counts["inserted"]
    trade_events_updated += counts["updated"]

    print(f"raw_records_seen={raw_records_seen}")
    print(f"raw_records_skipped_existing={raw_records_skipped_existing}")
    print(f"raw_records_processed={len(selected)}")
    print(f"trade_events_inserted={trade_events_inserted}")
    print(f"trade_events_updated={trade_events_updated}")
    print(f"event_type_counts={dict(sorted(event_type_counts.items()))}")
    print(f"venue_counts={dict(sorted(venue_counts.items()))}")
    print(f"output_path={event_store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
