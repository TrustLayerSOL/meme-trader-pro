"""CLI for P0 Helius enrichment dry-run planners."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.p0_helius_enrichment_planners import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    FUNDING_LINK_PATH,
    MASTER_BUDGET_PATH,
    MASTER_PLAN_PATH,
    MASTER_PRIORITY_PATH,
    REPEATED_BUYER_REPORT_PATH,
    ExecuteRejectedError,
    build_p0_helius_enrichment_plans,
)


def main() -> int:
    args = parse_args()
    try:
        report, paths = build_p0_helius_enrichment_plans(
            master_plan_path=args.master_plan_path,
            master_priority_path=args.master_priority_path,
            master_budget_path=args.master_budget_path,
            repeated_buyer_report_path=args.repeated_buyer_report_path,
            event_paths=[Path(path) for path in args.event_path] if args.event_path else None,
            funding_link_path=args.funding_link_path or None,
            output_dir=args.output_dir,
            status_path=args.status_path,
            pilot=args.pilot,
            credit_cap_per_pilot=args.credit_cap_per_pilot,
            total_credit_cap=args.total_credit_cap,
            max_launches=args.max_launches,
            max_wallets=args.max_wallets,
            max_creators=args.max_creators,
            max_mints=args.max_mints,
            dry_run=args.dry_run or not args.execute,
            execute=args.execute,
        )
    except ExecuteRejectedError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2) from exc
    print(f"report_id={report['report_id']}")
    print(f"overall_classification={report['overall_classification']}")
    print(f"combined_projected_credits={report['combined_projected_credits']}")
    print(f"network_calls_made={report['network_calls_made']}")
    for row in report["pilot_plans"]:
        print(
            f"pilot={row['pilot_id']} readiness={row['readiness_classification']} "
            f"credits={row['projected_credits']} calls={row['projected_calls']} targets={row['target_counts']}"
        )
    print(f"next_recommended_action={report['next_recommended_action']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dry-run P0 Helius enrichment planners.")
    parser.add_argument("--pilot", choices=["top-holder", "early-buyer-history", "creator-funder-graph", "all"], default="all")
    parser.add_argument("--credit-cap-per-pilot", type=int, default=25_000)
    parser.add_argument("--total-credit-cap", type=int, default=70_000)
    parser.add_argument("--max-launches", type=int, default=250)
    parser.add_argument("--max-wallets", type=int, default=1_000)
    parser.add_argument("--max-creators", type=int, default=250)
    parser.add_argument("--max-mints", type=int, default=250)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--master-plan-path", default=MASTER_PLAN_PATH)
    parser.add_argument("--master-priority-path", default=MASTER_PRIORITY_PATH)
    parser.add_argument("--master-budget-path", default=MASTER_BUDGET_PATH)
    parser.add_argument("--repeated-buyer-report-path", default=REPEATED_BUYER_REPORT_PATH)
    parser.add_argument("--event-path", action="append", default=None)
    parser.add_argument("--funding-link-path", default=FUNDING_LINK_PATH)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true", help="Rejected in this sprint; planners are dry-run only.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
