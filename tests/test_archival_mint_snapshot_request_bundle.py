import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_mint_snapshot_request_bundle import write_archival_mint_snapshot_request_bundle_report
from wallets.archival_mint_snapshot_request_bundle import build_archival_mint_snapshot_request_bundle_report


def collection_report():
    return {
        "mode": "ARCHIVAL_MINT_SUPPLY_SNAPSHOT_COLLECTION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {"requests_prepared": 2, "pending_archival_provider": 2},
        "requests": [
            {
                "token_mint": "MintA",
                "status": "pending_archival_provider",
                "max_acceptable_snapshot_slot": 100,
                "jsonrpc_payload": {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": ["MintA", {"encoding": "jsonParsed"}]},
            },
            {
                "token_mint": "MintB",
                "status": "pending_archival_provider",
                "max_acceptable_snapshot_slot": 200,
                "jsonrpc_payload": {"jsonrpc": "2.0", "id": 2, "method": "getAccountInfo", "params": ["MintB", {"encoding": "jsonParsed"}]},
            },
        ],
    }


class ArchivalMintSnapshotRequestBundleTests(unittest.TestCase):
    def test_builds_batch_request_without_fetching_or_mutating(self):
        report = build_archival_mint_snapshot_request_bundle_report(
            snapshot_collection_report=collection_report(),
            raw_response_path="data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_SNAPSHOT_REQUEST_BUNDLE_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["provider_calls_performed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["requests_bundled"], 2)
        self.assertEqual(report["summary"]["target_tokens"], 2)
        self.assertEqual(len(report["batch_jsonrpc_payload"]), 2)
        self.assertEqual(report["batch_jsonrpc_payload"][0]["method"], "getAccountInfo")
        self.assertIn("import_archival_mint_supply_snapshots.py", report["response_import_command"])
        self.assertEqual(
            report["raw_response_save_path"],
            "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
        )

    def test_includes_provider_handoff_template_and_rebuild_commands(self):
        report = build_archival_mint_snapshot_request_bundle_report(
            snapshot_collection_report=collection_report(),
            raw_response_path="data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
            batch_request_path="data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_request.json",
            response_template_path="data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_response_template.json",
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["request_packet_ready"], 1)
        self.assertEqual(report["batch_request_save_path"], "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_request.json")
        self.assertEqual(report["response_template_save_path"], "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_response_template.json")
        self.assertEqual(report["response_template"]["responses"], [])
        self.assertEqual(report["response_template"]["expected_responses"][0]["request_id"], "1")
        self.assertEqual(report["response_template"]["expected_responses"][0]["token_mint"], "MintA")
        joined_commands = "\n".join(report["post_import_commands"])
        self.assertIn("build_archival_supply_evidence.py", joined_commands)
        self.assertIn("build_score_ready_market_context.py", joined_commands)

    def test_writer_persists_report_request_packet_and_response_template(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection_path = root / "collection.json"
            report_path = root / "bundle_report.json"
            batch_path = root / "batch_request.json"
            template_path = root / "response_template.json"
            collection_path.write_text(json.dumps(collection_report()), encoding="utf-8")

            report = write_archival_mint_snapshot_request_bundle_report(
                collection_report_path=collection_path,
                report_path=report_path,
                raw_response_path="raw_response.json",
                batch_request_path=batch_path,
                response_template_path=template_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(batch_path.exists())
            self.assertTrue(template_path.exists())
            self.assertEqual(report["summary"]["requests_bundled"], 2)
            self.assertEqual(json.loads(batch_path.read_text(encoding="utf-8"))[0]["id"], 1)
            self.assertEqual(json.loads(template_path.read_text(encoding="utf-8"))["expected_responses"][1]["request_id"], "2")


if __name__ == "__main__":
    unittest.main()
