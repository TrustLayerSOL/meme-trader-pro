import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_forward_calibration_scorecard import write_forward_calibration_scorecard
from wallets.forward_calibration_scorecard import build_forward_calibration_scorecard


def record(wallet: str, outcome: str, *, status: str = "forward_outcome_labeled") -> dict:
    return {
        "wallet": wallet,
        "token_mint": f"{wallet}-{outcome}",
        "status": status,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
        "outcome_window_labels": {
            "15m": {"outcome_type": outcome},
        },
    }


class ForwardCalibrationScorecardTests(unittest.TestCase):
    def test_scorecard_ranks_wallets_without_mutating_trust(self):
        report = build_forward_calibration_scorecard(
            [
                record("WalletA", "runner"),
                record("WalletA", "flat"),
                record("WalletA", "unknown", status="blocked_missing_forward_entry_context"),
                record("WalletB", "flat"),
                record("WalletB", "flat"),
                record("WalletC", "rug"),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_CALIBRATION_SCORECARD_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertEqual(report["summary"]["wallets"], 3)
        self.assertEqual(report["summary"]["known_15m_outcomes"], 5)
        self.assertEqual(report["summary"]["flat_15m_outcomes"], 3)

        by_wallet = {row["wallet"]: row for row in report["wallets"]}
        self.assertEqual(by_wallet["WalletA"]["calibration_status"], "review_behavioral_signal")
        self.assertEqual(by_wallet["WalletA"]["runner_15m"], 1)
        self.assertEqual(by_wallet["WalletB"]["calibration_status"], "flat_noise_candidate")
        self.assertEqual(by_wallet["WalletC"]["calibration_status"], "risk_review_candidate")

        self.assertEqual(report["wallets"][0]["wallet"], "WalletA")

    def test_writer_persists_json_and_markdown_reports(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "forward_records.jsonl"
            output = root / "scorecard.json"
            markdown = root / "scorecard.md"
            rows = [record("WalletA", "runner"), record("WalletB", "flat")]
            records.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = write_forward_calibration_scorecard(
                records_path=records,
                report_path=output,
                markdown_path=markdown,
                generated_at=123.0,
            )

            self.assertTrue(output.exists())
            self.assertTrue(markdown.exists())
            self.assertEqual(report["summary"]["wallets"], 2)
            self.assertIn("input_paths", report)


if __name__ == "__main__":
    unittest.main()
