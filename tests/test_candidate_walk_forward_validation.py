import unittest
import json
import tempfile
from pathlib import Path

from utils.build_candidate_walk_forward_validation import write_candidate_walk_forward_validation_report
from wallets.candidate_walk_forward_validation import build_candidate_walk_forward_validation_report


WALLET_A = "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY"
WALLET_B = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"
WALLET_C = "D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3"


def row(wallet, event, ts, outcome="flat", *, blocked=False, context=True, token=None):
    payload = {
        "event_id": f"{wallet}-{event}",
        "wallet": wallet,
        "token_mint": token or f"Mint{event}",
        "signal_time": float(ts),
        "outcome_window_labels": {"15m": {"outcome_type": outcome, "pnl_pct": 10.0 if outcome == "runner" else 0.0}},
        "status": "resolved",
        "decision_context": {
            "estimated_entry_context": {
                "price": 0.01,
                "liquidity": 25000,
                "market_cap": 100000,
                "snapshot_time": float(ts) + 5,
                "execution_price_quote": 0.01,
            }
        },
    }
    if blocked:
        payload["status"] = "blocked_missing_forward_entry_context"
        payload["block_reasons"] = ["missing_forward_entry_context"]
    if not context:
        payload["decision_context"] = {}
    return payload


class CandidateWalkForwardValidationTests(unittest.TestCase):
    def test_filters_to_candidate_wallets_and_excludes_incomplete_rows_from_metrics(self):
        report = build_candidate_walk_forward_validation_report(
            records=[
                row(WALLET_A, "a1", 10, "runner"),
                row(WALLET_A, "a2", 20, "flat"),
                row(WALLET_A, "blocked", 30, "runner", blocked=True),
                row("OtherWallet", "other", 40, "runner"),
                row(WALLET_B, "unknown", 50, "unknown"),
                row(WALLET_B, "missing-context", 60, "runner", context=False),
            ],
            candidate_wallets=[WALLET_A, WALLET_B],
            generated_at=1000.0,
            train_fraction=0.5,
        )

        self.assertEqual(report["summary"]["candidate_wallets"], 2)
        self.assertEqual(report["summary"]["input_records"], 6)
        self.assertEqual(report["summary"]["candidate_records"], 5)
        self.assertEqual(report["summary"]["clean_records"], 2)
        self.assertEqual(report["summary"]["excluded_records"], 3)
        wallet_a = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_A)
        self.assertEqual(wallet_a["train"]["clean_records"], 1)
        self.assertEqual(wallet_a["validation"]["clean_records"], 1)
        self.assertEqual(wallet_a["validation"]["runner_count"], 0)
        self.assertIn("blocked_or_incomplete_rows_excluded_from_proof", wallet_a["reasons_not_to_trust"])

    def test_conclusions_use_only_allowed_language_and_report_degradation(self):
        report = build_candidate_walk_forward_validation_report(
            records=[
                row(WALLET_A, "train-1", 10, "runner", token="A"),
                row(WALLET_A, "train-2", 20, "runner", token="B"),
                row(WALLET_A, "train-3", 30, "runner", token="C"),
                row(WALLET_A, "validation-1", 40, "flat", token="D"),
                row(WALLET_A, "validation-2", 50, "flat", token="E"),
                row(WALLET_B, "train-1", 10, "runner", token="F"),
                row(WALLET_B, "validation-1", 20, "runner", token="G"),
                row(WALLET_C, "only-train", 10, "runner", token="H"),
            ],
            candidate_wallets=[WALLET_A, WALLET_B, WALLET_C],
            generated_at=1000.0,
            train_fraction=0.6,
            min_train_clean_rows=1,
            min_validation_clean_rows=1,
            degradation_tolerance=0.5,
        )

        allowed = {"continued_validation", "degraded", "inconclusive", "rejected"}
        self.assertTrue(all(row["conclusion"] in allowed for row in report["wallets"]))
        wallet_a = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_A)
        wallet_b = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_B)
        wallet_c = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_C)
        self.assertEqual(wallet_a["conclusion"], "degraded")
        self.assertEqual(wallet_b["conclusion"], "continued_validation")
        self.assertEqual(wallet_c["conclusion"], "inconclusive")
        self.assertGreater(report["persistence_degradation_summary"]["degraded_wallets"], 0)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_trust_mutations"], 0)
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_repaired_rows_replace_blocked_originals_before_validation(self):
        original = row(WALLET_A, "same", 10, "runner", blocked=True, token="A")
        repaired = row(WALLET_A, "same", 10, "runner", token="A")
        report = build_candidate_walk_forward_validation_report(
            records=[original, row(WALLET_A, "validation", 20, "runner", token="B")],
            repaired_records=[repaired],
            candidate_wallets=[WALLET_A],
            generated_at=1000.0,
            min_train_clean_rows=1,
            min_validation_clean_rows=1,
        )

        self.assertEqual(report["summary"]["repaired_records"], 1)
        self.assertEqual(report["summary"]["clean_records"], 2)
        self.assertEqual(report["summary"]["excluded_records"], 0)
        self.assertEqual(report["wallets"][0]["conclusion"], "continued_validation")

    def test_writer_exports_deterministic_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            output_dir = root / "out"
            records = [
                row(WALLET_A, "train", 10, "runner", token="A"),
                row(WALLET_A, "validation", 20, "runner", token="B"),
                row("OtherWallet", "other", 30, "runner", token="C"),
            ]
            records_path.write_text("\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n", encoding="utf-8")

            report = write_candidate_walk_forward_validation_report(
                records_path=records_path,
                repaired_records_path=root / "missing_repaired.jsonl",
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
                candidate_wallets=[WALLET_A],
                min_train_clean_rows=1,
                min_validation_clean_rows=1,
            )

            json_path = output_dir / "candidate_walk_forward_validation_fixed.json"
            csv_path = output_dir / "candidate_walk_forward_validation_fixed.csv"
            md_path = output_dir / "candidate_walk_forward_validation_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["generated_at"], 1000.0)
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("continued_validation", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Candidate Walk-Forward Validation", md_path.read_text(encoding="utf-8"))
