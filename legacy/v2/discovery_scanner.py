import time
import math
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class DiscoveryTokenState:
    mint: str
    first_seen_ts: float = field(default_factory=time.time)
    last_seen_ts: float = field(default_factory=time.time)

    tx_count: int = 0
    buy_count: int = 0
    sell_count: int = 0

    unique_buyers: set = field(default_factory=set)
    unique_sellers: set = field(default_factory=set)

    estimated_volume_usd: float = 0.0
    liquidity_usd: float = 0.0

    last_price: Optional[float] = None
    first_price: Optional[float] = None

    suspicious_flags: List[str] = field(default_factory=list)

    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.first_seen_ts)

    def tx_per_minute(self) -> float:
        age_min = max(self.age_seconds() / 60.0, 1.0)
        return self.tx_count / age_min

    def buyer_velocity(self) -> float:
        age_min = max(self.age_seconds() / 60.0, 1.0)
        return len(self.unique_buyers) / age_min

    def buy_sell_ratio(self) -> float:
        if self.sell_count <= 0:
            return float(self.buy_count)
        return self.buy_count / self.sell_count

    def price_change_pct(self) -> float:
        if not self.first_price or not self.last_price or self.first_price <= 0:
            return 0.0
        return ((self.last_price - self.first_price) / self.first_price) * 100.0


