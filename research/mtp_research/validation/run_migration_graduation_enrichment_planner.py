"""CLI for the dry-run migration/graduation enrichment planner."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.migration_graduation_enrichment_planner import (
    build_migration_graduation_enrichment_dry_run_plan,
    write_migration_graduation_enrichment_plan_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "migration_graduation_enrichment_plan"
)


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("--dry-run is required; this command must not fetch data")
    plan = build_migration_graduation_enrichment_dry_run_plan(
        candidates_path=args.candidates_path,
        mint_limit=args.mint_limit,
        windows=args.windows,
        request_ceiling=args.request_ceiling,
        hard_stop_projected_requests=args.hard_stop_projected_requests,
        selection=args.selection,
        dry_run=args.dry_run,
    )
    paths = write_migration_graduation_enrichment_plan_outputs(plan, output_dir=args.output_dir)
    print(f"report_id={plan['report_id']}")
    print(f"dry_run_classification={plan['dry_run_classification']}")
    print(f"selected_mint_count={plan['scope']['selected_mint_count']}")
    print(f"selected_creator_count={plan['scope']['selected_creator_count']}")
    print(f"primary_window={plan['request_estimate']['primary_window']}")
    print(f"base_projected_requests={plan['request_estimate']['primary_base_projected_requests']}")
    print(f"high_projected_requests={plan['request_estimate']['primary_high_projected_requests']}")
    print(f"request_ceiling_status={plan['request_estimate']['request_ceiling_status']}")
    print(f"network_calls_used={plan['scope']['network_calls_used']}")
    print(f"helius_calls_used={plan['scope']['helius_calls_used']}")
    print(f"exact_later_execute_command={plan['exact_later_execute_command']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run migration/graduation enrichment planner.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--mint-limit", type=int, default=100)
    parser.add_argument("--windows", nargs="+", default=["24h", "72h", "7d"], choices=["24h", "72h", "7d"])
    parser.add_argument("--request-ceiling", type=int, default=3000)
    parser.add_argument("--hard-stop-projected-requests", type=int, default=5000)
    parser.add_argument("--selection", default="deterministic", choices=["deterministic"])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
