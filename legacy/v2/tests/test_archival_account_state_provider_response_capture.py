import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.capture_archival_account_state_provider_response import write_archival_account_state_provider_response_capture_report
from wallets.archival_account_state_provider_response_capture import (
    build_archival_account_state_provider_response_capture_report,
)


def request_report(raw_response_save_path="data/reports/historical_backfill/raw_provider_responses/probe_raw.json"):
    return {
        "mode": "ARCHIVAL_ACCOUNT_STATE_PROVIDER_REQUEST_BUNDLE_REVIEW_ONLY",
        "request_status": "request_bundle_prepared",
        "request_bundle": {
            "provider_id": "quicknode_solana_mainnet_archive",
            "token_mint": "MintProbe111",
            "decision_slot": 1000,
            "requested_historical_context_slot": 1000,
            "max_acceptable_context_slot": 1000,
            "jsonrpc_payload": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": ["MintProbe111", {"encoding": "jsonParsed"}],
            },
            "raw_response_save_path": raw_response_save_path,
        },
    }


def mint_response(*, context_slot=999, supply="123456"):
    return {
        "jsonrpc": "2.0",
        "result": {
            "context": {"slot": context_slot},
            "value": {
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
            },
        },
        "id": 1,
    }


class ArchivalAccountStateProviderResponseCaptureTests(unittest.TestCase):
    def test_execute_without_archival_endpoint_blocks_without_provider_call(self):
        report = build_archival_account_state_provider_response_capture_report(
            request_report=request_report(),
            execute=True,
            rpc_url=None,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_ACCOUNT_STATE_PROVIDER_RESPONSE_CAPTURE_REVIEW_ONLY")
        self.assertEqual(report["capture_status"], "blocked_missing_archival_provider_rpc_url")
        self.assertIn("missing_archival_provider_rpc_url", report["blockers"])
        self.assertFalse(report["provider_endpoint_configured"])
        self.assertFalse(report["provider_call_performed"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertFalse(report["supply_snapshot_imported"])
        self.assertEqual(report["summary"]["blocked_captures"], 1)
        self.assertEqual(report["summary"]["provider_calls_performed"], 0)

    def test_execute_capture_preserves_raw_response_and_validates_without_import(self):
        calls = []

        def fake_rpc_post(url, payload, timeout):
            calls.append({"url": url, "payload": payload, "timeout": timeout})
            return mint_response(context_slot=999, supply="123456")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw" / "provider_response.json"
            report_path = root / "capture_report.json"
            request_path = root / "request_report.json"
            request_path.write_text(
                json.dumps(request_report(raw_response_save_path=str(raw_path))),
                encoding="utf-8",
            )

            report = write_archival_account_state_provider_response_capture_report(
                request_bundle_path=request_path,
                report_path=report_path,
                raw_response_path=raw_path,
                execute=True,
                rpc_url="https://secret.example/?api-key=do-not-store",
                rpc_post=fake_rpc_post,
                timeout=7,
                generated_at=123.0,
            )

            self.assertEqual(len(calls), 1)
            self.assertTrue(raw_path.exists())
            self.assertTrue(report_path.exists())
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["result"]["context"]["slot"], 999)
            self.assertEqual(report["capture_status"], "provider_response_captured_ready_for_manual_review")
            self.assertEqual(report["validation_status"], "provider_snapshot_ready_for_manual_review")
            self.assertTrue(report["provider_endpoint_configured"])
            self.assertTrue(report["provider_call_performed"])
            self.assertTrue(report["raw_provider_response_preserved"])
            self.assertFalse(report["supply_snapshot_import_allowed"])
            self.assertFalse(report["supply_snapshot_imported"])
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn("secret.example", rendered)
            self.assertNotIn("api-key", rendered)
            self.assertNotIn("do-not-store", rendered)

    def test_future_slot_response_is_rejected_and_not_imported(self):
        def fake_rpc_post(url, payload, timeout):
            return mint_response(context_slot=1001, supply="123456")

        report = build_archival_account_state_provider_response_capture_report(
            request_report=request_report(),
            execute=True,
            rpc_url="https://secret.example/?api-key=do-not-store",
            rpc_post=fake_rpc_post,
            generated_at=123.0,
        )

        self.assertEqual(report["capture_status"], "provider_response_captured_rejected")
        self.assertEqual(report["validation_status"], "rejected_provider_response_after_decision_slot")
        self.assertIn("provider_context_slot_after_decision_slot", report["blockers"])
        self.assertEqual(report["summary"]["rejected_future_slot_responses"], 1)
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertFalse(report["supply_snapshot_imported"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("secret.example", rendered)
        self.assertNotIn("api-key", rendered)

    def test_provider_call_failure_is_sanitized(self):
        def fake_rpc_post(url, payload, timeout):
            raise RuntimeError(f"failed endpoint {url}")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request_report.json"
            report_path = root / "capture_report.json"
            request_path.write_text(json.dumps(request_report()), encoding="utf-8")

            report = write_archival_account_state_provider_response_capture_report(
                request_bundle_path=request_path,
                report_path=report_path,
                execute=True,
                rpc_url="https://secret.example/?api-key=do-not-store",
                rpc_post=fake_rpc_post,
                generated_at=123.0,
            )

            self.assertEqual(report["capture_status"], "blocked_provider_call_failed")
            self.assertEqual(report["provider_call_error"], "RuntimeError")
            self.assertTrue(report["provider_call_performed"])
            self.assertEqual(report["summary"]["provider_calls_performed"], 1)
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn("secret.example", rendered)
            self.assertNotIn("api-key", rendered)

    def test_saved_raw_response_can_be_validated_without_provider_endpoint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw" / "provider_response.json"
            report_path = root / "capture_report.json"
            request_path = root / "request_report.json"
            request_path.write_text(
                json.dumps(request_report(raw_response_save_path=str(raw_path))),
                encoding="utf-8",
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(mint_response(context_slot=999)), encoding="utf-8")

            report = write_archival_account_state_provider_response_capture_report(
                request_bundle_path=request_path,
                report_path=report_path,
                raw_response_path=raw_path,
                execute=False,
                rpc_url=None,
                validate_saved_raw_response=True,
                generated_at=123.0,
            )

            self.assertEqual(report["capture_status"], "provider_response_captured_ready_for_manual_review")
            self.assertEqual(report["validation_status"], "provider_snapshot_ready_for_manual_review")
            self.assertFalse(report["provider_endpoint_configured"])
            self.assertFalse(report["provider_call_performed"])
            self.assertTrue(report["raw_provider_response_preserved"])
            self.assertEqual(report["summary"]["provider_calls_performed"], 0)
            self.assertEqual(report["summary"]["raw_responses_preserved"], 1)
            self.assertFalse(report["supply_snapshot_import_allowed"])
            self.assertFalse(report["supply_snapshot_imported"])

    def test_missing_saved_raw_response_blocks_without_provider_call(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw" / "missing_response.json"
            report_path = root / "capture_report.json"
            request_path = root / "request_report.json"
            request_path.write_text(
                json.dumps(request_report(raw_response_save_path=str(raw_path))),
                encoding="utf-8",
            )

            report = write_archival_account_state_provider_response_capture_report(
                request_bundle_path=request_path,
                report_path=report_path,
                raw_response_path=raw_path,
                execute=False,
                rpc_url=None,
                validate_saved_raw_response=True,
                generated_at=123.0,
            )

            self.assertEqual(report["capture_status"], "blocked_missing_saved_raw_provider_response")
            self.assertIn("missing_saved_raw_provider_response", report["blockers"])
            self.assertFalse(report["provider_call_performed"])
            self.assertFalse(report["raw_provider_response_preserved"])
            self.assertEqual(report["summary"]["blocked_captures"], 1)

    def test_missing_request_bundle_blocks_cleanly(self):
        report = build_archival_account_state_provider_response_capture_report(
            request_report={"mode": "ARCHIVAL_ACCOUNT_STATE_PROVIDER_REQUEST_BUNDLE_REVIEW_ONLY"},
            execute=True,
            rpc_url="https://secret.example/?api-key=do-not-store",
            generated_at=123.0,
        )

        self.assertEqual(report["capture_status"], "blocked_missing_request_bundle")
        self.assertFalse(report["provider_call_performed"])
        self.assertEqual(report["summary"]["blocked_captures"], 1)


if __name__ == "__main__":
    unittest.main()
