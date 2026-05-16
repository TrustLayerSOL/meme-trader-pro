import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_evidence_scorecard import write_wallet_evidence_scorecard_report
from wallets.wallet_evidence_scorecard import build_wallet_evidence_scorecard_report


class WalletEvidenceScorecardTests(unittest.TestCase):
    def test_combines_recommendation_lifecycle_and_enrichment_context(self):
        report = build_wallet_evidence_scorecard_report(
            wallet_evidence_readiness={
                "summary": {
                    "stage3_evidence_contract_completion_pct": 100,
                    "wallet_score_readiness_pct": 0,
                    "score_ready_market_context_records": 0,
                }
            },
            wallet_evidence_recommendations={
                "summary": {"wallets_reviewed": 1},
                "recommendations": [
                    {
                        "wallet": "WalletA",
                        "bucket": "paper_watch_candidate",
                        "promotion_gate": "do_not_promote_yet",
                        "reason_codes": ["usable_wallet_history_without_known_rug_exposure"],
                        "wallet_history": {"total_usable_evidence_rows": 12, "unique_mints": 2},
                    }
                ],
            },
            wallet_evidence_lifecycle={
                "wallets": {
                    "WalletA": {
                        "lifecycle_mints": 2,
                        "round_trip_lifecycles": 1,
                        "buy_only_lifecycles": 1,
                        "average_hold_duration_seconds": 120.0,
                    }
                }
            },
            wallet_evidence_enrichment={
                "evidence_records": [
                    {
                        "wallet": "WalletA",
                        "enrichment_status": "ENRICHED",
                        "estimated_entry_context": {"price": 1.0},
                        "later_token_outcome": {"outcome_type": "runner"},
                    },
                    {
                        "wallet": "WalletA",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "estimated_entry_context": {"price": None},
                        "later_token_outcome": {"outcome_type": "unknown"},
                    },
                ]
            },
            generated_at=1234.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "WALLET_EVIDENCE_SCORECARD_REVIEW_ONLY")
        self.assertEqual(report["summary"]["stage3_engine_completion_pct"], 100)
        self.assertEqual(report["summary"]["wallet_score_readiness_pct"], 0)
        self.assertEqual(report["summary"]["trusted_promotions_allowed"], 0)
        row = report["wallets"][0]
        self.assertEqual(row["wallet"], "WalletA")
        self.assertEqual(row["recommendation_bucket"], "paper_watch_candidate")
        self.assertEqual(row["promotion_gate"], "do_not_promote_yet")
        self.assertEqual(row["lifecycle"]["round_trip_lifecycles"], 1)
        self.assertEqual(row["enrichment"]["known_outcome_rows"], 1)
        self.assertEqual(row["enrichment"]["missing_market_context_rows"], 1)
        self.assertIn("missing_market_context", row["evidence_blockers"])
        self.assertEqual(row["next_action"], "collect_outcomes_and_market_context")

    def test_risk_review_wallets_keep_manual_next_action(self):
        report = build_wallet_evidence_scorecard_report(
            wallet_evidence_readiness={"summary": {"stage3_evidence_contract_completion_pct": 100}},
            wallet_evidence_recommendations={
                "recommendations": [
                    {
                        "wallet": "RiskWallet",
                        "bucket": "risk_review",
                        "promotion_gate": "do_not_promote_yet",
                        "reason_codes": ["unresolved_risk_flags"],
                    }
                ]
            },
            wallet_evidence_lifecycle={"wallets": {}},
            wallet_evidence_enrichment={"evidence_records": []},
            generated_at=1234.0,
        )

        row = report["wallets"][0]
        self.assertEqual(row["next_action"], "manual_risk_review")
        self.assertIn("manual_risk_review_required", row["evidence_blockers"])

    def test_writer_persists_scorecard_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_evidence_scorecard_report.json"
            report = write_wallet_evidence_scorecard_report(
                out_path=out,
                wallet_evidence_readiness={"summary": {"stage3_evidence_contract_completion_pct": 100}},
                wallet_evidence_recommendations={"recommendations": [{"wallet": "WalletA", "bucket": "observe_more"}]},
                wallet_evidence_lifecycle={"wallets": {}},
                wallet_evidence_enrichment={"evidence_records": []},
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["wallets_reviewed"], 1)


if __name__ == "__main__":
    unittest.main()
