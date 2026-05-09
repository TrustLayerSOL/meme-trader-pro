import json
import os
import time

from core.json_store import locked_update_json

PERFORMANCE_FILE = "data/wallet_performance.json"


class WalletPerformanceTracker:
    def __init__(self):
        self.data = self.load()

    def load(self):
        if not os.path.exists(PERFORMANCE_FILE):
            return self.default_state()

        try:
            with open(PERFORMANCE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return self.default_state()

    def default_state(self):
        return {
            "wallets": {},
            "signals": []
        }

    def save(self):
        try:
            locked_update_json(PERFORMANCE_FILE, self.default_state(), lambda _current: self.data)
        except Exception as e:
            print("Failed to save wallet performance:", e)

    def ensure_wallet_in(self, data, wallet):
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

    def ensure_wallet(self, wallet):
        wallets = self.data.setdefault("wallets", {})

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

    def record_signal(
        self,
        wallets,
        mint,
        signal_type,
        score,
        should_trade,
        token_age_seconds=None,
    ):
        now = time.time()

        signal = {
            "time": now,
            "mint": mint,
            "wallets": wallets,
            "signal_type": signal_type,
            "score": score,
            "should_trade": should_trade,
            "token_age_seconds": token_age_seconds,
        }

        def updater(data):
            if not isinstance(data, dict):
                data = self.default_state()
            data.setdefault("signals", []).insert(0, signal)
            data["signals"] = data["signals"][:1000]

            for wallet in wallets:
                record = self.ensure_wallet_in(data, wallet)
                record["signals"] += 1
                record["last_seen"] = now

            return data

        self.data = locked_update_json(PERFORMANCE_FILE, self.default_state(), updater)

    def record_trade_result(self, wallets, pnl):
        pnl = float(pnl or 0)

        def updater(data):
            if not isinstance(data, dict):
                data = self.default_state()

            for wallet in wallets:
                record = self.ensure_wallet_in(data, wallet)

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

            return data

        self.data = locked_update_json(PERFORMANCE_FILE, self.default_state(), updater)

    def get_wallet_score(self, wallet):
        record = self.data.get("wallets", {}).get(wallet)

        if not record:
            return {
                "wallet": wallet,
                "score": 50,
                "label": "UNPROVEN",
                "record": None,
            }

        score = float(record.get("score", 50))

        if score >= 85:
            label = "ELITE_PERFORMER"
        elif score >= 70:
            label = "GOOD_PERFORMER"
        elif score >= 50:
            label = "NEUTRAL_PERFORMER"
        elif score >= 30:
            label = "WEAK_PERFORMER"
        else:
            label = "BAD_PERFORMER"

        return {
            "wallet": wallet,
            "score": score,
            "label": label,
            "record": record,
        }

    def score_wallets(self, wallets):
        scored = [self.get_wallet_score(w) for w in wallets]

        if not scored:
            return {
                "avg_score": 0,
                "max_score": 0,
                "top_wallet": None,
                "wallet_scores": [],
            }

        avg_score = sum(w["score"] for w in scored) / len(scored)
        top = max(scored, key=lambda x: x["score"])

        return {
            "avg_score": round(avg_score, 2),
            "max_score": top["score"],
            "top_wallet": top["wallet"],
            "wallet_scores": scored,
        }
