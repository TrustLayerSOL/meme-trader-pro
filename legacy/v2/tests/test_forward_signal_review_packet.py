import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_signal_review_packet import write_forward_signal_review_packet
from wallets.forward_signal_review_packet import build_forward_signal_review_packet


def recommendation(wallet: str):
    return {
        "wallet": wallet,
        "recommendation_action": "REVIEW_FORWARD_SIGNAL_MANUALLY",
        "known_15m": 2,
        "runner_15m": 1,
        "flat_15m": 1,
        "blocked_records": 0,
        "auto_apply": False,
        "wallet_list_mutation_allowed": False,
    }


def repaired_row(wallet: str, event_id: str, mint: str, outcome: str):
    return {
        "event_id": event_id,
        "wallet": wallet,
        "token_mint": mint,
        "signal_time": 100.0,
        "transaction_signature": f"sig-{event_id}",
        "observed_action": "buy",
        "entry_context_repair": {
            "method": "same_transaction_quote_anchor",
            "confidence": "partial_forward_quote_anchor",
            "repaired_price": 0.01,
            "later_snapshots_available": 3,
        },
        "outcome_window_labels": {
            "15m": {
                "outcome_type": outcome,
                "label_confidence": "medium",
                "classification_reasons": ["test reason"],
            }
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


class ForwardSignalReviewPacketTests(unittest.TestCase):
    def test_review_packet_contains_only_manual_review_wallets_and_rows(self):
        report = build_forward_signal_review_packet(
            recommendations={
                "live_execution_locked": True,
                "summary": {"promotions_allowed": 0},
                "recommendations": [
                    recommendation("WalletA"),
                    {"wallet": "WalletB", "recommendation_action": "HOLD_NO_PROMOTION_FLAT_ONLY"},
                ],
            },
            repaired_records=[
                repaired_row("WalletA", "evt-1", "MintA", "runner"),
                repaired_row("WalletA", "evt-2", "MintB", "flat"),
                repaired_row("WalletB", "evt-3", "MintC", "runner"),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_SIGNAL_REVIEW_PACKET_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["review_wallets"], 1)
        self.assertEqual(report["summary"]["review_rows"], 2)
        self.assertEqual(report["summary"]["runner_15m_rows"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        wallet = report["wallets"][0]
        self.assertEqual(wallet["wallet"], "WalletA")
        self.assertEqual(wallet["recommendation_action"], "REVIEW_FORWARD_SIGNAL_MANUALLY")
        self.assertEqual(wallet["rows"][0]["token_mint"], "MintA")
        self.assertEqual(wallet["rows"][0]["repaired_price"], 0.01)
        self.assertEqual(wallet["rows"][0]["outcome_15m"], "runner")
        self.assertFalse(wallet["wallet_list_mutation_allowed"])

    def test_writer_persists_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recommendations_path = root / "recommendations.json"
            repaired_path = root / "repaired.jsonl"
            report_path = root / "packet.json"
            csv_path = root / "packet.csv"
            markdown_path = root / "packet.md"
            recommendations_path.write_text(
                json.dumps({"live_execution_locked": True, "recommendations": [recommendation("WalletA")]}),
                encoding="utf-8",
            )
            repaired_path.write_text(json.dumps(repaired_row("WalletA", "evt-1", "MintA", "runner")) + "\n", encoding="utf-8")

            report = write_forward_signal_review_packet(
                recommendations_path=recommendations_path,
                repaired_records_path=repaired_path,
                report_path=report_path,
                csv_path=csv_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["review_wallets"], 1)
            self.assertIn("Forward Signal Review Packet", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
