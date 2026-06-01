"""Summarize manually reviewed Pump.fun parser precision labels."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.pumpfun_precision_audit import (
    precision_summary,
    write_precision_summary,
    write_precision_summary_markdown,
)


def main() -> int:
    args = parse_args()
    summary = precision_summary(args.census_path, args.review_path)
    output = write_precision_summary(summary, args.output_path)
    markdown_output = write_precision_summary_markdown(summary, args.markdown_output_path)
    print(f"census_rows={summary['census_rows']}")
    print(f"review_rows={summary['review_rows']}")
    print(f"review_label_counts={summary['review_label_counts']}")
    print(f"reviewed_precision={summary['reviewed_precision']}")
    print(f"acceptable_for_scaling={summary['acceptable_for_scaling']}")
    print(f"warning_flags={summary['warning_flags']}")
    print(f"summary_output_path={output}")
    print(f"markdown_summary_output_path={markdown_output}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Pump.fun precision review labels and write a summary.")
    parser.add_argument("--census-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--review-path", default="data/backtests/diagnostics/reports/pumpfun_precision_review_sample.jsonl")
    parser.add_argument("--output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_summary.json")
    parser.add_argument("--markdown-output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_summary.md")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
