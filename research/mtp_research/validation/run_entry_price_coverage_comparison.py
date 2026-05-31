"""CLI for clean-vs-nearest-fallback entry price coverage comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.validation.entry_price_coverage_report import (
    compare_entry_price_coverage,
    write_entry_price_comparison_json,
    write_entry_price_comparison_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare clean and diagnostic fallback outcome labels.")
    parser.add_argument("--clean-outcomes-path", default="data/backtests/outcome_labels.jsonl")
    parser.add_argument("--fallback-outcomes-path", default="data/backtests/diagnostics/outcome_labels_nearest300.jsonl")
    parser.add_argument("--clean-dataset-path", default="data/backtests/research_dataset.jsonl")
    parser.add_argument("--fallback-dataset-path", default="data/backtests/diagnostics/research_dataset_nearest300.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    args = parser.parse_args()

    report = compare_entry_price_coverage(
        args.clean_outcomes_path,
        args.fallback_outcomes_path,
        clean_dataset_path=args.clean_dataset_path,
        fallback_dataset_path=args.fallback_dataset_path,
    )
    output_dir = Path(args.output_dir)
    markdown_path = write_entry_price_comparison_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_entry_price_comparison_json(report, output_dir / f"{report.report_id}.json")

    print(f"clean_labels_with_entry_price={report.clean_summary.labels_with_entry_price}")
    print(f"fallback_labels_with_entry_price={report.fallback_summary.labels_with_entry_price}")
    print(f"entry_price_gain={report.entry_price_gain}")
    print(f"forward_return_gain={report.forward_return_gain}")
    print(f"sparse_or_better_gain={report.sparse_or_better_gain}")
    print(f"no_price_reduction={report.no_price_reduction}")
    print(f"nearest_fallback_labels={report.fallback_summary.nearest_fallback_labels}")
    print(f"recommended_next_actions={report.recommended_next_actions}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
