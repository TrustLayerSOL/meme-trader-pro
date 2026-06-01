"""CLI for building time-span expansion backfill plans."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.features.feature_snapshot_store import FeatureSnapshotStore
from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.time_span_backfill_planner import TimeSpanBackfillPlanner
from research.mtp_research.pipeline.time_span_backfill_report import (
    write_plan_json,
    write_plan_markdown,
)
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def main() -> int:
    args = parse_args()
    plan, markdown_path, json_path = build_and_write_plan(args)
    print(f"real_candidates_found={plan.real_candidate_count}")
    print(f"plan_item_count={len(plan.plan_items)}")
    print(f"estimated_signature_requests={plan.estimated_signature_requests}")
    print(f"estimated_transaction_requests={plan.estimated_transaction_requests}")
    print(f"recommended_next_command={plan.recommended_next_command}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan time-span expansion backfill.")
    parser.add_argument("--registry-path")
    parser.add_argument("--raw-store-path", default=None)
    parser.add_argument("--event-store-path", default=None)
    parser.add_argument("--feature-store-path", default=None)
    parser.add_argument("--outcome-store-path", default=None)
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--target-time-span-seconds", type=int, default=3600)
    parser.add_argument("--min-raw-tx-per-token", type=int, default=50)
    parser.add_argument("--min-research-rows-per-token", type=int, default=100)
    parser.add_argument("--recommended-signature-limit", type=int, default=100)
    parser.add_argument("--recommended-transaction-limit", type=int, default=100)
    return parser.parse_args()


def build_and_write_plan(args: argparse.Namespace):
    planner = TimeSpanBackfillPlanner(
        raw_store=RawTransactionStore(args.raw_store_path) if args.raw_store_path else None,
        event_store=NormalizedEventStore(args.event_store_path) if args.event_store_path else None,
        feature_store=FeatureSnapshotStore(args.feature_store_path) if args.feature_store_path else None,
        outcome_store=OutcomeLabelStore(args.outcome_store_path) if args.outcome_store_path else None,
        dataset_store=ResearchDatasetStore(args.dataset_path) if args.dataset_path else None,
    )
    plan = planner.build_plan(
        min_liquidity_usd=args.min_liquidity_usd,
        candidate_limit=args.candidate_limit,
        target_time_span_seconds=args.target_time_span_seconds,
        min_raw_tx_per_token=args.min_raw_tx_per_token,
        min_research_rows_per_token=args.min_research_rows_per_token,
        recommended_signature_limit=args.recommended_signature_limit,
        recommended_transaction_limit=args.recommended_transaction_limit,
        registry_path=args.registry_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_plan_markdown(plan, output_dir / f"{plan.plan_id}.md")
    json_path = write_plan_json(plan, output_dir / f"{plan.plan_id}.json")
    return plan, markdown_path, json_path


if __name__ == "__main__":
    raise SystemExit(main())
