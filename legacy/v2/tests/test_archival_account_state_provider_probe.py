import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_account_state_provider_probe import write_archival_account_state_provider_probe_report
from wallets.archival_account_state_provider_probe import build_archival_account_state_provider_probe_report


def pagination_plan():
    return {
        "mode": "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY",
        "rows": [
            {
                "token_mint": "MintProbe111",
                "decision_slot": 1000,
                "signature_count": 2000,
                "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER",
                "reason": "decision_slot_reached_but_account_history_still_incomplete_at_threshold",
            },
            {
                "token_mint": "MintOther111",
                "decision_slot": 1200,
                "signature_count": 0,
                "recommended_action": "RUN_INITIAL_BOUNDED_PAGINATION",
            },
        ],
    }


def provider_evaluation():
    return {
        "mode": "ARCHIVAL_ACCOUNT_STATE_PROVIDER_EVALUATION_REVIEW_ONLY",
        "providers": [
            {
                "provider_id": "quicknode_solana_mainnet_archive",
                "status": "candidate_needs_manual_probe",
                "manual_probe_required": True,
            }
        ],
    }


def mint_response(*, context_slot=999, supply="123456", account_value=True):
    value = None if not account_value else {
        "data": {
            "program": "spl-token",
            "parsed": {
                "type": "mint",
                "info": {
                    "decimals": 6,
                    "supply": supply,
                },
            },
        }
    }
    return {
        "jsonrpc": "2.0",
        "result": {
            "context": {"slot": context_slot},
            "value": value,
        },
        "id": 1,
    }


class ArchivalAccountStateProviderProbeTests(unittest.TestCase):
    def test_dry_run_selects_provider_probe_target_without_import(self):
        report = build_archival_account_state_provider_probe_report(
            pagination_plan=pagination_plan(),
            provider_evaluation=provider_evaluation(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertEqual(report["summary"]["probe_targets"], 1)
        self.assertEqual(report["summary"]["snapshots_ready_for_manual_review"], 0)
        self.assertEqual(report["probe_target"]["token_mint"], "MintProbe111")
        self.assertEqual(report["probe_status"], "dry_run_probe_target_selected")

    def test_rejects_provider_response_after_decision_slot(self):
        report = build_archival_account_state_provider_probe_report(
            pagination_plan=pagination_plan(),
            provider_evaluation=provider_evaluation(),
            raw_provider_response=mint_response(context_slot=1001),
            generated_at=123.0,
        )

        self.assertEqual(report["probe_status"], "rejected_provider_response_after_decision_slot")
        self.assertIn("provider_context_slot_after_decision_slot", report["blockers"])
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertEqual(report["validation"]["provider_context_slot"], 1001)

    def test_blocks_provider_response_missing_supply(self):
        response = mint_response(context_slot=999)
        del response["result"]["value"]["data"]["parsed"]["info"]["supply"]

        report = build_archival_account_state_provider_probe_report(
            pagination_plan=pagination_plan(),
            provider_evaluation=provider_evaluation(),
            raw_provider_response=response,
            generated_at=123.0,
        )

        self.assertEqual(report["probe_status"], "blocked_missing_mint_supply")
        self.assertIn("missing_mint_supply", report["blockers"])
        self.assertFalse(report["supply_snapshot_import_allowed"])

    def test_valid_response_is_ready_for_manual_review_but_not_imported(self):
        report = build_archival_account_state_provider_probe_report(
            pagination_plan=pagination_plan(),
            provider_evaluation=provider_evaluation(),
            raw_provider_response=mint_response(context_slot=999, supply="123456"),
            generated_at=123.0,
        )

        self.assertEqual(report["probe_status"], "provider_snapshot_ready_for_manual_review")
        self.assertTrue(report["validation"]["decision_time_safe"])
        self.assertEqual(report["validation"]["mint_supply"], "123456")
        self.assertEqual(report["summary"]["snapshots_ready_for_manual_review"], 1)
        self.assertFalse(report["supply_snapshot_import_allowed"])

    def test_writer_preserves_raw_provider_response(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pagination_path = root / "pagination.json"
            provider_eval_path = root / "provider_eval.json"
            raw_path = root / "raw_input.json"
            preserved_raw_path = root / "preserved" / "raw_response.json"
            report_path = root / "probe.json"
            pagination_path.write_text(json.dumps(pagination_plan()), encoding="utf-8")
            provider_eval_path.write_text(json.dumps(provider_evaluation()), encoding="utf-8")
            raw_path.write_text(json.dumps(mint_response(context_slot=999)), encoding="utf-8")

            report = write_archival_account_state_provider_probe_report(
                pagination_plan_path=pagination_path,
                provider_evaluation_path=provider_eval_path,
                raw_provider_response_path=raw_path,
                preserved_raw_response_path=preserved_raw_path,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(preserved_raw_path.exists())
            self.assertTrue(report["raw_provider_response_preserved"])
            self.assertEqual(json.loads(preserved_raw_path.read_text(encoding="utf-8"))["result"]["context"]["slot"], 999)


if __name__ == "__main__":
    unittest.main()
