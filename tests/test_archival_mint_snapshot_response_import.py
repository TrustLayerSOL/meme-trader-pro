import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.import_archival_mint_supply_snapshots import write_archival_mint_snapshot_response_import_report
from wallets.archival_mint_snapshot_response_import import build_archival_mint_snapshot_response_import_report


def collection_report():
    return {
        "mode": "ARCHIVAL_MINT_SUPPLY_SNAPSHOT_COLLECTION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "requests": [
            {
                "token_mint": "MintA",
                "status": "pending_archival_provider",
                "requested_snapshot_slot": 100,
                "max_acceptable_snapshot_slot": 100,
                "jsonrpc_payload": {"id": 1, "method": "getAccountInfo", "params": ["MintA", {"encoding": "jsonParsed"}]},
            },
            {
                "token_mint": "MintB",
                "status": "pending_archival_provider",
                "requested_snapshot_slot": 200,
                "max_acceptable_snapshot_slot": 200,
                "jsonrpc_payload": {"id": 2, "method": "getAccountInfo", "params": ["MintB", {"encoding": "jsonParsed"}]},
            },
            {
                "token_mint": "MintC",
                "status": "pending_archival_provider",
                "requested_snapshot_slot": 300,
                "max_acceptable_snapshot_slot": 300,
                "jsonrpc_payload": {"id": 3, "method": "getAccountInfo", "params": ["MintC", {"encoding": "jsonParsed"}]},
            },
        ],
    }


def mint_response(request_id, slot, supply="1000000", decimals=6):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "context": {"slot": slot},
            "value": {
                "data": {
                    "program": "spl-token",
                    "parsed": {
                        "type": "mint",
                        "info": {"supply": supply, "decimals": decimals},
                    },
                }
            },
        },
    }


class ArchivalMintSnapshotResponseImportTests(unittest.TestCase):
    def test_imports_only_decision_time_safe_saved_responses(self):
        report = build_archival_mint_snapshot_response_import_report(
            snapshot_collection_report=collection_report(),
            raw_provider_response=[
                mint_response(1, 90, "1000000", 6),
                mint_response(2, 250, "2000000", 6),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_SNAPSHOT_RESPONSE_IMPORT_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["requests_scanned"], 3)
        self.assertEqual(report["summary"]["raw_responses_scanned"], 2)
        self.assertEqual(report["summary"]["snapshots_imported"], 1)
        self.assertEqual(report["summary"]["blocked_too_new_snapshots"], 1)
        self.assertEqual(report["summary"]["blocked_missing_response"], 1)
        self.assertEqual(report["snapshots"][0]["token_mint"], "MintA")
        self.assertEqual(report["snapshots"][0]["slot"], 90)
        self.assertTrue(report["snapshots"][0]["decision_time_safe"])

    def test_writer_persists_report_and_compatible_snapshot_jsonl(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection_path = root / "collection.json"
            raw_path = root / "raw.json"
            report_path = root / "import_report.json"
            snapshots_path = root / "snapshots.jsonl"
            collection_path.write_text(json.dumps(collection_report()), encoding="utf-8")
            raw_path.write_text(json.dumps([mint_response(1, 90)]), encoding="utf-8")

            report = write_archival_mint_snapshot_response_import_report(
                collection_report_path=collection_path,
                raw_response_path=raw_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(snapshots_path.exists())
            self.assertEqual(report["summary"]["snapshots_imported"], 1)
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintA")


if __name__ == "__main__":
    unittest.main()

