"""CLI for bounded parallel historical date-sharded acquisition."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.parallel_historical_date_acquisition import (
    DEFAULT_CENSUS_PATH,
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_CSV_PATH,
    DEFAULT_EXISTING_CENSUS_PATH,
    DEFAULT_RAW_DIR,
    DEFAULT_REPORT_DIR,
    run_parallel_historical_date_acquisition,
)


def main() -> int:
    args = parse_args()
    result = run_parallel_historical_date_acquisition(
        existing_census_path=args.existing_census_path,
        output_paths={
            "census_path": args.census_path,
            "csv_path": args.csv_path,
            "raw_dir": args.raw_dir,
            "checkpoint_path": args.checkpoint_path,
            "report_dir": args.report_dir,
        },
        target_dates=args.target_date,
        target_date_count=args.target_date_count,
        max_pages_per_window=args.max_pages_per_window,
        page_limit=args.page_limit,
        request_ceiling=args.request_ceiling,
        hard_stop_projected_requests=args.hard_stop_projected_requests,
        execute=args.execute,
        shard_workers=args.shard_workers,
    )
    _print_summary(result)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded parallel historical date acquisition pilot.")
    parser.add_argument("--existing-census-path", default=str(DEFAULT_EXISTING_CENSUS_PATH))
    parser.add_argument("--census-path", default=str(DEFAULT_CENSUS_PATH))
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH))
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--checkpoint-path", default=str(DEFAULT_CHECKPOINT_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--target-date", action="append", help="PT date YYYY-MM-DD. Repeatable.")
    parser.add_argument("--target-date-count", type=int, default=6)
    parser.add_argument("--max-pages-per-window", type=int, default=2)
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--request-ceiling", type=int, default=50)
    parser.add_argument("--hard-stop-projected-requests", type=int, default=100)
    parser.add_argument("--shard-workers", type=int, default=4)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _print_summary(result: dict) -> None:
    collection = result.get("collection", {})
    requests = result.get("requests", {})
    for key in [
        "readiness_classification",
        "method",
        "selected_dates",
    ]:
        print(f"{key}={result.get(key)}")
    print(f"mode={result.get('execution', {}).get('mode')}")
    print(f"projected_requests={requests.get('projected_requests')}")
    print(f"request_ceiling_status={requests.get('request_ceiling_status')}")
    print(f"requests_used={requests.get('requests_used', 0)}")
    print(f"dates_completed={collection.get('dates_completed', 0)}")
    print(f"transactions_seen={collection.get('transactions_seen', 0)}")
    print(f"accepted_added={collection.get('accepted_added', 0)}")
    print(f"merged_census_rows={collection.get('merged_census_rows', 0)}")
    print(f"census_path={result.get('outputs', {}).get('census_path')}")
    print(f"raw_dir={result.get('outputs', {}).get('raw_dir')}")
    print(f"report_dir={result.get('outputs', {}).get('report_dir')}")
    print(f"recommended_next_command={result.get('recommended_next_command')}")
    print(f"warnings={result.get('warnings', [])}")


if __name__ == "__main__":
    raise SystemExit(main())
