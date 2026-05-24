import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_helius_quote_anchor_merge import write_forward_helius_quote_anchor_merge
from wallets.forward_helius_quote_anchor_merge import build_forward_helius_quote_anchor_merge


def blocked_record(*, wallet="WalletA", mint="MintA", signal_time=100.0, signature="SigA"):
    return {
        "event_id": f"{wallet}|{signature}|{mint}|buy|{int(signal_time)}",
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": "buy",
        "signal_time": signal_time,
        "transaction_signature": signature,
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": ["missing_forward_entry_price"],
        "decision_context": {
            "estimated_entry_context": {
                "price": None,
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


def quote_probe_row(*, wallet="WalletA", mint="MintA", signature="SigA", signal_time=100.0, price=0.01):
    return {
        "event_id": f"{wallet}|{signature}|{mint}|buy|{int(signal_time)}",
        "wallet_address": wallet,
        "token_mint": mint,
        "transaction_signature": signature,
        "signal_time": signal_time,
        "status": "quote_anchor_recoverable",
        "execution_price_quote": price,
        "execution_price_source": "native_sol_balance_delta",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "quote_amount_delta": -1.0,
        "native_sol_raw_lamports_delta": -1_000_005_000,
        "native_sol_adjusted_lamports_delta": -1_000_000_000,
        "native_sol_fee_lamports": 5000,
    }


def snapshot(time_value=125.0, price=0.018, *, mint="MintA"):
    return {
        "time": time_value,
        "mint": mint,
        "source": "forward_market_context:dexscreener",
        "price": price,
        "liquidity": 10_000,
        "market_cap": price * 10_000_000,
    }


class ForwardHeliusQuoteAnchorMergeTests(unittest.TestCase):
    def test_merge_overlays_recovered_quotes_and_runs_resolver_without_mutating(self):
        report = build_forward_helius_quote_anchor_merge(
            records=[blocked_record(), blocked_record(wallet="WalletB", mint="MintB", signature="SigB")],
            quote_probe_rows=[
                quote_probe_row(),
                {**quote_probe_row(wallet="WalletB", mint="MintB", signature="SigB"), "status": "quote_anchor_not_recovered"},
            ],
            market_snapshots=[snapshot()],
            generated_at=1100.0,
            run_id="fixed",
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["recoverable_quote_anchors"], 1)
        self.assertEqual(report["summary"]["records_augmented_with_quote_anchor"], 1)
        self.assertEqual(report["summary"]["resolver_resolved_rows"], 1)
        self.assertEqual(report["summary"]["resolver_blocked_no_quote_anchor_rows"], 1)
        self.assertEqual(report["summary"]["repair_rows_written_to_canonical_resolver"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        augmented = report["augmented_records"][0]["decision_context"]["estimated_entry_context"]
        self.assertEqual(augmented["execution_price_quote"], 0.01)
        self.assertEqual(augmented["execution_price_source"], "native_sol_balance_delta")
        self.assertEqual(augmented["quote_anchor_source"], "helius_quote_probe")
        self.assertEqual(report["resolver_report"]["resolved_records"][0]["status"], "forward_outcome_labeled")

    def test_writer_persists_isolated_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            probe_path = root / "probe.json"
            snapshots_path = root / "snapshots.jsonl"
            output_dir = root / "out"
            records_path.write_text(json.dumps(blocked_record()) + "\n", encoding="utf-8")
            probe_path.write_text(json.dumps({"rows": [quote_probe_row()]}), encoding="utf-8")
            snapshots_path.write_text(json.dumps(snapshot()) + "\n", encoding="utf-8")

            report = write_forward_helius_quote_anchor_merge(
                records_path=records_path,
                quote_probe_path=probe_path,
                market_context_path=snapshots_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1100.0,
            )

            self.assertEqual(report["summary"]["resolver_resolved_rows"], 1)
            self.assertTrue((output_dir / "forward_helius_quote_anchor_merge_fixed.json").exists())
            self.assertTrue((output_dir / "forward_helius_quote_anchor_merge_fixed.csv").exists())
            self.assertTrue((output_dir / "forward_helius_quote_anchor_merge_resolved_fixed.jsonl").exists())
            self.assertTrue((output_dir / "forward_helius_quote_anchor_merge_rejected_fixed.jsonl").exists())
            self.assertTrue((output_dir / "forward_helius_quote_anchor_merge_fixed.md").exists())

    def test_merge_matches_probe_rows_without_event_id_by_wallet_mint_signature(self):
        probe_row = quote_probe_row()
        probe_row.pop("event_id")

        report = build_forward_helius_quote_anchor_merge(
            records=[blocked_record()],
            quote_probe_rows=[probe_row],
            market_snapshots=[snapshot()],
            generated_at=1100.0,
            run_id="fixed",
        )

        self.assertEqual(report["summary"]["records_augmented_with_quote_anchor"], 1)
        self.assertEqual(report["summary"]["resolver_resolved_rows"], 1)


if __name__ == "__main__":
    unittest.main()
