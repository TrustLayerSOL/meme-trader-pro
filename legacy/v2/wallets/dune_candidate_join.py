from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


MODE = "DUNE_CANDIDATE_JOIN_REVIEW_ONLY"
VERSION = "dune_candidate_join.v1"


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or row.get("trader_id") or "").strip()


def token_mint(row: dict[str, Any]) -> str:
    return str(
        row.get("token_mint")
        or row.get("token_mint_address")
        or row.get("token_bought_mint_address")
        or row.get("token_sold_mint_address")
        or ""
    ).strip()


def event_signature(row: dict[str, Any]) -> str:
    return str(row.get("transaction_signature") or row.get("signature") or row.get("tx_hash") or row.get("tx_id") or "").strip()


def event_time(row: dict[str, Any]) -> float | None:
    return as_float(row.get("signal_time") or row.get("observed_at") or row.get("timestamp"), None)


def parse_dune_time(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return as_float(value, None)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace(" UTC", "+00:00")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %Z", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def dune_row_time(row: dict[str, Any]) -> float | None:
    return parse_dune_time(row.get("block_time") or row.get("timestamp"))


def normalize_dex_rows(dune_dex_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in dune_dex_rows:
        if not isinstance(row, dict):
            continue
        normalized = dict(row)
        normalized["wallet_address"] = wallet_address(row)
        normalized["token_mint"] = token_mint(row)
        normalized["transaction_signature"] = event_signature(row)
        normalized["block_timestamp"] = dune_row_time(row)
        rows.append(normalized)
    return rows


def best_match(
    event: dict[str, Any],
    dex_rows: list[dict[str, Any]],
    *,
    max_time_delta_seconds: float,
) -> tuple[dict[str, Any] | None, str | None, float | None]:
    wallet = wallet_address(event)
    mint = token_mint(event)
    signature = event_signature(event)
    timestamp = event_time(event)
    candidates = [row for row in dex_rows if row.get("wallet_address") == wallet and row.get("token_mint") == mint]
    if signature:
        for row in candidates:
            if row.get("transaction_signature") == signature:
                row_time = as_float(row.get("block_timestamp"), None)
                delta = abs((timestamp or row_time or 0.0) - (row_time or timestamp or 0.0)) if timestamp is not None and row_time is not None else None
                return row, "signature_exact", delta
    if timestamp is None:
        return None, None, None
    best: tuple[dict[str, Any], float] | None = None
    for row in candidates:
        row_time = as_float(row.get("block_timestamp"), None)
        if row_time is None:
            continue
        delta = abs(timestamp - row_time)
        if delta <= max_time_delta_seconds and (best is None or delta < best[1]):
            best = (row, delta)
    if best:
        return best[0], "wallet_token_time_window", best[1]
    return None, None, None


def joined_event(event: dict[str, Any], dune_row: dict[str, Any], match_type: str, delta: float | None) -> dict[str, Any]:
    price = as_float(dune_row.get("price_usd"), None)
    amount_usd = as_float(dune_row.get("amount_usd"), None)
    return {
        "event_id": str(event.get("event_id") or ""),
        "wallet_address": wallet_address(event),
        "token_mint": token_mint(event),
        "local_transaction_signature": event_signature(event),
        "dune_transaction_signature": dune_row.get("transaction_signature"),
        "local_signal_time": event_time(event),
        "dune_block_time": dune_row.get("block_time") or dune_row.get("timestamp"),
        "time_delta_seconds": round(delta, 6) if delta is not None else None,
        "match_type": match_type,
        "amount_usd": amount_usd,
        "price_usd": price,
        "has_quote_anchor_candidate": amount_usd is not None or price is not None,
        "has_price_context_candidate": price is not None,
        "has_liquidity_context": False,
        "has_market_cap_context": False,
        "proof_ready": False,
        "evidence_quality": "dune_quote_price_candidate_not_score_ready",
        "missing_for_proof": ["liquidity", "market_cap"],
        "notes": "Dune DEX row is usable as candidate context only until liquidity and market cap are decision-time safe.",
    }


def build_dune_candidate_join_report(
    *,
    records: list[dict[str, Any]],
    dune_dex_rows: list[dict[str, Any]],
    candidate_wallets: list[str],
    max_time_delta_seconds: float = 300.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    candidate_set = {str(wallet).strip() for wallet in candidate_wallets if str(wallet).strip()}
    candidate_events = [row for row in records if wallet_address(row) in candidate_set]
    normalized_dex_rows = normalize_dex_rows(dune_dex_rows)
    joined: list[dict[str, Any]] = []
    exact = 0
    time_window = 0
    for event in candidate_events:
        match, match_type, delta = best_match(event, normalized_dex_rows, max_time_delta_seconds=max_time_delta_seconds)
        if not match or not match_type:
            continue
        if match_type == "signature_exact":
            exact += 1
        elif match_type == "wallet_token_time_window":
            time_window += 1
        joined.append(joined_event(event, match, match_type, delta))

    summary = {
        "candidate_wallets": len(candidate_set),
        "candidate_events_scanned": len(candidate_events),
        "dune_dex_rows": len(normalized_dex_rows),
        "matched_events": len(joined),
        "unmatched_candidate_events": max(0, len(candidate_events) - len(joined)),
        "exact_signature_matches": exact,
        "time_window_matches": time_window,
        "quote_anchor_candidate_events": sum(1 for row in joined if row["has_quote_anchor_candidate"]),
        "price_context_candidate_events": sum(1 for row in joined if row["has_price_context_candidate"]),
        "liquidity_context_candidate_events": 0,
        "market_cap_context_candidate_events": 0,
        "proof_ready_events": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "wallet_trust_mutations": 0,
    }
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
        "proof_metrics_exclude_dune_candidates_until_context_complete": True,
        "max_time_delta_seconds": float(max_time_delta_seconds),
        "summary": summary,
        "joined_events": joined,
        "limitations": [
            "dune_join_does_not_provide_liquidity",
            "dune_join_does_not_provide_market_cap",
            "matched_rows_are_context_candidates_not_trust_proof",
        ],
        "recommended_next_actions": [
            "Route matched Dune rows through a resolver that can preserve quote and price candidates.",
            "Keep liquidity and market-cap blockers open until pool reserve and supply evidence is available.",
            "Do not promote wallets or mutate trust from Dune matches.",
        ],
    }
