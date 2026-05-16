import json
import tempfile
import unittest
from pathlib import Path

from utils.recover_missing_raw_transactions import write_missing_raw_transaction_recovery_report
from wallets.missing_raw_transaction_recovery import (
    MODE,
    build_missing_raw_transaction_recovery_report,
    missing_transaction_targets,
)


def blocked_record(signature="SigA", wallet="WalletA", mint="MintA"):
    return {
        "status": "blocked_missing_transaction",
        "wallet": wallet,
        "token_mint": mint,
        "transaction_signature": signature,
        "timestamp": 1000,
    }


class FakeRpc:
    def __init__(self, transactions):
        self.transactions = transactions
        self.calls = []
        self.failures = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method != "getTransaction":
            return None
        return self.transactions.get(params[0])


class MissingRawTransactionRecoveryTests(unittest.TestCase):
    def test_missing_transaction_targets_dedupe_signatures(self):
        targets = missing_transaction_targets(
            {
                "records": [
                    blocked_record("SigA", "WalletA", "MintA"),
                    blocked_record("SigA", "WalletB", "MintB"),
                    blocked_record("SigB", "WalletC", "MintC"),
                    {"status": "blocked_missing_price", "transaction_signature": "SigC"},
                    {"status": "blocked_missing_transaction", "transaction_signature": ""},
                ]
            }
        )

        self.assertEqual([target["transaction_signature"] for target in targets], ["SigA", "SigB"])
        self.assertEqual(targets[0]["wallets"], ["WalletA", "WalletB"])
        self.assertEqual(targets[0]["token_mints"], ["MintA", "MintB"])

    def test_recovery_fetches_each_missing_signature_once(self):
        report = build_missing_raw_transaction_recovery_report(
            historical_backfill_report={
                "records": [
                    blocked_record("SigA", "WalletA", "MintA"),
                    blocked_record("SigA", "WalletB", "MintB"),
                    blocked_record("SigMissing", "WalletC", "MintC"),
                ]
            },
            rpc=FakeRpc({"SigA": {"blockTime": 1000, "meta": {}, "transaction": {"signatures": ["SigA"]}}}),
            execute=True,
            generated_at=1234,
        )

        self.assertEqual(report["mode"], MODE)
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["targets"], 2)
        self.assertEqual(report["summary"]["transactions_recovered"], 1)
        self.assertEqual(report["summary"]["transactions_blocked"], 1)
        self.assertEqual(report["summary"]["status_counts"], {"blocked_missing_transaction": 1, "recovered": 1})
        self.assertEqual(len(report["raw_transactions"]), 1)
        self.assertEqual(report["raw_transactions"][0]["signature"], "SigA")
        self.assertEqual(report["raw_transactions"][0]["wallet"], "WalletA")
        self.assertEqual(report["targets"][1]["status"], "blocked_missing_transaction")

    def test_dry_run_does_not_call_rpc(self):
        rpc = FakeRpc({"SigA": {"blockTime": 1000}})
        report = build_missing_raw_transaction_recovery_report(
            historical_backfill_report={"records": [blocked_record("SigA")]},
            rpc=rpc,
            execute=False,
            generated_at=1234,
        )

        self.assertEqual(report["summary"]["dry_run_targets"], 1)
        self.assertEqual(rpc.calls, [])
        self.assertEqual(report["targets"][0]["status"], "dry_run")

    def test_writer_persists_report_and_raw_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data" / "reports" / "historical_backfill" / "historical_market_context_backfill_report.json"
            out = root / "data" / "reports" / "historical_backfill" / "missing_raw_transaction_recovery_report.json"
            raw_dir = root / "data" / "wallet_backfills" / "raw_transactions"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({"records": [blocked_record("SigA")]}) + "\n")

            report = write_missing_raw_transaction_recovery_report(
                historical_backfill_report_path=source,
                report_path=out,
                raw_dir=raw_dir,
                rpc=FakeRpc({"SigA": {"blockTime": 1000, "meta": {}, "transaction": {"signatures": ["SigA"]}}}),
                execute=True,
                generated_at=1234,
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["transactions_recovered"], 1)
            raw_files = list(raw_dir.glob("missing_raw_transactions_*.jsonl"))
            self.assertEqual(len(raw_files), 1)
            raw_rows = [json.loads(line) for line in raw_files[0].read_text().splitlines()]
            self.assertEqual(raw_rows[0]["signature"], "SigA")


if __name__ == "__main__":
    unittest.main()
