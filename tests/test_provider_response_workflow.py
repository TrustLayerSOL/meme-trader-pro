import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wallets.provider_response_workflow import build_provider_response_workflow_report


def provider_response(request_id, slot=100):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "context": {"slot": slot},
            "value": {"data": {"parsed": {"type": "mint", "info": {"supply": "1000", "decimals": 6}}}},
        },
    }


def request_bundle(raw_dir: Path):
    return {
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "requests_bundled": 3,
            "target_tokens": 2,
            "request_chunk_count": 2,
            "filtered_out_requests": 4,
        },
        "batch_request_chunks": [
            {"index": 1, "path": str(raw_dir / "request.part001.json"), "request_count": 2, "request_ids": ["1", "2"]},
            {"index": 2, "path": str(raw_dir / "request.part002.json"), "request_count": 1, "request_ids": ["3"]},
        ],
        "response_template_chunks": [
            {
                "index": 1,
                "path": str(raw_dir / "template.part001.json"),
                "request_count": 2,
                "request_ids": ["1", "2"],
                "raw_response_save_path": str(raw_dir / "raw.part001.json"),
            },
            {
                "index": 2,
                "path": str(raw_dir / "template.part002.json"),
                "request_count": 1,
                "request_ids": ["3"],
                "raw_response_save_path": str(raw_dir / "raw.part002.json"),
            },
        ],
    }


class ProviderResponseWorkflowTests(unittest.TestCase):
    def test_reports_missing_response_parts_without_mutating_trust(self):
        with TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "raw.part001.json").write_text(
                json.dumps({"responses": [provider_response(1), provider_response(2)]}),
                encoding="utf-8",
            )

            report = build_provider_response_workflow_report(
                request_bundle_report=request_bundle(raw_dir),
                combined_raw_response_path=raw_dir / "combined.json",
                response_import_report={"summary": {"raw_responses_scanned": 0, "snapshots_imported": 0}},
                proof_readiness_report={"summary": {"proof_readiness_pct": 11}},
                root=raw_dir,
                generated_at=123.0,
            )

            self.assertTrue(report["review_only"])
            self.assertTrue(report["live_execution_locked"])
            self.assertFalse(report["wallet_list_mutated"])
            self.assertFalse(report["auto_trust_mutation_allowed"])
            self.assertEqual(report["summary"]["focused_request_rows"], 3)
            self.assertEqual(report["summary"]["response_part_files_expected"], 2)
            self.assertEqual(report["summary"]["response_part_files_present"], 1)
            self.assertEqual(report["summary"]["response_part_files_missing"], 1)
            self.assertEqual(report["summary"]["responses_in_part_files"], 2)
            self.assertEqual(report["summary"]["chunks_ready_to_combine"], 1)
            self.assertEqual(report["summary"]["chunks_missing_response_files"], 1)
            self.assertEqual(report["next_action"]["code"], "fill_missing_response_parts")
            self.assertIn("raw.part002.json", report["next_action"]["detail"])

    def test_reports_focused_import_as_next_action_after_combined_raw_exists(self):
        with TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "raw.part001.json").write_text(
                json.dumps({"responses": [provider_response(1), provider_response(2)]}),
                encoding="utf-8",
            )
            (raw_dir / "raw.part002.json").write_text(
                json.dumps({"responses": [provider_response(3)]}),
                encoding="utf-8",
            )
            combined = raw_dir / "combined.json"
            combined.write_text(
                json.dumps({"responses": [provider_response(1), provider_response(2), provider_response(3)]}),
                encoding="utf-8",
            )

            report = build_provider_response_workflow_report(
                request_bundle_report=request_bundle(raw_dir),
                combined_raw_response_path=combined,
                response_import_report={"summary": {"raw_responses_scanned": 0, "snapshots_imported": 0}},
                proof_readiness_report={"summary": {"proof_readiness_pct": 11}},
                root=raw_dir,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["response_part_files_missing"], 0)
            self.assertEqual(report["summary"]["combined_raw_responses"], 3)
            self.assertEqual(report["next_action"]["code"], "run_focused_import")
            self.assertIn("import_provider_recommended_archival_mint_supply_snapshots.py", "\n".join(report["operator_commands"]))


if __name__ == "__main__":
    unittest.main()
