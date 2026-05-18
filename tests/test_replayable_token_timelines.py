import unittest

from research.replayable_token_timelines import build_replayable_token_timelines_report


class ReplayableTokenTimelinesTests(unittest.TestCase):
    def test_timeline_layer_reaches_completion_when_gaps_are_inventoryed(self):
        report = build_replayable_token_timelines_report(
            evidence_layer_completion={
                "live_execution_locked": True,
                "summary": {
                    "evidence_layer_completion_pct": 100,
                    "remaining_blocked_wallets": 36,
                    "needs_outcome_labels": 36,
                    "needs_market_context": 32,
                    "needs_transaction_linkage": 0,
                    "wallet_score_readiness_pct": 0,
                },
            },
            recovery_closeout={
                "live_execution_locked": True,
                "summary": {
                    "wallets_reviewed": 36,
                    "still_blocked_wallets": 36,
                    "needs_market_context": 32,
                    "needs_outcome_labels": 36,
                    "needs_transaction_linkage": 0,
                },
                "next_action_counts": {
                    "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 32,
                    "BACKFILL_OUTCOME_LABELS": 4,
                },
                "wallets": [
                    {
                        "wallet": "WalletA",
                        "next_action": "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS",
                        "evidence_snapshot": {
                            "linked_mint_count": 2,
                            "missing_market_context_rows": 3,
                            "missing_outcome_label_rows": 4,
                        },
                    }
                ],
            },
            missing_market_context={
                "live_execution_locked": True,
                "summary": {
                    "target_mints": 77,
                    "missing_market_context_rows": 643,
                    "wallets_affected": 33,
                },
                "targets": [
                    {
                        "token_mint": "MintA",
                        "evidence_rows": 3,
                        "known_outcome_rows": 0,
                        "unknown_outcome_rows": 3,
                        "next_collection_step": "BACKFILL_MARKET_CONTEXT",
                    }
                ],
            },
            onchain_market_context={
                "live_execution_locked": True,
                "summary": {
                    "records_scanned": 643,
                    "price_recovered_records": 201,
                    "liquidity_recovered_records": 86,
                    "market_cap_recovered_records": 0,
                    "score_ready_candidate_records": 0,
                },
            },
            supply_evidence={
                "live_execution_locked": True,
                "summary": {
                    "records_scanned": 643,
                    "supply_recovered_records": 0,
                    "needs_archival_supply_records": 643,
                },
            },
            stage6_readiness={
                "live_execution_locked": True,
                "summary": {
                    "stage6_realism_contract_completion_pct": 100,
                    "data_score_readiness_pct": 0,
                },
                "blocking_data_gaps": ["missing_market_cap", "historical_supply_still_missing"],
            },
            stage8_readiness={
                "live_execution_locked": True,
                "summary": {
                    "stage8_validation_contract_completion_pct": 100,
                    "proof_readiness_pct": 0,
                },
                "evidence_gaps": ["low_known_outcome_coverage"],
            },
            generated_at=123.0,
            limit=5,
        )

        self.assertEqual(report["mode"], "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["replayable_token_timelines_completion_pct"], 100)
        self.assertEqual(report["summary"]["timeline_data_readiness_pct"], 0)
        self.assertEqual(report["summary"]["target_mints"], 77)
        self.assertEqual(report["summary"]["blocked_wallets_routed"], 36)
        self.assertIn("market_context_targets_inventoryed", report["passed_gates"])
        self.assertIn("outcome_label_gap_inventoryed", report["passed_gates"])
        self.assertIn("historical_supply_still_missing", report["residual_data_blockers"])
        self.assertEqual(report["timeline_targets"][0]["token_mint"], "MintA")

    def test_partial_wallet_score_readiness_does_not_make_inventory_layer_incomplete(self):
        report = build_replayable_token_timelines_report(
            evidence_layer_completion={
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "evidence_layer_completion_pct": 100,
                    "remaining_blocked_wallets": 36,
                    "needs_outcome_labels": 36,
                    "needs_market_context": 32,
                    "needs_transaction_linkage": 0,
                    "wallet_score_readiness_pct": 2,
                },
            },
            recovery_closeout={
                "live_execution_locked": True,
                "summary": {
                    "still_blocked_wallets": 36,
                    "needs_market_context": 32,
                    "needs_outcome_labels": 36,
                    "needs_transaction_linkage": 0,
                },
            },
            missing_market_context={
                "live_execution_locked": True,
                "summary": {
                    "target_mints": 77,
                    "missing_market_context_rows": 643,
                },
            },
            onchain_market_context={
                "live_execution_locked": True,
                "summary": {
                    "records_scanned": 643,
                    "price_recovered_records": 201,
                    "liquidity_recovered_records": 86,
                    "market_cap_recovered_records": 11,
                    "score_ready_candidate_records": 11,
                },
            },
            supply_evidence={
                "live_execution_locked": True,
                "summary": {
                    "records_scanned": 643,
                    "supply_recovered_records": 0,
                },
            },
            stage6_readiness={
                "live_execution_locked": True,
                "summary": {"stage6_realism_contract_completion_pct": 100},
                "blocking_data_gaps": ["historical_supply_still_missing"],
            },
            stage8_readiness={
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "stage8_validation_contract_completion_pct": 100,
                    "proof_readiness_pct": 2,
                },
            },
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["replayable_token_timelines_completion_pct"], 100)
        self.assertEqual(report["summary"]["timeline_data_readiness_pct"], 2)
        self.assertIn("trust_changes_blocked", report["passed_gates"])
        self.assertFalse(report["wallet_list_mutated"])


if __name__ == "__main__":
    unittest.main()
