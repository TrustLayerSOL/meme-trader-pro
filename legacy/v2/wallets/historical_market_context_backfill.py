from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float
from wallets.wallet_history_parser import QUOTE_MINTS
from wallets.wallet_missing_market_context import group_missing_rows


MODE = "HISTORICAL_MARKET_CONTEXT_BACKFILL_REVIEW_ONLY"
BACKFILL_VERSION = "historical_market_context_backfill.v1"


def token_amount(balance: dict[str, Any]) -> float:
    ui = as_dict(balance.get("uiTokenAmount"))
    value = ui.get("uiAmount")
    if value is None:
        value = ui.get("uiAmountString")
    return safe_float(value, 0.0) or 0.0


def balance_deltas_for_owner(tx: dict[str, Any], wallet: str) -> dict[str, float]:
    meta = as_dict(tx.get("meta"))
    pre: dict[str, float] = {}
    post: dict[str, float] = {}
    for row in meta.get("preTokenBalances") or []:
        if not isinstance(row, dict) or str(row.get("owner") or "") != wallet:
            continue
        mint = str(row.get("mint") or "").strip()
        if mint:
            pre[mint] = pre.get(mint, 0.0) + token_amount(row)
    for row in meta.get("postTokenBalances") or []:
        if not isinstance(row, dict) or str(row.get("owner") or "") != wallet:
            continue
        mint = str(row.get("mint") or "").strip()
        if mint:
            post[mint] = post.get(mint, 0.0) + token_amount(row)
    deltas = {}
    for mint in set(pre) | set(post):
        delta = post.get(mint, 0.0) - pre.get(mint, 0.0)
        if abs(delta) > 1e-12:
            deltas[mint] = delta
    return deltas


def raw_transaction_signature(raw: dict[str, Any]) -> str:
    signature = str(raw.get("signature") or "").strip()
    if signature:
        return signature
    tx = as_dict(raw.get("transaction"))
    signatures = as_dict(tx.get("transaction")).get("signatures")
    if isinstance(signatures, list) and signatures:
        return str(signatures[0] or "").strip()
    return ""


