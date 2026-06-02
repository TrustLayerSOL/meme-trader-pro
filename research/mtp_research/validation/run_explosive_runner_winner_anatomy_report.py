"""CLI for broad explosive-runner winner-anatomy report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.explosive_runner_winner_anatomy_report import (
    DEFAULT_ENTITY_PROXY_PATH,
    DEFAULT_FUNDING_LINK_PATH,
    DEFAULT_HOLDER_STATE_PATH,
    DEFAULT_MIGRATION_LABELS_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOT_PATHS,
    build_explosive_runner_winner_anatomy_report,
)


def main() -> int:
    args = parse_args()
    snapshot_paths = args.snapshot_path or [str(path) for path in DEFAULT_SNAPSHOT_PATHS]
    report, paths = build_explosive_runner_winner_anatomy_report(
        snapshot_paths=[Path(path) for path in snapshot_paths],
        output_dir=args.output_dir,
        status_path=args.status_path,
        holder_state_snapshots_path=_optional(args.holder_state_snapshots_path),
        entity_proxy_path=_optional(args.entity_proxy_path),
        migration_labels_path=_optional(args.migration_labels_path),
        funding_link_path=_optional(args.funding_link_path),
    )
    coverage = report["coverage_report"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_analyzed={coverage['total_launches']}")
    print(f"milestone_tier_counts={ {tier: data['launch_count'] for tier, data in report['milestone_tier_summary'].items()} }")
    print(f"holder_fdv_relationship_conclusion={report['holder_fdv_relationship_conclusion']['relationship_conclusion']}")
    print(f"recommended_next_theses={len(report['recommended_next_theses'])}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run broad explosive-runner winner-anatomy report.")
    parser.add_argument("--snapshot-path", action="append", default=None)
    parser.add_argument("--holder-state-snapshots-path", default=DEFAULT_HOLDER_STATE_PATH)
    parser.add_argument("--entity-proxy-path", default=DEFAULT_ENTITY_PROXY_PATH)
    parser.add_argument("--migration-labels-path", default=DEFAULT_MIGRATION_LABELS_PATH)
    parser.add_argument("--funding-link-path", default=DEFAULT_FUNDING_LINK_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default="theses/EXPLOSIVE_RUNNER_WINNER_ANATOMY_REPORT_STATUS.md")
    return parser.parse_args()


def _optional(value: str | None) -> str | None:
    return value or None


if __name__ == "__main__":
    raise SystemExit(main())
