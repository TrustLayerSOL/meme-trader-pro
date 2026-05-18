import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.recover_onchain_market_context import write_onchain_market_context_recovery_report
from wallets.onchain_market_context_recovery import (
    MODE,
    build_onchain_market_context_recovery_report,
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


def raw_tx(
    *,
    signature="SigA",
    wallet="WalletA",
    mint="MintA",
    pool_owner="PoolOwnerA",
    pool_token_pre=500_000,
    pool_token_post=510_000,
    pool_quote_pre=20.0,
    pool_quote_post=19.5,
    wallet_token_pre=0,
    wallet_token_post=10_000,
    wallet_quote_pre=5.0,
    wallet_quote_post=4.5,
    block_time=1000,
):
    return {
        "signature": signature,
        "source_file": "data/wallet_backfills/raw_transactions/raw.jsonl",
        "transaction": {
            "blockTime": block_time,
            "meta": {
                "preTokenBalances": [
                    token_balance(wallet, mint, wallet_token_pre),
                    token_balance(wallet, WSOL, wallet_quote_pre),
                    token_balance(pool_owner, mint, pool_token_pre),
                    token_balance(pool_owner, WSOL, pool_quote_pre),
                ],
                "postTokenBalances": [
                    token_balance(wallet, mint, wallet_token_post),
                    token_balance(wallet, WSOL, wallet_quote_post),
                    token_balance(pool_owner, mint, pool_token_post),
                    token_balance(pool_owner, WSOL, pool_quote_post),
                ],
            },
            "transaction": {"signatures": [signature]},
        },
    }


def backfill_record(**overrides):
    record = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "status": "partial_context_recovered",
        "block_reasons": ["blocked_missing_liquidity", "blocked_missing_market_cap"],
        "missing_fields": ["liquidity", "market_cap"],
        "decision_time_context": {
            "decision_time_safe": True,
            "source": "raw_transaction_history",
            "timestamp": 1000,
            "price": 0.003,
            "price_in_quote": 0.002,
            "quote_mint": WSOL,
            "quote_usd_price": 1.5,
            "market_cap": None,
            "liquidity": None,
        },
        "later_outcome": {"outcome_type": "runner", "future_only": True},
    }
    record.update(overrides)
    return record


