import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_signal_review_validator import write_forward_signal_review_validator
from wallets.forward_signal_review_validator import build_forward_signal_review_validator


def row(mint: str, signal_time: float, outcome: str = "runner"):
    return {
        "event_id": f"{mint}-{signal_time}",
        "token_mint": mint,
        "signal_time": signal_time,
        "outcome_15m": outcome,
        "repaired_price": 0.01,
    }


def packet(rows):
    return {
        "mode": "FORWARD_SIGNAL_REVIEW_PACKET_REVIEW_ONLY",
        "live_execution_locked": True,
        "wallets": [
            {
                "wallet": "WalletA",
                "review_only": True,
                "recommendation_action": "REVIEW_FORWARD_SIGNAL_MANUALLY",
                "rows": rows,
            }
        ],
    }


class ForwardSignalReviewValidatorTests(unittest.TestCase):
    def test_marks_wallet_as_repeatability_supported_without_allowing_mutation(self):
        report = build_forward_signal_review_validator(
            packet=packet(
                [
                    row("MintA", 100.0),
                    row("MintB", 2000.0),
                    row("MintC", 4000.0),
                    row("MintD", 8000.0),
                    row("MintE", 12000.0),
                    row("MintA", 12500.0, "unknown"),
                ]
            ),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_SIGNAL_REVIEW_VALIDATOR_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["validated_wallets"], 1)
        self.assertEqual(report["summary"]["repeatability_supported_wallets"], 1)
        self.assertEqual(report["summary"]["trust_mutations_allowed"], 0)
        wallet = report["wallets"][0]
        self.assertEqual(wallet["validation_status"], "repeatability_supported_manual_review")
        self.assertEqual(wallet["runner_distinct_token_mints"], 5)
        self.assertEqual(wallet["runner_signal_span_seconds"], 11900.0)
        self.assertFalse(wallet["wallet_trust_mutation_allowed"])
        self.assertFalse(wallet["wallet_list_mutation_allowed"])

    def test_marks_single_token_cluster_as_concentrated_anomaly(self):
        report = build_forward_signal_review_validator(
            packet=packet([row("MintA", 100.0), row("MintA", 105.0), row("MintA", 110.0)]),
            generated_at=123.0,
        )

        wallet = report["wallets"][0]
        self.assertEqual(wallet["validation_status"], "concentrated_anomaly_hold_review")
        self.assertEqual(wallet["runner_distinct_token_mints"], 1)
        self.assertEqual(wallet["dominant_runner_token_share"], 1.0)
        self.assertEqual(report["summary"]["repeatability_supported_wallets"], 0)

    def test_writer_persists_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path = root / "packet.json"
            report_path = root / "validator.json"
            csv_path = root / "validator.csv"
            markdown_path = root / "validator.md"
            packet_path.write_text(json.dumps(packet([row("MintA", 100.0)])), encoding="utf-8")

            report = write_forward_signal_review_validator(
                packet_path=packet_path,
                report_path=report_path,
                csv_path=csv_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["validated_wallets"], 1)
            self.assertIn("Forward Signal Review Validator", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
