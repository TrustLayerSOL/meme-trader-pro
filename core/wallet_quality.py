import json
import os
import time


ELITE_WALLETS_FILE = "data/elite_wallets.json"
BAD_WALLETS_FILE = "data/bad_wallets.json"


class WalletQualityAnalyzer:
    def __init__(self):
        self.elite_wallets = self.load_wallet_set(ELITE_WALLETS_FILE)
        self.bad_wallets = self.load_wallet_set(BAD_WALLETS_FILE)

        # Runtime behavior memory for this bot session
        self.activity = {}

    def load_wallet_set(self, filename):
        if not os.path.exists(filename):
            return set()

        try:
            with open(filename, "r") as f:
                data = json.load(f)

            if isinstance(data, list):
                return set(data)

            if isinstance(data, dict):
                return set(data.keys())

        except Exception:
            pass

        return set()

    def ensure_wallet(self, wallet):
        if wallet not in self.activity:
            self.activity[wallet] = {
                "buys": 0,
                "sells": 0,
                "mints": set(),
                "mint_events": {},
                "first_seen": time.time(),
                "last_seen": time.time(),
            }

        return self.activity[wallet]

    def record_event(self, wallet, event_type, mint):
        now = time.time()

        data = self.ensure_wallet(wallet)
        data["last_seen"] = now
        data["mints"].add(mint)

        if event_type == "buy":
            data["buys"] += 1
        elif event_type == "sell":
            data["sells"] += 1

        if mint not in data["mint_events"]:
            data["mint_events"][mint] = {
                "buys": 0,
                "sells": 0,
                "first_buy_time": None,
                "last_buy_time": None,
                "first_sell_time": None,
                "last_sell_time": None,
            }

        mint_data = data["mint_events"][mint]

        if event_type == "buy":
            mint_data["buys"] += 1

            if mint_data["first_buy_time"] is None:
                mint_data["first_buy_time"] = now

            mint_data["last_buy_time"] = now

        elif event_type == "sell":
            mint_data["sells"] += 1

            if mint_data["first_sell_time"] is None:
                mint_data["first_sell_time"] = now

            mint_data["last_sell_time"] = now

    def score_wallet(self, wallet):
        # ------------------------
        # MANUAL OVERRIDES
        # ------------------------
        if wallet in self.elite_wallets:
            return {
                "wallet": wallet,
                "score": 95,
                "label": "ELITE",
                "reasons": ["Manually marked elite wallet"],
            }

        if wallet in self.bad_wallets:
            return {
                "wallet": wallet,
                "score": 10,
                "label": "BAD",
                "reasons": ["Manually marked bad wallet"],
            }

        data = self.activity.get(wallet)

        if not data:
            return {
                "wallet": wallet,
                "score": 50,
                "label": "UNKNOWN",
                "reasons": ["No local wallet history yet"],
            }

        buys = int(data.get("buys", 0))
        sells = int(data.get("sells", 0))
        total = buys + sells
        unique_mints = len(data.get("mints", []))

        score = 50
        reasons = []

        # ------------------------
        # BUY ACTIVITY
        # ------------------------
        if buys >= 3:
            score += 5
            reasons.append("Some buy activity")

        if buys >= 8:
            score += 8
            reasons.append("Frequent buyer")

        if buys >= 15:
            score += 8
            reasons.append("Very active buyer")

        # ------------------------
        # SELL HEAVINESS
        # ------------------------
        if total > 0:
            sell_ratio = sells / total

            if sell_ratio > 0.80:
                score -= 25
                reasons.append("Extremely seller-heavy wallet")
            elif sell_ratio > 0.65:
                score -= 15
                reasons.append("Seller-heavy wallet")
            elif sell_ratio > 0.50:
                score -= 8
                reasons.append("Slightly seller-heavy wallet")

        # ------------------------
        # BUY-HEAVY BEHAVIOR
        # ------------------------
        if buys >= 3 and sells == 0:
            score += 10
            reasons.append("Buy-heavy wallet")

        elif buys > sells and buys >= 5:
            score += 6
            reasons.append("Net buyer")

        # ------------------------
        # DIVERSITY
        # ------------------------
        if unique_mints >= 20:
            score += 4
            reasons.append("Broad market activity")
        elif unique_mints >= 10:
            score += 2
            reasons.append("Moderate market activity")

        # ------------------------
        # SCALPER / CHURN DETECTION
        # ------------------------
        rapid_flip_count = 0
        repeated_churn_count = 0
        conviction_buy_count = 0

        for mint, mint_data in data.get("mint_events", {}).items():
            mint_buys = int(mint_data.get("buys", 0))
            mint_sells = int(mint_data.get("sells", 0))

            first_buy = mint_data.get("first_buy_time")
            first_sell = mint_data.get("first_sell_time")

            if first_buy and first_sell:
                seconds_to_first_sell = first_sell - first_buy

                if 0 <= seconds_to_first_sell <= 120:
                    rapid_flip_count += 1

            if mint_buys >= 2 and mint_sells >= 2:
                repeated_churn_count += 1

            if mint_buys >= 2 and mint_sells == 0:
                conviction_buy_count += 1

        if rapid_flip_count >= 5:
            score -= 20
            reasons.append("Repeated rapid flip behavior")
        elif rapid_flip_count >= 2:
            score -= 10
            reasons.append("Some rapid flips")

        if repeated_churn_count >= 5:
            score -= 15
            reasons.append("Heavy buy/sell churn")
        elif repeated_churn_count >= 2:
            score -= 8
            reasons.append("Some buy/sell churn")

        if conviction_buy_count >= 5:
            score += 12
            reasons.append("Repeated conviction buys")
        elif conviction_buy_count >= 2:
            score += 6
            reasons.append("Some conviction buys")

        # ------------------------
        # SESSION RECENCY
        # ------------------------
        last_seen = float(data.get("last_seen", 0) or 0)
        age_since_seen = time.time() - last_seen

        if age_since_seen <= 300:
            score += 2
            reasons.append("Recently active")

        # ------------------------
        # LABEL
        # ------------------------
        score = max(0, min(100, round(score, 2)))

        if score >= 90:
            label = "ELITE_LIVE"
        elif score >= 80:
            label = "STRONG_LIVE"
        elif score >= 65:
            label = "GOOD_LIVE"
        elif score >= 45:
            label = "NEUTRAL_LIVE"
        elif score >= 25:
            label = "WEAK_LIVE"
        else:
            label = "BAD_LIVE"

        return {
            "wallet": wallet,
            "score": score,
            "label": label,
            "reasons": reasons or ["Local activity based score"],
            "stats": {
                "buys": buys,
                "sells": sells,
                "unique_mints": unique_mints,
                "rapid_flip_count": rapid_flip_count,
                "repeated_churn_count": repeated_churn_count,
                "conviction_buy_count": conviction_buy_count,
            },
        }

    def score_wallets(self, wallets):
        scored = [self.score_wallet(w) for w in wallets]

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