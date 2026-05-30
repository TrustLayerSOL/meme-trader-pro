import unittest

from research.evidence_layer_completion import build_evidence_layer_completion_report


class EvidenceLayerCompletionTests(unittest.TestCase):
    def test_evidence_layer_reaches_completion_when_all_gaps_are_explicit(self):
        report = build_evidence_layer_completion_report(
            wallet_evidence_readiness={
                "live_execution_locked": True,
                "summary": {
                    "stage3_evidence_contract_completion_pct": 100,
                    "evidence_duplicate_count": 0,
                    "wallets_blocked": 0,
                    "evidence_rows": 100,
                    "rows_with_known_outcome": 20,
                    "score_ready_market_context_records": 0,
                },
                "evidence_gaps": ["low_known_outcome_coverage", "missing_market_context"],
            },
            wallet_evidence_scorecard={
                "live_execution_locked": True,
                "summary": {
                    "stage3_engine_completion_pct": 100,
                    "wallets_reviewed": 50,
                    "trusted_promotions_allowed": 0,
                },
            },
            recovery_closeout={
                "live_execution_locked": True,
                "summary": {
                    "wallets_reviewed": 36,
                    "still_blocked_wallets": 36,
                    "needs_outcome_labels": 36,
                    "needs_market_context": 32,
                    "needs_transaction_linkage": 0,
                    "ready_for_candidate_review": 0,
                },
                "next_action_counts": {
                    "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 32,
                    "BACKFILL_OUTCOME_LABELS": 4,
                },
            },
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["evidence_layer_completion_pct"], 100)
        self.assertEqual(report["summary"]["wallet_score_readiness_pct"], 0)
        self.assertEqual(report["summary"]["remaining_blocked_wallets"], 36)
        self.assertIn("classified_outcome_label_gap", report["passed_gates"])
        self.assertIn("classified_market_context_gap", report["passed_gates"])
        self.assertIn("outcome_labels_require_new_or_unrecovered_history", report["residual_data_blockers"])


if __name__ == "__main__":
    unittest.main()
