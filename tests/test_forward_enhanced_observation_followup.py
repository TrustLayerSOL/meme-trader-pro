import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_enhanced_observation_followup import write_forward_enhanced_observation_followup
from wallets.forward_enhanced_observation_followup import build_forward_enhanced_observation_followup


def watchlist() -> dict:
    return {
        "generated_at": 1000.0,
        "live_execution_locked": True,
        "summary": {
            "enhanced_observation_wallets": 1,
            "minimum_next_forward_signals_per_wallet": 3,
            "minimum_distinct_next_token_mints_per_wallet": 2,
            "promotions_allowed": 0,
            "wallet_trust_mutations_allowed": 0,
            "wallet_list_mutations_allowed": 0,
        },
        "wallets": [
            {
                "wallet": "WalletWatch",
                "observation_lane": "enhanced_observation",
                "trust_status": "not_trusted",
                "minimum_next_forward_signals": 3,
                "minimum_distinct_next_token_mints": 2,
                "evidence_summary": {
                    "runner_rows": 5,
                    "runner_distinct_token_mints": 4,
                    "unknown_15m_rows": 1,
                },
                "promotion_allowed": False,
                "wallet_trust_mutation_allowed": False,
                "wallet_list_mutation_allowed": False,
            }
        ],
    }


def row(wallet: str, mint: str, signal_time: float, outcome: str, *, blocked: bool = False) -> dict:
    return {
        "wallet": wallet,
        "token_mint": mint,
        "signal_time": signal_time,
        "block_reasons": ["missing_forward_entry_price"] if blocked else [],
        "outcome_window_labels": {
            "15m": {
                "outcome_type": outcome,
                "runner": outcome == "runner",
                "rug": outcome == "rug",
                "missing": outcome == "unknown",
            }
        },
    }


class ForwardEnhancedObservationFollowupTests(unittest.TestCase):
    def test_followup_counts_only_new_rows_after_watchlist_timestamp(self):
        report = build_forward_enhanced_observation_followup(
            watchlist=watchlist(),
            records=[
                row("WalletWatch", "OldMint", 900.0, "runner"),
                row("WalletWatch", "MintA", 1100.0, "runner"),
                row("WalletWatch", "MintB", 1200.0, "flat"),
                row("WalletWatch", "MintC", 1300.0, "unknown", blocked=True),
            ],
            generated_at=1400.0,
        )

        self.assertEqual(report["mode"], "FORWARD_ENHANCED_OBSERVATION_FOLLOWUP_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["followup_wallets"], 1)
        self.assertEqual(report["summary"]["wallets_meeting_review_threshold"], 1)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_trust_mutations_allowed"], 0)
        wallet = report["wallets"][0]
        self.assertEqual(wallet["wallet"], "WalletWatch")
        self.assertEqual(wallet["new_forward_records"], 3)
        self.assertEqual(wallet["new_distinct_token_mints"], 3)
        self.assertEqual(wallet["new_runner_15m"], 1)
        self.assertEqual(wallet["new_blocked_records"], 1)
        self.assertTrue(wallet["meets_review_threshold"])
        self.assertEqual(wallet["review_status"], "ready_for_human_followup_review")
        self.assertFalse(wallet["promotion_allowed"])
        self.assertFalse(wallet["wallet_trust_mutation_allowed"])

    def test_writer_persists_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            watchlist_path = root / "watchlist.json"
            records_path = root / "records.jsonl"
            report_path = root / "followup.json"
            markdown_path = root / "followup.md"
            watchlist_path.write_text(json.dumps(watchlist()), encoding="utf-8")
            records_path.write_text(
                "\n".join(
                    [
                        json.dumps(row("WalletWatch", "MintA", 1100.0, "runner")),
                        json.dumps(row("WalletWatch", "MintB", 1200.0, "flat")),
                        json.dumps(row("WalletWatch", "MintC", 1300.0, "unknown")),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = write_forward_enhanced_observation_followup(
                watchlist_path=watchlist_path,
                records_path=records_path,
                report_path=report_path,
                markdown_path=markdown_path,
                generated_at=1400.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["followup_wallets"], 1)
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("Forward Enhanced Observation Follow-Up", markdown)
            self.assertIn("WalletWatch", markdown)
            self.assertIn("No promotion is allowed", markdown)


if __name__ == "__main__":
    unittest.main()
