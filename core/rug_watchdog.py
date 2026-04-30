import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from core.env_loader import load_env
from infra.market_checker import MarketChecker
from core.protection_exit import ProtectionExitPlanner
from core.runtime_status import increment_component, update_component
from core.storage import EventStore
from core.token_inspector import TokenInspector


WATCHLIST_FILE = Path("data/manual_watchlist.json")
load_env()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def load_watchlist():
    try:
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_watchlist(data):
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        store = EventStore()
        for item in data:
            if isinstance(item, dict):
                store.upsert_watchlist_item(item)
    except Exception:
        pass


def pct_change(current, baseline):
    current = safe_float(current)
    baseline = safe_float(baseline)
    if baseline <= 0:
        return 0
    return ((current - baseline) / baseline) * 100


def evaluate_market(token, market_info):
    current_price = safe_float(market_info.get("price"))
    current_liquidity = safe_float(market_info.get("liquidity"))

    baseline_price = safe_float(token.get("baseline_price"))
    baseline_liquidity = safe_float(token.get("baseline_liquidity"))
    peak_price = max(safe_float(token.get("peak_price")), current_price)
    peak_liquidity = max(safe_float(token.get("peak_liquidity")), current_liquidity)

    if baseline_price <= 0 and current_price > 0:
        baseline_price = current_price

    if baseline_liquidity <= 0 and current_liquidity > 0:
        baseline_liquidity = current_liquidity

    price_from_entry_pct = pct_change(current_price, baseline_price)
    price_from_peak_pct = pct_change(current_price, peak_price)
    liquidity_from_entry_pct = pct_change(current_liquidity, baseline_liquidity)
    liquidity_from_peak_pct = pct_change(current_liquidity, peak_liquidity)

    status = "SAFE"
    risk = "SAFE"
    reasons = []

    if current_price <= 0:
        status = "NO_DATA"
        risk = "WARNING"
        reasons.append("No current price")

    if current_liquidity <= 0:
        status = "NO_DATA"
        risk = "WARNING"
        reasons.append("No current liquidity")

    if current_liquidity > 0 and current_liquidity < 3000:
        risk = "DANGER"
        status = "DANGER"
        reasons.append(f"Liquidity critically thin: ${current_liquidity:,.0f}")

    if liquidity_from_peak_pct <= -45:
        risk = "EMERGENCY"
        status = "EMERGENCY"
        reasons.append(f"Liquidity down {abs(liquidity_from_peak_pct):.1f}% from peak")
    elif liquidity_from_peak_pct <= -25 and risk not in ["EMERGENCY"]:
        risk = "DANGER"
        status = "DANGER"
        reasons.append(f"Liquidity down {abs(liquidity_from_peak_pct):.1f}% from peak")

    if price_from_peak_pct <= -55:
        risk = "EMERGENCY"
        status = "EMERGENCY"
        reasons.append(f"Price down {abs(price_from_peak_pct):.1f}% from peak")
    elif price_from_peak_pct <= -30 and risk not in ["EMERGENCY"]:
        risk = "DANGER"
        status = "DANGER"
        reasons.append(f"Price down {abs(price_from_peak_pct):.1f}% from peak")
    elif price_from_peak_pct <= -18 and risk == "SAFE":
        risk = "WARNING"
        status = "WARNING"
        reasons.append(f"Price down {abs(price_from_peak_pct):.1f}% from peak")

    if status == "EMERGENCY":
        alert_level = "emergency"
    elif status == "DANGER":
        alert_level = "danger"
    elif status in ["WARNING", "NO_DATA"]:
        alert_level = "warning"
    else:
        alert_level = "info"

    if not reasons:
        reasons.append("No abnormal price/liquidity drain detected")

    return {
        "status": status,
        "risk_level": risk,
        "alert_level": alert_level,
        "reason": "; ".join(reasons),
        "current_price": current_price,
        "current_liquidity": current_liquidity,
        "baseline_price": baseline_price,
        "baseline_liquidity": baseline_liquidity,
        "peak_price": peak_price,
        "peak_liquidity": peak_liquidity,
        "price_from_entry_pct": round(price_from_entry_pct, 2),
        "price_from_peak_pct": round(price_from_peak_pct, 2),
        "liquidity_from_entry_pct": round(liquidity_from_entry_pct, 2),
        "liquidity_from_peak_pct": round(liquidity_from_peak_pct, 2),
        "market_source": market_info.get("source"),
        "name": market_info.get("name"),
        "symbol": market_info.get("symbol"),
        "url": market_info.get("url"),
        "last_update": utc_now(),
    }


