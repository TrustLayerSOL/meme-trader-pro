import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_outcome_resolution import write_forward_outcome_resolution_report
from wallets.forward_outcome_resolution import build_forward_outcome_resolution_report


def evidence_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "observed_action": "buy",
        "timestamp": 100.0,
        "transaction_signature": "SigA",
        "collection_source": "forward_wallet_activity",
        "forward_observation": True,
        "estimated_entry_context": {
            "price": 0.01,
            "liquidity": 10_000,
            "market_cap": 100_000,
            "source": "forward_market_context:dexscreener",
            "snapshot_time": 102.0,
            "snapshot_lag_seconds": 2.0,
            "decision_time_safe": True,
            "forward_capture": True,
        },
        "estimated_exit_context": {"price": None, "decision_time_safe": True},
        "later_token_outcome": {
            "source": "forward_wallet_activity",
            "outcome_type": "pending_forward_outcome",
            "windows": {},
        },
        "risk_flags": ["forward_current_activity"],
    }
    row.update(overrides)
    return row


def snapshot(time_value, price, liquidity=10_000, *, mint="MintA", risk_label=None):
    return {
        "time": time_value,
        "mint": mint,
        "source": "forward_market_context:dexscreener",
        "price": price,
        "liquidity": liquidity,
        "market_cap": price * 10_000_000,
        "risk_label": risk_label,
        "payload": {"forward_capture": True},
    }


class ForwardOutcomeResolutionTests(unittest.TestCase):
    def test_resolves_fixed_windows_from_forward_snapshots_without_trust_mutation(self):
        report = build_forward_outcome_resolution_report(
            evidence_records=[evidence_row()],
            market_snapshots=[
                snapshot(102, 0.01),
                snapshot(125, 0.018, 12_000),
                snapshot(210, 0.012, 11_000),
                snapshot(390, 0.006, 9_000),
                snapshot(980, 0.001, 900, risk_label="EMERGENCY"),
            ],
            generated_at=1100,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["records_scanned"], 1)
        self.assertEqual(report["summary"]["known_15m_outcomes"], 1)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        record = report["records"][0]
        self.assertEqual(record["status"], "forward_outcome_labeled")
        self.assertEqual(record["outcome_window_labels"]["30s"]["outcome_type"], "runner")
        self.assertEqual(record["outcome_window_labels"]["15m"]["outcome_type"], "rug")
        self.assertEqual(record["later_token_outcome"]["windows"]["15m"]["source"], "forward_market_context_snapshots")
        self.assertNotIn("outcome_type", json.dumps(record["decision_context"]))

    def test_keeps_immature_windows_pending_instead_of_guessing(self):
        report = build_forward_outcome_resolution_report(
            evidence_records=[evidence_row()],
            market_snapshots=[snapshot(102, 0.01), snapshot(110, 0.011)],
            generated_at=115,
        )

        record = report["records"][0]
        self.assertEqual(record["status"], "pending_forward_outcome_windows")
        self.assertEqual(record["outcome_window_labels"]["30s"]["status"], "pending_forward_window")
        self.assertEqual(record["outcome_window_labels"]["30s"]["outcome_type"], "unknown")
        self.assertEqual(report["summary"]["pending_windows"], 4)
        self.assertEqual(report["summary"]["known_15m_outcomes"], 0)

    def test_writer_outputs_report_records_and_daily_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_path = root / "evidence.jsonl"
            snapshots_path = root / "snapshots.jsonl"
            report_path = root / "forward_outcomes.json"
            records_path = root / "forward_outcomes.jsonl"
            daily_json_path = root / "daily.json"
            daily_md_path = root / "daily.md"
            evidence_path.write_text(json.dumps(evidence_row()) + "\n", encoding="utf-8")
            snapshots_path.write_text(
                "\n".join(
                    [
                        json.dumps(snapshot(102, 0.01)),
                        json.dumps(snapshot(125, 0.018, 12_000)),
                        json.dumps(snapshot(980, 0.001, 900, risk_label="EMERGENCY")),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = write_forward_outcome_resolution_report(
                evidence_path=evidence_path,
                market_context_path=snapshots_path,
                report_path=report_path,
                records_path=records_path,
                daily_json_path=daily_json_path,
                daily_markdown_path=daily_md_path,
                generated_at=1100,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertTrue(daily_json_path.exists())
            self.assertTrue(daily_md_path.exists())
            self.assertEqual(report["summary"]["known_15m_outcomes"], 1)
            daily = json.loads(daily_json_path.read_text(encoding="utf-8"))
            self.assertEqual(daily["summary"]["days"], 1)
            self.assertIn("Forward Calibration", daily_md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
