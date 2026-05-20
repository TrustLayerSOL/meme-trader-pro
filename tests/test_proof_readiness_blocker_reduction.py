import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.proof_readiness_blocker_reduction import build_proof_readiness_blocker_reduction_report
from utils.build_proof_readiness_blocker_reduction import DEFAULT_SUPPLY_EVIDENCE, write_proof_readiness_blocker_reduction_report


def behavioral_trust_validation():
    return {
        "mode": "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "behavioral_trust_changes_allowed": False,
        "summary": {
            "behavioral_validation_completion_pct": 100,
            "behavioral_trust_justified": False,
            "validated_patterns": 7,
            "trust_ready_patterns": 0,
            "known_15m_outcomes": 2,
            "known_15m_required": 30,
            "fillable_rate": 6,
            "fillability_evidence_rate": 25,
            "fillable_rate_required": 70,
            "score_ready_market_context_records": 0,
            "proof_readiness_pct": 0,
        },
        "blocked_data_issues": [
            "proof_readiness_below_threshold",
            "insufficient_known_outcome_density",
            "fillable_rate_below_threshold",
            "score_ready_market_context_absent",
        ],
    }


def validation_proof_layer():
    return {
        "mode": "VALIDATION_PROOF_LAYER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "validation_proof_layer_completion_pct": 100,
            "proof_readiness_pct": 0,
            "criteria_count": 12,
            "blocked_criteria_count": 12,
            "stage8_known_15m_outcomes": 2,
            "stage8_fillable_rate": 6,
            "stage8_fillability_evidence_rate": 25,
            "stage8_data_score_readiness_pct": 0,
        },
        "proof_criteria": [
            {"code": "score_ready_market_context", "status": "blocked"},
            {"code": "known_outcome_coverage", "status": "blocked"},
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
            "fillable_events": 353,
            "fillable_rate": 6,
            "fillability_evidence_events": 1400,
            "fillability_evidence_rate": 25,
            "proof_readiness_pct": 0,
        },
        "evidence_gaps": ["low_known_outcome_coverage", "low_market_context_score_readiness"],
    }


def evidence_layer():
    return {
        "mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "evidence_layer_completion_pct": 100,
            "evidence_rows": 1033,
            "needs_outcome_labels": 36,
            "needs_market_context": 32,
            "remaining_blocked_wallets": 36,
            "score_ready_market_context_records": 0,
            "wallet_score_readiness_pct": 0,
        },
    }


def replayable_timelines():
    return {
        "mode": "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "replayable_token_timelines_completion_pct": 100,
            "timeline_data_readiness_pct": 0,
            "target_mints": 77,
            "missing_market_context_rows": 643,
            "wallets_needing_market_context": 32,
            "wallets_needing_outcome_labels": 36,
            "transaction_linkage_blockers": 0,
            "price_recovered_records": 201,
            "liquidity_recovered_records": 86,
            "market_cap_recovered_records": 0,
            "supply_recovered_records": 0,
            "score_ready_records": 0,
        },
        "residual_data_blockers": [
            "decision_time_market_context_requires_reconstruction",
            "known_outcome_coverage_still_low",
            "historical_supply_still_missing",
        ],
    }


def onchain_market_context():
    return {
        "mode": "ONCHAIN_MARKET_CONTEXT_RECOVERY_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "records_scanned": 643,
            "price_recovered_records": 201,
            "liquidity_recovered_records": 86,
            "market_cap_recovered_records": 0,
            "score_ready_candidate_records": 0,
            "block_reasons": {
                "blocked_missing_liquidity": 445,
                "blocked_missing_market_cap": 393,
                "blocked_missing_price": 250,
                "blocked_missing_onchain_pool_reserves": 436,
            },
        },
    }


def supply_evidence():
    return {
        "mode": "ONCHAIN_SUPPLY_EVIDENCE_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "records_scanned": 643,
            "supply_recovered_records": 0,
            "needs_archival_supply_records": 643,
        },
        "next_required_actions": ["Fetch or reconstruct historical mint-account supply at or before the decision slot."],
    }


