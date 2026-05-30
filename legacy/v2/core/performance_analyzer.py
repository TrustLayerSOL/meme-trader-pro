from collections import Counter, defaultdict


class PerformanceAnalyzer:
    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default

    def trade_pnl(self, trade):
        return self.safe_float(
            trade.get("total_pnl"),
            self.safe_float(trade.get("pnl")),
        )

    def trade_size(self, trade):
        return self.safe_float(
            trade.get("size_usd"),
            self.safe_float(trade.get("entry_value")),
        )

    def reason_family(self, reason):
        reason = str(reason or "unknown")
        if reason.startswith("weighted_early_signal"):
            return "weighted_early_signal"
        if reason.startswith("cluster"):
            return "cluster"
        if reason.startswith("early_signal"):
            return "early_signal"
        return reason.split("_score_")[0] if "_score_" in reason else reason[:48]

    def max_drawdown(self, pnls):
        equity = 0
        peak = 0
        max_dd = 0

        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)

        return max_dd

    def analyze(self, paper_state):
        paper_state = paper_state or {}
        open_trades = paper_state.get("open_trades", [])
        closed_trades = paper_state.get("closed_trades", [])
        failed_trades = paper_state.get("failed_trades", [])

        closed_pnls = [self.trade_pnl(t) for t in closed_trades]
        open_pnls = [self.trade_pnl(t) for t in open_trades]

        wins = [pnl for pnl in closed_pnls if pnl > 0]
        losses = [pnl for pnl in closed_pnls if pnl <= 0]

        total_closed = len(closed_trades)
        realized_pnl = sum(closed_pnls)
        unrealized_pnl = sum(open_pnls)
        total_pnl = realized_pnl + unrealized_pnl

        win_rate = (len(wins) / total_closed) * 100 if total_closed else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss) if total_closed else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else None

        closed_by_family = defaultdict(list)
        for trade in closed_trades:
            family = self.reason_family(trade.get("entry_reason") or trade.get("reason"))
            closed_by_family[family].append(self.trade_pnl(trade))

        family_rows = []
        for family, pnls in closed_by_family.items():
            family_wins = [p for p in pnls if p > 0]
            family_rows.append({
                "signal": family,
                "trades": len(pnls),
                "win_rate": round((len(family_wins) / len(pnls)) * 100, 2) if pnls else 0,
                "total_pnl": round(sum(pnls), 2),
                "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0,
            })

        reason_counter = Counter()
        for trade in closed_trades:
            reason_counter[self.reason_family(trade.get("entry_reason") or trade.get("reason"))] += 1

        best = sorted(closed_trades, key=self.trade_pnl, reverse=True)[:5]
        worst = sorted(closed_trades, key=self.trade_pnl)[:5]

        return {
            "open_trades": len(open_trades),
            "closed_trades": total_closed,
            "failed_trades": len(failed_trades),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "max_drawdown": round(self.max_drawdown(closed_pnls), 2),
            "signal_rows": sorted(family_rows, key=lambda r: r["total_pnl"], reverse=True),
            "reason_counts": reason_counter.most_common(),
            "best_trades": best,
            "worst_trades": worst,
        }
