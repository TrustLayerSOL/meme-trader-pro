"""Dry-run-first wrapper for bounded time-span expansion backfills."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.evidence_models import EvidenceRunConfig, make_evidence_run_id
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline
from research.mtp_research.pipeline.time_span_backfill_planner import TimeSpanBackfillPlanner


def main() -> int:
    args = parse_args()
    summary, plan = run_time_span_backfill(args)
    print(f"candidates_selected={summary.candidates_selected}")
    print(f"targets_planned={summary.targets_planned}")
    print(f"dry_run={summary.dry_run}")
    print(f"execute={args.execute}")
    print(f"signatures_seen={summary.signatures_seen}")
    print(f"transactions_fetched={summary.transactions_fetched}")
    print(f"raw_transactions_inserted={summary.raw_transactions_inserted}")
    print(f"raw_transactions_updated={summary.raw_transactions_updated}")
    print(f"warning_flags={summary.warning_flags}")
    print(f"recommended_next_command={plan.recommended_next_command}")
    if not args.execute:
        print("no_network_calls_made=True")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute or dry-run bounded time-span backfill.")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--min-liquidity-usd", type=float, default=10000)
    parser.add_argument("--max-signatures-per-target", type=int, default=75)
    parser.add_argument("--max-transactions-per-target", type=int, default=75)
    parser.add_argument("--signature-pages-per-target", type=int, default=1)
    parser.add_argument("--stop-after-targets", type=int)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--registry-path")
    parser.add_argument("--raw-path")
    return parser.parse_args()


def run_time_span_backfill(args: argparse.Namespace):
    planner = TimeSpanBackfillPlanner(
        raw_store=RawTransactionStore(args.raw_path) if args.raw_path else RawTransactionStore(),
    )
    plan = planner.build_plan(
        min_liquidity_usd=args.min_liquidity_usd,
        candidate_limit=args.candidate_limit,
        recommended_signature_limit=args.max_signatures_per_target,
        recommended_transaction_limit=args.max_transactions_per_target,
        registry_path=args.registry_path,
    )
    selected_plan_items = plan.plan_items[: args.stop_after_targets] if args.stop_after_targets else plan.plan_items
    targets = [_plan_item_to_target(item) for item in selected_plan_items]
    pipeline = EvidencePipeline(
        candidate_registry=CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry(),
        raw_transaction_store=RawTransactionStore(args.raw_path) if args.raw_path else RawTransactionStore(),
    )
    config = EvidenceRunConfig(
        run_id=make_evidence_run_id("time_span_backfill"),
        candidate_limit=args.candidate_limit,
        max_signatures_per_target=args.max_signatures_per_target,
        max_transactions_per_target=args.max_transactions_per_target,
        signature_pages_per_target=args.signature_pages_per_target,
        include_failed=False,
        dry_run=not args.execute or args.dry_run,
        roles=["pool"],
        metadata_json={"time_span_plan_id": plan.plan_id},
    )
    summary = pipeline.run_backfill_targets(targets, config, execute=args.execute and not args.dry_run)
    summary.candidates_seen = plan.candidate_count
    summary.candidates_selected = min(args.candidate_limit, plan.real_candidate_count)
    summary.targets_planned = len(targets)
    return summary, plan


def _plan_item_to_target(item):
    from research.mtp_research.ingestion.backfill_jobs import BackfillTarget, make_target_id

    return BackfillTarget(
        target_id=make_target_id(item.target_address, item.role, item.token_mint),
        address=item.target_address,
        role=item.role,
        token_mint=item.token_mint,
        source="time_span_backfill_plan",
        metadata_json={
            "reason": item.reason,
            "priority": item.priority,
            "pool_address": item.pool_address,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
