from __future__ import annotations

import time
from collections import Counter
from typing import Any

from research.outcome_linker import build_later_outcome_from_snapshots, build_windowed_outcomes_from_snapshots
from wallets.historical_market_context_backfill import token_amount
from wallets.historical_quote_price_enrichment import normalize_quote_price_series
from wallets.onchain_market_context_recovery import (
    quote_usd_price_from_context,
    pool_candidates_from_transaction,
)
from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "ONCHAIN_LATER_OUTCOME_BACKFILL_REVIEW_ONLY"
VERSION = "onchain_later_outcome_backfill.v1"
KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser"}
DEFAULT_HORIZON_SECONDS = 900.0


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def record_id(record: dict[str, Any]) -> str:
    return str(first_present(record.get("decision_id"), record.get("event_id"), record.get("mint")) or "").strip()


def record_mint(record: dict[str, Any]) -> str:
    return str(first_present(record.get("mint"), as_dict(record.get("signal_context")).get("mint")) or "").strip()


def record_signal_time(record: dict[str, Any]) -> float | None:
    decision = as_dict(record.get("decision"))
    signal_context = as_dict(record.get("signal_context"))
    return safe_float(
        first_present(
            record.get("signal_timestamp"),
            decision.get("decision_timestamp"),
            signal_context.get("entry_timestamp"),
            signal_context.get("captured_at"),
        ),
        None,
    )


def record_wallet(record: dict[str, Any]) -> str:
    wallets = as_list(record.get("wallets"))
    for row in wallets:
        if isinstance(row, dict):
            wallet = str(first_present(row.get("wallet"), row.get("address")) or "").strip()
        else:
            wallet = str(row or "").strip()
        if wallet:
            return wallet
    return ""


def record_market(record: dict[str, Any]) -> dict[str, Any]:
    signal_context = as_dict(record.get("signal_context"))
    decision_context = as_dict(record.get("decision_context"))
    return as_dict(signal_context.get("market")) or as_dict(signal_context.get("market_info")) or as_dict(decision_context.get("market"))


def record_quote_mint(record: dict[str, Any]) -> str | None:
    market = record_market(record)
    quote = str(first_present(market.get("quote_mint"), market.get("pool_quote_mint")) or "").strip()
    return quote or None


def existing_outcome(record: dict[str, Any]) -> dict[str, Any]:
    return as_dict(first_present(record.get("later_token_outcome"), record.get("later_outcome")))


def outcome_known(outcome: dict[str, Any]) -> bool:
    outcome_type = str(outcome.get("outcome_type") or "").lower()
    if outcome_type in KNOWN_OUTCOMES:
        return True
    windows = as_dict(outcome.get("windows"))
    return any(str(as_dict(row).get("outcome_type") or "").lower() in KNOWN_OUTCOMES for row in windows.values())


def outcome_from_onchain_backfill(outcome: dict[str, Any]) -> bool:
    if outcome.get("onchain_later_outcome_backfill_applied") is True:
        return True
    if str(outcome.get("source") or "") == "onchain_later_raw_transaction_pool_balances":
        return True
    windows = as_dict(outcome.get("windows"))
    return any(
        str(as_dict(row).get("source") or "") == "onchain_later_raw_transaction_pool_balances"
        for row in windows.values()
    )


def raw_transaction_time(raw: dict[str, Any]) -> float | None:
    tx = as_dict(raw.get("transaction"))
    return safe_float(first_present(tx.get("blockTime"), raw.get("blockTime")), None)


def raw_transaction_signature(raw: dict[str, Any]) -> str:
    signature = str(raw.get("signature") or "").strip()
    if signature:
        return signature
    tx = as_dict(raw.get("transaction"))
    signatures = as_dict(tx.get("transaction")).get("signatures")
    if isinstance(signatures, list) and signatures:
        return str(signatures[0] or "").strip()
    return ""


def raw_contains_mint(raw: dict[str, Any], mint: str) -> bool:
    if str(raw.get("token_mint") or "").strip() == mint:
        return True
    tx = as_dict(raw.get("transaction"))
    meta = as_dict(tx.get("meta"))
    for field in ("preTokenBalances", "postTokenBalances"):
        for row in meta.get(field) or []:
            if isinstance(row, dict) and str(row.get("mint") or "").strip() == mint:
                return True
    return False


def raw_mints(raw: dict[str, Any]) -> set[str]:
    mints = {str(raw.get("token_mint") or "").strip()} - {""}
    tx = as_dict(raw.get("transaction"))
    meta = as_dict(tx.get("meta"))
    for field in ("preTokenBalances", "postTokenBalances"):
        for row in meta.get(field) or []:
            if isinstance(row, dict):
                mint = str(row.get("mint") or "").strip()
                if mint:
                    mints.add(mint)
    return mints


