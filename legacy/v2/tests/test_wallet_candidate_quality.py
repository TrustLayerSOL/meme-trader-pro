import tempfile
import unittest
from pathlib import Path

from wallets.wallet_candidate_quality import build_wallet_candidate_quality_report
from utils.build_wallet_candidate_quality_report import write_wallet_candidate_quality_report


class WalletCandidateQualityReportTests(unittest.TestCase):
    def test_report_ranks_fresh_repeat_runner_above_sell_heavy_stale_candidate(self):
        report = build_wallet_candidate_quality_report(
            candidate_wallets={
                "generated_at": 2_000,
                "summary": {"candidate_wallets": 2},
                "candidates": [
                    {
                        "wallet": "WalletFreshRunner",
                        "score": 72,
                        "review": {"action": "PAPER_WATCH"},
                        "winner_mints": 3,
                        "early_buy_events": 12,
                        "unique_mints": 5,
                        "buy_events": 12,
                        "sell_events": 1,
                        "last_seen": 1_900,
                    },
                    {
                        "wallet": "WalletStaleSeller",
                        "score": 80,
                        "review": {"action": "HOLD_REVIEW"},
                        "winner_mints": 1,
                        "early_buy_events": 2,
                        "unique_mints": 3,
                        "buy_events": 3,
                        "sell_events": 8,
                        "last_seen": 800,
                    },
                ],
            },
            paper_watch_wallets={"wallets": []},
            bad_wallets=[],
            wallet_behavior={"wallets": {}},
            generated_at=2_000,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY")
        self.assertEqual(report["summary"]["active_candidates"], 2)
        self.assertEqual(report["summary"]["blocked_candidates"], 0)
        self.assertEqual(report["ranked_candidates"][0]["wallet"], "WalletFreshRunner")
        self.assertGreater(
            report["ranked_candidates"][0]["quality_score"],
            report["ranked_candidates"][1]["quality_score"],
        )
        self.assertIn("repeat runner overlap", report["ranked_candidates"][0]["reasons"])
        self.assertIn("sell-heavy observation", report["ranked_candidates"][1]["risk_flags"])

    def test_report_excludes_bad_wallets_from_ranked_candidates_and_counts_blocked(self):
        report = build_wallet_candidate_quality_report(
            candidate_wallets={
                "generated_at": 100,
                "candidates": [
                    {"wallet": "WalletAllowed", "score": 45, "winner_mints": 1, "last_seen": 100},
                    {"wallet": "WalletBad", "score": 99, "winner_mints": 6, "last_seen": 100},
                ],
                "blocked_candidates": [
                    {"wallet": "WalletAlreadyBlocked", "blocked_reason": "bad_wallet_list"},
                ],
            },
            paper_watch_wallets={"wallets": []},
            bad_wallets=["WalletBad", "WalletAlreadyBlocked"],
            wallet_behavior={"wallets": {}},
            generated_at=100,
        )

        self.assertEqual(report["summary"]["active_candidates"], 1)
        self.assertEqual(report["summary"]["blocked_candidates"], 2)
        self.assertEqual([row["wallet"] for row in report["ranked_candidates"]], ["WalletAllowed"])
        self.assertEqual(
            {row["wallet"] for row in report["blocked_candidates"]},
            {"WalletBad", "WalletAlreadyBlocked"},
        )

    def test_writer_persists_report_without_mutating_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_candidate_quality_report.json"
            report = write_wallet_candidate_quality_report(
                out_path=out,
                candidate_wallets={
                    "generated_at": 100,
                    "candidates": [{"wallet": "WalletA", "score": 55, "winner_mints": 1}],
                },
                paper_watch_wallets={"wallets": []},
                bad_wallets=[],
                wallet_behavior={"wallets": {}},
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["active_candidates"], 1)
            self.assertEqual(report["ranked_candidates"][0]["wallet"], "WalletA")


if __name__ == "__main__":
    unittest.main()
