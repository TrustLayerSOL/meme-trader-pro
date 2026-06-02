"""CLI for the dry-run pre-launch funding planner."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.pre_launch_funding_planner import (
    build_pre_launch_funding_dry_run_plan,
    write_pre_launch_funding_plan_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "pre_launch_funding_planner"
)


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("--dry-run is required; this command must not fetch data")
    plan = build_pre_launch_funding_dry_run_plan(
        candidates_path=args.candidates_path,
        max_creators=args.max_creators,
        lookback_hours=args.lookback_hours,
        request_ceiling=args.request_ceiling,
        hard_stop_projected_requests=args.hard_stop_projected_requests,
        creator_selection=args.creator_selection,
        dry_run=args.dry_run,
    )
    paths = write_pre_launch_funding_plan_outputs(plan, output_dir=args.output_dir)
    print(f"report_id={plan['report_id']}")
    print(f"dry_run_classification={plan['dry_run_classification']}")
    print(f"selected_creator_count={plan['scope']['selected_creator_count']}")
    print(f"launches_covered={plan['scope']['launches_covered_by_selected_creators']}")
    print(f"lookback_window={plan['request_estimate']['lookback_window']}")
    print(f"base_projected_requests={plan['request_estimate']['base_projected_requests']}")
    print(f"high_projected_requests={plan['request_estimate']['high_projected_requests']}")
    print(f"request_ceiling_status={plan['request_estimate']['request_ceiling_status']}")
    print(f"network_calls_used={plan['scope']['network_calls_used']}")
    print(f"helius_calls_used={plan['scope']['helius_calls_used']}")
    print(f"exact_later_execute_command={plan['exact_later_execute_command']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run pre-launch funding acquisition planner.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--max-creators", type=int, default=50)
    parser.add_argument("--lookback-hours", type=int, default=24, choices=[1, 6, 24, 168])
    parser.add_argument("--request-ceiling", type=int, default=3000)
    parser.add_argument("--hard-stop-projected-requests", type=int, default=5000)
    parser.add_argument("--creator-selection", default="deterministic", choices=["deterministic"])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
