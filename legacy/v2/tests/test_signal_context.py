import unittest

from core.signal_context import build_signal_context, classify_market_regime


class SignalContextTests(unittest.TestCase):
    def test_builds_replayable_context_from_scanner_payload(self):
        payload = {
            "mint": "MintA",
            "type": "wallet_cluster",
            "timestamp": 123.0,
            "wallets": ["WalletA", "WalletB"],
            "cluster_start_time": 100.0,
            "cluster_end_time": 112.0,
            "market_info": {
                "liquidity": 18_000,
                "market_cap": 75_000,
                "price": 0.00012,
                "volume": 42_000,
                "buy_velocity": 9,
                "pair_age_seconds": 55,
            },
            "holder_concentration_risk": "LOW",
            "estimated_slippage_pct": 2.4,
            "wallet_performance": {
                "wallet_scores": [
                    {"wallet": "WalletA", "score": 88, "label": "GOOD_PERFORMER"},
                    {"wallet": "WalletB", "score": 61, "label": "NEUTRAL_PERFORMER"},
                ]
            },
            "score_reasons": ["wallet cluster", "liquidity ok"],
        }

        ctx = build_signal_context(payload, decision={"paper_lane": "main"}, source="scanner")

        self.assertEqual(ctx["mint"], "MintA")
        self.assertEqual(ctx["source"], "scanner")
        self.assertEqual(ctx["triggering_wallets"][0]["wallet"], "WalletA")
        self.assertEqual(ctx["cluster"]["duration_seconds"], 12.0)
        self.assertEqual(ctx["market"]["liquidity"], 18_000)
        self.assertEqual(ctx["market"]["token_age_seconds"], 55)
        self.assertEqual(ctx["execution_assumptions"]["estimated_slippage_pct"], 2.4)
        self.assertIn("strong_runner_environment", ctx["market_regime"]["tags"])

    def test_classifies_low_liquidity_and_rug_heavy_context(self):
        regime = classify_market_regime(
            {
                "market": {"liquidity": 900, "volume": 150, "price_change_pct": -44},
                "risk": {"hard_block": True, "holder_concentration_risk": "DANGER"},
            }
        )

        self.assertIn("low_liquidity_market", regime["tags"])
        self.assertIn("rug_heavy_environment", regime["tags"])
        self.assertIn("high_volatility", regime["tags"])


if __name__ == "__main__":
    unittest.main()
