import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.behavioral_intelligence_layer import build_behavioral_intelligence_layer_report
from utils.build_behavioral_intelligence_layer import write_behavioral_intelligence_layer_report


def stage5_report():
    return {
        "mode": "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "stage5_wallet_ecosystem_completion_pct": 100,
            "relationship_data_readiness_pct": 33,
            "cluster_candidates": 1,
        },
        "cluster_candidates": [
            {
                "wallets": ["WalletA", "WalletB", "WalletC"],
                "wallet_count": 3,
                "repeated_edges": 2,
                "total_shared_events": 5,
                "review_priority": "high",
                "review_status": "needs_ecosystem_review",
                "mutation_allowed": False,
            }
        ],
        "residual_data_blockers": ["funding_overlap_source_missing", "deployer_link_source_missing"],
    }


def stage7_report():
    return {
        "mode": "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "regime_score_driving_allowed": False,
        "summary": {
            "stage7_regime_detection_completion_pct": 100,
            "regime_data_readiness_pct": 12,
            "known_15m_outcomes": 3,
            "unknown_regime_events": 2,
        },
        "regime_rows": [
            {
                "regime": "strong_runner_environment",
                "events": 7,
                "known_15m_outcomes": 3,
                "outcomes_15m": {"runner": 2, "rug": 1, "dead": 0, "loser": 0, "unknown": 4},
                "can_drive_wallet_trust": False,
            }
        ],
        "residual_data_blockers": ["regime_outcome_coverage_incomplete"],
    }


def proof_report():
    return {
        "mode": "VALIDATION_PROOF_LAYER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "validation_proof_layer_completion_pct": 100,
            "proof_readiness_pct": 0,
            "blocked_criteria_count": 2,
        },
        "proof_criteria": [
            {"code": "score_ready_market_context", "status": "blocked", "can_drive_wallet_trust": False},
            {"code": "known_outcome_coverage", "status": "blocked", "can_drive_wallet_trust": False},
        ],
    }


class BehavioralIntelligenceLayerTests(unittest.TestCase):
    def test_report_connects_ecosystems_regimes_and_proof_without_mutation(self):
        report = build_behavioral_intelligence_layer_report(
            wallet_ecosystem_intelligence=stage5_report(),
            market_regime_detection=stage7_report(),
            validation_proof_layer=proof_report(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["behavioral_score_driving_allowed"])
        self.assertEqual(report["summary"]["stage9_behavioral_intelligence_completion_pct"], 100)
        self.assertEqual(report["summary"]["behavioral_data_readiness_pct"], 0)
        self.assertEqual(report["summary"]["pattern_candidates"], 1)
        self.assertEqual(report["summary"]["dominant_regime"], "strong_runner_environment")
        self.assertIn("proof_limitations_carried_forward", report["passed_gates"])
        self.assertIn("behavioral_score_driving_blocked", report["passed_gates"])
        self.assertIn("proof_readiness_not_ready", report["residual_data_blockers"])

        candidate = report["behavioral_pattern_candidates"][0]
        self.assertEqual(candidate["wallets"], ["WalletA", "WalletB", "WalletC"])
        self.assertEqual(candidate["dominant_regime"], "strong_runner_environment")
        self.assertEqual(candidate["proof_readiness_pct"], 0)
        self.assertEqual(candidate["pattern_status"], "blocked_needs_evidence")
        self.assertFalse(candidate["can_drive_wallet_trust"])
        self.assertFalse(candidate["mutation_allowed"])

    def test_report_is_incomplete_when_stage5_is_missing(self):
        report = build_behavioral_intelligence_layer_report(
            wallet_ecosystem_intelligence={},
            market_regime_detection=stage7_report(),
            validation_proof_layer=proof_report(),
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["stage9_behavioral_intelligence_completion_pct"], 100)
        self.assertIn("stage5_ecosystem_visible", report["failed_gates"])
        self.assertIn("behavioral_pattern_candidates_visible", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage5_path = root / "stage5.json"
            stage7_path = root / "stage7.json"
            proof_path = root / "proof.json"
            out_path = root / "behavioral_intelligence_layer_report.json"
            stage5_path.write_text(json.dumps(stage5_report()), encoding="utf-8")
            stage7_path.write_text(json.dumps(stage7_report()), encoding="utf-8")
            proof_path.write_text(json.dumps(proof_report()), encoding="utf-8")

            report = write_behavioral_intelligence_layer_report(
                wallet_ecosystem_path=stage5_path,
                market_regime_path=stage7_path,
                validation_proof_path=proof_path,
                output_path=out_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["stage9_behavioral_intelligence_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["wallet_ecosystem_intelligence"], str(stage5_path))
            self.assertTrue(out_path.exists())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY")

