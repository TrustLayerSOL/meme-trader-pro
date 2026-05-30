#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
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
DEFAULT_QUOTE_PRICE_SERIES_PATH = ROOT / "data" / "reports" / "historical_backfill" / "sol_usd_price_series.jsonl"
DEFAULT_TOKEN_SNAPSHOT_DB_PATH = ROOT / "data" / "memetrader.db"
DEFAULT_REPORT_PATH = ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_report.json"
DEFAULT_OUTPUT_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "onchain_market_context_recovery_records.jsonl"
)


def market_cap_from_payload(payload_json: str | None) -> float | None:
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("market_cap", "market_cap_usd"):
        value = payload.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def load_historical_market_snapshots(token_snapshot_db_path: Path | str) -> list[dict[str, Any]]:
    token_snapshot_db_path = Path(token_snapshot_db_path)
    if not token_snapshot_db_path.exists():
        return []
    try:
        with sqlite3.connect(token_snapshot_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                select time, mint, source, price, liquidity, payload_json
                from token_snapshots
                where mint is not null and time is not null
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        market_cap = market_cap_from_payload(row["payload_json"])
        if market_cap is None:
            continue
        snapshots.append(
            {
                "timestamp": row["time"],
                "mint": row["mint"],
                "source": row["source"] or "token_snapshots",
                "price": row["price"],
                "liquidity": row["liquidity"],
                "market_cap": market_cap,
            }
        )
    return snapshots


def write_onchain_market_context_recovery_report(
    *,
    source_records_path: Path | str = DEFAULT_SOURCE_RECORDS_PATH,
    raw_transactions_dir: Path | str = DEFAULT_RAW_TRANSACTIONS_DIR,
    quote_price_series_path: Path | str = DEFAULT_QUOTE_PRICE_SERIES_PATH,
    token_snapshot_db_path: Path | str = DEFAULT_TOKEN_SNAPSHOT_DB_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    max_quote_age_seconds: float = 7200.0,
    max_market_snapshot_age_seconds: float = 7200.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    source_records_path = Path(source_records_path)
    raw_transactions_dir = Path(raw_transactions_dir)
    quote_price_series_path = Path(quote_price_series_path)
    token_snapshot_db_path = Path(token_snapshot_db_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    source_records = read_jsonl(source_records_path)
    raw_transactions = load_raw_transactions(raw_transactions_dir)
    quote_price_series = read_jsonl(quote_price_series_path)
    historical_market_snapshots = load_historical_market_snapshots(token_snapshot_db_path)
    report = build_onchain_market_context_recovery_report(
        backfill_records=source_records,
        raw_transactions=raw_transactions,
        quote_price_series=quote_price_series,
        max_quote_age_seconds=max_quote_age_seconds,
        historical_market_snapshots=historical_market_snapshots,
        max_market_snapshot_age_seconds=max_market_snapshot_age_seconds,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "source_records": relative_path(source_records_path, ROOT),
        "raw_transactions_dir": relative_path(raw_transactions_dir, ROOT),
        "quote_price_series": relative_path(quote_price_series_path, ROOT),
        "token_snapshot_db": relative_path(token_snapshot_db_path, ROOT),
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
    parser.add_argument("--quote-price-series", type=Path, default=DEFAULT_QUOTE_PRICE_SERIES_PATH)
    parser.add_argument("--token-snapshot-db", type=Path, default=DEFAULT_TOKEN_SNAPSHOT_DB_PATH)
    parser.add_argument("--max-quote-age-seconds", type=float, default=7200.0)
    parser.add_argument("--max-market-snapshot-age-seconds", type=float, default=7200.0)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_onchain_market_context_recovery_report(
        source_records_path=args.source_records,
        raw_transactions_dir=args.raw_transactions_dir,
        quote_price_series_path=args.quote_price_series,
        token_snapshot_db_path=args.token_snapshot_db,
        report_path=args.report_path,
        output_records_path=args.records_path,
        max_quote_age_seconds=args.max_quote_age_seconds,
        max_market_snapshot_age_seconds=args.max_market_snapshot_age_seconds,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
