def safe_float(value, default=0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def parse_owner_token_balance(response):
    values = ((response or {}).get("result") or {}).get("value") or []
    total_raw = 0
    total_ui = 0.0
    decimals = None
    account_count = 0

    for row in values:
        account = row.get("account") if isinstance(row, dict) else {}
        data = account.get("data") if isinstance(account, dict) else {}
        parsed = data.get("parsed") if isinstance(data, dict) else {}
        info = parsed.get("info") if isinstance(parsed, dict) else {}
        token_amount = info.get("tokenAmount") if isinstance(info, dict) else {}
        if not isinstance(token_amount, dict):
            continue

        raw_amount = int(safe_float(token_amount.get("amount")))
        ui_amount = safe_float(token_amount.get("uiAmount"))
        row_decimals = token_amount.get("decimals")
        if row_decimals is not None and decimals is None:
            decimals = int(safe_float(row_decimals))

        total_raw += raw_amount
        total_ui += ui_amount
        account_count += 1

    return {
        "account_count": account_count,
        "amount_raw": total_raw,
        "ui_amount": total_ui,
        "decimals": decimals,
        "has_balance": total_raw > 0,
    }
