import unittest

from wallets.wallet_candidate_context_recovery_queue import build_wallet_candidate_context_recovery_queue


class WalletCandidateContextRecoveryQueueTests(unittest.TestCase):
    def test_context_recovery_queue_targets_outcome_market_blockers(self):
        report = build_wallet_candidate_context_recovery_queue(
            collection_plan={
                "summary": {"total_targets": 3},
                "targets": [
                    {
                        "wallet": "PriorityWallet",
                        "next_collection_step": "COLLECT_OUTCOMES_AND_MARKET_CONTEXT",
                        "source_bucket": "paper_watch_candidate",
                        "known_outcomes": 1,
                        "round_trip_lifecycles": 0,
                        "missing": {"known_outcomes": 19, "round_trip_lifecycles": 3, "market_context": True},
                        "notes": ["known outcome sample below 20"],
                    },
                    {
                        "wallet": "OutcomeOnly",
                        "next_collection_step": "COLLECT_OUTCOME_LABELS",
                        "source_bucket": "observe_more",
                        "known_outcomes": 10,
                        "missing": {"known_outcomes": 10},
                    },
                    {
                        "wallet": "ObserveWallet",
                        "next_collection_step": "COLLECT_OUTCOMES_AND_MARKET_CONTEXT",
                        "source_bucket": "observe_more",
                        "known_outcomes": 0,
                        "round_trip_lifecycles": 1,
                        "missing": {"known_outcomes": 20, "round_trip_lifecycles": 2, "market_context": True},
                    },
                ],
            },
            blocker_reducer={"primary_blocker_counts": {"missing_outcomes_and_market_context": 2}},
            generated_at=123.0,
            limit=10,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["total_recovery_targets"], 2)
        self.assertEqual(report["summary"]["paper_watch_targets"], 1)
        self.assertEqual(report["summary"]["observe_more_targets"], 1)
        self.assertEqual(report["summary"]["missing_known_outcomes"], 39)
        self.assertEqual(report["targets"][0]["wallet"], "PriorityWallet")
        self.assertEqual(report["targets"][0]["required_context"], ["outcome_labels", "decision_time_market_context"])
        self.assertIn("missing_market_context_report", report["targets"][0]["suggested_sources"])


if __name__ == "__main__":
    unittest.main()
