class WalletLabeler:
    def label(self, record):
        record = record or {}
        labels = []

        signals = int(record.get("signals", 0) or 0)
        entries = int(record.get("paper_entries", 0) or 0)
        wins = int(record.get("wins", 0) or 0)
        losses = int(record.get("losses", 0) or 0)
        score = self.safe_float(record.get("score"), 50)
        avg_pnl = self.safe_float(record.get("avg_pnl"))
        worst_pnl = self.safe_float(record.get("worst_pnl"))
        best_pnl = self.safe_float(record.get("best_pnl"))

        if signals >= 100:
            labels.append("high-signal wallet")
        elif signals >= 25:
            labels.append("active signal wallet")

        if entries == 0:
            labels.append("unproven")
        elif entries < 5:
            labels.append("low-sample")
        else:
            labels.append("sampled")

        if entries > 0:
            win_rate = wins / max(1, entries)
            if score >= 58 and avg_pnl > 0:
                labels.append("paper-profitable")
            if score <= 40 or avg_pnl < -8:
                labels.append("fade/caution")
            if win_rate >= 0.6 and entries >= 3:
                labels.append("consistent winner")
            if win_rate <= 0.25 and entries >= 3:
                labels.append("consistent loser")

        if worst_pnl <= -30:
            labels.append("large-drawdown source")

        if best_pnl >= 30 and entries <= 2:
            labels.append("one-hit wonder")

        if not labels:
            labels.append("neutral")

        return labels

    def primary_label(self, record):
        labels = self.label(record)
        priority = [
            "paper-profitable",
            "consistent winner",
            "fade/caution",
            "consistent loser",
            "large-drawdown source",
            "high-signal wallet",
            "active signal wallet",
            "one-hit wonder",
            "low-sample",
            "unproven",
            "neutral",
        ]

        for item in priority:
            if item in labels:
                return item

        return labels[0]

    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default
