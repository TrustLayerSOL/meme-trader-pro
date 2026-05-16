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

from wallets.historical_market_context_backfill import (  # noqa: E402
    build_historical_market_context_backfill_report,
    relative_path,
)


DEFAULT_ENRICHMENT_REPORT = ROOT / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
DEFAULT_RAW_TRANSACTIONS_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_report.json"
DEFAULT_RECORDS_PATH = ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_records.jsonl"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        parsed = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default
    return parsed


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


def load_raw_transactions(raw_transactions_dir: Path, *, root: Path = ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not raw_transactions_dir.exists():
        return rows
    for path in sorted(raw_transactions_dir.glob("*.jsonl")):
        source_file = relative_path(path, root)
        for row in read_jsonl(path):
            row.setdefault("source_file", source_file)
            rows.append(row)
    return rows


def write_historical_market_context_backfill_report(
    *,
    enrichment_report_path: Path | str = DEFAULT_ENRICHMENT_REPORT,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    records_path: Path | str = DEFAULT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report_path = Path(report_path)
    records_path = Path(records_path)
    enrichment = read_json(Path(enrichment_report_path), {"evidence_records": []})
    raw_transactions = load_raw_transactions(Path(raw_transactions_dir))
    report = build_historical_market_context_backfill_report(
        wallet_evidence_enrichment=enrichment,
        raw_transactions=raw_transactions,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "enrichment_report": relative_path(Path(enrichment_report_path), ROOT),
        "raw_transactions_dir": relative_path(Path(raw_transactions_dir), ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "records": relative_path(records_path, ROOT),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with records_path.open("w", encoding="utf-8") as handle:
        for record in report.get("records") or []:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only historical market-context backfill report.")
    parser.add_argument("--enrichment-report", type=Path, default=DEFAULT_ENRICHMENT_REPORT)
    parser.add_argument("--raw-transactions-dir", type=Path, default=DEFAULT_RAW_TRANSACTIONS_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_historical_market_context_backfill_report(
        enrichment_report_path=args.enrichment_report,
        raw_transactions_dir=args.raw_transactions_dir,
        report_path=args.report_path,
        records_path=args.records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
