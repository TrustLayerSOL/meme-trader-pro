"""CLI for timestamp-compatible SOL/USD collection."""

from __future__ import annotations

import argparse

from research.mtp_research.launch_regime.sol_usd_collection import collect_sol_usd_prices


def main() -> int:
    args = parse_args()
    report = collect_sol_usd_prices(
        input_paths=args.input_path,
        output_path=args.output_path,
        execute=args.execute,
    )
    for key in (
        "execute",
        "start_ts",
        "end_ts",
        "price_rows_written",
        "network_calls",
        "output_path",
        "warning_flags",
    ):
        print(f"{key}={report[key]}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SOL/USD prices for lifecycle valuation timestamps.")
    parser.add_argument("--input-path", action="append", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
