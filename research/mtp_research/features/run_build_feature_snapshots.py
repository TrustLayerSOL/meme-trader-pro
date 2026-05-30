"""CLI for building v0 feature snapshots from normalized events."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.features.feature_snapshot_builder import FeatureSnapshotBuilder
from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v0 feature snapshots.")
    parser.add_argument("--events-path")
    parser.add_argument("--features-path")
    parser.add_argument("--token-mint")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--snapshot-step-sec", type=int, default=60)
    parser.add_argument("--max-snapshots", type=int)
    args = parser.parse_args()

    event_store = (
        NormalizedEventStore(path=args.events_path)
        if args.events_path
        else NormalizedEventStore()
    )
    feature_store = (
        FeatureSnapshotStore(path=args.features_path)
        if args.features_path
        else FeatureSnapshotStore()
    )
    events = event_store.load_all()
    if args.token_mint:
        events = [event for event in events if event.token_mint == args.token_mint]
    if args.limit is not None:
        events = events[: args.limit]

    block_times = sorted({event.block_time for event in events if event.block_time is not None})
    snapshot_times = _snapshot_times(block_times, args.snapshot_step_sec)
    if args.max_snapshots is not None:
        snapshot_times = snapshot_times[: args.max_snapshots]

    builder = FeatureSnapshotBuilder()
    token_mints = [args.token_mint] if args.token_mint else None
    snapshots = builder.build_snapshots(
        events,
        snapshot_times=snapshot_times,
        token_mints=token_mints,
    )
    counts = feature_store.upsert_many(snapshots)
    window_counts = Counter(snapshot.window_name for snapshot in snapshots)
    tokens_seen = {event.token_mint for event in events if event.token_mint}

    print(f"events_loaded={len(events)}")
    print(f"tokens_seen={len(tokens_seen)}")
    print(f"snapshot_times_generated={len(snapshot_times)}")
    print(f"snapshots_inserted={counts['inserted']}")
    print(f"snapshots_updated={counts['updated']}")
    print(f"output_path={feature_store.path}")
    print(f"window_counts={dict(sorted(window_counts.items()))}")
    return 0


def _snapshot_times(block_times: list[int], step_sec: int) -> list[int]:
    if not block_times:
        return []
    start = min(block_times)
    end = max(block_times)
    output: list[int] = []
    current = start
    while current <= end:
        output.append(current)
        current += step_sec
    if output[-1] != end:
        output.append(end)
    return output


if __name__ == "__main__":
    raise SystemExit(main())
