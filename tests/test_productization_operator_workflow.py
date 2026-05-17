import unittest

from research.productization_operator_workflow import build_productization_operator_workflow_report


class ProductizationOperatorWorkflowTests(unittest.TestCase):
    def test_operator_workflow_packages_report_chain_without_execution_or_mutation(self):
        report = build_productization_operator_workflow_report(
            evidence_layer={
                "mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"evidence_layer_completion_pct": 100, "wallet_score_readiness_pct": 0},
            },
            replayable_timelines={
                "mode": "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"replayable_token_timelines_completion_pct": 100, "timeline_data_readiness_pct": 0},
            },
            similar_rug_patterns={
                "mode": "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"similar_rug_pattern_completion_pct": 100, "rug_pattern_data_readiness_pct": 0},
            },
            alerting_dashboard_layer={
                "mode": "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"alerting_dashboard_layer_completion_pct": 100, "research_data_readiness_pct": 0},
                "blocked_data_issues": ["score_ready_market_context_absent"],
            },
            validation_proof_layer={
                "mode": "VALIDATION_PROOF_LAYER_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"validation_proof_layer_completion_pct": 100, "proof_readiness_pct": 0, "blocked_criteria_count": 1},
                "proof_criteria": [{"code": "score_ready_market_context", "status": "blocked"}],
            },
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "PRODUCTIZATION_OPERATOR_WORKFLOW_REVIEW_ONLY")
        self.assertTrue(report["read_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["productization_completion_pct"], 100)
        self.assertEqual(report["summary"]["operator_workflow_step_count"], 5)
        self.assertEqual(report["summary"]["proof_readiness_pct"], 0)
        self.assertEqual(report["summary"]["blocked_criteria_count"], 1)
        self.assertEqual(report["workflow_steps"][0]["name"], "Evidence Layer")
        self.assertEqual(report["workflow_steps"][-1]["name"], "Validation / Proof Layer")
        self.assertIn("run_reports", report["review_paths"])
        self.assertIn("api_review", report["review_paths"])
        self.assertIn("live_execution_locked", report["passed_gates"])
        self.assertIn("wallet_list_mutation_blocked", report["passed_gates"])
        self.assertIn("Do not use this workflow", report["operator_alerts"][0]["message"])


if __name__ == "__main__":
    unittest.main()
