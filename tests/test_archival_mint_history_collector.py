import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.collect_archival_mint_history import write_archival_mint_history_collection_report
from wallets.archival_mint_history_collector import build_archival_mint_history_collection_report


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
    }
    row.update(overrides)
    return row


def tx(slot, signature):
    return {
        "slot": slot,
        "transaction": {
            "slot": slot,
            "blockTime": 1234 + slot,
            "transaction": {"message": {"instructions": []}},
            "meta": {"innerInstructions": []},
        },
        "signature": signature,
    }


def tx_with_instructions(slot, signature, instructions):
    row = tx(slot, signature)
    row["transaction"]["transaction"]["message"]["instructions"] = instructions
    return row


def initialize_mint(mint="MintA"):
    return {
        "program": "spl-token",
        "parsed": {
            "type": "initializeMint2",
            "info": {
                "mint": mint,
                "decimals": 6,
            },
        },
    }


class FakeRpc:
    def __init__(self, signatures_by_mint, transactions_by_signature):
        self.signatures_by_mint = signatures_by_mint
        self.transactions_by_signature = transactions_by_signature
        self.calls = []
        self.failures = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "getSignaturesForAddress":
            mint = params[0]
            opts = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
            rows = list(self.signatures_by_mint.get(mint, []))
            before = opts.get("before")
            if before:
                index = next((idx for idx, row in enumerate(rows) if row.get("signature") == before), len(rows) - 1)
                rows = rows[index + 1 :]
            return rows[: int(opts.get("limit") or len(rows))]
        if method == "getTransaction":
            return self.transactions_by_signature.get(params[0])
        return None


