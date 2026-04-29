import os
import time
import aiohttp

from dotenv import load_dotenv
from core.runtime_status import increment_component, update_component

load_dotenv()

SOL_MINT = "So11111111111111111111111111111111111111112"


class JupiterQuoteEngine:
    def __init__(self):
        self.api_key = os.getenv("JUPITER_API_KEY")
        self.base_url = "https://api.jup.ag/swap/v1/quote"
        self.session = None

        self.last_429_time = 0
        self.cooldown_seconds = 20
        self.cache = {}
        self.cache_ttl = 3

    async def init_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=4)
            connector = aiohttp.TCPConnector(
                limit=50,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def close(self):
        if self.session:
            await self.session.close()

    def is_cooling_down(self):
        return time.time() - self.last_429_time < self.cooldown_seconds

    def cache_key(self, input_mint, output_mint, amount_raw, slippage_bps):
        return f"{input_mint}:{output_mint}:{amount_raw}:{slippage_bps}"

    def get_cached(self, key):
        item = self.cache.get(key)
        if not item:
            return None

        if time.time() - item["time"] <= self.cache_ttl:
            return item["data"]

        return None

    def set_cached(self, key, data):
        self.cache[key] = {
            "time": time.time(),
            "data": data,
        }

    async def get_quote(
        self,
        input_mint,
        output_mint,
        amount_raw,
        slippage_bps=1500,
    ):
        if not self.api_key:
            update_component(
                "quotes",
                status="missing_api_key",
                last_input_mint=input_mint,
                last_output_mint=output_mint,
            )
            return {
                "ok": False,
                "reason": "missing_jupiter_api_key",
                "raw": None,
            }

        if self.is_cooling_down():
            update_component(
                "quotes",
                status="cooldown_after_429",
                last_input_mint=input_mint,
                last_output_mint=output_mint,
            )
            return {
                "ok": False,
                "reason": "jupiter_cooldown_after_429",
                "raw": None,
            }

        key = self.cache_key(input_mint, output_mint, amount_raw, slippage_bps)
        cached = self.get_cached(key)

        if cached:
            return cached

        try:
            await self.init_session()

            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(int(amount_raw)),
                "slippageBps": str(int(slippage_bps)),
                "swapMode": "ExactIn",
            }

            headers = {"x-api-key": self.api_key}

            async with self.session.get(
                self.base_url,
                headers=headers,
                params=params,
            ) as resp:
                if resp.status == 429:
                    self.last_429_time = time.time()
                    increment_component(
                        "quotes",
                        "http_429s",
                        status="http_429",
                        last_input_mint=input_mint,
                        last_output_mint=output_mint,
                    )

                    result = {
                        "ok": False,
                        "reason": "jupiter_http_429",
                        "raw": None,
                    }

                    self.set_cached(key, result)
                    return result

                if resp.status != 200:
                    text = await resp.text()
                    update_component(
                        "quotes",
                        status=f"http_{resp.status}",
                        last_input_mint=input_mint,
                        last_output_mint=output_mint,
                    )

                    result = {
                        "ok": False,
                        "reason": f"jupiter_http_{resp.status}",
                        "raw": text,
                    }

                    self.set_cached(key, result)
                    return result

                data = await resp.json()

                out_amount = int(data.get("outAmount") or 0)
                price_impact_pct = float(data.get("priceImpactPct") or 0)
                route_plan = data.get("routePlan", [])

                if out_amount <= 0:
                    result = {
                        "ok": False,
                        "reason": "no_output_amount",
                        "raw": data,
                    }

                    self.set_cached(key, result)
                    return result

                if not route_plan:
                    result = {
                        "ok": False,
                        "reason": "no_route_plan",
                        "raw": data,
                    }

                    self.set_cached(key, result)
                    return result

                result = {
                    "ok": True,
                    "reason": "quote_ok",
                    "input_mint": input_mint,
                    "output_mint": output_mint,
                    "in_amount_raw": int(amount_raw),
                    "out_amount": out_amount,
                    "price_impact_pct": price_impact_pct,
                    "route_count": len(route_plan),
                    "route_plan": route_plan,
                    "raw": data,
                }

                self.set_cached(key, result)
                increment_component(
                    "quotes",
                    "successful_quotes",
                    status="quote_ok",
                    last_input_mint=input_mint,
                    last_output_mint=output_mint,
                    last_price_impact_pct=price_impact_pct,
                )
                return result

        except Exception as e:
            update_component(
                "quotes",
                status="quote_exception",
                last_error=str(e),
                last_input_mint=input_mint,
                last_output_mint=output_mint,
            )
            return {
                "ok": False,
                "reason": f"quote_exception: {e}",
                "raw": None,
            }

    async def get_buy_quote(
        self,
        output_mint,
        sol_amount=0.1,
        slippage_bps=1500,
    ):
        lamports = int(float(sol_amount) * 1_000_000_000)

        return await self.get_quote(
            input_mint=SOL_MINT,
            output_mint=output_mint,
            amount_raw=lamports,
            slippage_bps=slippage_bps,
        )

    async def get_sell_quote(
        self,
        input_mint,
        token_amount_raw,
        slippage_bps=2000,
    ):
        return await self.get_quote(
            input_mint=input_mint,
            output_mint=SOL_MINT,
            amount_raw=int(token_amount_raw),
            slippage_bps=slippage_bps,
        )

    def analyze_quote(self, quote, max_price_impact_pct=8):
        if not quote or not quote.get("ok"):
            return {
                "pass": False,
                "reason": quote.get("reason", "quote_failed") if quote else "quote_missing",
                "price_impact_pct": None,
            }

        price_impact_pct = float(quote.get("price_impact_pct") or 0)

        if price_impact_pct > float(max_price_impact_pct):
            return {
                "pass": False,
                "reason": f"price_impact_too_high_{price_impact_pct}",
                "price_impact_pct": price_impact_pct,
            }

        return {
            "pass": True,
            "reason": "quote_passed",
            "price_impact_pct": price_impact_pct,
        }
