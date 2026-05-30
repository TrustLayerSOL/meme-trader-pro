import argparse
import asyncio
import json


# BONK mint - used only because Dexscreener should usually have price data for it
TEST_MINT = "DezXAZ8z7PnrnRJjz3B9Vbbd3PpbVhZwz1ngeUbcDg2n"


def load_wallets():
    with open("data/tracked_wallets.json", "r") as f:
        data = json.load(f)
        return [w["trackedWalletAddress"] for w in data]


class MockRPC:
    def __init__(self):
        from infra.market_checker import MarketChecker

        self.market_checker = MarketChecker()

    async def rpc_call(self, method, params):
        return None

    async def get_transaction(self, signature):
        return None


class MockDevAnalyzer:
    def score_dev(self, dev_wallet):
        return {
            "score": 50,
            "label": "Test Dev",
            "reasons": ["Forced test dev score"]
        }


async def main():
    parser = argparse.ArgumentParser(description="Force a scanner cluster event for manual testing.")
    parser.add_argument(
        "--write-real-state",
        action="store_true",
        help="Allow writes to the project runtime state. Default uses temporary paper-trade state.",
    )
    args = parser.parse_args()

    if not args.write_real_state:
        print("Safe mode: no runtime files or live services will be touched.")
        print("Use --write-real-state to run this manual scanner exercise.")
        return

    from core.scanner import Scanner
    from paper_trader import PaperTrader

    wallets = load_wallets()

    if len(wallets) < 3:
        print("Need at least 3 tracked wallets for cluster test.")
        return

    rpc = MockRPC()
    try:
        scanner = Scanner(wallets, rpc)

        scanner.paper_trader = PaperTrader()
        scanner.dev_analyzer = MockDevAnalyzer()

        scanner.cluster_threshold = 3
        scanner.cluster_window = 90

        print("FORCING TEST CLUSTER")
        print("TEST MINT:", TEST_MINT)

        test_wallets = wallets[:3]

        for wallet in test_wallets:
            event = {
                "wallet": wallet,
                "mint": TEST_MINT,
                "delta": 1000000
            }

            await scanner.process_event(event)
            await asyncio.sleep(0.5)

        print("Forced test complete.")
        print("Check data/paper_trades.json and dashboard.")
    finally:
        session = getattr(rpc.market_checker, "session", None)
        if session:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
