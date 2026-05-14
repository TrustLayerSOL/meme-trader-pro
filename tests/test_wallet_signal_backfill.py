import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_outcome_ledger import build_records
from wallets.wallet_outcome_ledger import build_wallet_outcome_ledger


class WalletSignalBackfillTests(unittest.TestCase):
    def test_build_records_includes_wallet_performance_signals_as_unknown_outcome_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper.json"
            rejections = root / "rejections.jsonl"
            performance = root / "wallet_performance.json"
            paper.write_text(json.dumps({"open_trades": [], "closed_trades": [], "failed_trades": []}))
            rejections.write_text("")
            performance.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "mint": "MintA",
                                "wallets": ["WalletA", "WalletB"],
                                "score": 48,
                                "signal_type": "weighted_early_signal",
                                "token_age_seconds": 72,
                                "should_trade": False,
                            }
                        ]
                    }
                )
            )

            records = build_records(
                paper_path=paper,
                rejection_path=rejections,
                performance_path=performance,
            )
            ledger = build_wallet_outcome_ledger(records)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "wallet_performance_signal")
        self.assertEqual(records[0]["later_token_outcome"]["outcome_type"], "unknown")
        self.assertEqual(ledger["counts"]["wallets"], 2)
        self.assertEqual(ledger["wallets"]["WalletA"]["known_outcomes"], 0)

    def test_build_records_links_wallet_signal_to_later_snapshot_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper.json"
            rejections = root / "rejections.jsonl"
            performance = root / "wallet_performance.json"
            db = root / "snapshots.db"
            paper.write_text(json.dumps({"open_trades": [], "closed_trades": [], "failed_trades": []}))
            rejections.write_text("")
            performance.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "mint": "MintA",
                                "wallets": ["WalletA"],
                                "score": 48,
                                "signal_type": "weighted_early_signal",
                                "time": 100,
                                "token_age_seconds": 72,
                                "should_trade": False,
                            }
                        ]
                    }
                )
            )
            conn = sqlite3.connect(db)
            conn.execute(
                "create table token_snapshots (id integer primary key, time real, mint text, source text, context text, price real, liquidity real, risk_label text, payload_json text)"
            )
            conn.executemany(
                "insert into token_snapshots (time, mint, price, liquidity, risk_label) values (?, ?, ?, ?, ?)",
                [
                    (101, "MintA", 0.01, 10_000, None),
                    (130, "MintA", 0.018, 14_000, None),
                    (160, "MintA", 0.015, 13_000, None),
                ],
            )
            conn.commit()
            conn.close()

            records = build_records(
                paper_path=paper,
                rejection_path=rejections,
                performance_path=performance,
                snapshot_db_path=db,
            )
            ledger = build_wallet_outcome_ledger(records)

        self.assertEqual(records[0]["later_token_outcome"]["outcome_type"], "runner")
        self.assertEqual(ledger["wallets"]["WalletA"]["known_outcomes"], 1)
        self.assertEqual(ledger["wallets"]["WalletA"]["runner_participation"], 1)


if __name__ == "__main__":
    unittest.main()
