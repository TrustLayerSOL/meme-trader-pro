#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.trusted_historical_market_snapshot_provider import (  # noqa: E402
    build_trusted_historical_market_snapshot_report,
)


DEFAULT_SOURCE_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_records.jsonl"
)
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "trusted_historical_market_snapshot_report.json"
)
DEFAULT_OUTPUT_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "trusted_historical_market_snapshot_records.jsonl"
)


def relative_path(path: Path, root: Path = ROOT) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def write_trusted_historical_market_snapshot_report(
    *,
    source_records_path: Path | str = DEFAULT_SOURCE_RECORDS_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    source_records_path = Path(source_records_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    records = read_jsonl(source_records_path)
    report = build_trusted_historical_market_snapshot_report(
        backfill_records=records,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "source_records": relative_path(source_records_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "records": relative_path(output_records_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_records_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with output_records_path.open("w", encoding="utf-8") as handle:
        for record in report.get("records") or []:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only trusted historical market snapshot requirements report."
    )
    parser.add_argument("--source-records", type=Path, default=DEFAULT_SOURCE_RECORDS_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_trusted_historical_market_snapshot_report(
        source_records_path=args.source_records,
        report_path=args.report_path,
        output_records_path=args.records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
