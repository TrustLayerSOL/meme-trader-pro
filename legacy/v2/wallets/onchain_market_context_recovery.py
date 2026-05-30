from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any

from wallets.historical_market_context_backfill import index_raw_transactions, token_amount
from wallets.historical_quote_price_enrichment import nearest_prior_quote_price, normalize_quote_price_series
from wallets.wallet_evidence_models import as_dict, safe_float
from wallets.wallet_history_parser import QUOTE_MINTS


MODE = "ONCHAIN_MARKET_CONTEXT_RECOVERY_REVIEW_ONLY"
RECOVERY_VERSION = "onchain_market_context_recovery.v1"

WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
STABLE_USD_QUOTE_MINTS = {USDC_MINT, USDT_MINT}
LAMPORTS_PER_SOL = 1_000_000_000


def positive_float(value: Any) -> float | None:
    parsed = safe_float(value, None)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def first_positive(*values: Any) -> float | None:
    for value in values:
        parsed = positive_float(value)
        if parsed is not None:
            return parsed
    return None


def balance_rows_by_owner(tx: dict[str, Any], field: str) -> dict[str, dict[str, float]]:
    meta = as_dict(tx.get("meta"))
    owners: dict[str, dict[str, float]] = {}
    for row in meta.get(field) or []:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        mint = str(row.get("mint") or "").strip()
        if not owner or not mint:
            continue
        owners.setdefault(owner, {})
        owners[owner][mint] = owners[owner].get(mint, 0.0) + (token_amount(row) or 0.0)
    return owners


def account_key_pubkeys(tx: dict[str, Any]) -> list[str]:
    message = as_dict(as_dict(tx.get("transaction")).get("message"))
    pubkeys: list[str] = []
    for row in message.get("accountKeys") or []:
        if isinstance(row, dict):
            pubkey = str(row.get("pubkey") or "").strip()
        else:
            pubkey = str(row or "").strip()
        pubkeys.append(pubkey)
    return pubkeys


def native_sol_balances_by_account(tx: dict[str, Any]) -> dict[str, dict[str, float]]:
    meta = as_dict(tx.get("meta"))
    pubkeys = account_key_pubkeys(tx)
    pre_balances = meta.get("preBalances") or []
    post_balances = meta.get("postBalances") or []
    balances: dict[str, dict[str, float]] = {}
    for index, pubkey in enumerate(pubkeys):
        if not pubkey:
            continue
        pre = safe_float(pre_balances[index] if index < len(pre_balances) else None, 0.0) or 0.0
        post = safe_float(post_balances[index] if index < len(post_balances) else None, 0.0) or 0.0
        balances[pubkey] = {
            "pre": pre / LAMPORTS_PER_SOL,
            "post": post / LAMPORTS_PER_SOL,
        }
    return balances


