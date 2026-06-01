"""CLI for fast Pump.fun regime census collection via getTransactionsForAddress."""

from __future__ import annotations

import argparse
from datetime import date

from research.mtp_research.ingestion.pumpfun_gtfa_census_collection import (
    collect_pumpfun_regime_census_with_gtfa,
)


def main() -> int:
    args = parse_args()
    summary = collect_pumpfun_regime_census_with_gtfa(
        output_path=args.output_path,
        csv_output_path=args.csv_output_path,
        checkpoint_path=args.checkpoint_path,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        target_regime_launches=args.target_regime_launches,
        page_limit=args.page_limit,
        max_pages_per_window=args.max_pages_per_window,
        execute=args.execute,
    )
    for key in [
        "method",
        "start_date",
        "end_date",
        "window_count",
        "target_regime_launches",
        "accepted_launches_existing",
        "accepted_regime_launches_existing",
        "estimated_request_cap",
        "network_calls",
        "transactions_seen",
        "accepted_regime_launches",
        "accepted_launches_total",
        "warning_flags",
        "output_path",
        "csv_output_path",
        "checkpoint_path",
    ]:
        if key in summary:
            print(f"{key}={summary[key]}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Pump.fun launch-regime census rows with Helius gTFA.")
    parser.add_argument("--start-date", required=True, help="PT date, YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="PT date, YYYY-MM-DD")
    parser.add_argument("--target-regime-launches", type=int, default=1500)
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--max-pages-per-window", type=int, default=100)
    parser.add_argument("--output-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--csv-output-path", default="data/normalized/pumpfun_creation_census.csv")
    parser.add_argument(
        "--checkpoint-path",
        default="data/backtests/diagnostics/reports/pumpfun_gtfa_regime_census_checkpoint.json",
    )
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
