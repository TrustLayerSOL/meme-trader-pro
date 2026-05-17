import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.market_regime_detection import build_market_regime_detection_report
from utils.build_market_regime_detection import write_market_regime_detection_report


def replay_event(regimes, *, source="rejected_signal", outcome="unknown", fill_status="unknown_liquidity", wallet="WalletA"):
    return {
        "event_id": f"{source}-{wallet}-{outcome}",
        "source_record_type": source,
        "wallets": [{"wallet": wallet}],
        "decision_context": {
            "market_regime": {
                "tags": regimes,
                "reasons": ["fixture reason"],
            }
        },
        "execution_assumptions": {"fill_status": fill_status},
        "later_outcome": {"windows": {"15m": {"outcome_type": outcome}}},
        "research_safety": {"decision_time_safe": True, "future_outcome_separated": True, "leakage_paths": []},
    }


class MarketRegimeDetectionTests(unittest.TestCase):
    def test_report_inventories_regimes_without_driving_scores(self):
        report = build_market_regime_detection_report(
            replay_summary={
                "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
                "live_execution_locked": True,
                "counts": {"events": 5, "unsafe_events": 0},
            },
            replay_events=[
                replay_event(["strong_runner_environment"], source="accepted_trade", outcome="runner", fill_status="fillable_with_assumptions", wallet="WalletA"),
                replay_event(["strong_runner_environment"], source="rejected_signal", outcome="unknown", wallet="WalletB"),
                replay_event(["rug_heavy_environment", "high_volatility"], source="rejected_signal", outcome="rug", fill_status="failed_liquidity_floor", wallet="WalletC"),
                replay_event(["low_liquidity_market"], source="failed_trade", outcome="dead", fill_status="failed_liquidity_floor", wallet="WalletD"),
                replay_event([], source="rejected_signal", outcome="unknown", wallet="WalletE"),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["regime_score_driving_allowed"])
        self.assertEqual(report["summary"]["stage7_regime_detection_completion_pct"], 100)
        self.assertEqual(report["summary"]["events_analyzed"], 5)
        self.assertEqual(report["summary"]["regime_tags_observed"], 5)
        self.assertEqual(report["summary"]["known_15m_outcomes"], 3)
        self.assertEqual(report["summary"]["unknown_regime_events"], 1)
        self.assertIn("regime_tags_indexed", report["passed_gates"])
        self.assertIn("regime_score_driving_blocked", report["passed_gates"])

        runner = next(row for row in report["regime_rows"] if row["regime"] == "strong_runner_environment")
        self.assertEqual(runner["events"], 2)
        self.assertEqual(runner["accepted_trades"], 1)
        self.assertEqual(runner["rejected_signals"], 1)
        self.assertEqual(runner["known_15m_outcomes"], 1)
        self.assertEqual(runner["outcomes_15m"]["runner"], 1)

        rug = next(row for row in report["regime_rows"] if row["regime"] == "rug_heavy_environment")
        self.assertEqual(rug["failed_liquidity_events"], 1)
        self.assertEqual(rug["outcomes_15m"]["rug"], 1)

    def test_report_is_incomplete_without_replay_contract(self):
        report = build_market_regime_detection_report(
            replay_summary={},
            replay_events=[],
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["stage7_regime_detection_completion_pct"], 100)
        self.assertIn("replay_dataset_visible", report["failed_gates"])
        self.assertIn("regime_tags_indexed", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report_from_jsonl(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "summary.json"
            events_path = root / "replay_events.jsonl"
            out_path = root / "market_regime_detection_report.json"
            summary_path.write_text(
                json.dumps({
                    "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
                    "live_execution_locked": True,
                    "counts": {"events": 1, "unsafe_events": 0},
                }),
                encoding="utf-8",
            )
            events_path.write_text(json.dumps(replay_event(["dead_market"], outcome="dead")) + "\n", encoding="utf-8")

            report = write_market_regime_detection_report(
                replay_summary_path=summary_path,
                replay_events_path=events_path,
                output_path=out_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["stage7_regime_detection_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["historical_replay_summary"], str(summary_path))
            self.assertEqual(report["input_paths"]["historical_replay_events"], str(events_path))
            self.assertTrue(out_path.exists())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY")

