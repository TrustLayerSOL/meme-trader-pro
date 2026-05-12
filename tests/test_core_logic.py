import json
import unittest
import asyncio
import os
import subprocess
import sys
import tempfile
from unittest import mock
from tempfile import TemporaryDirectory
from pathlib import Path

import paper_trader
import main as bot_main
from core.storage import EventStore
from core.decision_ledger import build_decision_record, build_trade_result
from core import settings_manager
from core import rug_watchdog
from core.catalyst_cards import build_catalyst_cards_from_snapshots
from core.holder_concentration import analyze_holder_concentration
from core.protection_exit import ProtectionExitPlanner
from core.protection_amounts import apply_manual_amount_to_watchlist, build_manual_amount_patch
from core.position_cockpit import build_candles, build_simulated_action_intent
from core.paper_exploration import evaluate_paper_exploration
from core.rpc_provider import (
    HeliusRpcProvider,
    build_helius_rpc_providers,
    choose_first_healthy_provider,
    summarize_provider_health,
)
from core.token_inspector import TokenInspector, TOKEN_2022_PROGRAM
from core.token_balance import parse_owner_token_balance
from core.watchdog_balance import apply_wallet_balance_result
from core.watchdog_state import merge_watchlist_updates
from core.wallet_discovery import (
    CandidateWalletDiscovery,
    apply_review_policy,
    evaluate_candidate_wallet,
    extract_owner_deltas,
    normalize_tracked_wallets,
)
from core.wallet_lifecycle import (
    build_wallet_lifecycle_report,
    evaluate_wallet_lifecycle,
    sync_paper_watch_wallets,
)
from core.wallet_list_apply import (
    apply_wallet_review_decisions,
    build_tracked_wallet_row,
    normalize_review_decisions,
)
from utils import apply_wallet_review
from core.wallet_discovery_scheduler import run_wallet_discovery_cycle
from core.wallet_behavior import build_wallet_behavior_report
from core.scanner import Scanner
from infra.rpc_client import SolanaRPC
from social.reddit_collector import collect_reddit_social, reddit_post_to_signal
from social.social_signal import SocialSignalEngine


_MODULE_CWD = Path.cwd()
_MODULE_TMPDIR = None


def setUpModule():
    global _MODULE_TMPDIR
    _MODULE_TMPDIR = tempfile.TemporaryDirectory()
    os.chdir(_MODULE_TMPDIR.name)


def tearDownModule():
    os.chdir(_MODULE_CWD)
    if _MODULE_TMPDIR is not None:
        _MODULE_TMPDIR.cleanup()


class NoopStore:
    def upsert_trade(self, trade):
        return None

    def insert_token_snapshot(self, snapshot):
        return None

    def update_decision_action(self, decision_id, action):
        return None

    def update_decision_result(self, decision_id, result):
        return None


class RecordingStore:
    def __init__(self):
        self.snapshots = []
        self.swap_ticks = []
        self.decisions = []
        self.decision_actions = []
        self.decision_results = []

    def upsert_trade(self, trade):
        return None

    def insert_token_snapshot(self, snapshot):
        self.snapshots.append(snapshot)

    def insert_swap_tick(self, tick):
        self.swap_ticks.append(tick)
        return True

    def upsert_decision(self, decision):
        self.decisions.append(decision)
        return decision.get("decision_id")

    def update_decision_action(self, decision_id, action):
        self.decision_actions.append({"decision_id": decision_id, "action": action})
        return True

    def update_decision_result(self, decision_id, result):
        self.decision_results.append({"decision_id": decision_id, "result": result})
        return True


class NoopWalletPerformance:
    def record_trade_result(self, wallets, pnl):
        return None


class RpcProviderTests(unittest.TestCase):
    def test_rpc_client_import_does_not_require_live_api_key(self):
        with TemporaryDirectory() as tmpdir:
            env = dict(os.environ)
            env.pop("HELIUS_API_KEY", None)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            result = subprocess.run(
                [sys.executable, "-c", "import infra.rpc_client"],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_main_import_has_no_runtime_side_effect_output(self):
        result = subprocess.run(
            [sys.executable, "-c", "import main"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_default_helius_providers_prefer_gatekeeper_then_mainnet(self):
        providers = build_helius_rpc_providers(api_key="test-key")

        self.assertEqual([provider.name for provider in providers], ["helius_gatekeeper", "helius_mainnet", "solana_public"])
        self.assertIn("beta.helius-rpc.com", providers[0].url)
        self.assertIn("mainnet.helius-rpc.com", providers[1].url)
        self.assertEqual(providers[2].url, "https://api.mainnet-beta.solana.com")
        self.assertNotIn("test-key", providers[0].safe_url)
        self.assertNotIn("api-key=", providers[2].url)

    def test_provider_selection_falls_back_after_429(self):
        health = [
            {"name": "helius_gatekeeper", "ok": False, "http_status": 429, "detail": "max usage reached"},
            {"name": "helius_mainnet", "ok": True, "http_status": 200, "detail": "ok"},
        ]

        selected = choose_first_healthy_provider(health)
        summary = summarize_provider_health(health)

        self.assertEqual(selected["name"], "helius_mainnet")
        self.assertEqual(summary["state"], "degraded")
        self.assertEqual(summary["active_provider"], "helius_mainnet")

    def test_custom_fallback_provider_urls_are_supported(self):
        providers = build_helius_rpc_providers(
            api_key="test-key",
            primary_url="https://primary.example/?api-key=test-key",
            fallback_urls="https://backup.example/?api-key=test-key, https://second.example/?api-key=test-key",
        )

        self.assertEqual([provider.name for provider in providers], ["primary", "fallback_1", "fallback_2"])
        self.assertEqual(providers[1], HeliusRpcProvider("fallback_1", "https://backup.example/?api-key=test-key"))

    def test_external_fallback_urls_do_not_get_helius_key_appended(self):
        providers = build_helius_rpc_providers(
            api_key="test-key",
            fallback_urls="https://external.example/rpc",
        )

        external = next(provider for provider in providers if provider.name == "fallback_1")
        self.assertEqual(external.url, "https://external.example/rpc")


class CandidateWalletDiscoveryTests(unittest.TestCase):
    def test_normalize_tracked_wallets_supports_axiom_export_shape(self):
        wallets = normalize_tracked_wallets([
            {"trackedWalletAddress": "Wallet111", "name": "alpha"},
            {"address": "Wallet222", "name": "beta"},
            "ignored",
        ])

        self.assertEqual(set(wallets), {"Wallet111", "Wallet222"})
        self.assertEqual(wallets["Wallet111"]["name"], "alpha")

    def test_extract_owner_deltas_finds_positive_token_owner_changes(self):
        tx = {
            "blockTime": 1000,
            "meta": {
                "preTokenBalances": [
                    {"owner": "Buyer111", "mint": "Mint111", "uiTokenAmount": {"uiAmount": 0}},
                    {"owner": "Seller111", "mint": "Mint111", "uiTokenAmount": {"uiAmount": 10}},
                ],
                "postTokenBalances": [
                    {"owner": "Buyer111", "mint": "Mint111", "uiTokenAmount": {"uiAmount": 4}},
                    {"owner": "Seller111", "mint": "Mint111", "uiTokenAmount": {"uiAmount": 6}},
                ],
            },
        }

        deltas = extract_owner_deltas(tx, "Mint111")

        self.assertEqual(deltas[0]["wallet"], "Buyer111")
        self.assertEqual(deltas[0]["delta"], 4)
        self.assertEqual(deltas[0]["side"], "buy")
        self.assertEqual(deltas[1]["side"], "sell")

    def test_discovery_scores_untracked_repeat_early_buyers_for_watch_only_review(self):
        discovery = CandidateWalletDiscovery(
            tracked_wallets={"Tracked111": {"name": "known"}},
            existing_performance={"wallets": {"Tracked111": {"score": 62}}},
        )
        report = discovery.build_report(
            local_events=[
                {"time": 100, "event_type": "buy", "wallet": "Tracked111", "mint": "MintA"},
                {"time": 101, "event_type": "buy", "wallet": "New111", "mint": "MintA"},
                {"time": 102, "event_type": "buy", "wallet": "New111", "mint": "MintB"},
                {"time": 103, "event_type": "sell", "wallet": "Noisy111", "mint": "MintC"},
                {"time": 104, "event_type": "sell", "wallet": "Noisy111", "mint": "MintD"},
            ],
            mint_evidence=[
                {"mint": "WinnerA", "winner": True, "early_buyers": [{"wallet": "New111", "delta": 20, "time": 90}]},
                {"mint": "WinnerB", "winner": True, "early_buyers": [{"wallet": "New111", "delta": 10, "time": 91}]},
            ],
        )

        candidates = {row["wallet"]: row for row in report["candidates"]}
        self.assertIn("New111", candidates)
        self.assertFalse(candidates["New111"]["already_tracked"])
        self.assertIn(candidates["New111"]["recommended_tier"], {"tier_1_candidate", "tier_2_confirm"})
        self.assertGreater(candidates["New111"]["score"], candidates["Noisy111"]["score"])
        self.assertEqual(report["mode"], "WATCH_ONLY_REVIEW")

    def test_candidate_wallet_policy_promotes_only_to_paper_watch(self):
        decision = evaluate_candidate_wallet({
            "wallet": "New111",
            "already_tracked": False,
            "score": 78,
            "early_buy_events": 4,
            "winner_mints": 2,
            "unique_mints": 2,
            "sell_ratio": 0.1,
        })

        self.assertEqual(decision["action"], "PAPER_WATCH")
        self.assertFalse(decision["mutates_tracked_wallets"])
        self.assertIn("score >= 70", decision["reasons"])

    def test_candidate_wallet_policy_holds_thin_evidence(self):
        decision = evaluate_candidate_wallet({
            "wallet": "New111",
            "already_tracked": False,
            "score": 53,
            "early_buy_events": 1,
            "winner_mints": 1,
            "unique_mints": 1,
            "sell_ratio": 0,
        })

        self.assertEqual(decision["action"], "HOLD_REVIEW")
        self.assertIn("needs more mints or repeat evidence", decision["blockers"])

    def test_candidate_wallet_policy_flags_tracked_demotion_review(self):
        decision = evaluate_candidate_wallet({
            "wallet": "Tracked111",
            "already_tracked": True,
            "score": 35,
            "buy_events": 0,
            "sell_events": 9,
            "sell_ratio": 1.0,
        })

        self.assertEqual(decision["action"], "DEMOTE_REVIEW")
        self.assertFalse(decision["mutates_tracked_wallets"])
        self.assertIn("tracked wallet has weak current evidence", decision["blockers"])

    def test_apply_review_policy_summarizes_actions(self):
        report = apply_review_policy({
            "mode": "WATCH_ONLY_REVIEW",
            "candidates": [
                {"wallet": "New111", "already_tracked": False, "score": 78, "early_buy_events": 4, "winner_mints": 1, "unique_mints": 2},
                {"wallet": "Tracked111", "already_tracked": True, "score": 35, "sell_ratio": 1.0, "buy_events": 0, "sell_events": 4},
            ],
        })

        self.assertEqual(report["review_policy"]["mode"], "REVIEW_ONLY")
        self.assertEqual(report["review_summary"]["paper_watch"], 1)
        self.assertEqual(report["review_summary"]["demote_review"], 1)
        self.assertEqual(report["candidates"][0]["review"]["action"], "PAPER_WATCH")


class WalletLifecycleTests(unittest.TestCase):
    def test_promotes_profitable_repeat_wallet_to_trusted_candidate(self):
        decision = evaluate_wallet_lifecycle(
            "WalletWin",
            performance={"paper_entries": 6, "wins": 5, "losses": 1, "avg_pnl": 18, "total_pnl": 108, "score": 82},
            current_source="paper_watch",
        )

        self.assertEqual(decision["action"], "PROMOTE_TO_TRUSTED_REVIEW")
        self.assertEqual(decision["target_tier"], "trusted_review")
        self.assertFalse(decision["mutates_live_tracking"])

    def test_demotes_bad_existing_tracked_wallet(self):
        decision = evaluate_wallet_lifecycle(
            "WalletBad",
            performance={"paper_entries": 4, "wins": 0, "losses": 4, "avg_pnl": -14, "total_pnl": -56, "score": 22},
            current_source="tracked",
        )

        self.assertEqual(decision["action"], "DEMOTE_OFF_WATCH_REVIEW")
        self.assertEqual(decision["target_tier"], "demote_review")
        self.assertIn("negative average paper PnL", decision["blockers"])

    def test_paper_watch_candidate_can_enter_learning_lane(self):
        report = sync_paper_watch_wallets(
            current_wallets=[],
            candidate_report={
                "candidates": [{
                    "wallet": "WalletCandidate",
                    "review": {"action": "PAPER_WATCH"},
                    "score": 75,
                    "early_buy_events": 8,
                    "winner_mints": 1,
                }]
            },
            performance={"wallets": {}},
            generated_at=100,
        )

        self.assertEqual(report["mode"], "PAPER_WATCH_ONLY")
        self.assertEqual(report["summary"]["paper_watch_wallets"], 1)
        self.assertEqual(report["wallets"][0]["wallet"], "WalletCandidate")
        self.assertEqual(report["wallets"][0]["status"], "paper_watch")
        self.assertFalse(report["wallets"][0]["live_trade_driver"])

    def test_lifecycle_report_flags_promotions_and_demotions(self):
        report = build_wallet_lifecycle_report(
            tracked_wallets={"TrackedBad": {}, "TrackedGood": {}},
            paper_watch_wallets=[{"wallet": "WatchWin", "status": "paper_watch"}],
            candidate_report={"candidates": []},
            performance={
                "wallets": {
                    "TrackedBad": {"paper_entries": 4, "wins": 0, "losses": 4, "avg_pnl": -12, "score": 24},
                    "TrackedGood": {"paper_entries": 8, "wins": 6, "losses": 2, "avg_pnl": 11, "score": 76},
                    "WatchWin": {"paper_entries": 6, "wins": 5, "losses": 1, "avg_pnl": 15, "score": 82},
                }
            },
        )

        actions = {row["wallet"]: row["lifecycle"]["action"] for row in report["wallets"]}
        self.assertEqual(actions["TrackedBad"], "DEMOTE_OFF_WATCH_REVIEW")
        self.assertEqual(actions["WatchWin"], "PROMOTE_TO_TRUSTED_REVIEW")
        self.assertEqual(actions["TrackedGood"], "KEEP_TRUSTED")

    def test_lifecycle_report_includes_behavior_labels_and_rolling_windows(self):
        report = build_wallet_lifecycle_report(
            tracked_wallets={"Tracked111": {}},
            paper_watch_wallets=[],
            candidate_report={"candidates": []},
            performance={"wallets": {"Tracked111": {"paper_entries": 3, "wins": 2, "losses": 1, "avg_pnl": 10, "score": 80}}},
            behavior={
                "wallets": {
                    "Tracked111": {
                        "labels": ["paper-profitable", "early-buyer"],
                        "rolling": {"7d": {"entries": 3, "avg_pnl": 10}, "30d": {"entries": 3, "avg_pnl": 10}},
                    }
                }
            },
        )

        lifecycle = report["wallets"][0]["lifecycle"]
        self.assertEqual(lifecycle["labels"], ["paper-profitable", "early-buyer"])
        self.assertEqual(lifecycle["rolling"]["7d"]["entries"], 3)

    def test_lifecycle_report_includes_behavior_postmortem_rollup(self):
        report = build_wallet_lifecycle_report(
            tracked_wallets={"Tracked111": {}},
            paper_watch_wallets=[],
            candidate_report={"candidates": []},
            performance={"wallets": {"Tracked111": {"paper_entries": 3, "wins": 2, "losses": 1, "avg_pnl": 10, "score": 80}}},
            behavior={
                "wallets": {
                    "Tracked111": {
                        "postmortem": {
                            "closed_trades": 3,
                            "failed_trades": 1,
                            "best_trade": {"mint": "MintBest", "pnl_pct": 80},
                            "worst_trade": {"mint": "MintWorst", "pnl_pct": -20},
                            "exit_reasons": {"target_profit": 2},
                            "failure_reasons": {"quote_failed": 1},
                        },
                    }
                }
            },
        )

        postmortem = report["wallets"][0]["lifecycle"]["postmortem"]
        self.assertEqual(postmortem["closed_trades"], 3)
        self.assertEqual(postmortem["best_trade"]["mint"], "MintBest")

    def test_main_loads_paper_watch_wallets_without_tracked_mutation(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "paper_watch_wallets.json"
            path.write_text(json.dumps({
                "wallets": [
                    {"wallet": "Watch111", "status": "paper_watch"},
                    {"wallet": "Demote111", "status": "demote_review"},
                    {"wallet": "Watch111", "status": "paper_watch"},
                ]
            }))
            original_open = open

            def fake_open(file, *args, **kwargs):
                if str(file) == "data/paper_watch_wallets.json":
                    return original_open(path, *args, **kwargs)
                return original_open(file, *args, **kwargs)

            with mock.patch("builtins.open", side_effect=fake_open):
                wallets = bot_main.load_paper_watch_wallets()

        self.assertEqual(wallets, ["Watch111"])

    def test_scanner_can_add_paper_watch_wallets_after_startup(self):
        scanner = Scanner(["Tracked111"], None, paper_watch_wallets=[])

        added = scanner.add_paper_watch_wallets(["Watch111", "Tracked111", "Watch111"])

        self.assertEqual(added, ["Watch111"])
        self.assertTrue(scanner.is_observed_wallet("Watch111"))
        self.assertEqual(scanner.wallet_source("Watch111"), "paper_watch")
        self.assertEqual(scanner.wallet_source("Tracked111"), "tracked")

    def test_rpc_subscribes_only_new_paper_watch_wallets(self):
        class FakeWebsocket:
            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(json.loads(message))

        rpc = SolanaRPC(["Tracked111"], paper_watch_wallets=["Watch111"])
        websocket = FakeWebsocket()

        added = asyncio.run(rpc.subscribe_new_paper_watch_wallets(websocket, ["Watch111", "Watch222"]))

        self.assertEqual(added, ["Watch222"])
        self.assertIn("Watch222", rpc.paper_watch_wallets)
        self.assertIn("Watch222", rpc.observed_wallets)
        self.assertEqual(rpc.scanner.wallet_source("Watch222"), "paper_watch")
        self.assertEqual(len(websocket.sent), 1)
        self.assertEqual(websocket.sent[0]["params"][0]["mentions"], ["Watch222"])


class SolanaRpcPressureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.update_patch = mock.patch("infra.rpc_client.update_component")
        self.increment_patch = mock.patch("infra.rpc_client.increment_component")
        self.update_patch.start()
        self.increment_patch.start()

    async def asyncTearDown(self):
        self.increment_patch.stop()
        self.update_patch.stop()

    async def test_get_transaction_dedupes_concurrent_same_signature_fetches(self):
        rpc = SolanaRPC(["Tracked111"])
        rpc.transaction_min_interval = 0
        calls = []

        async def fake_rpc_call(method, params):
            calls.append((method, params[0]))
            await asyncio.sleep(0.01)
            return {"result": {"slot": 123, "signature": params[0]}}

        rpc.rpc_call = fake_rpc_call

        results = await asyncio.gather(
            rpc.get_transaction("Sig111"),
            rpc.get_transaction("Sig111"),
            rpc.get_transaction("Sig111"),
        )

        self.assertEqual(calls, [("getTransaction", "Sig111")])
        self.assertEqual([result["result"]["signature"] for result in results], ["Sig111", "Sig111", "Sig111"])

    async def test_get_transaction_reuses_cached_result(self):
        rpc = SolanaRPC(["Tracked111"])
        rpc.transaction_min_interval = 0
        calls = []

        async def fake_rpc_call(method, params):
            calls.append((method, params[0]))
            return {"result": {"slot": len(calls), "signature": params[0]}}

        rpc.rpc_call = fake_rpc_call

        first = await rpc.get_transaction("SigCached")
        second = await rpc.get_transaction("SigCached")

        self.assertEqual(first, second)
        self.assertEqual(calls, [("getTransaction", "SigCached")])

    async def test_get_transaction_paces_different_signature_fetches(self):
        rpc = SolanaRPC(["Tracked111"])
        rpc.transaction_min_interval = 0.02
        starts = []

        async def fake_rpc_call(method, params):
            starts.append(asyncio.get_running_loop().time())
            return {"result": {"signature": params[0]}}

        rpc.rpc_call = fake_rpc_call

        await asyncio.gather(
            rpc.get_transaction("SigA"),
            rpc.get_transaction("SigB"),
        )

        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], 0.015)

    async def test_enqueue_or_drop_message_drops_when_backlog_is_full(self):
        rpc = SolanaRPC(["Tracked111"])
        rpc.max_event_backlog = 1
        blocker = asyncio.create_task(asyncio.sleep(1))
        rpc.active_tasks.add(blocker)

        with mock.patch.object(rpc, "handle_message_fast") as handle_message:
            task = await rpc.enqueue_or_drop_message("{}")

        blocker.cancel()
        rpc.active_tasks.discard(blocker)
        self.assertIsNone(task)
        handle_message.assert_not_called()

    def test_subscription_ack_maps_subscription_to_wallet(self):
        rpc = SolanaRPC(["Tracked111"])
        rpc.pending_subscription_wallets[7] = "Tracked111"

        handled = rpc.handle_subscription_ack(json.dumps({
            "jsonrpc": "2.0",
            "id": 7,
            "result": 42,
        }))

        self.assertTrue(handled)
        self.assertEqual(rpc.subscription_wallets[42], "Tracked111")
        self.assertNotIn(7, rpc.pending_subscription_wallets)

    async def test_enqueue_or_drop_message_limits_one_noisy_wallet_without_blocking_others(self):
        rpc = SolanaRPC(["Noisy111", "Quiet111"])
        rpc.max_inflight_per_wallet = 1
        rpc.subscription_wallets[101] = "Noisy111"
        rpc.subscription_wallets[202] = "Quiet111"
        blocker = asyncio.create_task(asyncio.sleep(1))
        rpc.track_task(blocker, wallet="Noisy111")
        noisy_message = json.dumps({
            "jsonrpc": "2.0",
            "method": "logsNotification",
            "params": {"subscription": 101, "result": {"value": {"signature": "SigNoisy"}}},
        })
        quiet_message = json.dumps({
            "jsonrpc": "2.0",
            "method": "logsNotification",
            "params": {"subscription": 202, "result": {"value": {"signature": "SigQuiet"}}},
        })

        with mock.patch.object(rpc, "handle_message_fast") as handle_message:
            noisy_task = await rpc.enqueue_or_drop_message(noisy_message)
            quiet_task = await rpc.enqueue_or_drop_message(quiet_message)

        blocker.cancel()
        rpc.active_tasks.discard(blocker)
        self.assertIsNone(noisy_task)
        self.assertIsNotNone(quiet_task)
        await quiet_task
        handle_message.assert_awaited_once_with(quiet_message)


class WatchdogPressureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.update_patch = mock.patch("core.rug_watchdog.update_component")
        self.increment_patch = mock.patch("core.rug_watchdog.increment_component")
        self.update_patch.start()
        self.increment_patch.start()

    async def asyncTearDown(self):
        self.increment_patch.stop()
        self.update_patch.stop()

    async def test_largest_token_accounts_uses_cache_for_repeated_mint(self):
        class FakeChecker:
            session = object()

            async def init_session(self):
                return None

        cache = rug_watchdog.WatchdogDeepRpcCache(ttl_seconds=60, cooldown_seconds=60)
        calls = []

        async def fake_post(session, payload):
            calls.append(payload["method"])
            return {"result": {"value": [{"address": "Holder111"}]}}, "primary"

        with mock.patch("core.rug_watchdog.post_json_with_provider_failover", side_effect=fake_post):
            first = await rug_watchdog.fetch_largest_token_accounts(FakeChecker(), "Mint111", cache=cache)
            second = await rug_watchdog.fetch_largest_token_accounts(FakeChecker(), "Mint111", cache=cache)

        self.assertEqual(first, second)
        self.assertEqual(calls, ["getTokenLargestAccounts"])

    async def test_mint_account_info_uses_cooldown_after_rate_limit(self):
        class FakeChecker:
            session = object()

            async def init_session(self):
                return None

        cache = rug_watchdog.WatchdogDeepRpcCache(ttl_seconds=60, cooldown_seconds=60)
        calls = []

        async def fake_post(session, payload):
            calls.append(payload["method"])
            raise rug_watchdog.RpcProviderError([{"name": "helius", "detail": "Too Many Requests", "http_status": 429}])

        with mock.patch("core.rug_watchdog.post_json_with_provider_failover", side_effect=fake_post):
            first = await rug_watchdog.fetch_mint_account_info(FakeChecker(), "MintRate", cache=cache)
            second = await rug_watchdog.fetch_mint_account_info(FakeChecker(), "MintRate", cache=cache)

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(calls, ["getAccountInfo"])

    async def test_owner_token_balance_cache_is_scoped_by_wallet_and_mint(self):
        class FakeChecker:
            session = object()

            async def init_session(self):
                return None

        cache = rug_watchdog.WatchdogDeepRpcCache(ttl_seconds=60, cooldown_seconds=60)
        calls = []

        async def fake_post(session, payload):
            calls.append((payload["params"][0], payload["params"][1]["mint"]))
            return {
                "result": {
                    "value": [{
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "tokenAmount": {
                                            "amount": "100",
                                            "decimals": 2,
                                            "uiAmount": 1.0,
                                        }
                                    }
                                }
                            }
                        }
                    }]
                }
            }, "primary"

        with mock.patch("core.rug_watchdog.post_json_with_provider_failover", side_effect=fake_post):
            first = await rug_watchdog.fetch_owner_token_balance(FakeChecker(), "Wallet111", "Mint111", cache=cache)
            second = await rug_watchdog.fetch_owner_token_balance(FakeChecker(), "Wallet111", "Mint111", cache=cache)
            third = await rug_watchdog.fetch_owner_token_balance(FakeChecker(), "Wallet222", "Mint111", cache=cache)

        self.assertEqual(first, second)
        self.assertEqual(first["amount_raw"], 100)
        self.assertEqual(third["amount_raw"], 100)
        self.assertEqual(calls, [("Wallet111", "Mint111"), ("Wallet222", "Mint111")])

    async def test_exit_quote_feasibility_reuses_cached_quote(self):
        class FakeQuoteEngine:
            def __init__(self):
                self.calls = 0

            async def get_sell_quote(self, **kwargs):
                self.calls += 1
                return {
                    "ok": True,
                    "reason": "quote_ok",
                    "route_count": 1,
                    "out_amount": 123,
                    "price_impact_pct": 0.1,
                }

            def analyze_quote(self, quote, max_price_impact_pct=8):
                return {
                    "pass": bool(quote and quote.get("ok")),
                    "reason": quote.get("reason"),
                    "price_impact_pct": quote.get("price_impact_pct"),
                }

        cache = rug_watchdog.WatchdogDeepRpcCache(ttl_seconds=60, cooldown_seconds=60)
        quote_engine = FakeQuoteEngine()
        token = {"token_mint": "Mint111", "protection_exit_slippage_bps": 2000}
        prepared_exit = {
            "quote_required": True,
            "token_mint": "Mint111",
            "token_amount_raw": 1000,
            "suggested_sell_pct": 50,
        }

        first = await rug_watchdog.attach_exit_quote_feasibility(quote_engine, dict(prepared_exit), token, cache=cache)
        second = await rug_watchdog.attach_exit_quote_feasibility(quote_engine, dict(prepared_exit), token, cache=cache)

        self.assertEqual(quote_engine.calls, 1)
        self.assertEqual(first["quote_status"], "feasible")
        self.assertEqual(second["quote_status"], "feasible")


