import unittest

from wallets.wallet_cycle_report import build_wallet_cycle_report


class WalletCycleReportTests(unittest.TestCase):
    def test_report_summarizes_wallet_cycle_counts(self):
        report = build_wallet_cycle_report(
            tracked_wallets=[
                {"trackedWalletAddress": "TrackedA"},
                {"trackedWalletAddress": "TrackedB"},
            ],
            paper_watch_wallets={
                "wallets": [
                    {"wallet": "WatchA", "status": "paper_watch"},
                    {"wallet": "WatchB", "status": "paper_watch"},
                    {"wallet": "BlockedA", "status": "demote_review", "blocked_reason": "bad_wallet_list"},
                ],
                "summary": {"active_paper_watch_wallets": 2, "blocked_bad_wallets": 1},
            },
            bad_wallets=["BlockedA", "BlockedB"],
            candidate_audit={
                "counts": {
                    "promotion_review": 1,
                    "demotion_review": 3,
                    "resolved": 4,
                },
                "candidates": [
                    {
                        "wallet": "PromoteA",
                        "recommendation_action": "PROMOTION_REVIEW",
                        "audit_status": "HUMAN_REVIEW_REQUIRED",
                        "evidence": {"known_outcomes": 20, "promotion_score": 80},
                    },
                    {
                        "wallet": "DemoteA",
                        "recommendation_action": "DEMOTION_REVIEW",
                        "audit_status": "HUMAN_REVIEW_REQUIRED",
                        "evidence": {"known_outcomes": 25, "demotion_score": 70},
                    },
                ],
            },
            wallet_replay_scorecard={
                "counts": {"events": 100, "wallets": 12, "co_entry_pairs": 3},
                "ecosystems": {"repeated_pair_count": 2},
            },
            review_decisions={
                "decisions": [
                    {"wallet": "PromoteA", "decision": "approve_promotion", "approved": True},
                    {"wallet": "IgnoreA", "decision": "approve_demotion", "approved": False},
                    {"wallet": "DemoteA", "decision": "approve_demotion", "approved": True},
                ]
            },
            wallet_list_update_audit={
                "updates": [
                    {
                        "summary": {"promoted": 4, "demoted": 10, "skipped": 5},
                        "backup_dir": "data/archives/latest",
                    }
                ]
            },
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["counts"]["tracked_wallets"], 2)
        self.assertEqual(report["counts"]["active_paper_watch_wallets"], 2)
        self.assertEqual(report["counts"]["blocked_paper_watch_wallets"], 1)
        self.assertEqual(report["counts"]["bad_wallets"], 2)
        self.assertEqual(report["review_queue"]["promotion_review"], 1)
        self.assertEqual(report["review_queue"]["demotion_review"], 3)
        self.assertEqual(report["review_decisions"]["approved_promotion"], 1)
        self.assertEqual(report["review_decisions"]["approved_demotion"], 1)
        self.assertEqual(report["replay"]["events"], 100)
        self.assertEqual(report["latest_apply"]["summary"]["demoted"], 10)
        self.assertEqual(report["pending_candidates"]["demotion_review"][0]["wallet"], "DemoteA")

    def test_report_marks_attention_when_demotions_are_pending(self):
        report = build_wallet_cycle_report(
            tracked_wallets=[],
            paper_watch_wallets={"wallets": []},
            bad_wallets=[],
            candidate_audit={
                "counts": {"promotion_review": 0, "demotion_review": 2, "resolved": 0},
                "candidates": [
                    {"wallet": "DemoteA", "recommendation_action": "DEMOTION_REVIEW", "evidence": {"demotion_score": 60}},
                    {"wallet": "DemoteB", "recommendation_action": "DEMOTION_REVIEW", "evidence": {"demotion_score": 50}},
                ],
            },
            wallet_replay_scorecard={},
            review_decisions={"decisions": []},
            wallet_list_update_audit={},
        )

        self.assertIn("demotion_reviews_pending", report["attention"])


if __name__ == "__main__":
    unittest.main()
