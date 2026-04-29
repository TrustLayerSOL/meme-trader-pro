import json
from collections import Counter
from core.performance_analyzer import PerformanceAnalyzer
from core.replay_analyzer import ReplayAnalyzer


LIVE_STATE_FILE = "live_state.json"
WALLET_PERFORMANCE_FILE = "data/wallet_performance.json"
PAPER_TRADES_FILE = "data/paper_trades.json"


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    live = load_json(LIVE_STATE_FILE, {"events": [], "alerts": [], "tokens": {}})
    perf = load_json(WALLET_PERFORMANCE_FILE, {"wallets": {}, "signals": []})
    trades = load_json(PAPER_TRADES_FILE, {"open_trades": [], "closed_trades": [], "failed_trades": []})

    events = live.get("events", [])
    alerts = live.get("alerts", [])
    signals = perf.get("signals", [])

    buys = [e for e in events if e.get("type") == "buy"]
    sells = [e for e in events if e.get("type") == "sell"]

    print("\n==============================")
    print("📊 NIGHT SESSION REVIEW")
    print("==============================")

    print("Total events:", len(events))
    print("Buys:", len(buys))
    print("Sells:", len(sells))
    print("Evaluated alerts:", len(alerts))
    print("Performance signals:", len(signals))
    print("Open trades:", len(trades.get("open_trades", [])))
    print("Closed trades:", len(trades.get("closed_trades", [])))
    print("Failed trades:", len(trades.get("failed_trades", [])))

    performance = PerformanceAnalyzer().analyze(trades)

    print("\n==============================")
    print("💰 PERFORMANCE")
    print("==============================")
    print("Realized PnL:", performance["realized_pnl"])
    print("Unrealized PnL:", performance["unrealized_pnl"])
    print("Total PnL:", performance["total_pnl"])
    print("Win rate:", performance["win_rate"])
    print("Expectancy:", performance["expectancy"])
    print("Profit factor:", performance["profit_factor"])
    print("Max drawdown:", performance["max_drawdown"])

    print("\nSignal families:")
    for row in performance["signal_rows"]:
        print(
            row["signal"],
            "| trades:", row["trades"],
            "| win_rate:", row["win_rate"],
            "| total_pnl:", row["total_pnl"],
            "| avg_pnl:", row["avg_pnl"],
        )

    replay = ReplayAnalyzer().replay(alerts, trades)

    print("\n==============================")
    print("🧪 REPLAY LAB")
    print("==============================")
    print("Alerts replayed:", replay["total_alerts"])
    print("Actions:")
    for action, count in replay["actions"].most_common():
        print(action + ":", count)
    print("Verdicts:")
    for verdict, count in replay["verdicts"].most_common():
        print(verdict + ":", count)
    print("Calibration:")
    for row in replay["calibration"]:
        print(row)

    print("\n==============================")
    print("🧠 SCORE DISTRIBUTION")
    print("==============================")

    scores = [float(a.get("total_score", 0) or 0) for a in alerts]

    if scores:
        print("Highest score:", max(scores))
        print("Average score:", round(sum(scores) / len(scores), 2))

        buckets = {
            "0-29": len([s for s in scores if s < 30]),
            "30-49": len([s for s in scores if 30 <= s < 50]),
            "50-59": len([s for s in scores if 50 <= s < 60]),
            "60-69": len([s for s in scores if 60 <= s < 70]),
            "70-79": len([s for s in scores if 70 <= s < 80]),
            "80+": len([s for s in scores if s >= 80]),
        }

        for bucket, count in buckets.items():
            print(bucket + ":", count)
    else:
        print("No alerts scored.")

    print("\n==============================")
    print("🧬 EDGE DISTRIBUTION")
    print("==============================")

    edge_scores = [float(a.get("edge_score", 0) or 0) for a in alerts]
    edge_verdicts = Counter(a.get("edge_verdict", "legacy_no_edge") for a in alerts)

    if edge_scores:
        print("Highest edge:", max(edge_scores))
        print("Average edge:", round(sum(edge_scores) / len(edge_scores), 2))

        for verdict, count in edge_verdicts.most_common():
            print(verdict + ":", count)
    else:
        print("No edge scores yet.")

    print("\n==============================")
    print("⛔ TOP SKIP REASONS")
    print("==============================")

    reason_counter = Counter()

    for alert in alerts:
        for reason in alert.get("score_reasons", []):
            reason_counter[reason] += 1

    for reason, count in reason_counter.most_common(20):
        print(count, "-", reason)

    print("\n==============================")
    print("🚪 QUOTE BLOCKS")
    print("==============================")

    buy_quote_counter = Counter(a.get("buy_quote_reason", "none") for a in alerts)
    sell_quote_counter = Counter(a.get("sell_quote_reason", "none") for a in alerts)

    print("Buy quote reasons:")
    for reason, count in buy_quote_counter.most_common():
        print(count, "-", reason)

    print("\nSell quote reasons:")
    for reason, count in sell_quote_counter.most_common():
        print(count, "-", reason)

    print("\n==============================")
    print("🔥 TOP SIGNALS")
    print("==============================")

    top = sorted(alerts, key=lambda a: float(a.get("total_score", 0) or 0), reverse=True)[:15]

    for alert in top:
        print("\nMint:", alert.get("mint"))
        print("Score:", alert.get("total_score"))
        print("Edge:", alert.get("edge_score"), alert.get("edge_verdict"))
        print("Threshold:", alert.get("score_threshold"))
        print("Type:", alert.get("type"))
        print("Wallet count:", alert.get("wallet_count"))
        print("Weighted wallet:", alert.get("weighted_wallet_score"))
        print("Risk:", alert.get("risk_label"))
        print("True age:", alert.get("true_launch_age_seconds"))
        print("Buy quote:", alert.get("buy_quote_reason"))
        print("Sell quote:", alert.get("sell_quote_reason"))
        print("Should trade:", alert.get("should_trade"))
        print("Reasons:")
        for r in alert.get("score_reasons", [])[:8]:
            print(" -", r)


if __name__ == "__main__":
    main()
