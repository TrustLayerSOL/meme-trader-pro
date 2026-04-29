import time

from core.settings_manager import load_settings


DEFAULT_SETTINGS = {
    "mode": "CONFIRMATION",
    "sniper_score_threshold": 55,
    "confirmation_score_threshold": 68,
    "safe_score_threshold": 85,
}


class ScoringEngine:
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.settings.update(load_settings())

    def get_mode(self):
        return str(self.settings.get("mode", "SNIPER")).upper()

    def get_threshold(self):
        if self.get_mode() == "SAFE":
            return float(self.settings.get("safe_score_threshold", 85))
        if self.get_mode() == "CONFIRMATION":
            return float(self.settings.get("confirmation_score_threshold", 68))

        return float(self.settings.get("sniper_score_threshold", 55))

    def score_token(
        self,
        mint,
        wallets,
        dev_score_data=None,
        liquidity_score=0,
        volume_score=0,
        repeated_buys=0,
        token_age_seconds=None,
        true_launch_age_seconds=None,
        risk_penalties=None,
        wallet_quality=None,
        wallet_performance=None,
    ):
        dev_score_data = dev_score_data or {}
        risk_penalties = risk_penalties or []
        wallet_quality = wallet_quality or {}
        wallet_performance = wallet_performance or {}

        wallets = list(set(wallets or []))
        wallet_count = len(wallets)

        dev_score = float(dev_score_data.get("score", 0) or 0)
        dev_label = str(dev_score_data.get("label", "UNKNOWN")).upper()

        avg_wallet_quality = float(wallet_quality.get("avg_score", 0) or 0)
        max_wallet_quality = float(wallet_quality.get("max_score", 0) or 0)

        avg_wallet_perf = float(wallet_performance.get("avg_score", 0) or 0)
        max_wallet_perf = float(wallet_performance.get("max_score", 0) or 0)

        top_wallet = (
            wallet_performance.get("top_wallet")
            or wallet_quality.get("top_wallet")
        )

        score = 0
        reasons = []

        # ------------------------
        # WALLET PERFORMANCE MEMORY
        # ------------------------
        if max_wallet_perf >= 90:
            score += 35
            reasons.append(f"Elite performance wallet: {top_wallet}")
        elif max_wallet_perf >= 80:
            score += 26
            reasons.append("Strong historical wallet performer")
        elif max_wallet_perf >= 70:
            score += 18
            reasons.append("Good historical wallet performer")
        elif max_wallet_perf >= 55:
            score += 8
            reasons.append("Slightly positive wallet history")
        elif 0 < max_wallet_perf < 40:
            score -= 12
            reasons.append("Poor wallet performance history")

        if avg_wallet_perf >= 85:
            score += 14
            reasons.append("Elite average wallet history")
        elif avg_wallet_perf >= 70:
            score += 8
            reasons.append("Good average wallet history")
        elif 0 < avg_wallet_perf < 40:
            score -= 8
            reasons.append("Weak average wallet history")

        # ------------------------
        # LIVE WALLET QUALITY
        # ------------------------
        if max_wallet_quality >= 90:
            score += 28
            reasons.append(f"Elite live wallet signal: {top_wallet}")
        elif max_wallet_quality >= 80:
            score += 22
            reasons.append("Strong live wallet signal")
        elif max_wallet_quality >= 65:
            score += 12
            reasons.append("Good live wallet signal")
        elif max_wallet_quality >= 50:
            score += 5
            reasons.append("Neutral live wallet signal")
        else:
            score -= 8
            reasons.append("Weak live wallet signal")

        if avg_wallet_quality >= 80:
            score += 12
            reasons.append("High average live wallet quality")
        elif avg_wallet_quality >= 65:
            score += 7
            reasons.append("Good average live wallet quality")
        elif 0 < avg_wallet_quality < 40:
            score -= 8
            reasons.append("Low average live wallet quality")

        # ------------------------
        # SMART MONEY CLUSTER / EARLY SIGNAL
        # ------------------------
        if wallet_count >= 8:
            score += 38
            reasons.append(f"Major smart-wallet cluster ({wallet_count})")
        elif wallet_count >= 6:
            score += 32
            reasons.append(f"Strong smart-wallet cluster ({wallet_count})")
        elif wallet_count >= 4:
            score += 24
            reasons.append(f"Good smart-wallet cluster ({wallet_count})")
        elif wallet_count >= 3:
            score += 18
            reasons.append(f"Cluster confirmed ({wallet_count})")
        elif wallet_count == 2:
            score += 12
            reasons.append("Early 2-wallet signal")
        elif wallet_count == 1:
            score += 6
            reasons.append("Solo early signal")

        # ------------------------
        # DEV SCORE
        # Unknown dev is neutral in learning mode.
        # ------------------------
        if dev_label in ["BAD", "RUG", "BLACKLISTED"]:
            score -= 15
            reasons.append("Bad dev")
        elif dev_score >= 85:
            score += 24
            reasons.append("Elite dev history")
        elif dev_score >= 70:
            score += 17
            reasons.append("Strong dev")
        elif dev_score >= 55:
            score += 10
            reasons.append("Good dev")
        elif dev_score >= 40:
            score += 4
            reasons.append("Mid dev")
        else:
            reasons.append("Unknown dev neutral")

        # ------------------------
        # LIQUIDITY
        # ------------------------
        liquidity_score = float(liquidity_score or 0)

        if liquidity_score >= 85:
            score += 16
            reasons.append("Excellent liquidity")
        elif liquidity_score >= 70:
            score += 12
            reasons.append("Strong liquidity")
        elif liquidity_score >= 50:
            score += 7
            reasons.append("Acceptable liquidity")
        elif liquidity_score > 0:
            score -= 4
            reasons.append("Weak liquidity")

        # ------------------------
        # VOLUME / VELOCITY
        # ------------------------
        volume_score = float(volume_score or 0)

        if volume_score >= 85:
            score += 14
            reasons.append("Excellent volume")
        elif volume_score >= 70:
            score += 10
            reasons.append("Strong volume")
        elif volume_score >= 50:
            score += 5
            reasons.append("Acceptable volume")

        # ------------------------
        # REPEATED BUYS / CONVICTION
        # ------------------------
        repeated_buys = int(repeated_buys or 0)

        if repeated_buys >= 8:
            score += 14
            reasons.append("Very strong repeated buys")
        elif repeated_buys >= 5:
            score += 10
            reasons.append("Strong repeated buys")
        elif repeated_buys >= 2:
            score += 6
            reasons.append("Some repeated buys")

        # ------------------------
        # BOT-SEEN AGE
        # ------------------------
        if token_age_seconds is not None:
            token_age_seconds = float(token_age_seconds)

            if token_age_seconds <= 60:
                score += 6
                reasons.append("Fresh to bot")
            elif token_age_seconds <= 300:
                score += 3
                reasons.append("Recently seen by bot")

        # ------------------------
        # TRUE LAUNCH AGE
        # ------------------------
        if true_launch_age_seconds is not None:
            true_launch_age_seconds = float(true_launch_age_seconds)

            if true_launch_age_seconds <= 60:
                score += 18
                reasons.append("True ultra-early launch")
            elif true_launch_age_seconds <= 300:
                score += 14
                reasons.append("True very early launch")
            elif true_launch_age_seconds <= 900:
                score += 8
                reasons.append("True early launch")
            elif true_launch_age_seconds <= 3600:
                reasons.append("Mid-age launch")
            elif true_launch_age_seconds <= 7200:
                score -= 6
                reasons.append("Older launch")
            else:
                score -= 10
                reasons.append("Late launch timing")

        # ------------------------
        # RISK PENALTIES
        # ------------------------
        for p in risk_penalties:
            amount = float(p.get("amount", 0) or 0)
            label = p.get("label", "Risk penalty")

            score -= amount
            reasons.append(f"{label}: -{amount}")

        score = max(0, min(100, round(score, 2)))
        threshold = self.get_threshold()

        return {
            "mint": mint,
            "score": score,
            "threshold": threshold,
            "mode": self.get_mode(),
            "should_trade": score >= threshold,
            "wallet_count": wallet_count,
            "avg_wallet_quality": avg_wallet_quality,
            "max_wallet_quality": max_wallet_quality,
            "avg_wallet_performance": avg_wallet_perf,
            "max_wallet_performance": max_wallet_perf,
            "top_wallet": top_wallet,
            "token_age_seconds": token_age_seconds,
            "true_launch_age_seconds": true_launch_age_seconds,
            "reasons": reasons,
            "timestamp": time.time(),
        }
