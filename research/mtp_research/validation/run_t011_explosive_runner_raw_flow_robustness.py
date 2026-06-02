"""CLI for T011 raw-flow robustness review."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.t011_explosive_runner_raw_flow_robustness import (
    build_t011_raw_flow_robustness_report,
    write_t011_raw_flow_robustness_outputs,
)


DEFAULT_T011_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "T011_explosive_runner_raw_flow")
DEFAULT_T011_SUMMARY_PATH = DEFAULT_T011_DIR / "T011_explosive_runner_raw_flow_summary.json"
DEFAULT_TRIGGER_ROWS_PATH = DEFAULT_T011_DIR / "trigger_20k_feature_rows.csv"
DEFAULT_TIER_TABLE_PATH = DEFAULT_T011_DIR / "milestone_tier_feature_table.csv"
DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T011_explosive_runner_raw_flow_robustness"
)
DEFAULT_STATUS_PATH = "theses/T011_EXPLOSIVE_RUNNER_RAW_FLOW_ROBUSTNESS_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t011_raw_flow_robustness_report(
        t011_summary_path=args.t011_summary_path,
        trigger_20k_rows_path=args.trigger_20k_rows_path,
        snapshots_path=args.snapshots_path,
        tier_table_path=args.tier_table_path,
    )
    paths = write_t011_raw_flow_robustness_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"report_id={report['report_id']}")
    print(f"original_t011_classification={report['original_t011_classification']}")
    print(f"robustness_classification={report['robustness_classification']}")
    print(f"trigger_20k_count_analyzed={report['trigger_20k_count_analyzed']}")
    print(f"validation_design_recommended={report['validation_design_recommended']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run T011 raw-flow robustness review.")
    parser.add_argument("--t011-summary-path", default=DEFAULT_T011_SUMMARY_PATH)
    parser.add_argument("--trigger-20k-rows-path", default=DEFAULT_TRIGGER_ROWS_PATH)
    parser.add_argument("--tier-table-path", default=DEFAULT_TIER_TABLE_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
