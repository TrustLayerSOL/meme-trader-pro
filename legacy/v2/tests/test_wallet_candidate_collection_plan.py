import unittest

from wallets.wallet_candidate_collection_plan import build_wallet_candidate_collection_plan


class WalletCandidateCollectionPlanTests(unittest.TestCase):
    def test_collection_plan_classifies_stage4_evidence_gaps(self):
        report = build_wallet_candidate_collection_plan(
            {
                "candidates": [
                    {
                        "wallet": "NeedsMarket",
                        "recommendation_action": "HOLD_MORE_DATA",
                        "audit_status": "INSUFFICIENT_EVIDENCE",
                        "evidence": {
                            "source_bucket": "paper_watch_candidate",
                            "scorecard_next_action": "collect_outcomes_and_market_context",
                            "known_outcomes": 1,
                            "round_trip_lifecycles": 1,
                        },
                    },
                    {
                        "wallet": "NeedsOutcome",
                        "recommendation_action": "HOLD_MORE_DATA",
                        "audit_status": "INSUFFICIENT_EVIDENCE",
                        "evidence": {
                            "source_bucket": "observe_more",
                            "scorecard_next_action": "collect_outcome_labels",
                            "known_outcomes": 8,
                            "round_trip_lifecycles": 4,
                        },
                    },
                    {
                        "wallet": "NeedsRisk",
                        "recommendation_action": "RISK_REVIEW_REQUIRED",
                        "audit_status": "RISK_REVIEW_REQUIRED",
                        "evidence": {
                            "source_bucket": "risk_review",
                            "scorecard_next_action": "manual_risk_review",
                            "known_outcomes": 0,
                            "round_trip_lifecycles": 0,
                        },
                    },
                ],
                "resolved_candidates": [{"wallet": "Resolved"}],
            },
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["total_targets"], 3)
        self.assertEqual(report["summary"]["collect_outcomes_and_market_context"], 1)
        self.assertEqual(report["summary"]["collect_outcome_labels"], 1)
        self.assertEqual(report["summary"]["manual_risk_review"], 1)
        self.assertEqual(report["summary"]["resolved_excluded"], 1)

        rows = {row["wallet"]: row for row in report["targets"]}
        self.assertEqual(rows["NeedsMarket"]["next_collection_step"], "COLLECT_OUTCOMES_AND_MARKET_CONTEXT")
        self.assertTrue(rows["NeedsMarket"]["missing"]["market_context"])
        self.assertEqual(rows["NeedsMarket"]["missing"]["known_outcomes"], 19)
        self.assertEqual(rows["NeedsMarket"]["missing"]["round_trip_lifecycles"], 2)
        self.assertEqual(rows["NeedsOutcome"]["next_collection_step"], "COLLECT_OUTCOME_LABELS")
        self.assertFalse(rows["NeedsOutcome"]["missing"]["market_context"])
        self.assertEqual(rows["NeedsRisk"]["next_collection_step"], "MANUAL_RISK_REVIEW")
        self.assertTrue(rows["NeedsRisk"]["blocked_from_trust_change"])


if __name__ == "__main__":
    unittest.main()
