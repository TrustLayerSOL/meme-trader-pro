import json
import os
import time

DEV_DB_FILE = "dev_reputation.json"


class DevAnalyzer:
    def __init__(self):
        self.dev_db = self.load_db()

    def load_db(self):
        if not os.path.exists(DEV_DB_FILE):
            return {}

        try:
            with open(DEV_DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_db(self):
        with open(DEV_DB_FILE, "w") as f:
            json.dump(self.dev_db, f, indent=2)

    def score_dev(self, dev_wallet):
        if not dev_wallet:
            return {
                "score": 0,
                "label": "UNKNOWN_DEV",
                "reasons": ["No dev wallet"]
            }

        dev = self.dev_db.get(dev_wallet)

        if not dev:
            return {
                "score": -10,
                "label": "NEW_DEV",
                "reasons": ["No history"]
            }

        tokens = int(dev.get("tokens_created", 0) or 0)
        bonded = int(
            dev.get("bonded_tokens", dev.get("tokens_bonded", dev.get("migrated_tokens", 0)))
            or 0
        )

        score = 0
        reasons = []

        if bonded >= 5:
            score += 45
            reasons.append("5+ bonded/migrated projects")
        elif bonded >= 2:
            score += 15
            reasons.append("2-4 bonded/migrated projects; still inspect mechanics")
        elif bonded == 0:
            score -= 8
            reasons.append("No known bonded/migrated projects")

        if tokens >= 5 and bonded < 5:
            score += 10
            reasons.append("Multiple created tokens")

        if tokens == 1 and bonded == 0:
            score -= 15
            reasons.append("Single token dev")

        if score >= 40:
            label = "REPUTABLE_BONDED_DEV"
        elif score >= 15:
            label = "STRONG_DEV"
        elif score >= 0:
            label = "OK_DEV"
        else:
            label = "RISKY_DEV"

        return {
            "score": score,
            "label": label,
            "reasons": reasons,
            "tokens_created": tokens,
            "bonded_tokens": bonded,
        }
