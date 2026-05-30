from __future__ import annotations

from typing import Any

from wallets.wallet_evidence_models import build_evidence_record


QUOTE_MINTS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}
NATIVE_SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def token_amount(balance: dict[str, Any]) -> float:
    ui = as_dict(balance.get("uiTokenAmount"))
    value = ui.get("uiAmount")
    if value is None:
        value = ui.get("uiAmountString")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def balance_map(balances: Any, wallet: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in balances or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("owner") or "") != wallet:
            continue
        mint = str(row.get("mint") or "").strip()
        if not mint:
            continue
        out[mint] = token_amount(row)
    return out


def quote_delta_map(pre: dict[str, float], post: dict[str, float]) -> dict[str, float]:
    return {
        mint: post.get(mint, 0.0) - pre.get(mint, 0.0)
        for mint in sorted((set(pre) | set(post)) & QUOTE_MINTS)
        if abs(post.get(mint, 0.0) - pre.get(mint, 0.0)) >= 1e-12
    }


def primary_quote_delta(pre: dict[str, float], post: dict[str, float]) -> tuple[str | None, float | None]:
    deltas = quote_delta_map(pre, post)
    if not deltas:
        return None, None
    mint, delta = max(deltas.items(), key=lambda item: abs(item[1]))
    return mint, delta


def transaction_signature(tx: dict[str, Any], fallback: str = "") -> str:
    signatures = as_dict(tx.get("transaction")).get("signatures")
    if isinstance(signatures, list) and signatures:
        return str(signatures[0] or fallback)
    return fallback


def account_key_pubkey(account_key: Any) -> str:
    if isinstance(account_key, str):
        return account_key
    if isinstance(account_key, dict):
        return str(account_key.get("pubkey") or "")
    return ""


def transaction_account_keys(tx: dict[str, Any]) -> list[Any]:
    message = as_dict(as_dict(tx.get("transaction")).get("message"))
    keys = message.get("accountKeys")
    return keys if isinstance(keys, list) else []


def native_sol_delta(tx: dict[str, Any], wallet: str) -> tuple[str | None, float | None, dict[str, Any]]:
    keys = transaction_account_keys(tx)
    wallet_index = next((index for index, key in enumerate(keys) if account_key_pubkey(key) == wallet), None)
    if wallet_index is None:
        return None, None, {}

    meta = as_dict(tx.get("meta"))
    pre_balances = meta.get("preBalances")
    post_balances = meta.get("postBalances")
    if not isinstance(pre_balances, list) or not isinstance(post_balances, list):
        return None, None, {}
    if wallet_index >= len(pre_balances) or wallet_index >= len(post_balances):
        return None, None, {}

    try:
        raw_lamports_delta = int(post_balances[wallet_index]) - int(pre_balances[wallet_index])
    except (TypeError, ValueError):
        return None, None, {}
    if raw_lamports_delta == 0:
        return None, None, {}

    fee_lamports = 0
    try:
        fee_lamports = int(meta.get("fee") or 0)
    except (TypeError, ValueError):
        fee_lamports = 0

    fee_payer = account_key_pubkey(keys[0]) if keys else ""
    adjusted_lamports_delta = raw_lamports_delta
    if fee_lamports and wallet == fee_payer:
        adjusted_lamports_delta += fee_lamports
    if adjusted_lamports_delta == 0:
        return None, None, {}

    return (
        NATIVE_SOL_MINT,
        adjusted_lamports_delta / LAMPORTS_PER_SOL,
        {
            "native_sol_raw_lamports_delta": raw_lamports_delta,
            "native_sol_adjusted_lamports_delta": adjusted_lamports_delta,
            "native_sol_fee_lamports": fee_lamports if wallet == fee_payer else 0,
        },
    )


def parse_wallet_token_deltas(
    tx: dict[str, Any],
    *,
    wallet: str,
    signature: str = "",
    outcome_by_mint: dict[str, dict[str, Any]] | None = None,
    risk_flags: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(tx, dict) or not wallet:
        return []
    meta = as_dict(tx.get("meta"))
    pre = balance_map(meta.get("preTokenBalances"), wallet)
    post = balance_map(meta.get("postTokenBalances"), wallet)
    quote_mint, quote_delta = primary_quote_delta(pre, post)
    quote_source = "same_transaction_token_balance_delta"
    quote_metadata: dict[str, Any] = {}
    if not quote_mint or quote_delta in (None, 0):
        quote_mint, quote_delta, quote_metadata = native_sol_delta(tx, wallet)
        quote_source = "native_sol_balance_delta" if quote_mint and quote_delta not in (None, 0) else quote_source
    sig = transaction_signature(tx, signature)
    rows = []
    for mint in sorted(set(pre) | set(post)):
        if mint in QUOTE_MINTS:
            continue
        delta = post.get(mint, 0.0) - pre.get(mint, 0.0)
        if abs(delta) < 1e-12:
            continue
        row = build_evidence_record(
            wallet=wallet,
            token_mint=mint,
            observed_action="buy" if delta > 0 else "sell",
            timestamp=tx.get("blockTime"),
            transaction_signature=sig,
            token_amount_delta=delta,
            later_token_outcome=(outcome_by_mint or {}).get(mint),
            risk_flags=risk_flags or [],
        )
        if quote_mint and quote_delta not in (None, 0):
            execution_price = abs(float(quote_delta) / float(delta))
            row["quote_mint"] = quote_mint
            row["quote_amount_delta"] = quote_delta
            row["execution_price_quote"] = execution_price
            if quote_metadata:
                row.update(quote_metadata)
            row["estimated_entry_context"] = {
                **as_dict(row.get("estimated_entry_context")),
                "quote_mint": quote_mint,
                "quote_amount_delta": quote_delta,
                "execution_price_quote": execution_price,
                "execution_price_source": quote_source,
                **quote_metadata,
            }
        rows.append(row)
    return rows
