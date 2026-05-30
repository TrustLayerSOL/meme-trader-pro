import unittest

from wallets.wallet_candidate_decision_prep import build_wallet_candidate_decision_prep


class WalletCandidateDecisionPrepTests(unittest.TestCase):
    def audit(self):
        return {
            "counts": {"candidates": 3},
            "candidates": [
                {
                    "wallet": "PromoteWallet",
                    "recommendation_action": "PROMOTION_REVIEW",
                    "audit_status": "HUMAN_REVIEW_REQUIRED",
                    "review_resolved": False,
                    "evidence_gates": {"source_coverage": 0.9, "stage4_action": "PROMOTION_REVIEW_READY"},
                    "evidence": {
                        "source": "wallet_stage4_review",
                        "known_outcomes": 24,
                        "round_trip_lifecycles": 4,
                        "runner_participation": 12,
                        "rug_participation": 0,
                        "runner_participation_rate": 0.5,
                        "rug_participation_rate": 0.0,
                        "source_bucket": "paper_watch_candidate",
                        "recommendation_reasons": ["promotion gate passed"],
                    },
                },
                {
                    "wallet": "DemoteWallet",
                    "recommendation_action": "DEMOTION_REVIEW",
                    "audit_status": "HUMAN_REVIEW_REQUIRED",
                    "review_resolved": False,
                    "evidence_gates": {"source_coverage": 1.0, "stage4_action": "DEMOTION_OR_BLOCK_REVIEW"},
                    "evidence": {
                        "source": "wallet_stage4_review",
                        "known_outcomes": 20,
                        "round_trip_lifecycles": 1,
                        "runner_participation": 0,
                        "rug_participation": 20,
                        "runner_participation_rate": 0.0,
                        "rug_participation_rate": 1.0,
                        "source_bucket": "hold_no_edge",
                        "recommendation_reasons": ["rug-heavy evidence"],
                    },
                },
                {
                    "wallet": "RiskWallet",
                    "recommendation_action": "RISK_REVIEW_REQUIRED",
                    "audit_status": "RISK_REVIEW_REQUIRED",
                    "review_resolved": False,
                    "evidence": {"source": "wallet_stage4_review"},
                },
            ],
        }

    def test_builds_draft_decisions_without_approval_or_apply(self):
        report = build_wallet_candidate_decision_prep(self.audit(), generated_at=123.0)

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["proposed_decisions"], 2)
        self.assertEqual(report["summary"]["returned_proposed_decisions"], 2)
        self.assertEqual(report["summary"]["approve_promotion"], 1)
        self.assertEqual(report["summary"]["approve_demotion"], 1)
        self.assertEqual(report["summary"]["blocked_candidates"], 1)
        self.assertEqual(report["summary"]["returned_blocked_candidates"], 1)

        proposals = {row["wallet"]: row for row in report["proposed_decisions"]}
        self.assertEqual(proposals["PromoteWallet"]["decision"], "approve_promotion")
        self.assertFalse(proposals["PromoteWallet"]["approved"])
        self.assertTrue(proposals["PromoteWallet"]["requires_operator_approval"])
        self.assertEqual(proposals["PromoteWallet"]["candidate_source"], "wallet_stage4_review")
        self.assertEqual(proposals["PromoteWallet"]["evidence_snapshot"]["round_trip_lifecycles"], 4)
        self.assertEqual(proposals["DemoteWallet"]["decision"], "approve_demotion")
        self.assertEqual(report["blocked_candidates"][0]["reason"], "not_actionable_review_action")

    def test_selected_wallets_limit_the_prepared_records(self):
        report = build_wallet_candidate_decision_prep(
            self.audit(),
            selected_wallets=["DemoteWallet"],
            generated_at=123.0,
        )

        self.assertEqual(report["selected_wallets"], ["DemoteWallet"])
        self.assertEqual(report["summary"]["scanned_candidates"], 1)
        self.assertEqual(report["summary"]["proposed_decisions"], 1)
        self.assertEqual(report["proposed_decisions"][0]["wallet"], "DemoteWallet")
        self.assertEqual(report["proposed_decisions"][0]["decision"], "approve_demotion")

    def test_blocks_selected_rows_that_are_not_human_review_required(self):
        report = build_wallet_candidate_decision_prep(
            self.audit(),
            selected_wallets=["RiskWallet"],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["proposed_decisions"], 0)
        self.assertEqual(report["summary"]["blocked_candidates"], 1)
        self.assertEqual(report["blocked_candidates"][0]["wallet"], "RiskWallet")
        self.assertEqual(report["blocked_candidates"][0]["reason"], "not_actionable_review_action")


if __name__ == "__main__":
    unittest.main()
