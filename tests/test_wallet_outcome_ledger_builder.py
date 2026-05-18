import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_wallet_outcome_ledger import build_records


class WalletOutcomeLedgerBuilderTests(unittest.TestCase):
    def test_build_records_labels_legacy_rejected_signal_outcomes_from_snapshots(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rejection_path = root / "rejections.jsonl"
            paper_path = root / "paper_trades.json"
            performance_path = root / "wallet_performance.json"
            db_path = root / "memetrader.db"
            signal_time = 1000.0

            paper_path.write_text(json.dumps({"open_trades": [], "closed_trades": [], "failed_trades": []}), encoding="utf-8")
            performance_path.write_text(json.dumps({"signals": []}), encoding="utf-8")
            rejection_path.write_text(
                json.dumps(
                    {
                        "decision_id": "dec-legacy",
                        "recorded_at": signal_time,
                        "source": "market_radar",
                        "rejection reason": "liquidity_below_hot_lane",
                        "signal context": {
                            "mint": "MintA",
                            "signal_type": "market_radar_hot",
                            "market_info": {"liquidity": 5000, "market_cap": 10_000, "price": 0.01},
                            "wallets": ["WalletA"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                create table token_snapshots (
                    id integer primary key autoincrement,
                    time real,
                    mint text,
                    source text,
                    context text,
                    price real,
                    liquidity real,
                    risk_label text,
                    payload_json text
                )
                """
            )
            conn.executemany(
                "insert into token_snapshots (time, mint, source, context, price, liquidity, risk_label, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (signal_time + 10, "MintA", "test", "{}", 0.01, 5000, None, "{}"),
                    (signal_time + 800, "MintA", "test", "{}", 0.02, 6000, None, "{}"),
                ],
            )
            conn.commit()
            conn.close()

            records = build_records(
                paper_path=paper_path,
                rejection_path=rejection_path,
                performance_path=performance_path,
                snapshot_db_path=db_path,
                rejection_limit=10,
            )

        self.assertEqual(len(records), 1)
        outcome_15m = records[0]["later_token_outcome"]["windows"]["15m"]
        self.assertEqual(outcome_15m["outcome_type"], "runner")
        self.assertEqual(records[0]["signal_context"]["entry_timestamp"], signal_time)
        self.assertEqual(records[0]["signal_context"]["market"]["liquidity"], 5000)


if __name__ == "__main__":
    unittest.main()
