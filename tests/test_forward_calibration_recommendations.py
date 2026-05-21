import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_forward_calibration_recommendations import write_forward_calibration_recommendations
from wallets.forward_calibration_recommendations import build_forward_calibration_recommendations


def scorecard_row(wallet: str, status: str, **overrides) -> dict:
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


class ForwardCalibrationRecommendationsTests(unittest.TestCase):
    def test_flat_only_wallets_are_not_promoted(self):
        report = build_forward_calibration_recommendations(
            {
                "live_execution_locked": True,
                "wallets": [
                    scorecard_row("FlatWallet", "flat_noise_candidate"),
                    scorecard_row("BlockedWallet", "blocked_missing_context", known_15m=0, flat_15m=0, blocked_records=10),
                    scorecard_row("RunnerWallet", "review_behavioral_signal", runner_15m=2, flat_15m=1, known_15m=3),
                    scorecard_row("RiskWallet", "risk_review_candidate", rug_15m=1, flat_15m=1, known_15m=2),
                ],
            },
            generated_at=123.0,
        )

        by_wallet = {row["wallet"]: row for row in report["recommendations"]}
        self.assertEqual(by_wallet["FlatWallet"]["recommendation_action"], "HOLD_NO_PROMOTION_FLAT_ONLY")
        self.assertEqual(by_wallet["BlockedWallet"]["recommendation_action"], "FIX_FORWARD_ENTRY_CONTEXT")
        self.assertEqual(by_wallet["RunnerWallet"]["recommendation_action"], "REVIEW_FORWARD_SIGNAL_MANUALLY")
        self.assertEqual(by_wallet["RiskWallet"]["recommendation_action"], "RISK_REVIEW_REQUIRED")
        self.assertFalse(any(row["auto_apply"] for row in report["recommendations"]))
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)

    def test_writer_persists_json_and_markdown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scorecard = root / "scorecard.json"
            output = root / "recommendations.json"
            markdown = root / "recommendations.md"
            scorecard.write_text(
                json.dumps(
                    {
                        "live_execution_locked": True,
                        "wallets": [scorecard_row("FlatWallet", "flat_noise_candidate")],
                    }
                ),
                encoding="utf-8",
            )

            report = write_forward_calibration_recommendations(
                scorecard_path=scorecard,
                report_path=output,
                markdown_path=markdown,
                generated_at=123.0,
            )

            self.assertTrue(output.exists())
            self.assertTrue(markdown.exists())
            self.assertEqual(report["summary"]["wallets"], 1)
            self.assertIn("input_paths", report)


if __name__ == "__main__":
    unittest.main()
