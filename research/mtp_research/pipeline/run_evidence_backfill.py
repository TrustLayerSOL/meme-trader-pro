"""CLI for bounded evidence backfill planning/execution."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.raw_transaction_store import RawTransactionStore
from research.mtp_research.pipeline.evidence_models import (
    EvidenceRunConfig,
    make_evidence_run_id,
)
from research.mtp_research.pipeline.evidence_pipeline import EvidencePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded evidence backfill.")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--max-signatures-per-target", type=int, default=25)
    parser.add_argument("--max-transactions-per-target", type=int, default=25)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--role", action="append")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--registry-path")
    parser.add_argument("--raw-path")
    args = parser.parse_args()

    roles = args.role or ["mint", "pool", "creator"]
    pipeline = EvidencePipeline(
        candidate_registry=CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry(),
        raw_transaction_store=RawTransactionStore(args.raw_path) if args.raw_path else RawTransactionStore(),
    )
    candidates = pipeline.select_candidates(args.candidate_limit)
    targets = pipeline.plan_targets(candidates, roles)
    config = EvidenceRunConfig(
        run_id=make_evidence_run_id(),
        candidate_limit=args.candidate_limit,
        max_signatures_per_target=args.max_signatures_per_target,
        max_transactions_per_target=args.max_transactions_per_target,
        include_failed=args.include_failed,
        dry_run=not args.execute,
        roles=roles,
    )
    summary = pipeline.run_backfill_targets(targets, config, execute=args.execute)
    summary.candidates_seen = len(pipeline.candidate_registry.load_all())
    summary.candidates_selected = len(candidates)

    print(f"candidates_selected={summary.candidates_selected}")
    print(f"targets_planned={summary.targets_planned}")
    print(f"dry_run={summary.dry_run}")
    print(f"execute={args.execute}")
    print(f"requested_signature_limit={args.max_signatures_per_target}")
    print(f"requested_transaction_limit={args.max_transactions_per_target}")
    print(f"signatures_seen={summary.signatures_seen}")
    print(f"transactions_fetched={summary.transactions_fetched}")
    print(f"raw_transactions_inserted={summary.raw_transactions_inserted}")
    print(f"raw_transactions_updated={summary.raw_transactions_updated}")
    print(f"warning_flags={summary.warning_flags}")
    if not args.execute:
        print("no_network_calls_made=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
