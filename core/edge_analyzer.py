class EdgeAnalyzer:
    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default

    def analyze(
        self,
        wallet_count,
        weighted_wallet_score,
        repeated_buys,
        wallet_quality,
        wallet_performance,
        liquidity_usd,
        volume_usd,
        true_launch_age_seconds,
        token_age_seconds,
        social_match,
        rug_result,
        decision_score,
    ):
        wallet_count = int(wallet_count or 0)
        weighted_wallet_score = self.safe_float(weighted_wallet_score)
        repeated_buys = int(repeated_buys or 0)
        liquidity_usd = self.safe_float(liquidity_usd)
        volume_usd = self.safe_float(volume_usd)
        decision_score = self.safe_float(decision_score)

        wallet_quality = wallet_quality or {}
        wallet_performance = wallet_performance or {}
        social_match = social_match or {}
        rug_result = rug_result or {}

        max_quality = self.safe_float(wallet_quality.get("max_score"), 50)
        avg_quality = self.safe_float(wallet_quality.get("avg_score"), 50)
        max_perf = self.safe_float(wallet_performance.get("max_score"), 50)
        avg_perf = self.safe_float(wallet_performance.get("avg_score"), 50)
        risk_score = self.safe_float(rug_result.get("risk_score"))
        risk_label = str(rug_result.get("risk_label", "UNKNOWN"))

        score = 0
        positives = []
        risks = []

        if wallet_count >= 5:
            score += 26
            positives.append("dense_wallet_cluster")
        elif wallet_count >= 3:
            score += 20
            positives.append("confirmed_wallet_cluster")
        elif wallet_count == 2:
            score += 13
            positives.append("two_wallet_early_signal")
        elif wallet_count == 1:
            score += 5
            positives.append("solo_wallet_watch")

        if weighted_wallet_score >= 4:
            score += 24
            positives.append("elite_weighted_wallet_pressure")
        elif weighted_wallet_score >= 3:
            score += 18
            positives.append("strong_weighted_wallet_pressure")
        elif weighted_wallet_score >= 1.8:
            score += 12
            positives.append("quote_worthy_weighted_wallet_pressure")

        if max_perf >= 80 or max_quality >= 80:
            score += 16
            positives.append("top_wallet_quality")
        elif max_perf >= 65 or max_quality >= 65:
            score += 10
            positives.append("good_wallet_quality")
        elif avg_perf < 40 or avg_quality < 40:
            score -= 8
            risks.append("weak_wallet_quality")

        if repeated_buys >= 6:
            score += 12
            positives.append("repeated_buy_pressure")
        elif repeated_buys >= 2:
            score += 7
            positives.append("some_repeated_buys")

        if liquidity_usd >= 100000:
            score += 15
            positives.append("deep_liquidity")
        elif liquidity_usd >= 30000:
            score += 11
            positives.append("strong_liquidity")
        elif liquidity_usd >= 10000:
            score += 6
            positives.append("tradable_liquidity")
        elif liquidity_usd > 0:
            score -= 10
            risks.append("thin_liquidity")
        else:
            score -= 6
            risks.append("missing_liquidity")

        if volume_usd >= 250000:
            score += 10
            positives.append("strong_volume")
        elif volume_usd >= 50000:
            score += 6
            positives.append("active_volume")

        if true_launch_age_seconds is not None:
            true_age = self.safe_float(true_launch_age_seconds)
            if true_age <= 90:
                score += 14
                positives.append("ultra_early_launch")
            elif true_age <= 600:
                score += 10
                positives.append("early_launch")
            elif true_age >= 7200:
                score -= 8
                risks.append("late_launch")

        if token_age_seconds is not None:
            bot_age = self.safe_float(token_age_seconds)
            if bot_age <= 120:
                score += 6
                positives.append("fresh_to_bot")

        if social_match.get("matched"):
            score += min(10, self.safe_float(social_match.get("score_bonus"), 5))
            positives.append("social_catalyst")

        if rug_result.get("hard_block"):
            score = 0
            risks.append("hard_block")
        elif risk_label == "HIGH_RISK":
            score -= 14
            risks.append("high_risk")
        elif risk_label == "MEDIUM_RISK":
            score -= 6
            risks.append("medium_risk")

        if risk_score >= 18:
            score -= 8
            risks.append("elevated_risk_score")

        score = max(0, min(100, round(score, 2)))

        quote_worthy = (
            not rug_result.get("hard_block")
            and score >= 45
            and liquidity_usd >= 5000
        )

        paper_trade_worthy = (
            quote_worthy
            and score >= 62
            and (wallet_count >= 2 or weighted_wallet_score >= 1.8 or repeated_buys >= 3)
            and risk_label != "HIGH_RISK"
        )

        if score >= 75:
            verdict = "STRONG_EDGE"
        elif score >= 62:
            verdict = "TRADEABLE_EDGE"
        elif score >= 45:
            verdict = "QUOTE_WORTHY"
        elif score >= 28:
            verdict = "WATCHLIST"
        else:
            verdict = "IGNORE"

        return {
            "edge_score": score,
            "edge_verdict": verdict,
            "quote_worthy": quote_worthy,
            "paper_trade_worthy": paper_trade_worthy,
            "positives": positives,
            "risks": risks,
            "decision_score": decision_score,
        }
