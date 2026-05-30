import json
import tempfile
import unittest
from pathlib import Path

from research.historical_replay_dataset import validate_decision_time_safety
from utils.build_onchain_later_outcome_backfill import write_onchain_later_outcome_backfill_report
from wallets.onchain_later_outcome_backfill import (
    MODE,
    build_onchain_later_outcome_backfill_report,
    build_snapshot_rows_for_record,
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
    pool_token_post=500_000,
    pool_quote_post=20.0,
    block_time=130,
):
    return {
        "signature": signature,
        "token_mint": mint,
        "source_file": "data/wallet_backfills/raw_transactions/raw.jsonl",
        "transaction": {
            "blockTime": block_time,
            "slot": int(block_time),
            "meta": {
                "preTokenBalances": [
                    token_balance(wallet, mint, 0),
                    token_balance(wallet, WSOL, 10.0),
                    token_balance(pool_owner, mint, pool_token_post),
                    token_balance(pool_owner, WSOL, pool_quote_post),
                ],
                "postTokenBalances": [
                    token_balance(wallet, mint, 1_000),
                    token_balance(wallet, WSOL, 9.5),
                    token_balance(pool_owner, mint, pool_token_post),
                    token_balance(pool_owner, WSOL, pool_quote_post),
                ],
            },
            "transaction": {"signatures": [signature]},
        },
    }


def record(**overrides):
    row = {
        "decision_id": "DecisionA",
        "mint": "MintA",
        "wallets": [{"wallet": "WalletA"}],
        "signal_context": {
            "mint": "MintA",
            "entry_timestamp": 100,
            "market": {
                "price": 0.00004,
                "liquidity": 80.0,
                "quote_mint": WSOL,
            },
        },
        "decision": {"decision_timestamp": 100},
        "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
    }
    row.update(overrides)
    return row


class OnchainLaterOutcomeBackfillTests(unittest.TestCase):
    def test_builds_later_snapshots_and_labels_runner(self):
        report = build_onchain_later_outcome_backfill_report(
            records=[record()],
            raw_transactions=[
                raw_tx(signature="TooEarly", block_time=90, pool_token_post=500_000, pool_quote_post=20.0),
                raw_tx(signature="SigRun", block_time=130, pool_token_post=300_000, pool_quote_post=30.0),
            ],
            quote_price_series=[{"timestamp": 99, "price_usd": 1.0}],
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["known_15m_outcomes_added"], 1)
        outcome = report["records"][0]["later_token_outcome"]
        self.assertEqual(outcome["source"], "onchain_later_raw_transaction_pool_balances")
        self.assertEqual(outcome["windows"]["15m"]["outcome_type"], "runner")
        self.assertGreaterEqual(outcome["windows"]["15m"]["max_favorable_excursion_pct"], 100)
        self.assertEqual(report["records"][0]["snapshots_used"], 2)

    def test_liquidity_collapse_is_labeled_as_rug(self):
        report = build_onchain_later_outcome_backfill_report(
            records=[record()],
            raw_transactions=[
                raw_tx(signature="SigCollapse", block_time=150, pool_token_post=500_000, pool_quote_post=1.0),
            ],
            quote_price_series=[{"timestamp": 99, "price_usd": 1.0}],
            generated_at=1234,
        )

        outcome = report["records"][0]["later_token_outcome"]
        self.assertEqual(outcome["windows"]["15m"]["outcome_type"], "rug")
        self.assertTrue(outcome["windows"]["15m"]["rug"])

    def test_ignores_transactions_before_signal_time(self):
        snapshots = build_snapshot_rows_for_record(
            record(),
            raw_transactions=[raw_tx(signature="TooEarly", block_time=90)],
            quote_price_series=[{"timestamp": 89, "price_usd": 1.0}],
        )

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["source"], "decision_context_entry_anchor")

    def test_blocks_when_quote_price_is_future_only(self):
        report = build_onchain_later_outcome_backfill_report(
            records=[record(signal_context={"mint": "MintA", "entry_timestamp": 100, "market": {}})],
            raw_transactions=[raw_tx(block_time=130, pool_token_post=300_000, pool_quote_post=30.0)],
            quote_price_series=[{"timestamp": 131, "price_usd": 1.0}],
            generated_at=1234,
        )

        self.assertEqual(report["records"][0]["status"], "blocked_no_later_onchain_snapshots")
        self.assertIn("missing_later_snapshot_rows", report["records"][0]["block_reasons"])
        self.assertEqual(report["summary"]["known_15m_outcomes_added"], 0)

    def test_preserves_prior_onchain_backfill_as_importable_labeled_record(self):
        prior_outcome = {
            "source": "onchain_later_raw_transaction_pool_balances",
            "outcome_type": "loser",
            "onchain_later_outcome_backfill_applied": True,
            "windows": {
                "15m": {
                    "source": "onchain_later_raw_transaction_pool_balances",
                    "outcome_type": "loser",
                }
            },
        }
        report = build_onchain_later_outcome_backfill_report(
            records=[record(later_token_outcome=prior_outcome)],
            raw_transactions=[],
            quote_price_series=[],
            generated_at=1234,
        )

        row = report["records"][0]
        self.assertEqual(row["status"], "onchain_later_outcome_labeled")
        self.assertTrue(row["known_15m_added"])
        self.assertTrue(row["preserved_existing_known_outcome"])
        self.assertEqual(report["summary"]["known_15m_outcomes_added"], 1)

    def test_outcome_stays_out_of_decision_context(self):
        report = build_onchain_later_outcome_backfill_report(
            records=[record()],
            raw_transactions=[raw_tx(signature="SigRun", block_time=130, pool_token_post=300_000, pool_quote_post=30.0)],
            quote_price_series=[{"timestamp": 99, "price_usd": 1.0}],
            generated_at=1234,
        )
        event = {
            "decision_context": record()["signal_context"],
            "later_outcome": report["records"][0]["later_token_outcome"],
        }

        safety = validate_decision_time_safety(event)
        self.assertTrue(safety["decision_time_safe"])
        self.assertNotIn("outcome_type", json.dumps(event["decision_context"]))

    def test_writer_persists_report_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            raw_dir = root / "raw"
            quote_path = root / "quote.jsonl"
            report_path = root / "report.json"
            output_path = root / "outcomes.jsonl"
            raw_dir.mkdir()
            records_path.write_text(json.dumps(record()) + "\n", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx(signature="SigRun", block_time=130, pool_token_post=300_000, pool_quote_post=30.0)) + "\n", encoding="utf-8")
            quote_path.write_text(json.dumps({"timestamp": 99, "price_usd": 1.0}) + "\n", encoding="utf-8")

            report = write_onchain_later_outcome_backfill_report(
                records_path=records_path,
                raw_transactions_dir=raw_dir,
                quote_price_series_path=quote_path,
                report_path=report_path,
                output_records_path=output_path,
                generated_at=1234,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(output_path.exists())
            self.assertEqual(report["summary"]["known_15m_outcomes_added"], 1)


if __name__ == "__main__":
    unittest.main()
