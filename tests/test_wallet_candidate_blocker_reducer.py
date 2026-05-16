import unittest

from wallets.wallet_candidate_blocker_reducer import build_wallet_candidate_blocker_reducer


class WalletCandidateBlockerReducerTests(unittest.TestCase):
    def test_blocker_reducer_summarizes_stage4_blockers(self):
        report = build_wallet_candidate_blocker_reducer(
            candidate_audit={
                "counts": {"candidates": 3, "resolved": 1},
                "candidates": [
                    {"wallet": "RiskWallet", "audit_status": "RISK_REVIEW_REQUIRED"},
                    {"wallet": "MarketWallet", "audit_status": "INSUFFICIENT_EVIDENCE"},
                    {"wallet": "OutcomeWallet", "audit_status": "INSUFFICIENT_EVIDENCE"},
                ],
            },
            collection_plan={
                "summary": {
                    "total_targets": 3,
                    "collect_outcomes_and_market_context": 1,
                    "collect_outcome_labels": 1,
                    "manual_risk_review": 1,
                    "resolved_excluded": 1,
                },
                "targets": [
                    {
                        "wallet": "RiskWallet",
                        "next_collection_step": "MANUAL_RISK_REVIEW",
                        "known_outcomes": 0,
                        "round_trip_lifecycles": 0,
                        "missing": {"known_outcomes": 20, "round_trip_lifecycles": 3, "risk_review": True},
                    },
                    {
                        "wallet": "MarketWallet",
                        "next_collection_step": "COLLECT_OUTCOMES_AND_MARKET_CONTEXT",
                        "known_outcomes": 1,
                        "round_trip_lifecycles": 1,
                        "missing": {"known_outcomes": 19, "round_trip_lifecycles": 2, "market_context": True},
                    },
                    {
                        "wallet": "OutcomeWallet",
                        "next_collection_step": "COLLECT_OUTCOME_LABELS",
                        "known_outcomes": 8,
                        "round_trip_lifecycles": 4,
                        "missing": {"known_outcomes": 12, "round_trip_lifecycles": 0},
                    },
                ],
            },
            collection_batch={
                "summary": {"steps_passed": 16, "steps_failed": 0},
            },
            generated_at=123.0,
            limit=2,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["blocked_total"], 3)
        self.assertEqual(report["summary"]["actionable_review"], 0)
        self.assertEqual(report["primary_blocker_counts"]["manual_risk_review"], 1)
        self.assertEqual(report["primary_blocker_counts"]["missing_outcomes_and_market_context"], 1)
        self.assertEqual(report["primary_blocker_counts"]["missing_outcome_labels"], 1)
        self.assertEqual(report["batch_health"]["steps_failed"], 0)
        self.assertEqual(report["missing_totals"]["known_outcomes"], 51)
        self.assertEqual(len(report["top_blocked_wallets"]), 2)
        self.assertEqual(report["next_actions"][0]["action"], "resolve_manual_risk_reviews")


if __name__ == "__main__":
    unittest.main()
