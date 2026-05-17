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
            desktop_api.PAPER_TRADES_FILE: {"open_trades": [], "closed_trades": [], "failed_trades": []},
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

        with mock.patch.object(desktop_api, "read_json", side_effect=fake_read_json):
            with mock.patch.object(desktop_api, "load_status", return_value={}):
                first = desktop_api.read_state_files()
                second = desktop_api.read_state_files()

        self.assertIs(first, second)
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
        self.assertEqual(payload["metrics"]["closed_trades"], 3)
        self.assertEqual(payload["metrics"]["failed_trades"], 1)
        self.assertEqual(payload["metrics"]["win_rate"], 66.67)
        self.assertEqual(payload["lane_metrics"]["main"]["closed_trades"], 2)
        self.assertEqual(payload["lane_metrics"]["main"]["realized_pnl"], 20)
        self.assertEqual(payload["lane_metrics"]["exploration"]["closed_trades"], 1)
        self.assertEqual(payload["lane_metrics"]["exploration"]["total_pnl"], 5)
        self.assertEqual(payload["exit_reasons"]["target_profit"], 2)
        self.assertEqual(payload["failure_reasons"]["quote_failed"], 1)
        self.assertEqual(payload["wallet_label_exposure"]["paper-profitable"], 1)
        self.assertEqual(payload["wallet_label_exposure"]["follower-trap"], 2)
        self.assertIn("Need at least 50 closed", payload["readiness_gaps"][0])
        self.assertIn("paper trades", payload["readiness_gaps"][0])

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
        self.assertFalse(payload["meaningful_test_ready"])
        self.assertEqual(payload["lane_metrics"]["main"]["closed_trades"], 0)
        self.assertEqual(payload["lane_metrics"]["exploration"]["closed_trades"], 50)

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

    def test_decisions_route_enriches_missing_result_from_linked_trade(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_decision(build_decision_record({
                "decision_id": "dec_trade_link",
                "timestamp": 123,
                "mint": "MintLinked",
                "type": "cluster",
                "should_trade": True,
                "score_reasons": ["cluster confirmed"],
            }))
            store.upsert_trade({
                "mint": "MintLinked",
                "status": "closed",
                "entry_time": 130,
                "close_time": 190,
                "total_pnl": 36,
                "total_pnl_pct": 144,
                "exit_reason": "take_profit",
                "signal_metadata": {"decision_id": "dec_trade_link", "trade_id": "trade_1"},
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                status, _, body = desktop_api.route_request("GET", "/api/decisions?limit=10")

        payload = json.loads(body)
        item = payload["items"][0]
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(item["decision_id"], "dec_trade_link")
        self.assertEqual(item["trade_status"], "closed")
        self.assertEqual(item["pnl"], 36)
        self.assertEqual(item["pnl_pct"], 144)
        self.assertEqual(item["result"]["exit_reason"], "take_profit")
        self.assertEqual(item["result"]["source"], "sqlite_trade_link")

    def test_alerts_route_prefers_sqlite_alerts_over_live_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.insert_alert({
                "time": 123,
                "mint": "MintSqlite",
                "type": "cluster",
                "total_score": 77,
                "edge_score": 14,
                "edge_verdict": "watch",
                "should_trade": True,
                "risk_label": "LOW",
                "wallets": ["Wallet111"],
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.object(desktop_api, "read_json", return_value={"alerts": [{"mint": "MintLive"}]}):
                    status, content_type, body = desktop_api.route_request("GET", "/api/alerts?limit=10")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["source"], "sqlite_alerts")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["mint"], "MintSqlite")
        self.assertTrue(payload["items"][0]["should_trade"])
        self.assertEqual(payload["items"][0]["wallets"], ["Wallet111"])

    def test_alerts_route_falls_back_to_live_state_when_sqlite_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            EventStore(db_path)

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.object(desktop_api, "read_json", return_value={"alerts": [{"mint": "MintLive"}]}):
                    status, _, body = desktop_api.route_request("GET", "/api/alerts?limit=10")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["source"], "live_state_alerts")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["mint"], "MintLive")

    def test_trades_route_prefers_sqlite_trades_over_json_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_trade({
                "mint": "MintOpen",
                "status": "open",
                "entry_time": 123,
                "entry_reason": "paper_opened",
                "wallets": ["Wallet111"],
            })
            store.upsert_trade({
                "mint": "MintClosed",
                "status": "closed",
                "entry_time": 100,
                "close_time": 140,
                "total_pnl": 42.5,
                "total_pnl_pct": 170,
            })
            store.upsert_trade({
                "mint": "MintFailed",
                "status": "failed",
                "entry_time": 150,
                "failure_reason": "quote_failed",
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.object(desktop_api, "read_json", return_value={
                    "open_trades": [{"mint": "JsonOpen"}],
                    "closed_trades": [],
                    "failed_trades": [],
                }):
                    status, content_type, body = desktop_api.route_request("GET", "/api/trades")

        payload = json.loads(body)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertEqual(payload["source"], "sqlite_trades")
        self.assertEqual(payload["open_trades"][0]["mint"], "MintOpen")
        self.assertEqual(payload["open_trades"][0]["wallets"], ["Wallet111"])
        self.assertEqual(payload["closed_trades"][0]["mint"], "MintClosed")
        self.assertEqual(payload["closed_trades"][0]["total_pnl"], 42.5)
        self.assertEqual(payload["failed_trades"][0]["mint"], "MintFailed")
        self.assertEqual(payload["failed_trades"][0]["failure_reason"], "quote_failed")

    def test_trades_route_falls_back_to_json_when_sqlite_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            EventStore(db_path)

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                with mock.patch.object(desktop_api, "read_json", return_value={
                    "open_trades": [{"mint": "JsonOpen"}],
                    "closed_trades": [{"mint": "JsonClosed"}],
                    "failed_trades": [{"mint": "JsonFailed"}],
                }):
                    payload = desktop_api.build_trades_payload()

        self.assertEqual(payload["source"], "paper_trades_json")
        self.assertEqual(payload["open_trades"][0]["mint"], "JsonOpen")
        self.assertEqual(payload["closed_trades"][0]["mint"], "JsonClosed")
        self.assertEqual(payload["failed_trades"][0]["mint"], "JsonFailed")

    def test_cors_only_allows_local_desktop_origins(self):
        self.assertEqual(
            desktop_api.allowed_cors_origin("http://127.0.0.1:5173"),
            "http://127.0.0.1:5173",
        )
        self.assertIsNone(desktop_api.allowed_cors_origin("http://localhost:8765"))
        self.assertEqual(
            desktop_api.allowed_cors_origin("tauri://localhost"),
            "tauri://localhost",
        )
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

    def test_wallet_quant_payload_is_review_only(self):
        payload = desktop_api.build_wallet_quant_payload({
            "tracked_wallets": [{"trackedWalletAddress": "TrustedA"}],
            "paper_watch_wallets": {"wallets": ["WalletA", "WalletB"]},
            "wallet_performance": {
                "wallets": {
                    "WalletA": {"paper_entries": 8, "wins": 6, "losses": 2, "total_pnl": 42.0},
                    "WalletB": {"paper_entries": 7, "wins": 1, "losses": 6, "total_pnl": -28.0},
                }
            },
            "wallet_behavior": {
                "wallets": {
                    "WalletA": {"rolling": {"30d": {"expectancy": 5.25}}},
                    "WalletB": {"rolling": {"30d": {"expectancy": -4.0}}},
                }
            },
        })

        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["mode"], "WALLET_QUANT_REVIEW_ONLY")
        self.assertEqual(payload["counts"]["trusted"], 1)
        self.assertEqual(payload["counts"]["paper_watch"], 2)
        self.assertEqual(payload["recommendation_counts"]["PROMOTION_REVIEW"], 1)
        self.assertEqual(payload["recommendation_counts"]["DEMOTION_REVIEW"], 1)

    def test_wallet_quant_route_honors_limit(self):
        with mock.patch.object(desktop_api, "build_wallet_quant_payload", return_value={"wallets": [], "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-quant?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_replay_review_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_replay_review_payload", return_value={"mode": "WALLET_REPLAY_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-replay-review?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_cycle_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_cycle_payload", return_value={"mode": "WALLET_CYCLE_REPORT_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-cycle")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_wallet_candidate_audit_payload_surfaces_stage4_review_queue(self):
        payload = desktop_api.build_wallet_candidate_audit_payload({
            "wallet_candidate_audit": {
                "mode": "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY",
                "counts": {
                    "candidates": 2,
                    "promotion_review": 0,
                    "demotion_review": 1,
                    "risk_review_required": 1,
                },
                "candidates": [
                    {
                        "wallet": "WalletDemote",
                        "recommendation_action": "DEMOTION_REVIEW",
                        "audit_status": "HUMAN_REVIEW_REQUIRED",
                        "review_resolved": False,
                        "evidence": {
                            "source": "wallet_stage4_review",
                            "known_outcomes": 20,
                            "rug_participation": 20,
                            "round_trip_lifecycles": 1,
                        },
                    },
                    {
                        "wallet": "WalletRisk",
                        "recommendation_action": "RISK_REVIEW_REQUIRED",
                        "audit_status": "RISK_REVIEW_REQUIRED",
                        "review_resolved": False,
                        "evidence": {"source": "wallet_stage4_review"},
                    },
                ],
                "resolved_candidates": [],
            }
        }, limit=1)

        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["summary"]["demotion_review"], 1)
        self.assertEqual(payload["summary"]["risk_review_required"], 1)
        self.assertEqual(payload["stage4_summary"]["stage4_sourced_candidates"], 2)
        self.assertEqual(payload["candidates"][0]["wallet"], "WalletDemote")

    def test_wallet_candidate_audit_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_audit_payload", return_value={"mode": "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-audit?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_decision_prep_payload_is_draft_only(self):
        payload = desktop_api.build_wallet_candidate_decision_prep_payload({
            "wallet_candidate_audit": {
                "counts": {"candidates": 1},
                "candidates": [
                    {
                        "wallet": "WalletDemote",
                        "recommendation_action": "DEMOTION_REVIEW",
                        "audit_status": "HUMAN_REVIEW_REQUIRED",
                        "review_resolved": False,
                        "evidence": {
                            "source": "wallet_stage4_review",
                            "known_outcomes": 20,
                            "rug_participation": 20,
                        },
                    }
                ],
            }
        }, limit=10)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["proposed_decisions"], 1)
        self.assertFalse(payload["proposed_decisions"][0]["approved"])
        self.assertEqual(payload["proposed_decisions"][0]["decision"], "approve_demotion")

    def test_wallet_candidate_decision_prep_route_accepts_wallet_filter(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_decision_prep_payload", return_value={"mode": "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-decision-prep?limit=12&wallet=WalletA&wallets=WalletB,WalletC")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12, selected_wallets=["WalletA", "WalletB", "WalletC"])

    def test_wallet_candidate_review_summary_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_review_summary_payload({
            "wallet_candidate_audit": {
                "counts": {"candidates": 1},
                "candidates": [
                    {
                        "wallet": "WalletRisk",
                        "recommendation_action": "RISK_REVIEW_REQUIRED",
                        "audit_status": "RISK_REVIEW_REQUIRED",
                        "evidence": {"source": "wallet_stage4_review"},
                    }
                ],
                "resolved_candidates": [],
            }
        }, limit=10)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["risk_review_required"], 1)
        self.assertEqual(payload["buckets"]["risk_review_required"][0]["wallet"], "WalletRisk")

    def test_wallet_candidate_review_summary_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_review_summary_payload", return_value={"mode": "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-review-summary?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_collection_plan_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_collection_plan_payload({
            "wallet_candidate_audit": {
                "candidates": [
                    {
                        "wallet": "WalletThin",
                        "recommendation_action": "HOLD_MORE_DATA",
                        "audit_status": "INSUFFICIENT_EVIDENCE",
                        "evidence": {
                            "scorecard_next_action": "collect_outcomes_and_market_context",
                            "known_outcomes": 1,
                            "round_trip_lifecycles": 1,
                        },
                    }
                ],
                "resolved_candidates": [],
            }
        }, limit=10)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["collect_outcomes_and_market_context"], 1)
        self.assertEqual(payload["targets"][0]["wallet"], "WalletThin")

    def test_wallet_candidate_collection_plan_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_collection_plan_payload", return_value={"mode": "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-collection-plan?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_collection_batch_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_collection_batch_payload({
            "wallet_candidate_collection_batch": {
                "mode": "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY",
                "summary": {"steps_passed": 16, "steps_failed": 0},
                "steps": [{"name": "candidate_collection_plan", "status": "passed"}],
            }
        }, limit=1)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["steps_passed"], 16)
        self.assertEqual(payload["count"], 1)

    def test_wallet_candidate_collection_batch_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_collection_batch_payload", return_value={"mode": "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-collection-batch?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_blockers_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_blockers_payload({
            "wallet_candidate_audit": {"counts": {"candidates": 1}},
            "wallet_candidate_collection_plan": {
                "summary": {"total_targets": 1, "manual_risk_review": 1},
                "targets": [{"wallet": "RiskWallet", "next_collection_step": "MANUAL_RISK_REVIEW", "missing": {"known_outcomes": 20}}],
            },
            "wallet_candidate_collection_batch": {"summary": {"steps_passed": 16, "steps_failed": 0}},
        }, limit=1)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["primary_blocker_counts"]["manual_risk_review"], 1)
        self.assertEqual(payload["count"], 1)

    def test_wallet_candidate_blockers_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_blockers_payload", return_value={"mode": "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-blockers?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_context_recovery_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_context_recovery_payload({
            "wallet_candidate_collection_plan": {
                "targets": [
                    {"wallet": "MarketWallet", "next_collection_step": "COLLECT_OUTCOMES_AND_MARKET_CONTEXT", "missing": {"known_outcomes": 20, "market_context": True}}
                ]
            },
            "wallet_candidate_blocker_reducer": {"primary_blocker_counts": {"missing_outcomes_and_market_context": 1}},
        }, limit=1)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["total_recovery_targets"], 1)
        self.assertEqual(payload["count"], 1)

    def test_wallet_candidate_context_recovery_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_context_recovery_payload", return_value={"mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-context-recovery?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_context_recovery_runner_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_context_recovery_runner_payload({
            "wallet_candidate_context_recovery": {"targets": [{"wallet": "WalletA", "missing_known_outcomes": 20}]},
            "wallet_evidence_enriched_rows": [
                {"wallet": "WalletA", "token_mint": "MintA", "enrichment_status": "MISSING_MARKET_CONTEXT"}
            ],
            "wallet_missing_market_context": {"targets": [{"token_mint": "MintA", "wallets": ["WalletA"], "evidence_rows": 1}]},
        }, limit=1)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["targets_processed"], 1)
        self.assertEqual(payload["count"], 1)

    def test_wallet_candidate_context_recovery_runner_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_context_recovery_runner_payload", return_value={"mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-context-recovery-runner?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_context_recovery_closeout_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_context_recovery_closeout_payload({
            "wallet_candidate_context_recovery_runner": {
                "wallets": [
                    {
                        "wallet": "WalletA",
                        "remaining_blockers": ["missing_outcome_labels"],
                        "existing_evidence": {"total_rows": 2, "linked_transactions": ["SigA"]},
                    }
                ]
            }
        }, limit=1)

        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY")
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["wallets_reviewed"], 1)
        self.assertEqual(payload["count"], 1)

    def test_wallet_candidate_context_recovery_closeout_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_context_recovery_closeout_payload", return_value={"mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-context-recovery-closeout?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_quality_payload_is_review_only(self):
        payload = desktop_api.build_wallet_candidate_quality_payload({
            "candidate_wallets": {
                "candidates": [
                    {"wallet": "WalletA", "score": 60, "winner_mints": 2, "early_buy_events": 8, "last_seen": desktop_api.time.time()},
                    {"wallet": "WalletBad", "score": 99, "winner_mints": 9, "last_seen": desktop_api.time.time()},
                ],
            },
            "paper_watch_wallets": {"wallets": []},
            "bad_wallets": ["WalletBad"],
            "wallet_behavior": {"wallets": {}},
            "wallet_candidate_quality_report": {},
        })

        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertEqual(payload["mode"], "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY")
        self.assertEqual(payload["summary"]["active_candidates"], 1)
        self.assertEqual(payload["summary"]["blocked_candidates"], 1)
        self.assertEqual(payload["ranked_candidates"][0]["wallet"], "WalletA")

    def test_wallet_candidate_quality_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_quality_payload", return_value={"mode": "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-quality?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_quality_review_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_quality_review_payload", return_value={"mode": "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-quality-review?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_evidence_plan_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_evidence_plan_payload", return_value={"mode": "WALLET_CANDIDATE_EVIDENCE_PLAN_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-evidence-plan?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_candidate_backfill_targets_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_candidate_backfill_targets_payload", return_value={"mode": "WALLET_CANDIDATE_BACKFILL_TARGETS_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-candidate-backfill-targets?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_history_backfill_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_history_backfill_payload", return_value={"mode": "WALLET_HISTORY_BACKFILL_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-history-backfill?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_evidence_enrichment_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_evidence_enrichment_payload", return_value={"mode": "WALLET_EVIDENCE_ENRICHMENT_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-evidence-enrichment?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_wallet_missing_market_context_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_missing_market_context_payload", return_value={"mode": "WALLET_MISSING_MARKET_CONTEXT_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-missing-market-context?limit=12")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with(limit=12)

    def test_evidence_layer_completion_payload_is_review_only(self):
        payload = desktop_api.build_evidence_layer_completion_payload({
            "wallet_evidence_readiness": {
                "live_execution_locked": True,
                "summary": {
                    "stage3_evidence_contract_completion_pct": 100,
                    "wallet_score_readiness_pct": 0,
                    "evidence_duplicate_count": 0,
                    "wallets_blocked": 0,
                    "evidence_rows": 100,
                    "rows_with_known_outcome": 20,
                    "score_ready_market_context_records": 0,
                },
                "evidence_gaps": ["low_known_outcome_coverage", "missing_market_context"],
            },
            "wallet_evidence_scorecard": {
                "live_execution_locked": True,
                "summary": {
                    "stage3_engine_completion_pct": 100,
                    "trusted_promotions_allowed": 0,
                },
            },
            "wallet_candidate_context_recovery_closeout": {
                "live_execution_locked": True,
                "summary": {
                    "still_blocked_wallets": 36,
                    "needs_outcome_labels": 36,
                    "needs_market_context": 32,
                    "needs_transaction_linkage": 0,
                },
                "next_action_counts": {
                    "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 32,
                    "BACKFILL_OUTCOME_LABELS": 4,
                },
            },
        })

        self.assertEqual(payload["mode"], "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["evidence_layer_completion_pct"], 100)
        self.assertEqual(payload["summary"]["wallet_score_readiness_pct"], 0)

    def test_evidence_layer_completion_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_evidence_layer_completion_payload", return_value={"mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/evidence-layer-completion")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_replayable_token_timelines_payload_is_review_only(self):
        payload = desktop_api.build_replayable_token_timelines_payload({
            "evidence_layer_completion": {
                "live_execution_locked": True,
                "summary": {
                    "evidence_layer_completion_pct": 100,
                    "wallet_score_readiness_pct": 0,
                },
            },
            "wallet_candidate_context_recovery_closeout": {
                "live_execution_locked": True,
                "summary": {
                    "still_blocked_wallets": 36,
                    "needs_market_context": 32,
                    "needs_outcome_labels": 36,
                    "needs_transaction_linkage": 0,
                },
                "next_action_counts": {
                    "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 32,
                    "BACKFILL_OUTCOME_LABELS": 4,
                },
            },
            "wallet_missing_market_context": {
                "live_execution_locked": True,
                "summary": {"target_mints": 1, "missing_market_context_rows": 1},
                "targets": [{"token_mint": "MintA", "evidence_rows": 1, "unknown_outcome_rows": 1}],
            },
            "onchain_market_context": {
                "live_execution_locked": True,
                "summary": {"records_scanned": 1, "score_ready_candidate_records": 0},
            },
            "onchain_supply_evidence": {
                "live_execution_locked": True,
                "summary": {"records_scanned": 1, "supply_recovered_records": 0},
            },
            "replay_realism_readiness": {
                "live_execution_locked": True,
                "summary": {"stage6_realism_contract_completion_pct": 100},
            },
            "stage8_validation_readiness": {
                "live_execution_locked": True,
                "summary": {"stage8_validation_contract_completion_pct": 100, "proof_readiness_pct": 0},
            },
        })

        self.assertEqual(payload["mode"], "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["replayable_token_timelines_completion_pct"], 100)

    def test_replayable_token_timelines_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_replayable_token_timelines_payload", return_value={"mode": "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/replayable-token-timelines")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_similar_rug_patterns_payload_is_review_only(self):
        payload = desktop_api.build_similar_rug_patterns_payload({
            "wallet_evidence_enrichment": {
                "live_execution_locked": True,
                "summary": {
                    "total_evidence_rows": 3,
                    "rows_with_known_outcome": 1,
                    "rug_rows": 1,
                    "missing_outcome_label_rows": 2,
                },
                "evidence_records": [
                    {
                        "wallet": "WalletRug",
                        "token_mint": "MintRug",
                        "later_token_outcome": {"outcome_type": "rug", "rug": True},
                    },
                    {
                        "wallet": "WalletUnknown",
                        "token_mint": "MintUnknown",
                        "later_token_outcome": {"outcome_type": "unknown", "rug": False},
                    },
                ],
            },
            "wallet_outcome_ledger": {
                "live_execution_locked": True,
                "wallets": {
                    "WalletRug": {"known_outcomes": 1, "rug_participation": 1, "rug_participation_rate": 1.0},
                },
            },
            "wallet_replay_scorecard": {
                "live_execution_locked": True,
                "wallets": {
                    "WalletRug": {"windows": {"15m": {"known": 1, "rug": 1}}},
                },
            },
            "replayable_token_timelines": {
                "live_execution_locked": True,
                "summary": {
                    "replayable_token_timelines_completion_pct": 100,
                    "timeline_data_readiness_pct": 0,
                    "missing_market_context_rows": 2,
                },
            },
        })

        self.assertEqual(payload["mode"], "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["similar_rug_pattern_completion_pct"], 100)
        self.assertEqual(payload["summary"]["unknown_rows_excluded_from_rug_labels"], 2)

    def test_similar_rug_patterns_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_similar_rug_patterns_payload", return_value={"mode": "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/similar-rug-patterns")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_alerting_dashboard_layer_payload_is_review_only(self):
        payload = desktop_api.build_alerting_dashboard_layer_payload({
            "evidence_layer_completion": {
                "mode": "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"evidence_layer_completion_pct": 100, "wallet_score_readiness_pct": 0},
            },
            "replayable_token_timelines": {
                "mode": "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"replayable_token_timelines_completion_pct": 100, "timeline_data_readiness_pct": 0},
            },
            "similar_rug_patterns": {
                "mode": "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"similar_rug_pattern_completion_pct": 100, "rug_pattern_data_readiness_pct": 0},
            },
        })

        self.assertEqual(payload["mode"], "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["alerting_dashboard_layer_completion_pct"], 100)
        self.assertEqual(payload["summary"]["research_data_readiness_pct"], 0)

    def test_alerting_dashboard_layer_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_alerting_dashboard_layer_payload", return_value={"mode": "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/alerting-dashboard-layer")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_validation_proof_layer_payload_is_review_only(self):
        payload = desktop_api.build_validation_proof_layer_payload({
            "alerting_dashboard_layer": {
                "mode": "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY",
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"alerting_dashboard_layer_completion_pct": 100, "research_data_readiness_pct": 0},
                "blocked_data_issues": ["score_ready_market_context_absent"],
            },
            "stage8_validation_readiness": {
                "mode": "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY",
                "live_execution_locked": True,
                "summary": {"stage8_validation_contract_completion_pct": 100, "proof_readiness_pct": 0},
            },
        })

        self.assertEqual(payload["mode"], "VALIDATION_PROOF_LAYER_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["validation_proof_layer_completion_pct"], 100)
        self.assertEqual(payload["summary"]["proof_readiness_pct"], 0)

    def test_validation_proof_layer_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_validation_proof_layer_payload", return_value={"mode": "VALIDATION_PROOF_LAYER_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/validation-proof-layer")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_productization_operator_workflow_payload_is_review_only(self):
        payload = desktop_api.build_productization_operator_workflow_payload({
            "productization_operator_workflow": {
                "mode": "PRODUCTIZATION_OPERATOR_WORKFLOW_REVIEW_ONLY",
                "summary": {"productization_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "PRODUCTIZATION_OPERATOR_WORKFLOW_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["productization_completion_pct"], 100)

    def test_productization_operator_workflow_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_productization_operator_workflow_payload", return_value={"mode": "PRODUCTIZATION_OPERATOR_WORKFLOW_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/productization-operator-workflow")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_signal_context_layer_payload_is_review_only(self):
        payload = desktop_api.build_signal_context_layer_payload({
            "signal_context_layer": {
                "mode": "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY",
                "summary": {"stage2_signal_context_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertEqual(payload["summary"]["stage2_signal_context_completion_pct"], 100)

    def test_signal_context_layer_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_signal_context_layer_payload", return_value={"mode": "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/signal-context-layer")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_live_signal_foundation_payload_is_review_only(self):
        payload = desktop_api.build_live_signal_foundation_payload({
            "live_signal_foundation": {
                "mode": "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY",
                "summary": {"stage1_live_signal_foundation_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertEqual(payload["summary"]["stage1_live_signal_foundation_completion_pct"], 100)

    def test_live_signal_foundation_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_live_signal_foundation_payload", return_value={"mode": "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/live-signal-foundation")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_wallet_promotion_demotion_system_payload_is_review_only(self):
        payload = desktop_api.build_wallet_promotion_demotion_system_payload({
            "wallet_promotion_demotion_system": {
                "mode": "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY",
                "summary": {"stage4_promotion_demotion_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertEqual(payload["summary"]["stage4_promotion_demotion_completion_pct"], 100)

    def test_wallet_promotion_demotion_system_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_promotion_demotion_system_payload", return_value={"mode": "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-promotion-demotion-system")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_wallet_ecosystem_intelligence_payload_is_review_only(self):
        payload = desktop_api.build_wallet_ecosystem_intelligence_payload({
            "wallet_ecosystem_intelligence": {
                "mode": "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY",
                "summary": {"stage5_wallet_ecosystem_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertEqual(payload["summary"]["stage5_wallet_ecosystem_completion_pct"], 100)

    def test_wallet_ecosystem_intelligence_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_wallet_ecosystem_intelligence_payload", return_value={"mode": "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/wallet-ecosystem-intelligence")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_market_regime_detection_payload_is_review_only(self):
        payload = desktop_api.build_market_regime_detection_payload({
            "market_regime_detection": {
                "mode": "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY",
                "summary": {"stage7_regime_detection_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertFalse(payload["regime_score_driving_allowed"])
        self.assertEqual(payload["summary"]["stage7_regime_detection_completion_pct"], 100)

    def test_market_regime_detection_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_market_regime_detection_payload", return_value={"mode": "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/market-regime-detection")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_behavioral_intelligence_layer_payload_is_review_only(self):
        payload = desktop_api.build_behavioral_intelligence_layer_payload({
            "behavioral_intelligence_layer": {
                "mode": "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY",
                "summary": {"stage9_behavioral_intelligence_completion_pct": 100},
            }
        })

        self.assertEqual(payload["mode"], "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertFalse(payload["behavioral_score_driving_allowed"])
        self.assertEqual(payload["summary"]["stage9_behavioral_intelligence_completion_pct"], 100)

    def test_behavioral_intelligence_layer_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_behavioral_intelligence_layer_payload", return_value={"mode": "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/behavioral-intelligence-layer")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_behavioral_trust_validation_payload_is_review_only(self):
        payload = desktop_api.build_behavioral_trust_validation_payload({
            "behavioral_trust_validation": {
                "mode": "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY",
                "summary": {"behavioral_validation_completion_pct": 100, "behavioral_trust_justified": False},
            }
        })

        self.assertEqual(payload["mode"], "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertFalse(payload["behavioral_trust_changes_allowed"])
        self.assertFalse(payload["summary"]["behavioral_trust_justified"])

    def test_behavioral_trust_validation_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_behavioral_trust_validation_payload", return_value={"mode": "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/behavioral-trust-validation")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

    def test_proof_readiness_blocker_reduction_payload_is_review_only(self):
        payload = desktop_api.build_proof_readiness_blocker_reduction_payload({
            "proof_readiness_blocker_reduction": {
                "mode": "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY",
                "summary": {"blocker_reduction_completion_pct": 100, "behavioral_trust_justified": False},
            }
        })

        self.assertEqual(payload["mode"], "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["live_execution_locked"])
        self.assertFalse(payload["wallet_list_apply_allowed"])
        self.assertFalse(payload["wallet_list_mutated"])
        self.assertFalse(payload["auto_trust_mutation_allowed"])
        self.assertFalse(payload["behavioral_trust_changes_allowed"])
        self.assertFalse(payload["summary"]["behavioral_trust_justified"])

    def test_proof_readiness_blocker_reduction_route_is_read_only(self):
        with mock.patch.object(desktop_api, "build_proof_readiness_blocker_reduction_payload", return_value={"mode": "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY", "live_execution_locked": True}) as build_payload:
            status, content_type, body = desktop_api.route_request("GET", "/api/proof-readiness-blocker-reduction")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/json", content_type)
        self.assertTrue(json.loads(body)["live_execution_locked"])
        build_payload.assert_called_once_with()

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

    def test_wallet_detail_payload_uses_canonical_trades_when_state_has_no_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_trade({
                "mint": "MintSqlite",
                "status": "closed",
                "entry_time": 100,
                "close_time": 150,
                "wallets": ["Wallet111"],
                "total_pnl": 18,
                "total_pnl_pct": 45,
                "exit_reason": "take_profit",
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                payload = desktop_api.build_wallet_detail_payload("Wallet111", {
                    "tracked_wallets": [{"trackedWalletAddress": "Wallet111", "name": "alpha"}],
                    "wallet_performance": {"wallets": {"Wallet111": {"score": 72}}, "signals": []},
                    "wallet_behavior": {"wallets": {}},
                })

        self.assertEqual(payload["trade_source"], "sqlite_trades")
        self.assertEqual(len(payload["paper_trades"]), 1)
        self.assertEqual(payload["paper_trades"][0]["mint"], "MintSqlite")
        self.assertEqual(payload["paper_trades"][0]["pnl"], 18)
        self.assertEqual(payload["paper_trades"][0]["reason"], "take_profit")

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

    def test_wallet_context_for_mint_uses_canonical_trades_when_state_has_no_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = desktop_api.Path(tmp) / "memetrader.db"
            store = EventStore(db_path)
            store.upsert_trade({
                "mint": "MintSqlite",
                "status": "open",
                "entry_time": 100,
                "wallets": ["Wallet111"],
            })

            with mock.patch.object(desktop_api, "DB_FILE", db_path):
                context = desktop_api.build_wallet_context_for_mint("MintSqlite", {
                    "tracked_wallets": [{"trackedWalletAddress": "Wallet111", "name": "alpha"}],
                    "wallet_performance": {"wallets": {"Wallet111": {"score": 72}}, "signals": []},
                    "wallet_behavior": {"wallets": {}},
                })

        self.assertEqual(context["trade_source"], "sqlite_trades")
        self.assertEqual(context["wallet_count"], 1)
        self.assertEqual(context["wallets"][0]["wallet"], "Wallet111")

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
