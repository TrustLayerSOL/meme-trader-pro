import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_account_state_provider_evaluation import write_archival_account_state_provider_evaluation_report
from wallets.archival_account_state_provider_evaluation import build_archival_account_state_provider_evaluation_report


def pagination_plan(**summary_overrides):
    summary = {
        "tokens_planned": 34,
        "initial_pagination_tokens": 31,
        "continue_pagination_tokens": 2,
        "provider_recommended_tokens": 1,
        "complete_history_tokens": 0,
    }
    summary.update(summary_overrides)
    return {"mode": "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY", "summary": summary}


class ArchivalAccountStateProviderEvaluationTests(unittest.TestCase):
    def test_evaluates_provider_candidates_without_mutating_trust(self):
        report = build_archival_account_state_provider_evaluation_report(
            pagination_plan=pagination_plan(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_ACCOUNT_STATE_PROVIDER_EVALUATION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["providers_evaluated"], 3)
        self.assertEqual(report["summary"]["candidate_providers"], 1)
        self.assertTrue(report["summary"]["provider_probe_required"])

    def test_rejects_current_only_rpc_for_historical_supply(self):
        report = build_archival_account_state_provider_evaluation_report(
            pagination_plan=pagination_plan(),
            generated_at=123.0,
        )
        helius = next(row for row in report["providers"] if row["provider_id"] == "helius_getaccountinfo_current_rpc")

        self.assertEqual(helius["status"], "not_sufficient_for_historical_supply_snapshot")
        self.assertIn("does_not_prove_point_in_time_account_state", helius["blockers"])
        self.assertFalse(helius["can_unlock_archival_supply"])

    def test_marks_quicknode_as_manual_probe_candidate_not_validated(self):
        report = build_archival_account_state_provider_evaluation_report(
            pagination_plan=pagination_plan(provider_recommended_tokens=1),
            generated_at=123.0,
        )
        quicknode = next(row for row in report["providers"] if row["provider_id"] == "quicknode_solana_mainnet_archive")

        self.assertEqual(quicknode["status"], "candidate_needs_manual_probe")
        self.assertTrue(quicknode["manual_probe_required"])
        self.assertFalse(quicknode["validated_for_supply_import"])
        self.assertEqual(quicknode["recommended_next_action"], "RUN_ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE")

    def test_writer_persists_evaluation_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pagination_path = root / "pagination.json"
            report_path = root / "provider_eval.json"
            pagination_path.write_text(json.dumps(pagination_plan()), encoding="utf-8")

            report = write_archival_account_state_provider_evaluation_report(
                pagination_plan_path=pagination_path,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["providers_evaluated"], 3)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"]["candidate_providers"], 1)


if __name__ == "__main__":
    unittest.main()
