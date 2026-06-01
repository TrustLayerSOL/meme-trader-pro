"""CLI for building v0 outcome labels from local features and events."""

from __future__ import annotations

import argparse
from collections import Counter
from time import perf_counter

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.outcome_label_builder import OutcomeLabelBuilder
from research.mtp_research.validation.outcome_label_builder import _event_times_by_token
from research.mtp_research.validation.outcome_label_builder import _events_by_token
from research.mtp_research.validation.outcome_label_builder import _future_events_from_sorted
from research.mtp_research.validation.outcome_label_builder import _timestamps_by_token
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.snapshot_selection_models import SnapshotSelectionConfig
from research.mtp_research.validation.snapshot_selector import SnapshotSelector


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v0 outcome labels.")
    parser.add_argument("--features-path")
    parser.add_argument("--events-path")
    parser.add_argument("--outcomes-path")
    parser.add_argument("--token-mint")
    parser.add_argument("--max-snapshots", type=int)
    parser.add_argument("--snapshot-selection-strategy", default="head")
    parser.add_argument("--max-snapshots-per-token", type=int)
    parser.add_argument("--min-time-gap-seconds", type=int)
    parser.add_argument("--entry-max-staleness-sec", type=int, default=60)
    parser.add_argument("--allow-first-after-entry", action="store_true")
    parser.add_argument("--allow-nearest-entry-fallback", action="store_true")
    parser.add_argument("--nearest-entry-max-staleness-sec", type=int, default=300)
    parser.add_argument("--rug-drop-threshold", type=float, default=-0.7)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--stop-after-snapshots", type=int)
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--dry-run-summary", action="store_true")
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--append-or-upsert", action="store_true", default=True)
    args = parser.parse_args()
    started_at = perf_counter()

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
    real_mints = None
    if args.token_mint:
        events = [event for event in events if event.token_mint == args.token_mint]
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        events = [event for event in events if event.token_mint in real_mints]
    selection_config = SnapshotSelectionConfig(
        strategy=args.snapshot_selection_strategy,
        max_snapshots=args.max_snapshots,
        max_snapshots_per_token=args.max_snapshots_per_token,
        min_time_gap_seconds=args.min_time_gap_seconds,
        token_mints=[args.token_mint] if args.token_mint else [],
        real_only=args.real_only,
        min_liquidity_usd=args.min_liquidity_usd,
        metadata_json={"real_mint_count": len(real_mints) if real_mints is not None else None},
    )
    snapshots, selection_summary = SnapshotSelector().select_snapshots(snapshots, selection_config)
    if args.stop_after_snapshots is not None:
        snapshots = snapshots[: args.stop_after_snapshots]

    builder = OutcomeLabelBuilder(
        entry_max_staleness_sec=args.entry_max_staleness_sec,
        allow_first_after_entry=args.allow_first_after_entry,
        allow_nearest_entry_fallback=args.allow_nearest_entry_fallback,
        nearest_entry_max_staleness_sec=args.nearest_entry_max_staleness_sec,
        rug_drop_threshold=args.rug_drop_threshold,
    )
    labels = build_labels_with_progress(
        builder=builder,
        snapshots=snapshots,
        events=events,
        progress_every=args.progress_every,
    )
    if args.dry_run_summary:
        counts = {"inserted": 0, "updated": 0}
    elif args.overwrite:
        counts = outcome_store.replace_all(labels)
    else:
        counts = outcome_store.upsert_many(labels)
    quality_counts = Counter(label.label_quality for label in labels)
    horizon_counts = Counter(label.horizon_name for label in labels)
    nearest_fallback_count = sum(
        1 for label in labels if label.entry_price_source == "nearest_research_fallback"
    )

    print(f"snapshots_loaded={len(snapshots)}")
    print(f"events_loaded={len(events)}")
    print(f"token_count={len({snapshot.token_mint for snapshot in snapshots})}")
    print(f"selected_snapshot_count={len(snapshots)}")
    print(f"snapshot_selection_strategy={selection_summary.strategy}")
    print(f"snapshot_selection_input_snapshot_count={selection_summary.input_snapshot_count}")
    print(f"snapshot_selection_selected_snapshot_count={selection_summary.selected_snapshot_count}")
    print(f"snapshot_selection_input_token_count={selection_summary.input_token_count}")
    print(f"snapshot_selection_selected_token_count={selection_summary.selected_token_count}")
    print(f"snapshot_selection_input_time_span_seconds={selection_summary.input_time_span_seconds}")
    print(
        "snapshot_selection_selected_time_span_seconds="
        f"{selection_summary.selected_time_span_seconds}"
    )
    print(f"snapshot_selection_selected_by_token={selection_summary.selected_by_token}")
    print(f"snapshot_selection_warning_flags={selection_summary.warning_flags}")
    print(f"labels_generated={len(labels)}")
    print(f"labels_inserted={counts['inserted']}")
    print(f"labels_updated={counts['updated']}")
    print(f"dry_run_summary={args.dry_run_summary}")
    print(f"write_mode={'dry_run' if args.dry_run_summary else 'overwrite' if args.overwrite else 'append_or_upsert'}")
    print(f"label_quality_counts={dict(sorted(quality_counts.items()))}")
    print(f"horizon_counts={dict(sorted(horizon_counts.items()))}")
    print(f"nearest_research_fallback_count={nearest_fallback_count}")
    print(f"output_path={outcome_store.path}")
    if args.timing:
        print(f"elapsed_seconds={perf_counter() - started_at:.3f}")
    return 0


def build_labels_with_progress(
    builder: OutcomeLabelBuilder,
    snapshots,
    events,
    progress_every: int,
):
    price_points = builder.price_builder.build_price_points(events)
    points_by_token = builder.price_builder.group_by_token(price_points)
    point_times_by_token = _timestamps_by_token(points_by_token)
    events_by_token = _events_by_token(events)
    event_times_by_token = _event_times_by_token(events_by_token)
    labels = []
    progress_interval = progress_every if progress_every and progress_every > 0 else 0
    started_at = perf_counter()
    total = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        token_points = points_by_token.get(snapshot.token_mint, [])
        token_price_timestamps = point_times_by_token.get(snapshot.token_mint, [])
        token_events = events_by_token.get(snapshot.token_mint, [])
        token_event_times = event_times_by_token.get(snapshot.token_mint, [])
        for horizon in builder.horizons:
            future_events = _future_events_from_sorted(
                token_events,
                token_event_times,
                snapshot_ts=snapshot.snapshot_ts,
                horizon_seconds=horizon.seconds,
            )
            labels.append(
                builder.build_label_for_snapshot(
                    snapshot=snapshot,
                    events=events,
                    token_price_points=token_points,
                    horizon=horizon,
                    token_price_timestamps=token_price_timestamps,
                    future_events=future_events,
                )
            )
        if progress_interval and (index % progress_interval == 0 or index == total):
            print(
                "progress "
                f"snapshots_processed={index} "
                f"labels_generated={len(labels)} "
                f"elapsed_seconds={perf_counter() - started_at:.3f}"
            )
    return labels


if __name__ == "__main__":
    raise SystemExit(main())
