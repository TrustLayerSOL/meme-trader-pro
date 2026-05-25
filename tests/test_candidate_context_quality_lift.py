import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_context_quality_lift import write_candidate_context_quality_lift
from wallets.candidate_context_quality_lift import build_candidate_context_quality_lift


WALLET_A = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"
WALLET_B = "D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3"
WALLET_C = "ReadyWallet"


def record(wallet, event, *, blocked=False, reason=None, context=True, outcome="runner", token=None, has_quote=True):
    payload = {
        "event_id": f"{wallet}-{event}",
        "wallet": wallet,
        "token_mint": token or f"Mint{event}",
        "token_symbol": f"T{event}",
        "signal_time": float(len(event) + 100),
        "observed_action": "buy",
        "status": "resolved",
        "outcome_window_labels": {"15m": {"outcome_type": outcome}},
        "decision_context": {
            "estimated_entry_context": {
                "price": 0.01,
                "liquidity": 25000,
                "market_cap": 100000,
                "snapshot_time": 105.0,
                "execution_price_quote": 0.01,
            }
        },
    }
    if blocked:
        payload["status"] = f"blocked_{reason or 'missing_forward_entry_context'}"
        payload["block_reasons"] = [reason or "missing_forward_entry_context"]
    if not context:
        payload["decision_context"] = {
            "estimated_entry_context": {"execution_price_quote": 0.01} if has_quote else {}
        }
    return payload


def readiness_gate():
    return {
        "wallets": [
            {
                "wallet_address": WALLET_A,
                "paper_readiness_status": "not_ready",
                "failed_gates": ["max_excluded_rate_exceeded", "min_context_completion_rate_not_met"],
            },
            {
                "wallet_address": WALLET_B,
                "paper_readiness_status": "not_ready",
                "failed_gates": ["min_total_clean_rows_not_met", "max_excluded_rate_exceeded"],
            },
            {
                "wallet_address": WALLET_C,
                "paper_readiness_status": "eligible_for_manual_paper_simulation_review",
                "failed_gates": [],
            },
        ]
    }


class CandidateContextQualityLiftTests(unittest.TestCase):
    def test_builds_targeted_queue_for_not_ready_survivors_only(self):
        records = [
            record(WALLET_A, "clean"),
            record(WALLET_A, "snapshot-1", blocked=True, reason="missing_later_market_snapshot", context=False, has_quote=True),
            record(WALLET_A, "snapshot-2", blocked=True, reason="missing_later_market_snapshot", context=False, has_quote=True),
            record(WALLET_B, "quote-1", blocked=True, reason="missing_valid_execution_price_quote", context=False, has_quote=False),
            record(WALLET_B, "quote-2", blocked=True, reason="missing_valid_execution_price_quote", context=False, has_quote=False),
            record(WALLET_C, "ready-blocked", blocked=True, reason="missing_later_market_snapshot", context=False),
        ]

        report = build_candidate_context_quality_lift(
            readiness_gate=readiness_gate(),
            records=records,
            repaired_records=[],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["wallets_in_queue"], 2)
        self.assertEqual([row["wallet_address"] for row in report["wallets"]], [WALLET_A, WALLET_B])
        self.assertEqual(report["wallets"][0]["recommended_context_action"], "repair_market_snapshot")
        self.assertEqual(report["wallets"][1]["recommended_context_action"], "repair_entry_timestamp")
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_repaired_records_remove_rows_from_blocker_queue(self):
        blocked = record(WALLET_A, "same", blocked=True, reason="missing_later_market_snapshot", context=False)
        repaired = record(WALLET_A, "same", context=True)
        report = build_candidate_context_quality_lift(
            readiness_gate=readiness_gate(),
            records=[blocked],
            repaired_records=[repaired],
            generated_at=1000.0,
        )

        wallet = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_A)
        self.assertEqual(wallet["open_blocker_rows"], 0)
        self.assertEqual(wallet["recommended_context_action"], "collect_more_clean_candidate_rows")

    def test_missing_forward_entry_price_routes_to_entry_timestamp_repair(self):
        records = [
            record(WALLET_A, "price-1", blocked=True, reason="missing_forward_entry_price", context=False, has_quote=False),
            record(WALLET_A, "price-2", blocked=True, reason="missing_forward_entry_price", context=False, has_quote=False),
            record(WALLET_A, "outcome", blocked=False, context=True, outcome="unknown"),
        ]

        report = build_candidate_context_quality_lift(
            readiness_gate=readiness_gate(),
            records=records,
            repaired_records=[],
            generated_at=1000.0,
        )

        wallet = next(row for row in report["wallets"] if row["wallet_address"] == WALLET_A)
        self.assertEqual(wallet["recommended_context_action"], "repair_entry_timestamp")
        self.assertEqual(wallet["missing_valid_execution_price_quote_rows"], 2)

    def test_writer_exports_deterministic_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate_path = root / "gate.json"
            records_path = root / "records.jsonl"
            output_dir = root / "out"
            rows = [
                record(WALLET_A, "snapshot", blocked=True, reason="missing_later_market_snapshot", context=False),
                record(WALLET_B, "quote", blocked=True, reason="missing_valid_execution_price_quote", context=False, has_quote=False),
            ]
            gate_path.write_text(json.dumps(readiness_gate(), sort_keys=True), encoding="utf-8")
            records_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

            report = write_candidate_context_quality_lift(
                readiness_gate_path=gate_path,
                records_path=records_path,
                repaired_records_path=root / "missing_repaired.jsonl",
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            json_path = output_dir / "candidate_context_quality_lift_fixed.json"
            csv_path = output_dir / "candidate_context_quality_lift_fixed.csv"
            md_path = output_dir / "candidate_context_quality_lift_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("repair_market_snapshot", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Candidate Context Quality Lift", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
