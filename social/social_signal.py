import json
import os
import re
import time


SOCIAL_STATE_FILE = "data/social_state.json"


HIGH_IMPACT_ACCOUNTS = {
    "elonmusk": 30,
    "tesla": 20,
    "spacex": 20,
    "cb_doge": 12,
    "dogeofficialceo": 12,
}


STOP_WORDS = {
    "the", "and", "for", "you", "your", "are", "was", "were", "with", "this",
    "that", "from", "have", "has", "had", "not", "but", "they", "them", "his",
    "her", "him", "she", "our", "out", "all", "can", "will", "just", "what",
    "when", "where", "why", "how", "about", "into", "over", "under", "again",
    "there", "their", "would", "could", "should", "then", "than", "been",
    "being", "because", "very", "more", "less", "much", "many", "some",
    "like", "make", "made", "thing", "things", "time", "today", "tomorrow",
    "yesterday", "http", "https", "com", "www", "amp"
}


class SocialSignalEngine:
    def __init__(self):
        self.state = self.load_state()

    def load_state(self):
        if not os.path.exists(SOCIAL_STATE_FILE):
            return {"signals": []}

        try:
            with open(SOCIAL_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"signals": []}

    def save_state(self):
        with open(SOCIAL_STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def clean_text(self, text):
        text = str(text or "")
        text = text.replace("\n", " ")
        text = re.sub(r"http\S+", " ", text)
        text = re.sub(r"[^A-Za-z0-9$# ]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_keywords(self, text):
        cleaned = self.clean_text(text)
        raw_words = cleaned.split(" ")

        keywords = []

        for word in raw_words:
            word = word.strip()

            if not word:
                continue

            lower = word.lower()

            if lower in STOP_WORDS:
                continue

            if len(lower) < 3 and not lower.startswith("$"):
                continue

            if lower.isnumeric():
                continue

            if lower.startswith("$") and len(lower) > 1:
                keywords.append(lower.replace("$", ""))
                continue

            if lower.startswith("#") and len(lower) > 1:
                keywords.append(lower.replace("#", ""))
                continue

            keywords.append(lower)

        # Preserve order while de-duplicating
        seen = set()
        final = []

        for keyword in keywords:
            if keyword not in seen:
                seen.add(keyword)
                final.append(keyword)

        return final[:12]

    def account_weight(self, account):
        account = str(account or "").lower().replace("@", "")
        return HIGH_IMPACT_ACCOUNTS.get(account, 8)

    def add_signal(self, account, text, url=None):
        account = str(account or "").lower().replace("@", "")
        now = time.time()

        keywords = self.extract_keywords(text)
        weight = self.account_weight(account)

        signal = {
            "account": account,
            "text": text,
            "keywords": keywords,
            "weight": weight,
            "url": url,
            "timestamp": now,
            "expires_at": now + (6 * 60 * 60),
        }

        self.state.setdefault("signals", [])
        self.state["signals"].insert(0, signal)

        # Keep recent 200 social signals only
        self.state["signals"] = self.state["signals"][:200]

        self.save_state()

        return signal

    def get_active_signals(self):
        now = time.time()

        signals = [
            s for s in self.state.get("signals", [])
            if float(s.get("expires_at", 0) or 0) > now
        ]

        return signals

    def normalize_token_text(self, value):
        value = str(value or "").lower()
        value = re.sub(r"[^a-z0-9 ]+", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def match_token(self, mint, market_info=None):
        market_info = market_info or {}

        token_name = self.normalize_token_text(market_info.get("name", ""))
        token_symbol = self.normalize_token_text(market_info.get("symbol", ""))

        searchable = f"{token_name} {token_symbol}".strip()

        if not searchable:
            return {
                "matched": False,
                "score_bonus": 0,
                "matched_keywords": [],
                "matched_account": None,
                "matched_signal": None,
                "reason": "no_token_name_or_symbol",
            }

        best = {
            "matched": False,
            "score_bonus": 0,
            "matched_keywords": [],
            "matched_account": None,
            "matched_signal": None,
            "reason": "no_social_match",
        }

        active = self.get_active_signals()

        for signal in active:
            keywords = signal.get("keywords", [])
            matched_keywords = []

            for keyword in keywords:
                keyword = self.normalize_token_text(keyword)

                if not keyword:
                    continue

                if keyword == token_symbol:
                    matched_keywords.append(keyword)
                    continue

                if keyword in token_name.split(" "):
                    matched_keywords.append(keyword)
                    continue

                if len(keyword) >= 4 and keyword in searchable:
                    matched_keywords.append(keyword)

            if not matched_keywords:
                continue

            base_weight = float(signal.get("weight", 8) or 8)

            # Matching exact symbol is stronger than matching name text
            symbol_match = any(k == token_symbol for k in matched_keywords)

            bonus = base_weight

            if symbol_match:
                bonus += 10

            if len(matched_keywords) >= 2:
                bonus += 5

            bonus = min(35, bonus)

            if bonus > best["score_bonus"]:
                best = {
                    "matched": True,
                    "score_bonus": bonus,
                    "matched_keywords": matched_keywords,
                    "matched_account": signal.get("account"),
                    "matched_signal": signal,
                    "reason": "social_catalyst_match",
                }

        return best