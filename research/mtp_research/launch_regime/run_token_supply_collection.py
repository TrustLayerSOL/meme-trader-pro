"""CLI for bounded token-supply collection."""

from __future__ import annotations

import argparse

from research.mtp_research.launch_regime.token_supply_collection import collect_token_supply


def main() -> int:
    args = parse_args()
    report = collect_token_supply(
        launches_path=args.launches_path,
        output_path=args.output_path,
        execute=args.execute,
        limit=args.limit,
        request_pause_seconds=args.request_pause_seconds,
        workers=args.workers,
    )
    for key in (
        "execute",
        "mints_planned",
        "supply_rows_written",
        "failure_count",
        "failures",
        "network_calls",
        "output_path",
    ):
        if key in report:
            print(f"{key}={report[key]}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect token supply rows for lifecycle valuation.")
    parser.add_argument("--launches-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--request-pause-seconds", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
