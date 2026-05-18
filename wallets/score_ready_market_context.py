from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY"
VERSION = "score_ready_market_context.v1"


def positive_float(value: Any) -> float | None:
    parsed = safe_float(value, None)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("wallet") or "").strip(),
        str(row.get("token_mint") or "").strip(),
        str(row.get("transaction_signature") or "").strip(),
    )


def index_supply_records(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows or []:
        if isinstance(row, dict):
            indexed[record_key(row)] = row
    return indexed


def merged_supply_records(
    supply_evidence_records: list[dict[str, Any]],
    archival_supply_records: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed = index_supply_records(supply_evidence_records)
    for row in archival_supply_records or []:
        if not isinstance(row, dict) or row.get("status") != "archival_supply_recovered":
            continue
        indexed[record_key(row)] = {
            **row,
            "status": "archival_supply_recovered",
            "decision_time_safe": True,
            "source": "archival_supply_evidence",
        }
    return indexed


def classify_record(row: dict[str, Any], supply_by_key: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    context = as_dict(row.get("decision_time_context"))
    supply = supply_by_key.get(record_key(row), {})
    price = positive_float(context.get("price") or context.get("price_usd"))
    liquidity = positive_float(context.get("liquidity") or context.get("liquidity_usd"))
    market_cap = positive_float(context.get("market_cap"))
    market_cap_source = str(context.get("market_cap_source") or "")
    token_supply = positive_float(context.get("token_supply") or supply.get("ui_supply"))
    if market_cap is None and price is not None and token_supply is not None:
        market_cap = price * token_supply
    decision_time_safe = context.get("decision_time_safe") is True
    block_reasons = {str(reason) for reason in row.get("block_reasons") or [] if str(reason).strip()}
    supply_status = str(supply.get("status") or "missing_supply_evidence")
    supply_decision_time_safe = supply.get("decision_time_safe") is True
    blocked_by: list[str] = []
    next_action = "NO_ACTION_SCORE_READY"
    readiness = "score_ready"

    if price is None:
        readiness = "blocked_missing_price"
        blocked_by.append("missing_price")
        next_action = "RECOVER_DECISION_TIME_PRICE"
    elif liquidity is None:
        readiness = "blocked_missing_liquidity"
        blocked_by.append("missing_liquidity")
        next_action = "RECOVER_DECISION_TIME_LIQUIDITY"
    elif not decision_time_safe:
        readiness = "blocked_not_decision_time_safe"
        blocked_by.append("not_decision_time_safe")
        next_action = "REBUILD_DECISION_TIME_CONTEXT"
    elif market_cap is None and token_supply is None:
        readiness = "needs_archival_supply_for_market_cap"
        blocked_by.append("missing_archival_supply")
        next_action = "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT"
    elif market_cap is None and token_supply is not None:
        readiness = "needs_market_cap_recompute"
        blocked_by.append("market_cap_not_materialized")
        next_action = "RECOMPUTE_MARKET_CAP_FROM_DECISION_TIME_SUPPLY"
    elif (
        market_cap_source in {"decision_time_token_supply", "archival_supply_evidence"}
        and not supply_decision_time_safe
        and supply_status != "missing_supply_evidence"
    ):
        readiness = "blocked_supply_not_decision_time_safe"
        blocked_by.append("supply_not_decision_time_safe")
        next_action = "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT"

    if readiness != "score_ready":
        if "blocked_missing_market_cap" in block_reasons and "market_cap" not in blocked_by:
            blocked_by.append("market_cap")
        if "blocked_missing_supply" in block_reasons and "missing_archival_supply" not in blocked_by:
            blocked_by.append("missing_archival_supply")

    return {
        "version": VERSION,
        "wallet": str(row.get("wallet") or "").strip(),
        "token_mint": str(row.get("token_mint") or "").strip(),
        "timestamp": safe_float(row.get("timestamp") or context.get("timestamp"), None),
        "transaction_signature": str(row.get("transaction_signature") or "").strip(),
        "readiness_status": readiness,
        "next_action": next_action,
        "decision_time_safe": decision_time_safe,
        "can_mutate_wallet_trust": False,
        "price_present": price is not None,
        "liquidity_present": liquidity is not None,
        "market_cap_present": market_cap is not None,
        "supply_present": token_supply is not None,
        "supply_status": supply_status,
        "supply_source": supply.get("source"),
        "supply_decision_time_safe": supply_decision_time_safe,
        "decimals": supply.get("decimals"),
        "price": price,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "token_supply": token_supply,
        "blocked_by": sorted(set(blocked_by)),
        "source_status": row.get("status"),
        "source_block_reasons": sorted(block_reasons),
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("readiness_status") or "unknown") for row in records)
    rows_with_price_liq = sum(1 for row in records if row.get("price_present") and row.get("liquidity_present"))
    archival_rows = statuses.get("needs_archival_supply_for_market_cap", 0)
    tokens_by_action: dict[str, set[str]] = defaultdict(set)
    wallets_by_action: dict[str, set[str]] = defaultdict(set)
    for row in records:
        action = str(row.get("next_action") or "UNKNOWN")
        if row.get("token_mint"):
            tokens_by_action[action].add(str(row["token_mint"]))
        if row.get("wallet"):
            wallets_by_action[action].add(str(row["wallet"]))
    return {
        "records_scanned": len(records),
        "score_ready_records": statuses.get("score_ready", 0),
        "near_score_ready_records": statuses.get("needs_archival_supply_for_market_cap", 0) + statuses.get("needs_market_cap_recompute", 0),
        "archival_supply_candidate_rows": archival_rows,
        "tokens_needing_archival_supply": len(tokens_by_action.get("FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT", set())),
        "wallets_needing_archival_supply": len(wallets_by_action.get("FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT", set())),
        "rows_with_price_and_liquidity": rows_with_price_liq,
        "blocked_missing_price_rows": statuses.get("blocked_missing_price", 0),
        "blocked_missing_liquidity_rows": statuses.get("blocked_missing_liquidity", 0),
        "blocked_not_decision_time_safe_rows": statuses.get("blocked_not_decision_time_safe", 0),
        "needs_market_cap_recompute_rows": statuses.get("needs_market_cap_recompute", 0),
        "status_counts": dict(sorted(statuses.items())),
        "next_action_counts": dict(sorted(Counter(str(row.get("next_action") or "UNKNOWN") for row in records).items())),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_score_ready_market_context_report(
    *,
    onchain_market_context_records: list[dict[str, Any]],
    supply_evidence_records: list[dict[str, Any]],
    archival_supply_records: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    supply_by_key = merged_supply_records(supply_evidence_records, archival_supply_records)
    records = [
        classify_record(row, supply_by_key)
        for row in onchain_market_context_records or []
        if isinstance(row, dict)
    ]
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": build_summary(records),
        "records": records,
        "operator_note": (
            "Score-ready market-context classification separates rows that only need archival supply "
            "from rows still missing price, liquidity, or decision-time safety. It cannot mutate wallet trust."
        ),
    }