def quote_usd_price_from_context(
    context: dict[str, Any],
    *,
    timestamp: float | None = None,
    quote_mint_override: str | None = None,
    quote_price_series: list[dict[str, float]] | None = None,
    max_quote_age_seconds: float = 7200.0,
) -> dict[str, Any] | None:
    quote_mint = str(quote_mint_override or context.get("quote_mint") or "").strip()
    if quote_mint in STABLE_USD_QUOTE_MINTS:
        return {"price_usd": 1.0, "source": "stable_quote"}
    explicit = first_positive(context.get("quote_usd_price"), context.get("historical_quote_usd_price"))
    if explicit is not None:
        return {"price_usd": explicit, "source": str(context.get("quote_usd_price_source") or "decision_time_context")}
    price = positive_float(context.get("price"))
    price_in_quote = positive_float(context.get("price_in_quote"))
    if price is not None and price_in_quote is not None:
        return {"price_usd": price / price_in_quote, "source": "derived_from_price_and_quote"}
    if quote_mint == WSOL_MINT and quote_price_series:
        prior, status = nearest_prior_quote_price(
            quote_price_series,
            timestamp,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        if status == "quote_usd_price_recovered" and prior:
            return {
                "price_usd": prior["price_usd"],
                "source": "historical_quote_price_series",
                "timestamp": prior["timestamp"],
                "age_seconds": round((timestamp or 0.0) - prior["timestamp"], 6) if timestamp is not None else None,
            }
    return None


def pool_candidates_from_transaction(
    *,
    raw: dict[str, Any],
    wallet: str,
    token_mint: str,
    quote_mint: str | None,
) -> list[dict[str, Any]]:
    tx = as_dict(raw.get("transaction"))
    pre_by_owner = balance_rows_by_owner(tx, "preTokenBalances")
    post_by_owner = balance_rows_by_owner(tx, "postTokenBalances")
    native_sol_by_account = native_sol_balances_by_account(tx)
    owners = set(pre_by_owner) | set(post_by_owner)
    quote_mints = [quote_mint] if quote_mint else []
    quote_mints.extend(mint for mint in QUOTE_MINTS if mint not in quote_mints)

    candidates: list[dict[str, Any]] = []
    for owner in sorted(owners):
        if owner == wallet:
            continue
        pre = pre_by_owner.get(owner, {})
        post = post_by_owner.get(owner, {})
        token_pre = safe_float(pre.get(token_mint), 0.0) or 0.0
        token_post = safe_float(post.get(token_mint), 0.0) or 0.0
        if token_pre <= 0 and token_post <= 0:
            continue
        for candidate_quote_mint in quote_mints:
            if not candidate_quote_mint:
                continue
            quote_pre = safe_float(pre.get(candidate_quote_mint), 0.0) or 0.0
            quote_post = safe_float(post.get(candidate_quote_mint), 0.0) or 0.0
            quote_reserve_source = "token_balance_owner"
            if candidate_quote_mint == WSOL_MINT and quote_pre <= 0 and quote_post <= 0:
                native = native_sol_by_account.get(owner) or {}
                quote_pre = safe_float(native.get("pre"), 0.0) or 0.0
                quote_post = safe_float(native.get("post"), 0.0) or 0.0
                if quote_pre > 0 or quote_post > 0:
                    quote_reserve_source = "native_sol_account_balance"
            if quote_pre <= 0 and quote_post <= 0:
                continue
            candidates.append(
                {
                    "pool_owner": owner,
                    "quote_mint": candidate_quote_mint,
                    "pool_token_reserve_pre": token_pre,
                    "pool_token_reserve_post": token_post,
                    "pool_quote_reserve_pre": quote_pre,
                    "pool_quote_reserve_post": quote_post,
                    "pool_quote_reserve_source": quote_reserve_source,
                    "rank_quote_reserve": max(quote_pre, quote_post),
                }
            )
    candidates.sort(key=lambda item: item["rank_quote_reserve"], reverse=True)
    return candidates


def token_supply_from_context(context: dict[str, Any]) -> float | None:
    return first_positive(
        context.get("token_supply"),
        context.get("total_supply"),
        context.get("circulating_supply"),
        context.get("supply"),
    )


def remove_values(values: list[Any], remove: set[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip() and str(value) not in remove})


def normalize_historical_market_snapshots(rows: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        token_mint = str(row.get("mint") or row.get("token_mint") or "").strip()
        timestamp = safe_float(row.get("timestamp") or row.get("snapshot_time") or row.get("created_at"), None)
        market_cap = positive_float(row.get("market_cap") or row.get("market_cap_usd"))
        if not token_mint or timestamp is None or market_cap is None:
            continue
        normalized = {
            "token_mint": token_mint,
            "timestamp": float(timestamp),
            "market_cap": market_cap,
            "price": positive_float(row.get("price") or row.get("price_usd")),
            "source": str(row.get("source") or "local_token_snapshot"),
        }
        indexed.setdefault(token_mint, []).append(normalized)
    for snapshots in indexed.values():
        snapshots.sort(key=lambda item: item["timestamp"])
    return indexed


def nearest_prior_market_snapshot(
    snapshots_by_mint: dict[str, list[dict[str, Any]]],
    token_mint: str,
    timestamp: float | None,
    *,
    max_market_snapshot_age_seconds: float,
) -> dict[str, Any] | None:
    if timestamp is None or not token_mint:
        return None
    best: dict[str, Any] | None = None
    for snapshot in snapshots_by_mint.get(token_mint) or []:
        snapshot_time = safe_float(snapshot.get("timestamp"), None)
        if snapshot_time is None or snapshot_time > timestamp:
            continue
        age_seconds = timestamp - snapshot_time
        if age_seconds < 0 or age_seconds > max_market_snapshot_age_seconds:
            continue
        best = snapshot
    if best is None:
        return None
    return {
        **best,
        "age_seconds": round(timestamp - float(best["timestamp"]), 6),
    }


def recover_record(
    record: dict[str, Any],
    raw_by_signature: dict[str, dict[str, Any]],
    *,
    quote_price_series: list[dict[str, float]] | None = None,
    max_quote_age_seconds: float = 7200.0,
    historical_market_snapshots_by_mint: dict[str, list[dict[str, Any]]] | None = None,
    max_market_snapshot_age_seconds: float = 7200.0,
) -> dict[str, Any]:
    wallet = str(record.get("wallet") or "").strip()
    token_mint = str(record.get("token_mint") or "").strip()
    signature = str(record.get("transaction_signature") or "").strip()
    context = dict(as_dict(record.get("decision_time_context")))
    context.setdefault("decision_time_safe", True)
    quote_mint = str(context.get("quote_mint") or "").strip() or None
    timestamp = safe_float(record.get("timestamp") or context.get("timestamp"), None)
    raw = raw_by_signature.get(signature)
    block_reasons = {str(reason) for reason in record.get("block_reasons") or [] if str(reason).strip()}
    missing_fields = {str(field) for field in record.get("missing_fields") or [] if str(field).strip()}
    recovery_notes: list[str] = []
    status = str(record.get("status") or "unknown")
    recovery_method = str(record.get("recovery_method") or "")

    if not raw:
        block_reasons.add("blocked_missing_transaction")
        status = "blocked_missing_transaction"
        recovery_method = "blocked_missing_transaction"
    else:
        candidates = pool_candidates_from_transaction(
            raw=raw,
            wallet=wallet,
            token_mint=token_mint,
            quote_mint=quote_mint,
        )
        if not candidates:
            block_reasons.add("blocked_missing_liquidity")
            block_reasons.add("blocked_missing_onchain_pool_reserves")
            status = "blocked_missing_onchain_pool_reserves"
            recovery_method = "blocked_missing_onchain_pool_reserves"
        else:
            candidate = candidates[0]
            quote_mint = candidate.get("quote_mint") or quote_mint
            quote_post = positive_float(candidate.get("pool_quote_reserve_post"))
            quote_pre = positive_float(candidate.get("pool_quote_reserve_pre"))
            quote_reserve = quote_post if quote_post is not None else quote_pre
            token_post = positive_float(candidate.get("pool_token_reserve_post"))
            token_pre = positive_float(candidate.get("pool_token_reserve_pre"))
            token_reserve = token_post if token_post is not None else token_pre
            context.update(
                {
                    "source": context.get("source") or "raw_transaction_history",
                    "quote_mint": quote_mint,
                    "pool_context_source": "raw_transaction_pool_balances",
                    "pool_owner": candidate["pool_owner"],
                    "pool_quote_mint": candidate["quote_mint"],
                    "pool_quote_reserve_pre": candidate["pool_quote_reserve_pre"],
                    "pool_quote_reserve_post": candidate["pool_quote_reserve_post"],
                    "pool_quote_reserve_source": candidate.get("pool_quote_reserve_source"),
                    "pool_token_reserve_pre": candidate["pool_token_reserve_pre"],
                    "pool_token_reserve_post": candidate["pool_token_reserve_post"],
                    "decision_time_safe": True,
                }
            )
            if positive_float(context.get("price_in_quote")) is None and token_reserve is not None and quote_reserve is not None:
                context["price_in_quote"] = quote_reserve / token_reserve
                context["price_quote_per_token"] = quote_reserve / token_reserve
                context["price_in_quote_source"] = "onchain_pool_reserve_ratio"

            quote_usd_info = quote_usd_price_from_context(
                context,
                timestamp=timestamp,
                quote_mint_override=quote_mint,
                quote_price_series=quote_price_series,
                max_quote_age_seconds=max_quote_age_seconds,
            )
            quote_usd = positive_float(as_dict(quote_usd_info).get("price_usd"))
            if quote_usd is None:
                block_reasons.add("blocked_missing_quote_usd_price")
                status = "blocked_missing_quote_usd_price"
                recovery_method = "blocked_missing_quote_usd_price"
                quote_usd_info = None
            else:
                quote_usd_info = as_dict(quote_usd_info)
                context["quote_usd_price"] = quote_usd
                context["quote_usd_price_source"] = quote_usd_info.get("source")
                if quote_usd_info.get("timestamp") is not None:
                    context["quote_usd_price_time"] = quote_usd_info.get("timestamp")
                if quote_usd_info.get("age_seconds") is not None:
                    context["quote_usd_price_age_seconds"] = quote_usd_info.get("age_seconds")

                if quote_reserve is None:
                    block_reasons.add("blocked_missing_liquidity")
                    block_reasons.add("blocked_missing_onchain_pool_reserves")
                    status = "blocked_missing_onchain_pool_reserves"
                    recovery_method = "blocked_missing_onchain_pool_reserves"
                    quote_usd = None

            if quote_usd is not None:
                price_recovered_from_pool = False
                if positive_float(context.get("price")) is None and positive_float(context.get("price_in_quote")) is not None:
                    context["price"] = positive_float(context.get("price_in_quote")) * quote_usd
                    context["price_usd"] = context["price"]
                    context["price_source"] = "onchain_pool_reserve_ratio"
                    price_recovered_from_pool = True

                liquidity_usd = quote_reserve * quote_usd * 2
                pre_liquidity_usd = quote_pre * quote_usd * 2 if quote_pre is not None else None
                context.update(
                    {
                        "source": context.get("source") or "raw_transaction_history",
                        "liquidity": liquidity_usd,
                        "liquidity_usd": liquidity_usd,
                        "liquidity_source": "onchain_pool_balance_reconstruction",
                        "pool_quote_usd_price": quote_usd,
                        "pre_liquidity_usd": pre_liquidity_usd,
                        "post_liquidity_usd": liquidity_usd,
                        "decision_time_safe": True,
                    }
                )
                if positive_float(context.get("price")) is not None:
                    block_reasons.discard("blocked_missing_price")
                    missing_fields.discard("entry_price")
                block_reasons.discard("blocked_missing_liquidity")
                block_reasons.discard("blocked_missing_onchain_pool_reserves")
                missing_fields.discard("liquidity")
                status = "onchain_price_liquidity_recovered" if price_recovered_from_pool else "onchain_liquidity_recovered"
                recovery_method = "onchain_pool_balance_reconstruction"

                token_supply = token_supply_from_context(context)
                price = positive_float(context.get("price"))
                if token_supply is not None and price is not None:
                    context.update(
                        {
                            "token_supply": token_supply,
                            "market_cap": price * token_supply,
                            "market_cap_source": "decision_time_token_supply",
                        }
                    )
                    block_reasons.discard("blocked_missing_market_cap")
                    block_reasons.discard("blocked_missing_supply")
                    missing_fields.discard("market_cap")
                    status = "onchain_liquidity_market_cap_recovered"
                else:
                    prior_snapshot = nearest_prior_market_snapshot(
                        historical_market_snapshots_by_mint or {},
                        token_mint,
                        timestamp,
                        max_market_snapshot_age_seconds=max_market_snapshot_age_seconds,
                    )
                    if prior_snapshot:
                        context.update(
                            {
                                "market_cap": prior_snapshot["market_cap"],
                                "market_cap_source": "prior_decision_time_market_snapshot",
                                "market_cap_snapshot_source": prior_snapshot.get("source"),
                                "market_cap_snapshot_time": prior_snapshot["timestamp"],
                                "market_cap_snapshot_age_seconds": prior_snapshot["age_seconds"],
                            }
                        )
                        if prior_snapshot.get("price") is not None:
                            context["market_cap_snapshot_price"] = prior_snapshot.get("price")
                        block_reasons.discard("blocked_missing_market_cap")
                        block_reasons.discard("blocked_missing_supply")
                        missing_fields.discard("market_cap")
                        status = "onchain_liquidity_market_cap_recovered"
                        recovery_notes.append("market_cap_recovered_from_prior_local_market_snapshot")
                    else:
                        block_reasons.add("blocked_missing_market_cap")
                        block_reasons.add("blocked_missing_supply")
                        missing_fields.add("market_cap")
                        recovery_notes.append("market_cap_requires_decision_time_supply_or_prior_market_snapshot")

    score_ready_candidate = (
        positive_float(context.get("price")) is not None
        and positive_float(context.get("liquidity")) is not None
        and positive_float(context.get("market_cap")) is not None
        and context.get("decision_time_safe") is True
    )

    return {
        "onchain_recovery_version": RECOVERY_VERSION,
        "wallet": wallet,
        "token_mint": token_mint,
        "timestamp": timestamp,
        "transaction_signature": signature,
        "source_status": record.get("status"),
        "status": status,
        "recovery_method": recovery_method,
        "score_ready_candidate": score_ready_candidate,
        "decision_time_context": context,
        "later_outcome_reference": as_dict(record.get("later_outcome") or record.get("later_outcome_reference")),
        "missing_fields": sorted(missing_fields),
        "block_reasons": sorted(block_reasons),
        "recovery_notes": recovery_notes,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    block_reasons = Counter(reason for record in records for reason in record.get("block_reasons") or [])
    missing_fields = Counter(field for record in records for field in record.get("missing_fields") or [])
    liquidity_recovered = sum(1 for record in records if positive_float(as_dict(record.get("decision_time_context")).get("liquidity")) is not None)
    price_recovered = sum(1 for record in records if positive_float(as_dict(record.get("decision_time_context")).get("price")) is not None)
    market_cap_recovered = sum(1 for record in records if positive_float(as_dict(record.get("decision_time_context")).get("market_cap")) is not None)
    score_ready = sum(1 for record in records if record.get("score_ready_candidate"))
    return {
        "records_scanned": len(records),
        "price_recovered_records": price_recovered,
        "liquidity_recovered_records": liquidity_recovered,
        "market_cap_recovered_records": market_cap_recovered,
        "score_ready_candidate_records": score_ready,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
        "missing_context_categories": dict(sorted(missing_fields.items())),
        "wallets_affected": len({record.get("wallet") for record in records if record.get("wallet")}),
        "tokens_affected": len({record.get("token_mint") for record in records if record.get("token_mint")}),
        "next_required_actions": next_required_actions(records),
    }


def next_required_actions(records: list[dict[str, Any]]) -> list[str]:
    missing = Counter(field for record in records for field in record.get("missing_fields") or [])
    blocks = Counter(reason for record in records for reason in record.get("block_reasons") or [])
    actions: list[str] = []
    if blocks.get("blocked_missing_quote_usd_price"):
        actions.append("Recover historical quote USD prices before reconstructing pool liquidity for quote-priced rows.")
    if blocks.get("blocked_missing_onchain_pool_reserves") or blocks.get("blocked_missing_liquidity"):
        actions.append("Parse richer transaction or pool-account evidence for rows without target/quote pool reserves.")
    if missing.get("market_cap") or blocks.get("blocked_missing_supply"):
        actions.append("Add decision-time token supply evidence before treating market cap as recovered.")
    if not actions:
        actions.append("All rows have on-chain price, liquidity, and market-cap candidates ready for trusted-gate review.")
    return actions


def build_onchain_market_context_recovery_report(
    *,
    backfill_records: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    quote_price_series: list[dict[str, Any]] | None = None,
    max_quote_age_seconds: float = 7200.0,
    historical_market_snapshots: list[dict[str, Any]] | None = None,
    max_market_snapshot_age_seconds: float = 7200.0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    raw_by_signature = index_raw_transactions(raw_transactions)
    normalized_quote_prices = normalize_quote_price_series(quote_price_series or [])
    historical_market_snapshots_by_mint = normalize_historical_market_snapshots(historical_market_snapshots)
    market_snapshot_points = sum(len(rows) for rows in historical_market_snapshots_by_mint.values())
    records = [
        recover_record(
            record,
            raw_by_signature,
            quote_price_series=normalized_quote_prices,
            max_quote_age_seconds=max_quote_age_seconds,
            historical_market_snapshots_by_mint=historical_market_snapshots_by_mint,
            max_market_snapshot_age_seconds=max_market_snapshot_age_seconds,
        )
        for record in backfill_records or []
        if isinstance(record, dict)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "onchain_recovery_version": RECOVERY_VERSION,
        "quote_price_points": len(normalized_quote_prices),
        "max_quote_age_seconds": max_quote_age_seconds,
        "historical_market_snapshot_points": market_snapshot_points,
        "max_market_snapshot_age_seconds": max_market_snapshot_age_seconds,
        "provider_policy": {
            "primary_source": "home_built_onchain_reconstruction",
            "provider_snapshots_allowed_for": ["temporary_validation", "fallback_gap_analysis"],
            "provider_snapshots_not_allowed_for": ["unlabeled_score_trust", "fabricated_historical_context"],
        },
        "summary": build_summary(records),
        "records": records,
    }


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
