from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from research.mtp_research.validation.rule_runtime_v1 import (
    RuleRuntimeConfig,
    RuleRuntimeEngine,
    RuleRuntimeLiveAdapter,
    RuleRuntimeLiveAdapterConfig,
    RuleRuntimePriorityScheduler,
    archive_runtime_queue_candidates,
    birth_coverage_audit,
    first_fdv_queue_triage_audit,
    initialize_rule_runtime,
    load_historical_rule_config,
    normalize_live_path_row_for_rule_runtime,
    paper_buy_fdv_reconciliation_audit,
    run_rule_runtime_safety_patch_review,
    run_helius_transaction_subscribe_bonding_curve_probe_smoke,
    run_rule_runtime_live_adapter_once,
    run_first_fdv_queue_triage_smoke,
    run_rule_runtime_smoke,
    rule_runtime_status,
    _watch_mode_for_fdv,
)
from research.mtp_research.validation.bonding_curve_account_state import (
    BondingCurveState,
    BondingCurveAccountStateProbe,
    bonding_curve_pda,
    bonding_curve_resolution_audit,
    compute_fdv_from_bonding_curve_state,
    decode_pump_bonding_curve_account,
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
        "fdv_usd": fdv,
        "fdv_sol": fdv / 80.0,
        "fdv_units": "usd",
        "sol_usd": 80.0,
        "fdv_source": "bonding_curve_account_state",
        "fdv_source_confidence": "high",
        "account_data_hash": f"hash-{mint}-{ts}-{fdv}",
        "reserve_state_fingerprint": f"reserve-{mint}-{ts}-{fdv}",
        "event_count": events,
        "buy_count": buys,
        "active_wallet_count": wallets,
        "holder_count_at_10k_proxy": 5,
        "data_source": "mock_helius_rpc",
    }
    row.update(extra)
    return row


def _classic_curve_bytes(
    *,
    virtual_token_reserves: int = 1_000_000_000,
    virtual_sol_reserves: int = 30_000_000_000,
    real_token_reserves: int = 900_000_000,
    real_sol_reserves: int = 10_000_000_000,
    token_total_supply: int = 1_000_000_000,
    complete: bool = False,
) -> bytes:
    fields = [
        virtual_token_reserves,
        virtual_sol_reserves,
        real_token_reserves,
        real_sol_reserves,
        token_total_supply,
    ]
    return b"pumpacct" + b"".join(value.to_bytes(8, "little") for value in fields) + bytes([int(complete)])


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


def test_bonding_curve_pda_derives_known_live_curve_and_handles_missing_mint() -> None:
    assert (
        bonding_curve_pda("2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump")
        == "3eafeBvZDXbqqNdNP4NDWdWn7kD6KSn22rtNHNeTAKVK"
    )
    assert bonding_curve_pda("") is None


def test_decode_pump_bonding_curve_account_classic_layout_and_compute_fdv() -> None:
    state = decode_pump_bonding_curve_account(_classic_curve_bytes())

    assert state.decode_status == "decoded"
    assert state.layout_version == "pumpfun_classic_v1"
    assert state.virtual_token_reserves == 1_000_000_000
    assert state.virtual_sol_reserves == 30_000_000_000
    assert state.real_token_reserves == 900_000_000
    assert state.real_sol_reserves == 10_000_000_000
    assert state.token_total_supply == 1_000_000_000
    assert state.complete is False
    assert state.quote_type == "sol"

    result = compute_fdv_from_bonding_curve_state(state, sol_usd=150.0)

    assert result.probe_status == "success"
    assert result.fdv_source == "bonding_curve_account_state"
    assert result.fdv_source_confidence == "high"
    assert result.fdv_probe_method == "getAccountInfo_processed_bonding_curve"
    assert result.price_sol == 0.03
    assert result.fdv_sol == 30.0
    assert result.fdv_usd == 4_500.0


def test_compute_fdv_from_quote_reserves_when_quote_layout_is_supplied() -> None:
    state = BondingCurveState(
        decode_status="decoded",
        layout_version="pumpfun_quote_token_v1",
        virtual_token_reserves=1_000_000_000,
        virtual_quote_reserves=2_000_000_000,
        token_total_supply=1_000_000_000,
        token_decimals=6,
        quote_decimals=6,
        quote_mint="quote-mint",
        quote_type="quote_token",
    )

    result = compute_fdv_from_bonding_curve_state(state)

    assert result.probe_status == "success"
    assert result.price_quote == 2.0
    assert result.fdv_quote == 2_000.0
    assert result.fdv_usd is None
    assert result.calculation_error == "fdv_usd_unavailable"


def test_decoder_failure_does_not_fake_fdv() -> None:
    state = decode_pump_bonding_curve_account(b"too-short")
    result = compute_fdv_from_bonding_curve_state(state, sol_usd=150.0)

    assert state.decode_status == "decode_failed"
    assert state.decode_error == "account_data_too_short"
    assert result.probe_status == "failed"
    assert result.fdv_usd is None
    assert result.calculation_error == "decode_failed:account_data_too_short"


def test_account_state_probe_builds_first_fdv_event_from_mocked_get_account_info() -> None:
    payload_data = _classic_curve_bytes(virtual_sol_reserves=1_000_000, token_total_supply=1_000_000_000)

    def rpc_post(_rpc_url: str, payload: dict, _timeout: int) -> dict:
        assert payload["method"] == "getAccountInfo"
        assert payload["params"][1]["commitment"] == "processed"
        assert payload["params"][1]["encoding"] == "base64"
        import base64

        return {
            "result": {
                "value": {
                    "data": [base64.b64encode(payload_data).decode("ascii"), "base64"],
                }
            }
        }

    probe = BondingCurveAccountStateProbe(rpc_url="https://helius.invalid", rpc_post=rpc_post, sol_usd=100.0)
    result = probe.probe_birth(
        {
            "mint": "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump",
            "observed_time": 100.0,
            "bonding_curve": "3eafeBvZDXbqqNdNP4NDWdWn7kD6KSn22rtNHNeTAKVK",
        },
        now_fn=iter([100.010, 100.025, 100.030]).__next__,
    )
    event = result.to_runtime_event(timestamp=100.030)

    assert result.probe_status == "success"
    assert result.failure_reason is None
    assert result.bonding_curve == "3eafeBvZDXbqqNdNP4NDWdWn7kD6KSn22rtNHNeTAKVK"
    assert event is not None
    assert event["mint"] == "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump"
    assert event["fdv_source"] == "bonding_curve_account_state"
    assert event["fdv_source_confidence"] == "high"
    assert event["fdv_probe_method"] == "getAccountInfo_processed_bonding_curve"
    assert event["source_event_type"] == "first_fdv_account_state"
    assert event["observed_to_bonding_curve_resolved_ms"] == 10.0
    assert event["bonding_curve_resolved_to_getAccountInfo_ms"] == 15.0
    assert event["getAccountInfo_latency_ms"] == 15.0
    assert event["decode_latency_ms"] == 5.0
    assert event["observed_to_first_fdv_account_state_ms"] == 30.0


def test_transaction_delta_source_confirmation_cannot_create_single_row_paper_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    result = engine.process_path_event(
        _event(
            "delta-only",
            100,
            25_000,
            fdv_source="transaction_delta",
            fdv_source_confidence="low",
            confirmed_crossed_10k=True,
            confirmed_crossed_20k=True,
        )
    )

    assert result["paper_buy_created"] is False
    assert result["confirmed_crossed_10k"] is False
    assert result["confirmed_crossed_20k"] is False
    assert _rows(config.paper_trades_path) == []


