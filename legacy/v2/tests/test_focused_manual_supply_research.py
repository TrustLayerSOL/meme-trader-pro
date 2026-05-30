import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wallets.focused_manual_supply_research import (
    build_focused_manual_supply_packet,
    import_focused_manual_supply_evidence,
)


def request_bundle():
    return {
        "review_only": True,
        "live_execution_locked": True,
        "summary": {"requests_bundled": 2, "target_tokens": 1},
        "requests": [
            {
                "token_mint": "MintA",
                "latest_decision_slot": 120,
                "latest_decision_time": 1000,
                "max_acceptable_snapshot_slot": 120,
                "requested_snapshot_slot": 120,
                "requested_snapshot_time": 1000,
                "row_count": 2,
                "wallet_count": 2,
                "wallets": ["WalletA", "WalletB"],
                "transaction_signatures": ["SigA", "SigB"],
                "jsonrpc_payload": {"id": 7, "params": ["MintA", {"encoding": "jsonParsed"}]},
            },
            {
                "token_mint": "MintB",
                "latest_decision_slot": 200,
                "latest_decision_time": 2000,
                "max_acceptable_snapshot_slot": 200,
                "requested_snapshot_slot": 200,
                "requested_snapshot_time": 2000,
                "row_count": 1,
                "wallet_count": 1,
                "wallets": ["WalletC"],
                "transaction_signatures": ["SigC"],
                "jsonrpc_payload": {"id": 8, "params": ["MintB", {"encoding": "jsonParsed"}]},
            },
        ],
    }


class FocusedManualSupplyResearchTests(unittest.TestCase):
    def test_exports_focused_manual_supply_packet_and_template(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            packet = build_focused_manual_supply_packet(
                request_bundle_report=request_bundle(),
                output_dir=output_dir,
                limit=1,
                generated_at=123.0,
            )

            self.assertTrue(packet["review_only"])
            self.assertTrue(packet["live_execution_locked"])
            self.assertFalse(packet["wallet_list_apply_allowed"])
            self.assertEqual(packet["summary"]["requests_exported"], 1)
            self.assertTrue((output_dir / "focused_manual_supply_research_packet.csv").exists())
            self.assertTrue((output_dir / "focused_manual_supply_template.csv").exists())
            with (output_dir / "focused_manual_supply_template.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["request_id"], "7")
            self.assertEqual(rows[0]["token_mint"], "MintA")
            self.assertEqual(rows[0]["max_acceptable_snapshot_slot"], "120")

    def test_imports_only_tier_a_manual_supply_as_replay_safe_snapshot(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = output_dir / "manual_supply.csv"
            fieldnames = [
                "request_id",
                "token_mint",
                "max_acceptable_snapshot_slot",
                "raw_supply_base_units",
                "display_supply_optional",
                "decimals",
                "response_slot",
                "evidence_source",
                "evidence_url",
                "confidence_tier",
                "notes",
            ]
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "request_id": "7",
                        "token_mint": "MintA",
                        "max_acceptable_snapshot_slot": "120",
                        "raw_supply_base_units": "1000000",
                        "display_supply_optional": "1",
                        "decimals": "6",
                        "response_slot": "120",
                        "evidence_source": "Solscan historical export",
                        "evidence_url": "https://solscan.io/token/MintA",
                        "confidence_tier": "A_FULL_REPLAY_SAFE",
                        "notes": "Historical source proves raw base-unit supply at the exact decision slot.",
                    }
                )
                writer.writerow(
                    {
                        "request_id": "8",
                        "token_mint": "MintB",
                        "max_acceptable_snapshot_slot": "200",
                        "raw_supply_base_units": "2000000",
                        "display_supply_optional": "2",
                        "decimals": "6",
                        "response_slot": "205",
                        "evidence_source": "Solscan historical export",
                        "evidence_url": "https://solscan.io/token/MintB",
                        "confidence_tier": "A_FULL_REPLAY_SAFE",
                        "notes": "Too new and must be rejected.",
                    }
                )
                writer.writerow(
                    {
                        "request_id": "8",
                        "token_mint": "MintB",
                        "max_acceptable_snapshot_slot": "200",
                        "raw_supply_base_units": "2000000",
                        "display_supply_optional": "2",
                        "decimals": "6",
                        "response_slot": "199",
                        "evidence_source": "Dexscreener chart",
                        "evidence_url": "https://dexscreener.com/solana/MintB",
                        "confidence_tier": "C_SUGGESTIVE",
                        "notes": "Partial review note only.",
                    }
                )

            report = import_focused_manual_supply_evidence(
                csv_path,
                request_bundle_report=request_bundle(),
                output_dir=output_dir,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["rows_scanned"], 3)
            self.assertEqual(report["summary"]["accepted_rows"], 2)
            self.assertEqual(report["summary"]["rejected_rows"], 1)
            self.assertEqual(report["summary"]["tier_a_snapshot_rows"], 1)
            snapshots = [
                json.loads(line)
                for line in (output_dir / "focused_manual_supply_snapshots.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["token_mint"], "MintA")
            self.assertEqual(snapshots[0]["slot"], 120)
            self.assertEqual(snapshots[0]["raw_supply"], "1000000")
            self.assertEqual(snapshots[0]["source"], "focused_manual_supply_research")
            self.assertTrue(snapshots[0]["decision_time_safe"])

    def test_rejects_legacy_display_supply_and_decimal_slot_values(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            csv_path = output_dir / "manual_supply.csv"
            csv_path.write_text(
                "request_id,token_mint,max_acceptable_snapshot_slot,verified_supply,decimals,response_slot,evidence_source,evidence_url,confidence_tier,notes\n"
                "7,MintA,120,1.0,6,119.9,Solscan,https://solscan.io/token/MintA,A_FULL_REPLAY_SAFE,Ambiguous display supply\n",
                encoding="utf-8",
            )

            report = import_focused_manual_supply_evidence(
                csv_path,
                request_bundle_report=request_bundle(),
                output_dir=output_dir,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["accepted_rows"], 0)
            self.assertEqual(report["summary"]["rejected_rows"], 1)
            reasons = report["rejected_rows"][0]["rejection_reasons"]
            self.assertIn("legacy_verified_supply_not_allowed_use_raw_supply_base_units", reasons)
            self.assertIn("missing_or_invalid_response_slot", reasons)


if __name__ == "__main__":
    unittest.main()
