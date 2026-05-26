from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.dune_candidate_join import as_float, event_signature, parse_dune_time, token_mint, wallet_address


MODE = "DUNE_CANDIDATE_NONOVERLAP_SLICE_REVIEW_ONLY"
VERSION = "dune_candidate_nonoverlap_slice.v1"


def event_time(row: dict[str, Any]) -> float | None:
    return as_float(row.get("signal_time") or row.get("observed_at") or row.get("timestamp"), None)


def dune_time(row: dict[str, Any]) -> float | None:
    return parse_dune_time(row.get("block_time") or row.get("timestamp"))


def price_usd(row: dict[str, Any]) -> float | None:
    return as_float(row.get("price_usd"), None)


def amount_usd(row: dict[str, Any]) -> float | None:
    return as_float(row.get("amount_usd"), None)


def candidate_dex_rows(dune_rows: dict[str, Any]) -> list[dict[str, Any]]:
    rows = dune_rows.get("candidate_dex_trades") if isinstance(dune_rows, dict) else []
    return [row for row in rows or [] if isinstance(row, dict)]


def is_candidate_wallet(row: dict[str, Any], candidate_set: set[str]) -> bool:
    return wallet_address(row) in candidate_set


def overlaps_local(
    dune_row: dict[str, Any],
    local_records: list[dict[str, Any]],
    *,
    max_time_delta_seconds: float,
) -> bool:
    wallet = wallet_address(dune_row)
    mint = token_mint(dune_row)
    signature = event_signature(dune_row)
    dt = dune_time(dune_row)
    for local in local_records:
        if wallet_address(local) != wallet or token_mint(local) != mint:
            continue
        if signature and signature == event_signature(local):
            return True
        lt = event_time(local)
        if dt is not None and lt is not None and abs(dt - lt) <= max_time_delta_seconds:
            return True
    return False


def nonoverlap_record(row: dict[str, Any]) -> dict[str, Any]:
    price = price_usd(row)
    amount = amount_usd(row)
    block_reasons = [
        "missing_decision_time_liquidity",
        "missing_decision_time_market_cap",
        "missing_forward_outcome_window",
    ]
    if price is None:
        block_reasons.append("missing_dune_token_price")
    return {
        "version": VERSION,
        "wallet_address": wallet_address(row),
        "token_mint": token_mint(row),
        "dune_transaction_signature": event_signature(row),
        "dune_block_time": row.get("block_time") or row.get("timestamp"),
        "dune_block_timestamp": dune_time(row),
        "amount_usd": amount,
        "price_usd": price,
        "status": "blocked_nonoverlap_historical_context",
        "block_reasons": block_reasons,
        "has_quote_anchor_candidate": amount is not None or price is not None,
        "has_price_context_candidate": price is not None,
        "has_liquidity_context": False,
        "has_market_cap_context": False,
        "has_forward_outcome": False,
        "proof_ready": False,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(records: list[dict[str, Any]], *, dune_dex_rows: int, local_overlap_rows: int) -> dict[str, Any]:
    blocks = Counter(reason for row in records for reason in row.get("block_reasons") or [])
    return {
        "dune_dex_rows": dune_dex_rows,
        "local_overlap_rows": local_overlap_rows,
        "nonoverlap_rows": len(records),
        "quote_anchor_candidate_rows": sum(1 for row in records if row.get("has_quote_anchor_candidate")),
        "price_context_candidate_rows": sum(1 for row in records if row.get("has_price_context_candidate")),
        "liquidity_context_rows": 0,
        "market_cap_context_rows": 0,
        "forward_outcome_rows": 0,
        "proof_ready_rows": 0,
        "wallets_with_nonoverlap_rows": len({row.get("wallet_address") for row in records if row.get("wallet_address")}),
        "tokens_with_nonoverlap_rows": len({row.get("token_mint") for row in records if row.get("token_mint")}),
        "block_reason_counts": dict(sorted(blocks.items())),
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "wallet_trust_mutations": 0,
    }


def build_dune_candidate_nonoverlap_slice(
    *,
    dune_rows: dict[str, Any],
    local_records: list[dict[str, Any]],
    candidate_wallets: list[str],
    generated_at: float | None = None,
    max_time_delta_seconds: float = 300.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    candidate_set = {str(wallet).strip() for wallet in candidate_wallets if str(wallet).strip()}
    dex_rows = [row for row in candidate_dex_rows(dune_rows) if is_candidate_wallet(row, candidate_set)]
    overlap_rows = [
        row for row in dex_rows if overlaps_local(row, local_records, max_time_delta_seconds=max_time_delta_seconds)
    ]
    nonoverlap = [
        nonoverlap_record(row)
        for row in dex_rows
        if not overlaps_local(row, local_records, max_time_delta_seconds=max_time_delta_seconds)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "candidate_wallets_only": True,
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "promotion_allowed": False,
        "proof_metrics_exclude_nonoverlap_rows_until_context_complete": True,
        "max_time_delta_seconds": float(max_time_delta_seconds),
        "summary": build_summary(nonoverlap, dune_dex_rows=len(dex_rows), local_overlap_rows=len(overlap_rows)),
        "nonoverlap_records": nonoverlap,
        "operator_note": (
            "Non-overlapping Dune rows are historical context candidates only. They remain excluded from proof "
            "metrics until liquidity, market cap, and forward outcome windows are reconstructed under the same "
            "candidate-only guardrails."
        ),
    }
