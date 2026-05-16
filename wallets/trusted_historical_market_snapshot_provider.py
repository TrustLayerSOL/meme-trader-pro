from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "TRUSTED_HISTORICAL_MARKET_SNAPSHOT_REVIEW_ONLY"
SNAPSHOT_PROVIDER_VERSION = "trusted_historical_market_snapshot_provider.v1"

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
STABLE_USD_QUOTE_MINTS = {USDC_MINT, USDT_MINT}


def positive_number(value: Any) -> bool:
    parsed = safe_float(value, None)
    return parsed is not None and parsed > 0


def classify_available_fields(context: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    quote_mint = str(context.get("quote_mint") or "").strip()
    has_price = positive_number(context.get("price"))
    has_quote_price = positive_number(context.get("price_in_quote"))

    if has_price:
        fields.append("price")
    elif has_quote_price and quote_mint in STABLE_USD_QUOTE_MINTS:
        fields.append("price_usd_from_stable_quote")

    if has_quote_price:
        fields.append("price_in_quote")
    if positive_number(context.get("liquidity")):
        fields.append("liquidity")
    if positive_number(context.get("market_cap")):
        fields.append("market_cap")
    return fields


def required_fields_for_context(context: dict[str, Any]) -> list[str]:
    required: list[str] = []
    quote_mint = str(context.get("quote_mint") or "").strip()
    has_price = positive_number(context.get("price"))
    has_quote_price = positive_number(context.get("price_in_quote"))
    has_stable_quote_price = has_quote_price and quote_mint in STABLE_USD_QUOTE_MINTS

    if not has_price and not has_stable_quote_price:
        if has_quote_price:
            required.append("historical_quote_usd_price")
        else:
            required.append("price")
    if not positive_number(context.get("liquidity")):
        required.append("liquidity")
    if not positive_number(context.get("market_cap")):
        required.append("market_cap")
    if context.get("decision_time_safe") is not True:
        required.append("decision_time_safe_source")
    return sorted(dict.fromkeys(required))


def snapshot_status_for_record(source_status: str, context: dict[str, Any], required_fields: list[str]) -> str:
    if not required_fields:
        return "trusted_snapshot_complete"
    if positive_number(context.get("price")) and positive_number(context.get("liquidity")):
        return "liquidity_recovered_not_score_ready"
    if positive_number(context.get("price")):
        return "price_recovered_not_score_ready"
    if source_status == "partial_context_recovered" and positive_number(context.get("price_in_quote")):
        return "partial_quote_context_not_score_ready"
    return "needs_external_historical_market_snapshot"


def classify_backfill_record(record: dict[str, Any]) -> dict[str, Any]:
    context = as_dict(record.get("decision_time_context"))
    required_fields = required_fields_for_context(context)
    source_status = str(record.get("status") or "unknown")
    snapshot_status = snapshot_status_for_record(source_status, context, required_fields)
    score_ready = snapshot_status == "trusted_snapshot_complete"
    return {
        "snapshot_provider_version": SNAPSHOT_PROVIDER_VERSION,
        "wallet": str(record.get("wallet") or "").strip(),
        "token_mint": str(record.get("token_mint") or "").strip(),
        "timestamp": safe_float(record.get("timestamp"), None),
        "transaction_signature": str(record.get("transaction_signature") or "").strip(),
        "source_backfill_status": source_status,
        "snapshot_status": snapshot_status,
        "score_ready": score_ready,
        "decision_time_context": context,
        "later_outcome_reference": as_dict(record.get("later_outcome")),
        "available_decision_time_fields": classify_available_fields(context),
        "required_fields": required_fields,
        "source_block_reasons": sorted(
            str(reason) for reason in (record.get("block_reasons") or []) if str(reason).strip()
        ),
        "cannot_use_for_wallet_score_reason": None
        if score_ready
        else "decision_time_price_liquidity_market_cap_context_incomplete",
    }


def build_snapshot_requirements_by_token(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    scratch: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "records": 0,
            "wallet_set": set(),
            "required_fields_counter": Counter(),
            "snapshot_status_counts": Counter(),
            "timestamps": [],
            "sample_signatures": [],
        }
    )
    for record in records:
        if record.get("score_ready"):
            continue
        mint = str(record.get("token_mint") or "unknown")
        bucket = scratch[mint]
        bucket["records"] += 1
        if record.get("wallet"):
            bucket["wallet_set"].add(record["wallet"])
        bucket["required_fields_counter"].update(record.get("required_fields") or [])
        bucket["snapshot_status_counts"].update([str(record.get("snapshot_status") or "unknown")])
        timestamp = safe_float(record.get("timestamp"), None)
        if timestamp is not None:
            bucket["timestamps"].append(timestamp)
        signature = str(record.get("transaction_signature") or "").strip()
        if signature and len(bucket["sample_signatures"]) < 10:
            bucket["sample_signatures"].append(signature)

    for mint, bucket in sorted(scratch.items()):
        timestamps = bucket["timestamps"]
        grouped[mint] = {
            "records": bucket["records"],
            "wallets": len(bucket["wallet_set"]),
            "first_timestamp": min(timestamps) if timestamps else None,
            "last_timestamp": max(timestamps) if timestamps else None,
            "required_fields": sorted(bucket["required_fields_counter"].keys()),
            "required_field_counts": dict(sorted(bucket["required_fields_counter"].items())),
            "snapshot_status_counts": dict(sorted(bucket["snapshot_status_counts"].items())),
            "sample_signatures": bucket["sample_signatures"],
        }
    return grouped


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(record.get("snapshot_status") or "unknown") for record in records)
    required_fields = Counter(field for record in records for field in record.get("required_fields") or [])
    score_ready = sum(1 for record in records if record.get("score_ready"))
    liquidity_recovered = sum(
        1 for record in records if positive_number(as_dict(record.get("decision_time_context")).get("liquidity"))
    )
    market_cap_recovered = sum(
        1 for record in records if positive_number(as_dict(record.get("decision_time_context")).get("market_cap"))
    )
    return {
        "records_scanned": len(records),
        "score_ready_records": score_ready,
        "partial_quote_context_not_score_ready": statuses.get("partial_quote_context_not_score_ready", 0),
        "price_recovered_not_score_ready": statuses.get("price_recovered_not_score_ready", 0),
        "liquidity_recovered_not_score_ready": statuses.get("liquidity_recovered_not_score_ready", 0),
        "needs_external_historical_market_snapshot": statuses.get(
            "needs_external_historical_market_snapshot", 0
        ),
        "snapshot_status_counts": dict(sorted(statuses.items())),
        "required_field_counts": dict(sorted(required_fields.items())),
        "wallets_affected": len({record.get("wallet") for record in records if record.get("wallet")}),
        "tokens_affected": len({record.get("token_mint") for record in records if record.get("token_mint")}),
        "trust_gate_completion_pct": 100,
        "home_built_onchain_reconstruction_pct": reconstruction_pct(
            records_scanned=len(records),
            liquidity_recovered=liquidity_recovered,
            market_cap_recovered=market_cap_recovered,
        ),
        "provider_fallback_ingestion_pct": 0 if required_fields else 100,
        "external_historical_snapshot_ingestion_pct": 0 if required_fields else 100,
        "next_required_actions": next_required_actions(records),
    }


