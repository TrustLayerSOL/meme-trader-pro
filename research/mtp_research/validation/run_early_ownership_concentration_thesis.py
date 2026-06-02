"""CLI for the T001 early ownership concentration descriptive thesis cycle."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.early_ownership_concentration_thesis import (
    build_t001_early_ownership_report,
    write_t001_report_outputs,
)


DEFAULT_CANDIDATES_PATH = (
    "/Volumes/Polymarket Data/MemeTraderPro/data/normalized/"
    "launch_regime_classified/launch_regime_candidates.jsonl"
)
DEFAULT_EVENTS_PATH = (
    "/Volumes/Polymarket Data/MemeTraderPro/data/normalized/"
    "pumpfun_lifecycle_events_classified.jsonl"
)
DEFAULT_SNAPSHOTS_PATH = (
    "/Volumes/Polymarket Data/MemeTraderPro/data/normalized/"
    "launch_regime_valuation_enriched/launch_lifecycle_snapshots_valuation_enriched.jsonl"
)
DEFAULT_OUTCOMES_PATH = (
    "/Volumes/Polymarket Data/MemeTraderPro/data/normalized/"
    "launch_regime_valuation_enriched/launch_lifecycle_outcomes_valuation_enriched.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    "/Volumes/Polymarket Data/MemeTraderPro/data/backtests/diagnostics/reports/"
    "T001_early_ownership_concentration"
)
DEFAULT_STATUS_PATH = "theses/T001_EARLY_OWNERSHIP_CONCENTRATION_STATUS.md"


def main() -> int:
    args = parse_args()
    report = build_t001_early_ownership_report(
        candidates_path=args.candidates_path,
        events_path=args.events_path,
        snapshots_path=args.snapshots_path,
        outcomes_path=args.outcomes_path,
        bucket_count=args.bucket_count,
        observation_window_seconds=args.observation_window_seconds,
    )
    paths = write_t001_report_outputs(
        report,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    print(f"thesis_id={report['thesis_id']}")
    print(f"final_classification={report['final_classification']}")
    print(f"launch_count={report['sample_counts']['launch_count']}")
    print(f"warning_flags={report['warning_flags']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run descriptive T001 Early Ownership Concentration thesis cycle."
    )
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--events-path", default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--outcomes-path", default=DEFAULT_OUTCOMES_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    parser.add_argument("--bucket-count", type=int, default=5)
    parser.add_argument("--observation-window-seconds", type=int, default=120)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
