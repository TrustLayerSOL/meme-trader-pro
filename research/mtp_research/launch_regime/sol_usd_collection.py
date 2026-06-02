"""Timestamp-compatible SOL/USD collection for lifecycle valuation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen


COINGECKO_RANGE_URL = "https://api.coingecko.com/api/v3/coins/solana/market_chart/range"
HttpGet = Callable[[str], dict[str, Any]]


def timestamp_span(paths: list[Path | str]) -> tuple[int | None, int | None]:
    values = []
    for path in paths:
        if not Path(path).exists():
            continue
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                row = json.loads(text)
                for value in _row_timestamps(row):
                    values.append(value)
    return (min(values), max(values)) if values else (None, None)


def collect_sol_usd_prices(
    *,
    input_paths: list[Path | str],
    output_path: Path | str,
    http_get: HttpGet | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    start, end = timestamp_span(input_paths)
    if start is None or end is None:
        return {
            "execute": execute,
            "start_ts": start,
            "end_ts": end,
            "price_rows_written": 0,
            "network_calls": 0,
            "output_path": str(output_path),
            "warning_flags": ["no_timestamps"],
        }
    if not execute:
        return {
            "execute": False,
            "start_ts": start,
            "end_ts": end,
            "price_rows_written": 0,
            "network_calls": 0,
            "output_path": str(output_path),
            "warning_flags": [],
        }
    client = http_get or _http_get_json
    url = _range_url(start, end)
    payload = client(url)
    rows = [
        {
            "ts": int(ts_ms // 1000),
            "sol_usd": float(price),
            "source": "coingecko_solana_market_chart_range",
        }
        for ts_ms, price in payload.get("prices", [])
    ]
    _write_jsonl(Path(output_path), rows)
    return {
        "execute": True,
        "start_ts": start,
        "end_ts": end,
        "price_rows_written": len(rows),
        "network_calls": 1,
        "output_path": str(output_path),
        "warning_flags": [] if rows else ["no_price_rows_returned"],
    }


def _row_timestamps(row: dict[str, Any]) -> list[int]:
    values = []
    for key in ("snapshot_ts", "launch_ts"):
        if row.get(key) is not None:
            values.append(int(row[key]))
    metadata = row.get("metadata_json") or {}
    for key in ("price_event_block_time", "price_event_block_time_120m"):
        if metadata.get(key) is not None:
            values.append(int(metadata[key]))
        if row.get(key) is not None:
            values.append(int(row[key]))
    return values


def _range_url(start: int, end: int) -> str:
    query = urlencode({"vs_currency": "usd", "from": start, "to": end})
    return f"{COINGECKO_RANGE_URL}?{query}"


def _http_get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:  # noqa: S310 - fixed public HTTPS endpoint.
        return json.loads(response.read().decode("utf-8"))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in sorted(rows, key=lambda item: item["ts"]):
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    tmp_path.replace(path)
