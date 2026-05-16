import unittest

from research.similar_rug_patterns import build_similar_rug_patterns_report


class SimilarRugPatternsTests(unittest.TestCase):
    def test_similar_rug_layer_completes_without_labeling_unknowns_as_rugs(self):
        report = build_similar_rug_patterns_report(
            wallet_evidence_enrichment={
                "live_execution_locked": True,
                "summary": {
                    "total_evidence_rows": 5,
                    "rows_with_known_outcome": 2,
                    "rug_rows": 1,
                    "runner_rows": 1,
                    "missing_outcome_label_rows": 3,
                },
                "evidence_records": [
                    {
                        "wallet": "WalletRug",
                        "token_mint": "MintRug",
                        "observed_action": "buy",
                        "later_token_outcome": {"outcome_type": "rug", "rug": True},
                        "estimated_entry_context": {"liquidity": 12000, "market_cap": 4000},
                    },
                    {
                        "wallet": "WalletUnknown",
                        "token_mint": "MintUnknown",
                        "observed_action": "buy",
                        "later_token_outcome": {"outcome_type": "unknown", "rug": False},
                    },
                ],
            },
            wallet_outcome_ledger={
                "live_execution_locked": True,
                "counts": {"wallets": 2, "records": 5},
                "wallets": {
                    "WalletRug": {
                        "wallet": "WalletRug",
                        "known_outcomes": 1,
                        "rug_participation": 1,
                        "rug_participation_rate": 1.0,
                        "runner_participation_rate": 0.0,
                    },
                    "WalletUnknown": {
                        "wallet": "WalletUnknown",
                        "known_outcomes": 0,
                        "rug_participation": 0,
                        "rug_participation_rate": 0.0,
                    },
                },
            },
            wallet_replay_scorecard={
                "live_execution_locked": True,
                "counts": {"wallets": 2, "events": 5},
                "wallets": {
                    "WalletRug": {
                        "wallet": "WalletRug",
                        "windows": {"15m": {"known": 1, "rug": 1, "unknown": 0}},
                    }
                },
            },
            replayable_token_timelines={
                "live_execution_locked": True,
                "summary": {
                    "replayable_token_timelines_completion_pct": 100,
                    "timeline_data_readiness_pct": 0,
                    "missing_market_context_rows": 3,
                },
                "timeline_targets": [
                    {"token_mint": "MintUnknown", "unknown_outcome_rows": 3, "known_outcome_rows": 0}
                ],
            },
            generated_at=123.0,
            limit=10,
        )

        self.assertEqual(report["mode"], "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["similar_rug_pattern_completion_pct"], 100)
        self.assertEqual(report["summary"]["known_rug_rows"], 1)
        self.assertEqual(report["summary"]["unknown_rows_excluded_from_rug_labels"], 3)
        self.assertEqual(report["summary"]["rug_exposed_wallets"], 1)
        self.assertIn("unknown_outcomes_excluded", report["passed_gates"])
        self.assertEqual(report["rug_pattern_targets"][0]["token_mint"], "MintRug")
        self.assertEqual(report["rug_exposed_wallets"][0]["wallet"], "WalletRug")


if __name__ == "__main__":
    unittest.main()
