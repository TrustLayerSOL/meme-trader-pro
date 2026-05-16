import unittest

from wallets.wallet_candidate_context_recovery_closeout import build_wallet_candidate_context_recovery_closeout


class WalletCandidateContextRecoveryCloseoutTests(unittest.TestCase):
    def test_closeout_classifies_blocked_wallets_into_exact_next_actions(self):
        report = build_wallet_candidate_context_recovery_closeout(
            recovery_runner={
                "wallets": [
                    {
                        "wallet": "WalletBoth",
                        "source_bucket": "paper_watch_candidate",
                        "remaining_blockers": [
                            "missing_decision_time_market_context",
                            "missing_outcome_labels",
                        ],
                        "existing_evidence": {
                            "total_rows": 5,
                            "rows_with_entry_context": 0,
                            "rows_with_known_outcomes": 0,
                            "linked_transactions": ["SigBoth"],
                        },
                    },
                    {
                        "wallet": "WalletOutcome",
                        "source_bucket": "observe_more",
                        "remaining_blockers": ["missing_outcome_labels"],
                        "existing_evidence": {
                            "total_rows": 4,
                            "rows_with_entry_context": 4,
                            "rows_with_known_outcomes": 0,
                            "linked_transactions": ["SigOutcome"],
                        },
                    },
                    {
                        "wallet": "WalletTx",
                        "remaining_blockers": ["blocked_missing_transaction"],
                        "existing_evidence": {"total_rows": 0, "linked_transactions": []},
                    },
                    {
                        "wallet": "WalletReady",
                        "remaining_blockers": [],
                        "existing_evidence": {
                            "total_rows": 8,
                            "rows_with_entry_context": 8,
                            "rows_with_known_outcomes": 8,
                            "linked_transactions": ["SigReady"],
                        },
                    },
                ]
            },
            generated_at=123.0,
            limit=10,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["wallets_reviewed"], 4)
        self.assertEqual(report["summary"]["needs_market_context"], 1)
        self.assertEqual(report["summary"]["needs_outcome_labels"], 2)
        self.assertEqual(report["summary"]["needs_transaction_linkage"], 1)
        self.assertEqual(report["summary"]["ready_for_candidate_review"], 1)
        rows = {row["wallet"]: row for row in report["wallets"]}
        self.assertEqual(rows["WalletBoth"]["next_action"], "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS")
        self.assertEqual(rows["WalletOutcome"]["next_action"], "BACKFILL_OUTCOME_LABELS")
        self.assertEqual(rows["WalletTx"]["next_action"], "LINK_TRANSACTION_ARTIFACTS")
        self.assertEqual(rows["WalletReady"]["next_action"], "READY_FOR_CANDIDATE_REVIEW")
        self.assertFalse(rows["WalletReady"]["can_auto_apply"])


if __name__ == "__main__":
    unittest.main()
