"""CLI for the non-FDV incremental information audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.non_fdv_incremental_information_audit import (
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_non_fdv_incremental_information_audit,
)


def main() -> int:
    args = parse_args()
    report, paths = build_non_fdv_incremental_information_audit(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    print(f"report_id={report['report_id']}")
    print(f"rows_analyzed={report['rows_analyzed']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"recommendation={report['recommendation']['next_step']}")
    print(f"features_adding_incremental_information={report['recommendation']['features_adding_incremental_information']}")
    print(f"risk_filter_candidates={report['recommendation']['risk_filter_candidates']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"non_fdv_feature_incremental_rank_path={paths['non_fdv_feature_incremental_rank_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run non-FDV incremental information audit.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
