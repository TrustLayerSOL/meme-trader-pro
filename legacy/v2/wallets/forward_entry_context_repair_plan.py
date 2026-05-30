from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


MODE = "FORWARD_ENTRY_CONTEXT_REPAIR_PLAN_REVIEW_ONLY"
VERSION = "forward_entry_context_repair_plan.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def is_blocked_entry_context(row: dict[str, Any]) -> bool:
    if str(row.get("status") or "") != "blocked_missing_forward_entry_context":
        return False
    return "missing_forward_entry_price" in [str(reason) for reason in row.get("block_reasons") or []]


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def snapshot_mints(market_snapshots: list[dict[str, Any]]) -> set[str]:
    mints: set[str] = set()
    for row in market_snapshots or []:
        if not isinstance(row, dict):
            continue
        mint = str(row.get("mint") or row.get("token_mint") or "").strip()
        if mint:
            mints.add(mint)
    return mints


def repair_method(row: dict[str, Any]) -> str:
    context = entry_context(row)
    if safe_float(context.get("price"), None):
        return "ALREADY_HAS_PRICE_ANCHOR"
    if safe_float(context.get("execution_price_quote"), None):
        return "USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR"
    if safe_float(context.get("market_cap"), None) or safe_float(context.get("liquidity"), None):
        return "PARTIAL_CONTEXT_NEEDS_PRICE_ANCHOR"
    return "NEEDS_FORWARD_MARKET_SNAPSHOT"


def row_repair_action(method: str) -> str:
    if method in {"ALREADY_HAS_PRICE_ANCHOR", "USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR"}:
        return "QUOTE_ANCHOR_REPAIR"
    if method == "PARTIAL_CONTEXT_NEEDS_PRICE_ANCHOR":
        return "PRICE_ANCHOR_REQUIRED"
    return "MARKET_SNAPSHOT_REQUIRED"


def token_row(row: dict[str, Any], mints_with_snapshots: set[str]) -> dict[str, Any]:
    context = entry_context(row)
    method = repair_method(row)
    mint = str(row.get("token_mint") or "").strip()
    has_later_snapshots = mint in mints_with_snapshots
    return {
        "wallet": row.get("wallet"),
        "token_mint": mint,
        "transaction_signature": row.get("transaction_signature"),
        "signal_time": row.get("signal_time"),
        "repair_method": method,
        "repair_action": row_repair_action(method),
        "has_later_market_snapshots": has_later_snapshots,
        "has_execution_price_quote": safe_float(context.get("execution_price_quote"), None) is not None,
        "has_quote_delta": safe_float(context.get("quote_amount_delta"), None) is not None,
        "has_liquidity": safe_float(context.get("liquidity"), None) is not None,
        "has_market_cap": safe_float(context.get("market_cap"), None) is not None,
        "source": context.get("execution_price_source") or "unknown",
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def wallet_repair_action(method_counts: Counter[str], *, quote_without_snapshots: int) -> str:
    quote_rows = method_counts.get("USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR", 0) + method_counts.get(
        "ALREADY_HAS_PRICE_ANCHOR", 0
    )
    market_rows = method_counts.get("NEEDS_FORWARD_MARKET_SNAPSHOT", 0)
    partial_rows = method_counts.get("PARTIAL_CONTEXT_NEEDS_PRICE_ANCHOR", 0)
    if quote_rows and quote_without_snapshots == 0 and not market_rows and not partial_rows:
        return "QUOTE_ANCHOR_REPAIR_READY"
    if (market_rows or quote_without_snapshots) and not partial_rows and quote_rows == quote_without_snapshots:
        return "NEEDS_MARKET_CONTEXT_COLLECTION"
    return "MIXED_REPAIR"


def wallet_row(wallet: str, rows: list[dict[str, Any]], mints_with_snapshots: set[str]) -> dict[str, Any]:
    token_rows = [token_row(row, mints_with_snapshots) for row in rows]
    methods = Counter(str(row.get("repair_method") or "unknown") for row in token_rows)
    quote_rows = methods.get("USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR", 0) + methods.get(
        "ALREADY_HAS_PRICE_ANCHOR", 0
    )
    quote_without_snapshots = sum(
        1
        for row in token_rows
        if row.get("repair_method") in {"USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR", "ALREADY_HAS_PRICE_ANCHOR"}
        and not row.get("has_later_market_snapshots")
    )
    market_rows = methods.get("NEEDS_FORWARD_MARKET_SNAPSHOT", 0)
    partial_rows = methods.get("PARTIAL_CONTEXT_NEEDS_PRICE_ANCHOR", 0)
    return {
        "wallet": wallet,
        "review_only": True,
        "blocked_rows": len(rows),
        "tokens": len({row.get("token_mint") for row in token_rows if row.get("token_mint")}),
        "quote_anchor_repair_rows": quote_rows,
        "quote_anchor_and_snapshot_rows": quote_rows - quote_without_snapshots,
        "quote_anchor_without_snapshot_rows": quote_without_snapshots,
        "needs_market_snapshot_rows": market_rows,
        "partial_context_rows": partial_rows,
        "repair_methods": sorted(methods),
        "repair_action": wallet_repair_action(methods, quote_without_snapshots=quote_without_snapshots),
        "examples": token_rows[:5],
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(wallets: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter(str(row.get("repair_action") or "unknown") for row in wallets)
    return {
        "wallets": len(wallets),
        "blocked_rows": sum(int(row.get("blocked_rows") or 0) for row in wallets),
        "quote_anchor_repair_rows": sum(int(row.get("quote_anchor_repair_rows") or 0) for row in wallets),
        "quote_anchor_and_snapshot_rows": sum(int(row.get("quote_anchor_and_snapshot_rows") or 0) for row in wallets),
        "quote_anchor_without_snapshot_rows": sum(int(row.get("quote_anchor_without_snapshot_rows") or 0) for row in wallets),
        "needs_market_snapshot_rows": sum(int(row.get("needs_market_snapshot_rows") or 0) for row in wallets),
        "partial_context_rows": sum(int(row.get("partial_context_rows") or 0) for row in wallets),
        "quote_anchor_repair_wallets": actions.get("QUOTE_ANCHOR_REPAIR_READY", 0),
        "market_context_collection_wallets": actions.get("NEEDS_MARKET_CONTEXT_COLLECTION", 0),
        "mixed_repair_wallets": actions.get("MIXED_REPAIR", 0),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def rank_wallet(row: dict[str, Any]) -> tuple[int, int, str]:
    rank = {
        "QUOTE_ANCHOR_REPAIR_READY": 0,
        "MIXED_REPAIR": 1,
        "NEEDS_MARKET_CONTEXT_COLLECTION": 2,
    }.get(str(row.get("repair_action") or ""), 9)
    return (rank, -int(row.get("blocked_rows") or 0), str(row.get("wallet") or ""))


def build_forward_entry_context_repair_plan(
    records: list[dict[str, Any]],
    *,
    market_snapshots: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    mints_with_snapshots = snapshot_mints(market_snapshots or [])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records or []:
        if not isinstance(row, dict) or not is_blocked_entry_context(row):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            grouped[wallet].append(row)
    wallets = sorted(
        (wallet_row(wallet, rows, mints_with_snapshots) for wallet, rows in grouped.items()),
        key=rank_wallet,
    )
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(wallets),
        "wallets": wallets,
        "operator_note": (
            "Entry-context repair plan is review-only. It identifies which blocked forward rows can be "
            "repaired from existing quote anchors versus which need new market snapshots."
        ),
    }
