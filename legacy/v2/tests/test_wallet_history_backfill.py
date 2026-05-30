import tempfile
import unittest
from pathlib import Path

from utils.run_wallet_history_backfill import write_wallet_history_backfill_report
from wallets.wallet_history_backfill import build_wallet_history_backfill_report


class FakeRpc:
    def __init__(self):
        self.failures = []
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "getSignaturesForAddress":
            return [{"signature": "SigBuy"}, {"signature": "SigSell"}]
        if method == "getTransaction":
            signature = params[0]
            if signature == "SigBuy":
                return {
                    "blockTime": 123,
                    "meta": {
                        "preTokenBalances": [],
                        "postTokenBalances": [
                            {
                                "owner": "WalletA",
                                "mint": "MintA",
                                "uiTokenAmount": {"uiAmount": 10},
                            }
                        ],
                    },
                }
            return {
                "blockTime": 124,
                "meta": {
                    "preTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 10},
                        }
                    ],
                    "postTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 4},
                        }
                    ],
                },
            }
        return None


class WalletHistoryBackfillTests(unittest.TestCase):
    def test_default_queue_limit_covers_current_stage3_target_count(self):
        report = build_wallet_history_backfill_report(
            backfill_targets={
                "targets": [
                    {
                        "wallet": f"Wallet{i}",
                        "priority_score": 100 - i,
                        "next_collection_step": "COLLECT_WALLET_HISTORY",
                    }
                    for i in range(46)
                ]
            },
            execute=False,
        )

        self.assertEqual(report["summary"]["target_wallets"], 46)
        self.assertEqual(report["summary"]["dry_run_wallets"], 46)

    def test_parser_excludes_quote_side_mints_from_wallet_evidence(self):
        from wallets.wallet_history_parser import parse_wallet_token_deltas

        rows = parse_wallet_token_deltas(
            {
                "blockTime": 123,
                "meta": {
                    "preTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 3},
                        }
                    ],
                    "postTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 1},
                        },
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 10},
                        },
                    ],
                },
            },
            wallet="WalletA",
            signature="Sig111",
        )

        self.assertEqual([row["token_mint"] for row in rows], ["MintA"])

    def test_parser_records_quote_execution_price_from_same_transaction(self):
        from wallets.wallet_history_parser import parse_wallet_token_deltas

        rows = parse_wallet_token_deltas(
            {
                "blockTime": 123,
                "meta": {
                    "preTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 3},
                        }
                    ],
                    "postTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "So11111111111111111111111111111111111111112",
                            "uiTokenAmount": {"uiAmount": 2},
                        },
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 100},
                        },
                    ],
                },
            },
            wallet="WalletA",
            signature="Sig111",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["quote_mint"], "So11111111111111111111111111111111111111112")
        self.assertEqual(row["quote_amount_delta"], -1)
        self.assertEqual(row["execution_price_quote"], 0.01)
        self.assertEqual(row["estimated_entry_context"]["execution_price_quote"], 0.01)
        self.assertEqual(row["estimated_entry_context"]["quote_mint"], "So11111111111111111111111111111111111111112")

    def test_parser_recovers_quote_execution_price_from_native_sol_balance_delta(self):
        from wallets.wallet_history_parser import parse_wallet_token_deltas

        rows = parse_wallet_token_deltas(
            {
                "blockTime": 123,
                "transaction": {
                    "signatures": ["SigNativeBuy"],
                    "message": {
                        "accountKeys": [
                            {"pubkey": "WalletA", "signer": True},
                            {"pubkey": "OtherAccount", "signer": False},
                        ],
                    },
                },
                "meta": {
                    "fee": 5000,
                    "preBalances": [3_000_000_000, 1],
                    "postBalances": [1_999_995_000, 1],
                    "preTokenBalances": [],
                    "postTokenBalances": [
                        {
                            "owner": "WalletA",
                            "mint": "MintA",
                            "uiTokenAmount": {"uiAmount": 100},
                        }
                    ],
                },
            },
            wallet="WalletA",
            signature="SigNativeBuy",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["quote_mint"], "So11111111111111111111111111111111111111112")
        self.assertEqual(row["quote_amount_delta"], -1)
        self.assertEqual(row["execution_price_quote"], 0.01)
        self.assertEqual(row["estimated_entry_context"]["execution_price_source"], "native_sol_balance_delta")
        self.assertEqual(row["estimated_entry_context"]["native_sol_fee_lamports"], 5000)

    def test_collects_bounded_wallet_history_for_collection_targets(self):
        report = build_wallet_history_backfill_report(
            backfill_targets={
                "targets": [
                    {
                        "wallet": "WalletA",
                        "priority_score": 77,
                        "next_collection_step": "COLLECT_WALLET_HISTORY",
                    },
                    {
                        "wallet": "WalletRisk",
                        "priority_score": 80,
                        "next_collection_step": "REVIEW_RISK_FLAGS_FIRST",
                    },
                ]
            },
            rpc=FakeRpc(),
            execute=True,
            max_wallets=5,
            signature_limit=10,
            max_transactions_per_wallet=2,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "WALLET_HISTORY_BACKFILL_REVIEW_ONLY")
        self.assertEqual(report["summary"]["target_wallets"], 1)
        self.assertEqual(report["summary"]["collected_wallets"], 1)
        row = report["wallets"][0]
        self.assertEqual(row["wallet"], "WalletA")
        self.assertEqual(row["status"], "COLLECTED")
        self.assertEqual(row["signatures_fetched"], 2)
        self.assertEqual(row["transactions_inspected"], 2)
        self.assertEqual(row["buy_events"], 1)
        self.assertEqual(row["sell_events"], 1)
        self.assertEqual(row["unique_mints"], 1)

    def test_dry_run_does_not_call_rpc(self):
        rpc = FakeRpc()
        report = build_wallet_history_backfill_report(
            backfill_targets={
                "targets": [
                    {
                        "wallet": "WalletA",
                        "priority_score": 77,
                        "next_collection_step": "COLLECT_WALLET_HISTORY",
                    }
                ]
            },
            rpc=rpc,
            execute=False,
        )

        self.assertEqual(rpc.calls, [])
        self.assertEqual(report["summary"]["dry_run_wallets"], 1)
        self.assertEqual(report["wallets"][0]["status"], "DRY_RUN")

    def test_writer_persists_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_history_backfill_report.json"
            report = write_wallet_history_backfill_report(
                out_path=out,
                backfill_targets={
                    "targets": [
                        {
                            "wallet": "WalletA",
                            "next_collection_step": "COLLECT_WALLET_HISTORY",
                        }
                    ]
                },
                rpc=FakeRpc(),
                execute=False,
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["target_wallets"], 1)

    def test_writer_dedupes_existing_evidence_and_preserves_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "wallet_history_backfill_report.json"
            evidence = root / "wallet_history_evidence.jsonl"
            report_dir = root / "reports"
            raw_dir = root / "raw"
            evidence.write_text(
                (
                    '{"wallet":"WalletA","transaction_signature":"SigBuy","token_mint":"MintA","observed_action":"buy","token_amount_delta":10}\n'
                    '{"wallet":"WalletA","transaction_signature":"SigBuy","token_mint":"MintA","observed_action":"buy","token_amount_delta":10}\n'
                ),
                encoding="utf-8",
            )

            report = write_wallet_history_backfill_report(
                out_path=out,
                evidence_path=evidence,
                report_dir=report_dir,
                raw_dir=raw_dir,
                backfill_targets={
                    "targets": [
                        {
                            "wallet": "WalletA",
                            "next_collection_step": "COLLECT_WALLET_HISTORY",
                        }
                    ]
                },
                rpc=FakeRpc(),
                execute=True,
                max_wallets=1,
            )

            self.assertEqual(len(evidence.read_text(encoding="utf-8").splitlines()), 2)
            self.assertEqual(report["evidence_rows_written"], 1)
            self.assertEqual(report["evidence_duplicate_rows_skipped"], 1)
            self.assertEqual(report["existing_evidence_duplicates_removed"], 1)
            archive = report.get("evidence_dedupe_archive_path")
            self.assertTrue(archive)
            self.assertTrue(Path(archive).exists())


if __name__ == "__main__":
    unittest.main()
