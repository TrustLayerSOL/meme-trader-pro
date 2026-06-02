"""CLI for the T010 funding lineage descriptive thesis."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.funding_lineage_thesis import (
    build_t010_funding_lineage_report,
    write_t010_report_outputs,
)


DEFAULT_FUNDING_LINK_PATH = data_lake_path(
    "data", "backtests", "funding_link", "funding_link_pilot.parquet"
)
DEFAULT_OUTCOMES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_outcomes_valuation_enriched.jsonl",
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data",
    "backtests",
    "migration_graduation",
    "combined_migration_graduation_labels_provenance_upgraded.jsonl",
)
DEFAULT_T005_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T005_buy_sell_flow_baseline",
    "T005_buy_sell_flow_baseline_summary.json",
)
DEFAULT_T008_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T008_creator_migration_reputation_robustness_after_provenance_confirmation",
    "T008_creator_migration_reputation_robustness_summary.json",
)
DEFAULT_T009_SUMMARY_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T009_fast_broad_launch_quality",
    "T009_fast_broad_launch_quality_summary.json",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T010_funding_lineage"
)
DEFAULT_STATUS_PATH = "theses/T010_FUNDING_LINEAGE_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t010_funding_lineage_report(
        funding_link_path=args.funding_link_path,
        outcomes_path=args.outcomes_path,
        migration_labels_path=args.migration_labels_path,
        t005_summary_path=args.t005_summary_path,
        t008_summary_path=args.t008_summary_path,
        t009_summary_path=args.t009_summary_path,
    )
    paths = write_t010_report_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    repeated = report["main_comparisons"]["repeated_funder_vs_no_repeated_funder"]
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launch_count={report['dataset']['launch_count']}")
    print(f"funding_source_coverage={report['funding_link_coverage']['funding_source_available_pct']}")
    print(f"repeated_funder_coverage={report['funding_link_coverage']['repeated_funder_pct']}")
    print(f"repeated_funder_outperformed={repeated.get('left_outperformed_descriptively')}")
    print(f"larger_funding_link_rollout_recommended={report['larger_funding_link_rollout_recommended']}")
    print(f"chronological_robustness_recommended={report['chronological_robustness_recommended']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run descriptive T010 Funding Lineage thesis cycle.")
    parser.add_argument("--funding-link-path", default=DEFAULT_FUNDING_LINK_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--t005-summary-path", default=DEFAULT_T005_SUMMARY_PATH)
    parser.add_argument("--t008-summary-path", default=DEFAULT_T008_SUMMARY_PATH)
    parser.add_argument("--t009-summary-path", default=DEFAULT_T009_SUMMARY_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
