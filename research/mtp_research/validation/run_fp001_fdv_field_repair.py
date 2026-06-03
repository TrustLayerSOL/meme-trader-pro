"""CLI for FP001 FDV-efficiency field repair."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research.mtp_research.validation.fp001_fdv_field_repair import (
    DEFAULT_COMBINED_DATASET_PATH,
    DEFAULT_FP001_OUTPUT_DIR,
    DEFAULT_FP001_STATUS_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPAIRED_JSONL_PATH,
    DEFAULT_REPAIRED_PARQUET_PATH,
    DEFAULT_SOURCE_PATHS,
    DEFAULT_STATUS_PATH,
    build_fp001_fdv_field_repair,
)
from research.mtp_research.validation.fp001_formal_descriptive_thesis import DEFAULT_SUPPORT_SUMMARY_PATH


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source_paths = args.source_path if args.source_path else DEFAULT_SOURCE_PATHS
    report, paths = build_fp001_fdv_field_repair(
        combined_dataset_path=args.combined_dataset_path,
        source_paths=source_paths,
        support_summary_path=args.support_summary_path,
        repaired_parquet_path=args.repaired_parquet_path,
        repaired_jsonl_path=args.repaired_jsonl_path,
        output_dir=args.output_dir,
        fp001_output_dir=args.fp001_output_dir,
        status_path=args.status_path,
        fp001_status_path=args.fp001_status_path,
    )
    join = report["join_audit"]
    print(f"report_id={report['report_id']}")
    print(f"repair_readiness={report['repair_readiness']}")
    print(f"source_file={report['source_paths']['selected_source_path']}")
    print(f"combined_rows_before_repair={join['combined_rows_before_repair']}")
    print(f"rows_matched={join['rows_matched_on_launch_id']}")
    print(f"rows_with_all_fp001_fields_after_repair={join['rows_with_all_fp001_fields_after_repair']}")
    print(f"fp001_rerun_executed={report['fp001_rerun']['rerun_executed']}")
    print(f"fp001_repaired_classification={report['fp001_rerun']['classification']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    for key, path in report.get("fp001_report_paths", {}).items():
        print(f"fp001_{key}={path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline FP001 FDV field repair.")
    parser.add_argument("--combined-dataset-path", default=DEFAULT_COMBINED_DATASET_PATH, type=Path)
    parser.add_argument("--source-path", action="append", default=None, type=Path)
    parser.add_argument("--support-summary-path", default=DEFAULT_SUPPORT_SUMMARY_PATH, type=Path)
    parser.add_argument("--repaired-parquet-path", default=DEFAULT_REPAIRED_PARQUET_PATH, type=Path)
    parser.add_argument("--repaired-jsonl-path", default=DEFAULT_REPAIRED_JSONL_PATH, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--fp001-output-dir", default=DEFAULT_FP001_OUTPUT_DIR, type=Path)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH, type=Path)
    parser.add_argument("--fp001-status-path", default=DEFAULT_FP001_STATUS_PATH, type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
