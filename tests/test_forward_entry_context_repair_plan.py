import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_forward_entry_context_repair_plan import write_forward_entry_context_repair_plan
from wallets.forward_entry_context_repair_plan import build_forward_entry_context_repair_plan


def blocked_record(wallet: str, mint: str, context: dict) -> dict:
    return {
        "wallet": wallet,
        "token_mint": mint,
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": ["missing_forward_entry_price"],
        "decision_context": {"estimated_entry_context": context},
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


class ForwardEntryContextRepairPlanTests(unittest.TestCase):
    def test_plan_classifies_quote_repair_and_missing_market_context(self):
        report = build_forward_entry_context_repair_plan(
            [
                blocked_record(
                    "WalletA",
                    "MintA",
                    {
                        "execution_price_quote": 0.0001,
                        "execution_price_source": "same_transaction_token_balance_delta",
                        "quote_amount_delta": 1.2,
                    },
                ),
                blocked_record("WalletA", "MintB", {"execution_price_quote": None}),
                {"wallet": "WalletB", "status": "forward_outcome_labeled"},
            ],
            market_snapshots=[{"mint": "MintA", "time": 123.0, "price": 0.00011}],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_ENTRY_CONTEXT_REPAIR_PLAN_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["blocked_rows"], 2)
        self.assertEqual(report["summary"]["quote_anchor_repair_rows"], 1)
        self.assertEqual(report["summary"]["needs_market_snapshot_rows"], 1)
        self.assertEqual(report["summary"]["quote_anchor_and_snapshot_rows"], 1)
        self.assertEqual(report["summary"]["quote_anchor_without_snapshot_rows"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)

        by_wallet = {row["wallet"]: row for row in report["wallets"]}
        self.assertEqual(by_wallet["WalletA"]["repair_action"], "MIXED_REPAIR")
        self.assertEqual(by_wallet["WalletA"]["quote_anchor_repair_rows"], 1)
        self.assertEqual(by_wallet["WalletA"]["needs_market_snapshot_rows"], 1)
        self.assertIn("USE_EXECUTION_PRICE_QUOTE_AS_FORWARD_ENTRY_ANCHOR", by_wallet["WalletA"]["repair_methods"])

    def test_quote_anchor_without_later_snapshots_stays_context_collection(self):
        report = build_forward_entry_context_repair_plan(
            [
                blocked_record(
                    "WalletA",
                    "MintA",
                    {"execution_price_quote": 0.0001, "execution_price_source": "same_transaction_token_balance_delta"},
                )
            ],
            market_snapshots=[],
            generated_at=123.0,
        )

        row = report["wallets"][0]
        self.assertEqual(row["repair_action"], "NEEDS_MARKET_CONTEXT_COLLECTION")
        self.assertEqual(row["quote_anchor_repair_rows"], 1)
        self.assertEqual(row["quote_anchor_without_snapshot_rows"], 1)

    def test_writer_persists_report_and_markdown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records.jsonl"
            snapshots = root / "snapshots.jsonl"
            output = root / "repair.json"
            markdown = root / "repair.md"
            rows = [
                blocked_record(
                    "WalletA",
                    "MintA",
                    {"execution_price_quote": 0.0001, "execution_price_source": "same_transaction_token_balance_delta"},
                )
            ]
            records.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            snapshots.write_text(json.dumps({"mint": "MintA", "time": 123.0, "price": 0.00011}) + "\n", encoding="utf-8")

            report = write_forward_entry_context_repair_plan(
                records_path=records,
                market_context_path=snapshots,
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
