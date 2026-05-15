import tempfile
import unittest
from pathlib import Path

from wallets.wallet_candidate_quality_review import build_wallet_candidate_quality_review
from utils.build_wallet_candidate_quality_review import write_wallet_candidate_quality_review


class WalletCandidateQualityReviewTests(unittest.TestCase):
    def test_strong_quality_with_replay_support_becomes_promotion_review_ready(self):
        review = build_wallet_candidate_quality_review(
            candidate_quality_report={
                "ranked_candidates": [
                    {
                        "wallet": "WalletReady",
                        "quality_score": 86,
                        "recommended_observation": "STRONG_OBSERVATION",
                        "winner_mints": 5,
                        "early_buy_events": 20,
                        "risk_flags": [],
                    }
                ]
            },
            wallet_replay_scorecard={
                "wallets": {
                    "WalletReady": {
                        "total_events": 16,
                        "fillable_events": 14,
                        "windows": {"15m": {"known": 12}},
                        "signal_quality": {
                            "known_rate_15m": 0.75,
                            "runner_rate_known_15m": 0.75,
                            "rug_rate_known_15m": 0.0,
                        },
                    }
                }
            },
            wallet_outcome_ledger={
                "wallets": {
                    "WalletReady": {
                        "known_outcomes": 12,
                        "runner_participation_rate": 0.75,
                        "rug_participation_rate": 0.0,
                        "promotion_score": 74,
                    }
                }
            },
        )

        self.assertTrue(review["review_only"])
        self.assertTrue(review["live_execution_locked"])
        self.assertEqual(review["summary"]["promotion_review_ready"], 1)
        row = review["shortlist"][0]
        self.assertEqual(row["wallet"], "WalletReady")
        self.assertEqual(row["recommendation"]["action"], "PROMOTION_REVIEW_READY")
        self.assertFalse(row["recommendation"]["auto_apply"])

    def test_strong_quality_without_replay_support_stays_observe_more(self):
        review = build_wallet_candidate_quality_review(
            candidate_quality_report={
                "ranked_candidates": [
                    {
                        "wallet": "WalletThin",
                        "quality_score": 82,
                        "recommended_observation": "STRONG_OBSERVATION",
                        "risk_flags": [],
                    }
                ]
            },
            wallet_replay_scorecard={"wallets": {}},
            wallet_outcome_ledger={"wallets": {}},
        )

        self.assertEqual(review["summary"]["observe_more"], 1)
        self.assertEqual(review["shortlist"][0]["recommendation"]["action"], "OBSERVE_MORE")
        self.assertIn("replay evidence below threshold", review["shortlist"][0]["evidence_gaps"])

    def test_writer_persists_review_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_candidate_quality_review.json"
            review = write_wallet_candidate_quality_review(
                out_path=out,
                candidate_quality_report={
                    "ranked_candidates": [
                        {"wallet": "WalletA", "quality_score": 70, "recommended_observation": "PAPER_WATCH_REVIEW"}
                    ]
                },
                wallet_replay_scorecard={"wallets": {}},
                wallet_outcome_ledger={"wallets": {}},
            )

            self.assertTrue(out.exists())
            self.assertEqual(review["summary"]["total_reviewed"], 1)


if __name__ == "__main__":
    unittest.main()
