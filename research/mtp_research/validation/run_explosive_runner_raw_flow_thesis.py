"""CLI for T011 explosive-runner raw-flow continuation thesis."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.explosive_runner_raw_flow_thesis import (
    build_t011_explosive_runner_raw_flow_report,
    write_t011_explosive_runner_raw_flow_outputs,
)


DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_lifecycle_collected_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_HOLDER_STATE_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.jsonl"
)
DEFAULT_ENTITY_PROXY_PATH = data_lake_path(
    "data", "backtests", "entity_proxy", "entity_proxy_strict_cohort.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data",
    "backtests",
    "migration_graduation",
    "combined_migration_graduation_labels_provenance_upgraded.jsonl",
)
DEFAULT_FUNDING_LINK_PATH = data_lake_path(
    "data", "backtests", "funding_link", "funding_link_pilot.parquet"
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T011_explosive_runner_raw_flow"
)
DEFAULT_STATUS_PATH = "theses/T011_EXPLOSIVE_RUNNER_RAW_FLOW_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t011_explosive_runner_raw_flow_report(
        snapshots_path=args.snapshots_path,
        holder_state_snapshots_path=_optional(args.holder_state_snapshots_path),
        entity_proxy_path=_optional(args.entity_proxy_path),
        migration_labels_path=_optional(args.migration_labels_path),
        funding_link_path=_optional(args.funding_link_path),
    )
    paths = write_t011_explosive_runner_raw_flow_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"thesis_id={report['thesis_id']}")
    print(f"report_id={report['report_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launches_analyzed={report['dataset']['launches_analyzed']}")
    print(f"trigger_20k_count={report['trigger_summary']['trigger_20k_count']}")
    print(f"milestone_tier_counts={report['milestone_tier_counts']}")
    print(f"chronological_robustness_recommended={report['chronological_robustness_recommended']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run T011 explosive-runner raw-flow continuation thesis.")
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--funding-link-path", default=DEFAULT_FUNDING_LINK_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


def _optional(value: str | None) -> str | None:
    return value or None


if __name__ == "__main__":
    raise SystemExit(main())
