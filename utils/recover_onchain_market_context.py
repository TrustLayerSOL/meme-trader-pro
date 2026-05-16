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

from utils.backfill_historical_market_context import load_raw_transactions, read_jsonl  # noqa: E402
from wallets.onchain_market_context_recovery import (  # noqa: E402
    build_onchain_market_context_recovery_report,
    relative_path,
)


DEFAULT_SOURCE_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_quote_price_enrichment_records.jsonl"
)
DEFAULT_RAW_TRANSACTIONS_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_report.json"
DEFAULT_OUTPUT_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_records.jsonl"
)


def write_onchain_market_context_recovery_report(
    *,
    source_records_path: Path | str = DEFAULT_SOURCE_RECORDS_PATH,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    source_records_path = Path(source_records_path)
    raw_transactions_dir = Path(raw_transactions_dir)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    source_records = read_jsonl(source_records_path)
    raw_transactions = load_raw_transactions(raw_transactions_dir)
    report = build_onchain_market_context_recovery_report(
        backfill_records=source_records,
        raw_transactions=raw_transactions,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "source_records": relative_path(source_records_path, ROOT),
        "raw_transactions_dir": relative_path(raw_transactions_dir, ROOT),
    }
    report["output_paths"] = {
        "report": relative_path(report_path, ROOT),
        "records": relative_path(output_records_path, ROOT),
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
        description="Recover historical liquidity/market-cap context from local on-chain transaction evidence."
    )
    parser.add_argument("--source-records", type=Path, default=DEFAULT_SOURCE_RECORDS_PATH)
    parser.add_argument("--raw-transactions-dir", type=Path, default=DEFAULT_RAW_TRANSACTIONS_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_onchain_market_context_recovery_report(
        source_records_path=args.source_records,
        raw_transactions_dir=args.raw_transactions_dir,
        report_path=args.report_path,
        output_records_path=args.records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
