"""Dry-run planner for program-signature launch discovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.mtp_research.ingestion.program_signature_discovery_plan import (
    build_default_program_signature_discovery_plan,
)
from research.mtp_research.ingestion.run_program_signature_probe import run_probe


def main() -> int:
    args = parse_args()
    plan = build_default_program_signature_discovery_plan()
    print(f"created_at={plan.created_at}")
    print(f"target_count={len(plan.targets)}")
    print(f"execute_probe={args.execute_probe}")
    print(f"hydrate_sample={args.hydrate_sample}")
    print(f"limit_per_program={args.limit_per_program}")
    for target in sorted(plan.targets, key=lambda item: item.priority):
        print(
            "target "
            f"name={target.name} venue={target.venue} program_id={target.program_id} "
            f"expected_event_type={target.expected_event_type} priority={target.priority}"
        )
    print(f"recommended_probe_command={plan.recommended_probe_command}")
    print(f"warning_flags={plan.warning_flags}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "program_signature_discovery_plan.json"
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"plan_path={plan_path}")

    if not args.execute_probe:
        print("network_calls=0")
        return 0

    total_network_calls = 0
    for target in sorted(plan.targets, key=lambda item: item.priority):
        result = run_probe(
            program_id=target.program_id,
            limit=args.limit_per_program,
            hydrate_sample=args.hydrate_sample,
            output_dir=output_dir,
            execute=True,
            label=target.name,
        )
        total_network_calls += result["network_calls"]
        print(f"probe_result target={target.name} signatures_found={result['signatures_found']} hydrated_count={result['hydrated_count']}")
    print(f"network_calls={total_network_calls}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan broad launch discovery from program signatures.")
    parser.add_argument("--limit-per-program", type=int, default=10)
    parser.add_argument("--hydrate-sample", action="store_true")
    parser.add_argument("--execute-probe", action="store_true")
    parser.add_argument("--output-dir", default="data/backtests/diagnostics/reports")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
