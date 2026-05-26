import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_context_completion import write_dune_candidate_context_completion
from wallets.dune_candidate_context_completion import build_dune_candidate_context_completion


def candidate_record(*, price=0.01, signal_time=100.0, reasons=None):
    context = {
        "price": price,
        "price_usd": price,
        "price_source": "dune_dex_trade_candidate",
        "decision_time_safe": True,
    }
    if price is None:
        context.pop("price")
        context.pop("price_usd")
    return {
        "event_id": "WalletA|SigA|MintA|buy|100",
        "wallet": "WalletA",
        "token_mint": "MintA",
        "signal_time": signal_time,
        "transaction_signature": "SigA",
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": reasons
        or ["dune_context_not_score_ready", "missing_forward_liquidity", "missing_forward_market_cap"],
        "decision_context": {"estimated_entry_context": context},
        "dune_context_candidate": {"quality": "dune_price_candidate", "proof_ready": False},
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def market_snapshot(*, time_value=115.0, liquidity=25000.0, market_cap=100000.0, mint="MintA"):
    return {
        "mint": mint,
        "time": time_value,
        "price": 0.011,
        "liquidity": liquidity,
        "market_cap": market_cap,
        "source": "forward_market_context:dexscreener",
    }


class DuneCandidateContextCompletionTests(unittest.TestCase):
    def test_completes_price_rows_with_near_snapshot_liquidity_and_market_cap(self):
        report = build_dune_candidate_context_completion(
            candidate_records=[candidate_record()],
            market_snapshots=[market_snapshot()],
            generated_at=1000.0,
            max_snapshot_lag_seconds=120.0,
        )

        self.assertTrue(report["review_only"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])
        self.assertEqual(report["summary"]["candidate_records_scanned"], 1)
        self.assertEqual(report["summary"]["context_complete_records"], 1)
        self.assertEqual(report["summary"]["proof_ready_candidate_records"], 1)
        record = report["completed_records"][0]
        ctx = record["decision_context"]["estimated_entry_context"]
        self.assertEqual(record["status"], "dune_candidate_context_complete_review_only")
        self.assertEqual(ctx["liquidity"], 25000.0)
        self.assertEqual(ctx["market_cap"], 100000.0)
        self.assertEqual(ctx["market_snapshot_lag_seconds"], 15.0)
        self.assertNotIn("missing_forward_liquidity", record["block_reasons"])
        self.assertNotIn("missing_forward_market_cap", record["block_reasons"])
        self.assertFalse(record["can_mutate_wallet_trust"])
        self.assertFalse(record["wallet_list_mutation_allowed"])

    def test_keeps_rows_blocked_when_price_or_liquidity_is_missing(self):
        report = build_dune_candidate_context_completion(
            candidate_records=[
                candidate_record(price=None, reasons=["missing_forward_entry_price", "missing_forward_liquidity"]),
                candidate_record(price=0.01, reasons=["missing_forward_liquidity"], signal_time=200.0),
            ],
            market_snapshots=[
                market_snapshot(liquidity=1000.0, market_cap=2000.0),
                market_snapshot(time_value=205.0, liquidity=None, market_cap=2000.0),
            ],
            generated_at=1000.0,
            max_snapshot_lag_seconds=120.0,
        )

        self.assertEqual(report["summary"]["context_complete_records"], 0)
        self.assertEqual(report["summary"]["blocked_missing_price_records"], 1)
        self.assertEqual(report["summary"]["blocked_missing_liquidity_records"], 1)
        self.assertEqual(len(report["blocked_records"]), 2)

    def test_writer_exports_json_jsonl_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates_path = root / "candidates.jsonl"
            snapshots_path = root / "snapshots.jsonl"
            output_dir = root / "out"
            candidates_path.write_text(json.dumps(candidate_record(), sort_keys=True) + "\n", encoding="utf-8")
            snapshots_path.write_text(json.dumps(market_snapshot(), sort_keys=True) + "\n", encoding="utf-8")

            report = write_dune_candidate_context_completion(
                candidate_records_path=candidates_path,
                market_snapshots_path=snapshots_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertEqual(report["summary"]["context_complete_records"], 1)
            self.assertTrue((output_dir / "dune_candidate_context_completion_fixed.json").exists())
            self.assertTrue((output_dir / "dune_candidate_context_completed_records_fixed.jsonl").exists())
            self.assertTrue((output_dir / "dune_candidate_context_completion_events_fixed.csv").exists())
            self.assertTrue((output_dir / "dune_candidate_context_completion_fixed.md").exists())
            self.assertIn(
                "dune_candidate_context_complete_review_only",
                (output_dir / "dune_candidate_context_completed_records_fixed.jsonl").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
