"""CLI for expanded T011 descriptive rerun."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.t011_expanded_rerun import (
    DEFAULT_ENTITY_PROXY_PATH,
    DEFAULT_FUNDING_LINK_PATH,
    DEFAULT_HOLDER_STATE_PATH,
    DEFAULT_MIGRATION_LABELS_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOT_PATHS,
    build_t011_expanded_rerun_report,
)


def main() -> int:
    args = parse_args()
    snapshot_paths = args.snapshot_path or [str(path) for path in DEFAULT_SNAPSHOT_PATHS]
    report, paths = build_t011_expanded_rerun_report(
        snapshot_paths=[Path(item) for item in snapshot_paths],
        output_dir=args.output_dir,
        holder_state_snapshots_path=_optional(args.holder_state_snapshots_path),
        entity_proxy_path=_optional(args.entity_proxy_path),
        migration_labels_path=_optional(args.migration_labels_path),
        funding_link_path=_optional(args.funding_link_path),
    )
    audit = report["expanded_dataset_audit"]
    print(f"report_id={report['report_id']}")
    print(f"expanded_launch_count={audit['total_launches']}")
    print(f"expanded_20k_trigger_count={audit['trigger_counts']['20k']}")
    print(f"expanded_unique_20k_trigger_dates={audit['unique_trigger_dates']['20k']}")
    print(f"expanded_t011_classification={report['t011_result']['classification']}")
    print(f"expanded_robustness_classification={report['robustness_result']['robustness_classification']}")
    print(f"low_flow_high_fdv_efficiency_survived={report['old_vs_expanded_comparison']['low_flow_high_fdv_efficiency_pattern_survived']}")
    print(f"validation_recommended={report['validation_recommended']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run expanded T011 descriptive rerun.")
    parser.add_argument("--snapshot-path", action="append", default=None)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--funding-link-path", default=DEFAULT_FUNDING_LINK_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def _optional(value: str | None) -> str | None:
    if not value:
        return None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
