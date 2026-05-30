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
    args = parser.parse_args()

    raw_store = RawTransactionStore(path=args.raw_path) if args.raw_path else RawTransactionStore()
    event_store = (
        NormalizedEventStore(path=args.events_path)
        if args.events_path
        else NormalizedEventStore()
    )
    normalizer = TradeEventNormalizer()

    raw_records = raw_store.load_all()
    if args.signature:
        raw_records = [record for record in raw_records if record.signature == args.signature]
    selected = raw_records[: args.limit]

    trade_events_inserted = 0
    trade_events_updated = 0
    event_type_counts: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()

    for record in selected:
        summary = summarize_raw_transaction(record)
        summary.venue_classification = classify_venue(summary)
        result = normalizer.normalize_summary(summary, target_token_mint=args.token_mint)
        events = [
            normalizer.flow_to_normalized_event(summary, flow, index)
            for index, flow in enumerate(result.flows)
        ]
        counts = event_store.upsert_many(events)
        trade_events_inserted += counts["inserted"]
        trade_events_updated += counts["updated"]
        for event in events:
            event_type_counts[event.event_type] += 1
            venue_counts[event.venue or "unknown"] += 1

    print(f"raw_records_processed={len(selected)}")
    print(f"trade_events_inserted={trade_events_inserted}")
    print(f"trade_events_updated={trade_events_updated}")
    print(f"event_type_counts={dict(sorted(event_type_counts.items()))}")
    print(f"venue_counts={dict(sorted(venue_counts.items()))}")
    print(f"output_path={event_store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
