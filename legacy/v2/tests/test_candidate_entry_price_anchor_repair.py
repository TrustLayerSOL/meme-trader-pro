import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_entry_price_anchor_repair import write_candidate_entry_price_anchor_repair
from wallets.candidate_entry_price_anchor_repair import build_candidate_entry_price_anchor_repair


WALLET_A = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"
WALLET_B = "D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3"
OTHER = "OtherWallet"


def blocked_row(wallet, event, *, signature=None, mint=None):
    signature = signature or f"Sig{event}"
    mint = mint or f"Mint{event}"
    return {
        "event_id": f"{wallet}|{signature}|{mint}|buy|100",
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": "buy",
        "signal_time": 100.0,
        "transaction_signature": signature,
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": ["missing_forward_entry_price"],
        "decision_context": {
            "estimated_entry_context": {
                "price": None,
                "liquidity": None,
                "market_cap": None,
                "decision_time_safe": True,
            }
        },
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


def raw_anchor(wallet, signature, mint, *, action="buy", price=0.0123):
    return {
        "wallet": wallet,
        "signature": signature,
        "token_mint": mint,
        "observed_action": action,
        "execution_price_quote": price,
        "quote_mint": "So11111111111111111111111111111111111111112",
        "quote_amount_delta": -0.5,
        "execution_price_source": "test_raw_quote_anchor",
        "timestamp": 100.0,
    }


def quality_lift():
    return {
        "wallets": [
            {"wallet_address": WALLET_A, "recommended_context_action": "repair_entry_timestamp"},
            {"wallet_address": WALLET_B, "recommended_context_action": "repair_entry_timestamp"},
        ]
    }


class CandidateEntryPriceAnchorRepairTests(unittest.TestCase):
    def test_builds_candidate_only_anchor_repairs_and_rejections(self):
        records = [
            blocked_row(WALLET_A, "A", signature="SigA", mint="MintA"),
            blocked_row(WALLET_B, "B", signature="SigB", mint="MintB"),
            blocked_row(OTHER, "O", signature="SigO", mint="MintO"),
        ]
        report = build_candidate_entry_price_anchor_repair(
            context_quality_lift=quality_lift(),
            records=records,
            raw_rows=[
                raw_anchor(WALLET_A, "SigA", "MintA", price=0.01),
                raw_anchor(OTHER, "SigO", "MintO", price=0.99),
            ],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["target_wallets"], 2)
        self.assertEqual(report["summary"]["missing_entry_price_rows"], 2)
        self.assertEqual(report["summary"]["anchor_repaired_rows"], 1)
        self.assertEqual(report["summary"]["rejected_rows"], 1)
        repaired = report["anchor_repaired_records"][0]
        ctx = repaired["decision_context"]["estimated_entry_context"]
        self.assertEqual(repaired["wallet"], WALLET_A)
        self.assertEqual(ctx["execution_price_quote"], 0.01)
        self.assertEqual(ctx["price"], 0.01)
        self.assertEqual(repaired["entry_price_anchor_repair"]["method"], "preserved_raw_transaction_quote_anchor")
        self.assertFalse(repaired["wallet_list_mutation_allowed"])
        self.assertFalse(repaired["can_mutate_wallet_trust"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_rejects_rows_without_raw_anchor_or_valid_price(self):
        report = build_candidate_entry_price_anchor_repair(
            context_quality_lift=quality_lift(),
            records=[
                blocked_row(WALLET_A, "A", signature="SigA", mint="MintA"),
                blocked_row(WALLET_A, "B", signature="SigB", mint="MintB"),
            ],
            raw_rows=[raw_anchor(WALLET_A, "SigA", "MintA", price=0.0)],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["anchor_repaired_rows"], 0)
        self.assertEqual(report["summary"]["rejected_rows"], 2)
        reasons = {row["reject_reason"] for row in report["rejected_records"]}
        self.assertIn("invalid_or_missing_execution_price_quote", reasons)
        self.assertIn("missing_preserved_raw_transaction_anchor", reasons)

    def test_writer_exports_deterministic_json_csv_jsonl_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_path = root / "quality.json"
            records_path = root / "records.jsonl"
            raw_path = root / "raw.jsonl"
            output_dir = root / "out"
            quality_path.write_text(json.dumps(quality_lift(), sort_keys=True), encoding="utf-8")
            records_path.write_text(json.dumps(blocked_row(WALLET_A, "A", signature="SigA", mint="MintA"), sort_keys=True) + "\n", encoding="utf-8")
            raw_path.write_text(json.dumps(raw_anchor(WALLET_A, "SigA", "MintA", price=0.01), sort_keys=True) + "\n", encoding="utf-8")

            report = write_candidate_entry_price_anchor_repair(
                context_quality_lift_path=quality_path,
                records_path=records_path,
                raw_glob=str(raw_path),
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertTrue((output_dir / "candidate_entry_price_anchor_repair_fixed.json").exists())
            self.assertTrue((output_dir / "candidate_entry_price_anchor_repair_fixed.csv").exists())
            self.assertTrue((output_dir / "candidate_entry_price_anchor_repaired_records_fixed.jsonl").exists())
            self.assertTrue((output_dir / "candidate_entry_price_anchor_rejected_records_fixed.jsonl").exists())
            self.assertTrue((output_dir / "candidate_entry_price_anchor_repair_fixed.md").exists())
            saved = json.loads((output_dir / "candidate_entry_price_anchor_repair_fixed.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("anchor_repaired", (output_dir / "candidate_entry_price_anchor_repair_fixed.csv").read_text(encoding="utf-8"))
            self.assertIn("Candidate Entry Price Anchor Repair", (output_dir / "candidate_entry_price_anchor_repair_fixed.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