class WalletListApplyTests(unittest.TestCase):
    def test_normalizes_only_approved_review_decisions(self):
        decisions = normalize_review_decisions({
            "decisions": [
                {"wallet": "Promote111", "decision": "approve_promotion", "approved": True},
                {"wallet": "Ignore111", "decision": "approve_promotion", "approved": False},
                {"wallet": "Demote111", "decision": "approve_demotion", "approved": True},
            ]
        })

        self.assertEqual(set(decisions), {"Promote111", "Demote111"})
        self.assertEqual(decisions["Promote111"]["decision"], "approve_promotion")

    def test_build_tracked_wallet_row_preserves_axiom_shape(self):
        row = build_tracked_wallet_row("Wallet111", source="paper_watch", name="alpha")

        self.assertEqual(row["trackedWalletAddress"], "Wallet111")
        self.assertEqual(row["name"], "alpha")
        self.assertIn("MemeTraderPro", row["groups"])
        self.assertTrue(row["alertsOnFeed"])

    def test_apply_promotions_and_demotions_with_audit(self):
        result = apply_wallet_review_decisions(
            tracked_wallets=[
                {"trackedWalletAddress": "Keep111", "name": "keep", "groups": ["Main"]},
                {"trackedWalletAddress": "Demote111", "name": "bad", "groups": ["Main"]},
            ],
            paper_watch_wallets={
                "wallets": [
                    {"wallet": "Promote111", "status": "paper_watch", "source": "candidate_wallet_discovery"},
                ]
            },
            bad_wallets=[],
            review_decisions={
                "decisions": [
                    {"wallet": "Promote111", "decision": "approve_promotion", "approved": True, "note": "repeat winner"},
                    {"wallet": "Demote111", "decision": "approve_demotion", "approved": True, "note": "bad avg pnl"},
                ]
            },
            lifecycle_report={
                "wallets": [
                    {"wallet": "Promote111", "source": "paper_watch", "lifecycle": {"action": "PROMOTE_TO_TRUSTED_REVIEW", "metrics": {"total_pnl": 100}}},
                    {"wallet": "Demote111", "source": "tracked", "lifecycle": {"action": "DEMOTE_OFF_WATCH_REVIEW", "metrics": {"total_pnl": -50}}},
                ]
            },
            applied_at=123,
            dry_run=False,
        )

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["summary"]["promoted"], 1)
        self.assertEqual(result["summary"]["demoted"], 1)
        tracked = {row["trackedWalletAddress"] for row in result["tracked_wallets"]}
        self.assertEqual(tracked, {"Keep111", "Promote111"})
        self.assertEqual(result["paper_watch_wallets"]["wallets"][0]["status"], "promoted_to_tracked")
        self.assertEqual(result["bad_wallets"], ["Demote111"])
        self.assertEqual(result["audit"]["changes"][0]["action"], "promoted_to_tracked")

    def test_promotion_requires_lifecycle_and_paper_watch_evidence(self):
        result = apply_wallet_review_decisions(
            tracked_wallets=[],
            paper_watch_wallets={"wallets": []},
            bad_wallets=[],
            review_decisions={
                "decisions": [
                    {"wallet": "Random111", "decision": "approve_promotion", "approved": True},
                ]
            },
            lifecycle_report={"wallets": []},
            dry_run=False,
        )

        self.assertEqual(result["summary"]["promoted"], 0)
        self.assertEqual(result["summary"]["skipped"], 1)
        self.assertEqual(result["audit"]["skipped"][0]["reason"], "missing promotion evidence")

    def test_dry_run_does_not_change_lists(self):
        tracked = [{"trackedWalletAddress": "Demote111", "name": "bad"}]
        result = apply_wallet_review_decisions(
            tracked_wallets=tracked,
            paper_watch_wallets={"wallets": []},
            bad_wallets=[],
            review_decisions={"decisions": [{"wallet": "Demote111", "decision": "approve_demotion", "approved": True}]},
            lifecycle_report={"wallets": []},
            dry_run=True,
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["tracked_wallets"], tracked)
        self.assertEqual(result["summary"]["demoted"], 1)

    def test_wallet_apply_uses_single_lock_and_unique_backup_stamps(self):
        locks = []
        with TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            for name, value in {
                "TRACKED_WALLETS": "tracked_wallets.json",
                "PAPER_WATCH_WALLETS": "paper_watch_wallets.json",
                "CANDIDATE_WALLETS": "candidate_wallets.json",
                "WALLET_PERFORMANCE": "wallet_performance.json",
                "BAD_WALLETS": "bad_wallets.json",
                "REVIEW_DECISIONS": "wallet_review_decisions.json",
                "AUDIT_FILE": "wallet_list_update_audit.json",
            }.items():
                setattr(apply_wallet_review, name, tmp_root / value)
            apply_wallet_review.ARCHIVE_DIR = tmp_root / "archives"

            class FakeLock:
                def __init__(self, path):
                    self.path = Path(path)

                def __enter__(self):
                    locks.append(self.path.name)
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

            with mock.patch.object(apply_wallet_review, "JsonFileLock", FakeLock):
                first = apply_wallet_review.run_apply(dry_run=True)
                second = apply_wallet_review.run_apply(dry_run=True)

        self.assertIn("wallet_review_apply.lock", locks)
        self.assertNotEqual(first["stamp"], second["stamp"])


