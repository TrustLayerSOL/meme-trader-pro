from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.rule_runtime_v1 import (
    RuleRuntimeConfig,
    RuleRuntimeEngine,
    RuleRuntimeLiveAdapter,
    RuleRuntimeLiveAdapterConfig,
    RuleRuntimePriorityScheduler,
    archive_runtime_queue_candidates,
    first_fdv_queue_triage_audit,
    initialize_rule_runtime,
    load_historical_rule_config,
    normalize_live_path_row_for_rule_runtime,
    run_rule_runtime_live_adapter_once,
    run_first_fdv_queue_triage_smoke,
    run_rule_runtime_smoke,
    rule_runtime_status,
)
from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleV2Config, OfficialLifecycleStateMachine


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _event(mint: str, ts: float, fdv: float, *, events: int = 10, buys: int = 5, wallets: int = 4, **extra: object) -> dict:
    row = {
        "mint": mint,
        "timestamp": ts,
        "event_observed_at": ts + 0.25,
        "fdv_proxy": fdv,
        "event_count": events,
        "buy_count": buys,
        "active_wallet_count": wallets,
        "data_source": "mock_helius_rpc",
    }
    row.update(extra)
    return row


def test_load_historical_rule_config_prefers_refined_config_and_writes_audit(tmp_path: Path) -> None:
    refined = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v2" / "refined_historical_rule_paper_shadow_config.json"
    repaired_summary = tmp_path / "data" / "backtests" / "diagnostics" / "reports" / "historical_rule_refinement_repaired" / "historical_rule_refinement_repaired_summary.json"
    refined.parent.mkdir(parents=True)
    repaired_summary.parent.mkdir(parents=True)
    refined.write_text(
        json.dumps(
            {
                "selected_buy_rule_id": "RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER",
                "selected_exit_rule_id": "EXIT_NO_RECLAIM_AFTER_30PCT_10M",
                "base_gate": "confirmed clean 10k watch -> confirmed clean 20k candidate",
                "positive_confirms": ["high_fdv_efficiency_bucket"],
                "risk_rejects": ["single-row spikes, same-timestamp major jumps, FDV anomalies, invalid milestone ordering"],
                "required_live_fields": ["confirmed_crossed_10k", "confirmed_crossed_20k"],
                "confirmed_milestones_only": True,
                "raw_milestones_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    repaired_summary.write_text(
        json.dumps(
            {
                "classification": "refined_rule_promising_needs_live_actionability",
                "clean_confirmed_20k_count": 776,
                "selected_repaired_rule": {
                    "buy_rule_id": "RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER",
                    "exit_rule_id": "EXIT_NO_RECLAIM_AFTER_30PCT_10M",
                },
            }
        ),
        encoding="utf-8",
    )

    config = RuleRuntimeConfig(data_root=tmp_path)
    loaded = load_historical_rule_config(config)

    assert loaded["loaded"] is True
    assert loaded["selected_buy_rule_id"] == "RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER"
    assert loaded["selected_exit_rule_id"] == "EXIT_NO_RECLAIM_AFTER_30PCT_10M"
    assert loaded["repaired_context"]["clean_confirmed_20k_count"] == 776
    assert config.historical_rule_config_audit_json_path.exists()
    assert "Historical Rule Config Load Audit" in config.historical_rule_config_audit_md_path.read_text(encoding="utf-8")


def test_initializes_manifest_ledgers_and_monitor_under_rule_runtime_namespace(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)

    result = initialize_rule_runtime(config, reset=True)

    manifest = json.loads(config.runtime_manifest_json_path.read_text(encoding="utf-8"))
    assert result["runtime_label"] == "rule_runtime_v1"
    assert manifest["frozen_buy_rule_id"] == "RULE_D_20K_EFFICIENCY_CREATOR_HOLDER_RISK_FILTER"
    assert manifest["frozen_exit_rule_id"] == "EXIT_NO_RECLAIM_AFTER_30PCT_10M"
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
    assert config.paper_rule_variant_decisions_path.exists()
    assert config.paper_rule_variant_exits_path.exists()
    assert config.latency_events_path.exists()
    assert 'content="10"' in config.monitor_html_path.read_text(encoding="utf-8")


def test_confirmed_10k_promotes_to_watch_and_logs_latency(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("mint-a", 100, 10_500))
    result = engine.process_path_event(_event("mint-a", 130, 11_200))

    assert result["state"] == "confirmed_10k_watch"
    assert result["tier"] == 3
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


def test_confirmed_20k_creates_three_variant_decisions_with_available_risk_fields(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path, starting_wallet_usd=300, position_fraction=0.05)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("mint-a", 100, 10_200, events=4, buys=2, wallets=2))
    engine.process_path_event(_event("mint-a", 130, 11_000, events=5, buys=3, wallets=3))
    engine.process_path_event(_event("mint-a", 170, 20_500, events=8, buys=4, wallets=4))
    engine.process_path_event(
        _event(
            "mint-a",
            200,
            22_000,
            events=10,
            buys=5,
            wallets=5,
            creator_prior_migration_count=1,
            repeated_buyer_count=3,
            holder_count_at_10k_proxy=24,
            holder_growth_to_20k_proxy=9,
            topicality_bucket="news",
        )
    )

    decisions = _rows(config.paper_rule_variant_decisions_path)
    by_variant = {row["variant_id"]: row for row in decisions}
    assert set(by_variant) == {
        "FDV_BASELINE_20K",
        "FDV_CREATOR_HOLDER_AVAILABLE_FILTER",
        "FDV_FULL_RISK_FILTER_WHEN_AVAILABLE",
    }
    assert by_variant["FDV_BASELINE_20K"]["variant_status"] == "paper_buy"
    assert by_variant["FDV_BASELINE_20K"]["paper_buy_emitted"] is True
    assert by_variant["FDV_BASELINE_20K"]["fdv_efficiency_threshold_status"] == "fdv_threshold_unfrozen"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["variant_status"] == "paper_buy"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["risk_filter_status"] == "risk_filter_available_pass"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["creator_prior_migration_count"] == 1
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["repeated_buyer_count"] == 3
    assert by_variant["FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"]["variant_status"] == "not_evaluable"
    assert by_variant["FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"]["risk_filter_status"] == "missing"
    assert "early_buyer_with_prior_100k_count" in by_variant["FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"]["missing_required_fields"]
    assert len([row for row in _rows(config.paper_trades_path) if row["side"] == "paper_buy"]) == 1


def test_missing_risk_fields_do_not_block_fdv_baseline_variant(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for event in [
        _event("mint-a", 100, 10_200),
        _event("mint-a", 130, 11_000),
        _event("mint-a", 170, 20_500),
        _event("mint-a", 200, 22_000),
    ]:
        engine.process_path_event(event)

    by_variant = {row["variant_id"]: row for row in _rows(config.paper_rule_variant_decisions_path)}
    assert by_variant["FDV_BASELINE_20K"]["variant_status"] == "paper_buy"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["variant_status"] == "not_evaluable"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["risk_filter_status"] == "missing"
    assert "creator_prior_migration_count" in by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["missing_required_fields"]
    assert by_variant["FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"]["variant_status"] == "not_evaluable"


def test_variant_entry_rejections_capture_spike_jump_and_fdv_anomaly_flags(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for event in [
        _event("spike", 100, 2_400),
        _event("spike", 110, 36_000),
        _event("spike", 120, 2_500),
        _event("jump", 200, 11_000),
        _event("jump", 220, 12_000),
        _event("jump", 240, 1_100_000),
        _event("anomaly", 300, -1),
    ]:
        engine.process_path_event(event)

    decisions = _rows(config.paper_rule_variant_decisions_path)
    reasons = {row["mint"]: row["rejection_reason"] for row in decisions if row["variant_id"] == "FDV_BASELINE_20K"}
    assert reasons["spike"] == "single_row_spike"
    assert reasons["jump"] == "same_timestamp_major_jump"
    assert reasons["anomaly"] == "fdv_anomaly"
    assert not any(row["variant_status"] == "paper_buy" for row in decisions)


def test_exit_tracking_is_recorded_per_paper_variant(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for event in [
        _event("mint-a", 100, 10_500),
        _event("mint-a", 130, 11_500),
        _event(
            "mint-a",
            160,
            20_500,
            creator_prior_migration_count=1,
            repeated_buyer_count=2,
            holder_count_at_10k_proxy=18,
            holder_growth_to_20k_proxy=5,
        ),
        _event(
            "mint-a",
            180,
            21_000,
            creator_prior_migration_count=1,
            repeated_buyer_count=2,
            holder_count_at_10k_proxy=18,
            holder_growth_to_20k_proxy=5,
        ),
        _event("mint-a", 240, 70_000),
        _event("mint-a", 300, 48_000),
        _event("mint-a", 901, 45_000),
    ]:
        engine.process_path_event(event)

    exits = _rows(config.paper_rule_variant_exits_path)
    by_variant = {row["variant_id"]: row for row in exits}
    assert set(by_variant) == {"FDV_BASELINE_20K", "FDV_CREATOR_HOLDER_AVAILABLE_FILTER"}
    assert by_variant["FDV_BASELINE_20K"]["exit_rule_id"] == "EXIT_NO_RECLAIM_AFTER_30PCT_10M"
    assert by_variant["FDV_BASELINE_20K"]["paper_sell_emitted"] is True
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["paper_sell_fdv"] == 45_000


def test_status_and_monitor_include_variant_counts(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for event in [
        _event("mint-a", 100, 10_200),
        _event("mint-a", 130, 11_000),
        _event("mint-a", 170, 20_500),
        _event("mint-a", 200, 22_000),
    ]:
        engine.process_path_event(event)

    status = rule_runtime_status(config)
    html = config.monitor_html_path.read_text(encoding="utf-8")
    assert status["variants"]["FDV_BASELINE_20K"]["paper_buys"] == 1
    assert status["variants"]["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["not_evaluable"] == 1
    assert status["variants"]["FDV_FULL_RISK_FILTER_WHEN_AVAILABLE"]["not_evaluable"] == 1
    assert "Rule Runtime v1 Variants" in html
    assert "FDV_BASELINE_20K" in html
    assert "FDV_FULL_RISK_FILTER_WHEN_AVAILABLE" in html


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
    assert sell["exit_rule_id"] == "EXIT_NO_RECLAIM_AFTER_30PCT_10M"
    assert sell["exit_reason"] == "no_reclaim_after_10m_30pct_drawdown"
    assert sell["paper_sell_fdv"] == 45_000
    assert sell["local_high_fdv"] == 70_000
    assert sell["reclaimed_prior_high"] is False
    assert sell["no_real_trade"] is True


def test_priority_scheduler_orders_hot_work_before_background_metadata() -> None:
    scheduler = RuleRuntimePriorityScheduler()
    scheduler.add_job("metadata_background", {"mint": "m5"})
    scheduler.add_job("light_watch", {"mint": "m4"})
    scheduler.add_job("fresh_birth_first_path", {"mint": "m6"})
    scheduler.add_job("first_fdv_path", {"mint": "m3"})
    scheduler.add_job("near_threshold_watch", {"mint": "m25"})
    scheduler.add_job("confirmed_10k_watch", {"mint": "m2"})
    scheduler.add_job("paper_position_open", {"mint": "m1"})

    assert [scheduler.pop_next_job()["mint"] for _ in range(7)] == ["m1", "m2", "m25", "m3", "m6", "m4", "m5"]
    assert scheduler.queue_sizes() == {
        "paper_position_open": 0,
        "confirmed_10k_watch": 0,
        "near_threshold_watch": 0,
        "first_fdv_path": 0,
        "fresh_birth_first_path": 0,
        "light_watch": 0,
        "metadata_background": 0,
    }


def test_runtime_promotes_near_threshold_and_reports_first_fdv_queue_metrics(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("low", 100, 1_200))
    engine.process_path_event(_event("near", 110, 5_100))
    engine.process_path_event(_event("ten", 120, 10_500))
    engine.process_path_event(_event("ten", 150, 11_000))

    status = rule_runtime_status(config)
    queue = status["first_fdv_queue"]
    assert status["queue_sizes"]["near_threshold_watch"] == 1
    assert status["queue_sizes"]["confirmed_10k_watch"] == 1
    assert queue["scheduler_mode"] == "priority_single_worker"
    assert queue["queue_depth_by_tier"]["tier_1_fdv_path_seen"] == 1
    assert queue["queue_depth_by_tier"]["tier_2_near_threshold_watch"] == 1
    assert queue["queue_depth_by_tier"]["tier_3_confirmed_10k_watch"] == 1
    assert queue["promoted_to_fdv_path"] == 3
    assert queue["promoted_to_near_threshold"] == 2
    assert queue["promoted_to_confirmed_10k"] == 1
    assert queue["first_path_success_rate"] == 1.0
    assert "fdv_efficiency_threshold_unfrozen" in status["warnings"]


def test_runtime_aging_downgrades_and_archives_stale_first_path_candidates(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("quiet", 100, 1_100, events=0, buys=0, wallets=0))
    downgraded = archive_runtime_queue_candidates(config, now=170)
    archived = archive_runtime_queue_candidates(config, now=230)

    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    status = rule_runtime_status(config)
    assert downgraded["downgrade_count"] == 1
    assert archived["archived_no_activity"] == 1
    assert state["candidates"]["quiet"]["state"] == "archived_no_activity"
    assert status["first_fdv_queue"]["downgrade_count"] == 1
    assert status["first_fdv_queue"]["archived_no_activity"] == 1
    assert status["queue_sizes"]["first_fdv_path"] == 0


def test_runtime_archives_birth_without_fdv_path_after_timeout(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    state["candidates"]["birth-only"] = {
        "mint": "birth-only",
        "state": "birth_seen",
        "tier": 0,
        "first_seen_at": 100.0,
        "path_rows": [],
        "raw_milestones": {},
        "confirmed_milestones": {},
        "milestone_first_times": {},
        "confirmed_milestone_times": {},
    }
    config.runtime_state_path.write_text(json.dumps(state), encoding="utf-8")

    archived = archive_runtime_queue_candidates(config, now=230)

    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    assert archived["archived_no_fdv_path_timeout"] == 1
    assert state["candidates"]["birth-only"]["state"] == "archived_no_fdv_path_timeout"


def test_first_fdv_queue_triage_audit_writes_reports(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    engine.process_path_event(_event("near", 100, 5_500))

    audit = first_fdv_queue_triage_audit(config)

    assert audit["scheduler_mode"] == "priority_single_worker"
    assert audit["parallel_workers_added"] is False
    assert audit["queue_entries_created_from"] == "candidate_state"
    assert config.first_fdv_queue_triage_audit_json_path.exists()
    assert "First FDV Queue Triage Audit" in config.first_fdv_queue_triage_audit_md_path.read_text(encoding="utf-8")


def test_first_fdv_queue_triage_smoke_writes_summary(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path, repo_root=tmp_path)
    initialize_rule_runtime(config, reset=True)

    summary = run_first_fdv_queue_triage_smoke(
        config,
        events=[
            _event("low", 100, 1_000),
            _event("near", 110, 5_500),
            _event("ten", 120, 10_500),
            _event("ten", 150, 11_000),
        ],
    )

    assert summary["runtime_mode"] == "mock_live_bus"
    assert summary["events_processed"] == 4
    assert summary["first_fdv_queue"]["queue_depth_by_tier"]["tier_2_near_threshold_watch"] == 1
    assert summary["confirmed_10k_watches"] == 1
    assert config.first_fdv_queue_triage_smoke_summary_json_path.exists()
    assert "First FDV Queue Triage Smoke Summary" in config.first_fdv_queue_triage_smoke_summary_md_path.read_text(encoding="utf-8")


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


def test_live_adapter_normalizes_followup_path_rows_without_mutating_source(tmp_path: Path) -> None:
    source = tmp_path / "collector" / "followup_paths.jsonl"
    source.parent.mkdir(parents=True)
    row = {
        "sample_label": "official_lifecycle_watch_v2",
        "mint": "mint-a",
        "timestamp": 100.0,
        "fdv_proxy": 10_500,
        "event_count": 7,
        "buy_count": 3,
        "sell_count": 1,
        "active_wallet_count": 4,
        "crossed_10k": True,
        "crossed_20k": False,
        "source_provenance": "helius_pumpfun_no_laserstream_logs",
    }
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    before = source.read_bytes()
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    adapter = RuleRuntimeLiveAdapter(RuleRuntimeLiveAdapterConfig(data_root=tmp_path, source_followup_paths_path=source))

    events = adapter.read_new_events(limit=10)

    assert source.read_bytes() == before
    assert events == [
        {
            "mint": "mint-a",
            "timestamp": 100.0,
            "source_event_type": "collector_followup_path",
            "event_observed_at": 100.0,
            "fdv_proxy": 10_500.0,
            "event_count": 7,
            "buy_count": 3,
            "sell_count": 1,
            "active_wallet_count": 4,
            "path_evidence_count": 1,
            "raw_crossed_10k": True,
            "raw_crossed_20k": False,
            "confirmed_crossed_10k": None,
            "confirmed_crossed_20k": None,
            "single_row_spike_flag": False,
            "same_timestamp_major_jump_flag": False,
            "fdv_anomaly_flag": False,
            "milestone_provenance": "helius_pumpfun_no_laserstream_logs",
            "data_source": "official_lifecycle_watch_v2",
        }
    ]
    cursor = json.loads(config.live_adapter_cursor_path.read_text(encoding="utf-8"))
    assert cursor["rows_consumed"] == 1


def test_live_adapter_once_rejects_raw_20k_only_and_logs_reason(tmp_path: Path) -> None:
    source = tmp_path / "collector" / "followup_paths.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "sample_label": "official_lifecycle_watch_v2",
                "mint": "raw-only",
                "timestamp": 100.0,
                "fdv_proxy": 22_000,
                "event_count": 1,
                "buy_count": 1,
                "active_wallet_count": 1,
                "crossed_20k": True,
                "source_provenance": "helius_pumpfun_no_laserstream_logs",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(runtime_config, reset=True)

    result = run_rule_runtime_live_adapter_once(
        runtime_config,
        adapter_config=RuleRuntimeLiveAdapterConfig(data_root=tmp_path, source_followup_paths_path=source),
        limit=10,
    )

    decisions = _rows(runtime_config.paper_decisions_path)
    assert result["events_processed"] == 1
    assert result["paper_buys"] == 0
    assert decisions[-1]["decision"] == "paper_rejected_entry"
    assert decisions[-1]["rejection_reason"] == "insufficient_path_evidence_for_confirmed_20k"
    assert decisions[-1]["no_real_trade"] is True


def test_live_adapter_once_allows_confirmed_clean_20k_baseline_mode(tmp_path: Path) -> None:
    source = tmp_path / "collector" / "followup_paths.jsonl"
    source.parent.mkdir(parents=True)
    rows = [
        _event("mint-a", 100, 10_500, events=4, buys=2, wallets=2),
        _event("mint-a", 120, 11_000, events=5, buys=3, wallets=3),
        _event("mint-a", 150, 20_500, events=8, buys=4, wallets=4),
        _event("mint-a", 170, 22_000, events=10, buys=5, wallets=5),
    ]
    source.write_text(
        "\n".join(
            json.dumps({**row, "sample_label": "official_lifecycle_watch_v2", "source_provenance": "helius_pumpfun_no_laserstream_logs"})
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(runtime_config, reset=True)

    result = run_rule_runtime_live_adapter_once(
        runtime_config,
        adapter_config=RuleRuntimeLiveAdapterConfig(data_root=tmp_path, source_followup_paths_path=source),
        limit=10,
    )

    trades = _rows(runtime_config.paper_trades_path)
    assert result["events_processed"] == 4
    assert result["confirmed_10k_watches"] == 1
    assert result["confirmed_20k_entry_candidates"] == 1
    assert result["paper_buys"] == 1
    assert trades[0]["side"] == "paper_buy"
    assert trades[0]["threshold_status"] == "baseline_label_mode"
    assert trades[0]["efficiency_threshold_warning"] == "fdv_efficiency_threshold_unfrozen_baseline_mode"
    assert trades[0]["ca"] == "mint-a"


def test_smoke_summary_writes_required_report_fields(tmp_path: Path) -> None:
    source = tmp_path / "collector" / "followup_paths.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            [
                json.dumps({"mint": "mint-a", "timestamp": 100, "fdv_proxy": 10_500, "event_count": 3, "buy_count": 2, "active_wallet_count": 2}),
                json.dumps({"mint": "mint-a", "timestamp": 120, "fdv_proxy": 11_000, "event_count": 4, "buy_count": 2, "active_wallet_count": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(runtime_config, reset=True)

    result = run_rule_runtime_smoke(
        runtime_config,
        adapter_config=RuleRuntimeLiveAdapterConfig(data_root=tmp_path, source_followup_paths_path=source),
        max_events=10,
        max_seconds=0,
        target_confirmed_10k_watches=1,
    )

    assert result["events_processed"] == 2
    assert result["confirmed_10k_watches"] == 1
    assert result["threshold_status"] == "baseline-label-mode"
    summary = json.loads(runtime_config.smoke_summary_json_path.read_text(encoding="utf-8"))
    md = runtime_config.smoke_summary_md_path.read_text(encoding="utf-8")
    status_md = runtime_config.status_md_path.read_text(encoding="utf-8")
    for key in [
        "events_processed",
        "confirmed_10k_watches",
        "confirmed_20k_candidates",
        "paper_buys",
        "paper_sells",
        "rejected_spikes",
        "rejected_same_timestamp_jumps",
        "rejected_fdv_anomalies",
        "latency_p50_p90_p99",
        "monitor_path",
        "threshold_status",
    ]:
        assert key in summary
    assert "Rule Runtime v1 Smoke Summary" in md
    assert "RULE_RUNTIME_V1_STATUS" in status_md


def test_normalize_live_path_row_rejects_missing_path_evidence() -> None:
    normalized = normalize_live_path_row_for_rule_runtime(
        {
            "mint": "missing-fdv",
            "timestamp": 1,
            "event_count": 1,
        },
        row_index=0,
    )

    assert normalized is None


def test_official_lifecycle_record_path_emits_hot_path_event_before_jsonl_write(tmp_path: Path) -> None:
    config = OfficialLifecycleV2Config(data_root=tmp_path)
    seen: list[tuple[dict, bool]] = []

    def callback(event: dict) -> None:
        seen.append((event, config.followup_paths_path.exists() and bool(config.followup_paths_path.read_text(encoding="utf-8").strip())))

    machine = OfficialLifecycleStateMachine(config, hot_path_event_callback=callback)
    machine.record_birth({"mint": "mint-a", "observed_time": 90.0})
    machine.record_path(
        {
            "mint": "mint-a",
            "timestamp": 100.0,
            "fdv_proxy": 10_500,
            "event_count": 4,
            "buy_count": 2,
            "sell_count": 1,
            "active_wallet_count": 3,
            "source_provenance": "mock_collector",
        }
    )

    assert len(seen) == 1
    event, file_had_path_rows = seen[0]
    assert file_had_path_rows is False
    assert event["mint"] == "mint-a"
    assert event["source_event_type"] == "fdv_path_update"
    assert event["fdv_proxy"] == 10_500
    assert event["raw_crossed_10k"] is True
