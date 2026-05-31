"""CLI for building joined research dataset rows."""

from __future__ import annotations

import argparse
from collections import Counter
from time import perf_counter

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_builder import ResearchDatasetBuilder
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v0 research dataset rows.")
    parser.add_argument("--features-path")
    parser.add_argument("--outcomes-path")
    parser.add_argument("--dataset-path")
    parser.add_argument("--token-mint")
    parser.add_argument("--window-name")
    parser.add_argument("--horizon-name")
    parser.add_argument("--min-label-quality")
    parser.add_argument("--require-entry-price", action="store_true")
    parser.add_argument("--require-forward-return", action="store_true")
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--stop-after-labels", type=int)
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    parser.add_argument("--dry-run-summary", action="store_true")
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    started_at = perf_counter()

    snapshots = FeatureSnapshotStore(path=args.features_path).load_all() if args.features_path else FeatureSnapshotStore().load_all()
    labels = OutcomeLabelStore(path=args.outcomes_path).load_all() if args.outcomes_path else OutcomeLabelStore().load_all()
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        snapshots = [snapshot for snapshot in snapshots if snapshot.token_mint in real_mints]
        labels = [label for label in labels if label.token_mint in real_mints]
    if args.stop_after_labels is not None:
        labels = labels[: args.stop_after_labels]
    builder = ResearchDatasetBuilder()
    generated_rows = join_with_progress(
        builder=builder,
        snapshots=snapshots,
        labels=labels,
        progress_every=args.progress_every,
    )
    filtered_rows = builder.filter_rows(
        generated_rows,
        token_mints=[args.token_mint] if args.token_mint else None,
        window_names=[args.window_name] if args.window_name else None,
        horizon_names=[args.horizon_name] if args.horizon_name else None,
        min_label_quality=args.min_label_quality,
        require_entry_price=args.require_entry_price,
        require_forward_return=args.require_forward_return,
    )
    if args.max_rows is not None:
        filtered_rows = filtered_rows[: args.max_rows]

    store = ResearchDatasetStore(path=args.dataset_path) if args.dataset_path else ResearchDatasetStore()
    if args.dry_run_summary:
        counts = {"inserted": 0, "updated": 0}
    elif args.overwrite:
        counts = store.replace_all(filtered_rows)
    else:
        counts = store.upsert_many(filtered_rows)
    print(f"snapshots_loaded={len(snapshots)}")
    print(f"outcome_labels_loaded={len(labels)}")
    print(f"token_count={len({snapshot.token_mint for snapshot in snapshots})}")
    print(f"rows_generated_before_filters={len(generated_rows)}")
    print(f"rows_after_filters={len(filtered_rows)}")
    print(f"rows_inserted={counts['inserted']}")
    print(f"rows_updated={counts['updated']}")
    print(f"dry_run_summary={args.dry_run_summary}")
    print(f"write_mode={'dry_run' if args.dry_run_summary else 'overwrite' if args.overwrite else 'append_or_upsert'}")
    print(f"window_counts={dict(sorted(Counter(row.window_name for row in filtered_rows).items()))}")
    print(f"horizon_counts={dict(sorted(Counter(row.horizon_name for row in filtered_rows).items()))}")
    print(f"label_quality_counts={dict(sorted(Counter(row.label_quality for row in filtered_rows).items()))}")
    print(f"output_path={store.path}")
    if args.timing:
        print(f"elapsed_seconds={perf_counter() - started_at:.3f}")
    return 0


def join_with_progress(
    builder: ResearchDatasetBuilder,
    snapshots,
    labels,
    progress_every: int,
):
    labels_by_snapshot = {}
    for label in labels:
        labels_by_snapshot.setdefault(label.snapshot_id, []).append(label)

    rows = []
    progress_interval = progress_every if progress_every and progress_every > 0 else 0
    started_at = perf_counter()
    total = len(snapshots)
    for index, snapshot in enumerate(snapshots, start=1):
        for label in labels_by_snapshot.get(snapshot.snapshot_id, []):
            if label.token_mint != snapshot.token_mint:
                continue
            if label.snapshot_ts != snapshot.snapshot_ts:
                continue
            rows.append(builder.snapshot_and_label_to_row(snapshot, label))
        if progress_interval and (index % progress_interval == 0 or index == total):
            print(
                "progress "
                f"snapshots_processed={index} "
                f"rows_generated={len(rows)} "
                f"elapsed_seconds={perf_counter() - started_at:.3f}"
            )
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
