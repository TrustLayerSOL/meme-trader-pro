"""CLI for the T004 liquidity-persistence descriptive thesis cycle."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.liquidity_persistence_thesis import (
    build_t004_liquidity_persistence_report,
    write_t004_report_outputs,
)


DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_OUTCOMES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_valuation_enriched",
    "launch_lifecycle_outcomes_valuation_enriched.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T004_liquidity_persistence"
)
DEFAULT_STATUS_PATH = "theses/T004_LIQUIDITY_PERSISTENCE_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t004_liquidity_persistence_report(
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        bucket_count=args.bucket_count,
    )
    paths = write_t004_report_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launch_count={report['sample_counts']['launch_count']}")
    print(f"liquidity_proxy_source={report['liquidity_proxy_semantics']['dominant_source']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run descriptive T004 Liquidity Persistence thesis cycle."
    )
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--bucket-count", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
