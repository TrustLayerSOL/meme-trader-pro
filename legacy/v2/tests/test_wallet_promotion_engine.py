import unittest

from wallets.wallet_promotion_engine import recommend_from_ledger_row


class WalletPromotionEngineTests(unittest.TestCase):
    def row(self, **overrides):
        base = {
            "wallet": "WalletA",
            "known_outcomes": 30,
            "runner_participation_rate": 0.4,
            "rug_participation_rate": 0.03,
            "average_pnl_after_signal": 18.5,
            "promotion_score": 40,
            "demotion_score": 2,
            "confidence": {"sample_quality": "usable", "known_outcome_rate": 0.75},
        }
        base.update(overrides)
        return base

    def test_thin_sample_blocks_promotion_review(self):
        recommendation = recommend_from_ledger_row(
            self.row(
                known_outcomes=8,
                runner_participation_rate=0.9,
                average_pnl_after_signal=120,
                promotion_score=150,
                confidence={"sample_quality": "thin", "known_outcome_rate": 1.0},
            )
        )

        self.assertTrue(recommendation["review_only"])
        self.assertEqual(recommendation["action"], "HOLD_MORE_DATA")
        self.assertIn("known outcome sample below 20", recommendation["reasons"][0])

    def test_positive_repeatable_evidence_routes_to_promotion_review(self):
        recommendation = recommend_from_ledger_row(self.row())

        self.assertTrue(recommendation["review_only"])
        self.assertEqual(recommendation["action"], "PROMOTION_REVIEW")
        self.assertIn("runner rate", " ".join(recommendation["reasons"]))

    def test_rug_heavy_or_negative_evidence_routes_to_demotion_review(self):
        recommendation = recommend_from_ledger_row(
            self.row(
                runner_participation_rate=0.05,
                rug_participation_rate=0.35,
                average_pnl_after_signal=-22,
                promotion_score=1,
                demotion_score=45,
            )
        )

        self.assertTrue(recommendation["review_only"])
        self.assertEqual(recommendation["action"], "DEMOTION_REVIEW")
        self.assertIn("rug participation", " ".join(recommendation["reasons"]))


if __name__ == "__main__":
    unittest.main()