class WalletDiscoverySchedulerTests(unittest.TestCase):
    def test_scheduler_cycle_refreshes_review_files_without_applying_wallet_lists(self):
        writes = {}
        statuses = []
        candidate_report = {
            "mode": "WATCH_ONLY_REVIEW",
            "candidates": [{"wallet": "WalletCandidate", "review": {"action": "PAPER_WATCH"}}],
        }
        paper_watch_report = {
            "mode": "PAPER_WATCH_ONLY",
            "wallets": [{"wallet": "WalletCandidate", "status": "paper_watch"}],
            "summary": {"paper_watch_wallets": 1},
        }
        apply_result = {
            "dry_run": True,
            "summary": {"promoted": 0, "demoted": 1, "skipped": 0, "approved_decisions": 1},
            "audit": {"changes": [{"wallet": "WalletBad", "action": "demoted_from_tracked"}], "skipped": []},
        }

        summary = run_wallet_discovery_cycle(
            discover=lambda: candidate_report,
            sync_paper_watch=lambda: paper_watch_report,
            build_behavior=lambda: {"mode": "WALLET_BEHAVIOR_REVIEW", "wallets": {"WalletCandidate": {"labels": ["early-buyer"]}}},
            apply_preview=lambda dry_run=True: apply_result,
            write_json=lambda path, payload: writes.__setitem__(Path(path).name, payload),
            update_status=lambda component, **fields: statuses.append((component, fields)),
            now=lambda: 123,
        )

        self.assertEqual(writes["candidate_wallets.json"], candidate_report)
        self.assertEqual(writes["paper_watch_wallets.json"], paper_watch_report)
        self.assertEqual(writes["wallet_behavior.json"]["mode"], "WALLET_BEHAVIOR_REVIEW")
        self.assertEqual(writes["wallet_discovery_status.json"]["mode"], "WALLET_DISCOVERY_SCHEDULER")
        self.assertTrue(summary["live_execution_locked"])
        self.assertFalse(summary["mutates_tracked_wallets"])
        self.assertTrue(summary["apply_preview"]["dry_run"])
        self.assertEqual(summary["candidate_wallets"], 1)
        self.assertEqual(summary["paper_watch_wallets"], 1)
        self.assertEqual(statuses[-1][0], "wallet_discovery")
        self.assertEqual(statuses[-1][1]["status"], "cycle_ok")


class WalletBehaviorTests(unittest.TestCase):
    def test_builds_rolling_wallet_stats_and_behavior_labels(self):
        now = 1_000_000
        paper_state = {
            "closed_trades": [
                {"wallets": ["Winner"], "pnl_pct": 40, "entry_time": now - 1000, "close_time": now - 400},
                {"wallets": ["Winner"], "pnl_pct": 20, "entry_time": now - 2000, "close_time": now - 1200},
                {"wallets": ["Winner"], "pnl_pct": -5, "entry_time": now - 3000, "close_time": now - 2500},
                {"wallets": ["LateExit"], "pnl_pct": 4, "entry_time": now - 5000, "close_time": now - 100},
                {"wallets": ["Trap"], "pnl_pct": -30, "entry_time": now - 2000, "close_time": now - 1800},
                {"wallets": ["Trap"], "pnl_pct": -15, "entry_time": now - 4000, "close_time": now - 3800},
                {"wallets": ["OldWinner"], "pnl_pct": 60, "entry_time": now - (20 * 86400), "close_time": now - (20 * 86400) + 100},
            ]
        }
        performance = {
            "wallets": {
                "Winner": {"signals": 12, "paper_entries": 3},
                "LateExit": {"signals": 5, "paper_entries": 1},
                "Trap": {"signals": 200, "paper_entries": 2},
                "OldWinner": {"signals": 2, "paper_entries": 1},
            },
            "signals": [
                {"wallets": ["Winner"], "token_age_seconds": 35, "time": now - 100},
                {"wallets": ["Winner"], "token_age_seconds": 55, "time": now - 200},
                {"wallets": ["LateExit"], "token_age_seconds": 500, "time": now - 100},
            ],
        }

        report = build_wallet_behavior_report(performance=performance, paper_state=paper_state, now=now)
        wallets = report["wallets"]

        self.assertEqual(wallets["Winner"]["rolling"]["7d"]["entries"], 3)
        self.assertGreater(wallets["Winner"]["rolling"]["7d"]["avg_pnl"], 18)
        self.assertIn("paper-profitable", wallets["Winner"]["labels"])
        self.assertIn("early-buyer", wallets["Winner"]["labels"])
        self.assertIn("late-exit", wallets["LateExit"]["labels"])
        self.assertIn("follower-trap", wallets["Trap"]["labels"])
        self.assertEqual(wallets["OldWinner"]["rolling"]["7d"]["entries"], 0)
        self.assertEqual(wallets["OldWinner"]["rolling"]["30d"]["entries"], 1)

    def test_builds_per_wallet_postmortem_rollup_from_paper_trades(self):
        now = 1_000_000
        paper_state = {
            "closed_trades": [
                {
                    "mint": "MintWin",
                    "wallets": ["WalletPost"],
                    "total_pnl_pct": 45,
                    "entry_time": now - 500,
                    "close_time": now - 200,
                    "exit_reason": "target_profit",
                },
                {
                    "mint": "MintLoss",
                    "wallets": ["WalletPost"],
                    "total_pnl_pct": -18,
                    "entry_time": now - 300,
                    "close_time": now - 240,
                    "close_reason": "watchdog_exit",
                },
            ],
            "failed_trades": [
                {
                    "token_mint": "MintFail",
                    "wallets": ["WalletPost"],
                    "failure_reason": "quote_failed",
                    "time": now - 100,
                }
            ],
        }

        report = build_wallet_behavior_report(
            performance={"wallets": {"WalletPost": {"signals": 4, "paper_entries": 2}}},
            paper_state=paper_state,
            now=now,
        )

        postmortem = report["wallets"]["WalletPost"]["postmortem"]
        self.assertEqual(postmortem["closed_trades"], 2)
        self.assertEqual(postmortem["failed_trades"], 1)
        self.assertEqual(postmortem["best_trade"]["mint"], "MintWin")
        self.assertEqual(postmortem["worst_trade"]["mint"], "MintLoss")
        self.assertEqual(postmortem["exit_reasons"]["target_profit"], 1)
        self.assertEqual(postmortem["exit_reasons"]["watchdog_exit"], 1)
        self.assertEqual(postmortem["failure_reasons"]["quote_failed"], 1)
        self.assertEqual(postmortem["avg_hold_seconds"], 180)


class ProtectionExitPlannerTests(unittest.TestCase):
    def test_missing_amount_blocks_quote_check(self):
        plan = ProtectionExitPlanner().plan({
            "token_mint": "Mint111",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "alert_level": "emergency",
        })

        self.assertEqual(plan["action"], "PREPARE_FULL_EXIT")
        self.assertEqual(plan["quote_status"], "amount_missing")
        self.assertFalse(plan["live_action_allowed"])

    def test_decimal_amount_resolves_to_raw_amount(self):
        plan = ProtectionExitPlanner().plan({
            "token_mint": "Mint111",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "alert_level": "emergency",
            "token_amount": 12.5,
            "token_decimals": 6,
        })

        self.assertEqual(plan["quote_status"], "pending")
        self.assertEqual(plan["token_amount_raw"], 12_500_000)
        self.assertFalse(plan["live_action_allowed"])

    def test_manual_amount_patch_converts_decimal_amount(self):
        patch = build_manual_amount_patch(token_amount="12.5", token_decimals="6")

        self.assertEqual(patch["token_amount"], 12.5)
        self.assertEqual(patch["token_decimals"], 6)
        self.assertEqual(patch["token_amount_raw"], 12_500_000)
        self.assertEqual(patch["token_amount_source"], "operator_manual")
        self.assertEqual(patch["wallet_balance_status"], "manual_amount")

    def test_test_amount_patch_is_clearly_marked(self):
        patch = build_manual_amount_patch(token_amount="12.5", token_decimals="6", test_amount=True)

        self.assertEqual(patch["token_amount_raw"], 12_500_000)
        self.assertEqual(patch["token_amount_source"], "operator_test_amount")
        self.assertEqual(patch["wallet_balance_status"], "test_amount")
        self.assertTrue(patch["test_amount"])
        self.assertIn("Test amount only", patch["amount_safety_note"])

    def test_manual_amount_patch_rejects_missing_decimals(self):
        with self.assertRaises(ValueError):
            build_manual_amount_patch(token_amount="12.5")

    def test_apply_manual_amount_updates_matching_watchlist_item(self):
        rows = [{
            "token_mint": "Mint111",
            "wallet": "",
            "prepared_exit": {
                "quote_status": "amount_missing",
                "quote_reason": "manual_position_token_amount_missing",
            },
        }]

        updated = apply_manual_amount_to_watchlist(
            rows,
            mint="Mint111",
            token_amount="12.5",
            token_decimals="6",
        )

        self.assertEqual(updated[0]["token_amount_raw"], 12_500_000)
        self.assertEqual(updated[0]["prepared_exit"]["quote_status"], "pending")
        self.assertEqual(updated[0]["prepared_exit"]["quote_reason"], "ready_for_route_check")
        self.assertEqual(updated[0]["prepared_exit"]["token_amount_source"], "operator_manual")

    def test_apply_test_amount_marks_prepared_exit_as_test_only(self):
        rows = [{
            "token_mint": "Mint111",
            "wallet": "",
            "prepared_exit": {
                "quote_status": "amount_missing",
                "quote_reason": "manual_position_token_amount_missing",
            },
        }]

        updated = apply_manual_amount_to_watchlist(
            rows,
            mint="Mint111",
            token_amount="12.5",
            token_decimals="6",
            test_amount=True,
        )

        self.assertTrue(updated[0]["test_amount"])
        self.assertEqual(updated[0]["token_amount_source"], "operator_test_amount")
        self.assertEqual(updated[0]["prepared_exit"]["token_amount_reason"], "operator_test_amount_present")
        self.assertTrue(updated[0]["prepared_exit"]["test_amount"])


class TokenInspectorTests(unittest.TestCase):
    def test_permanent_delegate_hard_blocks_token_2022(self):
        account_info = {
            "result": {
                "value": {
                    "owner": TOKEN_2022_PROGRAM,
                    "data": {
                        "program": "spl-token-2022",
                        "parsed": {
                            "info": {
                                "extensions": [
                                    {"extension": "permanentDelegate"},
                                ],
                            },
                        },
                    },
                },
            },
        }

        result = TokenInspector().analyze_account_info("Mint111", account_info)
        self.assertTrue(result["hard_block"])
        self.assertEqual(result["risk_label"], "BLOCKED")

    def test_metadata_only_token_2022_passes(self):
        account_info = {
            "result": {
                "value": {
                    "owner": TOKEN_2022_PROGRAM,
                    "data": {
                        "program": "spl-token-2022",
                        "parsed": {
                            "info": {
                                "extensions": [
                                    {"extension": "metadataPointer"},
                                    {"extension": "tokenMetadata"},
                                ],
                            },
                        },
                    },
                },
            },
        }

        result = TokenInspector().analyze_account_info("Mint111", account_info)
        self.assertFalse(result["hard_block"])
        self.assertEqual(result["risk_label"], "PASS")


class HolderConcentrationTests(unittest.TestCase):
    def test_top_holder_concentration_flags_danger(self):
        result = analyze_holder_concentration([
            {"owner": "a", "amount": 80},
            {"owner": "b", "amount": 10},
            {"owner": "c", "amount": 10},
        ])

        self.assertEqual(result["risk_label"], "DANGER")
        self.assertFalse(result["hard_block"])

    def test_balanced_holders_pass(self):
        result = analyze_holder_concentration([
            {"owner": f"holder_{i}", "amount": 1}
            for i in range(30)
        ])

        self.assertEqual(result["risk_label"], "PASS")
        self.assertEqual(result["metrics"]["holder_count"], 30)


class WalletBalanceParsingTests(unittest.TestCase):
    def test_owner_token_balance_parser_sums_accounts(self):
        response = {
            "result": {
                "value": [
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "tokenAmount": {
                                            "amount": "100",
                                            "uiAmount": 0.0001,
                                            "decimals": 6,
                                        },
                                    },
                                },
                            },
                        },
                    },
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "tokenAmount": {
                                            "amount": "200",
                                            "uiAmount": 0.0002,
                                            "decimals": 6,
                                        },
                                    },
                                },
                            },
                        },
                    },
                ],
            },
        }

        parsed = parse_owner_token_balance(response)
        self.assertEqual(parsed["amount_raw"], 300)
        self.assertAlmostEqual(parsed["ui_amount"], 0.0003)
        self.assertEqual(parsed["decimals"], 6)
        self.assertTrue(parsed["has_balance"])

    def test_no_balance_lookup_preserves_manual_amount(self):
        token = {
            "token_amount": 12.5,
            "token_amount_raw": 12_500_000,
            "token_amount_source": "manual",
        }

        apply_wallet_balance_result(token, {
            "has_balance": False,
            "account_count": 0,
            "amount_raw": 0,
            "ui_amount": 0,
            "decimals": 6,
        })

        self.assertEqual(token["wallet_balance_status"], "no_balance")
        self.assertEqual(token["token_amount"], 12.5)
        self.assertEqual(token["token_amount_raw"], 12_500_000)
        self.assertEqual(token["token_amount_source"], "manual")


class CatalystCardTests(unittest.TestCase):
    def test_builds_card_from_scanner_and_paper_snapshots(self):
        cards = build_catalyst_cards_from_snapshots([
            {
                "time": 1,
                "source": "scanner",
                "context": "scanner_entry_candidate",
                "mint": "Mint111",
                "wallet_count": 2,
                "weighted_wallet_score": 3.2,
                "social_matched": True,
                "social_account": "elonmusk",
                "social_keywords": ["doge"],
                "edge_verdict": "TRADEABLE_EDGE",
                "edge_score": 74,
                "total_score": 82,
                "risk_label": "SAFE",
            },
            {
                "time": 2,
                "source": "paper_trader",
                "context": "paper_exit_closed",
                "mint": "Mint111",
                "status": "closed",
                "total_pnl": 12.5,
                "total_pnl_pct": 25,
            },
        ], generated_at=3)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["mint"], "Mint111")
        self.assertEqual(cards[0]["outcome"]["status"], "closed")
        self.assertTrue(cards[0]["social"]["matched"])
        self.assertIn("scanner_entry_candidate", cards[0]["contexts"])


