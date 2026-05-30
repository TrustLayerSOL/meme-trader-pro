import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_provider_response_workflow import write_provider_response_workflow_report


def response(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"context": {"slot": 100}, "value": {"data": {"parsed": {"type": "mint", "info": {"supply": "1000", "decimals": 6}}}}},
    }


class BuildProviderResponseWorkflowTests(unittest.TestCase):
    def test_writer_reads_reports_and_persists_operator_workflow(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw.part001.json"
            raw_path.write_text(json.dumps({"responses": [response(1)]}), encoding="utf-8")
            bundle_path = root / "bundle.json"
            import_path = root / "import.json"
            proof_path = root / "proof.json"
            output_path = root / "workflow.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "summary": {"requests_bundled": 1, "target_tokens": 1, "filtered_out_requests": 0},
                        "response_template_chunks": [
                            {
                                "index": 1,
                                "request_count": 1,
                                "request_ids": ["1"],
                                "raw_response_save_path": str(raw_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            import_path.write_text(json.dumps({"summary": {"raw_responses_scanned": 0, "snapshots_imported": 0}}), encoding="utf-8")
            proof_path.write_text(json.dumps({"summary": {"proof_readiness_pct": 11}}), encoding="utf-8")

            report = write_provider_response_workflow_report(
                request_bundle_path=bundle_path,
                response_import_path=import_path,
                proof_readiness_path=proof_path,
                combined_raw_response_path=root / "combined.json",
                report_path=output_path,
                root=root,
                generated_at=123.0,
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(report["summary"]["focused_request_rows"], 1)
            self.assertEqual(report["summary"]["responses_in_part_files"], 1)
            self.assertEqual(report["next_action"]["code"], "run_response_combiner")
            persisted = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["live_execution_locked"])
            self.assertFalse(persisted["wallet_list_mutated"])


if __name__ == "__main__":
    unittest.main()
