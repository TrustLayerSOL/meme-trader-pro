from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=None):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build_manual_amount_patch(token_amount=None, token_decimals=None, token_amount_raw=None, test_amount=False):
    amount = safe_float(token_amount)
    decimals = safe_int(token_decimals)
    raw_amount = safe_int(token_amount_raw)

    if raw_amount is not None and raw_amount <= 0:
        raise ValueError("Raw token amount must be greater than 0.")
    if amount is not None and amount <= 0:
        raise ValueError("Token amount must be greater than 0.")
    if decimals is not None and not 0 <= decimals <= 18:
        raise ValueError("Token decimals must be between 0 and 18.")
    if raw_amount is None and amount is None:
        raise ValueError("Provide token amount or raw token amount.")
    if raw_amount is None and amount is not None and decimals is None:
        raise ValueError("Decimals are required when using decimal token amount.")

    source = "operator_test_amount" if test_amount else "operator_manual"
    patch = {
        "token_amount_source": source,
        "token_amount_updated_at": utc_now(),
        "wallet_balance_status": "test_amount" if test_amount else "manual_amount",
    }
    if test_amount:
        patch["test_amount"] = True
        patch["amount_safety_note"] = "Test amount only. Does not represent a wallet balance or owned position."

    if amount is not None:
        patch["token_amount"] = amount
    if decimals is not None:
        patch["token_decimals"] = decimals
        patch["decimals"] = decimals
    if raw_amount is not None:
        patch["token_amount_raw"] = raw_amount
    elif amount is not None and decimals is not None:
        patch["token_amount_raw"] = max(1, int(amount * (10 ** decimals)))

    return patch


def watchlist_item_key(item):
    if not isinstance(item, dict):
        return None
    mint = item.get("token_mint")
    if not mint:
        return None
    return mint, item.get("wallet") or ""


def apply_manual_amount_to_watchlist(rows, mint, wallet="", token_amount=None, token_decimals=None, token_amount_raw=None, test_amount=False):
    if not mint:
        raise ValueError("Token mint is required.")
    patch = build_manual_amount_patch(
        token_amount=token_amount,
        token_decimals=token_decimals,
        token_amount_raw=token_amount_raw,
        test_amount=test_amount,
    )
    target_key = (mint, wallet or "")
    updated = False
    next_rows = []

    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        if watchlist_item_key(item) == target_key:
            next_item = dict(item)
            next_item.update(patch)
            prepared_exit = next_item.get("prepared_exit")
            if isinstance(prepared_exit, dict):
                prepared_exit = dict(prepared_exit)
                prepared_exit["quote_status"] = "pending" if patch.get("token_amount_raw") else prepared_exit.get("quote_status")
                prepared_exit["quote_reason"] = "ready_for_route_check" if patch.get("token_amount_raw") else prepared_exit.get("quote_reason")
                prepared_exit["token_amount_raw"] = patch.get("token_amount_raw", prepared_exit.get("token_amount_raw"))
                prepared_exit["token_amount_source"] = patch.get("token_amount_source")
                prepared_exit["token_amount_reason"] = "operator_test_amount_present" if test_amount else "operator_manual_amount_present"
                if test_amount:
                    prepared_exit["test_amount"] = True
                    prepared_exit["amount_safety_note"] = patch["amount_safety_note"]
                next_item["prepared_exit"] = prepared_exit
            next_item["last_update"] = utc_now()
            next_rows.append(next_item)
            updated = True
        else:
            next_rows.append(item)

    if not updated:
        raise ValueError("Protected token not found for the provided mint/wallet.")

    return next_rows
