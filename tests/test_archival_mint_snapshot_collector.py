import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.collect_archival_mint_supply_snapshots import write_archival_mint_snapshot_collection_report
from wallets.archival_mint_snapshot_collector import build_archival_mint_snapshot_collection_report


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


def candidate(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "transaction_signature": "SigA",
        "decision_slot": 100,
        "decision_block_time": 1000,
        "timestamp": 1000,
    }
    row.update(overrides)
    return row


def rpc_response(slot=90, supply="1000000000", decimals=6):
    return {
        "jsonrpc": "2.0",
        "result": {
            "context": {"slot": slot},
            "value": {
                "data": {
                    "program": "spl-token",
                    "parsed": {
                        "type": "mint",
                        "info": {
                            "supply": supply,
                            "decimals": decimals,
                        },
                    },
                }
            },
        },
    }


class ArchivalMintSnapshotCollectorTests(unittest.TestCase):
    def test_dry_run_builds_provider_request_manifest_without_fetching(self):
        report = build_archival_mint_snapshot_collection_report(
            archival_supply_plan=plan(),
            execute=False,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_SUPPLY_SNAPSHOT_COLLECTION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["requirements_scanned"], 1)
        self.assertEqual(report["summary"]["requests_prepared"], 1)
        self.assertEqual(report["summary"]["snapshots_collected"], 0)
        self.assertEqual(report["requests"][0]["token_mint"], "MintA")
        self.assertEqual(report["requests"][0]["max_acceptable_snapshot_slot"], 100)
        self.assertEqual(report["requests"][0]["status"], "pending_archival_provider")
        self.assertEqual(report["snapshots"], [])

    def test_dry_run_prepares_row_level_decision_slot_requests_when_candidates_exist(self):
        report = build_archival_mint_snapshot_collection_report(
            archival_supply_plan=plan(
                candidate_rows=[
                    candidate(wallet="WalletA", transaction_signature="SigA", decision_slot=100),
                    candidate(wallet="WalletB", transaction_signature="SigB", decision_slot=120),
                    candidate(wallet="WalletC", transaction_signature="SigC", decision_slot=120),
                ]
            ),
            execute=False,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["requests_prepared"], 2)
        self.assertEqual(report["summary"]["tokens_affected"], 1)
        self.assertEqual(report["requests"][0]["token_mint"], "MintA")
        self.assertEqual(report["requests"][0]["max_acceptable_snapshot_slot"], 100)
        self.assertEqual(report["requests"][0]["row_count"], 1)
        self.assertEqual(report["requests"][1]["max_acceptable_snapshot_slot"], 120)
        self.assertEqual(report["requests"][1]["row_count"], 2)
        self.assertEqual(report["requests"][1]["wallet_count"], 2)

    def test_row_level_requests_keep_audit_references_and_stable_evidence_key(self):
        report = build_archival_mint_snapshot_collection_report(
            archival_supply_plan=plan(
                candidate_rows=[
                    candidate(wallet="WalletA", transaction_signature="SigA", decision_slot=120, decision_block_time=1200),
                    candidate(wallet="WalletB", transaction_signature="SigB", decision_slot=120, decision_block_time=1200),
                ]
            ),
            execute=False,
            generated_at=123.0,
        )

        request = report["requests"][0]
        self.assertEqual(request["requested_snapshot_slot"], 120)
        self.assertEqual(request["requested_snapshot_time"], 1200)
        self.assertEqual(request["wallets"], ["WalletA", "WalletB"])
        self.assertEqual(request["transaction_signatures"], ["SigA", "SigB"])
        self.assertEqual(request["candidate_references"][0]["wallet"], "WalletA")
        self.assertEqual(request["candidate_references"][0]["decision_slot"], 120)
        self.assertEqual(request["candidate_references"][0]["decision_time"], 1200)
        self.assertTrue(request["evidence_key"].startswith("mint-snapshot:MintA:120:"))
        self.assertEqual(report["summary"]["requests_missing_audit_references"], 0)

    def test_execute_accepts_only_snapshot_at_or_before_decision_slot(self):
        calls = []

        def rpc_post(_url, payload, _timeout):
            calls.append(payload)
            return rpc_response(slot=95)

        report = build_archival_mint_snapshot_collection_report(
            archival_supply_plan=plan(),
            execute=True,
            rpc_url="https://archive.example",
            rpc_post=rpc_post,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_collected"], 1)
        self.assertEqual(report["summary"]["blocked_too_new_snapshots"], 0)
        self.assertEqual(report["requests"][0]["status"], "archival_snapshot_collected")
        self.assertEqual(report["snapshots"][0]["token_mint"], "MintA")
        self.assertEqual(report["snapshots"][0]["slot"], 95)
        self.assertEqual(report["snapshots"][0]["source"], "archival_rpc_getAccountInfo")
        self.assertEqual(calls[0]["method"], "getAccountInfo")
        self.assertEqual(calls[0]["params"][0], "MintA")

    def test_execute_rejects_standard_current_rpc_snapshot_after_decision_slot(self):
        report = build_archival_mint_snapshot_collection_report(
            archival_supply_plan=plan(),
            execute=True,
            rpc_url="https://standard-rpc.example",
            rpc_post=lambda _url, _payload, _timeout: rpc_response(slot=500),
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_collected"], 0)
        self.assertEqual(report["summary"]["blocked_too_new_snapshots"], 1)
        self.assertEqual(report["requests"][0]["status"], "blocked_snapshot_after_decision_slot")
        self.assertEqual(report["snapshots"], [])
        self.assertIn("snapshot_slot_after_decision_slot", report["requests"][0]["block_reasons"])

    def test_writer_persists_report_and_snapshot_jsonl(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "archival_supply_recovery_plan.json"
            report_path = root / "collection_report.json"
            snapshots_path = root / "archival_mint_supply_snapshots.jsonl"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")

            report = write_archival_mint_snapshot_collection_report(
                plan_path=plan_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                execute=True,
                rpc_url="https://archive.example",
                rpc_post=lambda _url, _payload, _timeout: rpc_response(slot=95),
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(snapshots_path.exists())
            self.assertEqual(report["summary"]["snapshots_collected"], 1)
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintA")


if __name__ == "__main__":
    unittest.main()
