import json
import tempfile
import unittest
from pathlib import Path

from wallets.forward_wallet_activity import build_forward_wallet_activity_report
from wallets.forward_wallet_activity import DEFAULT_MAX_RPC_CALLS_PER_DAY
from wallets.forward_wallet_activity import estimate_api_budget
from wallets.forward_wallet_activity import select_forward_wallets
from utils.run_forward_wallet_activity import run_forward_wallet_activity_cycle
from utils.run_forward_wallet_activity import write_forward_wallet_activity_report
from utils.run_forward_wallet_activity import build_forward_rpc_client


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
    def test_default_daily_budget_stays_inside_current_developer_plan_allowance(self):
        self.assertLessEqual(DEFAULT_MAX_RPC_CALLS_PER_DAY, 120_000)

    def test_default_budget_blocks_hundred_wallet_fifteen_minute_rotation(self):
        budget = estimate_api_budget(
            selected_wallets=100,
            signature_limit=40,
            max_transactions_per_wallet=20,
            interval_seconds=900,
        )

        self.assertEqual(budget["projected_rpc_calls_per_day"], 201600)
        self.assertEqual(budget["budget_status"], "blocked_daily_limit")
        self.assertFalse(budget["execute_allowed"])

    def test_fifty_wallet_fifteen_minute_rotation_fits_current_developer_plan_allowance(self):
        budget = estimate_api_budget(
            selected_wallets=50,
            signature_limit=40,
            max_transactions_per_wallet=20,
            interval_seconds=900,
        )

        self.assertEqual(budget["projected_rpc_calls_per_day"], 100800)
        self.assertEqual(budget["budget_status"], "within_budget")
        self.assertTrue(budget["execute_allowed"])
        self.assertLessEqual(budget["projected_rpc_calls_per_day"] * 13, 2_000_000)

    def test_estimates_forward_activity_api_budget(self):
        budget = estimate_api_budget(
            selected_wallets=50,
            signature_limit=40,
            max_transactions_per_wallet=20,
            interval_seconds=900,
            max_rpc_calls_per_cycle=2500,
            max_rpc_calls_per_day=250000,
        )

        self.assertEqual(budget["estimated_rpc_calls_per_cycle"], 1050)
        self.assertEqual(budget["projected_rpc_calls_per_day"], 100800)
        self.assertEqual(budget["budget_status"], "within_budget")
        self.assertTrue(budget["execute_allowed"])

    def test_blocks_execute_when_api_budget_exceeds_cycle_limit_before_rpc_calls(self):
        rpc = FakeRpc()
        report = build_forward_wallet_activity_report(
            tracked_wallets=[{"wallet": f"Wallet{i}"} for i in range(150)],
            paper_watch_wallets=[],
            rpc=rpc,
            execute=True,
            max_wallets=150,
            signature_limit=40,
            max_transactions_per_wallet=20,
            max_rpc_calls_per_cycle=2500,
            max_rpc_calls_per_day=250000,
            interval_seconds=900,
        )

        self.assertEqual(rpc.calls, [])
        self.assertEqual(report["summary"]["wallets_processed"], 0)
        self.assertEqual(report["summary"]["wallets_blocked_api_budget"], 150)
        self.assertEqual(report["api_budget"]["budget_status"], "blocked_cycle_limit")
        self.assertFalse(report["api_budget"]["execute_allowed"])
        self.assertIn("api budget", report["next_actions"][0])

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

    def test_writer_can_capture_market_context_before_merging_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "forward_report.json"
            evidence = root / "wallet_history_evidence.jsonl"
            report_dir = root / "reports"
            raw_dir = root / "raw"
            market_context_path = root / "forward_market_context.jsonl"

            def fake_market_provider(mint):
                return {
                    "source": "dexscreener",
                    "price": 0.02,
                    "liquidity": 50_000,
                    "market_cap": 500_000,
                    "url": f"https://dexscreener.test/{mint}",
                }

            report = write_forward_wallet_activity_report(
                out_path=out,
                evidence_path=evidence,
                report_dir=report_dir,
                raw_dir=raw_dir,
                market_context_path=market_context_path,
                tracked_wallets=[{"wallet": "WalletA"}],
                paper_watch_wallets=[],
                rpc=FakeRpc(),
                generated_at=205,
                lookback_seconds=900,
                execute=True,
                max_wallets=1,
                capture_market_context=True,
                market_context_provider=fake_market_provider,
                persist_market_context=False,
            )

            self.assertEqual(report["market_context"]["summary"]["snapshots_collected"], 1)
            self.assertEqual(report["market_context_snapshots_written"], 1)
            self.assertTrue(market_context_path.exists())
            row = json.loads(evidence.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["estimated_entry_context"]["price"], 0.02)
            self.assertEqual(row["estimated_entry_context"]["market_cap"], 500_000)

    def test_cycle_updates_runtime_status_without_execution_mutation(self):
        updates = []

        def fake_update(component, **fields):
            updates.append((component, fields))

        def fake_writer(**kwargs):
            return {
                "live_execution_locked": True,
                "summary": {
                    "wallets_processed": 3,
                    "wallets_collected": 2,
                    "evidence_rows_created": 5,
                    "wallets_blocked_rpc_error": 0,
                },
            }

        report = run_forward_wallet_activity_cycle(
            write_report=fake_writer,
            update_status=fake_update,
            execute=True,
            max_wallets=3,
            interval_seconds=300,
        )

        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(updates[0][0], "forward_wallet_activity")
        self.assertEqual(updates[0][1]["status"], "cycle_running")
        self.assertEqual(updates[-1][1]["status"], "cycle_ok")
        self.assertEqual(updates[-1][1]["wallets_processed"], 3)
        self.assertEqual(updates[-1][1]["evidence_rows_created"], 5)
        self.assertTrue(updates[-1][1]["live_execution_locked"])

    def test_cycle_surfaces_api_budget_status_in_runtime(self):
        updates = []

        def fake_update(component, **fields):
            updates.append((component, fields))

        def fake_writer(**kwargs):
            return {
                "live_execution_locked": True,
                "summary": {
                    "wallets_processed": 0,
                    "wallets_collected": 0,
                    "evidence_rows_created": 0,
                    "wallets_blocked_rpc_error": 0,
                    "wallets_blocked_api_budget": 150,
                },
                "api_budget": {
                    "budget_status": "blocked_cycle_limit",
                    "estimated_rpc_calls_per_cycle": 3150,
                    "projected_rpc_calls_per_day": 302400,
                },
            }

        run_forward_wallet_activity_cycle(
            write_report=fake_writer,
            update_status=fake_update,
            execute=True,
            max_wallets=150,
            interval_seconds=900,
        )

        self.assertEqual(updates[-1][1]["api_budget_status"], "blocked_cycle_limit")
        self.assertEqual(updates[-1][1]["estimated_rpc_calls_per_cycle"], 3150)
        self.assertEqual(updates[-1][1]["wallets_blocked_api_budget"], 150)

    def test_forward_rpc_client_defaults_to_public_only_providers(self):
        rpc = build_forward_rpc_client(allow_paid_rpc=False)

        self.assertTrue(rpc.providers)
        self.assertTrue(all("helius" not in provider.url for provider in rpc.providers))
        self.assertTrue(all("api-key=" not in provider.url for provider in rpc.providers))

    def test_forward_report_records_free_rpc_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = write_forward_wallet_activity_report(
                out_path=root / "forward_report.json",
                evidence_path=root / "wallet_history_evidence.jsonl",
                report_dir=root / "reports",
                raw_dir=root / "raw",
                tracked_wallets=[{"wallet": "WalletA"}],
                paper_watch_wallets=[],
                rpc=FakeRpc(),
                generated_at=1000,
                lookback_seconds=900,
                execute=True,
                max_wallets=1,
                rpc_mode="free_public_rpc",
                paid_rpc_allowed=False,
            )

            self.assertEqual(report["rpc_mode"], "free_public_rpc")
            self.assertFalse(report["paid_rpc_allowed"])


if __name__ == "__main__":
    unittest.main()
