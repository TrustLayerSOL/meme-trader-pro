from core.settings_manager import load_settings


class PositionSizer:
    def __init__(self):
        self.settings = load_settings()

    def size_trade(self, decision, rug_result, quote_analysis):
        score = float(decision.get("score", 0))
        threshold = float(decision.get("threshold", 55))
        risk_label = rug_result.get("risk_label", "UNKNOWN")

        # ------------------------
        # 🚨 HARD BLOCK ONLY
        # ------------------------
        if rug_result.get("hard_block"):
            return 0

        # ------------------------
        # 🚨 REQUIRE QUOTE PASS
        # ------------------------
        if not quote_analysis.get("pass"):
            return 0

        # ------------------------
        # 🎯 FORCE MINIMUM TRADE IF SIGNAL IS GOOD
        # ------------------------
        if score >= threshold:
            base_size = float(self.settings.get("paper_base_position_usd", 30))

            # Scale up slightly for strong signals
            if score >= 70:
                base_size = float(self.settings.get("paper_strong_position_usd", 60))
            elif score >= 65:
                base_size = float(self.settings.get("paper_medium_position_usd", 45))

            # Slight reduction for high risk, BUT NOT ZERO
            if risk_label == "HIGH_RISK":
                base_size *= 0.6
            elif risk_label == "MEDIUM_RISK":
                base_size *= 0.8

            return round(base_size, 2)

        # ------------------------
        # ❌ BELOW THRESHOLD
        # ------------------------
        return 0
