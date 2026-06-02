"""CLI for short-window expansion discovery labels and reports."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.short_window_expansion_discovery import (
    build_short_window_expansion_discovery_report,
    write_short_window_expansion_outputs,
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
    "data", "backtests", "diagnostics", "reports", "short_window_expansion_discovery"
)
DEFAULT_STATUS_PATH = "theses/SHORT_WINDOW_EXPANSION_DISCOVERY_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_short_window_expansion_discovery_report(
        snapshots_path=args.snapshots_path,
        holder_state_snapshots_path=args.holder_state_snapshots_path,
        entity_proxy_path=args.entity_proxy_path,
        migration_labels_path=args.migration_labels_path,
        funding_link_path=args.funding_link_path,
    )
    paths = write_short_window_expansion_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    label_20 = report["label_summary"]["trigger_20k"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_analyzed={report['dataset']['launches_analyzed']}")
    print(f"trigger_15k_count={report['trigger_feasibility']['trigger_15k']['launches_with_trigger']}")
    print(f"trigger_20k_count={report['trigger_feasibility']['trigger_20k']['launches_with_trigger']}")
    print(f"trigger_30k_count={report['trigger_feasibility']['trigger_30k']['launches_with_trigger']}")
    print(f"hit_50k_within_5m_count={label_20['hit_50k_within_5m_count']}")
    print(f"hit_100k_within_10m_count={label_20['hit_100k_within_10m_count']}")
    print(f"hit_2x_before_down_30pct_count={label_20['hit_2x_before_down_30pct_count']}")
    print(f"fast_narrow_vs_fast_broad={report['pattern_discovery']['fast_narrow_vs_fast_broad']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build short-window expansion diagnostic labels.")
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
