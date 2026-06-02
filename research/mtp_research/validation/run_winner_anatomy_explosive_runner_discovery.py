"""CLI for winner-anatomy explosive runner discovery."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.winner_anatomy_explosive_runner_discovery import (
    build_winner_anatomy_explosive_runner_report,
    write_winner_anatomy_outputs,
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
    "data", "backtests", "diagnostics", "reports", "T010_winner_anatomy_explosive_runners"
)
DEFAULT_STATUS_PATH = "theses/T010_WINNER_ANATOMY_EXPLOSIVE_RUNNERS_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_winner_anatomy_explosive_runner_report(
        snapshots_path=args.snapshots_path,
        holder_state_snapshots_path=args.holder_state_snapshots_path,
        entity_proxy_path=args.entity_proxy_path,
        migration_labels_path=args.migration_labels_path,
        funding_link_path=args.funding_link_path,
    )
    paths = write_winner_anatomy_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    counts = report["milestone_counts"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_analyzed={report['dataset']['launches_analyzed']}")
    print(f"trigger_20k_count={counts['trigger_20k_count']}")
    print(f"winner_50k_count={counts['crossed_50k_fdv_proxy']}")
    print(f"winner_100k_count={counts['crossed_100k_fdv_proxy']}")
    print(f"winner_200k_count={counts['crossed_200k_fdv_proxy']}")
    print(f"winner_500k_count={counts['crossed_500k_fdv_proxy']}")
    print(f"winner_1m_count={counts['crossed_1m_fdv_proxy']}")
    print(f"recommended_formal_thesis_next={report['recommended_formal_thesis_next']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run winner-anatomy explosive runner discovery.")
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--funding-link-path", default=DEFAULT_FUNDING_LINK_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
