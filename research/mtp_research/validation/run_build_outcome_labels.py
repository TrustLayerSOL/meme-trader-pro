"""CLI for building v0 outcome labels from local features and events."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.validation.outcome_label_builder import OutcomeLabelBuilder
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v0 outcome labels.")
    parser.add_argument("--features-path")
    parser.add_argument("--events-path")
    parser.add_argument("--outcomes-path")
    parser.add_argument("--token-mint")
    parser.add_argument("--max-snapshots", type=int)
    parser.add_argument("--entry-max-staleness-sec", type=int, default=60)
    parser.add_argument("--allow-first-after-entry", action="store_true")
    parser.add_argument("--allow-nearest-entry-fallback", action="store_true")
    parser.add_argument("--nearest-entry-max-staleness-sec", type=int, default=300)
    parser.add_argument("--rug-drop-threshold", type=float, default=-0.7)
    args = parser.parse_args()

    feature_store = (
        FeatureSnapshotStore(path=args.features_path)
        if args.features_path
        else FeatureSnapshotStore()
    )
    event_store = (
        NormalizedEventStore(path=args.events_path)
        if args.events_path
        else NormalizedEventStore()
    )
    outcome_store = (
        OutcomeLabelStore(path=args.outcomes_path)
        if args.outcomes_path
        else OutcomeLabelStore()
    )

    snapshots = feature_store.load_all()
    events = event_store.load_all()
    if args.token_mint:
        snapshots = [snapshot for snapshot in snapshots if snapshot.token_mint == args.token_mint]
        events = [event for event in events if event.token_mint == args.token_mint]
    if args.max_snapshots is not None:
        snapshots = snapshots[: args.max_snapshots]

    builder = OutcomeLabelBuilder(
        entry_max_staleness_sec=args.entry_max_staleness_sec,
        allow_first_after_entry=args.allow_first_after_entry,
        allow_nearest_entry_fallback=args.allow_nearest_entry_fallback,
        nearest_entry_max_staleness_sec=args.nearest_entry_max_staleness_sec,
        rug_drop_threshold=args.rug_drop_threshold,
    )
    labels = builder.build_labels(
        snapshots,
        events,
        token_mints=[args.token_mint] if args.token_mint else None,
    )
    counts = outcome_store.upsert_many(labels)
    quality_counts = Counter(label.label_quality for label in labels)
    horizon_counts = Counter(label.horizon_name for label in labels)
    nearest_fallback_count = sum(
        1 for label in labels if label.entry_price_source == "nearest_research_fallback"
    )

    print(f"snapshots_loaded={len(snapshots)}")
    print(f"events_loaded={len(events)}")
    print(f"labels_generated={len(labels)}")
    print(f"labels_inserted={counts['inserted']}")
    print(f"labels_updated={counts['updated']}")
    print(f"label_quality_counts={dict(sorted(quality_counts.items()))}")
    print(f"horizon_counts={dict(sorted(horizon_counts.items()))}")
    print(f"nearest_research_fallback_count={nearest_fallback_count}")
    print(f"output_path={outcome_store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
