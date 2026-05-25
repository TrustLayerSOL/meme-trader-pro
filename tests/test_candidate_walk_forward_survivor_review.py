import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_walk_forward_survivor_review import write_candidate_walk_forward_survivor_review
from wallets.candidate_walk_forward_survivor_review import build_candidate_walk_forward_survivor_review
from wallets.candidate_walk_forward_validation import build_candidate_walk_forward_validation_report


WALLET_A = "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY"
WALLET_B = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"
WALLET_C = "D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3"


def row(wallet, event, ts, outcome="flat", *, blocked=False, context=True, token=None):
    payload = {
        "event_id": f"{wallet}-{event}",
        "wallet": wallet,
        "token_mint": token or f"Mint{event}",
        "token_symbol": f"T{event}",
        "observed_action": "buy",
        "signal_time": float(ts),
        "transaction_signature": f"sig-{event}",
        "outcome_window_labels": {"15m": {"outcome_type": outcome, "pnl_pct": 25.0 if outcome == "runner" else 0.0}},
        "status": "resolved",
        "decision_context": {
            "estimated_entry_context": {
                "price": 0.01,
                "liquidity": 25000 + int(ts),
                "market_cap": 100000 + int(ts),
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


def validation_report(records, repaired_records=None):
    return build_candidate_walk_forward_validation_report(
        records=records,
        repaired_records=repaired_records or [],
        candidate_wallets=[WALLET_A, WALLET_B, WALLET_C],
        generated_at=1000.0,
        train_fraction=0.5,
        min_train_clean_rows=1,
        min_validation_clean_rows=1,
        degradation_tolerance=0.5,
    )


class CandidateWalkForwardSurvivorReviewTests(unittest.TestCase):
    def test_defaults_to_continued_validation_wallets_only(self):
        records = [
            row(WALLET_A, "a-train", 10, "runner"),
            row(WALLET_A, "a-validation", 20, "flat"),
            row(WALLET_B, "b-train", 10, "runner"),
            row(WALLET_B, "b-validation", 20, "runner"),
            row(WALLET_C, "c-train", 10, "runner"),
        ]
        base = validation_report(records)
        review = build_candidate_walk_forward_survivor_review(
            walk_forward_report=base,
            records=records,
            repaired_records=[],
            generated_at=2000.0,
        )

        self.assertEqual(review["summary"]["survivor_wallets"], 1)
        self.assertEqual([wallet["wallet_address"] for wallet in review["wallets"]], [WALLET_B])
        self.assertEqual(review["wallets"][0]["walk_forward_conclusion"], "continued_validation")
        self.assertEqual(review["wallets"][0]["paper_simulation_readiness"], "not_ready")
        self.assertFalse(review["wallets"][0]["promotion_allowed"])
        self.assertFalse(review["wallet_trust_mutation_allowed"])

    def test_reports_train_validation_rows_and_excludes_blocked_rows_from_proof(self):
        records = [
            row(WALLET_B, "train-runner", 10, "runner", token="A"),
            row(WALLET_B, "validation-runner", 20, "runner", token="B"),
            row(WALLET_B, "blocked", 30, "runner", blocked=True, token="C"),
            row(WALLET_B, "missing-context", 40, "runner", context=False, token="D"),
        ]
        base = validation_report(records)
        review = build_candidate_walk_forward_survivor_review(
            walk_forward_report=base,
            records=records,
            repaired_records=[],
            generated_at=2000.0,
        )
        wallet = review["wallets"][0]

        self.assertEqual(wallet["proof_metric_records"], 2)
        self.assertEqual(wallet["excluded_records"], 2)
        self.assertEqual(wallet["train"]["clean_records"], 1)
        self.assertEqual(wallet["validation"]["clean_records"], 1)
        self.assertEqual(len(wallet["train_event_evidence"]), 1)
        self.assertEqual(len(wallet["validation_event_evidence"]), 1)
        self.assertEqual(wallet["excluded_event_summary"]["blocked_records"], 1)
        self.assertIn("blocked_or_incomplete_rows_excluded_from_proof", wallet["reasons_not_to_trust"])

    def test_uses_repaired_rows_and_marks_repaired_event_quality(self):
        original = row(WALLET_B, "same", 10, "runner", blocked=True, token="A")
        repaired = row(WALLET_B, "same", 10, "runner", token="A")
        records = [original, row(WALLET_B, "validation", 20, "runner", token="B")]
        base = validation_report(records, repaired_records=[repaired])

        review = build_candidate_walk_forward_survivor_review(
            walk_forward_report=base,
            records=records,
            repaired_records=[repaired],
            generated_at=2000.0,
        )

        wallet = review["wallets"][0]
        evidence = wallet["train_event_evidence"][0]
        self.assertEqual(wallet["proof_metric_records"], 2)
        self.assertTrue(evidence["repaired_context"])
        self.assertEqual(evidence["evidence_quality"], "repaired_context")

    def test_writer_exports_deterministic_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            walk_forward_path = root / "walk_forward.json"
            output_dir = root / "out"
            records = [
                row(WALLET_B, "train", 10, "runner", token="A"),
                row(WALLET_B, "validation", 20, "runner", token="B"),
                row(WALLET_A, "degraded-train", 10, "runner", token="C"),
                row(WALLET_A, "degraded-validation", 20, "flat", token="D"),
            ]
            base = validation_report(records)
            records_path.write_text("\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n", encoding="utf-8")
            walk_forward_path.write_text(json.dumps(base, sort_keys=True), encoding="utf-8")

            report = write_candidate_walk_forward_survivor_review(
                walk_forward_report_path=walk_forward_path,
                records_path=records_path,
                repaired_records_path=root / "missing_repaired.jsonl",
                output_dir=output_dir,
                run_id="fixed",
                generated_at=2000.0,
            )

            json_path = output_dir / "candidate_walk_forward_survivor_review_fixed.json"
            csv_path = output_dir / "candidate_walk_forward_survivor_review_fixed.csv"
            events_csv_path = output_dir / "candidate_walk_forward_survivor_events_fixed.csv"
            md_path = output_dir / "candidate_walk_forward_survivor_review_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(events_csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["generated_at"], 2000.0)
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("continued_validation", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Candidate Walk-Forward Survivor Review", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
