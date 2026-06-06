from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.rule_runtime_v1 import (
    RuleRuntimeConfig,
    RuleRuntimeEngine,
    RuleRuntimePriorityScheduler,
    initialize_rule_runtime,
    rule_runtime_status,
)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _event(mint: str, ts: float, fdv: float, *, events: int = 10, buys: int = 5, wallets: int = 4) -> dict:
    return {
        "mint": mint,
        "timestamp": ts,
        "event_observed_at": ts + 0.25,
        "fdv_proxy": fdv,
        "event_count": events,
        "buy_count": buys,
        "active_wallet_count": wallets,
        "data_source": "mock_helius_rpc",
    }


def test_initializes_manifest_ledgers_and_monitor_under_rule_runtime_namespace(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)

    result = initialize_rule_runtime(config, reset=True)

    manifest = json.loads(config.runtime_manifest_json_path.read_text(encoding="utf-8"))
    assert result["runtime_label"] == "rule_runtime_v1"
    assert manifest["frozen_buy_rule_id"] == "BROAD_10K_WATCH_20K_BUY"
    assert manifest["frozen_exit_rule_id"] == "EXIT_NO_RECLAIM"
    assert manifest["paper_trading_enabled"] is True
    assert manifest["live_trading_enabled"] is False
    assert manifest["private_keys_allowed"] is False
    assert manifest["raw_milestones_allowed_for_entry"] is False
    assert manifest["single_row_spikes_allowed"] is False
    assert manifest["same_timestamp_major_jump_allowed_for_entry"] is False
    assert manifest["metadata_hot_path_allowed"] is False
    assert manifest["getTransaction_hot_path_required"] is False
    assert config.paper_trades_path.exists()
    assert config.paper_decisions_path.exists()
    assert config.latency_events_path.exists()
    assert 'content="10"' in config.monitor_html_path.read_text(encoding="utf-8")


def test_confirmed_10k_promotes_to_watch_and_logs_latency(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("mint-a", 100, 10_500))
    result = engine.process_path_event(_event("mint-a", 130, 11_200))

    assert result["state"] == "confirmed_10k_watch"
    assert result["tier"] == 2
    assert result["confirmed_crossed_10k"] is True
    status = rule_runtime_status(config)
    assert status["confirmed_10k_watches"] == 1
    assert status["confirmed_20k_entry_candidates"] == 0
    assert _rows(config.latency_events_path)[-1]["confirmed_10k_at"] == 130


def test_confirmed_20k_creates_one_paper_buy_with_efficiency_features(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path, starting_wallet_usd=300, position_fraction=0.05)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("mint-a", 100, 10_200, events=4, buys=2, wallets=2))
    engine.process_path_event(_event("mint-a", 130, 11_000, events=5, buys=3, wallets=3))
    engine.process_path_event(_event("mint-a", 170, 20_500, events=8, buys=4, wallets=4))
    first = engine.process_path_event(_event("mint-a", 200, 22_000, events=10, buys=5, wallets=5))
    duplicate = engine.process_path_event(_event("mint-a", 215, 23_000, events=11, buys=6, wallets=6))

    trades = _rows(config.paper_trades_path)
    decisions = _rows(config.paper_decisions_path)
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    assert first["paper_buy_created"] is True
    assert duplicate["paper_buy_created"] is False
    assert len([row for row in trades if row["side"] == "paper_buy"]) == 1
    buy = trades[0]
    assert buy["paper_event_id"].startswith("paper_buy_mint-a_")
    assert buy["paper_buy_fdv"] == 22_000
    assert buy["confirmed_10k_time"] == 130
    assert buy["confirmed_20k_time"] == 200
    assert buy["fdv_per_event_at_20k"] == 2200
    assert buy["fdv_per_buy_at_20k"] == 4400
    assert buy["fdv_per_active_wallet_at_20k"] == 4400
    assert buy["allocation_usd"] == 15
    assert buy["no_real_trade"] is True
    assert state["cash_usd"] == 285
    assert decisions[-1]["decision"] == "paper_buy"


def test_rejects_single_row_spike_and_same_timestamp_jump_for_entry(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("spike", 100, 2_400))
    spike_result = engine.process_path_event(_event("spike", 110, 36_000))
    engine.process_path_event(_event("spike", 120, 2_500))

    engine.process_path_event(_event("jump", 200, 11_000))
    engine.process_path_event(_event("jump", 220, 12_000))
    jump_result = engine.process_path_event(_event("jump", 240, 1_100_000))
    engine.process_path_event(_event("jump", 240, 1_120_000))

    assert spike_result["single_row_spike_flag"] is True
    assert jump_result["same_timestamp_major_jump_flag"] is True
    assert _rows(config.paper_trades_path) == []
    status = rule_runtime_status(config)
    assert status["rejected_spike_candidates"] == 1
    assert status["rejected_same_timestamp_jumps"] == 1


def test_rejects_invalid_milestone_ordering_and_fdv_anomalies(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    invalid = engine.process_path_event(_event("bad-order", 100, 55_000))
    anomaly = engine.process_path_event(_event("bad-fdv", 105, -1))

    assert invalid["state"] == "rejected_same_timestamp_jump"
    assert invalid["same_timestamp_major_jump_flag"] is True
    assert anomaly["state"] == "rejected_fdv_anomaly"
    assert anomaly["fdv_anomaly_flag"] is True
    status = rule_runtime_status(config)
    assert status["rejected_fdv_anomalies"] == 1


def test_exit_no_reclaim_creates_paper_sell_after_30pct_drawdown_timer(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for event in [
        _event("mint-a", 100, 10_500),
        _event("mint-a", 130, 11_500),
        _event("mint-a", 160, 20_500),
        _event("mint-a", 180, 21_000),
        _event("mint-a", 240, 70_000),
        _event("mint-a", 300, 48_000),
    ]:
        engine.process_path_event(event)
    result = engine.process_path_event(_event("mint-a", 901, 45_000))

    trades = _rows(config.paper_trades_path)
    sell = [row for row in trades if row["side"] == "paper_sell"][0]
    assert result["paper_sell_created"] is True
    assert sell["exit_rule_id"] == "EXIT_NO_RECLAIM"
    assert sell["exit_reason"] == "no_reclaim_after_10m_30pct_drawdown"
    assert sell["paper_sell_fdv"] == 45_000
    assert sell["local_high_fdv"] == 70_000
    assert sell["reclaimed_prior_high"] is False
    assert sell["no_real_trade"] is True


def test_priority_scheduler_orders_hot_work_before_background_metadata() -> None:
    scheduler = RuleRuntimePriorityScheduler()
    scheduler.add_job("metadata_background", {"mint": "m5"})
    scheduler.add_job("light_watch", {"mint": "m4"})
    scheduler.add_job("first_fdv_path", {"mint": "m3"})
    scheduler.add_job("confirmed_10k_watch", {"mint": "m2"})
    scheduler.add_job("paper_position_open", {"mint": "m1"})

    assert [scheduler.pop_next_job()["mint"] for _ in range(5)] == ["m1", "m2", "m3", "m4", "m5"]
    assert scheduler.queue_sizes() == {
        "paper_position_open": 0,
        "confirmed_10k_watch": 0,
        "first_fdv_path": 0,
        "light_watch": 0,
        "metadata_background": 0,
    }


def test_runtime_contains_no_live_execution_logic() -> None:
    text = Path("research/mtp_research/validation/rule_runtime_v1.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "sendtransaction",
        "swaptransaction",
        "jupiter",
        "route_order",
        "secretkey",
        "sign_transaction",
        "build_transaction",
    ]
    assert not any(term in text for term in forbidden)
