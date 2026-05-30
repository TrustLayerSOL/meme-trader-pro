from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def apply_wallet_balance_result(token, balance):
    if balance is None:
        return token

    token.update({
        "wallet_balance_status": "balance_found" if balance.get("has_balance") else "no_balance",
        "wallet_balance_accounts": balance.get("account_count"),
        "token_amount_updated_at": utc_now(),
    })

    if not balance.get("has_balance"):
        return token

    token.update({
        "token_amount_raw": balance.get("amount_raw", 0),
        "token_amount": balance.get("ui_amount", 0),
        "token_amount_source": "wallet_balance_lookup",
    })
    if balance.get("decimals") is not None:
        token["decimals"] = balance.get("decimals")
        token["token_decimals"] = balance.get("decimals")
    return token
