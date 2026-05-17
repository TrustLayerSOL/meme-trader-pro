import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.reconstruct_archival_mint_supply import write_archival_mint_supply_reconstruction_report
from wallets.archival_mint_supply_reconstruction import build_archival_mint_supply_reconstruction_report


def requirement(**overrides):
    row = {
        "token_mint": "MintA",
        "status": "ready_for_archival_supply_fetch",
        "earliest_decision_slot": 100,
        "latest_decision_slot": 120,
        "row_count": 2,
    }
    row.update(overrides)
    return row


def plan(**overrides):
    row = {
        "mode": "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY",
        "token_requirements": [requirement()],
        "candidate_rows": [],
    }
    row.update(overrides)
    return row


def tx(slot, signature, instructions):
    return {
        "signature": signature,
        "source": "complete_mint_history_fixture",
        "transaction": {
            "slot": slot,
            "blockTime": 1234 + slot,
            "transaction": {
                "message": {
                    "instructions": instructions,
                },
            },
            "meta": {
                "innerInstructions": [],
            },
        },
    }


def mint_to(amount, decimals=6, mint="MintA"):
    return {
        "program": "spl-token",
        "parsed": {
            "type": "mintToChecked",
            "info": {
                "mint": mint,
                "tokenAmount": {
                    "amount": str(amount),
                    "decimals": decimals,
                },
            },
        },
    }


def burn(amount, decimals=6, mint="MintA"):
    return {
        "program": "spl-token",
        "parsed": {
            "type": "burnChecked",
            "info": {
                "mint": mint,
                "tokenAmount": {
                    "amount": str(amount),
                    "decimals": decimals,
                },
            },
        },
    }


class ArchivalMintSupplyReconstructionTests(unittest.TestCase):
    def test_reconstructs_supply_only_when_mint_history_is_complete_through_decision_slot(self):
        report = build_archival_mint_supply_reconstruction_report(
            archival_supply_plan=plan(),
            raw_transactions=[
                tx(10, "SigMint", [mint_to(1_000_000_000)]),
                tx(20, "SigBurn", [burn(100_000_000)]),
            ],
            history_completeness={"MintA": {"complete_through_slot": 120, "source": "fixture_complete_history"}},
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_SUPPLY_RECONSTRUCTION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["snapshots_reconstructed"], 1)
        self.assertEqual(report["summary"]["blocked_incomplete_history"], 0)
        self.assertEqual(report["snapshots"][0]["token_mint"], "MintA")
        self.assertEqual(report["snapshots"][0]["raw_supply"], "900000000")
        self.assertEqual(report["snapshots"][0]["decimals"], 6)
        self.assertEqual(report["snapshots"][0]["source"], "mint_burn_history_reconstruction")
        self.assertTrue(report["snapshots"][0]["decision_time_safe"])

    def test_blocks_local_transaction_artifacts_when_mint_history_completeness_is_unknown(self):
        report = build_archival_mint_supply_reconstruction_report(
            archival_supply_plan=plan(),
            raw_transactions=[tx(10, "SigMint", [mint_to(1_000_000_000)])],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_reconstructed"], 0)
        self.assertEqual(report["summary"]["blocked_incomplete_history"], 1)
        self.assertEqual(report["requirements"][0]["status"], "blocked_incomplete_mint_history")
        self.assertIn("mint_history_not_complete_through_decision_slot", report["requirements"][0]["block_reasons"])
        self.assertEqual(report["snapshots"], [])

    def test_writer_persists_report_and_compatible_snapshot_jsonl(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "archival_supply_recovery_plan.json"
            raw_path = root / "raw.jsonl"
            completeness_path = root / "completeness.json"
            report_path = root / "reconstruction_report.json"
            snapshots_path = root / "reconstruction_snapshots.jsonl"

            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            raw_path.write_text(json.dumps(tx(10, "SigMint", [mint_to(1_000_000_000)])) + "\n", encoding="utf-8")
            completeness_path.write_text(json.dumps({"MintA": {"complete_through_slot": 120}}), encoding="utf-8")

            report = write_archival_mint_supply_reconstruction_report(
                plan_path=plan_path,
                raw_transaction_paths=[raw_path],
                completeness_path=completeness_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(snapshots_path.exists())
            self.assertEqual(report["summary"]["snapshots_reconstructed"], 1)
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintA")


if __name__ == "__main__":
    unittest.main()
