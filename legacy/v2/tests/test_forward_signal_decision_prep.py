import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_signal_decision_prep import write_forward_signal_decision_prep
from wallets.forward_signal_decision_prep import build_forward_signal_decision_prep


def validator_wallet(status: str = "repeatability_supported_manual_review"):
    return {
        "wallet": "WalletA",
        "validation_status": status,
        "runner_rows": 12,
        "total_review_rows": 16,
        "runner_distinct_token_mints": 6,
        "runner_signal_span_seconds": 7200.0,
        "dominant_runner_token_share": 0.25,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def packet_wallet():
    return {
        "wallet": "WalletA",
        "rows": [
            {
                "event_id": "evt-1",
                "token_mint": "MintA",
                "signal_time": 100.0,
                "repaired_price": 0.01,
                "outcome_15m": "runner",
            }
        ],
    }


class ForwardSignalDecisionPrepTests(unittest.TestCase):
    def test_prepares_manual_review_decision_without_trust_or_list_mutation(self):
        report = build_forward_signal_decision_prep(
            validator={
                "live_execution_locked": True,
                "wallets": [validator_wallet()],
            },
            packet={"wallets": [packet_wallet()]},
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_SIGNAL_DECISION_PREP_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["prepared_decisions"], 1)
        self.assertEqual(report["summary"]["manual_review_required"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["trust_mutations_allowed"], 0)
        decision = report["decisions"][0]
        self.assertEqual(decision["wallet"], "WalletA")
        self.assertEqual(decision["decision_type"], "manual_review_required")
        self.assertFalse(decision["approved"])
        self.assertFalse(decision["promotion_allowed"])
        self.assertFalse(decision["wallet_trust_mutation_allowed"])
        self.assertEqual(decision["evidence"]["runner_rows"], 12)
        self.assertEqual(decision["sample_rows"][0]["token_mint"], "MintA")

    def test_unsupported_wallets_are_held_out_of_decision_prep(self):
        report = build_forward_signal_decision_prep(
            validator={"live_execution_locked": True, "wallets": [validator_wallet("concentrated_anomaly_hold_review")]},
            packet={"wallets": [packet_wallet()]},
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["prepared_decisions"], 0)
        self.assertEqual(report["summary"]["held_out_wallets"], 1)
        self.assertEqual(report["held_out_wallets"][0]["wallet"], "WalletA")

    def test_writer_persists_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            validator_path = root / "validator.json"
            packet_path = root / "packet.json"
            report_path = root / "decision_prep.json"
            csv_path = root / "decision_prep.csv"
            markdown_path = root / "decision_prep.md"
            validator_path.write_text(json.dumps({"live_execution_locked": True, "wallets": [validator_wallet()]}), encoding="utf-8")
            packet_path.write_text(json.dumps({"wallets": [packet_wallet()]}), encoding="utf-8")

            report = write_forward_signal_decision_prep(
                validator_path=validator_path,
                packet_path=packet_path,
                report_path=report_path,
                csv_path=csv_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["prepared_decisions"], 1)
            self.assertIn("Forward Signal Decision Prep", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
