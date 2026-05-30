import unittest
from pathlib import Path

from utils.run_wallet_candidate_collection_batch import (
    BATCH_STEPS,
    build_batch_report,
    disallowed_command_present,
)


class WalletCandidateCollectionBatchTests(unittest.TestCase):
    def test_default_batch_steps_do_not_include_apply_or_trading_commands(self):
        self.assertFalse(disallowed_command_present(BATCH_STEPS))
        commands = [" ".join(step["command"]) for step in BATCH_STEPS]
        self.assertTrue(any("enrich_wallet_history_evidence.py" in command for command in commands))
        self.assertTrue(any("build_wallet_candidate_collection_plan.py" in command for command in commands))
        self.assertFalse(any("apply_wallet_review.py" in command for command in commands))

    def test_build_batch_report_runs_steps_and_preserves_review_locks(self):
        calls = []

        def fake_runner(command, *, cwd, timeout):
            calls.append((command, cwd, timeout))
            return {
                "status": "passed",
                "exit_code": 0,
                "stdout_tail": "ok",
                "stderr_tail": "",
            }

        report = build_batch_report(
            root=Path("/tmp/memetrader"),
            collection_plan={
                "summary": {
                    "total_targets": 49,
                    "collect_outcomes_and_market_context": 36,
                    "collect_outcome_labels": 9,
                    "manual_risk_review": 4,
                }
            },
            command_runner=fake_runner,
            generated_at=123.0,
            steps=[
                {"name": "step_one", "command": ["python", "one.py"]},
                {"name": "step_two", "command": ["python", "two.py"]},
            ],
        )

        self.assertEqual(report["mode"], "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["planned_targets"], 49)
        self.assertEqual(report["summary"]["steps_passed"], 2)
        self.assertEqual(report["summary"]["steps_failed"], 0)
        self.assertEqual([call[0] for call in calls], [["python", "one.py"], ["python", "two.py"]])
        self.assertEqual(report["steps"][0]["status"], "passed")

    def test_build_batch_report_blocks_disallowed_commands(self):
        with self.assertRaises(ValueError):
            build_batch_report(
                root=Path("/tmp/memetrader"),
                collection_plan={"summary": {}},
                command_runner=lambda *_args, **_kwargs: {"status": "passed", "exit_code": 0},
                steps=[{"name": "bad", "command": ["python", "utils/apply_wallet_review.py"]}],
            )


if __name__ == "__main__":
    unittest.main()
