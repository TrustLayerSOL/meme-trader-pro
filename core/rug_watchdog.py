import asyncio
import os
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

from core.env_loader import load_env
from infra.market_checker import MarketChecker
from core.holder_concentration import HolderConcentrationAnalyzer
from core.json_store import locked_update_json, read_json
from core.protection_exit import ProtectionExitPlanner
from core.redaction import redact_secrets
from core.rpc_provider import post_json_with_provider_failover
from core.runtime_status import increment_component, update_component
from core.storage import EventStore
from core.token_balance import parse_owner_token_balance
from core.token_inspector import TokenInspector
from core.watchdog_balance import apply_wallet_balance_result
from core.watchdog_state import merge_watchlist_updates
from execution.jupiter_quote import JupiterQuoteEngine


WATCHLIST_FILE = Path("data/manual_watchlist.json")
MARKET_CHECK_TIMEOUT_SECONDS = 8
MINT_INSPECTION_TIMEOUT_SECONDS = 8
QUOTE_CHECK_TIMEOUT_SECONDS = 8
HOLDER_CHECK_TIMEOUT_SECONDS = 8
WALLET_BALANCE_TIMEOUT_SECONDS = 8
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
    data = read_json(WATCHLIST_FILE, [])
    return data if isinstance(data, list) else []


def save_watchlist(data):
    stale_skips = {"count": 0}

    def stale_skip_total(rows):
        return sum(
            int(item.get("stale_watchdog_updates_skipped", 0) or 0)
            for item in rows
            if isinstance(item, dict)
        )

    def updater(current):
        if not current and not WATCHLIST_FILE.exists():
            return data
        merged = merge_watchlist_updates(current, data)
        stale_skips["count"] = max(0, stale_skip_total(merged) - stale_skip_total(current if isinstance(current, list) else []))
        return merged

    locked_update_json(WATCHLIST_FILE, [], updater)
    if stale_skips["count"]:
        increment_component(
            "watchdog",
            "stale_updates_skipped",
            amount=stale_skips["count"],
            status="stale_update_skipped",
        )
    try:
        store = EventStore()
        for item in load_watchlist():
            if isinstance(item, dict):
                store.upsert_watchlist_item(item)
    except Exception as exc:
        print("Failed to mirror watchlist to SQLite:", exc)


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
        "decimals": market_info.get("decimals"),
        "url": market_info.get("url"),
        "last_update": utc_now(),
    }


def build_token_snapshot(token, context="watchdog_check"):
    prepared_exit = token.get("prepared_exit") or {}
    holder_metrics = token.get("holder_concentration_metrics") or {}
    return {
        "time": time.time(),
        "timestamp": utc_now(),
        "mint": token.get("token_mint"),
        "source": "rug_watchdog",
        "context": context,
        "status": token.get("status"),
        "risk_label": token.get("risk_level"),
        "alert_level": token.get("alert_level"),
        "reason": token.get("reason"),
        "price": token.get("current_price"),
        "liquidity": token.get("current_liquidity"),
        "baseline_price": token.get("baseline_price"),
        "baseline_liquidity": token.get("baseline_liquidity"),
        "peak_price": token.get("peak_price"),
        "peak_liquidity": token.get("peak_liquidity"),
        "price_from_entry_pct": token.get("price_from_entry_pct"),
        "price_from_peak_pct": token.get("price_from_peak_pct"),
        "liquidity_from_entry_pct": token.get("liquidity_from_entry_pct"),
        "liquidity_from_peak_pct": token.get("liquidity_from_peak_pct"),
        "market_source": token.get("market_source"),
        "token_standard": token.get("token_standard"),
        "token_mechanics_risk": token.get("token_mechanics_risk"),
        "token_mechanics_reasons": token.get("token_mechanics_reasons", []),
        "holder_concentration_risk": token.get("holder_concentration_risk"),
        "holder_count": holder_metrics.get("holder_count"),
        "holder_top_1_pct": holder_metrics.get("top_1_pct"),
        "holder_top_5_pct": holder_metrics.get("top_5_pct"),
        "holder_top_10_pct": holder_metrics.get("top_10_pct"),
        "prepared_exit_action": prepared_exit.get("action"),
        "prepared_exit_sell_pct": prepared_exit.get("suggested_sell_pct"),
        "prepared_exit_quote_status": prepared_exit.get("quote_status"),
        "prepared_exit_quote_reason": prepared_exit.get("quote_reason"),
        "token_amount_raw": token.get("token_amount_raw"),
        "token_amount": token.get("token_amount"),
        "token_amount_source": token.get("token_amount_source"),
        "wallet_balance_status": token.get("wallet_balance_status"),
        "live_action_allowed": prepared_exit.get("live_action_allowed", False),
    }


