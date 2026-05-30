from dataclasses import dataclass, field
from time import time


@dataclass
class TokenScore:
    mint: str
    score: int = 0
    reasons: list = field(default_factory=list)
    first_seen: float = field(default_factory=time)
    tracked_buyers: set = field(default_factory=set)
    tracked_sellers: set = field(default_factory=set)
    liquidity: float = 0.0
    volume: float = 0.0


class TokenScorer:
    def __init__(self, sniper_threshold=60, safe_threshold=80):
        self.tokens = {}
        self.sniper_threshold = sniper_threshold
        self.safe_threshold = safe_threshold

    def get(self, mint):
        if mint not in self.tokens:
            self.tokens[mint] = TokenScore(mint=mint)
        return self.tokens[mint]

    def add_score(self, mint, points, reason):
        token = self.get(mint)
        token.score += points
        token.reasons.append(f"{points:+} {reason}")
        return token

    def score_market_data(self, mint, liquidity, volume):
        token = self.get(mint)

        liquidity = float(liquidity or 0)
        volume = float(volume or 0)

        token.liquidity = liquidity
        token.volume = volume

        if liquidity >= 20000:
            self.add_score(mint, 25, "strong liquidity")
        elif liquidity >= 10000:
            self.add_score(mint, 20, "good liquidity")
        elif liquidity >= 5000:
            self.add_score(mint, 15, "minimum liquidity passed")
        else:
            self.add_score(mint, -25, "low liquidity")

        if liquidity > 0:
            ratio = volume / liquidity

            if 0.3 <= ratio <= 3.0:
                self.add_score(mint, 15, "healthy volume/liquidity ratio")
            elif ratio > 5.0:
                self.add_score(mint, -15, "overheated volume")
            elif ratio < 0.1:
                self.add_score(mint, -10, "weak volume")

        return token

    def score_tracked_buy(self, mint, wallet_name, wallet_address):
        token = self.get(mint)

        if wallet_address in token.tracked_buyers:
            return token

        token.tracked_buyers.add(wallet_address)

        count = len(token.tracked_buyers)

        if count == 1:
            self.add_score(mint, 25, f"{wallet_name} bought")
        elif count == 2:
            self.add_score(mint, 20, f"second wallet {wallet_name}")
        else:
            self.add_score(mint, 15, f"extra wallet {wallet_name}")

        return token

    def score_tracked_sell(self, mint, wallet_name, wallet_address):
        token = self.get(mint)

        if wallet_address in token.tracked_sellers:
            return token

        token.tracked_sellers.add(wallet_address)
        self.add_score(mint, -30, f"{wallet_name} sold quickly")

        return token

    def is_sniper(self, mint):
        return self.get(mint).score >= self.sniper_threshold

    def is_safe(self, mint):
        return self.get(mint).score >= self.safe_threshold

    def print_score(self, mint):
        token = self.get(mint)

        print("\n🧠 SMART MONEY SCORE")
        print("MINT:", token.mint)
        print("SCORE:", token.score)
        print("BUYERS:", len(token.tracked_buyers))
        print("SELLERS:", len(token.tracked_sellers))

        for r in token.reasons[-6:]:
            print(" -", r)

        if self.is_safe(mint):
            print("🟢 SAFE SIGNAL")
        elif self.is_sniper(mint):
            print("🟡 SNIPER SIGNAL")
        else:
            print("⚪ No signal yet")