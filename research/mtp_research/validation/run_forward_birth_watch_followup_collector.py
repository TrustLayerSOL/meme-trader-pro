"""CLI for bounded Pump.fun birth-watch follow-up collection."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.forward_birth_watch_followup_collector import (
    run_birth_watch_followup_collection,
)


def main() -> int:
    args = parse_args()
    result = run_birth_watch_followup_collection(
        args.data_root,
        max_mints=args.max_mints,
        signatures_per_mint=args.signatures_per_mint,
        transactions_per_mint=args.transactions_per_mint,
        request_ceiling=args.request_ceiling,
        freshness_run_id=args.freshness_run_id,
        execute=args.execute,
    )
    print(f"report_id={result['report_id']}")
    print(f"execute={result['execute']}")
    print(f"selected_mint_count={result['selected_mint_count']}")
    print(f"freshness_run_id={result.get('freshness_run_id')}")
    print(f"projected_requests={result['projected_requests']}")
    print(f"request_ceiling_status={result['request_ceiling_status']}")
    print(f"network_calls_made={result['network_calls_made']}")
    print(f"rows_written={result['rows_written']}")
    print(f"mints_with_fdv_followup={result['mints_with_fdv_followup']}")
    print(f"mints_with_trigger_followup={result['mints_with_trigger_followup']}")
    print(f"warnings={result['warnings']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded birth-watch mint follow-up collection.")
    parser.add_argument("--data-root", default="/Volumes/ORICO/MemeTraderPro")
    parser.add_argument("--max-mints", type=int, default=10)
    parser.add_argument("--signatures-per-mint", type=int, default=10)
    parser.add_argument("--transactions-per-mint", type=int, default=10)
    parser.add_argument("--request-ceiling", type=int, default=250)
    parser.add_argument("--freshness-run-id")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