class ProofReadinessBlockerReductionTests(unittest.TestCase):
    def test_default_supply_input_uses_archival_supply_evidence_report(self):
        self.assertEqual(DEFAULT_SUPPLY_EVIDENCE.name, "archival_supply_evidence_report.json")

    def test_report_keeps_historical_supply_blocker_when_archival_evidence_is_partial(self):
        partial_supply = {
            "mode": "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY",
            "review_only": True,
            "live_execution_locked": True,
            "wallet_list_mutated": False,
            "summary": {
                "candidate_rows": 591,
                "supply_recovered_records": 60,
                "blocked_missing_snapshot_records": 531,
                "status_counts": {
                    "archival_supply_recovered": 60,
                    "blocked_missing_archival_snapshot": 531,
                },
            },
        }
        report = build_proof_readiness_blocker_reduction_report(
            behavioral_trust_validation=behavioral_trust_validation(),
            validation_proof_layer=validation_proof_layer(),
            stage8_validation=stage8_validation(),
            evidence_layer=evidence_layer(),
            replayable_token_timelines=replayable_timelines(),
            onchain_market_context=onchain_market_context(),
            supply_evidence=partial_supply,
            generated_at=123.0,
        )

        self.assertIn("historical_supply", report["reduction_queue"][0]["blocked_by"])
        self.assertTrue(any(row["category"] == "archival_supply_evidence" for row in report["reduction_queue"]))

    def test_report_prioritizes_exact_proof_blockers_without_mutation(self):
        report = build_proof_readiness_blocker_reduction_report(
            behavioral_trust_validation=behavioral_trust_validation(),
            validation_proof_layer=validation_proof_layer(),
            stage8_validation=stage8_validation(),
            evidence_layer=evidence_layer(),
            replayable_token_timelines=replayable_timelines(),
            onchain_market_context=onchain_market_context(),
            supply_evidence=supply_evidence(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["behavioral_trust_changes_allowed"])
        self.assertEqual(report["summary"]["blocker_reduction_completion_pct"], 100)
        self.assertFalse(report["summary"]["behavioral_trust_justified"])
        self.assertEqual(report["summary"]["known_15m_needed"], 28)
        self.assertEqual(report["summary"]["fillability_evidence_gap"], 45)
        self.assertEqual(report["summary"]["positive_fill_rate"], 6)
        self.assertEqual(report["summary"]["score_ready_market_context_records"], 0)
        self.assertGreaterEqual(report["summary"]["next_action_count"], 3)
        self.assertEqual(report["reduction_queue"][0]["priority"], 1)
        self.assertEqual(report["reduction_queue"][0]["category"], "score_ready_market_context")
        self.assertIn("historical_supply", report["reduction_queue"][0]["blocked_by"])
        self.assertIn("missing_onchain_pool_reserves", report["reduction_queue"][2]["blocked_by"])
        self.assertIn("trust_stays_blocked", report["passed_gates"])

    def test_report_is_incomplete_when_behavioral_trust_gate_is_missing(self):
        report = build_proof_readiness_blocker_reduction_report(
            behavioral_trust_validation={},
            validation_proof_layer=validation_proof_layer(),
            stage8_validation=stage8_validation(),
            evidence_layer=evidence_layer(),
            replayable_token_timelines=replayable_timelines(),
            onchain_market_context=onchain_market_context(),
            supply_evidence=supply_evidence(),
            generated_at=123.0,
        )

        self.assertLess(report["summary"]["blocker_reduction_completion_pct"], 100)
        self.assertIn("behavioral_trust_validation_visible", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "behavioral": root / "behavioral.json",
                "proof": root / "proof.json",
                "stage8": root / "stage8.json",
                "evidence": root / "evidence.json",
                "timelines": root / "timelines.json",
                "onchain": root / "onchain.json",
                "supply": root / "supply.json",
                "out": root / "proof_readiness_blocker_reduction_report.json",
            }
            paths["behavioral"].write_text(json.dumps(behavioral_trust_validation()), encoding="utf-8")
            paths["proof"].write_text(json.dumps(validation_proof_layer()), encoding="utf-8")
            paths["stage8"].write_text(json.dumps(stage8_validation()), encoding="utf-8")
            paths["evidence"].write_text(json.dumps(evidence_layer()), encoding="utf-8")
            paths["timelines"].write_text(json.dumps(replayable_timelines()), encoding="utf-8")
            paths["onchain"].write_text(json.dumps(onchain_market_context()), encoding="utf-8")
            paths["supply"].write_text(json.dumps(supply_evidence()), encoding="utf-8")

            report = write_proof_readiness_blocker_reduction_report(
                behavioral_trust_validation_path=paths["behavioral"],
                validation_proof_path=paths["proof"],
                stage8_validation_path=paths["stage8"],
                evidence_layer_path=paths["evidence"],
                replayable_token_timelines_path=paths["timelines"],
                onchain_market_context_path=paths["onchain"],
                supply_evidence_path=paths["supply"],
                output_path=paths["out"],
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["blocker_reduction_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["behavioral_trust_validation"], str(paths["behavioral"]))
            saved = json.loads(paths["out"].read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
