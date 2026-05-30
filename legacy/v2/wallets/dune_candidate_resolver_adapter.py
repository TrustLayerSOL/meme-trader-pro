from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "DUNE_CANDIDATE_RESOLVER_ADAPTER_REVIEW_ONLY"
VERSION = "dune_candidate_resolver_adapter.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or "").strip()


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or "").strip()


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("block_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason)]
    if isinstance(reasons, str) and reasons:
        return [reasons]
    return []


def joined_index(joined_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in joined_events:
        if not isinstance(row, dict):
            continue
        eid = event_id(row)
        if eid and eid not in indexed:
            indexed[eid] = row
    return indexed


def quality_for_join(join: dict[str, Any]) -> str:
    if safe_float(join.get("price_usd")) is not None:
        return "dune_price_candidate"
    return "dune_quote_candidate"


def adapted_record(row: dict[str, Any], join: dict[str, Any], generated_at: float) -> dict[str, Any]:
    context = dict(as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context")))
    price = safe_float(join.get("price_usd"))
    amount_usd = safe_float(join.get("amount_usd"))
    dune_context = {
        "source": "dune_candidate_join",
        "match_type": join.get("match_type"),
        "dune_transaction_signature": join.get("dune_transaction_signature"),
        "dune_block_time": join.get("dune_block_time"),
        "time_delta_seconds": join.get("time_delta_seconds"),
        "amount_usd": amount_usd,
        "price_usd": price,
        "evidence_quality": join.get("evidence_quality"),
        "decision_time_safe": True,
        "generated_at": generated_at,
    }
    if price is not None:
        context["price"] = price
        context["price_usd"] = price
        context["price_source"] = "dune_dex_trade_candidate"
        context["repair_confidence"] = "dune_candidate_price_not_score_ready"
    if amount_usd is not None:
        context["dune_amount_usd"] = amount_usd
    context["dune_dex_trade_candidate"] = dune_context
    context["decision_time_safe"] = True

    reasons = set(block_reasons(row))
    if price is not None:
        reasons.discard("missing_forward_entry_price")
    reasons.update(
        {
            "dune_context_not_score_ready",
            "missing_forward_liquidity",
            "missing_forward_market_cap",
        }
    )
    return {
        **row,
        "version": VERSION,
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": sorted(reasons),
        "decision_context": {
            **as_dict(row.get("decision_context")),
            "estimated_entry_context": context,
        },
        "dune_context_candidate": {
            "source": "dune_candidate_resolver_adapter",
            "quality": quality_for_join(join),
            "proof_ready": False,
            "missing_for_proof": ["liquidity", "market_cap"],
            "generated_at": generated_at,
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def audit_row(record: dict[str, Any]) -> dict[str, Any]:
    candidate = as_dict(record.get("dune_context_candidate"))
    context = as_dict(as_dict(record.get("decision_context")).get("estimated_entry_context"))
    dune = as_dict(context.get("dune_dex_trade_candidate"))
    return {
        "event_id": event_id(record),
        "wallet_address": wallet_address(record),
        "token_mint": token_mint(record),
        "transaction_signature": record.get("transaction_signature"),
        "dune_transaction_signature": dune.get("dune_transaction_signature"),
        "quality": candidate.get("quality"),
        "price_usd": context.get("price_usd"),
        "amount_usd": context.get("dune_amount_usd"),
        "proof_ready": candidate.get("proof_ready"),
        "block_reasons": ",".join(block_reasons(record)),
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_dune_candidate_resolver_adapter(
    *,
    records: list[dict[str, Any]],
    dune_join: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    joined_events = [row for row in as_list(dune_join.get("joined_events")) if isinstance(row, dict)]
    by_event = joined_index(joined_events)
    context_candidates: list[dict[str, Any]] = []
    for row in records or []:
        if not isinstance(row, dict):
            continue
        join = by_event.get(event_id(row))
        if not join:
            continue
        context_candidates.append(adapted_record(row, join, generated_at))

    qualities = Counter(as_dict(row.get("dune_context_candidate")).get("quality") for row in context_candidates)
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
        "proof_metrics_exclude_dune_candidates_until_context_complete": True,
        "summary": {
            "records_scanned": len(records or []),
            "joined_events_scanned": len(joined_events),
            "context_candidate_records": len(context_candidates),
            "price_candidate_records": int(qualities.get("dune_price_candidate", 0)),
            "quote_only_candidate_records": int(qualities.get("dune_quote_candidate", 0)),
            "liquidity_candidate_records": 0,
            "market_cap_candidate_records": 0,
            "proof_ready_records": 0,
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
        },
        "audit_rows": [audit_row(row) for row in context_candidates],
        "context_candidate_records": context_candidates,
        "limitations": [
            "dune_context_candidates_remain_blocked",
            "liquidity_required_before_proof_metrics",
            "market_cap_required_before_proof_metrics",
        ],
        "recommended_next_actions": [
            "Reconstruct pool liquidity for Dune-matched token/time rows.",
            "Reconstruct token supply or trusted market cap for Dune-matched token/time rows.",
            "Only then rerun candidate walk-forward validation with score-ready repaired rows.",
        ],
    }
