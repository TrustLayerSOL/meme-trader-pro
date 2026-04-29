import aiohttp
import asyncio
import os

from dotenv import load_dotenv
from core.runtime_status import increment_component, update_component

load_dotenv()


class MarketChecker:
    def __init__(self):
        self.jupiter_api_key = os.getenv("JUPITER_API_KEY")
        self.jupiter_price_url = "https://api.jup.ag/price/v3"
        self.dex_url = "https://api.dexscreener.com/latest/dex/tokens/"
        self.session = None
        self.cache = {}
        self.cache_ttl = 1.0

    async def init_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=4)
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    def cached(self, mint):
        item = self.cache.get(mint)
        if not item:
            return None

        age = asyncio.get_event_loop().time() - item["time"]
        if age <= self.cache_ttl:
            return item["data"]

        return None

    def store_cache(self, mint, data):
        self.cache[mint] = {
            "time": asyncio.get_event_loop().time(),
            "data": data,
        }

    async def get_jupiter_price(self, mint):
        if not self.jupiter_api_key:
            return None

        try:
            await self.init_session()

            headers = {"x-api-key": self.jupiter_api_key}
            params = {"ids": mint}

            async with self.session.get(
                self.jupiter_price_url,
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    update_component(
                        "market",
                        jupiter_price_status=resp.status,
                        last_price_source="jupiter",
                    )
                    return None

                data = await resp.json()
                item = data.get(mint)

                if not item:
                    return None

                price = float(item.get("usdPrice") or 0)
                liquidity = float(item.get("liquidity") or 0)

                if price <= 0:
                    return None

                increment_component(
                    "market",
                    "jupiter_price_successes",
                    last_price_source="jupiter",
                    last_price_mint=mint,
                )

                return {
                    "source": "jupiter",
                    "name": None,
                    "symbol": None,
                    "price": price,
                    "liquidity": liquidity,
                    "volume": 0,
                    "block_id": item.get("blockId"),
                    "decimals": item.get("decimals"),
                    "price_change_24h": item.get("priceChange24h"),
                    "pair_address": None,
                    "dex": None,
                    "url": None,
                }

        except Exception as e:
            print("❌ Jupiter price error:", e)
            return None

    async def get_dexscreener_info(self, mint):
        try:
            await self.init_session()

            async with self.session.get(self.dex_url + mint) as resp:
                if resp.status != 200:
                    update_component(
                        "market",
                        dexscreener_status=resp.status,
                        last_price_source="dexscreener",
                    )
                    return None

                data = await resp.json()
                pairs = data.get("pairs")

                if not pairs:
                    return None

                sol_pairs = [
                    p for p in pairs
                    if p.get("chainId") == "solana"
                ]

                if not sol_pairs:
                    return None

                best_pair = max(
                    sol_pairs,
                    key=lambda p: float(p.get("liquidity", {}).get("usd") or 0)
                )

                price = float(best_pair.get("priceUsd") or 0)
                liquidity = float(best_pair.get("liquidity", {}).get("usd") or 0)
                volume = float(best_pair.get("volume", {}).get("h24") or 0)

                if price <= 0:
                    return None

                increment_component(
                    "market",
                    "dexscreener_successes",
                    last_price_source="dexscreener",
                    last_price_mint=mint,
                )

                return {
                    "source": "dexscreener",
                    "name": best_pair.get("baseToken", {}).get("name"),
                    "symbol": best_pair.get("baseToken", {}).get("symbol"),
                    "price": price,
                    "liquidity": liquidity,
                    "market_cap": best_pair.get("marketCap"),
                    "fdv": best_pair.get("fdv"),
                    "volume": volume,
                    "block_id": None,
                    "decimals": None,
                    "price_change_24h": None,
                    "pair_address": best_pair.get("pairAddress"),
                    "dex": best_pair.get("dexId"),
                    "url": best_pair.get("url"),
                }

        except Exception as e:
            print("❌ Dexscreener fetch error:", e)
            return None

    async def get_token_info(self, mint):
        cached = self.cached(mint)
        if cached:
            return cached

        # Primary: Jupiter
        info = await self.get_jupiter_price(mint)

        # Fallback: Dexscreener
        if not info:
            info = await self.get_dexscreener_info(mint)

        if info:
            self.store_cache(mint, info)

        return info

    def liquidity_score(self, liquidity):
        liquidity = float(liquidity or 0)

        if liquidity >= 100000:
            return 90
        elif liquidity >= 50000:
            return 70
        elif liquidity >= 20000:
            return 55
        elif liquidity >= 10000:
            return 40
        elif liquidity > 0:
            return 20
        return 0

    def volume_score(self, volume):
        volume = float(volume or 0)

        if volume >= 500000:
            return 90
        elif volume >= 200000:
            return 70
        elif volume >= 50000:
            return 50
        elif volume >= 10000:
            return 30
        elif volume > 0:
            return 15
        return 0

    async def run_price_loop(self, paper_trader, interval=1):
        print(f"📡 Market price loop started ({interval}s)")
        update_component("market", status="price_loop_started", interval=interval)

        while True:
            try:
                open_trades = paper_trader.get_state().get("open_trades", [])
                update_component(
                    "market",
                    status="price_loop_alive",
                    open_trades=len(open_trades),
                )

                if not open_trades:
                    await asyncio.sleep(interval)
                    continue

                tasks = []
                mints = []

                for trade in list(open_trades):
                    mint = trade.get("mint")
                    if mint:
                        mints.append(mint)
                        tasks.append(self.get_token_info(mint))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for mint, info in zip(mints, results):
                    if isinstance(info, Exception) or not info:
                        continue

                    price = float(info.get("price") or 0)
                    liquidity = float(info.get("liquidity") or 10000)

                    if price <= 0:
                        continue

                    paper_trader.update_price(
                        mint=mint,
                        price=price,
                        liquidity_usd=liquidity,
                        market_info=info,
                    )

                await asyncio.sleep(interval)

            except Exception as e:
                print("❌ Price loop error:", e)
                update_component("market", status="price_loop_error", last_error=str(e))
                await asyncio.sleep(interval)
