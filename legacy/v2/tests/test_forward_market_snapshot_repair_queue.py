import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_market_snapshot_repair_queue import write_forward_market_snapshot_repair_queue
from wallets.forward_market_snapshot_repair_queue import build_forward_market_snapshot_repair_queue


def rejected_row(*, wallet="WalletA", mint="MintA", signal_time=100.0, reason="missing_later_market_snapshot"):
    return {
        "event_id": f"{wallet}|SigA|{mint}|buy|{int(signal_time)}",
        "wallet": wallet,
        "token_mint": mint,
        "signal_time": signal_time,
        "transaction_signature": "SigA",
        "status": "blocked_forward_entry_context_repair",
        "block_reason": reason,
        "has_quote_anchor": reason == "missing_later_market_snapshot",
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


class ForwardMarketSnapshotRepairQueueTests(unittest.TestCase):
    def test_queue_groups_only_missing_later_snapshot_rows_by_mint(self):
        report = build_forward_market_snapshot_repair_queue(
            rejected_records=[
                rejected_row(wallet="WalletA", mint="MintA", signal_time=100.0),
                rejected_row(wallet="WalletB", mint="MintA", signal_time=130.0),
                rejected_row(wallet="WalletC", mint="MintB", signal_time=200.0),
                rejected_row(wallet="WalletD", mint="MintC", reason="missing_valid_execution_price_quote"),
            ],
            run_id="fixed",
            generated_at=123.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["input_rejected_records"], 4)
        self.assertEqual(report["summary"]["missing_later_market_snapshot_rows"], 3)
        self.assertEqual(report["summary"]["queued_token_mints"], 2)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertEqual(report["queue"][0]["token_mint"], "MintA")
        self.assertEqual(report["queue"][0]["blocked_row_count"], 2)
        self.assertEqual(report["queue"][0]["wallet_count"], 2)
        self.assertEqual(report["queue"][0]["required_snapshot_start_time"], 100.0)
        self.assertEqual(report["queue"][0]["required_snapshot_end_time"], 1030.0)
        self.assertEqual(report["queue"][0]["recommended_action"], "collect_later_market_snapshot")
        self.assertFalse(report["queue"][0]["can_mutate_wallet_trust"])

    def test_writer_persists_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rejected_path = root / "rejected.jsonl"
            output_dir = root / "out"
            rejected_path.write_text(
                "\n".join(json.dumps(row) for row in [rejected_row(), rejected_row(mint="MintB")]) + "\n",
                encoding="utf-8",
            )

            report = write_forward_market_snapshot_repair_queue(
                rejected_records_path=rejected_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["queued_token_mints"], 2)
            self.assertTrue((output_dir / "forward_market_snapshot_repair_queue_fixed.json").exists())
            self.assertTrue((output_dir / "forward_market_snapshot_repair_queue_fixed.csv").exists())
            self.assertTrue((output_dir / "forward_market_snapshot_repair_queue_fixed.md").exists())


if __name__ == "__main__":
    unittest.main()
