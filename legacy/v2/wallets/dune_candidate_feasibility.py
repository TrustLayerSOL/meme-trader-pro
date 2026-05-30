from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "DUNE_CANDIDATE_FEASIBILITY_REVIEW_ONLY"
VERSION = "dune_candidate_feasibility.v1"


def sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def wallet_values(candidate_wallets: list[str]) -> str:
    return ", ".join(sql_string(wallet) for wallet in candidate_wallets if str(wallet).strip())


def build_dune_sql_queries(
    *,
    candidate_wallets: list[str],
    start_date: str,
    end_date: str,
    limit: int = 500,
) -> dict[str, str]:
    wallets = wallet_values(candidate_wallets)
    safe_limit = max(1, int(limit))
    start = sql_string(start_date)
    end = sql_string(end_date)
    return {
        "candidate_transactions": f"""
SELECT
  signer AS wallet_address,
  signature AS tx_hash,
  block_time,
  success
FROM solana.transactions
WHERE block_date >= DATE {start}
  AND block_date < DATE {end}
  AND signer IN ({wallets})
ORDER BY block_time DESC
LIMIT {safe_limit}
""".strip(),
        "candidate_dex_trades": f"""
SELECT
  trader_id AS wallet_address,
  tx_id AS tx_hash,
  block_time,
  token_bought_mint_address,
  token_sold_mint_address,
  token_bought_symbol,
  token_sold_symbol,
  token_bought_amount,
  token_sold_amount,
  amount_usd,
  CASE
    WHEN token_bought_mint_address IN (
      'So11111111111111111111111111111111111111112',
      'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
      'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
    )
      AND token_sold_amount > 0 THEN amount_usd / token_sold_amount
    WHEN token_sold_mint_address IN (
      'So11111111111111111111111111111111111111112',
      'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
      'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
    )
      AND token_bought_amount > 0 THEN amount_usd / token_bought_amount
    ELSE NULL
  END AS price_usd,
  CASE
    WHEN token_bought_mint_address IN (
      'So11111111111111111111111111111111111111112',
      'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
      'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
    ) THEN token_sold_mint_address
    ELSE token_bought_mint_address
  END AS token_mint
FROM dex_solana.trades
WHERE block_date >= DATE {start}
  AND block_date < DATE {end}
  AND trader_id IN ({wallets})
ORDER BY block_time DESC
LIMIT {safe_limit}
""".strip(),
        "candidate_token_transfers": f"""
SELECT
  coalesce(from_owner, to_owner, tx_signer) AS wallet_address,
  token_mint_address AS token_mint,
  symbol,
  count(*) AS transfer_count,
  min(block_time) AS first_seen,
  max(block_time) AS last_seen,
  sum(CAST(amount_display AS DOUBLE)) AS amount_display_sum,
  sum(CAST(amount_usd AS DOUBLE)) AS amount_usd_sum
FROM tokens_solana.transfers
WHERE block_time >= TIMESTAMP {start}
  AND block_time < TIMESTAMP {end}
  AND (
    from_owner IN ({wallets})
    OR to_owner IN ({wallets})
    OR tx_signer IN ({wallets})
  )
GROUP BY 1, 2, 3
ORDER BY transfer_count DESC
LIMIT {safe_limit}
""".strip(),
        "candidate_price_coverage": f"""
WITH candidate_tokens AS (
  SELECT DISTINCT
    CASE
      WHEN token_bought_mint_address IN (
        'So11111111111111111111111111111111111111112',
        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
        'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
      ) THEN token_sold_mint_address
      ELSE token_bought_mint_address
    END AS token_mint
  FROM dex_solana.trades
  WHERE block_date >= DATE {start}
    AND block_date < DATE {end}
    AND trader_id IN ({wallets})
)
SELECT
  token_mint,
  count(p.price) AS minute_price_points,
  min(p.timestamp) AS first_price_at,
  max(p.timestamp) AS last_price_at
FROM candidate_tokens c
LEFT JOIN prices.minute p
  ON p.blockchain = 'solana'
  AND p.contract_address = from_base58(c.token_mint)
  AND p.timestamp >= TIMESTAMP {start}
  AND p.timestamp < TIMESTAMP {end}
GROUP BY 1
ORDER BY minute_price_points DESC
LIMIT {safe_limit}
""".strip(),
    }


def number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed == parsed else 0.0


def row_wallet(row: dict[str, Any]) -> str:
    return str(row.get("wallet_address") or row.get("trader_id") or row.get("signer") or "").strip()


def row_mint(row: dict[str, Any]) -> str:
    return str(
        row.get("token_mint")
        or row.get("token_mint_address")
        or row.get("token_bought_mint_address")
        or row.get("token_sold_mint_address")
        or ""
    ).strip()


