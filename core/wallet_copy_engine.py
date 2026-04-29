from core.wallet_labeler import WalletLabeler


class WalletCopyEngine:
    """Convert wallet performance records into copy, paper-copy, or fade guidance."""

    def __init__(self):
        self.labeler = WalletLabeler()

    def wallet_rows(self, wallet_perf, limit=50):
        wallets = wallet_perf.get("wallets", {}) if isinstance(wallet_perf, dict) else {}
        rows = []

        for wallet, record in wallets.items():
            if not isinstance(record, dict):
                continue
            rows.append(self.wallet_row(wallet, record))

        rows.sort(
            key=lambda row: (
                self.action_rank(row["recommendation"]),
                row["confidence"],
                row["score"],
                row["signals"],
            ),
            reverse=True,
        )
        return rows[:limit]

    def signal_rows(self, wallet_perf, limit=40):
        signals = wallet_perf.get("signals", []) if isinstance(wallet_perf, dict) else []
        wallets = wallet_perf.get("wallets", {}) if isinstance(wallet_perf, dict) else {}
        rows = []

        for signal in signals[:limit * 3]:
            if not isinstance(signal, dict):
                continue

            signal_wallets = [w for w in signal.get("wallets", []) if w]
            wallet_reviews = [
                self.wallet_row(wallet, wallets.get(wallet, {}))
                for wallet in signal_wallets
            ]

            copy_wallets = [w for w in wallet_reviews if w["recommendation"] in ["COPY", "PAPER_COPY"]]
            fade_wallets = [w for w in wallet_reviews if w["recommendation"] == "FADE"]

            rows.append({
                "time": signal.get("time"),
                "mint": signal.get("mint"),
                "signal_type": signal.get("signal_type"),
                "score": signal.get("score"),
                "should_trade": bool(signal.get("should_trade")),
                "wallets": len(signal_wallets),
                "copy_wallets": len(copy_wallets),
                "fade_wallets": len(fade_wallets),
                "copy_confidence": round(sum(w["confidence"] for w in copy_wallets), 2),
                "recommended_action": self.signal_action(copy_wallets, fade_wallets, signal),
                "top_wallet": self.top_wallet(wallet_reviews),
            })

            if len(rows) >= limit:
                break

        return rows

    def wallet_row(self, wallet, record):
        record = record or {}
        labels = self.labeler.label(record)
        recommendation = self.recommendation(record, labels)
        entries = self.safe_int(record.get("paper_entries"))
        signals = self.safe_int(record.get("signals"))
        score = self.safe_float(record.get("score"), 50)
        avg_pnl = self.safe_float(record.get("avg_pnl"))
        total_pnl = self.safe_float(record.get("total_pnl"))

        return {
            "wallet": wallet,
            "recommendation": recommendation,
            "label": self.labeler.primary_label(record),
            "confidence": self.confidence(entries, signals),
            "size_multiplier": self.size_multiplier(recommendation, score, entries),
            "score": score,
            "signals": signals,
            "entries": entries,
            "wins": self.safe_int(record.get("wins")),
            "losses": self.safe_int(record.get("losses")),
            "avg_pnl": avg_pnl,
            "total_pnl": total_pnl,
            "labels": ", ".join(labels),
            "last_seen": record.get("last_seen"),
        }

    def recommendation(self, record, labels):
        entries = self.safe_int(record.get("paper_entries"))
        signals = self.safe_int(record.get("signals"))
        score = self.safe_float(record.get("score"), 50)
        avg_pnl = self.safe_float(record.get("avg_pnl"))

        if "fade/caution" in labels or "consistent loser" in labels or avg_pnl <= -8:
            return "FADE"
        if entries >= 5 and score >= 62 and avg_pnl > 0:
            return "COPY"
        if entries >= 2 and score >= 55 and avg_pnl > 0:
            return "PAPER_COPY"
        if signals >= 25 and entries == 0:
            return "OBSERVE"
        if entries > 0:
            return "HOLD_NEUTRAL"
        return "UNPROVEN"

    def signal_action(self, copy_wallets, fade_wallets, signal):
        copy_confidence = sum(w["confidence"] for w in copy_wallets)
        fade_confidence = sum(w["confidence"] for w in fade_wallets)

        if fade_confidence >= 1.5 and fade_confidence > copy_confidence:
            return "FADE_SIGNAL"
        if copy_confidence >= 2.0:
            return "COPY_WATCH"
        if copy_confidence >= 1.0:
            return "PAPER_COPY_WATCH"
        if signal.get("should_trade"):
            return "SCANNER_TRADE_ONLY"
        return "OBSERVE"

    def top_wallet(self, wallet_reviews):
        if not wallet_reviews:
            return None
        top = max(wallet_reviews, key=lambda row: (row["confidence"], row["score"], row["signals"]))
        return top.get("wallet")

    def confidence(self, entries, signals):
        sample_confidence = min(1.0, entries / 8)
        signal_confidence = min(0.5, signals / 200)
        return round(sample_confidence + signal_confidence, 3)

    def size_multiplier(self, recommendation, score, entries):
        if recommendation == "COPY":
            return round(min(1.25, 0.75 + ((score - 60) / 100) + min(0.25, entries / 40)), 2)
        if recommendation == "PAPER_COPY":
            return 0.5
        if recommendation == "FADE":
            return 0.0
        return 0.25

    def action_rank(self, action):
        return {
            "COPY": 6,
            "PAPER_COPY": 5,
            "OBSERVE": 4,
            "HOLD_NEUTRAL": 3,
            "UNPROVEN": 2,
            "FADE": 1,
        }.get(action, 0)

    def safe_float(self, value, default=0.0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default

    def safe_int(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return int(float(value))
        except Exception:
            return default
