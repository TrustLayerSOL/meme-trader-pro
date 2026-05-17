import unittest

from research.signal_context_layer import build_signal_context_layer_report


class SignalContextLayerTests(unittest.TestCase):
    def base_record(self, record_type="accepted_trade", source="paper_trade"):
        should_trade = record_type in {"accepted_trade", "failed_trade"}
        return {
            "schema_version": 1,
            "record_type": record_type,
            "mint": "MintA",
            "decision_id": f"dec-{record_type}",
            "source": source,
            "wallets": [{"wallet": "WalletA", "score": 80}],
            "signal_context": {
                "schema_version": 2,
                "mint": "MintA",
                "decision_id": f"dec-{record_type}",
                "source": source,
                "signal_type": "wallet_cluster",
                "paper_lane": "main",
                "entry_timestamp": 100.0,
                "triggering_wallets": [{"wallet": "WalletA", "score": 80}],
                "wallet_quality": {"weighted_wallet_score": 3.0},
                "cluster": {"wallet_count": 1, "duration_seconds": 4.0},
                "market": {"price": 0.01, "liquidity": 12000, "market_cap": 44000, "token_age_seconds": 72},
                "risk": {"risk_label": "LOW", "hard_block": False},
                "execution_assumptions": {"estimated_slippage_pct": 2.5, "delay_seconds": 1.0},
                "scoring": {"score": 82, "threshold": 68},
                "market_regime": {"tags": ["strong_runner_environment"]},
            },
            "decision": {
                "action": "paper_open_attempt" if should_trade else "skip",
                "should_trade": should_trade,
                "reason": "test",
                "paper_lane": "main",
                "decision_timestamp": 100.0,
            },
            "later_token_outcome": {"status": "unknown"},
            "replay_assumptions": {"fill_model": "realistic_fill_required", "perfect_fills_allowed": False},
            "research_safety": {
                "decision_time_safe": True,
                "future_outcome_separated": True,
                "shared_context_schema": True,
                "live_execution_locked": True,
            },
        }

    def test_stage2_report_proves_accepted_rejected_and_observed_records_share_context_contract(self):
        records = [
            self.base_record("accepted_trade", "paper_trade"),
            self.base_record("failed_trade", "paper_trade"),
            self.base_record("rejected_signal", "scanner"),
            self.base_record("rejected_signal", "wallet_performance_signal"),
        ]

        report = build_signal_context_layer_report(records, generated_at=123.0)

        self.assertEqual(report["mode"], "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY")
        self.assertTrue(report["read_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["stage2_signal_context_completion_pct"], 100)
        self.assertEqual(report["summary"]["total_records"], 4)
        self.assertEqual(report["summary"]["accepted_trade_records"], 1)
        self.assertEqual(report["summary"]["failed_trade_records"], 1)
        self.assertEqual(report["summary"]["rejected_signal_records"], 2)
        self.assertEqual(report["summary"]["wallet_observation_records"], 1)
        self.assertEqual(report["summary"]["shared_schema_records"], 4)
        self.assertEqual(report["summary"]["decision_time_safe_records"], 4)
        self.assertEqual(report["summary"]["future_outcome_separated_records"], 4)
        self.assertIn("accepted_trade_context_adapter_present", report["passed_gates"])
        self.assertIn("rejected_signal_context_adapter_present", report["passed_gates"])


if __name__ == "__main__":
    unittest.main()
