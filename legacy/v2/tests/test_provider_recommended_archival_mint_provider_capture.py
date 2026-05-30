import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.test_archival_mint_snapshot_provider_capture import request_bundle_report
from utils.capture_provider_recommended_archival_mint_supply_provider_responses import (
    write_provider_recommended_archival_mint_snapshot_provider_capture_report,
)


class ProviderRecommendedArchivalMintProviderCaptureTests(unittest.TestCase):
    def test_writer_uses_focused_bundle_and_raw_response_paths(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "provider_recommended_bundle.json"
            report_path = root / "provider_recommended_capture_report.json"
            raw_path = root / "provider_recommended_raw.json"
            bundle_path.write_text(json.dumps(request_bundle_report()), encoding="utf-8")

            report = write_provider_recommended_archival_mint_snapshot_provider_capture_report(
                request_bundle_path=bundle_path,
                report_path=report_path,
                raw_response_path=raw_path,
                execute=False,
                rpc_url="https://secret.example/?api-key=do-not-store",
                rpc_post=None,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["capture_status"], "dry_run_capture_not_executed")
            self.assertEqual(report["summary"]["request_chunks_available"], 2)
            self.assertEqual(report["summary"]["requests_available"], 3)
            self.assertEqual(report["input_paths"]["request_bundle"], str(bundle_path))
            self.assertEqual(report["output_paths"]["raw_provider_response"], None)
            self.assertFalse(report["supply_snapshot_import_allowed"])


if __name__ == "__main__":
    unittest.main()
