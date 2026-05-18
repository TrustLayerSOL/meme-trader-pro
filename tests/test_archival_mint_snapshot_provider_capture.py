import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wallets.archival_mint_snapshot_provider_capture import build_archival_mint_snapshot_provider_capture_report


def request_bundle_report():
    return {
        "mode": "ARCHIVAL_MINT_SNAPSHOT_REQUEST_BUNDLE_REVIEW_ONLY",
        "raw_response_save_path": "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
        "batch_request_chunks": [
            {
                "index": 1,
                "path": "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_request.part001.json",
                "request_count": 2,
                "request_ids": ["mint-snapshot:a", "mint-snapshot:b"],
                "jsonrpc_payload": [
                    {"jsonrpc": "2.0", "id": "mint-snapshot:a", "method": "getAccountInfo", "params": ["MintA"]},
                    {"jsonrpc": "2.0", "id": "mint-snapshot:b", "method": "getAccountInfo", "params": ["MintB"]},
                ],
            },
            {
                "index": 2,
                "path": "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_request.part002.json",
                "request_count": 1,
                "request_ids": ["mint-snapshot:c"],
                "jsonrpc_payload": [
                    {"jsonrpc": "2.0", "id": "mint-snapshot:c", "method": "getAccountInfo", "params": ["MintC"]},
                ],
            },
        ],
    }


def provider_responses(payload):
    return [
        {
            "jsonrpc": "2.0",
            "id": row["id"],
            "result": {
                "context": {"slot": 99},
                "value": {
                    "data": {
                        "program": "spl-token",
                        "parsed": {"type": "mint", "info": {"supply": "1000000", "decimals": 6}},
                    }
                },
            },
        }
        for row in payload
    ]


class ArchivalMintSnapshotProviderCaptureTests(unittest.TestCase):
    def test_execute_without_provider_endpoint_blocks_without_provider_calls(self):
        report, raw_batch = build_archival_mint_snapshot_provider_capture_report(
            request_bundle_report=request_bundle_report(),
            execute=True,
            rpc_url=None,
            rpc_post=None,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_SNAPSHOT_PROVIDER_CAPTURE_REVIEW_ONLY")
        self.assertEqual(report["capture_status"], "blocked_missing_archival_provider_rpc_url")
        self.assertIn("missing_archival_provider_rpc_url", report["blockers"])
        self.assertFalse(report["provider_endpoint_configured"])
        self.assertEqual(report["summary"]["provider_calls_performed"], 0)
        self.assertEqual(report["summary"]["raw_response_chunks_preserved"], 0)
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertIsNone(raw_batch)

    def test_execute_captures_chunks_and_combines_responses_without_import(self):
        calls = []

        def fake_rpc_post(url, payload, timeout):
            calls.append({"url": url, "payload": payload, "timeout": timeout})
            return provider_responses(payload)

        report, raw_batch = build_archival_mint_snapshot_provider_capture_report(
            request_bundle_report=request_bundle_report(),
            execute=True,
            rpc_url="https://secret.example/?api-key=do-not-store",
            rpc_post=fake_rpc_post,
            timeout=7,
            generated_at=123.0,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(report["capture_status"], "provider_batch_responses_captured_for_saved_import")
        self.assertEqual(report["summary"]["provider_calls_performed"], 2)
        self.assertEqual(report["summary"]["raw_response_chunks_preserved"], 2)
        self.assertEqual(report["summary"]["combined_responses"], 3)
        self.assertFalse(report["supply_snapshot_import_allowed"])
        self.assertFalse(report["supply_snapshot_imported"])
        self.assertEqual(raw_batch["responses"][0]["id"], "mint-snapshot:a")
        self.assertEqual(len(raw_batch["responses"]), 3)
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("secret.example", rendered)
        self.assertNotIn("api-key", rendered)
        self.assertNotIn("do-not-store", rendered)

    def test_provider_failure_is_sanitized_and_does_not_emit_raw_batch(self):
        def fake_rpc_post(url, payload, timeout):
            raise RuntimeError(f"failed endpoint {url}")

        report, raw_batch = build_archival_mint_snapshot_provider_capture_report(
            request_bundle_report=request_bundle_report(),
            execute=True,
            rpc_url="https://secret.example/?api-key=do-not-store",
            rpc_post=fake_rpc_post,
            generated_at=123.0,
        )

        self.assertEqual(report["capture_status"], "blocked_provider_call_failed")
        self.assertEqual(report["summary"]["provider_calls_performed"], 1)
        self.assertEqual(report["summary"]["raw_response_chunks_preserved"], 0)
        self.assertIn("provider_call_failed", report["blockers"])
        self.assertIsNone(raw_batch)
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("secret.example", rendered)
        self.assertNotIn("api-key", rendered)

    def test_writer_contract_paths_are_relative_and_safe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw" / "batch.json"
            report, raw_batch = build_archival_mint_snapshot_provider_capture_report(
                request_bundle_report={**request_bundle_report(), "raw_response_save_path": str(raw_path)},
                execute=False,
                rpc_url="https://secret.example/?api-key=do-not-store",
                rpc_post=None,
                generated_at=123.0,
            )

            self.assertEqual(report["capture_status"], "dry_run_capture_not_executed")
            self.assertIsNone(raw_batch)
            self.assertEqual(report["summary"]["request_chunks_available"], 2)
            self.assertEqual(report["summary"]["requests_available"], 3)


if __name__ == "__main__":
    unittest.main()
