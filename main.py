import asyncio

import json
import os

from infra.rpc_client import SolanaRPC
from paper_trader import PaperTrader
from infra.market_checker import MarketChecker
from execution.jupiter_quote import JupiterQuoteEngine
from core.open_position_monitor import run_open_position_monitor
from core.runtime_status import update_component


def runtime_interval(name, default, minimum=0.2):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def configure_event_loop():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("⚡ uvloop enabled")
    except ImportError:
        print("⚠️ uvloop not installed, using default asyncio")


def load_wallets():
    with open("data/tracked_wallets.json", "r") as f:
        data = json.load(f)
        return [w["trackedWalletAddress"] for w in data]


def load_paper_watch_wallets():
    try:
        with open("data/paper_watch_wallets.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        return []

    rows = data.get("wallets") if isinstance(data, dict) else data
    wallets = []
    for row in rows or []:
        if isinstance(row, dict):
            wallet = row.get("wallet") or row.get("address") or row.get("trackedWalletAddress")
            if wallet and row.get("status", "paper_watch") != "demote_review":
                wallets.append(wallet)
        elif row:
            wallets.append(str(row))
    return list(dict.fromkeys(wallets))


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
                last_error=None,
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
    price_interval = runtime_interval("MEMETRADER_PRICE_INTERVAL_SECONDS", 1.0)
    tracked_wallets = load_wallets()
    paper_watch_wallets = load_paper_watch_wallets()
    print(f"✅ Loaded {len(tracked_wallets)} tracked wallets")
    print(f"🧪 Loaded {len(paper_watch_wallets)} paper-watch wallets")
    update_component(
        "bot",
        status="starting",
        tracked_wallets=len(tracked_wallets),
        paper_watch_wallets=len(paper_watch_wallets),
    )

    paper_trader = PaperTrader()
    market_checker = MarketChecker()
    jupiter_quote = JupiterQuoteEngine()
    rpc = SolanaRPC(
        tracked_wallets,
        paper_watch_wallets=paper_watch_wallets,
        paper_watch_loader=load_paper_watch_wallets,
    )

    rpc.scanner.paper_trader = paper_trader
    rpc.market_checker = market_checker
    rpc.jupiter_quote = jupiter_quote

    try:
        await asyncio.gather(
            rpc.connect(),
            run_open_position_monitor(
                paper_trader=paper_trader,
                market_checker=market_checker,
                interval=price_interval,
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
        configure_event_loop()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped cleanly.")
