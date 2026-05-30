import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from analysis.export_sqlite_skips import export_sqlite_skips_to_rejections, load_exported_decision_ids


class ExportSqliteSkipsTests(unittest.TestCase):
    def test_export_appends_once_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            out = Path(tmp) / "rej.jsonl"
            conn = sqlite3.connect(str(db))
            conn.execute(
                """
                CREATE TABLE decision_records (
                    decision_id TEXT PRIMARY KEY,
                    created_at REAL,
                    updated_at REAL,
                    mint TEXT,
                    signal_type TEXT,
                    scanner_stage TEXT,
                    final_action TEXT,
                    action_reason TEXT,
                    paper_lane TEXT,
                    should_trade INTEGER,
                    total_score REAL,
                    threshold REAL,
                    edge_score REAL,
                    edge_verdict TEXT,
                    risk_label TEXT,
                    risk_score REAL,
                    buy_quote_pass INTEGER,
                    sell_quote_pass INTEGER,
                    position_size_usd REAL,
                    trade_id TEXT,
                    trade_status TEXT,
                    entry_time REAL,
                    close_time REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    payload_json TEXT,
                    result_json TEXT
                )
                """
            )
            pl = {
                "rule_outcomes": {
                    "scoring": {
                        "reasons": [
                            "BLOCK: thin liquidity",
                            "market_radar_skip: low score",
                        ],
                    },
                },
            }
            conn.execute(
                """
                INSERT INTO decision_records (
                    decision_id, created_at, updated_at, mint, signal_type,
                    final_action, action_reason, paper_lane, should_trade,
                    total_score, threshold, edge_score, risk_label, payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "dec_test1",
                    1.0,
                    2.0,
                    "MintA",
                    "cluster",
                    "skip",
                    None,
                    "main",
                    0,
                    55.0,
                    68.0,
                    40.0,
                    "MEDIUM_RISK",
                    json.dumps(pl),
                ),
            )
            conn.commit()
            conn.close()

            s1 = export_sqlite_skips_to_rejections(db_path=db, output_path=out, limit=100, dry_run=False)
            self.assertEqual(s1["appended"], 1)
            self.assertEqual(s1["rows_scanned"], 1)

            s2 = export_sqlite_skips_to_rejections(db_path=db, output_path=out, limit=100, dry_run=False)
            self.assertEqual(s2["appended"], 0)
            self.assertEqual(s2["skipped_duplicate"], 1)

            lines = out.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["source"], "sqlite_skip_export")
            self.assertEqual(row["decision_id"], "dec_test1")
            self.assertIn("BLOCK: thin liquidity", row["rejection reason"])

    def test_load_exported_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.jsonl"
            p.write_text(
                '{"decision_id":"a"}\n{"decision_id":"b"}\n',
                encoding="utf-8",
            )
            ids = load_exported_decision_ids(p)
            self.assertEqual(ids, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
