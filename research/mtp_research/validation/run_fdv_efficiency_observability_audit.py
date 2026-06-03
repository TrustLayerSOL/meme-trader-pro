"""CLI for the FDV-efficiency observability audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.fdv_efficiency_observability_audit import (
    DEFAULT_MASTER_JSONL_PATH,
    DEFAULT_MASTER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SNAPSHOTS_PATH,
    DEFAULT_STATUS_PATH,
    DEFAULT_TRIGGER_20K_PATH,
    build_fdv_efficiency_observability_audit,
)


def main() -> int:
    args = parse_args()
    report, paths = build_fdv_efficiency_observability_audit(
        master_path=Path(args.master_path),
        jsonl_fallback=Path(args.jsonl_fallback),
        snapshots_path=Path(args.snapshots_path),
        trigger_20k_path=Path(args.trigger_20k_path),
        output_dir=Path(args.output_dir),
        status_path=Path(args.status_path),
    )
    action_20k_100k = next(
        (row for row in report["actionability_window_summary"] if row["trigger_level"] == "20k" and row["target_level"] == "100k"),
        {},
    )
    action_20k_500k = next(
        (row for row in report["actionability_window_summary"] if row["trigger_level"] == "20k" and row["target_level"] == "500k"),
        {},
    )
    print(f"report_id={report['report_id']}")
    print(f"rows_analyzed={report['rows_analyzed']}")
    print(f"validation_runs={report['guardrails']['validation_runs']}")
    print(f"thesis_runs={report['guardrails']['thesis_runs']}")
    print(f"classification={report['classification']}")
    print(f"trigger_levels_available={list(report['observability_coverage_by_trigger'].keys())}")
    print(f"median_20k_to_100k_seconds={action_20k_100k.get('median_time_seconds')}")
    print(f"median_20k_to_500k_seconds={action_20k_500k.get('median_time_seconds')}")
    print(f"summary_json_path={paths['summary_json_path']}")
    print(f"summary_markdown_path={paths['summary_md_path']}")
    print(f"trigger_observability_path={paths['trigger_observability_path']}")
    print(f"actionability_windows_path={paths['actionability_windows_path']}")
    print(f"snapshot_latency_path={paths['snapshot_latency_path']}")
    print(f"status_path={paths['status_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FDV-efficiency observability audit.")
    parser.add_argument("--master-path", default=DEFAULT_MASTER_PATH)
    parser.add_argument("--jsonl-fallback", default=DEFAULT_MASTER_JSONL_PATH)
    parser.add_argument("--snapshots-path", default=DEFAULT_SNAPSHOTS_PATH)
    parser.add_argument("--trigger-20k-path", default=DEFAULT_TRIGGER_20K_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
