import unittest

from core.replay_visibility import build_replay_visibility_report


class ReplayVisibilityTests(unittest.TestCase):
    def test_report_exposes_rejection_context_for_review(self):
        rows = [
            {
                "decision_id": "dec-1",
                "mint": "MintA",
                "source": "scanner",
                "lane": "main",
                "rejection reason": "weak wallet score",
                "signal context": {
                    "mint": "MintA",
                    "triggering_wallets": [{"wallet": "WalletA", "score": 42}],
                    "cluster": {"wallet_count": 1, "duration_seconds": 33},
                    "market": {"liquidity": 3_400, "market_cap": 16_000, "token_age_seconds": 61},
                    "execution_assumptions": {"estimated_slippage_pct": 7.5},
                    "market_regime": {"tags": ["low_liquidity_market"]},
                    "risk": {"holder_concentration_risk": "MEDIUM"},
                },
                "what would have happened afterward if traded": {"status": "unknown"},
            }
        ]

        report = build_replay_visibility_report(rows)

        self.assertEqual(report["mode"], "REPLAY_VISIBILITY_REVIEW_ONLY")
        self.assertEqual(report["counts"]["records"], 1)
        item = report["records"][0]
        self.assertEqual(item["trigger"]["wallets"][0]["wallet"], "WalletA")
        self.assertEqual(item["market"]["liquidity"], 3_400)
        self.assertEqual(item["execution"]["estimated_slippage_pct"], 7.5)
        self.assertIn("low_liquidity_market", item["market_regime"]["tags"])
        self.assertIn("no perfect fills", item["replay_notes"][0])


if __name__ == "__main__":
    unittest.main()
