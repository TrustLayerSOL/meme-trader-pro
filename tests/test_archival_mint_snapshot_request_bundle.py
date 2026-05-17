import unittest

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


if __name__ == "__main__":
    unittest.main()