def reconstruction_pct(*, records_scanned: int, liquidity_recovered: int, market_cap_recovered: int) -> int:
    if records_scanned <= 0:
        return 100
    # Liquidity is the first home-built target; market cap requires separate supply evidence.
    weighted = (liquidity_recovered * 0.65) + (market_cap_recovered * 0.35)
    return int(round((weighted / records_scanned) * 100))


def next_required_actions(records: list[dict[str, Any]]) -> list[str]:
    required = Counter(field for record in records for field in record.get("required_fields") or [])
    actions: list[str] = []
    if required.get("price"):
        actions.append("Recover decision-time token price from transaction quote deltas or pool math before using provider fallback.")
    if required.get("historical_quote_usd_price"):
        actions.append("Recover historical quote-asset USD prices from replay-safe sources or richer swap evidence.")
    if required.get("liquidity") or required.get("market_cap"):
        actions.append("Recover decision-time liquidity from on-chain pool/vault balance evidence first.")
    if required.get("market_cap"):
        actions.append("Recover decision-time token supply before treating market cap as score-ready.")
    if required.get("decision_time_safe_source"):
        actions.append("Reject or repair rows whose context source cannot be proven decision-time safe.")
    if not actions:
        actions.append("All rows have decision-time price, liquidity, and market-cap context for wallet-score review.")
    return actions


def provider_capabilities() -> dict[str, Any]:
    return {
        "local_raw_transaction_quote_delta": {
            "decision_time_safe": True,
            "provides": ["price_in_quote"],
            "does_not_provide": ["historical_quote_usd_price", "liquidity", "market_cap"],
            "score_ready_by_itself": False,
        },
        "home_built_onchain_pool_reconstruction": {
            "decision_time_safe": True,
            "provides": ["liquidity"],
            "requires": ["raw_transaction_token_balances", "quote_usd_price"],
            "does_not_provide_without_extra_evidence": ["market_cap"],
            "score_ready_by_itself": False,
        },
        "home_built_supply_reconstruction": {
            "decision_time_safe_required": True,
            "provides": ["market_cap"],
            "requires": ["token_price", "decision_time_token_supply"],
            "status": "next_required_lane",
        },
        "historical_quote_price_enrichment": {
            "decision_time_safe": True,
            "provides": ["price"],
            "does_not_provide": ["liquidity", "market_cap"],
            "score_ready_by_itself": False,
        },
        "provider_historical_market_snapshot_fallback": {
            "decision_time_safe_required": True,
            "required_outputs": ["price", "liquidity", "market_cap", "source_timestamp"],
            "status": "fallback_or_validation_only",
        },
    }


def provider_policy() -> dict[str, str]:
    return {
        "primary_lane": "home_built_onchain_reconstruction",
        "provider_snapshots": "validation_or_fallback_only",
        "long_term_goal": "replay_safe_proprietary_reconstruction",
    }


def build_trusted_historical_market_snapshot_report(
    *,
    backfill_records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    records = [classify_backfill_record(record) for record in backfill_records if isinstance(record, dict)]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "snapshot_provider_version": SNAPSHOT_PROVIDER_VERSION,
        "provider_policy": provider_policy(),
        "provider_capabilities": provider_capabilities(),
        "summary": build_summary(records),
        "snapshot_requirements_by_token": build_snapshot_requirements_by_token(records),
        "records": records,
    }