def index_raw_transactions_by_mint(raw_transactions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for raw in raw_transactions or []:
        if not isinstance(raw, dict):
            continue
        for mint in raw_mints(raw):
            indexed.setdefault(mint, []).append(raw)
    for rows in indexed.values():
        rows.sort(key=lambda raw: raw_transaction_time(raw) or 0.0)
    return indexed


def entry_anchor_snapshot(record: dict[str, Any], *, mint: str, signal_time: float) -> dict[str, Any] | None:
    market = record_market(record)
    price = safe_float(first_present(market.get("price"), market.get("price_usd")), None)
    liquidity = safe_float(first_present(market.get("liquidity"), market.get("liquidity_usd")), None)
    if price is None or price <= 0:
        return None
    row = {
        "time": signal_time,
        "mint": mint,
        "price": price,
        "liquidity": liquidity,
        "source": "decision_context_entry_anchor",
    }
    risk = as_dict(as_dict(record.get("signal_context")).get("risk"))
    risk_label = first_present(risk.get("risk_label"), as_dict(record.get("decision_context")).get("risk_label"))
    if risk_label:
        row["risk_label"] = risk_label
    return row


def raw_to_snapshot(
    *,
    raw: dict[str, Any],
    wallet: str,
    mint: str,
    quote_mint: str | None,
    quote_price_series: list[dict[str, float]],
    max_quote_age_seconds: float,
) -> dict[str, Any] | None:
    block_time = raw_transaction_time(raw)
    if block_time is None:
        return None
    candidates = pool_candidates_from_transaction(raw=raw, wallet=wallet, token_mint=mint, quote_mint=quote_mint)
    if not candidates:
        return None
    candidate = candidates[0]
    candidate_quote_mint = str(candidate.get("quote_mint") or quote_mint or "").strip()
    token_reserve = safe_float(first_present(candidate.get("pool_token_reserve_post"), candidate.get("pool_token_reserve_pre")), None)
    quote_reserve = safe_float(first_present(candidate.get("pool_quote_reserve_post"), candidate.get("pool_quote_reserve_pre")), None)
    if token_reserve is None or token_reserve <= 0 or quote_reserve is None or quote_reserve <= 0:
        return None
    quote_info = quote_usd_price_from_context(
        {"quote_mint": candidate_quote_mint},
        timestamp=block_time,
        quote_mint_override=candidate_quote_mint,
        quote_price_series=quote_price_series,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    quote_usd = safe_float(as_dict(quote_info).get("price_usd"), None)
    if quote_usd is None or quote_usd <= 0:
        return None
    price_in_quote = quote_reserve / token_reserve
    return {
        "time": block_time,
        "mint": mint,
        "price": price_in_quote * quote_usd,
        "liquidity": quote_reserve * quote_usd * 2,
        "source": "onchain_later_raw_transaction_pool_balances",
        "transaction_signature": raw_transaction_signature(raw),
        "pool_owner": candidate.get("pool_owner"),
        "quote_mint": candidate_quote_mint,
        "quote_usd_price": quote_usd,
        "quote_usd_price_source": as_dict(quote_info).get("source"),
    }


def build_snapshot_rows_for_record(
    record: dict[str, Any],
    *,
    raw_transactions: list[dict[str, Any]],
    quote_price_series: list[dict[str, float]],
    horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
    max_quote_age_seconds: float = 7200.0,
) -> list[dict[str, Any]]:
    mint = record_mint(record)
    signal_time = record_signal_time(record)
    if not mint or signal_time is None:
        return []
    wallet = record_wallet(record)
    quote_mint = record_quote_mint(record)
    end_time = signal_time + max(0.0, float(horizon_seconds))
    snapshots: list[dict[str, Any]] = []
    anchor = entry_anchor_snapshot(record, mint=mint, signal_time=signal_time)
    if anchor:
        snapshots.append(anchor)
    seen_signatures: set[str] = set()
    for raw in raw_transactions or []:
        if not isinstance(raw, dict) or not raw_contains_mint(raw, mint):
            continue
        block_time = raw_transaction_time(raw)
        if block_time is None or block_time < signal_time or block_time > end_time:
            continue
        signature = raw_transaction_signature(raw)
        if signature and signature in seen_signatures:
            continue
        snapshot = raw_to_snapshot(
            raw=raw,
            wallet=wallet,
            mint=mint,
            quote_mint=quote_mint,
            quote_price_series=quote_price_series,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        if not snapshot:
            continue
        if signature:
            seen_signatures.add(signature)
        snapshots.append(snapshot)
    snapshots.sort(key=lambda row: safe_float(row.get("time"), 0.0) or 0.0)
    return snapshots


def build_record_result(
    record: dict[str, Any],
    *,
    raw_transactions: list[dict[str, Any]],
    quote_price_series: list[dict[str, float]],
    horizon_seconds: float,
    max_quote_age_seconds: float,
) -> dict[str, Any]:
    mint = record_mint(record)
    signal_time = record_signal_time(record)
    current = existing_outcome(record)
    row = {
        "version": VERSION,
        "event_id": record_id(record),
        "token_mint": mint,
        "signal_time": signal_time,
        "status": "pending_onchain_later_outcome_backfill",
        "snapshots_used": 0,
        "known_15m_added": False,
        "preserved_existing_known_outcome": outcome_known(current),
        "block_reasons": [],
        "can_mutate_wallet_trust": False,
    }
    if row["preserved_existing_known_outcome"]:
        row["later_token_outcome"] = current
        if outcome_from_onchain_backfill(current):
            row["status"] = "onchain_later_outcome_labeled"
            row["known_15m_added"] = True
        else:
            row["status"] = "skipped_existing_known_outcome"
        return row
    snapshots = build_snapshot_rows_for_record(
        record,
        raw_transactions=raw_transactions,
        quote_price_series=quote_price_series,
        horizon_seconds=horizon_seconds,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    row["snapshots_used"] = len(snapshots)
    row["snapshot_sources"] = sorted({str(s.get("source") or "") for s in snapshots if s.get("source")})
    later_snapshots = [snap for snap in snapshots if str(snap.get("source")) != "decision_context_entry_anchor"]
    if signal_time is None or not mint:
        row["status"] = "blocked_missing_signal_identity"
        row["block_reasons"] = ["missing_mint_or_signal_time"]
        row["later_token_outcome"] = current or {"outcome_type": "unknown"}
        return row
    if not later_snapshots:
        row["status"] = "blocked_no_later_onchain_snapshots"
        row["block_reasons"] = ["missing_later_snapshot_rows"]
        row["later_token_outcome"] = current or {"outcome_type": "unknown"}
        return row
    outcome = build_later_outcome_from_snapshots(
        mint=mint,
        signal_time=signal_time,
        snapshots=snapshots,
        horizon_seconds=horizon_seconds,
    )
    outcome["windows"] = build_windowed_outcomes_from_snapshots(
        mint=mint,
        signal_time=signal_time,
        snapshots=snapshots,
    )
    outcome["source"] = "onchain_later_raw_transaction_pool_balances"
    outcome["snapshot_sources"] = row["snapshot_sources"]
    row["later_token_outcome"] = outcome
    outcome_15m = as_dict(as_dict(outcome.get("windows")).get("15m"))
    row["known_15m_added"] = str(outcome_15m.get("outcome_type") or "").lower() in KNOWN_OUTCOMES
    row["status"] = "onchain_later_outcome_labeled" if row["known_15m_added"] else "onchain_later_outcome_unknown"
    return row


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in records)
    blocks = Counter(reason for row in records for reason in row.get("block_reasons") or [])
    return {
        "records_scanned": len(records),
        "known_15m_outcomes_added": sum(1 for row in records if row.get("known_15m_added")),
        "existing_known_outcomes_preserved": statuses.get("skipped_existing_known_outcome", 0),
        "records_with_onchain_snapshots": sum(1 for row in records if int(row.get("snapshots_used") or 0) > 0),
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
        "tokens_affected": len({row.get("token_mint") for row in records if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_onchain_later_outcome_backfill_report(
    *,
    records: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    quote_price_series: list[dict[str, Any]] | None = None,
    horizon_seconds: float = DEFAULT_HORIZON_SECONDS,
    max_quote_age_seconds: float = 7200.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    normalized_quote_prices = normalize_quote_price_series(quote_price_series or [])
    raw_by_mint = index_raw_transactions_by_mint(raw_transactions)
    results = [
        build_record_result(
            record,
            raw_transactions=raw_by_mint.get(record_mint(record), []),
            quote_price_series=normalized_quote_prices,
            horizon_seconds=horizon_seconds,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        for record in records or []
        if isinstance(record, dict)
    ]
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "horizon_seconds": horizon_seconds,
        "max_quote_age_seconds": max_quote_age_seconds,
        "quote_price_points": len(normalized_quote_prices),
        "summary": build_summary(results),
        "records": results,
        "operator_note": (
            "On-chain later outcomes are evaluation-only. They are built from raw transactions after the signal timestamp "
            "and must never be copied into decision-time context or live execution logic."
        ),
    }
