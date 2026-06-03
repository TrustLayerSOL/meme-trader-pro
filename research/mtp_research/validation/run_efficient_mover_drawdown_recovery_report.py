"""CLI for efficient-mover drawdown recovery report."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.efficient_mover_drawdown_recovery_report import (
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOTS_PATH,
    DEFAULT_STATUS_PATH,
    build_efficient_mover_drawdown_recovery_report,
)


def main() -> int:
    args = parse_args()
    report, paths = build_efficient_mover_drawdown_recovery_report(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        snapshots_path=Path(args.snapshots_path),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    trailing = report["trailing_stop_30pct_diagnostic"]
    print(f"report_id={report['report_id']}")
    print(f"efficient_mover_rows={report['efficient_mover_universe']['rows']}")
    print(f"drawdown_event_counts_by_level={report['drawdown_event_counts_by_level']}")
    print(f"drawdown_30pct_events={trailing['drawdown_30pct_events']}")
    print(f"drawdown_30pct_recoverable={trailing['recoverable_count']}")
    print(f"drawdown_30pct_terminal={trailing['terminal_count']}")
    print(f"drawdown_30pct_data_limited={trailing['data_limited_count']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_markdown_path']}")
    print(f"drawdown_events_path={paths['drawdown_events_path']}")
    print(f"recoverable_vs_terminal_features_path={paths['recoverable_vs_terminal_features_path']}")
    print(f"trailing_stop_30pct_diagnostic_path={paths['trailing_stop_30pct_diagnostic_path']}")
    print(f"exit_side_candidate_features_path={paths['exit_side_candidate_features_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run efficient-mover drawdown recovery report.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
