"""CLI for planning bounded backfill targets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.ingestion.models import LaunchCandidate
from research.mtp_research.pipeline.backfill_target_planner import BackfillTargetPlanner


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan v3 backfill targets.")
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--role", action="append")
    parser.add_argument("--registry-path")
    parser.add_argument("--output-path", default="data/backtests/backfill_targets_plan.jsonl")
    parser.add_argument("--include-mock", action="store_true")
    parser.add_argument("--require-pool-address", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    args = parser.parse_args()

    roles = args.role or ["mint", "pool", "creator"]
    registry = CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry()
    all_candidates = registry.load_all()
    candidates, skipped_mock = _filter_candidates(
        all_candidates,
        include_mock=args.include_mock,
        require_pool_address=args.require_pool_address,
        min_liquidity_usd=args.min_liquidity_usd,
    )
    candidates = candidates[: args.candidate_limit]
    targets = BackfillTargetPlanner().candidates_to_targets(candidates, roles=roles, exclude_mock=not args.include_mock)
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for target in targets:
            f.write(json.dumps(asdict(target), sort_keys=True))
            f.write("\n")
    role_counts = Counter(target.role for target in targets)
    print(f"candidates_selected={len(candidates)}")
    print(f"skipped_mock={skipped_mock}")
    print(f"targets_planned={len(targets)}")
    print(f"role_counts={dict(sorted(role_counts.items()))}")
    print(f"output_path={output_path}")
    if not targets:
        print("warning=No evidence-bearing real candidates found. Run real discovery first.")
    print("network_calls=0")
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
