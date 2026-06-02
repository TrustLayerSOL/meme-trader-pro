"""CLI for the combined aligned P0 structural fingerprint report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research.mtp_research.validation.combined_aligned_p0_fingerprint_report import (
    DEFAULT_BALANCED_STRUCTURAL_PATH,
    DEFAULT_DATASET_JSONL_PATH,
    DEFAULT_DATASET_PARQUET_PATH,
    DEFAULT_ORIGINAL_STRUCTURAL_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REMAINING_STRUCTURAL_PATH,
    DEFAULT_STATUS_PATH,
    build_combined_aligned_p0_fingerprint_report,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report, paths = build_combined_aligned_p0_fingerprint_report(
        original_structural_path=args.original_structural_path,
        balanced_structural_path=args.balanced_structural_path,
        remaining_structural_path=args.remaining_structural_path,
        output_dir=args.output_dir,
        dataset_parquet_path=args.dataset_parquet_path,
        dataset_jsonl_path=args.dataset_jsonl_path,
        status_path=args.status_path,
    )
    coverage = report["coverage_audit"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"combined_unique_rows={coverage['total_unique_launches']}")
    print(f"all_three_p0_rows={coverage['all_three_p0_launches']}")
    print(f"balanced_sample_rows={coverage['balanced_sample_rows']}")
    print(f"leftover_sample_rows={coverage['leftover_sample_rows']}")
    print(f"next_recommendation={report['next_recommendation']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the combined aligned P0 structural fingerprint dataset and report."
    )
    parser.add_argument("--original-structural-path", default=DEFAULT_ORIGINAL_STRUCTURAL_PATH, type=Path)
    parser.add_argument("--balanced-structural-path", default=DEFAULT_BALANCED_STRUCTURAL_PATH, type=Path)
    parser.add_argument("--remaining-structural-path", default=DEFAULT_REMAINING_STRUCTURAL_PATH, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--dataset-parquet-path", default=DEFAULT_DATASET_PARQUET_PATH, type=Path)
    parser.add_argument("--dataset-jsonl-path", default=DEFAULT_DATASET_JSONL_PATH, type=Path)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH, type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
