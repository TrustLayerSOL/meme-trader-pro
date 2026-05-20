import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_focused_manual_supply_research import (
    import_focused_manual_supply_template,
    write_focused_manual_supply_packet,
)


def request_bundle():
    return {
        "requests": [
            {
                "token_mint": "MintA",
                "max_acceptable_snapshot_slot": 120,
                "requested_snapshot_slot": 120,
                "requested_snapshot_time": 1000,
                "jsonrpc_payload": {"id": 1, "params": ["MintA", {"encoding": "jsonParsed"}]},
            }
        ]
    }


class BuildFocusedManualSupplyResearchTests(unittest.TestCase):
    def test_writer_reads_request_bundle_and_exports_packet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            output_dir = root / "manual"
            bundle_path.write_text(json.dumps(request_bundle()), encoding="utf-8")

            report = write_focused_manual_supply_packet(
                request_bundle_path=bundle_path,
                output_dir=output_dir,
                limit=10,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["requests_exported"], 1)
            self.assertTrue((output_dir / "focused_manual_supply_research_packet.csv").exists())
            self.assertTrue((output_dir / "focused_manual_supply_template.csv").exists())

    def test_import_wrapper_reads_request_bundle_and_writes_snapshot_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            output_dir = root / "manual"
            csv_path = root / "manual.csv"
            bundle_path.write_text(json.dumps(request_bundle()), encoding="utf-8")
            csv_path.write_text(
                "request_id,token_mint,max_acceptable_snapshot_slot,verified_supply,decimals,response_slot,evidence_source,evidence_url,confidence_tier,notes\n"
                "1,MintA,120,1000000,6,119,Solscan,https://solscan.io/token/MintA,A_FULL_REPLAY_SAFE,Verified before slot\n",
                encoding="utf-8",
            )

            report = import_focused_manual_supply_template(
                csv_path=csv_path,
                request_bundle_path=bundle_path,
                output_dir=output_dir,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["tier_a_snapshot_rows"], 1)
            self.assertTrue((output_dir / "focused_manual_supply_snapshots.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
