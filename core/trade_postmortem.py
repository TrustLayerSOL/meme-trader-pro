class TradePostmortem:
    def analyze(self, paper_state):
        trades = []
        paper_state = paper_state or {}
        for section in ["open_trades", "closed_trades"]:
            for trade in paper_state.get(section, []) or []:
                if isinstance(trade, dict):
                    trades.append(self.trade_row(trade))

        winners = [row for row in trades if row["pnl"] > 0]
        losers = [row for row in trades if row["pnl"] <= 0]

        return {
            "rows": trades,
            "winner_lessons": self.winner_lessons(winners),
            "loser_lessons": self.loser_lessons(losers),
            "recommendations": self.recommendations(trades),
        }

    def trade_row(self, trade):
        entry = self.safe_float(trade.get("entry_price"))
        quoted = self.safe_float(trade.get("quoted_entry_price"), entry)
        high = self.safe_float(trade.get("highest_price_seen"), entry)
        close = self.safe_float(trade.get("close_price"), self.safe_float(trade.get("current_price")))
        size = self.safe_float(trade.get("size_usd"), self.safe_float(trade.get("entry_value")))
        liquidity = self.safe_float(trade.get("liquidity_usd"), self.safe_float(trade.get("entry_liquidity_usd")))
        pnl = self.safe_float(trade.get("total_pnl"), self.safe_float(trade.get("pnl")))
        pnl_pct = self.safe_float(trade.get("total_pnl_pct"), self.safe_float(trade.get("pnl_pct")))
        sells = trade.get("sells", []) if isinstance(trade.get("sells"), list) else []

        return {
            "mint": trade.get("token_mint") or trade.get("mint"),
            "status": trade.get("status"),
            "entry_reason": trade.get("entry_reason") or trade.get("reason"),
            "close_reason": trade.get("close_reason"),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "wallets": len(trade.get("wallets", []) or []),
            "size_usd": round(size, 2),
            "liquidity_usd": round(liquidity, 2),
            "size_to_liquidity_pct": round((size / liquidity) * 100, 2) if liquidity > 0 else 0,
            "entry_markup_pct": round(((entry / quoted) - 1) * 100, 2) if quoted > 0 else 0,
            "high_multiple": round(high / entry, 2) if entry > 0 else 0,
            "close_multiple": round(close / entry, 2) if entry > 0 else 0,
            "hold_seconds": self.hold_seconds(trade),
            "partial_sells": len([sell for sell in sells if "take_profit" in str(sell.get("reason", ""))]),
            "sell_reasons": ", ".join(str(sell.get("reason")) for sell in sells),
        }

    def winner_lessons(self, winners):
        if not winners:
            return ["No winning closed trades yet."]

        best = max(winners, key=lambda row: row["pnl"])
        return [
            f"Best trade reached {best['high_multiple']}x from entry.",
            f"It banked {best['partial_sells']} partial profit sell(s) before the remaining position stopped out.",
            f"The useful pattern was not the final exit; it was fast profit-taking during a very brief pump window.",
        ]

    def loser_lessons(self, losers):
        closed_losers = [row for row in losers if row["status"] == "closed"]
        if not closed_losers:
            return ["No closed losing trades yet."]

        no_partial = len([row for row in closed_losers if row["partial_sells"] == 0])
        avg_entry_markup = sum(row["entry_markup_pct"] for row in closed_losers) / len(closed_losers)
        return [
            f"{no_partial}/{len(closed_losers)} losing closed trades had no partial profit sell before stop.",
            f"Average simulated entry markup was {avg_entry_markup:.2f}%, so entries need a real edge just to overcome execution friction.",
            "Most losers were cluster signals that fell straight into hard stop-loss territory.",
        ]

    def recommendations(self, rows):
        recommendations = []
        closed = [row for row in rows if row["status"] == "closed"]
        losses = [row for row in closed if row["pnl"] <= 0]
        wins = [row for row in closed if row["pnl"] > 0]

        if losses:
            recommendations.append("Raise or disable cluster entries until replay proves positive expectancy.")
            recommendations.append("Add an early failure exit: if no new high within 10-20 seconds and price is red, cut before -30%.")
            recommendations.append("Require stronger post-entry momentum confirmation before sizing up to $60.")

        if wins:
            recommendations.append("Keep fast partial take-profit logic; it is the only reason the best trade survived the reversal.")
            recommendations.append("After a 2.5x partial, consider moving the remaining stop to breakeven or a tighter trailing stop.")

        recommendations.append("Treat low-liquidity tokens as hostile: execution markup plus sell slippage is dominating outcomes.")
        return recommendations

    def hold_seconds(self, trade):
        entry = self.safe_float(trade.get("entry_time"), None)
        close = self.safe_float(trade.get("close_time"), None)
        if entry is None or close is None:
            return None
        return round(max(0, close - entry), 2)

    def safe_float(self, value, default=0.0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default
