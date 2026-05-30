import unittest

from research.wallet_evidence_readiness import build_wallet_evidence_readiness_report


class WalletEvidenceReadinessTests(unittest.TestCase):
    def target_report(self):
        return {
            "mode": "WALLET_CANDIDATE_BACKFILL_TARGETS_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "total_targets": 50,
                "needs_wallet_history": 46,
                "needs_outcome_label_backfill": 0,
                "needs_more_replay_events": 0,
                "risk_review": 4,
            },
        }

    def history_report(self):
        return {
            "mode": "WALLET_HISTORY_BACKFILL_REVIEW_ONLY",
            "live_execution_locked": True,
            "execute": True,
            "summary": {
                "wallets_processed": 46,
                "wallets_successfully_backfilled": 2,
                "wallets_partially_backfilled": 44,
                "wallets_blocked": 0,
                "total_evidence_rows_created": 745,
                "ready_for_candidate_review": 39,
            },
            "evidence_total_rows_after_merge": 1033,
            "evidence_rows_written": 700,
            "evidence_duplicate_rows_skipped": 45,
        }

    def enrichment_report(self):
        return {
            "mode": "WALLET_EVIDENCE_ENRICHMENT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "total_evidence_rows": 1033,
                "unique_wallets": 46,
                "unique_mints": 91,
                "rows_with_entry_context": 324,
                "rows_with_known_outcome": 24,
                "missing_market_context_rows": 709,
                "missing_outcome_label_rows": 321,
            },
        }

    def missing_context_report(self):
        return {
            "mode": "WALLET_MISSING_MARKET_CONTEXT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "target_mints": 77,
                "missing_market_context_rows": 643,
                "wallets_affected": 33,
            },
        }

    def trusted_context_report(self):
        return {
            "mode": "TRUSTED_HISTORICAL_MARKET_SNAPSHOT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 643,
                "score_ready_records": 0,
                "trust_gate_completion_pct": 100,
            },
        }

    def score_ready_context_report(self):
        return {
            "mode": "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 643,
                "score_ready_records": 43,
                "near_score_ready_records": 589,
            },
        }

    def test_stage3_contract_can_complete_while_score_readiness_is_low(self):
        report = build_wallet_evidence_readiness_report(
            candidate_backfill_targets=self.target_report(),
            wallet_history_backfill=self.history_report(),
            wallet_evidence_enrichment=self.enrichment_report(),
            wallet_missing_market_context=self.missing_context_report(),
            trusted_historical_market_context=self.trusted_context_report(),
            evidence_duplicate_count=0,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "WALLET_EVIDENCE_STAGE3_READINESS_REVIEW_ONLY")
        self.assertEqual(report["summary"]["stage3_evidence_contract_completion_pct"], 100)
        self.assertEqual(report["summary"]["wallet_score_readiness_pct"], 0)
        self.assertIn("wallet_history_targets_processed", report["passed_gates"])
        self.assertIn("risk_review_remaining", report["evidence_gaps"])
        self.assertIn("missing_market_context", report["evidence_gaps"])
        self.assertIn("no_score_ready_market_context", report["evidence_gaps"])

    def test_stage3_contract_flags_duplicate_evidence(self):
        report = build_wallet_evidence_readiness_report(
            candidate_backfill_targets=self.target_report(),
            wallet_history_backfill=self.history_report(),
            wallet_evidence_enrichment=self.enrichment_report(),
            wallet_missing_market_context=self.missing_context_report(),
            trusted_historical_market_context=self.trusted_context_report(),
            evidence_duplicate_count=7,
        )

        self.assertLess(report["summary"]["stage3_evidence_contract_completion_pct"], 100)
        self.assertIn("evidence_file_has_duplicates", report["failed_gates"])

    def test_stage3_readiness_accepts_score_ready_market_context_classifier(self):
        report = build_wallet_evidence_readiness_report(
            candidate_backfill_targets=self.target_report(),
            wallet_history_backfill=self.history_report(),
            wallet_evidence_enrichment=self.enrichment_report(),
            wallet_missing_market_context=self.missing_context_report(),
            trusted_historical_market_context=self.score_ready_context_report(),
            evidence_duplicate_count=0,
        )

        self.assertEqual(report["summary"]["score_ready_market_context_records"], 43)
        self.assertEqual(report["summary"]["wallet_score_readiness_pct"], 2)

    def test_stage3_readiness_accepts_forward_evidence_file_count(self):
        enrichment = self.enrichment_report()
        enrichment["summary"]["total_evidence_rows"] = 1037

        report = build_wallet_evidence_readiness_report(
            candidate_backfill_targets=self.target_report(),
            wallet_history_backfill=self.history_report(),
            wallet_evidence_enrichment=enrichment,
            wallet_missing_market_context=self.missing_context_report(),
            trusted_historical_market_context=self.score_ready_context_report(),
            evidence_duplicate_count=0,
            evidence_file_rows=1037,
        )

        self.assertEqual(report["summary"]["evidence_rows"], 1037)
        self.assertEqual(report["summary"]["stage3_evidence_contract_completion_pct"], 100)


if __name__ == "__main__":
    unittest.main()
