WATCHDOG_OWNED_FIELDS = {
    "status",
    "risk_level",
    "reason",
    "last_update",
    "last_checked_at",
    "baseline_price",
    "baseline_liquidity",
    "peak_price",
    "peak_liquidity",
    "current_price",
    "current_liquidity",
    "market_cap",
    "volume",
    "url",
    "market_info",
    "alert_level",
    "alert_reasons",
    "price_from_entry_pct",
    "price_from_peak_pct",
    "liquidity_from_entry_pct",
    "liquidity_from_peak_pct",
    "holder_concentration",
    "holder_concentration_risk",
    "holder_concentration_reasons",
    "holder_concentration_metrics",
    "token_mechanics",
    "token_standard",
    "token_extensions",
    "token_mechanics_risk",
    "token_mechanics_reasons",
    "token_inspection",
    "prepared_exit",
    "wallet_balance_status",
    "wallet_balance_accounts",
    "wallet_balance_reason",
    "watchdog_run_id",
    "watchdog_started_at_epoch",
    "watchdog_checked_at_epoch",
    "watchdog_checked_at",
}


def watchlist_key(item):
    if not isinstance(item, dict) or not item.get("token_mint"):
        return None
    return item.get("token_mint"), item.get("wallet") or ""


def safe_epoch(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def watchdog_update_is_newer(current, checked):
    current_epoch = safe_epoch(current.get("watchdog_checked_at_epoch"))
    checked_epoch = safe_epoch(checked.get("watchdog_checked_at_epoch"))
    if checked_epoch is None:
        return current_epoch is None
    if current_epoch is None:
        return True
    return checked_epoch >= current_epoch


def patch_watchdog_fields(current, checked):
    patched = dict(current)
    for field in WATCHDOG_OWNED_FIELDS:
        if field in checked:
            patched[field] = checked[field]
    return patched


def mark_stale_skip(item, checked):
    patched = dict(item)
    patched["stale_watchdog_updates_skipped"] = int(patched.get("stale_watchdog_updates_skipped", 0) or 0) + 1
    patched["last_stale_watchdog_run_id"] = checked.get("watchdog_run_id")
    patched["last_stale_watchdog_checked_at_epoch"] = checked.get("watchdog_checked_at_epoch")
    return patched


def merge_watchlist_updates(current, checked_items):
    checked_by_key = {
        watchlist_key(item): item
        for item in checked_items
        if watchlist_key(item) is not None
    }
    merged = []
    seen = set()

    for item in current if isinstance(current, list) else []:
        if not isinstance(item, dict):
            continue
        key = watchlist_key(item)
        checked = checked_by_key.get(key)
        if checked:
            if watchdog_update_is_newer(item, checked):
                merged.append(patch_watchdog_fields(item, checked))
            else:
                merged.append(mark_stale_skip(item, checked))
            seen.add(key)
        else:
            merged.append(item)

    for key, checked in checked_by_key.items():
        if key not in seen:
            merged.append(checked)

    return merged
