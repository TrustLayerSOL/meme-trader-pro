import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.test_archival_mint_snapshot_request_bundle import collection_report_with_requests
from utils.build_provider_recommended_archival_mint_snapshot_request_bundle import (
    provider_recommended_token_mints,
    write_provider_recommended_archival_mint_snapshot_request_bundle_report,
)


def pagination_plan():
    return {
        "mode": "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY",
        "rows": [
            {"token_mint": "Mint2", "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"},
            {"token_mint": "Mint4", "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"},
            {"token_mint": "Mint5", "recommended_action": "RUN_SUPPLY_RECONSTRUCTION"},
            {"token_mint": "", "recommended_action": "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"},
        ],
    }


class ProviderRecommendedArchivalMintSnapshotRequestBundleTests(unittest.TestCase):
    def test_extracts_provider_recommended_mints_from_pagination_plan(self):
        self.assertEqual(provider_recommended_token_mints(pagination_plan()), {"Mint2", "Mint4"})

    def test_writer_persists_only_provider_recommended_requests(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection_path = root / "collection.json"
            pagination_path = root / "pagination.json"
            report_path = root / "provider_bundle_report.json"
            batch_path = root / "provider_batch_request.json"
            template_path = root / "provider_response_template.json"
            collection_path.write_text(json.dumps(collection_report_with_requests(5)), encoding="utf-8")
            pagination_path.write_text(json.dumps(pagination_plan()), encoding="utf-8")

            report = write_provider_recommended_archival_mint_snapshot_request_bundle_report(
                collection_report_path=collection_path,
                pagination_plan_path=pagination_path,
                report_path=report_path,
                raw_response_path="provider_batch_raw.json",
                batch_request_path=batch_path,
                response_template_path=template_path,
                batch_chunk_size=1,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["source_filter"], "provider_recommended_archival_account_state")
            self.assertEqual(report["summary"]["allowed_token_count"], 2)
            self.assertEqual(report["summary"]["requests_bundled"], 2)
            self.assertEqual(report["summary"]["target_tokens"], 2)
            self.assertEqual(report["summary"]["filtered_out_requests"], 3)
            self.assertEqual(report["provider_recommended_token_count"], 2)
            self.assertEqual(json.loads(batch_path.read_text(encoding="utf-8"))[0]["id"], 2)
            self.assertEqual(json.loads(template_path.read_text(encoding="utf-8"))["expected_responses"][1]["token_mint"], "Mint4")
            self.assertEqual(report["batch_request_chunks"][1]["request_ids"], ["4"])


if __name__ == "__main__":
    unittest.main()
