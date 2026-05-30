import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.behavioral_trust_validation import build_behavioral_trust_validation_report
from utils.build_behavioral_trust_validation import write_behavioral_trust_validation_report


def behavioral_layer():
    return {
        "mode": "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "behavioral_score_driving_allowed": False,
        "summary": {
            "stage9_behavioral_intelligence_completion_pct": 100,
            "pattern_candidates": 2,
            "proof_readiness_pct": 0,
            "known_15m_outcomes": 2,
            "behavioral_data_readiness_pct": 0,
        },
        "behavioral_pattern_candidates": [
            {
                "pattern_id": "behavioral-cluster-001",
                "wallets": ["WalletA", "WalletB"],
                "total_shared_events": 5,
                "dominant_regime": "unknown",
                "regime_known_15m_outcomes": 2,
                "proof_readiness_pct": 0,
                "can_drive_wallet_trust": False,
                "mutation_allowed": False,
            },
            {
                "pattern_id": "behavioral-cluster-002",
                "wallets": ["WalletC", "WalletD"],
                "total_shared_events": 2,
                "dominant_regime": "strong_runner_environment",
                "regime_known_15m_outcomes": 0,
                "proof_readiness_pct": 0,
                "can_drive_wallet_trust": False,
                "mutation_allowed": False,
            },
        ],
    }


def validation_proof():
    return {
        "mode": "VALIDATION_PROOF_LAYER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "validation_proof_layer_completion_pct": 100,
            "proof_readiness_pct": 0,
            "blocked_criteria_count": 2,
            "stage8_known_15m_outcomes": 2,
            "stage8_fillable_rate": 6,
            "stage8_fillability_evidence_rate": 25,
            "stage8_data_score_readiness_pct": 0,
        },
        "proof_criteria": [
            {"code": "known_outcome_coverage", "status": "blocked"},
            {"code": "score_ready_market_context", "status": "blocked"},
        ],
    }


def stage8_validation():
    return {
        "mode": "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "stage8_validation_contract_completion_pct": 100,
            "events": 6042,
            "known_15m_outcomes": 2,
            "known_15m_outcome_rate": 0,
            "fillable_rate": 6,
            "fillability_evidence_rate": 25,
            "proof_readiness_pct": 0,
            "stage6_data_score_readiness_pct": 0,
        },
    }


def evidence_layer():
    return {
        "mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "evidence_layer_completion_pct": 100,
            "wallet_score_readiness_pct": 0,
            "rows_with_known_outcome": 24,
            "score_ready_market_context_records": 0,
            "remaining_blocked_wallets": 36,
        },
    }


class BehavioralTrustValidationTests(unittest.TestCase):
    def test_report_blocks_behavioral_trust_when_proof_and_context_are_not_ready(self):
        report = build_behavioral_trust_validation_report(
            behavioral_intelligence_layer=behavioral_layer(),
            validation_proof_layer=validation_proof(),
            stage8_validation=stage8_validation(),
            evidence_layer=evidence_layer(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["behavioral_trust_changes_allowed"])
        self.assertFalse(report["summary"]["behavioral_trust_justified"])
        self.assertEqual(report["summary"]["behavioral_validation_completion_pct"], 100)
        self.assertEqual(report["summary"]["validated_patterns"], 2)
        self.assertEqual(report["summary"]["trust_ready_patterns"], 0)
        self.assertIn("insufficient_known_outcome_density", report["blocked_data_issues"])
        self.assertIn("score_ready_market_context_absent", report["blocked_data_issues"])
        self.assertIn("behavioral_trust_blocked", report["passed_gates"])

        row = report["pattern_validations"][0]
        self.assertEqual(row["trust_verdict"], "not_justified")
        self.assertFalse(row["can_drive_wallet_trust"])
        self.assertIn("proof_readiness_below_threshold", row["blocking_reasons"])
        self.assertIn("market_context_not_score_ready", row["blocking_reasons"])

    def test_report_is_incomplete_without_behavioral_patterns(self):
        report = build_behavioral_trust_validation_report(
            behavioral_intelligence_layer={},
            validation_proof_layer=validation_proof(),
            stage8_validation=stage8_validation(),
            evidence_layer=evidence_layer(),
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["behavioral_validation_completion_pct"], 100)
        self.assertIn("behavioral_patterns_visible", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            behavioral_path = root / "behavioral.json"
            proof_path = root / "proof.json"
            stage8_path = root / "stage8.json"
            evidence_path = root / "evidence.json"
            out_path = root / "behavioral_trust_validation_report.json"
            behavioral_path.write_text(json.dumps(behavioral_layer()), encoding="utf-8")
            proof_path.write_text(json.dumps(validation_proof()), encoding="utf-8")
            stage8_path.write_text(json.dumps(stage8_validation()), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence_layer()), encoding="utf-8")

            report = write_behavioral_trust_validation_report(
                behavioral_intelligence_path=behavioral_path,
                validation_proof_path=proof_path,
                stage8_validation_path=stage8_path,
                evidence_layer_path=evidence_path,
                output_path=out_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["behavioral_validation_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["behavioral_intelligence_layer"], str(behavioral_path))
            self.assertTrue(out_path.exists())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY")
