"""CLI for building joined research dataset rows."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
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
    args = parser.parse_args()

    snapshots = FeatureSnapshotStore(path=args.features_path).load_all() if args.features_path else FeatureSnapshotStore().load_all()
    labels = OutcomeLabelStore(path=args.outcomes_path).load_all() if args.outcomes_path else OutcomeLabelStore().load_all()
    builder = ResearchDatasetBuilder()
    generated_rows = builder.join_snapshots_to_outcomes(snapshots, labels)
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
    counts = store.upsert_many(filtered_rows)
    print(f"snapshots_loaded={len(snapshots)}")
    print(f"outcome_labels_loaded={len(labels)}")
    print(f"rows_generated_before_filters={len(generated_rows)}")
    print(f"rows_after_filters={len(filtered_rows)}")
    print(f"rows_inserted={counts['inserted']}")
    print(f"rows_updated={counts['updated']}")
    print(f"window_counts={dict(sorted(Counter(row.window_name for row in filtered_rows).items()))}")
    print(f"horizon_counts={dict(sorted(Counter(row.horizon_name for row in filtered_rows).items()))}")
    print(f"label_quality_counts={dict(sorted(Counter(row.label_quality for row in filtered_rows).items()))}")
    print(f"output_path={store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
