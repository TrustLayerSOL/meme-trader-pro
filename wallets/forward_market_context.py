from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import evidence_confidence
from wallets.wallet_evidence_models import missing_fields_for_evidence
from wallets.wallet_evidence_models import safe_float


MODE = "FORWARD_MARKET_CONTEXT_REVIEW_ONLY"
SOURCE_PREFIX = "forward_market_context"
DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE = 50
DEFAULT_MAX_MARKET_CONTEXT_MINTS = 50
DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS = 120.0
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/"


def evidence_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def unique_evidence_mints(evidence_records: list[dict[str, Any]], *, max_mints: int) -> list[str]:
    mints: list[str] = []
    seen: set[str] = set()
    for row in evidence_records or []:
        if not isinstance(row, dict):
            continue
        mint = evidence_mint(row)
        if not mint or mint in seen:
            continue
        seen.add(mint)
        mints.append(mint)
        if len(mints) >= max(0, int(max_mints)):
            break
    return mints


def estimate_market_context_budget(
    *,
    selected_mints: int,
    max_market_context_calls_per_cycle: int = DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE,
) -> dict[str, Any]:
    estimated_calls = max(0, int(selected_mints))
    limit = int(max_market_context_calls_per_cycle)
    execute_allowed = estimated_calls <= limit
    return {
        "selected_mints": estimated_calls,
        "estimated_market_context_calls_per_cycle": estimated_calls,
        "max_market_context_calls_per_cycle": limit,
        "budget_status": "within_budget" if execute_allowed else "blocked_market_context_cycle_limit",
        "block_reason": None if execute_allowed else "estimated_market_context_calls_per_cycle_exceeds_limit",
        "execute_allowed": execute_allowed,
    }


def first_number(*values: Any) -> float | None:
    for value in values:
        number = safe_float(value, None)
        if number is not None:
            return number
    return None


def parse_tx_count(info: dict[str, Any]) -> int | None:
    tx_count = first_number(info.get("tx_count"), info.get("tx_count_m5"))
    return int(tx_count) if tx_count is not None else None


def normalize_market_info(mint: str, info: dict[str, Any], *, observed_at: float) -> dict[str, Any] | None:
    if not mint or not isinstance(info, dict):
        return None
    price = first_number(info.get("price"), info.get("priceUsd"), info.get("price_usd"))
    liquidity = first_number(info.get("liquidity"), info.get("liquidity_usd"), as_dict(info.get("liquidity")).get("usd"))
    market_cap = first_number(info.get("market_cap"), info.get("marketCap"), info.get("fdv"), info.get("fdv_usd"))
    if price is None and liquidity is None and market_cap is None:
        return None
    provider_source = str(info.get("source") or "unknown").strip() or "unknown"
    source = f"{SOURCE_PREFIX}:{provider_source}"
    payload = {
        "mint": mint,
        "time": observed_at,
        "price": price,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "fdv": first_number(info.get("fdv"), info.get("fdv_usd")),
        "source": source,
        "provider_source": provider_source,
        "url": info.get("url"),
        "pair_address": info.get("pair_address") or info.get("pairAddress"),
        "dex": info.get("dex"),
        "tx_count": parse_tx_count(info),
        "decision_time_safe": True,
        "forward_capture": True,
        "raw_provider": info,
    }
    return {
        "time": observed_at,
        "mint": mint,
        "source": source,
        "context": json.dumps(
            {
                "context_type": "forward_collection_market_context",
                "decision_time_safe": True,
                "forward_capture": True,
            },
            sort_keys=True,
        ),
        "price": price,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "risk_label": info.get("risk_label"),
        "payload": payload,
        "payload_json": json.dumps(payload, sort_keys=True),
    }


def snapshot_entry_context(snapshot: dict[str, Any], *, event_timestamp: float) -> dict[str, Any]:
    snapshot_time = safe_float(snapshot.get("time"), None)
    lag = round(snapshot_time - event_timestamp, 6) if snapshot_time is not None else None
    return {
        "price": safe_float(snapshot.get("price"), None),
        "liquidity": safe_float(snapshot.get("liquidity"), None),
        "market_cap": safe_float(snapshot.get("market_cap"), None),
        "source": snapshot.get("source"),
        "snapshot_time": snapshot_time,
        "snapshot_lag_seconds": lag,
        "decision_time_safe": True,
        "forward_capture": True,
        "context_time_type": "collection_time_near_event",
    }


