import json
import tempfile
import unittest
from pathlib import Path

from utils.build_trusted_historical_market_snapshot_report import (
    write_trusted_historical_market_snapshot_report,
)
from wallets.trusted_historical_market_snapshot_provider import (
    MODE,
    build_trusted_historical_market_snapshot_report,
)


WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def backfill_record(**overrides):
    record = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "status": "partial_context_recovered",
        "block_reasons": ["blocked_missing_liquidity", "blocked_missing_market_cap"],
        "decision_time_context": {
            "decision_time_safe": True,
            "source": "raw_transaction_history",
            "timestamp": 1000,
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


class TrustedHistoricalMarketSnapshotProviderTests(unittest.TestCase):
    def test_partial_quote_context_is_not_score_ready_without_market_fields(self):
        report = build_trusted_historical_market_snapshot_report(
            backfill_records=[backfill_record()],
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["records_scanned"], 1)
        self.assertEqual(report["summary"]["score_ready_records"], 0)
        self.assertEqual(report["summary"]["partial_quote_context_not_score_ready"], 1)

        record = report["records"][0]
        self.assertEqual(record["snapshot_status"], "partial_quote_context_not_score_ready")
        self.assertFalse(record["score_ready"])
        self.assertEqual(record["available_decision_time_fields"], ["price_in_quote"])
        self.assertIn("historical_quote_usd_price", record["required_fields"])
        self.assertIn("liquidity", record["required_fields"])
        self.assertIn("market_cap", record["required_fields"])
        self.assertNotIn("outcome_type", record["decision_time_context"])
        self.assertEqual(record["later_outcome_reference"]["outcome_type"], "runner")

    def test_usdc_quote_counts_as_price_but_still_requires_liquidity_and_market_cap(self):
        report = build_trusted_historical_market_snapshot_report(
            backfill_records=[
                backfill_record(
                    decision_time_context={
                        "decision_time_safe": True,
                        "source": "raw_transaction_history",
                        "timestamp": 1000,
                        "price": None,
                        "price_in_quote": 0.005,
                        "quote_mint": USDC,
                        "market_cap": None,
                        "liquidity": None,
                    }
                )
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["available_decision_time_fields"], ["price_usd_from_stable_quote", "price_in_quote"])
        self.assertNotIn("historical_quote_usd_price", record["required_fields"])
        self.assertEqual(sorted(record["required_fields"]), ["liquidity", "market_cap"])
        self.assertFalse(record["score_ready"])

    def test_blocked_missing_price_needs_external_snapshot_and_does_not_invent_values(self):
        report = build_trusted_historical_market_snapshot_report(
            backfill_records=[
                backfill_record(
                    status="blocked_missing_price",
                    block_reasons=["blocked_missing_price"],
                    decision_time_context={
                        "decision_time_safe": True,
                        "timestamp": 1000,
                        "price": None,
                        "price_in_quote": None,
                        "market_cap": None,
                        "liquidity": None,
                    },
                )
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["snapshot_status"], "needs_external_historical_market_snapshot")
        self.assertFalse(record["score_ready"])
        self.assertIsNone(record["decision_time_context"]["price"])
        self.assertIsNone(record["decision_time_context"]["price_in_quote"])
        self.assertEqual(
            sorted(record["required_fields"]),
            ["liquidity", "market_cap", "price"],
        )

    def test_complete_decision_time_context_is_score_ready(self):
        report = build_trusted_historical_market_snapshot_report(
            backfill_records=[
                backfill_record(
                    status="recovered_from_trusted_snapshot",
                    block_reasons=[],
                    decision_time_context={
                        "decision_time_safe": True,
                        "timestamp": 1000,
                        "price": 0.01,
                        "price_in_quote": None,
                        "market_cap": 100000.0,
                        "liquidity": 25000.0,
                    },
                )
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["snapshot_status"], "trusted_snapshot_complete")
        self.assertTrue(record["score_ready"])
        self.assertEqual(record["required_fields"], [])
        self.assertEqual(report["summary"]["score_ready_records"], 1)

    def test_recovered_usd_price_without_liquidity_and_market_cap_is_not_score_ready(self):
        report = build_trusted_historical_market_snapshot_report(
            backfill_records=[
                backfill_record(
                    status="partial_context_recovered",
                    decision_time_context={
                        "decision_time_safe": True,
                        "timestamp": 1000,
                        "price": 0.3,
                        "price_in_quote": 0.002,
                        "quote_mint": WSOL,
                        "market_cap": None,
                        "liquidity": None,
                    },
                )
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["snapshot_status"], "price_recovered_not_score_ready")
        self.assertFalse(record["score_ready"])
        self.assertEqual(record["required_fields"], ["liquidity", "market_cap"])
        self.assertEqual(report["summary"]["price_recovered_not_score_ready"], 1)

    def test_report_groups_requirements_by_token_and_writer_persists_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "historical_market_context_backfill_records.jsonl"
            report_path = root / "trusted_historical_market_snapshot_report.json"
            output_records_path = root / "trusted_historical_market_snapshot_records.jsonl"
            records_path.write_text(
                "\n".join(
                    [
                        json.dumps(backfill_record(wallet="WalletA", transaction_signature="SigA", timestamp=1000)),
                        json.dumps(backfill_record(wallet="WalletB", transaction_signature="SigB", timestamp=1060)),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = write_trusted_historical_market_snapshot_report(
                source_records_path=records_path,
                report_path=report_path,
                output_records_path=output_records_path,
                generated_at=1234,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(output_records_path.exists())
            self.assertEqual(report["summary"]["records_scanned"], 2)
            token_group = report["snapshot_requirements_by_token"]["MintA"]
            self.assertEqual(token_group["records"], 2)
            self.assertEqual(token_group["wallets"], 2)
            self.assertEqual(token_group["first_timestamp"], 1000)
            self.assertEqual(token_group["last_timestamp"], 1060)
            self.assertIn("historical_quote_usd_price", token_group["required_fields"])
            output_rows = [json.loads(line) for line in output_records_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(output_rows), 2)


if __name__ == "__main__":
    unittest.main()
