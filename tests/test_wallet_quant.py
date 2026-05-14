import unittest

from core.wallet_quant import build_wallet_quant_report, recommend_wallet_tier, wallet_quant_row


class WalletQuantTests(unittest.TestCase):
    def test_promotion_review_requires_sample_and_positive_evidence(self):
        row = wallet_quant_row(
            wallet="WalletA",
            performance={"paper_entries": 8, "wins": 6, "losses": 2, "total_pnl": 42.0},
            behavior={
                "labels": ["paper-profitable"],
                "rolling": {"7d": {"entries": 2}, "30d": {"expectancy": 5.25, "median_hold_seconds": 90}},
                "postmortem": {"avg_hold_seconds": 120, "failed_trades": 1},
                "signal_count": 12,
            },
            current_tier="paper_watch",
        )

        self.assertEqual(recommend_wallet_tier(row)["action"], "PROMOTION_REVIEW")
        self.assertEqual(row["signal_count"], 12)
        self.assertEqual(row["rolling_7d_entries"], 2)
        self.assertEqual(row["median_hold_seconds_30d"], 90)
        self.assertEqual(row["avg_hold_seconds"], 120)
        self.assertEqual(row["failed_trades"], 1)

    def test_demote_negative_wallet_with_sample(self):
        row = wallet_quant_row(
            wallet="WalletB",
            performance={"paper_entries": 7, "wins": 1, "losses": 6, "total_pnl": -28.0},
            behavior={"labels": ["late-exit"], "rolling": {"30d": {"expectancy": -4.0}}},
            current_tier="trusted",
        )

        self.assertEqual(recommend_wallet_tier(row)["action"], "DEMOTION_REVIEW")

    def test_hold_low_sample_wallet(self):
        row = wallet_quant_row(
            wallet="WalletC",
            performance={"paper_entries": 1, "wins": 1, "losses": 0, "total_pnl": 80.0},
            behavior={"labels": ["paper-profitable"]},
            current_tier="candidate",
        )

        self.assertEqual(recommend_wallet_tier(row)["action"], "HOLD_MORE_DATA")

    def test_build_report_groups_wallets_by_recommendation(self):
        report = build_wallet_quant_report(
            tracked_wallets=[{"trackedWalletAddress": "TrustedA"}],
            paper_watch_wallets=["WalletA", "WalletB"],
            performance={
                "wallets": {
                    "WalletA": {"paper_entries": 8, "wins": 6, "losses": 2, "total_pnl": 42.0},
                    "WalletB": {"paper_entries": 7, "wins": 1, "losses": 6, "total_pnl": -28.0},
                }
            },
            behavior={
                "wallets": {
                    "WalletA": {"rolling": {"30d": {"expectancy": 5.25}}},
                    "WalletB": {"rolling": {"30d": {"expectancy": -4.0}}},
                }
            },
        )

        self.assertEqual(report["counts"]["trusted"], 1)
        self.assertEqual(report["counts"]["paper_watch"], 2)
        self.assertEqual(report["recommendation_counts"]["PROMOTION_REVIEW"], 1)
        self.assertEqual(report["recommendation_counts"]["DEMOTION_REVIEW"], 1)


if __name__ == "__main__":
    unittest.main()
