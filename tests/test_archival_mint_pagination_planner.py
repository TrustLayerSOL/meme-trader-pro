import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_mint_pagination_plan import write_archival_mint_pagination_plan_report
from wallets.archival_mint_pagination_planner import build_archival_mint_pagination_plan_report


def row(**overrides):
    item = {
        "token_mint": "MintA",
        "decision_slot": 100,
        "signature_count": 0,
        "oldest_signature_slot": None,
        "newest_signature_slot": None,
        "pagination_complete": False,
        "reached_decision_slot": False,
        "status": "no_signature_checkpoint",
    }
    item.update(overrides)
    return item


def progress(rows):
    return {
        "mode": "ARCHIVAL_MINT_HISTORY_PROGRESS_REVIEW_ONLY",
        "rows": rows,
    }


class ArchivalMintPaginationPlannerTests(unittest.TestCase):
    def test_recommends_initial_collection_for_missing_checkpoint(self):
        report = build_archival_mint_pagination_plan_report(
            progress_report=progress([row()]),
            page_size=100,
            pages_per_batch=10,
            provider_threshold_signatures=2000,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["initial_pagination_tokens"], 1)
        self.assertEqual(report["rows"][0]["recommended_action"], "RUN_INITIAL_BOUNDED_PAGINATION")

    def test_recommends_continuing_when_decision_slot_not_reached(self):
        report = build_archival_mint_pagination_plan_report(
            progress_report=progress([row(
                token_mint="MintB",
                decision_slot=1000,
                signature_count=1000,
                newest_signature_slot=3000,
                oldest_signature_slot=2000,
                status="checkpoint_before_decision_not_reached",
            )]),
            page_size=100,
            pages_per_batch=10,
            provider_threshold_signatures=2000,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["continue_pagination_tokens"], 1)
        self.assertEqual(report["rows"][0]["recommended_action"], "CONTINUE_PAGINATION_TOWARD_DECISION_SLOT")
        self.assertGreater(report["rows"][0]["estimated_pages_to_decision_slot"], 0)

    def test_recommends_provider_when_decision_reached_but_history_not_complete_at_threshold(self):
        report = build_archival_mint_pagination_plan_report(
            progress_report=progress([row(
                token_mint="MintC",
                decision_slot=1000,
                signature_count=2000,
                newest_signature_slot=3000,
                oldest_signature_slot=900,
                reached_decision_slot=True,
                status="checkpoint_reached_decision_slot_but_not_history_start",
            )]),
            page_size=100,
            pages_per_batch=10,
            provider_threshold_signatures=2000,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["provider_recommended_tokens"], 1)
        self.assertEqual(report["rows"][0]["recommended_action"], "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER")
        self.assertEqual(report["rows"][0]["reason"], "decision_slot_reached_but_account_history_still_incomplete_at_threshold")

    def test_marks_complete_history_ready_for_reconstruction(self):
        report = build_archival_mint_pagination_plan_report(
            progress_report=progress([row(
                token_mint="MintD",
                signature_count=25,
                oldest_signature_slot=1,
                newest_signature_slot=200,
                pagination_complete=True,
                reached_decision_slot=True,
                status="signature_history_complete",
            )]),
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["complete_history_tokens"], 1)
        self.assertEqual(report["rows"][0]["recommended_action"], "RUN_SUPPLY_RECONSTRUCTION")

    def test_writer_persists_plan_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress_path = root / "progress.json"
            report_path = root / "plan.json"
            progress_path.write_text(json.dumps(progress([row()])), encoding="utf-8")

            report = write_archival_mint_pagination_plan_report(
                progress_path=progress_path,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["initial_pagination_tokens"], 1)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"]["initial_pagination_tokens"], 1)


if __name__ == "__main__":
    unittest.main()
