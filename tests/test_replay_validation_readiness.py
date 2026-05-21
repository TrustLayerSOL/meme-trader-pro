import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.replay_validation_readiness import build_replay_validation_readiness_report
from utils.build_replay_validation_readiness import write_replay_validation_readiness_report


class ReplayValidationReadinessTests(unittest.TestCase):
    def replay_summary(self):
        return {
            "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
            "live_execution_locked": True,
            "counts": {"events": 100, "accepted_trade": 10, "rejected_signal": 90, "unsafe_events": 0},
            "fill_status_counts": {"fillable_with_assumptions": 20, "failed_liquidity_floor": 5, "unknown_liquidity": 75},
            "window_outcome_counts": {"15m": {"runner": 5, "rug": 3, "dead": 2, "unknown": 90}},
        }

    def stage6_report(self):
        return {
            "mode": "REPLAY_REALISM_STAGE6_READINESS_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "stage6_realism_contract_completion_pct": 100,
                "data_score_readiness_pct": 0,
                "score_ready_records": 0,
            },
            "blocking_data_gaps": ["missing_market_cap"],
        }

    def scorecard(self):
        return {
            "mode": "WALLET_REPLAY_SCORECARD_REVIEW_ONLY",
            "live_execution_locked": True,
            "counts": {"events": 100, "wallets": 12, "co_entry_pairs": 4},
        }

    def ledger(self):
        return {
            "mode": "WALLET_OUTCOME_LEDGER_REVIEW_ONLY",
            "live_execution_locked": True,
            "counts": {"records": 100, "wallets": 12},
            "recommendation_counts": {"HOLD_MORE_DATA": 12},
        }

    def backfill_targets(self):
        return {
            "mode": "WALLET_CANDIDATE_BACKFILL_TARGETS_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "total_targets": 50,
                "needs_wallet_history": 45,
                "needs_outcome_label_backfill": 1,
                "needs_more_replay_events": 0,
                "risk_review": 4,
                "ready_or_hold": 0,
            },
        }

    def forward_outcome_resolution(self):
        return {
            "mode": "FORWARD_OUTCOME_RESOLUTION_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 200,
                "known_15m_outcomes": 120,
                "pending_windows": 5,
                "wallets_affected": 9,
                "tokens_affected": 40,
                "window_outcome_counts": {"flat": 410, "runner": 10, "unknown": 380},
                "status_counts": {"forward_outcome_labeled": 120, "pending_forward_outcome_windows": 5},
                "wallet_list_mutations": 0,
                "auto_trust_mutations": 0,
            },
        }

    def daily_forward_calibration(self):
        return {
            "mode": "DAILY_FORWARD_CALIBRATION_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "days": 2,
                "records": 200,
                "known_15m_outcomes": 120,
                "wallet_list_mutations": 0,
                "auto_trust_mutations": 0,
            },
            "days": [
                {
                    "date": "2026-05-20",
                    "records": 125,
                    "known_15m_outcomes": 75,
                    "outcomes_15m": {"flat": 70, "runner": 5, "unknown": 50},
                    "wallets": 8,
                    "tokens": 30,
                },
                {
                    "date": "2026-05-21",
                    "records": 75,
                    "known_15m_outcomes": 45,
                    "outcomes_15m": {"flat": 45, "unknown": 30},
                    "wallets": 5,
                    "tokens": 20,
                },
            ],
        }

    def test_validation_contract_can_be_complete_while_proof_readiness_is_low(self):
        report = build_replay_validation_readiness_report(
            replay_summary=self.replay_summary(),
            stage6_readiness=self.stage6_report(),
            wallet_replay_scorecard=self.scorecard(),
            wallet_outcome_ledger=self.ledger(),
            wallet_candidate_backfill_targets=self.backfill_targets(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["stage8_validation_contract_completion_pct"], 100)
        self.assertLess(report["summary"]["proof_readiness_pct"], 100)
        self.assertEqual(report["summary"]["known_15m_outcome_rate"], 10)
        self.assertEqual(report["summary"]["fillable_rate"], 20)
        self.assertEqual(report["summary"]["fillability_evidence_rate"], 25)
        self.assertIn("replay_scorecard_matches_event_count", report["passed_gates"])
        self.assertIn("low_known_outcome_coverage", report["evidence_gaps"])
        self.assertIn("Stage 8 validation loop is complete; edge proof remains evidence-limited.", report["operator_summary"])

    def test_forward_calibration_is_reported_without_increasing_historical_proof_readiness(self):
        report = build_replay_validation_readiness_report(
            replay_summary=self.replay_summary(),
            stage6_readiness=self.stage6_report(),
            wallet_replay_scorecard=self.scorecard(),
            wallet_outcome_ledger=self.ledger(),
            wallet_candidate_backfill_targets=self.backfill_targets(),
            forward_outcome_resolution=self.forward_outcome_resolution(),
            daily_forward_calibration=self.daily_forward_calibration(),
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["proof_readiness_pct"], 0)
        self.assertEqual(report["summary"]["forward_known_15m_outcomes"], 120)
        self.assertEqual(report["summary"]["forward_known_15m_outcome_rate"], 60)
        self.assertEqual(report["summary"]["forward_pending_windows"], 5)
        self.assertEqual(report["summary"]["forward_days"], 2)
        self.assertEqual(report["forward_calibration_summary"]["outcomes_15m"]["flat"], 115)
        self.assertIn("Forward calibration is reported separately from historical proof readiness.", report["operator_summary"])

    def test_fillability_target_uses_known_fillability_evidence_not_positive_fills_only(self):
        replay = self.replay_summary()
        replay["fill_status_counts"] = {
            "fillable_with_assumptions": 20,
            "failed_liquidity_floor": 55,
            "unknown_liquidity": 25,
        }
        stage6 = self.stage6_report()
        stage6["summary"]["data_score_readiness_pct"] = 80

        report = build_replay_validation_readiness_report(
            replay_summary=replay,
            stage6_readiness=stage6,
            wallet_replay_scorecard=self.scorecard(),
            wallet_outcome_ledger=self.ledger(),
            wallet_candidate_backfill_targets=self.backfill_targets(),
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["fillable_rate"], 20)
        self.assertEqual(report["summary"]["failed_liquidity_rate"], 55)
        self.assertEqual(report["summary"]["fillability_evidence_rate"], 75)
        self.assertNotIn("low_fillable_coverage", report["evidence_gaps"])

    def test_validation_contract_flags_stale_scorecard(self):
        scorecard = self.scorecard()
        scorecard["counts"]["events"] = 99

        report = build_replay_validation_readiness_report(
            replay_summary=self.replay_summary(),
            stage6_readiness=self.stage6_report(),
            wallet_replay_scorecard=scorecard,
            wallet_outcome_ledger=self.ledger(),
            wallet_candidate_backfill_targets=self.backfill_targets(),
        )

        self.assertLess(report["summary"]["stage8_validation_contract_completion_pct"], 100)
        self.assertIn("replay_scorecard_stale", report["failed_gates"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            stage6 = root / "stage6.json"
            scorecard = root / "scorecard.json"
            ledger = root / "ledger.json"
            targets = root / "targets.json"
            out = root / "stage8.json"
            replay.write_text(json.dumps(self.replay_summary()), encoding="utf-8")
            stage6.write_text(json.dumps(self.stage6_report()), encoding="utf-8")
            scorecard.write_text(json.dumps(self.scorecard()), encoding="utf-8")
            ledger.write_text(json.dumps(self.ledger()), encoding="utf-8")
            targets.write_text(json.dumps(self.backfill_targets()), encoding="utf-8")

            report = write_replay_validation_readiness_report(
                replay_summary_path=replay,
                stage6_readiness_path=stage6,
                wallet_replay_scorecard_path=scorecard,
                wallet_outcome_ledger_path=ledger,
                wallet_candidate_backfill_targets_path=targets,
                report_path=out,
                generated_at=123.0,
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["stage8_validation_contract_completion_pct"], 100)
            self.assertIn("input_paths", report)

    def test_writer_can_include_forward_calibration_inputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            stage6 = root / "stage6.json"
            scorecard = root / "scorecard.json"
            ledger = root / "ledger.json"
            targets = root / "targets.json"
            forward = root / "forward.json"
            daily = root / "daily.json"
            out = root / "stage8.json"
            replay.write_text(json.dumps(self.replay_summary()), encoding="utf-8")
            stage6.write_text(json.dumps(self.stage6_report()), encoding="utf-8")
            scorecard.write_text(json.dumps(self.scorecard()), encoding="utf-8")
            ledger.write_text(json.dumps(self.ledger()), encoding="utf-8")
            targets.write_text(json.dumps(self.backfill_targets()), encoding="utf-8")
            forward.write_text(json.dumps(self.forward_outcome_resolution()), encoding="utf-8")
            daily.write_text(json.dumps(self.daily_forward_calibration()), encoding="utf-8")

            report = write_replay_validation_readiness_report(
                replay_summary_path=replay,
                stage6_readiness_path=stage6,
                wallet_replay_scorecard_path=scorecard,
                wallet_outcome_ledger_path=ledger,
                wallet_candidate_backfill_targets_path=targets,
                forward_outcome_resolution_path=forward,
                daily_forward_calibration_path=daily,
                report_path=out,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["forward_known_15m_outcomes"], 120)
            self.assertIn("forward_outcome_resolution", report["input_paths"])
            self.assertIn("daily_forward_calibration", report["input_paths"])


if __name__ == "__main__":
    unittest.main()