class ArchivalMintHistoryCollectorTests(unittest.TestCase):
    def test_dry_run_prepares_mint_history_collection_targets(self):
        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            execute=False,
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_MINT_HISTORY_COLLECTION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["requirements_scanned"], 1)
        self.assertEqual(report["summary"]["mint_history_targets"], 1)
        self.assertEqual(report["summary"]["mint_histories_complete"], 0)
        self.assertEqual(report["targets"][0]["status"], "pending_mint_history_collection")
        self.assertEqual(report["targets"][0]["token_mint"], "MintA")

    def test_max_targets_limits_execute_scope_without_mutating_plan(self):
        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(token_requirements=[
                requirement(token_mint="MintA"),
                requirement(token_mint="MintB"),
                requirement(token_mint="MintC"),
            ]),
            execute=False,
            max_targets=2,
            generated_at=123.0,
        )

        self.assertEqual(report["target_limit"], 2)
        self.assertEqual(report["summary"]["requirements_available"], 3)
        self.assertEqual(report["summary"]["requirements_scanned"], 2)
        self.assertEqual([row["token_mint"] for row in report["targets"]], ["MintA", "MintB"])
        self.assertFalse(report["wallet_list_mutated"])

    def test_execute_marks_history_complete_only_when_signature_pagination_ends(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigNew", "slot": 150},
                    {"signature": "SigDecision", "slot": 100},
                    {"signature": "SigMint", "slot": 10},
                ]
            },
            transactions_by_signature={
                "SigDecision": tx(100, "SigDecision"),
                "SigMint": tx(10, "SigMint"),
            },
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=2,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["mint_histories_complete"], 1)
        self.assertEqual(report["summary"]["raw_transactions_preserved"], 2)
        self.assertEqual(report["targets"][0]["status"], "mint_history_complete_through_decision_slot")
        self.assertEqual(report["history_completeness"]["MintA"]["complete_through_slot"], 100)
        self.assertEqual(report["raw_transactions"][0]["token_mint"], "MintA")
        self.assertEqual(report["raw_transactions"][0]["source"], "archival_mint_history_collection")

    def test_execute_resumes_from_signature_checkpoint(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigNew", "slot": 150},
                    {"signature": "SigDecision", "slot": 100},
                    {"signature": "SigMint", "slot": 10},
                ]
            },
            transactions_by_signature={
                "SigDecision": tx(100, "SigDecision"),
                "SigMint": tx(10, "SigMint"),
            },
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=1,
            existing_signature_checkpoint={
                "MintA": {
                    "next_before": "SigNew",
                    "pagination_complete": False,
                    "signatures": [{"signature": "SigNew", "slot": 150}],
                }
            },
            generated_at=123.0,
        )

        signature_calls = [call for call in rpc.calls if call[0] == "getSignaturesForAddress"]
        self.assertEqual(signature_calls[0][1][1]["before"], "SigNew")
        self.assertEqual(report["summary"]["mint_histories_complete"], 1)
        self.assertEqual(report["targets"][0]["signatures_loaded_from_checkpoint"], 1)
        self.assertEqual(report["targets"][0]["signatures_fetched_this_run"], 2)
        self.assertTrue(report["signature_checkpoint"]["MintA"]["pagination_complete"])
        self.assertIsNone(report["signature_checkpoint"]["MintA"]["next_before"])

    def test_execute_blocks_when_page_limit_prevents_completeness_proof(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigNew", "slot": 150},
                    {"signature": "SigDecision", "slot": 100},
                ]
            },
            transactions_by_signature={"SigDecision": tx(100, "SigDecision")},
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=2,
            max_pages_per_mint=1,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["mint_histories_complete"], 0)
        self.assertEqual(report["summary"]["blocked_incomplete_history"], 1)
        self.assertEqual(report["targets"][0]["status"], "blocked_partial_mint_history")
        self.assertIn("signature_page_limit_reached", report["targets"][0]["block_reasons"])
        self.assertEqual(report["history_completeness"], {})

    def test_execute_allows_mint_initialization_boundary_before_decision_without_full_pagination(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigDecision", "slot": 100},
                    {"signature": "SigInit", "slot": 10},
                ]
            },
            transactions_by_signature={
                "SigDecision": tx(100, "SigDecision"),
                "SigInit": tx_with_instructions(10, "SigInit", [initialize_mint()]),
            },
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=2,
            max_pages_per_mint=1,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["mint_histories_complete"], 1)
        self.assertEqual(report["summary"]["raw_transactions_preserved"], 2)
        self.assertEqual(report["targets"][0]["status"], "mint_history_complete_through_decision_slot")
        self.assertEqual(report["targets"][0]["history_boundary"], "mint_initialization_detected")
        self.assertEqual(report["history_completeness"]["MintA"]["complete_through_slot"], 100)
        self.assertEqual(report["history_completeness"]["MintA"]["history_boundary"], "mint_initialization_detected")

    def test_execute_blocks_when_transaction_budget_would_truncate_decision_history(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigDecision", "slot": 100},
                    {"signature": "SigMint", "slot": 10},
                ]
            },
            transactions_by_signature={
                "SigDecision": tx(100, "SigDecision"),
                "SigMint": tx(10, "SigMint"),
            },
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=2,
            max_transactions_per_mint=1,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["mint_histories_complete"], 0)
        self.assertEqual(report["summary"]["blocked_incomplete_history"], 1)
        self.assertEqual(report["targets"][0]["status"], "blocked_partial_mint_history")
        self.assertIn("transaction_budget_exhausted", report["targets"][0]["block_reasons"])
        self.assertEqual(report["history_completeness"], {})

    def test_execute_blocks_when_transaction_fetches_are_missing(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigDecision", "slot": 100},
                    {"signature": "SigMint", "slot": 10},
                ]
            },
            transactions_by_signature={"SigMint": tx(10, "SigMint")},
        )

        report = build_archival_mint_history_collection_report(
            archival_supply_plan=plan(),
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=2,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["mint_histories_complete"], 0)
        self.assertEqual(report["summary"]["blocked_incomplete_history"], 1)
        self.assertEqual(report["targets"][0]["status"], "blocked_partial_mint_history")
        self.assertIn("missing_mint_transactions", report["targets"][0]["block_reasons"])
        self.assertEqual(report["history_completeness"], {})

    def test_writer_persists_report_raw_transactions_and_completeness(self):
        rpc = FakeRpc(
            signatures_by_mint={"MintA": [{"signature": "SigMint", "slot": 10}]},
            transactions_by_signature={"SigMint": tx(10, "SigMint")},
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            report_path = root / "report.json"
            raw_path = root / "raw.jsonl"
            completeness_path = root / "complete.json"
            checkpoint_path = root / "checkpoint.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")

            report = write_archival_mint_history_collection_report(
                plan_path=plan_path,
                report_path=report_path,
                raw_transactions_path=raw_path,
                completeness_path=completeness_path,
                signature_checkpoint_path=checkpoint_path,
                rpc=rpc,
                execute=True,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(raw_path.exists())
            self.assertTrue(completeness_path.exists())
            self.assertTrue(checkpoint_path.exists())
            self.assertEqual(report["summary"]["mint_histories_complete"], 1)
            self.assertEqual(json.loads(completeness_path.read_text(encoding="utf-8"))["MintA"]["complete_through_slot"], 100)
            self.assertTrue(json.loads(checkpoint_path.read_text(encoding="utf-8"))["MintA"]["pagination_complete"])
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8").strip())["signature"], "SigMint")

    def test_writer_preserves_prior_completeness_and_raw_transactions_across_bounded_runs(self):
        rpc = FakeRpc(
            signatures_by_mint={"MintA": [{"signature": "SigMint", "slot": 10}]},
            transactions_by_signature={"SigMint": tx(10, "SigMint")},
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            report_path = root / "report.json"
            raw_path = root / "raw.jsonl"
            completeness_path = root / "complete.json"
            checkpoint_path = root / "checkpoint.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            completeness_path.write_text(
                json.dumps({"MintExisting": {"complete_through_slot": 50}}),
                encoding="utf-8",
            )
            raw_path.write_text(json.dumps({"signature": "SigExisting", "token_mint": "MintExisting"}) + "\n", encoding="utf-8")

            write_archival_mint_history_collection_report(
                plan_path=plan_path,
                report_path=report_path,
                raw_transactions_path=raw_path,
                completeness_path=completeness_path,
                signature_checkpoint_path=checkpoint_path,
                rpc=rpc,
                execute=True,
                generated_at=123.0,
            )

            completeness = json.loads(completeness_path.read_text(encoding="utf-8"))
            raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(completeness["MintExisting"]["complete_through_slot"], 50)
            self.assertEqual(completeness["MintA"]["complete_through_slot"], 100)
            self.assertEqual([row["signature"] for row in raw_rows], ["SigExisting", "SigMint"])


if __name__ == "__main__":
    unittest.main()
