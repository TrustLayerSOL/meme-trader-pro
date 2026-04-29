import asyncio

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("⚡ uvloop enabled")
except ImportError:
    print("⚠️ uvloop not installed, using default asyncio")

import json

from infra.rpc_client import SolanaRPC
from paper_trader import PaperTrader
from infra.market_checker import MarketChecker
from execution.jupiter_quote import JupiterQuoteEngine
from core.runtime_status import update_component


def load_wallets():
    with open("data/tracked_wallets.json", "r") as f:
        data = json.load(f)
        return [w["trackedWalletAddress"] for w in data]


async def heartbeat(paper_trader, interval=30):
    while True:
        try:
            state = paper_trader.get_state()

            open_count = len(state.get("open_trades", []))
            closed_count = len(state.get("closed_trades", []))
            failed_count = len(state.get("failed_trades", []))

            print(
                f"💓 Bot alive | open: {open_count} | closed: {closed_count} | failed: {failed_count}"
            )

            update_component(
                "bot",
                status="alive",
                open_trades=open_count,
                closed_trades=closed_count,
                failed_trades=failed_count,
                heartbeat_interval=interval,
            )

            await asyncio.sleep(interval)

        except Exception as e:
            print("❌ Heartbeat error:", e)
            update_component("bot", status="heartbeat_error", last_error=str(e))
            await asyncio.sleep(interval)


async def main():
    tracked_wallets = load_wallets()
    print(f"✅ Loaded {len(tracked_wallets)} tracked wallets")
    update_component(
        "bot",
        status="starting",
        tracked_wallets=len(tracked_wallets),
    )

    paper_trader = PaperTrader()
    market_checker = MarketChecker()
    jupiter_quote = JupiterQuoteEngine()
    rpc = SolanaRPC(tracked_wallets)

    rpc.scanner.paper_trader = paper_trader
    rpc.market_checker = market_checker
    rpc.jupiter_quote = jupiter_quote

    try:
        await asyncio.gather(
            rpc.connect(),
            market_checker.run_price_loop(
                paper_trader=paper_trader,
                interval=1,
            ),
            heartbeat(paper_trader, interval=30),
        )

    finally:
        update_component("bot", status="stopping")

        if rpc.session:
            await rpc.session.close()

        if market_checker.session:
            await market_checker.session.close()

        await jupiter_quote.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped cleanly.")
