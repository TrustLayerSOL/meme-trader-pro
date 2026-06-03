"""CLI for the final broad runner-fingerprint report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.final_runner_fingerprint_report import (
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_final_runner_fingerprint_report,
)


def main() -> int:
    args = parse_args()
    report, paths = build_final_runner_fingerprint_report(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"rows_analyzed={report['dataset']['rows_analyzed']}")
    print(f"candidate_fingerprints={len(report['candidate_fingerprints'])}")
    print(f"recommendation={report['recommendation']['next_step']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"candidate_fingerprints_path={paths['candidate_fingerprints_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run final broad runner-fingerprint report.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
