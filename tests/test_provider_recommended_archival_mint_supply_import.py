import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.test_archival_mint_snapshot_response_import import collection_report, mint_response
from utils.import_provider_recommended_archival_mint_supply_snapshots import (
    write_provider_recommended_archival_mint_snapshot_response_import_report,
)


def import_pagination_plan():
    return {
        "mode": "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY",
        "rows": [
            {"token_mint": "MintB", "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"},
            {"token_mint": "MintC", "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"},
            {"token_mint": "MintA", "recommended_action": "RUN_SUPPLY_RECONSTRUCTION"},
        ],
    }


class ProviderRecommendedArchivalMintSupplyImportTests(unittest.TestCase):
    def test_writer_imports_only_provider_recommended_mints(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection_path = root / "collection.json"
            pagination_path = root / "pagination.json"
            raw_path = root / "provider_recommended_raw.json"
            report_path = root / "provider_recommended_import_report.json"
            snapshots_path = root / "provider_recommended_snapshots.jsonl"
            collection_path.write_text(json.dumps(collection_report()), encoding="utf-8")
            pagination_path.write_text(json.dumps(import_pagination_plan()), encoding="utf-8")
            raw_path.write_text(json.dumps([mint_response(2, 190)]), encoding="utf-8")

            report = write_provider_recommended_archival_mint_snapshot_response_import_report(
                collection_report_path=collection_path,
                pagination_plan_path=pagination_path,
                raw_response_path=raw_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["source_filter"], "provider_recommended_archival_account_state")
            self.assertEqual(report["summary"]["allowed_token_count"], 2)
            self.assertEqual(report["summary"]["filtered_out_requests"], 1)
            self.assertEqual(report["summary"]["requests_scanned"], 2)
            self.assertEqual(report["summary"]["snapshots_imported"], 1)
            self.assertEqual(report["summary"]["blocked_missing_response"], 1)
            self.assertEqual(report["provider_recommended_token_count"], 2)
            self.assertTrue(report_path.exists())
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintB")


if __name__ == "__main__":
    unittest.main()