class PaperTraderPnlTests(unittest.TestCase):
    def test_update_pnl_rejects_impossible_paper_value(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = NoopStore()
                trader.wallet_performance = NoopWalletPerformance()

                trade = {
                    "mint": "MintImpossible",
                    "token_mint": "MintImpossible",
                    "status": "open",
                    "entry_price": 1,
                    "current_price": 1,
                    "size_usd": 45,
                    "entry_fee_usd": 0.05,
                    "realized_pnl": 0,
                    "remaining_token_amount": 1_500_000,
                    "initial_token_amount": 45,
                    "remaining_pct": 100,
                }

                updated = trader.update_pnl(trade)

                self.assertFalse(updated)
                self.assertEqual(trade["status"], "invalid")
                self.assertIn("paper_value_sanity", trade["invalid_reason"])
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_update_price_quarantines_invalid_trade_without_selling(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = NoopStore()
                trader.wallet_performance = NoopWalletPerformance()
                trade = {
                    "mint": "MintInvalid",
                    "token_mint": "MintInvalid",
                    "status": "open",
                    "entry_price": 1,
                    "current_price": 1,
                    "size_usd": 45,
                    "entry_fee_usd": 0.05,
                    "realized_pnl": 0,
                    "remaining_token_amount": 1_500_000,
                    "initial_token_amount": 45,
                    "remaining_pct": 100,
                }
                trader.state["open_trades"] = [trade]

                updated = trader.update_price("MintInvalid", 3, liquidity_usd=100_000)

                self.assertEqual(updated["status"], "invalid")
                self.assertEqual(updated.get("sells", []), [])
                self.assertEqual(updated["remaining_pct"], 100)
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_open_trade_pnl_keeps_entry_fee_after_price_update(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = NoopStore()
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False

                trade = trader.open_trade(
                    "MintFee",
                    entry_price=1,
                    size_usd=100,
                    liquidity_usd=100_000,
                    reason="fee regression",
                )
                self.assertIsNotNone(trade)
                entry_fee = float(trade["entry_fee_usd"])
                self.assertGreater(entry_fee, 0)

                updated = trader.update_price("MintFee", trade["entry_price"], liquidity_usd=100_000)

                self.assertAlmostEqual(updated["total_pnl"], -entry_fee, places=8)
                self.assertAlmostEqual(updated["pnl"], -entry_fee, places=8)
                self.assertLess(updated["total_pnl_pct"], 0)
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_update_price_records_chart_snapshot_for_live_monitoring(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                store = RecordingStore()
                trader.store = store
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False

                trade = trader.open_trade(
                    "MintChart",
                    entry_price=1,
                    size_usd=100,
                    liquidity_usd=100_000,
                    reason="chart snapshot regression",
                    market_info={"price": 1, "liquidity": 100_000, "market_cap": 1_000_000},
                )
                self.assertIsNotNone(trade)
                store.snapshots.clear()

                trader.update_price(
                    "MintChart",
                    1.25,
                    liquidity_usd=125_000,
                    market_info={"price": 1.25, "liquidity": 125_000, "market_cap": 1_250_000},
                )

                self.assertEqual(len(store.snapshots), 1)
                self.assertEqual(store.snapshots[0]["context"], "paper_price_update")
                self.assertEqual(store.snapshots[0]["mint"], "MintChart")
                self.assertEqual(store.snapshots[0]["price"], 1.25)
                self.assertEqual(store.snapshots[0]["market_cap"], 1_250_000)
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_open_trade_records_paper_lane_for_exploration(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = NoopStore()
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False

                trade = trader.open_trade(
                    "MintExplore",
                    entry_price=1,
                    size_usd=10,
                    liquidity_usd=100_000,
                    reason="exploration_entry",
                    paper_lane="exploration",
                    exploration=True,
                    signal_metadata={"paper_lane": "exploration"},
                )

                self.assertIsNotNone(trade)
                self.assertEqual(trade["paper_lane"], "exploration")
                self.assertTrue(trade["exploration"])
                self.assertEqual(trade["signal_metadata"]["paper_lane"], "exploration")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_open_trade_promotes_decision_id_to_canonical_trade_fields(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                store = RecordingStore()
                trader.store = store
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False

                trade = trader.open_trade(
                    "MintLineageOpen",
                    entry_price=1,
                    size_usd=10,
                    liquidity_usd=100_000,
                    reason="lineage_entry",
                    signal_metadata={"decision_id": "dec_open_lineage", "paper_lane": "main"},
                )

                self.assertIsNotNone(trade)
                self.assertEqual(trade.get("decision_id"), "dec_open_lineage")
                self.assertEqual(trade["signal_metadata"]["decision_id"], "dec_open_lineage")
                self.assertEqual(store.snapshots[-1]["decision_id"], "dec_open_lineage")
                self.assertEqual(store.decision_actions[-1]["decision_id"], "dec_open_lineage")
                self.assertEqual(store.decision_actions[-1]["action"]["final_action"], "paper_opened")
                self.assertEqual(store.decision_results[-1]["decision_id"], "dec_open_lineage")
                self.assertEqual(store.decision_results[-1]["result"]["decision_id"], "dec_open_lineage")
                self.assertEqual(store.decision_results[-1]["result"]["trade_status"], "open")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_failed_buy_records_canonical_failure_fields(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = NoopStore()
                trader.wallet_performance = NoopWalletPerformance()

                with mock.patch.object(
                    trader.engine,
                    "simulate_buy_fill",
                    return_value={"success": False, "reason": "slippage_too_high", "fee_usd": 0.05},
                ):
                    trade = trader.open_trade(
                        "MintFail",
                        entry_price=1,
                        size_usd=10,
                        liquidity_usd=1,
                        reason="failed_entry",
                    )

                self.assertIsNone(trade)
                failed = trader.state["failed_trades"][0]
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["failure_reason"], "slippage_too_high")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_failed_buy_promotes_decision_id_and_updates_failure_result(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                store = RecordingStore()
                trader.store = store
                trader.wallet_performance = NoopWalletPerformance()

                with mock.patch.object(
                    trader.engine,
                    "simulate_buy_fill",
                    return_value={"success": False, "reason": "slippage_too_high", "fee_usd": 0.05},
                ):
                    trade = trader.open_trade(
                        "MintLineageFail",
                        entry_price=1,
                        size_usd=10,
                        liquidity_usd=1,
                        reason="failed_entry",
                        signal_metadata={"decision_id": "dec_failed_lineage", "paper_lane": "main"},
                    )

                self.assertIsNone(trade)
                failed = trader.state["failed_trades"][0]
                self.assertEqual(failed.get("decision_id"), "dec_failed_lineage")
                self.assertEqual(failed["signal_metadata"]["decision_id"], "dec_failed_lineage")
                self.assertEqual(store.snapshots[-1]["decision_id"], "dec_failed_lineage")
                self.assertEqual(store.decision_actions[-1]["action"]["final_action"], "paper_failed")
                self.assertEqual(store.decision_results[-1]["result"]["decision_id"], "dec_failed_lineage")
                self.assertEqual(store.decision_results[-1]["result"]["trade_status"], "failed")
                self.assertEqual(store.decision_results[-1]["result"]["failure_reason"], "slippage_too_high")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_close_sell_failure_updates_decision_lineage(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                store = RecordingStore()
                trader.store = store
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False
                trade = trader.open_trade(
                    "MintLineageCloseFail",
                    entry_price=1,
                    size_usd=10,
                    liquidity_usd=100_000,
                    reason="lineage_entry",
                    signal_metadata={"decision_id": "dec_exit_failed_lineage", "paper_lane": "main"},
                )
                store.snapshots.clear()
                store.decision_actions.clear()
                store.decision_results.clear()

                with mock.patch.object(
                    trader.engine,
                    "simulate_sell_fill",
                    return_value={"success": False, "reason": "exit_slippage"},
                ):
                    closed = trader.close_trade(trade, 0.8, 1, "hard_stop_loss")

                self.assertFalse(closed)
                self.assertTrue(store.snapshots)
                self.assertEqual(store.snapshots[-1]["context"], "paper_exit_failed")
                self.assertEqual(store.snapshots[-1]["decision_id"], "dec_exit_failed_lineage")
                self.assertTrue(store.decision_actions)
                self.assertEqual(store.decision_actions[-1]["action"]["final_action"], "paper_exit_failed")
                self.assertEqual(store.decision_results[-1]["result"]["decision_id"], "dec_exit_failed_lineage")
                self.assertEqual(store.decision_results[-1]["result"]["failure_reason"], "exit_slippage")
                self.assertEqual(store.decision_results[-1]["result"]["exit_reason"], "hard_stop_loss")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file


class FastPositionMonitorTests(unittest.TestCase):
    def test_fast_position_evaluation_flags_warning_without_deep_checks(self):
        from core.fast_position_monitor import evaluate_fast_position

        row = evaluate_fast_position(
            {
                "mint": "MintFast",
                "entry_price": 1.0,
                "current_price": 1.0,
                "entry_liquidity_usd": 10_000,
                "current_liquidity_usd": 10_000,
            },
            {
                "price": 0.82,
                "liquidity": 6_500,
                "market_cap": 82_000,
                "source": "jupiter+dexscreener",
            },
        )

        self.assertEqual(row["mint"], "MintFast")
        self.assertEqual(row["risk_level"], "WARNING")
        self.assertEqual(row["price_from_entry_pct"], -18.0)
        self.assertEqual(row["liquidity_from_entry_pct"], -35.0)
        self.assertFalse(row["deep_checks_ran"])
        self.assertIn("cheap_market_only", row["monitor_mode"])

    def test_fast_monitor_cycle_updates_open_paper_trade_price(self):
        from core.fast_position_monitor import run_fast_monitor_cycle

        class FakeMarketChecker:
            async def get_token_info(self, mint):
                return {
                    "price": 0.9,
                    "liquidity": 80_000,
                    "market_cap": 900_000,
                    "source": "jupiter+dexscreener",
                }

        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                trader = paper_trader.PaperTrader()
                trader.store = RecordingStore()
                trader.wallet_performance = NoopWalletPerformance()
                trader.engine.config["simulate_failed_fills"] = False
                trade = trader.open_trade(
                    "MintFastCycle",
                    entry_price=1,
                    size_usd=10,
                    liquidity_usd=100_000,
                    reason="fast_monitor_cycle",
                    signal_metadata={"decision_id": "dec_fast_monitor"},
                )
                trader.store.snapshots.clear()

                summary = asyncio.run(run_fast_monitor_cycle(
                    paper_trader=trader,
                    market_checker=FakeMarketChecker(),
                    timeout=1,
                ))

                updated = trader.find_open_trade("MintFastCycle")
                self.assertEqual(summary["checked_count"], 1)
                self.assertEqual(summary["rows"][0]["mint"], "MintFastCycle")
                self.assertEqual(updated["current_price"], 0.9)
                self.assertEqual(updated["current_liquidity_usd"], 80_000)
                self.assertEqual(trader.store.snapshots[-1]["context"], "paper_price_update")
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file


class ScannerCandidateFilterTests(unittest.TestCase):
    def test_paper_exploration_lifts_safe_near_miss_as_separate_lane(self):
        decision = {
            "should_trade": False,
            "score": 58,
            "threshold": 68,
            "reasons": ["confirmation threshold not met"],
        }

        result = evaluate_paper_exploration(
            decision=decision,
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_score_threshold": 52,
                "paper_exploration_size_usd": 10,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True},
            sell_quote_analysis={"pass": True},
            edge_result={"paper_trade_worthy": False, "edge_score": 10},
            position_size_usd=30,
        )

        self.assertTrue(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "exploration")
        self.assertTrue(result["decision"]["exploration"]["enabled"])
        self.assertEqual(result["position_size_usd"], 10)
        self.assertIn("PAPER EXPLORATION", result["decision"]["reasons"][-1])

    def test_paper_exploration_does_not_override_hard_risk_block(self):
        result = evaluate_paper_exploration(
            decision={"should_trade": False, "score": 90, "threshold": 68, "reasons": []},
            settings={"paper_exploration_enabled": True, "paper_exploration_score_threshold": 52},
            rug_result={"hard_block": True},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True},
            sell_quote_analysis={"pass": True},
            edge_result={"paper_trade_worthy": True, "edge_score": 99},
            position_size_usd=30,
        )

        self.assertFalse(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "main")
        self.assertEqual(result["decision"]["exploration"]["reason"], "hard_risk_block")

    def test_paper_exploration_does_not_override_exit_liquidity_block(self):
        result = evaluate_paper_exploration(
            decision={"should_trade": False, "score": 90, "threshold": 68, "reasons": []},
            settings={"paper_exploration_enabled": True, "paper_exploration_score_threshold": 52},
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True},
            sell_quote_analysis={"pass": False, "reason": "no route"},
            edge_result={"paper_trade_worthy": True, "edge_score": 99},
            position_size_usd=30,
        )

        self.assertFalse(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "main")
        self.assertEqual(result["decision"]["exploration"]["reason"], "exit_liquidity_block")

    def test_paper_exploration_can_sample_strong_route_failed_observation(self):
        result = evaluate_paper_exploration(
            decision={"should_trade": False, "score": 92, "threshold": 68, "reasons": []},
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_route_failed_enabled": True,
                "paper_exploration_route_failed_score_threshold": 70,
                "paper_exploration_route_failed_min_edge_score": 65,
                "paper_exploration_route_failed_size_usd": 5,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True, "reason": "quote_passed"},
            sell_quote_analysis={"pass": False, "reason": "no_exit_route"},
            edge_result={"paper_trade_worthy": True, "edge_score": 88},
            position_size_usd=0,
        )

        decision = result["decision"]
        self.assertTrue(decision["should_trade"])
        self.assertTrue(decision["paper_should_trade"])
        self.assertFalse(decision["live_should_trade"])
        self.assertEqual(decision["paper_lane"], "exploration")
        self.assertEqual(decision["exploration"]["reason"], "route_failed_observation")
        self.assertTrue(decision["exploration"]["route_observation_only"])
        self.assertEqual(result["position_size_usd"], 5)
        self.assertIn("ROUTE OBSERVATION", decision["reasons"][-1])

    def test_paper_exploration_route_failed_observation_requires_strong_signal(self):
        result = evaluate_paper_exploration(
            decision={"should_trade": False, "score": 58, "threshold": 68, "reasons": []},
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_route_failed_enabled": True,
                "paper_exploration_route_failed_score_threshold": 70,
                "paper_exploration_route_failed_min_edge_score": 65,
                "paper_exploration_route_failed_size_usd": 5,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": False, "reason": "no_buy_route"},
            sell_quote_analysis={"pass": False, "reason": "no_exit_route"},
            edge_result={"paper_trade_worthy": False, "edge_score": 52},
            position_size_usd=0,
        )

        self.assertFalse(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "main")
        self.assertEqual(result["decision"]["exploration"]["reason"], "buy_quote_block")

    def test_paper_exploration_does_not_sample_when_quote_was_budget_skipped(self):
        result = evaluate_paper_exploration(
            decision={"should_trade": False, "score": 90, "threshold": 68, "reasons": []},
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_route_failed_enabled": True,
                "paper_exploration_route_failed_score_threshold": 70,
                "paper_exploration_route_failed_min_edge_score": 65,
                "paper_exploration_route_failed_size_usd": 5,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": False, "reason": "below_swap_quote_quality_gate"},
            sell_quote_analysis={"pass": False, "reason": "sell_quote_not_checked_below_swap_quote_quality_gate"},
            edge_result={"paper_trade_worthy": True, "edge_score": 90},
            position_size_usd=0,
        )

        self.assertFalse(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "main")
        self.assertEqual(result["decision"]["exploration"]["reason"], "buy_quote_block")

    def test_paper_exploration_can_sample_strong_confirmation_blocked_candidate(self):
        result = evaluate_paper_exploration(
            decision={
                "should_trade": False,
                "score": 78,
                "threshold": 68,
                "reasons": ["CONFIRMATION BLOCK: outside timing window"],
                "confirmation": {"allow": False, "reasons": ["outside timing window"]},
            },
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_confirmation_blocked_enabled": True,
                "paper_exploration_confirmation_score_threshold": 70,
                "paper_exploration_confirmation_min_edge_score": 60,
                "paper_exploration_confirmation_size_usd": 5,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True, "reason": "quote_passed"},
            sell_quote_analysis={"pass": True, "reason": "quote_passed"},
            edge_result={"paper_trade_worthy": False, "edge_score": 58},
            position_size_usd=48,
        )

        decision = result["decision"]
        self.assertTrue(decision["should_trade"])
        self.assertTrue(decision["paper_should_trade"])
        self.assertFalse(decision["live_should_trade"])
        self.assertEqual(decision["paper_lane"], "exploration")
        self.assertEqual(decision["exploration"]["reason"], "confirmation_block_observation")
        self.assertTrue(decision["exploration"]["confirmation_observation_only"])
        self.assertEqual(result["position_size_usd"], 5)

    def test_paper_exploration_confirmation_sample_requires_quote_passes(self):
        result = evaluate_paper_exploration(
            decision={
                "should_trade": False,
                "score": 82,
                "threshold": 68,
                "reasons": ["CONFIRMATION BLOCK: too early"],
                "confirmation": {"allow": False, "reasons": ["too early"]},
            },
            settings={
                "paper_exploration_enabled": True,
                "paper_exploration_confirmation_blocked_enabled": True,
                "paper_exploration_confirmation_score_threshold": 70,
                "paper_exploration_confirmation_min_edge_score": 60,
                "paper_exploration_confirmation_size_usd": 5,
            },
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
            buy_quote_analysis={"pass": True, "reason": "quote_passed"},
            sell_quote_analysis={"pass": False, "reason": "no_exit_route"},
            edge_result={"paper_trade_worthy": True, "edge_score": 82},
            position_size_usd=48,
        )

        self.assertFalse(result["decision"]["should_trade"])
        self.assertEqual(result["decision"]["paper_lane"], "main")
        self.assertEqual(result["decision"]["exploration"]["reason"], "confirmation_block")

    def test_paper_exploration_does_not_override_strategy_or_confirmation_blocks(self):
        for decision in [
            {
                "should_trade": False,
                "score": 90,
                "threshold": 68,
                "reasons": ["STRATEGY GUARD BLOCK: losing family"],
                "strategy_guard": {"action": "BLOCK"},
            },
            {
                "should_trade": False,
                "score": 90,
                "threshold": 68,
                "reasons": ["CONFIRMATION BLOCK: too early"],
                "confirmation": {"allow": False},
            },
        ]:
            result = evaluate_paper_exploration(
                decision=decision,
                settings={"paper_exploration_enabled": True, "paper_exploration_score_threshold": 52},
                rug_result={"hard_block": False},
                market_sanity={"allow": True},
                buy_quote_analysis={"pass": True},
                sell_quote_analysis={"pass": True},
                edge_result={"paper_trade_worthy": True, "edge_score": 99},
                position_size_usd=30,
            )

            self.assertFalse(result["decision"]["should_trade"])
            self.assertFalse(result["decision"]["live_should_trade"])
            self.assertEqual(result["decision"]["paper_lane"], "main")
            self.assertIn("block", result["decision"]["exploration"]["reason"])


class SettingsManagerTests(unittest.TestCase):
    def test_save_settings_parses_string_booleans(self):
        with TemporaryDirectory() as tmpdir:
            original_file = settings_manager.SETTINGS_FILE
            settings_manager.SETTINGS_FILE = Path(tmpdir) / "bot_settings.json"
            try:
                saved = settings_manager.save_settings({
                    "paper_exploration_enabled": "false",
                    "confirmation_require_momentum": "0",
                    "strategy_guard_enabled": "off",
                })

                self.assertFalse(saved["paper_exploration_enabled"])
                self.assertFalse(saved["confirmation_require_momentum"])
                self.assertFalse(saved["strategy_guard_enabled"])
            finally:
                settings_manager.SETTINGS_FILE = original_file

    def test_save_settings_preserves_route_failed_exploration_controls(self):
        with TemporaryDirectory() as tmpdir:
            original_file = settings_manager.SETTINGS_FILE
            settings_manager.SETTINGS_FILE = Path(tmpdir) / "bot_settings.json"
            try:
                saved = settings_manager.save_settings({
                    "paper_exploration_route_failed_enabled": "true",
                    "paper_exploration_route_failed_score_threshold": 74,
                    "paper_exploration_route_failed_min_edge_score": 69,
                    "paper_exploration_route_failed_size_usd": 4,
                })

                self.assertTrue(saved["paper_exploration_route_failed_enabled"])
                self.assertEqual(saved["paper_exploration_route_failed_score_threshold"], 74)
                self.assertEqual(saved["paper_exploration_route_failed_min_edge_score"], 69)
                self.assertEqual(saved["paper_exploration_route_failed_size_usd"], 4)
            finally:
                settings_manager.SETTINGS_FILE = original_file

    def test_save_settings_preserves_confirmation_blocked_exploration_controls(self):
        with TemporaryDirectory() as tmpdir:
            original_file = settings_manager.SETTINGS_FILE
            settings_manager.SETTINGS_FILE = Path(tmpdir) / "bot_settings.json"
            try:
                saved = settings_manager.save_settings({
                    "paper_exploration_confirmation_blocked_enabled": "true",
                    "paper_exploration_confirmation_score_threshold": 71,
                    "paper_exploration_confirmation_min_edge_score": 61,
                    "paper_exploration_confirmation_size_usd": 6,
                })

                self.assertTrue(saved["paper_exploration_confirmation_blocked_enabled"])
                self.assertEqual(saved["paper_exploration_confirmation_score_threshold"], 71)
                self.assertEqual(saved["paper_exploration_confirmation_min_edge_score"], 61)
                self.assertEqual(saved["paper_exploration_confirmation_size_usd"], 6)
            finally:
                settings_manager.SETTINGS_FILE = original_file

    def test_save_settings_preserves_paper_activity_evaluation_controls(self):
        with TemporaryDirectory() as tmpdir:
            original_file = settings_manager.SETTINGS_FILE
            settings_manager.SETTINGS_FILE = Path(tmpdir) / "bot_settings.json"
            try:
                saved = settings_manager.save_settings({
                    "paper_activity_evaluation_enabled": "true",
                    "paper_activity_evaluation_weighted_trigger": 0.8,
                    "paper_activity_evaluation_min_combined_wallet_score": 45,
                })

                self.assertTrue(saved["paper_activity_evaluation_enabled"])
                self.assertEqual(saved["paper_activity_evaluation_weighted_trigger"], 0.8)
                self.assertEqual(saved["paper_activity_evaluation_min_combined_wallet_score"], 45)
            finally:
                settings_manager.SETTINGS_FILE = original_file

    def test_save_settings_preserves_swap_quote_budget_controls(self):
        with TemporaryDirectory() as tmpdir:
            original_file = settings_manager.SETTINGS_FILE
            settings_manager.SETTINGS_FILE = Path(tmpdir) / "bot_settings.json"
            try:
                saved = settings_manager.save_settings({
                    "swap_quote_budget_enabled": "true",
                    "swap_quote_score_threshold": 70,
                    "swap_quote_min_edge_score": 62,
                    "swap_quote_max_requests_per_minute": 12,
                    "swap_quote_budget_window_seconds": 45,
                })

                self.assertTrue(saved["swap_quote_budget_enabled"])
                self.assertEqual(saved["swap_quote_score_threshold"], 70)
                self.assertEqual(saved["swap_quote_min_edge_score"], 62)
                self.assertEqual(saved["swap_quote_max_requests_per_minute"], 12)
                self.assertEqual(saved["swap_quote_budget_window_seconds"], 45)
            finally:
                settings_manager.SETTINGS_FILE = original_file


class ScannerRuntimeTests(unittest.TestCase):
    def test_swap_quote_gate_skips_candidates_below_quote_quality(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.settings.update({
            "swap_quote_budget_enabled": True,
            "swap_quote_score_threshold": 68,
            "swap_quote_min_edge_score": 65,
        })

        allowed, reason = scanner.should_request_swap_quote(
            decision={"score": 52, "strategy_guard": {"action": "ALLOW"}},
            edge_result={"edge_score": 50, "quote_worthy": True},
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "below_swap_quote_quality_gate")

    def test_swap_quote_gate_allows_candidates_near_paper_entry_quality(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.settings.update({
            "swap_quote_budget_enabled": True,
            "swap_quote_score_threshold": 68,
            "swap_quote_min_edge_score": 65,
        })

        allowed, reason = scanner.should_request_swap_quote(
            decision={"score": 69, "strategy_guard": {"action": "ALLOW"}},
            edge_result={"edge_score": 40, "quote_worthy": False},
            rug_result={"hard_block": False},
            market_sanity={"allow": True},
        )

        self.assertTrue(allowed)
        self.assertEqual(reason, "swap_quote_quality_gate_passed")

    def test_swap_quote_budget_blocks_after_configured_request_count(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.settings.update({
            "swap_quote_budget_enabled": True,
            "swap_quote_max_requests_per_minute": 2,
            "swap_quote_budget_window_seconds": 60,
        })

        self.assertTrue(scanner.consume_swap_quote_budget(now=1000))
        self.assertTrue(scanner.consume_swap_quote_budget(now=1001))
        self.assertFalse(scanner.consume_swap_quote_budget(now=1002))
        self.assertTrue(scanner.consume_swap_quote_budget(now=1061))

    def test_paper_activity_evaluation_can_trigger_mid_quality_wallet(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.settings.update({
            "paper_activity_evaluation_enabled": True,
            "paper_activity_evaluation_weighted_trigger": 0.8,
            "paper_activity_evaluation_min_combined_wallet_score": 45,
        })

        self.assertTrue(scanner.should_evaluate_fast(
            wallet_count=1,
            weighted_wallet_score=0.8,
            combined_wallet_score=51,
        ))

    def test_paper_activity_evaluation_keeps_low_quality_wallets_out(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.settings.update({
            "paper_activity_evaluation_enabled": True,
            "paper_activity_evaluation_weighted_trigger": 0.8,
            "paper_activity_evaluation_min_combined_wallet_score": 45,
        })

        self.assertFalse(scanner.should_evaluate_fast(
            wallet_count=1,
            weighted_wallet_score=0.3,
            combined_wallet_score=38,
        ))

    def test_scanner_token_changes_preserve_signature_time_and_sol_delta(self):
        scanner = Scanner(["Tracked111"], None)
        result = {
            "blockTime": 1234,
            "transaction": {
                "signatures": ["Sig111"],
                "message": {
                    "accountKeys": [
                        "Tracked111",
                        "Other111",
                    ],
                },
            },
            "meta": {
                "preBalances": [5_000_000_000, 1],
                "postBalances": [4_500_000_000, 1],
                "preTokenBalances": [
                    {"owner": "Tracked111", "mint": "Mint111pump", "uiTokenAmount": {"uiAmount": 0}},
                    {"owner": "Tracked111", "mint": "So11111111111111111111111111111111111111112", "uiTokenAmount": {"uiAmount": 1}},
                ],
                "postTokenBalances": [
                    {"owner": "Tracked111", "mint": "Mint111pump", "uiTokenAmount": {"uiAmount": 1000}},
                    {"owner": "Tracked111", "mint": "So11111111111111111111111111111111111111112", "uiTokenAmount": {"uiAmount": 0.5}},
                ],
            },
        }

        changes = scanner.extract_token_changes(result, {"Tracked111"})

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["signature"], "Sig111")
        self.assertEqual(changes[0]["block_time"], 1234)
        self.assertEqual(changes[0]["native_delta"], -0.5)
        self.assertEqual(changes[0]["quote_mint"], "So11111111111111111111111111111111111111112")
        self.assertEqual(changes[0]["quote_delta"], -0.5)

    def test_process_event_writes_market_enriched_swap_tick(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                return {
                    "price": 0.002,
                    "market_cap": 2_000_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

        class FakeRpc:
            market_checker = FakeMarketChecker()

        scanner = Scanner(["Tracked111"], FakeRpc())
        scanner.store = RecordingStore()
        scanner.should_evaluate_fast = lambda **_kwargs: False

        with mock.patch("core.scanner.add_event"):
            asyncio.run(scanner.process_event({
                "wallet": "Tracked111",
                "mint": "Mint111pump",
                "delta": 1000,
                "native_delta": 0.0,
                "signature": "Sig111",
                "block_time": 1234,
            }))

        self.assertEqual(len(scanner.store.swap_ticks), 1)
        tick = scanner.store.swap_ticks[0]
        self.assertEqual(tick["signature"], "Sig111")
        self.assertEqual(tick["side"], "buy")
        self.assertEqual(tick["token_amount"], 1000)
        self.assertEqual(tick["sol_amount"], 0.0)
        self.assertEqual(tick["price"], 0.002)
        self.assertEqual(tick["market_cap"], 2_000_000)

    def test_process_event_writes_balance_delta_swap_tick_price_when_quote_side_exists(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                if mint == "So11111111111111111111111111111111111111112":
                    return {"price": 150, "source": "jupiter"}
                return {
                    "price": 0.002,
                    "market_cap": 2_000_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

        class FakeRpc:
            market_checker = FakeMarketChecker()

        scanner = Scanner(["Tracked111"], FakeRpc())
        scanner.store = RecordingStore()
        scanner.should_evaluate_fast = lambda **_kwargs: False

        with mock.patch("core.scanner.add_event"):
            asyncio.run(scanner.process_event({
                "wallet": "Tracked111",
                "mint": "Mint111pump",
                "delta": 1000,
                "native_delta": 0.0,
                "quote_mint": "So11111111111111111111111111111111111111112",
                "quote_delta": -0.5,
                "dex_route_detected": True,
                "dex_route_programs": ["jupiter_v6"],
                "signature": "Sig111",
                "block_time": 1234,
            }))

        self.assertEqual(len(scanner.store.swap_ticks), 1)
        tick = scanner.store.swap_ticks[0]
        self.assertEqual(tick["source"], "wallet_event_dex_route_delta")
        self.assertEqual(tick["quote_mint"], "So11111111111111111111111111111111111111112")
        self.assertEqual(tick["quote_amount"], 0.5)
        self.assertEqual(tick["sol_amount"], 0.5)
        self.assertAlmostEqual(tick["price"], 0.075)
        self.assertEqual(tick["market_cap"], 75_000_000)

    def test_scanner_marks_token_changes_with_dex_route_metadata(self):
        scanner = Scanner(["Tracked111"], None)
        result = {
            "blockTime": 1234,
            "transaction": {
                "signatures": ["Sig111"],
                "message": {
                    "accountKeys": [
                        "Tracked111",
                        {"pubkey": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"},
                    ],
                    "instructions": [
                        {"programId": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"},
                    ],
                },
            },
            "meta": {
                "preBalances": [5_000_000_000, 1],
                "postBalances": [5_000_000_000, 1],
                "preTokenBalances": [
                    {"owner": "Tracked111", "mint": "Mint111pump", "uiTokenAmount": {"uiAmount": 0}},
                    {"owner": "Tracked111", "mint": "So11111111111111111111111111111111111111112", "uiTokenAmount": {"uiAmount": 1}},
                ],
                "postTokenBalances": [
                    {"owner": "Tracked111", "mint": "Mint111pump", "uiTokenAmount": {"uiAmount": 1000}},
                    {"owner": "Tracked111", "mint": "So11111111111111111111111111111111111111112", "uiTokenAmount": {"uiAmount": 0.5}},
                ],
            },
        }

        changes = scanner.extract_token_changes(result, {"Tracked111"})

        self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0]["dex_route_detected"])
        self.assertEqual(changes[0]["dex_route_programs"], ["jupiter_v6"])
        self.assertEqual(changes[0]["quote_mint"], "So11111111111111111111111111111111111111112")

    def test_process_event_uses_dex_route_delta_source_only_when_route_detected(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                if mint == "So11111111111111111111111111111111111111112":
                    return {"price": 150, "source": "jupiter"}
                return {
                    "price": 0.002,
                    "market_cap": 2_000_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

        class FakeRpc:
            market_checker = FakeMarketChecker()

        scanner = Scanner(["Tracked111"], FakeRpc())
        scanner.store = RecordingStore()
        scanner.should_evaluate_fast = lambda **_kwargs: False

        with mock.patch("core.scanner.add_event"):
            asyncio.run(scanner.process_event({
                "wallet": "Tracked111",
                "mint": "Mint111pump",
                "delta": 1000,
                "native_delta": 0.0,
                "quote_mint": "So11111111111111111111111111111111111111112",
                "quote_delta": -0.5,
                "dex_route_detected": True,
                "dex_route_programs": ["jupiter_v6"],
                "signature": "Sig111",
                "block_time": 1234,
            }))

        tick = scanner.store.swap_ticks[0]
        self.assertEqual(tick["source"], "wallet_event_dex_route_delta")
        self.assertEqual(tick["dex_route_programs"], ["jupiter_v6"])
        self.assertAlmostEqual(tick["price"], 0.075)

    def test_process_event_ignores_quote_delta_price_when_no_dex_route_detected(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                if mint == "So11111111111111111111111111111111111111112":
                    return {"price": 150, "source": "jupiter"}
                return {
                    "price": 0.002,
                    "market_cap": 2_000_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

        class FakeRpc:
            market_checker = FakeMarketChecker()

        scanner = Scanner(["Tracked111"], FakeRpc())
        scanner.store = RecordingStore()
        scanner.should_evaluate_fast = lambda **_kwargs: False

        with mock.patch("core.scanner.add_event"):
            asyncio.run(scanner.process_event({
                "wallet": "Tracked111",
                "mint": "Mint111pump",
                "delta": 1000,
                "native_delta": 0.0,
                "quote_mint": "So11111111111111111111111111111111111111112",
                "quote_delta": -0.5,
                "signature": "Sig111",
                "block_time": 1234,
            }))

        tick = scanner.store.swap_ticks[0]
        self.assertEqual(tick["source"], "wallet_event_market_enriched")
        self.assertEqual(tick["price"], 0.002)
        self.assertEqual(tick["market_cap"], 2_000_000)

    def test_tracked_wallet_takes_precedence_over_paper_watch_overlap(self):
        scanner = Scanner(["Tracked111"], None, paper_watch_wallets=["Tracked111", "Watch111"])

        self.assertEqual(scanner.wallet_source("Tracked111"), "tracked")
        self.assertTrue(scanner.wallet_can_drive_live("Tracked111"))
        self.assertEqual(scanner.wallet_source("Watch111"), "paper_watch")

    def test_scanner_uses_configured_jupiter_prescore_threshold(self):
        scanner = Scanner([], None)
        scanner.settings["jupiter_prescore_threshold"] = 55

        self.assertEqual(scanner.jupiter_prescore_threshold(), 55)

    def test_scanner_reruns_signal_when_wallet_hit_arrives_during_evaluation(self):
        scanner = Scanner([], None)
        calls = []

        async def fake_evaluate_once(mint):
            calls.append(mint)
            if len(calls) == 1:
                await scanner.evaluate_signal(mint)

        scanner._evaluate_signal_once = fake_evaluate_once

        asyncio.run(scanner.evaluate_signal("MintRace"))

        self.assertEqual(calls, ["MintRace", "MintRace"])

    def test_runtime_skip_snapshot_keeps_decision_id(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                return {
                    "price": 0.001,
                    "market_cap": 100_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

            def liquidity_score(self, liquidity):
                return 10

            def volume_score(self, volume):
                return 10

        class FakeJupiterQuote:
            async def get_buy_quote(self, **kwargs):
                return {"ok": True, "out_amount": "1000", "routePlan": []}

            async def get_sell_quote(self, **kwargs):
                return {"ok": True, "routePlan": []}

            def analyze_quote(self, quote, max_price_impact_pct):
                return {"pass": True, "reason": "quote_passed", "price_impact_pct": 1.0}

        class FakeRpc:
            market_checker = FakeMarketChecker()
            jupiter_quote = FakeJupiterQuote()

        async def fake_dev_wallet(mint):
            return "Dev111"

        async def fake_token_inspection(rpc, mint):
            return {
                "token_standard": "spl_token",
                "extensions": [],
                "risk_label": "LOW",
                "reasons": [],
            }

        async def fake_launch_info(mint):
            return {"launch_age_seconds": 45}

        async def fake_holder_risk(mint):
            return scanner.skipped_holder_cluster_risk("test skipped")

        scanner = Scanner(["Tracked111"], FakeRpc())
        scanner.store = RecordingStore()
        scanner.paper_trader = None
        scanner.token_buys["MintRuntimeSkip"] = [{"wallet": "Tracked111"}]
        scanner.cluster_threshold = 1
        scanner.find_dev_wallet = fake_dev_wallet
        scanner.dev_analyzer.score_dev = lambda dev_wallet: {"score": 0, "label": "Unknown", "bonded_tokens": 0}
        scanner.token_inspector.inspect_with_rpc = fake_token_inspection
        scanner.token_launch_age.get_launch_info = fake_launch_info
        scanner.token_age.get_age_seconds = lambda mint: 45
        scanner.wallet_quality.score_wallets = lambda wallets: {"avg_score": 80, "max_score": 80}
        scanner.wallet_performance.score_wallets = lambda wallets: {"avg_score": 70, "max_score": 70}
        scanner.wallet_performance.record_signal = lambda **kwargs: None
        scanner.anti_rug.analyze = lambda **kwargs: {
            "risk_label": "LOW_RISK",
            "risk_score": 0,
            "warnings": [],
            "penalties": [],
            "hard_block": False,
            "hard_block_reason": None,
        }
        scanner.scoring_engine.score_token = lambda **kwargs: {
            "score": 80,
            "threshold": 68,
            "mode": "CONFIRMATION",
            "should_trade": True,
            "reasons": ["strong wallet signal"],
        }
        scanner.social_signal.match_token = lambda **kwargs: {
            "matched": False,
            "score_bonus": 0,
            "matched_keywords": [],
            "matched_account": None,
        }
        scanner.edge_analyzer.analyze = lambda **kwargs: {
            "edge_score": 80,
            "edge_verdict": "watch",
            "quote_worthy": True,
            "paper_trade_worthy": True,
            "positives": [],
            "risks": [],
        }
        scanner.evaluate_holder_cluster_risk = fake_holder_risk
        scanner.confirmation_filter.evaluate = lambda **kwargs: {"allow": True, "reasons": [], "warnings": []}
        scanner.position_sizer.size_trade = lambda **kwargs: 25

        with mock.patch("core.scanner.add_alert"), mock.patch("core.scanner.update_token"):
            asyncio.run(scanner._evaluate_signal_once("MintRuntimeSkip"))

        runtime_snapshot = [
            snapshot for snapshot in scanner.store.snapshots
            if snapshot.get("context") == "scanner_runtime_skip"
        ][0]
        decision_id = scanner.store.decisions[0]["decision_id"]
        self.assertEqual(runtime_snapshot["decision_id"], decision_id)
        self.assertEqual(scanner.store.decision_actions[-1]["decision_id"], decision_id)
        self.assertEqual(scanner.store.decision_actions[-1]["action"]["final_action"], "runtime_skip")

    def test_scanner_records_weak_candidate_without_spending_swap_quote(self):
        class FakeMarketChecker:
            async def get_token_info(self, mint):
                return {
                    "price": 0.001,
                    "market_cap": 100_000,
                    "liquidity": 50_000,
                    "source": "jupiter+dexscreener",
                }

            def liquidity_score(self, liquidity):
                return 10

            def volume_score(self, volume):
                return 10

        class FakeJupiterQuote:
            def __init__(self):
                self.buy_calls = 0

            async def get_buy_quote(self, **kwargs):
                self.buy_calls += 1
                return {"ok": True, "out_amount": "1000", "routePlan": []}

            async def get_sell_quote(self, **kwargs):
                return {"ok": True, "routePlan": []}

            def analyze_quote(self, quote, max_price_impact_pct):
                return {"pass": True, "reason": "quote_passed", "price_impact_pct": 1.0}

        class FakeRpc:
            market_checker = FakeMarketChecker()

            def __init__(self):
                self.jupiter_quote = FakeJupiterQuote()

        async def fake_dev_wallet(mint):
            return "Dev111"

        async def fake_token_inspection(rpc, mint):
            return {
                "token_standard": "spl_token",
                "extensions": [],
                "risk_label": "LOW",
                "reasons": [],
            }

        async def fake_launch_info(mint):
            return {"launch_age_seconds": 45}

        async def fake_holder_risk(mint):
            return scanner.skipped_holder_cluster_risk("test skipped")

        rpc = FakeRpc()
        scanner = Scanner(["Tracked111"], rpc)
        scanner.settings.update({
            "swap_quote_budget_enabled": True,
            "swap_quote_score_threshold": 68,
            "swap_quote_min_edge_score": 65,
        })
        scanner.store = RecordingStore()
        scanner.paper_trader = None
        scanner.token_buys["MintWeakQuote"] = [{"wallet": "Tracked111"}]
        scanner.cluster_threshold = 1
        scanner.find_dev_wallet = fake_dev_wallet
        scanner.dev_analyzer.score_dev = lambda dev_wallet: {"score": 0, "label": "Unknown", "bonded_tokens": 0}
        scanner.token_inspector.inspect_with_rpc = fake_token_inspection
        scanner.token_launch_age.get_launch_info = fake_launch_info
        scanner.token_age.get_age_seconds = lambda mint: 45
        scanner.wallet_quality.score_wallets = lambda wallets: {"avg_score": 55, "max_score": 55}
        scanner.wallet_performance.score_wallets = lambda wallets: {"avg_score": 55, "max_score": 55}
        scanner.wallet_performance.record_signal = lambda **kwargs: None
        scanner.anti_rug.analyze = lambda **kwargs: {
            "risk_label": "LOW_RISK",
            "risk_score": 0,
            "warnings": [],
            "penalties": [],
            "hard_block": False,
            "hard_block_reason": None,
        }
        scanner.scoring_engine.score_token = lambda **kwargs: {
            "score": 55,
            "threshold": 68,
            "mode": "CONFIRMATION",
            "should_trade": False,
            "reasons": ["watchable but not entry quality"],
        }
        scanner.social_signal.match_token = lambda **kwargs: {
            "matched": False,
            "score_bonus": 0,
            "matched_keywords": [],
            "matched_account": None,
        }
        scanner.edge_analyzer.analyze = lambda **kwargs: {
            "edge_score": 55,
            "edge_verdict": "watch",
            "quote_worthy": True,
            "paper_trade_worthy": False,
            "positives": [],
            "risks": [],
        }
        scanner.evaluate_holder_cluster_risk = fake_holder_risk
        scanner.confirmation_filter.evaluate = lambda **kwargs: {"allow": True, "reasons": [], "warnings": []}
        scanner.position_sizer.size_trade = lambda **kwargs: 25

        with mock.patch("core.scanner.add_alert"), mock.patch("core.scanner.update_token"):
            asyncio.run(scanner._evaluate_signal_once("MintWeakQuote"))

        self.assertEqual(rpc.jupiter_quote.buy_calls, 0)
        decision_payload = scanner.store.decisions[0]["payload"]
        buy_quote = decision_payload["quotes"]["buy"]
        self.assertFalse(buy_quote["pass"])
        self.assertEqual(buy_quote["reason"], "below_swap_quote_quality_gate")

    def test_scanner_keeps_paper_watch_wallets_in_separate_observed_lane(self):
        scanner = Scanner(["Tracked111"], None, paper_watch_wallets=["Watch111"])

        self.assertTrue(scanner.is_observed_wallet("Tracked111"))
        self.assertTrue(scanner.is_observed_wallet("Watch111"))
        self.assertEqual(scanner.wallet_source("Tracked111"), "tracked")
        self.assertEqual(scanner.wallet_source("Watch111"), "paper_watch")
        self.assertFalse(scanner.wallet_can_drive_live("Watch111"))

    def test_known_major_stable_mint_is_blocked_from_meme_candidates(self):
        scanner = Scanner([], None)

        result = scanner.evaluate_candidate_market_sanity(
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            {
                "symbol": "BTC",
                "name": "Bitcoin",
                "market_cap": 1_500_000_000_000,
                "liquidity": 34_000_000,
            },
        )

        self.assertFalse(result["allow"])
        self.assertIn("known_major_or_stable_mint", result["reasons"])

    def test_oversized_market_is_blocked_from_meme_candidates(self):
        scanner = Scanner([], None)

        result = scanner.evaluate_candidate_market_sanity(
            "MemeMint111",
            {
                "symbol": "MEME",
                "name": "Meme",
                "market_cap": 25_000_000,
                "liquidity": 5_000_000,
            },
        )

        self.assertFalse(result["allow"])
        self.assertIn("market_cap_above_meme_window", result["reasons"])

    def test_pump_style_candidate_in_meme_window_is_allowed(self):
        scanner = Scanner([], None)

        result = scanner.evaluate_candidate_market_sanity(
            "6BeSoAxGFpRBjSvKFa5N9h7EFNsSWBxuMn43KpYZpump",
            {
                "symbol": "BANG",
                "name": "Bang",
                "market_cap": 35_000,
                "liquidity": 18_000,
            },
        )

        self.assertTrue(result["allow"])

    def test_scanner_holder_check_analyzes_largest_token_accounts(self):
        class FakeRpc:
            async def rpc_call(self, method, params):
                return {
                    "result": {
                        "value": [
                            {"address": "Holder111", "uiAmount": 60},
                            {"address": "Holder222", "uiAmount": 20},
                            {"address": "Holder333", "uiAmount": 20},
                        ],
                    },
                }

        scanner = Scanner([], FakeRpc())
        scanner.settings["scanner_holder_check_timeout_seconds"] = 1

        result = asyncio.run(scanner.evaluate_holder_cluster_risk("MintHolderRisk"))

        self.assertEqual(result["holder_concentration_risk"], "DANGER")
        self.assertEqual(result["holder_concentration_metrics"]["holder_count"], 3)
        self.assertEqual(result["holder_concentration_metrics"]["top_1_pct"], 60.0)

    def test_scanner_holder_check_timeout_returns_unknown_evidence(self):
        class SlowRpc:
            async def rpc_call(self, method, params):
                await asyncio.sleep(0.05)
                return {"result": {"value": []}}

        scanner = Scanner([], SlowRpc())
        scanner.settings["scanner_holder_check_timeout_seconds"] = 0.001

        result = asyncio.run(scanner.evaluate_holder_cluster_risk("MintSlow"))

        self.assertEqual(result["holder_concentration_risk"], "UNKNOWN")
        self.assertEqual(result["holder_concentration_reasons"], ["Scanner holder check timed out"])

    def test_scanner_holder_check_is_gated_to_quote_worthy_candidates(self):
        scanner = Scanner([], None)
        scanner.settings["jupiter_prescore_threshold"] = 40

        self.assertFalse(
            scanner.holder_check_candidate_worthy(
                {"score": 31},
                {"quote_worthy": False, "paper_trade_worthy": False},
            )
        )
        self.assertTrue(
            scanner.holder_check_candidate_worthy(
                {"score": 31},
                {"quote_worthy": True, "paper_trade_worthy": False},
            )
        )
        self.assertTrue(
            scanner.holder_check_candidate_worthy(
                {"score": 40},
                {"quote_worthy": False, "paper_trade_worthy": False},
            )
        )

    def test_scanner_linked_wallet_risk_does_not_infer_unavailable_graph(self):
        scanner = Scanner(["Tracked111"], None)

        result = scanner.wallet_cluster_risk_context(
            signal_type="cluster",
            wallets=["Tracked111", "Tracked222"],
            wallet_count=2,
            repeated_buys=1,
        )

        self.assertEqual(result["risk_label"], "NOT_CHECKED")
        self.assertEqual(result["reason"], "no_linked_wallet_graph_source")
        self.assertEqual(result["observed_wallet_cluster"]["wallet_count"], 2)

    def test_holder_danger_elevates_rug_result_to_hard_block(self):
        scanner = Scanner(["Tracked111"], None)
        rug_result = {
            "risk_label": "LOW_RISK",
            "risk_score": 0,
            "warnings": [],
            "penalties": [],
            "hard_block": False,
            "hard_block_reason": None,
        }

        result = scanner.apply_holder_cluster_to_rug_result(
            rug_result=rug_result,
            holder_context={
                "holder_concentration_risk": "DANGER",
                "holder_concentration_reasons": ["Top holder controls at least 50%"],
                "holder_concentration_metrics": {"holder_count": 3},
            },
            cluster_context={"risk_label": "NOT_CHECKED"},
        )

        self.assertTrue(result["hard_block"])
        self.assertEqual(result["risk_label"], "HIGH_RISK")
        self.assertGreaterEqual(result["risk_score"], 22)
        self.assertIn("Holder concentration: Top holder controls at least 50%", result["warnings"])

    def test_record_signal_embeds_holder_cluster_risk_from_rug_result(self):
        scanner = Scanner(["Tracked111"], None)
        scanner.store = RecordingStore()
        decision = {
            "score": 71,
            "threshold": 68,
            "mode": "CONFIRMATION",
            "should_trade": False,
            "reasons": ["Holder concentration block"],
        }
        rug_result = {
            "risk_label": "HIGH_RISK",
            "risk_score": 28,
            "warnings": ["Holder concentration: Top holder controls at least 50%"],
            "hard_block": True,
            "hard_block_reason": "Holder concentration: Top holder controls at least 50%",
            "holder_concentration_risk": "DANGER",
            "holder_concentration_reasons": ["Top holder controls at least 50%"],
            "holder_concentration_metrics": {
                "holder_count": 3,
                "top_1_pct": 60.0,
                "top_10_pct": 100.0,
                "top_holder_address": "Holder111",
            },
            "linked_wallet_risk": {
                "risk_label": "CLUSTER_SIGNAL",
                "cluster_wallet_count": 2,
                "repeated_buys": 1,
            },
        }

        scanner.record_signal(
            mint="MintHolderRisk",
            now=123.0,
            signal_type="cluster",
            wallets=["Tracked111", "Tracked222"],
            wallet_count=2,
            weighted_wallet_score=2.4,
            social_match={},
            wallet_quality={},
            wallet_performance={},
            dev_wallet="Dev111",
            dev_score={"score": 10, "label": "Unknown", "bonded_tokens": 0},
            token_inspection={},
            liquidity_score=5,
            volume_score=4,
            market_info={"price": 0.001, "liquidity": 12000},
            rug_result=rug_result,
            buy_quote_analysis={"pass": False, "reason": "not_checked", "price_impact_pct": None},
            sell_quote_analysis={"pass": False, "reason": "not_checked", "price_impact_pct": None},
            buy_quote=None,
            sell_quote=None,
            position_size_usd=0,
            token_age_seconds=45,
            true_launch_age_seconds=45,
            launch_info={},
            decision=decision,
            edge_result={},
        )

        payload = scanner.store.decisions[0]["payload"]
        holder_cluster = payload["rule_outcomes"]["holder_cluster"]
        self.assertEqual(holder_cluster["holder_risk_label"], "DANGER")
        self.assertEqual(holder_cluster["holder_count"], 3)
        self.assertEqual(holder_cluster["top_1_pct"], 60.0)
        self.assertEqual(holder_cluster["linked_wallet_risk"]["risk_label"], "CLUSTER_SIGNAL")

    def test_duplicate_open_trade_merge_keeps_single_open_mint(self):
        with TemporaryDirectory() as tmpdir:
            original_file = paper_trader.PAPER_TRADES_FILE
            paper_trader.PAPER_TRADES_FILE = str(Path(tmpdir) / "paper_trades.json")
            try:
                first = paper_trader.PaperTrader()
                first.store = NoopStore()
                first.wallet_performance = NoopWalletPerformance()
                first.engine.config["simulate_failed_fills"] = False
                first_trade = first.open_trade(
                    "MintRace",
                    entry_price=1,
                    size_usd=100,
                    liquidity_usd=100_000,
                    reason="first",
                )

                second = paper_trader.PaperTrader()
                second.store = NoopStore()
                second.wallet_performance = NoopWalletPerformance()
                second.engine.config["simulate_failed_fills"] = False
                second.state["open_trades"] = []
                second_trade = second.open_trade(
                    "MintRace",
                    entry_price=2,
                    size_usd=100,
                    liquidity_usd=100_000,
                    reason="second",
                )

                final = paper_trader.PaperTrader()
                open_trades = [
                    trade for trade in final.state["open_trades"]
                    if trade.get("mint") == "MintRace"
                ]

                self.assertIsNotNone(first_trade)
                self.assertIsNotNone(second_trade)
                self.assertEqual(len(open_trades), 1)
                self.assertEqual(open_trades[0]["entry_reason"], "first")
                self.assertEqual(open_trades[0]["duplicate_open_attempts"], 1)
            finally:
                paper_trader.PAPER_TRADES_FILE = original_file

    def test_stale_open_trade_does_not_resurrect_closed_trade(self):
        trader = paper_trader.PaperTrader()
        trader.store = NoopStore()
        trader.wallet_performance = NoopWalletPerformance()
        current = trader.default_state()
        updated = trader.default_state()
        current["closed_trades"] = [{
            "mint": "MintClosed",
            "entry_time": 100,
            "status": "closed",
            "close_time": 200,
        }]
        updated["open_trades"] = [{
            "mint": "MintClosed",
            "entry_time": 100,
            "status": "open",
            "current_price": 2,
        }]

        merged = trader.merge_state_for_save(current, updated)

        self.assertEqual(merged["open_trades"], [])
        self.assertEqual(len(merged["closed_trades"]), 1)

    def test_failed_buy_attempts_for_same_mint_keep_distinct_times(self):
        trader = paper_trader.PaperTrader()
        trader.store = NoopStore()
        trader.wallet_performance = NoopWalletPerformance()
        merged = trader.merge_trade_lists(
            [{"mint": "MintFail", "time": 100, "reason": "slippage"}],
            [{"mint": "MintFail", "time": 101, "reason": "route_failed"}],
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual([trade["time"] for trade in merged], [101, 100])


class WatchdogRaceControlTests(unittest.TestCase):
    def test_watchdog_merge_rejects_stale_run_updates(self):
        current = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "reason": "newer result",
            "watchdog_checked_at_epoch": 200,
        }]
        checked = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "SAFE",
            "risk_level": "SAFE",
            "reason": "older result",
            "watchdog_checked_at_epoch": 100,
        }]

        merged = merge_watchlist_updates(current, checked)

        self.assertEqual(merged[0]["status"], "EMERGENCY")
        self.assertEqual(merged[0]["risk_level"], "EMERGENCY")
        self.assertEqual(merged[0]["reason"], "newer result")
        self.assertEqual(merged[0]["stale_watchdog_updates_skipped"], 1)

    def test_watchdog_merge_accepts_newer_run_updates(self):
        current = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "WARNING",
            "watchdog_checked_at_epoch": 100,
        }]
        checked = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "reason": "newer result",
            "watchdog_checked_at_epoch": 200,
        }]

        merged = merge_watchlist_updates(current, checked)

        self.assertEqual(merged[0]["status"], "EMERGENCY")
        self.assertEqual(merged[0]["risk_level"], "EMERGENCY")
        self.assertEqual(merged[0]["reason"], "newer result")

    def test_watchdog_merge_preserves_newer_operator_amount_metadata(self):
        current = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "WARNING",
            "token_amount": 42.5,
            "token_amount_raw": 42500000,
            "token_amount_source": "manual_operator",
            "token_amount_updated_at": "2026-05-06T01:00:00+00:00",
            "test_amount": True,
            "watchdog_checked_at_epoch": 100,
        }]
        checked = [{
            "token_mint": "MintWatch",
            "wallet": "Wallet1",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "token_amount": 1,
            "token_amount_raw": 1000000,
            "token_amount_source": "watchdog_stale_read",
            "test_amount": False,
            "watchdog_checked_at_epoch": 200,
        }]

        merged = merge_watchlist_updates(current, checked)

        self.assertEqual(merged[0]["status"], "EMERGENCY")
        self.assertEqual(merged[0]["token_amount"], 42.5)
        self.assertEqual(merged[0]["token_amount_raw"], 42500000)
        self.assertEqual(merged[0]["token_amount_source"], "manual_operator")
        self.assertTrue(merged[0]["test_amount"])

    def test_rug_watchdog_source_populates_risk(self):
        cards = build_catalyst_cards_from_snapshots([
            {
                "time": 1,
                "source": "rug_watchdog",
                "context": "watchdog_check",
                "mint": "Mint111",
                "risk_label": "DANGER",
                "token_mechanics_risk": "blocked_delegate",
            },
        ], generated_at=3)

        self.assertEqual(cards[0]["risk"]["label"], "DANGER")
        self.assertEqual(cards[0]["risk"]["mechanics"], "blocked_delegate")


class SocialSignalTests(unittest.TestCase):
    def test_social_signal_extracts_ticker_mint_and_sentiment(self):
        with TemporaryDirectory() as tmp:
            engine = SocialSignalEngine(state_file=str(Path(tmp) / "social_state.json"))
            signal = engine.add_signal(
                account="tester",
                text="Buying $DOGE cult runner 79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump",
                timestamp=123,
            )

        self.assertIn("doge", signal["tickers"])
        self.assertIn("79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump", signal["mints"])
        self.assertEqual(signal["sentiment"], "bullish")

    def test_social_event_id_is_stable_across_engine_instances(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "social_state.json")
            first = SocialSignalEngine(state_file=path).add_signal(
                account="tester",
                text="Buying $DOGE cult runner",
                timestamp=123,
            )
            second = SocialSignalEngine(state_file=path).build_signal(
                account="tester",
                text="Buying $DOGE cult runner",
                timestamp=123,
            )

        self.assertEqual(first["event_id"], second["event_id"])

    def test_exact_mint_matches_without_market_metadata(self):
        mint = "79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump"
        with TemporaryDirectory() as tmp:
            engine = SocialSignalEngine(state_file=str(Path(tmp) / "social_state.json"))
            engine.add_signal(
                account="tester",
                text=f"Watch this mint {mint}",
                timestamp=123,
            )
            result = engine.match_token(mint, market_info={})

        self.assertTrue(result["matched"])
        self.assertEqual(result["reason"], "social_exact_mint_match")

    def test_malformed_social_rows_do_not_break_active_signals(self):
        with TemporaryDirectory() as tmp:
            engine = SocialSignalEngine(state_file=str(Path(tmp) / "social_state.json"))
            engine.state = {
                "signals": [
                    "bad row",
                    {"expires_at": "not-a-number"},
                    {"expires_at": 9999999999, "account": "tester"},
                ]
            }

            active = engine.get_active_signals()

        self.assertEqual(len(active), 1)

    def test_social_engine_matches_canonical_events_rows(self):
        mint = "79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump"
        with TemporaryDirectory() as tmp:
            engine = SocialSignalEngine(state_file=str(Path(tmp) / "social_state.json"))
            event = engine.build_signal(
                account="reddit_alpha",
                text=f"Fresh $BONK launch {mint}",
                source_platform="reddit",
                timestamp=123,
            )
            engine.state = {"events": [event]}

            result = engine.match_token(mint, market_info={})

        self.assertTrue(result["matched"])
        self.assertEqual(result["reason"], "social_exact_mint_match")


class PositionCockpitTests(unittest.TestCase):
    def test_event_store_records_and_updates_decision_records(self):
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            decision = build_decision_record({
                "decision_id": "dec_test_1",
                "timestamp": 1000,
                "mint": "Mint111",
                "type": "cluster",
                "wallets": ["Wallet111"],
                "wallet_count": 1,
                "total_score": 72,
                "score_threshold": 68,
                "edge_score": 14,
                "edge_verdict": "watch",
                "risk_label": "LOW",
                "risk_score": 8,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "position_size_usd": 25,
                "should_trade": True,
                "paper_lane": "main",
                "score_reasons": ["cluster confirmed"],
            })

            decision_id = store.upsert_decision(decision)
            store.update_decision_action(decision_id, {
                "scanner_stage": "paper_entry",
                "final_action": "paper_opened",
                "reason": "paper fill succeeded",
            })
            store.update_decision_result(decision_id, {
                "trade_status": "closed",
                "entry_time": 1001,
                "close_time": 1100,
                "pnl": 42.5,
                "pnl_pct": 170,
            })
            rows = store.recent_decisions(limit=10)
            counts = store.counts()

        self.assertEqual(decision_id, "dec_test_1")
        self.assertEqual(counts["decision_records"], 1)
        self.assertEqual(rows[0]["mint"], "Mint111")
        self.assertEqual(rows[0]["final_action"], "paper_opened")
        self.assertEqual(rows[0]["trade_status"], "closed")
        self.assertEqual(rows[0]["pnl"], 42.5)
        self.assertTrue(rows[0]["buy_quote_pass"])
        self.assertEqual(rows[0]["payload"]["action"]["final_action"], "paper_opened")
        self.assertEqual(rows[0]["result"]["pnl_pct"], 170)

    def test_decision_record_preserves_extended_evidence_fields(self):
        decision = build_decision_record({
            "decision_id": "dec_extended_1",
            "timestamp": 1000,
            "mint": "MintExtended",
            "type": "cluster",
            "wallets": ["WalletA", "WalletB"],
            "wallet_count": 2,
            "weighted_wallet_score": 2.4,
            "social_match": {
                "matched": True,
                "reason": "social_exact_mint_match",
                "event_ids": ["social_1"],
                "matched_keywords": ["launch"],
                "matched_account": "alpha",
                "score_bonus": 7,
            },
            "catalyst_card_ids": ["card_1"],
            "catalyst_score": 82,
            "social_match_confidence": 0.91,
            "social_evidence_urls": ["https://example.test/post/1"],
            "holder_concentration_risk": "WARNING",
            "holder_concentration_reasons": ["Top 10 holders control at least 70%"],
            "holder_concentration_metrics": {
                "holder_count": 41,
                "top_1_pct": 18.5,
                "top_10_pct": 72.2,
                "top_holder_address": "Holder111",
            },
            "linked_wallet_risk": {
                "risk_label": "WATCH",
                "cluster_wallet_count": 3,
                "reasons": ["same funder seen twice"],
            },
            "buy_quote_pass": True,
            "buy_quote_reason": "quote_passed",
            "buy_quote_price_impact_pct": 1.2,
            "buy_quote_route_count": 2,
            "buy_quote_in_amount_raw": 100000000,
            "buy_quote_out_amount": 555000,
            "buy_quote_slippage_bps": 1500,
            "sell_quote_pass": False,
            "sell_quote_reason": "no_route_plan",
            "sell_quote_price_impact_pct": None,
            "sell_quote_route_count": 0,
            "sell_quote_slippage_bps": 2000,
            "broader_crypto_context": {"sol_1h_change_pct": -3.2},
            "stablecoin_context": {"usdc_depeg_warning": False},
            "market_risk_regime": "risk_off",
            "should_trade": False,
            "score_reasons": ["exit liquidity blocked"],
        })

        payload = decision["payload"]

        self.assertEqual(payload["inputs"]["social_catalyst"]["event_ids"], ["social_1"])
        self.assertEqual(payload["inputs"]["social_catalyst"]["catalyst_card_ids"], ["card_1"])
        self.assertEqual(payload["inputs"]["social_catalyst"]["match_confidence"], 0.91)
        self.assertEqual(payload["inputs"]["market_context"]["risk_regime"], "risk_off")
        self.assertEqual(payload["rule_outcomes"]["holder_cluster"]["holder_risk_label"], "WARNING")
        self.assertEqual(payload["rule_outcomes"]["holder_cluster"]["holder_count"], 41)
        self.assertEqual(payload["rule_outcomes"]["holder_cluster"]["top_10_pct"], 72.2)
        self.assertEqual(payload["rule_outcomes"]["holder_cluster"]["linked_wallet_risk"]["risk_label"], "WATCH")
        self.assertEqual(payload["route_feasibility"]["buy"]["route_count"], 2)
        self.assertEqual(payload["route_feasibility"]["buy"]["slippage_bps"], 1500)
        self.assertFalse(payload["route_feasibility"]["sell"]["pass"])

    def test_event_store_normalizes_failed_trade_rows_for_sqlite_mirror(self):
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            store.upsert_trade({
                "mint": "MintFailed",
                "side": "buy",
                "time": 123.0,
                "failure_reason": "quote_failed",
            })
            with store.connect() as conn:
                row = conn.execute("SELECT status, entry_time, reason, payload_json FROM trades").fetchone()

        self.assertEqual(row[0], "failed")
        self.assertEqual(row[1], 123.0)
        self.assertEqual(row[2], "quote_failed")
        self.assertIn("quote_failed", row[3])

    def test_event_store_terminal_trade_removes_stale_open_mirror_row(self):
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            store.upsert_trade({"mint": "MintClose", "status": "open", "entry_time": 100.0})
            store.upsert_trade({
                "mint": "MintClose",
                "status": "closed",
                "entry_time": 100.0,
                "close_time": 200.0,
                "exit_reason": "target_profit",
            })
            with store.connect() as conn:
                rows = conn.execute("SELECT status FROM trades ORDER BY status").fetchall()

        self.assertEqual([row[0] for row in rows], ["closed"])

    def test_trade_sync_rebuilds_sqlite_trades_to_match_json_buckets(self):
        from utils.sync_state_to_sqlite import sync_trades

        trades = {
            "open_trades": [{"mint": "MintOpen", "status": "open", "entry_time": 1}],
            "closed_trades": [{"mint": "MintClosed", "status": "closed", "entry_time": 2, "close_time": 3}],
            "failed_trades": [{"mint": "MintFailed", "side": "buy", "time": 4, "failure_reason": "quote_failed"}],
        }
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            store.upsert_trade({"mint": "StaleOpen", "status": "open", "entry_time": 9})
            result = sync_trades(store, trades, rebuild=True)

        self.assertTrue(result["parity"])
        self.assertEqual(result["actual"], {"open_trades": 1, "closed_trades": 1, "failed_trades": 1})

    def test_trade_sync_backfills_decision_results_from_paper_trade_metadata(self):
        from utils.sync_state_to_sqlite import sync_decision_results

        trades = {
            "open_trades": [{
                "mint": "MintOpen",
                "status": "open",
                "entry_time": 1,
                "paper_lane": "main",
                "signal_metadata": {"decision_id": "dec_open", "paper_lane": "main"},
            }],
            "closed_trades": [{
                "mint": "MintClosed",
                "status": "closed",
                "entry_time": 2,
                "close_time": 3,
                "total_pnl": 12.5,
                "total_pnl_pct": 41,
                "exit_reason": "target_profit",
                "paper_lane": "exploration",
                "signal_metadata": {"decision_id": "dec_closed", "paper_lane": "exploration"},
            }],
            "failed_trades": [{
                "mint": "MintFailed",
                "status": "failed",
                "time": 4,
                "failure_reason": "quote_failed",
                "signal_metadata": {"decision_id": "dec_failed", "paper_lane": "main"},
            }],
        }
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            for decision_id, lane in [
                ("dec_open", "main"),
                ("dec_closed", "exploration"),
                ("dec_failed", "main"),
            ]:
                store.upsert_decision(build_decision_record({
                    "decision_id": decision_id,
                    "mint": decision_id,
                    "paper_lane": lane,
                    "should_trade": True,
                    "score_reasons": ["paper decision"],
                }))
            result = sync_decision_results(store, trades)
            rows = {row["decision_id"]: row for row in store.recent_decisions(limit=10)}

        self.assertEqual(result["updated"], 3)
        self.assertEqual(rows["dec_open"]["final_action"], "paper_opened")
        self.assertEqual(rows["dec_open"]["trade_status"], "open")
        self.assertEqual(rows["dec_closed"]["final_action"], "paper_closed")
        self.assertEqual(rows["dec_closed"]["trade_status"], "closed")
        self.assertEqual(rows["dec_closed"]["pnl"], 12.5)
        self.assertEqual(rows["dec_closed"]["pnl_pct"], 41)
        self.assertEqual(rows["dec_closed"]["result"]["paper_outcome"]["paper_lane"], "exploration")
        self.assertEqual(rows["dec_failed"]["final_action"], "paper_failed")
        self.assertEqual(rows["dec_failed"]["trade_status"], "failed")

    def test_trade_sync_creates_synthetic_decisions_for_legacy_paper_trades(self):
        from utils.sync_state_to_sqlite import sync_decision_results

        trades = {
            "closed_trades": [{
                "mint": "LegacyMintClosed",
                "status": "closed",
                "entry_time": 100,
                "close_time": 200,
                "total_pnl": 18.5,
                "total_pnl_pct": 61,
                "entry_reason": "weighted_early_signal_CONFIRMATION_score_88.0_LOW_RISK_quote_ok",
                "close_reason": "target_profit",
                "wallets": ["WalletA"],
                "size_usd": 60,
            }],
            "failed_trades": [{
                "mint": "LegacyMintFailed",
                "time": 300,
                "failure_reason": "buy_failed",
                "entry_reason": "weighted_early_signal_CONFIRMATION_score_77.0_LOW_RISK_quote_ok",
                "wallets": ["WalletB"],
            }],
        }
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            result = sync_decision_results(store, trades, create_missing=True)
            rows = {row["mint"]: row for row in store.recent_decisions(limit=10)}

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["missing_decision_id"], 0)
        self.assertEqual(rows["LegacyMintClosed"]["final_action"], "paper_closed")
        self.assertEqual(rows["LegacyMintClosed"]["trade_status"], "closed")
        self.assertEqual(rows["LegacyMintClosed"]["pnl"], 18.5)
        self.assertEqual(rows["LegacyMintClosed"]["pnl_pct"], 61)
        self.assertEqual(rows["LegacyMintClosed"]["paper_lane"], "main")
        self.assertEqual(rows["LegacyMintFailed"]["final_action"], "paper_failed")
        self.assertEqual(rows["LegacyMintFailed"]["trade_status"], "failed")

    def test_trade_result_preserves_decision_outcome_fields(self):
        result = build_trade_result({
            "mint": "Mint111",
            "status": "closed",
            "entry_time": 100,
            "close_time": 200,
            "total_pnl": 12.25,
            "total_pnl_pct": 49,
            "exit_reason": "trailing_stop",
            "signal_metadata": {"decision_id": "dec_test_2"},
        }, "paper_exit_closed")

        self.assertEqual(result["context"], "paper_exit_closed")
        self.assertEqual(result["trade_status"], "closed")
        self.assertEqual(result.get("decision_id"), "dec_test_2")
        self.assertEqual(result["pnl"], 12.25)
        self.assertEqual(result["pnl_pct"], 49)
        self.assertEqual(result["exit_reason"], "trailing_stop")

    def test_trade_result_preserves_paper_outcome_details(self):
        result = build_trade_result({
            "mint": "Mint111",
            "status": "closed",
            "entry_time": 100,
            "close_time": 200,
            "entry_price": 0.001,
            "exit_price": 0.0018,
            "entry_liquidity_usd": 15000,
            "exit_liquidity_usd": 21000,
            "size_usd": 25,
            "remaining_pct": 0,
            "fees_usd": 0.18,
            "total_pnl": 18.5,
            "total_pnl_pct": 74,
            "exit_reason": "target_profit",
            "paper_lane": "exploration",
            "exploration": True,
            "signal_metadata": {
                "decision_id": "dec_test_3",
                "paper_lane": "exploration",
                "exploration_result": {"lane": "exploration", "reason": "near_miss"},
            },
        }, "paper_exit_closed")

        self.assertEqual(result["paper_outcome"]["paper_lane"], "exploration")
        self.assertTrue(result["paper_outcome"]["exploration"])
        self.assertEqual(result["paper_outcome"]["entry_price"], 0.001)
        self.assertEqual(result["paper_outcome"]["exit_price"], 0.0018)
        self.assertEqual(result["paper_outcome"]["position_size_usd"], 25)
        self.assertEqual(result["paper_outcome"]["fees_usd"], 0.18)
        self.assertEqual(result["paper_outcome"]["exploration_result"]["reason"], "near_miss")

    def test_event_store_records_swap_ticks_for_trade_stream_candles(self):
        with TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "memetrader.db")
            store.insert_swap_tick({
                "time": 100.1,
                "mint": "Mint111",
                "signature": "Sig111",
                "wallet": "Wallet111",
                "side": "buy",
                "price": 0.001,
                "market_cap": 1_000_000,
                "liquidity": 22_000,
                "token_amount": 1000,
                "sol_amount": 1,
                "source": "helius_swap",
            })
            store.insert_swap_tick({
                "time": 101.1,
                "mint": "Mint111",
                "signature": "Sig222",
                "side": "sell",
                "price": 0.0012,
                "market_cap": 1_200_000,
                "liquidity": 23_000,
                "source": "helius_swap",
            })

            rows = store.recent_swap_ticks("Mint111", limit=10, newest_first=False)
            counts = store.counts()

        self.assertEqual(counts["swap_ticks"], 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["signature"], "Sig111")
        self.assertEqual(rows[0]["price"], 0.001)
        self.assertEqual(rows[1]["market_cap"], 1_200_000)

    def test_build_candles_groups_snapshots(self):
        candles = build_candles([
            {"time": 100, "price": 1.0, "market_cap": 1000},
            {"time": 101, "price": 1.2, "market_cap": 1200},
            {"time": 106, "price": 0.9, "market_cap": 900},
            {"time": 107, "price": 0.7, "market_cap": 700},
        ], interval_seconds=5)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["open"], 1.0)
        self.assertEqual(candles[0]["close"], 1.2)
        self.assertEqual(candles[0]["high"], 1.2)
        self.assertEqual(candles[0]["low"], 1.0)
        self.assertEqual(candles[0]["color"], "green")
        self.assertEqual(candles[1]["color"], "red")

    def test_build_candles_can_infer_sparse_opens_from_previous_close(self):
        candles = build_candles([
            {"time": 100, "price": 1.0},
            {"time": 101, "price": 1.2},
            {"time": 102, "price": 0.8},
        ], interval_seconds=1, carry_forward_open=True)

        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[1]["open"], 1.0)
        self.assertEqual(candles[1]["close"], 1.2)
        self.assertEqual(candles[1]["color"], "green")
        self.assertEqual(candles[2]["open"], 1.2)
        self.assertEqual(candles[2]["close"], 0.8)
        self.assertEqual(candles[2]["color"], "red")

    def test_build_candles_respects_requested_output_limit(self):
        rows = [{"time": 100 + index, "price": 1 + index / 1000} for index in range(180)]

        default_candles = build_candles(rows, interval_seconds=1)
        limited_candles = build_candles(rows, interval_seconds=1, max_candles=60)

        self.assertEqual(len(default_candles), 180)
        self.assertEqual(len(limited_candles), 60)
        self.assertEqual(limited_candles[0]["time"], 220)

    def test_simulated_action_intent_is_never_live(self):
        intent = build_simulated_action_intent(
            mint="Mint111",
            action_type="prepare_exit_early",
            source="position_cockpit",
            amount={"sell_pct": 100},
            reason="operator_pressed_exit_early",
        )

        self.assertEqual(intent["mint"], "Mint111")
        self.assertEqual(intent["action_type"], "prepare_exit_early")
        self.assertEqual(intent["execution_mode"], "SIMULATION_ONLY")
        self.assertFalse(intent["live_action_allowed"])

    def test_import_text_block_supports_account_pipe_text(self):
        with TemporaryDirectory() as tmp:
            engine = SocialSignalEngine(state_file=str(Path(tmp) / "social_state.json"))
            imported = engine.import_text_block(
                "elonmusk | Grok based launch $GROK | https://x.com/example/status/1"
            )

        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["account"], "elonmusk")
        self.assertEqual(imported[0]["url"], "https://x.com/example/status/1")
        self.assertIn("grok", imported[0]["keywords"])

    def test_reddit_post_maps_to_social_signal(self):
        engine = SocialSignalEngine(state_file="unused.json")
        signal = reddit_post_to_signal(
            {
                "id": "abc123",
                "author": "AlphaPoster",
                "title": "Fresh $BONK launch",
                "selftext": "Mint 79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump looks based",
                "created_utc": 1234,
                "permalink": "/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch/",
                "score": 88,
                "num_comments": 12,
            },
            subreddit="SolanaMemeCoins",
            engine=engine,
        )

        self.assertEqual(signal["source_platform"], "reddit")
        self.assertEqual(signal["account"], "reddit_solanamemecoins_alphaposter")
        self.assertIn("bonk", signal["tickers"])
        self.assertIn("79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump", signal["mints"])
        self.assertEqual(signal["engagement"]["score"], 88)
        self.assertIn("reddit.com/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch", signal["url"])

    def test_reddit_collector_stores_signals_and_status_without_trade_trigger(self):
        listing = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "author": "AlphaPoster",
                            "title": "Fresh $BONK launch",
                            "selftext": "Mint 79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump looks based",
                            "created_utc": 1234,
                            "permalink": "/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch/",
                            "score": 88,
                            "num_comments": 12,
                        }
                    }
                ]
            }
        }

        def fetcher(url, timeout, headers):
            return listing

        with TemporaryDirectory() as tmp:
            state_file = str(Path(tmp) / "social_state.json")
            result = collect_reddit_social(
                subreddits=["SolanaMemeCoins"],
                limit=10,
                state_file=state_file,
                fetcher=fetcher,
            )
            engine = SocialSignalEngine(state_file=state_file)

        self.assertEqual(result["collector"], "reddit")
        self.assertEqual(result["stored_count"], 1)
        self.assertFalse(result["trade_triggered"])
        self.assertEqual(engine.signal_summary()["total"], 1)
        self.assertEqual(result["status"]["collector"], "reddit")
        self.assertEqual(result["status"]["event_count"], 1)

    def test_reddit_collector_preserves_existing_canonical_events(self):
        listing = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "author": "AlphaPoster",
                            "title": "Fresh $BONK launch",
                            "created_utc": 1234,
                            "permalink": "/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch/",
                        }
                    }
                ]
            }
        }

        def fetcher(url, timeout, headers):
            return listing

        with TemporaryDirectory() as tmp:
            state_file = str(Path(tmp) / "social_state.json")
            SocialSignalEngine(state_file=state_file).import_text_block(
                "manual | Manual $WIF watch | https://example.test/manual"
            )
            collect_reddit_social(
                subreddits=["SolanaMemeCoins"],
                limit=10,
                state_file=state_file,
                fetcher=fetcher,
            )
            engine = SocialSignalEngine(state_file=state_file)

        self.assertEqual(engine.signal_summary()["total"], 2)
        accounts = engine.signal_summary()["accounts"]
        self.assertEqual(accounts["manual"], 1)
        self.assertEqual(accounts["reddit_solanamemecoins_alphaposter"], 1)

    def test_reddit_collector_filters_duplicates_and_noisy_posts(self):
        listing = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "abc123",
                            "author": "AlphaPoster",
                            "title": "Fresh $BONK launch",
                            "selftext": "Mint 79ogrGd2bhRS455phmsJo8iHYzBusqgLeyxF9Tf5pump looks based",
                            "created_utc": 1234,
                            "permalink": "/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch/",
                            "score": 88,
                            "num_comments": 12,
                        }
                    },
                    {
                        "data": {
                            "id": "abc123",
                            "author": "AlphaPoster",
                            "title": "Fresh $BONK launch",
                            "created_utc": 1235,
                            "permalink": "/r/SolanaMemeCoins/comments/abc123/fresh_bonk_launch/",
                        }
                    },
                    {
                        "data": {
                            "id": "noise1",
                            "author": "AutoModerator",
                            "title": "Daily discussion thread",
                            "selftext": "What are you buying today?",
                            "created_utc": 1236,
                            "permalink": "/r/SolanaMemeCoins/comments/noise1/daily/",
                        }
                    },
                ]
            }
        }

        def fetcher(url, timeout, headers):
            return listing

        with TemporaryDirectory() as tmp:
            state_file = str(Path(tmp) / "social_state.json")
            result = collect_reddit_social(
                subreddits=["SolanaMemeCoins"],
                limit=10,
                state_file=state_file,
                fetcher=fetcher,
            )
            engine = SocialSignalEngine(state_file=state_file)

        self.assertEqual(result["fetched_count"], 3)
        self.assertEqual(result["stored_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["rejected_count"], 1)
        self.assertEqual(result["rejection_reasons"]["noisy_author"], 1)
        self.assertEqual(engine.signal_summary()["total"], 1)
        self.assertFalse(result["broader_source_expansion"]["allowed"])


if __name__ == "__main__":
    unittest.main()
