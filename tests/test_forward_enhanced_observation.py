import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_enhanced_observation import write_forward_enhanced_observation
from wallets.forward_enhanced_observation import build_forward_enhanced_observation


def rollup() -> dict:
    return {
        "live_execution_locked": True,
        "summary": {
            "wallets": 1,
            "manual_review_required": 1,
            "repeatability_supported": 1,
            "promotions_allowed": 0,
            "trust_mutations_allowed": 0,
            "wallet_list_mutations_allowed": 0,
        },
        "wallets": [
            {
                "wallet": "WalletEnhanced",
                "decision_type": "manual_review_required",
                "validation_status": "repeatability_supported_manual_review",
                "runner_rows": 59,
                "unknown_15m_rows": 14,
                "total_review_rows": 73,
                "runner_distinct_token_mints": 33,
                "runner_signal_span_seconds": 37734.0,
                "dominant_runner_token_share": 0.067797,
                "top_token_mints": [{"token_mint": "MintA", "rows": 4}],
                "required_human_checks": ["do not promote from this artifact alone"],
                "promotion_allowed": False,
                "wallet_trust_mutation_allowed": False,
                "wallet_list_mutation_allowed": False,
            }
        ],
    }


class ForwardEnhancedObservationTests(unittest.TestCase):
    def test_repeatability_supported_manual_review_wallet_enters_enhanced_observation_only(self):
        report = build_forward_enhanced_observation(rollup=rollup(), generated_at=123.0)

        self.assertEqual(report["mode"], "FORWARD_ENHANCED_OBSERVATION_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["enhanced_observation_wallets"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_trust_mutations_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations_allowed"], 0)
        wallet = report["wallets"][0]
        self.assertEqual(wallet["wallet"], "WalletEnhanced")
        self.assertEqual(wallet["observation_lane"], "enhanced_observation")
        self.assertEqual(wallet["review_action"], "WATCH_NEXT_FORWARD_TRADES")
        self.assertEqual(wallet["trust_status"], "not_trusted")
        self.assertEqual(wallet["minimum_next_forward_signals"], 25)
        self.assertEqual(wallet["minimum_distinct_next_token_mints"], 10)
        self.assertIn("continue observation", wallet["operator_recommendation"])
        self.assertFalse(wallet["promotion_allowed"])
        self.assertFalse(wallet["wallet_trust_mutation_allowed"])
        self.assertFalse(wallet["wallet_list_mutation_allowed"])

    def test_writer_persists_watchlist_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollup_path = root / "rollup.json"
            report_path = root / "enhanced.json"
            markdown_path = root / "enhanced.md"
            rollup_path.write_text(json.dumps(rollup()), encoding="utf-8")

            report = write_forward_enhanced_observation(
                rollup_path=rollup_path,
                report_path=report_path,
                markdown_path=markdown_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["enhanced_observation_wallets"], 1)
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("Forward Enhanced Observation", markdown)
            self.assertIn("WalletEnhanced", markdown)
            self.assertIn("No promotion is allowed", markdown)


if __name__ == "__main__":
    unittest.main()
