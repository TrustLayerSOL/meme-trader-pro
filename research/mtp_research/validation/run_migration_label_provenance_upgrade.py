"""CLI for offline migration-label provenance upgrade audit."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.migration_label_provenance_upgrade import (
    build_migration_label_provenance_upgrade_report,
    write_migration_label_provenance_upgrade_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data", "backtests", "migration_graduation", "combined_migration_graduation_labels.jsonl"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "migration_label_provenance_upgrade"
)
DEFAULT_STATUS_PATH = "theses/MIGRATION_LABEL_PROVENANCE_UPGRADE_STATUS.md"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_migration_label_provenance_upgrade_report(
        candidates_path=args.candidates_path,
        migration_labels_path=args.migration_labels_path,
        max_targets=args.max_targets,
    )
    paths = write_migration_label_provenance_upgrade_outputs(
        report,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"positive_label_count={report['scope']['positive_label_count']}")
    print(f"source_quality_counts={report['source_quality_counts']}")
    print(f"selected_targets={report['acquisition_plan']['selected_target_count']}")
    print(f"estimated_high_requests={report['acquisition_plan']['estimated_request_equivalent_calls']['high']}")
    print(f"network_calls_made={report['acquisition_plan']['network_calls_made']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline migration-label provenance upgrade audit.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--max-targets", type=int, default=250)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
