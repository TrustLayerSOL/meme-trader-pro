import unittest

from research.validation_proof_layer import build_validation_proof_layer_report


class ValidationProofLayerTests(unittest.TestCase):
    def test_proof_layer_turns_visible_blockers_into_readiness_criteria(self):
        report = build_validation_proof_layer_report(
            alerting_dashboard_layer={
                "mode": "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "alerting_dashboard_layer_completion_pct": 100,
                    "research_data_readiness_pct": 0,
                    "blocked_data_issue_count": 3,
                },
                "blocked_data_issues": [
                    "known_outcome_coverage_still_low",
                    "score_ready_market_context_absent",
                    "historical_supply_still_missing",
                ],
            },
            stage8_validation={
                "mode": "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY",
                "live_execution_locked": True,
                "summary": {
                    "stage8_validation_contract_completion_pct": 100,
                    "proof_readiness_pct": 0,
                    "known_15m_outcomes": 2,
                    "fillable_rate": 6,
                    "fillability_evidence_rate": 25,
                    "stage6_data_score_readiness_pct": 0,
                },
                "evidence_gaps": ["low_known_outcome_coverage", "low_market_context_score_readiness"],
            },
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "VALIDATION_PROOF_LAYER_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["validation_proof_layer_completion_pct"], 100)
        self.assertEqual(report["summary"]["proof_readiness_pct"], 0)
        self.assertEqual(report["summary"]["criteria_count"], 3)
        self.assertEqual(report["summary"]["blocked_criteria_count"], 3)
        self.assertEqual(report["summary"]["stage8_fillability_evidence_rate"], 25)
        self.assertEqual(report["proof_criteria"][0]["status"], "blocked")
        self.assertIn("decision-time market", report["proof_criteria"][0]["requirement"])
        self.assertIn("live_execution_locked", report["passed_gates"])
        self.assertIn("proof_not_overclaimed", report["passed_gates"])
        self.assertIn("Do not use this as permission", report["operator_alerts"][0]["message"])


if __name__ == "__main__":
    unittest.main()