def stamp_watchdog_result(token):
    checked_at = time.time()
    token.update({
        "watchdog_checked_at_epoch": checked_at,
        "watchdog_checked_at": utc_now(),
        "last_checked_at": utc_now(),
    })
    return token


async def fetch_mint_account_info(checker, mint):
    await checker.init_session()
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

    data, provider = await post_json_with_provider_failover(checker.session, payload)
    if provider:
        update_component("providers", active_provider=provider, last_method="getAccountInfo", status="ok")
    return data


async def fetch_owner_token_balance(checker, wallet, mint):
    if not wallet:
        return None

    await checker.init_session()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet,
            {
                "mint": mint,
            },
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
            },
        ],
    }

    data, provider = await post_json_with_provider_failover(checker.session, payload)
    if provider:
        update_component("providers", active_provider=provider, last_method="getTokenAccountsByOwner", status="ok")
    return parse_owner_token_balance(data) if data else None


async def fetch_largest_token_accounts(checker, mint):
    await checker.init_session()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [
            mint,
            {
                "commitment": "confirmed",
            },
        ],
    }

    data, provider = await post_json_with_provider_failover(checker.session, payload)
    if provider:
        update_component("providers", active_provider=provider, last_method="getTokenLargestAccounts", status="ok")
    if not data:
        return None
    return (data.get("result") or {}).get("value") or []


