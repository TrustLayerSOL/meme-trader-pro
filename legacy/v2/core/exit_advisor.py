import time


class ExitAdvisor:
    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default

    def advise(self, trade):
        entry_price = self.safe_float(trade.get("entry_price"))
        current_price = self.safe_float(trade.get("current_price"), entry_price)
        highest_price = self.safe_float(trade.get("highest_price_seen"), current_price)
        pnl_pct = self.safe_float(trade.get("total_pnl_pct"), self.safe_float(trade.get("pnl_pct")))
        remaining_pct = self.safe_float(trade.get("remaining_pct"), 100)
        entry_liquidity = self.safe_float(
            trade.get("entry_liquidity_usd"),
            self.safe_float(trade.get("liquidity_usd")),
        )
        current_liquidity = self.safe_float(
            trade.get("current_liquidity_usd"),
            self.safe_float(trade.get("liquidity_usd")),
        )
        entry_time = self.safe_float(trade.get("entry_time"))

        price_from_high_pct = 0
        if highest_price > 0:
            price_from_high_pct = ((current_price - highest_price) / highest_price) * 100

        liquidity_change_pct = 0
        if entry_liquidity > 0:
            liquidity_change_pct = ((current_liquidity - entry_liquidity) / entry_liquidity) * 100

        age_seconds = max(0, time.time() - entry_time) if entry_time > 0 else None

        action = "HOLD"
        severity = "OK"
        reasons = []

        if pnl_pct <= -30:
            action = "EXIT"
            severity = "DANGER"
            reasons.append("Hard stop loss hit")
        elif pnl_pct <= -18:
            action = "WATCH"
            severity = "WARNING"
            reasons.append("Trade is approaching stop-loss territory")

        if price_from_high_pct <= -45:
            action = "EXIT"
            severity = "DANGER"
            reasons.append("Major drawdown from high")
        elif price_from_high_pct <= -25 and action != "EXIT":
            action = "REDUCE"
            severity = "WARNING"
            reasons.append("Sharp pullback from high")

        if liquidity_change_pct <= -35:
            action = "EXIT"
            severity = "DANGER"
            reasons.append("Liquidity has drained materially")
        elif liquidity_change_pct <= -18 and action not in ["EXIT", "REDUCE"]:
            action = "WATCH"
            severity = "WARNING"
            reasons.append("Liquidity is weakening")

        if pnl_pct >= 25 and remaining_pct > 65 and action not in ["EXIT", "REDUCE"]:
            action = "REDUCE"
            severity = "PROFIT"
            reasons.append("Profit target zone reached")
        elif pnl_pct >= 10 and action == "HOLD":
            action = "WATCH"
            severity = "PROFIT"
            reasons.append("Green trade, protect gains")

        if age_seconds is not None and age_seconds > 3600 and pnl_pct < 5 and action == "HOLD":
            action = "WATCH"
            severity = "STALE"
            reasons.append("Position is aging without momentum")

        if not reasons:
            reasons.append("No exit trigger active")

        return {
            "action": action,
            "severity": severity,
            "reasons": reasons,
            "pnl_pct": round(pnl_pct, 2),
            "price_from_high_pct": round(price_from_high_pct, 2),
            "liquidity_change_pct": round(liquidity_change_pct, 2),
            "age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
        }
