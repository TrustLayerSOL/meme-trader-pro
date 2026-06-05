"""CLI for baseline-vs-filter actionable-20k audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.baseline_vs_filter_audit import run_baseline_vs_filter_audit


def main() -> int:
    args = parse_args()
    result = run_baseline_vs_filter_audit(
        data_root=Path(args.data_root).expanduser() if args.data_root else None,
        source_report_root=Path(args.source_report_root).expanduser() if args.source_report_root else None,
        execute=args.execute,
    )
    print("## Baseline Vs Filter Audit")
    print(f"execute={result.get('execute')}")
    print(f"audit_label={result.get('audit_label')}")
    print(f"source_report_root={result.get('source_report_root')}")
    print(f"baseline_actionable_crossed_20k_count={result.get('baseline_actionable_crossed_20k_count')}")
    print(f"all_crossed_20k_count={result.get('all_crossed_20k_count')}")
    print(f"filter_pass_counts={result.get('filter_pass_counts')}")
    print(f"best_exit_candidate_on_baseline={result.get('best_exit_candidate_on_baseline')}")
    print(f"recommendation={result.get('recommendation')}")
    print(f"disabled_config_path={result.get('disabled_config_path')}")
    print(f"status_file={result.get('status_file')}")
    print(f"readiness={result.get('readiness')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline-vs-filter audit for actionable crossed-20k mints.")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--source-report-root", default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
