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
