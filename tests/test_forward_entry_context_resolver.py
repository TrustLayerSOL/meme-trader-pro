import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_entry_context_resolver import write_forward_entry_context_resolver_report
from wallets.forward_entry_context_resolver import build_forward_entry_context_resolver_report


def blocked_record(*, wallet="WalletA", mint="MintA", signal_time=100.0, quote=0.01):
    return {
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": "buy",
        "signal_time": signal_time,
        "transaction_signature": "SigA",
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": ["missing_forward_entry_price"],
        "decision_context": {
            "estimated_entry_context": {
                "price": None,
                "execution_price_quote": quote,
                "execution_price_source": "same_transaction_token_balance_delta",
                "quote_amount_delta": 1.0,
                "quote_mint": "So11111111111111111111111111111111111111112",
                "liquidity": None,
                "market_cap": None,
                "decision_time_safe": True,
            },
            "collection_source": "forward_wallet_activity",
            "forward_observation": True,
            "risk_flags": ["forward_current_activity"],
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def snapshot(time_value, price, *, mint="MintA"):
    return {
        "time": time_value,
        "mint": mint,
        "source": "forward_market_context:dexscreener",
        "price": price,
        "liquidity": 10_000,
        "market_cap": price * 10_000_000,
    }


class ForwardEntryContextResolverTests(unittest.TestCase):
    def test_resolves_only_quote_rows_with_later_snapshots(self):
        report = build_forward_entry_context_resolver_report(
            records=[
                blocked_record(wallet="WalletA", mint="MintA", signal_time=100.0, quote=0.01),
                blocked_record(wallet="WalletB", mint="MintB", signal_time=100.0, quote=0.02),
                blocked_record(wallet="WalletC", mint="MintC", signal_time=100.0, quote=None),
            ],
            market_snapshots=[
                snapshot(125, 0.018, mint="MintA"),
                snapshot(90, 0.03, mint="MintB"),
            ],
            generated_at=1100,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["blocked_rows_scanned"], 3)
        self.assertEqual(report["summary"]["quote_anchor_candidates"], 2)
        self.assertEqual(report["summary"]["resolved_rows"], 1)
        self.assertEqual(report["summary"]["blocked_no_later_snapshot_rows"], 1)
        self.assertEqual(report["summary"]["blocked_no_quote_anchor_rows"], 1)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        resolved = report["resolved_records"][0]
        self.assertEqual(resolved["status"], "forward_outcome_labeled")
        self.assertEqual(resolved["entry_context_repair"]["method"], "same_transaction_quote_anchor")
        self.assertEqual(resolved["outcome_window_labels"]["30s"]["outcome_type"], "runner")
        self.assertNotIn("outcome_type", json.dumps(resolved["decision_context"]))

    def test_writer_persists_report_records_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            snapshots_path = root / "snapshots.jsonl"
            report_path = root / "report.json"
            resolved_path = root / "resolved.jsonl"
            rejected_path = root / "rejected.jsonl"
            markdown_path = root / "report.md"
            records_path.write_text(json.dumps(blocked_record()) + "\n", encoding="utf-8")
            snapshots_path.write_text(json.dumps(snapshot(125, 0.018)) + "\n", encoding="utf-8")

            report = write_forward_entry_context_resolver_report(
                records_path=records_path,
                market_context_path=snapshots_path,
                report_path=report_path,
                resolved_records_path=resolved_path,
                rejected_records_path=rejected_path,
                markdown_path=markdown_path,
                generated_at=1100,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(resolved_path.exists())
            self.assertTrue(rejected_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(report["summary"]["resolved_rows"], 1)
            self.assertIn("Forward Entry Context Resolver", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
