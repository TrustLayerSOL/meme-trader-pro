import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PERFORMANCE_FILE = ROOT / "data" / "wallet_performance.json"
PAPER_TRADES_FILE = ROOT / "data" / "paper_trades.json"


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def ensure_wallet(data, wallet):
    wallets = data.setdefault("wallets", {})
    if wallet not in wallets:
        wallets[wallet] = {
            "signals": 0,
            "paper_entries": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0,
            "avg_pnl": 0,
            "best_pnl": 0,
            "worst_pnl": 0,
            "score": 50,
            "last_seen": None,
        }
    return wallets[wallet]


def reset_trade_memory(record):
    record["paper_entries"] = 0
    record["wins"] = 0
    record["losses"] = 0
    record["total_pnl"] = 0
    record["avg_pnl"] = 0
    record["best_pnl"] = 0
    record["worst_pnl"] = 0
    record["score"] = 50


def apply_trade(record, pnl):
    pnl = float(pnl or 0)

    record["paper_entries"] += 1
    record["total_pnl"] += pnl

    if pnl > 0:
        record["wins"] += 1
    else:
        record["losses"] += 1

    entries = max(1, record["paper_entries"])
    record["avg_pnl"] = record["total_pnl"] / entries
    record["best_pnl"] = max(record["best_pnl"], pnl)
    record["worst_pnl"] = min(record["worst_pnl"], pnl)

    win_rate = record["wins"] / entries
    avg_pnl = record["avg_pnl"]

    confidence = min(1, entries / 5)
    raw_edge = 0
    raw_edge += (win_rate - 0.5) * 40

    if avg_pnl > 0:
        raw_edge += min(25, avg_pnl)
    else:
        raw_edge += max(-30, avg_pnl)

    score = 50 + (raw_edge * confidence)

    record["score"] = max(0, min(100, round(score, 2)))


def main():
    perf = load_json(PERFORMANCE_FILE, {"wallets": {}, "signals": []})
    trades = load_json(PAPER_TRADES_FILE, {"closed_trades": []})

    for record in perf.setdefault("wallets", {}).values():
        reset_trade_memory(record)

    touched = set()

    for trade in trades.get("closed_trades", []):
        pnl = trade.get("total_pnl", trade.get("pnl", 0))
        for wallet in trade.get("wallets", []):
            record = ensure_wallet(perf, wallet)
            apply_trade(record, pnl)
            touched.add(wallet)

    save_json(PERFORMANCE_FILE, perf)
    print(f"Backfilled paper trade results for {len(touched)} wallets")


if __name__ == "__main__":
    main()
