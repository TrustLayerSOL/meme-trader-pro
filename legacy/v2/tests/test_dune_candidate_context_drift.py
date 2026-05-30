import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_context_drift import write_dune_candidate_context_drift
from wallets.dune_candidate_context_drift import build_dune_candidate_context_drift


def record(event_id="E1", *, price=0.01, liquidity=1000.0, market_cap=10000.0, outcome="flat"):
    return {
        "event_id": event_id,
        "wallet": "WalletA",
        "token_mint": "MintA",
        "signal_time": 100.0,
        "transaction_signature": "SigA",
        "status": "forward_outcome_labeled",
        "block_reasons": [],
        "decision_context": {
            "estimated_entry_context": {
                "price": price,
                "price_usd": price,
                "liquidity": liquidity,
                "market_cap": market_cap,
                "decision_time_safe": True,
            }
        },
        "outcome_window_labels": {"15m": {"outcome_type": outcome}},
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


class DuneCandidateContextDriftTests(unittest.TestCase):
    def test_matches_local_context_and_marks_no_material_drift_under_threshold(self):
        report = build_dune_candidate_context_drift(
            dune_completed_records=[record(price=0.009, liquidity=1000.0, market_cap=10000.0)],
            local_records=[record(price=0.01, liquidity=1000.0, market_cap=10000.0)],
            generated_at=1000.0,
            max_price_delta_pct=25.0,
        )

        self.assertTrue(report["review_only"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["dune_records_scanned"], 1)
        self.assertEqual(report["summary"]["local_matches"], 1)
        self.assertEqual(report["summary"]["no_material_drift_records"], 1)
        self.assertEqual(report["summary"]["material_price_drift_records"], 0)
        row = report["drift_records"][0]
        self.assertEqual(row["drift_status"], "no_material_drift")
        self.assertAlmostEqual(row["price_delta_pct"], -10.0)
        self.assertTrue(row["liquidity_match"])
        self.assertTrue(row["market_cap_match"])
        self.assertTrue(row["outcome_15m_match"])

    def test_flags_material_price_drift_and_missing_local_rows(self):
        report = build_dune_candidate_context_drift(
            dune_completed_records=[
                record(event_id="E1", price=0.005),
                record(event_id="Missing", price=0.01),
            ],
            local_records=[record(event_id="E1", price=0.01)],
            generated_at=1000.0,
            max_price_delta_pct=25.0,
        )

        self.assertEqual(report["summary"]["material_price_drift_records"], 1)
        self.assertEqual(report["summary"]["missing_local_match_records"], 1)
        self.assertEqual([row["drift_status"] for row in report["drift_records"]], ["material_price_drift", "missing_local_match"])

    def test_writer_exports_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dune_path = root / "dune.jsonl"
            local_path = root / "local.jsonl"
            output_dir = root / "out"
            dune_path.write_text(json.dumps(record(price=0.009), sort_keys=True) + "\n", encoding="utf-8")
            local_path.write_text(json.dumps(record(price=0.01), sort_keys=True) + "\n", encoding="utf-8")

            report = write_dune_candidate_context_drift(
                dune_completed_records_path=dune_path,
                local_records_path=local_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertEqual(report["summary"]["local_matches"], 1)
            self.assertTrue((output_dir / "dune_candidate_context_drift_fixed.json").exists())
            self.assertTrue((output_dir / "dune_candidate_context_drift_fixed.csv").exists())
            self.assertTrue((output_dir / "dune_candidate_context_drift_fixed.md").exists())
            self.assertIn("no_material_drift", (output_dir / "dune_candidate_context_drift_fixed.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
