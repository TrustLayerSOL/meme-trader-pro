import time


SECONDS_PER_DAY = 86400


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def listify(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def trade_time(trade):
    return safe_float(
        trade.get("close_time")
        or trade.get("exit_time")
        or trade.get("time")
        or trade.get("entry_time"),
        0,
    )


def trade_pnl(trade):
    for key in ("pnl_pct", "total_pnl_pct", "pnl", "total_pnl"):
        if key in trade:
            return safe_float(trade.get(key), 0)
    return 0.0


def hold_seconds(trade):
    entry = safe_float(trade.get("entry_time"), 0)
    close = safe_float(trade.get("close_time") or trade.get("exit_time") or trade.get("time"), 0)
    if not entry or not close or close < entry:
        return 0.0
    return close - entry


def empty_window():
    return {
        "entries": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "avg_pnl": 0,
        "total_pnl": 0,
        "median_hold_seconds": 0,
    }


def percentile_middle(values):
    values = sorted(values)
    if not values:
        return 0
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def summarize_trades(trades):
    if not trades:
        return empty_window()
    pnls = [trade_pnl(trade) for trade in trades]
    wins = len([pnl for pnl in pnls if pnl > 0])
    losses = len(pnls) - wins
    total = sum(pnls)
    return {
        "entries": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades), 4),
        "avg_pnl": round(total / len(trades), 4),
        "total_pnl": round(total, 4),
        "median_hold_seconds": round(percentile_middle([hold_seconds(trade) for trade in trades]), 2),
    }


def reason_for_trade(trade):
    for key in ("exit_reason", "close_reason", "failure_reason", "reason", "entry_reason"):
        value = trade.get(key)
        if value not in (None, ""):
            return str(value)
    return "unrecorded"


def summarize_postmortem_trade(trade):
    return {
        "mint": trade.get("mint") or trade.get("token_mint") or trade.get("tokenMint") or "",
        "symbol": trade.get("symbol") or trade.get("name") or "",
        "status": trade.get("status") or trade.get("_bucket") or "paper",
        "source": trade.get("_bucket") or "",
        "pnl_pct": trade_pnl(trade),
        "pnl": safe_float(trade.get("total_pnl") if "total_pnl" in trade else trade.get("pnl"), 0),
        "reason": reason_for_trade(trade),
        "hold_seconds": round(hold_seconds(trade), 2),
        "time": trade_time(trade),
    }


def count_by_reason(trades):
    counts = {}
    for trade in trades:
        reason = reason_for_trade(trade)
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def build_wallet_postmortem(wallet_trades):
    closed = [trade for trade in wallet_trades if trade.get("_bucket") == "closed_trades"]
    failed = [trade for trade in wallet_trades if trade.get("_bucket") == "failed_trades"]
    terminal = closed + failed
    closed_by_pnl = sorted(closed, key=trade_pnl, reverse=True)
    holds = [hold_seconds(trade) for trade in closed if hold_seconds(trade) > 0]

    return {
        "closed_trades": len(closed),
        "failed_trades": len(failed),
        "best_trade": summarize_postmortem_trade(closed_by_pnl[0]) if closed_by_pnl else None,
        "worst_trade": summarize_postmortem_trade(closed_by_pnl[-1]) if closed_by_pnl else None,
        "exit_reasons": count_by_reason(closed),
        "failure_reasons": count_by_reason(failed),
        "avg_hold_seconds": round(sum(holds) / len(holds), 2) if holds else 0,
        "recent_outcomes": [
            summarize_postmortem_trade(trade)
            for trade in sorted(terminal, key=trade_time, reverse=True)[:5]
        ],
    }


def all_trade_rows(paper_state):
    paper_state = paper_state if isinstance(paper_state, dict) else {}
    rows = []
    for key in ("open_trades", "closed_trades", "failed_trades"):
        for trade in paper_state.get(key, []) or []:
            if isinstance(trade, dict):
                next_trade = dict(trade)
                next_trade["_bucket"] = key
                rows.append(next_trade)
    return rows


