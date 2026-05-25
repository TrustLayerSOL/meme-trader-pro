import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_walk_forward_paper_readiness_gate import write_candidate_walk_forward_paper_readiness_gate
from wallets.candidate_walk_forward_paper_readiness_gate import build_candidate_walk_forward_paper_readiness_gate


def survivor_wallet(wallet, *, proof=100, excluded=0, validation=40, validation_runners=8, token_count=20, conclusion="continued_validation"):
    return {
        "wallet_address": wallet,
        "walk_forward_conclusion": conclusion,
        "paper_simulation_readiness": "not_ready",
        "candidate_records": proof + excluded,
        "proof_metric_records": proof,
        "excluded_records": excluded,
        "train": {"clean_records": max(1, proof - validation), "runner_count": 10, "runner_rate": 0.2, "token_count": 30},
        "validation": {
            "clean_records": validation,
            "runner_count": validation_runners,
            "runner_rate": round(validation_runners / validation, 4) if validation else 0.0,
            "token_count": token_count,
        },
        "reasons_not_to_trust": ["candidate_validation_layer_only"],
    }


class CandidateWalkForwardPaperReadinessGateTests(unittest.TestCase):
    def test_marks_survivors_not_ready_when_clean_sample_and_context_gate_fail(self):
        survivor_review = {
            "summary": {"survivor_wallets": 2},
            "wallets": [
                survivor_wallet("WalletA", proof=19, excluded=36, validation=6, validation_runners=5, token_count=6),
                survivor_wallet("WalletB", proof=16, excluded=102, validation=5, validation_runners=3, token_count=5),
            ],
        }

        report = build_candidate_walk_forward_paper_readiness_gate(
            survivor_review=survivor_review,
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["wallets_evaluated"], 2)
        self.assertEqual(report["summary"]["eligible_for_manual_paper_simulation_review"], 0)
        self.assertTrue(all(row["paper_readiness_status"] == "not_ready" for row in report["wallets"]))
        self.assertIn("min_total_clean_rows_not_met", report["wallets"][0]["failed_gates"])
        self.assertIn("max_excluded_rate_exceeded", report["wallets"][1]["failed_gates"])
        self.assertFalse(report["paper_simulation_enabled"])
        self.assertFalse(report["promotion_allowed"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])

    def test_marks_wallet_eligible_only_for_manual_review_when_all_gates_pass(self):
        survivor_review = {
            "wallets": [
                survivor_wallet("WalletA", proof=150, excluded=10, validation=50, validation_runners=10, token_count=25),
            ],
        }

        report = build_candidate_walk_forward_paper_readiness_gate(
            survivor_review=survivor_review,
            generated_at=1000.0,
        )
        wallet = report["wallets"][0]

        self.assertEqual(wallet["paper_readiness_status"], "eligible_for_manual_paper_simulation_review")
        self.assertEqual(wallet["failed_gates"], [])
        self.assertIn("manual_operator_review_required_before_any_paper_simulation", wallet["required_next_steps"])
        self.assertFalse(wallet["paper_simulation_enabled"])
        self.assertFalse(wallet["promotion_allowed"])

    def test_rejects_non_survivor_conclusions_from_paper_readiness(self):
        survivor_review = {
            "wallets": [
                survivor_wallet("WalletA", proof=150, excluded=0, validation=50, validation_runners=10, token_count=25, conclusion="degraded"),
            ],
        }

        report = build_candidate_walk_forward_paper_readiness_gate(
            survivor_review=survivor_review,
            generated_at=1000.0,
        )

        wallet = report["wallets"][0]
        self.assertEqual(wallet["paper_readiness_status"], "not_ready")
        self.assertIn("walk_forward_conclusion_not_continued_validation", wallet["failed_gates"])

    def test_writer_exports_deterministic_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            survivor_review_path = root / "survivor.json"
            output_dir = root / "out"
            survivor_review = {
                "wallets": [
                    survivor_wallet("WalletA", proof=150, excluded=10, validation=50, validation_runners=10, token_count=25),
                ],
            }
            survivor_review_path.write_text(json.dumps(survivor_review, sort_keys=True), encoding="utf-8")

            report = write_candidate_walk_forward_paper_readiness_gate(
                survivor_review_path=survivor_review_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            json_path = output_dir / "candidate_walk_forward_paper_readiness_gate_fixed.json"
            csv_path = output_dir / "candidate_walk_forward_paper_readiness_gate_fixed.csv"
            md_path = output_dir / "candidate_walk_forward_paper_readiness_gate_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["generated_at"], 1000.0)
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("eligible_for_manual_paper_simulation_review", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Candidate Walk-Forward Paper Readiness Gate", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
