from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float
from wallets.wallet_history_parser import QUOTE_MINTS


MODE = "HISTORICAL_QUOTE_PRICE_ENRICHMENT_REVIEW_ONLY"
ENRICHMENT_VERSION = "historical_quote_price_enrichment.v1"

WSOL_MINT = "So11111111111111111111111111111111111111112"


def normalize_quote_price_series(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        timestamp = safe_float(row.get("timestamp") or row.get("time"), None)
        price = safe_float(row.get("price_usd") or row.get("price"), None)
        if timestamp is None or price is None or price <= 0:
            continue
        normalized.append({"timestamp": timestamp, "price_usd": price})
    normalized.sort(key=lambda item: item["timestamp"])
    return normalized


def nearest_prior_quote_price(
    series: list[dict[str, float]],
    timestamp: float | None,
    *,
    max_quote_age_seconds: float,
) -> tuple[dict[str, float] | None, str]:
    if timestamp is None:
        return None, "blocked_missing_timestamp"
    candidate: dict[str, float] | None = None
    for row in series:
        if row["timestamp"] <= timestamp:
            candidate = row
        else:
            break
    if candidate is None:
        return None, "blocked_missing_prior_quote_usd_price"
    age = timestamp - candidate["timestamp"]
    if age > max_quote_age_seconds:
        return candidate, "blocked_stale_quote_usd_price"
    return candidate, "quote_usd_price_recovered"


def quote_price_supported(context: dict[str, Any]) -> bool:
    quote_mint = str(context.get("quote_mint") or "").strip()
    return quote_mint == WSOL_MINT and safe_float(context.get("price_in_quote"), None) not in (None, 0)


def remove_missing_entry_price(missing_fields: list[Any]) -> list[str]:
    return sorted({str(field) for field in missing_fields if str(field) and str(field) != "entry_price"})


def classify_record(
    record: dict[str, Any],
    *,
    quote_price_series: list[dict[str, float]],
    max_quote_age_seconds: float,
) -> dict[str, Any]:
    enriched = dict(record)
    context = dict(as_dict(enriched.get("decision_time_context")))
    timestamp = safe_float(enriched.get("timestamp") or context.get("timestamp"), None)
    enriched["quote_price_enrichment_version"] = ENRICHMENT_VERSION

    if not quote_price_supported(context):
        enriched["quote_price_status"] = "blocked_no_quote_price_context"
        enriched["decision_time_context"] = context
        return enriched

    prior_price, status = nearest_prior_quote_price(
        quote_price_series,
        timestamp,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    enriched["quote_price_status"] = status
    if status != "quote_usd_price_recovered" or not prior_price:
        enriched["decision_time_context"] = context
        return enriched

    price_in_quote = safe_float(context.get("price_in_quote"), None)
    quote_usd = safe_float(prior_price.get("price_usd"), None)
    if price_in_quote is None or quote_usd is None:
        enriched["quote_price_status"] = "blocked_missing_quote_inputs"
        enriched["decision_time_context"] = context
        return enriched

    quote_time = safe_float(prior_price.get("timestamp"), None)
    context.update(
        {
            "price": price_in_quote * quote_usd,
            "price_usd": price_in_quote * quote_usd,
            "quote_usd_price": quote_usd,
            "quote_usd_price_time": quote_time,
            "quote_usd_price_age_seconds": round(timestamp - quote_time, 6)
            if timestamp is not None and quote_time is not None
            else None,
            "quote_usd_price_source": "historical_quote_price_series",
            "decision_time_safe": True,
        }
    )
    enriched["decision_time_context"] = context
    enriched["missing_fields"] = remove_missing_entry_price(enriched.get("missing_fields") or [])
    block_reasons = [str(reason) for reason in enriched.get("block_reasons") or [] if str(reason)]
    enriched["block_reasons"] = sorted({reason for reason in block_reasons if reason != "blocked_missing_price"})
    enriched["recovery_method"] = "quote_usd_price_enriched_from_historical_series"
    return enriched


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(record.get("quote_price_status") or "unknown") for record in records)
    return {
        "records_scanned": len(records),
        "price_recovered_records": statuses.get("quote_usd_price_recovered", 0),
        "unsupported_records": statuses.get("blocked_no_quote_price_context", 0),
        "missing_prior_quote_price_records": statuses.get("blocked_missing_prior_quote_usd_price", 0),
        "stale_quote_price_records": statuses.get("blocked_stale_quote_usd_price", 0),
        "status_counts": dict(sorted(statuses.items())),
        "tokens_affected": len({record.get("token_mint") for record in records if record.get("token_mint")}),
        "wallets_affected": len({record.get("wallet") for record in records if record.get("wallet")}),
        "supported_quote_mints": sorted(QUOTE_MINTS),
    }


def build_historical_quote_price_enrichment_report(
    *,
    backfill_records: list[dict[str, Any]],
    quote_price_series: list[dict[str, Any]],
    max_quote_age_seconds: float = 7200.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    normalized_prices = normalize_quote_price_series(quote_price_series)
    records = [
        classify_record(
            record,
            quote_price_series=normalized_prices,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        for record in backfill_records or []
        if isinstance(record, dict)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "quote_price_enrichment_version": ENRICHMENT_VERSION,
        "max_quote_age_seconds": max_quote_age_seconds,
        "quote_price_points": len(normalized_prices),
        "summary": build_summary(records),
        "records": records,
    }
