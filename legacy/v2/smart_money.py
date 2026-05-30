import time
from collections import defaultdict


class SmartMoneyTracker:
    def __init__(self, window_seconds=90, alert_wallet_count=3):
        self.window_seconds = window_seconds
        self.alert_wallet_count = alert_wallet_count
        self.buys_by_mint = defaultdict(list)
        self.alerted_mints = set()

    def record_buy(self, mint, wallet):
        now = time.time()

        self.buys_by_mint[mint].append({
            "wallet": wallet,
            "time": now
        })

        # Keep only recent buys
        self.buys_by_mint[mint] = [
            item for item in self.buys_by_mint[mint]
            if now - item["time"] <= self.window_seconds
        ]

        unique_wallets = list({
            item["wallet"]
            for item in self.buys_by_mint[mint]
        })

        count = len(unique_wallets)

        if count >= self.alert_wallet_count and mint not in self.alerted_mints:
            self.alerted_mints.add(mint)
            return {
                "alert": True,
                "mint": mint,
                "wallet_count": count,
                "wallets": unique_wallets,
                "window_seconds": self.window_seconds
            }

        return {
            "alert": False,
            "mint": mint,
            "wallet_count": count,
            "wallets": unique_wallets,
            "window_seconds": self.window_seconds
        }