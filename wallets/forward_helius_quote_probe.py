from __future__ import annotations

import time
from typing import Any

from wallets.wallet_history_parser import parse_wallet_token_deltas


MODE = "FORWARD_HELIUS_QUOTE_PROBE_REVIEW_ONLY"
VERSION = "forward_helius_quote_probe.v1"
TARGET_BLOCK_REASON = "missing_valid_execution_price_quote"


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def candidate_rows(rejected_records: list[dict[str, Any]], *, wallet: str | None = None, max_rows: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in rejected_records or []:
        if not isinstance(row, dict):
            continue
        if row.get("block_reason") != TARGET_BLOCK_REASON:
            continue
        if wallet and row.get("wallet") != wallet:
            continue
        if not row.get("transaction_signature") or not row.get("token_mint") or not row.get("wallet"):
            continue
        rows.append(row)
        if len(rows) >= max(0, int(max_rows)):
            break
    return rows


def fetch_transaction(rpc: Any, signature: str) -> dict[str, Any] | None:
    result = rpc.call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed",
            },
        ],
    )
    return result if isinstance(result, dict) else None


def dry_run_row(row: dict[str, Any]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "")
    mint = str(row.get("token_mint") or "")
    signature = str(row.get("transaction_signature") or "")
    return {
        "wallet_address": wallet,
        "event_id": row.get("event_id"),
        "token_mint": mint,
        "transaction_signature": signature,
        "signal_time": row.get("signal_time"),
        "source_block_reason": row.get("block_reason"),
        "status": "dry_run_selected",
        "transaction_found": False,
        "parsed_token_delta_rows": 0,
        "matching_token_delta_found": False,
        "quote_mint": None,
        "quote_amount_delta": None,
        "execution_price_quote": None,
        "execution_price_source": None,
        "repair_allowed": False,
        "promotion_allowed": False,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
        "notes": "selected for review-only Helius quote probe; no RPC call made",
    }


def probe_row(row: dict[str, Any], rpc: Any) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "")
    mint = str(row.get("token_mint") or "")
    signature = str(row.get("transaction_signature") or "")
    tx = fetch_transaction(rpc, signature)
    parsed = parse_wallet_token_deltas(tx or {}, wallet=wallet, signature=signature)
    matching = next((item for item in parsed if item.get("token_mint") == mint), None)
    quote = safe_float((matching or {}).get("execution_price_quote"), None)
    if not isinstance(tx, dict):
        status = "transaction_fetch_failed"
    elif quote is not None and quote > 0:
        status = "quote_anchor_recoverable"
    else:
        status = "quote_anchor_not_recovered"
    return {
        "wallet_address": wallet,
        "event_id": row.get("event_id"),
        "token_mint": mint,
        "transaction_signature": signature,
        "signal_time": row.get("signal_time"),
        "source_block_reason": row.get("block_reason"),
        "status": status,
        "transaction_found": isinstance(tx, dict),
        "parsed_token_delta_rows": len(parsed),
        "matching_token_delta_found": matching is not None,
        "quote_mint": (matching or {}).get("quote_mint"),
        "quote_amount_delta": (matching or {}).get("quote_amount_delta"),
        "execution_price_quote": quote,
        "execution_price_source": "same_transaction_token_balance_delta" if quote is not None and quote > 0 else None,
        "repair_allowed": False,
        "promotion_allowed": False,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
        "notes": (
            "quote anchor can feed a separate review-only repair step"
            if quote is not None and quote > 0
            else "transaction did not expose a matching quote delta for this wallet and mint"
        ),
    }


def build_summary(rows: list[dict[str, Any]], *, execute: bool, selected_count: int) -> dict[str, Any]:
    recoverable = sum(1 for row in rows if row.get("status") == "quote_anchor_recoverable")
    attempted = sum(1 for row in rows if row.get("status") != "dry_run_selected")
    fetched = sum(1 for row in rows if row.get("transaction_found") is True)
    failures = sum(1 for row in rows if row.get("status") == "transaction_fetch_failed")
    return {
        "rows_selected": selected_count,
        "rows_attempted": attempted,
        "transactions_fetched": fetched,
        "rpc_failures": failures,
        "rows_tested": len(rows),
        "recoverable_quote_rows": recoverable,
        "unrecoverable_rows": attempted - recoverable,
        "wallets_tested": len({row.get("wallet_address") for row in rows if row.get("wallet_address")}),
        "tokens_tested": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        "execute": execute,
        "repair_rows_written": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_helius_quote_probe(
    *,
    rejected_records: list[dict[str, Any]],
    rpc: Any,
    wallet: str | None = None,
    max_rows: int = 5,
    execute: bool = False,
    paid_rpc_allowed: bool = False,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    if execute and not paid_rpc_allowed:
        raise ValueError("Helius quote probe execute mode requires --allow-paid-rpc.")
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    selected = candidate_rows(rejected_records, wallet=wallet, max_rows=max_rows)
    rows = [probe_row(row, rpc) for row in selected] if execute else [dry_run_row(row) for row in selected]
    return {
        "generated_at": generated_at,
        "run_id": run_id,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "execute": execute,
        "paid_rpc_allowed": paid_rpc_allowed,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "target_block_reason": TARGET_BLOCK_REASON,
        "wallet_filter": wallet,
        "max_rows": max_rows,
        "summary": build_summary(rows, execute=execute, selected_count=len(selected)),
        "rows": rows,
        "operator_note": (
            "Helius quote probe is review-only. It tests whether paid RPC transaction bodies expose "
            "same-transaction quote anchors, but it does not write repaired records, mutate trust, "
            "mutate wallet lists, promote wallets, or execute trades."
        ),
    }