def signal_rows_by_wallet(performance):
    performance = performance if isinstance(performance, dict) else {}
    grouped = {}
    for signal in performance.get("signals", []) or []:
        if not isinstance(signal, dict):
            continue
        for wallet in listify(signal.get("wallets")):
            grouped.setdefault(str(wallet), []).append(signal)
    return grouped


def labels_for(record, rolling, signals):
    labels = []
    seven = rolling["7d"]
    thirty = rolling["30d"]
    signal_count = int(safe_float(record.get("signals"), 0))
    entries = int(safe_float(record.get("paper_entries"), 0))
    early_signals = [
        signal for signal in signals
        if safe_float(signal.get("token_age_seconds"), 999999) <= 90
    ]
    late_signals = [
        signal for signal in signals
        if safe_float(signal.get("token_age_seconds"), 0) >= 300
    ]

    if len(early_signals) >= 2:
        labels.append("early-buyer")
    if len(late_signals) >= 1 and not early_signals:
        labels.append("late-buyer")
    if seven["entries"] >= 3 and seven["avg_pnl"] > 0 and seven["win_rate"] >= 0.6:
        labels.append("paper-profitable")
    elif thirty["entries"] >= 3 and thirty["avg_pnl"] > 0 and thirty["win_rate"] >= 0.6:
        labels.append("paper-profitable")
    if thirty["entries"] >= 2 and thirty["avg_pnl"] <= -10:
        labels.append("follower-trap")
    if signal_count >= 100 and entries <= 2:
        labels.append("high-fee-churner")
    if thirty["entries"] and thirty["median_hold_seconds"] >= 1800:
        labels.append("late-exit")
    if thirty["entries"] >= 2 and thirty["median_hold_seconds"] <= 120 and thirty["avg_pnl"] < 0:
        labels.append("rug-exit-fast")
    if signal_count >= 50 and thirty["entries"] >= 2 and thirty["win_rate"] <= 0.25:
        labels.append("copy-bait")

    return sorted(dict.fromkeys(labels))


def build_wallet_behavior_report(performance=None, paper_state=None, now=None):
    now = time.time() if now is None else float(now)
    performance = performance if isinstance(performance, dict) else {}
    perf_wallets = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    trades = all_trade_rows(paper_state)
    signals_by_wallet = signal_rows_by_wallet(performance)
    wallets = set(perf_wallets) | set(signals_by_wallet)
    trades_by_wallet = {}

    for trade in trades:
        for wallet in listify(trade.get("wallets")):
            wallet = str(wallet)
            wallets.add(wallet)
            trades_by_wallet.setdefault(wallet, []).append(trade)

    wallet_rows = {}
    for wallet in sorted(wallets):
        wallet_trades = trades_by_wallet.get(wallet, [])
        rolling = {}
        for days in (7, 30):
            since = now - (days * SECONDS_PER_DAY)
            rolling[f"{days}d"] = summarize_trades([
                trade for trade in wallet_trades
                if trade_time(trade) >= since
            ])
        record = perf_wallets.get(wallet, {}) if isinstance(perf_wallets.get(wallet), dict) else {}
        wallet_rows[wallet] = {
            "wallet": wallet,
            "rolling": rolling,
            "postmortem": build_wallet_postmortem(wallet_trades),
            "labels": labels_for(record, rolling, signals_by_wallet.get(wallet, [])),
            "signal_count": int(safe_float(record.get("signals"), len(signals_by_wallet.get(wallet, [])))),
            "paper_entries": int(safe_float(record.get("paper_entries"), len(wallet_trades))),
        }

    label_counts = {}
    for row in wallet_rows.values():
        for label in row["labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "generated_at": now,
        "mode": "WALLET_BEHAVIOR_REVIEW",
        "live_execution_locked": True,
        "wallet_count": len(wallet_rows),
        "label_counts": label_counts,
        "wallets": wallet_rows,
    }
