import json
import tempfile
import unittest
from pathlib import Path

from utils.enrich_historical_quote_prices import write_historical_quote_price_enrichment_report
from wallets.historical_quote_price_enrichment import (
    MODE,
    build_historical_quote_price_enrichment_report,
)


WSOL = "So11111111111111111111111111111111111111112"


def backfill_record(**overrides):
    record = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000.0,
        "transaction_signature": "SigA",
        "status": "partial_context_recovered",
        "block_reasons": ["blocked_missing_liquidity", "blocked_missing_market_cap"],
        "decision_time_context": {
            "decision_time_safe": True,
            "source": "raw_transaction_history",
            "timestamp": 1000.0,
            "price": None,
            "price_in_quote": 0.002,
            "quote_mint": WSOL,
            "market_cap": None,
            "liquidity": None,
        },
        "later_outcome": {"outcome_type": "runner"},
        "missing_fields": ["entry_price", "liquidity", "market_cap"],
    }
    record.update(overrides)
    return record


class HistoricalQuotePriceEnrichmentTests(unittest.TestCase):
    def test_converts_wsol_quote_price_using_prior_historical_sol_price(self):
        report = build_historical_quote_price_enrichment_report(
            backfill_records=[backfill_record()],
            quote_price_series=[{"timestamp": 900.0, "price_usd": 150.0}],
            generated_at=1234.0,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["records_scanned"], 1)
        self.assertEqual(report["summary"]["price_recovered_records"], 1)
        record = report["records"][0]
        context = record["decision_time_context"]
        self.assertEqual(record["quote_price_status"], "quote_usd_price_recovered")
        self.assertAlmostEqual(context["price"], 0.3)
        self.assertEqual(context["quote_usd_price"], 150.0)
        self.assertEqual(context["quote_usd_price_time"], 900.0)
        self.assertTrue(context["decision_time_safe"])
        self.assertNotIn("outcome_type", context)
        self.assertEqual(record["later_outcome"]["outcome_type"], "runner")
        self.assertNotIn("entry_price", record["missing_fields"])
        self.assertIn("liquidity", record["missing_fields"])

    def test_does_not_use_future_quote_price(self):
        report = build_historical_quote_price_enrichment_report(
            backfill_records=[backfill_record()],
            quote_price_series=[{"timestamp": 1001.0, "price_usd": 150.0}],
            generated_at=1234.0,
        )

        record = report["records"][0]
        self.assertEqual(record["quote_price_status"], "blocked_missing_prior_quote_usd_price")
        self.assertIsNone(record["decision_time_context"]["price"])
        self.assertIn("entry_price", record["missing_fields"])

    def test_does_not_use_stale_prior_quote_price(self):
        report = build_historical_quote_price_enrichment_report(
            backfill_records=[backfill_record()],
            quote_price_series=[{"timestamp": 1.0, "price_usd": 150.0}],
            max_quote_age_seconds=300.0,
            generated_at=1234.0,
        )

        record = report["records"][0]
        self.assertEqual(record["quote_price_status"], "blocked_stale_quote_usd_price")
        self.assertIsNone(record["decision_time_context"]["price"])

    def test_ignores_records_without_quote_price_context(self):
        report = build_historical_quote_price_enrichment_report(
            backfill_records=[
                backfill_record(
                    status="blocked_missing_price",
                    decision_time_context={
                        "decision_time_safe": True,
                        "timestamp": 1000.0,
                        "price": None,
                        "price_in_quote": None,
                        "quote_mint": None,
                    },
                )
            ],
            quote_price_series=[{"timestamp": 900.0, "price_usd": 150.0}],
            generated_at=1234.0,
        )

        self.assertEqual(report["summary"]["unsupported_records"], 1)
        self.assertEqual(report["records"][0]["quote_price_status"], "blocked_no_quote_price_context")

    def test_writer_persists_enriched_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_records = root / "source.jsonl"
            quote_series = root / "sol_prices.jsonl"
            report_path = root / "report.json"
            records_path = root / "records.jsonl"
            source_records.write_text(json.dumps(backfill_record()) + "\n", encoding="utf-8")
            quote_series.write_text(json.dumps({"timestamp": 900.0, "price_usd": 150.0}) + "\n", encoding="utf-8")

            report = write_historical_quote_price_enrichment_report(
                source_records_path=source_records,
                quote_price_series_path=quote_series,
                report_path=report_path,
                output_records_path=records_path,
                generated_at=1234.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertEqual(report["summary"]["price_recovered_records"], 1)
            rows = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
            self.assertAlmostEqual(rows[0]["decision_time_context"]["price"], 0.3)


if __name__ == "__main__":
    unittest.main()
