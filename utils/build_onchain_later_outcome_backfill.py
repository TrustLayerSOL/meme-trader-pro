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
from wallets.historical_market_context_backfill import relative_path  # noqa: E402
from wallets.onchain_later_outcome_backfill import build_onchain_later_outcome_backfill_report  # noqa: E402


DEFAULT_RECORDS_PATH = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_RAW_TRANSACTIONS_DIR = ROOT / "data" / "wallet_backfills" / "raw_transactions"
DEFAULT_QUOTE_PRICE_SERIES_PATH = ROOT / "data" / "reports" / "historical_backfill" / "sol_usd_price_series.jsonl"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "replay_validation" / "onchain_later_outcome_backfill_report.json"
DEFAULT_OUTPUT_RECORDS_PATH = ROOT / "data" / "reports" / "replay_validation" / "onchain_later_outcome_backfill_records.jsonl"


def write_onchain_later_outcome_backfill_report(
    *,
    records_path: Path | str = DEFAULT_RECORDS_PATH,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    quote_price_series_path: Path | str = DEFAULT_QUOTE_PRICE_SERIES_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    generated_at: float | None = None,
) -> dict[str, Any]:
    records_path = Path(records_path)
    raw_transactions_dir = Path(raw_transactions_dir)
    quote_price_series_path = Path(quote_price_series_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)

    report = build_onchain_later_outcome_backfill_report(
        records=read_jsonl(records_path),
        raw_transactions=load_raw_transactions(raw_transactions_dir),
        quote_price_series=read_jsonl(quote_price_series_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "records": relative_path(records_path, ROOT),
        "raw_transactions_dir": relative_path(raw_transactions_dir, ROOT),
        "quote_price_series": relative_path(quote_price_series_path, ROOT),
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
    parser = argparse.ArgumentParser(description="Build review-only on-chain later outcome labels from raw transactions.")
    parser.add_argument("--records-path", type=Path, default=DEFAULT_RECORDS_PATH)
    parser.add_argument("--raw-transactions-dir", type=Path, default=DEFAULT_RAW_TRANSACTIONS_DIR)
    parser.add_argument("--quote-price-series", type=Path, default=DEFAULT_QUOTE_PRICE_SERIES_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_onchain_later_outcome_backfill_report(
        records_path=args.records_path,
        raw_transactions_dir=args.raw_transactions_dir,
        quote_price_series_path=args.quote_price_series,
        report_path=args.report_path,
        output_records_path=args.output_records_path,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
