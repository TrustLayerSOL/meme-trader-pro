import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.export_archival_supply_proof_readiness import write_archival_supply_proof_exports
from wallets.archival_supply_proof_exports import build_archival_supply_proof_export


def request_bundle():
    return {
        "mode": "ARCHIVAL_MINT_SNAPSHOT_REQUEST_BUNDLE_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {"requests_bundled": 3, "request_chunk_count": 1, "target_tokens": 2},
        "requests": [
            {"evidence_key": "KeyA", "token_mint": "MintA", "max_acceptable_snapshot_slot": 100},
            {"evidence_key": "KeyB", "token_mint": "MintB", "max_acceptable_snapshot_slot": 200},
            {"evidence_key": "KeyC", "token_mint": "MintC", "max_acceptable_snapshot_slot": 300},
        ],
    }


def response_import():
    return {
        "mode": "ARCHIVAL_MINT_SNAPSHOT_RESPONSE_IMPORT_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {"raw_responses_scanned": 2, "snapshots_imported": 1, "blocked_missing_response": 1},
        "import_rows": [
            {
                "evidence_key": "KeyA",
                "token_mint": "MintA",
                "request_id": "1",
                "status": "archival_snapshot_imported",
                "requested_snapshot_slot": 100,
                "requested_snapshot_time": 1000,
                "provider_response_slot": 90,
                "decision_time_safe": True,
            },
            {
                "evidence_key": "KeyB",
                "token_mint": "MintB",
                "request_id": "2",
                "status": "blocked_snapshot_after_decision_slot",
                "block_reasons": ["snapshot_slot_after_decision_slot"],
                "requested_snapshot_slot": 200,
                "provider_response_slot": 250,
                "decision_time_safe": False,
            },
            {
                "evidence_key": "KeyC",
                "token_mint": "MintC",
                "request_id": "3",
                "status": "blocked_missing_response",
                "block_reasons": ["missing_provider_response"],
                "requested_snapshot_slot": 300,
                "decision_time_safe": False,
            },
        ],
    }


def archival_supply_evidence():
    return {
        "mode": "ARCHIVAL_SUPPLY_EVIDENCE_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {"supply_recovered_records": 1, "blocked_missing_snapshot_records": 1},
        "records": [
            {
                "evidence_key": "KeyA",
                "wallet": "WalletA",
                "token_mint": "MintA",
                "transaction_signature": "SigA",
                "decision_slot": 100,
                "snapshot_slot": 90,
                "raw_supply": "1000000",
                "ui_supply": 1.0,
                "decimals": 6,
                "status": "archival_supply_recovered",
                "source": "saved_archival_rpc_getAccountInfo_response",
                "decision_time_safe": True,
            },
            {
                "evidence_key": "KeyB",
                "wallet": "WalletB",
                "token_mint": "MintB",
                "transaction_signature": "SigB",
                "decision_slot": 200,
                "status": "blocked_snapshot_after_decision_slot",
                "block_reasons": ["snapshot_slot_after_decision_slot"],
                "decision_time_safe": False,
            },
        ],
    }


def score_ready_context():
    return {
        "mode": "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {"score_ready_records": 2, "near_score_ready_records": 1},
        "records": [
            {
                "wallet": "WalletA",
                "token_mint": "MintA",
                "transaction_signature": "SigA",
                "readiness_status": "score_ready",
                "supply_source": "archival_supply_evidence",
            },
            {
                "wallet": "WalletPrior",
                "token_mint": "MintPrior",
                "transaction_signature": "SigPrior",
                "readiness_status": "score_ready",
                "supply_source": "prior_snapshot",
            },
        ],
    }


def proof_readiness():
    return {
        "mode": "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY",
        "live_execution_locked": True,
        "summary": {"proof_readiness_pct": 5, "fillable_rate": 52},
        "reduction_queue": [
            {"priority": 1, "category": "archival_supply_evidence", "gap": 2},
            {"priority": 2, "category": "fillable_rate", "gap": 18},
        ],
    }


class ArchivalSupplyProofExportTests(unittest.TestCase):
    def test_builds_audit_summary_and_output_tables(self):
        report = build_archival_supply_proof_export(
            request_bundle_report=request_bundle(),
            response_import_report=response_import(),
            archival_supply_evidence_report=archival_supply_evidence(),
            score_ready_market_context_report=score_ready_context(),
            proof_readiness_report=proof_readiness(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_SUPPLY_PROOF_EXPORT_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertEqual(report["summary"]["total_request_rows"], 3)
        self.assertEqual(report["summary"]["imported_provider_responses"], 2)
        self.assertEqual(report["summary"]["matched_rows"], 2)
        self.assertEqual(report["summary"]["valid_archival_supply_rows"], 1)
        self.assertEqual(report["summary"]["rejected_or_quarantined_rows"], 2)
        self.assertEqual(report["summary"]["rows_upgraded_from_near_score_ready_to_score_ready"], 1)
        self.assertEqual(report["summary"]["updated_proof_readiness_pct"], 5)
        self.assertEqual(report["valid_evidence_rows"][0]["evidence_key"], "KeyA")
        self.assertEqual(report["rejected_rows"][0]["status"], "blocked_snapshot_after_decision_slot")
        self.assertIn("Proof Readiness", report["markdown"])

    def test_writer_persists_markdown_csv_and_json_outputs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "request_bundle": root / "request_bundle.json",
                "response_import": root / "response_import.json",
                "archival_supply_evidence": root / "archival_supply_evidence.json",
                "score_ready": root / "score_ready.json",
                "proof": root / "proof.json",
            }
            paths["request_bundle"].write_text(json.dumps(request_bundle()), encoding="utf-8")
            paths["response_import"].write_text(json.dumps(response_import()), encoding="utf-8")
            paths["archival_supply_evidence"].write_text(json.dumps(archival_supply_evidence()), encoding="utf-8")
            paths["score_ready"].write_text(json.dumps(score_ready_context()), encoding="utf-8")
            paths["proof"].write_text(json.dumps(proof_readiness()), encoding="utf-8")

            report = write_archival_supply_proof_exports(
                request_bundle_path=paths["request_bundle"],
                response_import_path=paths["response_import"],
                archival_supply_evidence_path=paths["archival_supply_evidence"],
                score_ready_market_context_path=paths["score_ready"],
                proof_readiness_path=paths["proof"],
                markdown_path=root / "proof.md",
                evidence_csv_path=root / "evidence.csv",
                rejected_csv_path=root / "rejected.csv",
                summary_json_path=root / "summary.json",
                generated_at=123.0,
            )

            self.assertTrue((root / "proof.md").exists())
            self.assertTrue((root / "evidence.csv").exists())
            self.assertTrue((root / "rejected.csv").exists())
            self.assertTrue((root / "summary.json").exists())
            self.assertEqual(report["summary"]["valid_archival_supply_rows"], 1)
            with (root / "evidence.csv").open(encoding="utf-8") as handle:
                evidence_rows = list(csv.DictReader(handle))
            with (root / "rejected.csv").open(encoding="utf-8") as handle:
                rejected_rows = list(csv.DictReader(handle))
            self.assertEqual(evidence_rows[0]["evidence_key"], "KeyA")
            self.assertEqual(rejected_rows[0]["status"], "blocked_snapshot_after_decision_slot")
            saved_summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_summary["summary"]["updated_proof_readiness_pct"], 5)


if __name__ == "__main__":
    unittest.main()
