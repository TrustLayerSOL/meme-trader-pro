import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.json_store import locked_update_json, read_json


ACTION_INTENTS_FILE = Path("data/position_action_intents.json")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def normalize_mint(value):
    return str(value or "").strip()


def position_mint(position):
    if not isinstance(position, dict):
        return ""
    return normalize_mint(position.get("mint") or position.get("token_mint"))


def build_position_rows(paper_state, watchlist):
    rows = []

    for trade in paper_state.get("open_trades", []) if isinstance(paper_state, dict) else []:
        if not isinstance(trade, dict):
            continue
        mint = position_mint(trade)
        if not mint:
            continue
        rows.append({
            "source": "paper_trade",
            "mint": mint,
            "label": trade.get("symbol") or trade.get("name") or mint[:8],
            "status": trade.get("status", "open"),
            "entry_price": safe_float(trade.get("entry_price")),
            "current_price": safe_float(trade.get("current_price"), safe_float(trade.get("entry_price"))),
            "entry_market_cap": trade.get("entry_market_cap"),
            "current_market_cap": trade.get("current_market_cap") or trade.get("market_cap"),
            "liquidity": trade.get("current_liquidity_usd") or trade.get("liquidity_usd"),
            "size_usd": trade.get("size_usd"),
            "remaining_pct": trade.get("remaining_pct"),
            "total_pnl": trade.get("total_pnl"),
            "total_pnl_pct": trade.get("total_pnl_pct"),
            "risk_level": trade.get("risk_label") or trade.get("risk_level"),
            "raw": trade,
        })

    watched = {row["mint"] for row in rows}
    for item in watchlist if isinstance(watchlist, list) else []:
        if not isinstance(item, dict):
            continue
        mint = position_mint(item)
        if not mint or mint in watched:
            continue
        holder_metrics = item.get("holder_concentration_metrics") or {}
        rows.append({
            "source": "manual_watchlist",
            "mint": mint,
            "label": item.get("symbol") or item.get("name") or mint[:8],
            "status": item.get("status", "WATCHING"),
            "current_price": safe_float(item.get("current_price")),
            "current_market_cap": item.get("market_cap"),
            "liquidity": item.get("current_liquidity"),
            "risk_level": item.get("risk_level"),
            "alert_level": item.get("alert_level"),
            "holder_count": holder_metrics.get("holder_count") or item.get("holder_count"),
            "raw": item,
        })
    return rows


def build_candles(snapshots, interval_seconds=5, value_key="price", carry_forward_open=False, max_candles=None):
    grouped = defaultdict(list)
    interval = max(1, int(interval_seconds or 5))
    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue
        ts = safe_float(snapshot.get("time") or snapshot.get("timestamp"))
        value = safe_float(snapshot.get(value_key))
        if value <= 0 and value_key != "market_cap":
            value = safe_float(snapshot.get("market_cap"))
        if ts <= 0 or value <= 0:
            continue
        bucket = int(ts // interval) * interval
        grouped[bucket].append((ts, value))

    candles = []
    previous_close = None
    for bucket in sorted(grouped):
        points = sorted(grouped[bucket], key=lambda item: item[0])
        values = [point[1] for point in points]
        open_value = previous_close if carry_forward_open and previous_close is not None and len(values) == 1 else values[0]
        close_value = values[-1]
        candles.append({
            "time": bucket,
            "time_iso": datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat(),
            "open": open_value,
            "high": max([open_value] + values),
            "low": min([open_value] + values),
            "close": close_value,
            "volume": len(values),
            "color": "green" if close_value >= open_value else "red",
            "synthetic": bool(carry_forward_open and previous_close is not None and len(values) == 1),
        })
        previous_close = close_value
    if max_candles is None:
        return candles
    return candles[-max(1, int(max_candles)):]


def build_simulated_action_intent(mint, action_type, source, amount=None, reason="operator_request"):
    return {
        "id": f"{normalize_mint(mint)}:{action_type}:{int(time.time() * 1000)}",
        "time": time.time(),
        "created_at": utc_now(),
        "mint": normalize_mint(mint),
        "action_type": action_type,
        "source": source,
        "amount": amount or {},
        "reason": reason,
        "execution_mode": "SIMULATION_ONLY",
        "live_action_allowed": False,
        "status": "prepared",
        "safety_note": "Prepared action only. No live buy or sell was executed.",
    }


def record_simulated_action_intent(intent, path=ACTION_INTENTS_FILE):
    def updater(data):
        if not isinstance(data, dict):
            data = {"intents": []}
        intents = data.get("intents", [])
        if not isinstance(intents, list):
            intents = []
        intents.insert(0, intent)
        data["intents"] = intents[:500]
        data["last_updated"] = time.time()
        return data

    return locked_update_json(path, {"intents": []}, updater)


def load_action_intents(path=ACTION_INTENTS_FILE):
    data = read_json(path, {"intents": []})
    return data if isinstance(data, dict) else {"intents": []}
