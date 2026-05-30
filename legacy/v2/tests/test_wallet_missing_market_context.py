import json
import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_missing_market_context_targets import write_wallet_missing_market_context_targets
from wallets.wallet_missing_market_context import build_wallet_missing_market_context_targets


class WalletMissingMarketContextTests(unittest.TestCase):
    def test_groups_missing_context_rows_by_mint(self):
        report = build_wallet_missing_market_context_targets(
            wallet_evidence_enrichment={
                "evidence_records": [
                    {
                        "wallet": "WalletA",
                        "token_mint": "MintMissing",
                        "observed_action": "buy",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigA",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "confidence_score": 70,
                        "missing_fields": ["entry_price"],
                        "later_token_outcome": {"outcome_type": "unknown"},
                    },
                    {
                        "wallet": "WalletB",
                        "token_mint": "MintMissing",
                        "observed_action": "sell",
                        "timestamp": 1060.0,
                        "transaction_signature": "SigB",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "confidence_score": 90,
                        "missing_fields": ["entry_price"],
                        "later_token_outcome": {"outcome_type": "rug"},
                    },
                    {
                        "wallet": "WalletC",
                        "token_mint": "MintReady",
                        "observed_action": "buy",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigC",
                        "enrichment_status": "ENRICHED",
                        "estimated_entry_context": {"price": 1.0},
                    },
                    {
                        "wallet": "WalletQuote",
                        "token_mint": "So11111111111111111111111111111111111111112",
                        "observed_action": "buy",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigQuote",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "missing_fields": ["entry_price"],
                    },
                ]
            },
            before_seconds=30,
            after_seconds=120,
            generated_at=1234.0,
        )

        self.assertEqual(report["mode"], "WALLET_MISSING_MARKET_CONTEXT_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["target_mints"], 1)
        self.assertEqual(report["summary"]["missing_market_context_rows"], 2)
        target = report["targets"][0]
        self.assertEqual(target["token_mint"], "MintMissing")
        self.assertEqual(target["evidence_rows"], 2)
        self.assertEqual(target["unique_wallets"], 2)
        self.assertEqual(target["first_timestamp"], 1000.0)
        self.assertEqual(target["last_timestamp"], 1060.0)
        self.assertEqual(target["backfill_window"]["start_time"], 970.0)
        self.assertEqual(target["backfill_window"]["end_time"], 1180.0)
        self.assertEqual(target["observed_actions"], {"buy": 1, "sell": 1})
        self.assertEqual(target["known_outcome_rows"], 1)
        self.assertEqual(target["next_collection_step"], "BACKFILL_MARKET_CONTEXT")

    def test_dedupes_repeated_evidence_rows(self):
        report = build_wallet_missing_market_context_targets(
            wallet_evidence_enrichment={
                "evidence_records": [
                    {
                        "wallet": "WalletA",
                        "token_mint": "MintMissing",
                        "observed_action": "buy",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigA",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "missing_fields": ["entry_price"],
                    },
                    {
                        "wallet": "WalletA",
                        "token_mint": "MintMissing",
                        "observed_action": "buy",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigA",
                        "enrichment_status": "MISSING_MARKET_CONTEXT",
                        "missing_fields": ["entry_price"],
                    },
                ]
            }
        )

        self.assertEqual(report["summary"]["missing_market_context_rows"], 1)

    def test_writer_persists_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_missing_market_context_targets.json"
            source = Path(tmp) / "wallet_evidence_enrichment_report.json"
            source.write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "wallet": "WalletA",
                                "token_mint": "MintMissing",
                                "timestamp": 1000,
                                "transaction_signature": "SigA",
                                "enrichment_status": "MISSING_MARKET_CONTEXT",
                                "missing_fields": ["entry_price"],
                            }
                        ]
                    }
                )
            )

            report = write_wallet_missing_market_context_targets(
                out_path=out,
                enrichment_report_path=source,
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["target_mints"], 1)
            self.assertEqual(json.loads(out.read_text())["targets"][0]["token_mint"], "MintMissing")


if __name__ == "__main__":
    unittest.main()
