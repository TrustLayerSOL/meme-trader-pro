import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.combine_provider_response_chunks import write_combined_provider_response_chunks


def response(request_id, slot=100):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"context": {"slot": slot}, "value": {"data": {"parsed": {"type": "mint", "info": {"supply": "1000", "decimals": 6}}}}},
    }


class ProviderResponseChunkCombinerTests(unittest.TestCase):
    def test_combines_chunk_response_files_without_mutating_trust(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            part1 = root / "raw.part001.json"
            part2 = root / "raw.part002.json"
            output = root / "combined.json"
            report_path = root / "combine_report.json"
            part1.write_text(json.dumps({"responses": [response(1), response(2)]}), encoding="utf-8")
            part2.write_text(json.dumps([response(3)]), encoding="utf-8")

            report = write_combined_provider_response_chunks(
                input_glob=str(root / "raw.part*.json"),
                output_path=output,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report["review_only"])
            self.assertTrue(report["live_execution_locked"])
            self.assertFalse(report["wallet_list_mutated"])
            self.assertFalse(report["auto_trust_mutation_allowed"])
            self.assertEqual(report["summary"]["chunk_files_scanned"], 2)
            self.assertEqual(report["summary"]["responses_collected"], 3)
            combined = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([row["id"] for row in combined["responses"]], [1, 2, 3])
            self.assertTrue(report_path.exists())

    def test_dedupes_response_ids_and_records_invalid_chunks(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            part1 = root / "raw.part001.json"
            part2 = root / "raw.part002.json"
            bad = root / "raw.part003.json"
            output = root / "combined.json"
            report_path = root / "combine_report.json"
            part1.write_text(json.dumps({"responses": [response(1), response(2)]}), encoding="utf-8")
            part2.write_text(json.dumps([response(2), response(4)]), encoding="utf-8")
            bad.write_text("{bad json", encoding="utf-8")

            report = write_combined_provider_response_chunks(
                input_glob=str(root / "raw.part*.json"),
                output_path=output,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["responses_collected"], 3)
            self.assertEqual(report["summary"]["duplicate_response_ids"], 1)
            self.assertEqual(report["summary"]["invalid_chunk_files"], 1)
            self.assertEqual([row["id"] for row in json.loads(output.read_text(encoding="utf-8"))["responses"]], [1, 2, 4])


if __name__ == "__main__":
    unittest.main()
