import unittest

from wallets.wallet_candidate_review_summary import build_wallet_candidate_review_summary


class WalletCandidateReviewSummaryTests(unittest.TestCase):
    def test_review_summary_buckets_candidate_queue(self):
        report = build_wallet_candidate_review_summary(
            {
                "candidates": [
                    {
                        "wallet": "ActionWallet",
                        "recommendation_action": "DEMOTION_REVIEW",
                        "audit_status": "HUMAN_REVIEW_REQUIRED",
                        "evidence": {"source": "wallet_stage4_review", "known_outcomes": 20, "rug_participation": 20},
                        "evidence_gates": {"stage4_action": "DEMOTION_OR_BLOCK_REVIEW"},
                        "audit_notes": ["rug-heavy evidence"],
                    },
                    {
                        "wallet": "RiskWallet",
                        "recommendation_action": "RISK_REVIEW_REQUIRED",
                        "audit_status": "RISK_REVIEW_REQUIRED",
                        "evidence": {"source": "wallet_stage4_review", "source_bucket": "risk_review"},
                    },
                    {
                        "wallet": "ThinWallet",
                        "recommendation_action": "HOLD_MORE_DATA",
                        "audit_status": "INSUFFICIENT_EVIDENCE",
                        "evidence": {"source": "wallet_stage4_review", "source_bucket": "paper_watch_candidate"},
                    },
                ],
                "resolved_candidates": [
                    {
                        "wallet": "ResolvedWallet",
                        "recommendation_action": "DEMOTION_REVIEW",
                        "audit_status": "RESOLVED_APPLIED",
                        "evidence": {"source": "wallet_stage4_review"},
                    }
                ],
            },
            decision_prep={"summary": {"proposed_decisions": 1, "blocked_candidates": 2}},
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["candidates"], 3)
        self.assertEqual(report["summary"]["resolved_candidates"], 1)
        self.assertEqual(report["summary"]["actionable_review"], 1)
        self.assertEqual(report["summary"]["risk_review_required"], 1)
        self.assertEqual(report["summary"]["insufficient_evidence"], 1)
        self.assertEqual(report["summary"]["draft_proposed_decisions"], 1)
        self.assertEqual(report["buckets"]["actionable_review"][0]["wallet"], "ActionWallet")
        self.assertEqual(report["buckets"]["risk_review_required"][0]["wallet"], "RiskWallet")
        self.assertEqual(report["buckets"]["insufficient_evidence"][0]["wallet"], "ThinWallet")
        self.assertEqual(report["resolved_candidates"][0]["wallet"], "ResolvedWallet")


if __name__ == "__main__":
    unittest.main()
