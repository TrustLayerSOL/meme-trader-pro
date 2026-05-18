import tempfile
import unittest
from pathlib import Path

from wallets.forward_wallet_activity import build_forward_wallet_activity_report
from wallets.forward_wallet_activity import select_forward_wallets
from utils.run_forward_wallet_activity import write_forward_wallet_activity_report


class FakeRpc:
    def __init__(self):
        self.failures = []
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "getSignaturesForAddress":
            return [
                {"signature": "RecentBuy", "blockTime": 200},
                {"signature": "OldBuy", "blockTime": 50},
            ]
        if method == "getTransaction":
            signature = params[0]
            if signature == "RecentBuy":
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
                "blockTime": 50,
                "transaction": {"signatures": [signature]},
                "meta": {"preTokenBalances": [], "postTokenBalances": []},
            }
        return None


class ForwardWalletActivityTests(unittest.TestCase):
    def test_selects_tracked_then_paper_watch_without_duplicates(self):
        wallets = select_forward_wallets(
            tracked_wallets=[{"wallet": "WalletA"}, "WalletB"],
            paper_watch_wallets={"wallets": [{"wallet": "WalletB"}, {"wallet": "WalletC"}]},
            max_wallets=3,
        )

        self.assertEqual(wallets, ["WalletA", "WalletB", "WalletC"])

    def test_build_report_collects_only_recent_current_activity(self):
        report = build_forward_wallet_activity_report(
            tracked_wallets=[{"wallet": "WalletA"}],
            paper_watch_wallets=[],
            rpc=FakeRpc(),
            generated_at=1000,
            lookback_seconds=900,
            execute=True,
            max_wallets=1,
            signature_limit=10,
            max_transactions_per_wallet=5,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "FORWARD_WALLET_ACTIVITY_REVIEW_ONLY")
        self.assertEqual(report["summary"]["wallets_processed"], 1)
        self.assertEqual(report["summary"]["evidence_rows_created"], 1)
        self.assertEqual(report["summary"]["old_signatures_skipped"], 1)
        row = report["evidence_records"][0]
        self.assertEqual(row["wallet"], "WalletA")
        self.assertEqual(row["token_mint"], "MintA")
        self.assertEqual(row["observed_action"], "buy")
        self.assertEqual(row["later_token_outcome"]["outcome_type"], "pending_forward_outcome")
        self.assertIn("forward_current_activity", row["risk_flags"])

    def test_dry_run_does_not_call_rpc(self):
        rpc = FakeRpc()
        report = build_forward_wallet_activity_report(
            tracked_wallets=[{"wallet": "WalletA"}],
            paper_watch_wallets=[],
            rpc=rpc,
            execute=False,
        )

        self.assertEqual(rpc.calls, [])
        self.assertEqual(report["summary"]["dry_run_wallets"], 1)

    def test_writer_merges_forward_evidence_into_existing_evidence_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "forward_report.json"
            evidence = root / "wallet_history_evidence.jsonl"
            report_dir = root / "reports"
            raw_dir = root / "raw"

            report = write_forward_wallet_activity_report(
                out_path=out,
                evidence_path=evidence,
                report_dir=report_dir,
                raw_dir=raw_dir,
                tracked_wallets=[{"wallet": "WalletA"}],
                paper_watch_wallets=[],
                rpc=FakeRpc(),
                generated_at=1000,
                lookback_seconds=900,
                execute=True,
                max_wallets=1,
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["evidence_rows_written"], 1)
            self.assertEqual(len(evidence.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
