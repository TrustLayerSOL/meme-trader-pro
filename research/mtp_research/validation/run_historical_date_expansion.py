"""CLI for historical date-expansion coverage sprint."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path, data_lake_root
from research.mtp_research.validation.historical_date_expansion import (
    build_historical_date_expansion,
    write_status_and_plan,
)


DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_valuation_enriched", "launch_regime_candidates.jsonl"
)
DEFAULT_OUTPUT_ROOT = data_lake_path("data", "backtests", "explosive_runner_expanded")
DEFAULT_REPORT_DIR = data_lake_path("data", "backtests", "diagnostics", "reports", "historical_date_expansion")
DEFAULT_STATUS_PATH = "theses/EXPLOSIVE_RUNNER_HISTORICAL_DATE_EXPANSION_STATUS.md"
DEFAULT_PLAN_PATH = "docs/research/MEMETRADER_EXPLOSIVE_RUNNER_HISTORICAL_EXPANSION_PLAN.md"


def main() -> int:
    args = parse_args()
    report = build_historical_date_expansion(
        snapshots_path=args.snapshots_path,
        candidates_path=args.candidates_path,
        output_root=args.output_root,
        report_dir=args.report_dir,
        data_lake_root=data_lake_root(),
    )
    paths = write_status_and_plan(report, status_path=args.status_path, plan_path=args.plan_path)
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"current_20k_trigger_dates={report['previous_20k_trigger_dates']}")
    print(f"expanded_20k_trigger_dates={report['expanded_20k_trigger_dates']}")
    print(f"current_20k_trigger_rows={report['previous_20k_trigger_rows']}")
    print(f"expanded_20k_trigger_rows={report['expanded_20k_trigger_rows']}")
    print(f"top_date_share={report['date_balance']['top_date_share']}")
    print(f"top3_date_share={report['date_balance']['top3_date_share']}")
    print(f"external_acquisition_required={report['external_acquisition_required']}")
    for key, path in report["report_paths"].items():
        print(f"{key}={path}")
    for key, path in report["expanded_paths"].items():
        print(f"{key}={path}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run historical date-expansion coverage audit.")
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--plan-path", default=DEFAULT_PLAN_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
