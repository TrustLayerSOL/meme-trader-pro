import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.collect_post_decision_supply_transactions import write_post_decision_supply_transaction_collection_report
from wallets.post_decision_transaction_body_collector import build_post_decision_supply_transaction_collection_report


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


def current_snapshot(**overrides):
    row = {
        "token_mint": "MintA",
        "slot": 200,
        "raw_supply": "1000000000",
        "decimals": 6,
        "collected_at": 123.0,
        "source": "current_getTokenSupply",
    }
    row.update(overrides)
    return row


def checkpoint(**overrides):
    row = {
        "MintA": {
            "token_mint": "MintA",
            "pagination_complete": False,
            "next_before": "SigDecision",
            "signatures": [
                {"signature": "SigOldHead", "slot": 150},
                {"signature": "SigDecision", "slot": 100},
            ],
            "signatures_fetched_total": 2,
            "oldest_signature_slot": 100,
            "newest_signature_slot": 150,
        }
    }
    row.update(overrides)
    return row


def tx(slot, signature):
    return {
        "slot": slot,
        "signature": signature,
        "transaction": {
            "slot": slot,
            "transaction": {"message": {"instructions": []}},
            "meta": {"innerInstructions": []},
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


class FakeBatchRpc(FakeRpc):
    def __init__(self, signatures_by_mint, transactions_by_signature):
        super().__init__(signatures_by_mint, transactions_by_signature)
        self.batch_calls = []

    def batch_call(self, calls):
        self.batch_calls.append(calls)
        results = []
        for method, params in calls:
            self.calls.append((method, params))
            if method == "getTransaction":
                results.append(self.transactions_by_signature.get(params[0]))
            else:
                results.append(None)
        return results


class PostDecisionTransactionBodyCollectorTests(unittest.TestCase):
    def test_max_targets_prioritizes_low_missing_post_decision_body_targets(self):
        multi_plan = plan(token_requirements=[
            requirement(token_mint="MintA", earliest_decision_slot=100),
            requirement(token_mint="MintB", earliest_decision_slot=100),
        ])
        checkpoints = checkpoint()
        checkpoints["MintA"]["signatures"] = [
            {"signature": f"SigA{idx}", "slot": 180 - idx} for idx in range(5)
        ] + [{"signature": "SigADecision", "slot": 100}]
        checkpoints["MintB"] = {
            "token_mint": "MintB",
            "signatures": [
                {"signature": "SigBNew", "slot": 180},
                {"signature": "SigBDecision", "slot": 100},
            ],
        }

        report = build_post_decision_supply_transaction_collection_report(
            archival_supply_plan=multi_plan,
            current_supply_snapshots=[
                current_snapshot(token_mint="MintA"),
                current_snapshot(token_mint="MintB"),
            ],
            signature_checkpoint=checkpoints,
            raw_transactions=[],
            execute=False,
            max_targets=1,
            generated_at=130.0,
        )

        self.assertEqual(report["targets"][0]["token_mint"], "MintB")

    def test_execute_refreshes_checkpoint_to_head_and_fetches_missing_post_decision_bodies(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigAfterCurrent", "slot": 240},
                    {"signature": "SigNew", "slot": 180},
                    {"signature": "SigOldHead", "slot": 150},
                    {"signature": "SigMid", "slot": 140},
                ]
            },
            transactions_by_signature={
                "SigNew": tx(180, "SigNew"),
                "SigMid": tx(140, "SigMid"),
                "SigOldHead": tx(150, "SigOldHead"),
            },
        )

        report = build_post_decision_supply_transaction_collection_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[tx(150, "SigOldHead")],
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=2,
            max_transactions_per_mint=10,
            generated_at=130.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["targets_refreshed"], 1)
        self.assertEqual(report["summary"]["raw_transactions_preserved"], 2)
        self.assertEqual(report["targets"][0]["status"], "post_decision_transaction_bodies_collected")
        self.assertEqual(report["targets"][0]["missing_post_decision_transactions_after"], 0)
        self.assertEqual(report["signature_checkpoint"]["MintA"]["checkpoint_collected_at"], 130.0)
        self.assertEqual(
            {row["signature"] for row in report["raw_transactions"]},
            {"SigNew", "SigMid"},
        )

    def test_execute_uses_batch_transaction_fetch_when_rpc_supports_it(self):
        rpc = FakeBatchRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigNew2", "slot": 190},
                    {"signature": "SigNew1", "slot": 180},
                    {"signature": "SigOldHead", "slot": 150},
                ]
            },
            transactions_by_signature={
                "SigNew1": tx(180, "SigNew1"),
                "SigNew2": tx(190, "SigNew2"),
            },
        )

        report = build_post_decision_supply_transaction_collection_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[tx(150, "SigOldHead")],
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=1,
            max_transactions_per_mint=10,
            generated_at=130.0,
        )

        self.assertEqual(report["summary"]["raw_transactions_preserved"], 2)
        self.assertEqual(report["targets"][0]["missing_post_decision_transactions_after"], 0)
        self.assertEqual(len(rpc.batch_calls), 1)
        self.assertEqual([call[0] for call in rpc.batch_calls[0]], ["getTransaction", "getTransaction"])

    def test_execute_uses_existing_checkpoint_when_it_already_spans_current_snapshot(self):
        rpc = FakeBatchRpc(
            signatures_by_mint={"MintA": []},
            transactions_by_signature={
                "SigNew": tx(180, "SigNew"),
            },
        )
        existing_checkpoint = checkpoint()
        existing_checkpoint["MintA"]["signatures"] = [
            {"signature": "SigAfterCurrent", "slot": 240},
            {"signature": "SigNew", "slot": 180},
            {"signature": "SigOldHead", "slot": 150},
            {"signature": "SigDecision", "slot": 100},
        ]
        existing_checkpoint["MintA"]["oldest_signature_slot"] = 100
        existing_checkpoint["MintA"]["newest_signature_slot"] = 240

        report = build_post_decision_supply_transaction_collection_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot(slot=200)],
            signature_checkpoint=existing_checkpoint,
            raw_transactions=[tx(150, "SigOldHead")],
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=1,
            max_transactions_per_mint=10,
            generated_at=130.0,
        )

        self.assertEqual(report["summary"]["raw_transactions_preserved"], 1)
        self.assertEqual(report["targets"][0]["status"], "post_decision_transaction_bodies_collected")
        self.assertEqual(report["targets"][0]["missing_post_decision_transactions_after"], 0)
        self.assertEqual([call[0] for call in rpc.calls], ["getTransaction"])
        self.assertEqual(len(rpc.batch_calls), 1)

    def test_blocks_checkpoint_refresh_when_head_page_does_not_overlap_existing_checkpoint(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigAfterCurrent", "slot": 240},
                    {"signature": "SigNew", "slot": 180},
                ]
            },
            transactions_by_signature={"SigNew": tx(180, "SigNew")},
        )

        report = build_post_decision_supply_transaction_collection_report(
            archival_supply_plan=plan(),
            current_supply_snapshots=[current_snapshot()],
            signature_checkpoint=checkpoint(),
            raw_transactions=[],
            rpc=rpc,
            execute=True,
            signature_page_limit=10,
            max_pages_per_mint=1,
            max_transactions_per_mint=10,
            generated_at=130.0,
        )

        self.assertEqual(report["summary"]["targets_refreshed"], 0)
        self.assertEqual(report["summary"]["blocked_incomplete_refresh"], 1)
        self.assertEqual(report["targets"][0]["status"], "blocked_incomplete_head_refresh")
        self.assertNotIn("checkpoint_collected_at", report["signature_checkpoint"]["MintA"])
        self.assertEqual(report["raw_transactions"], [])

    def test_writer_merges_raw_rows_and_persists_refreshed_checkpoint(self):
        rpc = FakeRpc(
            signatures_by_mint={
                "MintA": [
                    {"signature": "SigNew", "slot": 180},
                    {"signature": "SigOldHead", "slot": 150},
                ]
            },
            transactions_by_signature={"SigNew": tx(180, "SigNew")},
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            current_path = root / "current.jsonl"
            checkpoint_path = root / "checkpoint.json"
            raw_path = root / "raw.jsonl"
            report_path = root / "report.json"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")
            current_path.write_text(json.dumps(current_snapshot()) + "\n", encoding="utf-8")
            checkpoint_path.write_text(json.dumps(checkpoint()), encoding="utf-8")
            raw_path.write_text(json.dumps(tx(150, "SigOldHead")) + "\n", encoding="utf-8")

            report = write_post_decision_supply_transaction_collection_report(
                plan_path=plan_path,
                current_supply_snapshots_path=current_path,
                signature_checkpoint_path=checkpoint_path,
                raw_transactions_path=raw_path,
                existing_raw_glob=None,
                report_path=report_path,
                rpc=rpc,
                execute=True,
                signature_page_limit=10,
                max_pages_per_mint=1,
                max_transactions_per_mint=10,
                generated_at=130.0,
            )

            self.assertEqual(report["summary"]["raw_transactions_preserved"], 1)
            raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["signature"] for row in raw_rows}, {"SigOldHead", "SigNew"})
            saved_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_checkpoint["MintA"]["checkpoint_collected_at"], 130.0)
            self.assertTrue(report_path.exists())


if __name__ == "__main__":
    unittest.main()
