import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.collect_current_mint_supply_snapshots import (
    build_current_mint_supply_snapshots,
    write_current_mint_supply_snapshots,
)


def plan():
    return {
        "token_requirements": [
            {"token_mint": "MintA", "status": "ready_for_archival_supply_fetch"},
            {"token_mint": "MintB", "status": "ready_for_archival_supply_fetch"},
            {"token_mint": "MintA", "status": "ready_for_archival_supply_fetch"},
            {"token_mint": "MintSkip", "status": "blocked"},
        ]
    }


class FakeRpc:
    def __init__(self):
        self.calls = []

    def get_token_supply(self, mint):
        self.calls.append(mint)
        if mint == "MintB":
            return {"error": {"message": "not found"}}
        return {
            "result": {
                "context": {"slot": 200},
                "value": {
                    "amount": "1000000000",
                    "decimals": 6,
                    "uiAmount": 1000.0,
                    "uiAmountString": "1000",
                },
            }
        }


class FlakyRpc:
    def __init__(self):
        self.calls = []

    def get_token_supply(self, mint):
        self.calls.append(mint)
        if len(self.calls) == 1:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        return {
            "result": {
                "context": {"slot": 200},
                "value": {"amount": "1000000000", "decimals": 6, "uiAmount": 1000.0, "uiAmountString": "1000"},
            }
        }


class CurrentMintSupplySnapshotTests(unittest.TestCase):
    def test_collects_unique_ready_token_supply_snapshots_and_blocks_errors(self):
        rpc = FakeRpc()
        report = build_current_mint_supply_snapshots(plan(), rpc, generated_at=123.0)

        self.assertEqual(rpc.calls, ["MintA", "MintB"])
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["tokens_requested"], 2)
        self.assertEqual(report["summary"]["snapshots_collected"], 1)
        self.assertEqual(report["summary"]["blocked_rpc_error"], 1)
        self.assertEqual(report["snapshots"][0]["token_mint"], "MintA")
        self.assertEqual(report["snapshots"][0]["raw_supply"], "1000000000")
        self.assertEqual(report["snapshots"][0]["slot"], 200)
        self.assertEqual(report["snapshots"][0]["source"], "current_getTokenSupply")

    def test_writer_persists_report_and_snapshot_rows(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            report_path = root / "report.json"
            snapshots_path = root / "snapshots.jsonl"
            plan_path.write_text(json.dumps(plan()), encoding="utf-8")

            report = write_current_mint_supply_snapshots(
                plan_path=plan_path,
                report_path=report_path,
                snapshots_path=snapshots_path,
                rpc=FakeRpc(),
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(snapshots_path.exists())
            self.assertEqual(report["summary"]["snapshots_collected"], 1)
            rows = [json.loads(line) for line in snapshots_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["token_mint"], "MintA")

    def test_retries_transient_rpc_errors_before_blocking_token(self):
        report = build_current_mint_supply_snapshots(
            {"token_requirements": [{"token_mint": "MintA", "status": "ready_for_archival_supply_fetch"}]},
            FlakyRpc(),
            retry_attempts=2,
            retry_sleep_seconds=0,
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["snapshots_collected"], 1)
        self.assertEqual(report["summary"]["blocked_rows"], 0)


if __name__ == "__main__":
    unittest.main()
