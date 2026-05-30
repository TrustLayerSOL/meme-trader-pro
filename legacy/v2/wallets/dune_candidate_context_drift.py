from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "DUNE_CANDIDATE_CONTEXT_DRIFT_REVIEW_ONLY"
VERSION = "dune_candidate_context_drift.v1"


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or "").strip()


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def value(row: dict[str, Any], *keys: str) -> float | None:
    ctx = entry_context(row)
    for key in keys:
        parsed = safe_float(ctx.get(key), None)
        if parsed is not None:
            return parsed
    return None


def outcome_15m(row: dict[str, Any]) -> str:
    labels = as_dict(row.get("outcome_window_labels"))
    return str(as_dict(labels.get("15m")).get("outcome_type") or "").lower()


def pct_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None or baseline == 0:
        return None
    return round(((candidate - baseline) / baseline) * 100.0, 6)


def near_equal(left: float | None, right: float | None, *, tolerance_pct: float = 0.01) -> bool:
    if left is None or right is None:
        return False
    return abs(pct_delta(left, right) or 0.0) <= tolerance_pct


def index_local_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in records or []:
        if not isinstance(row, dict):
            continue
        eid = event_id(row)
        if eid and eid not in indexed:
            indexed[eid] = row
    return indexed


def compare_record(
    dune: dict[str, Any],
    local: dict[str, Any] | None,
    *,
    max_price_delta_pct: float,
) -> dict[str, Any]:
    dune_price = value(dune, "price_usd", "price")
    dune_liquidity = value(dune, "liquidity")
    dune_market_cap = value(dune, "market_cap")
    row = {
        "version": VERSION,
        "event_id": event_id(dune),
        "wallet_address": wallet_address(dune),
        "token_mint": token_mint(dune),
        "transaction_signature": dune.get("transaction_signature"),
        "local_match": local is not None,
        "dune_price": dune_price,
        "local_price": None,
        "price_delta_pct": None,
        "dune_liquidity": dune_liquidity,
        "local_liquidity": None,
        "liquidity_delta_pct": None,
        "dune_market_cap": dune_market_cap,
        "local_market_cap": None,
        "market_cap_delta_pct": None,
        "dune_outcome_15m": outcome_15m(dune),
        "local_outcome_15m": None,
        "liquidity_match": False,
        "market_cap_match": False,
        "outcome_15m_match": False,
        "drift_status": "missing_local_match",
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }
    if local is None:
        return row

    local_price = value(local, "price_usd", "price")
    local_liquidity = value(local, "liquidity")
    local_market_cap = value(local, "market_cap")
    price_delta = pct_delta(dune_price, local_price)
    liquidity_delta = pct_delta(dune_liquidity, local_liquidity)
    market_cap_delta = pct_delta(dune_market_cap, local_market_cap)
    row.update(
        {
            "local_price": local_price,
            "price_delta_pct": price_delta,
            "local_liquidity": local_liquidity,
            "liquidity_delta_pct": liquidity_delta,
            "local_market_cap": local_market_cap,
            "market_cap_delta_pct": market_cap_delta,
            "local_outcome_15m": outcome_15m(local),
            "liquidity_match": near_equal(dune_liquidity, local_liquidity),
            "market_cap_match": near_equal(dune_market_cap, local_market_cap),
            "outcome_15m_match": outcome_15m(dune) == outcome_15m(local),
        }
    )
    if price_delta is not None and abs(price_delta) > float(max_price_delta_pct):
        row["drift_status"] = "material_price_drift"
    elif not row["liquidity_match"]:
        row["drift_status"] = "liquidity_drift"
    elif not row["market_cap_match"]:
        row["drift_status"] = "market_cap_drift"
    elif not row["outcome_15m_match"]:
        row["drift_status"] = "outcome_drift"
    else:
        row["drift_status"] = "no_material_drift"
    return row


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("drift_status") or "unknown") for row in records)
    price_deltas = [abs(float(row["price_delta_pct"])) for row in records if row.get("price_delta_pct") is not None]
    return {
        "dune_records_scanned": len(records),
        "local_matches": sum(1 for row in records if row.get("local_match") is True),
        "missing_local_match_records": statuses.get("missing_local_match", 0),
        "no_material_drift_records": statuses.get("no_material_drift", 0),
        "material_price_drift_records": statuses.get("material_price_drift", 0),
        "liquidity_drift_records": statuses.get("liquidity_drift", 0),
        "market_cap_drift_records": statuses.get("market_cap_drift", 0),
        "outcome_drift_records": statuses.get("outcome_drift", 0),
        "max_abs_price_delta_pct": round(max(price_deltas), 6) if price_deltas else None,
        "avg_abs_price_delta_pct": round(sum(price_deltas) / len(price_deltas), 6) if price_deltas else None,
        "status_counts": dict(sorted(statuses.items())),
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "wallet_trust_mutations": 0,
    }


def build_dune_candidate_context_drift(
    *,
    dune_completed_records: list[dict[str, Any]],
    local_records: list[dict[str, Any]],
    generated_at: float | None = None,
    max_price_delta_pct: float = 25.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    local_by_event = index_local_records(local_records)
    records = [
        compare_record(row, local_by_event.get(event_id(row)), max_price_delta_pct=max_price_delta_pct)
        for row in dune_completed_records or []
        if isinstance(row, dict)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "promotion_allowed": False,
        "max_price_delta_pct": float(max_price_delta_pct),
        "summary": build_summary(records),
        "drift_records": records,
        "operator_note": (
            "Dune context drift is a review-only comparison of context-confirmed Dune rows against local "
            "forward records. It cannot promote wallets, mutate trust, mutate wallet lists, or unlock execution."
        ),
    }
