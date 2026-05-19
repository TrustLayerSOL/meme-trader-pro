import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_supply_stability_evidence import write_supply_stability_evidence_report
from wallets.supply_stability_evidence import build_supply_stability_evidence_report


def requirement(**overrides):
    row = {
        "token_mint": "MintA",
        "status": "ready_for_archival_supply_fetch",
        "earliest_decision_slot": 100,
        "latest_decision_slot": 120,
        "row_count": 2,
    }
    row.update(overrides)
    return row


def plan(**overrides):
    row = {
        "mode": "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY",
        "token_requirements": [requirement()],
        "candidate_rows": [],
    }
    row.update(overrides)
    return row


def current_snapshot(**overrides):
    row = {
        "token_mint": "MintA",
        "slot": 200,
        "raw_supply": "1000000000",
        "decimals": 6,
        "source": "current_getTokenSupply",
    }
    row.update(overrides)
    return row


def tx(slot, signature, instructions):
    return {
        "signature": signature,
        "transaction": {
            "slot": slot,
            "transaction": {"message": {"instructions": instructions}},
            "meta": {"innerInstructions": []},
        },
    }


def mint_to(amount, decimals=6, mint="MintA"):
    return {
        "program": "spl-token",
        "parsed": {
            "type": "mintToChecked",
            "info": {"mint": mint, "tokenAmount": {"amount": str(amount), "decimals": decimals}},
        },
    }


class SupplyStabilityEvidenceTests(unittest.TestCase):
    def test_proves_current_supply_as_decision_time_supply_when_no_post_decision_supply_events_exist(self):
        report = build_supply_stability_evidence_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            raw_transactions=[],
            history_completeness={"MintA": {"complete_through_slot": 120, "source": "mint_history_collection"}},
            generated_at=123.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["snapshots_reconstructed"], 1)
        self.assertEqual(report["requirements"][0]["status"], "stable_current_supply_proven")
        self.assertEqual(report["snapshots"][0]["token_mint"], "MintA")
        self.assertEqual(report["snapshots"][0]["slot"], 100)
        self.assertEqual(report["snapshots"][0]["source"], "current_supply_stability_proof")
        self.assertEqual(report["snapshots"][0]["raw_supply"], "1000000000")
        self.assertTrue(report["snapshots"][0]["decision_time_safe"])

    def test_blocks_current_supply_when_mint_history_does_not_cover_decision_slot(self):
        report = build_supply_stability_evidence_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            raw_transactions=[],
            history_completeness={"MintA": {"complete_through_slot": 90}},
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_reconstructed"], 0)
        self.assertEqual(report["requirements"][0]["status"], "blocked_incomplete_post_decision_history")
        self.assertIn("mint_history_not_complete_through_decision_slot", report["requirements"][0]["block_reasons"])

    def test_blocks_current_supply_when_supply_changed_after_decision(self):
        report = build_supply_stability_evidence_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            raw_transactions=[tx(110, "SigMint", [mint_to(10_000_000)])],
            history_completeness={"MintA": {"complete_through_slot": 120}},
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_reconstructed"], 0)
        self.assertEqual(report["requirements"][0]["status"], "blocked_supply_changed_after_decision")
        self.assertEqual(report["requirements"][0]["post_decision_supply_event_count"], 1)

    def test_writer_persists_report_and_compatible_snapshot_jsonl(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            current_path = root / "current.jsonl"
            raw_path = root / "raw.jsonl"
            completeness_path = root / "completeness.json"
            report_path = root / "report.json"
            snapshots_path = root / "snapshots.jsonl"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            current_path.write_text(json.dumps(current_snapshot()) + "\n", encoding="utf-8")
            raw_path.write_text("", encoding="utf-8")
            completeness_path.write_text(json.dumps({"MintA": {"complete_through_slot": 120}}), encoding="utf-8")

            report = write_supply_stability_evidence_report(
                plan_path=plan_path,
                current_supply_snapshots_path=current_path,
                raw_transaction_paths=[raw_path],
                completeness_path=completeness_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(snapshots_path.exists())
            self.assertEqual(report["summary"]["snapshots_reconstructed"], 1)
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["source"], "current_supply_stability_proof")


if __name__ == "__main__":
    unittest.main()