class DiscoveryScanner:
    """
    Lightweight market-wide discovery scanner.

    This module does NOT require a paid API.
    It is built to accept token events from scanner.py and score early-launch momentum.

    scanner.py can call:
        discovery.record_event(...)
        discovery.get_discovery_score(mint)
    """

    def __init__(
        self,
        max_token_age_seconds: int = 60 * 60,
        min_liquidity_usd: float = 1_000.0,
        min_tx_count: int = 3,
        min_unique_buyers: int = 2,
    ):
        self.tokens: Dict[str, DiscoveryTokenState] = {}

        self.max_token_age_seconds = max_token_age_seconds
        self.min_liquidity_usd = min_liquidity_usd
        self.min_tx_count = min_tx_count
        self.min_unique_buyers = min_unique_buyers

    def get_or_create(self, mint: str) -> DiscoveryTokenState:
        if mint not in self.tokens:
            self.tokens[mint] = DiscoveryTokenState(mint=mint)
        return self.tokens[mint]

    def record_event(
        self,
        mint: str,
        wallet: Optional[str] = None,
        side: Optional[str] = None,
        amount_usd: float = 0.0,
        liquidity_usd: float = 0.0,
        price: Optional[float] = None,
        suspicious_flags: Optional[List[str]] = None,
    ) -> None:
        """
        Records one observed token event.

        side:
            "buy"
            "sell"
            None / unknown
        """

        if not mint:
            return

        state = self.get_or_create(mint)
        state.last_seen_ts = time.time()
        state.tx_count += 1

        amount_usd = float(amount_usd or 0.0)
        liquidity_usd = float(liquidity_usd or 0.0)

        state.estimated_volume_usd += max(amount_usd, 0.0)
        state.liquidity_usd = max(state.liquidity_usd, liquidity_usd)

        if price is not None and price > 0:
            if state.first_price is None:
                state.first_price = price
            state.last_price = price

        if side == "buy":
            state.buy_count += 1
            if wallet:
                state.unique_buyers.add(wallet)

        elif side == "sell":
            state.sell_count += 1
            if wallet:
                state.unique_sellers.add(wallet)

        if suspicious_flags:
            for flag in suspicious_flags:
                if flag not in state.suspicious_flags:
                    state.suspicious_flags.append(flag)

    def score_volume(self, state: DiscoveryTokenState) -> float:
        volume = state.estimated_volume_usd

        if volume <= 0:
            return 0.0

        # Log scale so $2k matters early, but $100k does not dominate too hard.
        score = math.log10(volume + 1) / 5.0
        return min(score, 1.0)

    def score_liquidity(self, state: DiscoveryTokenState) -> float:
        liq = state.liquidity_usd

        if liq <= 0:
            return 0.0

        if liq < self.min_liquidity_usd:
            return 0.15

        # Strong early meme liquidity usually starts getting interesting above 5k-20k.
        score = math.log10(liq + 1) / 5.0
        return min(score, 1.0)

    def score_velocity(self, state: DiscoveryTokenState) -> float:
        txpm = state.tx_per_minute()

        if txpm <= 0:
            return 0.0

        # 1 tx/min = low, 10+ tx/min = strong early action.
        return min(txpm / 10.0, 1.0)

    def score_buyers(self, state: DiscoveryTokenState) -> float:
        buyers = len(state.unique_buyers)

        if buyers <= 0:
            return 0.0

        # 10 unique buyers early is meaningful.
        return min(buyers / 10.0, 1.0)

    def score_buy_pressure(self, state: DiscoveryTokenState) -> float:
        ratio = state.buy_sell_ratio()

        if state.buy_count <= 0:
            return 0.0

        if state.sell_count == 0 and state.buy_count >= 2:
            return 1.0

        # Ratio above 2 is good. Above 4 is very good.
        return min(ratio / 4.0, 1.0)

    def score_token_age(self, state: DiscoveryTokenState) -> float:
        age = state.age_seconds()

        if age <= 60:
            return 1.0
        if age <= 5 * 60:
            return 0.9
        if age <= 15 * 60:
            return 0.75
        if age <= 30 * 60:
            return 0.55
        if age <= 60 * 60:
            return 0.35

        return 0.1

    def score_price_momentum(self, state: DiscoveryTokenState) -> float:
        change = state.price_change_pct()

        if change <= 0:
            return 0.0

        # 100% early move is strong but not automatic all-in.
        return min(change / 100.0, 1.0)

    def risk_penalty(self, state: DiscoveryTokenState) -> float:
        penalty = 0.0

        age = state.age_seconds()

        if age > self.max_token_age_seconds:
            penalty += 0.35

        if state.liquidity_usd > 0 and state.liquidity_usd < self.min_liquidity_usd:
            penalty += 0.30

        if state.tx_count < self.min_tx_count:
            penalty += 0.20

        if len(state.unique_buyers) < self.min_unique_buyers:
            penalty += 0.20

        if state.sell_count > state.buy_count and state.sell_count >= 3:
            penalty += 0.25

        if state.suspicious_flags:
            penalty += min(0.50, 0.12 * len(state.suspicious_flags))

        return min(penalty, 0.85)

    def get_discovery_score(self, mint: str) -> Dict[str, Any]:
        if mint not in self.tokens:
            return {
                "mint": mint,
                "discovery_score": 0.0,
                "passed_discovery": False,
                "reason": "not_seen",
            }

        state = self.tokens[mint]

        volume_score = self.score_volume(state)
        liquidity_score = self.score_liquidity(state)
        velocity_score = self.score_velocity(state)
        buyers_score = self.score_buyers(state)
        buy_pressure_score = self.score_buy_pressure(state)
        age_score = self.score_token_age(state)
        price_momentum_score = self.score_price_momentum(state)

        raw_score = (
            volume_score * 0.18
            + liquidity_score * 0.17
            + velocity_score * 0.20
            + buyers_score * 0.18
            + buy_pressure_score * 0.12
            + age_score * 0.10
            + price_momentum_score * 0.05
        )

        penalty = self.risk_penalty(state)
        final_score = max(0.0, min(1.0, raw_score - penalty))

        passed = (
            final_score >= 0.55
            and state.tx_count >= self.min_tx_count
            and len(state.unique_buyers) >= self.min_unique_buyers
            and state.age_seconds() <= self.max_token_age_seconds
        )

        return {
            "mint": mint,
            "discovery_score": round(final_score, 4),
            "passed_discovery": passed,
            "age_seconds": round(state.age_seconds(), 2),
            "tx_count": state.tx_count,
            "buy_count": state.buy_count,
            "sell_count": state.sell_count,
            "unique_buyers": len(state.unique_buyers),
            "unique_sellers": len(state.unique_sellers),
            "tx_per_minute": round(state.tx_per_minute(), 3),
            "buyer_velocity": round(state.buyer_velocity(), 3),
            "buy_sell_ratio": round(state.buy_sell_ratio(), 3),
            "estimated_volume_usd": round(state.estimated_volume_usd, 2),
            "liquidity_usd": round(state.liquidity_usd, 2),
            "price_change_pct": round(state.price_change_pct(), 2),
            "suspicious_flags": state.suspicious_flags,
            "component_scores": {
                "volume": round(volume_score, 4),
                "liquidity": round(liquidity_score, 4),
                "velocity": round(velocity_score, 4),
                "buyers": round(buyers_score, 4),
                "buy_pressure": round(buy_pressure_score, 4),
                "age": round(age_score, 4),
                "price_momentum": round(price_momentum_score, 4),
                "risk_penalty": round(penalty, 4),
            },
        }

    def cleanup_old_tokens(self, older_than_seconds: int = 3 * 60 * 60) -> None:
        now = time.time()
        stale = [
            mint for mint, state in self.tokens.items()
            if now - state.last_seen_ts > older_than_seconds
        ]

        for mint in stale:
            del self.tokens[mint]

    def get_top_discoveries(self, limit: int = 20) -> List[Dict[str, Any]]:
        scored = [self.get_discovery_score(mint) for mint in self.tokens.keys()]
        scored.sort(key=lambda x: x.get("discovery_score", 0.0), reverse=True)
        return scored[:limit]