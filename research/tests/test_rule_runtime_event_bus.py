from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.rule_runtime_event_bus import RuleRuntimeEventBus
from research.mtp_research.validation.rule_runtime_v1 import (
    RuleRuntimeConfig,
    RuleRuntimeEngine,
    initialize_rule_runtime,
    rule_runtime_status,
)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _event(mint: str, ts: float, fdv: float, *, event_id: str | None = None, event_type: str = "fdv_path_update") -> dict:
    return {
        "event_id": event_id or f"{mint}-{ts}-{fdv}",
        "mint": mint,
        "observed_at": ts,
        "monotonic_observed_at": ts + 0.001,
        "source_adapter": "mock_live_bus",
        "source_event_type": event_type,
        "fdv_proxy": fdv,
        "fdv_usd": fdv,
        "fdv_sol": fdv / 80.0,
        "fdv_units": "usd",
        "sol_usd": 80.0,
        "fdv_source": "bonding_curve_account_state",
        "fdv_source_confidence": "high",
        "account_data_hash": f"hash-{mint}-{ts}-{fdv}",
        "reserve_state_fingerprint": f"reserve-{mint}-{ts}-{fdv}",
        "event_count": 10,
        "buy_count": 5,
        "sell_count": 1,
        "active_wallet_count": 4,
        "holder_count_at_10k_proxy": 5,
        "path_evidence_count": 1,
        "raw_crossed_10k": fdv >= 10_000,
        "raw_crossed_15k": fdv >= 15_000,
        "raw_crossed_20k": fdv >= 20_000,
        "raw_crossed_50k": fdv >= 50_000,
        "raw_crossed_100k": fdv >= 100_000,
        "raw_crossed_500k": fdv >= 500_000,
        "raw_crossed_1m": fdv >= 1_000_000,
        "candidate_state_before": None,
        "candidate_state_after": None,
        "source_provenance": "mock_live_bus",
        "raw_snapshot_ref": None,
    }


def test_event_bus_enqueue_dequeue_dedupe_and_backpressure() -> None:
    bus = RuleRuntimeEventBus(max_queue_size=2)

    assert bus.emit(_event("mint-a", 1, 1_000, event_id="e1")) is True
    assert bus.emit(_event("mint-a", 1, 1_000, event_id="e1")) is False
    assert bus.emit(_event("mint-b", 2, 2_000, event_id="e2")) is True
    assert bus.emit(_event("mint-c", 3, 3_000, event_id="e3"), block=False) is False

    metrics = bus.metrics()
    assert metrics["emitted"] == 2
    assert metrics["deduped"] == 1
    assert metrics["dropped_backpressure"] == 1
    assert metrics["queue_depth"] == 2
    assert [event["event_id"] for event in bus.drain(max_events=10)] == ["e1", "e2"]
    assert bus.metrics()["queue_depth"] == 0


def test_direct_runtime_consumes_live_bus_and_emits_paper_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    bus = RuleRuntimeEventBus()
    for event in [
        _event("mint-a", 100, 10_500),
        _event("mint-a", 125, 11_000),
        _event("mint-a", 150, 20_500),
        _event("mint-a", 175, 22_000),
    ]:
        bus.emit(event)

    result = engine.consume_event_bus(bus, max_events=10)

    trades = _rows(config.paper_trades_path)
    status = rule_runtime_status(config)
    assert result["processed"] == 4
    assert result["paper_buys_created"] == 1
    assert status["runtime_mode"] == "live_bus"
    assert status["live_bus_events"] == 4
    assert status["file_adapter_events"] == 0
    assert len([row for row in trades if row["side"] == "paper_buy"]) == 1
    latency = _rows(config.latency_events_path)[-1]
    assert latency["runtime_mode"] == "live_bus"
    assert latency["event_to_rule_ms"] is not None
    assert latency["bus_to_runtime_ms"] is not None


def test_direct_runtime_rejects_raw_20k_spike_and_same_timestamp_jump(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    bus = RuleRuntimeEventBus()
    for event in [
        _event("raw-only", 100, 22_000),
        _event("spike", 100, 2_400),
        _event("spike", 105, 36_000),
        _event("spike", 110, 2_500),
        _event("jump", 200, 11_000),
        _event("jump", 220, 12_000),
        _event("jump", 240, 1_100_000),
    ]:
        bus.emit(event)

    engine.consume_event_bus(bus, max_events=20)

    status = rule_runtime_status(config)
    decisions = _rows(config.paper_decisions_path)
    assert status["paper_buys"] == 0
    assert status["rejected_spike_candidates"] == 1
    assert status["rejected_same_timestamp_jumps"] == 1
    assert any(row.get("rejection_reason") == "insufficient_path_evidence_for_confirmed_20k" for row in decisions)


def test_direct_runtime_emits_paper_sell_from_live_bus_exit_path(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    bus = RuleRuntimeEventBus()
    for event in [
        _event("mint-a", 100, 10_500),
        _event("mint-a", 130, 11_500),
        _event("mint-a", 160, 20_500),
        _event("mint-a", 180, 21_000),
        _event("mint-a", 240, 70_000),
        _event("mint-a", 300, 48_000),
        _event("mint-a", 901, 45_000),
    ]:
        bus.emit(event)

    result = engine.consume_event_bus(bus, max_events=20)

    trades = _rows(config.paper_trades_path)
    assert result["paper_buys_created"] == 1
    assert result["paper_sells_created"] == 1
    assert [row["side"] for row in trades] == ["paper_buy", "paper_sell"]


def test_metadata_events_do_not_block_hot_path(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    bus = RuleRuntimeEventBus()
    bus.emit(_event("mint-a", 100, 0, event_type="metadata_update_background"))
    bus.emit(_event("mint-a", 101, 9_000))

    result = engine.consume_event_bus(bus, max_events=10)

    assert result["processed"] == 1
    assert result["background_skipped"] == 1
    assert rule_runtime_status(config)["live_bus_events"] == 1
