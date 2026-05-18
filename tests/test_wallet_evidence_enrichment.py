import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.enrich_wallet_history_evidence import load_market_snapshots
from wallets.wallet_evidence_enrichment import (
    build_wallet_evidence_enrichment_report,
    write_wallet_evidence_enrichment_outputs,
)


class WalletEvidenceEnrichmentTests(unittest.TestCase):
    def test_enriches_entry_context_without_future_leakage(self):
        evidence = [
            {
                "schema_version": "wallet_evidence.v1",
                "wallet": "WalletA",
                "token_mint": "MintA",
                "observed_action": "buy",
                "timestamp": 1000.0,
                "transaction_signature": "SigA",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
                "estimated_exit_context": {"price": None, "decision_time_safe": True},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            }
        ]
        snapshots = [
            {"mint": "MintA", "time": 990.0, "price": 1.0, "liquidity": 1000, "market_cap": 10_000},
            {"mint": "MintA", "time": 1005.0, "price": 1.1, "liquidity": 1100, "market_cap": 11_000},
            {"mint": "MintA", "time": 1030.0, "price": 1.6, "liquidity": 1200, "market_cap": 16_000},
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=snapshots,
            replay_events=[],
            generated_at=1234.0,
        )

        row = report["evidence_records"][0]
        entry = row["estimated_entry_context"]
        self.assertEqual(report["mode"], "WALLET_EVIDENCE_ENRICHMENT_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(entry["price"], 1.0)
        self.assertEqual(entry["market_cap"], 10_000)
        self.assertEqual(entry["snapshot_time"], 990.0)
        self.assertTrue(entry["decision_time_safe"])
        self.assertNotEqual(entry["price"], 1.1)
        self.assertNotIn("entry_price", row["missing_fields"])
        self.assertEqual(row["outcome_window_labels"]["30s"]["outcome_type"], "runner")
        self.assertEqual(row["later_token_outcome"]["source"], "token_snapshots")
        self.assertEqual(report["summary"]["total_evidence_rows"], 1)
        self.assertEqual(report["summary"]["rows_with_entry_context"], 1)
        self.assertEqual(report["summary"]["enriched_rows"], 1)

    def test_records_missing_context_explicitly(self):
        evidence = [
            {
                "wallet": "WalletB",
                "token_mint": "MintMissing",
                "observed_action": "buy",
                "timestamp": 2000.0,
                "transaction_signature": "SigB",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
                "estimated_exit_context": {"price": None, "decision_time_safe": True},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            }
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=[],
            replay_events=[],
            generated_at=1234.0,
        )

        row = report["evidence_records"][0]
        self.assertEqual(row["enrichment_status"], "MISSING_MARKET_CONTEXT")
        self.assertIn("entry_price", row["missing_fields"])
        self.assertIn("later_token_outcome", row["missing_fields"])
        self.assertIn("no prior market snapshot", row["enrichment_notes"])
        self.assertEqual(report["summary"]["missing_market_context_rows"], 1)

    def test_replay_fallback_prefers_known_outcome_over_first_unknown_event(self):
        evidence = [
            {
                "wallet": "WalletC",
                "token_mint": "MintReplay",
                "observed_action": "buy",
                "timestamp": 1010.0,
                "transaction_signature": "SigC",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
                "estimated_exit_context": {"price": None, "decision_time_safe": True},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            }
        ]
        replay_events = [
            {
                "event_id": "unknown-first",
                "mint": "MintReplay",
                "signal_timestamp": 900.0,
                "later_outcome": {
                    "outcome_type": "unknown",
                    "runner": False,
                    "rug": False,
                    "dead": False,
                    "windows": {},
                },
            },
            {
                "event_id": "known-second",
                "mint": "MintReplay",
                "signal_timestamp": 1015.0,
                "later_outcome": {
                    "outcome_type": "runner",
                    "runner": True,
                    "rug": False,
                    "dead": False,
                    "windows": {
                        "15m": {
                            "outcome_type": "runner",
                            "runner": True,
                            "rug": False,
                            "dead": False,
                            "label_confidence": "medium",
                        }
                    },
                },
            },
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=[],
            replay_events=replay_events,
            generated_at=1234.0,
        )

        row = report["evidence_records"][0]
        self.assertEqual(row["later_token_outcome"]["outcome_type"], "runner")
        self.assertEqual(row["later_token_outcome"]["event_id"], "known-second")
        self.assertTrue(row["outcome_window_labels"]["15m"]["runner"])
        self.assertEqual(row["estimated_entry_context"]["price"], None)
        self.assertEqual(report["summary"]["rows_with_known_outcome"], 1)

    def test_replay_fallback_rejects_known_outcome_before_evidence_timestamp(self):
        evidence = [
            {
                "wallet": "WalletBefore",
                "token_mint": "MintReplayBefore",
                "observed_action": "buy",
                "timestamp": 1010.0,
                "transaction_signature": "SigBefore",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
                "estimated_exit_context": {"price": None, "decision_time_safe": True},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            }
        ]
        replay_events = [
            {
                "event_id": "known-before",
                "mint": "MintReplayBefore",
                "signal_timestamp": 1005.0,
                "later_outcome": {
                    "outcome_type": "rug",
                    "runner": False,
                    "rug": True,
                    "dead": False,
                    "windows": {},
                },
            }
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=[],
            replay_events=replay_events,
            generated_at=1234.0,
        )

        row = report["evidence_records"][0]
        self.assertEqual(row["later_token_outcome"]["outcome_type"], "unknown")
        self.assertEqual(report["summary"]["rows_with_known_outcome"], 0)

    def test_wallet_lifecycle_exit_labels_buy_without_snapshot_or_replay_outcome(self):
        evidence = [
            {
                "wallet": "WalletLife",
                "token_mint": "MintLife",
                "observed_action": "buy",
                "timestamp": 1000.0,
                "transaction_signature": "BuySig",
                "estimated_entry_context": {
                    "price": 1.0,
                    "liquidity": 1000.0,
                    "market_cap": 10_000.0,
                    "source": "fixture_decision_context",
                    "decision_time_safe": True,
                },
                "estimated_exit_context": {"price": None},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            },
            {
                "wallet": "WalletLife",
                "token_mint": "MintLife",
                "observed_action": "sell",
                "timestamp": 1100.0,
                "transaction_signature": "SellSig",
                "estimated_entry_context": {
                    "price": 1.6,
                    "liquidity": 1400.0,
                    "market_cap": 16_000.0,
                    "source": "fixture_sell_context",
                    "decision_time_safe": True,
                },
                "estimated_exit_context": {"price": None},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            },
        ]
        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=[],
            replay_events=[],
            generated_at=1234.0,
        )

        buy = report["evidence_records"][0]
        self.assertEqual(buy["later_token_outcome"]["source"], "wallet_lifecycle_exit")
        self.assertEqual(buy["later_token_outcome"]["outcome_type"], "runner")
        self.assertEqual(buy["estimated_entry_context"]["price"], 1.0)
        self.assertEqual(buy["estimated_exit_context"]["price"], 1.6)
        self.assertFalse(buy["estimated_exit_context"]["decision_time_safe"])
        self.assertTrue(buy["estimated_exit_context"]["future_outcome_separated"])
        self.assertEqual(report["summary"]["rows_with_known_outcome"], 1)

    def test_wallet_lifecycle_exit_can_use_matching_quote_execution_prices(self):
        evidence = [
            {
                "wallet": "WalletQuoteLife",
                "token_mint": "MintQuoteLife",
                "observed_action": "buy",
                "timestamp": 1000.0,
                "transaction_signature": "BuyQuoteSig",
                "estimated_entry_context": {
                    "execution_price_quote": 0.01,
                    "quote_mint": "So11111111111111111111111111111111111111112",
                    "decision_time_safe": True,
                },
                "estimated_exit_context": {"price": None},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            },
            {
                "wallet": "WalletQuoteLife",
                "token_mint": "MintQuoteLife",
                "observed_action": "sell",
                "timestamp": 1100.0,
                "transaction_signature": "SellQuoteSig",
                "estimated_entry_context": {
                    "execution_price_quote": 0.016,
                    "quote_mint": "So11111111111111111111111111111111111111112",
                    "decision_time_safe": True,
                },
                "estimated_exit_context": {"price": None},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            },
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=[],
            replay_events=[],
            generated_at=1234.0,
        )

        buy = report["evidence_records"][0]
        self.assertEqual(buy["later_token_outcome"]["outcome_type"], "runner")
        self.assertEqual(buy["estimated_exit_context"]["price"], 0.016)
        self.assertEqual(buy["estimated_exit_context"]["source"], "wallet_lifecycle_quote_execution_context")

    def test_replay_fallback_does_not_overwrite_snapshot_known_outcome(self):
        evidence = [
            {
                "wallet": "WalletD",
                "token_mint": "MintSnapshotWins",
                "observed_action": "buy",
                "timestamp": 1000.0,
                "transaction_signature": "SigD",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
                "estimated_exit_context": {"price": None, "decision_time_safe": True},
                "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                "outcome_window_labels": {},
                "risk_flags": [],
            }
        ]
        snapshots = [
            {"mint": "MintSnapshotWins", "time": 1000.0, "price": 1.0, "liquidity": 1000},
            {"mint": "MintSnapshotWins", "time": 1010.0, "price": 0.2, "liquidity": 900},
        ]
        replay_events = [
            {
                "event_id": "replay-runner",
                "mint": "MintSnapshotWins",
                "signal_timestamp": 1000.0,
                "later_outcome": {
                    "outcome_type": "runner",
                    "runner": True,
                    "rug": False,
                    "dead": False,
                    "windows": {},
                },
            }
        ]

        report = build_wallet_evidence_enrichment_report(
            evidence_records=evidence,
            market_snapshots=snapshots,
            replay_events=replay_events,
            generated_at=1234.0,
        )

        row = report["evidence_records"][0]
        self.assertEqual(row["later_token_outcome"]["source"], "token_snapshots")
        self.assertEqual(row["later_token_outcome"]["outcome_type"], "rug")
        self.assertNotEqual(row["later_token_outcome"].get("event_id"), "replay-runner")

    def test_writes_report_and_jsonl_outputs(self):
        report = build_wallet_evidence_enrichment_report(
            evidence_records=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "observed_action": "buy",
                    "timestamp": 1000.0,
                    "transaction_signature": "SigA",
                    "estimated_entry_context": {"price": None, "decision_time_safe": True},
                    "estimated_exit_context": {"price": None, "decision_time_safe": True},
                    "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
                    "outcome_window_labels": {},
                    "risk_flags": [],
                }
            ],
            market_snapshots=[{"mint": "MintA", "time": 999.0, "price": 2.0, "liquidity": 2000}],
            replay_events=[],
            generated_at=1234.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            paths = write_wallet_evidence_enrichment_outputs(
                report,
                report_path=output_dir / "report.json",
                evidence_path=output_dir / "evidence.jsonl",
                snapshot_dir=output_dir / "snapshots",
                generated_at=1234.0,
            )

            self.assertTrue(paths["report_path"].exists())
            self.assertTrue(paths["evidence_path"].exists())
            self.assertTrue(paths["snapshot_path"].exists())
            written_report = json.loads(paths["report_path"].read_text())
            written_rows = [json.loads(line) for line in paths["evidence_path"].read_text().splitlines()]
            self.assertEqual(written_report["summary"]["total_evidence_rows"], 1)
            self.assertEqual(written_rows[0]["estimated_entry_context"]["price"], 2.0)

    def test_loads_market_snapshots_from_sqlite_for_target_mints(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memetrader.db"
            con = sqlite3.connect(db_path)
            con.execute("CREATE TABLE token_snapshots (time REAL, mint TEXT, source TEXT, context TEXT, price REAL, liquidity REAL, risk_label TEXT, payload_json TEXT)")
            con.execute("CREATE TABLE swap_ticks (time REAL, mint TEXT, source TEXT, price REAL, market_cap REAL, liquidity REAL, payload_json TEXT)")
            con.execute(
                "INSERT INTO token_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (990.0, "MintA", "token_snapshots", "{}", 1.0, 1000.0, None, "{}"),
            )
            con.execute(
                "INSERT INTO swap_ticks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1005.0, "MintA", "swap_ticks", 1.1, 11000.0, 1200.0, "{}"),
            )
            con.execute(
                "INSERT INTO token_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1000.0, "MintB", "token_snapshots", "{}", 9.0, 9000.0, None, "{}"),
            )
            con.commit()
            con.close()

            rows = load_market_snapshots(
                db_path,
                mints={"MintA"},
                min_time_by_mint={"MintA": 1000.0},
                max_time_by_mint={"MintA": 1000.0},
                before_seconds=20,
                after_seconds=20,
            )

            self.assertEqual({row["mint"] for row in rows}, {"MintA"})
            self.assertEqual([row["time"] for row in rows], [990.0, 1005.0])
            self.assertEqual(rows[1]["market_cap"], 11000.0)


if __name__ == "__main__":
    unittest.main()
