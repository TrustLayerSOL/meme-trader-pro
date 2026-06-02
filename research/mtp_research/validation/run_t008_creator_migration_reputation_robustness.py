"""CLI for T008 creator migration reputation robustness review."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.t008_creator_migration_reputation_robustness import (
    build_t008_creator_migration_reputation_robustness_report,
    write_t008_robustness_outputs,
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
    "data", "backtests", "diagnostics", "reports", "T008_creator_migration_reputation_robustness"
)
DEFAULT_STATUS_PATH = "theses/T008_CREATOR_MIGRATION_REPUTATION_ROBUSTNESS_STATUS.md"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_t008_creator_migration_reputation_robustness_report(
        candidates_path=args.candidates_path,
        outcomes_path=args.outcomes_path,
        migration_labels_path=args.migration_labels_path,
        min_split_bucket_count=args.min_split_bucket_count,
        data_limited_min_launches=args.data_limited_min_launches,
    )
    paths = write_t008_robustness_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"report_id={report['report_id']}")
    print(f"original_t008_classification={report['original_t008_classification']}")
    print(f"robustness_classification={report['robustness_classification']}")
    print(f"launch_count={report['launch_count']}")
    print(f"full_sample_direction={report['full_sample_direction']}")
    print(f"validation_recommended={report['validation_recommended']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T008 Creator Migration Reputation robustness review."
    )
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--min-split-bucket-count", type=int, default=25)
    parser.add_argument("--data-limited-min-launches", type=int, default=100)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
