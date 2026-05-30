#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.historical_quote_price_enrichment import (  # noqa: E402
    build_historical_quote_price_enrichment_report,
)


DEFAULT_SOURCE_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_records.jsonl"
)
DEFAULT_QUOTE_PRICE_SERIES_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "sol_usd_price_series.jsonl"
)
DEFAULT_REPORT_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_quote_price_enrichment_report.json"
)
DEFAULT_OUTPUT_RECORDS_PATH = (
    ROOT / "data" / "reports" / "historical_backfill" / "historical_quote_price_enrichment_records.jsonl"
)
COINGECKO_SOL_RANGE_URL = "https://api.coingecko.com/api/v3/coins/solana/market_chart/range"


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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def timestamp_bounds_for_wsol(records: list[dict[str, Any]], *, pad_seconds: float = 7200.0) -> tuple[float, float] | None:
    times: list[float] = []
    for record in records:
        context = record.get("decision_time_context") if isinstance(record.get("decision_time_context"), dict) else {}
        if context.get("quote_mint") != "So11111111111111111111111111111111111111112":
            continue
        if context.get("price_in_quote") in (None, "", 0):
            continue
        try:
            times.append(float(record.get("timestamp") or context.get("timestamp")))
        except (TypeError, ValueError):
            continue
    if not times:
        return None
    return max(0.0, min(times) - pad_seconds), max(times) + pad_seconds


def fetch_coingecko_sol_usd_series(start: float, end: float, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "vs_currency": "usd",
            "from": int(start),
            "to": int(end),
            "precision": "full",
        }
    )
    request = urllib.request.Request(
        f"{COINGECKO_SOL_RANGE_URL}?{query}",
        headers={"accept": "application/json", "user-agent": "MemeTraderPro historical quote enrichment"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows: list[dict[str, Any]] = []
    for point in payload.get("prices") or []:
        if not isinstance(point, list) or len(point) < 2:
            continue
        try:
            rows.append(
                {
                    "timestamp": float(point[0]) / 1000.0,
                    "price_usd": float(point[1]),
                    "source": "coingecko_solana_market_chart_range",
                }
            )
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: item["timestamp"])
    return rows


def load_or_fetch_quote_price_series(
    *,
    quote_price_series_path: Path,
    records: list[dict[str, Any]],
    fetch_coingecko: bool,
    timeout: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if fetch_coingecko:
        bounds = timestamp_bounds_for_wsol(records)
        if not bounds:
            return [], {"source": "coingecko", "status": "blocked_no_wsol_rows"}
        start, end = bounds
        rows = fetch_coingecko_sol_usd_series(start, end, timeout=timeout)
        write_jsonl(quote_price_series_path, rows)
        return rows, {
            "source": "coingecko_solana_market_chart_range",
            "status": "fetched",
            "from": start,
            "to": end,
            "points": len(rows),
            "path": relative_path(quote_price_series_path),
        }
    rows = read_jsonl(quote_price_series_path)
    return rows, {
        "source": "local_quote_price_series",
        "status": "loaded" if rows else "missing_or_empty",
        "path": relative_path(quote_price_series_path),
        "points": len(rows),
    }


def write_historical_quote_price_enrichment_report(
    *,
    source_records_path: Path | str = DEFAULT_SOURCE_RECORDS_PATH,
    quote_price_series_path: Path | str = DEFAULT_QUOTE_PRICE_SERIES_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    output_records_path: Path | str = DEFAULT_OUTPUT_RECORDS_PATH,
    max_quote_age_seconds: float = 7200.0,
    fetch_coingecko: bool = False,
    fetch_timeout: float = 20.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    source_records_path = Path(source_records_path)
    quote_price_series_path = Path(quote_price_series_path)
    report_path = Path(report_path)
    output_records_path = Path(output_records_path)
    generated_at = time.time() if generated_at is None else float(generated_at)
    records = read_jsonl(source_records_path)
    quote_prices, quote_price_source = load_or_fetch_quote_price_series(
        quote_price_series_path=quote_price_series_path,
        records=records,
        fetch_coingecko=fetch_coingecko,
        timeout=fetch_timeout,
    )
    report = build_historical_quote_price_enrichment_report(
        backfill_records=records,
        quote_price_series=quote_prices,
        max_quote_age_seconds=max_quote_age_seconds,
        generated_at=generated_at,
    )
    report["quote_price_source"] = quote_price_source
    report["input_paths"] = {
        "source_records": relative_path(source_records_path),
        "quote_price_series": relative_path(quote_price_series_path),
    }
    report["output_paths"] = {
        "report": relative_path(report_path),
        "records": relative_path(output_records_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_records_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_jsonl(output_records_path, report.get("records") or [])
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich historical WSOL quote prices with a decision-time-safe SOL/USD series."
    )
    parser.add_argument("--source-records", type=Path, default=DEFAULT_SOURCE_RECORDS_PATH)
    parser.add_argument("--quote-price-series", type=Path, default=DEFAULT_QUOTE_PRICE_SERIES_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--records-path", type=Path, default=DEFAULT_OUTPUT_RECORDS_PATH)
    parser.add_argument("--max-quote-age-seconds", type=float, default=7200.0)
    parser.add_argument("--fetch-coingecko", action="store_true")
    parser.add_argument("--fetch-timeout", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_historical_quote_price_enrichment_report(
        source_records_path=args.source_records,
        quote_price_series_path=args.quote_price_series,
        report_path=args.report_path,
        output_records_path=args.records_path,
        max_quote_age_seconds=args.max_quote_age_seconds,
        fetch_coingecko=args.fetch_coingecko,
        fetch_timeout=args.fetch_timeout,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
