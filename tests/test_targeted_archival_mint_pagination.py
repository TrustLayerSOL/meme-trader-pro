import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.run_targeted_archival_mint_pagination import select_target_requirements
from utils.run_targeted_archival_mint_pagination import write_targeted_archival_mint_pagination_report


def requirement(mint):
    return {
        "token_mint": mint,
        "status": "ready_for_archival_supply_fetch",
        "earliest_decision_slot": 100,
    }


def pagination_row(mint, action="CONTINUE_PAGINATION_TOWARD_DECISION_SLOT", estimated_pages=3, priority=85):
    return {
        "token_mint": mint,
        "recommended_action": action,
        "estimated_pages_to_decision_slot": estimated_pages,
        "priority": priority,
    }


class TargetedArchivalMintPaginationTests(unittest.TestCase):
    def test_selects_only_continue_pagination_targets_within_page_limit(self):
        supply_plan = {
            "token_requirements": [
                requirement("MintA"),
                requirement("MintB"),
                requirement("MintC"),
                requirement("MintD"),
            ]
        }
        pagination_plan = {
            "rows": [
                pagination_row("MintA", estimated_pages=2),
                pagination_row("MintB", estimated_pages=20),
                pagination_row("MintC", action="CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER", estimated_pages=1),
                pagination_row("MintD", estimated_pages=4),
            ]
        }

        selected = select_target_requirements(
            supply_plan=supply_plan,
            pagination_plan=pagination_plan,
            max_estimated_pages=5,
            max_targets=None,
        )

        self.assertEqual([row["token_mint"] for row in selected], ["MintA", "MintD"])

    def test_selects_target_bucket_with_min_and_max_page_limits(self):
        supply_plan = {
            "token_requirements": [
                requirement("MintA"),
                requirement("MintB"),
                requirement("MintC"),
                requirement("MintD"),
            ]
        }
        pagination_plan = {
            "rows": [
                pagination_row("MintA", estimated_pages=2),
                pagination_row("MintB", estimated_pages=8),
                pagination_row("MintC", estimated_pages=12),
                pagination_row("MintD", estimated_pages=25),
            ]
        }

        selected = select_target_requirements(
            supply_plan=supply_plan,
            pagination_plan=pagination_plan,
            min_estimated_pages=8,
            max_estimated_pages=20,
            max_targets=None,
        )

        self.assertEqual([row["token_mint"] for row in selected], ["MintB", "MintC"])

    def test_writer_persists_filtered_plan_and_collection_summary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            supply_path = root / "supply.json"
            pagination_path = root / "pagination.json"
            filtered_path = root / "filtered.json"
            report_path = root / "targeted.json"
            collection_report_path = root / "collection.json"
            raw_path = root / "raw.jsonl"
            completeness_path = root / "complete.json"
            checkpoint_path = root / "checkpoint.json"

            supply_path.write_text(json.dumps({
                "token_requirements": [requirement("MintA"), requirement("MintB")]
            }), encoding="utf-8")
            pagination_path.write_text(json.dumps({
                "rows": [
                    pagination_row("MintA", estimated_pages=2),
                    pagination_row("MintB", action="CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER", estimated_pages=1),
                ]
            }), encoding="utf-8")

            report = write_targeted_archival_mint_pagination_report(
                supply_plan_path=supply_path,
                pagination_plan_path=pagination_path,
                filtered_plan_path=filtered_path,
                report_path=report_path,
                collection_report_path=collection_report_path,
                raw_transactions_path=raw_path,
                completeness_path=completeness_path,
                signature_checkpoint_path=checkpoint_path,
                execute=False,
                min_estimated_pages=1,
                max_estimated_pages=5,
                generated_at=123.0,
            )

            filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
            persisted = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(report["summary"]["selected_targets"], 1)
            self.assertEqual(report["summary"]["collection_mint_history_targets"], 1)
            self.assertEqual(filtered["token_requirements"][0]["token_mint"], "MintA")
            self.assertEqual(persisted["summary"]["selected_targets"], 1)
            self.assertTrue(report["live_execution_locked"])
            self.assertFalse(report["wallet_list_mutated"])


if __name__ == "__main__":
    unittest.main()
