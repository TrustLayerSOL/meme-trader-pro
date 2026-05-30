import hashlib
import json
import os
import re
import time

from core.json_store import atomic_write_json, locked_update_json


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
    def __init__(self, state_file=SOCIAL_STATE_FILE):
        self.state_file = state_file
        self.state = self.load_state()

    def load_state(self):
        if not os.path.exists(self.state_file):
            return {"events": []}

        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception:
            return {"events": []}

    def save_state(self):
        self.state["last_updated"] = time.time()
        atomic_write_json(self.state_file, self.state)

    def signal_rows(self):
        rows = []
        seen = set()
        for key in ("events", "signals"):
            source_rows = self.state.get(key, [])
            if not isinstance(source_rows, list):
                continue
            for signal in source_rows:
                if not isinstance(signal, dict):
                    continue
                row_key = signal.get("event_id") or (
                    signal.get("account"),
                    signal.get("timestamp"),
                    self.clean_text(signal.get("text", "")).lower(),
                )
                if row_key in seen:
                    continue
                seen.add(row_key)
                rows.append(signal)
        return rows

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

    def infer_account_category(self, account):
        account = str(account or "").lower().replace("@", "")
        if account in HIGH_IMPACT_ACCOUNTS:
            return "high_impact"
        if account in ["cz", "aeyakovenko", "solana", "pumpdotfun"]:
            return "crypto_kol"
        return "watchlist"

    def score_sentiment(self, text):
        text = str(text or "").lower()
        bullish = [
            "buy", "bought", "send", "sending", "moon", "based", "breakout",
            "runner", "cult", "cto", "backed", "partnership", "launch",
        ]
        bearish = [
            "rug", "scam", "drain", "sell", "dump", "avoid", "fake",
            "honeypot", "exploit", "warning", "danger",
        ]
        score = 0
        score += sum(1 for word in bullish if word in text)
        score -= sum(1 for word in bearish if word in text)
        if score > 0:
            return "bullish"
        if score < 0:
            return "bearish"
        return "neutral"

    def extract_tickers(self, text):
        tickers = []
        for match in re.findall(r"\$([A-Za-z][A-Za-z0-9_]{1,12})", str(text or "")):
            value = match.lower()
            if value not in tickers:
                tickers.append(value)
        return tickers[:12]

    def extract_mints(self, text):
        mints = []
        for match in re.findall(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", str(text or "")):
            if match not in mints:
                mints.append(match)
        return mints[:12]

    def social_event_id(self, account, text, timestamp):
        cleaned = self.clean_text(text).lower()
        account_key = str(account or "").lower().replace("@", "")
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
        return f"{account_key}:{int(float(timestamp or 0))}:{digest}"

    def build_signal(
        self,
        account,
        text,
        url=None,
        source_platform="x",
        timestamp=None,
        engagement=None,
        raw=None,
        expires_hours=6,
    ):
        account = str(account or "").lower().replace("@", "")
        now = time.time()
        event_time = float(timestamp or now)

        return {
            "event_id": self.social_event_id(account, text, event_time),
            "source_platform": source_platform,
            "account": account,
            "account_category": self.infer_account_category(account),
            "text": text,
            "keywords": self.extract_keywords(text),
            "tickers": self.extract_tickers(text),
            "mints": self.extract_mints(text),
            "sentiment": self.score_sentiment(text),
            "weight": self.account_weight(account),
            "url": url,
            "timestamp": event_time,
            "discovered_at": now,
            "expires_at": now + (float(expires_hours or 6) * 60 * 60),
            "engagement": engagement or {},
            "raw": raw or {},
        }

    def add_signal(
        self,
        account,
        text,
        url=None,
        source_platform="x",
        timestamp=None,
        engagement=None,
        raw=None,
        expires_hours=6,
    ):
        signal = self.build_signal(
            account=account,
            text=text,
            url=url,
            source_platform=source_platform,
            timestamp=timestamp,
            engagement=engagement,
            raw=raw,
            expires_hours=expires_hours,
        )

        self.state.setdefault("events", [])
        self.state["events"].insert(0, signal)

        # Keep recent 500 social signals only
        self.state["events"] = self.dedupe_signals(self.state["events"])[:500]
        self.state.pop("signals", None)

        self.save_state()

        return signal

    def dedupe_signals(self, signals):
        seen = set()
        cleaned = []
        for signal in signals or []:
            if not isinstance(signal, dict):
                continue
            key = signal.get("event_id") or (
                signal.get("account"),
                signal.get("timestamp"),
                self.clean_text(signal.get("text", "")).lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(signal)
        return cleaned

    def import_text_block(self, text, default_account="manual", source_platform="x"):
        imported = []
        for line in str(text or "").splitlines():
            line = line.strip()
            if not line:
                continue

            account = default_account
            body = line
            url = None

            if "|" in line:
                parts = [part.strip() for part in line.split("|")]
                if len(parts) >= 2:
                    account = parts[0].replace("@", "") or default_account
                    body = parts[1]
                    if len(parts) >= 3:
                        url = parts[2] or None
            elif line.startswith("@") and ":" in line:
                left, right = line.split(":", 1)
                account = left.replace("@", "").strip() or default_account
                body = right.strip()

            imported.append(self.build_signal(
                account=account,
                text=body,
                url=url,
                source_platform=source_platform,
            ))

        if imported:
            def updater(state):
                if not isinstance(state, dict):
                    state = {"events": []}
                events = state.get("events", [])
                if not isinstance(events, list):
                    events = state.get("signals") if isinstance(state.get("signals"), list) else []
                state["events"] = self.dedupe_signals(imported + events)[:500]
                state.pop("signals", None)
                state["last_updated"] = time.time()
                return state

            self.state = locked_update_json(self.state_file, {"events": []}, updater)

        return imported

    def safe_float(self, value, default=0):
        try:
            if value in [None, ""]:
                return default
            return float(value)
        except Exception:
            return default

    def get_active_signals(self):
        now = time.time()

        signals = []
        for signal in self.signal_rows():
            if not isinstance(signal, dict):
                continue
            if self.safe_float(signal.get("expires_at"), 0) > now:
                signals.append(signal)

        return signals

    def signal_summary(self):
        signals = self.signal_rows()
        active = self.get_active_signals()
        accounts = {}
        sentiments = {"bullish": 0, "bearish": 0, "neutral": 0}
        keywords = {}

        for signal in signals:
            account = signal.get("account") or "unknown"
            accounts[account] = accounts.get(account, 0) + 1
            sentiment = signal.get("sentiment") or "neutral"
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
            for keyword in signal.get("keywords", []):
                keywords[keyword] = keywords.get(keyword, 0) + 1

        return {
            "total": len(signals),
            "active": len(active),
            "accounts": accounts,
            "sentiments": sentiments,
            "keywords": keywords,
            "last_updated": self.state.get("last_updated"),
        }

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
        active = self.get_active_signals()
        token_mint = str(mint or "")

        for signal in active:
            if token_mint and token_mint in signal.get("mints", []):
                return {
                    "matched": True,
                    "score_bonus": min(35, self.safe_float(signal.get("weight"), 8) + 15),
                    "matched_keywords": [token_mint],
                    "matched_account": signal.get("account"),
                    "matched_signal": signal,
                    "reason": "social_exact_mint_match",
                }

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

        for signal in active:
            keywords = list(signal.get("keywords", [])) + list(signal.get("tickers", []))
            matched_keywords = []
            token_mint = str(mint or "")

            if token_mint and token_mint in signal.get("mints", []):
                matched_keywords.append(token_mint)

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
