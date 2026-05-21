import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_signal_operator_rollup import write_forward_signal_operator_rollup
from wallets.forward_signal_operator_rollup import build_forward_signal_operator_rollup


def packet():
    return {
        "wallets": [
            {
                "wallet": "WalletA",
                "rows": [
                    {"token_mint": "MintA", "signal_time": 100.0, "outcome_15m": "runner", "repaired_price": 0.01},
                    {"token_mint": "MintB", "signal_time": 200.0, "outcome_15m": "runner", "repaired_price": 0.02},
                    {"token_mint": "MintC", "signal_time": 300.0, "outcome_15m": "unknown", "repaired_price": 0.03},
                ],
            }
        ],
    }


def validator():
    return {
        "live_execution_locked": True,
        "wallets": [
            {
                "wallet": "WalletA",
                "validation_status": "repeatability_supported_manual_review",
                "runner_rows": 2,
                "runner_distinct_token_mints": 2,
                "runner_signal_span_seconds": 100.0,
                "dominant_runner_token_share": 0.5,
            }
        ],
    }


def decision_prep():
    return {
        "live_execution_locked": True,
        "decisions": [
            {
                "wallet": "WalletA",
                "decision_type": "manual_review_required",
                "approved": False,
                "promotion_allowed": False,
                "required_human_checks": ["inspect wallet", "do not promote from this artifact alone"],
                "wallet_trust_mutation_allowed": False,
                "wallet_list_mutation_allowed": False,
            }
        ],
    }


class ForwardSignalOperatorRollupTests(unittest.TestCase):
    def test_rollup_combines_packet_validator_and_decision_prep_safely(self):
        report = build_forward_signal_operator_rollup(
            packet=packet(),
            validator=validator(),
            decision_prep=decision_prep(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_SIGNAL_OPERATOR_ROLLUP_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["wallets"], 1)
        self.assertEqual(report["summary"]["manual_review_required"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["trust_mutations_allowed"], 0)
        wallet = report["wallets"][0]
        self.assertEqual(wallet["wallet"], "WalletA")
        self.assertEqual(wallet["decision_type"], "manual_review_required")
        self.assertEqual(wallet["validation_status"], "repeatability_supported_manual_review")
        self.assertEqual(wallet["runner_rows"], 2)
        self.assertEqual(wallet["top_token_mints"][0]["token_mint"], "MintA")
        self.assertFalse(wallet["promotion_allowed"])
        self.assertFalse(wallet["wallet_trust_mutation_allowed"])

    def test_writer_persists_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path = root / "packet.json"
            validator_path = root / "validator.json"
            decision_path = root / "decision.json"
            report_path = root / "rollup.json"
            markdown_path = root / "rollup.md"
            packet_path.write_text(json.dumps(packet()), encoding="utf-8")
            validator_path.write_text(json.dumps(validator()), encoding="utf-8")
            decision_path.write_text(json.dumps(decision_prep()), encoding="utf-8")

            report = write_forward_signal_operator_rollup(
                packet_path=packet_path,
                validator_path=validator_path,
                decision_prep_path=decision_path,
                report_path=report_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["wallets"], 1)
            self.assertIn("Forward Signal Operator Rollup", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
