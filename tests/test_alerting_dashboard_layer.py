import unittest

from research.alerting_dashboard_layer import build_alerting_dashboard_layer_report


class AlertingDashboardLayerTests(unittest.TestCase):
    def test_dashboard_layer_summarizes_gates_and_blockers_without_mutation(self):
        report = build_alerting_dashboard_layer_report(
            evidence_layer={
                "mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "evidence_layer_completion_pct": 100,
                    "wallet_score_readiness_pct": 0,
                    "remaining_blocked_wallets": 36,
                },
                "residual_data_blockers": ["wallet_scores_not_ready"],
            },
            replayable_timelines={
                "mode": "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "replayable_token_timelines_completion_pct": 100,
                    "timeline_data_readiness_pct": 0,
                    "missing_market_context_rows": 643,
                },
                "residual_data_blockers": ["timeline_data_not_score_ready"],
            },
            similar_rug_patterns={
                "mode": "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {
                    "similar_rug_pattern_completion_pct": 100,
                    "rug_pattern_data_readiness_pct": 0,
                    "known_rug_rows": 22,
                    "unknown_rows_excluded_from_rug_labels": 643,
                },
                "residual_data_blockers": ["unknown_outcomes_cannot_be_pattern_matched"],
            },
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["alerting_dashboard_layer_completion_pct"], 100)
        self.assertEqual(report["summary"]["research_data_readiness_pct"], 0)
        self.assertEqual(report["summary"]["completed_gate_count"], 3)
        self.assertEqual(report["summary"]["blocked_data_issue_count"], 3)
        self.assertEqual(report["status_cards"][0]["name"], "Evidence Layer")
        self.assertEqual(report["status_cards"][1]["name"], "Replayable Token Timelines")
        self.assertEqual(report["status_cards"][2]["name"], "Similar-Rug Pattern Matching")
        self.assertIn("live_execution_locked", report["passed_gates"])
        self.assertIn("wallet_list_mutation_blocked", report["passed_gates"])
        self.assertEqual(report["operator_alerts"][0]["severity"], "blocker")
        self.assertIn("Do not promote", report["operator_alerts"][0]["message"])


if __name__ == "__main__":
    unittest.main()