async def fetch_mint_account_info(checker, mint):
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        return None

    await checker.init_session()
    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            mint,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
            },
        ],
    }

    async with checker.session.post(url, json=payload) as resp:
        if resp.status != 200:
            return None
        return await resp.json()


async def check_once():
    checker = MarketChecker()
    inspector = TokenInspector()
    exit_planner = ProtectionExitPlanner()
    watchlist = load_watchlist()
    update_component(
        "watchdog",
        status="checking",
        protected_tokens=len(watchlist),
    )

    try:
        for token in watchlist:
            mint = token.get("token_mint")
            if not mint:
                continue

            market_info = await checker.get_token_info(mint)

            if not market_info:
                increment_component(
                    "watchdog",
                    "no_data_checks",
                    last_mint=mint,
                )
                token.update({
                    "status": "NO_DATA",
                    "risk_level": "WARNING",
                    "alert_level": "warning",
                    "reason": "No market data from Jupiter or Dexscreener",
                    "last_update": utc_now(),
                })
                continue

            token.update(evaluate_market(token, market_info))

            account_info = await fetch_mint_account_info(checker, mint)
            if account_info:
                inspection = inspector.analyze_account_info(mint, account_info)
                token.update({
                    "token_standard": inspection.get("token_standard"),
                    "token_extensions": inspection.get("extensions", []),
                    "token_mechanics_risk": inspection.get("risk_label"),
                    "token_mechanics_reasons": inspection.get("reasons", []),
                    "token_inspection": inspection,
                })
                if inspection.get("hard_block"):
                    token.update({
                        "status": "EMERGENCY",
                        "risk_level": "EMERGENCY",
                        "alert_level": "emergency",
                        "reason": token.get("reason", "") + "; " + "; ".join(inspection.get("reasons", [])),
                    })

            prepared_exit = exit_planner.plan(token)
            token["prepared_exit"] = prepared_exit

            if prepared_exit.get("suggested_sell_pct", 0) > 0:
                try:
                    EventStore().insert_event({
                        "time": time.time(),
                        "type": "protection_exit_intent",
                        "mint": mint,
                        "wallet": token.get("wallet"),
                        "status": token.get("status"),
                        "risk_level": token.get("risk_level"),
                        "alert_level": token.get("alert_level"),
                        "prepared_exit": prepared_exit,
                    })
                except Exception:
                    pass

            increment_component(
                "watchdog",
                "successful_checks",
                last_mint=mint,
                last_risk_level=token.get("risk_level"),
            )

        save_watchlist(watchlist)
        update_component(
            "watchdog",
            status="complete",
            protected_tokens=len(watchlist),
        )
        return watchlist

    finally:
        if checker.session:
            await checker.session.close()


def run_once():
    return asyncio.run(check_once())


def run_watchdog(interval=5):
    print("Rug Watchdog started")

    while True:
        try:
            watchlist = run_once()
            for token in watchlist:
                print(
                    f"{token.get('token_mint')} -> {token.get('status')} | {token.get('reason')}"
                )
        except Exception as exc:
            print("Rug Watchdog error:", exc)

        time.sleep(interval)


if __name__ == "__main__":
    run_watchdog()
