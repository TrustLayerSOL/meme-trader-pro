import unittest

from research.outcome_labeler import label_later_token_outcome


class OutcomeLabelerTests(unittest.TestCase):
    def test_runner_label_from_profit_and_high_watermark(self):
        labeled = label_later_token_outcome(
            trade={
                "status": "closed",
                "entry_price": 0.01,
                "highest_price_seen": 0.021,
                "close_price": 0.015,
                "total_pnl_pct": 50,
            }
        )

        self.assertEqual(labeled["outcome_type"], "runner")
        self.assertTrue(labeled["runner"])
        self.assertFalse(labeled["rug"])
        self.assertGreaterEqual(labeled["max_favorable_excursion_pct"], 100)
        self.assertIn("profit exceeded runner threshold", labeled["classification_reasons"])

    def test_rug_label_from_liquidity_collapse(self):
        labeled = label_later_token_outcome(
            outcome={
                "status": "closed",
                "pnl_pct": -86,
                "entry_liquidity_usd": 20_000,
                "exit_liquidity_usd": 2_000,
                "close_reason": "liquidity drained by developer",
            }
        )

        self.assertEqual(labeled["outcome_type"], "rug")
        self.assertTrue(labeled["rug"])
        self.assertFalse(labeled["runner"])
        self.assertEqual(labeled["label_confidence"], "high")
        self.assertLessEqual(labeled["liquidity_change_pct"], -85)
        self.assertIn("liquidity collapse exceeded rug threshold", labeled["classification_reasons"])

    def test_open_trade_is_not_counted_as_known_outcome(self):
        labeled = label_later_token_outcome(
            trade={
                "status": "open",
                "entry_price": 0.01,
                "current_price": 0.011,
            }
        )

        self.assertEqual(labeled["outcome_type"], "open")
        self.assertFalse(labeled["runner"])
        self.assertFalse(labeled["rug"])
        self.assertFalse(labeled["dead"])
        self.assertEqual(labeled["label_confidence"], "low")


if __name__ == "__main__":
    unittest.main()
