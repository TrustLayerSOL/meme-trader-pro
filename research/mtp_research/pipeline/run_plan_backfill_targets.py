"""CLI for planning bounded backfill targets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from research.mtp_research.ingestion.candidate_registry import CandidateRegistry
from research.mtp_research.pipeline.backfill_target_planner import BackfillTargetPlanner


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan v3 backfill targets.")
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--role", action="append")
    parser.add_argument("--registry-path")
    parser.add_argument("--output-path", default="data/backtests/backfill_targets_plan.jsonl")
    args = parser.parse_args()

    roles = args.role or ["mint", "pool", "creator"]
    registry = CandidateRegistry(args.registry_path) if args.registry_path else CandidateRegistry()
    candidates = registry.load_all()[: args.candidate_limit]
    targets = BackfillTargetPlanner().candidates_to_targets(candidates, roles=roles)
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for target in targets:
            f.write(json.dumps(asdict(target), sort_keys=True))
            f.write("\n")
    role_counts = Counter(target.role for target in targets)
    print(f"candidates_selected={len(candidates)}")
    print(f"targets_planned={len(targets)}")
    print(f"role_counts={dict(sorted(role_counts.items()))}")
    print(f"output_path={output_path}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
