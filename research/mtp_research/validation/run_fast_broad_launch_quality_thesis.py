"""CLI for the T009 fast + broad launch quality descriptive thesis."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.fast_broad_launch_quality_thesis import (
    build_t009_fast_broad_launch_quality_report,
    write_t009_report_outputs,
)


DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_OUTCOMES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_outcomes_valuation_enriched.jsonl",
)
DEFAULT_HOLDER_STATE_PATH = data_lake_path(
    "data",
    "backtests",
    "holder_state",
    "strict_cohort_holder_state_snapshots.jsonl",
)
DEFAULT_ENTITY_PROXY_PATH = data_lake_path(
    "data",
    "backtests",
    "entity_proxy",
    "entity_proxy_strict_cohort.jsonl",
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
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T009_fast_broad_launch_quality",
)
DEFAULT_STATUS_PATH = "theses/T009_FAST_BROAD_LAUNCH_QUALITY_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t009_fast_broad_launch_quality_report(
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        holder_state_snapshots_path=args.holder_state_snapshots_path,
        entity_proxy_path=args.entity_proxy_path,
        migration_labels_path=args.migration_labels_path,
        t005_summary_path=args.t005_summary_path,
        dataset_scope=args.dataset_scope,
    )
    paths = write_t009_report_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    primary = report["main_comparisons"]["fast_and_broad_vs_fast_and_narrow"]
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launch_count={report['sample_counts']['launch_count']}")
    print(f"speed_feature={report['selected_features']['speed_feature_used']}")
    print(f"breadth_feature={report['selected_features']['breadth_feature_used']}")
    print(f"interaction_group_counts={report['interaction_groups']['counts']}")
    print(f"fast_and_broad_outperformed_fast_and_narrow={primary.get('left_outperformed_descriptively')}")
    print(
        "t009_clearer_than_t005="
        f"{report['t005_baseline_comparison'].get('t009_provides_clearer_separation_than_t005_baseline')}"
    )
    print(f"chronological_robustness_recommended={report['chronological_robustness_recommended']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run descriptive T009 Fast + Broad Early Launch Quality thesis cycle."
    )
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--t005-summary-path", default=DEFAULT_T005_SUMMARY_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--dataset-scope", default="all_collected")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
