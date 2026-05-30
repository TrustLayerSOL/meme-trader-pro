import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_merged_calibration_recommendations import write_forward_merged_calibration_recommendations
from wallets.forward_merged_calibration_recommendations import build_forward_merged_calibration_recommendations


def wallet_row(wallet: str, status: str, **overrides):
    row = {
        "wallet": wallet,
        "calibration_status": status,
        "records": 10,
        "known_15m": 2,
        "runner_15m": 0,
        "rug_15m": 0,
        "dead_15m": 0,
        "loser_15m": 0,
        "flat_15m": 2,
        "blocked_records": 0,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }
    row.update(overrides)
    return row


def merged_scorecard():
    return {
        "mode": "FORWARD_MERGED_CALIBRATION_SCORECARD_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {
            "merged_records": 100,
            "repaired_records": 5,
            "replaced_original_blocked_records": 5,
        },
        "scorecard": {
            "live_execution_locked": True,
            "wallets": [
                wallet_row("RunnerWallet", "review_behavioral_signal", known_15m=3, runner_15m=2, flat_15m=1),
                wallet_row("BlockedWallet", "blocked_missing_context", known_15m=0, flat_15m=0, blocked_records=10),
                wallet_row("FlatWallet", "flat_noise_candidate"),
            ],
        },
    }


class ForwardMergedCalibrationRecommendationsTests(unittest.TestCase):
    def test_merged_recommendations_keep_runner_as_manual_review_only(self):
        report = build_forward_merged_calibration_recommendations(merged_scorecard(), generated_at=123.0)

        self.assertEqual(report["mode"], "FORWARD_MERGED_CALIBRATION_RECOMMENDATIONS_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["wallets"], 3)
        self.assertEqual(report["summary"]["review_forward_signal_wallets"], 1)
        self.assertEqual(report["summary"]["fix_context_wallets"], 1)
        self.assertEqual(report["summary"]["flat_only_hold_wallets"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertEqual(report["merged_scorecard_summary"]["repaired_records"], 5)

        by_wallet = {row["wallet"]: row for row in report["recommendations"]}
        self.assertEqual(by_wallet["RunnerWallet"]["recommendation_action"], "REVIEW_FORWARD_SIGNAL_MANUALLY")
        self.assertFalse(by_wallet["RunnerWallet"]["auto_apply"])
        self.assertFalse(by_wallet["RunnerWallet"]["wallet_list_mutation_allowed"])

    def test_writer_persists_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scorecard_path = root / "merged_scorecard.json"
            report_path = root / "recommendations.json"
            markdown_path = root / "recommendations.md"
            scorecard_path.write_text(json.dumps(merged_scorecard()), encoding="utf-8")

            report = write_forward_merged_calibration_recommendations(
                merged_scorecard_path=scorecard_path,
                report_path=report_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["review_forward_signal_wallets"], 1)
            self.assertIn("Merged Forward Calibration Recommendations", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
