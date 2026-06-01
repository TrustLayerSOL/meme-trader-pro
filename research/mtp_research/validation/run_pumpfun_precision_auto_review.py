"""Auto-sanity review a deterministic Pump.fun precision sample.

This command rehydrates only sampled creation signatures and checks raw
transaction facts. It does not collect lifecycle data or authorize scaling.
"""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter
from research.mtp_research.ingestion.pumpfun_creation_census import load_census_rows
from research.mtp_research.validation.pumpfun_precision_audit import (
    auto_review_precision_sample,
    precision_summary,
    write_precision_reviews,
    write_precision_summary,
    write_precision_summary_markdown,
)


def main() -> int:
    args = parse_args()
    rows = load_census_rows(args.census_path)
    if not args.execute:
        print(f"census_rows={len(rows)}")
        print(f"sample_rows_planned={min(args.sample_size, len(rows))}")
        print(f"estimated_get_transaction_calls={min(args.sample_size, len(rows))}")
        print("execute_required=true")
        print("network_calls=0")
        return 0

    adapter = HeliusHistoricalAdapter.from_env(transaction_workers=args.transaction_workers)
    reviews = auto_review_precision_sample(rows, adapter=adapter, sample_size=args.sample_size)
    review_output = write_precision_reviews(reviews, args.review_output_path)
    summary = precision_summary(args.census_path, review_output)
    summary_output = write_precision_summary(summary, args.summary_output_path)
    markdown_output = write_precision_summary_markdown(summary, args.markdown_summary_output_path)
    print(f"census_rows={summary['census_rows']}")
    print(f"review_rows={summary['review_rows']}")
    print(f"review_label_counts={summary['review_label_counts']}")
    print(f"reviewed_precision={summary['reviewed_precision']}")
    print(f"acceptable_for_scaling={summary['acceptable_for_scaling']}")
    print(f"warning_flags={summary['warning_flags']}")
    print(f"review_output_path={review_output}")
    print(f"summary_output_path={summary_output}")
    print(f"markdown_summary_output_path={markdown_output}")
    print(f"network_calls={len(reviews)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-sanity review Pump.fun precision sample.")
    parser.add_argument("--census-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--transaction-workers", type=int, default=8)
    parser.add_argument("--review-output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_auto_review_sample.jsonl")
    parser.add_argument("--summary-output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_auto_summary.json")
    parser.add_argument("--markdown-summary-output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_auto_summary.md")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
