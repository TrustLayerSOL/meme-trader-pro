import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_nonoverlap_slice import write_dune_candidate_nonoverlap_slice
from wallets.dune_candidate_nonoverlap_slice import build_dune_candidate_nonoverlap_slice


WALLET = "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY"


def local_record(event_id="E1", *, signature="SigLocal", mint="MintA", signal_time=1000.0):
    return {
        "event_id": event_id,
        "wallet": WALLET,
        "token_mint": mint,
        "transaction_signature": signature,
        "signal_time": signal_time,
        "status": "forward_outcome_labeled",
        "block_reasons": [],
        "decision_context": {
            "estimated_entry_context": {
                "price": 0.01,
                "liquidity": 1000.0,
                "market_cap": 10000.0,
                "snapshot_time": signal_time + 10,
                "execution_price_quote": 0.01,
            }
        },
        "outcome_window_labels": {"15m": {"outcome_type": "runner"}},
    }


def dune_row(*, signature="SigDune", mint="MintB", block_time="2026-05-01 00:00:00.000 UTC"):
    return {
        "wallet_address": WALLET,
        "tx_hash": signature,
        "block_time": block_time,
        "token_mint": mint,
        "amount_usd": 12.5,
        "price_usd": 0.02,
    }


class DuneCandidateNonoverlapSliceTests(unittest.TestCase):
    def test_classifies_nonoverlap_dex_rows_as_blocked_historical_candidates(self):
        report = build_dune_candidate_nonoverlap_slice(
            dune_rows={"candidate_dex_trades": [
                dune_row(signature="SigLocal", mint="MintA"),
                dune_row(signature="SigNew", mint="MintB"),
            ]},
            local_records=[local_record()],
            candidate_wallets=[WALLET],
            generated_at=1000.0,
        )

        self.assertTrue(report["review_only"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["dune_dex_rows"], 2)
        self.assertEqual(report["summary"]["local_overlap_rows"], 1)
        self.assertEqual(report["summary"]["nonoverlap_rows"], 1)
        self.assertEqual(report["summary"]["price_context_candidate_rows"], 1)
        self.assertEqual(report["summary"]["proof_ready_rows"], 0)
        candidate = report["nonoverlap_records"][0]
        self.assertEqual(candidate["status"], "blocked_nonoverlap_historical_context")
        self.assertIn("missing_decision_time_liquidity", candidate["block_reasons"])
        self.assertIn("missing_decision_time_market_cap", candidate["block_reasons"])
        self.assertIn("missing_forward_outcome_window", candidate["block_reasons"])
        self.assertFalse(candidate["proof_ready"])

    def test_time_window_overlap_is_not_counted_as_nonoverlap(self):
        report = build_dune_candidate_nonoverlap_slice(
            dune_rows={"candidate_dex_trades": [
                dune_row(signature="OtherSig", mint="MintA", block_time="1970-01-01 00:16:45.000 UTC"),
            ]},
            local_records=[local_record(signal_time=1000.0, mint="MintA")],
            candidate_wallets=[WALLET],
            generated_at=1000.0,
            max_time_delta_seconds=10.0,
        )

        self.assertEqual(report["summary"]["local_overlap_rows"], 1)
        self.assertEqual(report["summary"]["nonoverlap_rows"], 0)

    def test_writer_exports_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dune_path = root / "dune.json"
            local_path = root / "local.jsonl"
            output_dir = root / "out"
            dune_path.write_text(json.dumps({"candidate_dex_trades": [dune_row()]}, sort_keys=True), encoding="utf-8")
            local_path.write_text(json.dumps(local_record(), sort_keys=True) + "\n", encoding="utf-8")

            report = write_dune_candidate_nonoverlap_slice(
                dune_rows_path=dune_path,
                local_records_path=local_path,
                output_dir=output_dir,
                run_id="fixed",
                candidate_wallets=[WALLET],
                generated_at=1000.0,
            )

            self.assertEqual(report["summary"]["nonoverlap_rows"], 1)
            self.assertTrue((output_dir / "dune_candidate_nonoverlap_slice_fixed.json").exists())
            self.assertTrue((output_dir / "dune_candidate_nonoverlap_slice_fixed.csv").exists())
            self.assertTrue((output_dir / "dune_candidate_nonoverlap_slice_fixed.md").exists())
            self.assertIn("blocked_nonoverlap_historical_context", (output_dir / "dune_candidate_nonoverlap_slice_fixed.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