def apply_forward_market_context(
    evidence_records: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    *,
    max_event_snapshot_lag_seconds: float = DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    snapshot_by_mint = {str(row.get("mint") or ""): row for row in snapshots or [] if isinstance(row, dict)}
    enriched: list[dict[str, Any]] = []
    with_context = 0
    stale = 0
    missing = 0
    for row in evidence_records or []:
        if not isinstance(row, dict):
            continue
        next_row = dict(row)
        mint = evidence_mint(next_row)
        snapshot = snapshot_by_mint.get(mint)
        if not snapshot:
            missing += 1
            enriched.append(next_row)
            continue
        event_time = safe_float(next_row.get("timestamp"), None)
        snapshot_time = safe_float(snapshot.get("time"), None)
        lag = None if event_time is None or snapshot_time is None else snapshot_time - event_time
        if lag is None or lag < 0 or lag > max(0.0, float(max_event_snapshot_lag_seconds)):
            stale += 1
            flags = list(next_row.get("risk_flags") or [])
            if "market_context_snapshot_stale_for_event" not in flags:
                flags.append("market_context_snapshot_stale_for_event")
            next_row["risk_flags"] = flags
            enriched.append(next_row)
            continue

        current = as_dict(next_row.get("estimated_entry_context"))
        next_row["estimated_entry_context"] = {
            **current,
            **snapshot_entry_context(snapshot, event_timestamp=event_time),
        }
        next_row["missing_fields"] = missing_fields_for_evidence(next_row)
        next_row["confidence_score"] = evidence_confidence(next_row)
        with_context += 1
        enriched.append(next_row)
    return enriched, {
        "evidence_rows_with_forward_context": with_context,
        "evidence_rows_stale_for_context": stale,
        "evidence_rows_without_market_snapshot": missing,
    }


def fetch_dexscreener_market_info(mint: str, *, timeout: float = 4.0) -> dict[str, Any] | None:
    request = Request(DEXSCREENER_TOKEN_URL + str(mint), headers={"accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list):
        return None
    sol_pairs = [pair for pair in pairs if isinstance(pair, dict) and pair.get("chainId") == "solana"]
    if not sol_pairs:
        return None
    best = max(sol_pairs, key=lambda pair: safe_float(as_dict(pair.get("liquidity")).get("usd"), 0.0) or 0.0)
    txns = as_dict(best.get("txns"))
    m5 = as_dict(txns.get("m5"))
    return {
        "source": "dexscreener",
        "price": best.get("priceUsd"),
        "liquidity": as_dict(best.get("liquidity")).get("usd"),
        "market_cap": best.get("marketCap"),
        "fdv": best.get("fdv"),
        "pair_address": best.get("pairAddress"),
        "dex": best.get("dexId"),
        "url": best.get("url"),
        "tx_count_m5": int(first_number(m5.get("buys"), 0) or 0) + int(first_number(m5.get("sells"), 0) or 0),
    }


def build_forward_market_context_report(
    *,
    evidence_records: list[dict[str, Any]],
    market_provider: Callable[[str], dict[str, Any] | None] | None = None,
    generated_at: float | None = None,
    execute: bool = False,
    max_market_mints: int = DEFAULT_MAX_MARKET_CONTEXT_MINTS,
    max_market_context_calls_per_cycle: int = DEFAULT_MAX_MARKET_CONTEXT_CALLS_PER_CYCLE,
    max_event_snapshot_lag_seconds: float = DEFAULT_MAX_EVENT_SNAPSHOT_LAG_SECONDS,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    rows = [dict(row) for row in evidence_records or [] if isinstance(row, dict)]
    mints = unique_evidence_mints(rows, max_mints=max_market_mints)
    api_budget = estimate_market_context_budget(
        selected_mints=len(mints),
        max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
    )

    if execute and not api_budget["execute_allowed"]:
        return {
            "generated_at": generated_at,
            "mode": MODE,
            "review_only": True,
            "live_execution_locked": True,
            "execute": bool(execute),
            "api_budget": api_budget,
            "summary": {
                "evidence_rows": len(rows),
                "unique_mints_selected": len(mints),
                "dry_run_mints": 0,
                "mints_blocked_api_budget": len(mints),
                "snapshots_collected": 0,
                "market_provider_misses": 0,
                "evidence_rows_with_forward_context": 0,
                "evidence_rows_stale_for_context": 0,
                "evidence_rows_without_market_snapshot": len(rows),
            },
            "market_context_snapshots": [],
            "evidence_records": rows,
            "next_actions": [
                "Lower max_market_mints, increase max_market_context_calls_per_cycle, or rotate lower-priority mints across slower cycles.",
            ],
        }

    snapshots: list[dict[str, Any]] = []
    misses = 0
    provider = market_provider or fetch_dexscreener_market_info
    if execute:
        for mint in mints:
            info = provider(mint)
            snapshot = normalize_market_info(mint, info or {}, observed_at=generated_at)
            if snapshot is None:
                misses += 1
                continue
            snapshots.append(snapshot)

    enriched, enrichment_counts = apply_forward_market_context(
        rows,
        snapshots,
        max_event_snapshot_lag_seconds=max_event_snapshot_lag_seconds,
    )
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "execute": bool(execute),
        "limits": {
            "max_market_mints": max_market_mints,
            "max_market_context_calls_per_cycle": max_market_context_calls_per_cycle,
            "max_event_snapshot_lag_seconds": max_event_snapshot_lag_seconds,
        },
        "api_budget": api_budget,
        "summary": {
            "evidence_rows": len(rows),
            "unique_mints_selected": len(mints),
            "dry_run_mints": len(mints) if not execute else 0,
            "mints_blocked_api_budget": 0,
            "snapshots_collected": len(snapshots),
            "market_provider_misses": misses,
            **enrichment_counts,
        },
        "market_context_snapshots": snapshots,
        "evidence_records": enriched,
    }
