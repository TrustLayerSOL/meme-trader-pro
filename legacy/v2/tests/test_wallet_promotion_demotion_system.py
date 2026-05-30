import unittest

from research.wallet_promotion_demotion_system import build_wallet_promotion_demotion_system_report


def report_stub(mode: str, summary=None, **overrides):
    row = {
        "mode": mode,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": summary or {},
    }
    row.update(overrides)
    return row


class WalletPromotionDemotionSystemTests(unittest.TestCase):
    def test_stage4_reaches_completion_when_review_chain_is_visible_and_guarded(self):
        report = build_wallet_promotion_demotion_system_report(
            stage4_review=report_stub(
                "WALLET_STAGE4_PROMOTION_DEMOTION_REVIEW_ONLY",
                {
                    "stage4_review_completion_pct": 40,
                    "wallets_reviewed": 50,
                    "promotion_review_ready": 0,
                    "hold_more_data": 45,
                    "risk_review_required": 4,
                    "demotion_or_block_review": 1,
                    "auto_applied": 0,
                },
                reviews=[{"wallet": "WalletA", "stage4_action": "HOLD_MORE_DATA", "auto_apply": False}],
            ),
            candidate_audit=report_stub(
                "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY",
                {
                    "candidates": 49,
                    "promotion_review": 0,
                    "demotion_review": 1,
                    "risk_review_required": 4,
                    "insufficient_evidence": 45,
                    "resolved": 5,
                },
                counts={
                    "candidates": 49,
                    "promotion_review": 0,
                    "demotion_review": 1,
                    "risk_review_required": 4,
                    "insufficient_evidence": 45,
                    "resolved": 5,
                },
                candidates=[{"wallet": "WalletA", "review_only": True, "wallet_list_apply_allowed": False}],
            ),
            decision_prep=report_stub(
                "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY",
                {"proposed_decisions": 1, "blocked_candidates": 48},
                proposed_decisions=[{"wallet": "WalletA", "approved": False, "requires_operator_approval": True}],
            ),
            review_summary=report_stub(
                "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY",
                {"actionable_review": 0, "risk_review_required": 4, "insufficient_evidence": 45},
            ),
            collection_plan=report_stub(
                "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY",
                {
                    "total_targets": 49,
                    "collect_outcomes_and_market_context": 36,
                    "collect_outcome_labels": 9,
                    "manual_risk_review": 4,
                },
            ),
            collection_batch=report_stub(
                "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY",
                {"steps_planned": 16, "steps_run": 16, "steps_passed": 16, "steps_failed": 0},
            ),
            blocker_reducer=report_stub(
                "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY",
                {"blocked_total": 49, "batch_steps_failed": 0},
                primary_blocker_counts={"missing_outcomes_and_market_context": 36, "missing_outcome_labels": 9, "manual_risk_review": 4},
            ),
            context_recovery_queue=report_stub(
                "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY",
                {"total_recovery_targets": 36},
            ),
            context_recovery_runner=report_stub(
                "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY",
                {"targets_processed": 36, "wallets_with_existing_artifacts": 36, "still_blocked_wallets": 36},
            ),
            context_recovery_closeout=report_stub(
                "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY",
                {"wallets_reviewed": 36, "still_blocked_wallets": 36, "ready_for_candidate_review": 0},
                next_action_counts={"BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 32, "BACKFILL_OUTCOME_LABELS": 4},
            ),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["stage4_promotion_demotion_completion_pct"], 100)
        self.assertEqual(report["summary"]["wallets_in_review_pipeline"], 54)
        self.assertEqual(report["summary"]["auto_applied"], 0)
        self.assertEqual(report["summary"]["trusted_promotions_allowed"], 0)
        self.assertIn("auto_trust_mutation_blocked", report["passed_gates"])
        self.assertIn("context_recovery_closeout_visible", report["passed_gates"])

    def test_stage4_completion_gate_fails_if_wallet_mutation_is_present(self):
        report = build_wallet_promotion_demotion_system_report(
            stage4_review=report_stub(
                "WALLET_STAGE4_PROMOTION_DEMOTION_REVIEW_ONLY",
                {"wallets_reviewed": 1, "auto_applied": 0},
            ),
            candidate_audit=report_stub("WALLET_CANDIDATE_AUDIT_REVIEW_ONLY", {"candidates": 1}),
            decision_prep=report_stub("WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY", {"proposed_decisions": 0}),
            review_summary=report_stub("WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY", {"insufficient_evidence": 1}),
            collection_plan=report_stub("WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY", {"total_targets": 1}),
            collection_batch=report_stub("WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY", {"steps_failed": 0}),
            blocker_reducer=report_stub("WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY", {"blocked_total": 1}),
            context_recovery_queue=report_stub("WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY", {"total_recovery_targets": 1}),
            context_recovery_runner=report_stub("WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY", {"targets_processed": 1}),
            context_recovery_closeout=report_stub(
                "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY",
                {"wallets_reviewed": 1, "still_blocked_wallets": 1},
                wallet_list_mutated=True,
            ),
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["stage4_promotion_demotion_completion_pct"], 100)
        self.assertIn("wallet_list_mutation_blocked", report["failed_gates"])


if __name__ == "__main__":
    unittest.main()
