import unittest

from wallets.wallet_candidate_context_recovery_runner import build_wallet_candidate_context_recovery_report


class WalletCandidateContextRecoveryRunnerTests(unittest.TestCase):
    def test_context_recovery_links_existing_artifacts_without_mutations(self):
        report = build_wallet_candidate_context_recovery_report(
            recovery_queue={
                "targets": [
                    {
                        "wallet": "WalletA",
                        "source_bucket": "paper_watch_candidate",
                        "missing_known_outcomes": 20,
                        "missing_round_trip_lifecycles": 3,
                    },
                    {
                        "wallet": "WalletB",
                        "source_bucket": "observe_more",
                        "missing_known_outcomes": 10,
                        "missing_round_trip_lifecycles": 1,
                    },
                ]
            },
            enriched_evidence=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "transaction_signature": "SigA",
                    "enrichment_status": "MISSING_MARKET_CONTEXT",
                    "estimated_entry_context": {"price": None},
                    "later_token_outcome": {"outcome_type": "unknown"},
                },
                {
                    "wallet": "WalletB",
                    "token_mint": "MintB",
                    "transaction_signature": "SigB",
                    "enrichment_status": "ENRICHED",
                    "estimated_entry_context": {"price": 0.01},
                    "later_token_outcome": {"outcome_type": "runner"},
                },
            ],
            missing_market_context={
                "targets": [
                    {
                        "token_mint": "MintA",
                        "evidence_rows": 3,
                        "wallets": ["WalletA"],
                        "next_collection_step": "BACKFILL_MARKET_CONTEXT",
                    }
                ]
            },
            replay_events=[
                {
                    "event_id": "ReplayA",
                    "decision_context": {
                        "triggering_wallets": [{"wallet": "WalletA"}],
                        "market": {"liquidity": 1000},
                    },
                    "later_outcome": {"outcome_type": "unknown"},
                }
            ],
            historical_backfill_records=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "status": "blocked_missing_price",
                    "block_reasons": ["blocked_missing_price"],
                }
            ],
            generated_at=123.0,
            limit=10,
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["targets_processed"], 2)
        self.assertEqual(report["summary"]["evidence_rows_linked"], 2)
        self.assertEqual(report["summary"]["replay_events_linked"], 1)
        self.assertEqual(report["summary"]["missing_market_context_rows_linked"], 3)
        self.assertEqual(report["summary"]["historical_backfill_records_linked"], 1)
        rows = {row["wallet"]: row for row in report["wallets"]}
        self.assertEqual(rows["WalletA"]["status"], "existing_artifacts_linked")
        self.assertIn("missing_decision_time_market_context", rows["WalletA"]["remaining_blockers"])
        self.assertEqual(rows["WalletB"]["existing_evidence"]["rows_with_known_outcomes"], 1)
        self.assertFalse(report["wallet_list_apply_allowed"])


if __name__ == "__main__":
    unittest.main()
