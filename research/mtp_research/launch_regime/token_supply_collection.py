"""Bounded token-supply collection for launch lifecycle valuation."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol

from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter


class TokenSupplyAdapter(Protocol):
    def fetch_token_supply(self, mint: str) -> dict[str, Any]:
        ...


def load_unique_mints(path: Path | str) -> list[str]:
    mints = set()
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            mint = row.get("token_mint") or row.get("mint")
            if mint:
                mints.add(str(mint))
    return sorted(mints)


def collect_token_supply(
    *,
    launches_path: Path | str,
    output_path: Path | str,
    adapter: TokenSupplyAdapter | None = None,
    execute: bool = False,
    limit: int | None = None,
    request_pause_seconds: float = 0.0,
    workers: int = 1,
) -> dict[str, Any]:
    mints = load_unique_mints(launches_path)
    if limit is not None:
        mints = mints[:limit]
    if not execute:
        return {
            "execute": False,
            "mints_planned": len(mints),
            "supply_rows_written": 0,
            "network_calls": 0,
            "output_path": str(output_path),
        }

    rpc = adapter or HeliusHistoricalAdapter.from_env()
    rows = []
    failures = []
    if workers <= 1:
        for index, mint in enumerate(mints):
            row, failure = _fetch_one_supply(rpc, mint)
            if row:
                rows.append(row)
            if failure:
                failures.append(failure)
            if request_pause_seconds > 0 and index < len(mints) - 1:
                time.sleep(request_pause_seconds)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_fetch_one_supply, rpc, mint): mint for mint in mints}
            for future in as_completed(futures):
                row, failure = future.result()
                if row:
                    rows.append(row)
                if failure:
                    failures.append(failure)
    _write_jsonl(Path(output_path), rows)
    return {
        "execute": True,
        "mints_planned": len(mints),
        "supply_rows_written": len(rows),
        "failure_count": len(failures),
        "failures": failures[:10],
        "network_calls": len(mints),
        "output_path": str(output_path),
    }


def _fetch_one_supply(
    adapter: TokenSupplyAdapter,
    mint: str,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        return _normalize_supply_row(adapter.fetch_token_supply(mint)), None
    except Exception as exc:  # pragma: no cover - real provider diagnostics
        return None, {"mint": mint, "error": str(exc)}


def _normalize_supply_row(row: dict[str, Any]) -> dict[str, Any]:
    total_supply = _float_or_none(row.get("ui_amount_string"))
    if total_supply is None:
        total_supply = _float_or_none(row.get("ui_amount"))
    return {
        "mint": row["mint"],
        "total_supply": total_supply,
        "raw_amount": row.get("amount"),
        "decimals": row.get("decimals"),
        "slot": row.get("slot"),
        "supply_source": row.get("source") or "helius_getTokenSupply",
        "supply_provenance": "current_spl_mint_supply",
        "circulating_supply": None,
        "circulating_supply_source": None,
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in sorted(rows, key=lambda item: item["mint"]):
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")
    tmp_path.replace(path)
