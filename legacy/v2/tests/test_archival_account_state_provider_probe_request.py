import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_account_state_provider_probe_request import (
    write_archival_account_state_provider_probe_request_report,
)
from wallets.archival_account_state_provider_probe_request import (
    build_archival_account_state_provider_probe_request_report,
)


def probe_report():
    return {
        "mode": "ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE_REVIEW_ONLY",
        "provider_id": "quicknode_solana_mainnet_archive",
        "probe_status": "dry_run_probe_target_selected",
        "probe_target": {
            "token_mint": "MintProbe111",
            "decision_slot": 1000,
            "signature_count": 2000,
        },
    }


class ArchivalAccountStateProviderProbeRequestTests(unittest.TestCase):
    def test_builds_manual_request_bundle_without_provider_call_or_secret(self):
        report = build_archival_account_state_provider_probe_request_report(
            provider_probe=probe_report(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_ACCOUNT_STATE_PROVIDER_REQUEST_BUNDLE_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["provider_call_performed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertEqual(report["summary"]["request_bundles_prepared"], 1)
        self.assertEqual(report["request_bundle"]["token_mint"], "MintProbe111")
        self.assertEqual(report["request_bundle"]["max_acceptable_context_slot"], 1000)
        self.assertEqual(report["request_bundle"]["jsonrpc_payload"]["method"], "getAccountInfo")
        self.assertNotIn("api-key", json.dumps(report).lower())
        self.assertNotIn("bearer", json.dumps(report).lower())

    def test_blocks_when_probe_target_is_missing(self):
        report = build_archival_account_state_provider_probe_request_report(
            provider_probe={
                "mode": "ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE_REVIEW_ONLY",
                "provider_id": "quicknode_solana_mainnet_archive",
                "probe_status": "blocked_no_provider_probe_target",
            },
            generated_at=123.0,
        )

        self.assertEqual(report["request_status"], "blocked_missing_probe_target")
        self.assertEqual(report["summary"]["blocked_request_bundles"], 1)
        self.assertIn("missing_probe_target", report["blockers"])

    def test_request_bundle_contains_operator_validation_steps(self):
        report = build_archival_account_state_provider_probe_request_report(
            provider_probe=probe_report(),
            generated_at=123.0,
        )

        steps = report["operator_steps"]
        self.assertIn("Save provider raw JSON response", " ".join(steps))
        self.assertIn("--raw-provider-response-path", report["validation_command"])
        self.assertIn("context.slot <= decision_slot", " ".join(report["acceptance_criteria"]))

    def test_writer_persists_request_bundle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            probe_path = root / "provider_probe.json"
            report_path = root / "request_bundle.json"
            probe_path.write_text(json.dumps(probe_report()), encoding="utf-8")

            report = write_archival_account_state_provider_probe_request_report(
                provider_probe_path=probe_path,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["request_bundles_prepared"], 1)
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["request_bundle"]["token_mint"], "MintProbe111")


if __name__ == "__main__":
    unittest.main()
