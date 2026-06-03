"""CLI for efficient-mover continuation anatomy report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.efficient_mover_continuation_anatomy import (
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_efficient_mover_continuation_anatomy,
)


def main() -> int:
    args = parse_args()
    report, paths = build_efficient_mover_continuation_anatomy(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    print(f"report_id={report['report_id']}")
    print(f"efficient_mover_rows={report['efficient_mover_universe']['rows']}")
    print(f"continuation_rows={report['continuation_vs_trap_counts']['continuation_rows']}")
    print(f"trap_or_stall_rows={report['continuation_vs_trap_counts']['trap_or_stall_rows']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"recommended_next_action={report['recommended_next_action']['choice']}:{report['recommended_next_action']['action']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"feature_comparison_path={paths['feature_comparison_path']}")
    print(f"candidate_filters_path={paths['candidate_filters_path']}")
    print(f"entry_vs_exit_features_path={paths['entry_vs_exit_features_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run efficient-mover continuation anatomy report.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
