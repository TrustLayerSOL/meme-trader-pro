"""Create a deterministic manual-review sample for Pump.fun parser precision."""

from __future__ import annotations

import argparse

from research.mtp_research.ingestion.pumpfun_creation_census import load_census_rows
from research.mtp_research.validation.pumpfun_precision_audit import (
    deterministic_precision_sample,
    write_precision_review_template,
)


def main() -> int:
    args = parse_args()
    rows = load_census_rows(args.census_path)
    sample = deterministic_precision_sample(rows, args.sample_size)
    output = write_precision_review_template(sample, args.output_path)
    print(f"census_rows={len(rows)}")
    print(f"sample_rows={len(sample)}")
    print(f"review_template_path={output}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Pump.fun precision audit sample.")
    parser.add_argument("--census-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--sample-size", type=int, default=25)
    parser.add_argument("--output-path", default="data/backtests/diagnostics/reports/pumpfun_precision_review_sample.jsonl")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
