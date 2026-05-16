import json
import tempfile
import unittest
from pathlib import Path

from utils.build_onchain_supply_evidence import write_onchain_supply_evidence_report
from wallets.onchain_supply_evidence import MODE, build_onchain_supply_evidence_report


def token_balance(owner, mint, amount, decimals=6):
    raw_amount = str(int(amount * (10**decimals)))
    return {
        "owner": owner,
        "mint": mint,
        "uiTokenAmount": {
            "amount": raw_amount,
            "decimals": decimals,
            "uiAmount": amount,
            "uiAmountString": str(amount),
        },
    }


def raw_tx(signature="SigA", wallet="WalletA", mint="MintA", block_time=1000):
    return {
        "signature": signature,
        "source_file": "data/wallet_backfills/raw_transactions/raw.jsonl",
        "transaction": {
            "slot": 123,
            "blockTime": block_time,
            "meta": {
                "preTokenBalances": [token_balance(wallet, mint, 100, decimals=6)],
                "postTokenBalances": [token_balance(wallet, mint, 200, decimals=6)],
            },
            "transaction": {"signatures": [signature]},
        },
    }


def market_record(**overrides):
    record = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "decision_time_context": {
            "decision_time_safe": True,
            "price": 0.01,
            "liquidity": 10_000,
            "market_cap": None,
        },
        "block_reasons": ["blocked_missing_supply", "blocked_missing_market_cap"],
        "missing_fields": ["market_cap"],
    }
    record.update(overrides)
    return record


class OnchainSupplyEvidenceTests(unittest.TestCase):
    def test_recovers_supply_when_decision_context_already_has_supply(self):
        report = build_onchain_supply_evidence_report(
            market_context_records=[
                market_record(
                    decision_time_context={
                        **market_record()["decision_time_context"],
                        "token_supply": 1_000_000_000,
                    }
                )
            ],
            raw_transactions=[raw_tx()],
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        record = report["records"][0]
        self.assertEqual(record["status"], "supply_recovered")
        self.assertEqual(record["ui_supply"], 1_000_000_000)
        self.assertEqual(record["source"], "decision_time_context")
        self.assertEqual(record["decimals"], 6)
        self.assertEqual(report["summary"]["supply_recovered_records"], 1)

    def test_recovers_decimals_but_blocks_supply_when_raw_transaction_has_no_mint_supply(self):
        report = build_onchain_supply_evidence_report(
            market_context_records=[market_record()],
            raw_transactions=[raw_tx()],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "needs_archival_supply")
        self.assertEqual(record["decimals"], 6)
        self.assertIsNone(record["ui_supply"])
        self.assertIn("blocked_missing_supply", record["block_reasons"])
        self.assertIn("raw transaction token balances expose decimals but not total supply", record["notes"])

    def test_refuses_current_only_supply_as_score_ready(self):
        report = build_onchain_supply_evidence_report(
            market_context_records=[
                market_record(
                    decision_time_context={
                        **market_record()["decision_time_context"],
                        "current_supply": 1_000_000_000,
                    }
                )
            ],
            raw_transactions=[raw_tx()],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "unsafe_current_only")
        self.assertIsNone(record["ui_supply"])
        self.assertIn("blocked_current_supply_not_decision_time_safe", record["block_reasons"])

    def test_writer_persists_report_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_records = root / "onchain_market_context_recovery_records.jsonl"
            raw_dir = root / "raw_transactions"
            report_path = root / "onchain_supply_evidence_report.json"
            records_path = root / "onchain_supply_evidence_records.jsonl"
            raw_dir.mkdir()
            source_records.write_text(json.dumps(market_record()) + "\n", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx()) + "\n", encoding="utf-8")

            report = write_onchain_supply_evidence_report(
                source_records_path=source_records,
                raw_transactions_dir=raw_dir,
                report_path=report_path,
                output_records_path=records_path,
                generated_at=1234,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertEqual(report["summary"]["records_scanned"], 1)
            rows = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintA")


if __name__ == "__main__":
    unittest.main()
