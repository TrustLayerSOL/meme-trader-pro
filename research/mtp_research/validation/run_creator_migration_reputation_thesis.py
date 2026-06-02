"""CLI for the T008 creator migration reputation descriptive thesis cycle."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.creator_migration_reputation_thesis import (
    build_t008_creator_migration_reputation_report,
    write_t008_report_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_OUTCOMES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_lifecycle_outcomes.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "combined_migration_graduation_labels.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T008_creator_migration_reputation"
)
DEFAULT_STATUS_PATH = "theses/T008_CREATOR_MIGRATION_REPUTATION_STATUS.md"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_t008_creator_migration_reputation_report(
        candidates_path=args.candidates_path,
        outcomes_path=args.outcomes_path,
        migration_labels_path=args.migration_labels_path,
        dataset_scope=args.dataset_scope,
    )
    paths = write_t008_report_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"dataset_scope={report['dataset']['dataset_scope']}")
    print(f"launch_count={report['sample_counts']['launch_count']}")
    print(f"primary_bucket_counts={report['feature_audit']['primary_bucket_counts']}")
    print(f"migration_vs_raw_launch_count_read={report['migration_vs_raw_launch_count_read']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run descriptive T008 Creator Migration Reputation thesis cycle."
    )
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--dataset-scope", default="all_collected")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
