"""CLI for formal T011 validation."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.t011_explosive_runner_validation import (
    build_t011_validation_report,
    write_t011_validation_outputs,
)


DEFAULT_DESIGN_PATH = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T011_validation_design", "T011_validation_design.json"
)
DEFAULT_T011_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "T011_explosive_runner_raw_flow")
DEFAULT_TRIGGER_ROWS_PATH = DEFAULT_T011_DIR / "trigger_20k_feature_rows.csv"
DEFAULT_T011_SUMMARY_PATH = DEFAULT_T011_DIR / "T011_explosive_runner_raw_flow_summary.json"
DEFAULT_ROBUSTNESS_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T011_explosive_runner_raw_flow_robustness",
    "T011_explosive_runner_raw_flow_robustness_summary.json",
)
DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "T011_validation")
DEFAULT_STATUS_PATH = "theses/T011_EXPLOSIVE_RUNNER_VALIDATION_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t011_validation_report(
        design_path=args.design_path,
        trigger_20k_rows_path=args.trigger_20k_rows_path,
        t011_summary_path=args.t011_summary_path,
        robustness_summary_path=args.robustness_summary_path,
        snapshots_path=args.snapshots_path,
    )
    paths = write_t011_validation_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"report_id={report['report_id']}")
    print(f"validation_classification={report['validation_classification']}")
    print(f"train_rows={report['primary_split']['train_rows']}")
    print(f"holdout_rows={report['primary_split']['holdout_rows']}")
    print(f"training_cutoffs={report['training_cutoffs']}")
    print(f"primary_group_support={report['primary_validation']['support_count']}")
    print(f"baseline_hit_rate={report['primary_validation']['baseline_holdout_hit_rate']}")
    print(f"primary_group_hit_rate={report['primary_validation']['primary_group_hit_rate']}")
    print(f"relative_lift={report['primary_validation']['relative_lift']}")
    print(f"leakage_checks_passed={report['leakage_checks']['all_checks_passed']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run formal T011 validation.")
    parser.add_argument("--design-path", default=DEFAULT_DESIGN_PATH)
    parser.add_argument("--trigger-20k-rows-path", default=DEFAULT_TRIGGER_ROWS_PATH)
    parser.add_argument("--t011-summary-path", default=DEFAULT_T011_SUMMARY_PATH)
    parser.add_argument("--robustness-summary-path", default=DEFAULT_ROBUSTNESS_SUMMARY_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
