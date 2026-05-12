import asyncio
import time

from infra.market_checker import MarketChecker
from core.runtime_status import update_component


def safe_float(value, default=0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def pct_change(current, baseline):
    current = safe_float(current)
    baseline = safe_float(baseline)
    if baseline <= 0:
        return 0
    return round(((current - baseline) / baseline) * 100, 2)


def position_mint(position):
    if not isinstance(position, dict):
        return ""
    return str(position.get("mint") or position.get("token_mint") or "").strip()


def evaluate_fast_position(position, market_info):
    position = position if isinstance(position, dict) else {}
    market_info = market_info if isinstance(market_info, dict) else {}
    mint = position_mint(position)
    current_price = safe_float(market_info.get("price"), safe_float(position.get("current_price"), safe_float(position.get("entry_price"))))
    current_liquidity = safe_float(
        market_info.get("liquidity"),
        safe_float(position.get("current_liquidity_usd"), safe_float(position.get("liquidity_usd"))),
    )
    entry_price = safe_float(position.get("entry_price"), current_price)
    entry_liquidity = safe_float(
        position.get("entry_liquidity_usd"),
        safe_float(position.get("liquidity_usd"), current_liquidity),
    )
    peak_price = max(safe_float(position.get("highest_price_seen"), entry_price), current_price)
    peak_liquidity = max(safe_float(position.get("peak_liquidity"), entry_liquidity), current_liquidity)

    price_from_entry_pct = pct_change(current_price, entry_price)
    price_from_peak_pct = pct_change(current_price, peak_price)
    liquidity_from_entry_pct = pct_change(current_liquidity, entry_liquidity)
    liquidity_from_peak_pct = pct_change(current_liquidity, peak_liquidity)
    reasons = []
    risk_level = "SAFE"

    if current_price <= 0 or current_liquidity <= 0:
        risk_level = "WARNING"
        reasons.append("missing fast market quote")
    if price_from_entry_pct <= -30 or price_from_peak_pct <= -40 or liquidity_from_peak_pct <= -50:
        risk_level = "DANGER"
        reasons.append("fast monitor danger drawdown")
    elif (
        price_from_entry_pct <= -15
        or price_from_peak_pct <= -25
        or liquidity_from_entry_pct <= -30
        or liquidity_from_peak_pct <= -35
    ) and risk_level == "SAFE":
        risk_level = "WARNING"
        reasons.append("fast monitor warning drawdown")

    return {
        "mint": mint,
        "checked_at": time.time(),
        "monitor_mode": "cheap_market_only_fast_position_monitor",
        "deep_checks_ran": False,
        "risk_level": risk_level,
        "reasons": reasons or ["fast quote/liquidity check clean"],
        "price": current_price,
        "liquidity": current_liquidity,
        "market_cap": market_info.get("market_cap") or market_info.get("marketCap") or market_info.get("fdv"),
        "market_source": market_info.get("source"),
        "price_from_entry_pct": price_from_entry_pct,
        "price_from_peak_pct": price_from_peak_pct,
        "liquidity_from_entry_pct": liquidity_from_entry_pct,
        "liquidity_from_peak_pct": liquidity_from_peak_pct,
    }


async def run_fast_monitor_cycle(paper_trader=None, market_checker=None, timeout=3):
    if paper_trader is None:
        from paper_trader import PaperTrader
        paper_trader = PaperTrader()
    market_checker = market_checker or MarketChecker()
    open_trades = [
        trade for trade in paper_trader.state.get("open_trades", [])
        if isinstance(trade, dict) and position_mint(trade)
    ]
    rows = []
    errors = []

    for trade in open_trades:
        mint = position_mint(trade)
        try:
            market_info = await asyncio.wait_for(
                market_checker.get_token_info(mint),
                timeout=max(0.5, float(timeout or 3)),
            )
        except Exception as exc:
            row = {
                "mint": mint,
                "checked_at": time.time(),
                "monitor_mode": "cheap_market_only_fast_position_monitor",
                "deep_checks_ran": False,
                "risk_level": "WARNING",
                "reasons": [f"fast market check failed: {str(exc)[:120]}"],
            }
            rows.append(row)
            errors.append({"mint": mint, "message": str(exc)[:160]})
            continue

        row = evaluate_fast_position(trade, market_info)
        rows.append(row)
        price = safe_float(row.get("price"))
        if price > 0:
            paper_trader.update_price(
                mint,
                price,
                liquidity_usd=safe_float(row.get("liquidity"), safe_float(trade.get("current_liquidity_usd"), 10000)),
                market_info=market_info if isinstance(market_info, dict) else {},
            )

    summary = {
        "generated_at": time.time(),
        "mode": "FAST_POSITION_MONITOR",
        "live_execution_locked": True,
        "checked_count": len(rows),
        "open_trade_count": len(open_trades),
        "warning_count": len([row for row in rows if row.get("risk_level") == "WARNING"]),
        "danger_count": len([row for row in rows if row.get("risk_level") == "DANGER"]),
        "errors": errors,
        "rows": rows,
    }
    update_component(
        "open_position_monitor",
        status="complete",
        checked_count=summary["checked_count"],
        warning_count=summary["warning_count"],
        danger_count=summary["danger_count"],
        last_success_at=summary["generated_at"] if not errors else None,
        last_error=errors[0]["message"] if errors else None,
    )
    return summary


def run_once():
    return asyncio.run(run_fast_monitor_cycle())


async def run_open_position_monitor(paper_trader=None, market_checker=None, interval=1.0, timeout=3):
    while True:
        try:
            await run_fast_monitor_cycle(
                paper_trader=paper_trader,
                market_checker=market_checker,
                timeout=timeout,
            )
        except Exception as exc:
            update_component(
                "open_position_monitor",
                status="error",
                last_error=str(exc)[:240],
            )
        await asyncio.sleep(max(0.5, float(interval or 1.0)))


if __name__ == "__main__":
    import json
    print(json.dumps(run_once(), indent=2, sort_keys=True))
