from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "DUNE_CANDIDATE_CONTEXT_COMPLETION_REVIEW_ONLY"
VERSION = "dune_candidate_context_completion.v1"


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def signal_time(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("signal_time") or row.get("timestamp"), None)


def positive_float(value: Any) -> float | None:
    parsed = safe_float(value, None)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("block_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason)]
    return [str(reasons)] if reasons else []


def snapshots_by_mint(snapshots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in snapshots or []:
        if not isinstance(row, dict):
            continue
        mint = token_mint(row)
        if not mint:
            continue
        grouped.setdefault(mint, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: safe_float(row.get("time"), 0.0) or 0.0)
    return grouped


def nearest_later_snapshot(
    row: dict[str, Any],
    grouped_snapshots: dict[str, list[dict[str, Any]]],
    *,
    max_snapshot_lag_seconds: float,
) -> dict[str, Any] | None:
    mint = token_mint(row)
    ts = signal_time(row)
    if not mint or ts is None:
        return None
    max_lag = max(0.0, float(max_snapshot_lag_seconds))
    for snapshot in grouped_snapshots.get(mint, []):
        snapshot_time = safe_float(snapshot.get("time"), None)
        if snapshot_time is None:
            continue
        lag = snapshot_time - ts
        if 0 <= lag <= max_lag:
            return snapshot
    return None


def completion_status(context: dict[str, Any], snapshot: dict[str, Any] | None) -> tuple[str, list[str]]:
    price = positive_float(context.get("price") or context.get("price_usd"))
    liquidity = positive_float(as_dict(snapshot or {}).get("liquidity"))
    market_cap = positive_float(as_dict(snapshot or {}).get("market_cap"))
    missing: list[str] = []
    if price is None:
        missing.append("missing_price")
    if snapshot is None:
        missing.append("missing_near_market_snapshot")
    if liquidity is None:
        missing.append("missing_liquidity")
    if market_cap is None:
        missing.append("missing_market_cap")
    if missing:
        return "blocked_missing_forward_entry_context", missing
    return "dune_candidate_context_complete_review_only", []


def complete_record(
    row: dict[str, Any],
    snapshot: dict[str, Any] | None,
    *,
    generated_at: float,
) -> dict[str, Any]:
    current_context = dict(entry_context(row))
    status, missing = completion_status(current_context, snapshot)
    reasons = set(block_reasons(row))
    if snapshot is not None:
        liquidity = positive_float(snapshot.get("liquidity"))
        market_cap = positive_float(snapshot.get("market_cap"))
        snapshot_time = safe_float(snapshot.get("time"), None)
        ts = signal_time(row)
        if liquidity is not None:
            current_context["liquidity"] = liquidity
            current_context["liquidity_source"] = "near_event_forward_market_snapshot"
            reasons.discard("missing_forward_liquidity")
        if market_cap is not None:
            current_context["market_cap"] = market_cap
            current_context["market_cap_source"] = "near_event_forward_market_snapshot"
            reasons.discard("missing_forward_market_cap")
        current_context["market_snapshot_source"] = snapshot.get("source")
        current_context["market_snapshot_time"] = snapshot_time
        current_context["market_snapshot_lag_seconds"] = (
            round(snapshot_time - ts, 6) if snapshot_time is not None and ts is not None else None
        )
    if status == "dune_candidate_context_complete_review_only":
        reasons.discard("dune_context_not_score_ready")
    else:
        reasons.add("dune_context_not_score_ready")
        if "missing_price" in missing:
            reasons.add("missing_forward_entry_price")
        if "missing_liquidity" in missing:
            reasons.add("missing_forward_liquidity")
        if "missing_market_cap" in missing:
            reasons.add("missing_forward_market_cap")
        if "missing_near_market_snapshot" in missing:
            reasons.add("missing_near_market_snapshot")

    return {
        **row,
        "version": VERSION,
        "status": status,
        "block_reasons": sorted(reasons),
        "decision_context": {
            **as_dict(row.get("decision_context")),
            "estimated_entry_context": current_context,
        },
        "dune_context_completion": {
            "source": "dune_candidate_context_completion",
            "context_complete": status == "dune_candidate_context_complete_review_only",
            "proof_ready_candidate": status == "dune_candidate_context_complete_review_only",
            "missing_for_completion": missing,
            "generated_at": generated_at,
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def audit_row(row: dict[str, Any]) -> dict[str, Any]:
    context = entry_context(row)
    completion = as_dict(row.get("dune_context_completion"))
    return {
        "event_id": row.get("event_id"),
        "wallet_address": row.get("wallet") or row.get("wallet_address"),
        "token_mint": token_mint(row),
        "transaction_signature": row.get("transaction_signature"),
        "status": row.get("status"),
        "price_usd": context.get("price_usd") or context.get("price"),
        "liquidity": context.get("liquidity"),
        "market_cap": context.get("market_cap"),
        "market_snapshot_lag_seconds": context.get("market_snapshot_lag_seconds"),
        "proof_ready_candidate": completion.get("proof_ready_candidate"),
        "block_reasons": ",".join(block_reasons(row)),
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in records)
    blocks = Counter(reason for row in records for reason in block_reasons(row))
    return {
        "candidate_records_scanned": len(records),
        "context_complete_records": statuses.get("dune_candidate_context_complete_review_only", 0),
        "proof_ready_candidate_records": statuses.get("dune_candidate_context_complete_review_only", 0),
        "blocked_records": len(records) - statuses.get("dune_candidate_context_complete_review_only", 0),
        "blocked_missing_price_records": blocks.get("missing_forward_entry_price", 0),
        "blocked_missing_liquidity_records": blocks.get("missing_forward_liquidity", 0),
        "blocked_missing_market_cap_records": blocks.get("missing_forward_market_cap", 0),
        "status_counts": dict(sorted(statuses.items())),
        "block_reason_counts": dict(sorted(blocks.items())),
        "wallet_list_mutations": 0,
        "wallet_trust_mutations": 0,
        "promotions_allowed": 0,
    }


def build_dune_candidate_context_completion(
    *,
    candidate_records: list[dict[str, Any]],
    market_snapshots: list[dict[str, Any]],
    generated_at: float | None = None,
    max_snapshot_lag_seconds: float = 120.0,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped = snapshots_by_mint(market_snapshots)
    records = [
        complete_record(
            row,
            nearest_later_snapshot(row, grouped, max_snapshot_lag_seconds=max_snapshot_lag_seconds),
            generated_at=generated_at,
        )
        for row in candidate_records or []
        if isinstance(row, dict)
    ]
    completed = [row for row in records if row.get("status") == "dune_candidate_context_complete_review_only"]
    blocked = [row for row in records if row.get("status") != "dune_candidate_context_complete_review_only"]
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
        "max_snapshot_lag_seconds": max_snapshot_lag_seconds,
        "summary": build_summary(records),
        "audit_rows": [audit_row(row) for row in records],
        "completed_records": completed,
        "blocked_records": blocked,
        "operator_note": (
            "Dune candidate context completion is candidate-only and review-only. Completed rows have price, "
            "near-event liquidity, and near-event market cap, but no wallet trust, wallet list, promotion, "
            "or execution setting can be mutated by this report."
        ),
    }
