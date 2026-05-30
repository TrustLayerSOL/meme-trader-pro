import unittest

from research.signal_schema import (
    build_record_from_wallet_signal,
    build_record_from_rejection,
    build_record_from_trade,
    build_signal_outcome_record,
)


class ResearchSignalSchemaTests(unittest.TestCase):
    def base_context(self):
        return {
            "schema_version": 2,
            "mint": "MintA",
            "decision_id": "dec-1",
            "signal_type": "wallet_cluster",
            "paper_lane": "main",
            "entry_timestamp": 100.0,
            "triggering_wallets": [
                {"wallet": "WalletA", "score": 80, "label": "GOOD_PERFORMER"},
                {"wallet": "WalletB", "score": 55, "label": "NEUTRAL_PERFORMER"},
            ],
            "cluster": {"wallet_count": 2, "duration_seconds": 11.0},
            "market": {"liquidity": 12_000, "market_cap": 44_000, "token_age_seconds": 52},
            "risk": {"risk_label": "LOW", "hard_block": False},
            "execution_assumptions": {"estimated_slippage_pct": 2.8, "delay_seconds": 1.5},
            "market_regime": {"tags": ["strong_runner_environment"]},
        }

    def test_accepted_and_rejected_records_share_comparable_shape(self):
        accepted = build_signal_outcome_record(
            signal_context=self.base_context(),
            decision={"action": "paper_open_attempt", "should_trade": True, "reason": "wallet cluster passed"},
            later_token_outcome={"status": "closed", "pnl_pct": 41.2, "runner": True},
            trade={"entry_price": 0.01, "close_price": 0.01412, "entry_time": 101.5, "close_time": 201.5},
        )
        rejected = build_signal_outcome_record(
            signal_context=self.base_context(),
            decision={"action": "skip", "should_trade": False, "reason": "liquidity too low"},
            later_token_outcome={"status": "unknown"},
            rejection_reason="liquidity too low",
        )

        self.assertEqual(set(accepted.keys()), set(rejected.keys()))
        self.assertEqual(accepted["wallets"][0]["wallet"], "WalletA")
        self.assertEqual(rejected["decision"]["action"], "skip")
        self.assertTrue(accepted["research_safety"]["decision_time_safe"])
        self.assertTrue(rejected["research_safety"]["shared_context_schema"])
        self.assertEqual(accepted["replay_assumptions"]["fill_model"], "realistic_fill_required")

    def test_rejection_adapter_preserves_rejection_reason_and_context(self):
        row = {
            "decision_id": "dec-2",
            "source": "scanner",
            "rejection reason": "weak wallet score",
            "signal context": self.base_context(),
            "what would have happened afterward if traded": {"status": "unknown"},
        }

        record = build_record_from_rejection(row)

        self.assertEqual(record["record_type"], "rejected_signal")
        self.assertEqual(record["decision"]["reason"], "weak wallet score")
        self.assertEqual(record["later_token_outcome"]["status"], "unknown")

    def test_rejection_adapter_normalizes_legacy_market_info_and_recorded_at(self):
        row = {
            "decision_id": "dec-legacy",
            "recorded_at": 456.0,
            "source": "market_radar",
            "lane": "market_radar",
            "rejection reason": "liquidity_below_hot_lane",
            "mint": "MintLegacy",
            "signal context": {
                "mint": "MintLegacy",
                "signal_type": "market_radar_hot",
                "market_info": {
                    "liquidity": 4_149.91,
                    "market_cap": 5_882.29,
                    "price": 0.00000587,
                },
                "total_score": 15,
                "score_threshold": 70,
            },
            "what would have happened afterward if traded": {"status": "unknown"},
        }

        record = build_record_from_rejection(row)

        self.assertEqual(record["signal_context"]["entry_timestamp"], 456.0)
        self.assertEqual(record["decision"]["decision_timestamp"], 456.0)
        self.assertEqual(record["signal_context"]["market"]["liquidity"], 4_149.91)
        self.assertEqual(record["signal_context"]["market"]["market_cap"], 5_882.29)
        self.assertEqual(record["signal_context"]["market"]["price"], 0.00000587)
        self.assertEqual(record["replay_assumptions"]["liquidity_usd"], 4_149.91)

    def test_trade_adapter_extracts_later_outcome_without_future_decision_inputs(self):
        trade = {
            "decision_id": "dec-3",
            "status": "closed",
            "wallets": ["WalletA"],
            "token_mint": "MintA",
            "entry_time": 100,
            "close_time": 190,
            "entry_price": 0.01,
            "close_price": 0.008,
            "total_pnl_pct": -20,
            "entry_reason": "wallet cluster passed",
            "signal_metadata": {
                "decision_id": "dec-3",
                "paper_lane": "main",
                "token_age_seconds": 60,
                "market_info": {"liquidity": 9_000, "market_cap": 30_000},
            },
        }

        record = build_record_from_trade(trade)

        self.assertEqual(record["record_type"], "accepted_trade")
        self.assertEqual(record["later_token_outcome"]["pnl_pct"], -20)
        self.assertEqual(record["signal_context"]["market"]["token_age_seconds"], 60)
        self.assertTrue(record["research_safety"]["future_outcome_separated"])

    def test_wallet_signal_adapter_preserves_decision_time_context_without_claiming_outcome(self):
        signal = {
            "mint": "MintB",
            "wallets": ["WalletC"],
            "score": 12,
            "should_trade": False,
            "signal_type": "early_signal",
            "time": 123,
            "token_age_seconds": 88,
        }

        record = build_record_from_wallet_signal(signal)

        self.assertEqual(record["record_type"], "rejected_signal")
        self.assertEqual(record["source"], "wallet_performance_signal")
        self.assertEqual(record["wallets"][0]["wallet"], "WalletC")
        self.assertEqual(record["signal_context"]["market"]["token_age_seconds"], 88)
        self.assertEqual(record["later_token_outcome"]["outcome_type"], "unknown")
        self.assertFalse(record["decision"]["should_trade"])


if __name__ == "__main__":
    unittest.main()
