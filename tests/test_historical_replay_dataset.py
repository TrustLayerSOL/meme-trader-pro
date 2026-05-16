import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.historical_replay_dataset import (
    build_historical_replay_dataset,
    build_replay_event,
    validate_decision_time_safety,
)
from utils.build_historical_replay_dataset import write_replay_dataset_files


class HistoricalReplayDatasetTests(unittest.TestCase):
    def base_unified_record(self, *, record_type="rejected_signal"):
        return {
            "schema_version": 1,
            "record_type": record_type,
            "mint": "MintA",
            "decision_id": "dec-1",
            "source": "wallet_performance_signal",
            "wallets": [{"wallet": "WalletA", "score": 82}],
            "signal_context": {
                "mint": "MintA",
                "decision_id": "dec-1",
                "source": "wallet_performance_signal",
                "signal_type": "wallet_cluster",
                "entry_timestamp": 100.0,
                "triggering_wallets": [{"wallet": "WalletA", "score": 82}],
                "cluster": {"wallet_count": 1, "duration_seconds": 4.5},
                "market": {
                    "liquidity": 12_000,
                    "market_cap": 44_000,
                    "token_age_seconds": 72,
                },
                "risk": {"risk_label": "LOW", "hard_block": False},
                "execution_assumptions": {
                    "estimated_slippage_pct": 2.5,
                    "delay_seconds": 1.0,
                },
                "market_regime": {"tags": ["runner_heavy"]},
            },
            "decision": {
                "action": "skip" if record_type == "rejected_signal" else "paper_open_attempt",
                "should_trade": record_type == "accepted_trade",
                "reason": "wallet score below threshold",
                "paper_lane": "main",
                "decision_timestamp": 100.0,
            },
            "later_token_outcome": {
                "status": "snapshot_evaluated",
                "outcome_type": "runner",
                "runner": True,
                "rug": False,
                "dead": False,
                "max_favorable_excursion_pct": 84.0,
                "windows": {
                    "30s": {"outcome_type": "runner", "runner": True, "rug": False, "dead": False},
                    "2m": {"outcome_type": "runner", "runner": True, "rug": False, "dead": False},
                    "5m": {"outcome_type": "loser", "runner": False, "rug": False, "dead": False},
                    "15m": {"outcome_type": "rug", "runner": False, "rug": True, "dead": False},
                },
            },
            "replay_assumptions": {
                "fill_model": "realistic_fill_required",
                "perfect_fills_allowed": False,
                "slippage_estimate_pct": 2.5,
                "latency_seconds": 1.0,
                "liquidity_usd": 12_000,
            },
        }

    def test_replay_event_separates_decision_context_from_later_outcome(self):
        event = build_replay_event(self.base_unified_record())

        self.assertEqual(event["schema_version"], "historical_replay_event.v1")
        self.assertEqual(event["event_id"], "dec-1")
        self.assertEqual(event["mint"], "MintA")
        self.assertEqual(event["wallets"][0]["wallet"], "WalletA")
        self.assertEqual(event["decision"]["action"], "skip")
        self.assertEqual(event["decision_context"]["market"]["liquidity"], 12_000)
        self.assertEqual(event["later_outcome"]["outcome_type"], "runner")
        self.assertEqual(event["later_outcome"]["windows"]["15m"]["outcome_type"], "rug")
        self.assertNotIn("later_token_outcome", event["decision_context"])
        self.assertTrue(event["research_safety"]["decision_time_safe"])
        self.assertFalse(event["execution_assumptions"]["perfect_fills_allowed"])

    def test_replay_event_declares_fixed_evaluation_windows(self):
        event = build_replay_event(self.base_unified_record())

        self.assertEqual(
            event["evaluation_windows"],
            [
                {"label": "30s", "seconds": 30},
                {"label": "2m", "seconds": 120},
                {"label": "5m", "seconds": 300},
                {"label": "15m", "seconds": 900},
            ],
        )

    def test_execution_assumptions_include_realistic_fill_controls(self):
        record = self.base_unified_record()
        record["replay_assumptions"] = {}
        record["signal_context"]["market"]["liquidity"] = 800

        event = build_replay_event(record)

        self.assertEqual(event["execution_assumptions"]["fill_status"], "failed_liquidity_floor")
        self.assertEqual(event["execution_assumptions"]["liquidity_floor_usd"], 1_000)
        self.assertEqual(event["execution_assumptions"]["entry_liquidity_usd"], 800)
        self.assertGreater(event["execution_assumptions"]["slippage_bps"], 0)
        self.assertGreater(event["execution_assumptions"]["latency_seconds"], 0)
        self.assertFalse(event["execution_assumptions"]["perfect_fills_allowed"])

    def test_execution_assumptions_model_partial_fill_when_size_exceeds_liquidity_depth(self):
        record = self.base_unified_record()
        record["replay_assumptions"] = {
            "position_size_usd": 500,
            "liquidity_usd": 10_000,
            "max_position_liquidity_pct": 1.0,
            "slippage_estimate_pct": 2.5,
        }

        event = build_replay_event(record)
        assumptions = event["execution_assumptions"]

        self.assertEqual(assumptions["fill_status"], "partial_fill_limited")
        self.assertEqual(assumptions["requested_entry_usd"], 500)
        self.assertEqual(assumptions["max_fill_usd"], 100)
        self.assertEqual(assumptions["expected_fill_usd"], 100)
        self.assertEqual(assumptions["fill_ratio"], 0.2)
        self.assertTrue(assumptions["partial_fill"])
        self.assertEqual(assumptions["entry_effective_price_multiplier"], 1.025)

    def test_execution_assumptions_include_exit_realism_and_execution_timestamps(self):
        record = self.base_unified_record()
        record["replay_assumptions"] = {
            "position_size_usd": 50,
            "liquidity_usd": 10_000,
            "latency_seconds": 1.5,
            "exit_latency_seconds": 2.0,
            "sell_slippage_estimate_pct": 4.0,
        }

        event = build_replay_event(record)
        assumptions = event["execution_assumptions"]

        self.assertEqual(assumptions["entry_executable_at"], 101.5)
        self.assertEqual(assumptions["exit_latency_seconds"], 2.0)
        self.assertEqual(assumptions["exit_slippage_estimate_pct"], 4.0)
        self.assertEqual(assumptions["exit_effective_price_multiplier"], 0.96)
        self.assertFalse(assumptions["partial_exit_assumed"])

    def test_leakage_validator_rejects_future_fields_inside_decision_context(self):
        event = build_replay_event(self.base_unified_record())
        event["decision_context"]["future_price"] = 0.02

        safety = validate_decision_time_safety(event)

        self.assertFalse(safety["decision_time_safe"])
        self.assertIn("decision_context.future_price", safety["leakage_paths"])

    def test_replay_event_preserves_legacy_market_info_context(self):
        record = self.base_unified_record()
        record["signal_context"] = {
            "mint": "MintA",
            "decision_id": "dec-legacy",
            "source": "market_radar",
            "signal_type": "market_radar_hot",
            "captured_at": 99.0,
            "market_info": {"liquidity": 4_200, "market_cap": 9_100, "price": 0.0000091},
            "hard_block": False,
            "holder_concentration_risk": "UNKNOWN",
            "score_reasons_tail": ["BLOCK: score_below_market_radar_threshold"],
            "total_score": 15,
            "score_threshold": 70,
        }

        event = build_replay_event(record)

        self.assertEqual(event["decision_context"]["market"]["liquidity"], 4_200)
        self.assertEqual(event["decision_context"]["risk"]["holder_concentration_risk"], "UNKNOWN")
        self.assertEqual(event["decision_context"]["scoring"]["score"], 15)

    def test_dataset_contains_accepted_and_rejected_records_with_summary_counts(self):
        accepted = self.base_unified_record(record_type="accepted_trade")
        rejected = self.base_unified_record(record_type="rejected_signal")
        rejected["signal_context"]["market"]["liquidity"] = 500
        rejected["replay_assumptions"] = {}
        dataset = build_historical_replay_dataset([accepted, rejected], generated_at=123.0)

        self.assertEqual(dataset["schema_version"], "historical_replay_dataset.v1")
        self.assertEqual(dataset["generated_at"], 123.0)
        self.assertEqual(dataset["counts"]["events"], 2)
        self.assertEqual(dataset["counts"]["accepted_trade"], 1)
        self.assertEqual(dataset["counts"]["rejected_signal"], 1)
        self.assertEqual(dataset["counts"]["unsafe_events"], 0)
        self.assertEqual(dataset["fill_status_counts"]["fillable_with_assumptions"], 1)
        self.assertEqual(dataset["fill_status_counts"]["failed_liquidity_floor"], 1)
        self.assertEqual(dataset["evaluation_windows"], ["30s", "2m", "5m", "15m"])
        self.assertEqual(dataset["window_outcome_counts"]["30s"]["runner"], 2)
        self.assertEqual(dataset["window_outcome_counts"]["15m"]["rug"], 2)
        self.assertEqual(
            {event["source_record_type"] for event in dataset["events"]},
            {"accepted_trade", "rejected_signal"},
        )

    def test_writer_creates_jsonl_events_and_summary(self):
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = write_replay_dataset_files(
                [self.base_unified_record(record_type="accepted_trade")],
                out_dir=out_dir,
                generated_at=123.0,
            )

            self.assertEqual(result["summary_path"], str(out_dir / "summary.json"))
            self.assertEqual(result["events_path"], str(out_dir / "replay_events.jsonl"))
            self.assertTrue((out_dir / "summary.json").exists())
            self.assertTrue((out_dir / "replay_events.jsonl").exists())
            self.assertIn('"schema_version": "historical_replay_event.v1"', (out_dir / "replay_events.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
