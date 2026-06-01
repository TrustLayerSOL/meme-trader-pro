"""Build a Pump.fun creation-event census from bounded scan reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from research.mtp_research.ingestion.pumpfun_creation_census import (
    build_creation_census_from_scan_report,
    write_creation_census,
    write_creation_census_csv,
)


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.scan_report).read_text(encoding="utf-8"))
    rows = build_creation_census_from_scan_report(report)
    jsonl_path = write_creation_census(rows, args.output_path)
    csv_path = write_creation_census_csv(rows, args.csv_output_path)
    counts = Counter(row.parser_confidence for row in rows)
    accepted = [row for row in rows if not row.rejection_reason]
    rejected = [row for row in rows if row.rejection_reason]
    print(f"scan_report={args.scan_report}")
    print(f"census_rows={len(rows)}")
    print(f"accepted_rows={len(accepted)}")
    print(f"rejected_or_unknown_rows={len(rejected)}")
    print(f"parser_confidence_counts={dict(sorted(counts.items()))}")
    print(f"jsonl_output_path={jsonl_path}")
    print(f"csv_output_path={csv_path}")
    print("network_calls=0")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Pump.fun creation-event census from a bounded scan report.")
    parser.add_argument("--scan-report", required=True)
    parser.add_argument("--output-path", default="data/normalized/pumpfun_creation_census.jsonl")
    parser.add_argument("--csv-output-path", default="data/normalized/pumpfun_creation_census.csv")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
