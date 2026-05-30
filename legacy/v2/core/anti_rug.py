class AntiRugAnalyzer:
    def __init__(self):
        pass

    def analyze(
        self,
        mint,
        market_info=None,
        dev_score=None,
        token_inspection=None,
        wallet_count=0,
        repeated_buys=0,
    ):
        market_info = market_info or {}
        dev_score = dev_score or {}
        token_inspection = token_inspection or {}

        penalties = []
        warnings = []

        hard_block = False
        hard_block_reason = None

        liquidity = self.safe_float(market_info.get("liquidity", 0))
        volume = self.safe_float(market_info.get("volume", 0))

        dev_label = str(dev_score.get("label", "Unknown")).upper()
        dev_points = self.safe_float(dev_score.get("score", 0))
        bonded_tokens = int(self.safe_float(dev_score.get("bonded_tokens", 0)))

        wallet_count = int(wallet_count or 0)
        repeated_buys = int(repeated_buys or 0)

        # ------------------------
        # TRUE HARD BLOCKS ONLY
        # ------------------------
        if dev_label in ["BLACKLISTED", "KNOWN_RUG", "RUGGER"]:
            hard_block = True
            hard_block_reason = "Known rug / blacklisted dev"

        if token_inspection.get("hard_block"):
            hard_block = True
            hard_block_reason = "; ".join(token_inspection.get("reasons", []))

        for reason in token_inspection.get("reasons", []):
            if reason != "No dangerous token mechanics detected":
                warnings.append(reason)

        if token_inspection.get("risk_label") == "CAUTION":
            penalties.append({
                "label": "Token mechanics caution",
                "amount": 5,
            })

        # ------------------------
        # LIQUIDITY RISK
        # Learning mode: liquidity should penalize, not instantly block.
        # ------------------------
        if liquidity <= 0:
            penalties.append({
                "label": "No liquidity data",
                "amount": 6,
            })
            warnings.append("No liquidity data available")

        elif liquidity < 1500:
            penalties.append({
                "label": "Extremely thin liquidity",
                "amount": 10,
            })
            warnings.append("Extremely thin liquidity")

        elif liquidity < 5000:
            penalties.append({
                "label": "Low liquidity",
                "amount": 8,
            })
            warnings.append("Low liquidity")

        elif liquidity < 10000:
            penalties.append({
                "label": "Thin liquidity",
                "amount": 4,
            })
            warnings.append("Thin liquidity")

        # ------------------------
        # VOLUME RISK
        # ------------------------
        if volume <= 0:
            penalties.append({
                "label": "No volume data",
                "amount": 3,
            })
            warnings.append("No volume data")

        elif volume < 5000:
            penalties.append({
                "label": "Low volume",
                "amount": 4,
            })
            warnings.append("Low volume")

        # ------------------------
        # DEV RISK
        # Unknown dev is NOT a hard block in meme coin mode.
        # ------------------------
        if bonded_tokens >= 5:
            warnings.append("Dev has 5+ bonded/migrated projects")
        elif 2 <= bonded_tokens <= 4:
            penalties.append({
                "label": "Moderate dev bond history",
                "amount": 2,
            })
            warnings.append("Dev has 2-4 bonded/migrated projects; inspect extensions")
        elif dev_label in ["NEW_DEV", "UNKNOWN_DEV"]:
            penalties.append({
                "label": "No known bonded dev history",
                "amount": 5,
            })
            warnings.append("No known bonded/migrated dev history")

        if dev_label in ["BAD", "WEAK", "RISKY", "RISKY_DEV"]:
            penalties.append({
                "label": "Bad dev",
                "amount": 8,
            })
            warnings.append("Weak or risky dev history")

        elif dev_points > 0 and dev_points < 30:
            penalties.append({
                "label": "Weak dev score",
                "amount": 6,
            })
            warnings.append("Weak dev score")

        # ------------------------
        # WALLET CONVICTION RISK
        # Do not over-punish solo signals in learning mode.
        # ------------------------
        if wallet_count <= 0:
            penalties.append({
                "label": "No wallet confirmation",
                "amount": 8,
            })
            warnings.append("No wallet confirmation")

        elif wallet_count == 1 and repeated_buys == 0:
            penalties.append({
                "label": "Solo wallet only",
                "amount": 3,
            })
            warnings.append("Solo wallet signal")

        elif wallet_count == 1 and repeated_buys > 0:
            penalties.append({
                "label": "Single wallet repeated buys",
                "amount": 1,
            })
            warnings.append("Single wallet repeated buys")

        # ------------------------
        # POSITIVE CONTEXT REDUCES RISK
        # ------------------------
        risk_score = 0

        for p in penalties:
            risk_score += self.safe_float(p.get("amount", 0))

        if wallet_count >= 3:
            risk_score -= 6

        if wallet_count >= 5:
            risk_score -= 5

        if repeated_buys >= 3:
            risk_score -= 4

        if liquidity >= 20000:
            risk_score -= 4

        if volume >= 50000:
            risk_score -= 4

        if bonded_tokens >= 5:
            risk_score -= 8
        elif 2 <= bonded_tokens <= 4:
            risk_score -= 2

        risk_score = max(0, round(risk_score, 2))

        # ------------------------
        # RISK LABEL
        # ------------------------
        if hard_block:
            risk_label = "BLOCKED"
        elif risk_score >= 22:
            risk_label = "HIGH_RISK"
        elif risk_score >= 10:
            risk_label = "MEDIUM_RISK"
        else:
            risk_label = "LOW_RISK"

        return {
            "mint": mint,
            "risk_score": risk_score,
            "risk_label": risk_label,
            "warnings": warnings,
            "penalties": penalties,
            "hard_block": hard_block,
            "hard_block_reason": hard_block_reason,
        }

    def safe_float(self, value):
        try:
            if value is None:
                return 0
            return float(value)
        except Exception:
            return 0
