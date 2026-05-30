import json
import tempfile
import unittest
from pathlib import Path

from utils.backfill_historical_market_context import write_historical_market_context_backfill_report
from wallets.historical_market_context_backfill import (
    MODE,
    build_historical_market_context_backfill_report,
)


WSOL = "So11111111111111111111111111111111111111112"


def token_balance(owner, mint, amount):
    return {
        "owner": owner,
        "mint": mint,
        "uiTokenAmount": {
            "uiAmount": amount,
            "uiAmountString": str(amount),
        },
    }


def raw_tx(signature, wallet, mint, token_pre, token_post, quote_pre=None, quote_post=None, block_time=1000):
    pre = [token_balance(wallet, mint, token_pre)]
    post = [token_balance(wallet, mint, token_post)]
    if quote_pre is not None:
        pre.append(token_balance(wallet, WSOL, quote_pre))
    if quote_post is not None:
        post.append(token_balance(wallet, WSOL, quote_post))
    return {
        "signature": signature,
        "wallet": wallet,
        "source_file": "data/wallet_backfills/raw_transactions/raw.jsonl",
        "transaction": {
            "blockTime": block_time,
            "meta": {
                "preTokenBalances": pre,
                "postTokenBalances": post,
            },
            "transaction": {"signatures": [signature]},
        },
    }


def missing_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "observed_action": "buy",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "token_amount_delta": 100.0,
        "enrichment_status": "MISSING_MARKET_CONTEXT",
        "estimated_entry_context": {"price": None, "decision_time_safe": True},
        "later_token_outcome": {
            "outcome_type": "runner",
            "runner": True,
            "source": "future_label",
        },
        "missing_fields": ["entry_price", "exit_price"],
        "confidence_score": 90,
    }
    row.update(overrides)
    return row


class HistoricalMarketContextBackfillTests(unittest.TestCase):
    def test_recovers_partial_context_from_raw_transaction_quote_delta(self):
        report = build_historical_market_context_backfill_report(
            wallet_evidence_enrichment={"evidence_records": [missing_row()]},
            raw_transactions=[
                raw_tx("SigA", "WalletA", "MintA", token_pre=0, token_post=100, quote_pre=1.0, quote_post=0.8)
            ],
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["records_scanned"], 1)
        self.assertEqual(report["summary"]["records_partially_recovered"], 1)
        self.assertEqual(report["summary"]["records_blocked"], 0)
        record = report["records"][0]
        self.assertEqual(record["status"], "partial_context_recovered")
        self.assertEqual(record["recovery_method"], "recovered_from_transaction_history")
        self.assertEqual(record["decision_time_context"]["source"], "raw_transaction_history")
        self.assertTrue(record["decision_time_context"]["decision_time_safe"])
        self.assertEqual(record["decision_time_context"]["quote_mint"], WSOL)
        self.assertAlmostEqual(record["decision_time_context"]["price_in_quote"], 0.002)
        self.assertEqual(record["decision_time_context"]["source_file"], "data/wallet_backfills/raw_transactions/raw.jsonl")
        self.assertNotIn("outcome_type", record["decision_time_context"])
        self.assertEqual(record["later_outcome"]["outcome_type"], "runner")
        self.assertIn("blocked_missing_liquidity", record["block_reasons"])

    def test_missing_transaction_is_blocked_with_reason(self):
        report = build_historical_market_context_backfill_report(
            wallet_evidence_enrichment={"evidence_records": [missing_row()]},
            raw_transactions=[],
            generated_at=1234,
        )

        self.assertEqual(report["summary"]["records_blocked"], 1)
        self.assertEqual(report["summary"]["block_reasons"], {"blocked_missing_transaction": 1})
        self.assertEqual(report["records"][0]["status"], "blocked_missing_transaction")

    def test_transaction_without_quote_delta_does_not_fake_price(self):
        report = build_historical_market_context_backfill_report(
            wallet_evidence_enrichment={"evidence_records": [missing_row()]},
            raw_transactions=[raw_tx("SigA", "WalletA", "MintA", token_pre=0, token_post=100)],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "blocked_missing_price")
        self.assertIsNone(record["decision_time_context"].get("price"))
        self.assertIsNone(record["decision_time_context"].get("price_in_quote"))
        self.assertEqual(report["summary"]["block_reasons"], {"blocked_missing_price": 1})

    def test_writer_persists_report_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enrichment = root / "data" / "wallet_backfills" / "wallet_evidence_enrichment_report.json"
            raw_dir = root / "data" / "wallet_backfills" / "raw_transactions"
            report_path = root / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_report.json"
            records_path = root / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_records.jsonl"
            enrichment.parent.mkdir(parents=True)
            raw_dir.mkdir(parents=True)
            enrichment.write_text(json.dumps({"evidence_records": [missing_row()]}) + "\n")
            (raw_dir / "raw.jsonl").write_text(
                json.dumps(raw_tx("SigA", "WalletA", "MintA", 0, 100, 1.0, 0.8, 1000)) + "\n"
            )

            report = write_historical_market_context_backfill_report(
                enrichment_report_path=enrichment,
                raw_transactions_dir=raw_dir,
                report_path=report_path,
                records_path=records_path,
                generated_at=1234,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertEqual(report["summary"]["records_scanned"], 1)
            self.assertEqual(json.loads(report_path.read_text())["summary"]["records_partially_recovered"], 1)
            records = [json.loads(line) for line in records_path.read_text().splitlines()]
            self.assertEqual(records[0]["transaction_signature"], "SigA")


if __name__ == "__main__":
    unittest.main()
