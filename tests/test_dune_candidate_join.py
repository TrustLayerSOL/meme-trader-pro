import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_join import write_dune_candidate_join
from wallets.dune_candidate_join import build_dune_candidate_join_report


WALLET_A = "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY"
WALLET_B = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"
OTHER = "OtherWallet"


def event(wallet, event_id, mint, ts, signature="SigA", *, status="blocked_missing_forward_entry_context"):
    return {
        "event_id": event_id,
        "wallet": wallet,
        "token_mint": mint,
        "signal_time": float(ts),
        "transaction_signature": signature,
        "status": status,
    }


def dune_row(wallet, mint, tx_hash, block_time, *, price_usd=0.01):
    return {
        "wallet_address": wallet,
        "token_mint": mint,
        "tx_hash": tx_hash,
        "block_time": block_time,
        "amount_usd": 25.0,
        "price_usd": price_usd,
    }


class DuneCandidateJoinTests(unittest.TestCase):
    def test_matches_candidate_events_by_signature_and_keeps_context_not_proof_ready(self):
        report = build_dune_candidate_join_report(
            records=[
                event(WALLET_A, "A1", "MintA", 1000, signature="SigA"),
                event(OTHER, "Other", "MintA", 1000, signature="SigA"),
            ],
            dune_dex_rows=[dune_row(WALLET_A, "MintA", "SigA", "1970-01-01 00:16:40.000 UTC")],
            candidate_wallets=[WALLET_A],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["candidate_events_scanned"], 1)
        self.assertEqual(report["summary"]["matched_events"], 1)
        self.assertEqual(report["summary"]["exact_signature_matches"], 1)
        self.assertEqual(report["summary"]["quote_anchor_candidate_events"], 1)
        self.assertEqual(report["summary"]["price_context_candidate_events"], 1)
        self.assertEqual(report["summary"]["liquidity_context_candidate_events"], 0)
        self.assertEqual(report["summary"]["market_cap_context_candidate_events"], 0)
        self.assertEqual(report["summary"]["proof_ready_events"], 0)
        joined = report["joined_events"][0]
        self.assertEqual(joined["match_type"], "signature_exact")
        self.assertEqual(joined["evidence_quality"], "dune_quote_price_candidate_not_score_ready")
        self.assertFalse(joined["proof_ready"])
        self.assertIn("liquidity", joined["missing_for_proof"])
        self.assertIn("market_cap", joined["missing_for_proof"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])
        self.assertFalse(report["promotion_allowed"])

    def test_matches_by_wallet_token_and_time_window_when_signature_missing(self):
        report = build_dune_candidate_join_report(
            records=[event(WALLET_A, "A1", "MintA", 1000, signature="")],
            dune_dex_rows=[dune_row(WALLET_A, "MintA", "SigDune", "1970-01-01 00:17:00.000 UTC")],
            candidate_wallets=[WALLET_A],
            max_time_delta_seconds=90,
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["matched_events"], 1)
        self.assertEqual(report["summary"]["time_window_matches"], 1)
        self.assertEqual(report["joined_events"][0]["match_type"], "wallet_token_time_window")
        self.assertEqual(report["joined_events"][0]["time_delta_seconds"], 20.0)

    def test_writer_exports_deterministic_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            dune_rows_path = root / "dune_rows.json"
            output_dir = root / "out"
            records_path.write_text(json.dumps(event(WALLET_A, "A1", "MintA", 1000, signature="SigA")) + "\n")
            dune_rows_path.write_text(
                json.dumps({"candidate_dex_trades": [dune_row(WALLET_A, "MintA", "SigA", "1970-01-01 00:16:40.000 UTC")]})
            )

            report = write_dune_candidate_join(
                records_path=records_path,
                dune_rows_path=dune_rows_path,
                output_dir=output_dir,
                run_id="fixed",
                candidate_wallets=[WALLET_A],
                generated_at=1000.0,
            )

            json_path = output_dir / "dune_candidate_join_fixed.json"
            csv_path = output_dir / "dune_candidate_join_events_fixed.csv"
            md_path = output_dir / "dune_candidate_join_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["generated_at"], 1000.0)
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("dune_quote_price_candidate_not_score_ready", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Dune Candidate Join", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
