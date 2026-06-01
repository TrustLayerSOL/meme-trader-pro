"""CLI for offline launch lifecycle quality audit."""

from __future__ import annotations

import argparse

from research.mtp_research.launch_regime.lifecycle_quality_audit import (
    DEFAULT_REPORT_DIR,
    run_launch_lifecycle_quality_audit,
)


def main() -> int:
    args = parse_args()
    report = run_launch_lifecycle_quality_audit(
        launches_path=args.launches_path,
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        events_path=args.events_path,
        raw_path=args.raw_path,
        output_dir=args.output_dir,
    )
    for key in (
        "launch_count",
        "snapshot_count",
        "outcome_count",
        "event_count",
        "unique_launch_mints",
        "unique_snapshot_mints",
        "unique_outcome_mints",
        "unique_event_mints",
        "event_venue_counts",
        "event_classification_counts",
        "launch_venue_counts",
        "launch_regime_counts",
        "program_id_counts",
        "per_launch_event_classification_coverage",
        "priced_snapshot_count",
        "zero_event_snapshot_count",
        "priced_outcome_count",
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
        "market_cap_unknown_outcome_count",
        "survived_counts",
        "event_max_age_bucket_counts",
        "top_unknown_instruction_clusters",
        "warning_flags",
        "network_calls",
    ):
        print(f"{key}={report[key]}")
    print(f"json_report_path={args.output_dir}/launch_lifecycle_quality_audit.json")
    print(f"markdown_report_path={args.output_dir}/launch_lifecycle_quality_audit.md")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit launch lifecycle artifacts without network calls.")
    parser.add_argument("--launches-path", required=True)
    parser.add_argument("--snapshots-path", required=True)
    parser.add_argument("--outcomes-path", required=True)
    parser.add_argument("--events-path", required=True)
    parser.add_argument("--raw-path")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
