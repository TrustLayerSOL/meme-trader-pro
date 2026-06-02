"""CLI for repeated-buyer runner participation descriptive report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.repeated_buyer_runner_participation_report import (
    DEFAULT_EVENT_PATHS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOT_PATHS,
    build_repeated_buyer_runner_participation_report,
)


def main() -> int:
    args = parse_args()
    snapshot_paths = args.snapshot_path or [str(path) for path in DEFAULT_SNAPSHOT_PATHS]
    event_paths = args.event_path or [str(path) for path in DEFAULT_EVENT_PATHS]
    report, paths = build_repeated_buyer_runner_participation_report(
        snapshot_paths=[Path(path) for path in snapshot_paths],
        event_paths=[Path(path) for path in event_paths],
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    coverage = report["coverage_report"]
    tiers = {tier: values["launch_count"] for tier, values in report["milestone_tier_summary"].items()}
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_analyzed={coverage['total_launches']}")
    print(f"early_buyer_coverage={coverage['before_20k_early_buyer_coverage_pct']}")
    print(f"repeated_buyer_coverage={coverage['before_20k_repeated_runner_buyer_coverage_pct']}")
    print(f"milestone_tier_counts={tiers}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repeated-buyer runner participation report.")
    parser.add_argument("--snapshot-path", action="append", default=None)
    parser.add_argument("--event-path", action="append", default=None)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default="theses/REPEATED_BUYER_RUNNER_PARTICIPATION_STATUS.md")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
