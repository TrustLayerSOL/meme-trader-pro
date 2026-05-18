import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.replayable_token_timelines import build_replayable_token_timelines_report
from utils.build_replayable_token_timelines import write_replayable_token_timelines_report


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

    def test_timeline_layer_accepts_score_ready_and_archival_supply_summaries(self):
        report = build_replayable_token_timelines_report(
            evidence_layer_completion={
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "evidence_layer_completion_pct": 100,
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
                    "price_recovered_records": 634,
                    "liquidity_recovered_records": 632,
                    "score_ready_records": 43,
                },
            },
            supply_evidence={
                "live_execution_locked": True,
                "summary": {
                    "candidate_rows": 591,
                    "supply_recovered_records": 2,
                },
            },
            stage6_readiness={
                "live_execution_locked": True,
                "summary": {
                    "stage6_realism_contract_completion_pct": 100,
                    "data_score_readiness_pct": 7,
                },
                "blocking_data_gaps": ["historical_supply_still_missing"],
            },
            stage8_readiness={
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "stage8_validation_contract_completion_pct": 100,
                    "proof_readiness_pct": 6,
                },
            },
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["score_ready_records"], 43)
        self.assertEqual(report["summary"]["supply_records_scanned"], 591)
        self.assertEqual(report["summary"]["supply_recovered_records"], 2)
        self.assertEqual(report["summary"]["timeline_data_readiness_pct"], 6)

    def test_writer_merges_onchain_inventory_with_score_ready_classifier(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.json"
            closeout_path = root / "closeout.json"
            missing_path = root / "missing.json"
            onchain_path = root / "onchain.json"
            score_ready_path = root / "score_ready.json"
            supply_path = root / "supply.json"
            stage6_path = root / "stage6.json"
            stage8_path = root / "stage8.json"
            output_path = root / "timeline.json"

            evidence_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"evidence_layer_completion_pct": 100, "wallet_score_readiness_pct": 2},
            }), encoding="utf-8")
            closeout_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {"still_blocked_wallets": 36, "needs_market_context": 32, "needs_outcome_labels": 36, "needs_transaction_linkage": 0},
            }), encoding="utf-8")
            missing_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {"target_mints": 77, "missing_market_context_rows": 643},
            }), encoding="utf-8")
            onchain_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {
                    "records_scanned": 643,
                    "price_recovered_records": 634,
                    "liquidity_recovered_records": 632,
                    "market_cap_recovered_records": 41,
                    "score_ready_candidate_records": 41,
                },
            }), encoding="utf-8")
            score_ready_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {"records_scanned": 643, "score_ready_records": 43},
            }), encoding="utf-8")
            supply_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {"candidate_rows": 591, "supply_recovered_records": 2},
            }), encoding="utf-8")
            stage6_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "summary": {"stage6_realism_contract_completion_pct": 100, "data_score_readiness_pct": 7},
                "blocking_data_gaps": ["historical_supply_still_missing"],
            }), encoding="utf-8")
            stage8_path.write_text(__import__("json").dumps({
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"stage8_validation_contract_completion_pct": 100, "proof_readiness_pct": 7},
            }), encoding="utf-8")

            report = write_replayable_token_timelines_report(
                evidence_layer_path=evidence_path,
                recovery_closeout_path=closeout_path,
                missing_market_context_path=missing_path,
                onchain_market_context_path=onchain_path,
                score_ready_market_context_path=score_ready_path,
                supply_evidence_path=supply_path,
                stage6_readiness_path=stage6_path,
                stage8_readiness_path=stage8_path,
                output_path=output_path,
            )

            self.assertEqual(report["summary"]["replayable_token_timelines_completion_pct"], 100)
            self.assertEqual(report["summary"]["price_recovered_records"], 634)
            self.assertEqual(report["summary"]["liquidity_recovered_records"], 632)
            self.assertEqual(report["summary"]["score_ready_records"], 43)
            self.assertEqual(report["summary"]["supply_records_scanned"], 591)


if __name__ == "__main__":
    unittest.main()
