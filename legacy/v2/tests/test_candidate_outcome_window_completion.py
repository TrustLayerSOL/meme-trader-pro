import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_outcome_window_completion import write_candidate_outcome_window_completion
from wallets.candidate_outcome_window_completion import build_candidate_outcome_window_completion


def resolved_record(wallet, event, *, known=False, status=None, mint=None):
    outcome = "runner" if known else "unknown"
    window_status = "known" if known else "unknown"
    return {
        "event_id": f"{wallet}|Sig{event}|Mint{event}|buy|100",
        "wallet": wallet,
        "token_mint": mint or f"Mint{event}",
        "observed_action": "buy",
        "signal_time": 100.0,
        "transaction_signature": f"Sig{event}",
        "status": status or ("forward_outcome_labeled" if known else "forward_outcome_unknown_after_entry_repair"),
        "outcome_window_labels": {
            "15m": {
                "status": window_status,
                "outcome_type": outcome,
                "evaluation_horizon_seconds": 900,
                "classification_reasons": [] if known else ["missing later forward market snapshots"],
            }
        },
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


def rejected_record(wallet, event, *, reason="missing_later_market_snapshot"):
    return {
        "event_id": f"{wallet}|Sig{event}|Mint{event}|buy|100",
        "wallet": wallet,
        "token_mint": f"Mint{event}",
        "observed_action": "buy",
        "signal_time": 100.0,
        "transaction_signature": f"Sig{event}",
        "status": "blocked_forward_entry_context_repair",
        "block_reason": reason,
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


class CandidateOutcomeWindowCompletionTests(unittest.TestCase):
    def test_builds_capture_queue_for_unknown_15m_and_missing_later_snapshots(self):
        report = build_candidate_outcome_window_completion(
            resolved_records=[
                resolved_record("WalletA", "Known", known=True),
                resolved_record("WalletA", "Unknown", known=False),
            ],
            rejected_records=[
                rejected_record("WalletB", "Rejected"),
            ],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["records_scanned"], 3)
        self.assertEqual(report["summary"]["known_15m_rows"], 1)
        self.assertEqual(report["summary"]["unresolved_15m_rows"], 1)
        self.assertEqual(report["summary"]["rejected_missing_later_snapshot_rows"], 1)
        self.assertEqual(report["summary"]["capture_queue_rows"], 2)
        self.assertEqual(report["summary"]["unique_tokens_to_capture"], 2)
        self.assertTrue(all(row["recommended_action"] == "capture_later_market_snapshot" for row in report["capture_queue"]))
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_ignores_rejected_rows_with_non_snapshot_reasons(self):
        report = build_candidate_outcome_window_completion(
            resolved_records=[],
            rejected_records=[
                rejected_record("WalletA", "NoQuote", reason="missing_valid_execution_price_quote"),
            ],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["capture_queue_rows"], 0)
        self.assertEqual(report["summary"]["structurally_blocked_rows"], 1)

    def test_writer_exports_deterministic_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved_path = root / "resolved.jsonl"
            rejected_path = root / "rejected.jsonl"
            output_dir = root / "out"
            resolved_path.write_text(
                "\n".join(
                    [
                        json.dumps(resolved_record("WalletA", "Known", known=True), sort_keys=True),
                        json.dumps(resolved_record("WalletA", "Unknown", known=False), sort_keys=True),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            rejected_path.write_text(json.dumps(rejected_record("WalletB", "Rejected"), sort_keys=True) + "\n", encoding="utf-8")

            report = write_candidate_outcome_window_completion(
                resolved_records_path=resolved_path,
                rejected_records_path=rejected_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertTrue((output_dir / "candidate_outcome_window_completion_fixed.json").exists())
            self.assertTrue((output_dir / "candidate_outcome_window_completion_fixed.csv").exists())
            self.assertTrue((output_dir / "candidate_outcome_window_capture_queue_fixed.csv").exists())
            self.assertTrue((output_dir / "candidate_outcome_window_completion_fixed.md").exists())
            saved = json.loads((output_dir / "candidate_outcome_window_completion_fixed.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("capture_later_market_snapshot", (output_dir / "candidate_outcome_window_capture_queue_fixed.csv").read_text(encoding="utf-8"))
            self.assertIn("Candidate Outcome Window Completion", (output_dir / "candidate_outcome_window_completion_fixed.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
