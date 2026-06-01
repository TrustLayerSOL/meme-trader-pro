"""CLI for Pump.fun first-two-hour lifecycle collection planning."""

from __future__ import annotations

import argparse

from research.mtp_research.launch_regime.pumpfun_lifecycle_plan import (
    DEFAULT_CENSUS_PATH,
    DEFAULT_MARKDOWN_PLAN_PATH,
    DEFAULT_PLAN_PATH,
    DEFAULT_PRECISION_SUMMARY_PATH,
    build_pumpfun_lifecycle_plan,
    write_pumpfun_lifecycle_plan,
    write_pumpfun_lifecycle_plan_markdown,
)


def main() -> int:
    args = parse_args()
    plan = build_pumpfun_lifecycle_plan(
        census_path=args.census_path,
        precision_summary_path=args.precision_summary_path,
        target_launches=args.target_launches,
        signature_pages_per_launch=args.signature_pages_per_launch,
        max_transactions_per_launch=args.max_transactions_per_launch,
        targets_per_launch=args.targets_per_launch,
        max_rpc_requests=args.max_rpc_requests,
    )
    output_path = write_pumpfun_lifecycle_plan(plan, args.output_path)
    markdown_path = write_pumpfun_lifecycle_plan_markdown(plan, args.markdown_output_path)
    _print_summary(plan, output_path, markdown_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan Pump.fun lifecycle collection without network calls.")
    parser.add_argument("--census-path", default=str(DEFAULT_CENSUS_PATH))
    parser.add_argument("--precision-summary-path", default=str(DEFAULT_PRECISION_SUMMARY_PATH))
    parser.add_argument("--target-launches", type=int, default=2500)
    parser.add_argument("--signature-pages-per-launch", type=int, default=1)
    parser.add_argument("--max-transactions-per-launch", type=int, default=100)
    parser.add_argument("--targets-per-launch", type=int, default=1)
    parser.add_argument("--max-rpc-requests", type=int, default=300_000)
    parser.add_argument("--output-path", default=str(DEFAULT_PLAN_PATH))
    parser.add_argument("--markdown-output-path", default=str(DEFAULT_MARKDOWN_PLAN_PATH))
    return parser.parse_args()


def _print_summary(plan: dict, output_path, markdown_path) -> None:
    keys = [
        "census_rows",
        "accepted_census_rows",
        "deduped_accepted_launches",
        "eligible_launches",
        "selected_launches",
        "target_launches",
        "collection_scope",
        "expected_snapshot_rows",
        "expected_outcome_rows",
        "expected_research_rows",
        "estimated_signature_requests",
        "estimated_transaction_requests",
        "estimated_total_rpc_requests",
        "estimated_credits",
        "expected_raw_transactions_up_to",
        "launch_regime_counts",
        "launch_weekday_counts",
        "accepted_weekday_counts",
        "accepted_hour_local_counts",
        "accepted_configured_window_counts",
        "network_calls",
        "plan_reasonable",
        "warning_flags",
        "next_safe_action",
    ]
    for key in keys:
        print(f"{key}={plan[key]}")
    print(f"output_path={output_path}")
    print(f"markdown_output_path={markdown_path}")


if __name__ == "__main__":
    raise SystemExit(main())
