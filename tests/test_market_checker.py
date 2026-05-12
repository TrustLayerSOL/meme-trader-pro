import unittest
from unittest import mock

import time

from infra.market_checker import (
    MarketChecker,
    estimate_pump_market_cap,
    extract_dexscreener_pair_metadata,
    merge_market_info,
    needs_dexscreener_enrichment,
)


class MarketCheckerMetadataTests(unittest.TestCase):
    def test_extracts_image_links_and_transaction_counts(self):
        pair = {
            "info": {
                "imageUrl": "https://example.test/token.png",
                "websites": [{"url": "https://project.test"}],
                "socials": [{"type": "twitter", "url": "https://x.com/project"}],
            },
            "txns": {
                "m5": {"buys": 7, "sells": 5},
                "h1": {"buys": 20, "sells": 8},
            },
        }

        metadata = extract_dexscreener_pair_metadata(pair)

        self.assertEqual(metadata["image_url"], "https://example.test/token.png")
        self.assertEqual(metadata["website"], "https://project.test")
        self.assertEqual(metadata["twitter"], "https://x.com/project")
        self.assertEqual(metadata["tx_count"], 12)
        self.assertEqual(metadata["buy_count"], 7)
        self.assertEqual(metadata["sell_count"], 5)

    def test_jupiter_price_info_needs_enrichment_when_display_metadata_is_missing(self):
        info = {
            "source": "jupiter",
            "price": 0.0000067,
            "liquidity": 4200,
            "name": None,
            "symbol": None,
            "image_url": None,
            "market_cap": None,
            "tx_count": None,
        }

        self.assertTrue(needs_dexscreener_enrichment(info))

    def test_merge_keeps_jupiter_price_but_adds_dexscreener_display_metadata(self):
        primary = {
            "source": "jupiter",
            "price": 0.0000067,
            "liquidity": 4200,
            "name": None,
            "symbol": None,
            "image_url": None,
            "market_cap": None,
        }
        enrichment = {
            "source": "dexscreener",
            "price": 0.0000065,
            "liquidity": 4300,
            "name": "Launch Coin",
            "symbol": "LAUNCH",
            "image_url": "https://example.test/launch.png",
            "market_cap": 6700,
            "tx_count": 17,
            "url": "https://dexscreener.test/launch",
        }

        merged = merge_market_info(primary, enrichment)

        self.assertEqual(merged["source"], "jupiter+dexscreener")
        self.assertEqual(merged["price"], 0.0000067)
        self.assertEqual(merged["liquidity"], 4200)
        self.assertEqual(merged["name"], "Launch Coin")
        self.assertEqual(merged["symbol"], "LAUNCH")
        self.assertEqual(merged["image_url"], "https://example.test/launch.png")
        self.assertEqual(merged["market_cap"], 6700)
        self.assertEqual(merged["tx_count"], 17)

    def test_merge_replaces_missing_zero_liquidity_and_volume_from_dexscreener(self):
        primary = {
            "source": "jupiter",
            "price": 0.0000067,
            "liquidity": 0,
            "volume": 0,
        }
        enrichment = {
            "source": "dexscreener",
            "price": 0.0000065,
            "liquidity": 200000,
            "volume": 50000,
        }

        merged = merge_market_info(primary, enrichment)

        self.assertEqual(merged["price"], 0.0000067)
        self.assertEqual(merged["liquidity"], 200000)
        self.assertEqual(merged["volume"], 50000)

    def test_estimates_pump_market_cap_when_supply_window_is_standard(self):
        self.assertEqual(
            estimate_pump_market_cap("Mint111111111111111111111111111111111pump", 0.0000067),
            6700,
        )


class MarketCheckerPressureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.increment_patch = mock.patch("infra.market_checker.increment_component")
        self.update_patch = mock.patch("infra.market_checker.update_component")
        self.increment_patch.start()
        self.update_patch.start()

    async def asyncTearDown(self):
        self.update_patch.stop()
        self.increment_patch.stop()

    async def test_jupiter_price_429_starts_cooldown(self):
        class FakeResponse:
            status = 429

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        checker = MarketChecker()
        checker.jupiter_api_key = "test-key"
        checker.session = FakeSession()

        info = await checker.get_jupiter_price("Mint429")

        self.assertIsNone(info)
        self.assertTrue(checker.jupiter_price_cooling_down())

    async def test_dexscreener_429_starts_cooldown(self):
        class FakeResponse:
            status = 429

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        checker = MarketChecker()
        checker.session = FakeSession()

        info = await checker.get_dexscreener_info("Mint429")

        self.assertIsNone(info)
        self.assertTrue(checker.dexscreener_cooling_down())

    async def test_get_token_info_avoids_external_calls_when_price_sources_are_cooling_down(self):
        class FakeChecker(MarketChecker):
            def __init__(self):
                super().__init__()
                self.jupiter_calls = 0
                self.dex_calls = 0

            async def get_jupiter_price(self, mint):
                self.jupiter_calls += 1
                return {"source": "jupiter", "price": 1.0, "liquidity": 1000}

            async def get_dexscreener_info(self, mint):
                self.dex_calls += 1
                return {"source": "dexscreener", "price": 1.1, "liquidity": 2000}

        checker = FakeChecker()
        checker.last_jupiter_429_time = time.time()
        checker.last_dexscreener_429_time = time.time()

        info = await checker.get_token_info("MintBothLimited")

        self.assertIsNone(info)
        self.assertEqual(checker.jupiter_calls, 0)
        self.assertEqual(checker.dex_calls, 0)

    async def test_get_token_info_uses_dexscreener_while_jupiter_price_is_cooling_down(self):
        class FakeChecker(MarketChecker):
            def __init__(self):
                super().__init__()
                self.jupiter_calls = 0
                self.dex_calls = 0

            async def get_jupiter_price(self, mint):
                self.jupiter_calls += 1
                return {"source": "jupiter", "price": 1.0, "liquidity": 1000}

            async def get_dexscreener_info(self, mint):
                self.dex_calls += 1
                return {"source": "dexscreener", "price": 1.1, "liquidity": 2000}

        checker = FakeChecker()
        checker.last_jupiter_429_time = time.time()

        info = await checker.get_token_info("MintRateLimited")

        self.assertEqual(info["source"], "dexscreener")
        self.assertEqual(checker.jupiter_calls, 0)
        self.assertEqual(checker.dex_calls, 1)

    async def test_get_token_info_reuses_cached_market_info_across_fast_monitor_ticks(self):
        class FakeChecker(MarketChecker):
            def __init__(self):
                super().__init__()
                self.cache_ttl = 30
                self.jupiter_calls = 0
                self.dex_calls = 0

            async def get_jupiter_price(self, mint):
                self.jupiter_calls += 1
                return {
                    "source": "jupiter",
                    "price": 1.0,
                    "liquidity": 1000,
                    "name": "Cached Token",
                    "symbol": "CACHE",
                    "image_url": "https://example.test/cache.png",
                    "market_cap": 100000,
                    "tx_count": 12,
                }

            async def get_dexscreener_info(self, mint):
                self.dex_calls += 1
                return None

        checker = FakeChecker()

        first = await checker.get_token_info("MintCached")
        second = await checker.get_token_info("MintCached")

        self.assertEqual(first, second)
        self.assertEqual(checker.jupiter_calls, 1)
        self.assertEqual(checker.dex_calls, 0)
