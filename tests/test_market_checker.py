import unittest

from infra.market_checker import (
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