def index_raw_transactions(raw_transactions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for raw in raw_transactions or []:
        if not isinstance(raw, dict):
            continue
        signature = raw_transaction_signature(raw)
        if signature and signature not in indexed:
            indexed[signature] = raw
    return indexed


def quote_price_context(
    *,
    raw: dict[str, Any],
    wallet: str,
    mint: str,
    evidence_timestamp: float | None,
) -> tuple[dict[str, Any], list[str], str]:
    tx = as_dict(raw.get("transaction"))
    block_time = safe_float(tx.get("blockTime"), evidence_timestamp)
    deltas = balance_deltas_for_owner(tx, wallet)
    token_delta = deltas.get(mint)
    if token_delta is None or abs(token_delta) <= 1e-12:
        return empty_context(evidence_timestamp), ["blocked_insufficient_data"], "blocked_insufficient_data"

    quote_deltas = {quote_mint: delta for quote_mint, delta in deltas.items() if quote_mint in QUOTE_MINTS}
    quote_deltas = {quote_mint: delta for quote_mint, delta in quote_deltas.items() if abs(delta) > 1e-12}
    if not quote_deltas:
        return empty_context(evidence_timestamp), ["blocked_missing_price"], "blocked_missing_price"

    quote_mint, quote_delta = max(quote_deltas.items(), key=lambda item: abs(item[1]))
    source_file = raw.get("source_file")
    context = {
        "source": "raw_transaction_history",
        "source_file": source_file,
        "timestamp": block_time,
        "decision_time_safe": True,
        "price": None,
        "price_in_quote": abs(quote_delta) / abs(token_delta),
        "price_quote_per_token": abs(quote_delta) / abs(token_delta),
        "quote_mint": quote_mint,
        "quote_amount_delta": quote_delta,
        "token_amount_delta": token_delta,
        "price_unit": "quote_per_token",
        "market_cap": None,
        "liquidity": None,
    }
    block_reasons = ["blocked_missing_liquidity", "blocked_missing_market_cap"]
    if token_delta and quote_delta and (token_delta > 0) == (quote_delta > 0):
        block_reasons.append("needs_manual_review")
    return context, block_reasons, "partial_context_recovered"


def empty_context(timestamp: float | None) -> dict[str, Any]:
    return {
        "source": None,
        "timestamp": timestamp,
        "decision_time_safe": True,
        "price": None,
        "price_in_quote": None,
        "market_cap": None,
        "liquidity": None,
    }


def evidence_rows_from_enrichment(wallet_evidence_enrichment: Any) -> list[dict[str, Any]]:
    grouped = group_missing_rows(as_dict(wallet_evidence_enrichment).get("evidence_records") or [])
    rows = [row for grouped_rows in grouped.values() for row in grouped_rows]
    rows.sort(
        key=lambda row: (
            str(row.get("token_mint") or row.get("mint") or ""),
            safe_float(row.get("timestamp"), 0.0) or 0.0,
            str(row.get("transaction_signature") or ""),
        )
    )
    return rows


def classify_evidence_row(row: dict[str, Any], raw_by_signature: dict[str, dict[str, Any]]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "").strip()
    mint = str(row.get("token_mint") or row.get("mint") or "").strip()
    signature = str(row.get("transaction_signature") or "").strip()
    timestamp = safe_float(row.get("timestamp"), None)
    raw = raw_by_signature.get(signature)
    if not raw:
        context = empty_context(timestamp)
        block_reasons = ["blocked_missing_transaction"]
        status = "blocked_missing_transaction"
        recovery_method = "blocked_missing_transaction"
    else:
        context, block_reasons, status = quote_price_context(
            raw=raw,
            wallet=wallet,
            mint=mint,
            evidence_timestamp=timestamp,
        )
        recovery_method = "recovered_from_transaction_history" if status == "partial_context_recovered" else status

    confidence = confidence_level(status, block_reasons)
    missing_fields = sorted(
        {
            field
            for field in (row.get("missing_fields") if isinstance(row.get("missing_fields"), list) else [])
            if field
        }
        | {
            field
            for reason, field in (
                ("blocked_missing_price", "entry_price"),
                ("blocked_missing_liquidity", "liquidity"),
                ("blocked_missing_market_cap", "market_cap"),
            )
            if reason in block_reasons
        }
    )
    return {
        "backfill_version": BACKFILL_VERSION,
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": row.get("observed_action") or "unknown",
        "timestamp": timestamp,
        "transaction_signature": signature,
        "status": status,
        "recovery_method": recovery_method,
        "decision_time_context": context,
        "later_outcome": as_dict(row.get("later_token_outcome")),
        "outcome_window_labels": as_dict(row.get("outcome_window_labels")),
        "missing_fields": missing_fields,
        "block_reasons": sorted(set(block_reasons)),
        "confidence_level": confidence,
        "source_evidence": {
            "parser_version": row.get("parser_version"),
            "enrichment_version": row.get("enrichment_version"),
            "enrichment_status": row.get("enrichment_status"),
            "confidence_score": row.get("confidence_score"),
        },
    }


def confidence_level(status: str, block_reasons: list[str]) -> str:
    if status == "partial_context_recovered" and "needs_manual_review" not in block_reasons:
        return "medium"
    if status == "partial_context_recovered":
        return "low"
    return "low"


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    block_reasons = Counter(reason for record in records for reason in record.get("block_reasons") or [])
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    confidence_levels = Counter(str(record.get("confidence_level") or "unknown") for record in records)
    missing_fields = Counter(field for record in records for field in record.get("missing_fields") or [])
    wallets_with_partial_context = sorted(
        {record.get("wallet") for record in records if record.get("status") == "partial_context_recovered" and record.get("wallet")}
    )
    return {
        "records_scanned": len(records),
        "records_recovered": statuses.get("recovered_from_transaction_history", 0),
        "records_partially_recovered": statuses.get("partial_context_recovered", 0),
        "records_blocked": sum(count for status, count in statuses.items() if str(status).startswith("blocked_")),
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
        "wallets_affected": len({record.get("wallet") for record in records if record.get("wallet")}),
        "tokens_affected": len({record.get("token_mint") for record in records if record.get("token_mint")}),
        "wallets_with_partial_context": len(wallets_with_partial_context),
        "wallets_with_partial_context_sample": wallets_with_partial_context[:25],
        "missing_context_categories": dict(sorted(missing_fields.items())),
        "confidence_levels": dict(sorted(confidence_levels.items())),
        "next_required_actions": next_required_actions(records),
    }


def next_required_actions(records: list[dict[str, Any]]) -> list[str]:
    actions = []
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    blocks = Counter(reason for record in records for reason in record.get("block_reasons") or [])
    if statuses.get("partial_context_recovered"):
        actions.append("Review partial transaction-derived quote prices before deciding whether they can feed enrichment.")
    if blocks.get("blocked_missing_transaction"):
        actions.append("Collect or recover raw transactions for signatures missing from local artifacts.")
    if blocks.get("blocked_missing_price"):
        actions.append("Backfill decision-time price from trusted historical market snapshots or richer swap parser evidence.")
    if blocks.get("blocked_missing_liquidity") or blocks.get("blocked_missing_market_cap"):
        actions.append("Backfill liquidity and market-cap context from replay-safe historical market artifacts.")
    if not actions:
        actions.append("No missing historical market-context actions remain in this report.")
    return actions


def build_historical_market_context_backfill_report(
    *,
    wallet_evidence_enrichment: Any,
    raw_transactions: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    raw_by_signature = index_raw_transactions(raw_transactions)
    rows = evidence_rows_from_enrichment(wallet_evidence_enrichment)
    records = [classify_evidence_row(row, raw_by_signature) for row in rows]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "backfill_version": BACKFILL_VERSION,
        "summary": build_summary(records),
        "records": records,
    }


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
