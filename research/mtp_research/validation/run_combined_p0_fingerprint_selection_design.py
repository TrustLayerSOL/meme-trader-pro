"""CLI for combined P0 fingerprint selection/design report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research.mtp_research.validation.combined_p0_fingerprint_selection_design import (
    DEFAULT_CANDIDATE_FINGERPRINTS_PATH,
    DEFAULT_COMBINED_DATASET_PATH,
    DEFAULT_ENTRY_VS_EXIT_FEATURES_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    DEFAULT_SUMMARY_PATH,
    DEFAULT_TIER_FEATURE_COMPARISON_PATH,
    build_combined_p0_fingerprint_selection_design,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report, paths = build_combined_p0_fingerprint_selection_design(
        summary_path=args.summary_path,
        tier_feature_comparison_path=args.tier_feature_comparison_path,
        entry_vs_exit_features_path=args.entry_vs_exit_features_path,
        candidate_fingerprints_path=args.candidate_fingerprints_path,
        combined_dataset_path=args.combined_dataset_path,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    selected = [row["fingerprint_id"] for row in report["selected_candidate_fingerprints"]]
    deferred = [row["fingerprint_id"] for row in report["rejected_or_deferred_fingerprints"]]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"selected_fingerprints={selected}")
    print(f"deferred_fingerprints={deferred}")
    print(f"immediate_next_action={report['immediate_next_action']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create combined P0 fingerprint selection/design report.")
    parser.add_argument("--summary-path", default=DEFAULT_SUMMARY_PATH, type=Path)
    parser.add_argument("--tier-feature-comparison-path", default=DEFAULT_TIER_FEATURE_COMPARISON_PATH, type=Path)
    parser.add_argument("--entry-vs-exit-features-path", default=DEFAULT_ENTRY_VS_EXIT_FEATURES_PATH, type=Path)
    parser.add_argument("--candidate-fingerprints-path", default=DEFAULT_CANDIDATE_FINGERPRINTS_PATH, type=Path)
    parser.add_argument("--combined-dataset-path", default=DEFAULT_COMBINED_DATASET_PATH, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH, type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
