import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_wallet_outcome_ledger import build_records


class WalletOutcomeLedgerBuilderTests(unittest.TestCase):
    def write_empty_inputs(self, root: Path) -> tuple[Path, Path, Path]:
        paper_path = root / "paper_trades.json"
        performance_path = root / "wallet_performance.json"
        rejection_path = root / "rejections.jsonl"
        paper_path.write_text(json.dumps({"open_trades": [], "closed_trades": [], "failed_trades": []}), encoding="utf-8")
        performance_path.write_text(json.dumps({"signals": []}), encoding="utf-8")
        return paper_path, performance_path, rejection_path

    def write_rejection(self, path: Path, *, decision_id: str = "dec-legacy", mint: str = "MintA", signal_time: float = 1000.0) -> None:
        path.write_text(
            json.dumps(
                {
                    "decision_id": decision_id,
                    "recorded_at": signal_time,
                    "source": "market_radar",
                    "rejection reason": "liquidity_below_hot_lane",
                    "signal context": {
                        "mint": mint,
                        "signal_type": "market_radar_hot",
                        "market_info": {"liquidity": 5000, "market_cap": 10_000, "price": 0.01},
                        "wallets": ["WalletA"],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def write_token_snapshot_db(self, path: Path, rows: list[tuple[float, str, str, str, float, float, str | None, str]]) -> None:
        conn = sqlite3.connect(path)
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
        if rows:
            conn.executemany(
                "insert into token_snapshots (time, mint, source, context, price, liquidity, risk_label, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        conn.commit()
        conn.close()

    def test_build_records_labels_legacy_rejected_signal_outcomes_from_snapshots(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_path, performance_path, rejection_path = self.write_empty_inputs(root)
            db_path = root / "memetrader.db"
            signal_time = 1000.0

            self.write_rejection(rejection_path, signal_time=signal_time)
            self.write_token_snapshot_db(
                db_path,
                [
                    (signal_time + 10, "MintA", "test", "{}", 0.01, 5000, None, "{}"),
                    (signal_time + 800, "MintA", "test", "{}", 0.02, 6000, None, "{}"),
                ],
            )

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

    def test_build_records_applies_onchain_later_outcome_when_snapshot_outcome_is_unknown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_path, performance_path, rejection_path = self.write_empty_inputs(root)
            db_path = root / "missing.db"
            onchain_path = root / "onchain_outcomes.jsonl"

            self.write_rejection(rejection_path, decision_id="dec-legacy", mint="MintA", signal_time=1000.0)
            onchain_path.write_text(
                json.dumps(
                    {
                        "event_id": "dec-legacy",
                        "status": "onchain_later_outcome_labeled",
                        "known_15m_added": True,
                        "later_token_outcome": {
                            "source": "onchain_later_raw_transaction_pool_balances",
                            "outcome_type": "runner",
                            "label_confidence": "medium",
                            "windows": {
                                "15m": {
                                    "source": "onchain_later_raw_transaction_pool_balances",
                                    "outcome_type": "runner",
                                    "label_confidence": "medium",
                                }
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = build_records(
                paper_path=paper_path,
                rejection_path=rejection_path,
                performance_path=performance_path,
                snapshot_db_path=db_path,
                rejection_limit=10,
                onchain_outcome_records_path=onchain_path,
            )

        self.assertEqual(len(records), 1)
        outcome = records[0]["later_token_outcome"]
        self.assertTrue(outcome["onchain_later_outcome_backfill_applied"])
        self.assertEqual(outcome["source"], "onchain_later_raw_transaction_pool_balances")
        self.assertEqual(outcome["windows"]["15m"]["outcome_type"], "runner")

    def test_build_records_does_not_overwrite_known_snapshot_outcome_with_onchain_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_path, performance_path, rejection_path = self.write_empty_inputs(root)
            db_path = root / "memetrader.db"
            onchain_path = root / "onchain_outcomes.jsonl"
            signal_time = 1000.0

            self.write_rejection(rejection_path, decision_id="dec-legacy", mint="MintA", signal_time=signal_time)
            self.write_token_snapshot_db(
                db_path,
                [
                    (signal_time + 10, "MintA", "test", "{}", 0.01, 5000, None, "{}"),
                    (signal_time + 800, "MintA", "test", "{}", 0.02, 6000, None, "{}"),
                ],
            )
            onchain_path.write_text(
                json.dumps(
                    {
                        "event_id": "dec-legacy",
                        "status": "onchain_later_outcome_labeled",
                        "known_15m_added": True,
                        "later_token_outcome": {
                            "source": "onchain_later_raw_transaction_pool_balances",
                            "outcome_type": "loser",
                            "windows": {"15m": {"outcome_type": "loser"}},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = build_records(
                paper_path=paper_path,
                rejection_path=rejection_path,
                performance_path=performance_path,
                snapshot_db_path=db_path,
                rejection_limit=10,
                onchain_outcome_records_path=onchain_path,
            )

        outcome = records[0]["later_token_outcome"]
        self.assertNotIn("onchain_later_outcome_backfill_applied", outcome)
        self.assertEqual(outcome["windows"]["15m"]["outcome_type"], "runner")
        self.assertEqual(outcome["outcome_windows_source"], "token_snapshots")


if __name__ == "__main__":
    unittest.main()
