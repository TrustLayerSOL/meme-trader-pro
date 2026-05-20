import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_post_decision_supply_coverage import write_post_decision_supply_coverage_report
from wallets.post_decision_supply_coverage import build_post_decision_supply_coverage_report


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
    }
    row.update(overrides)
    return row


def current_snapshot(**overrides):
    row = {
        "token_mint": "MintA",
        "slot": 200,
        "raw_supply": "1000000000",
        "decimals": 6,
        "collected_at": 123.0,
        "source": "current_getTokenSupply",
    }
    row.update(overrides)
    return row


def checkpoint(**overrides):
    row = {
        "MintA": {
            "token_mint": "MintA",
            "checkpoint_collected_at": 124.0,
            "pagination_complete": False,
            "signatures": [
                {"signature": "SigNew", "slot": 180},
                {"signature": "SigMid", "slot": 140},
                {"signature": "SigDecision", "slot": 100},
            ],
        }
    }
    row.update(overrides)
    return row


def tx(slot, signature, instructions=None):
    return {
        "token_mint": "MintA",
        "signature": signature,
        "slot": slot,
        "transaction": {
            "slot": slot,
            "transaction": {"message": {"instructions": instructions or []}},
            "meta": {"innerInstructions": []},
        },
    }


def mint_to():
    return {
        "program": "spl-token",
        "parsed": {
            "type": "mintToChecked",
            "info": {"mint": "MintA", "tokenAmount": {"amount": "100", "decimals": 6}},
        },
    }


class PostDecisionSupplyCoverageTests(unittest.TestCase):
    def test_marks_post_decision_supply_stable_when_checkpoint_and_raw_transactions_cover_window(self):
        report = build_post_decision_supply_coverage_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[tx(180, "SigNew"), tx(140, "SigMid")],
            generated_at=125.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["stable_tokens"], 1)
        self.assertEqual(report["rows"][0]["status"], "post_decision_supply_stable")
        self.assertEqual(report["history_completeness_updates"]["MintA"]["post_decision_complete_through_slot"], 200)
        self.assertEqual(report["history_completeness_updates"]["MintA"]["post_decision_raw_transactions_checked"], 2)

    def test_blocks_when_post_decision_transaction_bodies_are_missing(self):
        report = build_post_decision_supply_coverage_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[tx(180, "SigNew")],
            generated_at=125.0,
        )

        self.assertEqual(report["summary"]["stable_tokens"], 0)
        self.assertEqual(report["rows"][0]["status"], "needs_post_decision_transaction_bodies")
        self.assertEqual(report["rows"][0]["missing_post_decision_transaction_count"], 1)

    def test_blocks_when_supply_changes_after_decision(self):
        report = build_post_decision_supply_coverage_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[tx(180, "SigNew", [mint_to()]), tx(140, "SigMid")],
            generated_at=125.0,
        )

        self.assertEqual(report["summary"]["stable_tokens"], 0)
        self.assertEqual(report["rows"][0]["status"], "blocked_supply_changed_after_decision")
        self.assertEqual(report["rows"][0]["post_decision_supply_event_count"], 1)

    def test_writer_persists_report_and_completeness_updates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            current_path = root / "current.jsonl"
            checkpoint_path = root / "checkpoint.json"
            raw_path = root / "raw.jsonl"
            report_path = root / "report.json"
            updates_path = root / "updates.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            current_path.write_text(json.dumps(current_snapshot()) + "\n", encoding="utf-8")
            checkpoint_path.write_text(json.dumps(checkpoint()), encoding="utf-8")
            raw_path.write_text(json.dumps(tx(180, "SigNew")) + "\n" + json.dumps(tx(140, "SigMid")) + "\n", encoding="utf-8")

            report = write_post_decision_supply_coverage_report(
                plan_path=plan_path,
                current_supply_snapshots_path=current_path,
                signature_checkpoint_path=checkpoint_path,
                raw_transaction_paths=[raw_path],
                report_path=report_path,
                completeness_updates_path=updates_path,
                generated_at=125.0,
            )

            self.assertEqual(report["summary"]["stable_tokens"], 1)
            self.assertTrue(report_path.exists())
            self.assertTrue(updates_path.exists())
            updates = json.loads(updates_path.read_text(encoding="utf-8"))
            self.assertIn("MintA", updates)

    def test_writer_merges_post_decision_checkpoint_over_base_checkpoint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            current_path = root / "current.jsonl"
            base_checkpoint_path = root / "base_checkpoint.json"
            post_checkpoint_path = root / "post_checkpoint.json"
            raw_path = root / "raw.jsonl"
            report_path = root / "report.json"
            updates_path = root / "updates.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            current_path.write_text(json.dumps(current_snapshot()) + "\n", encoding="utf-8")
            base_checkpoint_path.write_text(json.dumps({"MintA": {"signatures": []}}), encoding="utf-8")
            post_checkpoint_path.write_text(json.dumps(checkpoint()), encoding="utf-8")
            raw_path.write_text(json.dumps(tx(180, "SigNew")) + "\n" + json.dumps(tx(140, "SigMid")) + "\n", encoding="utf-8")

            report = write_post_decision_supply_coverage_report(
                plan_path=plan_path,
                current_supply_snapshots_path=current_path,
                signature_checkpoint_path=base_checkpoint_path,
                post_decision_signature_checkpoint_path=post_checkpoint_path,
                raw_transaction_paths=[raw_path],
                report_path=report_path,
                completeness_updates_path=updates_path,
                generated_at=125.0,
            )

            self.assertEqual(report["summary"]["stable_tokens"], 1)
            self.assertEqual(report["rows"][0]["checkpoint_collected_at"], 124.0)


if __name__ == "__main__":
    unittest.main()
