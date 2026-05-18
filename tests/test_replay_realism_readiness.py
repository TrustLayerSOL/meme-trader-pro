import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.replay_realism_readiness import build_replay_realism_readiness_report
from utils.build_replay_realism_readiness import write_replay_realism_readiness_report


class ReplayRealismReadinessTests(unittest.TestCase):
    def replay_summary(self):
        return {
            "schema_version": "historical_replay_dataset.v1",
            "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
            "live_execution_locked": True,
            "counts": {"events": 10, "unsafe_events": 0},
            "evaluation_windows": ["30s", "2m", "5m", "15m"],
            "fill_status_counts": {
                "fillable_with_assumptions": 3,
                "failed_liquidity_floor": 2,
                "unknown_liquidity": 5,
            },
        }

    def trusted_report(self):
        return {
            "mode": "TRUSTED_HISTORICAL_MARKET_SNAPSHOT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 4,
                "score_ready_records": 0,
                "trust_gate_completion_pct": 100,
                "home_built_onchain_reconstruction_pct": 22,
                "required_field_counts": {"market_cap": 4},
            },
        }

    def supply_report(self):
        return {
            "mode": "ONCHAIN_SUPPLY_EVIDENCE_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 4,
                "supply_recovered_records": 0,
                "needs_archival_supply_records": 4,
                "unsafe_current_only_records": 0,
            },
        }

    def score_ready_context_report(self):
        return {
            "mode": "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "records_scanned": 643,
                "score_ready_records": 43,
                "blocked_missing_price_rows": 9,
                "blocked_missing_liquidity_rows": 2,
                "near_score_ready_records": 589,
            },
        }

    def archival_supply_report(self):
        return {
            "mode": "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY",
            "live_execution_locked": True,
            "summary": {
                "candidate_rows": 591,
                "supply_recovered_records": 2,
                "blocked_missing_snapshot_records": 589,
                "unsafe_current_only_records": 0,
            },
        }

    def test_readiness_marks_stage6_contract_complete_but_data_not_score_ready(self):
        report = build_replay_realism_readiness_report(
            replay_summary=self.replay_summary(),
            trusted_market_context_report=self.trusted_report(),
            supply_evidence_report=self.supply_report(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "REPLAY_REALISM_STAGE6_READINESS_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["stage6_realism_contract_completion_pct"], 100)
        self.assertEqual(report["summary"]["score_ready_records"], 0)
        self.assertEqual(report["summary"]["data_score_readiness_pct"], 0)
        self.assertIn("trusted_market_context_blocks_incomplete_rows", report["passed_gates"])
        self.assertIn("historical_supply_still_missing", report["blocking_data_gaps"])
        self.assertIn("Stage 6 realism gate is complete; market-context coverage remains blocked from scoring.", report["operator_summary"])

    def test_readiness_flags_unsafe_replay_events(self):
        summary = self.replay_summary()
        summary["counts"]["unsafe_events"] = 1

        report = build_replay_realism_readiness_report(
            replay_summary=summary,
            trusted_market_context_report=self.trusted_report(),
            supply_evidence_report=self.supply_report(),
        )

        self.assertLess(report["summary"]["stage6_realism_contract_completion_pct"], 100)
        self.assertIn("decision_time_leakage_present", report["failed_gates"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_path = root / "summary.json"
            trusted_path = root / "trusted.json"
            supply_path = root / "supply.json"
            out_path = root / "readiness.json"
            replay_path.write_text(__import__("json").dumps(self.replay_summary()), encoding="utf-8")
            trusted_path.write_text(__import__("json").dumps(self.trusted_report()), encoding="utf-8")
            supply_path.write_text(__import__("json").dumps(self.supply_report()), encoding="utf-8")

            report = write_replay_realism_readiness_report(
                replay_summary_path=replay_path,
                trusted_market_context_report_path=trusted_path,
                supply_evidence_report_path=supply_path,
                report_path=out_path,
                generated_at=123.0,
            )

            self.assertTrue(out_path.exists())
            self.assertEqual(report["summary"]["stage6_realism_contract_completion_pct"], 100)
            self.assertIn("input_paths", report)

    def test_readiness_accepts_score_ready_classifier_and_archival_supply_schema(self):
        report = build_replay_realism_readiness_report(
            replay_summary=self.replay_summary(),
            trusted_market_context_report=self.score_ready_context_report(),
            supply_evidence_report=self.archival_supply_report(),
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["score_ready_records"], 43)
        self.assertEqual(report["summary"]["historical_market_context_records_scanned"], 643)
        self.assertEqual(report["summary"]["supply_recovered_records"], 2)
        self.assertEqual(report["summary"]["supply_records_scanned"], 591)
        self.assertEqual(report["summary"]["data_score_readiness_pct"], 7)
        self.assertIn("historical_supply_still_missing", report["blocking_data_gaps"])


if __name__ == "__main__":
    unittest.main()
