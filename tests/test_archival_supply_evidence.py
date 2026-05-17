import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_supply_evidence import write_archival_supply_evidence_report
from wallets.archival_supply_evidence import build_archival_supply_evidence_report


def requirement(**overrides):
    row = {
        "token_mint": "MintA",
        "status": "ready_for_archival_supply_fetch",
        "earliest_decision_slot": 100,
        "latest_decision_slot": 120,
        "required_evidence": "historical_mint_account_supply_at_or_before_decision_slot",
        "row_count": 2,
    }
    row.update(overrides)
    return row


def candidate(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "transaction_signature": "SigA",
        "decision_slot": 110,
        "timestamp": 1000,
    }
    row.update(overrides)
    return row


def plan(**overrides):
    row = {
        "mode": "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY",
        "token_requirements": [requirement()],
        "candidate_rows": [candidate(), candidate(wallet="WalletB", transaction_signature="SigB", decision_slot=120)],
    }
    row.update(overrides)
    return row


def snapshot(**overrides):
    row = {
        "token_mint": "MintA",
        "slot": 90,
        "raw_supply": "1000000000",
        "decimals": 6,
        "source": "historical_mint_account_snapshot",
        "source_file": "fixtures/mint_supply.jsonl",
    }
    row.update(overrides)
    return row


def rpc_snapshot(**overrides):
    row = {
        "token_mint": "MintA",
        "result": {
            "context": {"slot": 90},
            "value": {
                "data": {
                    "program": "spl-token",
                    "parsed": {
                        "type": "mint",
                        "info": {
                            "supply": "1000000000",
                            "decimals": 6,
                        },
                    },
                }
            },
        },
        "source": "historical_getAccountInfo_fixture",
    }
    row.update(overrides)
    return row


class ArchivalSupplyEvidenceTests(unittest.TestCase):
    def test_imports_historical_snapshot_for_each_safe_candidate_row(self):
        report = build_archival_supply_evidence_report(
            archival_supply_plan=plan(),
            supply_snapshots=[snapshot()],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["candidate_rows"], 2)
        self.assertEqual(report["summary"]["supply_recovered_records"], 2)
        self.assertEqual(report["summary"]["tokens_recovered"], 1)
        self.assertEqual(report["records"][0]["status"], "archival_supply_recovered")
        self.assertEqual(report["records"][0]["ui_supply"], 1000.0)
        self.assertEqual(report["records"][0]["raw_supply"], "1000000000")
        self.assertEqual(report["records"][0]["decimals"], 6)
        self.assertTrue(report["records"][0]["decision_time_safe"])

    def test_parses_rpc_get_account_info_snapshot_shape(self):
        report = build_archival_supply_evidence_report(
            archival_supply_plan=plan(),
            supply_snapshots=[rpc_snapshot()],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["supply_recovered_records"], 2)
        self.assertEqual(report["records"][0]["source"], "historical_getAccountInfo_fixture")

    def test_rejects_snapshot_after_decision_slot(self):
        report = build_archival_supply_evidence_report(
            archival_supply_plan=plan(candidate_rows=[candidate(decision_slot=110)]),
            supply_snapshots=[snapshot(slot=115)],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["supply_recovered_records"], 0)
        self.assertEqual(report["summary"]["blocked_snapshot_after_decision_slot_records"], 1)
        self.assertEqual(report["records"][0]["status"], "blocked_snapshot_after_decision_slot")
        self.assertIn("snapshot_slot_after_decision_slot", report["records"][0]["block_reasons"])
        self.assertIsNone(report["records"][0]["ui_supply"])

    def test_blocks_missing_snapshot_without_fabricating_supply(self):
        report = build_archival_supply_evidence_report(
            archival_supply_plan=plan(),
            supply_snapshots=[],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["supply_recovered_records"], 0)
        self.assertEqual(report["summary"]["blocked_missing_snapshot_records"], 2)
        self.assertIsNone(report["records"][0]["ui_supply"])
        self.assertEqual(report["records"][0]["status"], "blocked_missing_archival_snapshot")

    def test_writer_persists_report_and_records(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "archival_supply_recovery_plan.json"
            snapshots_path = root / "mint_supply_snapshots.jsonl"
            report_path = root / "archival_supply_evidence_report.json"
            records_path = root / "archival_supply_evidence_records.jsonl"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            snapshots_path.write_text(json.dumps(snapshot()) + "\n", encoding="utf-8")

            report = write_archival_supply_evidence_report(
                plan_path=plan_path,
                snapshots_path=snapshots_path,
                report_path=report_path,
                output_records_path=records_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertEqual(report["summary"]["supply_recovered_records"], 2)
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
