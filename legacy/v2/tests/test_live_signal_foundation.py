import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.live_signal_foundation import build_live_signal_foundation_report
from utils.build_live_signal_foundation import write_live_signal_foundation_report


def signal_context_report():
    return {
        "mode": "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "stage2_signal_context_completion_pct": 100,
            "total_records": 10,
            "accepted_trade_records": 2,
            "failed_trade_records": 1,
            "rejected_signal_records": 5,
            "wallet_observation_records": 2,
            "shared_schema_records": 10,
            "canonical_context_records": 8,
            "decision_time_market_context_records": 6,
            "decision_time_safe_records": 10,
            "future_outcome_separated_records": 10,
            "decision_time_market_context_coverage_pct": 60,
        },
    }


def replay_summary():
    return {
        "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "events": 10,
            "accepted_trade": 2,
            "failed_trade": 1,
            "rejected_signal": 5,
            "unsafe_events": 0,
        },
    }


class LiveSignalFoundationTests(unittest.TestCase):
    def test_report_marks_stage1_complete_when_signal_path_is_persisted_and_safe(self):
        report = build_live_signal_foundation_report(
            signal_context_layer=signal_context_report(),
            historical_replay_summary=replay_summary(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["stage1_live_signal_foundation_completion_pct"], 100)
        self.assertEqual(report["summary"]["signal_records"], 10)
        self.assertEqual(report["summary"]["historical_replay_events"], 10)
        self.assertEqual(report["summary"]["wallet_observation_records"], 2)
        self.assertEqual(report["summary"]["source_consistency_pct"], 100)
        self.assertEqual(report["summary"]["decision_time_market_context_coverage_pct"], 60)
        self.assertIn("event_persistence_consistent", report["passed_gates"])
        self.assertIn("replay_safety_clean", report["passed_gates"])
        self.assertIn("live_execution_locked", report["passed_gates"])

    def test_report_is_incomplete_without_persisted_replay_events(self):
        report = build_live_signal_foundation_report(
            signal_context_layer=signal_context_report(),
            historical_replay_summary={},
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["stage1_live_signal_foundation_completion_pct"], 100)
        self.assertIn("historical_replay_visible", report["failed_gates"])
        self.assertIn("event_persistence_consistent", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            signal_path = root / "signal_context.json"
            replay_path = root / "summary.json"
            out_path = root / "live_signal_foundation_report.json"
            signal_path.write_text(json.dumps(signal_context_report()), encoding="utf-8")
            replay_path.write_text(json.dumps(replay_summary()), encoding="utf-8")

            report = write_live_signal_foundation_report(
                signal_context_path=signal_path,
                historical_replay_summary_path=replay_path,
                output_path=out_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["stage1_live_signal_foundation_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["signal_context_layer"], str(signal_path))
            self.assertTrue(out_path.exists())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY")

