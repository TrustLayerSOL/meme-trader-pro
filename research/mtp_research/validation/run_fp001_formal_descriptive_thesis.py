"""CLI for FP001 formal descriptive thesis."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research.mtp_research.validation.fp001_formal_descriptive_thesis import (
    DEFAULT_COMBINED_DATASET_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    DEFAULT_SUPPORT_SUMMARY_PATH,
    build_fp001_formal_descriptive_thesis,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report, paths = build_fp001_formal_descriptive_thesis(
        support_summary_path=args.support_summary_path,
        combined_dataset_path=args.combined_dataset_path,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    print(f"report_id={report['report_id']}")
    print(f"classification={report['classification']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"rows_analyzed={report['rows_analyzed']}")
    coverage = report.get("feature_coverage", {})
    if coverage:
        print(f"rows_with_all_fp001_fields={coverage.get('rows_with_all_fp001_fields')}")
        print(f"feature_coverage_pct={coverage.get('coverage_pct')}")
    print(f"next_recommendation={report['next_recommendation']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FP001 formal descriptive thesis.")
    parser.add_argument("--support-summary-path", default=DEFAULT_SUPPORT_SUMMARY_PATH, type=Path)
    parser.add_argument("--combined-dataset-path", default=DEFAULT_COMBINED_DATASET_PATH, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH, type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
