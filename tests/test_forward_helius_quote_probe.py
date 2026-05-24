import json
import tempfile
import unittest
from pathlib import Path

from utils.run_forward_helius_quote_probe import write_forward_helius_quote_probe
from wallets.forward_helius_quote_probe import build_forward_helius_quote_probe


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.failures = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method != "getTransaction":
            return None
        signature = params[0]
        if signature == "RecoverableSig":
            return {
                "blockTime": 200,
                "transaction": {"signatures": [signature]},
                "meta": {
                    "preTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 5},
                        }
                    ],
                    "postTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 4},
                        },
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 100},
                        },
                    ],
                },
            }
        return {
            "blockTime": 200,
            "transaction": {"signatures": [signature]},
            "meta": {"preTokenBalances": [], "postTokenBalances": []},
        }


def rejected_row(signature="RecoverableSig", wallet="WalletA", mint="MintA"):
    return {
        "wallet": wallet,
        "transaction_signature": signature,
        "token_mint": mint,
        "signal_time": 200.0,
        "block_reason": "missing_valid_execution_price_quote",
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


class ForwardHeliusQuoteProbeTests(unittest.TestCase):
    def test_probe_reports_recoverable_quote_without_mutating(self):
        rpc = FakeRpc()

        report = build_forward_helius_quote_probe(
            rejected_records=[rejected_row(), rejected_row(signature="UnrecoverableSig", mint="MintB")],
            rpc=rpc,
            execute=True,
            paid_rpc_allowed=True,
            max_rows=2,
            run_id="fixed",
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "FORWARD_HELIUS_QUOTE_PROBE_REVIEW_ONLY")
        self.assertEqual(report["summary"]["rows_tested"], 2)
        self.assertEqual(report["summary"]["recoverable_quote_rows"], 1)
        self.assertEqual(report["summary"]["unrecoverable_rows"], 1)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual(report["rows"][0]["status"], "quote_anchor_recoverable")
        self.assertEqual(report["rows"][0]["execution_price_quote"], 0.01)

    def test_dry_run_selects_rows_without_calling_rpc(self):
        rpc = FakeRpc()

        report = build_forward_helius_quote_probe(
            rejected_records=[rejected_row(), rejected_row(signature="OtherSig", mint="MintB")],
            rpc=rpc,
            execute=False,
            paid_rpc_allowed=False,
            max_rows=2,
            run_id="fixed",
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["rows_selected"], 2)
        self.assertEqual(report["summary"]["rows_attempted"], 0)
        self.assertEqual(report["summary"]["transactions_fetched"], 0)
        self.assertEqual(report["summary"]["recoverable_quote_rows"], 0)
        self.assertEqual(len(rpc.calls), 0)
        self.assertEqual(report["rows"][0]["status"], "dry_run_selected")

    def test_execute_requires_paid_rpc_permission(self):
        with self.assertRaisesRegex(ValueError, "allow-paid-rpc"):
            build_forward_helius_quote_probe(
                rejected_records=[rejected_row()],
                rpc=FakeRpc(),
                execute=True,
                paid_rpc_allowed=False,
                max_rows=1,
                run_id="fixed",
                generated_at=123.0,
            )

    def test_writer_persists_probe_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rejected_path = root / "rejected.jsonl"
            output_dir = root / "out"
            rejected_path.write_text(json.dumps(rejected_row()) + "\n", encoding="utf-8")

            report = write_forward_helius_quote_probe(
                rejected_records_path=rejected_path,
                output_dir=output_dir,
                rpc=FakeRpc(),
                execute=True,
                paid_rpc_allowed=True,
                max_rows=1,
                run_id="fixed",
                generated_at=123.0,
            )

            self.assertTrue((output_dir / "forward_helius_quote_probe_fixed.json").exists())
            self.assertTrue((output_dir / "forward_helius_quote_probe_fixed.csv").exists())
            self.assertEqual(report["summary"]["recoverable_quote_rows"], 1)


if __name__ == "__main__":
    unittest.main()
