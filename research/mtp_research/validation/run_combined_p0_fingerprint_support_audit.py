"""CLI for combined P0 fingerprint support/coverage audit."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from research.mtp_research.validation.combined_p0_fingerprint_support_audit import (
    DEFAULT_COMBINED_DATASET_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SELECTION_SUMMARY_PATH,
    DEFAULT_STATUS_PATH,
    build_combined_p0_fingerprint_support_audit,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report, paths = build_combined_p0_fingerprint_support_audit(
        selection_summary_path=args.selection_summary_path,
        combined_dataset_path=args.combined_dataset_path,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"fingerprints_audited={len(report['fingerprint_audits'])}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run combined P0 fingerprint support audit.")
    parser.add_argument("--selection-summary-path", default=DEFAULT_SELECTION_SUMMARY_PATH, type=Path)
    parser.add_argument("--combined-dataset-path", default=DEFAULT_COMBINED_DATASET_PATH, type=Path)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH, type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
