import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_merged_calibration_scorecard import write_forward_merged_calibration_scorecard
from wallets.forward_merged_calibration_scorecard import build_forward_merged_calibration_scorecard


def original_record(event_id: str, wallet: str, outcome: str = "unknown", *, status: str = "blocked_missing_forward_entry_context"):
    return {
        "event_id": event_id,
        "wallet": wallet,
        "token_mint": f"{wallet}-{event_id}",
        "status": status,
        "outcome_window_labels": {"15m": {"outcome_type": outcome}},
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def repaired_record(event_id: str, wallet: str, outcome: str):
    return {
        "event_id": event_id,
        "wallet": wallet,
        "token_mint": f"{wallet}-{event_id}",
        "status": "forward_outcome_labeled",
        "entry_context_repair": {"method": "same_transaction_quote_anchor"},
        "outcome_window_labels": {"15m": {"outcome_type": outcome}},
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


class ForwardMergedCalibrationScorecardTests(unittest.TestCase):
    def test_merged_scorecard_replaces_repaired_blocked_rows_without_trust_mutation(self):
        report = build_forward_merged_calibration_scorecard(
            original_records=[
                original_record("evt-1", "WalletA"),
                original_record("evt-2", "WalletA", "flat", status="forward_outcome_labeled"),
                original_record("evt-3", "WalletB"),
            ],
            repaired_records=[
                repaired_record("evt-1", "WalletA", "runner"),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_MERGED_CALIBRATION_SCORECARD_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["original_records"], 3)
        self.assertEqual(report["summary"]["repaired_records"], 1)
        self.assertEqual(report["summary"]["replaced_original_blocked_records"], 1)
        self.assertEqual(report["summary"]["merged_records"], 3)
        self.assertEqual(report["summary"]["known_15m_outcomes"], 2)
        self.assertEqual(report["summary"]["runner_15m_outcomes"], 1)
        self.assertEqual(report["summary"]["blocked_records"], 1)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertEqual(report["scorecard"]["summary"]["wallet_list_mutations"], 0)

        by_wallet = {row["wallet"]: row for row in report["scorecard"]["wallets"]}
        self.assertEqual(by_wallet["WalletA"]["calibration_status"], "review_behavioral_signal")
        self.assertEqual(by_wallet["WalletA"]["records"], 2)
        self.assertEqual(by_wallet["WalletA"]["known_15m"], 2)

    def test_writer_persists_merged_report_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_path = root / "original.jsonl"
            repaired_path = root / "repaired.jsonl"
            report_path = root / "merged.json"
            markdown_path = root / "merged.md"
            original_path.write_text(json.dumps(original_record("evt-1", "WalletA")) + "\n", encoding="utf-8")
            repaired_path.write_text(json.dumps(repaired_record("evt-1", "WalletA", "runner")) + "\n", encoding="utf-8")

            report = write_forward_merged_calibration_scorecard(
                original_records_path=original_path,
                repaired_records_path=repaired_path,
                report_path=report_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["merged_records"], 1)
            self.assertIn("Merged Forward Calibration Scorecard", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