class OnchainMarketContextRecoveryTests(unittest.TestCase):
    def test_recovers_liquidity_from_pool_owner_reserves_without_using_later_outcome(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[backfill_record()],
            raw_transactions=[raw_tx()],
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["liquidity_recovered_records"], 1)
        self.assertEqual(report["summary"]["market_cap_recovered_records"], 0)
        record = report["records"][0]
        context = record["decision_time_context"]
        self.assertEqual(record["status"], "onchain_liquidity_recovered")
        self.assertEqual(record["recovery_method"], "onchain_pool_balance_reconstruction")
        self.assertEqual(context["liquidity"], 58.5)
        self.assertEqual(context["liquidity_usd"], 58.5)
        self.assertEqual(context["pool_quote_reserve_post"], 19.5)
        self.assertEqual(context["pool_token_reserve_post"], 510_000)
        self.assertEqual(context["pool_owner"], "PoolOwnerA")
        self.assertEqual(context["pool_context_source"], "raw_transaction_pool_balances")
        self.assertTrue(context["decision_time_safe"])
        self.assertNotIn("future_only", context)
        self.assertEqual(record["later_outcome_reference"]["future_only"], True)
        self.assertNotIn("blocked_missing_liquidity", record["block_reasons"])
        self.assertIn("blocked_missing_market_cap", record["block_reasons"])
        self.assertIn("blocked_missing_supply", record["block_reasons"])

    def test_recovers_market_cap_only_when_supply_is_present_in_decision_context(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[
                backfill_record(
                    decision_time_context={
                        **backfill_record()["decision_time_context"],
                        "token_supply": 1_000_000_000,
                    }
                )
            ],
            raw_transactions=[raw_tx()],
            generated_at=1234,
        )

        record = report["records"][0]
        context = record["decision_time_context"]
        self.assertEqual(record["status"], "onchain_liquidity_market_cap_recovered")
        self.assertEqual(context["market_cap"], 3_000_000.0)
        self.assertEqual(context["market_cap_source"], "decision_time_token_supply")
        self.assertNotIn("blocked_missing_market_cap", record["block_reasons"])
        self.assertNotIn("market_cap", record["missing_fields"])
        self.assertEqual(report["summary"]["score_ready_candidate_records"], 1)

    def test_recovers_market_cap_from_prior_local_market_snapshot(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[backfill_record()],
            raw_transactions=[raw_tx()],
            historical_market_snapshots=[
                {
                    "mint": "MintA",
                    "timestamp": 900,
                    "market_cap": 2_500_000,
                    "price": 0.0025,
                    "source": "local_token_snapshots",
                }
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        context = record["decision_time_context"]
        self.assertEqual(record["status"], "onchain_liquidity_market_cap_recovered")
        self.assertEqual(context["market_cap"], 2_500_000)
        self.assertEqual(context["market_cap_source"], "prior_decision_time_market_snapshot")
        self.assertEqual(context["market_cap_snapshot_time"], 900.0)
        self.assertEqual(context["market_cap_snapshot_age_seconds"], 100.0)
        self.assertTrue(record["score_ready_candidate"])
        self.assertNotIn("blocked_missing_market_cap", record["block_reasons"])
        self.assertNotIn("blocked_missing_supply", record["block_reasons"])

    def test_does_not_use_future_market_snapshot_for_market_cap(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[backfill_record()],
            raw_transactions=[raw_tx()],
            historical_market_snapshots=[
                {
                    "mint": "MintA",
                    "timestamp": 1001,
                    "market_cap": 2_500_000,
                    "source": "local_token_snapshots",
                }
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "onchain_liquidity_recovered")
        self.assertIsNone(record["decision_time_context"].get("market_cap"))
        self.assertIn("blocked_missing_market_cap", record["block_reasons"])
        self.assertFalse(record["score_ready_candidate"])

    def test_does_not_use_stale_market_snapshot_for_market_cap(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[
                backfill_record(
                    timestamp=10_000,
                    decision_time_context={**backfill_record()["decision_time_context"], "timestamp": 10_000},
                )
            ],
            raw_transactions=[raw_tx()],
            historical_market_snapshots=[
                {
                    "mint": "MintA",
                    "timestamp": 100,
                    "market_cap": 2_500_000,
                    "source": "local_token_snapshots",
                }
            ],
            max_market_snapshot_age_seconds=7200,
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "onchain_liquidity_recovered")
        self.assertIsNone(record["decision_time_context"].get("market_cap"))
        self.assertIn("blocked_missing_market_cap", record["block_reasons"])
        self.assertFalse(record["score_ready_candidate"])

    def test_blocks_when_no_non_wallet_pool_owner_has_target_and_quote_reserves(self):
        report = build_onchain_market_context_recovery_report(
            backfill_records=[backfill_record()],
            raw_transactions=[
                raw_tx(
                    pool_owner="OtherOwner",
                    pool_token_pre=0,
                    pool_token_post=0,
                    pool_quote_pre=0,
                    pool_quote_post=0,
                )
            ],
            generated_at=1234,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "blocked_missing_onchain_pool_reserves")
        self.assertIsNone(record["decision_time_context"].get("liquidity"))
        self.assertIn("blocked_missing_liquidity", record["block_reasons"])

    def test_recovers_price_and_liquidity_from_pool_reserves_with_prior_quote_series(self):
        record = backfill_record(
            status="blocked_missing_price",
            block_reasons=["blocked_missing_price", "blocked_missing_liquidity", "blocked_missing_market_cap"],
            missing_fields=["entry_price", "liquidity", "market_cap"],
            decision_time_context={
                "decision_time_safe": True,
                "timestamp": 1000,
                "price": None,
                "price_in_quote": None,
                "quote_mint": None,
                "market_cap": None,
                "liquidity": None,
            },
        )

        report = build_onchain_market_context_recovery_report(
            backfill_records=[record],
            raw_transactions=[raw_tx(pool_token_post=500_000, pool_quote_post=25.0)],
            quote_price_series=[{"timestamp": 990, "price_usd": 2.0}],
            generated_at=1234,
        )

        recovered = report["records"][0]
        context = recovered["decision_time_context"]
        self.assertEqual(recovered["status"], "onchain_price_liquidity_recovered")
        self.assertEqual(context["quote_mint"], WSOL)
        self.assertEqual(context["quote_usd_price"], 2.0)
        self.assertEqual(context["quote_usd_price_source"], "historical_quote_price_series")
        self.assertEqual(context["price_in_quote"], 0.00005)
        self.assertEqual(context["price"], 0.0001)
        self.assertEqual(context["price_source"], "onchain_pool_reserve_ratio")
        self.assertEqual(context["liquidity"], 100.0)
        self.assertNotIn("blocked_missing_price", recovered["block_reasons"])
        self.assertNotIn("entry_price", recovered["missing_fields"])

    def test_does_not_use_future_quote_series_for_pool_price(self):
        record = backfill_record(
            status="blocked_missing_price",
            block_reasons=["blocked_missing_price", "blocked_missing_liquidity"],
            decision_time_context={
                "decision_time_safe": True,
                "timestamp": 1000,
                "price": None,
                "price_in_quote": None,
                "quote_mint": None,
                "market_cap": None,
                "liquidity": None,
            },
        )

        report = build_onchain_market_context_recovery_report(
            backfill_records=[record],
            raw_transactions=[raw_tx(pool_token_post=500_000, pool_quote_post=25.0)],
            quote_price_series=[{"timestamp": 1001, "price_usd": 2.0}],
            generated_at=1234,
        )

        recovered = report["records"][0]
        self.assertEqual(recovered["status"], "blocked_missing_quote_usd_price")
        self.assertIsNone(recovered["decision_time_context"].get("price"))
        self.assertIn("blocked_missing_quote_usd_price", recovered["block_reasons"])

    def test_writer_persists_report_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "historical_quote_price_enrichment_records.jsonl"
            raw_dir = root / "raw_transactions"
            quote_series_path = root / "sol_usd_price_series.jsonl"
            report_path = root / "onchain_market_context_recovery_report.json"
            output_records_path = root / "onchain_market_context_recovery_records.jsonl"
            raw_dir.mkdir()
            records_path.write_text(json.dumps(backfill_record()) + "\n", encoding="utf-8")
            quote_series_path.write_text(json.dumps({"timestamp": 990, "price_usd": 2.0}) + "\n", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx()) + "\n", encoding="utf-8")

            report = write_onchain_market_context_recovery_report(
                source_records_path=records_path,
                raw_transactions_dir=raw_dir,
                quote_price_series_path=quote_series_path,
                report_path=report_path,
                output_records_path=output_records_path,
                generated_at=1234,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(output_records_path.exists())
            self.assertEqual(report["summary"]["records_scanned"], 1)
            self.assertEqual(report["quote_price_points"], 1)
            output_rows = [json.loads(line) for line in output_records_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(output_rows[0]["transaction_signature"], "SigA")

    def test_writer_loads_prior_local_token_snapshots_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "historical_quote_price_enrichment_records.jsonl"
            raw_dir = root / "raw_transactions"
            quote_series_path = root / "sol_usd_price_series.jsonl"
            db_path = root / "memetrader.db"
            report_path = root / "onchain_market_context_recovery_report.json"
            output_records_path = root / "onchain_market_context_recovery_records.jsonl"
            raw_dir.mkdir()
            records_path.write_text(json.dumps(backfill_record()) + "\n", encoding="utf-8")
            quote_series_path.write_text("", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx()) + "\n", encoding="utf-8")
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "create table token_snapshots (time real, mint text, source text, context text, price real, liquidity real, risk_label text, payload_json text)"
                )
                conn.execute(
                    "insert into token_snapshots (time, mint, source, context, price, liquidity, risk_label, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        900,
                        "MintA",
                        "rejected_signal_context",
                        "{}",
                        0.0025,
                        5_000,
                        None,
                        json.dumps({"market_cap": 2_500_000}),
                    ),
                )

            report = write_onchain_market_context_recovery_report(
                source_records_path=records_path,
                raw_transactions_dir=raw_dir,
                quote_price_series_path=quote_series_path,
                token_snapshot_db_path=db_path,
                report_path=report_path,
                output_records_path=output_records_path,
                generated_at=1234,
            )

            self.assertEqual(report["historical_market_snapshot_points"], 1)
            output_rows = [json.loads(line) for line in output_records_path.read_text(encoding="utf-8").splitlines()]
            context = output_rows[0]["decision_time_context"]
            self.assertEqual(output_rows[0]["status"], "onchain_liquidity_market_cap_recovered")
            self.assertEqual(context["market_cap"], 2_500_000)
            self.assertEqual(context["market_cap_source"], "prior_decision_time_market_snapshot")


if __name__ == "__main__":
    unittest.main()