async def attach_exit_quote_feasibility(quote_engine, prepared_exit, token):
    if not prepared_exit.get("quote_required"):
        return prepared_exit

    amount_raw = int(prepared_exit.get("token_amount_raw") or 0)
    sell_pct = safe_float(prepared_exit.get("suggested_sell_pct"))
    if amount_raw <= 0:
        prepared_exit.update({
            "quote_status": "amount_missing",
            "quote_reason": "manual_position_token_amount_missing",
            "quote_checked_at": utc_now(),
            "live_action_allowed": False,
        })
        return prepared_exit

    if sell_pct <= 0:
        prepared_exit.update({
            "quote_status": "not_required",
            "quote_reason": "no_sell_suggested",
            "quote_checked_at": utc_now(),
            "live_action_allowed": False,
        })
        return prepared_exit

    mint = prepared_exit.get("token_mint") or token.get("token_mint")
    sell_amount_raw = max(1, int(amount_raw * min(sell_pct, 100) / 100))
    slippage_bps = int(safe_float(token.get("protection_exit_slippage_bps"), 2000))
    max_price_impact_pct = safe_float(token.get("protection_exit_max_price_impact_pct"), 15)

    try:
        quote = await asyncio.wait_for(
            quote_engine.get_sell_quote(
                input_mint=mint,
                token_amount_raw=sell_amount_raw,
                slippage_bps=slippage_bps,
            ),
            timeout=QUOTE_CHECK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        prepared_exit.update({
            "quote_status": "timeout",
            "quote_pass": False,
            "quote_reason": "quote_check_timeout",
            "quote_checked_at": utc_now(),
            "quote_input_amount_raw": sell_amount_raw,
            "quote_slippage_bps": slippage_bps,
            "quote_max_price_impact_pct": max_price_impact_pct,
            "live_action_allowed": False,
        })
        update_component(
            "watchdog",
            status="quote_timeout",
            last_mint=mint,
        )
        return prepared_exit

    analysis = quote_engine.analyze_quote(
        quote,
        max_price_impact_pct=max_price_impact_pct,
    )

    quote_status = "feasible" if analysis.get("pass") else "blocked"
    if quote and not quote.get("ok"):
        reason = str(quote.get("reason") or "")
        if reason == "missing_jupiter_api_key":
            quote_status = "missing_api_key"
        elif "429" in reason or "cooldown" in reason:
            quote_status = "rate_limited"
        else:
            quote_status = "failed"

    prepared_exit.update({
        "quote_status": quote_status,
        "quote_pass": bool(analysis.get("pass")),
        "quote_reason": analysis.get("reason"),
        "quote_checked_at": utc_now(),
        "quote_input_amount_raw": sell_amount_raw,
        "quote_slippage_bps": slippage_bps,
        "quote_max_price_impact_pct": max_price_impact_pct,
        "quote_price_impact_pct": analysis.get("price_impact_pct"),
        "quote_route_count": quote.get("route_count") if quote else None,
        "quote_out_lamports": quote.get("out_amount") if quote else None,
        "live_action_allowed": False,
    })
    return prepared_exit


async def check_once():
    run_id = uuid.uuid4().hex
    run_started_at = time.time()
    checker = MarketChecker()
    inspector = TokenInspector()
    holder_analyzer = HolderConcentrationAnalyzer()
    exit_planner = ProtectionExitPlanner()
    quote_engine = JupiterQuoteEngine()
    watchlist = load_watchlist()
    update_component(
        "watchdog",
        status="checking",
        protected_tokens=len(watchlist),
        run_id=run_id,
        run_started_at=run_started_at,
    )

    try:
        for token in watchlist:
            mint = token.get("token_mint")
            if not mint:
                continue
            token.update({
                "watchdog_run_id": run_id,
                "watchdog_started_at_epoch": run_started_at,
            })

            try:
                market_info = await asyncio.wait_for(
                    checker.get_token_info(mint),
                    timeout=MARKET_CHECK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                increment_component(
                    "watchdog",
                    "market_timeouts",
                    last_mint=mint,
                    status="market_timeout",
                )
                token.update({
                    "status": "NO_DATA",
                    "risk_level": "WARNING",
                    "alert_level": "warning",
                    "reason": f"Market check timed out after {MARKET_CHECK_TIMEOUT_SECONDS}s",
                    "last_update": utc_now(),
                })
                prepared_exit = exit_planner.plan(token)
                token["prepared_exit"] = prepared_exit
                stamp_watchdog_result(token)
                try:
                    EventStore().insert_token_snapshot(build_token_snapshot(token, context="watchdog_market_timeout"))
                except Exception:
                    pass
                continue

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
                prepared_exit = exit_planner.plan(token)
                token["prepared_exit"] = prepared_exit
                stamp_watchdog_result(token)
                try:
                    EventStore().insert_token_snapshot(build_token_snapshot(token, context="watchdog_no_market_data"))
                except Exception:
                    pass
                continue

            token.update(evaluate_market(token, market_info))

            wallet = str(token.get("wallet") or "").strip()
            if wallet:
                try:
                    balance = await asyncio.wait_for(
                        fetch_owner_token_balance(checker, wallet, mint),
                        timeout=WALLET_BALANCE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    balance = None
                    increment_component(
                        "watchdog",
                        "wallet_balance_timeouts",
                        last_mint=mint,
                        status="wallet_balance_timeout",
                    )
                    token.update({
                        "wallet_balance_status": "timeout",
                        "wallet_balance_reason": f"Wallet balance lookup timed out after {WALLET_BALANCE_TIMEOUT_SECONDS}s",
                        "token_amount_updated_at": utc_now(),
                    })
                except Exception as exc:
                    error = redact_secrets(exc)
                    balance = None
                    increment_component(
                        "watchdog",
                        "wallet_balance_errors",
                        last_mint=mint,
                        status="wallet_balance_error",
                        last_error=error[:240],
                    )
                    token.update({
                        "wallet_balance_status": "error",
                        "wallet_balance_reason": error[:160],
                        "token_amount_updated_at": utc_now(),
                    })

                if balance is not None:
                    apply_wallet_balance_result(token, balance)
                    increment_component(
                        "watchdog",
                        "wallet_balance_checks",
                        last_mint=mint,
                        status="wallet_balance_checked",
                    )

            try:
                account_info = await asyncio.wait_for(
                    fetch_mint_account_info(checker, mint),
                    timeout=MINT_INSPECTION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                account_info = None
                increment_component(
                    "watchdog",
                    "mint_inspection_timeouts",
                    last_mint=mint,
                    status="mint_inspection_timeout",
                )
                token.update({
                    "token_mechanics_risk": "UNKNOWN",
                    "token_mechanics_reasons": [
                        f"Mint inspection timed out after {MINT_INSPECTION_TIMEOUT_SECONDS}s",
                    ],
                })
            except Exception as exc:
                error = redact_secrets(exc)
                account_info = None
                increment_component(
                    "watchdog",
                    "mint_inspection_errors",
                    last_mint=mint,
                    status="mint_inspection_error",
                    last_error=error[:240],
                )
                token.update({
                    "token_mechanics_risk": "UNKNOWN",
                    "token_mechanics_reasons": [
                        f"Mint inspection error: {error[:160]}",
                    ],
                })

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

            try:
                holder_rows = await asyncio.wait_for(
                    fetch_largest_token_accounts(checker, mint),
                    timeout=HOLDER_CHECK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                holder_rows = None
                increment_component(
                    "watchdog",
                    "holder_check_timeouts",
                    last_mint=mint,
                    status="holder_check_timeout",
                )
            except Exception as exc:
                error = redact_secrets(exc)
                holder_rows = None
                increment_component(
                    "watchdog",
                    "holder_check_errors",
                    last_mint=mint,
                    status="holder_check_error",
                    last_error=error[:240],
                )
                token.update({
                    "holder_concentration_risk": "UNKNOWN",
                    "holder_concentration_reasons": [
                        f"Holder concentration error: {error[:160]}",
                    ],
                })

            if holder_rows is not None:
                holder_result = holder_analyzer.analyze(holder_rows)
                token.update({
                    "holder_concentration": holder_result,
                    "holder_concentration_risk": holder_result.get("risk_label"),
                    "holder_concentration_reasons": holder_result.get("warnings", []),
                    "holder_concentration_metrics": holder_result.get("metrics", {}),
                })
                if (
                    holder_result.get("risk_label") in ["DANGER", "WARNING"]
                    and token.get("risk_level") not in ["EMERGENCY", "DANGER"]
                ):
                    token["risk_level"] = "WARNING"
                    token["status"] = "WARNING"
                    token["alert_level"] = "warning"
                    warnings = holder_result.get("warnings", [])
                    if warnings:
                        token["reason"] = token.get("reason", "") + "; Holder concentration: " + "; ".join(warnings)

            prepared_exit = exit_planner.plan(token)
            prepared_exit = await attach_exit_quote_feasibility(
                quote_engine,
                prepared_exit,
                token,
            )
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

            try:
                stamp_watchdog_result(token)
                EventStore().insert_token_snapshot(build_token_snapshot(token))
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
            run_id=run_id,
            run_completed_at=time.time(),
        )
        return watchlist

    finally:
        if checker.session:
            await checker.session.close()
        await quote_engine.close()


def run_once():
    return asyncio.run(check_once())


def watchdog_interval(default=1.0):
    try:
        return max(0.5, float(os.getenv("MEMETRADER_WATCHDOG_INTERVAL_SECONDS", default)))
    except (TypeError, ValueError):
        return default


def run_watchdog(interval=None):
    if interval is None:
        interval = watchdog_interval()
    print("Rug Watchdog started")

    while True:
        try:
            watchlist = run_once()
            for token in watchlist:
                print(
                    f"{token.get('token_mint')} -> {token.get('status')} | {token.get('reason')}"
                )
        except Exception as exc:
            print("Rug Watchdog error:", redact_secrets(exc))

        time.sleep(interval)


if __name__ == "__main__":
    run_watchdog()