def build_wallet_rows(candidate_wallets: list[str], query_results: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    tx_by_wallet: dict[str, dict[str, Any]] = {}
    for row in query_results.get("candidate_transactions", []):
        wallet = row_wallet(row)
        if not wallet:
            continue
        bucket = tx_by_wallet.setdefault(wallet, {"sampled_rows": 0, "timestamps": [], "aggregate_row": None})
        bucket["sampled_rows"] += 1
        if row.get("tx_count") is not None:
            bucket["aggregate_row"] = row
        if row.get("block_time") is not None:
            bucket["timestamps"].append(str(row.get("block_time")))
    dex_counts = Counter(row_wallet(row) for row in query_results.get("candidate_dex_trades", []) if row_wallet(row))
    transfer_counts = Counter(row_wallet(row) for row in query_results.get("candidate_token_transfers", []) if row_wallet(row))
    token_sets: dict[str, set[str]] = {wallet: set() for wallet in candidate_wallets}
    for query_name in ("candidate_dex_trades", "candidate_token_transfers"):
        for row in query_results.get(query_name, []):
            wallet = row_wallet(row)
            mint = row_mint(row)
            if wallet and mint:
                token_sets.setdefault(wallet, set()).add(mint)

    rows: list[dict[str, Any]] = []
    for wallet in candidate_wallets:
        tx = tx_by_wallet.get(wallet, {})
        aggregate = tx.get("aggregate_row") if isinstance(tx.get("aggregate_row"), dict) else {}
        timestamps = sorted(str(item) for item in tx.get("timestamps", []) if str(item).strip())
        tx_count = int(number(aggregate.get("tx_count"))) if aggregate else int(number(tx.get("sampled_rows")))
        dex_count = int(dex_counts.get(wallet, 0))
        transfer_count = int(transfer_counts.get(wallet, 0))
        rows.append(
            {
                "wallet_address": wallet,
                "transaction_history_rows": tx_count,
                "first_seen": aggregate.get("first_seen") if aggregate else (timestamps[0] if timestamps else None),
                "last_seen": aggregate.get("last_seen") if aggregate else (timestamps[-1] if timestamps else None),
                "dex_trade_rows": dex_count,
                "token_transfer_rows": transfer_count,
                "candidate_token_count": len(token_sets.get(wallet, set())),
                "dune_historical_activity_available": bool(tx or dex_count or transfer_count),
                "dune_quote_anchor_candidate_available": dex_count > 0,
                "dune_price_context_candidate_available": dex_count > 0,
                "dune_liquidity_context_candidate_available": False,
                "dune_market_cap_context_candidate_available": False,
                "proof_ready_from_dune_alone": False,
            }
        )
    return rows


def build_dune_candidate_feasibility_report(
    *,
    candidate_wallets: list[str],
    start_date: str,
    end_date: str,
    query_results: dict[str, list[dict[str, Any]]] | None = None,
    generated_at: float | None = None,
    execution_mode: str = "dry_run",
    query_errors: dict[str, str] | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    candidates = [str(wallet).strip() for wallet in candidate_wallets if str(wallet).strip()]
    query_results = query_results or {}
    query_errors = query_errors or {}
    queries = build_dune_sql_queries(
        candidate_wallets=candidates,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    wallet_rows = build_wallet_rows(candidates, query_results)
    dex_rows = query_results.get("candidate_dex_trades", [])
    price_rows = query_results.get("candidate_price_coverage", [])
    tokens_with_price = {row_mint(row) for row in price_rows if number(row.get("minute_price_points")) > 0}
    dex_token_rows_with_price = [row for row in dex_rows if row_mint(row) in tokens_with_price or number(row.get("price_usd")) > 0]

    summary = {
        "candidate_wallets": len(candidates),
        "query_count": len(queries),
        "queries_completed": len([name for name in queries if name in query_results]),
        "queries_failed": len(query_errors),
        "rows_returned_total": sum(len(rows) for rows in query_results.values()),
        "rows_returned_by_query": {name: len(rows) for name, rows in sorted(query_results.items())},
        "wallets_with_transaction_history": sum(
            1 for row in wallet_rows if row["dune_historical_activity_available"]
        ),
        "wallets_with_dex_matches": sum(1 for row in wallet_rows if row["dex_trade_rows"] > 0),
        "quote_anchor_candidate_rows": len(dex_rows),
        "price_context_candidate_rows": len(dex_token_rows_with_price),
        "liquidity_context_candidate_rows": 0,
        "market_cap_context_candidate_rows": 0,
        "proof_ready_rows": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "wallet_trust_mutations": 0,
    }
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "execution_mode": execution_mode,
        "review_only": True,
        "read_only": True,
        "candidate_wallets_only": True,
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "promotion_allowed": False,
        "date_window": {"start_date": start_date, "end_date": end_date},
        "summary": summary,
        "wallets": wallet_rows,
        "query_errors": query_errors,
        "dune_capability_assessment": {
            "historical_wallet_activity": summary["wallets_with_transaction_history"] > 0,
            "same_transaction_quote_anchor_candidates": summary["quote_anchor_candidate_rows"] > 0,
            "token_price_context_candidates": summary["price_context_candidate_rows"] > 0,
            "decision_time_liquidity": False,
            "decision_time_market_cap": False,
            "safe_for_walk_forward_backfill": summary["wallets_with_transaction_history"] > 0,
            "safe_as_trust_source_by_itself": False,
        },
        "recommended_next_actions": [
            "Use Dune as a candidate-only historical activity and DEX-trade backfill source.",
            "Join Dune rows to local forward evidence by wallet, token mint, signature, and time window.",
            "Keep liquidity and market-cap blockers open until pool/vault reserve and supply evidence is recovered.",
            "Do not mutate wallet trust, wallet lists, recommendations, or execution settings from this report.",
        ],
        "limitations": [
            "dune_does_not_fully_solve_liquidity_or_market_cap",
            "dune_refresh_is_not_a_live_execution_path",
            "dex_rows_are_quote_anchor_candidates_not_trust_proof",
            "meme_token_price_coverage_must_be_verified_per_token",
        ],
    }
