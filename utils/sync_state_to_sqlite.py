import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.storage import EventStore


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    live = load_json(ROOT / "live_state.json", {"events": [], "alerts": []})
    trades = load_json(ROOT / "data" / "paper_trades.json", {})
    watchlist = load_json(ROOT / "data" / "manual_watchlist.json", [])

    store = EventStore(ROOT / "data" / "memetrader.db")

    for event in live.get("events", []):
        store.insert_event(event)

    for alert in live.get("alerts", []):
        store.insert_alert(alert)

    for trade in trades.get("open_trades", []):
        store.upsert_trade(trade)

    for trade in trades.get("closed_trades", []):
        store.upsert_trade(trade)

    for trade in trades.get("failed_trades", []):
        store.upsert_trade(trade)

    for item in watchlist:
        store.upsert_watchlist_item(item)

    print(store.counts())


if __name__ == "__main__":
    main()