def test_account_state_single_raw_row_does_not_buy_but_two_confirmed_rows_can_promote(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    first = engine.process_path_event(
        _event("acct", 100, 22_000, fdv_source="bonding_curve_account_state", fdv_source_confidence="high")
    )
    assert first["paper_buy_created"] is False
    assert _rows(config.paper_trades_path) == []

    for row in [
        _event("acct-ok", 100, 10_500, fdv_source="bonding_curve_account_state", fdv_source_confidence="high"),
        _event("acct-ok", 120, 11_000, fdv_source="bonding_curve_account_state", fdv_source_confidence="high"),
        _event("acct-ok", 150, 20_500, fdv_source="bonding_curve_account_state", fdv_source_confidence="high"),
        _event("acct-ok", 170, 22_000, fdv_source="bonding_curve_account_state", fdv_source_confidence="high"),
    ]:
        result = engine.process_path_event(row)

    assert result["confirmed_crossed_10k"] is True
    assert result["confirmed_crossed_20k"] is True
    assert result["paper_buy_created"] is True
    assert len([row for row in _rows(config.paper_trades_path) if row["side"] == "paper_buy"]) == 1


def test_runtime_milestones_use_explicit_usd_fdv_not_sol_proxy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(
        _event(
            "sol-only",
            100,
            250.0,
            fdv_units="sol",
            fdv_sol=250.0,
            fdv_source="bonding_curve_account_state",
            fdv_source_confidence="high",
        )
    )
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    assert state["candidates"]["sol-only"]["raw_milestones"] == {}
    assert state["candidates"]["sol-only"]["state"] == "fdv_path_seen"

    result = engine.process_path_event(
        _event(
            "usd-explicit",
            100,
            250.0,
            fdv_units="sol",
            fdv_sol=250.0,
            fdv_usd=20_250.0,
            fdv_source="bonding_curve_account_state",
            fdv_source_confidence="high",
        )
    )
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    row = state["candidates"]["usd-explicit"]["path_rows"][0]
    assert row["fdv_proxy"] == 20_250.0
    assert row["fdv_units"] == "usd"
    assert row["fdv_sol"] == 250.0
    assert row["raw_crossed_20k"] is True
    assert result["paper_buy_created"] is False


def test_first_fdv_source_metrics_and_latency_decomposition_are_reported(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(
        _event(
            "acct",
            100,
            9_000,
            fdv_source="bonding_curve_account_state",
            fdv_source_confidence="high",
            fdv_probe_method="getAccountInfo_processed_bonding_curve",
            observed_to_bonding_curve_resolved_ms=5.0,
            bonding_curve_resolved_to_getAccountInfo_ms=7.0,
            getAccountInfo_latency_ms=7.0,
            decode_latency_ms=2.0,
            observed_to_first_fdv_account_state_ms=14.0,
        )
    )
    engine.process_path_event(_event("delta", 110, 4_000, fdv_source="transaction_delta", fdv_source_confidence="low"))

    status = rule_runtime_status(config)
    sources = status["first_fdv_probe_sources"]
    latency = _rows(config.latency_events_path)[0]

    assert sources["bonding_curve_account_state_successes"] == 1
    assert sources["transaction_delta_successes"] == 1
    assert sources["getAccountInfo_p50_p90_p99"] == {"p50": 7.0, "p90": 7.0, "p99": 7.0}
    assert sources["decode_p50_p90_p99"] == {"p50": 2.0, "p90": 2.0, "p99": 2.0}
    assert sources["observed_to_first_fdv_account_state_p50_p90_p99"] == {"p50": 14.0, "p90": 14.0, "p99": 14.0}
    assert latency["first_fdv_source"] == "bonding_curve_account_state"
    assert latency["observed_to_first_fdv_account_state_ms"] == 14.0


def test_bonding_curve_resolution_audit_writes_resolution_fields(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    collector_root = tmp_path / "collector"
    collector_root.mkdir()
    (collector_root / "hydration_results.jsonl").write_text(
        json.dumps(
            {
                "signature": "sig-a",
                "hydration_status": "hydrated_create_confirmed",
                "mint": "2wubx5DrRJG1Ki25gSefzQEYtJegDUwVtMb7MR8ypump",
                "bonding_curve": "3eafeBvZDXbqqNdNP4NDWdWn7kD6KSn22rtNHNeTAKVK",
                "associated_bonding_curve": "assoc-a",
                "creator": "creator-a",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (collector_root / "births.jsonl").write_text("", encoding="utf-8")
    (collector_root / "followup_paths.jsonl").write_text(json.dumps({"mint": "m", "pool_address": "pool-a"}) + "\n", encoding="utf-8")

    audit = bonding_curve_resolution_audit(config, source_root=collector_root)

    assert audit["pumpfun_create_rows"] == 1
    assert audit["mint_available"] == 1
    assert audit["bonding_curve_available"] == 1
    assert audit["associated_bonding_curve_available"] == 1
    assert audit["creator_available"] == 1
    assert audit["bonding_curve_pda_derivable"] == 1
    assert audit["bonding_curve_pda_matches_known"] == 1
    assert audit["path_rows_with_curve_or_pool_fields"] == 1
    assert config.bonding_curve_resolution_audit_json_path.exists()
    assert "Bonding Curve Resolution Audit" in config.bonding_curve_resolution_audit_md_path.read_text(encoding="utf-8")


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


def test_partial_clean_risk_fields_do_not_block_fdv_baseline_variant(tmp_path: Path) -> None:
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
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["variant_status"] == "paper_buy"
    assert by_variant["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["risk_filter_status"] == "risk_filter_available_pass"
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
    assert status["variants"]["FDV_CREATOR_HOLDER_AVAILABLE_FILTER"]["paper_buys"] == 1
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
    archived = archive_runtime_queue_candidates(config, now=170)

    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    status = rule_runtime_status(config)
    assert archived["archived_no_activity"] == 1
    assert state["candidates"]["quiet"]["state"] == "archived_no_activity"
    assert state["candidates"]["quiet"]["archive_reason"] == "tier_1_max_age"
    assert status["first_fdv_queue"]["downgrade_count"] == 0
    assert status["first_fdv_queue"]["archived_no_activity"] == 1
    assert status["queue_sizes"]["first_fdv_path"] == 0


def test_tier_1_pressure_reports_oldest_first_retry_budget_and_rates(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    for index in range(6):
        engine.process_path_event(_event(f"tier-one-{index}", 100 + index, 1_200, events=1, buys=0, wallets=1))

    first_archive = archive_runtime_queue_candidates(
        config,
        now=121,
        first_path_fast_attempt_window_seconds=15,
        no_activity_archive_seconds=120,
        tier_1_pressure_threshold=5,
        tier_1_max_age_seconds=120,
        tier_1_retry_interval_seconds=10,
        tier_1_retry_budget=2,
    )
    second_archive = archive_runtime_queue_candidates(
        config,
        now=132,
        first_path_fast_attempt_window_seconds=15,
        no_activity_archive_seconds=120,
        tier_1_pressure_threshold=5,
        tier_1_max_age_seconds=120,
        tier_1_retry_interval_seconds=10,
        tier_1_retry_budget=2,
    )

    status = rule_runtime_status(config)
    queue = status["first_fdv_queue"]
    assert first_archive["tier_1_retry_scheduled"] == 6
    assert second_archive["archived_no_activity"] == 6
    assert queue["tier_1_depth"] == 0
    assert queue["tier_1_oldest_age_seconds"] is None
    assert queue["tier_1_age_p50_p90"] == {"p50": None, "p90": None}
    assert queue["tier_1_processed_count"] == 6
    assert queue["tier_1_archive_count"] == 6
    assert queue["tier_1_promotion_count"] == 6
    assert queue["tier_1_retry_count"] == 12
    assert queue["tier_1_retry_budget"] == 2
    assert queue["tier_1_pressure_mode"] is True
    assert queue["tier_1_next_mints_oldest_first"] == []
    assert queue["promotion_rate"] == 1.0
    assert queue["archive_rate"] == 1.0
    assert queue["first_fdv_success_rate"] == 1.0
    assert queue["first_fdv_timeout_rate"] == 0.0
    assert queue["first_fdv_median_latency_ms"] == 0.0
    assert queue["metadata_hot_path_allowed"] is False
    assert queue["metadata_enrichment_in_first_fdv"] is False


def test_tier_1_drains_flat_low_fdv_and_promotes_rising_or_floor_candidates(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("flat-low", 100, 800, events=1, buys=0, wallets=1))
    engine.process_path_event(_event("flat-low", 110, 805, events=1, buys=0, wallets=1))
    engine.process_path_event(_event("rising", 100, 800, events=1, buys=0, wallets=1))
    engine.process_path_event(_event("rising", 110, 3_600, events=1, buys=1, wallets=2))
    engine.process_path_event(_event("floor", 100, 3_200, events=1, buys=0, wallets=1))
    engine.process_path_event(_event("floor", 110, 3_150, events=1, buys=0, wallets=1))
    engine.process_path_event(_event("confirmed", 100, 10_200, events=2, buys=1, wallets=2))
    engine.process_path_event(_event("confirmed", 110, 10_400, events=2, buys=1, wallets=2))

    archived = archive_runtime_queue_candidates(config, now=131)

    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    status = rule_runtime_status(config)
    queue = status["first_fdv_queue"]

    assert archived["archived_no_activity"] == 1
    assert state["candidates"]["flat-low"]["state"] == "archived_no_activity"
    assert state["candidates"]["flat-low"]["archive_reason"] == "tier_1_low_fdv_flat_stale"
    assert state["candidates"]["flat-low"]["fdv_delta_pct"] < 0.01
    assert state["candidates"]["rising"]["state"] == "near_threshold_watch"
    assert state["candidates"]["rising"]["tier_1_exit_reason"] == "rising_fdv"
    assert state["candidates"]["floor"]["state"] == "near_threshold_watch"
    assert state["candidates"]["floor"]["tier_1_exit_reason"] == "fdv_above_promotion_floor"
    assert state["candidates"]["confirmed"]["state"] == "confirmed_10k_watch"
    assert queue["tier_1_depth"] == 0
    assert queue["tier_1_retention_reasons_oldest_first"] == []
    assert queue["tier_1_archive_count"] == 1
    assert queue["promoted_to_near_threshold"] == 3


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


def test_birth_coverage_audit_reports_birth_parse_and_rejection_counts(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    collector_root = tmp_path / "data" / "forward_observation" / "official_lifecycle_watch_v2"
    collector_root.mkdir(parents=True)
    (collector_root / "provisional_births.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"signature": "s1", "mint": "m1"}),
                json.dumps({"signature": "s2", "mint": "m2"}),
                json.dumps({"signature": "s2", "mint": "m2"}),
                json.dumps({"signature": "s3", "layout_status": "unrecognized"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (collector_root / "hydration_results.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"signature": "s1", "hydration_status": "confirmed", "candidate": {"mint": "m1"}}),
                json.dumps({"signature": "s2", "hydration_status": "failed", "missing_reason": "parser_failure"}),
                json.dumps({"signature": "s3", "hydration_status": "unrecognized_layout"}),
                json.dumps({"signature": "s4", "hydration_status": "official", "candidate": {"mint": "m4"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (collector_root / "births.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"signature": "s1", "mint": "m1"}),
                json.dumps({"signature": "s4", "mint": "m4"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (collector_root / "stale_births.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"signature": "s2", "missing_reason": "parser_failure"}),
                json.dumps({"signature": "s3", "missing_reason": "unrecognized_layout"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    audit = birth_coverage_audit(config)

    assert audit["provisional_birth_logs"] == 4
    assert audit["confirmed_create_parses"] == 2
    assert audit["fresh_accepted_births"] == 2
    assert audit["stale_quarantined_births"] == 2
    assert audit["parser_failures"] == 1
    assert audit["hydration_failures"] == 1
    assert audit["duplicate_births"] == 1
    assert audit["unrecognized_layouts"] == 1
    assert audit["accepted_birth_rate"] == 0.5
    assert audit["rejected_stale_rate"] == 0.5
    assert config.birth_coverage_audit_json_path.exists()
    assert "Birth Coverage Audit" in config.birth_coverage_audit_md_path.read_text(encoding="utf-8")


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


def test_paper_buy_fdv_reconciliation_audit_flags_duplicate_confirmations(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    mint = "G7ezsywkeKqbW57MiZNQWb6UKmYwpAoe7KfBkVEgpump"
    curve = "F4DzVCL6eC2h9i6xv8twEpmd2Bc8yh859dfHCKF2Qmmk"
    state = {
        "virtual_token_reserves": 333321305707295,
        "virtual_sol_reserves": 96573484665,
        "real_token_reserves": 53421305707295,
        "real_sol_reserves": 66573484665,
        "token_total_supply": 1000000000000000,
        "token_decimals": 6,
        "quote_decimals": 9,
        "complete": False,
    }
    path_rows = [
        {
            "mint": mint,
            "timestamp": 100.0,
            "event_id": "path_1",
            "data_source": "bonding_curve_account_state",
            "fdv_proxy": 23394.22,
            "fdv_usd": 23394.22,
            "fdv_sol": 289.74,
            "fdv_units": "usd",
            "sol_usd": 80.74,
            "bonding_curve": curve,
        },
        {
            "mint": mint,
            "timestamp": 101.0,
            "event_id": "path_2",
            "data_source": "bonding_curve_account_state",
            "fdv_proxy": 23394.22,
            "fdv_usd": 23394.22,
            "fdv_sol": 289.74,
            "fdv_units": "usd",
            "sol_usd": 80.74,
            "bonding_curve": curve,
        },
    ]
    probe_rows = [
        {
            "mint": mint,
            "event_id": "probe_1",
            "probe_status": "success",
            "fdv_proxy": 23394.22,
            "fdv_usd": 23394.22,
            "fdv_sol": 289.74,
            "fdv_units": "usd",
            "sol_usd": 80.74,
            "bonding_curve": curve,
            "source_create_signature": "sig",
            "create_slot": 123,
            "first_fdv_emitted_at": 100.0,
            "account_state": state,
        },
        {
            "mint": mint,
            "event_id": "probe_2",
            "probe_status": "success",
            "fdv_proxy": 23394.22,
            "fdv_usd": 23394.22,
            "fdv_sol": 289.74,
            "fdv_units": "usd",
            "sol_usd": 80.74,
            "bonding_curve": curve,
            "source_create_signature": "sig",
            "create_slot": 123,
            "first_fdv_emitted_at": 101.0,
            "account_state": state,
        },
    ]
    trade = {
        "side": "paper_buy",
        "mint": mint,
        "timestamp": 101.0,
        "paper_event_id": "paper_buy_g7",
        "paper_buy_fdv": 23394.22,
        "data_source": "bonding_curve_account_state",
    }
    config.path_events_path.write_text("\n".join(json.dumps(row) for row in path_rows) + "\n", encoding="utf-8")
    config.bonding_curve_account_probe_events_path.write_text("\n".join(json.dumps(row) for row in probe_rows) + "\n", encoding="utf-8")
    config.paper_trades_path.write_text(json.dumps(trade) + "\n", encoding="utf-8")

    audit = paper_buy_fdv_reconciliation_audit(config)
    row = next(row for row in audit["rows"] if row["mint"] == mint)

    assert row["duplicate_or_same_state_confirmations"] is True
    assert "confirming_rows_duplicate_same_state" in row["warnings"]
    assert "fake_volume_suspect" in row["paper_labels"]
    assert config.paper_buy_fdv_reconciliation_audit_json_path.exists()
    assert "Paper Buy FDV Reconciliation Audit" in config.paper_buy_fdv_reconciliation_audit_md_path.read_text(encoding="utf-8")
    assert config.paper_buy_fdv_reconciliation_rows_csv_path.exists()


def test_duplicate_same_state_rows_do_not_confirm_20k_or_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    common = {
        "data_source": "bonding_curve_account_state",
        "fdv_source": "bonding_curve_account_state",
        "fdv_source_confidence": "high",
        "fdv_units": "usd",
        "fdv_usd": 23_394.22,
        "fdv_sol": 292.43,
        "reserve_state_fingerprint": "same-state",
        "account_data_hash": "same-hash",
        "slot": 424711168,
    }

    first = engine.process_path_event(_event("g7-style", 100, 23_394.22, **common))
    second = engine.process_path_event(_event("g7-style", 101, 23_394.22, **common))
    status = rule_runtime_status(config)

    assert first["confirmed_crossed_20k"] is False
    assert second["confirmed_crossed_20k"] is False
    assert status["paper_buys"] == 0
    assert status["duplicate_same_state_confirmation_reject_count"] == 1
    decisions = _rows(config.paper_decisions_path)
    assert any(row["rejection_reason"] == "duplicate_same_state_confirmation" for row in decisions)


def test_distinct_account_state_rows_can_confirm_20k(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("distinct", 100, 20_500, reserve_state_fingerprint="state-a", account_data_hash="hash-a", slot=1))
    result = engine.process_path_event(_event("distinct", 110, 21_000, reserve_state_fingerprint="state-b", account_data_hash="hash-b", slot=2))
    status = rule_runtime_status(config)

    assert result["confirmed_crossed_20k"] is True
    assert status["confirmed_20k_entry_candidates"] == 1


def test_chase_guard_rejects_paper_entry_above_26k_hard_cap(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("chase", 100, 22_486.83, reserve_state_fingerprint="chase-a", account_data_hash="chase-a", slot=1))
    result = engine.process_path_event(_event("chase", 111, 27_876.00, reserve_state_fingerprint="chase-b", account_data_hash="chase-b", slot=2))
    decisions = _rows(config.paper_decisions_path)
    decision = next(row for row in decisions if row["mint"] == "chase" and row["paper_event_id"].startswith("decision_"))

    assert result["paper_buy_created"] is False
    assert decision["decision"] == "paper_rejected_entry"
    assert decision["rejection_reason"] == "chase_guard_exceeded"
    assert decision["trigger_fdv_usd"] == 22486.83
    assert decision["max_entry_above_trigger_pct"] == 0.3
    assert decision["max_allowed_paper_entry_fdv_usd"] == 26_000.0
    assert decision["chase_guard_result"] == "rejected"
    assert rule_runtime_status(config)["chase_guard_reject_count"] == 1


def test_missing_fdv_units_or_usd_rejects_paper_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("missing-units", 100, 20_100, fdv_units=None, fdv_usd=20_100, reserve_state_fingerprint="a", account_data_hash="a"))
    engine.process_path_event(_event("missing-units", 110, 20_200, fdv_units=None, fdv_usd=20_200, reserve_state_fingerprint="b", account_data_hash="b"))
    decisions = _rows(config.paper_decisions_path)

    assert any(row.get("rejection_reason") == "missing_fdv_units" for row in decisions)
    assert rule_runtime_status(config)["paper_buys"] == 0


def test_pumpfun_token2022_with_valid_curve_decode_is_supported_for_paper_entry(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    token_2022_program = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    engine.process_path_event(
        _event(
            "token-2022-pump",
            100,
            20_100,
            token_program=token_2022_program,
            mint_account_owner=token_2022_program,
            pumpfun_create_verified=True,
            bonding_curve_pda_verified=True,
            bonding_curve_decode_status="success",
            calculation_status="success",
            reserve_state_fingerprint="token2022-a",
            account_data_hash="token2022-a",
        )
    )
    engine.process_path_event(
        _event(
            "token-2022-pump",
            110,
            20_200,
            token_program=token_2022_program,
            mint_account_owner=token_2022_program,
            pumpfun_create_verified=True,
            bonding_curve_pda_verified=True,
            bonding_curve_decode_status="success",
            calculation_status="success",
            reserve_state_fingerprint="token2022-b",
            account_data_hash="token2022-b",
        )
    )
    decision = next(
        row
        for row in _rows(config.paper_decisions_path)
        if row["mint"] == "token-2022-pump" and row["paper_event_id"].startswith("decision_")
    )

    assert decision["token_program_status"] == "pumpfun_token2022_supported"
    assert decision["pumpfun_token2022_supported"] is True
    assert decision["token_program_gate_result"] == "pass"
    assert "unsupported_token_program" not in decision["risk_labels"]
    assert rule_runtime_status(config)["pumpfun_token2022_supported_count"] == 1


def test_token2022_without_valid_pumpfun_curve_decode_rejects_paper_entry(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    token_2022_program = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    engine.process_path_event(
        _event(
            "invalid-token-2022",
            100,
            20_100,
            token_program=token_2022_program,
            mint_account_owner=token_2022_program,
            pumpfun_create_verified=False,
            bonding_curve_pda_verified=True,
            bonding_curve_decode_status="success",
            calculation_status="success",
            reserve_state_fingerprint="invalid-token2022-a",
            account_data_hash="invalid-token2022-a",
        )
    )
    engine.process_path_event(
        _event(
            "invalid-token-2022",
            110,
            20_200,
            token_program=token_2022_program,
            mint_account_owner=token_2022_program,
            pumpfun_create_verified=False,
            bonding_curve_pda_verified=True,
            bonding_curve_decode_status="success",
            calculation_status="success",
            reserve_state_fingerprint="invalid-token2022-b",
            account_data_hash="invalid-token2022-b",
        )
    )
    decision = next(
        row
        for row in _rows(config.paper_decisions_path)
        if row["mint"] == "invalid-token-2022" and row["paper_event_id"].startswith("decision_")
    )

    assert decision["decision"] == "paper_rejected_entry"
    assert decision["rejection_reason"] == "unsupported_token_program"
    assert "unsupported_token_program" in decision["risk_labels"]
    assert decision["token_program_status"] == "unsupported_token_program"
    assert decision["pumpfun_token2022_supported"] is False
    assert decision["token_program_gate_result"] == "reject"
    status = rule_runtime_status(config)
    assert status["paper_buys"] == 0
    assert status["unsupported_token_program_reject_count"] == 1


def test_unknown_token_program_rejects_paper_entry(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("unknown-program", 100, 20_100, token_program="unknown111", reserve_state_fingerprint="unknown-a", account_data_hash="unknown-a"))
    engine.process_path_event(_event("unknown-program", 110, 20_200, token_program="unknown111", reserve_state_fingerprint="unknown-b", account_data_hash="unknown-b"))
    decision = next(row for row in _rows(config.paper_decisions_path) if row["mint"] == "unknown-program" and row["paper_event_id"].startswith("decision_"))

    assert decision["decision"] == "paper_rejected_entry"
    assert decision["token_program_status"] == "unknown_token_program"
    assert decision["token_program_gate_result"] == "reject"
    assert rule_runtime_status(config)["unknown_token_program_count"] == 1


def test_duplicate_state_block_clears_after_later_distinct_confirmation(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)
    common = {
        "data_source": "bonding_curve_account_state",
        "fdv_source": "bonding_curve_account_state",
        "fdv_source_confidence": "high",
        "fdv_units": "usd",
        "fdv_usd": 20_250,
        "fdv_sol": 253.125,
        "reserve_state_fingerprint": "same-state-before-distinct",
        "account_data_hash": "same-hash-before-distinct",
        "slot": 7,
    }

    engine.process_path_event(_event("duplicate-clears", 100, 20_250, **common))
    second = engine.process_path_event(_event("duplicate-clears", 101, 20_250, **common))
    third = engine.process_path_event(
        _event(
            "duplicate-clears",
            110,
            20_600,
            reserve_state_fingerprint="later-distinct-state",
            account_data_hash="later-distinct-hash",
            slot=8,
        )
    )
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    candidate = state["candidates"]["duplicate-clears"]
    final_decision = [row for row in _rows(config.paper_decisions_path) if row["mint"] == "duplicate-clears"][-1]

    assert second["confirmed_crossed_20k"] is False
    assert third["confirmed_crossed_20k"] is True
    assert candidate["duplicate_state_seen"] is True
    assert candidate["duplicate_state_block_active"] is False
    assert candidate["duplicate_state_block_cleared"] is True
    assert candidate["duplicate_state_seen_before_distinct_confirmation"] is True
    assert final_decision["rejection_reason"] != "duplicate_same_state_confirmation"


def test_entry_band_rejects_first_observation_above_allowed_entry_zone(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("missed-entry", 100, 12_000, reserve_state_fingerprint="missed-a", account_data_hash="missed-a"))
    engine.process_path_event(_event("missed-entry", 110, 27_500, reserve_state_fingerprint="missed-b", account_data_hash="missed-b"))
    result = engine.process_path_event(_event("missed-entry", 111, 27_700, reserve_state_fingerprint="missed-c", account_data_hash="missed-c"))
    decision = [row for row in _rows(config.paper_decisions_path) if row["mint"] == "missed-entry"][-1]

    assert result["paper_buy_created"] is False
    assert decision["decision"] == "paper_rejected_entry"
    assert decision["entry_band_result"] == "reject"
    assert decision["entry_band_rejection_reason"] == "missed_live_arm"
    assert decision["missed_entry_zone"] is True
    assert decision["missed_live_arm"] is True
    assert decision["chase_guard_exceeded"] is True
    assert decision["observed_inside_entry_zone"] is False
    assert rule_runtime_status(config)["missed_entry_zone_count"] == 1
    assert rule_runtime_status(config)["missed_live_arm_count"] == 1


def test_entry_band_allows_fast_runner_inside_26k_chase_zone(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("fast-entry", 100, 14_000, reserve_state_fingerprint="fast-a", account_data_hash="fast-a"))
    engine.process_path_event(_event("fast-entry", 110, 24_500, reserve_state_fingerprint="fast-b", account_data_hash="fast-b"))
    result = engine.process_path_event(_event("fast-entry", 111, 24_700, reserve_state_fingerprint="fast-c", account_data_hash="fast-c"))
    decision = [row for row in _rows(config.paper_decisions_path) if row["mint"] == "fast-entry"][-1]

    assert result["paper_buy_created"] is True
    assert decision["decision"] == "paper_buy"
    assert decision["entry_band_result"] == "pass"
    assert decision["entry_zone_max_usd"] == 26_000.0
    assert decision["chase_guard_result"] == "pass"
    assert decision["hot_watch_active_before_entry"] is True


def test_watch_mode_arms_entry_zone_at_14k() -> None:
    assert _watch_mode_for_fdv(13_999.0) == "confirmed_10k_watch"
    assert _watch_mode_for_fdv(14_000.0) == "entry_zone_watch"


def test_fake_volume_dev_pump_or_missing_holder_depth_rejects_primary_paper_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("label-risk", 100, 20_100, events=1, buys=0, wallets=1, holder_count_at_10k_proxy=None, reserve_state_fingerprint="risk-a", account_data_hash="risk-a"))
    engine.process_path_event(_event("label-risk", 110, 20_200, events=1, buys=0, wallets=1, holder_count_at_10k_proxy=None, reserve_state_fingerprint="risk-b", account_data_hash="risk-b"))
    decision = next(
        row
        for row in _rows(config.paper_decisions_path)
        if row["mint"] == "label-risk" and row["paper_event_id"].startswith("decision_")
    )

    assert decision["decision"] == "paper_rejected_entry"
    assert decision["rejection_reason"] == "high_risk_label_hard_reject"
    assert "dev_pump_suspect" in decision["risk_labels"]
    assert "fake_volume_suspect" in decision["risk_labels"]
    assert "missing_holder_depth" in decision["risk_labels"]
    status = rule_runtime_status(config)
    assert status["paper_buys"] == 0
    assert status["dev_pump_suspect_count"] >= 1
    assert status["fake_volume_suspect_count"] >= 1
    assert status["missing_holder_depth_label_count"] >= 1


def test_holder_gate_and_mayhem_labels_are_entry_safe(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("holder-one", 100, 20_100, holder_count_at_10k_proxy=1, mayhem_mode=True, reserve_state_fingerprint="h1a", account_data_hash="h1a"))
    engine.process_path_event(_event("holder-one", 110, 20_200, holder_count_at_10k_proxy=1, mayhem_mode=True, reserve_state_fingerprint="h1b", account_data_hash="h1b"))
    engine.process_path_event(_event("holder-three", 200, 20_100, holder_count_at_10k_proxy=3, mayhem_mode=True, reserve_state_fingerprint="h3a", account_data_hash="h3a"))
    engine.process_path_event(_event("holder-three", 210, 20_200, holder_count_at_10k_proxy=3, mayhem_mode=True, reserve_state_fingerprint="h3b", account_data_hash="h3b"))
    decisions = _rows(config.paper_decisions_path)
    holder_one = next(row for row in decisions if row["mint"] == "holder-one" and row["paper_event_id"].startswith("decision_"))
    holder_three = next(row for row in decisions if row["mint"] == "holder-three" and row["paper_event_id"].startswith("decision_"))

    assert holder_one["decision"] == "paper_rejected_entry"
    assert holder_one["rejection_reason"] == "holder_count_lte_1_hard_reject"
    assert "mayhem_mode" in holder_one["risk_labels"]
    assert holder_three["decision"] == "paper_buy"
    assert "low_holder_depth_2_to_4" in holder_three["risk_labels"]
    assert "mayhem_mode" in holder_three["risk_labels"]
    assert "holder_count_lte_1_hard_reject" not in holder_three["risk_labels"]


def test_stagnation_after_runup_triggers_paper_sell(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    engine = RuleRuntimeEngine(config)

    engine.process_path_event(_event("stagnate", 100, 20_100, reserve_state_fingerprint="s-a", account_data_hash="s-a"))
    engine.process_path_event(_event("stagnate", 110, 20_200, reserve_state_fingerprint="s-b", account_data_hash="s-b"))
    engine.process_path_event(_event("stagnate", 130, 31_000, reserve_state_fingerprint="s-c", account_data_hash="s-c"))
    result = engine.process_path_event(_event("stagnate", 260, 30_500, reserve_state_fingerprint="s-d", account_data_hash="s-d"))
    sells = [row for row in _rows(config.paper_trades_path) if row.get("side") == "paper_sell"]

    assert result["paper_sell_created"] is True
    assert sells[-1]["exit_reason"] == "stagnation_after_runup"
    assert sells[-1]["stagnation_exit_triggered"] is True
    assert rule_runtime_status(config)["stagnation_exit_count"] == 1


def test_retroactive_safety_review_voids_bugged_and_chased_buys(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    state["cash_usd"] = 171.75
    state["wallet_usd"] = 300.0
    for mint, fdv, allocation in [
        ("DNAtTgzVBrR2hwKrRNqG8Y1ECuuGxLLxEme5KAMGpump", 26_210.75, 45.0),
        ("BhooE6fGh6eqK3h2Tj6MBiEayjv26ah4A2oDUjqrpump", 27_876.00, 45.0),
        ("G7ezsywkeKqbW57MiZNQWb6UKmYwpAoe7KfBkVEgpump", 23_394.22, 38.25),
    ]:
        state["open_positions"][mint] = {"mint": mint, "paper_buy_fdv": fdv, "allocation_usd": allocation, "paper_units": allocation / fdv, "side": "paper_buy"}
    config.runtime_state_path.write_text(json.dumps(state), encoding="utf-8")
    audit_rows = [
        {"mint": "DNAtTgzVBrR2hwKrRNqG8Y1ECuuGxLLxEme5KAMGpump", "paper_buy_fdv": 26_210.75, "paper_buy_found": True, "warnings": ["manual_axiom_market_cap_materially_below_runtime_fdv"], "paper_buy_fdv_above_trigger_pct": 0.3105375},
        {"mint": "BhooE6fGh6eqK3h2Tj6MBiEayjv26ah4A2oDUjqrpump", "paper_buy_fdv": 27_876.00, "paper_buy_found": True, "warnings": ["paper_buy_fdv_more_than_15pct_above_trigger_without_chase_approval"], "paper_buy_fdv_above_trigger_pct": 0.239659},
        {"mint": "G7ezsywkeKqbW57MiZNQWb6UKmYwpAoe7KfBkVEgpump", "paper_buy_fdv": 23_394.22, "paper_buy_found": True, "warnings": ["confirming_rows_duplicate_same_state"], "paper_buy_fdv_above_trigger_pct": 0.0},
    ]
    config.paper_buy_fdv_reconciliation_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.paper_buy_fdv_reconciliation_audit_json_path.write_text(json.dumps({"rows": audit_rows}), encoding="utf-8")

    review = run_rule_runtime_safety_patch_review(config)
    status = rule_runtime_status(config)

    assert review["retroactive_review"]["voided_paper_buys"] == 3
    assert status["voided_paper_buys"] == 3
    assert status["valid_paper_buys"] == 0
    assert status["cash_usd"] == 300.0
    assert config.retroactive_paper_buy_safety_review_json_path.exists()


def test_retroactive_safety_review_voids_unsupported_or_high_risk_paper_buy(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    state["cash_usd"] = 285.0
    state["wallet_usd"] = 300.0
    state["open_positions"]["token-2022-pump"] = {
        "mint": "token-2022-pump",
        "paper_buy_fdv": 22_436.05,
        "allocation_usd": 15.0,
        "paper_units": 15.0 / 22_436.05,
        "side": "paper_buy",
    }
    state["candidates"]["token-2022-pump"] = {
        "mint": "token-2022-pump",
        "state": "paper_position_open",
        "tier": 4,
        "paper_buy_created": True,
    }
    state["variant_open_positions"]["FDV_BASELINE_20K|token-2022-pump"] = {
        "variant_id": "FDV_BASELINE_20K",
        "mint": "token-2022-pump",
        "paper_buy_fdv": 22_436.05,
        "no_real_trade": True,
    }
    config.runtime_state_path.write_text(json.dumps(state), encoding="utf-8")
    config.paper_trades_path.write_text(
        json.dumps(
            {
                "mint": "token-2022-pump",
                "ca": "token-2022-pump",
                "side": "paper_buy",
                "timestamp": 100.0,
                "allocation_usd": 15.0,
                "paper_buy_fdv": 22_436.05,
                "fdv_usd": 22_436.05,
                "fdv_units": "usd",
                "token_program": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                "mint_account_owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                "risk_labels": ["dev_pump_suspect", "fake_volume_suspect", "missing_holder_depth"],
                "no_real_trade": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review = run_rule_runtime_safety_patch_review(config)
    status = rule_runtime_status(config)
    row = next(row for row in review["rows"] if row["mint"] == "token-2022-pump")

    assert row["action"] == "voided"
    assert row["void_reason"] == "unsupported_token_program"
    assert status["valid_paper_buys"] == 0
    assert status["voided_paper_buys"] == 1
    assert status["variants"]["FDV_BASELINE_20K"]["open_positions"] == 0
    assert status["cash_usd"] == 300.0


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


def test_bonding_curve_probe_uses_existing_helius_only_without_paid_provider_dependency() -> None:
    text = Path("research/mtp_research/validation/bonding_curve_account_state.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "laserstream",
        "yellowstone",
        "geyser",
        "pumpportal",
        "birdeye",
        "bitquery",
        "jupiter",
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


def test_transaction_subscribe_smoke_resolves_beta_endpoint_before_stream(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source

    captured: dict[str, object] = {}
    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            captured["config"] = config
            captured["websocket_url"] = websocket_url
            captured["timeout_seconds"] = timeout_seconds

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            captured["max_events"] = max_events
            captured["max_seconds"] = max_seconds
            captured["on_create_event"] = on_create_event
            return []

    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=3,
        max_runtime_seconds=2.0,
    )

    assert captured["websocket_url"] == "wss://beta.helius-rpc.com/?api-key=test-key"
    assert captured["timeout_seconds"] == 2.0
    assert captured["max_events"] == 3
    assert captured["max_seconds"] == 2.0
    assert summary["transactionSubscribe_used"] is True


def test_transaction_subscribe_smoke_starts_probes_during_stream(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-a_123_0",
        "signature": "sig-a",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "mint-a",
        "bonding_curve": "curve-a",
        "parser_status": "decoded",
    }
    stream_active = {"value": False}
    probe_started_during_stream: list[bool] = []

    def append_row(path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            stream_active["value"] = True
            append_row(self.config.pumpfun_create_stream_events_path, create_event)
            on_create_event(dict(create_event))
            for _ in range(100):
                if probe_started_during_stream:
                    break
                import time

                time.sleep(0.01)
            stream_active["value"] = False
            return [create_event]

    def fake_probe_runner(
        config: RuleRuntimeConfig,
        create: dict,
        *,
        probe: object,
        event_callback=None,
        now_fn=None,
        follow_up_probe_delays=None,
    ) -> dict:
        assert follow_up_probe_delays == ()
        probe_started_during_stream.append(stream_active["value"])
        row = {
            "event_id": "probe-a",
            "mint": create["mint"],
            "bonding_curve": create["bonding_curve"],
            "source_create_signature": create["signature"],
            "create_observed_at": create["observed_at"],
            "probe_started_at": 100.01,
            "first_curve_state_at": 100.02,
            "first_fdv_emitted_at": 100.02,
            "observed_to_probe_started_ms": 10.0,
            "probe_started_to_first_curve_state_ms": 10.0,
            "observed_to_first_fdv_emitted_ms": 20.0,
            "probe_attempt_count": 2,
            "account_not_found_retry_count": 1,
            "account_not_found_recovered_by_retry": True,
            "first_failure_reason": "account_not_found",
            "retry_delays_ms": [100.0],
            "winning_probe_source": "getAccountInfo_processed",
            "probe_status": "success",
            "probe_scheduled_during_stream": create.get("probe_scheduled_during_stream"),
            "helius_rpc_request_count": 1,
            "http_429_count": 0,
        }
        append_row(config.bonding_curve_account_probe_events_path, row)
        if event_callback is not None:
            event_callback(
                {
                    "event_id": "fdv-a",
                    "mint": create["mint"],
                    "timestamp": 100.02,
                    "observed_at": create["observed_at"],
                    "event_observed_at": create["observed_at"],
                    "fdv_proxy": 9_000.0,
                    "source_event_type": "fdv_path_update",
                    "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                    "fdv_source": "bonding_curve_account_state",
                    "fdv_source_confidence": "high",
                    "observed_to_first_fdv_account_state_ms": 20.0,
                }
            )
        return row

    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=2.0,
    )

    assert probe_started_during_stream == [True]
    assert summary["probes_started_during_stream"] == 1
    assert summary["decoded_create_mints_with_probe"] == 1
    assert summary["decoded_create_unique_mints"] == 1
    assert summary["decoded_create_mints_without_probe"] == 0
    assert summary["decoded_create_probe_coverage_rate"] == 1.0
    assert summary["account_not_found_retries"] == 1
    assert summary["account_not_found_recovered_by_retry"] == 1
    assert summary["observed_to_probe_started_p50_p90_p99"] == {"p50": 10.0, "p90": 10.0, "p99": 10.0}
    assert summary["observed_to_first_fdv_p50_p90_p99"] == {"p50": 20.0, "p90": 20.0, "p99": 20.0}


def test_transaction_subscribe_smoke_keeps_low_fdv_runners_on_post_birth_watch(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source
    from research.mtp_research.validation import rule_runtime_v1 as runtime

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-low_123_0",
        "signature": "sig-low",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "late-runner",
        "bonding_curve": "curve-late",
        "parser_status": "decoded",
    }
    probe_calls: list[str] = []
    probe_threads: dict[str, str] = {}

    def append_row(path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            append_row(self.config.pumpfun_create_stream_events_path, create_event)
            on_create_event(dict(create_event))
            if on_idle is not None:
                on_idle()
            return [create_event]

    def fake_probe_runner(
        config: RuleRuntimeConfig,
        create: dict,
        *,
        probe: object,
        event_callback=None,
        now_fn=None,
        follow_up_probe_delays=None,
    ) -> dict:
        if create.get("post_birth_watch_follow_up_scheduled"):
            phase = "post_birth_watch_follow_up"
        elif create.get("hot_watch_follow_up_scheduled"):
            phase = "entry_zone_hot_watch_follow_up"
        elif create.get("confirmation_follow_up_scheduled"):
            phase = "confirmation_follow_up"
        else:
            phase = "initial"
        probe_calls.append(phase)
        probe_threads[phase] = threading.current_thread().name
        fdv = 24_000.0 if phase in {"post_birth_watch_follow_up", "confirmation_follow_up"} else 2_400.0
        row = {
            "event_id": f"probe-{phase}",
            "mint": create["mint"],
            "bonding_curve": create["bonding_curve"],
            "source_create_signature": create["signature"],
            "create_observed_at": create["observed_at"],
            "probe_started_at": 100.01,
            "first_curve_state_at": 100.02,
            "first_fdv_emitted_at": 100.02,
            "observed_to_probe_started_ms": 10.0,
            "probe_started_to_first_curve_state_ms": 10.0,
            "observed_to_first_fdv_emitted_ms": 20.0,
            "probe_attempt_count": 1,
            "account_not_found_retry_count": 0,
            "account_not_found_recovered_by_retry": False,
            "probe_status": "success",
            "probe_phase": phase,
            "probe_scheduled_during_stream": create.get("probe_scheduled_during_stream"),
            "post_birth_watch_follow_up_scheduled": bool(create.get("post_birth_watch_follow_up_scheduled")),
            "post_birth_watch_lane": create.get("post_birth_watch_lane"),
            "fdv_proxy": fdv,
            "fdv_usd": fdv,
            "fdv_units": "usd",
            "helius_rpc_request_count": 1,
            "http_429_count": 0,
        }
        append_row(config.bonding_curve_account_probe_events_path, row)
        if event_callback is not None and phase == "post_birth_watch_follow_up":
            for index, confirm_fdv in enumerate((21_000.0, fdv), start=1):
                event_callback(
                    {
                        "event_id": f"fdv-{phase}-{index}",
                        "mint": create["mint"],
                        "timestamp": 125.0 + index,
                        "observed_at": create["observed_at"],
                        "event_observed_at": create["observed_at"],
                        "fdv_proxy": confirm_fdv,
                        "fdv_usd": confirm_fdv,
                        "fdv_units": "usd",
                        "source_event_type": "fdv_path_update",
                        "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                        "fdv_source": "bonding_curve_account_state",
                        "fdv_source_confidence": "high",
                        "account_data_hash": f"hash-{phase}-{index}",
                        "reserve_state_fingerprint": f"reserve-{phase}-{index}",
                        "observed_to_first_fdv_account_state_ms": 20.0,
                    }
                )
        elif event_callback is not None:
            event_callback(
                {
                    "event_id": f"fdv-{phase}",
                    "mint": create["mint"],
                    "timestamp": 100.02 if phase == "initial" else 125.0,
                    "observed_at": create["observed_at"],
                    "event_observed_at": create["observed_at"],
                    "fdv_proxy": fdv,
                    "fdv_usd": fdv,
                    "fdv_units": "usd",
                    "source_event_type": "fdv_path_update",
                    "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                    "fdv_source": "bonding_curve_account_state",
                    "fdv_source_confidence": "high",
                    "account_data_hash": f"hash-{phase}",
                    "reserve_state_fingerprint": f"reserve-{phase}",
                    "observed_to_first_fdv_account_state_ms": 20.0,
                }
            )
        return row

    monkeypatch.setattr(runtime, "POST_BIRTH_WATCH_TRIGGER_FDV", 2_000.0, raising=False)
    monkeypatch.setattr(runtime, "POST_BIRTH_WATCH_PROBE_DELAYS_SECONDS", (0.0,), raising=False)
    monkeypatch.setattr(runtime, "ENTRY_ZONE_PROBE_DELAYS_SECONDS", (0.0,), raising=False)
    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=2.0,
    )

    assert probe_calls[0] == "initial"
    assert probe_calls.count("post_birth_watch_follow_up") == 1
    assert probe_calls.count("confirmation_follow_up") == 1
    assert probe_calls.count("entry_zone_hot_watch_follow_up") == 1
    assert probe_threads["initial"].startswith("txsub-fdv-probe")
    assert probe_threads["post_birth_watch_follow_up"].startswith("txsub-watch-follow-up")
    assert summary["post_birth_watch_follow_up_futures"] == 1
    assert summary["post_birth_watch_follow_up_probe_rows"] == 1
    assert summary["post_birth_watch_follow_up_successes"] == 1
    assert summary["post_birth_watch_probe_count"] == 1
    assert summary["post_birth_watch_success_count"] == 1
    assert summary["post_birth_watch_promotions_to_5k"] == 1
    assert summary["post_birth_watch_promotions_to_10k"] == 1
    assert summary["post_birth_watch_promotions_to_20k"] == 1
    assert summary["post_birth_watch_lane_counts"] == {"low_fdv": 1}
    assert summary["confirmed_20k_candidates"] == 1


def test_transaction_subscribe_shutdown_cancels_slow_watch_followups(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source
    from research.mtp_research.validation import rule_runtime_v1 as runtime

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-shutdown_123_0",
        "signature": "sig-shutdown",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "slow-watch-runner",
        "bonding_curve": "curve-slow-watch",
        "parser_status": "decoded",
    }

    def append_row(path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            append_row(self.config.pumpfun_create_stream_events_path, create_event)
            on_create_event(dict(create_event))
            if on_idle is not None:
                on_idle()
            return [create_event]

    def fake_probe_runner(
        config: RuleRuntimeConfig,
        create: dict,
        *,
        probe: object,
        event_callback=None,
        now_fn=None,
        follow_up_probe_delays=None,
    ) -> dict:
        is_watch_follow_up = bool(create.get("post_birth_watch_follow_up_scheduled"))
        if is_watch_follow_up:
            time.sleep(0.2)
        fdv = 2_400.0
        phase = "post_birth_watch_follow_up" if is_watch_follow_up else "initial"
        row = {
            "event_id": f"probe-{phase}",
            "mint": create["mint"],
            "bonding_curve": create["bonding_curve"],
            "source_create_signature": create["signature"],
            "create_observed_at": create["observed_at"],
            "probe_started_at": 100.01,
            "first_curve_state_at": 100.02,
            "first_fdv_emitted_at": 100.02,
            "observed_to_probe_started_ms": 10.0,
            "probe_started_to_first_curve_state_ms": 10.0,
            "observed_to_first_fdv_emitted_ms": 20.0,
            "probe_attempt_count": 1,
            "account_not_found_retry_count": 0,
            "account_not_found_recovered_by_retry": False,
            "probe_status": "success",
            "probe_phase": phase,
            "probe_scheduled_during_stream": create.get("probe_scheduled_during_stream"),
            "post_birth_watch_follow_up_scheduled": is_watch_follow_up,
            "post_birth_watch_lane": create.get("post_birth_watch_lane"),
            "fdv_proxy": fdv,
            "fdv_usd": fdv,
            "fdv_units": "usd",
            "helius_rpc_request_count": 1,
            "http_429_count": 0,
        }
        append_row(config.bonding_curve_account_probe_events_path, row)
        if event_callback is not None and not is_watch_follow_up:
            event_callback(
                {
                    "event_id": f"fdv-{phase}",
                    "mint": create["mint"],
                    "timestamp": 100.02,
                    "observed_at": create["observed_at"],
                    "event_observed_at": create["observed_at"],
                    "fdv_proxy": fdv,
                    "fdv_usd": fdv,
                    "fdv_units": "usd",
                    "source_event_type": "fdv_path_update",
                    "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                    "fdv_source": "bonding_curve_account_state",
                    "fdv_source_confidence": "high",
                    "account_data_hash": "hash-initial",
                    "reserve_state_fingerprint": "reserve-initial",
                    "observed_to_first_fdv_account_state_ms": 20.0,
                }
            )
        return row

    monkeypatch.setattr(runtime, "POST_BIRTH_WATCH_TRIGGER_FDV", 2_000.0, raising=False)
    monkeypatch.setattr(runtime, "POST_BIRTH_WATCH_PROBE_DELAYS_SECONDS", (0.0,) * 8, raising=False)
    monkeypatch.setattr(runtime, "TRANSACTION_SUBSCRIBE_SHUTDOWN_GRACE_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    started = time.monotonic()
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=1.0,
    )

    assert time.monotonic() - started < 1.0
    assert summary["decoded_create_probe_coverage_rate"] == 1.0
    assert summary["helius_transaction_subscribe_first_fdv"]["shutdown_cancelled_watch_follow_up_futures"] > 0


def test_transaction_subscribe_status_reports_decoded_creates_without_probe(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.helius_transaction_subscribe_capability_audit_json_path.write_text(
        json.dumps(
            {
                "recommended_endpoint": {
                    "name": "helius_beta",
                    "transactionSubscribe_supported": True,
                }
            }
        ),
        encoding="utf-8",
    )
    config.pumpfun_create_stream_events_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"mint": "mint-covered", "parser_status": "decoded", "bonding_curve_verified": True},
                {"mint": "mint-missing", "parser_status": "decoded", "bonding_curve_verified": True},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config.bonding_curve_account_probe_events_path.write_text(
        json.dumps({"mint": "mint-covered", "probe_status": "success", "probe_scheduled_during_stream": True}) + "\n",
        encoding="utf-8",
    )

    txsub = rule_runtime_status(config)["helius_transaction_subscribe_first_fdv"]

    assert txsub["decoded_create_unique_mints"] == 2
    assert txsub["decoded_create_mints_with_probe"] == 1
    assert txsub["decoded_create_mints_without_probe"] == 1
    assert txsub["decoded_create_probe_coverage_rate"] == 0.5
    assert txsub["decoded_create_mints_without_probe_sample"] == ["mint-missing"]
    assert "decoded_creates_missing_bonding_curve_probe" in txsub["warnings"]


def test_transaction_subscribe_first_fdv_latency_uses_initial_probe_rows(tmp_path: Path) -> None:
    config = RuleRuntimeConfig(data_root=tmp_path)
    initialize_rule_runtime(config, reset=True)
    config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.helius_transaction_subscribe_capability_audit_json_path.write_text(
        json.dumps(
            {
                "recommended_endpoint": {
                    "name": "helius_beta",
                    "transactionSubscribe_supported": True,
                }
            }
        ),
        encoding="utf-8",
    )
    config.pumpfun_create_stream_events_path.write_text(
        json.dumps({"mint": "latency-mint", "parser_status": "decoded", "bonding_curve_verified": True}) + "\n",
        encoding="utf-8",
    )
    config.bonding_curve_account_probe_events_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {
                    "mint": "latency-mint",
                    "probe_status": "success",
                    "probe_phase": "initial",
                    "probe_scheduled_during_stream": True,
                    "observed_to_probe_started_ms": 10.0,
                    "observed_to_first_fdv_emitted_ms": 20.0,
                    "getAccountInfo_latency_ms": 5.0,
                },
                {
                    "mint": "latency-mint",
                    "probe_status": "success",
                    "probe_phase": "post_birth_watch_follow_up",
                    "probe_scheduled_during_stream": True,
                    "observed_to_probe_started_ms": 300_000.0,
                    "observed_to_first_fdv_emitted_ms": 300_020.0,
                    "getAccountInfo_latency_ms": 5.0,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    txsub = rule_runtime_status(config)["helius_transaction_subscribe_first_fdv"]

    assert txsub["observed_to_probe_started_p50_p90_p99"] == {"p50": 10.0, "p90": 10.0, "p99": 10.0}
    assert txsub["observed_to_first_fdv_p50_p90_p99"] == {"p50": 20.0, "p90": 20.0, "p99": 20.0}


def test_transaction_subscribe_smoke_schedules_confirmation_followups_for_near_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-confirm_123_0",
        "signature": "sig-confirm",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "confirm-me",
        "bonding_curve": "curve-confirm",
        "parser_status": "decoded",
    }
    probe_calls: list[tuple[float, ...]] = []

    def append_row(path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            append_row(self.config.pumpfun_create_stream_events_path, create_event)
            on_create_event(dict(create_event))
            return [create_event]

    def emit_path(event_callback, fdv: float, ts: float, fingerprint: str) -> None:
        if event_callback is None:
            return
        event_callback(
            {
                "event_id": f"fdv-confirm-{fingerprint}",
                "mint": create_event["mint"],
                "timestamp": ts,
                "observed_at": create_event["observed_at"],
                "event_observed_at": create_event["observed_at"],
                "fdv_proxy": fdv,
                "fdv_usd": fdv,
                "fdv_units": "usd",
                "source_event_type": "fdv_path_update",
                "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                "fdv_source": "bonding_curve_account_state",
                "fdv_source_confidence": "high",
                "reserve_state_fingerprint": fingerprint,
                "account_data_hash": fingerprint,
            }
        )

    def fake_probe_runner(
        config: RuleRuntimeConfig,
        create: dict,
        *,
        probe: object,
        event_callback=None,
        now_fn=None,
        follow_up_probe_delays=None,
    ) -> dict:
        delays = tuple(follow_up_probe_delays or ())
        probe_calls.append(delays)
        if not delays:
            row = {
                "event_id": "probe-initial-confirm",
                "mint": create["mint"],
                "bonding_curve": create["bonding_curve"],
                "probe_status": "success",
                "probe_scheduled_during_stream": True,
                "fdv_proxy": 6_000.0,
                "fdv_usd": 6_000.0,
                "fdv_units": "usd",
                "observed_to_probe_started_ms": 5.0,
                "helius_rpc_request_count": 1,
                "http_429_count": 0,
            }
            append_row(config.bonding_curve_account_probe_events_path, row)
            emit_path(event_callback, 6_000.0, 100.01, "initial-state")
            return row
        row = {
            "event_id": "probe-confirmation-followup",
            "mint": create["mint"],
            "bonding_curve": create["bonding_curve"],
            "probe_status": "success",
            "probe_phase": "confirmation_follow_up",
            "fdv_proxy": 12_000.0,
            "fdv_usd": 12_000.0,
            "fdv_units": "usd",
            "observed_to_probe_started_ms": 250.0,
            "helius_rpc_request_count": 2,
            "http_429_count": 0,
        }
        append_row(config.bonding_curve_account_probe_events_path, row)
        emit_path(event_callback, 11_000.0, 100.25, "confirm-state-a")
        emit_path(event_callback, 12_000.0, 101.00, "confirm-state-b")
        return row

    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=2.0,
    )

    assert probe_calls[0] == ()
    assert any(delays for delays in probe_calls[1:])
    assert summary["decoded_create_probe_coverage_rate"] == 1.0
    assert summary["confirmed_10k_watches"] == 1


def test_transaction_subscribe_cleanup_drains_late_hot_watch_jobs(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source
    from research.mtp_research.validation import rule_runtime_v1 as runtime

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-hot-late_123_0",
        "signature": "sig-hot-late",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "late-hot-watch",
        "bonding_curve": "curve-hot-late",
        "parser_status": "decoded",
    }
    probe_phases: list[str] = []

    def append_row(path: Path, row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            append_row(self.config.pumpfun_create_stream_events_path, create_event)
            on_create_event(dict(create_event))
            return [create_event]

    def fake_probe_runner(
        config: RuleRuntimeConfig,
        create: dict,
        *,
        probe: object,
        event_callback=None,
        now_fn=None,
        follow_up_probe_delays=None,
    ) -> dict:
        if create.get("hot_watch_follow_up_scheduled"):
            phase = "near_threshold_hot_watch_follow_up"
            fdv = 13_500.0
            ts = 101.0
        elif create.get("confirmation_follow_up_scheduled"):
            phase = "confirmation_follow_up"
            fdv = 13_500.0
            ts = 100.5
        else:
            time.sleep(0.03)
            phase = "initial"
            fdv = 13_500.0
            ts = 100.03
        probe_phases.append(phase)
        row = {
            "event_id": f"probe-{phase}",
            "mint": create["mint"],
            "bonding_curve": create["bonding_curve"],
            "probe_status": "success",
            "probe_phase": phase,
            "probe_scheduled_during_stream": create.get("probe_scheduled_during_stream"),
            "hot_watch_follow_up_scheduled": bool(create.get("hot_watch_follow_up_scheduled")),
            "fdv_proxy": fdv,
            "fdv_usd": fdv,
            "fdv_units": "usd",
            "observed_to_probe_started_ms": 10.0,
            "observed_to_first_fdv_emitted_ms": 20.0,
            "helius_rpc_request_count": 1,
            "http_429_count": 0,
        }
        append_row(config.bonding_curve_account_probe_events_path, row)
        if event_callback is not None:
            event_callback(
                {
                    "event_id": f"fdv-{phase}",
                    "mint": create["mint"],
                    "timestamp": ts,
                    "observed_at": create["observed_at"],
                    "event_observed_at": create["observed_at"],
                    "fdv_proxy": fdv,
                    "fdv_usd": fdv,
                    "fdv_units": "usd",
                    "source_event_type": "fdv_path_update",
                    "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                    "fdv_source": "bonding_curve_account_state",
                    "fdv_source_confidence": "high",
                    "account_data_hash": f"hash-{phase}",
                    "reserve_state_fingerprint": f"reserve-{phase}",
                    "observed_to_first_fdv_account_state_ms": 20.0,
                }
            )
        return row

    monkeypatch.setattr(runtime, "HOT_WATCH_PROBE_DELAYS_SECONDS", (0.01,), raising=False)
    monkeypatch.setattr(runtime, "CONFIRMATION_FOLLOW_UP_TRIGGER_FDV", 99_000.0, raising=False)
    monkeypatch.setattr(runtime, "TRANSACTION_SUBSCRIBE_SHUTDOWN_GRACE_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=1.0,
    )

    assert probe_phases == ["initial", "near_threshold_hot_watch_follow_up"]
    assert summary["hot_watch_follow_up_futures"] == 1
    assert summary["hot_watch_probe_count"] == 1
    assert summary["entry_zone_watch_probe_count"] == 0
    assert summary["confirmed_20k_candidates"] == 0


def test_transaction_subscribe_smoke_runs_final_archive_sweep_before_summary(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.validation import forward_efficient_mover_observer as observer
    from research.mtp_research.validation import helius_transaction_subscribe_source as tx_source

    audit = {
        "recommended_endpoint": {
            "name": "helius_beta",
            "transactionSubscribe_supported": True,
            "accountSubscribe_supported": True,
            "getAccountInfo_supported": True,
        }
    }
    create_event = {
        "event_id": "txsub_sig-stale_123_0",
        "signature": "sig-stale",
        "slot": 123,
        "observed_at": 100.0,
        "mint": "stale-low",
        "bonding_curve": "curve-stale",
        "parser_status": "decoded",
    }

    def fake_audit(config: RuleRuntimeConfig) -> dict:
        config.helius_transaction_subscribe_capability_audit_json_path.parent.mkdir(parents=True, exist_ok=True)
        config.helius_transaction_subscribe_capability_audit_json_path.write_text(json.dumps(audit), encoding="utf-8")
        return audit

    class FakeCreateSource:
        def __init__(self, *, config: RuleRuntimeConfig, websocket_url: str, timeout_seconds: float) -> None:
            self.config = config

        def fetch_create_events(self, *, max_events: int, max_seconds: float, on_create_event=None, on_idle=None) -> list[dict]:
            assert on_create_event is not None
            on_create_event(dict(create_event))
            return [create_event]

    def fake_probe_runner(config: RuleRuntimeConfig, create: dict, *, probe: object, event_callback=None, now_fn=None, follow_up_probe_delays=None) -> dict:
        assert event_callback is not None
        for index, timestamp in enumerate([100.0, 101.0, 102.0, 103.0]):
            event_callback(
                {
                    "event_id": f"fdv-stale-{index}",
                    "mint": create["mint"],
                    "timestamp": timestamp,
                    "observed_at": create["observed_at"],
                    "event_observed_at": create["observed_at"],
                    "fdv_proxy": 2_257.0,
                    "source_event_type": "fdv_path_update",
                    "source_adapter": "helius_transaction_subscribe_bonding_curve_probe",
                    "fdv_source": "bonding_curve_account_state",
                    "fdv_source_confidence": "high",
                    "observed_to_first_fdv_account_state_ms": 20.0,
                }
            )
        return {
            "event_id": "probe-stale",
            "mint": create["mint"],
            "probe_status": "success",
            "probe_scheduled_during_stream": True,
            "helius_rpc_request_count": 1,
            "http_429_count": 0,
        }

    monkeypatch.setattr(tx_source, "helius_transaction_subscribe_capability_audit", fake_audit)
    monkeypatch.setattr(tx_source, "HeliusTransactionSubscribeCreateSource", FakeCreateSource)
    monkeypatch.setattr(tx_source, "run_bonding_curve_account_probe_for_create_event", fake_probe_runner)
    monkeypatch.setattr(observer, "resolve_forward_sol_usd_price", lambda _root: 100.0)
    monkeypatch.setattr(observer, "resolve_helius_api_key", lambda *, load_project_dotenv=True: "test-key")
    monkeypatch.setattr(observer, "resolve_helius_ws_url", lambda *, load_project_dotenv=True: "wss://configured.example")

    config = RuleRuntimeConfig(data_root=tmp_path)
    summary = run_helius_transaction_subscribe_bonding_curve_probe_smoke(
        config,
        collector_data_root=tmp_path / "collector",
        target_births=1,
        max_runtime_seconds=2.0,
    )

    state = json.loads(config.runtime_state_path.read_text(encoding="utf-8"))
    candidate = state["candidates"]["stale-low"]
    assert candidate["state"] == "archived_no_activity"
    assert candidate["archive_reason"] == "tier_1_low_fdv_flat_stale"
    assert summary["first_fdv_queue"]["tier_1_depth"] == 0
    assert summary["first_fdv_queue"]["tier_1_retention_reasons_oldest_first"] == []


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
