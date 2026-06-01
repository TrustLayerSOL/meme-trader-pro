"""CLI for offline launch lifecycle valuation enrichment."""

from __future__ import annotations

import argparse

from research.mtp_research.launch_regime.valuation_enrichment import run_valuation_enrichment


def main() -> int:
    args = parse_args()
    report = run_valuation_enrichment(
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        output_dir=args.output_dir,
    )
    for key in (
        "snapshot_count",
        "outcome_count",
        "true_market_cap_available_count",
        "fdv_available_count",
        "valuation_proxy_available_count",
        "bonding_curve_liquidity_proxy_available_count",
        "threshold_outcomes_usable_count",
        "price_sol_available_count",
        "price_usd_available_count",
        "supply_available_count",
        "sol_usd_available_count",
        "valuation_missing_reason_counts",
        "threshold_outcomes_missing_reason_counts",
        "snapshot_output_path",
        "outcome_output_path",
        "network_calls",
    ):
        print(f"{key}={report[key]}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich launch lifecycle artifacts with conservative valuation fields.")
    parser.add_argument("--snapshots-path", required=True)
    parser.add_argument("--outcomes-path", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
