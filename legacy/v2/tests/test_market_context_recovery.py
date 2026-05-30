import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.recover_market_context_from_json import (
    build_market_context_snapshots,
    recover_market_context_snapshots,
)


class MarketContextRecoveryTests(unittest.TestCase):
    def test_builds_decision_time_snapshots_from_surviving_json_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "data" / "wallet_evidence"
            replay_dir = root / "data" / "historical_replay"
            rejected_dir = root / "data" / "rejected_signals"
            evidence_dir.mkdir(parents=True)
            replay_dir.mkdir(parents=True)
            rejected_dir.mkdir(parents=True)
            (evidence_dir / "wallet_history_evidence_enriched.jsonl").write_text(
                json.dumps(
                    {
                        "wallet": "WalletA",
                        "token_mint": "MintA",
                        "timestamp": 1000.0,
                        "transaction_signature": "SigA",
                        "estimated_entry_context": {
                            "price": 1.23,
                            "liquidity": 4567,
                            "market_cap": 123000,
                            "snapshot_time": 990.0,
                            "decision_time_safe": True,
                            "source": "wallet_event_market_enriched",
                        },
                    }
                )
                + "\n"
            )
            (replay_dir / "replay_events.jsonl").write_text(
                json.dumps(
                    {
                        "mint": "MintB",
                        "signal_timestamp": 2000.0,
                        "source": "paper_trade",
                        "decision_context": {
                            "market": {
                                "price": 2.0,
                                "liquidity": 8000,
                                "market_cap": 200000,
                                "token_age_seconds": 42,
                            },
                            "risk": {"risk_label": "LOW_RISK"},
                        },
                    }
                )
                + "\n"
            )
            (rejected_dir / "rejections.jsonl").write_text(
                json.dumps(
                    {
                        "mint": "MintC",
                        "recorded_at": 3000.0,
                        "rejection reason": "liquidity_too_low",
                        "signal context": {
                            "market_info": {
                                "price": 3.0,
                                "liquidity": 9000,
                                "market_cap": 300000,
                            }
                        },
                    }
                )
                + "\n"
            )

            snapshots = build_market_context_snapshots(root)

        by_mint = {row["mint"]: row for row in snapshots}
        self.assertEqual(set(by_mint), {"MintA", "MintB", "MintC"})
        self.assertEqual(by_mint["MintA"]["time"], 990.0)
        self.assertEqual(by_mint["MintA"]["price"], 1.23)
        self.assertEqual(by_mint["MintA"]["payload"]["market_cap"], 123000)
        self.assertTrue(by_mint["MintA"]["payload"]["decision_time_safe"])
        self.assertEqual(by_mint["MintB"]["risk_label"], "LOW_RISK")
        self.assertEqual(by_mint["MintC"]["payload"]["rejection_reason"], "liquidity_too_low")

    def test_recovery_is_idempotent_for_recovered_snapshot_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            evidence_dir = data_dir / "wallet_evidence"
            evidence_dir.mkdir(parents=True)
            db_path = data_dir / "memetrader.db"
            (evidence_dir / "wallet_history_evidence_enriched.jsonl").write_text(
                json.dumps(
                    {
                        "wallet": "WalletA",
                        "token_mint": "MintA",
                        "timestamp": 1000.0,
                        "estimated_entry_context": {
                            "price": 1.0,
                            "liquidity": 1000,
                            "market_cap": 10000,
                            "snapshot_time": 1000.0,
                            "decision_time_safe": True,
                        },
                    }
                )
                + "\n"
            )

            first = recover_market_context_snapshots(root=root, db_path=db_path)
            second = recover_market_context_snapshots(root=root, db_path=db_path)

            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM token_snapshots").fetchone()[0]

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["skipped_existing"], 1)
        self.assertEqual(count, 1)

    def test_recovers_entry_context_from_archived_enrichment_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "data" / "reports" / "wallet_backfills"
            archive_dir.mkdir(parents=True)
            (archive_dir / "wallet_evidence_enrichment_20260515-103825.json").write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "wallet": "WalletArchived",
                                "token_mint": "MintArchived",
                                "timestamp": 5000.0,
                                "estimated_entry_context": {
                                    "price": 5.0,
                                    "liquidity": 50000,
                                    "market_cap": 500000,
                                    "snapshot_time": 4990.0,
                                    "source": "archived_market_context",
                                    "decision_time_safe": True,
                                },
                            }
                        ]
                    }
                )
            )

            snapshots = build_market_context_snapshots(root)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["mint"], "MintArchived")
        self.assertEqual(snapshots[0]["time"], 4990.0)
        self.assertEqual(snapshots[0]["price"], 5.0)
        self.assertEqual(snapshots[0]["payload"]["wallet"], "WalletArchived")

    def test_archived_enrichment_can_restore_context_for_same_current_evidence_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_dir = root / "data" / "wallet_evidence"
            archive_dir = root / "data" / "reports" / "wallet_backfills"
            evidence_dir.mkdir(parents=True)
            archive_dir.mkdir(parents=True)
            current_row = {
                "wallet": "WalletA",
                "token_mint": "MintA",
                "timestamp": 7000.0,
                "transaction_signature": "SigA",
                "estimated_entry_context": {"price": None, "decision_time_safe": True},
            }
            archived_row = {
                **current_row,
                "estimated_entry_context": {
                    "price": 7.0,
                    "liquidity": 70000,
                    "market_cap": 700000,
                    "snapshot_time": 6990.0,
                    "source": "archived_market_context",
                    "decision_time_safe": True,
                },
            }
            (evidence_dir / "wallet_history_evidence_enriched.jsonl").write_text(json.dumps(current_row) + "\n")
            (archive_dir / "wallet_evidence_enrichment_20260515-103825.json").write_text(
                json.dumps({"evidence_records": [archived_row]})
            )

            snapshots = build_market_context_snapshots(root)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["mint"], "MintA")
        self.assertEqual(snapshots[0]["price"], 7.0)


if __name__ == "__main__":
    unittest.main()
