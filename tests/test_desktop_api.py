import json
import tempfile
import unittest
from http import HTTPStatus
from unittest import mock

import desktop_api
from core.decision_ledger import build_decision_record
from core.storage import EventStore


class DesktopApiTests(unittest.TestCase):
    def setUp(self):
        desktop_api.PROVIDER_HEALTH_CACHE["updated_at"] = 0
        desktop_api.PROVIDER_HEALTH_CACHE["payload"] = None
        desktop_api.invalidate_state_cache()
        desktop_api.DESKTOP_ENV_LOADED = False
        desktop_api.DESKTOP_API_TOKEN = None

    def test_overview_payload_is_paper_locked(self):
        payload = desktop_api.build_overview_payload({
            "paper": {"open_trades": [{}], "closed_trades": [{}, {}], "failed_trades": []},
            "watchlist": [{"token_mint": "abc"}],
            "runtime": {"bot": {"updated_at": desktop_api.time.time(), "state": "alive"}},
            "social": {"events": [{"text": "test"}]},
            "catalysts": {"cards": [{"mint": "abc"}]},
            "settings": {"strategy_mode": "confirmation", "paper_trading": True},
        })

        self.assertEqual(payload["mode"], "PAPER_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["counts"]["open_trades"], 1)
        self.assertEqual(payload["counts"]["protected_positions"], 1)

    def test_read_state_files_uses_short_lived_cache(self):
        files = {
            desktop_api.WATCHLIST_FILE: [],
            desktop_api.SOCIAL_STATE_FILE: {"events": []},
            desktop_api.CATALYST_CARDS_FILE: {"cards": []},
            desktop_api.SETTINGS_FILE: {},
            desktop_api.TRACKED_WALLETS_FILE: [],
            desktop_api.WALLET_PERFORMANCE_FILE: {"wallets": {}, "signals": []},
            desktop_api.WALLET_BEHAVIOR_FILE: {"wallets": {}},
            desktop_api.CANDIDATE_WALLETS_FILE: {"candidates": []},
            desktop_api.PAPER_WATCH_WALLETS_FILE: {"wallets": []},
            desktop_api.WALLET_REVIEW_DECISIONS_FILE: {"decisions": []},
        }
        reads = []

        def fake_read_json(path, default):
            reads.append(path)
            return files.get(path, default)

        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[
            {"status": "open", "payload": {"mint": "MintSqlOpen", "status": "open"}},
        ]) as fetch_trades:
            with mock.patch.object(desktop_api, "read_json", side_effect=fake_read_json):
                with mock.patch.object(desktop_api, "load_status", return_value={}):
                    first = desktop_api.read_state_files()
                    second = desktop_api.read_state_files()

        self.assertIs(first, second)
        fetch_trades.assert_called_once()
        self.assertEqual(reads.count(desktop_api.PAPER_TRADES_FILE), 1)

    def test_read_state_files_fallback_reads_paper_json_when_sqlite_empty(self):
        reads = []

        def fake_read_json(path, default):
            reads.append(path)
            if path == desktop_api.PAPER_TRADES_FILE:
                return {"open_trades": [{"mint": "MintJsonOpen"}], "closed_trades": [], "failed_trades": []}
            return default

        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[]):
            with mock.patch.object(desktop_api, "read_json", side_effect=fake_read_json):
                with mock.patch.object(desktop_api, "load_status", return_value={}):
                    state = desktop_api.read_state_files()

        self.assertEqual(state["paper"]["open_trades"][0]["mint"], "MintJsonOpen")
        self.assertEqual(reads.count(desktop_api.PAPER_TRADES_FILE), 1)

    def test_runtime_summary_treats_fresh_scanner_as_websocket_coverage(self):
        now = desktop_api.time.time()
        payload = desktop_api.summarize_runtime({
            "bot": {"updated_at": now, "status": "alive"},
            "websocket": {
                "updated_at": now - 600,
                "status": "subscribed",
                "subscribed_wallets": 519,
                "last_error": "old keepalive timeout",
            },
            "scanner": {"updated_at": now, "status": "listening"},
        })

        websocket = next(row for row in payload["components"] if row["name"] == "websocket")
        self.assertEqual(payload["state"], "online")
        self.assertTrue(websocket["fresh"])
        self.assertEqual(websocket["detail"], "scanner heartbeat fresh; websocket subscription active")

    def test_overview_wallet_confidence_summarizes_recent_signal_wallets(self):
        payload = desktop_api.build_overview_payload({
            "paper": {
                "open_trades": [{"mint": "MintOpen", "wallets": ["WalletWin"]}],
                "closed_trades": [],
                "failed_trades": [],
            },
            "watchlist": [],
            "runtime": {},
            "social": {},
            "catalysts": {},
            "settings": {},
            "wallet_performance": {
                "wallets": {
                    "WalletWin": {"score": 86, "paper_entries": 4, "avg_pnl": 18},
                    "WalletTrap": {"score": 24, "paper_entries": 2, "avg_pnl": -22},
                },
                "signals": [
                    {"mint": "MintA", "wallets": ["WalletWin"], "time": 300, "should_trade": True},
                    {"mint": "MintB", "wallets": ["WalletTrap"], "time": 200, "should_trade": False},
                    {"mint": "MintA", "wallets": ["WalletWin"], "time": 100, "should_trade": True},
                ],
            },
            "wallet_behavior": {
                "wallets": {
                    "WalletWin": {"labels": ["paper-profitable", "early-buyer"], "postmortem": {"closed_trades": 4, "failed_trades": 0}},
                    "WalletTrap": {"labels": ["follower-trap"], "postmortem": {"closed_trades": 1, "failed_trades": 1}},
                }
            },
        })

        summary = payload["wallet_confidence"]
        self.assertEqual(summary["wallet_count"], 2)
        self.assertEqual(summary["signal_count"], 3)
        self.assertEqual(summary["token_count"], 3)
        self.assertEqual(summary["proven_wallets"], 1)
        self.assertEqual(summary["trap_wallets"], 1)
        self.assertEqual(summary["open_trade_wallets"], 1)
        self.assertEqual(summary["avg_score"], 55)
        self.assertEqual(summary["top_labels"]["paper-profitable"], 1)

    def test_paper_review_payload_reports_readiness_and_trade_quality(self):
        payload = desktop_api.build_paper_review_payload({
            "paper": {
                "open_trades": [{"mint": "MintOpen", "wallets": ["WalletWin"], "total_pnl": 5}],
                "closed_trades": [
                    {"mint": "MintWin", "wallets": ["WalletWin"], "total_pnl": 40, "total_pnl_pct": 40, "entry_reason": "cluster_score_pass", "exit_reason": "target_profit"},
                    {"mint": "MintLoss", "wallets": ["WalletTrap"], "total_pnl": -20, "total_pnl_pct": -20, "entry_reason": "weighted_early_signal", "exit_reason": "hard_stop_loss"},
                    {"mint": "MintExplore", "wallets": ["WalletScout"], "total_pnl": 5, "total_pnl_pct": 50, "entry_reason": "paper_exploration", "exit_reason": "target_profit", "paper_lane": "exploration", "exploration": True},
                    {"mint": "MintRadar", "wallets": [], "total_pnl": 3, "total_pnl_pct": 30, "entry_reason": "market_radar_hot", "exit_reason": "target_profit", "paper_lane": "market_radar"},
                ],
                "failed_trades": [
                    {"mint": "MintFail", "wallets": ["WalletTrap"], "failure_reason": "quote_failed"},
                ],
            },
            "wallet_behavior": {
                "wallets": {
                    "WalletWin": {"labels": ["paper-profitable", "early-buyer"]},
                    "WalletTrap": {"labels": ["follower-trap"]},
                }
            },
        })

        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["meaningful_test_ready"])
        self.assertEqual(payload["minimum_closed_trades"], 50)
        self.assertEqual(payload["metrics"]["closed_trades"], 4)
        self.assertEqual(payload["metrics"]["failed_trades"], 1)
        self.assertEqual(payload["metrics"]["win_rate"], 75.0)
        self.assertEqual(payload["lane_metrics"]["main"]["closed_trades"], 2)
        self.assertEqual(payload["lane_metrics"]["main"]["realized_pnl"], 20)
        self.assertEqual(payload["lane_metrics"]["co_main"]["closed_trades"], 3)
        self.assertEqual(payload["lane_metrics"]["co_main"]["realized_pnl"], 23)
        self.assertEqual(payload["lane_metrics"]["exploration"]["closed_trades"], 1)
        self.assertEqual(payload["lane_metrics"]["exploration"]["total_pnl"], 5)
        self.assertEqual(payload["lane_metrics"]["market_radar"]["closed_trades"], 1)
        self.assertEqual(payload["lane_metrics"]["market_radar"]["total_pnl"], 3)
        self.assertFalse(payload["co_main_meaningful_test_ready"])
        self.assertFalse(payload["wallet_main_meaningful_test_ready"])
        self.assertFalse(payload["market_radar_main_meaningful_test_ready"])
        self.assertEqual(payload["exit_reasons"]["target_profit"], 3)
        self.assertEqual(payload["failure_reasons"]["quote_failed"], 1)
        self.assertEqual(payload["wallet_label_exposure"]["paper-profitable"], 1)
        self.assertEqual(payload["wallet_label_exposure"]["follower-trap"], 2)
        self.assertIn("Need at least 50 closed co-main paper trades", payload["readiness_gaps"][0])
        self.assertEqual(payload["sample_progress"]["lanes"]["wallet_main"]["closed_trades"], 2)
        self.assertEqual(payload["sample_progress"]["lanes"]["co_main"]["closed_trades"], 3)
        self.assertEqual(payload["sample_progress"]["lanes"]["market_radar"]["closed_trades"], 1)
        self.assertEqual(payload["sample_progress"]["lanes"]["exploration"]["closed_trades"], 1)
        self.assertFalse(payload["sample_progress"]["lanes"]["market_radar"]["meets_minimum"])
        self.assertEqual(payload["decision_lineage"]["all"]["total"], 6)
        self.assertEqual(payload["decision_lineage"]["all"]["with_decision_id"], 0)
        self.assertEqual(payload["decision_lineage"]["main"]["total"], 4)
        self.assertTrue(any("Paper lineage" in gap for gap in payload["readiness_gaps"]))

    def test_paper_review_omits_lineage_gap_when_trades_linked(self):
        payload = desktop_api.build_paper_review_payload({
            "paper": {
                "open_trades": [],
                "closed_trades": [
                    {"mint": f"M{i}", "paper_lane": "main", "total_pnl": 0.1, "decision_id": f"dec_{i}"}
                    for i in range(12)
                ],
                "failed_trades": [],
            },
            "wallet_behavior": {"wallets": {}},
        })
        self.assertFalse(any("Paper lineage" in gap for gap in payload["readiness_gaps"]))
        self.assertEqual(payload["decision_lineage"]["all"]["coverage_pct"], 100.0)

    def test_paper_review_main_readiness_is_not_satisfied_by_exploration_only(self):
        payload = desktop_api.build_paper_review_payload({
            "paper": {
                "open_trades": [],
                "closed_trades": [
                    {
                        "mint": f"MintExplore{i}",
                        "paper_lane": "exploration",
                        "exploration": True,
                        "total_pnl": 1,
                        "entry_reason": "paper_exploration",
                    }
                    for i in range(50)
                ],
                "failed_trades": [],
            },
            "wallet_behavior": {"wallets": {}},
        })

        self.assertTrue(payload["exploration_sample_ready"])
        self.assertFalse(payload["main_meaningful_test_ready"])
        self.assertFalse(payload["co_main_meaningful_test_ready"])
        self.assertFalse(payload["meaningful_test_ready"])
        self.assertEqual(payload["lane_metrics"]["co_main"]["closed_trades"], 0)
        self.assertEqual(payload["lane_metrics"]["main"]["closed_trades"], 0)
        self.assertEqual(payload["lane_metrics"]["exploration"]["closed_trades"], 50)

    def test_market_radar_review_groups_token_nursery_stages(self):
        rows = [
            {
                "decision_id": "dec_rejected",
                "mint": "RejectMint",
                "updated_at": 10,
                "final_action": "skip",
                "paper_lane": "market_radar",
                "total_score": 42,
                "threshold": 70,
                "buy_quote_pass": False,
                "sell_quote_pass": False,
                "payload": {
                    "market_info": {"symbol": "REJ", "liquidity": 25_000, "market_cap": 80_000},
                    "market_radar": {
                        "score": {"allowed": False, "score": 42, "threshold": 70, "blockers": ["entry_liquidity_below_quality_gate"]},
                        "decision": {"skip_reason": "entry_liquidity_below_quality_gate", "skip_bucket": "liquidity"},
                        "sources": ["latest_profiles"],
                    },
                },
            },
            {
                "decision_id": "dec_watch",
                "mint": "WatchMint",
                "updated_at": 20,
                "final_action": "skip",
                "paper_lane": "market_radar",
                "total_score": 64,
                "threshold": 70,
                "buy_quote_pass": None,
                "sell_quote_pass": None,
                "payload": {
                    "market_info": {"symbol": "WATCH", "liquidity": 130_000, "market_cap": 500_000},
                    "market_radar": {
                        "score": {"allowed": False, "score": 64, "threshold": 70, "blockers": ["score_below_market_radar_threshold"]},
                        "decision": {"skip_reason": "score_below_market_radar_threshold", "skip_bucket": "score"},
                    },
                },
            },
            {
                "decision_id": "dec_quote",
                "mint": "QuoteMint",
                "updated_at": 30,
                "final_action": "skip",
                "paper_lane": "market_radar",
                "total_score": 78,
                "threshold": 70,
                "buy_quote_pass": False,
                "sell_quote_pass": False,
                "payload": {
                    "market_info": {"symbol": "QUOTE", "liquidity": 220_000, "market_cap": 900_000},
                    "market_radar": {
                        "score": {"allowed": True, "score": 78, "threshold": 70, "blockers": []},
                        "decision": {"skip_reason": "market_radar_quote_cooldown", "skip_bucket": "quote_or_route", "quote_retryable": True},
                    },
                },
            },
            {
                "decision_id": "dec_open",
                "mint": "OpenMint",
                "updated_at": 40,
                "final_action": "paper_opened",
                "paper_lane": "market_radar",
                "total_score": 82,
                "threshold": 70,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "trade_status": "open",
                "payload": {
                    "market_info": {"symbol": "OPEN", "liquidity": 300_000, "market_cap": 1_200_000},
                    "market_radar": {
                        "score": {"allowed": True, "score": 82, "threshold": 70, "blockers": []},
                        "decision": {"open_reason": "hot_candidate_quote_passed"},
                    },
                },
            },
            {
                "decision_id": "dec_closed",
                "mint": "ClosedMint",
                "updated_at": 50,
                "final_action": "paper_opened",
                "paper_lane": "market_radar",
                "total_score": 88,
                "threshold": 70,
                "trade_status": "closed",
                "pnl": 12,
                "pnl_pct": 45,
                "result": {
                    "trade_status": "closed",
                    "pnl": 12,
                    "pnl_pct": 45,
                    "entry_time": 100,
                    "close_time": 220,
                    "exit_reason": "target_profit",
                    "paper_outcome": {
                        "entry_price": 0.001,
                        "exit_price": 0.00145,
                        "entry_liquidity_usd": 200_000,
                        "exit_liquidity_usd": 260_000,
                        "entry_market_cap": 1_000_000,
                        "exit_market_cap": 1_450_000,
                        "position_size_usd": 25,
                        "entry_reason": "market_radar_hot_candidate",
                        "exit_reason": "target_profit",
                    },
                },
                "payload": {
                    "market_info": {"symbol": "CLOSED", "liquidity": 350_000, "market_cap": 1_500_000},
                    "market_radar": {"score": {"allowed": True, "score": 88, "threshold": 70}, "decision": {}},
                },
            },
            {
                "decision_id": "dec_failed",
                "mint": "FailedMint",
                "updated_at": 60,
                "final_action": "open_attempt_failed",
                "paper_lane": "market_radar",
                "total_score": 75,
                "threshold": 70,
                "trade_status": "failed",
                "result": {
                    "trade_status": "failed",
                    "failure_reason": "buy_quote_429",
                    "paper_outcome": {
                        "position_size_usd": 25,
                        "entry_reason": "market_radar_hot_candidate",
                    },
                },
                "payload": {
                    "market_info": {"symbol": "FAILED", "liquidity": 180_000, "market_cap": 700_000},
                    "market_radar": {"score": {"allowed": True, "score": 75, "threshold": 70}, "decision": {}},
                },
            },
            {"decision_id": "dec_main", "mint": "MainMint", "paper_lane": "main", "payload": {}},
        ]

        with mock.patch.object(desktop_api, "fetch_decision_rows", return_value=rows):
            payload = desktop_api.build_market_radar_review_payload(limit=100)

        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["mode"], "MARKET_RADAR_REVIEW_ONLY")
        self.assertEqual(payload["summary"]["total"], 6)
        self.assertEqual(payload["summary"]["rejected"], 1)
        self.assertEqual(payload["summary"]["watch"], 1)
        self.assertEqual(payload["summary"]["quote_watch"], 1)
        self.assertEqual(payload["summary"]["paper_bought"], 1)
        self.assertEqual(payload["summary"]["closed"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["items"][0]["mint"], "FailedMint")
        self.assertEqual(payload["items"][0]["stage"], "failed")
        self.assertEqual(payload["items"][0]["postmortem"]["failure_reason"], "buy_quote_429")
        self.assertEqual(payload["items"][1]["stage"], "closed")
        self.assertEqual(payload["items"][1]["postmortem"]["exit_reason"], "target_profit")
        self.assertEqual(payload["items"][1]["postmortem"]["entry_price"], 0.001)
        self.assertEqual(payload["items"][1]["postmortem"]["exit_price"], 0.00145)
        self.assertEqual(payload["items"][1]["postmortem"]["liquidity_change_pct"], 30.0)
        self.assertEqual(payload["items"][1]["postmortem"]["market_cap_change_pct"], 45.0)
        self.assertEqual(payload["items"][1]["postmortem"]["hold_seconds"], 120.0)
        self.assertEqual(payload["items"][2]["stage"], "paper_bought")
        self.assertEqual(payload["items"][3]["stage"], "quote_watch")
        self.assertEqual(payload["items"][4]["reason"], "score_below_market_radar_threshold")
        self.assertEqual(payload["items"][5]["liquidity_usd"], 25000)
        self.assertEqual(payload["items"][5]["stage"], "rejected")

    def test_market_radar_review_stage_requires_quote_worthy_candidate_for_quote_watch(self):
        base = {
            "final_action": "skip",
            "paper_lane": "market_radar",
            "total_score": 76,
            "threshold": 70,
            "buy_quote_pass": False,
            "sell_quote_pass": False,
        }

        not_allowed_quote_bucket = {
            **base,
            "payload": {
                "market_radar": {
                    "score": {"allowed": False, "score": 76, "threshold": 70, "blockers": ["entry_liquidity_below_quality_gate"]},
                    "decision": {"skip_reason": "market_radar_quote_cooldown", "skip_bucket": "quote_or_route", "quote_retryable": True},
                }
            },
        }
        allowed_quote_bucket = {
            **base,
            "payload": {
                "market_radar": {
                    "score": {"allowed": True, "score": 76, "threshold": 70, "blockers": []},
                    "decision": {"skip_reason": "market_radar_quote_cooldown", "skip_bucket": "quote_or_route", "quote_retryable": True},
                }
            },
        }
        near_score_only = {
            **base,
            "buy_quote_pass": None,
            "sell_quote_pass": None,
            "total_score": 64,
            "payload": {
                "market_radar": {
                    "score": {"allowed": False, "score": 64, "threshold": 70, "blockers": ["score_below_market_radar_threshold"]},
                    "decision": {"skip_reason": "score_below_market_radar_threshold", "skip_bucket": "score"},
                }
            },
        }
        near_hard_blocker = {
            **base,
            "total_score": 69,
            "payload": {
                "market_radar": {
                    "score": {"allowed": False, "score": 69, "threshold": 70, "blockers": ["one_sided_sell_flow", "score_below_market_radar_threshold"]},
                    "decision": {"skip_reason": "one_sided_sell_flow", "skip_bucket": "order_flow"},
                }
            },
        }

        self.assertEqual(desktop_api.market_radar_review_stage(not_allowed_quote_bucket), "rejected")
        self.assertEqual(desktop_api.market_radar_review_stage(allowed_quote_bucket), "quote_watch")
        self.assertEqual(desktop_api.market_radar_review_stage(near_score_only), "watch")
        self.assertEqual(desktop_api.market_radar_review_stage(near_hard_blocker), "rejected")

    def test_winner_pattern_review_extracts_repeatable_big_winner_traits(self):
        payload = desktop_api.build_winner_pattern_payload({
            "paper": {
                "open_trades": [],
                "closed_trades": [
                    {
                        "mint": "WinnerMint",
                        "symbol": "WIN",
                        "total_pnl": 700,
                        "total_pnl_pct": 1200,
                        "entry_market_cap": 5_000_000,
                        "exit_market_cap": 150_000_000,
                        "entry_liquidity_usd": 250_000,
                        "risk_label": "LOW_RISK",
                        "entry_reason": "weighted_early_signal_CONFIRMATION_score_92_LOW_RISK_quote_ok",
                        "wallets": ["WalletElite"],
                        "signal_metadata": {
                            "score": 92,
                            "threshold": 68,
                            "risk_label": "LOW_RISK",
                            "buy_quote_analysis": {"pass": True},
                            "sell_quote_analysis": {"pass": True},
                            "score_reasons": [
                                "Elite live wallet signal: WalletElite",
                                "CONFIRMATION: Launch age 99s is in confirmation window",
                                "Excellent liquidity",
                            ],
                        },
                        "sells": [{"reason": "take_profit_2.5x"}],
                    },
                    {
                        "mint": "LoserMint",
                        "symbol": "LOSE",
                        "total_pnl": -20,
                        "entry_liquidity_usd": 4_000,
                        "entry_reason": "cluster_SNIPER_score_57_LOW_RISK_quote_ok",
                        "wallets": ["WalletTrap"],
                    },
                ],
                "failed_trades": [],
            },
            "wallet_behavior": {"wallets": {}},
        })

        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["winner_count"], 1)
        self.assertEqual(payload["loser_count"], 1)
        self.assertEqual(payload["top_winners"][0]["mint"], "WinnerMint")
        self.assertIn("elite wallet", payload["repeatable_traits"])
        self.assertIn("confirmation window", payload["repeatable_traits"])
        self.assertIn("strong liquidity", payload["repeatable_traits"])
        self.assertIn("partial take-profit", payload["repeatable_traits"])
        self.assertEqual(payload["wallet_leaders"][0]["wallet"], "WalletElite")

    def test_trades_payload_prefers_sqlite_source_of_truth(self):
        json_state = {
            "open_trades": [{"mint": "MintSqlOpen", "status": "open"}],
            "closed_trades": [{"mint": "MintSqlClosed", "status": "closed"}],
            "failed_trades": [{"mint": "MintSqlFailed", "status": "failed"}],
        }
        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[
            {"status": "open", "payload": {"mint": "MintSqlOpen", "status": "open"}},
            {"status": "closed", "payload": {"mint": "MintSqlClosed", "status": "closed"}},
            {"status": "failed", "payload": {"mint": "MintSqlFailed", "status": "failed"}},
        ]):
            with mock.patch.object(desktop_api, "read_json", return_value=json_state):
                payload = desktop_api.build_trades_payload()

        self.assertEqual(payload["source"], "sqlite_trades")
        self.assertEqual(payload["source_detail"], "data/memetrader.db:trades")
        self.assertEqual(payload["source_contract"]["trades"], "sqlite_trades")
        self.assertEqual(payload["fallback_source"], "paper_trades_json")
        self.assertEqual(payload["open_trades"][0]["mint"], "MintSqlOpen")
        self.assertEqual(payload["closed_trades"][0]["mint"], "MintSqlClosed")
        self.assertEqual(payload["failed_trades"][0]["mint"], "MintSqlFailed")

    def test_trades_payload_falls_back_to_json_when_sqlite_parity_fails(self):
        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[
            {"status": "open", "payload": {"mint": "MintSqlOpen", "status": "open"}},
        ]):
            with mock.patch.object(desktop_api, "read_json", return_value={
                "open_trades": [{"mint": "MintJsonOpen", "status": "open"}],
                "closed_trades": [],
                "failed_trades": [{"mint": "MintJsonFailed", "status": "failed"}],
            }):
                payload = desktop_api.build_trades_payload()

        self.assertEqual(payload["source"], "paper_trades_json")
        self.assertEqual(payload["fallback_reason"], "sqlite_trades_parity_mismatch")
        self.assertIn("parity", payload["mirror_warning"])
        self.assertEqual(payload["open_trades"][0]["mint"], "MintJsonOpen")
        self.assertEqual(payload["failed_trades"][0]["mint"], "MintJsonFailed")

    def test_legacy_failed_sqlite_trade_rows_are_not_bucketed_as_open(self):
        state = desktop_api.paper_state_from_trade_rows([
            {"payload": {"mint": "MintLegacyFail", "side": "buy", "time": 123.0, "failure_reason": "quote_failed"}},
        ])

        self.assertEqual(state["open_trades"], [])
        self.assertEqual(state["failed_trades"][0]["mint"], "MintLegacyFail")

    def test_trades_payload_uses_json_when_sqlite_has_no_trade_rows(self):
        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[]):
            with mock.patch.object(desktop_api, "read_json", return_value={
                "open_trades": [{"mint": "MintOpen"}],
                "closed_trades": [{"mint": "MintClosed"}],
                "failed_trades": [],
            }):
                payload = desktop_api.build_trades_payload()

        self.assertEqual(payload["source"], "paper_trades_json")
        self.assertEqual(payload["source_detail"], "data/paper_trades.json")
        self.assertEqual(payload["source_contract"]["trades"], "paper_trades_json")
        self.assertEqual(payload["fallback_reason"], "sqlite_trades_empty")
        self.assertEqual(payload["open_trades"][0]["mint"], "MintOpen")

    def test_read_state_files_uses_sqlite_paper_state_when_available(self):
        files = {
            desktop_api.PAPER_TRADES_FILE: {"open_trades": [{"mint": "MintSqlOpen", "status": "open"}], "closed_trades": [], "failed_trades": []},
            desktop_api.WATCHLIST_FILE: [],
            desktop_api.SOCIAL_STATE_FILE: {"events": []},
            desktop_api.CATALYST_CARDS_FILE: {"cards": []},
            desktop_api.SETTINGS_FILE: {},
            desktop_api.TRACKED_WALLETS_FILE: [],
            desktop_api.WALLET_PERFORMANCE_FILE: {"wallets": {}, "signals": []},
            desktop_api.WALLET_BEHAVIOR_FILE: {"wallets": {}},
            desktop_api.CANDIDATE_WALLETS_FILE: {"candidates": []},
            desktop_api.PAPER_WATCH_WALLETS_FILE: {"wallets": []},
            desktop_api.WALLET_REVIEW_DECISIONS_FILE: {"decisions": []},
        }

        def fake_read_json(path, default):
            return files.get(path, default)

        with mock.patch.object(desktop_api, "fetch_trade_rows", return_value=[
            {"status": "open", "payload": {"mint": "MintSqlOpen", "status": "open"}},
        ]):
            with mock.patch.object(desktop_api, "read_json", side_effect=fake_read_json) as read_json:
                with mock.patch.object(desktop_api, "load_status", return_value={}):
                    state = desktop_api.read_state_files()

        self.assertEqual(state["paper"]["open_trades"][0]["mint"], "MintSqlOpen")
        self.assertIn(desktop_api.PAPER_TRADES_FILE, [call.args[0] for call in read_json.call_args_list])

    def test_alerts_payload_prefers_sqlite_source_of_truth(self):
        live_state = {"alerts": [{"mint": "MintLive", "score": 88}]}
        with mock.patch.object(desktop_api, "fetch_alert_rows", return_value=[
            {"payload": {"mint": "MintSql", "score": 91, "type": "cluster"}},
        ]):
            with mock.patch.object(desktop_api, "safe_sqlite_counts", return_value={"alerts": 3}):
                payload = desktop_api.build_alerts_payload(live_state)

        self.assertEqual(payload["source"], "sqlite_alerts")
        self.assertEqual(payload["source_detail"], "data/memetrader.db:alerts")
        self.assertEqual(payload["source_contract"]["alerts"], "sqlite_alerts")
        self.assertEqual(payload["fallback_source"], "live_state_alerts")
        self.assertEqual(payload["live_state_count"], 1)
        self.assertEqual(payload["sqlite_mirror_count"], 3)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["mint"], "MintSql")
        self.assertIn("differs", payload["mirror_warning"])

    def test_alerts_payload_falls_back_to_live_state_when_sqlite_empty(self):
        live_state = {"alerts": [{"mint": "MintLive", "score": 88}]}
        with mock.patch.object(desktop_api, "fetch_alert_rows", return_value=[]):
            with mock.patch.object(desktop_api, "safe_sqlite_counts", return_value={"alerts": 0}):
                payload = desktop_api.build_alerts_payload(live_state)

        self.assertEqual(payload["source"], "live_state_alerts")
        self.assertEqual(payload["source_detail"], "live_state.json")
        self.assertEqual(payload["source_contract"]["alerts"], "live_state_alerts")
        self.assertEqual(payload["fallback_source"], "sqlite_alerts")
        self.assertEqual(payload["fallback_reason"], "sqlite_alerts_empty")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["mint"], "MintLive")
        self.assertIsNone(payload["mirror_warning"])

    def test_fetch_alert_rows_falls_back_to_summary_columns_when_payload_is_malformed(self):
        fake_row = {
            "time": 123.0,
            "mint": "MintBadPayload",
            "signal_type": "cluster",
            "total_score": 71,
            "edge_score": 64,
            "edge_verdict": "EDGE",
            "should_trade": 1,
            "risk_label": "LOW_RISK",
            "payload_json": "{bad",
        }
        with mock.patch.object(desktop_api, "read_sqlite_rows", return_value=[fake_row]):
            rows = desktop_api.fetch_alert_rows(limit=10)

        self.assertEqual(rows[0]["payload"]["mint"], "MintBadPayload")
        self.assertEqual(rows[0]["payload"]["type"], "cluster")
        self.assertEqual(rows[0]["payload"]["total_score"], 71)
        self.assertTrue(rows[0]["payload"]["should_trade"])

    def test_alerts_route_uses_alerts_source_contract(self):
        with mock.patch.object(desktop_api, "fetch_alert_rows", return_value=[
            {"payload": {"mint": "MintRouteSql"}},
        ]):
            with mock.patch.object(desktop_api, "read_json", return_value={"alerts": [{"mint": "MintRoute"}]}):
                with mock.patch.object(desktop_api, "safe_sqlite_counts", return_value={"alerts": 1}):
                    status, _, body = desktop_api.route_request("GET", "/api/alerts")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["source"], "sqlite_alerts")
        self.assertEqual(payload["source_detail"], "data/memetrader.db:alerts")
        self.assertIsNone(payload["mirror_warning"])
        self.assertEqual(payload["items"][0]["mint"], "MintRouteSql")

    def test_add_protected_token_payload_is_watch_only_and_adds_row(self):
        payload = {
            "mint": "MintProtect111111111111111111111111111",
            "wallet": "Wallet111",
            "amount": "123.5",
            "decimals": "6",
            "alert_only": True,
            "exit_priority": "immediate",
            "test": True,
        }

        with mock.patch.object(desktop_api, "read_json", return_value=[]):
            with mock.patch.object(desktop_api, "locked_update_json", side_effect=lambda _path, _default, updater: updater([])):
                response = desktop_api.add_protected_token_payload(payload)

        self.assertEqual(response["mode"], "PROTECTED_WATCH_ONLY")
        self.assertTrue(response["live_execution_locked"])
        self.assertFalse(response["auto_sell_enabled"])
        self.assertEqual(response["item"]["token_mint"], "MintProtect111111111111111111111111111")
        self.assertEqual(response["item"]["wallet"], "Wallet111")
        self.assertEqual(response["item"]["status"], "WATCHING")
        self.assertEqual(response["item"]["token_amount_raw"], 123500000)
        self.assertTrue(response["item"]["test_amount"])

    def test_mutation_routes_are_not_allowed(self):
        status, content_type, body = desktop_api.route_request("POST", "/api/positions")

        self.assertEqual(status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertIn("text/plain", content_type)
        self.assertIn(b"Mutation routes are not available", body)

    def test_protected_amount_metadata_route_updates_watchlist_only(self):
        rows = [{
            "token_mint": "Mint111",
            "wallet": "",
            "prepared_exit": {"quote_status": "amount_missing", "quote_reason": "token_amount_missing"},
        }]
        body = json.dumps({
            "mint": "Mint111",
            "amount": "42.5",
            "decimals": "6",
            "test": True,
        }).encode("utf-8")
        with mock.patch.object(desktop_api, "WATCHLIST_FILE", desktop_api.ROOT / "data" / "fake_watchlist.json"):
            with mock.patch.object(desktop_api, "read_json", return_value=rows):
                with mock.patch.object(desktop_api, "locked_update_json", side_effect=lambda _path, _default, updater: updater(rows)):
                    status, content_type, response_body = desktop_api.route_request("POST", "/api/watchlist/protected-amount", body)
        payload = json.loads(response_body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["mode"], "PROTECTED_METADATA_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["auto_sell_enabled"])
        self.assertEqual(payload["item"]["token_amount"], 42.5)
        self.assertEqual(payload["item"]["token_amount_raw"], 42500000)
        self.assertTrue(payload["item"]["test_amount"])
        self.assertEqual(payload["item"]["prepared_exit"]["quote_status"], "pending")

    def test_metadata_post_requires_session_token_when_configured(self):
        body = json.dumps({"mint": "Mint111", "amount": "1", "decimals": "6"}).encode("utf-8")
        with mock.patch.object(desktop_api, "DESKTOP_API_TOKEN", "secret-token"):
            status, _, response_body = desktop_api.route_request("POST", "/api/watchlist/protected-amount", body)
            payload = json.loads(response_body)

            self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
            self.assertIn("session token", payload["error"])

            with mock.patch.object(desktop_api, "read_json", return_value=[]):
                with mock.patch.object(desktop_api, "locked_update_json", side_effect=lambda _path, _default, updater: updater([])):
                    status, _, response_body = desktop_api.route_request(
                        "POST",
                        "/api/watchlist/protected-amount",
                        body,
                        headers={"X-MemeTraderPro-Token": "secret-token"},
                    )

            self.assertEqual(status, HTTPStatus.BAD_REQUEST)

    def test_static_index_embeds_session_token_for_same_origin_app(self):
        with mock.patch.object(desktop_api, "DESKTOP_API_TOKEN", "secret-token"):
            status, content_type, body = desktop_api.static_response("/")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn(b"window.__MTP_API_TOKEN = \"secret-token\"", body)

    def test_session_file_records_running_process_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = desktop_api.Path(temp_dir) / "desktop_api_session.json"
            with mock.patch.object(desktop_api, "SESSION_FILE", session_file):
                payload = desktop_api.write_desktop_session_file("secret-token")

            stored = json.loads(session_file.read_text())

        self.assertEqual(payload["token"], "secret-token")
        self.assertEqual(stored["token"], "secret-token")
        self.assertEqual(stored["process_id"], desktop_api.os.getpid())
        self.assertEqual(stored["started_at"], desktop_api.SERVER_STARTED_AT)

    def test_protected_amount_metadata_route_rejects_bad_amount(self):
        body = json.dumps({"mint": "Mint111", "amount": "-1", "decimals": "6"}).encode("utf-8")

        status, _, response_body = desktop_api.route_request("POST", "/api/watchlist/protected-amount", body)
        payload = json.loads(response_body)

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertTrue(payload["live_execution_locked"])
        self.assertIn("greater than 0", payload["error"])

    def test_options_preflight_is_allowed_for_desktop_shell(self):
        status, _, body = desktop_api.route_request("OPTIONS", "/api/overview")

        self.assertEqual(status, HTTPStatus.NO_CONTENT)
        self.assertEqual(body, b"")

    def test_unknown_api_route_404s(self):
        status, _, body = desktop_api.route_request("GET", "/api/buy")

        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(body, b"Not found")

    def test_health_route_reports_execution_locked_metadata_mode(self):
        status, content_type, body = desktop_api.route_request("GET", "/api/health")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["mode"], "EXECUTION_LOCKED")
        self.assertTrue(payload["live_execution_locked"])
        self.assertTrue(payload["metadata_mutations_enabled"])
        self.assertFalse(payload["execution_mutations_enabled"])
        self.assertEqual(payload["process_id"], desktop_api.os.getpid())
        self.assertEqual(payload["session_started_at"], desktop_api.SERVER_STARTED_AT)

    def test_decisions_route_reads_canonical_decision_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_route_1",
                "timestamp": 123,
                "mint": "Mint111",
                "type": "cluster",
                "should_trade": False,
                "total_score": 55,
                "score_threshold": 68,
                "risk_label": "WARNING",
                "score_reasons": ["below threshold"],
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                status, content_type, body = desktop_api.route_request("GET", "/api/decisions?limit=10")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["source"], "decision_records")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["decision_id"], "dec_route_1")
        self.assertEqual(payload["items"][0]["final_action"], "skip")
        self.assertEqual(payload["items"][0]["action_reason"], "below threshold")

    def test_decisions_route_preserves_extended_decision_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_route_extended",
                "timestamp": 123,
                "mint": "MintExtended",
                "type": "cluster",
                "should_trade": False,
                "social_match": {
                    "matched": True,
                    "event_ids": ["social_1"],
                    "matched_keywords": ["launch"],
                },
                "catalyst_card_ids": ["card_1"],
                "holder_concentration_risk": "DANGER",
                "holder_concentration_metrics": {"holder_count": 9, "top_10_pct": 94.2},
                "buy_quote_pass": True,
                "buy_quote_route_count": 1,
                "sell_quote_pass": False,
                "sell_quote_reason": "no_route_plan",
                "sell_quote_route_count": 0,
                "score_reasons": ["exit liquidity blocked"],
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                status, content_type, body = desktop_api.route_request("GET", "/api/decisions?limit=10")

        payload = json.loads(body)
        item_payload = payload["items"][0]["payload"]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(item_payload["inputs"]["social_catalyst"]["event_ids"], ["social_1"])
        self.assertEqual(item_payload["rule_outcomes"]["holder_cluster"]["holder_risk_label"], "DANGER")
        self.assertEqual(item_payload["route_feasibility"]["buy"]["route_count"], 1)
        self.assertEqual(item_payload["route_feasibility"]["sell"]["reason"], "no_route_plan")

    def test_decisions_route_filters_quote_failed_and_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_quote_failed",
                "timestamp": 123,
                "mint": "MintQuoteFail",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": False,
                "buy_quote_pass": True,
                "sell_quote_pass": False,
                "score_reasons": ["exit liquidity blocked"],
            }))
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_exploration",
                "timestamp": 124,
                "mint": "MintExplore",
                "type": "cluster",
                "paper_lane": "exploration",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "score_reasons": ["near miss"],
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                status, _, body = desktop_api.route_request("GET", "/api/decisions?filter=quote_failed&lane=main")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["filter"], "quote_failed")
        self.assertEqual(payload["lane"], "main")
        self.assertEqual(payload["items"][0]["decision_id"], "dec_quote_failed")

    def test_decision_explanation_route_prefers_google_ai_explainer_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_ai_1",
                "timestamp": 123,
                "mint": "MintAi111",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": False,
                "buy_quote_pass": True,
                "sell_quote_pass": False,
                "sell_quote_reason": "no_route_plan",
                "score_reasons": ["exit liquidity blocked"],
            }))

            captured = {}

            def fake_generate(decision, api_key=None, model=None, timeout=20):
                captured["decision"] = decision
                captured["api_key"] = api_key
                captured["model"] = model
                captured["timeout"] = timeout
                return {
                    "text": "Skipped because the sell route failed while score was near threshold.",
                    "model": model,
                    "response_id": "resp_test",
                }

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.dict(desktop_api.os.environ, {
                    "GOOGLE_AI_API_KEY": "test-google-key",
                    "GOOGLE_AI_DECISION_EXPLAINER_MODEL": "test-gemini-model",
                }):
                    with mock.patch.object(desktop_api, "generate_google_decision_explanation", side_effect=fake_generate):
                        status, content_type, body = desktop_api.route_request("GET", "/api/decisions/dec_ai_1/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["advisory_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["execution_routes_enabled"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "google_ai_decision_explainer")
        self.assertEqual(payload["provider"], "google_ai")
        self.assertEqual(payload["advisory"], "Skipped because the sell route failed while score was near threshold.")
        self.assertEqual(payload["model"], "test-gemini-model")
        self.assertEqual(captured["api_key"], "test-google-key")
        self.assertEqual(captured["decision"]["decision_id"], "dec_ai_1")
        self.assertEqual(captured["decision"]["payload"]["route_feasibility"]["sell"]["reason"], "no_route_plan")

    def test_decision_explanation_falls_back_to_openai_when_google_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_openai_fallback",
                "timestamp": 123,
                "mint": "MintOpenAi111",
                "type": "cluster",
                "should_trade": False,
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.dict(desktop_api.os.environ, {
                    "GOOGLE_AI_API_KEY": "",
                    "OPENAI_API_KEY": "test-openai-key",
                    "OPENAI_DECISION_EXPLAINER_MODEL": "test-openai-model",
                }):
                    with mock.patch.object(desktop_api, "generate_decision_explanation", return_value={
                        "text": "OpenAI fallback explanation.",
                        "model": "test-openai-model",
                        "response_id": "resp_test",
                    }) as generate:
                        status, _, body = desktop_api.route_request("GET", "/api/decisions/dec_openai_fallback/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["source"], "openai_decision_explainer")
        self.assertEqual(payload["advisory"], "OpenAI fallback explanation.")
        generate.assert_called_once()

    def test_decision_explanation_uses_groq_when_google_hits_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_groq_fallback",
                "timestamp": 123,
                "mint": "MintGroq111",
                "type": "cluster",
                "should_trade": False,
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.dict(desktop_api.os.environ, {
                    "GOOGLE_AI_API_KEY": "test-google-key",
                    "GROQ_API_KEY": "test-groq-key",
                    "GROQ_DECISION_EXPLAINER_MODEL": "test-groq-model",
                    "OPENAI_API_KEY": "",
                }):
                    with mock.patch.object(
                        desktop_api,
                        "generate_google_decision_explanation",
                        side_effect=RuntimeError("Google AI request failed with HTTP 429: quota exceeded"),
                    ) as google_generate:
                        with mock.patch.object(desktop_api, "generate_groq_decision_explanation", return_value={
                            "text": "Groq fallback explanation.",
                            "model": "test-groq-model",
                            "response_id": "groq_resp",
                        }) as groq_generate:
                            status, _, body = desktop_api.route_request("GET", "/api/decisions/dec_groq_fallback/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["provider"], "groq")
        self.assertEqual(payload["source"], "groq_decision_explainer")
        self.assertEqual(payload["fallback_from"], "google_ai")
        self.assertEqual(payload["attempted_providers"], ["google_ai", "groq"])
        self.assertEqual(payload["advisory"], "Groq fallback explanation.")
        google_generate.assert_called_once()
        groq_generate.assert_called_once()

    def test_decision_explanation_does_not_use_groq_for_non_limit_google_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_google_error",
                "timestamp": 123,
                "mint": "MintGoogleError111",
                "type": "cluster",
                "should_trade": False,
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.dict(desktop_api.os.environ, {
                    "GOOGLE_AI_API_KEY": "test-google-key",
                    "GROQ_API_KEY": "test-groq-key",
                    "OPENAI_API_KEY": "",
                }):
                    with mock.patch.object(
                        desktop_api,
                        "generate_google_decision_explanation",
                        side_effect=RuntimeError("Google AI request failed with HTTP 400: invalid request"),
                    ):
                        with mock.patch.object(desktop_api, "generate_groq_decision_explanation") as groq_generate:
                            status, _, body = desktop_api.route_request("GET", "/api/decisions/dec_google_error/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertFalse(payload["available"])
        self.assertEqual(payload["provider"], "google_ai")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["attempted_providers"], ["google_ai"])
        groq_generate.assert_not_called()

    def test_decision_explanation_missing_key_is_unavailable_without_external_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_ai_missing_key",
                "timestamp": 123,
                "mint": "MintNoKey111",
                "type": "cluster",
                "should_trade": False,
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.dict(desktop_api.os.environ, {"GOOGLE_AI_API_KEY": "", "GROQ_API_KEY": "", "OPENAI_API_KEY": ""}):
                    with mock.patch.object(desktop_api, "generate_google_decision_explanation") as google_generate:
                        with mock.patch.object(desktop_api, "generate_groq_decision_explanation") as groq_generate:
                            with mock.patch.object(desktop_api, "generate_decision_explanation") as openai_generate:
                                status, _, body = desktop_api.route_request("GET", "/api/decisions/dec_ai_missing_key/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertFalse(payload["available"])
        self.assertEqual(payload["status"], "missing_api_key")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertNotIn("OPENAI_API_KEY=", json.dumps(payload))
        self.assertNotIn("GOOGLE_AI_API_KEY=", json.dumps(payload))
        self.assertNotIn("GROQ_API_KEY=", json.dumps(payload))
        google_generate.assert_not_called()
        groq_generate.assert_not_called()
        openai_generate.assert_not_called()

    def test_decision_explanation_unknown_decision_404s(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            EventStore(db_path)

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                status, _, body = desktop_api.route_request("GET", "/api/decisions/not_found/explanation")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertTrue(payload["live_execution_locked"])
        self.assertIn("decision_id not found", payload["error"])

    def test_decision_lane_report_summarizes_decision_record_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            main_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_main_win",
                "timestamp": 123,
                "mint": "MintMain",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "score_reasons": ["main entry"],
            }))
            store.update_decision_action(main_id, {
                "final_action": "paper_opened",
                "paper_lane": "main",
                "reason": "paper entry opened",
            })
            store.update_decision_result(main_id, {
                "trade_status": "closed",
                "pnl": 12.5,
                "pnl_pct": 41,
                "exit_reason": "target_profit",
            })
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_main_quote_fail",
                "timestamp": 124,
                "mint": "MintSkip",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": False,
                "buy_quote_pass": True,
                "sell_quote_pass": False,
                "score_reasons": ["exit liquidity blocked"],
            }))
            exploration_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_explore_loss",
                "timestamp": 125,
                "mint": "MintExplore",
                "type": "cluster",
                "paper_lane": "exploration",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "score_reasons": ["near miss"],
            }))
            store.update_decision_action(exploration_id, {
                "final_action": "paper_opened",
                "paper_lane": "exploration",
                "reason": "exploration paper entry opened",
            })
            store.update_decision_result(exploration_id, {
                "trade_status": "closed",
                "pnl": -4,
                "pnl_pct": -40,
                "exit_reason": "hard_stop_loss",
            })
            radar_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_radar_win",
                "timestamp": 126,
                "mint": "MintRadar",
                "type": "market_radar_hot",
                "paper_lane": "market_radar",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "score_reasons": ["hot market radar"],
            }))
            store.update_decision_action(radar_id, {
                "final_action": "paper_opened",
                "paper_lane": "market_radar",
                "reason": "market radar paper entry opened",
            })
            store.update_decision_result(radar_id, {
                "trade_status": "closed",
                "pnl": 8,
                "pnl_pct": 30,
                "exit_reason": "target_profit",
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                report = desktop_api.build_decision_lane_report_payload(state={
                    "watchlist": [{"mint": "ProtectedMint"}],
                })

        self.assertEqual(report["source"], "sqlite_decision_records")
        self.assertEqual(report["total_decisions"], 4)
        self.assertEqual(report["lanes"]["main"]["candidate_decisions"], 2)
        self.assertEqual(report["lanes"]["main"]["paper_opened"], 1)
        self.assertEqual(report["lanes"]["main"]["quote_failed"], 1)
        self.assertEqual(report["lanes"]["main"]["closed_trades"], 1)
        self.assertEqual(report["lanes"]["main"]["win_rate"], 100.0)
        self.assertEqual(report["lanes"]["main"]["total_pnl"], 12.5)
        self.assertEqual(report["lanes"]["market_radar"]["closed_trades"], 1)
        self.assertEqual(report["lanes"]["market_radar"]["total_pnl"], 8)
        self.assertEqual(report["lanes"]["co_main"]["candidate_decisions"], 3)
        self.assertEqual(report["lanes"]["co_main"]["closed_trades"], 2)
        self.assertEqual(report["lanes"]["co_main"]["total_pnl"], 20.5)
        self.assertEqual(report["lanes"]["exploration"]["closed_trades"], 1)
        self.assertEqual(report["lanes"]["exploration"]["win_rate"], 0.0)
        self.assertEqual(report["lanes"]["exploration"]["total_pnl"], -4)
        self.assertEqual(report["lanes"]["protected_manual"]["protected_positions"], 1)

    def test_paper_review_includes_decision_lane_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_review_lane",
                "timestamp": 123,
                "mint": "MintReview",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": False,
                "score_reasons": ["below threshold"],
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                payload = desktop_api.build_paper_review_payload({
                    "paper": {"open_trades": [], "closed_trades": [], "failed_trades": []},
                    "wallet_behavior": {"wallets": {}},
                    "watchlist": [],
                })

        self.assertEqual(payload["decision_lane_report"]["source"], "sqlite_decision_records")
        self.assertEqual(payload["decision_lane_report"]["lanes"]["main"]["skipped"], 1)

    def test_decision_lane_report_counts_market_radar_skip_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_radar_quote_skip",
                "timestamp": 126,
                "mint": "MintRadarSkip",
                "type": "market_radar_hot",
                "paper_lane": "market_radar",
                "should_trade": False,
                "buy_quote_pass": False,
                "sell_quote_pass": False,
                "score_reasons": ["market_radar_skip: shared_quote_cooldown_after_429"],
                "market_radar": {
                    "decision": {
                        "skip_reason": "shared_quote_cooldown_after_429",
                        "skip_bucket": "quote_or_route",
                        "quote_retryable": True,
                    },
                },
            }))
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_old_radar_skip",
                "timestamp": 125,
                "mint": "MintOldRadarSkip",
                "type": "market_radar_hot",
                "paper_lane": "market_radar",
                "should_trade": False,
                "buy_quote_pass": False,
                "sell_quote_pass": False,
                "score_reasons": ["hot_m5_activity"],
            }))

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                report = desktop_api.build_decision_lane_report_payload()

        radar = report["lanes"]["market_radar"]
        self.assertEqual(radar["skipped"], 2)
        self.assertEqual(radar["skip_reasons"]["shared_quote_cooldown_after_429"], 1)
        self.assertNotIn("hot_m5_activity", radar["skip_reasons"])
        self.assertEqual(radar["skip_buckets"]["quote_or_route"], 1)

    def test_decision_lane_report_normalizes_protected_and_result_lanes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_manual",
                "timestamp": 123,
                "mint": "MintManual",
                "type": "manual_protection",
                "paper_lane": "manual",
                "should_trade": False,
                "score_reasons": ["protected manual review"],
            }))
            result_lane_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_result_lane",
                "timestamp": 124,
                "mint": "MintResultLane",
                "type": "cluster",
                "should_trade": True,
                "score_reasons": ["entry"],
            }))
            store.update_decision_result(result_lane_id, {
                "trade_status": "closed",
                "pnl": 2,
                "pnl_pct": 20,
                "paper_outcome": {"paper_lane": "exploration"},
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                report = desktop_api.build_decision_lane_report_payload(state={"watchlist": []})

        self.assertEqual(report["lanes"]["protected_manual"]["candidate_decisions"], 1)
        self.assertEqual(report["lanes"]["exploration"]["closed_trades"], 1)
        self.assertEqual(report["lanes"]["main"]["candidate_decisions"], 0)

    def test_decision_outcome_analytics_groups_labeled_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            social_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_social_win",
                "timestamp": 123,
                "mint": "MintSocial",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "social_match": {"matched": True, "reason": "social_exact_mint_match"},
                "score_reasons": ["social plus wallets"],
            }))
            store.update_decision_action(social_id, {"final_action": "paper_opened", "paper_lane": "main"})
            store.update_decision_result(social_id, {"trade_status": "closed", "pnl": 20, "pnl_pct": 80})
            wallet_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_wallet_loss",
                "timestamp": 124,
                "mint": "MintWallet",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "wallets": ["Wallet111", "Wallet222"],
                "score_reasons": ["wallet cluster"],
            }))
            store.update_decision_action(wallet_id, {"final_action": "paper_opened", "paper_lane": "main"})
            store.update_decision_result(wallet_id, {"trade_status": "closed", "pnl": -10, "pnl_pct": -40})
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_quote_fail",
                "timestamp": 125,
                "mint": "MintQuote",
                "type": "cluster",
                "paper_lane": "main",
                "should_trade": False,
                "buy_quote_pass": True,
                "sell_quote_pass": False,
                "score_reasons": ["exit liquidity blocked"],
            }))
            radar_id = store.upsert_decision(build_decision_record({
                "decision_id": "dec_radar_win",
                "timestamp": 126,
                "mint": "MintRadar",
                "type": "market_radar_hot",
                "paper_lane": "market_radar",
                "should_trade": True,
                "buy_quote_pass": True,
                "sell_quote_pass": True,
                "score_reasons": ["hot market radar"],
            }))
            store.update_decision_action(radar_id, {"final_action": "paper_opened", "paper_lane": "market_radar"})
            store.update_decision_result(radar_id, {"trade_status": "closed", "pnl": 6, "pnl_pct": 60})

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                payload = desktop_api.build_decision_outcome_analytics_payload(limit=100)

        self.assertEqual(payload["source"], "sqlite_decision_records")
        self.assertEqual(payload["groups"]["social_catalyst"]["closed_trades"], 1)
        self.assertEqual(payload["groups"]["social_catalyst"]["win_rate"], 100.0)
        self.assertEqual(payload["groups"]["wallet_only"]["closed_trades"], 1)
        self.assertEqual(payload["groups"]["wallet_only"]["total_pnl"], -10)
        self.assertEqual(payload["groups"]["quote_failed"]["candidate_decisions"], 1)
        self.assertEqual(payload["lanes"]["market_radar"]["closed_trades"], 1)
        self.assertEqual(payload["lanes"]["co_main"]["closed_trades"], 3)
        self.assertEqual(payload["lanes"]["co_main"]["total_pnl"], 16)
        self.assertFalse(payload["social_expansion_gate"]["allowed"])
        self.assertIn("labeled social outcomes", payload["social_expansion_gate"]["reason"])

    def test_decision_analytics_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_decision_outcome_analytics_payload", return_value={
            "generated_at": 123,
            "source": "sqlite_decision_records",
            "live_execution_locked": True,
            "total_decisions": 0,
            "groups": {},
            "social_expansion_gate": {"allowed": False},
        }):
            status, content_type, body = desktop_api.route_request("GET", "/api/decision-analytics?limit=25")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["social_expansion_gate"]["allowed"])

    def test_runtime_summary_includes_open_position_monitor(self):
        payload = desktop_api.summarize_runtime({
            "scanner": {"updated_at": desktop_api.time.time(), "status": "ok"},
            "open_position_monitor": {"updated_at": desktop_api.time.time(), "status": "complete"},
        })

        names = {row["name"] for row in payload["components"]}
        self.assertIn("open_position_monitor", names)

    def test_runtime_summary_flags_stale_wallet_feed_when_scanner_heartbeat_is_fresh(self):
        now = desktop_api.time.time()
        runtime = {
            "bot": {"status": "alive", "updated_at": now},
            "scanner": {
                "status": "listening",
                "updated_at": now,
                "last_swap_tick_at": now - 900,
                "wallet_feed_fresh_seconds": 300,
            },
            "websocket": {"status": "subscribed", "updated_at": now},
        }

        summary = desktop_api.summarize_runtime(runtime)
        scanner = next(row for row in summary["components"] if row["name"] == "scanner")

        self.assertFalse(scanner["fresh"])
        self.assertIn("wallet feed stale", scanner["detail"])
        self.assertIn("scanner", summary["stale_components"])

    def test_runtime_summary_treats_old_quote_ok_as_idle_healthy(self):
        now = desktop_api.time.time()
        runtime = {
            "quotes": {
                "status": "quote_ok",
                "updated_at": now - 900,
                "last_error": "",
            },
        }

        summary = desktop_api.summarize_runtime(runtime)
        quotes = next(row for row in summary["components"] if row["name"] == "quotes")

        self.assertTrue(quotes["fresh"])
        self.assertEqual(quotes["state"], "quote_ok")
        self.assertIn("idle", quotes["detail"])

    def test_runtime_summary_treats_expired_quote_cooldown_as_idle_healthy(self):
        now = desktop_api.time.time()
        runtime = {
            "quotes": {
                "status": "cooldown_after_429",
                "updated_at": now - 900,
            },
        }

        summary = desktop_api.summarize_runtime(runtime)
        quotes = next(row for row in summary["components"] if row["name"] == "quotes")

        self.assertTrue(quotes["fresh"])
        self.assertEqual(quotes["state"], "cooldown_after_429")
        self.assertIn("expired", quotes["detail"])

    def test_runtime_summary_keeps_quote_errors_unhealthy_even_when_recent(self):
        now = desktop_api.time.time()
        runtime = {
            "quotes": {
                "status": "quote_exception",
                "updated_at": now,
                "last_error": "Jupiter timeout",
            },
        }

        summary = desktop_api.summarize_runtime(runtime)
        quotes = next(row for row in summary["components"] if row["name"] == "quotes")

        self.assertFalse(quotes["fresh"])
        self.assertIn("Jupiter timeout", quotes["detail"])

    def test_runtime_summary_does_not_fail_scanner_when_events_are_flowing_but_route_ticks_are_quiet(self):
        now = desktop_api.time.time()
        runtime = {
            "bot": {"status": "alive", "updated_at": now},
            "scanner": {
                "status": "listening",
                "updated_at": now,
                "wallet_events": 25,
                "last_swap_tick_at": now - 900,
                "wallet_feed_fresh_seconds": 300,
            },
            "websocket": {"status": "subscribed", "updated_at": now},
        }

        summary = desktop_api.summarize_runtime(runtime)
        scanner = next(row for row in summary["components"] if row["name"] == "scanner")

        self.assertTrue(scanner["fresh"])
        self.assertIn("route-backed swap ticks quiet", scanner["detail"])
        self.assertNotIn("scanner", summary["stale_components"])

    def test_runtime_summary_respects_component_heartbeat_interval(self):
        now = desktop_api.time.time()
        runtime = {
            "wallet_discovery": {
                "status": "cycle_ok",
                "updated_at": now - 120,
                "heartbeat_interval": 300,
            },
        }

        summary = desktop_api.summarize_runtime(runtime)
        wallet_discovery = next(row for row in summary["components"] if row["name"] == "wallet_discovery")

        self.assertTrue(wallet_discovery["fresh"])

    def test_cors_only_allows_local_desktop_origins(self):
        self.assertEqual(
            desktop_api.allowed_cors_origin("http://127.0.0.1:5173"),
            "http://127.0.0.1:5173",
        )
        self.assertEqual(
            desktop_api.allowed_cors_origin("http://localhost:5173"),
            "http://localhost:5173",
        )
        self.assertIsNone(desktop_api.allowed_cors_origin("http://localhost:8765"))
        self.assertEqual(
            desktop_api.allowed_cors_origin("tauri://localhost"),
            "tauri://localhost",
        )
        self.assertIsNone(desktop_api.allowed_cors_origin("https://localhost:5173"))
        self.assertIsNone(desktop_api.allowed_cors_origin("https://example.com"))
        self.assertIsNone(desktop_api.allowed_cors_origin("null"))

    def test_candidate_feed_rejects_unsafe_image_urls(self):
        item = desktop_api.compact_candidate_snapshot({
            "time": 200,
            "mint": "Mint111",
            "source": "scanner",
            "context": "scanner_skip",
            "market_info": {
                "image_url": "data:image/svg+xml;base64,PHN2Zy8+",
            },
        })

        self.assertIsNone(item["image_url"])

    def test_safe_route_request_converts_uncaught_errors_to_500(self):
        with mock.patch.object(desktop_api, "route_request", side_effect=RuntimeError("boom")):
            status, content_type, body = desktop_api.safe_route_request("GET", "/api/overview")

        self.assertEqual(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("application/json", content_type)
        self.assertIn(b"Internal desktop API error", body)
        self.assertNotIn(b"boom", body)

    def test_malformed_query_params_fall_back_to_safe_defaults(self):
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=[]):
            status, _, body = desktop_api.route_request("GET", "/api/candles?mint=Mint111&limit=bad&interval=nope")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["snapshot_count"], 0)
        self.assertEqual(payload["interval_seconds"], 1)

    def test_path_params_are_decoded_before_lookup(self):
        with mock.patch.object(desktop_api, "build_wallet_detail_payload", return_value={"wallet": "Wallet Test"}) as build_detail:
            status, _, body = desktop_api.route_request("GET", "/api/wallets/Wallet%20Test")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(json.loads(body)["wallet"], "Wallet Test")
        build_detail.assert_called_once()
        self.assertEqual(build_detail.call_args.args[0], "Wallet Test")

    def test_token_candles_alias_uses_mint(self):
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=[]):
            status, _, body = desktop_api.route_request("GET", "/api/tokens/Mint111/candles")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["mint"], "Mint111")

    def test_snapshots_payload_declares_sqlite_source_of_truth(self):
        rows = [{"mint": "Mint111", "time": 123.0, "source": "scanner"}]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_snapshots_payload(mint="Mint111", limit=25)

        self.assertEqual(payload["source"], "sqlite_token_snapshots")
        self.assertEqual(payload["source_detail"], "data/memetrader.db:token_snapshots")
        self.assertEqual(payload["source_contract"]["snapshots"], "sqlite_token_snapshots")
        self.assertEqual(payload["source_contract"]["trades"], "paper_trades_json")
        self.assertEqual(payload["snapshot_count"], 1)
        self.assertEqual(payload["snapshots"], rows)

    def test_candles_route_without_mint_does_not_scan_all_tokens(self):
        with mock.patch.object(desktop_api, "fetch_snapshot_rows") as fetch_rows:
            status, _, body = desktop_api.route_request("GET", "/api/candles")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["snapshot_count"], 0)
        fetch_rows.assert_not_called()

    def test_positions_payload_compacts_sources(self):
        payload = desktop_api.build_positions_payload({
            "paper": {
                "open_trades": [{
                    "token_mint": "Mint111",
                    "symbol": "MTP",
                    "status": "open",
                    "current_price": 0.1,
                    "total_pnl_pct": 12.5,
                }]
            },
            "watchlist": [],
        })

        self.assertEqual(payload["positions"][0]["mint"], "Mint111")
        self.assertEqual(payload["positions"][0]["label"], "MTP")
        self.assertFalse(payload["positions"][0]["live_action_allowed"])

    def test_position_detail_declares_mixed_json_and_sqlite_sources(self):
        state = {
            "paper": {
                "open_trades": [{
                    "token_mint": "Mint111",
                    "symbol": "MTP",
                    "status": "open",
                    "current_price": 0.12,
                }]
            },
            "watchlist": [],
            "social": {"events": []},
            "catalysts": {"cards": []},
            "wallet_performance": {"wallets": {}, "signals": []},
            "wallet_behavior": {"wallets": {}},
        }
        snapshots = [{"mint": "Mint111", "time": 123.0, "market_info": {"market_cap": 12345}}]
        with mock.patch.object(desktop_api, "read_state_files", return_value=state):
            with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=snapshots):
                payload = desktop_api.build_position_detail_payload("Mint111")

        self.assertEqual(payload["position_source"], "paper_trades_json")
        self.assertEqual(payload["position_source_detail"], "data/paper_trades.json")
        self.assertEqual(payload["snapshot_source"], "sqlite_token_snapshots")
        self.assertEqual(payload["snapshot_source_detail"], "data/memetrader.db:token_snapshots")
        self.assertTrue(payload["mixed_market_fields"])
        self.assertEqual(payload["source_contract"]["position"], "paper_trades_json")
        self.assertEqual(payload["source_contract"]["snapshots"], "sqlite_token_snapshots")
        self.assertEqual(payload["source_contract"]["social"], "social_state_json")
        self.assertEqual(payload["source_contract"]["wallet_context"], "wallet_performance_json_and_wallet_behavior_json_and_paper_trades_json")
        self.assertEqual(payload["latest_snapshot"], snapshots[-1])

    def test_position_detail_declares_manual_watchlist_source(self):
        state = {
            "paper": {"open_trades": [], "closed_trades": [], "failed_trades": []},
            "watchlist": [{"token_mint": "MintWatch", "symbol": "WATCH", "status": "WATCHING"}],
            "social": {"events": []},
            "catalysts": {"cards": []},
            "wallet_performance": {"wallets": {}, "signals": []},
            "wallet_behavior": {"wallets": {}},
        }
        with mock.patch.object(desktop_api, "read_state_files", return_value=state):
            with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=[]):
                payload = desktop_api.build_position_detail_payload("MintWatch")

        self.assertEqual(payload["position_source"], "manual_watchlist_json")
        self.assertEqual(payload["position_source_detail"], "data/manual_watchlist.json")
        self.assertEqual(payload["source_contract"]["position"], "manual_watchlist_json")

    def test_position_detail_keeps_source_contract_without_selected_position(self):
        state = {
            "paper": {"open_trades": [], "closed_trades": [], "failed_trades": []},
            "watchlist": [],
            "social": {"events": []},
            "catalysts": {"cards": []},
            "wallet_performance": {"wallets": {}, "signals": []},
            "wallet_behavior": {"wallets": {}},
        }
        with mock.patch.object(desktop_api, "read_state_files", return_value=state):
            with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=[]):
                payload = desktop_api.build_position_detail_payload("MintMissing")

        self.assertIsNone(payload["position_source"])
        self.assertIsNone(payload["position_source_detail"])
        self.assertFalse(payload["mixed_market_fields"])
        self.assertEqual(payload["source_contract"]["position"], "paper_trades_json_or_manual_watchlist_json")
        self.assertEqual(payload["source_contract"]["snapshots"], "sqlite_token_snapshots")

    def test_compact_position_preserves_zero_values(self):
        compact = desktop_api.compact_position({
            "mint": "MintZero",
            "source": "paper",
            "current_price": 0,
            "current_market_cap": 0,
            "liquidity": 0,
            "holder_count": 0,
            "raw": {
                "current_price": 10,
                "market_cap": 10_000,
                "current_liquidity": 5000,
                "total_pnl_pct": 0,
                "pnl_pct": 12,
                "holder_concentration_metrics": {"holder_count": 44},
            },
        })

        self.assertEqual(compact["price"], 0)
        self.assertEqual(compact["market_cap"], 0)
        self.assertEqual(compact["liquidity"], 0)
        self.assertEqual(compact["pnl_pct"], 0)
        self.assertEqual(compact["holder_count"], 0)

    def test_wallet_trade_summary_preserves_zero_pnl(self):
        summary = desktop_api.summarize_wallet_trade({
            "mint": "MintZero",
            "total_pnl_pct": 0,
            "pnl_pct": 22,
            "total_pnl": 0,
            "pnl": 10,
        }, "open_trades")

        self.assertEqual(summary["pnl_pct"], 0)
        self.assertEqual(summary["pnl"], 0)

    def test_candidate_wallets_payload_is_watch_only(self):
        data = {
            "generated_at": 123,
            "mode": "WATCH_ONLY_REVIEW",
            "summary": {"candidate_wallets": 2, "untracked_wallets": 1, "tracked_wallets": 1},
            "source_counts": {"tracked_wallets": 518, "local_events": 5000},
            "candidates": [
                {
                    "wallet": "NewWallet111",
                    "score": 75,
                    "recommended_tier": "tier_2_confirm",
                    "already_tracked": False,
                    "early_buy_events": 8,
                    "winner_mints": 1,
                    "buy_events": 0,
                    "sell_events": 0,
                    "unique_mints": 1,
                    "reasons": ["8 early buy event(s)", "1 winner mint overlap(s)"],
                },
                {
                    "wallet": "Tracked111",
                    "score": 55,
                    "recommended_tier": "watch_only",
                    "already_tracked": True,
                    "early_buy_events": 0,
                    "winner_mints": 0,
                    "buy_events": 4,
                    "sell_events": 1,
                    "unique_mints": 3,
                    "reasons": ["4 local buy event(s)"],
                },
            ],
        }

        with mock.patch.object(desktop_api, "read_json", return_value=data):
            payload = desktop_api.build_candidate_wallets_payload(limit=1)

        self.assertEqual(payload["mode"], "WATCH_ONLY_REVIEW")
        self.assertTrue(payload["live_execution_locked"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["summary"]["untracked_wallets"], 1)
        self.assertEqual(payload["review_summary"]["paper_watch"], 1)
        self.assertEqual(payload["candidates"][0]["wallet"], "NewWallet111")
        self.assertFalse(payload["candidates"][0]["already_tracked"])
        self.assertEqual(payload["candidates"][0]["review"]["action"], "PAPER_WATCH")

    def test_candidate_wallets_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_candidate_wallets_payload", return_value={"candidates": []}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/candidate-wallets?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body), {"candidates": []})
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_lifecycle_payload_flags_promotion_and_demotion(self):
        state = {
            "tracked_wallets": [
                {"trackedWalletAddress": "TrackedBad"},
            ],
            "paper_watch_wallets": {
                "wallets": [{"wallet": "WatchWin", "status": "paper_watch"}],
            },
            "candidate_wallets": {"candidates": []},
            "wallet_performance": {
                "wallets": {
                    "TrackedBad": {"paper_entries": 4, "wins": 0, "losses": 4, "avg_pnl": -12, "score": 24},
                    "WatchWin": {"paper_entries": 6, "wins": 5, "losses": 1, "avg_pnl": 15, "score": 82},
                }
            },
        }

        payload = desktop_api.build_wallet_lifecycle_payload(state=state, limit=10)

        self.assertEqual(payload["mode"], "REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["summary"]["promotion_review"], 1)
        self.assertEqual(payload["summary"]["demote_review"], 1)
        actions = {row["wallet"]: row["lifecycle"]["action"] for row in payload["wallets"]}
        self.assertEqual(actions["WatchWin"], "PROMOTE_TO_TRUSTED_REVIEW")
        self.assertEqual(actions["TrackedBad"], "DEMOTE_OFF_WATCH_REVIEW")

    def test_wallet_lifecycle_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_lifecycle_payload", return_value={"wallets": []}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-lifecycle?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body), {"wallets": []})
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_review_decision_route_writes_approval_metadata_only(self):
        current = {"decisions": []}
        body = json.dumps({
            "wallet": "Wallet111",
            "decision": "approve_promotion",
            "approved": True,
            "note": "repeat winner",
        }).encode("utf-8")

        with mock.patch.object(desktop_api, "read_json", return_value=current):
            with mock.patch.object(desktop_api, "locked_update_json", side_effect=lambda _path, _default, updater: updater(current)):
                status, content_type, response_body = desktop_api.route_request("POST", "/api/wallet-review-decision", body)

        payload = json.loads(response_body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["mode"], "WALLET_REVIEW_DECISION_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["decision"]["wallet"], "Wallet111")
        self.assertEqual(payload["decision"]["decision"], "approve_promotion")
        self.assertEqual(payload["summary"]["approved_decisions"], 1)

    def test_wallet_review_decision_route_rejects_unknown_decision(self):
        body = json.dumps({
            "wallet": "Wallet111",
            "decision": "buy_now",
            "approved": True,
        }).encode("utf-8")

        status, _, response_body = desktop_api.route_request("POST", "/api/wallet-review-decision", body)
        payload = json.loads(response_body)

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("decision", payload["error"])
        self.assertTrue(payload["live_execution_locked"])

    def test_wallet_review_apply_route_returns_dry_run_preview_without_state_lists(self):
        result = {
            "dry_run": True,
            "stamp": "20260506T000000Z",
            "summary": {"promoted": 1, "demoted": 2, "skipped": 0, "approved_decisions": 3},
            "audit": {
                "changes": [{"wallet": "Wallet111", "action": "promoted_to_tracked"}],
                "skipped": [],
            },
            "tracked_wallets": [{"trackedWalletAddress": "Wallet111"}],
            "bad_wallets": [],
            "paper_watch_wallets": {"wallets": []},
        }

        with mock.patch.object(desktop_api, "run_wallet_review_apply", return_value=result) as run_apply:
            status, content_type, response_body = desktop_api.route_request("GET", "/api/wallet-review-apply")

        payload = json.loads(response_body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["summary"]["promoted"], 1)
        self.assertEqual(payload["changes"][0]["wallet"], "Wallet111")
        self.assertNotIn("tracked_wallets", payload)
        self.assertNotIn("bad_wallets", payload)
        run_apply.assert_called_once_with(dry_run=True)

    def test_wallet_review_apply_route_requires_exact_confirmation_for_apply(self):
        body = json.dumps({"confirm": "apply"}).encode("utf-8")

        with mock.patch.object(desktop_api, "run_wallet_review_apply") as run_apply:
            status, _, response_body = desktop_api.route_request("POST", "/api/wallet-review-apply", body)

        payload = json.loads(response_body)
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertIn("confirmation", payload["error"])
        self.assertTrue(payload["live_execution_locked"])
        run_apply.assert_not_called()

    def test_wallet_review_apply_route_applies_after_exact_confirmation(self):
        result = {
            "dry_run": False,
            "stamp": "20260506T000000Z",
            "backup_dir": "/tmp/wallet_apply",
            "summary": {"promoted": 0, "demoted": 1, "skipped": 0, "approved_decisions": 1},
            "audit": {
                "changes": [{"wallet": "Wallet222", "action": "demoted_from_tracked"}],
                "skipped": [],
            },
            "tracked_wallets": [],
            "bad_wallets": ["Wallet222"],
            "paper_watch_wallets": {"wallets": []},
        }
        body = json.dumps({"confirm": "APPLY_WALLET_REVIEW"}).encode("utf-8")

        with mock.patch.object(desktop_api, "run_wallet_review_apply", return_value=result) as run_apply:
            status, content_type, response_body = desktop_api.route_request("POST", "/api/wallet-review-apply", body)

        payload = json.loads(response_body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["backup_dir"], "/tmp/wallet_apply")
        self.assertEqual(payload["summary"]["demoted"], 1)
        run_apply.assert_called_once_with(dry_run=False)

    def test_candles_payload_is_json_serializable(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0},
            {"time": 101, "mint": "Mint111", "price": 1.2},
            {"time": 106, "mint": "Mint111", "price": 0.9},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111")

        encoded = json.dumps(payload)
        self.assertIn("Mint111", encoded)
        self.assertEqual(payload["interval_seconds"], 1)
        self.assertEqual(len(payload["candles"]), 3)
        self.assertEqual(payload["candles"][1]["open"], 1.0)
        self.assertEqual(payload["candles"][2]["color"], "red")

    def test_candles_payload_can_use_liquidity_metric(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "liquidity": 1000},
            {"time": 101, "mint": "Mint111", "price": 1.2, "liquidity": 1200},
            {"time": 106, "mint": "Mint111", "price": 0.9, "liquidity": 900},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111", metric="liquidity", interval_seconds=5)

        self.assertEqual(payload["metric"], "liquidity")
        self.assertEqual(payload["candles"][0]["open"], 1000)
        self.assertEqual(payload["candles"][0]["close"], 1200)

    def test_candles_payload_can_use_market_cap_metric(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "market_cap": 100_000},
            {"time": 101, "mint": "Mint111", "price": 1.2, "market_cap": 125_000},
            {"time": 106, "mint": "Mint111", "price": 0.9, "market_cap": 90_000},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111", metric="market_cap", interval_seconds=5)

        self.assertEqual(payload["metric"], "market_cap")
        self.assertEqual(payload["candles"][0]["open"], 100_000)
        self.assertEqual(payload["candles"][0]["close"], 125_000)

    def test_market_cap_candles_infer_sparse_opens_from_previous_close(self):
        rows = [
            {"time": 100, "mint": "Mint111", "market_cap": 100_000},
            {"time": 101, "mint": "Mint111", "market_cap": 125_000},
            {"time": 102, "mint": "Mint111", "market_cap": 90_000},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111", metric="market_cap", interval_seconds=1)

        self.assertEqual(payload["candles"][1]["open"], 100_000)
        self.assertEqual(payload["candles"][1]["close"], 125_000)
        self.assertEqual(payload["candles"][2]["open"], 125_000)
        self.assertEqual(payload["candles"][2]["close"], 90_000)
        self.assertEqual(payload["candles"][2]["color"], "red")

    def test_market_cap_candles_estimate_pump_market_cap_from_price_when_missing(self):
        rows = [
            {"time": 100, "mint": "Mint111pump", "price": 0.000001},
            {"time": 101, "mint": "Mint111pump", "price": 0.0000012},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            with mock.patch.object(desktop_api, "fetch_swap_tick_rows", return_value=[]):
                payload = desktop_api.build_candles_payload("Mint111pump", metric="market_cap", interval_seconds=1)

        self.assertEqual(payload["candles"][0]["close"], 1000)
        self.assertEqual(payload["candles"][1]["close"], 1200)

    def test_candles_payload_reports_sampled_quote_quality(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "source": "paper_trader", "context": "paper_price_update"},
            {"time": 101, "mint": "Mint111", "price": 1.0, "source": "paper_trader", "context": "paper_price_update"},
            {"time": 102, "mint": "Mint111", "price": 1.0, "source": "rug_watchdog", "context": "watchdog_check"},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111", metric="price", interval_seconds=1)

        self.assertEqual(payload["sample_kind"], "sampled_quote")
        self.assertEqual(payload["quality"]["distinct_value_count"], 1)
        self.assertEqual(payload["quality"]["source_contexts"]["paper_trader:paper_price_update"], 2)
        self.assertTrue(payload["quality"]["warning"])
        self.assertTrue(all(candle["synthetic"] for candle in payload["candles"][1:]))

    def test_candles_payload_prefers_swap_ticks_when_available(self):
        snapshots = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "market_cap": 1_000_000},
        ]
        ticks = [
            {"time": 100.1, "mint": "Mint111", "price": 1.0, "market_cap": 1_000_000, "source": "helius_swap"},
            {"time": 100.4, "mint": "Mint111", "price": 1.4, "market_cap": 1_400_000, "source": "helius_swap"},
            {"time": 101.1, "mint": "Mint111", "price": 1.2, "market_cap": 1_200_000, "source": "helius_swap"},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=snapshots):
            with mock.patch.object(desktop_api, "fetch_swap_tick_rows", return_value=ticks):
                payload = desktop_api.build_candles_payload("Mint111", metric="market_cap", interval_seconds=1)

        self.assertEqual(payload["sample_kind"], "swap_tick")
        self.assertEqual(payload["tick_count"], 3)
        self.assertTrue(payload["quality"]["trade_stream_active"])
        self.assertEqual(payload["candles"][0]["open"], 1_000_000)
        self.assertEqual(payload["candles"][0]["high"], 1_400_000)
        self.assertEqual(payload["candles"][0]["close"], 1_400_000)
        self.assertFalse(any(candle.get("synthetic") for candle in payload["candles"]))

    def test_invalid_candle_metric_falls_back_to_price(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "liquidity": 1000},
            {"time": 101, "mint": "Mint111", "price": 1.2, "liquidity": 1200},
        ]
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows):
            payload = desktop_api.build_candles_payload("Mint111", metric="unsupported")

        self.assertEqual(payload["metric"], "price")
        self.assertEqual(payload["candles"][0]["open"], 1.0)

    def test_snapshot_trend_reports_price_and_liquidity_change(self):
        rows = [
            {"time": 100, "mint": "Mint111", "price": 1.0, "liquidity": 1000, "source": "scanner", "context": "entry"},
            {"time": 110, "mint": "Mint111", "price": 1.5, "liquidity": 800, "source": "watchdog", "context": "check"},
        ]
        with mock.patch.object(desktop_api.time, "time", return_value=130):
            trend = desktop_api.build_snapshot_trend(rows)

        self.assertEqual(trend["price_change_pct"], 50.0)
        self.assertEqual(trend["liquidity_change_pct"], -20.0)
        self.assertEqual(trend["latest_source"], "watchdog")
        self.assertEqual(trend["latest_context"], "check")
        self.assertEqual(trend["latest_age_seconds"], 20)

    def test_candidate_feed_compacts_scanner_snapshots_with_images_and_reasons(self):
        rows = [
            {
                "time": 200,
                "mint": "MintSkip",
                "source": "scanner",
                "context": "scanner_skip",
                "price": 0.00002,
                "liquidity": 4400,
                "market_cap": 9200,
                "market_info": {
                    "name": "Skip Coin",
                    "symbol": "SKIP",
                    "image": "https://example.test/skip.png",
                    "tx_count": 44,
                    "holder_count": 18,
                },
                "should_trade": False,
                "skip_reason": "market_cap_above_meme_window",
                "score_reasons": ["Market sanity block"],
                "wallet_count": 3,
                "weighted_wallet_score": 1.7,
                "total_score": 41,
                "risk_label": "MEDIUM_RISK",
            },
            {
                "time": 100,
                "mint": "MintSkip",
                "source": "scanner",
                "context": "scanner_skip",
                "price": 0.00001,
                "liquidity": 2500,
                "market_info": {"symbol": "OLD"},
                "should_trade": False,
                "skip_reason": "old_reason",
            },
            {
                "time": 190,
                "mint": "MintReady",
                "source": "scanner",
                "context": "scanner_entry_candidate",
                "price": 0.00003,
                "liquidity": 8000,
                "market_cap": 16000,
                "market_info": {
                    "name": "Ready Coin",
                    "symbol": "READY",
                    "logoURI": "https://example.test/ready.png",
                    "transactions": {"total": 88},
                    "holders": 27,
                },
                "should_trade": True,
                "score_reasons": ["Wallet cluster passed"],
                "wallet_count": 5,
                "weighted_wallet_score": 2.8,
                "total_score": 76,
                "risk_label": "LOW_RISK",
            },
            {
                "time": 180,
                "mint": "WatchdogOnly",
                "source": "watchdog",
                "context": "watchdog_check",
                "price": 0.1,
            },
        ]

        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=rows) as fetch_rows:
            payload = desktop_api.build_candidate_feed_payload(limit=20)

        fetch_rows.assert_called_once_with(limit=100, newest_first=True)
        self.assertEqual(payload["count"], 2)
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual([item["mint"] for item in payload["items"]], ["MintSkip", "MintReady"])
        self.assertEqual(payload["items"][0]["symbol"], "SKIP")
        self.assertEqual(payload["items"][0]["image_url"], "https://example.test/skip.png")
        self.assertEqual(payload["items"][0]["tx_count"], 44)
        self.assertEqual(payload["items"][0]["holder_count"], 18)
        self.assertEqual(payload["items"][0]["status"], "SKIPPED")
        self.assertIn("market_cap_above_meme_window", payload["items"][0]["reasons"])
        self.assertEqual(payload["items"][1]["status"], "TRADE_READY")
        self.assertEqual(payload["items"][1]["image_url"], "https://example.test/ready.png")
        self.assertEqual(payload["items"][1]["tx_count"], 88)
        self.assertEqual(payload["items"][1]["holder_count"], 27)

    def test_candidate_feed_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_candidate_feed_payload", return_value={"items": []}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/candidates?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body), {"items": []})
        build_payload.assert_called_once_with(limit=12)

    def test_candidate_feed_fetches_extra_rows_before_filtering_and_dedupe(self):
        with mock.patch.object(desktop_api, "fetch_snapshot_rows", return_value=[]) as fetch_rows:
            desktop_api.build_candidate_feed_payload(limit=10)

        fetch_rows.assert_called_once_with(limit=50, newest_first=True)

    def test_candidate_feed_estimates_pump_market_cap_when_missing(self):
        item = desktop_api.compact_candidate_snapshot({
            "time": 200,
            "mint": "Mint111111111111111111111111111111111pump",
            "source": "scanner",
            "context": "scanner_skip",
            "price": 0.0000067,
            "liquidity": 4400,
            "should_trade": False,
        })

        self.assertEqual(item["market_cap"], 6700)
        self.assertTrue(item["market_cap_estimated"])

    def test_event_feed_compacts_recent_wallet_events(self):
        rows = [
            {
                "time": 200,
                "event_type": "buy",
                "wallet": "Wallet111",
                "mint": "Mint111",
                "payload": {
                    "amount": 42.5,
                    "wallet_quality_score": 71,
                    "wallet_performance_score": 64,
                    "combined_wallet_score": 68.2,
                },
            },
            {
                "time": 190,
                "event_type": "sell",
                "wallet": "Wallet222",
                "mint": "Mint222",
                "payload": {"amount": 10},
            },
        ]
        metadata = {
            "Mint111": {
                "name": "Metadata Coin",
                "symbol": "META",
                "image_url": "https://example.test/meta.png",
                "market_cap": 12345,
                "liquidity": 6789,
            }
        }

        with mock.patch.object(desktop_api, "fetch_event_rows", return_value=rows) as fetch_rows:
            with mock.patch.object(desktop_api, "fetch_event_metadata", return_value=metadata) as fetch_metadata:
                with mock.patch.object(desktop_api, "fetch_rpc_asset_metadata", return_value={}) as fetch_rpc_metadata:
                    with mock.patch.object(desktop_api.time, "time", return_value=205):
                        payload = desktop_api.build_event_feed_payload(limit=12)

        fetch_rows.assert_called_once_with(limit=12)
        fetch_metadata.assert_called_once_with(["Mint111", "Mint222"])
        fetch_rpc_metadata.assert_called_once_with(["Mint222"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["source"], "events")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["items"][0]["type"], "buy")
        self.assertEqual(payload["items"][0]["age_seconds"], 5)
        self.assertEqual(payload["items"][0]["amount"], 42.5)
        self.assertEqual(payload["items"][0]["wallet_quality_score"], 71)
        self.assertEqual(payload["items"][0]["combined_wallet_score"], 68.2)
        self.assertEqual(payload["items"][0]["name"], "Metadata Coin")
        self.assertEqual(payload["items"][0]["symbol"], "META")
        self.assertEqual(payload["items"][0]["image_url"], "https://example.test/meta.png")
        self.assertEqual(payload["items"][0]["market_cap"], 12345)
        self.assertEqual(payload["items"][0]["liquidity"], 6789)

    def test_event_feed_rejects_unsafe_metadata_images(self):
        rows = [{"time": 200, "event_type": "buy", "wallet": "Wallet111", "mint": "Mint111", "payload": {}}]
        metadata = {"Mint111": {"symbol": "BAD", "image_url": "data:image/svg+xml;base64,PHN2Zy8+"}}

        with mock.patch.object(desktop_api, "fetch_event_rows", return_value=rows):
            with mock.patch.object(desktop_api, "fetch_event_metadata", return_value=metadata):
                with mock.patch.object(desktop_api, "fetch_rpc_asset_metadata", return_value={}):
                    with mock.patch.object(desktop_api.time, "time", return_value=205):
                        payload = desktop_api.build_event_feed_payload(limit=12)

        self.assertEqual(payload["items"][0]["symbol"], "BAD")
        self.assertIsNone(payload["items"][0]["image_url"])

    def test_extracts_helius_asset_metadata_for_scanner_tape(self):
        metadata = desktop_api.extract_asset_metadata({
            "result": {
                "content": {
                    "metadata": {
                        "name": "Launch Token",
                        "symbol": "LAUNCH",
                    },
                    "links": {
                        "image": "https://example.test/launch.png",
                    },
                },
            },
        })

        self.assertEqual(metadata["name"], "Launch Token")
        self.assertEqual(metadata["symbol"], "LAUNCH")
        self.assertEqual(metadata["image_url"], "https://example.test/launch.png")

    def test_event_feed_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_event_feed_payload", return_value={"items": []}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/events?limit=24")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body), {"items": []})
        build_payload.assert_called_once_with(limit=24)

    def test_protection_summary_keeps_live_actions_locked(self):
        row = {
            "source": "manual_watchlist",
            "status": "EMERGENCY",
            "risk_level": "EMERGENCY",
            "alert_level": "emergency",
            "raw": {
                "reason": "Liquidity down 60% from peak",
                "auto_sell": True,
                "token_standard": "TOKEN_2022",
                "token_extensions": ["metadataPointer"],
                "token_mechanics_risk": "PASS",
                "token_mechanics_reasons": ["No dangerous token mechanics detected"],
                "prepared_exit": {
                    "quote_status": "amount_missing",
                    "suggested_sell_pct": 100,
                    "urgency": "emergency",
                    "token_amount_reason": "token_amount_missing",
                    "reasons": ["Emergency protection state"],
                },
                "token_amount": 12.5,
                "token_amount_raw": 12500000,
                "token_amount_source": "operator_manual",
                "token_decimals": 6,
                "wallet_balance_status": "manual_amount",
                "test_amount": True,
                "amount_safety_note": "Test amount only. Does not represent a wallet balance or owned position.",
            },
        }

        summary = desktop_api.build_protection_summary(row)

        self.assertEqual(summary["state"], "EMERGENCY")
        self.assertEqual(summary["quote_status"], "amount_missing")
        self.assertEqual(summary["suggested_sell_pct"], 100)
        self.assertFalse(summary["live_action_allowed"])
        self.assertFalse(summary["auto_sell_enabled"])
        self.assertIn("Emergency protection state", summary["reasons"])
        self.assertEqual(summary["token_standard"], "TOKEN_2022")
        self.assertEqual(summary["token_amount"], 12.5)
        self.assertEqual(summary["token_amount_raw"], 12500000)
        self.assertEqual(summary["token_amount_source"], "operator_manual")
        self.assertEqual(summary["token_decimals"], 6)
        self.assertEqual(summary["wallet_balance_status"], "manual_amount")
        self.assertTrue(summary["test_amount"])
        self.assertIn("Test amount only", summary["amount_safety_note"])

    def test_signal_summary_matches_catalyst_and_social_mint(self):
        mint = "Mint111"
        summary = desktop_api.build_signal_summary(
            mint,
            {"signals": [{"account": "kol", "text": f"watch {mint}", "mints": [mint], "keywords": ["watch"], "weight": 8}]},
            {"cards": [{"mint": mint, "outcome": {"summary": "observed candidate"}, "sources": ["rug_watchdog"], "snapshot_count": 3}]},
        )

        self.assertEqual(summary["social_count"], 1)
        self.assertEqual(summary["catalyst_count"], 1)
        self.assertEqual(summary["social"][0]["account"], "kol")
        self.assertEqual(summary["catalysts"][0]["summary"], "observed candidate")

    def test_social_endpoint_supports_legacy_signals_key(self):
        status, _, body = desktop_api.json_response(
            desktop_api.summarize_social_payload({"signals": [{"account": "kol"}]})
        )
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["count"], 1)

    def test_social_freshness_payload_flags_stale_sources_and_collectors(self):
        now = desktop_api.time.time()
        payload = desktop_api.build_social_freshness_payload(
            social_state={"events": [{"account": "kol", "updated_at": now - 7200}]},
            catalyst_state={"cards": [{"mint": "Mint111", "updated_at": now - 60}]},
            collector_state={
                "collectors": [
                    {
                        "collector": "reddit",
                        "enabled": True,
                        "last_success_at": now - 2400,
                        "fresh_seconds": 1800,
                        "event_count": 12,
                        "last_error": "rate limited",
                    }
                ]
            },
        )

        rows = {row["source"]: row for row in payload["rows"]}
        self.assertEqual(payload["overall"], "WARN")
        self.assertEqual(rows["manual_social_import"]["status"], "STALE")
        self.assertEqual(rows["catalyst_cards"]["status"], "FRESH")
        self.assertEqual(rows["reddit"]["status"], "STALE")
        self.assertEqual(rows["reddit"]["event_count"], 12)
        self.assertIn("rate limited", rows["reddit"]["detail"])

    def test_social_freshness_reads_runtime_social_collectors_dict(self):
        now = desktop_api.time.time()
        payload = desktop_api.build_social_freshness_payload(
            social_state={"events": []},
            catalyst_state={"cards": []},
            collector_state={
                "social_collectors": {
                    "reddit": {
                        "collector": "reddit",
                        "label": "Reddit Collector",
                        "enabled": True,
                        "last_success_at": now - 60,
                        "fresh_seconds": 1800,
                        "event_count": 4,
                    }
                }
            },
        )

        rows = {row["source"]: row for row in payload["rows"]}
        self.assertEqual(rows["reddit"]["label"], "Reddit Collector")
        self.assertEqual(rows["reddit"]["status"], "FRESH")
        self.assertEqual(rows["reddit"]["event_count"], 4)

    def test_social_freshness_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_social_freshness_payload", return_value={
            "generated_at": 123,
            "mode": "SOCIAL_FRESHNESS_READ_ONLY",
            "live_execution_locked": True,
            "overall": "WARN",
            "counts": {"NOT_CONFIGURED": 1},
            "rows": [{"source": "automated_collectors", "status": "NOT_CONFIGURED"}],
        }):
            status, content_type, body = desktop_api.route_request("GET", "/api/social/freshness")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["rows"][0]["status"], "NOT_CONFIGURED")

    def test_social_payload_declares_json_source_and_decision_evidence_boundary(self):
        payload = desktop_api.summarize_social_payload({"events": [{"mint": "Mint111", "text": "watch"}]})

        self.assertEqual(payload["source"], "social_state_json")
        self.assertEqual(payload["source_detail"], "data/social_state.json")
        self.assertEqual(payload["source_contract"]["social"], "social_state_json")
        self.assertEqual(payload["source_contract"]["catalysts"], "catalyst_cards_json")
        self.assertEqual(payload["source_contract"]["decision_social_evidence"], "sqlite_decision_records_embedded_evidence")
        self.assertEqual(payload["count"], 1)

    def test_social_import_route_saves_local_research_only(self):
        mint = "Mint111111111111111111111111111111111"
        body = json.dumps({
            "mint": mint,
            "url": "https://x.com/trader/status/123",
            "text": f"KOL is watching {mint}",
            "account": "trader",
            "keywords": "kol, watch",
        }).encode("utf-8")

        def fake_update(_path, _default, updater):
            return updater({"events": []})

        with mock.patch.object(desktop_api, "locked_update_json", side_effect=fake_update):
            status, content_type, response_body = desktop_api.route_request("POST", "/api/social/import", body)

        payload = json.loads(response_body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["trade_triggered"])
        self.assertEqual(payload["item"]["account"], "trader")
        self.assertEqual(payload["item"]["mints"], [mint])
        self.assertEqual(payload["item"]["keywords"], ["kol", "watch"])

    def test_wallets_payload_merges_labels_and_performance(self):
        payload = desktop_api.build_wallets_payload({
            "tracked_wallets": [{
                "trackedWalletAddress": "Wallet111",
                "name": "alpha",
                "emoji": "*",
                "groups": ["Main"],
            }],
            "wallet_performance": {
                "wallets": {
                    "Wallet111": {
                        "signals": 5,
                        "paper_entries": 2,
                        "wins": 1,
                        "losses": 1,
                        "total_pnl": 12,
                        "avg_pnl": 6,
                        "best_pnl": 20,
                        "worst_pnl": -8,
                        "score": 72,
                        "last_seen": desktop_api.time.time(),
                    }
                },
                "signals": [{
                    "mint": "Mint111",
                    "wallets": ["Wallet111"],
                    "signal_type": "cluster",
                    "score": 72,
                    "should_trade": True,
                }],
            },
        })

        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["tracked_count"], 1)
        self.assertEqual(payload["wallets"][0]["name"], "alpha")
        self.assertEqual(payload["wallets"][0]["label"], "GOOD_PERFORMER")
        self.assertEqual(payload["wallets"][0]["win_rate_pct"], 50.0)
        self.assertEqual(payload["recent_signals"][0]["mint"], "Mint111")
        self.assertEqual(payload["source"], "wallet_performance_json")
        self.assertEqual(payload["source_contract"]["performance"], "wallet_performance_json")
        self.assertEqual(payload["source_contract"]["tracked_wallets"], "tracked_wallets_json")
        self.assertEqual(payload["source_contract"]["behavior"], "wallet_behavior_json")
        self.assertEqual(payload["source_contract"]["events"], "sqlite_events_raw_activity")

    def test_wallet_detail_payload_includes_signals_and_paper_trades(self):
        payload = desktop_api.build_wallet_detail_payload("Wallet111", {
            "tracked_wallets": [{
                "trackedWalletAddress": "Wallet111",
                "name": "alpha",
                "emoji": "*",
                "groups": ["Main"],
            }],
            "wallet_performance": {
                "wallets": {
                    "Wallet111": {
                        "signals": 5,
                        "paper_entries": 2,
                        "wins": 1,
                        "losses": 1,
                        "total_pnl": 12,
                        "avg_pnl": 6,
                        "best_pnl": 20,
                        "worst_pnl": -8,
                        "score": 72,
                        "last_seen": desktop_api.time.time(),
                    }
                },
                "signals": [
                    {"mint": "Mint111", "wallets": ["Wallet111"], "signal_type": "cluster", "score": 72, "should_trade": True},
                    {"mint": "Mint222", "wallets": ["OtherWallet"], "signal_type": "cluster", "score": 10, "should_trade": False},
                ],
            },
            "paper": {
                "open_trades": [{"token_mint": "Mint111", "wallets": ["Wallet111"], "status": "open", "total_pnl_pct": 4}],
                "closed_trades": [{"token_mint": "Mint333", "wallets": ["OtherWallet"], "status": "closed"}],
                "failed_trades": [{"token_mint": "Mint444", "wallets": ["Wallet111"], "failure_reason": "risk"}],
            },
            "wallet_behavior": {
                "wallets": {
                    "Wallet111": {
                        "labels": ["early-buyer"],
                        "rolling": {"7d": {"entries": 2, "avg_pnl": 4}},
                        "postmortem": {
                            "closed_trades": 1,
                            "failed_trades": 1,
                            "best_trade": {"mint": "Mint111", "pnl_pct": 4},
                            "worst_trade": {"mint": "Mint444", "pnl_pct": 0},
                            "exit_reasons": {"target_profit": 1},
                            "failure_reasons": {"risk": 1},
                        },
                    }
                }
            },
        })

        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["wallet"]["wallet"], "Wallet111")
        self.assertEqual(payload["wallet"]["name"], "alpha")
        self.assertEqual(len(payload["recent_signals"]), 1)
        self.assertEqual(payload["recent_signals"][0]["mint"], "Mint111")
        self.assertEqual(len(payload["paper_trades"]), 2)
        self.assertEqual(payload["paper_trades"][0]["mint"], "Mint111")
        self.assertEqual(payload["behavior"]["labels"], ["early-buyer"])
        self.assertEqual(payload["postmortem"]["closed_trades"], 1)
        self.assertEqual(payload["postmortem"]["failure_reasons"]["risk"], 1)
        self.assertEqual(payload["source_contract"]["performance"], "wallet_performance_json")
        self.assertEqual(payload["source_contract"]["paper_trades"], "sqlite_trades_or_json_fallback")

    def test_wallet_context_for_mint_summarizes_signal_wallet_confidence(self):
        context = desktop_api.build_wallet_context_for_mint("Mint111", {
            "tracked_wallets": [{"trackedWalletAddress": "Wallet111", "name": "alpha"}],
            "wallet_performance": {
                "wallets": {
                    "Wallet111": {"signals": 5, "paper_entries": 3, "wins": 2, "losses": 1, "avg_pnl": 12, "score": 82},
                    "Wallet222": {"signals": 9, "paper_entries": 1, "wins": 0, "losses": 1, "avg_pnl": -20, "score": 28},
                },
                "signals": [
                    {"mint": "Mint111", "wallets": ["Wallet111", "Wallet222"], "score": 75, "should_trade": True},
                    {"mint": "OtherMint", "wallets": ["Wallet333"], "score": 20},
                ],
            },
            "wallet_behavior": {
                "wallets": {
                    "Wallet111": {
                        "labels": ["paper-profitable", "early-buyer"],
                        "rolling": {"7d": {"entries": 3, "avg_pnl": 12, "win_rate": 0.6667}},
                        "postmortem": {
                            "closed_trades": 3,
                            "failed_trades": 0,
                            "best_trade": {"mint": "MintWin", "pnl_pct": 60},
                            "worst_trade": {"mint": "MintLoss", "pnl_pct": -8},
                        },
                    },
                    "Wallet222": {
                        "labels": ["follower-trap"],
                        "postmortem": {"closed_trades": 1, "failed_trades": 1},
                    },
                }
            },
            "paper": {
                "open_trades": [{"mint": "Mint111", "wallets": ["Wallet111"]}],
                "closed_trades": [],
                "failed_trades": [],
            },
        })

        self.assertEqual(context["wallet_count"], 2)
        self.assertEqual(context["proven_wallets"], 1)
        self.assertEqual(context["trap_wallets"], 1)
        self.assertEqual(context["avg_score"], 55)
        self.assertEqual(context["wallets"][0]["wallet"], "Wallet111")
        self.assertEqual(context["wallets"][0]["name"], "alpha")
        self.assertIn("paper-profitable", context["wallets"][0]["labels"])
        self.assertEqual(context["wallets"][0]["postmortem"]["closed_trades"], 3)
        self.assertEqual(context["matched_signals"], 1)

    def test_wallets_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallets_payload", return_value={"wallets": [], "live_execution_locked": True}):
            status, content_type, body = desktop_api.route_request("GET", "/api/wallets")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["live_execution_locked"])

    def test_wallet_detail_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_detail_payload", return_value={
            "read_only": True,
            "live_execution_locked": True,
            "wallet": {"wallet": "Wallet111"},
            "recent_signals": [],
            "paper_trades": [],
        }):
            status, content_type, body = desktop_api.route_request("GET", "/api/wallets/Wallet111")
        payload = json.loads(body)

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["wallet"]["wallet"], "Wallet111")

    def test_operator_config_payload_is_read_only_and_summarized(self):
        with mock.patch.object(desktop_api, "check_helius_provider_health", return_value={
            "state": "missing_key",
            "active_provider": None,
            "providers": [],
            "live_execution_unlocked": False,
        }):
            payload = desktop_api.build_operator_config_payload({
                "settings": {
                    "mode": "CONFIRMATION",
                    "confirmation_score_threshold": 68,
                    "paper_base_position_usd": 30,
                    "confirmation": {"min_liquidity": 10000},
                },
                "runtime": {"bot": {"updated_at": desktop_api.time.time(), "state": "alive"}},
            })

        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertTrue(payload["safety"]["metadata_mutations_enabled"])
        self.assertFalse(payload["safety"]["execution_mutations_enabled"])
        self.assertEqual(payload["strategy"]["mode"], "CONFIRMATION")
        self.assertEqual(payload["selected_token_refresh_ms"], 1000)
        self.assertIn("providers", payload)
        self.assertFalse(payload["providers"]["live_execution_unlocked"])

    def test_operator_config_reports_degraded_provider_failover(self):
        provider_status = {
            "state": "degraded",
            "active_provider": "helius_mainnet",
            "providers": [
                {"name": "helius_gatekeeper", "ok": False, "http_status": 429, "detail": "max usage reached"},
                {"name": "helius_mainnet", "ok": True, "http_status": 200, "detail": "ok"},
            ],
        }
        with mock.patch.object(desktop_api, "check_helius_provider_health", return_value=provider_status):
            payload = desktop_api.build_operator_config_payload({})

        self.assertEqual(payload["providers"]["state"], "degraded")
        self.assertEqual(payload["providers"]["active_provider"], "helius_mainnet")
        self.assertEqual(payload["providers"]["providers"][0]["detail"], "max usage reached")

    def test_desktop_api_loads_local_env_for_provider_health(self):
        with mock.patch.object(desktop_api, "load_env") as mocked_load_env:
            desktop_api.load_desktop_env()

        mocked_load_env.assert_called_once()

    def test_log_tail_redacts_api_keys(self):
        with mock.patch.object(desktop_api, "LOG_FILES", {"test": desktop_api.ROOT / "logs" / "fake.log"}):
            with mock.patch.object(desktop_api, "tail_file", return_value=["url api-key=[REDACTED]"]):
                payload = desktop_api.build_logs_payload(limit=1)

        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["logs"]["test"]["lines"], ["url api-key=[REDACTED]"])

    def test_operator_and_logs_routes_are_read_only(self):
        with mock.patch.object(desktop_api, "build_operator_config_payload", return_value={"read_only": True, "live_execution_locked": True}):
            status, _, body = desktop_api.route_request("GET", "/api/operator-config")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(json.loads(body)["read_only"])

        with mock.patch.object(desktop_api, "build_logs_payload", return_value={"read_only": True, "live_execution_locked": True, "logs": {}}):
            status, _, body = desktop_api.route_request("GET", "/api/logs")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(json.loads(body)["live_execution_locked"])


if __name__ == "__main__":
    unittest.main()
