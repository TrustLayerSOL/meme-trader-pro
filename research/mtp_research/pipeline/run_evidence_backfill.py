"""CLI for bounded evidence backfill planning/execution."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
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
    parser.add_argument("--include-mock", action="store_true")
    parser.add_argument("--require-pool-address", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    args = parser.parse_args()

    roles = args.role or ["mint", "pool", "creator"]
    pipeline = EvidencePipeline(
        candidate_registry=CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry(),
        raw_transaction_store=RawTransactionStore(args.raw_path) if args.raw_path else RawTransactionStore(),
    )
    all_candidates = pipeline.candidate_registry.load_all()
    candidates, skipped_mock = _filter_candidates(
        all_candidates,
        include_mock=args.include_mock,
        require_pool_address=args.require_pool_address,
        min_liquidity_usd=args.min_liquidity_usd,
    )
    candidates = candidates[: args.candidate_limit]
    targets = pipeline.plan_targets(candidates, roles, exclude_mock=not args.include_mock)
    config = EvidenceRunConfig(
        run_id=make_evidence_run_id(),
        candidate_limit=args.candidate_limit,
        max_signatures_per_target=args.max_signatures_per_target,
        max_transactions_per_target=args.max_transactions_per_target,
        include_failed=args.include_failed,
        dry_run=not args.execute,
        roles=roles,
    )
    if not targets:
        warning_flags = ["no_evidence_bearing_real_candidates"]
        print(f"candidates_selected={len(candidates)}")
        print("targets_planned=0")
        print(f"dry_run={not args.execute}")
        print(f"execute={args.execute}")
        print(f"requested_signature_limit={args.max_signatures_per_target}")
        print(f"requested_transaction_limit={args.max_transactions_per_target}")
        print("signatures_seen=0")
        print("transactions_fetched=0")
        print("raw_transactions_inserted=0")
        print("raw_transactions_updated=0")
        print(f"skipped_mock={skipped_mock}")
        print(f"warning_flags={warning_flags}")
        print("No evidence-bearing real candidates found. Run real discovery first.")
        if not args.execute:
            print("no_network_calls_made=True")
        return 0

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
    print(f"skipped_mock={skipped_mock}")
    print(f"warning_flags={summary.warning_flags}")
    if not args.execute:
        print("no_network_calls_made=True")
    return 0


def _filter_candidates(
    candidates: list[LaunchCandidate],
    include_mock: bool = False,
    require_pool_address: bool = False,
    min_liquidity_usd: float | None = None,
) -> tuple[list[LaunchCandidate], int]:
    skipped_mock = 0
    filtered: list[LaunchCandidate] = []
    for candidate in candidates:
        if not include_mock and _is_mock_candidate(candidate):
            skipped_mock += 1
            continue
        if require_pool_address and not candidate.pool_address:
            continue
        if min_liquidity_usd is not None and (
            candidate.liquidity_usd is None or candidate.liquidity_usd < min_liquidity_usd
        ):
            continue
        filtered.append(candidate)
    filtered.sort(key=lambda candidate: (candidate.pool_address is None, candidate.first_seen_ts))
    return filtered, skipped_mock


def _is_mock_candidate(candidate: LaunchCandidate) -> bool:
    metadata = candidate.metadata_json or {}
    return bool(
        metadata.get("is_mock")
        or metadata.get("example_only")
        or candidate.source in {"mock", "manual_example"}
        or candidate.venue in {"mock", "manual_example"}
    )


if __name__ == "__main__":
    raise SystemExit(main())
