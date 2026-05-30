import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_mint_history_progress import write_archival_mint_history_progress_report
from wallets.archival_mint_history_progress import build_archival_mint_history_progress_report


def requirement(**overrides):
    row = {
        "token_mint": "MintA",
        "status": "ready_for_archival_supply_fetch",
        "earliest_decision_slot": 100,
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


class ArchivalMintHistoryProgressTests(unittest.TestCase):
    def test_reports_missing_checkpoint_without_mutating_trust(self):
        report = build_archival_mint_history_progress_report(
            archival_supply_plan=plan(),
            signature_checkpoint={},
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_HISTORY_PROGRESS_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["requirements_scanned"], 1)
        self.assertEqual(report["summary"]["tokens_missing_checkpoint"], 1)
        self.assertEqual(report["rows"][0]["status"], "no_signature_checkpoint")

    def test_marks_checkpoint_reached_decision_but_not_complete(self):
        report = build_archival_mint_history_progress_report(
            archival_supply_plan=plan(),
            signature_checkpoint={
                "MintA": {
                    "signatures_fetched_total": 2000,
                    "oldest_signature_slot": 90,
                    "newest_signature_slot": 200,
                    "pagination_complete": False,
                }
            },
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["checkpointed_tokens"], 1)
        self.assertEqual(report["summary"]["tokens_reached_decision_slot"], 1)
        self.assertEqual(report["summary"]["tokens_with_complete_history"], 0)
        self.assertEqual(report["rows"][0]["status"], "checkpoint_reached_decision_slot_but_not_history_start")

    def test_marks_complete_history_as_reconstruction_ready(self):
        report = build_archival_mint_history_progress_report(
            archival_supply_plan=plan(),
            signature_checkpoint={
                "MintA": {
                    "signatures_fetched_total": 12,
                    "oldest_signature_slot": 1,
                    "newest_signature_slot": 200,
                    "pagination_complete": True,
                }
            },
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["tokens_with_complete_history"], 1)
        self.assertEqual(report["rows"][0]["status"], "signature_history_complete")
        self.assertEqual(report["rows"][0]["next_action"], "RUN_SUPPLY_RECONSTRUCTION")

    def test_writer_persists_progress_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            checkpoint_path = root / "checkpoint.json"
            report_path = root / "report.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            checkpoint_path.write_text(json.dumps({"MintA": {"signatures_fetched_total": 1}}), encoding="utf-8")

            report = write_archival_mint_history_progress_report(
                plan_path=plan_path,
                signature_checkpoint_path=checkpoint_path,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["checkpointed_tokens"], 1)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"]["checkpointed_tokens"], 1)


if __name__ == "__main__":
    unittest.main()
