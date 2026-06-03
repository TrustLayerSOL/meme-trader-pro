"""CLI for FRP-001 formal descriptive thesis."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.frp001_formal_descriptive_thesis import (
    DEFAULT_CANDIDATE_FINGERPRINTS_PATH,
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_frp001_formal_descriptive_thesis,
)


def main() -> int:
    args = parse_args()
    report, paths = build_frp001_formal_descriptive_thesis(
        candidate_fingerprints_path=Path(args.candidate_fingerprints_path),
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    print(f"report_id={report['report_id']}")
    print(f"fingerprint_id={(report.get('frozen_definition') or {}).get('fingerprint_id')}")
    print(f"classification={report['classification']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"rows_analyzed={report['rows_analyzed']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"frp002_runs={report['guardrails']['frp002_runs']}")
    print(f"next_recommendation={report['next_recommendation']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"tier_support_table_path={paths['tier_support_table_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FRP-001 formal descriptive thesis.")
    parser.add_argument("--candidate-fingerprints-path", default=DEFAULT_CANDIDATE_FINGERPRINTS_PATH)
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
