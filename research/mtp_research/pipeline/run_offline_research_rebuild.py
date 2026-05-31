"""CLI for rebuilding local derived research artifacts without network calls."""

from __future__ import annotations

import argparse

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.evidence_models import (
    EvidenceRunConfig,
    make_evidence_run_id,
)
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild local v3 research artifacts.")
    parser.add_argument("--parse-limit", type=int)
    parser.add_argument("--normalize-limit", type=int)
    parser.add_argument("--max-snapshots", type=int)
    parser.add_argument("--events-path")
    parser.add_argument("--raw-path")
    parser.add_argument("--features-path")
    parser.add_argument("--outcomes-path")
    parser.add_argument("--dataset-path")
    args = parser.parse_args()

    pipeline = EvidencePipeline(
        raw_transaction_store=RawTransactionStore(args.raw_path) if args.raw_path else RawTransactionStore(),
        normalized_event_store=NormalizedEventStore(args.events_path) if args.events_path else NormalizedEventStore(),
        feature_snapshot_store=FeatureSnapshotStore(args.features_path) if args.features_path else FeatureSnapshotStore(),
        outcome_label_store=OutcomeLabelStore(args.outcomes_path) if args.outcomes_path else OutcomeLabelStore(),
        research_dataset_store=ResearchDatasetStore(args.dataset_path) if args.dataset_path else ResearchDatasetStore(),
    )
    summary = pipeline.run_offline_rebuild(
        EvidenceRunConfig(run_id=make_evidence_run_id(), dry_run=False),
        parse_limit=args.parse_limit,
        normalize_limit=args.normalize_limit,
        max_snapshots=args.max_snapshots,
    )
    print(f"normalized_events_inserted={summary.normalized_events_inserted}")
    print(f"normalized_events_updated={summary.normalized_events_updated}")
    print(f"trade_events_inserted={summary.trade_events_inserted}")
    print(f"trade_events_updated={summary.trade_events_updated}")
    print(f"feature_snapshots_inserted={summary.feature_snapshots_inserted}")
    print(f"feature_snapshots_updated={summary.feature_snapshots_updated}")
    print(f"outcome_labels_inserted={summary.outcome_labels_inserted}")
    print(f"outcome_labels_updated={summary.outcome_labels_updated}")
    print(f"research_rows_inserted={summary.research_rows_inserted}")
    print(f"research_rows_updated={summary.research_rows_updated}")
    print(f"artifact_paths={summary.artifact_paths}")
    print(f"warning_flags={summary.warning_flags}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
