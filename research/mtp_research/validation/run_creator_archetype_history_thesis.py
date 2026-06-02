"""CLI for the T003 creator-archetype history descriptive thesis cycle."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.creator_archetype_history_thesis import (
    build_t003_creator_archetype_report,
    write_t003_report_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_valuation_enriched",
    "launch_lifecycle_snapshots_valuation_enriched.jsonl",
)
DEFAULT_OUTCOMES_PATH = data_lake_path(
    "data",
    "normalized",
    "launch_regime_valuation_enriched",
    "launch_lifecycle_outcomes_valuation_enriched.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "T003_creator_archetype_history"
)
DEFAULT_STATUS_PATH = "theses/T003_CREATOR_ARCHETYPE_HISTORY_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t003_creator_archetype_report(
        candidates_path=args.candidates_path,
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        bucket_count=args.bucket_count,
    )
    paths = write_t003_report_outputs(report, output_dir=args.output_dir, status_path=args.status_path)
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launch_count={report['sample_counts']['launch_count']}")
    print(f"creator_count={report['creator_counts']['creator_count']}")
    print(f"repeat_creator_count={report['creator_counts']['repeat_creator_count']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run descriptive T003 Creator Archetype History thesis cycle."
    )
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--bucket-count", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
