from __future__ import annotations

import json
import csv
import sqlite3
import time
import threading
from pathlib import Path

import pytest

import research.mtp_research.collectors.bonding_curve_progress_recorder_v1 as recorder_module
from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import (
    BroadPumpFunLaunchAdapter,
    BondingCurveProgressRecorder,
    BondingCurveRecorderConfig,
    FakeBirthSourceAuditRoute,
    FakeCurveStateProbe,
    FakeLaunchSource,
    GlobalMigrationDedupeWriter,
    PUMPSWAP_MARKET_ACCOUNT_LENGTH,
    PUMPSWAP_MARKET_DISCRIMINATOR_BYTES,
    PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
    SOL_MINT,
    USDC_MINT,
    _base58_decode_string,
    _decode_pumpswap_market_account_data,
    FakeTransactionSubscribeAuditRoute,
    TransactionSubscribeNormalizedBirthSource,
    compute_true_curve_progress_from_state,
    deterministic_sample_admitted,
    evaluate_t007_thesis_ready_gate,
    progress_priority_tier,
    run_direct_mint_lookup,
    run_migrated_mint_replay,
    run_axiom_reconciliation,
    run_birth_source_audit,
    run_live_smoke,
    run_migration_route_audit,
    run_migration_source_audit,
    run_global_pumpswap_migration_lane,
    run_transaction_live_smoke,
    run_transaction_birth_source_audit,
    run_trade_flow_coverage_audit,
    run_migration_linkage_audit,
    run_migration_capture_forensics,
    run_migration_dedupe_audit,
    run_rebuild_migrations_from_spool,
    run_migration_write_path_audit,
    run_trade_flow_eventful_gap_audit,
    run_long_scan_readiness_audit,
    run_capacity_rejected_migration_promotion_simulation,
    run_migration_full_path_status_reconciliation,
    run_tracking_admission_audit,
    tracking_profile_settings,
    write_t007_thesis_ready_gate,
)
from research.mtp_research.validation.pumpfun_bonding_curve import bonding_curve_pda
from research.mtp_research.validation.t007aa_forward_thesis_dataset_report import summarize_campaign
from research.mtp_research.validation.helius_transaction_subscribe_source import (
    decode_pumpfun_transaction_subscribe_notification,
)


def _launch(mint: str, received_at: float = 1000.0) -> dict:
    return {
        "mint": mint,
        "signature": f"sig-{mint}",
        "slot": 10,
        "block_time": 900,
        "received_at": received_at,
        "source_type": "fake_source",
    }


def _obs(mint: str, progress: float, age: float, *, complete: bool = False, observation_id: str | None = None) -> dict:
    return {
        "mint": mint,
        "slot": int(100 + age),
        "block_time": int(900 + age),
        "received_at": 1000.0 + age,
        "observation_source": "fake_curve",
        "bonding_curve_account": f"curve-{mint}",
        "raw_curve_state": {"virtual_sol_reserves": 1_000_000 + int(progress * 1000), "virtual_token_reserves": 900_000},
        "progress_pct": progress,
        "complete": complete,
        "fdv_proxy": progress * 1000.0,
        "decode_status": "decoded",
        "seconds_since_launch": age,
        "observation_id": observation_id or f"obs-{mint}-{age}",
    }


def test_source_reader_queue_enforces_hard_wall_clock_stop() -> None:
    class DurationIgnoringSource:
        def stream_notifications(self, duration_seconds, on_event):
            started = time.monotonic()
            index = 0
            while time.monotonic() - started < 0.8:
                on_event({"index": index})
                index += 1
                time.sleep(0.005)

    handled: list[dict] = []
    started = time.monotonic()
    stats = recorder_module._stream_notifications_via_reader_queue(
        DurationIgnoringSource(),
        0.05,
        handled.append,
        queue_max_size=100,
        thread_name="test-hard-stop-source-reader",
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert stats["source_consumer_hard_stop_triggered"] is True
    assert stats["source_reader_threaded"] is True
    assert handled


def test_source_reader_queue_prioritizes_birth_events_over_trade_noise() -> None:
    class TradeNoiseThenBirthSource:
        def stream_notifications(self, duration_seconds, on_event):
            for index in range(25):
                on_event({"signature": f"sig-trade-{index}", "trade_rows": [{"mint": f"mint-trade-{index}"}]})
            on_event(
                {
                    "signature": "sig-birth",
                    "decoded_rows": [{"mint": "mint-birth", "bonding_curve": "curve-birth"}],
                }
            )

    handled_signatures: list[str] = []

    def handle_event(event: dict) -> None:
        handled_signatures.append(str(event.get("signature")))
        if event.get("trade_rows") and not event.get("decoded_rows"):
            time.sleep(0.01)

    stats = recorder_module._stream_notifications_via_reader_queue(
        TradeNoiseThenBirthSource(),
        1.0,
        handle_event,
        queue_max_size=100,
        thread_name="test-priority-source-reader",
    )

    assert stats["source_event_queue_high_water_mark"] > 1
    assert "sig-birth" in handled_signatures
    assert handled_signatures.index("sig-birth") < 5


def test_source_reader_queue_can_deprioritize_duplicate_birth_noise() -> None:
    class DuplicateBirthNoiseThenNewBirthSource:
        def stream_notifications(self, duration_seconds, on_event):
            on_event(
                {
                    "signature": "sig-old-first",
                    "decoded_rows": [{"mint": "mint-old", "bonding_curve": "curve-old"}],
                }
            )
            for index in range(25):
                on_event(
                    {
                        "signature": f"sig-old-duplicate-{index}",
                        "decoded_rows": [{"mint": "mint-old", "bonding_curve": "curve-old"}],
                    }
                )
            on_event(
                {
                    "signature": "sig-new-birth",
                    "decoded_rows": [{"mint": "mint-new", "bonding_curve": "curve-new"}],
                }
            )

    queued_birth_mints: set[str] = set()

    def priority_for_first_seen_birth(event: dict) -> int:
        decoded_rows = list(event.get("decoded_rows") or [])
        decoded_mints = {str(row.get("mint")) for row in decoded_rows if row.get("mint")}
        first_seen_mints = decoded_mints - queued_birth_mints
        queued_birth_mints.update(decoded_mints)
        if first_seen_mints:
            return 0
        if decoded_rows:
            return 2
        if event.get("trade_rows"):
            return 1
        return 3

    handled_signatures: list[str] = []

    def handle_event(event: dict) -> None:
        handled_signatures.append(str(event.get("signature")))
        if str(event.get("signature", "")).startswith("sig-old-duplicate-"):
            time.sleep(0.01)

    stats = recorder_module._stream_notifications_via_reader_queue(
        DuplicateBirthNoiseThenNewBirthSource(),
        1.0,
        handle_event,
        queue_max_size=100,
        thread_name="test-duplicate-birth-priority-source-reader",
        event_priority_fn=priority_for_first_seen_birth,
    )

    assert stats["source_event_queue_high_water_mark"] > 1
    assert "sig-new-birth" in handled_signatures
    assert handled_signatures.index("sig-new-birth") < 5


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_strict_curve_admission_excludes_unverified_birth_candidate(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            require_verified_curve_account_for_admission=True,
        )
    )

    row = recorder.process_birth({**_launch("mint-unverified"), "source_type": "transaction_subscribe"})

    assert row["admitted"] is False
    assert row["admission_reason"] == "birth_candidate_unverified_curve"
    assert row["curve_account_verified"] is False
    assert row["thesis_usable_birth"] is False
    assert recorder.states == {}
    summary = recorder.build_summary()
    assert summary["birth_candidate_seen_count"] == 1
    assert summary["birth_candidate_excluded_count"] == 1
    assert summary["birth_candidate_excluded_by_reason"]["birth_candidate_unverified_curve"] == 1
    assert summary["thesis_usable_birth_count"] == 0


def test_strict_curve_admission_accepts_pda_verified_birth(tmp_path: Path) -> None:
    mint = "3sERStHyCYmMtzxokNuTPcyPcq89E9Kmp4nZVEVJpump"
    curve = bonding_curve_pda(mint)
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            require_verified_curve_account_for_admission=True,
        )
    )

    row = recorder.process_birth(
        {
            **_launch(mint),
            "source_type": "transaction_subscribe",
            "decode_route": "direct_create",
            "bonding_curve_account": curve,
        }
    )

    assert row["admitted"] is True
    assert row["admission_reason"] == "sample_admitted"
    assert row["bonding_curve_pda_verified"] is True
    assert row["curve_account_verified"] is True
    assert row["thesis_usable_birth"] is True
    summary = recorder.build_summary()
    assert summary["birth_candidate_seen_count"] == 1
    assert summary["curve_account_resolved_count"] == 1
    assert summary["curve_account_verified_count"] == 1
    assert summary["thesis_usable_birth_count"] == 1


def test_birth_summary_separates_live_and_replay_backfilled_rows(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    recorder.process_birth(_launch("mint-live"))
    recorder.record_replay_backfilled_birth(
        {
            "mint": "mint-replay",
            "launch_signature_from_replay": "sig-replay",
            "launch_slot_from_replay": 123,
            "launch_time_from_replay": 456,
            "pool_or_pair_address": "pool-replay",
            "quote_asset": "SOL",
        }
    )

    summary = recorder.build_summary()

    assert summary["birth_rows_total_including_replay"] == 2
    assert summary["birth_rows_live_source"] == 1
    assert summary["birth_rows_replay_backfilled"] == 1
    assert summary["unique_birth_mints_live_source"] == 1
    assert summary["unique_birth_mints_replay_backfilled"] == 1


def test_replay_backfill_does_not_overwrite_existing_live_birth_mapping(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-existing-live"))

    row = recorder.record_replay_backfilled_birth(
        {
            "mint": "mint-existing-live",
            "launch_signature_from_replay": "sig-replay-existing",
            "launch_slot_from_replay": 123,
            "launch_time_from_replay": 456,
            "pool_or_pair_address": "pool-replay-existing",
            "quote_asset": "SOL",
        }
    )

    assert row["birth_backfilled_from_replay"] is False
    assert row["replay_backfill_skipped_existing_live_birth"] is True
    assert recorder.birth_rows_by_mint["mint-existing-live"]["birth_backfilled_from_replay"] is False
    summary = recorder.build_summary()
    assert summary["migration_backfill_skipped_existing_live_birth_count"] == 1
    assert summary["birth_rows_replay_backfilled"] == 0


def test_lifecycle_coverage_prioritizes_source_miss_over_depth_only_when_birth_absent(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007_full_path_lifecycle_tracker import build_lifecycle_outputs

    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [{"mint": "mint-migration-only", "signature": "sig-mig", "pool_or_pair_address": "pool", "migration_received_at": 300.0}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "post_migration_observations.jsonl",
        [{"mint": "mint-migration-only", "pool_or_pair_address": "pool", "decision_time": 301.0, "base_reserve_raw": 1}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "executable_quote_observations.jsonl",
        [{"mint": "mint-migration-only", "pool_or_pair_address": "pool", "decision_time": 302.0, "price_impact_pct": 0.1}],
    )

    payload = build_lifecycle_outputs(tmp_path, tmp_path, write_outputs=True)
    rows = _jsonl(tmp_path / "lifecycle_ledger.jsonl")

    assert payload["summary"]["coverage_buckets"]["backfill_possible"] == 1
    assert payload["summary"]["source_miss_count"] == 1
    assert rows[0]["first_missing_link"] == "birth_source_miss"
    assert rows[0]["coverage_status"] == "migration_plus_depth_only"
    assert rows[0]["backfill_status"] == "backfill_possible"


def test_lifecycle_source_coverage_separates_preexisting_from_true_source_miss(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007_full_path_lifecycle_tracker import build_lifecycle_outputs

    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"started_at": 1000.0, "ended_at": 1600.0, "run_id": "run-source-coverage"}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-source-coverage"}), encoding="utf-8")
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {"mint": "mint-live", "signature": "sig-mig-live", "pool_or_pair_address": "pool-live", "quote_asset": "SOL"},
            {"mint": "mint-preexisting", "signature": "sig-mig-pre", "pool_or_pair_address": "pool-pre", "quote_asset": "SOL"},
            {"mint": "mint-source-miss", "signature": "sig-mig-miss", "pool_or_pair_address": "pool-miss", "quote_asset": "SOL"},
            {"mint": "mint-unresolved", "signature": "sig-mig-unresolved", "pool_or_pair_address": "pool-unresolved", "quote_asset": "SOL"},
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-live", "admitted": True, "birth_seen_live": True, "birth_backfilled_from_replay": False},
            {
                "mint": "mint-preexisting",
                "birth_seen_live": False,
                "birth_backfilled_from_replay": True,
                "launch_time_from_replay": 900.0,
            },
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "migration_backfill_jobs.jsonl",
        [
            {"mint": "mint-preexisting", "status": "completed", "launch_time_from_replay": 900.0, "launch_signature_from_replay": "sig-create-pre"},
            {"mint": "mint-source-miss", "status": "completed", "launch_time_from_replay": 1200.0, "launch_signature_from_replay": "sig-create-miss"},
            {"mint": "mint-unresolved", "status": "failed", "failure_reason": "replay_birth_not_found"},
        ],
    )

    payload = build_lifecycle_outputs(tmp_path, tmp_path, write_outputs=True)
    summary = payload["summary"]
    rows = {row["mint"]: row for row in _jsonl(tmp_path / "lifecycle_ledger.jsonl")}
    audit = {row["mint"]: row for row in _jsonl(tmp_path / "migration_source_coverage_audit.jsonl")}

    assert summary["live_birth_linked_migration_count"] == 1
    assert summary["migration_only_preexisting_count"] == 1
    assert summary["true_birth_source_miss_count"] == 1
    assert summary["migration_only_replay_unresolved_count"] == 1
    assert summary["source_miss_count"] == 1
    assert rows["mint-preexisting"]["coverage_status"] == "migration_only_preexisting"
    assert rows["mint-preexisting"]["first_missing_link"] == "launch_before_campaign"
    assert rows["mint-source-miss"]["coverage_status"] == "migration_only_source_miss"
    assert rows["mint-source-miss"]["first_missing_link"] == "birth_source_miss"
    assert rows["mint-unresolved"]["coverage_status"] == "migration_only_replay_unresolved"
    assert rows["mint-unresolved"]["first_missing_link"] == "launch_replay_unresolved"
    assert audit["mint-source-miss"]["birth_source_missed_it"] is True
    assert (tmp_path / "migration_source_coverage_audit.csv").exists()


def test_pumpswap_program_subscribe_request_can_target_245_and_301_byte_pools() -> None:
    requests = [
        recorder_module._pumpswap_program_subscribe_request(
            "req-245",
            quote_mint=recorder_module.SOL_MINT,
            account_length=recorder_module.PUMPSWAP_MARKET_ACCOUNT_LENGTH,
        ),
        recorder_module._pumpswap_program_subscribe_request(
            "req-301",
            quote_mint=recorder_module.SOL_MINT,
            account_length=recorder_module.PUMPSWAP_MARKET_ACCOUNT_LENGTH_EXTENDED,
        ),
    ]

    sizes = [request["params"][1]["filters"][0]["dataSize"] for request in requests]

    assert sizes == [245, 301]


def test_campaign_contract_initializes_manifest_required_artifacts_and_placeholders(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    expected_artifacts = {
        "birth_audit.jsonl",
        "curve_observations.jsonl",
        "true_curve_threshold_crossings.jsonl",
        "curve_velocity_events.jsonl",
        "curve_acceleration_events.jsonl",
        "trade_flow_events.jsonl",
        "organic_flow_events.jsonl",
        "holder_distribution_snapshots.jsonl",
        "dev_behavior_events.jsonl",
        "global_migration_events.jsonl",
        "global_migration_event_duplicates.jsonl",
        "global_migration_candidates.jsonl",
        "post_migration_observations.jsonl",
        "execution_cost_observations.jsonl",
        "token_path_summary.jsonl",
        "valuation_formula_audit.jsonl",
        "wallet_dev_checkpoints.jsonl",
        "probe_attempts.jsonl",
        "live_status.json",
        "collector_summary.json",
        "campaign_manifest.json",
    }
    assert all((tmp_path / name).exists() for name in expected_artifacts)
    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text(encoding="utf-8"))
    required_manifest_fields = {
        "campaign_id",
        "run_id",
        "started_at",
        "requested_duration_seconds",
        "source_duration_seconds",
        "followup_drain_seconds",
        "sample_rate_percent",
        "max_active_tracking",
        "active_lifecycle_policy_version",
        "quote_normalization_version",
        "curve_progress_formula_version",
        "migration_detector_version",
        "valuation_ladder_policy",
        "valuation_ladder_enabled",
        "trading_enabled",
        "paper_trading_enabled",
        "mayhem_touched",
        "local_staging_root",
        "archive_root",
        "archive_status",
        "sol_usd",
        "quote_assets_supported",
        "source_lanes_enabled",
        "tests_checks_run_before_campaign",
    }
    assert required_manifest_fields <= set(manifest)
    assert manifest["valuation_ladder_policy"] == "market_cap_confirmed_only"
    assert manifest["valuation_ladder_enabled"] is False
    assert manifest["trading_enabled"] is False
    assert manifest["paper_trading_enabled"] is False
    assert manifest["mayhem_touched"] is False
    assert manifest["quote_assets_supported"] == ["SOL", "USDC"]
    assert _jsonl(tmp_path / "trade_flow_events.jsonl")[0]["trade_flow_status"] == "schema_ready_pending_live_source"
    assert _jsonl(tmp_path / "holder_distribution_snapshots.jsonl")[0]["holder_distribution_status"] == "schema_ready_pending_live_source"
    assert _jsonl(tmp_path / "dev_behavior_events.jsonl")[0]["dev_behavior_status"] == "schema_ready_pending_live_source"
    assert _jsonl(tmp_path / "post_migration_observations.jsonl")[0]["executable_quote_status"] == "schema_ready_pending_live_source"
    assert _jsonl(tmp_path / "execution_cost_observations.jsonl")[0]["execution_cost_status"] == "schema_ready_pending_live_source"


def test_atomic_json_writer_uses_unique_temp_paths_for_concurrent_status_writes(tmp_path: Path, monkeypatch) -> None:
    from research.mtp_research.collectors import bonding_curve_progress_recorder_v1 as recorder_module

    replace_sources: list[str] = []

    def fake_replace(src: object, dst: object) -> None:
        source = Path(src)
        replace_sources.append(source.name)
        source.unlink()

    monkeypatch.setattr(recorder_module.os, "replace", fake_replace)

    recorder_module._atomic_write_json(tmp_path / "live_status.json", {"writer": 1})
    recorder_module._atomic_write_json(tmp_path / "live_status.json", {"writer": 2})

    assert len(replace_sources) == 2
    assert len(set(replace_sources)) == 2
    assert all(name.startswith("live_status.json.") and name.endswith(".tmp") for name in replace_sources)


def test_t007_blocker_lanes_are_schema_ready_without_enabling_trading(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text(encoding="utf-8"))
    summary = recorder.build_summary()

    for lane in [
        "trade_flow",
        "organic_flow",
        "holder_distribution",
        "dev_behavior",
        "post_migration_depth",
        "execution_cost",
    ]:
        assert manifest["source_lanes_enabled"][lane] == "schema_ready"
    assert manifest["trading_enabled"] is False
    assert manifest["paper_trading_enabled"] is False
    assert manifest["mayhem_touched"] is False
    assert summary["remaining_t007_blockers_before_next_scan"] == []
    assert summary["remaining_t007_blockers_before_thesis_testing"] == [
        "live_feature_coverage_validation",
        "profitability_or_edge_claim_disallowed_until_forward_evidence",
    ]


def test_trade_flow_records_efficiency_breadth_and_organic_diagnostics(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-flow", received_at=1000.0))
    recorder.record_observation(_obs("mint-flow", 45.0, 1.0))

    first = recorder.record_trade_event(
        {
            "mint": "mint-flow",
            "side": "buy",
            "trader_wallet": "buyer-a",
            "fee_payer": "buyer-a",
            "token_amount": 100.0,
            "quote_amount": 1.5,
            "quote_asset": "SOL",
            "received_at": 1002.0,
            "decision_time": 1002.0,
            "signature": "sig-buy-a",
        }
    )
    second = recorder.record_trade_event(
        {
            "mint": "mint-flow",
            "side": "sell",
            "trader_wallet": "seller-a",
            "fee_payer": "seller-a",
            "token_amount": 25.0,
            "quote_amount": 0.25,
            "quote_asset": "SOL",
            "received_at": 1003.0,
            "decision_time": 1003.0,
            "signature": "sig-sell-a",
        }
    )

    trade_rows = [row for row in _jsonl(tmp_path / "trade_flow_events.jsonl") if row.get("mint") == "mint-flow"]
    organic_rows = [row for row in _jsonl(tmp_path / "organic_flow_events.jsonl") if row.get("mint") == "mint-flow"]
    summary = recorder.build_summary()
    assert first["trade_flow_status"] == "available"
    assert second["trade_count_since_launch"] == 2
    assert second["buy_count_since_launch"] == 1
    assert second["sell_count_since_launch"] == 1
    assert second["unique_buyers_since_launch"] == 1
    assert second["unique_sellers_since_launch"] == 1
    assert second["net_quote_inflow_since_launch"] == 1.25
    assert second["progress_per_trade"] == 22.5
    assert trade_rows[-1]["decision_time_safe"] is True
    assert organic_rows[-1]["organic_share_status"] == "partial"
    assert organic_rows[-1]["bot_like_trade_share"] == 0.0
    assert summary["trade_flow_events_written"] == 2
    assert summary["organic_flow_events_written"] == 2
    assert summary["buyer_breadth_available_count"] == 2


def test_first_pumpswap_swap_for_live_birth_emits_inferred_migration(tmp_path: Path) -> None:
    mint = "swapBornMint111111111111111111111111111111111pump"
    pool = "poolForFirstSwap111111111111111111111111111111111"
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch(mint, received_at=1000.0))

    counter: dict[str, object] = {}
    row = {
        "swap_direction": "buy",
        "mint": mint,
        "base_mint": mint,
        "pool": pool,
        "quote_mint": SOL_MINT,
        "base_amount": 1_000_000,
        "quote_amount": 100_000,
        "received_at": 1005.0,
        "signature": "first-swap-sig",
    }

    assert recorder_module._emit_pumpswap_balance_delta_partial_event(
        output_root=tmp_path,
        recorder=recorder,
        counter=counter,
        row=row,
        event={},
    ) == 1
    assert recorder_module._emit_pumpswap_balance_delta_partial_event(
        output_root=tmp_path,
        recorder=recorder,
        counter=counter,
        row=row,
        event={},
    ) == 1

    migrations = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert len(migrations) == 1
    assert migrations[0]["mint"] == mint
    assert migrations[0]["pool_or_pair_address"] == pool
    assert migrations[0]["detection_method"] == "pumpswap_first_swap_after_live_birth"
    assert migrations[0]["migration_evidence_level"] == "LEVEL_B"
    assert migrations[0]["migration_evidence_reason"] == "first_pumpswap_swap_after_live_birth"
    assert migrations[0]["confidence"] == "confirmed"
    assert migrations[0]["seen_in_birth_source"] is True
    assert migrations[0]["admitted"] is True
    assert migrations[0]["migration_received_at"] == 1005.0
    assert recorder.build_summary()["global_migration_events_deduped"] == 1
    recorder_module._merge_global_migration_dedupe_summary(
        recorder.summary_counters,
        {
            "global_migration_events_deduped": 0,
            "global_migration_unique_mints": 0,
            "global_migration_unique_pools": 0,
        },
    )
    assert recorder.build_summary()["global_migration_events_deduped"] == 1
    assert recorder.build_summary()["migration_level_b_count"] == 1
    assert recorder.build_summary()["evidence_records_written"] >= 1



def test_summary_reconciles_global_migration_counter_from_artifact(tmp_path: Path) -> None:
    mint = "artifactCounterMint11111111111111111111111111111pump"
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch(mint, received_at=1000.0))
    recorder_module._emit_pumpswap_balance_delta_partial_event(
        output_root=tmp_path,
        recorder=recorder,
        counter={},
        row={
            "swap_direction": "buy",
            "mint": mint,
            "base_mint": mint,
            "pool": "artifact-counter-pool",
            "quote_mint": SOL_MINT,
            "base_amount": 1_000_000,
            "quote_amount": 100_000,
            "received_at": 1005.0,
            "signature": "artifact-counter-sig",
        },
        event={},
    )

    recorder.summary_counters["global_migration_events_deduped"] = 0
    recorder.summary_counters["global_migration_unique_mints"] = 0
    recorder.summary_counters["global_migration_unique_pools"] = 0

    summary = recorder.build_summary(final=True)

    assert summary["global_migration_events_deduped"] == 1
    assert summary["global_migration_unique_mints"] == 1
    assert summary["global_migration_unique_pools"] == 1


def test_explicit_pumpswap_pool_create_emits_level_a_migration(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-level-a", received_at=1000.0))
    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)

    result = writer.record(
        {
            "mint": "mint-level-a",
            "base_mint": "mint-level-a",
            "pool_or_pair_address": "pool-level-a",
            "signature": "sig-level-a",
            "slot": 123,
            "received_at": 1001.0,
            "migration_received_at": 1001.0,
            "source_route": "pumpswap_pool_create",
            "detection_method": "pumpswap_pair_created_signal",
            "confidence": "confirmed",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
        }
    )

    events = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert result == "event"
    assert events[0]["migration_evidence_level"] == "LEVEL_A"
    assert events[0]["migration_evidence_reason"] == "explicit_pool_create_or_migrate"


def test_collector_writes_evidence_records_before_projected_artifacts(tmp_path: Path) -> None:
    mint = "evidenceMint111111111111111111111111111111111pump"
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch(mint, received_at=1000.0))
    recorder_module._emit_pumpswap_balance_delta_partial_event(
        output_root=tmp_path,
        recorder=recorder,
        counter={},
        row={
            "swap_direction": "buy",
            "mint": mint,
            "base_mint": mint,
            "pool": "evidence-pool",
            "quote_mint": SOL_MINT,
            "base_amount": 1_000_000,
            "quote_amount": 100_000,
            "received_at": 1005.0,
            "signature": "evidence-swap-sig",
        },
        event={},
    )

    evidence = _jsonl(tmp_path / "evidence_records.jsonl")
    assert any(row["signature"] == f"sig-{mint}" and row["source_lane"] == "pumpfun_birth" for row in evidence)
    assert any(row["signature"] == "evidence-swap-sig" and row["source_lane"] == "pumpswap_swap" for row in evidence)
    assert any(row["signature"] == "evidence-swap-sig" and row["source_lane"] == "global_migration" for row in evidence)
    assert recorder.build_summary()["evidence_records_written"] >= 3
    assert recorder.build_summary()["post_migration_snapshot_scheduled_count"] > 0


def _pumpswap_fixture_account_data(base_mint: str, quote_mint: str) -> bytes:
    data = bytearray(PUMPSWAP_MARKET_ACCOUNT_LENGTH)
    data[:8] = PUMPSWAP_MARKET_DISCRIMINATOR_BYTES
    data[8] = 1
    data[9:11] = (7).to_bytes(2, "little")
    data[43:75] = _base58_decode_string(base_mint)
    data[75:107] = _base58_decode_string(quote_mint)
    data[203:211] = (12345).to_bytes(8, "little")
    return bytes(data)


def test_pumpswap_pool_account_fixture_decodes_metadata_as_partial_depth_source() -> None:
    decoded = _decode_pumpswap_market_account_data(
        _pumpswap_fixture_account_data(SOL_MINT, USDC_MINT),
        account_pubkey="pool-fixture",
    )

    assert decoded["pool_or_pair_address"] == "pool-fixture"
    assert decoded["base_mint"] == SOL_MINT
    assert decoded["quote_mint"] == USDC_MINT
    assert decoded["data_size"] == PUMPSWAP_MARKET_ACCOUNT_LENGTH
    assert decoded["discriminator_valid"] is True


def test_post_migration_row_preserves_pool_account_metadata_and_partial_depth(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-pool-meta",
            "base_mint": "mint-pool-meta",
            "pool_or_pair_address": "pool-meta",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "partial",
            "pool_decode_route": "pumpswap_market_account_v1",
            "pool_decode_confidence": "metadata_only",
            "pool_account_owner": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
            "pool_account_size": PUMPSWAP_MARKET_ACCOUNT_LENGTH,
            "pool_discriminator": PUMPSWAP_MARKET_DISCRIMINATOR_BYTES.hex(),
            "pool_base_mint": "mint-pool-meta",
            "pool_quote_mint": SOL_MINT,
            "pool_state_slot": 123,
            "pool_state_observed_at": 1000.0,
        }
    )
    summary = recorder.build_summary()

    assert row["pool_decode_route"] == "pumpswap_market_account_v1"
    assert row["pool_decode_confidence"] == "metadata_only"
    assert row["pool_account_owner"] == PUMPSWAP_PROGRAM_ID_FOR_AUDIT
    assert row["pool_account_size"] == PUMPSWAP_MARKET_ACCOUNT_LENGTH
    assert row["pool_discriminator"] == PUMPSWAP_MARKET_DISCRIMINATOR_BYTES.hex()
    assert row["pool_base_mint"] == "mint-pool-meta"
    assert row["pool_quote_mint"] == SOL_MINT
    assert row["pool_state_status"] == "partial"
    assert row["depth_status"] == "partial"
    assert summary["post_migration_pool_state_partial_count"] == 1


def test_post_migration_liquidity_usd_normalizes_sol_usdc_and_skips_unknown(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    sol = recorder.record_post_migration_observation(
        {
            "mint": "mint-sol-liq",
            "pool_or_pair_address": "pool-sol",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 10.0,
        }
    )
    usdc = recorder.record_post_migration_observation(
        {
            "mint": "mint-usdc-liq",
            "pool_or_pair_address": "pool-usdc",
            "quote_asset": "USDC",
            "quote_mint": USDC_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 10.0,
        }
    )
    unknown = recorder.record_post_migration_observation(
        {
            "mint": "mint-unknown-liq",
            "pool_or_pair_address": "pool-unknown",
            "quote_asset": "UNKNOWN",
            "quote_mint": "unknown-mint",
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 10.0,
        }
    )
    summary = recorder.build_summary()

    assert sol["pool_liquidity_usd"] == 1350.0
    assert usdc["pool_liquidity_usd"] == 10.0
    assert unknown["pool_liquidity_usd"] is None
    assert summary["pool_liquidity_quote_present_count"] == 3
    assert summary["pool_liquidity_usd_present_count"] == 2


class _FeeProbe:
    def __init__(self, fees=None, error: Exception | None = None):
        self.fees = fees if fees is not None else [100, 200, 300, 400]
        self.error = error

    def fetch_recent_prioritization_fees(self, account_addresses=None):
        if self.error:
            raise self.error
        return [{"prioritizationFee": fee} for fee in self.fees]


def test_execution_cost_periodic_observation_computes_prioritization_fee_percentiles(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.execution_cost_probe = _FeeProbe([100, 200, 300, 400])

    row = recorder.record_execution_cost_sample("periodic", as_of=1200.0)
    summary = recorder.build_summary()

    assert row["observation_reason"] == "periodic"
    assert row["timestamp"] == 1200.0
    assert row["recent_prioritization_fee_p50"] == 250.0
    assert row["recent_prioritization_fee_p75"] == 325.0
    assert row["recent_prioritization_fee_p90"] == 370.0
    assert row["recent_prioritization_fee_p95"] == 385.0
    assert row["recent_prioritization_fee_max"] == 400
    assert row["recent_prioritization_fee_sample_count"] == 4
    assert row["execution_cost_status"] == "partial"
    assert row["execution_cost_source"] == "getRecentPrioritizationFees"
    assert row["failed_tx_share_status"] == "deferred"
    assert row["decision_time_safe"] is True
    assert summary["execution_cost_observations_written"] == 1
    assert summary["execution_cost_partial_count"] == 1
    assert summary["recent_prioritization_fee_sample_count"] == 4
    assert summary["failed_tx_share_deferred_count"] == 1


def test_migration_event_triggers_execution_cost_observation(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.execution_cost_probe = _FeeProbe([10, 20, 30])
    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)

    writer.record(
        {
            "mint": "mint-cost-migration",
            "pool_or_pair_address": "pool-cost-migration",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "source_route": "pumpswap_program_subscribe",
            "detection_method": "program_subscribe_pool_create",
            "confidence": "confirmed",
            "received_at": 2000.0,
        }
    )

    rows = [row for row in _jsonl(tmp_path / "execution_cost_observations.jsonl") if row.get("observation_reason") == "migration_event"]
    assert len(rows) == 1
    assert rows[0]["execution_cost_status"] == "partial"


def test_execution_cost_preserves_zero_fee_percentiles(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.execution_cost_probe = _FeeProbe([0, 0, 0, 0])

    row = recorder.record_execution_cost_sample("periodic", as_of=1250.0)

    assert row["recent_prioritization_fee_p50"] == 0.0
    assert row["recent_prioritization_fee_p90"] == 0.0
    assert row["recent_prioritization_fee_sample_count"] == 4


def test_execution_cost_rpc_error_writes_error_row(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.execution_cost_probe = _FeeProbe(error=RuntimeError("rpc down"))

    row = recorder.record_execution_cost_sample("periodic", as_of=1300.0)
    summary = recorder.build_summary()

    assert row["execution_cost_status"] == "error"
    assert row["execution_cost_source"] == "getRecentPrioritizationFees"
    assert row["error_reason"] == "rpc down"
    assert summary["execution_cost_error_count"] == 1


def test_global_migration_schedules_post_migration_observation_horizons(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)

    result = writer.record(
        {
            "mint": "mint-migration",
            "pool_or_pair_address": "pool-migration",
            "quote_asset": "SOL",
            "quote_mint": "So11111111111111111111111111111111111111112",
            "source_route": "pumpswap_program_subscribe",
            "detection_method": "program_subscribe_pool_create",
            "confidence": "confirmed",
            "received_at": 2000.0,
            "slot": 123,
        }
    )
    recorder.write_due_post_migration_observations(as_of=2000.0)

    rows = [row for row in _jsonl(tmp_path / "post_migration_observations.jsonl") if row.get("mint") == "mint-migration"]
    summary = recorder.build_summary()
    migration = _jsonl(tmp_path / "global_migration_events.jsonl")[0]

    assert result == "event"
    assert migration["migration_received_at"] == 2000.0
    assert summary["post_migration_observations_scheduled"] == len((0, 5, 15, 30, 60, 120, 300, 600))
    assert rows[0]["horizon_seconds_after_migration"] == 0
    assert rows[0]["observation_slot"] == 123
    assert rows[0]["decision_time_safe"] is True
    assert rows[0]["valuation_ladder_used"] is False
    assert rows[0]["executable_quote_status"] == "deferred"
    assert rows[0]["quote_source"] == "not_implemented"
    assert rows[0]["price_impact_pct"] is None


def test_late_migration_leaves_future_post_migration_horizons_pending(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.schedule_post_migration_observations(
        {
            "mint": "mint-late",
            "pool_or_pair_address": "pool-late",
            "quote_asset": "USDC",
            "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "migration_received_at": 5000.0,
            "source_route": "pumpswap_program_subscribe_usdc",
            "detection_method": "program_subscribe_pool_create",
            "confidence": "confirmed",
        },
        as_of=5030.0,
    )
    summary = recorder.finalize()
    rows = [row for row in _jsonl(tmp_path / "post_migration_observations.jsonl") if row.get("mint") == "mint-late"]

    assert [row["horizon_seconds_after_migration"] for row in rows] == [0, 5, 15, 30]
    assert summary["post_migration_observations_completed_by_horizon"] == {"0": 1, "5": 1, "15": 1, "30": 1}
    assert summary["post_migration_observations_pending_at_finalization"] == 4
    assert summary["post_migration_observations_by_quote_asset"] == {"USDC": 4}


def test_missing_pool_decode_writes_explicit_partial_or_error_status(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-no-pool",
            "quote_asset": "SOL",
            "migration_received_at": 6000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 6000.0,
            "executable_quote_status": "deferred",
            "quote_source": "not_implemented",
            "decision_time": 6000.0,
        }
    )
    summary = recorder.build_summary()

    assert row["pool_state_status"] == "error"
    assert row["depth_status"] == "error"
    assert row["error_reason"] == "missing_pool_or_pair_address"
    assert row["executable_quote_status"] == "deferred"
    assert row["valuation_ladder_used"] is False
    assert summary["post_migration_pool_state_error_count"] == 1
    assert summary["post_migration_quote_deferred_count"] == 1


def test_post_migration_fields_remain_outcome_diagnostic_not_entry_features(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-outcome",
            "pool_or_pair_address": "pool-outcome",
            "quote_asset": "SOL",
            "migration_received_at": 7000.0,
            "horizon_seconds_after_migration": 5,
            "observation_received_at": 7005.0,
            "decision_time": 7000.0,
        }
    )

    assert row["diagnostic_only"] is True
    assert row["trading_enabled"] is False
    assert row["paper_trading_enabled"] is False
    assert row["decision_time_safe"] is True
    assert row["valuation_ladder_used"] is False


def test_t007aa_report_summarizes_post_migration_depth_quote_availability(tmp_path: Path) -> None:
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-report",
                "unique_birth_mints": 1,
                "admitted_births": 1,
                "valuation_ladder_emission_policy": "market_cap_confirmed_only",
                "valuation_ladder_events_written": 0,
                "post_migration_observations_scheduled": 8,
                "post_migration_observations_written": 2,
                "post_migration_observations_completed_by_horizon": {"0": 1, "5": 1},
                "post_migration_observations_pending_at_finalization": 6,
                "post_migration_pool_state_partial_count": 2,
                "post_migration_quote_deferred_count": 2,
                "pool_liquidity_quote_present_count": 1,
                "pool_liquidity_usd_present_count": 1,
                "execution_cost_observations_written": 1,
                "execution_cost_partial_count": 1,
                "recent_prioritization_fee_sample_count": 4,
                "failed_tx_share_deferred_count": 1,
                "execution_cost_observations_by_reason": {"periodic": 1},
                "post_migration_observations_by_quote_asset": {"SOL": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "campaign_manifest.json").write_text(json.dumps({"campaign_id": "campaign-report"}), encoding="utf-8")
    (tmp_path / "global_migration_events.jsonl").write_text(
        json.dumps({"mint": "mint-report", "pool_or_pair_address": "pool-report", "quote_asset": "SOL"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "post_migration_observations.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "mint": "mint-report",
                        "horizon_seconds_after_migration": 0,
                        "quote_asset": "SOL",
                        "pool_state_status": "partial",
                        "depth_status": "partial",
                        "pool_liquidity_quote": 10.0,
                        "pool_liquidity_usd": 1350.0,
                        "executable_quote_status": "deferred",
                    }
                ),
                json.dumps(
                    {
                        "mint": "mint-report",
                        "horizon_seconds_after_migration": 5,
                        "quote_asset": "SOL",
                        "pool_state_status": "partial",
                        "depth_status": "partial",
                        "executable_quote_status": "deferred",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "execution_cost_observations.jsonl").write_text(
        json.dumps(
            {
                "observation_reason": "periodic",
                "execution_cost_status": "partial",
                "execution_cost_source": "getRecentPrioritizationFees",
                "recent_prioritization_fee_sample_count": 4,
                "failed_tx_share_status": "deferred",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    item = summarize_campaign(tmp_path)

    assert item["post_migration_observation_availability"]["observations_written"] == 2
    assert item["post_migration_observation_availability"]["migrations_without_post_migration_observations"] == 0
    assert item["post_migration_observation_availability"]["horizons_observed"] == [0, 5]
    assert item["post_migration_observation_availability"]["pool_state_status_counts"] == {"partial": 2}
    assert item["post_migration_observation_availability"]["quote_status_counts"] == {"deferred": 2}
    assert item["post_migration_observation_availability"]["pool_liquidity_quote_present_count"] == 1
    assert item["post_migration_observation_availability"]["pool_liquidity_usd_present_count"] == 1
    assert item["execution_cost_availability"]["observations_written"] == 1
    assert item["execution_cost_availability"]["status_counts"] == {"partial": 1}
    assert item["execution_cost_availability"]["recent_prioritization_fee_sample_count"] == 4
    assert item["execution_cost_availability"]["failed_tx_share_status_counts"] == {"deferred": 1}


def test_t007_post_migration_work_does_not_touch_mayhem_files(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.schedule_post_migration_observations(
        {
            "mint": "mint-no-mayhem",
            "pool_or_pair_address": "pool-no-mayhem",
            "quote_asset": "SOL",
            "migration_received_at": 8000.0,
            "source_route": "pumpswap_program_subscribe",
            "detection_method": "program_subscribe_pool_create",
            "confidence": "confirmed",
        },
        as_of=8000.0,
    )

    summary = recorder.build_summary()

    assert summary["mayhem_code_modified"] is False


def test_holder_dev_post_migration_and_execution_lanes_write_diagnostic_rows(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-rich", received_at=1000.0), "creator": "creator-rich"})

    holder = recorder.record_holder_snapshot(
        {
            "mint": "mint-rich",
            "checkpoint": "60pct",
            "holder_count": 42,
            "top_1_holder_pct": 11.5,
            "top_5_holder_pct": 31.0,
            "received_at": 1010.0,
            "decision_time": 1010.0,
        }
    )
    dev = recorder.record_dev_behavior_event(
        {
            "mint": "mint-rich",
            "creator_wallet": "creator-rich",
            "prior_launch_count": 7,
            "prior_migration_count": 2,
            "creator_sold_before_60": False,
            "creator_retained_balance_status": "available",
            "received_at": 1001.0,
            "decision_time": 1001.0,
        }
    )
    post = recorder.record_post_migration_observation(
        {
            "mint": "mint-rich",
            "pool_or_pair_address": "pool-rich",
            "quote_asset": "SOL",
            "checkpoint": "30s_after_migration",
            "real_liquidity_usd": 55_000,
            "price_impact_pct": 1.7,
            "executable_quote_status": "available",
            "post_migration_buy_volume": 10.0,
            "post_migration_sell_volume": 15.0,
            "sell_side_dump_status": "partial",
            "sell_side_dump_signal": True,
            "received_at": 1100.0,
            "decision_time": 1100.0,
        }
    )
    cost = recorder.record_execution_cost_observation(
        {
            "mint": "mint-rich",
            "priority_fee_p50_microlamports": 2000,
            "priority_fee_p90_microlamports": 5000,
            "failed_tx_share": 0.04,
            "execution_cost_status": "partial",
            "received_at": 1101.0,
            "decision_time": 1101.0,
        }
    )
    summary = recorder.finalize()
    path = _jsonl(tmp_path / "token_path_summary.jsonl")[0]

    assert holder["holder_distribution_status"] == "available"
    assert dev["dev_behavior_status"] == "available"
    assert post["post_migration_observation_status"] == "available"
    assert post["executable_quote_status"] == "available"
    assert post["sell_side_dump_status"] == "partial"
    assert post["sell_side_dump_signal"] is True
    assert cost["execution_cost_status"] == "partial"
    assert summary["holder_distribution_snapshots_written"] == 1
    assert summary["dev_behavior_events_written"] == 1
    assert summary["post_migration_observations_written"] == 1
    assert summary["sell_side_dump_diagnostics_written"] == 1
    assert summary["execution_cost_observations_written"] == 1
    assert path["holder_distribution_status"] == "available"
    assert path["dev_behavior_status"] == "available"
    assert path["post_migration_depth_status"] == "available"
    assert path["execution_cost_status"] == "partial"
    assert path["post_migration_observation_count"] == 1


def test_decision_time_safety_flags_future_feature_rows(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-future", received_at=1000.0))

    row = recorder.record_trade_event(
        {
            "mint": "mint-future",
            "side": "buy",
            "trader_wallet": "buyer-future",
            "quote_amount": 1.0,
            "quote_asset": "SOL",
            "received_at": 1010.0,
            "decision_time": 1005.0,
        }
    )
    summary = recorder.build_summary()

    assert row["decision_time_safe"] is False
    assert row["decision_time_safety_status"] == "violation_future_observation"
    assert summary["decision_time_safety_violation_count"] == 1


def test_deterministic_admission_sampling_is_stable() -> None:
    mint = "StableMint111111111111111111111111111111111111"

    first = deterministic_sample_admitted(mint, 55)
    second = deterministic_sample_admitted(mint, 55)

    assert first == second
    assert deterministic_sample_admitted(mint, 100) is True
    assert deterministic_sample_admitted(mint, 0) is False


def test_capacity_rejection_records_birth_audit(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1)
    )

    assert recorder.process_birth(_launch("mint-a"))["admitted"] is True
    rejected = recorder.process_birth(_launch("mint-b"))

    assert rejected["admitted"] is False
    assert rejected["admission_reason"] == "capacity_rejected_active_tracking_limit"
    summary = recorder.build_summary(final=True)
    assert summary["admitted_births"] == 1
    assert summary["capacity_rejected_births"] == 1
    audit = _jsonl(tmp_path / "birth_audit.jsonl")
    assert [row["admission_reason"] for row in audit] == ["sample_admitted", "capacity_rejected_active_tracking_limit"]


def test_first_threshold_crossing_is_not_overwritten_and_crossings_are_ordered(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-a"))

    recorder.record_observation(_obs("mint-a", 49.0, 1.0, observation_id="before"))
    recorder.record_observation(_obs("mint-a", 66.0, 2.0, observation_id="first"))
    recorder.record_observation(_obs("mint-a", 72.0, 3.0, observation_id="later"))

    crossings = _jsonl(tmp_path / "threshold_crossings.jsonl")
    true_curve_crossings = _jsonl(tmp_path / "true_curve_threshold_crossings.jsonl")
    thresholds = [row["threshold_pct"] for row in crossings if row["crossing_type"] == "true_curve_progress"]
    assert thresholds == [40.0, 50.0, 55.0, 60.0, 62.5, 65.0, 67.5, 70.0]
    assert [row["threshold_pct"] for row in true_curve_crossings] == thresholds
    first_60 = [row for row in crossings if row["crossing_type"] == "true_curve_progress" and row["threshold_pct"] == 60.0][0]
    assert first_60["source_observation_id"] == "first"
    assert first_60["progress_pct"] == 66.0
    assert first_60["progress_pct_status"] == "decoded_exact"


def test_curve_velocity_and_acceleration_use_only_past_observations(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-velocity"))

    recorder.record_observation(_obs("mint-velocity", 40.0, 1.0, observation_id="past"))
    recorder.record_observation(_obs("mint-velocity", 50.0, 6.0, observation_id="current"))

    velocity_rows = [row for row in _jsonl(tmp_path / "curve_velocity_events.jsonl") if row.get("mint") == "mint-velocity"]
    acceleration_rows = [row for row in _jsonl(tmp_path / "curve_acceleration_events.jsonl") if row.get("mint") == "mint-velocity"]
    available_5s = [row for row in velocity_rows if row.get("window_seconds") == 5 and row.get("feature_status") == "available"]
    assert available_5s[-1]["from_progress_pct"] == 40.0
    assert available_5s[-1]["to_progress_pct"] == 50.0
    assert available_5s[-1]["progress_delta"] == 10.0
    assert available_5s[-1]["progress_per_second"] == 2.0
    assert all(row["as_of_received_at"] <= 1006.0 for row in velocity_rows)
    assert all(row["as_of_received_at"] <= 1006.0 for row in acceleration_rows)


def test_migration_before_crossing_marks_crossing_not_actionable(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-a"))

    recorder.record_observation(_obs("mint-a", 45.0, 1.0, complete=True, observation_id="migration"))
    recorder.record_observation(_obs("mint-a", 65.0, 2.0, observation_id="late-crossing"))

    crossings = _jsonl(tmp_path / "threshold_crossings.jsonl")
    assert crossings
    assert all(row["migration_seen_before_crossing"] is True for row in crossings)
    migrations = _jsonl(tmp_path / "migration_events.jsonl")
    assert migrations[0]["last_progress_pct_before_completion"] == 45.0


def test_priority_escalates_with_progress_and_queue_overload_drops_low_priority(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, followup_queue_max_size=2)
    )
    recorder.process_birth(_launch("low-a"))
    recorder.process_birth(_launch("low-b"))
    recorder.process_birth(_launch("critical"))

    assert progress_priority_tier(35.0) == "low"
    assert progress_priority_tier(55.0) == "high"
    assert progress_priority_tier(70.0) == "very_high"
    assert progress_priority_tier(90.0) == "critical"

    assert recorder.enqueue_followup("low-a", 35.0)["queued"] is True
    assert recorder.enqueue_followup("low-b", 35.0)["queued"] is True
    decision = recorder.enqueue_followup("critical", 90.0)

    assert decision["queued"] is True
    assert decision["evicted_mint"] in {"low-a", "low-b"}
    assert recorder.summary_counters["queue_dropped_count"] == 1
    queued_mints = {item["mint"] for item in recorder.followup_queue}
    assert "critical" in queued_mints


def test_summary_includes_required_fields(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, followup_queue_max_size=4)
    )
    recorder.process_birth(_launch("mint-a"))
    recorder.record_observation(_obs("mint-a", 61.0, 1.0))
    recorder.record_observation(_obs("mint-a", 96.0, 20.0, complete=True))
    summary = recorder.finalize()

    required = {
        "run_id",
        "source_duration",
        "followup_drain_duration",
        "sample_rate",
        "total_births_detected",
        "admitted_births",
        "sample_rejected_births",
        "capacity_rejected_births",
        "active_tracking_max_count",
        "queue_max_size",
        "queue_high_water_mark",
        "queue_dropped_count",
        "observations_written",
        "threshold_crossings_written",
        "migrations_written",
        "decode_failures",
        "rpc_failures",
        "stale_observations",
        "birth_to_first_observation_latency_ms",
        "observation_interval_by_progress_tier",
        "tokens_with_60pct_plus_crossing",
        "tokens_with_70pct_plus_crossing",
        "tokens_with_migration",
        "stop_reasons",
    }
    assert required <= set(summary)
    assert summary["tokens_with_60pct_plus_crossing"] == 1
    assert summary["tokens_with_migration"] == 1
    assert (tmp_path / "collector_summary.json").exists()
    assert (tmp_path / "run_config.json").exists()


def test_broad_source_adapter_converts_fake_launch_events_into_recorder_births() -> None:
    source = FakeLaunchSource(
        [
            {
                "mint": "mint-a",
                "signature": "sig-a",
                "slot": 123,
                "block_time": 456,
                "observed_at": 1000.0,
                "source_adapter": "fake_broad_source",
                "bonding_curve": "curve-a",
                "creator": "creator-a",
                "metadata_json": {"compact": True},
            }
        ]
    )
    adapter = BroadPumpFunLaunchAdapter(source)

    launches = adapter.fetch_launches()

    assert launches == [
        {
            "mint": "mint-a",
            "signature": "sig-a",
            "slot": 123,
            "block_time": 456,
            "received_at": 1000.0,
            "source_type": "fake_broad_source",
            "bonding_curve_account": "curve-a",
            "associated_bonding_curve": None,
            "creator": "creator-a",
            "raw_decoded_launch_payload": {"compact": True},
        }
    ]


def test_broad_source_adapter_persists_associated_bonding_curve(tmp_path: Path) -> None:
    source = FakeLaunchSource(
        [
            {
                "mint": "mint-a",
                "signature": "sig-a",
                "observed_at": 1000.0,
                "source_adapter": "fake_broad_source",
                "bonding_curve": "curve-a",
                "associated_bonding_curve": "assoc-a",
                "creator": "creator-a",
            }
        ]
    )
    probe = FakeCurveStateProbe(
        {
            "mint-a": {
                "bonding_curve": "curve-a",
                "account_state": {"virtual_sol_reserves": 1},
                "observed_at": 1001.0,
            }
        }
    )

    run_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1000.0,
        sleep_fn=lambda _seconds: None,
    )

    birth = _jsonl(tmp_path / "birth_audit.jsonl")[0]
    observation = _jsonl(tmp_path / "curve_observations.jsonl")[0]
    assert birth["associated_bonding_curve"] == "assoc-a"
    assert observation["associated_bonding_curve"] == "assoc-a"


def test_birth_source_audit_counts_direct_wrapped_duplicate_and_rejected_routes(tmp_path: Path) -> None:
    route = FakeBirthSourceAuditRoute(
        [
            {
                "signature": "sig-direct",
                "slot": 1,
                "received_at": 1000.0,
                "logs": ["Program log: Instruction: CreateV2"],
                "mentioned_program_ids": ["pumpfun-program"],
                "direct_candidates": [
                    {
                        "mint": "mint-a",
                        "signature": "sig-direct",
                        "bonding_curve": "curve-a",
                        "associated_bonding_curve": "assoc-a",
                        "creator": "creator-a",
                    }
                ],
            },
            {
                "signature": "sig-inner",
                "slot": 2,
                "received_at": 1001.0,
                "logs": ["Program log: Instruction: Buy"],
                "mentioned_program_ids": ["pumpfun-program"],
                "wrapped_inner_candidates": [
                    {
                        "mint": "mint-b",
                        "signature": "sig-inner",
                        "bonding_curve": "curve-b",
                        "associated_bonding_curve": "assoc-b",
                        "creator": "creator-b",
                        "source_instruction_level": "inner",
                        "source_instruction_decode_route": "wrapped_compact_create",
                    }
                ],
            },
            {
                "signature": "sig-dup",
                "slot": 3,
                "received_at": 1002.0,
                "logs": ["Program log: Instruction: CreateV2"],
                "mentioned_program_ids": ["pumpfun-program"],
                "direct_candidates": [
                    {
                        "mint": "mint-a",
                        "signature": "sig-dup",
                        "bonding_curve": "curve-a2",
                        "associated_bonding_curve": "assoc-a2",
                    }
                ],
            },
            {
                "signature": "sig-reject",
                "slot": 4,
                "received_at": 1003.0,
                "logs": ["Program log: Instruction: CreateV2"],
                "mentioned_program_ids": ["pumpfun-program"],
                "direct_candidates": [{"signature": "sig-reject", "bonding_curve": "curve-missing-mint"}],
            },
        ]
    )

    summary = run_birth_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=route,
        now_fn=lambda: 1000.0,
    )

    assert summary["raw_websocket_notifications_received"] == 4
    assert summary["pumpfun_program_mentions"] == 4
    assert summary["candidate_transactions_inspected"] == 4
    assert summary["direct_create_candidates"] == 3
    assert summary["wrapped_inner_create_candidates"] == 1
    assert summary["decoded_births"] == 4
    assert summary["births_rejected_by_adapter"] == 1
    assert summary["duplicate_mints"] == 1
    assert summary["final_normalized_births"] == 2
    assert summary["unique_mints"] == 2
    rows = _jsonl(tmp_path / "raw_birth_source_audit.jsonl")
    assert rows[0]["associated_bonding_curve"] == "assoc-a"
    assert rows[1]["decode_route"] == "wrapped_compact_create"
    assert rows[-1]["reject_reason"] == "missing_mint"
    assert "transaction" not in rows[0]


def test_birth_source_audit_writes_source_comparison_table(tmp_path: Path) -> None:
    route = FakeBirthSourceAuditRoute(
        [
            {
                "signature": "sig-direct",
                "received_at": 1000.0,
                "logs": ["Program log: Instruction: CreateV2"],
                "mentioned_program_ids": ["pumpfun-program"],
                "direct_candidates": [{"mint": "mint-a", "signature": "sig-direct", "bonding_curve": "curve-a"}],
            }
        ]
    )

    summary = run_birth_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=route,
        now_fn=lambda: 1000.0,
    )

    source_names = {row["source_name"] for row in summary["source_route_comparison"]}
    assert "PumpFunCreateWebSocketCandidateSource" in source_names
    assert "HeliusTransactionSubscribeCreateSource" in source_names
    assert (tmp_path / "birth_source_audit_summary.json").exists()


def test_transaction_birth_source_audit_counts_direct_inner_wrapped_and_duplicates(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-direct",
                "slot": 10,
                "decoded_rows": [
                    {
                        "signature": "sig-direct",
                        "slot": 10,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "associated_bonding_curve": "assoc-a",
                        "creator": "creator-a",
                        "source_instruction_level": "top_level",
                        "instruction_type": "create_live_v3",
                        "parser_status": "decoded",
                    }
                ],
            },
            {
                "received_at": 1010.0,
                "signature": "sig-inner",
                "slot": 11,
                "decoded_rows": [
                    {
                        "signature": "sig-inner",
                        "slot": 11,
                        "mint": "mint-b",
                        "bonding_curve": "curve-b",
                        "associated_bonding_curve": "assoc-b",
                        "creator": "creator-b",
                        "source_instruction_level": "inner",
                        "instruction_type": "create_v2",
                        "parser_status": "decoded",
                    }
                ],
            },
            {
                "received_at": 1020.0,
                "signature": "sig-wrapped",
                "slot": 12,
                "decoded_rows": [
                    {
                        "signature": "sig-wrapped",
                        "slot": 12,
                        "mint": "mint-c",
                        "bonding_curve": "curve-c",
                        "associated_bonding_curve": "assoc-c",
                        "creator": "creator-c",
                        "source_instruction_level": "inner",
                        "source_instruction_decode_route": "mayhem_wrapped_compact_create",
                        "instruction_type": "create_v2",
                        "parser_status": "decoded",
                    }
                ],
            },
            {
                "received_at": 1030.0,
                "signature": "sig-dup",
                "slot": 13,
                "decoded_rows": [
                    {
                        "signature": "sig-dup",
                        "slot": 13,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a2",
                        "associated_bonding_curve": "assoc-a2",
                        "source_instruction_level": "top_level",
                        "instruction_type": "create_live_v4",
                        "parser_status": "decoded",
                    }
                ],
            },
        ],
        websocket_closed_early=True,
        websocket_close_reason="fake_close",
        actual_duration_seconds=40.0,
    )

    summary = run_transaction_birth_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=300),
        source=source,
        now_fn=lambda: 1000.0,
    )

    assert summary["requested_duration_seconds"] == 300
    assert summary["actual_duration_seconds"] == 40.0
    assert summary["websocket_closed_early"] is True
    assert summary["websocket_close_reason"] == "fake_close"
    assert summary["raw_transaction_notifications"] == 4
    assert summary["pumpfun_mentions"] == 4
    assert summary["create_like_candidates"] == 4
    assert summary["direct_creates_decoded"] == 2
    assert summary["inner_creates_decoded"] == 1
    assert summary["wrapped_compact_creates_decoded"] == 1
    assert summary["total_decoded_births"] == 4
    assert summary["unique_decoded_birth_mints"] == 3
    assert summary["duplicate_mints"] == 1
    assert summary["bonding_curve_account_present_count"] == 4
    assert summary["associated_bonding_curve_present_count"] == 4
    assert summary["creator_dev_present_count"] == 3
    assert summary["rejects_by_reason"] == {"duplicate_mint": 1}
    rows = _jsonl(tmp_path / "transaction_raw_birth_source_audit.jsonl")
    assert [row["decoded_route"] for row in rows] == ["direct", "inner", "wrapped_compact", "direct"]
    assert rows[0]["associated_bonding_curve"] == "assoc-a"
    assert rows[-1]["reject_reason"] == "duplicate_mint"


def test_transaction_birth_source_audit_records_reject_reasons_and_empty_decodes(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-empty",
                "slot": 20,
                "decoded_rows": [],
            },
            {
                "received_at": 1010.0,
                "signature": "sig-missing-mint",
                "slot": 21,
                "decoded_rows": [
                    {
                        "signature": "sig-missing-mint",
                        "slot": 21,
                        "bonding_curve": "curve-missing",
                        "source_instruction_level": "top_level",
                        "parser_status": "decode_failed",
                        "parser_error": "missing_mint_account",
                    }
                ],
            },
        ],
        actual_duration_seconds=20.0,
    )

    summary = run_transaction_birth_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=300),
        source=source,
        now_fn=lambda: 1000.0,
    )

    assert summary["raw_transaction_notifications"] == 2
    assert summary["total_decoded_births"] == 1
    assert summary["unique_decoded_birth_mints"] == 0
    assert summary["rejects_by_reason"] == {"decoder_no_create_candidate": 1, "missing_mint": 1}
    rows = _jsonl(tmp_path / "transaction_raw_birth_source_audit.jsonl")
    assert rows[0]["decode_attempted"] is False
    assert rows[0]["reject_reason"] == "decoder_no_create_candidate"
    assert rows[1]["decode_attempted"] is True
    assert rows[1]["reject_reason"] == "missing_mint"


def test_transaction_normalized_birth_source_dedupes_and_retains_first_seen_row() -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1005.0,
                "signature": "sig-late",
                "slot": 20,
                "decoded_rows": [
                    {
                        "signature": "sig-late",
                        "slot": 20,
                        "mint": "mint-a",
                        "bonding_curve": "curve-late",
                        "source_instruction_level": "inner",
                        "source_instruction_decode_route": "mayhem_wrapped_compact_create",
                        "creator": "creator-late",
                    }
                ],
            },
            {
                "received_at": 1000.0,
                "signature": "sig-first",
                "slot": 10,
                "decoded_rows": [
                    {
                        "signature": "sig-first",
                        "slot": 10,
                        "mint": "mint-a",
                        "bonding_curve": "curve-first",
                        "associated_bonding_curve": None,
                        "source_instruction_level": "top_level",
                        "creator": "creator-first",
                    }
                ],
            },
            {
                "received_at": 1001.0,
                "signature": "sig-b",
                "slot": 11,
                "decoded_rows": [
                    {
                        "signature": "sig-b",
                        "slot": 11,
                        "mint": "mint-b",
                        "bonding_curve": "curve-b",
                        "associated_bonding_curve": "assoc-b",
                        "source_instruction_level": "inner",
                        "creator": "creator-b",
                    }
                ],
            },
        ],
        actual_duration_seconds=30.0,
    )

    normalized_source = TransactionSubscribeNormalizedBirthSource(source)
    normalized = normalized_source.fetch_launches(300)

    assert [row["mint"] for row in normalized] == ["mint-a", "mint-b"]
    assert normalized[0]["signature"] == "sig-first"
    assert normalized[0]["slot"] == 10
    assert normalized[0]["bonding_curve_account"] == "curve-first"
    metrics = normalized_source.metrics
    assert metrics["decoded_birth_rows"] == 3
    assert metrics["unique_birth_mints"] == 2
    assert metrics["duplicate_mint_rows"] == 1
    assert metrics["duplicate_rows_by_route"] == {"wrapped_compact": 1}
    assert metrics["first_seen_route_counts"] == {"direct": 1, "inner": 1}
    assert metrics["duplicate_rows_with_same_mint_but_different_route"] == 1
    assert metrics["duplicate_rows_with_same_mint_but_different_signature"] == 1
    assert metrics["associated_bonding_curve_present_count"] == 1
    assert metrics["associated_bonding_curve_missing_count"] == 1


def test_transaction_normalized_stream_skips_full_normalization_for_duplicate_birth_rows(monkeypatch) -> None:
    duplicate_rows = [
        {
            "signature": f"sig-dup-{index}",
            "slot": 10 + index,
            "mint": "mint-a",
            "bonding_curve": "curve-a",
            "source_instruction_level": "inner",
            "creator": "creator-a",
        }
        for index in range(25)
    ]
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-first",
                "slot": 10,
                "decoded_rows": [
                    {
                        "signature": "sig-first",
                        "slot": 10,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "source_instruction_level": "top_level",
                        "creator": "creator-a",
                    }
                ],
            },
            {
                "received_at": 1001.0,
                "signature": "sig-duplicates",
                "slot": 11,
                "decoded_rows": duplicate_rows,
            },
            {
                "received_at": 1002.0,
                "signature": "sig-new",
                "slot": 12,
                "decoded_rows": [
                    {
                        "signature": "sig-new",
                        "slot": 12,
                        "mint": "mint-b",
                        "bonding_curve": "curve-b",
                        "source_instruction_level": "top_level",
                        "creator": "creator-b",
                    }
                ],
            },
        ],
        actual_duration_seconds=3.0,
    )
    original_normalizer = recorder_module._launch_from_transaction_decoded_row
    normalized_mints: list[str] = []

    def counting_normalizer(row: dict, event: dict) -> dict:
        normalized_mints.append(str(row.get("mint")))
        return original_normalizer(row, event)

    monkeypatch.setattr(recorder_module, "_launch_from_transaction_decoded_row", counting_normalizer)
    normalized_source = TransactionSubscribeNormalizedBirthSource(source)
    launches: list[dict] = []

    normalized_source.stream_launches(3.0, launches.append)

    assert [row["mint"] for row in launches] == ["mint-a", "mint-b"]
    assert normalized_mints == ["mint-a", "mint-b"]
    assert normalized_source.metrics["duplicate_mint_rows"] == 25


def test_transaction_normalized_stream_prioritizes_token_mint_birth_identity() -> None:
    class TradeNoiseThenTokenMintBirthSource:
        source_name = "token_mint_priority_fake_txsub"
        actual_duration_seconds = 1.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            for index in range(25):
                on_event({"signature": f"sig-trade-{index}", "trade_rows": [{"mint": f"mint-trade-{index}"}]})
            on_event(
                {
                    "received_at": 1000.0,
                    "signature": "sig-token-mint-birth",
                    "slot": 12,
                    "decoded_rows": [
                        {
                            "signature": "sig-token-mint-birth",
                            "slot": 12,
                            "token_mint": "mint-token-field",
                            "bonding_curve": "curve-token-field",
                            "source_instruction_level": "top_level",
                            "creator": "creator-token-field",
                        }
                    ],
                }
            )

    normalized_source = TransactionSubscribeNormalizedBirthSource(TradeNoiseThenTokenMintBirthSource())
    handled: list[str] = []

    def on_launch(launch: dict) -> None:
        handled.append(str(launch.get("mint")))

    normalized_source.stream_launches(1.0, on_launch)

    assert handled == ["mint-token-field"]
    assert normalized_source.metrics["unique_birth_mints"] == 1
    assert normalized_source.metrics["trade_rows_skipped_unknown_mint"] == 25


def test_transaction_normalized_stream_does_not_inline_drain_trade_rows_before_later_birth() -> None:
    class DelayedBirthAfterTradeSource:
        source_name = "delayed_birth_after_trade_fake_txsub"
        actual_duration_seconds = 0.1
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            on_event(
                {
                    "received_at": 1000.0,
                    "signature": "sig-a",
                    "slot": 10,
                    "decoded_rows": [
                        {
                            "signature": "sig-a",
                            "slot": 10,
                            "mint": "mint-a",
                            "bonding_curve": "curve-a",
                            "source_instruction_level": "top_level",
                            "creator": "creator-a",
                        }
                    ],
                }
            )
            on_event({"received_at": 1000.01, "signature": "sig-trade-a", "trade_rows": [{"mint": "mint-a", "signature": "sig-trade-a"}]})
            time.sleep(0.05)
            on_event(
                {
                    "received_at": 1000.02,
                    "signature": "sig-b",
                    "slot": 11,
                    "decoded_rows": [
                        {
                            "signature": "sig-b",
                            "slot": 11,
                            "mint": "mint-b",
                            "bonding_curve": "curve-b",
                            "source_instruction_level": "top_level",
                            "creator": "creator-b",
                        }
                    ],
                }
            )

    normalized_source = TransactionSubscribeNormalizedBirthSource(DelayedBirthAfterTradeSource())
    handled: list[str] = []

    def on_launch(launch: dict) -> None:
        handled.append(f"launch:{launch['mint']}")

    def on_trade(trade: dict) -> None:
        handled.append(f"trade:{trade['mint']}")

    normalized_source.stream_launches(1.0, on_launch, on_trade=on_trade)

    assert handled[:2] == ["launch:mint-a", "launch:mint-b"]
    assert handled[-1] == "trade:mint-a"


def test_transaction_live_smoke_samples_after_dedupe_and_does_not_probe_duplicates(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-a",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-a",
                        "slot": 1,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "associated_bonding_curve": None,
                        "source_instruction_level": "top_level",
                        "creator": "creator-a",
                    },
                    {
                        "signature": "sig-a-dup",
                        "slot": 2,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a-dup",
                        "source_instruction_level": "inner",
                        "source_instruction_decode_route": "mayhem_wrapped_compact_create",
                    },
                ],
            },
            {
                "received_at": 1001.0,
                "signature": "sig-b",
                "slot": 3,
                "decoded_rows": [
                    {
                        "signature": "sig-b",
                        "slot": 3,
                        "mint": "mint-b",
                        "bonding_curve": "curve-b",
                        "associated_bonding_curve": "assoc-b",
                        "source_instruction_level": "inner",
                        "creator": "creator-b",
                    }
                ],
            },
        ],
        actual_duration_seconds=10.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}, "observed_at": 1002.0},
            "mint-b": {"bonding_curve": "curve-b", "account_state": {"virtual_sol_reserves": 2}, "observed_at": 1003.0},
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1004.0,
    )

    assert summary["source_route"] == "transaction_subscribe"
    assert summary["decoded_birth_rows"] == 3
    assert summary["unique_birth_mints"] == 2
    assert summary["duplicate_mint_rows"] == 1
    assert summary["births_admitted_after_dedupe"] == 2
    assert summary["sample_rejected_after_dedupe"] == 0
    assert summary["curve_observation_attempts"] == 2
    assert [call["mint"] for call in probe.calls] == ["mint-a", "mint-b"]
    births = _jsonl(tmp_path / "birth_audit.jsonl")
    assert len(births) == 2
    assert births[0]["launch_signature"] == "sig-a"
    assert births[0]["associated_bonding_curve"] is None


def test_transaction_live_smoke_applies_probe_results_before_source_window_ends(tmp_path: Path) -> None:
    class WaitingSource:
        source_name = "waiting_for_probe_result_source"
        actual_duration_seconds = 0.2
        websocket_closed_early = False
        websocket_close_reason = None
        observed_curve_during_source = False

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            on_event(
                {
                    "received_at": time.time(),
                    "signature": "sig-continuous-probe",
                    "slot": 22,
                    "decoded_rows": [
                        {
                            "signature": "sig-continuous-probe",
                            "slot": 22,
                            "mint": "mint-continuous-probe",
                            "bonding_curve": "curve-continuous-probe",
                            "source_instruction_level": "top_level",
                            "creator": "creator-continuous-probe",
                        }
                    ],
                }
            )
            deadline = time.time() + 0.25
            observations_path = tmp_path / "curve_observations.jsonl"
            while time.time() < deadline:
                if observations_path.exists() and "mint-continuous-probe" in observations_path.read_text(encoding="utf-8"):
                    self.observed_curve_during_source = True
                    return
                time.sleep(0.01)

    source = WaitingSource()
    probe = FakeCurveStateProbe(
        {
            "mint-continuous-probe": {
                "bonding_curve": "curve-continuous-probe",
                "account_state": {
                    "real_token_reserves": 790_000_000,
                    "token_decimals": 0,
                    "virtual_sol_reserves": 2,
                },
                "observed_at": time.time(),
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            source_duration_seconds=1.0,
            sample_rate_percent=100,
            helius_max_estimated_credits=10_000,
        ),
        source=TransactionSubscribeNormalizedBirthSource(source),
        curve_probe=probe,
    )

    assert source.observed_curve_during_source is True
    assert summary["progress_decoded_candidate_count"] == 1


def test_transaction_live_smoke_thin_probes_capacity_rejected_verified_births(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-a",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-a",
                        "slot": 1,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "source_instruction_level": "top_level",
                    }
                ],
            },
            {
                "received_at": 1001.0,
                "signature": "sig-b",
                "slot": 2,
                "decoded_rows": [
                    {
                        "signature": "sig-b",
                        "slot": 2,
                        "mint": "mint-b",
                        "bonding_curve": "curve-b",
                        "source_instruction_level": "top_level",
                    }
                ],
            },
        ],
        actual_duration_seconds=10.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}, "observed_at": 1002.0},
            "mint-b": {"bonding_curve": "curve-b", "account_state": {"virtual_sol_reserves": 2}, "observed_at": 1003.0},
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1004.0,
    )

    births = _jsonl(tmp_path / "birth_audit.jsonl")
    assert births[0]["admission_reason"] == "sample_admitted"
    assert str(births[1]["admission_reason"]).startswith("capacity_rejected_active_tracking_limit")
    assert births[1]["thin_probe_scheduled"] is True
    assert births[1]["admitted"] is False
    assert summary["births_admitted_after_dedupe"] == 1
    assert summary["capacity_rejected_after_dedupe"] == 1
    assert summary["thin_probe_async_dispatch_enabled"] is True
    assert summary["thin_probe_worker_count"] == 1
    assert summary["thin_probe_worker_error_count"] == 0
    assert summary["thin_probe_execution_queue_dropped_count"] == 0
    assert summary["thin_probe_execution_queue_high_water_mark"] == 1
    assert summary["curve_observation_attempts"] == 2
    assert [call["mint"] for call in probe.calls] == ["mint-a", "mint-b"]
    probe_attempts = _jsonl(tmp_path / "probe_attempts.jsonl")
    actual_probe_attempts = [row for row in probe_attempts if row.get("actual_probe_executed") is True]
    attempts_by_mint = {row["mint"]: row for row in actual_probe_attempts}
    assert set(attempts_by_mint) == {"mint-a", "mint-b"}
    assert attempts_by_mint["mint-b"]["probe_scope"] in {"thin_initial_probe", "deep_initial_probe"}
    assert attempts_by_mint["mint-b"]["account_found"] is True


def test_running_live_status_writes_are_throttled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[dict] = []

    def fake_atomic_write(path: Path, payload: dict) -> None:
        if Path(path).name == "live_status.json":
            writes.append(dict(payload))

    monkeypatch.setattr(recorder_module, "_atomic_write_json", fake_atomic_write)
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path))

    writes.clear()
    recorder._write_live_status("running")
    recorder._write_live_status("running")

    running_writes = [row for row in writes if row.get("run_status") == "running"]
    assert len(running_writes) == 1
    assert recorder.summary_counters["live_status_throttled_write_skip_count"] == 1


def test_transaction_live_smoke_bounds_global_migration_thread_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_global_migration_lane(*args, **kwargs) -> dict:
        started.set()
        release.wait(timeout=5.0)
        return {"global_migration_events_deduped": 0}

    monkeypatch.setattr(recorder_module, "run_global_pumpswap_migration_lane", slow_global_migration_lane)

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            source_duration_seconds=0.01,
            followup_drain_seconds=0,
            sample_rate_percent=100,
            enable_global_pumpswap_migration=True,
            global_migration_thread_join_timeout_seconds=0.01,
        ),
        source=FakeTransactionSubscribeAuditRoute([], actual_duration_seconds=0.01),
        curve_probe=FakeCurveStateProbe({}),
        now_fn=lambda: 1004.0,
    )
    release.set()

    assert started.is_set()
    assert summary["global_migration_thread_timed_out"] is True
    assert summary["global_migration_thread_join_timeout_seconds"] == 0.01
    assert summary["global_migration_errors"] == ["global_migration_thread_join_timeout"]


def test_t0118_transaction_live_smoke_drains_migration_side_effects_while_source_is_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mint = "mint-live-drain"
    migration_emitted = threading.Event()

    class SourceStaysOpenUntilLiveSideEffect:
        source_name = "source_stays_open_until_live_side_effect"
        actual_duration_seconds = 10.0
        side_effect_seen_while_open = False

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True, "read_only": True}

        def stream_notifications(self, _duration_seconds: float, on_event) -> None:
            on_event(
                {
                    "received_at": 1000.0,
                    "signature": "sig-birth-live-drain",
                    "slot": 10,
                    "decoded_rows": [
                        {
                            "signature": "sig-birth-live-drain",
                            "slot": 10,
                            "mint": mint,
                            "bonding_curve": "curve-live-drain",
                            "source_instruction_level": "top_level",
                        }
                    ],
                }
            )
            assert migration_emitted.wait(timeout=2.0)
            on_event(
                {
                    "received_at": 1001.0,
                    "signature": "sig-trade-live-drain",
                    "slot": 11,
                    "trade_rows": [
                        {
                            "signature": "sig-trade-live-drain",
                            "slot": 11,
                            "mint": mint,
                            "received_at": 1001.0,
                            "trade_direction": "buy",
                            "trader_wallet": "wallet-live-drain",
                        }
                    ],
                }
            )
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                rows = _jsonl(tmp_path / "post_migration_observations.jsonl")
                if any(row.get("mint") == mint and row.get("event_type") != "schema_marker" for row in rows):
                    self.side_effect_seen_while_open = True
                    break
                time.sleep(0.02)

    source = SourceStaysOpenUntilLiveSideEffect()

    def fake_global_migration_lane(config, recorder, **_kwargs) -> dict:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if any(row.get("mint") == mint for row in _jsonl(tmp_path / "birth_audit.jsonl")):
                break
            time.sleep(0.02)
        writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)
        writer.record(
            {
                "mint": mint,
                "signature": "sig-migration-live-drain",
                "slot": 12,
                "received_at": 1001.5,
                "migration_received_at": 1001.5,
                "pool_or_pair_address": "pool-live-drain",
                "quote_mint": SOL_MINT,
                "quote_asset": "SOL",
                "confidence": "confirmed",
                "detection_method": "pumpswap_pair_created_signal",
            }
        )
        migration_emitted.set()
        return {
            "global_migration_events_deduped": 1,
            "global_migration_unique_mints": 1,
            "global_migration_unique_pools": 1,
        }

    monkeypatch.setattr(recorder_module, "run_global_pumpswap_migration_lane", fake_global_migration_lane)

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            source_duration_seconds=10,
            sample_rate_percent=100,
            enable_global_pumpswap_migration=True,
            followup_drain_seconds=0,
        ),
        source=source,
        curve_probe=FakeCurveStateProbe(
            {
                mint: {
                    "bonding_curve": "curve-live-drain",
                    "account_state": {"virtual_sol_reserves": 2, "virtual_token_reserves": 1},
                    "observed_at": 1000.1,
                }
            }
        ),
        now_fn=lambda: 1002.0,
    )

    assert source.side_effect_seen_while_open is True
    assert summary["live_migration_side_effect_drain_count"] >= 1
    assert summary["live_migration_side_effects_applied"] >= 1
    assert summary["live_migration_side_effects_failed"] == 0
    assert not any("global_migration_side_effects_must_run_on_recorder_owner_thread" in str(error) for error in summary["global_migration_errors"])
    assert summary["post_migration_observations_written"] > 0
    intent_rows = _jsonl(tmp_path / "global_migration_write_intents.jsonl")
    assert any(row["write_status"] == "retry_pending" for row in intent_rows)
    assert any(row["write_status"] == "written" for row in intent_rows)


def test_transaction_live_smoke_keeps_artifact_true_global_migration_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_global_migration_lane(config, recorder, **_kwargs) -> dict:
        writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)
        for index in range(2):
            writer.record(
                {
                    "mint": f"mint-summary-floor-{index}",
                    "signature": f"sig-summary-floor-{index}",
                    "slot": 120 + index,
                    "received_at": 1000.0 + index,
                    "migration_received_at": 1000.0 + index,
                    "pool_or_pair_address": f"pool-summary-floor-{index}",
                    "quote_mint": SOL_MINT,
                    "quote_asset": "SOL",
                    "confidence": "confirmed",
                    "detection_method": "pumpswap_pair_created_signal",
                }
            )
        return {
            "global_migration_events_deduped": 1,
            "global_migration_unique_mints": 1,
            "global_migration_unique_pools": 1,
        }

    monkeypatch.setattr(recorder_module, "run_global_pumpswap_migration_lane", fake_global_migration_lane)

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            source_duration_seconds=0.01,
            sample_rate_percent=100,
            enable_global_pumpswap_migration=True,
            followup_drain_seconds=0,
        ),
        source=FakeTransactionSubscribeAuditRoute([], actual_duration_seconds=0.01),
        curve_probe=FakeCurveStateProbe({}),
        now_fn=lambda: 1003.0,
    )

    rows = _jsonl(tmp_path / "global_migration_events.jsonl")
    persisted = json.loads((tmp_path / "collector_summary.json").read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert summary["global_migration_events_deduped"] == 2
    assert summary["global_migration_unique_mints"] == 2
    assert summary["global_migration_unique_pools"] == 2
    assert persisted["global_migration_events_deduped"] == 2
    assert persisted["global_migration_unique_mints"] == 2
    assert persisted["global_migration_unique_pools"] == 2


def test_cli_live_smoke_dispatches_to_transaction_streaming_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[BondingCurveRecorderConfig] = []

    def fake_transaction_live_smoke(config: BondingCurveRecorderConfig) -> dict:
        calls.append(config)
        return {
            "run_id": config.run_id,
            "archive_status": "not_requested",
            "live_source_used": "transaction_subscribe",
            "subscription_connect_status": "available",
        }

    def legacy_live_smoke_should_not_run(config: BondingCurveRecorderConfig) -> dict:
        raise AssertionError("legacy live-smoke path should not run")

    monkeypatch.setattr(recorder_module, "run_transaction_live_smoke", fake_transaction_live_smoke)
    monkeypatch.setattr(recorder_module, "run_live_smoke", legacy_live_smoke_should_not_run)

    result = recorder_module.main(
        [
            "--mode",
            "live-smoke",
            "--duration-seconds",
            "1",
            "--followup-drain-seconds",
            "0",
            "--birth-priority-worker-count",
            "3",
            "--birth-priority-queue-max-size",
            "123",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0].source_duration_seconds == 1
    assert calls[0].enable_global_pumpswap_migration is True
    assert calls[0].birth_priority_worker_count == 3
    assert calls[0].birth_priority_queue_max_size == 123


def test_cli_global_pumpswap_migration_can_be_explicitly_disabled_for_debug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[BondingCurveRecorderConfig] = []

    def fake_transaction_live_smoke(config: BondingCurveRecorderConfig) -> dict:
        calls.append(config)
        return {
            "run_id": config.run_id,
            "archive_status": "not_requested",
            "live_source_used": "transaction_subscribe",
            "subscription_connect_status": "available",
        }

    monkeypatch.setattr(recorder_module, "run_transaction_live_smoke", fake_transaction_live_smoke)

    result = recorder_module.main(
        [
            "--mode",
            "transaction-live-smoke",
            "--duration-seconds",
            "1",
            "--followup-drain-seconds",
            "0",
            "--output-root",
            str(tmp_path),
            "--enable-global-pumpswap-migration",
            "false",
        ]
    )

    assert result == 0
    assert len(calls) == 1
    assert calls[0].enable_global_pumpswap_migration is False


def test_transaction_live_smoke_records_sample_rejections_and_capacity_after_dedupe(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0 + index,
                "signature": f"sig-{index}",
                "slot": index,
                "decoded_rows": [
                    {
                        "signature": f"sig-{index}",
                        "slot": index,
                        "mint": f"mint-{index}",
                        "bonding_curve": f"curve-{index}",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
            for index in range(3)
        ],
        actual_duration_seconds=10.0,
    )
    probe = FakeCurveStateProbe(
        {f"mint-{index}": {"bonding_curve": f"curve-{index}", "account_state": {}, "observed_at": 1010.0} for index in range(3)}
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1010.0,
    )

    assert summary["unique_birth_mints"] == 3
    assert summary["births_admitted_after_dedupe"] == 1
    assert summary["capacity_rejected_after_dedupe"] == 2
    assert summary["curve_observation_attempts"] == 3
    assert [call["mint"] for call in probe.calls] == ["mint-0", "mint-1", "mint-2"]


def test_transaction_live_smoke_streams_probe_without_source_duration_delay(tmp_path: Path) -> None:
    clock = {"now": 1000.0}

    class StreamingSource:
        source_name = "streaming_fake_txsub"
        actual_duration_seconds = 300.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def iter_notifications(self, duration_seconds: float) -> list[dict]:
            clock["now"] = 1300.0
            return [self._event()]

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            clock["now"] = 1000.05
            on_event(self._event())
            clock["now"] = 1300.0

        def _event(self) -> dict:
            return {
                "received_at": 1000.0,
                "signature": "sig-a",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-a",
                        "slot": 1,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "source_instruction_level": "top_level",
                        "creator": "creator-a",
                    }
                ],
            }

    probe = FakeCurveStateProbe({"mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}}})

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=StreamingSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    assert summary["curve_observation_attempts"] == 1
    assert summary["source_reader_threaded"] is True
    assert summary["source_event_queue_dropped_count"] == 0
    assert summary["source_reader_error_count"] == 0


def test_transaction_live_smoke_source_reader_is_decoupled_from_slow_probe(tmp_path: Path) -> None:
    clock = {"now": 1000.0}
    callback_durations_ms: list[float] = []

    class FastReaderSource:
        source_name = "fast_reader_fake_txsub"
        actual_duration_seconds = 1.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            for index in range(2):
                event = {
                    "received_at": 1000.0 + index,
                    "signature": f"sig-fast-{index}",
                    "slot": index,
                    "decoded_rows": [
                        {
                            "signature": f"sig-fast-{index}",
                            "slot": index,
                            "mint": f"mint-fast-{index}",
                            "bonding_curve": f"curve-fast-{index}",
                            "source_instruction_level": "top_level",
                        }
                    ],
                }
                started = time.perf_counter()
                on_event(event)
                callback_durations_ms.append((time.perf_counter() - started) * 1000.0)
            clock["now"] = 1001.0

    class SlowProbe(FakeCurveStateProbe):
        def probe_create_event(self, create_event: dict, *, now_fn=time.time) -> dict:
            time.sleep(0.08)
            return super().probe_create_event(create_event, now_fn=now_fn)

    probe = SlowProbe(
        {
            "mint-fast-0": {"bonding_curve": "curve-fast-0", "account_state": {"virtual_sol_reserves": 1}},
            "mint-fast-1": {"bonding_curve": "curve-fast-1", "account_state": {"virtual_sol_reserves": 1}},
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, source_duration_seconds=1),
        source=FastReaderSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    assert summary["curve_observation_attempts"] == 2
    assert summary["source_event_queue_dropped_count"] == 0
    assert max(callback_durations_ms) < 40.0


def test_transaction_live_smoke_trade_flow_writes_do_not_block_next_birth_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_started_at: dict[str, float] = {}
    original_record_trade_event = recorder_module.BondingCurveProgressRecorder.record_trade_event

    def slow_record_trade_event(self: BondingCurveProgressRecorder, trade: dict) -> dict:
        time.sleep(0.02)
        return original_record_trade_event(self, trade)

    monkeypatch.setattr(
        recorder_module.BondingCurveProgressRecorder,
        "record_trade_event",
        slow_record_trade_event,
    )

    class TradeHeavySource:
        source_name = "trade_heavy_source"
        actual_duration_seconds = 1.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            base = time.time()
            on_event(
                {
                    "received_at": base,
                    "signature": "sig-mint-trade-a",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-mint-trade-a",
                            "slot": 1,
                            "mint": "mint-trade-a",
                            "bonding_curve": "curve-mint-trade-a",
                            "source_instruction_level": "top_level",
                            "creator": "creator-a",
                        }
                    ],
                    "trade_rows": [
                        {
                            "signature": f"sig-trade-{index}",
                            "slot": 2 + index,
                            "mint": "mint-trade-a",
                            "side": "buy",
                            "trader_wallet": f"buyer-{index}",
                            "fee_payer": f"buyer-{index}",
                            "token_amount": 100.0,
                            "quote_amount": 1.0,
                            "quote_asset": "SOL",
                            "received_at": base + 0.001 + (index * 0.001),
                            "decision_time": base + 0.001 + (index * 0.001),
                            "source_event_type": "pumpfun_trade",
                            "trade_decode_status": "balance_delta_inferred",
                        }
                        for index in range(20)
                    ],
                }
            )
            on_event(
                {
                    "received_at": base + 0.002,
                    "signature": "sig-mint-trade-b",
                    "slot": 100,
                    "decoded_rows": [
                        {
                            "signature": "sig-mint-trade-b",
                            "slot": 100,
                            "mint": "mint-trade-b",
                            "bonding_curve": "curve-mint-trade-b",
                            "source_instruction_level": "top_level",
                            "creator": "creator-b",
                        }
                    ],
                }
            )

    class RecordingProbe(FakeCurveStateProbe):
        def probe_create_event(self, create_event: dict, *, now_fn=time.time) -> dict:
            mint = str(create_event.get("mint") or "")
            probe_started_at[mint] = time.time()
            return super().probe_create_event(create_event, now_fn=now_fn)

    probe = RecordingProbe(
        {
            "mint-trade-a": {"bonding_curve": "curve-mint-trade-a", "account_state": {"virtual_sol_reserves": 1}},
            "mint-trade-b": {"bonding_curve": "curve-mint-trade-b", "account_state": {"virtual_sol_reserves": 1}},
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, source_duration_seconds=1),
        source=TradeHeavySource(),
        curve_probe=probe,
        now_fn=time.time,
    )

    assert summary["trade_rows_recorded"] == 20
    assert summary["curve_observation_attempts"] == 2
    assert probe_started_at["mint-trade-b"] - probe_started_at["mint-trade-a"] < 0.25


def test_transaction_live_smoke_priority_birth_workers_do_not_block_second_birth_probe(tmp_path: Path) -> None:
    first_probe_can_finish = threading.Event()
    first_probe_started = threading.Event()
    second_probe_started = threading.Event()
    probe_started_at: dict[str, float] = {}
    probe_finished_at: dict[str, float] = {}

    class TwoBirthSource:
        source_name = "two_birth_priority_fake_txsub"
        actual_duration_seconds = 1.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            base = time.time()
            for index, mint in enumerate(["mint-priority-a", "mint-priority-b"]):
                on_event(
                    {
                        "received_at": base + (index * 0.001),
                        "signature": f"sig-{mint}",
                        "slot": 100 + index,
                        "decoded_rows": [
                            {
                                "signature": f"sig-{mint}",
                                "slot": 100 + index,
                                "mint": mint,
                                "bonding_curve": f"curve-{mint}",
                                "source_instruction_level": "top_level",
                                "creator": f"creator-{mint}",
                            }
                        ],
                    }
                )

    class BlockingFirstProbe(FakeCurveStateProbe):
        def probe_create_event(self, create_event: dict[str, Any], *, now_fn: Any = time.time) -> dict[str, Any]:
            mint = str(create_event.get("mint") or "")
            probe_started_at[mint] = time.time()
            if mint == "mint-priority-a":
                first_probe_started.set()
                assert second_probe_started.wait(timeout=1.0)
                first_probe_can_finish.wait(timeout=1.0)
            if mint == "mint-priority-b":
                second_probe_started.set()
                first_probe_can_finish.set()
            result = super().probe_create_event(create_event, now_fn=now_fn)
            probe_finished_at[mint] = time.time()
            return result

    probe = BlockingFirstProbe(
        {
            "mint-priority-a": {"bonding_curve": "curve-mint-priority-a", "account_state": {"virtual_sol_reserves": 1}},
            "mint-priority-b": {"bonding_curve": "curve-mint-priority-b", "account_state": {"virtual_sol_reserves": 1}},
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            source_duration_seconds=1,
            birth_priority_worker_count=2,
        ),
        source=TwoBirthSource(),
        curve_probe=probe,
        now_fn=time.time,
    )
    assert first_probe_started.is_set()
    assert second_probe_started.is_set()
    assert probe_started_at["mint-priority-b"] < probe_finished_at["mint-priority-a"]
    assert summary["birth_priority_worker_count"] == 2
    assert summary["birth_priority_dispatch_enabled"] is True
    assert summary["birth_priority_queue_dropped_count"] == 0
    assert summary["curve_observation_attempts"] == 2


def test_source_duration_quality_warns_on_recovered_websocket_reconnect_when_duration_completes(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute([], actual_duration_seconds=600.0)
    source.websocket_keepalive_timeout_count = 1
    source.websocket_reconnect_count = 1
    source.reconnect_attempts = 1

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=600),
        source=source,
        curve_probe=FakeCurveStateProbe({}),
        now_fn=lambda: 1000.0,
    )

    assert summary["completed_requested_duration"] is True
    assert summary["source_duration_quality_status"] == "complete_with_reconnect_warning"
    assert summary["validation_run_quality_label"] == "RUN_QUALITY_COMPLETE_WITH_RECONNECT_WARNING"
    assert summary["early_end_reason"] == "websocket_reconnect_or_keepalive"


def test_running_live_status_does_not_rebuild_lifecycle_outputs_per_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    calls = {"payload": 0, "outputs": 0}

    def fail_running_payload(*args, **kwargs):
        calls["payload"] += 1
        raise AssertionError("running live status must not rebuild lifecycle payload from artifacts")

    def fail_running_outputs(*args, **kwargs):
        calls["outputs"] += 1
        raise AssertionError("running live status must not rebuild lifecycle outputs from artifacts")

    monkeypatch.setattr(recorder_module, "build_lifecycle_live_status_payload", fail_running_payload)
    monkeypatch.setattr(recorder_module, "build_lifecycle_outputs", fail_running_outputs)

    recorder.process_birth(_launch("mint-live-status"))
    recorder.record_trade_event(
        {
            "mint": "mint-live-status",
            "side": "buy",
            "trader_wallet": "buyer-a",
            "quote_amount": 0.1,
            "quote_asset": "SOL",
            "received_at": 1001.0,
        }
    )
    recorder.record_holder_snapshot(
        {
            "mint": "mint-live-status",
            "holder_distribution_status": "partial_trade_derived",
            "holder_count": 1,
            "received_at": 1001.0,
        }
    )

    status = json.loads((tmp_path / "live_status.json").read_text(encoding="utf-8"))
    assert calls == {"payload": 0, "outputs": 0}
    assert status["full_path_lifecycle_status"] == "running_counter_only"
    assert status["long_scan_status"] == "BLOCKED_FOR_LONG_SCAN"


def test_transaction_live_smoke_streaming_duplicate_does_not_probe_again(tmp_path: Path) -> None:
    clock = {"now": 2000.0}

    class StreamingDuplicateSource:
        source_name = "streaming_duplicate_fake_txsub"
        actual_duration_seconds = 300.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def iter_notifications(self, duration_seconds: float) -> list[dict]:
            clock["now"] = 2300.0
            return self._events()

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            for event in self._events():
                clock["now"] = event["received_at"] + 0.05
                on_event(event)
            clock["now"] = 2300.0

        def _events(self) -> list[dict]:
            return [
                {
                    "received_at": 2000.0,
                    "signature": "sig-first",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-first",
                            "slot": 1,
                            "mint": "mint-a",
                            "bonding_curve": "curve-a",
                            "source_instruction_level": "top_level",
                        }
                    ],
                },
                {
                    "received_at": 2001.0,
                    "signature": "sig-dup",
                    "slot": 2,
                    "decoded_rows": [
                        {
                            "signature": "sig-dup",
                            "slot": 2,
                            "mint": "mint-a",
                            "bonding_curve": "curve-a-dup",
                            "source_instruction_level": "inner",
                            "source_instruction_decode_route": "mayhem_wrapped_compact_create",
                        }
                    ],
                },
            ]

    probe = FakeCurveStateProbe({"mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}}})

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=StreamingDuplicateSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    assert summary["decoded_birth_rows"] == 2
    assert summary["unique_birth_mints"] == 1
    assert summary["duplicate_mint_rows"] == 1
    assert summary["duplicate_rows_by_route"] == {"wrapped_compact": 1}
    assert summary["curve_observation_attempts"] == 1
    assert len(probe.calls) == 1


def test_transaction_live_smoke_records_streamed_trade_rows_for_seen_births(tmp_path: Path) -> None:
    clock = {"now": 3000.0}

    class StreamingTradeSource:
        source_name = "streaming_trade_fake_txsub"
        actual_duration_seconds = 60.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            clock["now"] = 3000.05
            on_event(
                {
                    "received_at": 3000.0,
                    "signature": "sig-create",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-create",
                            "slot": 1,
                            "mint": "mint-a",
                            "bonding_curve": "curve-a",
                            "source_instruction_level": "top_level",
                            "creator": "creator-a",
                        }
                    ],
                    "trade_rows": [
                        {
                            "signature": "sig-buy",
                            "slot": 2,
                            "mint": "mint-a",
                            "side": "buy",
                            "trader_wallet": "buyer-a",
                            "fee_payer": "buyer-a",
                            "token_amount": 100.0,
                            "quote_amount": 1.0,
                            "quote_asset": "SOL",
                            "received_at": 3000.04,
                            "decision_time": 3000.04,
                            "source_event_type": "pumpfun_trade",
                            "trade_decode_status": "balance_delta_inferred",
                        }
                    ],
                }
            )

    probe = FakeCurveStateProbe({"mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}}})

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=StreamingTradeSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    trade_rows = _jsonl(tmp_path / "trade_flow_events.jsonl")
    organic_rows = _jsonl(tmp_path / "organic_flow_events.jsonl")
    assert summary["decoded_trade_rows"] == 1
    assert summary["trade_rows_recorded"] == 1
    assert summary["trade_flow_events_written"] == 1
    assert summary["organic_flow_events_written"] == 1
    assert trade_rows[-1]["mint"] == "mint-a"
    assert trade_rows[-1]["side"] == "buy"
    assert trade_rows[-1]["quote_amount"] == 1.0
    assert organic_rows[-1]["mint"] == "mint-a"


def test_transaction_live_smoke_records_birth_dev_and_trade_derived_holder_enrichment(tmp_path: Path) -> None:
    clock = {"now": 3100.0}

    class StreamingEnrichmentSource:
        source_name = "streaming_enrichment_fake_txsub"
        actual_duration_seconds = 60.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            clock["now"] = 3100.05
            on_event(
                {
                    "received_at": 3100.0,
                    "signature": "sig-create",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-create",
                            "slot": 1,
                            "mint": "mint-a",
                            "bonding_curve": "curve-a",
                            "source_instruction_level": "top_level",
                            "creator": "creator-a",
                        }
                    ],
                    "trade_rows": [
                        {
                            "signature": "sig-buy",
                            "slot": 2,
                            "mint": "mint-a",
                            "side": "buy",
                            "trader_wallet": "buyer-a",
                            "fee_payer": "buyer-a",
                            "token_amount": 100.0,
                            "quote_amount": 1.0,
                            "quote_asset": "SOL",
                            "received_at": 3100.04,
                            "decision_time": 3100.04,
                            "source_event_type": "pumpfun_trade",
                            "trade_decode_status": "balance_delta_inferred",
                        }
                    ],
                }
            )

    probe = FakeCurveStateProbe({"mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}}})

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=StreamingEnrichmentSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    holder_rows = _jsonl(tmp_path / "holder_distribution_snapshots.jsonl")
    dev_rows = _jsonl(tmp_path / "dev_behavior_events.jsonl")
    assert summary["holder_distribution_snapshots_written"] == 1
    assert summary["dev_behavior_events_written"] == 1
    assert holder_rows[-1]["mint"] == "mint-a"
    assert holder_rows[-1]["holder_distribution_status"] == "partial_trade_derived"
    assert holder_rows[-1]["holder_count"] == 1
    assert dev_rows[-1]["mint"] == "mint-a"
    assert dev_rows[-1]["dev_behavior_status"] == "partial_birth_metadata"
    assert dev_rows[-1]["creator_wallet"] == "creator-a"


def _t007_gate_ready_status() -> dict:
    return {
        "unique_birth_mints": 100,
        "progress_decoded_candidate_count": 90,
        "true_curve_threshold_crossings_written": 12,
        "curve_velocity_events_written": 80,
        "curve_acceleration_events_written": 70,
        "trade_flow_events_written": 65,
        "trade_rows_recorded": 65,
        "buyer_breadth_available_count": 65,
        "global_migration_events": 3,
        "token_path_summary_rows": 100,
        "decision_time_safety_violation_count": 0,
        "organic_flow_events_written": 65,
        "deferred_feature_families": [
            "holder_distribution_partial_snapshots",
            "dev_creator_behavior_partial_features",
            "post_migration_observations_partial",
            "execution_cost_observations_partial",
        ],
        "valuation_ladder_emission_policy": "market_cap_confirmed_only",
    }


def _t007bb_passed_60m_payload(**overrides) -> dict:
    payload = {
        **_t007_gate_ready_status(),
        "deferred_feature_families": [],
        "holder_distribution_snapshots_written": 10,
        "dev_behavior_events_written": 10,
        "post_migration_observations_written": 8,
        "post_migration_pool_state_partial_count": 8,
        "pool_liquidity_quote_present_count": 8,
        "pool_liquidity_usd_present_count": 8,
        "executable_quote_observations_written": 8,
        "price_impact_rows_populated": 8,
        "price_impact_available_count": 8,
        "executable_quote_decision_time_safe_count": 8,
        "execution_cost_observations_written": 4,
        "fee_model_status": "confirmed",
        "fee_model_confirmed_count": 8,
        "fee_model_unknown_count": 0,
        "decision_label": "T007BA_60M_PARTIAL_DEPTH_VALIDATION_PASSED",
        "source_duration_quality_status": "complete",
        "archive_status": "complete",
        "run_finalized": True,
        "queue_drops": 0,
        "queue_dropped_count": 0,
        "capacity_rejected": 0,
        "capacity_rejected_after_dedupe": 0,
        "http_429": 0,
        "http_429_count": 0,
        "rpc_failures": 0,
        "decision_time_safety_violations": 0,
        "decision_time_safety_violation_count": 0,
        "valuation_ladder_events": 0,
        "valuation_ladder_events_written": 0,
        "mayhem_files_modified": False,
        "trading_paper_wallet_signing_execution_untouched": True,
        "fee_proof_label": "POST_PATCH_EVENT_FEE_PROOF_PASSED",
        "event_endpoint_pass_count": 315,
        "event_endpoint_fail_count": 0,
    }
    payload.update(overrides)
    return payload


def test_t007bb_passed_clean_60m_unlocks_exactly_one_2h_thesis_collection() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007bb_passed_60m_payload(),
        thesis_scope="partial_post_migration_depth",
    )

    assert gate["can_run_one_2h_thesis_collection"] is True
    assert gate["can_run_2h_plus_scan"] is True
    assert gate["can_run_4h_plus"] is False
    assert gate["allowed_scan_scope"] == "one_controlled_2h_thesis_collection"
    assert gate["edge_claim_allowed"] is False
    assert gate["live_trading_allowed"] is False
    assert gate["paper_trading_allowed"] is False
    assert gate["valuation_ladder_allowed"] is False
    assert gate["wallet_signing_execution_allowed"] is False
    assert gate["minimum_next_action"] == "run exactly one controlled 2h thesis collection"


def test_t007bb_partial_or_failed_60m_keeps_2h_blocked() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007bb_passed_60m_payload(
            source_duration_quality_status="partial",
            decision_label="T007BA_60M_PARTIAL_DEPTH_VALIDATION_PARTIAL",
        ),
        thesis_scope="partial_post_migration_depth",
    )

    assert gate["can_run_one_2h_thesis_collection"] is False
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["allowed_scan_scope"] != "one_controlled_2h_thesis_collection"
    assert "clean_60m_validation_not_passed" in gate["blocking_reasons"]


def test_t007bb_2h_unlock_does_not_allow_4h_trading_ladder_or_edge_claims() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007bb_passed_60m_payload(),
        thesis_scope="partial_post_migration_depth",
    )

    assert gate["can_run_one_2h_thesis_collection"] is True
    assert gate["can_run_4h_plus"] is False
    assert gate["edge_claim_allowed"] is False
    assert gate["live_trading_allowed"] is False
    assert gate["paper_trading_allowed"] is False
    assert gate["valuation_ladder_allowed"] is False
    assert gate["mayhem_files_modified"] is False


def _write_t007bc_jsonl(root: Path, name: str, rows: list[dict]) -> None:
    (root / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_t007bc_coverage_matrix_dedupes_migrations_and_separates_loss_buckets(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007bc_migrated_mint_full_path_coverage_repair import (
        analyze_t007bc_migrated_full_path_coverage,
    )

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    (archive / "collector_summary.json").write_text(json.dumps({"run_id": "t007bb-fixture"}), encoding="utf-8")
    (archive / "campaign_manifest.json").write_text(json.dumps({"run_id": "t007bb-fixture"}), encoding="utf-8")
    _write_t007bc_jsonl(
        archive,
        "global_migration_events.jsonl",
        [
            {"mint": "mint-full", "signature": "sig-mig-full", "pool_or_pair_address": "pool-full", "migration_received_at": 300.0},
            {"mint": "mint-full", "signature": "sig-mig-full-dup", "pool_or_pair_address": "pool-full", "migration_received_at": 301.0},
            {"mint": "mint-depth", "signature": "sig-mig-depth", "pool_or_pair_address": "pool-depth", "migration_received_at": 320.0},
            {"mint": "mint-sampled", "signature": "sig-mig-sampled", "pool_or_pair_address": "pool-sampled", "migration_received_at": 330.0},
        ],
    )
    _write_t007bc_jsonl(
        archive,
        "birth_audit.jsonl",
        [
            {"mint": "mint-full", "admitted": True, "received_at": 100.0, "admission_reason": "sample_admitted_after_prune"},
            {"mint": "mint-sampled", "admitted": False, "received_at": 110.0, "admission_reason": "sample_rejected"},
        ],
    )
    _write_t007bc_jsonl(archive, "curve_observations.jsonl", [{"mint": "mint-full", "computed_progress_pct": 70.0, "received_at": 120.0}])
    _write_t007bc_jsonl(archive, "true_curve_threshold_crossings.jsonl", [{"mint": "mint-full", "threshold_pct": 70.0, "crossing_received_at": 130.0}])
    _write_t007bc_jsonl(archive, "curve_velocity_events.jsonl", [{"mint": "mint-full", "decision_time": 140.0}])
    _write_t007bc_jsonl(archive, "curve_acceleration_events.jsonl", [{"mint": "mint-full", "decision_time": 141.0}])
    _write_t007bc_jsonl(archive, "trade_flow_events.jsonl", [{"mint": "mint-full", "decision_time": 150.0}])
    _write_t007bc_jsonl(archive, "organic_flow_events.jsonl", [{"mint": "mint-full", "decision_time": 151.0}])
    _write_t007bc_jsonl(archive, "holder_distribution_snapshots.jsonl", [{"mint": "mint-full", "decision_time": 160.0}])
    _write_t007bc_jsonl(archive, "dev_behavior_events.jsonl", [{"mint": "mint-full", "decision_time": 161.0}])
    _write_t007bc_jsonl(
        archive,
        "post_migration_observations.jsonl",
        [
            {"mint": "mint-full", "decision_time": 305.0, "pool_or_pair_address": "pool-full", "base_reserve_raw": 1},
            {"mint": "mint-depth", "decision_time": 325.0, "pool_or_pair_address": "pool-depth", "base_reserve_raw": 1},
        ],
    )
    _write_t007bc_jsonl(
        archive,
        "executable_quote_observations.jsonl",
        [
            {"mint": "mint-full", "decision_time": 306.0, "pool_or_pair_address": "pool-full", "price_impact_pct": 0.1},
            {"mint": "mint-depth", "decision_time": 326.0, "pool_or_pair_address": "pool-depth", "price_impact_pct": 0.2},
        ],
    )
    _write_t007bc_jsonl(archive, "pumpswap_swap_events.jsonl", [{"base_mint": "mint-full", "decision_time": 307.0, "pool_or_pair_address": "pool-full"}])
    _write_t007bc_jsonl(
        archive,
        "execution_cost_observations.jsonl",
        [
            {"decision_time": 99.0, "execution_cost_status": "partial", "observation_reason": "campaign_start"},
            {"decision_time": 299.0, "execution_cost_status": "partial", "observation_reason": "migration_event"},
        ],
    )

    summary = analyze_t007bc_migrated_full_path_coverage(archive, output)

    assert summary["raw_global_migration_rows"] == 4
    assert summary["migrated_unique_mints"] == 3
    assert summary["coverage_buckets"]["full_path"] == 1
    assert summary["coverage_buckets"]["backfill_possible"] == 1
    assert summary["coverage_buckets"]["birth_seen_sample_rejected"] == 1
    assert summary["strict_full_paths"] == 1
    assert summary["sampling_loss_count"] == 1
    assert summary["migration_plus_depth_only_mints"] == 0
    rows = {row["mint"]: row for row in csv.DictReader((output / "migration_full_path_coverage_matrix.csv").open())}
    assert rows["mint-depth"]["coverage_status"] == "backfill_possible"
    assert rows["mint-depth"]["pre_migration_failure_cause"] == "birth_source_miss"
    assert rows["mint-sampled"]["pre_migration_failure_cause"] == "sample_rejected"
    assert rows["mint-full"]["execution_cost_at_migration_status"] == "joined"
    assert rows["mint-full"]["execution_cost_join_decision_time_safe"] == "True"
    assert (output / "migration_full_path_coverage_summary.json").exists()
    assert (output / "backfill_feasibility_by_mint.csv").exists()


def test_t007bc_latest_prior_execution_cost_join_is_decision_time_safe() -> None:
    from research.mtp_research.validation.t007bc_migrated_mint_full_path_coverage_repair import (
        join_latest_prior_execution_cost,
    )

    rows = [
        {"decision_time": 90.0, "execution_cost_status": "partial", "observation_reason": "prior"},
        {"decision_time": 110.0, "execution_cost_status": "partial", "observation_reason": "future"},
    ]

    joined = join_latest_prior_execution_cost(100.0, rows)
    unavailable = join_latest_prior_execution_cost(80.0, rows)

    assert joined["status"] == "joined"
    assert joined["joined_decision_time"] == 90.0
    assert joined["source_observation_reason"] == "prior"
    assert joined["decision_time_safe"] is True
    assert unavailable["status"] == "not_available"
    assert unavailable["joined_decision_time"] is None
    assert unavailable["decision_time_safe"] is True


def test_t007bc_full_path_gate_blocks_migrated_thesis_but_allows_depth_only_analysis() -> None:
    from research.mtp_research.validation.t007bc_migrated_mint_full_path_coverage_repair import (
        build_t007bc_full_path_gate,
    )

    gate = build_t007bc_full_path_gate(
        {
            "migrated_unique_mints": 94,
            "strict_full_paths": 0,
            "near_full_migrated_mints": 1,
            "migration_plus_depth_only_mints": 83,
            "migrated_birth_seen_rate": 27 / 94,
            "migrated_admitted_rate": 21 / 94,
            "migrated_curve_observation_rate": 4 / 94,
            "migrated_trade_flow_rate": 5 / 94,
            "migrated_post_migration_quote_rate": 87 / 94,
            "migrated_execution_cost_join_rate": 0.0,
        }
    )

    assert gate["full_birth_to_exit_thesis_allowed"] is False
    assert gate["full_migrated_token_thesis_allowed"] is False
    assert gate["post_migration_depth_only_analysis_allowed"] is True
    assert gate["pre_migration_only_analysis_allowed"] is True
    assert gate["longer_full_path_collection_allowed"] is False
    assert "full_path_migrated_mints_zero" in gate["blocking_reasons"]
    assert gate["valuation_ladder_suppressed"] is True
    assert gate["mayhem_files_modified"] is False


def test_t007bc_guardrails_do_not_enable_mayhem_valuation_or_trading_paths() -> None:
    from research.mtp_research.validation.t007bc_migrated_mint_full_path_coverage_repair import (
        T007BC_GUARDRAILS,
    )

    assert T007BC_GUARDRAILS["live_scan_ran"] is False
    assert T007BC_GUARDRAILS["mayhem_files_modified"] is False
    assert T007BC_GUARDRAILS["valuation_ladder_suppressed"] is True
    assert T007BC_GUARDRAILS["trading_enabled"] is False
    assert T007BC_GUARDRAILS["paper_trading_enabled"] is False
    assert T007BC_GUARDRAILS["wallet_signing_execution_modified"] is False


def test_t007_gate_blocks_60m_scan_when_trade_flow_is_missing() -> None:
    status = _t007_gate_ready_status()
    status["trade_flow_events_written"] = 0
    status["trade_rows_recorded"] = 0

    gate = evaluate_t007_thesis_ready_gate(status)

    assert gate["can_run_10m_feature_proof"] is True
    assert gate["can_run_60m_thesis_scan"] is False
    assert "trade_flow" in gate["missing_feature_families"]
    assert gate["minimum_next_action"] == "implement trade-flow feed"


def test_t007_gate_blocks_60m_scan_when_buyer_breadth_is_missing() -> None:
    status = _t007_gate_ready_status()
    status["buyer_breadth_available_count"] = 0

    gate = evaluate_t007_thesis_ready_gate(status)

    assert gate["can_run_60m_thesis_scan"] is False
    assert "buyer_breadth" in gate["missing_feature_families"]


def test_t007_gate_blocks_60m_scan_when_migration_linkage_is_missing() -> None:
    status = _t007_gate_ready_status()
    status["global_migration_events"] = 0

    gate = evaluate_t007_thesis_ready_gate(status)

    assert gate["can_run_60m_thesis_scan"] is False
    assert "pumpswap_global_migration_linkage" in gate["missing_feature_families"]
    assert gate["minimum_next_action"] == "fix migration linkage"


def test_t007_gate_blocks_60m_scan_when_advanced_lanes_are_placeholders_only() -> None:
    status = _t007_gate_ready_status()
    status["deferred_feature_families"] = []
    status["organic_flow_events_written"] = 0
    status["holder_distribution_snapshots_written"] = 1
    status["dev_behavior_events_written"] = 1
    status["post_migration_observations_written"] = 1
    status["execution_cost_observations_written"] = 1
    status["placeholder_feature_families"] = [
        "holder_distribution_partial_snapshots",
        "dev_creator_behavior_partial_features",
        "post_migration_observations_partial",
        "execution_cost_observations_partial",
    ]

    gate = evaluate_t007_thesis_ready_gate(status)

    assert gate["can_run_60m_thesis_scan"] is False
    assert "advanced_feature_families_placeholder_only" in gate["blocking_reasons"]
    assert "holder_distribution_partial_snapshots" in gate["missing_feature_families"]
    assert "dev_creator_behavior_partial_features" in gate["missing_feature_families"]
    assert "post_migration_observations_partial" in gate["missing_feature_families"]
    assert "execution_cost_observations_partial" in gate["missing_feature_families"]
    assert gate["minimum_next_action"] == "implement holder/dev enrichment"


def test_t007_gate_allows_10m_feature_proof_with_missing_lanes() -> None:
    gate = evaluate_t007_thesis_ready_gate({"valuation_ladder_emission_policy": "market_cap_confirmed_only"})

    assert gate["can_run_10m_feature_proof"] is True
    assert gate["scan_categories"]["feature_feed_proof"]["max_duration_seconds"] == 600
    assert gate["can_run_60m_thesis_scan"] is False


def test_t007_gate_blocks_60m_when_execution_cost_rows_are_missing() -> None:
    status = _t007_gate_ready_status()
    status["deferred_feature_families"] = []
    status["post_migration_observations_written"] = 4
    status["execution_cost_observations_written"] = 0

    gate = evaluate_t007_thesis_ready_gate(status, thesis_scope="h001_pre_migration")

    assert gate["can_run_60m_thesis_scan"] is False
    assert "execution_cost_observations_partial" in gate["missing_feature_families"]


def test_t007_gate_allows_60m_when_required_live_and_depth_execution_partial_live() -> None:
    status = _t007_gate_ready_status()
    status["deferred_feature_families"] = []
    status["holder_distribution_snapshots_written"] = 4
    status["dev_behavior_events_written"] = 4
    status["post_migration_observations_written"] = 4
    status["post_migration_pool_state_partial_count"] = 4
    status["execution_cost_observations_written"] = 4
    status["execution_cost_partial_count"] = 4

    gate = evaluate_t007_thesis_ready_gate(status, thesis_scope="h001_pre_migration")

    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["blocking_reasons"] == []
    assert gate["minimum_next_action"] == "run 60m thesis-data collection"


def test_t007_gate_allows_60m_h001_only_scan_when_required_live_and_advanced_deferred() -> None:
    gate = evaluate_t007_thesis_ready_gate(_t007_gate_ready_status(), thesis_scope="h001_pre_migration")

    assert gate["can_run_60m_thesis_scan"] is False
    assert "post_migration_observations_partial" in gate["missing_feature_families"]
    assert "execution_cost_observations_partial" in gate["missing_feature_families"]


def test_t007_gate_keeps_valuation_ladder_suppressed() -> None:
    status = _t007_gate_ready_status()
    status["valuation_ladder_emission_policy"] = "enabled"

    gate = evaluate_t007_thesis_ready_gate(status)

    assert gate["valuation_ladder_suppressed"] is False
    assert gate["can_run_60m_thesis_scan"] is False
    assert "valuation_ladder_not_suppressed" in gate["blocking_reasons"]


def test_t007_gate_recommendations_do_not_suggest_long_scans_when_blockers_remain() -> None:
    gate = evaluate_t007_thesis_ready_gate({"valuation_ladder_emission_policy": "market_cap_confirmed_only"})

    assert gate["can_run_60m_thesis_scan"] is False
    assert "60m" not in gate["minimum_next_action"]
    assert "2h" not in gate["minimum_next_action"]
    assert "4h" not in gate["minimum_next_action"]


def test_t007_gate_writes_artifacts_and_marks_mayhem_untouched(tmp_path: Path) -> None:
    gate = write_t007_thesis_ready_gate(tmp_path, _t007_gate_ready_status())

    assert gate["mayhem_files_modified"] is False
    assert (tmp_path / "thesis_ready_gate.json").exists()
    assert (tmp_path / "summary.md").exists()


def test_live_smoke_applies_sampling_and_only_tracks_admitted_launches(tmp_path: Path) -> None:
    source = FakeLaunchSource([_launch("mint-a"), _launch("mint-b"), _launch("mint-c")])
    probe = FakeCurveStateProbe(
        {
            "mint-a": {"bonding_curve": "curve-a", "account_state": {"virtual_sol_reserves": 1}, "observed_at": 1001.0},
            "mint-b": {"bonding_curve": "curve-b", "account_state": {"virtual_sol_reserves": 2}, "observed_at": 1002.0},
            "mint-c": {"bonding_curve": "curve-c", "account_state": {"virtual_sol_reserves": 3}, "observed_at": 1003.0},
        }
    )

    summary = run_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=0),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1000.0,
        sleep_fn=lambda _seconds: None,
    )

    assert summary["births_detected"] == 3
    assert summary["births_admitted"] == 0
    assert summary["sample_rejected"] == 3
    assert summary["curve_observation_attempts"] == 0
    assert probe.calls == []
    assert _jsonl(tmp_path / "curve_observations.jsonl") == []
    assert (tmp_path / "threshold_crossings.jsonl").exists()
    assert (tmp_path / "migration_events.jsonl").exists()


def test_live_smoke_preserves_unresolved_progress_formula_instead_of_faking_progress(tmp_path: Path) -> None:
    source = FakeLaunchSource([_launch("mint-a")])
    probe = FakeCurveStateProbe(
        {
            "mint-a": {
                "bonding_curve": "curve-a",
                "account_state": {"virtual_sol_reserves": 1_000_000, "virtual_token_reserves": 2_000_000},
                "fdv_proxy": 1234.5,
                "observed_at": 1001.0,
            }
        }
    )

    summary = run_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1000.0,
        sleep_fn=lambda _seconds: None,
    )

    observations = _jsonl(tmp_path / "curve_observations.jsonl")
    assert summary["births_detected"] == 1
    assert summary["births_admitted"] == 1
    assert summary["curve_observation_attempts"] == 1
    assert summary["curve_observations_written"] == 1
    assert summary["exact_progress_decoded_count"] == 0
    assert summary["unresolved_progress_formula_count"] == 1
    assert observations[0]["progress_pct"] is None
    assert observations[0]["progress_pct_status"] == "unresolved_formula"
    assert observations[0]["raw_curve_state"]["virtual_sol_reserves"] == 1_000_000


def test_reserve_progress_formula_handles_human_token_units() -> None:
    result = compute_true_curve_progress_from_state(
        {
            "real_token_reserves": 396_550_000,
            "token_total_supply": 1_000_000_000,
            "token_decimals": 6,
            "complete": False,
        }
    )

    assert result["progress_pct_status"] == "decoded_candidate"
    assert result["reserve_scale_mode"] == "human_token_units"
    assert result["progress_denominator_tokens"] == 793_100_000
    assert result["real_token_reserves_scaled"] == 396_550_000
    assert result["progress_pct"] == 50.0


def test_reserve_progress_formula_handles_raw_integer_units_without_marking_exact() -> None:
    result = compute_true_curve_progress_from_state(
        {
            "real_token_reserves": 396_550_000_000_000,
            "token_total_supply": 1_000_000_000_000_000,
            "token_decimals": 6,
            "complete": False,
        }
    )

    assert result["progress_pct_status"] == "decoded_candidate"
    assert result["reserve_scale_mode"] == "raw_integer_units_6_decimals"
    assert result["real_token_reserves_scaled"] == 396_550_000
    assert result["progress_pct"] == 50.0


def test_reserve_progress_formula_complete_zero_reserve_reaches_exact_100() -> None:
    result = compute_true_curve_progress_from_state(
        {
            "real_token_reserves": 0,
            "token_total_supply": 1_000_000_000_000_000,
            "token_decimals": 6,
            "complete": True,
        }
    )

    assert result["progress_pct_status"] == "decoded_exact"
    assert result["progress_pct"] == 100.0
    assert result["complete"] is True


def test_reserve_progress_formula_unresolved_when_scale_cannot_be_determined() -> None:
    result = compute_true_curve_progress_from_state({"virtual_sol_reserves": 1})

    assert result["progress_pct"] is None
    assert result["progress_pct_status"] == "unresolved_formula"
    assert result["reserve_scale_mode"] == "unknown"


def test_true_curve_and_valuation_crossings_are_distinguishable_and_first_only(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-a"))

    recorder.record_observation(
        {
            **_obs("mint-a", 40.0, 1.0, observation_id="first"),
            "progress_pct_status": "decoded_candidate",
            "progress_formula_version": "pumpfun_real_token_reserves_v1",
            "fdv_proxy": 29_000,
            "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
        }
    )
    recorder.record_observation(
        {
            **_obs("mint-a", 66.0, 2.0, observation_id="second"),
            "progress_pct_status": "decoded_candidate",
            "progress_formula_version": "pumpfun_real_token_reserves_v1",
            "fdv_proxy": 36_500,
            "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
        }
    )
    recorder.record_observation(
        {
            **_obs("mint-a", 67.0, 3.0, observation_id="duplicate-range"),
            "progress_pct_status": "decoded_candidate",
            "progress_formula_version": "pumpfun_real_token_reserves_v1",
            "fdv_proxy": 37_000,
            "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
        }
    )

    crossings = _jsonl(tmp_path / "threshold_crossings.jsonl")
    progress_thresholds = [row["threshold_pct"] for row in crossings if row["crossing_type"] == "true_curve_progress"]
    valuation_bands = [row["threshold_usd"] for row in crossings if row["crossing_type"] == "valuation_band"]
    assert progress_thresholds == [40.0, 50.0, 55.0, 60.0, 62.5, 65.0]
    assert valuation_bands == [15_000, 20_000, 25_000, 30_000, 35_000, 36_000]
    assert len([row for row in crossings if row["crossing_type"] == "valuation_band" and row["threshold_usd"] == 36_000]) == 1
    assert all(row.get("progress_formula_version") for row in crossings if row["crossing_type"] == "true_curve_progress")


def test_valuation_missing_does_not_fabricate_band_crossing(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-a"))

    recorder.record_observation({**_obs("mint-a", 41.0, 1.0), "fdv_proxy": None, "valuation_proxy_usd": None})
    summary = recorder.finalize()

    crossings = _jsonl(tmp_path / "threshold_crossings.jsonl")
    assert [row["crossing_type"] for row in crossings] == ["true_curve_progress"]
    assert summary["valuation_missing_count"] == 1
    assert summary["valuation_present_count"] == 0


def test_transaction_live_smoke_writes_dual_thesis_summary_counts(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 1000.0,
                "signature": "sig-a",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-a",
                        "slot": 1,
                        "mint": "mint-a",
                        "bonding_curve": "curve-a",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-a": {
                "bonding_curve": "curve-a",
                "account_state": {
                    "real_token_reserves": 317_240_000_000_000,
                    "token_total_supply": 1_000_000_000_000_000,
                    "token_decimals": 6,
                    "virtual_sol_reserves": 1,
                    "real_sol_reserves": 1,
                    "complete": False,
                },
                "fdv_proxy": 36_500,
                "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
                "fdv_usd": 36_500,
                "observed_at": 1000.2,
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1000.2,
    )

    assert summary["progress_decoded_candidate_count"] == 1
    assert summary["unresolved_progress_formula_count"] == 0
    assert summary["reserve_scale_mode_counts"] == {"raw_integer_units_6_decimals": 1}
    assert summary["valuation_present_count"] == 1
    assert summary["valuation_band_crossings_by_band"]["36000"] == 1
    assert summary["first_30k_valuation_crossings_count"] == 1
    assert summary["first_36k_valuation_crossings_count"] == 1
    assert summary["true_curve_threshold_crossings_by_threshold"]["60.0"] == 1


def test_live_smoke_summary_includes_live_source_fields_and_capacity_rejections(tmp_path: Path) -> None:
    source = FakeLaunchSource([_launch("mint-a"), _launch("mint-b")])
    probe = FakeCurveStateProbe({"mint-a": {"bonding_curve": "curve-a", "account_state": {}, "observed_at": 1001.0}})

    summary = run_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 1000.0,
        sleep_fn=lambda _seconds: None,
    )

    required = {
        "live_source_used",
        "subscription_connect_status",
        "births_detected",
        "births_admitted",
        "sample_rejected",
        "capacity_rejected",
        "curve_observation_attempts",
        "curve_observations_written",
        "exact_progress_decoded_count",
        "unresolved_progress_formula_count",
        "decode_failures",
        "rpc_failures",
        "queue_high_water_mark",
        "queue_drops",
        "birth_to_admission_latency_ms",
        "birth_to_first_curve_observation_latency_ms",
        "active_tracking_max_count",
        "stop_reasons",
        "mayhem_code_modified",
    }
    assert required <= set(summary)
    assert summary["births_detected"] == 2
    assert summary["births_admitted"] == 1
    assert summary["capacity_rejected"] == 1
    assert summary["mayhem_code_modified"] is False


def test_collector_summary_exposes_route_latency_histograms_and_production_backlog_gates(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            route_latency_gate_enabled=True,
            max_birth_to_admission_p95_ms=50,
            max_birth_to_first_curve_observation_p95_ms=500,
            helius_budget_gate_enabled=True,
            helius_max_estimated_credits=10_000,
        )
    )
    recorder.birth_to_admission_latencies_ms.extend([10.0, 20.0, 30.0])
    recorder.birth_to_first_observation_latencies_ms.extend([100.0, 200.0, 300.0])

    summary = recorder.build_summary()

    histograms = summary["route_latency_histograms"]
    assert histograms["birth_to_admission_latency_ms"]["count"] == 3
    assert histograms["birth_to_first_curve_observation_latency_ms"]["p95"] == 290.0
    assert summary["latency_histograms_present"] is True
    assert summary["route_latency_gate_passed"] is True
    assert summary["route_latency_gate_failures"] == []
    assert summary["gatekeeper_ab_status"] == "not_configured"
    assert summary["subscription_first_curve_updates_status"] in {"enabled", "not_configured"}
    assert summary["commitment_reorg_drop_accounting_present"] is True
    assert summary["helius_budget_gate_present"] is True
    assert summary["helius_budget_gate_passed"] is True


def test_collector_summary_splits_admission_enqueue_and_complete_latency_gates(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            route_latency_gate_enabled=True,
            max_birth_to_admission_p95_ms=1000,
            max_birth_to_admission_complete_p95_ms=1500,
            max_birth_to_first_curve_observation_p95_ms=3000,
            helius_max_estimated_credits=10_000,
        )
    )
    recorder.birth_to_admission_enqueue_latencies_ms.extend([100.0, 200.0, 300.0])
    recorder.birth_to_admission_complete_latencies_ms.extend([200.0, 300.0, 2500.0])
    recorder.birth_to_first_observation_latencies_ms.extend([400.0, 500.0, 600.0])

    summary = recorder.build_summary()

    assert summary["birth_to_admission_enqueue_latency_ms"]["p95"] == 290.0
    assert summary["birth_to_admission_complete_latency_ms"]["p95"] == 2280.0
    assert summary["birth_to_admission_latency_ms"] == summary["birth_to_admission_enqueue_latency_ms"]
    assert summary["route_latency_gate_scope"] == "decision_path_only"
    assert "birth_to_admission_complete_p95_exceeded" not in summary["route_latency_gate_failures"]
    assert summary["route_latency_gate_passed"] is True
    assert summary["materialization_latency_gate_passed"] is False
    assert summary["birth_projection_latency_gate_scope"] == "diagnostic_only"
    assert summary["materialization_latency_gate_failures"] == ["birth_to_admission_complete_p95_exceeded"]


def test_pre_migration_paper_gate_requires_full_paper_contract(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_birth_to_admission_complete_p95_ms=1500,
            max_birth_to_first_curve_observation_p95_ms=3000,
            max_normalized_birth_to_probe_start_p95_ms=1500,
        )
    )
    recorder.birth_to_admission_complete_latencies_ms.extend([100.0, 200.0, 2000.0])
    recorder.birth_to_first_observation_latencies_ms.extend([100.0, 200.0, 300.0])
    recorder.normalized_birth_to_probe_start_latencies_ms.extend([10.0, 20.0, 30.0])
    recorder.summary_counters["progress_decoded_candidate_count"] = 1
    recorder.summary_counters["valuation_present_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_1s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_5s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_10s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_30s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_60s_count"] = 1

    gate = recorder.build_summary()["pre_migration_paper_readiness_gate"]

    assert gate["pre_migration_paper_ready"] is False
    assert "birth_to_admission_complete_p95_exceeded" in gate["blocking_reasons"]
    assert "dev_previous_migrations_field_not_decision_time_safe" in gate["blocking_reasons"]
    assert "creator_sold_before_entry_field_not_decision_time_safe" in gate["blocking_reasons"]
    assert gate["pre_entry_snapshot_fields_available"] is True
    assert gate["post_entry_hot_flow_snapshot_1s_available"] is True
    assert gate["paper_position_accounting_available"] is True


def test_wallet_dev_checkpoint_exports_decision_safe_paper_fields(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(
        {
            **_launch("paper-dev-fields", received_at=1000.0),
            "creator": "creator-paper",
            "creator_history": [
                {"mint": "prior-1", "launch_received_at": 900.0, "migrated": True},
                {"mint": "prior-2", "launch_received_at": 910.0, "migrated": True},
                {"mint": "prior-3", "launch_received_at": 920.0, "migrated": True},
            ],
        }
    )
    state = recorder.states["paper-dev-fields"]
    recorder._emit_wallet_dev_checkpoint(
        state,
        "pre_entry",
        source_event={"received_at": 1001.0, "creator_sold_before_entry": False},
    )

    row = _jsonl(tmp_path / "wallet_dev_checkpoints.jsonl")[-1]
    assert row["dev_previous_migrations"] == 3
    assert row["dev_previous_migrations_ge_3"] is True
    assert row["dev_previous_migrations_decision_time_safe"] is True
    assert row["creator_sold_before_entry"] is False
    assert row["creator_sold_before_entry_decision_time_safe"] is True
    summary = recorder.build_summary()
    assert summary["dev_previous_migrations_field_decision_time_safe"] is True
    assert summary["creator_sold_before_entry_field_decision_time_safe"] is True


def test_wallet_dev_checkpoint_uses_local_creator_history_and_observed_creator_sells(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-prior", received_at=1000.0), "creator": "creator-local"})
    prior_state = recorder.states["mint-prior"]
    recorder._emit_migration_event(prior_state, {"slot": 20, "received_at": 1010.0}, received_at=1010.0)

    recorder.process_birth({**_launch("mint-next", received_at=1020.0), "creator": "creator-local"})
    next_state = recorder.states["mint-next"]
    recorder.record_trade_event(
        {
            "mint": "mint-next",
            "received_at": 1021.0,
            "side": "sell",
            "trader_wallet": "creator-local",
            "quote_amount": 0.1,
            "token_amount": 100.0,
        }
    )
    recorder._emit_wallet_dev_checkpoint(next_state, "pre_entry", source_event={"received_at": 1022.0})

    row = _jsonl(tmp_path / "wallet_dev_checkpoints.jsonl")[-1]
    assert row["creator_history_status"] == "available"
    assert row["creator_history_source"] == "local_observed_lifecycle_ledger"
    assert row["dev_previous_migrations"] == 1
    assert row["dev_previous_migrations_ge_3"] is False
    assert row["dev_previous_migrations_decision_time_safe"] is True
    assert row["creator_sold_before_entry"] is True
    assert row["creator_sold_before_entry_source"] == "local_observed_trade_flow"
    assert row["creator_sold_before_entry_decision_time_safe"] is True


def test_collector_summary_exposes_post_enqueue_latency_decomposition_and_pre_migration_gate(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            route_latency_gate_enabled=True,
            max_birth_to_admission_p95_ms=1000,
            max_birth_to_admission_complete_p95_ms=1500,
            max_birth_to_first_curve_observation_p95_ms=3000,
            helius_max_estimated_credits=10_000,
        )
    )
    recorder.birth_to_admission_enqueue_latencies_ms.extend([10.0, 20.0, 30.0])
    recorder.birth_enqueue_to_admission_worker_start_latencies_ms.extend([5.0, 10.0, 15.0])
    recorder.admission_worker_process_birth_duration_ms.extend([40.0, 50.0, 60.0])
    recorder.admission_worker_to_probe_job_enqueue_latencies_ms.extend([1.0, 2.0, 3.0])
    recorder.probe_job_enqueue_to_probe_start_latencies_ms.extend([4.0, 5.0, 6.0])
    recorder.birth_to_admission_complete_latencies_ms.extend([60.0, 70.0, 80.0])
    recorder.normalized_birth_to_probe_start_latencies_ms.extend([20.0, 30.0, 40.0])
    recorder.birth_to_first_observation_latencies_ms.extend([200.0, 300.0, 400.0])
    recorder.summary_counters["progress_decoded_candidate_count"] = 1
    recorder.summary_counters["valuation_present_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_1s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_5s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_10s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_30s_count"] = 1
    recorder.summary_counters["near_entry_hot_flow_snapshot_60s_count"] = 1
    recorder.summary_counters["dev_previous_migrations_field_decision_time_safe_count"] = 1
    recorder.summary_counters["creator_sold_before_entry_field_decision_time_safe_count"] = 1

    summary = recorder.build_summary()

    histograms = summary["route_latency_histograms"]
    assert histograms["birth_enqueue_to_admission_worker_start_latency_ms"]["p95"] == 14.5
    assert histograms["admission_worker_process_birth_duration_ms"]["p95"] == 59.0
    assert histograms["admission_worker_to_probe_job_enqueue_latency_ms"]["p95"] == 2.9
    assert histograms["probe_job_enqueue_to_probe_start_latency_ms"]["p95"] == 5.9
    gate = summary["pre_migration_paper_readiness_gate"]
    assert gate["gate_id"] == "T011_PRE_MIGRATION_PAPER_READINESS_GATE"
    assert gate["pre_migration_paper_ready"] is True
    assert gate["migration_full_path_required_for_pre_migration_paper"] is False


def test_transaction_live_smoke_schedules_first_curve_before_slow_birth_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_started = threading.Event()
    process_birth_finished = threading.Event()
    original_process_birth = recorder_module.BondingCurveProgressRecorder.process_birth

    def slow_process_birth(self: BondingCurveProgressRecorder, launch: dict) -> dict:
        probe_started.wait(timeout=0.5)
        row = original_process_birth(self, launch)
        process_birth_finished.set()
        return row

    class RecordingProbe(FakeCurveStateProbe):
        def probe_create_event(self, create_event: dict, *, now_fn=time.time) -> dict:
            probe_started.set()
            assert not process_birth_finished.is_set()
            return super().probe_create_event(create_event, now_fn=now_fn)

    monkeypatch.setattr(recorder_module.BondingCurveProgressRecorder, "process_birth", slow_process_birth)

    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": time.time(),
                "signature": "sig-early-probe",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-early-probe",
                        "slot": 1,
                        "mint": "mint-early-probe",
                        "bonding_curve": "curve-early-probe",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = RecordingProbe(
        {
            "mint-early-probe": {
                "bonding_curve": "curve-early-probe",
                "account_state": {"virtual_sol_reserves": 1},
                "observed_at": time.time(),
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, source_duration_seconds=1),
        source=source,
        curve_probe=probe,
        now_fn=time.time,
    )

    assert probe_started.is_set()
    assert process_birth_finished.is_set()
    assert summary["curve_observation_attempts"] == 1
    assert summary["source_fast_first_curve_probe_enqueued"] == 1
    assert summary["admission_worker_to_probe_job_enqueue_latency_ms"]["count"] == 0
    assert summary["probe_job_enqueue_to_probe_start_latency_ms"]["count"] == 1


def test_transaction_live_smoke_source_fast_path_probes_birth_while_admission_worker_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_birth_entered = threading.Event()
    first_birth_released = threading.Event()
    second_probe_started = threading.Event()
    original_process_birth = recorder_module.BondingCurveProgressRecorder.process_birth

    def slow_first_process_birth(self: BondingCurveProgressRecorder, launch: dict) -> dict:
        if launch.get("mint") == "mint-fast-path-a":
            first_birth_entered.set()
            second_probe_started.wait(timeout=0.5)
            first_birth_released.set()
        return original_process_birth(self, launch)

    class RecordingProbe(FakeCurveStateProbe):
        def probe_create_event(self, create_event: dict, *, now_fn=time.time) -> dict:
            if create_event.get("mint") == "mint-fast-path-b":
                assert not first_birth_released.is_set()
                second_probe_started.set()
            return super().probe_create_event(create_event, now_fn=now_fn)

    class TwoBirthSource:
        source_name = "two_birth_source"
        actual_duration_seconds = 1.0

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, _duration_seconds: float, on_event) -> None:
            base = time.time()
            for suffix in ("a", "b"):
                on_event(
                    {
                        "received_at": base,
                        "normalized_at": base,
                        "signature": f"sig-fast-path-{suffix}",
                        "slot": 1,
                        "decoded_rows": [
                            {
                                "signature": f"sig-fast-path-{suffix}",
                                "slot": 1,
                                "mint": f"mint-fast-path-{suffix}",
                                "bonding_curve": f"curve-fast-path-{suffix}",
                                "source_instruction_level": "top_level",
                            }
                        ],
                    }
                )

    monkeypatch.setattr(recorder_module.BondingCurveProgressRecorder, "process_birth", slow_first_process_birth)

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            source_duration_seconds=1,
            birth_priority_worker_count=1,
        ),
        source=TwoBirthSource(),
        curve_probe=RecordingProbe(
            {
                "mint-fast-path-a": {"bonding_curve": "curve-fast-path-a", "account_state": {"virtual_sol_reserves": 1}},
                "mint-fast-path-b": {"bonding_curve": "curve-fast-path-b", "account_state": {"virtual_sol_reserves": 1}},
            }
        ),
        now_fn=time.time,
    )

    assert first_birth_entered.is_set()
    assert second_probe_started.is_set()
    assert summary["source_fast_first_curve_probe_enqueued"] >= 1
    assert summary["curve_observation_attempts"] == 2


def test_transaction_live_smoke_hot_flow_snapshots_do_not_wait_for_bulk_trade_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_record_trade_event = recorder_module.BondingCurveProgressRecorder.record_trade_event

    def slow_record_trade_event(self: BondingCurveProgressRecorder, trade: dict) -> dict:
        time.sleep(0.02)
        return original_record_trade_event(self, trade)

    monkeypatch.setattr(recorder_module.BondingCurveProgressRecorder, "record_trade_event", slow_record_trade_event)

    class HotFlowSource:
        source_name = "hot_flow_source"
        actual_duration_seconds = 1.0

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def stream_notifications(self, _duration_seconds: float, on_event) -> None:
            base = time.time()
            on_event(
                {
                    "received_at": base,
                    "signature": "sig-hot-flow-birth",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-hot-flow-birth",
                            "slot": 1,
                            "mint": "mint-hot-flow",
                            "bonding_curve": "curve-hot-flow",
                            "source_instruction_level": "top_level",
                        }
                    ],
                }
            )
            for index in range(15):
                on_event(
                    {
                        "received_at": base + 0.1 + (index * 0.1),
                        "signature": f"sig-hot-flow-trade-{index}",
                        "slot": 2 + index,
                        "trade_rows": [
                            {
                                "signature": f"sig-hot-flow-trade-{index}",
                                "slot": 2 + index,
                                "mint": "mint-hot-flow",
                                "trade_direction": "sell" if index == 3 else "buy",
                                "trader_wallet": f"wallet-{index}",
                                "quote_amount": 1.0 + index,
                                "received_at": base + 0.1 + (index * 0.1),
                            }
                        ],
                    }
                )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, source_duration_seconds=1),
        source=HotFlowSource(),
        curve_probe=FakeCurveStateProbe(
            {"mint-hot-flow": {"bonding_curve": "curve-hot-flow", "account_state": {"virtual_sol_reserves": 1}}}
        ),
        now_fn=time.time,
    )

    rows = _jsonl(tmp_path / "near_entry_hot_flow_snapshots.jsonl")
    assert summary["near_entry_hot_flow_enabled"] is True
    assert summary["near_entry_hot_flow_events_recorded"] >= 10
    assert summary["near_entry_hot_flow_snapshot_5s_count"] == 1
    assert summary["near_entry_hot_flow_snapshot_10s_count"] == 1
    assert rows
    five_second = next(row for row in rows if row["window_seconds_after_entry"] == 5)
    assert five_second["buy_count_after_entry"] >= 10
    assert five_second["sell_count_after_entry"] == 1
    assert five_second["unique_buyers_after_entry"] >= 10
    one_second = next(row for row in rows if row["window_seconds_after_entry"] == 1)
    assert one_second["snapshot_phase"] == "post_entry"
    assert one_second["decision_time_safe"] is True
    assert one_second["decision_time_safety_status"] == "safe"
    assert five_second["largest_sell_quote_after_entry"] == 4.0


def test_valuation_ladder_events_and_paths_capture_transition_retrace_and_stalls(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, source_duration_seconds=120)
    )
    recorder.process_birth(_launch("mint-ladder"))

    recorder.record_observation({**_obs("mint-ladder", 41.0, 1.0, observation_id="cross-30k"), "fdv_proxy": 30_500, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    recorder.record_observation({**_obs("mint-ladder", 42.0, 4.0, observation_id="cross-40k"), "fdv_proxy": 42_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    recorder.record_observation({**_obs("mint-ladder", 43.0, 20.0, observation_id="retrace"), "fdv_proxy": 38_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    summary = recorder.finalize()

    events = _jsonl(tmp_path / "valuation_ladder_events.jsonl")
    bands = [row["band_usd"] for row in events if row["event_type"] == "valuation_band_cross"]
    assert 30_000 in bands
    assert 35_000 in bands
    assert 36_000 in bands
    assert 40_000 in bands
    first_40k = [row for row in events if row["event_type"] == "valuation_band_cross" and row["band_usd"] == 40_000][0]
    assert first_40k["seconds_since_previous_band"] == 0.0
    assert first_40k["previous_band_usd"] == 36_000
    assert first_40k["true_curve_progress_pct"] == 42.0
    assert first_40k["source_observation_id"] == "cross-40k"

    paths = _jsonl(tmp_path / "valuation_ladder_paths.jsonl")
    assert len(paths) == 1
    path = paths[0]
    assert path["seconds_30k_to_40k"] == 3.0
    assert path["seconds_30k_to_60k"] is None
    assert path["max_valuation_after_30k"] == 42_000
    assert path["min_valuation_after_30k"] == 30_500
    assert path["max_retrace_pct_after_30k"] == round((42_000 - 38_000) / 42_000 * 100.0, 6)
    assert path["stalled_after_40k_no_next_10s"] is True
    assert path["path_ended_after_40k_before_next_band"] is True
    assert summary["valuation_ladder_events_written"] == len(events)
    assert summary["valuation_ladder_paths_written"] == 1
    assert summary["tokens_crossing_30k"] == 1
    assert summary["tokens_crossing_40k"] == 1
    assert summary["median_seconds_30k_to_40k"] == 3.0
    assert summary["count_stalled_after_40k_10s"] == 1


def test_wallet_dev_checkpoints_are_explicit_and_creator_history_is_prior_only(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(
        {
            **_launch("mint-wallet"),
            "creator": "creator-a",
            "creator_history": [
                {"mint": "prior", "launch_received_at": 900.0, "migrated": True, "max_fdv_band": 60_000},
                {"mint": "future", "launch_received_at": 1100.0, "migrated": True, "max_fdv_band": 100_000},
            ],
        }
    )
    recorder.record_observation(
        {
                **_obs("mint-wallet", 41.0, 2.0, observation_id="cross-36k"),
                "fdv_proxy": 36_500,
                "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
                "creator_sell_before_40k": True,
            }
    )
    summary = recorder.finalize()

    checkpoints = _jsonl(tmp_path / "wallet_dev_checkpoints.jsonl")
    birth_checkpoint = [row for row in checkpoints if row["checkpoint_type"] == "birth"][0]
    valuation_checkpoint = [
        row for row in checkpoints if row["checkpoint_type"] == "valuation_band" and row["checkpoint_band_usd"] == 36_000
    ][0]
    assert birth_checkpoint["creator_address"] == "creator-a"
    assert birth_checkpoint["wallet_metrics_status"] == "not_available"
    assert birth_checkpoint["top_1_buyer_share"] is None
    assert birth_checkpoint["creator_history_status"] == "available"
    assert birth_checkpoint["creator_prior_launch_count_before_this_launch"] == 1
    assert birth_checkpoint["creator_prior_migration_count_before_this_launch"] == 1
    assert valuation_checkpoint["creator_sell_before_40k"] is True
    assert valuation_checkpoint["creator_prior_max_fdv_band_before_this_launch"] == 60_000
    assert summary["wallet_dev_checkpoints_written"] == len(checkpoints)
    assert summary["creator_history_available_count"] >= 1
    assert summary["wallet_metrics_not_available_count"] >= 1


def test_decode_coverage_by_route_status_and_missing_valuation_reason(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(
        {
            **_launch("mint-direct"),
            "source_type": "transaction_subscribe",
            "raw_decoded_launch_payload": {"decode_route": "direct"},
        }
    )
    recorder.process_birth(
        {
            **_launch("mint-wrapped"),
            "source_type": "transaction_subscribe",
            "raw_decoded_launch_payload": {"decode_route": "wrapped_compact"},
        }
    )

    recorder.record_observation({**_obs("mint-direct", 41.0, 1.0), "fdv_proxy": 30_500, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    recorder.record_observation(
        {
            "mint": "mint-wrapped",
            "received_at": 1001.0,
            "decode_status": "decode_failed",
            "error_reason": "account_decode_failed",
            "raw_curve_state": {},
            "observation_id": "decode-failed",
        }
    )
    summary = recorder.finalize()

    assert summary["decode_coverage_by_source_route"]["transaction_subscribe:direct"]["decoded"] == 1
    assert summary["decode_coverage_by_source_route"]["transaction_subscribe:wrapped_compact"]["decode_failed"] == 1
    assert summary["progress_decode_coverage_by_source_route"]["transaction_subscribe:direct"]["decoded_exact"] == 1
    assert summary["progress_decode_coverage_by_source_route"]["transaction_subscribe:wrapped_compact"]["unavailable"] == 1
    assert summary["valuation_coverage_by_source_route"]["transaction_subscribe:direct"]["present"] == 1
    assert summary["valuation_coverage_by_source_route"]["transaction_subscribe:wrapped_compact"]["missing"] == 1
    assert summary["valuation_missing_reason_counts"]["curve_decode_failed"] == 1


def test_transaction_live_smoke_wallet_checkpoints_do_not_block_first_observation(tmp_path: Path) -> None:
    clock = {"now": 3000.0}

    class WalletCheckpointStreamingSource:
        source_name = "wallet_checkpoint_streaming_fake"
        actual_duration_seconds = 300.0
        websocket_closed_early = False
        websocket_close_reason = None

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True}

        def iter_notifications(self, duration_seconds: float) -> list[dict]:
            return []

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            clock["now"] = 3000.05
            on_event(
                {
                    "received_at": 3000.0,
                    "signature": "sig-wallet-stream",
                    "slot": 1,
                    "decoded_rows": [
                        {
                            "signature": "sig-wallet-stream",
                            "slot": 1,
                            "mint": "mint-wallet-stream",
                            "bonding_curve": "curve-wallet-stream",
                            "source_instruction_level": "top_level",
                            "creator": "creator-stream",
                        }
                    ],
                }
            )
            clock["now"] = 3300.0

    probe = FakeCurveStateProbe(
        {
            "mint-wallet-stream": {
                "bonding_curve": "curve-wallet-stream",
                "account_state": {
                    "real_token_reserves": 317_240_000_000_000,
                    "token_total_supply": 1_000_000_000_000_000,
                    "token_decimals": 6,
                    "complete": False,
                },
                "fdv_proxy": 36_500,
                "observed_at": 3000.2,
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=WalletCheckpointStreamingSource(),
        curve_probe=probe,
        now_fn=lambda: clock["now"],
    )

    assert summary["curve_observation_attempts"] == 1
    assert summary["birth_to_first_curve_observation_latency_ms"]["median"] < 1000
    assert summary["first_curve_observation_under_1s"] == 1
    assert summary["wallet_dev_checkpoints_written"] >= 2


def test_probe_retry_success_records_attempts_and_final_success_without_duplicate_crossings(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 4000.0,
                "signature": "sig-retry",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-retry",
                        "slot": 1,
                        "mint": "mint-retry",
                        "bonding_curve": "decoded-curve",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-retry": [
                {
                    "probe_status": "failed",
                    "failure_reason": "account_not_found",
                    "decode_status": "decode_failed",
                    "observed_at": 4000.1,
                },
                {
                    "probe_status": "success",
                    "bonding_curve": "decoded-curve",
                    "account_state": {
                        "real_token_reserves": 317_240_000_000_000,
                        "token_total_supply": 1_000_000_000_000_000,
                        "token_decimals": 6,
                        "virtual_sol_reserves": 20_000_000_000,
                        "virtual_token_reserves": 800_000_000_000_000,
                        "complete": False,
                    },
                    "fdv_proxy": 40_000,
                    "fdv_usd": 40_000,
                    "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
                    "observed_at": 4000.2,
                },
                {
                    "probe_status": "success",
                    "bonding_curve": "decoded-curve",
                    "account_state": {
                        "real_token_reserves": 317_240_000_000_000,
                        "token_total_supply": 1_000_000_000_000_000,
                        "token_decimals": 6,
                        "virtual_sol_reserves": 20_000_000_000,
                        "virtual_token_reserves": 800_000_000_000_000,
                        "complete": False,
                    },
                    "fdv_proxy": 41_000,
                    "fdv_usd": 41_000,
                    "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
                    "observed_at": 4000.3,
                },
            ]
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            probe_retry_delays_ms=(0, 0),
        ),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 4000.3,
    )

    attempts = _jsonl(tmp_path / "probe_attempts.jsonl")
    observations = _jsonl(tmp_path / "curve_observations.jsonl")
    valuation_bands = [
        row for row in _jsonl(tmp_path / "threshold_crossings.jsonl") if row.get("crossing_type") == "valuation_band"
    ]
    assert summary["first_attempt_success_count"] == 0
    assert summary["retry_success_count"] == 1
    assert summary["final_account_not_found_count"] == 0
    assert summary["median_attempts_until_success"] == 2
    assert [row["probe_attempt_index"] for row in attempts] == [0, 1]
    assert observations[-1]["final_for_mint"] is True
    assert observations[-1]["account_found"] is True
    assert len([row for row in valuation_bands if row["threshold_usd"] == 40_000]) == 1


def test_probe_retry_failure_records_final_account_not_found(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 4100.0,
                "signature": "sig-fail",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-fail",
                        "slot": 1,
                        "mint": "mint-fail",
                        "bonding_curve": "decoded-curve",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-fail": [
                {"probe_status": "failed", "failure_reason": "account_not_found", "decode_status": "decode_failed", "observed_at": 4100.1},
                {"probe_status": "failed", "failure_reason": "account_not_found", "decode_status": "decode_failed", "observed_at": 4100.2},
            ]
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, probe_retry_delays_ms=(0,)),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 4100.2,
    )

    observations = _jsonl(tmp_path / "curve_observations.jsonl")
    assert summary["first_attempt_success_count"] == 0
    assert summary["retry_success_count"] == 0
    assert summary["final_account_not_found_count"] == 1
    assert observations[-1]["final_for_mint"] is True
    assert observations[-1]["account_found"] is False


def test_valuation_units_require_confirmed_usd_for_ladder_crossings(tmp_path: Path) -> None:
    unresolved = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path / "raw", sample_rate_percent=100))
    unresolved.process_birth(_launch("mint-raw"))
    unresolved.record_observation({**_obs("mint-raw", 41.0, 1.0), "fdv_proxy": 40_000, "fdv_units": "raw"})
    unresolved_summary = unresolved.finalize()
    assert unresolved_summary["valuation_units_status_counts"]["raw_unresolved"] == 1
    assert unresolved_summary["tokens_crossing_30k"] == 0

    converted = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path / "converted", sample_rate_percent=100, sol_usd=135)
    )
    converted.process_birth(_launch("mint-sol"))
    converted.record_observation({**_obs("mint-sol", 41.0, 1.0), "fdv_proxy": 250, "fdv_units": "sol"})
    converted_summary = converted.finalize()
    observation = _jsonl(tmp_path / "converted" / "curve_observations.jsonl")[0]
    assert observation["fdv_proxy_raw"] == 250
    assert observation["fdv_proxy_sol"] == 250
    assert observation["fdv_proxy_usd"] == 33_750
    assert observation["valuation_units_status"] == "sol_converted_to_usd"
    assert converted_summary["tokens_crossing_30k"] == 0
    assert converted_summary["valuation_ladder_suppressed_untrusted_count"] == 1


def test_quote_asset_normalization_handles_sol_usdc_and_unknown_without_ladder_trust(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135)
    )
    recorder.process_birth({**_launch("mint-sol"), "quote_mint": recorder_module.SOL_MINT})
    recorder.process_birth({**_launch("mint-usdc"), "quote_mint": recorder_module.USDC_MINT})
    recorder.process_birth({**_launch("mint-unknown"), "quote_mint": "unknown-quote-mint"})

    recorder.record_observation(
        {**_obs("mint-sol", 41.0, 1.0), "quote_mint": recorder_module.SOL_MINT, "fdv_proxy": 10, "fdv_units": "quote"}
    )
    recorder.record_observation(
        {**_obs("mint-usdc", 42.0, 1.0), "quote_mint": recorder_module.USDC_MINT, "fdv_proxy": 10, "fdv_units": "quote"}
    )
    recorder.record_observation(
        {**_obs("mint-unknown", 43.0, 1.0), "quote_mint": "unknown-quote-mint", "fdv_proxy": 10, "fdv_units": "quote"}
    )
    summary = recorder.finalize()

    births = {row["mint"]: row for row in _jsonl(tmp_path / "birth_audit.jsonl")}
    observations = {row["mint"]: row for row in _jsonl(tmp_path / "curve_observations.jsonl")}
    assert births["mint-sol"]["quote_asset"] == "SOL"
    assert births["mint-usdc"]["quote_asset"] == "USDC"
    assert births["mint-unknown"]["quote_asset"] == "unknown"
    assert observations["mint-sol"]["quote_to_usd_rate"] == 135
    assert observations["mint-sol"]["quote_to_usd_source"] == "manual_cli_sol_usd"
    assert observations["mint-sol"]["valuation_usd"] == 1350
    assert observations["mint-usdc"]["quote_to_usd_rate"] == 1.0
    assert observations["mint-usdc"]["quote_to_usd_source"] == "usdc_assumed_1"
    assert observations["mint-usdc"]["valuation_usd"] == 10
    assert observations["mint-unknown"]["valuation_usd"] is None
    assert observations["mint-unknown"]["valuation_units_status"] == "unknown_quote_asset"
    assert summary["births_by_quote_asset"]["SOL"] == 1
    assert summary["births_by_quote_asset"]["USDC"] == 1
    assert summary["births_by_quote_asset"]["unknown"] == 1
    assert summary["curve_observations_by_quote_asset"]["SOL"] == 1
    assert summary["curve_observations_by_quote_asset"]["USDC"] == 1
    assert summary["unknown_quote_count"] == 1
    assert summary["valuation_ladder_events_written"] == 0


def test_sol_usd_resolver_prefers_cli_then_env_then_pyth(monkeypatch) -> None:
    monkeypatch.delenv("MTP_SOL_USD", raising=False)
    monkeypatch.delenv("SOL_USD", raising=False)
    monkeypatch.setattr(recorder_module, "_fetch_sol_usd_from_pyth_hermes", lambda timeout_seconds=3.0: 142.25)

    cli = recorder_module._resolve_sol_usd_for_run(141.0, allow_auto=True)
    assert cli["sol_usd"] == 141.0
    assert cli["sol_usd_source"] == "manual_cli_sol_usd"
    assert cli["sol_usd_status"] == "available"

    monkeypatch.setenv("MTP_SOL_USD", "143.5")
    env = recorder_module._resolve_sol_usd_for_run(None, allow_auto=True)
    assert env["sol_usd"] == 143.5
    assert env["sol_usd_source"] == "env_mtp_sol_usd"
    assert env["sol_usd_status"] == "available"

    monkeypatch.delenv("MTP_SOL_USD", raising=False)
    auto = recorder_module._resolve_sol_usd_for_run(None, allow_auto=True)
    assert auto["sol_usd"] == 142.25
    assert auto["sol_usd_source"] == "pyth_hermes_sol_usd"
    assert auto["sol_usd_status"] == "available"


def test_sol_usd_missing_blocks_sol_market_cap_thesis_gate() -> None:
    blocked = evaluate_t007_thesis_ready_gate(
        {
            "live_feature_families": [
                *recorder_module.T007_H001_REQUIRED_FEATURE_FAMILIES,
                *recorder_module.T007_ADVANCED_FEATURE_FAMILIES,
            ],
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "curve_observations_by_quote_asset": {"SOL": 10},
            "sol_usd": None,
            "sol_usd_status": "missing",
        }
    )
    assert blocked["sol_usd_required"] is True
    assert blocked["sol_usd_available"] is False
    assert "sol_usd_missing_for_sol_market_cap" in blocked["blocking_reasons"]
    assert blocked["can_run_60m_thesis_scan"] is False

    allowed = evaluate_t007_thesis_ready_gate(
        {
            "live_feature_families": [
                *recorder_module.T007_H001_REQUIRED_FEATURE_FAMILIES,
                *recorder_module.T007_ADVANCED_FEATURE_FAMILIES,
            ],
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "bonding_curve_market_cap_quote_asset_SOL_count": 10,
            "sol_usd": 142.25,
            "sol_usd_status": "available",
            "sol_usd_source": "pyth_hermes_sol_usd",
        }
    )
    assert allowed["sol_usd_required"] is True
    assert allowed["sol_usd_available"] is True
    assert "sol_usd_missing_for_sol_market_cap" not in allowed["blocking_reasons"]


def test_final_summary_counts_velocity_acceleration_and_token_path_outputs(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )
    recorder.process_birth(_launch("mint-feature-counts"))
    recorder.record_observation({**_obs("mint-feature-counts", 41.0, 1.0), "received_at": 101.0})
    recorder.record_observation({**_obs("mint-feature-counts", 44.0, 6.0), "received_at": 106.0})
    recorder.record_observation({**_obs("mint-feature-counts", 48.0, 12.0), "received_at": 112.0})

    summary = recorder.finalize()

    assert summary["curve_velocity_events_written"] > 0
    assert summary["curve_acceleration_events_written"] > 0
    assert summary["token_path_summary_rows"] == 1
    assert summary["token_path_summary_written"] == 1


def test_reserve_fdv_comparison_is_persisted(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )
    recorder.process_birth(_launch("mint-reserve"))
    recorder.record_observation(
        {
            **_obs("mint-reserve", 41.0, 1.0),
            "fdv_proxy": 25,
            "fdv_units": "sol",
            "raw_curve_state": {
                "decode_status": "decoded",
                "virtual_sol_reserves": 20_000_000_000,
                "virtual_token_reserves": 800_000_000_000_000,
                "real_token_reserves": 317_240_000_000_000,
                "token_total_supply": 1_000_000_000_000_000,
                "token_decimals": 6,
                "quote_type": "sol",
            },
        }
    )

    observation = _jsonl(tmp_path / "curve_observations.jsonl")[0]
    assert observation["reserve_fdv_sol"] == 25
    assert observation["reserve_fdv_usd"] == 2500
    assert observation["reserve_fdv_status"] == "computed"
    assert observation["bonding_curve_market_cap_quote"] == 25
    assert observation["bonding_curve_market_cap_usd"] == 2500
    assert observation["bonding_curve_market_cap_quote_asset"] == "SOL"
    assert observation["bonding_curve_market_cap_status"] == "computed"
    assert observation["valuation_usd"] == 2500
    assert observation["valuation_source_field"] == "bonding_curve_market_cap_usd"
    assert observation["valuation_market_cap_confirmed"] is True
    assert observation["valuation_ladder_trust_status"] == "market_cap_confirmed"
    assert observation["fdv_proxy_agreement_status"] == "matches_existing_proxy"


def test_usdc_bonding_curve_market_cap_formula_is_confirmed_and_ladder_safe(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-usdc-curve"), "quote_mint": recorder_module.USDC_MINT})
    recorder.record_observation(
        {
            **_obs("mint-usdc-curve", 41.0, 1.0),
            "quote_mint": recorder_module.USDC_MINT,
            "raw_curve_state": {
                "decode_status": "decoded",
                "virtual_quote_reserves": 20_000_000_000,
                "virtual_token_reserves": 800_000_000_000_000,
                "real_token_reserves": 317_240_000_000_000,
                "token_total_supply": 1_000_000_000_000_000,
                "token_decimals": 6,
                "quote_decimals": 6,
                "quote_mint": recorder_module.USDC_MINT,
                "quote_type": "usdc",
            },
        }
    )
    summary = recorder.finalize()

    observation = _jsonl(tmp_path / "curve_observations.jsonl")[0]
    valuation_bands = [
        row for row in _jsonl(tmp_path / "threshold_crossings.jsonl") if row.get("crossing_type") == "valuation_band"
    ]
    assert observation["bonding_curve_price_quote"] == 0.000025
    assert observation["bonding_curve_market_cap_quote"] == 25_000
    assert observation["bonding_curve_market_cap_usd"] == 25_000
    assert observation["bonding_curve_market_cap_quote_asset"] == "USDC"
    assert observation["reserve_fdv_sol"] is None
    assert observation["reserve_fdv_usd"] == 25_000
    assert observation["valuation_usd"] == 25_000
    assert observation["valuation_units_status"] == "bonding_curve_market_cap_confirmed"
    assert observation["valuation_market_cap_confirmed"] is True
    assert [row["threshold_usd"] for row in valuation_bands] == [15_000, 20_000, 25_000]
    assert summary["valuation_ladder_market_cap_confirmed_count"] == 1


def test_decoded_curve_quote_type_overrides_unknown_birth_quote_for_market_cap(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )
    recorder.process_birth({**_launch("mint-unknown-birth-quote"), "quote_asset": "unknown", "quote_mint": None})
    recorder.record_observation(
        {
            **_obs("mint-unknown-birth-quote", 41.0, 1.0),
            "quote_asset": "unknown",
            "raw_curve_state": {
                "decode_status": "decoded",
                "layout_version": "pumpfun_classic_v1",
                "quote_type": "sol",
                "quote_mint": None,
                "virtual_sol_reserves": 110_307_329_530,
                "virtual_token_reserves": 881_202_173_712_173,
                "real_token_reserves": 601_302_173_712_173,
                "token_total_supply": 1_000_000_000_000_000,
                "token_decimals": 6,
            },
        }
    )

    observation = _jsonl(tmp_path / "curve_observations.jsonl")[0]
    assert observation["quote_asset"] == "SOL"
    assert observation["bonding_curve_market_cap_quote_asset"] == "SOL"
    assert observation["bonding_curve_market_cap_usd"] is not None
    assert observation["valuation_market_cap_confirmed"] is True


def test_mayhem_bonding_curve_market_cap_candidate_does_not_unlock_ladder(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )
    recorder.process_birth({**_launch("mint-mayhem-curve"), "source_type": "mayhem", "quote_mint": recorder_module.SOL_MINT})
    recorder.record_observation(
        {
            **_obs("mint-mayhem-curve", 8.44, 1.0),
            "quote_mint": recorder_module.SOL_MINT,
            "is_mayhem": True,
            "raw_curve_state": {
                "decode_status": "decoded",
                "virtual_sol_reserves": 20_000_000_000,
                "virtual_token_reserves": 800_000_000_000_000,
                "real_token_reserves": 317_240_000_000_000,
                "token_total_supply": 1_000_000_000_000_000,
                "token_decimals": 6,
                "quote_type": "sol",
            },
        }
    )
    summary = recorder.finalize()

    observation = _jsonl(tmp_path / "curve_observations.jsonl")[0]
    valuation_bands = [
        row for row in _jsonl(tmp_path / "threshold_crossings.jsonl") if row.get("crossing_type") == "valuation_band"
    ]
    assert observation["bonding_curve_market_cap_usd"] == 2500
    assert observation["valuation_usd"] is None
    assert observation["valuation_market_cap_confirmed"] is False
    assert observation["valuation_ladder_trust_status"] == "raw_unresolved"
    assert valuation_bands == []
    assert summary["valuation_ladder_market_cap_confirmed_count"] == 0


def test_pumpswap_pool_market_cap_stays_separate_from_liquidity_for_sol_quote(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )
    recorder.process_birth({**_launch("mint-pool-sol"), "quote_mint": recorder_module.SOL_MINT})

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-pool-sol",
            "pool_or_pair_address": "pool-sol",
            "quote_asset": "SOL",
            "quote_mint": recorder_module.SOL_MINT,
            "migration_received_at": 1005.0,
            "observation_received_at": 1006.0,
            "base_reserve_scaled": 1_000_000_000.0,
            "quote_reserve_scaled": 1330.0,
            "pool_liquidity_quote": 2670.0,
            "token_total_supply_scaled": 1_000_000_000.0,
        }
    )

    written = [item for item in _jsonl(tmp_path / "post_migration_observations.jsonl") if item.get("mint") == "mint-pool-sol"][0]
    assert row["pool_market_cap_quote"] == 1330
    assert row["pool_market_cap_usd"] == 133_000
    assert row["pool_liquidity_usd"] == 267_000
    assert row["pool_market_cap_quote_asset"] == "SOL"
    assert row["pool_market_cap_status"] == "computed"
    assert row["valuation_ladder_used"] is False
    assert written["pool_market_cap_usd"] == 133_000
    assert written["pool_liquidity_usd"] == 267_000


def test_pumpswap_pool_market_cap_supports_usdc_quote(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-pool-usdc"), "quote_mint": recorder_module.USDC_MINT})

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-pool-usdc",
            "pool_or_pair_address": "pool-usdc",
            "quote_asset": "USDC",
            "quote_mint": recorder_module.USDC_MINT,
            "migration_received_at": 1005.0,
            "observation_received_at": 1006.0,
            "base_reserve_scaled": 1_000_000_000.0,
            "quote_reserve_scaled": 25_000.0,
            "pool_liquidity_quote": 50_000.0,
            "token_total_supply_scaled": 1_000_000_000.0,
        }
    )

    quote_rows = [
        item for item in _jsonl(tmp_path / "executable_quote_observations.jsonl") if item.get("mint") == "mint-pool-usdc"
    ]
    assert row["quote_to_usd_rate"] == 1.0
    assert row["pool_price_quote_per_token"] == 0.000025
    assert row["pool_market_cap_quote"] == 25_000
    assert row["pool_market_cap_usd"] == 25_000
    assert row["pool_liquidity_usd"] == 50_000
    assert row["pool_market_cap_quote_asset"] == "USDC"
    assert row["pool_market_cap_status"] == "computed"
    assert quote_rows
    assert quote_rows[0]["expected_output_quote_usd"] is not None


def test_pumpswap_pool_market_cap_supports_raw_sol_reserves(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=100)
    )

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-pool-raw-sol",
            "pool_or_pair_address": "pool-raw-sol",
            "quote_asset": "SOL",
            "quote_mint": recorder_module.SOL_MINT,
            "base_reserve_raw": 1_000_000_000_000_000,
            "quote_reserve_raw": 1_330_000_000_000,
            "base_decimals": 6,
            "quote_decimals": 9,
            "pool_liquidity_quote": 2670.0,
            "token_total_supply_raw": 1_000_000_000_000_000,
            "token_decimals": 6,
        }
    )

    assert row["pool_market_cap_quote"] == 1330
    assert row["pool_market_cap_usd"] == 133_000
    assert row["pool_market_cap_status"] == "computed"


def test_capacity_rejections_are_summarized_by_minute_and_route(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1)
    )
    recorder.process_birth({**_launch("mint-a", received_at=1000), "source_type": "transaction_subscribe", "decode_route": "direct"})
    recorder.process_birth({**_launch("mint-b", received_at=1061), "source_type": "transaction_subscribe", "decode_route": "wrapped_compact"})
    summary = recorder.finalize()
    assert summary["capacity_rejected_by_minute"] == {"17": 1}
    assert summary["capacity_rejected_by_route"] == {"transaction_subscribe:wrapped_compact": 1}
    assert summary["active_tracking_still_active_at_finalization"] == 1


def test_axiom_reconciliation_reports_each_pipeline_stage(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-seen"), "source_type": "transaction_subscribe"})
    recorder.record_observation({**_obs("mint-seen", 41.0, 1.0), "fdv_proxy": 250, "fdv_units": "sol"})
    recorder.finalize()

    output = run_axiom_reconciliation(tmp_path, ["mint-seen", "mint-missing"])
    rows = _jsonl(tmp_path / "axiom_reconciliation.jsonl")
    csv_text = (tmp_path / "axiom_reconciliation.csv").read_text()
    seen = [row for row in rows if row["mint"] == "mint-seen"][0]
    missing = [row for row in rows if row["mint"] == "mint-missing"][0]
    assert output["axiom_reconciliation_rows"] == 2
    assert seen["seen_by_transaction_subscribe"] is True
    assert seen["normalized_as_unique_birth"] is True
    assert seen["admitted"] is True
    assert seen["curve_probed"] is True
    assert seen["decoded_successfully"] is True
    assert "mint-seen" in csv_text
    assert missing["seen_by_transaction_subscribe"] is False


def test_high_fdv_without_migration_increments_diagnostics(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-high-fdv"))
    recorder.record_observation({**_obs("mint-high-fdv", 8.0, 1.0), "fdv_proxy": 120_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    summary = recorder.finalize()

    candidates = _jsonl(tmp_path / "migration_candidates.jsonl")
    assert summary["high_fdv_without_migration_event_count"] == 1
    assert summary["tokens_crossing_60k_without_migration_event"] == 1
    assert summary["tokens_crossing_100k_without_migration_event"] == 1
    assert summary["tokens_crossing_250k_without_migration_event"] == 0
    assert summary["migration_candidates_seen"] == 1
    assert candidates[0]["candidate_reason"] == "high_fdv_without_migration_event"
    assert candidates[0]["migration_candidate_not_confirmed"] is True


def test_complete_true_emits_migration_event_and_counts_signal(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-complete"))
    recorder.record_observation({**_obs("mint-complete", 99.0, 1.0, complete=True), "fdv_proxy": 80_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    summary = recorder.finalize()

    migrations = _jsonl(tmp_path / "migration_events.jsonl")
    assert summary["migration_events_written"] == 1
    assert summary["complete_true_count"] == 1
    assert migrations[0]["migration_signal_source"] == "complete_flag_true"


def test_zero_reserve_and_progress_100_emit_migration_events(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-zero"))
    recorder.process_birth(_launch("mint-progress"))
    recorder.record_observation(
        {
            **_obs("mint-zero", 100.0, 1.0),
            "progress_pct_status": "decoded_candidate",
            "real_token_reserves_scaled": 0.0,
            "fdv_proxy": 90_000,
            "fdv_units": "usd",
            "valuation_market_cap_confirmed": True,
        }
    )
    recorder.record_observation({**_obs("mint-progress", 100.0, 2.0), "progress_pct_status": "decoded_candidate", "fdv_proxy": 95_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    summary = recorder.finalize()

    migrations = _jsonl(tmp_path / "migration_events.jsonl")
    assert summary["reserve_zero_count"] == 1
    assert summary["progress_100pct_count"] == 2
    assert summary["migration_events_written"] == 2
    assert {row["migration_signal_source"] for row in migrations} >= {"reserve_zero_or_near_zero", "progress_100pct"}


def test_explicit_migrate_and_dex_pair_signals_count_as_migration(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-log"))
    recorder.process_birth(_launch("mint-dex"))
    recorder.record_observation({**_obs("mint-log", 55.0, 1.0), "explicit_migrate_log": True, "fdv_proxy": 60_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    recorder.record_observation({**_obs("mint-dex", 55.0, 2.0), "dex_pair_signal": True, "fdv_proxy": 60_000, "fdv_units": "usd", "valuation_market_cap_confirmed": True})
    summary = recorder.finalize()

    assert summary["explicit_migrate_log_count"] == 1
    assert summary["dex_pair_signal_count"] == 1
    assert summary["migration_events_written"] == 2


def test_max_active_tracking_config_is_recorded_and_larger_cap_admits_more(tmp_path: Path) -> None:
    low = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path / "low", sample_rate_percent=100, max_active_tracking=1))
    high = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path / "high", sample_rate_percent=100, max_active_tracking=3))
    launches = [_launch(f"mint-cap-{idx}", received_at=1000 + idx) for idx in range(3)]
    for launch in launches:
        low.process_birth(launch)
        high.process_birth(launch)
    low_summary = low.finalize()
    high_summary = high.finalize()

    assert low_summary["max_active_tracking"] == 1
    assert high_summary["max_active_tracking"] == 3
    assert low_summary["admitted_births"] == 1
    assert high_summary["admitted_births"] == 3
    assert low_summary["capacity_rejected_births"] == 2
    assert high_summary["capacity_rejected_births"] == 0


def test_axiom_reconciliation_readme_is_written_without_axiom_list(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    summary = recorder.finalize()

    readme = tmp_path / "axiom_reconciliation_README.md"
    assert readme.exists()
    assert "--mode axiom-reconcile" in readme.read_text()
    assert summary["axiom_reconciliation_readme_path"].endswith("axiom_reconciliation_README.md")


def test_unconfirmed_liquidity_like_valuation_does_not_emit_ladder_or_high_fdv_candidate(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth({**_launch("mint-mayhem-liquidity"), "source_type": "mayhem"})
    recorder.record_observation(
        {
            **_obs("mint-mayhem-liquidity", 8.44, 1.0),
            "fdv_proxy": 267_000,
            "fdv_units": "usd",
            "axiom_market_cap_usd": 133_000,
            "axiom_liquidity_usd": 267_000,
            "is_mayhem": True,
        }
    )
    summary = recorder.finalize()

    crossings = _jsonl(tmp_path / "threshold_crossings.jsonl")
    audit_rows = _jsonl(tmp_path / "valuation_formula_audit.jsonl")
    assert [row for row in crossings if row.get("crossing_type") == "valuation_band"] == []
    assert summary["valuation_present_count"] == 1
    assert summary["valuation_ladder_suppressed_untrusted_count"] == 1
    assert summary["valuation_band_crossings_by_band"].get("250000", 0) == 0
    assert summary["tokens_crossing_250k_without_migration_event"] == 0
    assert summary["migration_candidates_seen"] == 0
    assert audit_rows[0]["matches_axiom_liquidity"] is True
    assert audit_rows[0]["possible_2x_market_cap"] is True
    assert audit_rows[0]["valuation_formula_classification"] == "mayhem_unresolved"


def test_low_progress_token_finalizes_after_configured_timeout_and_admits_after_prune(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            low_progress_timeouts=((5.0, 60.0), (10.0, 120.0), (20.0, 300.0), (40.0, 600.0)),
        )
    )
    recorder.process_birth(_launch("mint-low", received_at=1000.0))
    recorder.record_observation(_obs("mint-low", 4.0, 1.0))

    admitted = recorder.process_birth(_launch("mint-new", received_at=1061.0))
    summary = recorder.build_summary()
    paths = _jsonl(tmp_path / "valuation_ladder_paths.jsonl")

    assert admitted["admitted"] is True
    assert admitted["admission_reason"] == "sample_admitted_after_prune"
    assert summary["active_pruned_count"] == 1
    assert summary["low_progress_timeout_count"] == 1
    assert summary["admission_after_prune_count"] == 1
    assert summary["capacity_rejected_after_prune_count"] == 0
    assert paths[0]["finalization_reason"] == "low_progress_timeout"
    assert paths[0]["last_progress_pct"] == 4.0
    assert paths[0]["highest_progress_pct"] == 4.0
    assert paths[0]["highest_threshold_crossed"] is None
    assert paths[0]["observations_count"] == 1
    assert paths[0]["pruned_due_to_low_progress"] is True
    assert paths[0]["high_progress_protected"] is False


def test_no_decode_token_finalizes_after_retry_window(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            no_decode_timeout_seconds=30.0,
        )
    )
    recorder.process_birth(_launch("mint-nodecode", received_at=1000.0))
    recorder.record_observation(
        {
            "mint": "mint-nodecode",
            "received_at": 1001.0,
            "decode_status": "decode_failed",
            "error_reason": "account_not_found",
        }
    )

    admitted = recorder.process_birth(_launch("mint-new", received_at=1031.0))
    summary = recorder.build_summary()
    paths = _jsonl(tmp_path / "valuation_ladder_paths.jsonl")

    assert admitted["admitted"] is True
    assert summary["no_decode_timeout_count"] == 1
    assert paths[0]["finalization_reason"] == "no_decode_timeout"
    assert paths[0]["observations_count"] == 1
    assert paths[0]["decoded_observations_count"] == 0


def test_high_progress_token_is_protected_from_capacity_pruning(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1)
    )
    recorder.process_birth(_launch("mint-high", received_at=1000.0))
    recorder.record_observation(_obs("mint-high", 45.0, 1.0))

    rejected = recorder.process_birth(_launch("mint-new", received_at=2000.0))
    summary = recorder.build_summary()

    assert rejected["admitted"] is False
    assert rejected["admission_reason"] == "capacity_rejected_active_tracking_limit_after_prune"
    assert recorder.states["mint-high"].stopped is False
    assert summary["capacity_rejected_after_prune_count"] == 1
    assert summary["active_pruned_count"] == 0
    assert summary["protected_high_progress_active_count"] == 1


def test_stale_low_progress_token_is_pruned_before_rejecting_new_sampled_birth(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            low_progress_timeouts=((5.0, 10.0), (10.0, 120.0), (20.0, 300.0), (40.0, 600.0)),
        )
    )
    recorder.process_birth(_launch("mint-stale", received_at=1000.0))
    recorder.record_observation(_obs("mint-stale", 2.0, 1.0))

    admitted = recorder.process_birth(_launch("mint-new", received_at=1011.0))
    summary = recorder.build_summary()

    assert admitted["admitted"] is True
    assert summary["stale_low_priority_pruned_count"] == 1
    assert summary["admission_after_prune_count"] == 1
    assert summary["capacity_rejected_births"] == 0


def test_capacity_rejected_after_prune_increments_only_when_pruning_cannot_free_capacity(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1)
    )
    recorder.process_birth(_launch("mint-protected", received_at=1000.0))
    recorder.record_observation(_obs("mint-protected", 80.0, 1.0))

    recorder.process_birth(_launch("mint-rejected", received_at=3000.0))
    summary = recorder.build_summary()

    assert summary["active_pruned_count"] == 0
    assert summary["admission_after_prune_count"] == 0
    assert summary["capacity_rejected_after_prune_count"] == 1


def test_watcher_status_includes_active_lifecycle_and_coverage_fields(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=2)
    )
    recorder.process_birth(_launch("mint-status-a", received_at=1000.0))
    recorder.record_observation(_obs("mint-status-a", 45.0, 1.0))
    recorder.process_birth(_launch("mint-status-b", received_at=1002.0))

    status = json.loads((tmp_path / "live_status.json").read_text())

    assert status["active_count_by_progress_tier"]["progress_40_to_60"] == 1
    assert status["active_count_by_progress_tier"]["no_decoded_progress"] == 1
    assert "active_count_by_age_bucket" in status
    assert status["protected_high_progress_active_count"] == 1
    assert status["effective_admitted_coverage"] == 1.0
    assert status["admitted_sample_pass_coverage"] == 1.0
    assert status["capacity_rejection_rate"] == 0.0
    for key in [
        "active_pruned_count",
        "low_progress_timeout_count",
        "no_decode_timeout_count",
        "admission_after_prune_count",
        "capacity_rejected_after_prune_count",
    ]:
        assert key in status


def test_local_staging_path_is_used_as_active_write_root(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    staging_root = tmp_path / "stage"

    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=legacy_root, staging_root=staging_root, sample_rate_percent=100)
    )

    assert recorder.output_root == staging_root
    assert (staging_root / "run_config.json").exists()
    assert not legacy_root.exists()
    run_config = json.loads((staging_root / "run_config.json").read_text())
    assert run_config["staging_root"] == str(staging_root)
    assert run_config["active_write_root"] == str(staging_root)
    assert run_config["storage_preflight_status"] == "ok"


def test_archive_root_is_only_used_after_finalization(tmp_path: Path) -> None:
    staging_root = tmp_path / "stage"
    archive_root = tmp_path / "archive"
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path / "legacy",
            staging_root=staging_root,
            archive_root=archive_root,
            archive_after_run=True,
            sample_rate_percent=100,
        )
    )
    recorder.process_birth(_launch("mint-archive"))

    assert not archive_root.exists()
    recorder.finalize()
    archive = recorder_module.archive_completed_run_if_requested(recorder, recorder.build_summary(final=True))

    assert archive["archive_status"] == "complete"
    assert archive_root.exists()
    assert (archive_root / "archive_manifest.json").exists()


def test_archive_failure_does_not_invalidate_local_finalized_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staging_root = tmp_path / "stage"
    archive_root = tmp_path / "archive"
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path / "legacy",
            staging_root=staging_root,
            archive_root=archive_root,
            archive_after_run=True,
            sample_rate_percent=100,
        )
    )
    recorder.process_birth(_launch("mint-archive-fail"))
    summary = recorder.finalize()

    def fail_archive(_source: Path, _destination: Path) -> dict:
        return {"archive_status": "failed", "errors": ["simulated_archive_failure"], "files_copied": 0, "bytes_copied": 0}

    monkeypatch.setattr(recorder_module, "_copy_run_folder_to_archive", fail_archive)
    archive = recorder_module.archive_completed_run_if_requested(recorder, summary)

    local_summary = json.loads((staging_root / "collector_summary.json").read_text())
    assert local_summary["run_finalized"] is True
    assert archive["archive_status"] == "failed"
    assert local_summary["archive_status"] == "failed"
    assert (staging_root / "collector_summary.json").exists()


def test_storage_preflight_catches_unwritable_staging_path(tmp_path: Path) -> None:
    staging_file = tmp_path / "not-a-directory"
    staging_file.write_text("not a directory")

    with pytest.raises(ValueError, match="storage preflight failed"):
        BondingCurveRecorderConfig(output_root=tmp_path / "legacy", staging_root=staging_file)


def test_storage_preflight_requires_archive_root_when_archive_after_run_enabled(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="archive_root is required"):
        BondingCurveRecorderConfig(output_root=tmp_path / "stage", archive_after_run=True)


def test_archive_manifest_is_written_after_transaction_live_smoke(tmp_path: Path) -> None:
    staging_root = tmp_path / "stage"
    archive_root = tmp_path / "archive"
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 6000.0,
                "signature": "sig-archive",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-archive",
                        "slot": 1,
                        "mint": "mint-archive-live",
                        "bonding_curve": "curve-archive-live",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-archive-live": {
                "bonding_curve": "curve-archive-live",
                "account_state": {
                    "real_token_reserves": 317_240_000_000_000,
                    "token_total_supply": 1_000_000_000_000_000,
                    "token_decimals": 6,
                    "complete": False,
                },
                "fdv_proxy": 20_000,
                "fdv_units": "usd",
                "observed_at": 6000.2,
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path / "legacy",
            staging_root=staging_root,
            archive_root=archive_root,
            archive_after_run=True,
            sample_rate_percent=100,
        ),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 6000.2,
    )

    manifest = json.loads((staging_root / "archive_manifest.json").read_text())
    archived_manifest = json.loads((archive_root / "archive_manifest.json").read_text())
    assert summary["archive_status"] == "complete"
    assert manifest["verification_status"] == "verified"
    assert archived_manifest["destination_archive_path"] == str(archive_root)
    assert (archive_root / "collector_summary.json").exists()


def test_local_retention_archives_older_finalized_runs_from_default_local_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_root = tmp_path / "local_forward"
    archive_root = tmp_path / "orico_forward"
    monkeypatch.setattr(recorder_module, "DEFAULT_BASE_ROOT", local_root)
    for idx in range(4):
        run = local_root / f"old-run-{idx}"
        run.mkdir(parents=True)
        (run / "collector_summary.json").write_text(
            json.dumps({"run_id": run.name, "run_status": "finalized", "run_finalized": True}),
            encoding="utf-8",
        )
        (run / "payload.txt").write_text(str(idx), encoding="utf-8")
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=local_root / "current-run",
            sample_rate_percent=100,
            local_retention_enabled=True,
            local_retention_keep_latest=3,
            local_retention_archive_root=archive_root,
        )
    )

    summary = recorder.build_summary(final=False)
    report = recorder_module.apply_local_retention_if_configured(recorder, summary)

    assert report["local_retention_status"] == "complete"
    assert report["local_retention_archived_count"] == 2
    assert (archive_root / "old-run-0" / "payload.txt").exists()
    assert (archive_root / "old-run-1" / "payload.txt").exists()
    assert (local_root / "old-run-0").is_symlink()
    assert (local_root / "current-run").is_dir()


def test_finalization_writes_partial_summary_on_artifact_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-partial"))
    original_append = recorder._append_jsonl

    def fail_final_wallet_checkpoint(filename: str, row: dict) -> None:
        if filename == "wallet_dev_checkpoints.jsonl":
            raise OSError("simulated wallet checkpoint failure")
        original_append(filename, row)

    monkeypatch.setattr(recorder, "_append_jsonl", fail_final_wallet_checkpoint)
    summary = recorder.finalize()

    assert summary["run_finalized"] is True
    assert summary["finalization_errors"]
    assert (tmp_path / "collector_summary.json").exists()
    assert (tmp_path / "collector_summary_partial.json").exists()
    status = json.loads((tmp_path / "live_status.json").read_text())
    assert status["run_status"] == "finalized_with_errors"


def test_watcher_status_reads_from_staging_path(tmp_path: Path) -> None:
    staging_root = tmp_path / "stage"
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path / "legacy", staging_root=staging_root, sample_rate_percent=100)
    )

    status = json.loads((staging_root / "live_status.json").read_text())
    assert status["output_folder"] == str(staging_root)
    assert status["active_write_root"] == str(staging_root)
    assert (staging_root / "t007_live_watcher.html").exists()
    assert not (tmp_path / "legacy" / "live_status.json").exists()


def test_market_cap_confirmed_value_can_emit_ladder(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-marketcap"))
    recorder.record_observation({**_obs("mint-marketcap", 41.0, 1.0), "market_cap_usd": 36_500})
    summary = recorder.finalize()

    valuation_bands = [
        row for row in _jsonl(tmp_path / "threshold_crossings.jsonl") if row.get("crossing_type") == "valuation_band"
    ]
    assert summary["valuation_ladder_market_cap_confirmed_count"] == 1
    assert summary["valuation_ladder_suppressed_untrusted_count"] == 0
    assert summary["tokens_crossing_36k"] == 1
    assert [row["threshold_usd"] for row in valuation_bands] == [15_000, 20_000, 25_000, 30_000, 35_000, 36_000]


def test_t007_live_status_and_watcher_are_written_with_required_stats(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    status_path = tmp_path / "live_status.json"
    watcher_path = tmp_path / "t007_live_watcher.html"
    assert status_path.exists()
    assert watcher_path.exists()
    status = json.loads(status_path.read_text())
    assert status["run_id"] == recorder.config.run_id
    assert status["run_status"] == "initialized"
    assert status["output_folder"] == str(tmp_path)
    for key in [
        "elapsed_time_seconds",
        "raw_notifications",
        "unique_birth_mints",
        "unique_births_per_min",
        "admitted_births",
        "sample_rejected",
        "capacity_rejected",
        "active_tracking_count",
        "curve_observations_written",
        "decode_success_count",
        "decode_error_count",
        "retry_success_count",
        "final_account_not_found",
        "queue_drops",
        "rpc_failures",
        "http_429",
        "progress_crossings_by_threshold",
        "complete_true_count",
        "migration_events",
        "last_heartbeat_timestamp",
        "valuation_ladder_emission_policy",
        "birth_decision_path_commit_count",
        "live_status_hot_path_force_disabled_count",
    ]:
        assert key in status
    assert "T007 True Curve Progress Watcher" in watcher_path.read_text()
    assert "10m collector + feature proof passed; 60m thesis readiness blocked" in watcher_path.read_text()
    assert "startup-boundary migration does not count as full-path evidence" in watcher_path.read_text()

    recorder.process_birth(_launch("mint-status"))
    recorder.record_observation({**_obs("mint-status", 60.0, 1.0), "progress_pct_status": "decoded_candidate"})
    updated = json.loads(status_path.read_text())
    assert updated["run_status"] == "running"
    assert updated["unique_birth_mints"] == 1
    assert updated["admitted_births"] == 1
    assert updated["curve_observations_written"] == 1
    assert updated["decode_success_count"] == 1
    assert updated["progress_crossings_by_threshold"]["60.0"] == 1
    assert updated["birth_decision_path_commit_count"] == 1
    assert updated["live_status_hot_path_force_disabled_count"] == 1


def test_t0116_finalized_live_status_clears_drain_timer(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            source_duration_seconds=600,
            followup_drain_seconds=180,
        )
    )
    recorder.started_at = time.time() - 608.0

    recorder._write_live_status("finalized", {"actual_source_duration_seconds": 600.5})

    status = json.loads((tmp_path / "live_status.json").read_text())
    assert status["runtime_phase"] == "finalized"
    assert status["source_remaining_seconds"] == 0.0
    assert status["drain_remaining_seconds"] == 0.0
    assert status["finalization_elapsed_seconds"] == 0.0
    assert status["finalization_overrun_seconds"] == 0.0
    assert status["finalization_stuck_warning"] is False


def test_t011_trade_flow_audit_writes_debug_and_flags_denominator_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE mint_identity (mint TEXT PRIMARY KEY, first_seen_at REAL, progress_decoded INTEGER DEFAULT 0)")
    connection.executemany(
        "INSERT INTO mint_identity VALUES (?, ?, ?)",
        [("mint-covered", 100.0, 1), ("mint-missing", 101.0, 1), ("mint-non-birth", 102.0, 0)],
    )
    connection.commit()
    connection.close()
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-covered", "admitted": True, "admission_reason": "sample_admitted", "received_at": 100.0},
            {"mint": "mint-missing", "admitted": True, "admission_reason": "sample_admitted", "received_at": 101.0},
        ],
    )
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-covered", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-missing", "decode_status": "decoded"}])
    _write_t007bc_jsonl(tmp_path, "holder_distribution_snapshots.jsonl", [{"mint": "mint-missing"}])
    (tmp_path / "canonical_sqlite_db_pointer.json").write_text(json.dumps({"canonical_db_path": str(db_path)}), encoding="utf-8")
    (tmp_path / "collector_summary.json").write_text(json.dumps({"unique_birth_mints": 2}), encoding="utf-8")
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {
                        "metric_id": "trade_flow_mint_coverage",
                        "numerator": 1,
                        "denominator": 3,
                        "ratio": 1 / 3,
                        "status": "fail",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = run_trade_flow_coverage_audit(tmp_path)

    assert summary["unique_birth_mints"] == 2
    assert summary["trade_flow_denominator"] == 3
    assert summary["trade_flow_missing_mints"] == 2
    assert summary["denominator_mismatch_flagged"] is True
    assert summary["missing_trade_flow_mints_by_category"]["admitted_no_trade_events_observed"] == 1
    assert summary["missing_trade_flow_mints_by_category"]["denominator_policy_non_birth_mint"] == 1
    assert summary["trade_flow_unconditional_birth_coverage"]["purpose"] == "diagnostic_only"
    assert summary["trade_flow_eventful_parse_coverage"]["purpose"] == "parser_writer_subscription_readiness"
    assert summary["trade_flow_eventful_parse_coverage"]["hard_long_scan_blocker"] is False
    assert summary["trade_flow_true_gap_mints_count"] == 0
    assert summary["trade_flow_no_event_mints_count"] == 1
    assert summary["denominator_policy_issue_count"] == 1
    rows = {row["mint"]: row for row in summary["missing_mints"]}
    assert rows["mint-non-birth"]["should_count_against_long_scan_readiness"] is False
    assert rows["mint-missing"]["failure_reason"] == "admitted_no_trade_events_observed"
    assert rows["mint-missing"]["should_count_against_long_scan_readiness"] is False
    assert summary["capacity_rejected_expected_to_require_trade_flow_coverage"] is False
    assert (tmp_path / "trade_flow_coverage_audit.json").exists()
    assert (tmp_path / "trade_flow_missing_mints_debug.json").exists()
    assert (tmp_path / "trade_flow_coverage_audit.md").exists()


def test_t011_trade_flow_audit_handles_missing_supervisor_metric(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE mint_identity (mint TEXT PRIMARY KEY, first_seen_at REAL, progress_decoded INTEGER DEFAULT 0)")
    connection.executemany("INSERT INTO mint_identity VALUES (?, ?, ?)", [("mint-covered", 100.0, 1), ("mint-missing", 101.0, 1)])
    connection.commit()
    connection.close()
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-covered", "admitted": True, "received_at": 100.0},
            {"mint": "mint-missing", "admitted": True, "received_at": 101.0},
        ],
    )
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-covered", "trade_flow_status": "available"}])
    (tmp_path / "canonical_sqlite_db_pointer.json").write_text(json.dumps({"canonical_db_path": str(db_path)}), encoding="utf-8")
    (tmp_path / "collector_summary.json").write_text(json.dumps({"unique_birth_mints": 2}), encoding="utf-8")

    summary = run_trade_flow_coverage_audit(tmp_path)

    assert summary["trade_flow_denominator"] == 2
    assert summary["trade_flow_covered_mints"] == 1
    assert summary["corrected_trade_flow_denominator"] == 2
    assert summary["corrected_trade_flow_covered_mints"] == 1


def test_t011_trade_flow_audit_categorizes_capacity_rejected_no_trade_events(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-covered", "admitted": True, "admission_reason": "sample_admitted", "received_at": 100.0},
            {
                "mint": "mint-capacity",
                "admitted": False,
                "admission_reason": "capacity_rejected_active_tracking_limit_after_prune",
                "received_at": 101.0,
            },
        ],
    )
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-covered", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(
        tmp_path,
        "curve_observations.jsonl",
        [
            {"mint": "mint-covered", "decode_status": "decoded"},
            {"mint": "mint-capacity", "decode_status": "decoded"},
        ],
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"unique_birth_mints": 2}), encoding="utf-8")

    summary = run_trade_flow_coverage_audit(tmp_path)
    row = {item["mint"]: item for item in summary["missing_mints"]}["mint-capacity"]

    assert summary["missing_trade_flow_mints_by_category"]["capacity_rejected_no_trade_events_observed"] == 1
    assert row["admission_status"] == "capacity_rejected"
    assert row["capacity_rejected"] is True
    assert row["raw_trade_like_events_seen"] is False
    assert row["trade_flow_writer_attempted"] is False
    assert row["should_count_against_long_scan_readiness"] is False
    assert summary["true_missing_collector_or_parser_gap_count"] == 0


def test_t011_trade_flow_audit_ignores_raw_trade_like_events_before_birth_for_gap(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-covered", "admitted": True, "admission_reason": "sample_admitted", "received_at": 100.0},
            {
                "mint": "mint-capacity",
                "admitted": False,
                "admission_reason": "capacity_rejected_active_tracking_limit_after_prune",
                "received_at": 200.0,
            },
        ],
    )
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-covered", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-capacity", "decode_status": "decode_failed"}])
    _write_t007bc_jsonl(
        tmp_path,
        "raw_trade_events.jsonl",
        [{"mint": "mint-capacity", "event_type": "buy", "received_at": 150.0, "signature": "sig-pre-birth"}],
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"unique_birth_mints": 2}), encoding="utf-8")

    summary = run_trade_flow_coverage_audit(tmp_path)
    row = {item["mint"]: item for item in summary["missing_mints"]}["mint-capacity"]

    assert row["raw_trade_like_events_before_birth_count"] == 1
    assert row["raw_trade_like_before_birth_only"] is True
    assert row["raw_trade_like_events_seen"] is False
    assert row["failure_reason"] == "capacity_rejected_no_trade_events_observed"
    assert row["should_count_against_long_scan_readiness"] is False
    assert summary["true_missing_collector_or_parser_gap_count"] == 0


def test_t011_migration_linkage_audit_writes_explicit_unlinked_reason(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "birth-mint", "admitted": True, "received_at": 100.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "migration-only",
                "signature": "sig-migration",
                "migration_received_at": 200.0,
                "pool_or_pair_address": "pool-1",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [])
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")
    (tmp_path / "lifecycle_coverage_summary.json").write_text(json.dumps({"migrated_unique_mints": 0, "decision_safe_full_paths": 0}), encoding="utf-8")

    summary = run_migration_linkage_audit(tmp_path)

    assert summary["global_migration_events_deduped"] == 1
    assert summary["lifecycle_migrated_unique_mints"] == 0
    assert summary["decision_safe_full_paths"] == 0
    assert summary["failure_reason_counts"]["migration_mint_not_in_birth_set"] == 1
    assert summary["migration_rows"][0]["failure_reason"] == "migration_mint_not_in_birth_set"
    assert (tmp_path / "migration_linkage_audit.json").exists()
    assert (tmp_path / "migration_linkage_audit.md").exists()


def test_t011_migration_linkage_rejects_migration_slot_before_birth_slot(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [{"mint": "mint-slot-order", "admitted": True, "received_at": 100.0, "slot": 200}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "curve_observations.jsonl",
        [{"mint": "mint-slot-order", "received_at": 120.0, "slot": 200, "decode_status": "decoded"}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "mint-slot-order",
                "signature": "sig-mig-slot",
                "pool_or_pair_address": "pool-slot",
                "migration_received_at": 130.0,
                "slot": 199,
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "mint-slot-order", "received_at": 140.0}])

    summary = run_migration_linkage_audit(tmp_path)
    row = summary["migration_rows"][0]

    assert summary["decision_safe_full_paths"] == 0
    assert summary["failure_reason_counts"]["migration_slot_before_birth_slot"] == 1
    assert row["birth_slot"] == 200
    assert row["migration_slot"] == 199
    assert row["failure_reason"] == "migration_slot_before_birth_slot"


def test_t011_migration_linkage_audit_classifies_startup_boundary_migration(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-startup", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "startup-migration",
                "signature": "sig-startup-migration",
                "migration_received_at": 100.5,
                "pool_or_pair_address": "pool-startup",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "startup-migration"}])
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")
    (tmp_path / "lifecycle_coverage_summary.json").write_text(
        json.dumps({"migrated_unique_mints": 1, "decision_safe_full_paths": 0}),
        encoding="utf-8",
    )

    summary = run_migration_linkage_audit(tmp_path)

    row = summary["migration_rows"][0]
    assert row["failure_reason"] == "migration_before_birth_source_ready"
    assert row["migration_readiness_failure_reason"] == "startup_boundary_migration_not_decision_safe"
    assert row["startup_boundary_migration"] is True
    assert row["decision_safe_full_path"] is False
    assert row["seconds_after_campaign_start"] == 0.5
    assert row["seconds_before_first_birth_source_event"] == 0.5
    assert summary["startup_boundary_migration_count"] == 1
    assert summary["steady_state_unlinked_migration_count"] == 0
    assert summary["migration_readiness_failure_reason_counts"]["startup_boundary_migration_not_decision_safe"] == 1
    assert "migration_mint_not_in_birth_set" not in summary["failure_reason_counts"]


def test_t011_cli_migration_linkage_audit_skips_live_storage_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "birth-mint", "admitted": True, "received_at": 100.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "birth-mint",
                "signature": "sig-migration",
                "migration_received_at": 200.0,
                "pool_or_pair_address": "pool-1",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "birth-mint", "received_at": 150.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "birth-mint"}])
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")
    (tmp_path / "lifecycle_coverage_summary.json").write_text(
        json.dumps({"migrated_unique_mints": 1, "decision_safe_full_paths": 1}),
        encoding="utf-8",
    )

    def fail_storage_preflight(_config: object) -> None:
        raise AssertionError("offline audit must not run live storage preflight")

    monkeypatch.setattr(recorder_module, "_run_storage_preflight", fail_storage_preflight)

    exit_code = recorder_module.main(["--mode", "audit-migration-linkage", "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "migration_linkage_audit_json=" in output
    assert (tmp_path / "migration_linkage_audit.json").exists()


def test_t0115_migration_capture_forensics_keeps_high_fdv_low_progress_as_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0115", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-t0115"}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "mint-missed", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-missed", "received_at": 300.0, "progress_pct": 21.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "migration_candidates.jsonl",
        [
            {
                "mint": "mint-missed",
                "received_at": 350.0,
                "candidate_reason": "high_fdv_without_migration_event",
                "valuation_usd": 125000,
                "progress_pct": 21.0,
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [])

    summary = run_migration_capture_forensics(tmp_path)

    assert summary["missed_candidate_count"] == 0
    assert summary["readiness_correction"] == "no_in_window_migration_observed"
    assert summary["derived_migration_likely_candidates"][0]["migration_grade_evidence"] is False
    assert summary["derived_migration_likely_candidates"][0]["classification"] == "high_fdv_diagnostic_not_migration_evidence"
    assert (tmp_path / "migration_capture_forensics.json").exists()
    assert (tmp_path / "migration_capture_forensics.md").exists()


def test_t0115_migration_capture_forensics_flags_migration_grade_derived_detector_miss(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0115-migration-grade", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-t0115-migration-grade"}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "mint-missed", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-missed", "received_at": 300.0, "progress_pct": 100.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "migration_candidates.jsonl",
        [
            {
                "mint": "mint-missed",
                "received_at": 350.0,
                "candidate_reason": "high_fdv_without_migration_event",
                "valuation_usd": 125000,
                "progress_pct": 100.0,
                "complete": True,
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [])

    summary = run_migration_capture_forensics(tmp_path)

    assert summary["missed_candidate_count"] == 1
    assert summary["readiness_correction"] == "in_window_migration_candidates_missed_by_detector"
    assert summary["derived_migration_likely_candidates"][0]["migration_grade_evidence"] is True
    assert summary["derived_migration_likely_candidates"][0]["classification"] == "migration_detector_missed_candidate"
    assert (tmp_path / "migration_capture_forensics.json").exists()
    assert (tmp_path / "migration_capture_forensics.md").exists()


def test_t0118_migration_capture_forensics_caps_large_detail_arrays(tmp_path: Path) -> None:
    raw_rows = [
        {
            "candidate_id": f"raw-{index}",
            "mint": f"mint-forensics-cap-{index}",
            "signature": f"sig-forensics-cap-{index}",
            "slot": index,
            "received_at": 200.0 + index,
            "pool_or_pair_address": f"pool-forensics-cap-{index}",
            "quote_mint": SOL_MINT,
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
        }
        for index in range(650)
    ]
    _write_t007bc_jsonl(tmp_path, "global_migration_raw_candidates.jsonl", raw_rows)
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [])

    summary = run_migration_capture_forensics(tmp_path)

    assert summary["raw_migration_spool_rows"] == 650
    assert summary["forensics_detail_row_limit"] == 500
    assert summary["forensics_detail_rows_truncated"] is True
    assert len(summary["raw_candidates"]) == 500
    assert len(summary["decode_rows"]) == 500


def test_t0115_migration_capture_forensics_classifies_startup_and_in_window(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0115-window", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-t0115-window"}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "birth-ready", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {"mint": "startup-mint", "pool_or_pair_address": "pool-startup", "migration_received_at": 100.5},
            {"mint": "birth-ready", "pool_or_pair_address": "pool-window", "migration_received_at": 200.0},
        ],
    )
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "birth-ready", "received_at": 150.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "birth-ready", "received_at": 201.0}])

    summary = run_migration_capture_forensics(tmp_path)

    assert summary["startup_boundary_count"] == 1
    assert summary["in_window_migration_candidate_count"] == 1
    rows = {row["mint"]: row for row in summary["timestamp_rows"]}
    assert rows["startup-mint"]["classification"] == "startup_boundary"
    assert rows["birth-ready"]["classification"] == "in_window"
    assert summary["birth_linkage_rows"][1]["decision_safe_full_path"] is True


def test_t0115_expected_mint_audit_reports_artifact_coverage(tmp_path: Path) -> None:
    expected = tmp_path / "expected_migrations.txt"
    expected.write_text("mint-expected\n", encoding="utf-8")
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-t0115-expected"}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "mint-expected", "admitted": True, "received_at": 100.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-expected", "received_at": 110.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-expected", "received_at": 120.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [{"mint": "mint-expected", "pool_or_pair_address": "pool-expected", "migration_received_at": 130.0}],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "mint-expected", "received_at": 131.0}])

    summary = run_migration_capture_forensics(tmp_path, expected_mints_path=expected)

    audit_row = summary["expected_mints_audit"][0]
    assert audit_row["mint"] == "mint-expected"
    assert audit_row["birth_seen"] is True
    assert audit_row["decoded_migration_candidate_seen"] is True
    assert audit_row["full_path_linked"] is True


def test_t0115_cli_migration_capture_forensics_skips_live_storage_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "collector_summary.json").write_text(json.dumps({"run_id": "run-t0115-cli"}), encoding="utf-8")

    def fail_storage_preflight(_config: object) -> None:
        raise AssertionError("offline forensics must not run live storage preflight")

    monkeypatch.setattr(recorder_module, "_run_storage_preflight", fail_storage_preflight)

    exit_code = recorder_module.main(["--mode", "audit-migration-capture-forensics", "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "migration_capture_forensics_json=" in output
    assert (tmp_path / "migration_capture_forensics.json").exists()


def test_t0117_forensics_separates_raw_pumpswap_activity_from_migration_candidates(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0117", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"run_id": "run-t0117", "raw_notifications": 3}),
        encoding="utf-8",
    )
    _write_t007bc_jsonl(
        tmp_path,
        "pumpswap_transaction_route_audit.jsonl",
        [
            {"signature": "sig-route-1", "slot": 1, "received_at": 101.0},
            {"signature": "sig-route-2", "slot": 2, "received_at": 102.0},
            {"signature": "sig-route-3", "slot": 3, "received_at": 103.0},
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "pumpswap_swap_events.jsonl",
        [
            {"signature": "sig-swap-1", "slot": 4, "received_at": 104.0, "mint": "mint-swap", "pool": "pool-swap"},
            {"signature": "sig-swap-2", "slot": 5, "received_at": 105.0, "mint": "mint-swap", "pool": "pool-swap"},
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_raw_candidates.jsonl",
        [
            {
                "candidate_id": "cand-raw",
                "signature": "sig-raw",
                "slot": 6,
                "observed_at": 106.0,
                "pool_address": "pool-raw",
                "source_channel": "pumpswap_pool_create",
                "decode_status": "missing_mint",
                "write_enqueued": True,
            }
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_candidates.jsonl",
        [
            {
                "candidate_id": "cand-decoded",
                "signature": "sig-decoded",
                "slot": 7,
                "received_at": 107.0,
                "mint": "mint-decoded",
                "pool_or_pair_address": "pool-decoded",
                "quote_mint": SOL_MINT,
                "quote_asset": "SOL",
                "source_route": "pumpswap_pool_create",
                "detection_method": "pumpswap_pair_created_signal",
                "confidence": "candidate",
            }
        ],
    )

    summary = run_migration_capture_forensics(tmp_path)

    taxonomy = summary["raw_candidate_taxonomy"]
    assert taxonomy["raw_pumpswap_notification"] == 3
    assert taxonomy["raw_pumpswap_swap_event"] == 2
    assert taxonomy["raw_pool_create_like_event"] == 2
    assert taxonomy["raw_migration_like_event"] == 1
    assert taxonomy["decoded_pool_create_candidate"] == 1
    assert taxonomy["decoded_migration_candidate"] == 1
    assert taxonomy["decode_failed_candidate"] == 1
    assert summary["raw_migration_candidate_count_before_decode"] == 6
    assert "raw PumpSwap notifications/swaps plus migration-like artifacts" in summary["raw_candidate_count_explanation"]


def test_t0117_write_path_audit_reports_retry_pending_and_persisted_rows(tmp_path: Path) -> None:
    migration = {
        "candidate_id": "cand-write",
        "signature": "sig-write",
        "slot": 10,
        "received_at": 120.0,
        "mint": "mint-write",
        "base_mint": "mint-write",
        "pool_or_pair_address": "pool-write",
        "quote_mint": SOL_MINT,
        "quote_asset": "SOL",
        "source_route": "pumpswap_first_swap_after_live_birth",
    }
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [migration])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_write_intents.jsonl",
        [
            {
                **migration,
                "candidate_id": "cand-write",
                "write_status": "retry_pending",
                "write_success": False,
                "write_error": "recorder_side_effects_deferred_to_owner_thread",
                "writer_thread_id": 123,
                "thread_affinity_error": False,
                "retry_count": 0,
            }
        ],
    )

    audit = run_migration_write_path_audit(tmp_path)

    row = audit["write_path_rows"][0]
    assert audit["decoded_migration_candidates"] == 1
    assert audit["write_status_counts"] == {"retry_pending": 1}
    assert audit["classification_counts"]["migration_candidate_spooled_but_not_written"] == 1
    assert row["signature"] == "sig-write"
    assert row["write_queued"] is True
    assert row["write_attempted"] is True
    assert row["write_success"] is False
    assert row["persisted_artifact_row_exists"] is True
    assert row["classification"] == "migration_candidate_spooled_but_not_written"
    assert (tmp_path / "migration_write_path_audit.json").exists()
    assert (tmp_path / "migration_write_path_audit.md").exists()


def test_t0117_dedupe_audit_flags_distinct_mints_collapsed_under_same_key(tmp_path: Path) -> None:
    rows = [
        {
            "signature": "sig-a",
            "received_at": 100.0,
            "mint": "mint-a",
            "pool_or_pair_address": "pool-a",
            "quote_mint": SOL_MINT,
            "quote_asset": "SOL",
        },
        {
            "signature": "sig-b",
            "received_at": 101.0,
            "mint": "mint-b",
            "pool_or_pair_address": "pool-b",
            "quote_mint": SOL_MINT,
            "quote_asset": "SOL",
            "dedupe_key": "forced-broad-key",
        },
        {
            "signature": "sig-c",
            "received_at": 102.0,
            "mint": "mint-c",
            "pool_or_pair_address": "pool-c",
            "quote_mint": SOL_MINT,
            "quote_asset": "SOL",
            "dedupe_key": "forced-broad-key",
        },
    ]
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", rows)

    audit = run_migration_dedupe_audit(tmp_path)

    assert audit["decoded_candidates_before_dedupe"] == 3
    assert audit["dedupe_key_too_broad"] is True
    broad = [row for row in audit["dedupe_rows"] if row["dedupe_key"] == "forced-broad-key"][0]
    assert broad["dedupe_key_too_broad"] is True
    assert broad["mints"] == ["mint-b", "mint-c"]
    assert (tmp_path / "migration_dedupe_audit.json").exists()
    assert (tmp_path / "migration_dedupe_audit.md").exists()


def test_t0117_candidate_linkage_matrix_reports_specific_full_path_failure_reasons(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-linkage", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-not-admitted", "admitted": False, "received_at": 101.0, "admission_reason": "sample_rejected"},
            {"mint": "mint-missing-curve", "admitted": True, "received_at": 102.0},
            {"mint": "mint-full", "admitted": True, "received_at": 103.0},
        ],
    )
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-full", "received_at": 120.0, "feature_observed_at": 120.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-full", "received_at": 121.0, "feature_observed_at": 121.0}])
    _write_t007bc_jsonl(tmp_path, "holder_distribution_snapshots.jsonl", [{"mint": "mint-full", "received_at": 122.0}])
    _write_t007bc_jsonl(tmp_path, "dev_behavior_events.jsonl", [{"mint": "mint-full", "received_at": 122.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "mint-full", "received_at": 131.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {"mint": "mint-unknown", "pool_or_pair_address": "pool-unknown", "received_at": 130.0, "slot": 10},
            {"mint": "mint-not-admitted", "pool_or_pair_address": "pool-not-admitted", "received_at": 130.0, "slot": 11},
            {"mint": "mint-missing-curve", "pool_or_pair_address": "pool-missing-curve", "received_at": 130.0, "slot": 12},
            {"mint": "mint-full", "pool_or_pair_address": "pool-full", "received_at": 130.0, "slot": 13},
        ],
    )

    summary = run_migration_capture_forensics(tmp_path)

    rows = {row["candidate_mint"]: row for row in summary["migration_candidate_linkage_matrix"]}
    assert rows["mint-unknown"]["failure_reason"] == "migration_mint_not_in_birth_set"
    assert rows["mint-not-admitted"]["failure_reason"] == "migration_mint_birth_seen_but_not_admitted"
    assert rows["mint-missing-curve"]["failure_reason"] == "missing_pre_migration_curve_state"
    assert rows["mint-full"]["final_full_path_status"] == "decision_safe_full_path"
    assert (tmp_path / "migration_candidate_linkage_matrix.csv").exists()
    assert (tmp_path / "migration_candidate_linkage_matrix.json").exists()


def test_t0117_trade_flow_eventful_gap_audit_is_separate_from_no_event_mints(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {"mint": "mint-gap", "admitted": True, "received_at": 100.0},
            {"mint": "mint-no-event", "admitted": True, "received_at": 100.0},
        ],
    )
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": "mint-gap", "received_at": 101.0}, {"mint": "mint-no-event", "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "raw_trade_events.jsonl", [{"mint": "mint-gap", "signature": "sig-gap", "received_at": 102.0}])
    _write_t007bc_jsonl(tmp_path, "pumpswap_swap_events.jsonl", [{"mint": "mint-post", "signature": "sig-post", "received_at": 103.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [])
    (tmp_path / "collector_summary.json").write_text(json.dumps({"unique_birth_mints": 2}), encoding="utf-8")

    gap = run_trade_flow_eventful_gap_audit(tmp_path)

    assert gap["eventful_gap_count"] == 1
    assert gap["no_event_missing_count"] == 1
    assert gap["eventful_gap_rows"][0]["mint"] == "mint-gap"
    assert gap["eventful_gap_rows"][0]["raw_event_present"] is True
    assert gap["eventful_gap_rows"][0]["classification"] == "real_collector_or_writer_gap"
    coverage = json.loads((tmp_path / "trade_flow_coverage_audit.json").read_text(encoding="utf-8"))
    assert coverage["post_migration_swap_mints_excluded_from_pre_migration_trade_flow"] == 1
    assert (tmp_path / "trade_flow_eventful_gap_audit.json").exists()
    assert (tmp_path / "trade_flow_eventful_gap_audit.md").exists()


def test_t0117_long_readiness_banner_uses_migration_write_capture_failure_text(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "mint-a", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-a", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"unique_birth_mints": 1, "actual_duration_seconds": 600.0, "requested_source_duration_seconds": 600.0}),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(json.dumps({"needed_decodes_to_pass": 0}), encoding="utf-8")
    (tmp_path / "migration_capture_forensics.json").write_text(
        json.dumps(
            {
                "readiness_correction": "migration_lane_write_path_failure",
                "migration_write_retry_pending_count": 1,
                "json_path": str(tmp_path / "migration_capture_forensics.json"),
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["long_scan_readiness_banner_text"] == "Migration lane write/capture failure — full-path readiness invalid"
    assert report["migration_lane_health"] == "failed"


def test_t0115_long_readiness_uses_capture_forensics_issue_status(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"unique_birth_mints": 1, "actual_duration_seconds": 600.0, "requested_source_duration_seconds": 600.0}),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(
        json.dumps({"needed_decodes_to_pass": 0, "missing_age_eligible_count": 0, "scheduler_gap_count": 0}),
        encoding="utf-8",
    )
    (tmp_path / "migration_capture_forensics.json").write_text(
        json.dumps(
            {
                "readiness_correction": "in_window_migration_candidates_missed_by_detector",
                "missed_candidate_count": 2,
                "global_migration_thread_error_count": 1,
                "json_path": str(tmp_path / "migration_capture_forensics.json"),
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["migration_opportunity_status"] == "in_window_migration_candidates_missed_by_detector"
    assert report["migration_readiness_classification"] == "in_window_migration_candidates_missed_by_detector"
    assert report["long_scan_readiness_banner_text"] == "Migration detector/linkage audit required"
    assert "migration_capture_forensics_issue" in report["blockers"]
    assert report["migration_capture_forensics_path"] == str(tmp_path / "migration_capture_forensics.json")


def test_t0116_listener_thread_spools_without_cross_thread_sqlite_use(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    def fail_if_called_from_listener(_filename: str, _row: dict) -> None:
        if threading.get_ident() != recorder._sqlite_owner_thread_id:
            raise AssertionError("listener thread used recorder SQLite path")

    recorder._record_persistent_lifecycle_artifact = fail_if_called_from_listener  # type: ignore[method-assign]
    errors: list[str] = []

    def listener_thread() -> None:
        try:
            writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)
            writer.record(
                {
                    "mint": "mint-thread-safe",
                    "signature": "sig-thread-safe",
                    "slot": 10,
                    "received_at": 200.0,
                    "pool_or_pair_address": "pool-thread-safe",
                    "quote_mint": SOL_MINT,
                    "confidence": "confirmed",
                    "detection_method": "pumpswap_pair_created_signal",
                }
            )
        except Exception as exc:  # pragma: no cover - assertion below reports details
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=listener_thread, name="test-t0116-listener")
    thread.start()
    thread.join(timeout=5)

    assert errors == []
    assert _jsonl(tmp_path / "global_migration_events.jsonl")
    raw_rows = _jsonl(tmp_path / "global_migration_raw_candidates.jsonl")
    intent_rows = _jsonl(tmp_path / "global_migration_write_intents.jsonl")
    assert raw_rows[0]["mint"] == "mint-thread-safe"
    assert raw_rows[0]["write_enqueued"] is True
    assert any(row["write_status"] == "retry_pending" for row in intent_rows)
    assert any(row.get("write_error") == "recorder_side_effects_deferred_to_owner_thread" for row in intent_rows)


def test_t0116_first_swap_listener_thread_defers_owner_side_effects(tmp_path: Path) -> None:
    mint = "threadFirstSwapMint111111111111111111111111pump"
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch(mint, received_at=100.0))

    def fail_if_called_from_listener(_filename: str, _row: dict) -> None:
        if threading.get_ident() != recorder._sqlite_owner_thread_id:
            raise AssertionError("listener thread used recorder SQLite path")

    recorder._record_persistent_lifecycle_artifact = fail_if_called_from_listener  # type: ignore[method-assign]
    errors: list[str] = []

    def listener_thread() -> None:
        try:
            recorder_module._emit_pumpswap_balance_delta_partial_event(
                output_root=tmp_path,
                recorder=recorder,
                counter={},
                row={
                    "swap_direction": "buy",
                    "mint": mint,
                    "base_mint": mint,
                    "pool": "thread-first-swap-pool",
                    "quote_mint": SOL_MINT,
                    "base_amount": 1_000_000,
                    "quote_amount": 100_000,
                    "received_at": 105.0,
                    "signature": "thread-first-swap-sig",
                },
                event={},
            )
        except Exception as exc:  # pragma: no cover - assertion below reports details
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=listener_thread, name="test-first-swap-listener")
    thread.start()
    thread.join(timeout=5)

    assert errors == []
    assert _jsonl(tmp_path / "global_migration_events.jsonl")[0]["mint"] == mint
    assert any(row["write_status"] == "retry_pending" for row in _jsonl(tmp_path / "global_migration_write_intents.jsonl"))

    result = recorder.apply_global_migration_side_effects_from_artifact()

    assert result["migration_side_effects_applied"] == 1
    intent_rows = _jsonl(tmp_path / "global_migration_write_intents.jsonl")
    assert any(row["write_status"] == "written" and row["retry_count"] == 1 for row in intent_rows)
    assert _jsonl(tmp_path / "post_migration_observations.jsonl")


def test_t0116_migration_candidate_spooled_before_sqlite_failure(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    def fail_persistent(_filename: str, _row: dict) -> None:
        raise sqlite3.ProgrammingError("SQLite objects created in a thread can only be used in that same thread")

    recorder._record_persistent_lifecycle_artifact = fail_persistent  # type: ignore[method-assign]
    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)

    status = writer.record(
        {
            "mint": "mint-sqlite-fail",
            "signature": "sig-sqlite-fail",
            "slot": 11,
            "received_at": 201.0,
            "pool_or_pair_address": "pool-sqlite-fail",
            "quote_mint": SOL_MINT,
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
        }
    )

    assert status == "event"
    raw_rows = _jsonl(tmp_path / "global_migration_raw_candidates.jsonl")
    intent_rows = _jsonl(tmp_path / "global_migration_write_intents.jsonl")
    assert raw_rows[0]["mint"] == "mint-sqlite-fail"
    assert any(row["write_status"] == "failed" for row in intent_rows)
    assert any(row["write_error_class"] == "ProgrammingError" for row in intent_rows)
    assert any(row["thread_affinity_error"] is True for row in intent_rows)


def test_t0116_owner_thread_rebuild_applies_spooled_migration_side_effects(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder, defer_recorder_side_effects=True)
    writer.record(
        {
            "mint": "mint-rebuild-side-effects",
            "signature": "sig-rebuild-side-effects",
            "slot": 12,
            "received_at": 202.0,
            "pool_or_pair_address": "pool-rebuild-side-effects",
            "quote_mint": SOL_MINT,
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
        }
    )

    result = recorder.apply_global_migration_side_effects_from_artifact()

    assert result["migration_side_effects_applied"] == 1
    intent_rows = _jsonl(tmp_path / "global_migration_write_intents.jsonl")
    assert any(row["write_status"] == "written" and row["retry_count"] == 1 for row in intent_rows)
    assert _jsonl(tmp_path / "post_migration_observations.jsonl")


def test_t0116_offline_rebuild_from_raw_spool_recovers_migration_candidate(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_raw_candidates.jsonl",
        [
            {
                "candidate_id": "raw-rebuild-1",
                "mint": "mint-spool-rebuild",
                "signature": "sig-spool-rebuild",
                "slot": 13,
                "observed_at": 203.0,
                "received_at": 203.0,
                "pool_address": "pool-spool-rebuild",
                "pool_or_pair_address": "pool-spool-rebuild",
                "quote_mint": SOL_MINT,
                "quote_asset": "SOL",
                "confidence": "confirmed",
                "detection_method": "pumpswap_pair_created_signal",
            }
        ],
    )

    summary = run_rebuild_migrations_from_spool(tmp_path)

    assert summary["raw_spool_rows"] == 1
    assert summary["events_recovered_from_spool"] == 1
    assert _jsonl(tmp_path / "global_migration_events.jsonl")[0]["mint"] == "mint-spool-rebuild"
    assert (tmp_path / "migration_capture_forensics.json").exists()
    assert (tmp_path / "long_scan_readiness_audit.json").exists()


def test_t0116_forensics_and_readiness_report_thread_affinity_failure(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0116", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"run_id": "run-t0116", "actual_duration_seconds": 600.0, "requested_source_duration_seconds": 600.0}),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(json.dumps({"needed_decodes_to_pass": 0}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "mint-affinity", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "mint-affinity", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_write_intents.jsonl",
        [
            {
                "candidate_id": "affinity-1",
                "mint": "mint-affinity",
                "signature": "sig-affinity",
                "write_status": "failed",
                "write_error_class": "ProgrammingError",
                "write_error": "SQLite objects created in a thread can only be used in that same thread",
                "thread_affinity_error": True,
            }
        ],
    )

    forensics = run_migration_capture_forensics(tmp_path)
    readiness = run_long_scan_readiness_audit(tmp_path)

    assert forensics["migration_write_intent_failure_count"] == 1
    assert forensics["sqlite_thread_affinity_error_count"] == 1
    assert forensics["readiness_correction"] == "migration_writer_thread_affinity_error"
    assert readiness["migration_opportunity_status"] == "migration_writer_thread_affinity_error"
    assert readiness["long_scan_readiness_banner_text"] == "Migration lane write/capture failure — full-path readiness invalid"


def test_t0116_forensics_treats_recovered_thread_affinity_as_resolved(tmp_path: Path) -> None:
    mint = "mint-recovered-affinity"
    migration_time = 120.0
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-t0116", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-t0116",
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "global_migration_errors": [
                    "ProgrammingError: SQLite objects created in a thread can only be used in that same thread"
                ],
                "migration_side_effects_applied": 1,
                "migration_side_effects_failed": 0,
                "live_migration_side_effect_drain_count": 1,
                "live_migration_side_effects_applied": 1,
                "live_migration_side_effects_failed": 0,
                "live_migration_side_effects_source_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(json.dumps({"needed_decodes_to_pass": 0}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 110.0, "feature_observed_at": 110.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": mint, "trade_flow_status": "available", "received_at": 111.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 121.0}])
    migration = {
        "mint": mint,
        "signature": "sig-recovered-affinity",
        "received_at": migration_time,
        "migration_received_at": migration_time,
        "pool_or_pair_address": "pool-recovered-affinity",
        "quote_mint": SOL_MINT,
        "quote_asset": "SOL",
    }
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [migration])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_write_intents.jsonl",
        [{**migration, "write_status": "written", "write_success": True, "thread_affinity_error": False}],
    )
    (tmp_path / "live_status.json").write_text(
        json.dumps(
            {
                "run_id": "run-t0116",
                "run_status": "finalized",
                "runtime_phase": "finalized",
                "can_run_60m_thesis_scan": False,
            }
        ),
        encoding="utf-8",
    )

    forensics = run_migration_capture_forensics(tmp_path)
    readiness = run_long_scan_readiness_audit(tmp_path)
    live_status = json.loads((tmp_path / "live_status.json").read_text(encoding="utf-8"))

    assert forensics["raw_global_thread_affinity_error_count"] == 1
    assert forensics["resolved_global_thread_affinity_error_count"] == 1
    assert forensics["sqlite_thread_affinity_error_count"] == 0
    assert forensics["global_migration_thread_error_count"] == 0
    assert forensics["readiness_correction"] == "in_window_migration_decision_safe_full_path_observed"
    assert readiness["can_run_60m_thesis_scan"] is True
    assert live_status["can_run_60m_thesis_scan"] is True
    assert live_status["long_scan_status"] == "READY_FOR_60M_THESIS_SCAN"


def test_t0118_long_readiness_blocks_finalization_only_migration_side_effect_recovery(tmp_path: Path) -> None:
    mint = "mint-finalization-only"
    migration_time = 120.0
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-finalization-only", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-finalization-only",
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "migration_side_effects_applied": 1,
                "migration_side_effects_failed": 0,
                "live_migration_side_effect_drain_count": 0,
                "live_migration_side_effects_applied": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(json.dumps({"needed_decodes_to_pass": 0}), encoding="utf-8")
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 110.0, "feature_observed_at": 110.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": mint, "trade_flow_status": "available", "received_at": 111.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 121.0}])
    migration = {
        "mint": mint,
        "signature": "sig-finalization-only",
        "received_at": migration_time,
        "migration_received_at": migration_time,
        "pool_or_pair_address": "pool-finalization-only",
        "quote_mint": SOL_MINT,
        "quote_asset": "SOL",
    }
    _write_t007bc_jsonl(tmp_path, "global_migration_events.jsonl", [migration])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_write_intents.jsonl",
        [{**migration, "write_status": "written", "write_success": True, "thread_affinity_error": False}],
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["can_run_10m_collector_proof"] is True
    assert report["can_run_10m_feature_proof"] is True
    assert report["decision_safe_full_path_status"] == "observed"
    assert report["can_run_60m_thesis_scan"] is False
    assert "migration_side_effects_not_proven_live" in report["blockers"]
    assert "prove_live_migration_side_effect_drain_before_longer_scan" in report["next_fix_recommendations"]


def test_t011_migration_linkage_distinguishes_curve_decode_after_migration(tmp_path: Path) -> None:
    mint = "mint-late-curve"
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 100.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 110.0, "feature_observed_at": 110.0}])
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 106.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [{"mint": mint, "migration_received_at": 105.0, "pool_or_pair_address": "pool-late-curve", "quote_asset": "SOL"}],
    )
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")

    summary = run_migration_linkage_audit(tmp_path)

    assert summary["failure_reason_counts"] == {"migration_before_first_curve_observation": 1}
    assert summary["migration_rows"][0]["pre_migration_curve_state_exists"] is True
    assert summary["migration_rows"][0]["pre_migration_curve_state_before_migration"] is False


def test_t011_long_scan_readiness_report_blocks_60m_until_trade_flow_and_migration_linkage_clear(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [{"mint": "mint-a", "admitted": True, "received_at": 100.0, "trade_flow_status": "writer_gap"}],
    )
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"unique_birth_mints": 1, "global_migration_events_deduped": 0}), encoding="utf-8"
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "action": "WARN",
                "abort_reasons": [],
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1},
                    {"metric_id": "trade_flow_mint_coverage", "status": "fail", "numerator": 0, "denominator": 1},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["can_run_10m_collector_proof"] is True
    assert report["10m_collector_proof_status"] == "passed"
    assert report["can_run_10m_feature_proof"] is False
    assert report["10m_feature_proof_status"] == "failed"
    assert report["can_run_10m_feature_proof_reason"] == "collector_or_eventful_trade_flow_gate_not_proven"
    assert report["can_run_60m_thesis_scan"] is False
    assert report["60m_thesis_readiness"] == "blocked"
    assert report["can_run_2h_plus_scan"] is False
    assert report["long_scan_status"] == "BLOCKED_FOR_LONG_SCAN"
    assert report["long_scan_readiness_banner_text"] == "10m collector + feature proof passed; 60m thesis readiness blocked"
    assert "trade_flow_eventful_parser_writer_gap" in report["blockers"]
    assert "no_in_window_decision_safe_full_path" in report["blockers"]
    assert "fix_trade_flow_missing_flow_for_birth_mints" in report["next_fix_recommendations"]
    assert (tmp_path / "long_scan_readiness_audit.json").exists()
    assert (tmp_path / "long_scan_readiness_audit.md").exists()


def test_t011_long_scan_readiness_uses_canonical_lifecycle_curve_gate_when_supervisor_missing(tmp_path: Path) -> None:
    mint = "mint-canonical-curve-pass"
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 100.0}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 101.0, "feature_observed_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": mint, "trade_flow_status": "available", "received_at": 102.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": mint,
                "migration_received_at": 105.0,
                "pool_or_pair_address": "pool-canonical-curve-pass",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 106.0}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 10,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "global_migration_events_deduped": 1,
                "live_migration_side_effect_drain_count": 1,
                "live_migration_side_effects_applied": 1,
                "live_migration_side_effects_failed": 0,
                "live_migration_side_effects_source_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "lifecycle_coverage_summary.json").write_text(
        json.dumps(
            {
                "lifecycle_materializer_status": "ok",
                "verified_births": 10,
                "curve_state_decoded": 9,
                "decision_safe_full_paths": 1,
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["t0103_curve_gate_passed"] is True
    assert report["t0103_curve_gate_source"] == "canonical_lifecycle_materializer"
    assert report["canonical_lifecycle_curve_decode_ratio"] == 0.9
    assert report["can_run_10m_collector_proof"] is True
    assert report["can_run_10m_feature_proof"] is True
    assert report["decision_safe_full_path_status"] == "observed"
    assert report["can_run_60m_thesis_scan"] is True
    assert report["long_scan_status"] == "READY_FOR_60M_THESIS_SCAN"


def test_t011_long_scan_readiness_recommends_rerun_for_startup_boundary_only(tmp_path: Path) -> None:
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps({"run_id": "run-startup", "started_at": 100.0, "ended_at": 700.0}),
        encoding="utf-8",
    )
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "startup-migration",
                "signature": "sig-startup-migration",
                "migration_received_at": 100.5,
                "pool_or_pair_address": "pool-startup",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "startup-migration"}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps({"unique_birth_mints": 1, "actual_duration_seconds": 600.0, "requested_source_duration_seconds": 600.0}),
        encoding="utf-8",
    )
    (tmp_path / "lifecycle_coverage_summary.json").write_text(
        json.dumps({"migrated_unique_mints": 1, "decision_safe_full_paths": 0}),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1}
                ]
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["can_run_10m_feature_proof"] is True
    assert report["10m_collector_proof_status"] == "passed"
    assert report["10m_feature_proof_status"] == "passed"
    assert report["can_run_60m_thesis_scan"] is False
    assert report["60m_thesis_readiness"] == "blocked"
    assert "no_in_window_decision_safe_full_path" in report["blockers"]
    assert report["migration_opportunity_status"] == "no_in_window_migration_observed"
    assert report["decision_safe_full_path_status"] == "not_observed"
    assert "startup-boundary migration does not count as full-path evidence" in report["long_scan_blocker_bullets"]
    assert report["migration_readiness_classification"] == "diagnostic_only_startup_boundary"
    assert "rerun_10m_feature_proof_until_in_window_migration_observed" in report["next_fix_recommendations"]
    assert "fix_migration_linkage_or_explain_unlinked_global_migration" not in report["next_fix_recommendations"]


def test_t011_long_scan_readiness_uses_canonical_materializer_full_path_count(tmp_path: Path) -> None:
    mint = "mint-linkage-only"
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 100.0, "slot": 10}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 110.0, "slot": 11, "decode_status": "decoded"}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": mint, "received_at": 111.0, "trade_flow_status": "available"}])
    _write_t007bc_jsonl(tmp_path, "holder_distribution_snapshots.jsonl", [{"mint": mint, "received_at": 112.0}])
    _write_t007bc_jsonl(tmp_path, "dev_behavior_events.jsonl", [{"mint": mint, "received_at": 113.0}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [{"mint": mint, "migration_received_at": 150.0, "received_at": 150.0, "slot": 20, "pool_or_pair_address": "pool-linkage-only"}],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 151.0}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 1,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "global_migration_events_deduped": 1,
                "live_migration_side_effect_drain_count": 1,
                "live_migration_side_effects_applied": 1,
                "live_migration_side_effects_failed": 0,
                "live_migration_side_effects_source_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "lifecycle_coverage_summary.json").write_text(
        json.dumps(
            {
                "lifecycle_materializer_status": "ok",
                "verified_births": 1,
                "curve_state_decoded": 1,
                "migrated_unique_mints": 1,
                "decision_safe_full_paths": 0,
            }
        ),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["row_derived_decision_safe_full_paths"] == 1
    assert report["lifecycle_summary_decision_safe_full_paths"] == 0
    assert report["decision_safe_full_paths"] == 0
    assert report["decision_safe_full_path_status"] == "not_observed"
    assert report["can_run_60m_thesis_scan"] is False
    assert "no_in_window_decision_safe_full_path" in report["blockers"]


def test_t011_long_scan_readiness_keeps_proofs_passed_when_no_migration_opportunity(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 1,
                "global_migration_events_deduped": 0,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(
        json.dumps({"needed_decodes_to_pass": 0, "missing_age_eligible_count": 0, "scheduler_gap_count": 0}),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["10m_collector_proof_status"] == "passed"
    assert report["10m_feature_proof_status"] == "passed"
    assert report["migration_opportunity_status"] == "no_migration_opportunity_observed"
    assert report["decision_safe_full_path_status"] == "not_observed"
    assert report["60m_thesis_readiness"] == "blocked"
    assert report["can_run_60m_thesis_scan"] is False
    assert report["can_run_2h_plus_scan"] is False


def test_long_scan_readiness_reports_latency_source_gap_reorg_and_budget_gates(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 1,
                "global_migration_events_deduped": 0,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429": 0,
                "latency_histograms_present": True,
                "route_latency_gate_passed": False,
                "route_latency_gate_failures": ["birth_to_first_curve_observation_p95_exceeded"],
                "commitment_reorg_drop_accounting_present": True,
                "dropped_or_reorged_count": 1,
                "source_gap_unbackfilled_count": 1,
                "helius_budget_gate_present": True,
                "helius_budget_gate_passed": False,
                "helius_budget_blocker": "estimated_credits_exceed_configured_cap",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(
        json.dumps({"needed_decodes_to_pass": 0, "missing_age_eligible_count": 0, "scheduler_gap_count": 0}),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["route_latency_gate_passed"] is False
    assert "route_latency_gate_failed" in report["blockers"]
    assert report["source_gap_reorg_gate_passed"] is False
    assert "source_gap_or_reorg_accounting_failed" in report["blockers"]
    assert report["helius_budget_gate_passed"] is False
    assert "helius_budget_gate_not_passed" in report["blockers"]
    assert report["can_run_2h_plus_scan"] is False


def test_long_scan_readiness_treats_derived_materialization_latency_failure_as_hard_veto(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 1,
                "global_migration_events_deduped": 0,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429": 0,
                "latency_histograms_present": True,
                "route_latency_gate_passed": True,
                "route_latency_histograms": {
                    "birth_to_admission_complete_latency_ms": {"count": 3, "p95": 1503.13}
                },
                "materialization_latency_gate_passed": True,
                "materialization_latency_gate_failures": [],
                "commitment_reorg_drop_accounting_present": True,
                "dropped_or_reorged_count": 0,
                "source_gap_unbackfilled_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps({"coverage_metrics": [{"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass"}]}),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(
        json.dumps({"needed_decodes_to_pass": 0, "missing_age_eligible_count": 0, "scheduler_gap_count": 0}),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["materialization_latency_gate_passed"] is False
    assert "birth_to_admission_complete_p95_exceeded" in report["materialization_latency_gate_failures"]
    assert "materialization_latency_gate_failed" in report["blockers"]
    assert report["can_run_60m_thesis_scan"] is False


def test_state_snapshot_prevents_live_state_mutation_iteration_errors(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1)
    )
    recorder.states["first"] = recorder_module.TrackingState(mint="first", deep_tracking_admitted=True)
    recorder.states["first"].launch_received_at = 1000.0

    class MutatingStateDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.mutated_during_iteration = False

        def values(self):
            if self.mutated_during_iteration:
                return super().values()
            state_dict = self
            iterator = super().values().__iter__()

            class MutatingValues:
                def __iter__(self):
                    yield next(iterator)
                    state_dict["second"] = recorder_module.TrackingState(mint="second", deep_tracking_admitted=True)
                    state_dict["second"].launch_received_at = 1001.0
                    state_dict.mutated_during_iteration = True
                    yield from iterator

            return MutatingValues()

    recorder.states = MutatingStateDict(recorder.states)

    count = recorder._active_tracking_count()

    assert count >= 1


def test_t011_long_scan_readiness_reports_recovered_reconnect_and_sqlite_store(tmp_path: Path) -> None:
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": "first-birth", "admitted": True, "received_at": 101.0}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": "first-birth", "trade_flow_status": "available"}])
    (tmp_path / "t007_lifecycle_state.sqlite").write_bytes(b"sqlite-placeholder")
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "unique_birth_mints": 1,
                "global_migration_events_deduped": 0,
                "actual_duration_seconds": 600.0,
                "requested_source_duration_seconds": 600.0,
                "source_duration_quality_status": "degraded",
                "websocket_keepalive_timeout_count": 1,
                "websocket_reconnect_count": 1,
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429": 0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scan_supervisor_status.json").write_text(
        json.dumps(
            {
                "coverage_metrics": [
                    {"metric_id": "curve_decode_age_eligible_mint_coverage", "status": "pass", "numerator": 1, "denominator": 1}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "curve_decode_reliability_audit.json").write_text(
        json.dumps({"needed_decodes_to_pass": 0, "missing_age_eligible_count": 0, "scheduler_gap_count": 0}),
        encoding="utf-8",
    )

    report = run_long_scan_readiness_audit(tmp_path)

    assert report["source_quality_label"] == "complete_with_reconnect_warning"
    assert report["source_reconnect_warning"] is True
    assert "source completed with reconnect warning" in report["long_scan_blocker_bullets"]
    assert report["persistent_lifecycle_store"] == "sqlite_ok"
    assert report["persistent_lifecycle_events_jsonl"] == "optional_missing"
    status = json.loads((tmp_path / "live_status.json").read_text()) if (tmp_path / "live_status.json").exists() else {}
    if status:
        assert status["persistent_lifecycle_store"] == "sqlite_ok"


def test_transaction_live_smoke_updates_final_live_status_with_source_metrics(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 5000.0,
                "signature": "sig-status",
                "slot": 1,
                "decoded_rows": [
                    {
                        "signature": "sig-status",
                        "slot": 1,
                        "mint": "mint-status-live",
                        "bonding_curve": "curve-status-live",
                        "source_instruction_level": "top_level",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            "mint-status-live": {
                "bonding_curve": "curve-status-live",
                "account_state": {
                    "real_token_reserves": 317_240_000_000_000,
                    "token_total_supply": 1_000_000_000_000_000,
                    "token_decimals": 6,
                    "complete": False,
                },
                "fdv_proxy": 36_500,
                "fdv_units": "usd",
                "observed_at": 5000.2,
            }
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 5000.2,
    )
    status = json.loads((tmp_path / "live_status.json").read_text())

    assert summary["raw_transaction_notifications"] == 1
    assert status["run_status"] == "finalized"
    assert status["raw_notifications"] == 1
    assert status["unique_birth_mints"] == 1
    assert status["admitted_births"] == 1
    assert status["output_folder"] == str(tmp_path)
    assert status["watcher_status"] == "available"


def test_global_migration_event_can_be_emitted_for_non_admitted_token(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 7000.0,
                "signature": "sig-migrate-global",
                "slot": 77,
                "decoded_rows": [
                    {
                        "signature": "sig-migrate-global",
                        "slot": 77,
                        "mint": "mint-global-migrate",
                        "instruction_type": "migrate",
                        "parser_status": "decoded",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 7000.1,
    )

    rows = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert summary["global_migration_events"] == 1
    assert rows[0]["mint"] == "mint-global-migrate"
    assert rows[0]["detection_method"] == "pumpfun_migrate_instruction"
    assert rows[0]["confidence"] == "confirmed"
    assert rows[0]["admission_scope"] == "global_source_not_admission_gated"


def test_global_migration_event_can_be_matched_to_admitted_pruned_token(tmp_path: Path) -> None:
    (tmp_path / "birth_audit.jsonl").write_text(
        json.dumps({"mint": "mint-pruned", "admitted": True, "admission_reason": "sample_admitted"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "valuation_ladder_paths.jsonl").write_text(
        json.dumps(
            {
                "mint": "mint-pruned",
                "stop_reason": "low_progress_timeout",
                "last_progress_pct": 7.0,
                "highest_progress_pct": 8.0,
                "curve_observation_count": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "global_migration_events.jsonl").write_text(
        json.dumps(
            {
                "mint": "mint-pruned",
                "signature": "sig-pruned-migrate",
                "detection_method": "pumpfun_migrate_instruction",
                "confidence": "confirmed",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    run_axiom_reconciliation(tmp_path, [{"mint": "mint-pruned", "token_name": "Pruned"}])

    row = _jsonl(tmp_path / "axiom_reconciliation.jsonl")[0]
    assert row["collector_birth_seen"] is True
    assert row["collector_admitted"] is True
    assert row["pruned"] is True
    assert row["prune_reason"] == "low_progress_timeout"
    assert row["global_migration_event_seen"] is True
    assert row["global_migration_detection_method"] == "pumpfun_migrate_instruction"
    assert row["explanation"] == "seen_but_pruned_before_migration"


def test_axiom_reconciliation_identifies_seen_and_active_but_migration_not_decoded(tmp_path: Path) -> None:
    (tmp_path / "birth_audit.jsonl").write_text(
        json.dumps({"mint": "mint-active", "admitted": True, "admission_reason": "sample_admitted"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "curve_observations.jsonl").write_text(
        json.dumps({"mint": "mint-active", "decode_status": "decoded", "progress_pct": 64.0}) + "\n",
        encoding="utf-8",
    )

    run_axiom_reconciliation(tmp_path, [{"mint": "mint-active", "token_name": "Active"}])

    row = _jsonl(tmp_path / "axiom_reconciliation.jsonl")[0]
    assert row["collector_birth_seen"] is True
    assert row["collector_admitted"] is True
    assert row["pruned"] is False
    assert row["curve_observations_count"] == 1
    assert row["global_migration_event_seen"] is False
    assert row["explanation"] == "seen_and_active_but_migration_not_decoded"


def test_axiom_reconciliation_handles_mints_absent_from_birth_source(tmp_path: Path) -> None:
    run_axiom_reconciliation(tmp_path, [{"mint": "mint-absent", "axiom_column": "migrated"}])

    row = _jsonl(tmp_path / "axiom_reconciliation.jsonl")[0]
    assert row["mint"] == "mint-absent"
    assert row["collector_birth_seen"] is False
    assert row["collector_admitted"] is False
    assert row["global_migration_event_seen"] is False
    assert row["explanation"] == "not_seen_by_source"


def test_migration_detector_does_not_reenable_valuation_ladder(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 7100.0,
                "signature": "sig-migrate-no-ladder",
                "slot": 78,
                "decoded_rows": [
                    {
                        "signature": "sig-migrate-no-ladder",
                        "slot": 78,
                        "mint": "mint-no-ladder",
                        "complete": True,
                        "parser_status": "decoded",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_source_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 7100.1,
    )

    assert summary["mayhem_code_modified"] is False
    assert summary["valuation_ladder_emission_policy"] == "market_cap_confirmed_only"
    assert summary["valuation_ladder_events_written"] == 0
    assert _jsonl(tmp_path / "valuation_ladder_events.jsonl") == []


def test_migration_route_audit_writes_route_specific_counters(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8000.0,
                "signature": "sig-route-migrate",
                "slot": 80,
                "decoded_rows": [
                    {
                        "signature": "sig-route-migrate",
                        "slot": 80,
                        "mint": "mint-route-migrate",
                        "instruction_type": "migrate",
                        "parser_status": "decoded",
                    }
                ],
            },
            {
                "received_at": 8001.0,
                "signature": "sig-route-pumpswap",
                "slot": 81,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-route-pumpswap",
                        "slot": 81,
                        "mint": "mint-route-pumpswap",
                        "pool_address": "pool-route",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                        "parser_status": "decoded",
                    }
                ],
            },
        ],
        actual_duration_seconds=2.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=2),
        source=source,
        now_fn=lambda: 8002.0,
    )

    assert summary["routes"]["pumpfun_migrate_instruction_log"]["decoded_migration_events"] == 1
    assert summary["routes"]["pumpswap_pool_create"]["decoded_migration_events"] == 1
    assert summary["routes"]["current_pumpfun_create_account_required"]["raw_notifications"] == 2
    rows = _jsonl(tmp_path / "migration_route_audit_rows.jsonl")
    assert {row["source_route"] for row in rows} == {"pumpfun_migrate_instruction_log", "pumpswap_pool_create"}


def test_pumpswap_pair_created_fixture_produces_global_migration_event(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8100.0,
                "signature": "sig-pumpswap-pair",
                "slot": 82,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-pumpswap-pair",
                        "slot": 82,
                        "mint": "mint-pumpswap-pair",
                        "pool_address": "pool-pair",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 8101.0,
    )

    rows = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert summary["routes"]["pumpswap_pool_create"]["unique_migrated_mints"] == 1
    assert rows[0]["detection_method"] == "pumpswap_pair_created_signal"
    assert rows[0]["pool_or_pair_address"] == "pool-pair"


def test_axiom_reconcile_recommends_missing_route_when_lookup_evidence_exists(tmp_path: Path) -> None:
    (tmp_path / "axiom_direct_lookup_evidence.jsonl").write_text(
        json.dumps(
            {
                "mint": "mint-axiom-route",
                "direct_lookup_signatures_found": 3,
                "migration_like_signature_found": True,
                "migration_program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "migration_instruction_name": "CreatePool",
                "pool_or_pair_address": "pool-axiom",
                "detection_route_needed": "pumpswap_pool_create",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    run_axiom_reconciliation(tmp_path, [{"mint": "mint-axiom-route"}])

    row = _jsonl(tmp_path / "axiom_reconciliation.jsonl")[0]
    assert row["collector_birth_seen"] is False
    assert row["direct_lookup_signatures_found"] == 3
    assert row["migration_like_signature_found"] is True
    assert row["migration_program_id"] == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    assert row["pool_or_pair_address"] == "pool-axiom"
    assert row["detection_route_needed"] == "pumpswap_pool_create"
    assert row["explanation"] == "seen_by_direct_lookup_not_live_source"


class FakeDirectMintLookupClient:
    def __init__(self, signatures_by_address: dict[str, list[dict]], transactions_by_signature: dict[str, dict]) -> None:
        self.signatures_by_address = signatures_by_address
        self.transactions_by_signature = transactions_by_signature
        self.signature_calls: list[dict] = []
        self.transaction_calls: list[str] = []

    def fetch_signatures_for_address(self, address: str, *, limit: int, before: str | None = None) -> list[dict]:
        self.signature_calls.append({"address": address, "limit": limit, "before": before})
        return [dict(row) for row in self.signatures_by_address.get(address, [])[:limit]]

    def fetch_transaction(self, signature: str) -> dict:
        self.transaction_calls.append(signature)
        return dict(self.transactions_by_signature.get(signature, {}))


def test_direct_mint_lookup_detects_pumpfun_migrate_signature(tmp_path: Path) -> None:
    client = FakeDirectMintLookupClient(
        {"mint-migrate": [{"signature": "sig-migrate", "slot": 90, "blockTime": 1700}]},
        {
            "sig-migrate": {
                "slot": 90,
                "blockTime": 1700,
                "meta": {"logMessages": ["Program log: Instruction: Migrate"]},
                "transaction": {
                    "message": {
                        "instructions": [
                            {"programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "accounts": ["mint-migrate", "curve-a"]}
                        ]
                    }
                },
            }
        },
    )

    summary = run_direct_mint_lookup(
        tmp_path,
        [{"mint": "mint-migrate", "token_name": "Migrates"}],
        client=client,
        direct_lookup_limit=5,
        sleep_ms=0,
    )

    row = _jsonl(tmp_path / "direct_mint_lookup_rows.jsonl")[0]
    assert summary["found_migration_route_count"] == 1
    assert row["pumpfun_migrate_found"] is True
    assert row["detected_route_needed"] == "pumpfun_migrate"
    assert row["direct_lookup_status"] == "found_migration_route"
    assert row["migration_like_signature"] == "sig-migrate"


def test_direct_mint_lookup_detects_pumpswap_pool_create_signature(tmp_path: Path) -> None:
    client = FakeDirectMintLookupClient(
        {"mint-pool": [{"signature": "sig-pool", "slot": 91, "blockTime": 1800}]},
        {
            "sig-pool": {
                "slot": 91,
                "blockTime": 1800,
                "meta": {"logMessages": ["Program log: Instruction: CreatePool"]},
                "transaction": {
                    "message": {
                        "instructions": [
                            {
                                "programId": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                                "accounts": ["payer-a", "pool-a", "mint-pool", "So11111111111111111111111111111111111111112"],
                            }
                        ]
                    }
                },
            }
        },
    )

    run_direct_mint_lookup(
        tmp_path,
        [{"mint": "mint-pool", "token_name": "Pool"}],
        client=client,
        direct_lookup_limit=5,
        sleep_ms=0,
    )

    row = _jsonl(tmp_path / "direct_mint_lookup_rows.jsonl")[0]
    assert row["pumpswap_pool_create_found"] is True
    assert row["detected_route_needed"] == "pumpswap_account_required"
    assert row["direct_lookup_status"] == "found_pool_route"
    assert row["migration_program_id"] == "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    assert row["pool_or_pair_address"] == "pool-a"


def test_direct_mint_lookup_records_no_relevant_signatures(tmp_path: Path) -> None:
    client = FakeDirectMintLookupClient({"mint-empty": []}, {})

    run_direct_mint_lookup(
        tmp_path,
        [{"mint": "mint-empty"}],
        client=client,
        direct_lookup_limit=5,
        sleep_ms=0,
    )

    row = _jsonl(tmp_path / "direct_mint_lookup_rows.jsonl")[0]
    assert row["signatures_found"] == 0
    assert row["transactions_fetched"] == 0
    assert row["direct_lookup_status"] == "no_relevant_signatures"


def test_pumpswap_candidate_without_exact_mint_emits_global_migration_candidate(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8200.0,
                "signature": "sig-pumpswap-unresolved",
                "slot": 92,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-pumpswap-unresolved",
                        "slot": 92,
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                        "pool_address": "pool-unresolved",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 8201.0,
    )

    candidates = _jsonl(tmp_path / "global_migration_candidates.jsonl")
    assert summary["routes"]["pumpswap_pool_create"]["decoded_migration_candidates"] == 1
    assert candidates[0]["confidence"] == "candidate"
    assert candidates[0]["pool_or_pair_address"] == "pool-unresolved"


def test_pumpswap_raw_payload_candidate_extracts_mint_and_pool_from_token_balances(tmp_path: Path) -> None:
    mint = "3eN8Zjs3dEY9k3DArtzgvb7QR9CeexxR75LPRo6tpump"
    pool = "5BFTM1WSwN2SGhN5dnUzTkqbVis7d8TdKPsxNMAEdsAh"
    tx = {
        "slot": 93,
        "blockTime": 1801,
        "transaction": {
            "signatures": ["sig-pumpswap-raw"],
            "message": {
                "accountKeys": [
                    {"pubkey": "payer-live", "signer": True, "writable": True},
                    {"pubkey": pool, "signer": False, "writable": True},
                    {"pubkey": mint, "signer": False, "writable": False},
                    {"pubkey": "So11111111111111111111111111111111111111112", "signer": False, "writable": False},
                ],
                "instructions": [
                    {
                        "programId": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "accounts": ["payer-live", pool, mint, "So11111111111111111111111111111111111111112"],
                    }
                ],
            },
        },
        "meta": {
            "logMessages": ["Program log: Instruction: CreatePool"],
            "postTokenBalances": [
                {"accountIndex": 2, "mint": mint, "owner": pool, "uiTokenAmount": {"uiAmountString": "1000", "decimals": 6}},
                {
                    "accountIndex": 3,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": pool,
                    "uiTokenAmount": {"uiAmountString": "10", "decimals": 9},
                },
            ],
            "innerInstructions": [],
        },
    }
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8300.0,
                "signature": "sig-pumpswap-raw",
                "slot": 93,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "raw_payload": {"params": {"result": {"transaction": tx}}},
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 8301.0,
    )

    rows = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert summary["routes"]["pumpswap_pool_create"]["decoded_migration_events"] == 1
    assert summary["routes"]["pumpswap_pool_create"]["missing_mint_count"] == 0
    assert summary["routes"]["pumpswap_pool_create"]["missing_pair_pool_count"] == 0
    assert rows[0]["mint"] == mint
    assert rows[0]["pool_or_pair_address"] == pool


def test_pumpswap_pool_create_uses_canonical_raw_mint_not_row_event_mints(tmp_path: Path) -> None:
    canonical_mint = "CanonicalMint111111111111111111111111111111pump"
    wrong_mint_a = "WrongDecodedEventMintAAAAAAAAAAAAAAAAAAAAAAAAAA"
    wrong_mint_b = "WrongDecodedEventMintBBBBBBBBBBBBBBBBBBBBBBBBBB"
    pool = "CanonicalPool11111111111111111111111111111111"
    tx = {
        "slot": 94,
        "blockTime": 1802,
        "transaction": {
            "signatures": ["sig-pumpswap-canonical"],
            "message": {
                "accountKeys": [
                    {"pubkey": "payer-live", "signer": True, "writable": True},
                    {"pubkey": pool, "signer": False, "writable": True},
                    {"pubkey": canonical_mint, "signer": False, "writable": False},
                    {"pubkey": "So11111111111111111111111111111111111111112", "signer": False, "writable": False},
                ],
                "instructions": [
                    {
                        "programId": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                        "accounts": ["payer-live", pool, canonical_mint, "So11111111111111111111111111111111111111112"],
                    }
                ],
            },
        },
        "meta": {
            "logMessages": ["Program log: Instruction: CreatePool"],
            "postTokenBalances": [
                {"accountIndex": 2, "mint": canonical_mint, "owner": pool, "uiTokenAmount": {"uiAmountString": "1000", "decimals": 6}},
                {
                    "accountIndex": 3,
                    "mint": "So11111111111111111111111111111111111111112",
                    "owner": pool,
                    "uiTokenAmount": {"uiAmountString": "10", "decimals": 9},
                },
            ],
        },
    }
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8302.0,
                "signature": "sig-pumpswap-canonical",
                "slot": 94,
                "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                "logs": ["Program log: Instruction: CreatePool"],
                "raw_payload": {"params": {"result": {"transaction": tx}}},
                "decoded_rows": [
                    {
                        "signature": "sig-pumpswap-canonical",
                        "slot": 94,
                        "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                        "instruction_type": "buy",
                        "mint": wrong_mint_a,
                    },
                    {
                        "signature": "sig-pumpswap-canonical",
                        "slot": 94,
                        "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                        "instruction_type": "sell",
                        "mint": wrong_mint_b,
                    },
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1),
        source=source,
        now_fn=lambda: 8303.0,
    )

    rows = _jsonl(tmp_path / "global_migration_events.jsonl")
    duplicates = _jsonl(tmp_path / "global_migration_event_duplicates.jsonl")
    assert summary["routes"]["pumpswap_pool_create"]["decoded_migration_events"] == 1
    assert [row["mint"] for row in rows] == [canonical_mint]
    assert rows[0]["pool_or_pair_address"] == pool
    assert len(duplicates) == 1
    assert duplicates[0]["mint"] == canonical_mint
    assert wrong_mint_a not in {row["mint"] for row in rows + duplicates}
    assert wrong_mint_b not in {row["mint"] for row in rows + duplicates}


def test_pumpswap_duplicate_events_collapse_to_one_global_migration_event(tmp_path: Path) -> None:
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8400.0,
                "signature": "sig-pool-first",
                "slot": 100,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-pool-first",
                        "slot": 100,
                        "mint": "mint-dedupe",
                        "pool_address": "pool-dedupe",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            },
            {
                "received_at": 8401.0,
                "signature": "sig-pool-duplicate",
                "slot": 101,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-pool-duplicate",
                        "slot": 101,
                        "mint": "mint-dedupe",
                        "pool_address": "pool-dedupe",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            },
        ],
        actual_duration_seconds=2.0,
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=2),
        source=source,
        now_fn=lambda: 8402.0,
    )

    events = _jsonl(tmp_path / "global_migration_events.jsonl")
    duplicates = _jsonl(tmp_path / "global_migration_event_duplicates.jsonl")
    assert [row["signature"] for row in events] == ["sig-pool-first"]
    assert len(duplicates) == 1
    assert duplicates[0]["signature"] == "sig-pool-duplicate"
    assert duplicates[0]["duplicate_of_signature"] == "sig-pool-first"
    assert summary["deduped_pumpswap_migration_events"] == 1
    assert summary["duplicate_pumpswap_rows_suppressed"] == 1


class FakeReconnectTransactionSubscribeAuditRoute(FakeTransactionSubscribeAuditRoute):
    def __init__(self, events: list[dict[str, Any]]) -> None:
        super().__init__(events, actual_duration_seconds=10.0)
        self.reconnect_attempts = 1
        self.reconnect_success_count = 1
        self.reconnect_failure_count = 0
        self.reconnect_reasons = ["ConnectionClosedError: keepalive ping timeout"]
        self.total_disconnected_seconds = 0.25
        self.completed_requested_duration = True


def test_reconnect_preserves_pumpswap_dedupe_state(tmp_path: Path) -> None:
    source = FakeReconnectTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8500.0,
                "signature": "sig-before-reconnect",
                "slot": 110,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-before-reconnect",
                        "slot": 110,
                        "mint": "mint-reconnect",
                        "pool_address": "pool-reconnect",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            },
            {
                "received_at": 8501.0,
                "signature": "sig-after-reconnect",
                "slot": 111,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-after-reconnect",
                        "slot": 111,
                        "mint": "mint-reconnect",
                        "pool_address": "pool-reconnect",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            },
        ]
    )

    summary = run_migration_route_audit(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=10),
        source=source,
        now_fn=lambda: 8510.0,
    )

    assert summary["reconnect_attempts"] == 1
    assert summary["reconnect_success_count"] == 1
    assert summary["completed_requested_duration"] is True
    assert summary["deduped_pumpswap_migration_events"] == 1
    assert summary["duplicate_pumpswap_rows_suppressed"] == 1


def test_transaction_live_smoke_emits_pumpswap_migration_for_sample_rejected_birth(tmp_path: Path) -> None:
    birth_source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8600.0,
                "signature": "sig-birth-sample-rejected",
                "slot": 120,
                "decoded_rows": [
                    {
                        "signature": "sig-birth-sample-rejected",
                        "slot": 120,
                        "mint": "mint-sample-rejected",
                        "bonding_curve_account": "curve-sample-rejected",
                        "instruction_type": "create",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    migration_source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8601.0,
                "signature": "sig-migration-sample-rejected",
                "slot": 121,
                "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "logs": ["Program log: Instruction: CreatePool"],
                "decoded_rows": [
                    {
                        "signature": "sig-migration-sample-rejected",
                        "slot": 121,
                        "mint": "mint-sample-rejected",
                        "pool_address": "pool-sample-rejected",
                        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                        "instruction_type": "create_pool",
                    }
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1, sample_rate_percent=0, enable_global_pumpswap_migration=True),
        source=birth_source,
        curve_probe=FakeCurveStateProbe({}),
        global_migration_source=migration_source,
        now_fn=lambda: 8602.0,
    )

    events = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert summary["global_migration_events_deduped"] == 1
    assert summary["global_migration_mints_seen_in_birth_source"] == 1
    assert summary["global_migration_mints_sample_rejected"] == 1
    assert events[0]["seen_in_birth_source"] is True
    assert events[0]["admitted"] is False
    assert events[0]["sample_rejected"] is True
    assert summary["valuation_ladder_events_written"] == 0
    assert summary["mayhem_code_modified"] is False


def test_pumpswap_program_subscribe_market_account_emits_deduped_migration_event(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-program-subscribe"))
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8700.0,
                "slot": 130,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-program-subscribe",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-program-subscribe",
                    "quote_mint": "So11111111111111111111111111111111111111112",
                    "lp_mint": "lp-program-subscribe",
                    "pool_base_token_account": "pool-base-token",
                    "pool_quote_token_account": "pool-quote-token",
                    "coin_creator": "coin-creator",
                    "is_mayhem_mode": False,
                    "is_cashback_coin": False,
                    "program_subscribe_account_created": True,
                },
            },
            {
                "received_at": 8701.0,
                "slot": 131,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-program-subscribe",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-program-subscribe",
                    "quote_mint": "So11111111111111111111111111111111111111112",
                    "program_subscribe_account_created": True,
                },
            },
        ],
        actual_duration_seconds=2.0,
    )

    summary = run_global_pumpswap_migration_lane(
        BondingCurveRecorderConfig(output_root=tmp_path, enable_global_pumpswap_migration=True),
        recorder,
        source=source,
        duration_seconds=2,
    )

    events = _jsonl(tmp_path / "global_migration_events.jsonl")
    duplicates = _jsonl(tmp_path / "global_migration_event_duplicates.jsonl")
    assert summary["deduped_pumpswap_migration_events"] == 1
    assert summary["duplicate_pumpswap_rows_suppressed"] == 1
    assert events[0]["mint"] == "mint-program-subscribe"
    assert events[0]["pool_or_pair_address"] == "pool-program-subscribe"
    assert events[0]["source_route"] == "pumpswap_program_subscribe"
    assert events[0]["detection_method"] == "pumpswap_pool_account_create"
    assert events[0]["seen_in_birth_source"] is True
    assert events[0]["admitted"] is True
    assert duplicates[0]["duplicate_of_signature"] == "program-subscribe:130:pool-program-subscribe"


def test_pumpswap_program_subscribe_keeps_sol_and_usdc_pools_and_counts_quote_assets(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8790.0,
                "slot": 138,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-sol",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-sol-pool",
                    "quote_mint": recorder_module.SOL_MINT,
                    "program_subscribe_account_created": True,
                },
            },
            {
                "received_at": 8791.0,
                "slot": 139,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-usdc",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-usdc-pool",
                    "quote_mint": recorder_module.USDC_MINT,
                    "program_subscribe_account_created": True,
                },
            },
        ],
        actual_duration_seconds=2.0,
    )

    summary = run_global_pumpswap_migration_lane(
        BondingCurveRecorderConfig(output_root=tmp_path, enable_global_pumpswap_migration=True),
        recorder,
        source=source,
        duration_seconds=2,
    )

    events = _jsonl(tmp_path / "global_migration_events.jsonl")
    assert summary["deduped_pumpswap_migration_events"] == 2
    assert summary["pumpswap_raw_candidates_by_quote_asset"]["SOL"] == 1
    assert summary["pumpswap_raw_candidates_by_quote_asset"]["USDC"] == 1
    assert summary["global_migration_events_by_quote_asset"]["SOL"] == 1
    assert summary["global_migration_events_by_quote_asset"]["USDC"] == 1
    assert {row["quote_asset"] for row in events} == {"SOL", "USDC"}


def test_default_pumpswap_program_subscribe_route_filters_sol_and_usdc_quotes() -> None:
    route = recorder_module.PumpSwapProgramSubscribeMigrationRoute(websocket_url="wss://example.invalid")

    availability = route.availability()

    assert availability["quote_mints"] == [recorder_module.SOL_MINT, recorder_module.USDC_MINT]
    assert set(availability["filters_by_quote_asset"]) == {"SOL", "USDC"}


def test_default_global_migration_lane_uses_transaction_subscribe_not_account_update_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDefaultTransactionSubscribeRoute:
        source_name = "fake_default_transaction_subscribe"
        actual_duration_seconds = 1.0
        websocket_closed_early = False
        websocket_close_reason = None
        websocket_keepalive_timeout_count = 0
        websocket_reconnect_count = 0
        reconnect_attempts = 0
        reconnect_success_count = 0
        reconnect_failure_count = 0
        reconnect_reasons: list[str] = []
        total_disconnected_seconds = 0.0
        completed_requested_duration = True

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def availability(self) -> dict:
            return {"source": self.source_name, "available": True, "transactionSubscribe": True}

        def stream_notifications(self, duration_seconds: float, on_event) -> None:
            self.actual_duration_seconds = float(duration_seconds)

    monkeypatch.setattr(
        recorder_module,
        "_default_global_pumpswap_migration_route",
        lambda _config: FakeDefaultTransactionSubscribeRoute(),
    )

    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    summary = run_global_pumpswap_migration_lane(recorder.config, recorder, source=None, duration_seconds=1)

    assert summary["live_source_used"] == "fake_default_transaction_subscribe"
    assert "pumpswap_transaction_subscribe" in summary["route_status_by_route"]
    assert summary["pumpswap_swap_events_decoded"] == 0
    assert summary["source_event_queue_dropped_count"] == 0


def test_pumpswap_program_subscribe_account_updates_are_bounded_candidates(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8810.0,
                "slot": 150,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-existing",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-existing",
                    "quote_mint": recorder_module.SOL_MINT,
                },
            },
            {
                "received_at": 8811.0,
                "slot": 151,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-existing",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-existing",
                    "quote_mint": recorder_module.SOL_MINT,
                },
            },
            {
                "received_at": 8812.0,
                "slot": 152,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-existing",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-existing",
                    "quote_mint": recorder_module.SOL_MINT,
                },
            },
        ],
        actual_duration_seconds=3.0,
    )

    summary = run_global_pumpswap_migration_lane(
        BondingCurveRecorderConfig(output_root=tmp_path, enable_global_pumpswap_migration=True),
        recorder,
        source=source,
        duration_seconds=3,
    )

    assert summary["raw_pumpswap_candidates"] == 1
    assert summary["program_subscribe_unconfirmed_update_candidates"] == 1
    assert summary["program_subscribe_existing_pool_updates_suppressed"] == 2
    assert summary["deduped_pumpswap_migration_events"] == 0
    assert summary["global_migration_candidates"] == 1
    assert _jsonl(tmp_path / "global_migration_events.jsonl") == []
    assert len(_jsonl(tmp_path / "global_migration_raw_candidates.jsonl")) == 1
    assert len(_jsonl(tmp_path / "global_migration_write_intents.jsonl")) <= 2
    assert recorder.summary_counters["post_migration_observations_scheduled"] == 0
    assert not [
        row
        for row in _jsonl(tmp_path / "post_migration_observations.jsonl")
        if row.get("event_type") == "post_migration_depth_seen"
    ]


def test_pumpswap_program_subscribe_filters_bad_size_but_keeps_unknown_quote_as_candidate(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 8800.0,
                "slot": 140,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-bad-size",
                "account_data_decoded": {
                    "data_size": 200,
                    "discriminator_valid": True,
                    "base_mint": "mint-bad-size",
                    "quote_mint": "So11111111111111111111111111111111111111112",
                },
            },
            {
                "received_at": 8801.0,
                "slot": 141,
                "route_type": "programSubscribe",
                "audit_source_route": "pumpswap_program_subscribe",
                "account_pubkey": "pool-bad-quote",
                "account_data_decoded": {
                    "data_size": 245,
                    "discriminator_valid": True,
                    "base_mint": "mint-bad-quote",
                    "quote_mint": "not-sol",
                },
            },
        ],
        actual_duration_seconds=2.0,
    )

    summary = run_global_pumpswap_migration_lane(
        BondingCurveRecorderConfig(output_root=tmp_path, enable_global_pumpswap_migration=True),
        recorder,
        source=source,
        duration_seconds=2,
    )

    assert summary["raw_pumpswap_candidates"] == 1
    assert summary["unsupported_quote_asset_count"] == 1
    assert _jsonl(tmp_path / "global_migration_events.jsonl") == []
    candidates = _jsonl(tmp_path / "global_migration_candidates.jsonl")
    assert candidates[0]["mint"] == "mint-bad-quote"
    assert candidates[0]["quote_asset"] == "unsupported"


def test_axiom_reconciliation_marks_direct_lookup_pumpswap_route(tmp_path: Path) -> None:
    (tmp_path / "axiom_direct_lookup_evidence.jsonl").write_text(
        json.dumps(
            {
                "mint": "mint-direct-pool",
                "signatures_found": 4,
                "transactions_fetched": 2,
                "pumpswap_pool_create_found": True,
                "migration_like_signature": "sig-direct-pool",
                "migration_program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
                "migration_instruction_name": "CreatePool",
                "pool_or_pair_address": "pool-direct",
                "detected_route_needed": "pumpswap_account_required",
                "direct_lookup_status": "found_pool_route",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    run_axiom_reconciliation(tmp_path, [{"mint": "mint-direct-pool"}])

    row = _jsonl(tmp_path / "axiom_reconciliation.jsonl")[0]
    assert row["explanation"] == "pumpswap_route_detected"
    assert row["direct_lookup_replay_status"] == "found_pool_route"
    assert row["detection_route_needed"] == "pumpswap_account_required"
    assert row["pool_or_pair_address"] == "pool-direct"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_replay_campaign(
    root: Path,
    *,
    started_at: float = 1000.0,
    ended_at: float = 1600.0,
    migrations: list[dict] | None = None,
    births: list[dict] | None = None,
    observations: list[dict] | None = None,
    paths: list[dict] | None = None,
) -> None:
    (root / "campaign_manifest.json").write_text(
        json.dumps({"campaign_id": "campaign-test", "run_id": "campaign-test", "started_at": started_at, "ended_at": ended_at}),
        encoding="utf-8",
    )
    (root / "collector_summary.json").write_text(json.dumps({"run_id": "campaign-test"}), encoding="utf-8")
    _write_jsonl(root / "global_migration_events.jsonl", migrations or [])
    _write_jsonl(root / "birth_audit.jsonl", births or [])
    _write_jsonl(root / "curve_observations.jsonl", observations or [])
    _write_jsonl(root / "token_path_summary.jsonl", paths or [])


def _create_tx(mint: str, signature: str, block_time: int, *, slot: int = 10) -> dict:
    return {
        "slot": slot,
        "blockTime": block_time,
        "meta": {"logMessages": ["Program log: Instruction: Create"]},
        "transaction": {
            "message": {
                "instructions": [
                    {
                        "programId": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
                        "accounts": [mint, f"curve-{mint}"],
                    }
                ]
            }
        },
    }


def test_migrated_mint_replay_classifies_preexisting_launch(tmp_path: Path) -> None:
    _write_replay_campaign(
        tmp_path,
        migrations=[{"mint": "mint-pre", "signature": "sig-mig-pre", "pool_or_pair_address": "pool-pre", "quote_asset": "SOL"}],
    )
    client = FakeDirectMintLookupClient(
        {"mint-pre": [{"signature": "sig-create-pre", "slot": 9, "blockTime": 900}]},
        {"sig-create-pre": _create_tx("mint-pre", "sig-create-pre", 900, slot=9)},
    )

    summary = run_migrated_mint_replay(tmp_path, client=client, lookup_sleep_ms=0)

    row = _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")[0]
    assert row["migration_completeness_class"] == "MIGRATION_ONLY_PREEXISTING"
    assert row["launched_before_campaign"] is True
    assert row["birth_source_should_have_seen_it"] is False
    assert row["source_miss_reason"] == "launched_before_campaign"
    assert summary["migrated_preexisting_count"] == 1


def test_migrated_mint_replay_classifies_during_campaign_source_miss(tmp_path: Path) -> None:
    _write_replay_campaign(
        tmp_path,
        migrations=[{"mint": "mint-missed", "signature": "sig-mig-missed", "pool_or_pair_address": "pool-missed", "quote_asset": "SOL"}],
    )
    client = FakeDirectMintLookupClient(
        {"mint-missed": [{"signature": "sig-create-missed", "slot": 20, "blockTime": 1200}]},
        {"sig-create-missed": _create_tx("mint-missed", "sig-create-missed", 1200, slot=20)},
    )

    run_migrated_mint_replay(tmp_path, client=client, lookup_sleep_ms=0)

    row = _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")[0]
    assert row["migration_completeness_class"] == "MIGRATION_ONLY_SOURCE_MISS"
    assert row["launched_during_campaign"] is True
    assert row["birth_source_should_have_seen_it"] is True
    assert row["birth_source_missed_it"] is True
    assert row["source_miss_reason"] == "birth_route_not_watched"


def test_migrated_mint_replay_full_path_and_sample_rejected_classes(tmp_path: Path) -> None:
    _write_replay_campaign(
        tmp_path,
        migrations=[
            {"mint": "mint-full", "signature": "sig-mig-full", "pool_or_pair_address": "pool-full", "quote_asset": "SOL"},
            {"mint": "mint-sampled", "signature": "sig-mig-sampled", "pool_or_pair_address": "pool-sampled", "quote_asset": "SOL"},
        ],
        births=[
            {"mint": "mint-full", "admitted": True, "admission_reason": "sample_admitted"},
            {"mint": "mint-sampled", "admitted": False, "admission_reason": "sample_rejected"},
        ],
        observations=[{"mint": "mint-full", "progress_pct": 65.0, "decode_status": "decoded"}],
        paths=[{"mint": "mint-full", "curve_observation_count": 1, "highest_progress_pct": 65.0}],
    )

    summary = run_migrated_mint_replay(tmp_path, client=FakeDirectMintLookupClient({}, {}), lookup_sleep_ms=0)

    rows = {row["mint"]: row for row in _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")}
    assert rows["mint-full"]["migration_completeness_class"] == "FULL_PATH"
    assert rows["mint-sampled"]["migration_completeness_class"] == "SAMPLE_REJECTED_WITH_MIGRATION"
    assert summary["migrated_full_path_count"] == 1
    assert summary["migrated_sample_rejected_count"] == 1


def test_migrated_mint_replay_unresolved_and_summary_outputs(tmp_path: Path) -> None:
    _write_replay_campaign(
        tmp_path,
        migrations=[{"mint": "mint-unresolved", "signature": "sig-mig-unresolved", "pool_or_pair_address": "pool-unresolved"}],
    )

    summary = run_migrated_mint_replay(tmp_path, client=FakeDirectMintLookupClient({}, {}), lookup_sleep_ms=0)

    row = _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")[0]
    assert row["migration_completeness_class"] == "MIGRATION_ONLY_REPLAY_UNRESOLVED"
    assert row["replay_birth_found"] is False
    assert summary["migrated_replay_unresolved_count"] == 1
    assert (tmp_path / "migrated_mint_completeness.csv").exists()
    assert (tmp_path / "migrated_mint_replay_summary.json").exists()
    assert (tmp_path / "campaign_quality_gate.json").exists()
    assert summary["valuation_ladder_emission_policy"] == "market_cap_confirmed_only"
    assert summary["mayhem_code_modified"] is False


def test_thin_tracking_schema_records_sampled_out_birth_without_enabling_ladder(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=0))

    row = recorder.process_birth(_launch("mint-thin"))

    probe_rows = _jsonl(tmp_path / "probe_attempts.jsonl")
    assert row["admitted"] is False
    assert row["tracking_tier"] == "thin"
    assert row["deep_tracking_admitted"] is False
    assert row["enrichment_sampling_status"] == "sampled_out"
    assert probe_rows[0]["mint"] == "mint-thin"
    assert probe_rows[0]["tracking_tier"] == "thin"
    assert probe_rows[0]["probe_status"] == "scheduled"
    assert recorder.build_summary()["valuation_ladder_emission_policy"] == "market_cap_confirmed_only"


def test_deep_tracking_escalates_when_progress_crosses_threshold(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    recorder.process_birth(_launch("mint-escalate"))

    row = recorder.record_observation(_obs("mint-escalate", 45.0, 1.0))

    assert row["tracking_tier"] == "escalated"
    path_summary = _jsonl(tmp_path / "token_path_summary.jsonl")
    recorder.finalize()
    path_summary = _jsonl(tmp_path / "token_path_summary.jsonl")
    assert path_summary[0]["tracking_tier"] == "escalated"


def _txsub_payload_for_pumpfun_layout(
    mint: str,
    *,
    signature: str,
    slot: int,
    instruction_level: str = "top_level",
    mint_index: int = 2,
    data: list[int] | None = None,
    token_program: str = recorder_module.USDC_MINT,
) -> dict:
    curve = bonding_curve_pda(mint)
    accounts = [f"acct-{idx}-{mint[:4]}" for idx in range(18)]
    accounts[mint_index] = mint
    accounts[mint_index + 1] = curve
    accounts[6] = f"creator-{mint[:4]}"
    accounts[8] = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb" if token_program == "token2022" else "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    accounts[11] = recorder_module.PUMP_FUN_PROGRAM_ID_FOR_AUDIT
    instruction = {
        "programId": recorder_module.PUMP_FUN_PROGRAM_ID_FOR_AUDIT,
        "accounts": accounts,
        "data": data,
    }
    if instruction_level == "inner":
        top_instructions = [{"programId": "FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9", "accounts": accounts[:6]}]
        inner = [{"index": 0, "instructions": [instruction]}]
    else:
        top_instructions = [instruction]
        inner = []
    return {
        "params": {
            "result": {
                "slot": slot,
                "transaction": {
                    "transaction": {
                        "signatures": [signature],
                        "message": {
                            "accountKeys": [{"pubkey": account} for account in accounts],
                            "instructions": top_instructions,
                        },
                    },
                    "meta": {
                        "logMessages": ["Program log: Create"],
                        "innerInstructions": inner,
                    },
                    "slot": slot,
                    "blockTime": 1781415000,
                },
            }
        }
    }


@pytest.mark.parametrize(
    ("mint", "signature", "instruction_level", "mint_index", "data"),
    [
        ("2oP7a1jrLgfuSHmBPMxteJZ1VzgBUkrMydQBxomEpump", "4Nj6baPq", "top_level", 2, list(bytes.fromhex("da40faee6589f5d6"))),
        ("EFowy7zw1qMwN8bnqHhU4cnDXvsDSnxAVtpYazuMpump", "42zTtXTX", "inner", 2, None),
        ("BsrZnHHz17nQPHhab7vY7RhAzUBb6fnQZxwQr1hBpump", "31wK5rMp", "top_level", 1, None),
    ],
)
def test_replayed_source_missed_launch_layouts_decode_to_birth_rows(
    mint: str,
    signature: str,
    instruction_level: str,
    mint_index: int,
    data: list[int] | None,
) -> None:
    payload = _txsub_payload_for_pumpfun_layout(
        mint,
        signature=signature,
        slot=426353216,
        instruction_level=instruction_level,
        mint_index=mint_index,
        data=data,
        token_program="token2022",
    )

    rows = decode_pumpfun_transaction_subscribe_notification(payload, observed_at=1781415000.0)

    assert len(rows) == 1
    assert rows[0]["mint"] == mint
    assert rows[0]["bonding_curve"] == bonding_curve_pda(mint)
    assert rows[0]["source_instruction_decode_route"] == "pumpfun_mint_curve_layout_create"
    assert rows[0]["parser_status"] == "decoded"


def test_repaired_birth_route_sets_capture_provenance(tmp_path: Path) -> None:
    mint = "2oP7a1jrLgfuSHmBPMxteJZ1VzgBUkrMydQBxomEpump"
    payload = _txsub_payload_for_pumpfun_layout(
        mint,
        signature="4Nj6baPq",
        slot=426353216,
        data=list(bytes.fromhex("da40faee6589f5d6")),
        token_program="token2022",
    )
    decoded_rows = decode_pumpfun_transaction_subscribe_notification(payload, observed_at=1781415000.0)
    source = FakeTransactionSubscribeAuditRoute(
        [{"received_at": 1781415000.0, "signature": "4Nj6baPq", "slot": 426353216, "decoded_rows": decoded_rows}],
        actual_duration_seconds=1.0,
    )

    run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1, sample_rate_percent=100),
        source=source,
        curve_probe=FakeCurveStateProbe({}),
        now_fn=lambda: 1781415001.0,
    )

    birth = _jsonl(tmp_path / "birth_audit.jsonl")[0]
    assert birth["mint"] == mint
    assert birth["birth_capture_route"] == "transaction_subscribe:pumpfun_mint_curve_layout_create"
    assert birth["birth_capture_method"] == "transaction_subscribe_live"
    assert birth["birth_capture_confidence"] == "decoded"
    assert birth["birth_backfilled_from_replay"] is False
    assert birth["birth_seen_live"] is True
    assert birth["birth_source_route_version"] == "t007af_birth_source_route_v2"


def test_replay_backfill_creates_birth_row_when_migration_seen_but_birth_absent(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_replay_backfilled_birth(
        {
            "mint": "mint-backfilled",
            "launch_signature_from_replay": "sig-backfilled",
            "launch_slot_from_replay": 123,
            "launch_time_from_replay": 456,
            "pool_or_pair_address": "pool-backfilled",
            "quote_asset": "SOL",
        }
    )

    assert row["mint"] == "mint-backfilled"
    assert row["birth_backfilled_from_replay"] is True
    assert row["birth_seen_live"] is False
    assert row["birth_capture_method"] == "global_migration_replay_backfill"
    assert _jsonl(tmp_path / "birth_audit.jsonl")[0]["birth_backfilled_from_replay"] is True


def test_unknown_pumpswap_migration_enqueues_bounded_replay_backfill_job(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, migration_backfill_queue_max_size=1)
    )

    result = recorder.enqueue_migration_backfill(
        {
            "mint": "mint-unknown-migration",
            "signature": "sig-migration",
            "pool_or_pair_address": "pool-unknown",
            "quote_asset": "SOL",
        }
    )

    jobs = _jsonl(tmp_path / "migration_backfill_jobs.jsonl")
    assert result["enqueued"] is True
    assert jobs[0]["mint"] == "mint-unknown-migration"
    assert jobs[0]["backfill_trigger"] == "migration_event"
    assert jobs[0]["status"] == "queued"
    summary = recorder.build_summary()
    assert summary["migration_backfill_jobs_enqueued"] == 1
    assert summary["migration_backfill_queue_high_water"] == 1


def test_replay_backfill_enqueue_writes_birth_row_with_trigger_provenance(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    client = FakeDirectMintLookupClient(
        {"mint-backfill-live": [{"signature": "sig-create-live", "slot": 20, "blockTime": 1200}]},
        {"sig-create-live": _create_tx("mint-backfill-live", "sig-create-live", 1200, slot=20)},
    )

    result = recorder.enqueue_migration_backfill(
        {
            "mint": "mint-backfill-live",
            "signature": "sig-migrate-live",
            "pool_or_pair_address": "pool-live",
            "quote_asset": "SOL",
        },
        client=client,
        lookup_sleep_ms=0,
    )

    birth = _jsonl(tmp_path / "birth_audit.jsonl")[0]
    assert result["completed"] is True
    assert birth["mint"] == "mint-backfill-live"
    assert birth["birth_seen_live"] is False
    assert birth["birth_backfilled_from_replay"] is True
    assert birth["birth_capture_method"] == "global_migration_replay_backfill"
    assert birth["birth_capture_route"] == "global_migration:replay_backfill"
    assert birth["birth_capture_confidence"] == "replay_backfilled"
    assert birth["backfill_trigger"] == "migration_event"
    assert birth["backfill_trigger_signature"] == "sig-migrate-live"
    assert birth["backfill_job_id"] == result["backfill_job_id"]
    summary = recorder.build_summary()
    assert summary["migration_backfill_jobs_completed"] == 1
    assert summary["migration_backfilled_birth_rows_written"] == 1
    assert summary["migration_backfill_success_rate"] == 1.0


def test_global_migration_writer_completes_backfill_when_live_replay_client_supplied(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))
    client = FakeDirectMintLookupClient(
        {"mint-global-backfill": [{"signature": "sig-create-global", "slot": 20, "blockTime": 1200}]},
        {"sig-create-global": _create_tx("mint-global-backfill", "sig-create-global", 1200, slot=20)},
    )
    writer = recorder_module.GlobalMigrationDedupeWriter(
        tmp_path,
        recorder=recorder,
        migration_backfill_client=client,
        migration_backfill_lookup_sleep_ms=0,
    )

    status = writer.record(
        {
            "mint": "mint-global-backfill",
            "signature": "sig-migrate-global",
            "pool_or_pair_address": "pool-global",
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pool_create",
        }
    )

    birth = _jsonl(tmp_path / "birth_audit.jsonl")[0]
    jobs = _jsonl(tmp_path / "migration_backfill_jobs.jsonl")
    assert status == "event"
    assert jobs[-1]["status"] == "completed"
    assert birth["birth_backfilled_from_replay"] is True
    assert birth["backfill_trigger_signature"] == "sig-migrate-global"
    summary = recorder.build_summary()
    assert summary["migration_backfill_jobs_enqueued"] == 1
    assert summary["migration_backfill_jobs_completed"] == 1
    assert summary["migration_backfilled_birth_rows_written"] == 1


def test_replay_backfill_failure_is_counted_without_blocking(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    result = recorder.enqueue_migration_backfill(
        {
            "mint": "mint-backfill-fail",
            "signature": "sig-migrate-fail",
            "pool_or_pair_address": "pool-fail",
            "quote_asset": "SOL",
        },
        client=FakeDirectMintLookupClient({}, {}),
        lookup_sleep_ms=0,
    )

    jobs = _jsonl(tmp_path / "migration_backfill_jobs.jsonl")
    assert result["completed"] is False
    assert jobs[-1]["status"] == "failed"
    assert jobs[-1]["failure_reason"] == "replay_birth_not_found"
    summary = recorder.build_summary()
    assert summary["migration_backfill_jobs_failed"] == 1
    assert summary["migration_backfill_success_rate"] == 0.0


def test_backfilled_migration_mint_becomes_backfilled_birth_with_migration(tmp_path: Path) -> None:
    _write_replay_campaign(
        tmp_path,
        migrations=[{"mint": "mint-backfilled-class", "signature": "sig-mig", "pool_or_pair_address": "pool", "quote_asset": "SOL"}],
        births=[
            {
                "mint": "mint-backfilled-class",
                "admitted": False,
                "admission_reason": "sample_rejected",
                "birth_backfilled_from_replay": True,
                "birth_seen_live": False,
            }
        ],
    )

    summary = run_migrated_mint_replay(tmp_path, client=FakeDirectMintLookupClient({}, {}), lookup_sleep_ms=0)

    row = _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")[0]
    assert row["migration_completeness_class"] == "BACKFILLED_BIRTH_WITH_MIGRATION"
    assert summary["migrated_backfilled_birth_count"] == 1


def test_every_birth_schedules_thin_probe_even_when_deep_admitted(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    birth = recorder.process_birth(_launch("mint-deep-thin-marker"))

    assert birth["admitted"] is True
    assert birth["thin_probe_scheduled"] is True
    assert recorder.build_summary()["thin_probe_scheduled_count"] == 1


def test_sampled_out_birth_runs_successful_thin_probe_and_replay_class_is_thin_path(tmp_path: Path) -> None:
    mint = "mint-sampled-thin"
    source = FakeTransactionSubscribeAuditRoute(
        [{"received_at": 2000.0, "signature": "sig-birth", "slot": 20, "decoded_rows": [{**_launch(mint, received_at=2000.0), "bonding_curve": f"curve-{mint}"}]}],
        actual_duration_seconds=1.0,
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1, sample_rate_percent=0),
        source=source,
        curve_probe=FakeCurveStateProbe({mint: {"progress_pct": 12.5, "fdv_units": "usd", "fdv_usd": 0}}),
        now_fn=lambda: 2000.2,
    )

    birth = _jsonl(tmp_path / "birth_audit.jsonl")[0]
    observations = _jsonl(tmp_path / "curve_observations.jsonl")
    assert birth["admitted"] is False
    assert birth["thin_probe_scheduled"] is True
    assert observations[0]["mint"] == mint
    assert observations[0]["tracking_tier"] == "thin"
    assert summary["sampled_out_with_thin_path_count"] == 1

    _write_jsonl(tmp_path / "global_migration_events.jsonl", [{"mint": mint, "signature": "sig-mig", "pool_or_pair_address": "pool", "quote_asset": "SOL"}])
    replay = run_migrated_mint_replay(tmp_path, client=FakeDirectMintLookupClient({}, {}), lookup_sleep_ms=0)
    row = _jsonl(tmp_path / "migrated_mint_replay_rows.jsonl")[0]
    assert row["migration_completeness_class"] == "SAMPLE_REJECTED_WITH_THIN_PATH"
    assert replay["migrated_sample_rejected_with_thin_path_count"] == 1


def test_capacity_rejected_birth_runs_scheduled_thin_probe_retries_account_not_found(tmp_path: Path) -> None:
    admitted_mint = "mint-admitted-protected"
    rejected_mint = "mint-capacity-thin"
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 2000.0,
                "signature": "sig-births",
                "slot": 20,
                "decoded_rows": [
                    {**_launch(admitted_mint, received_at=2000.0), "bonding_curve": f"curve-{admitted_mint}"},
                    {**_launch(rejected_mint, received_at=2000.1), "bonding_curve": f"curve-{rejected_mint}"},
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    probe = FakeCurveStateProbe(
        {
            admitted_mint: {"progress_pct": 80.0, "fdv_units": "usd", "fdv_usd": 0},
            rejected_mint: [
                {"probe_status": "failed", "failure_reason": "account_not_found", "decode_status": "decode_failed"},
                {"progress_pct": 12.5, "fdv_units": "usd", "fdv_usd": 0},
            ],
        }
    )

    summary = run_transaction_live_smoke(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            source_duration_seconds=1,
            sample_rate_percent=100,
            max_active_tracking=1,
            thin_probe_retry_delays_ms=(1,),
        ),
        source=source,
        curve_probe=probe,
        now_fn=lambda: 2000.2,
    )

    births = {row["mint"]: row for row in _jsonl(tmp_path / "birth_audit.jsonl")}
    rejected_attempt_rows = [
        row for row in _jsonl(tmp_path / "probe_attempts.jsonl") if row.get("mint") == rejected_mint
    ]
    rejected_attempts = [row for row in rejected_attempt_rows if row.get("actual_probe_executed") is True]

    assert births[admitted_mint]["admitted"] is True
    assert births[rejected_mint]["admitted"] is False
    assert str(births[rejected_mint]["admission_reason"]).startswith("capacity_rejected_active_tracking_limit")
    assert births[rejected_mint]["thin_probe_scheduled"] is True
    assert [call["mint"] for call in probe.calls] == [admitted_mint, rejected_mint, rejected_mint]
    scheduled_rows = [row for row in rejected_attempt_rows if row.get("probe_status") == "scheduled"]
    assert scheduled_rows
    assert scheduled_rows[0]["actual_probe_executed"] is False
    assert len(rejected_attempts) == 2
    assert rejected_attempts[0]["actual_probe_executed"] is True
    assert rejected_attempts[0]["account_found"] is False
    assert rejected_attempts[0]["decode_error"] == "account_not_found"
    assert rejected_attempts[1]["actual_probe_executed"] is True
    assert rejected_attempts[1]["account_found"] is True
    assert summary["capacity_rejected_after_prune_count"] == 1
    assert summary["final_account_not_found_count"] == 0


def test_thin_probe_overload_defers_without_blocking_deep_tracking(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, thin_probe_queue_max_size=0)
    )

    birth = recorder.process_birth(_launch("mint-deep-not-blocked"))

    assert birth["admitted"] is True
    assert birth["thin_probe_scheduled"] is False
    assert "mint-deep-not-blocked" in recorder.states
    summary = recorder.build_summary()
    assert summary["thin_probe_deferred_count"] == 1
    assert summary["deep_probe_delayed_by_thin_count"] == 0


def test_migration_event_escalates_thin_tracked_token(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=0))
    recorder.process_birth(_launch("mint-thin-migrates"))

    writer = recorder_module.GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)
    status = writer.record(
        {
            "mint": "mint-thin-migrates",
            "signature": "sig-mig-thin",
            "pool_or_pair_address": "pool-thin",
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pool_create",
        }
    )

    state = recorder.states["mint-thin-migrates"]
    assert status == "event"
    assert state.tracking_tier == "escalated"
    assert state.tracking_tier_reason == "global_migration_event"


def test_t01110_high_cap_profile_is_explicit_not_default(tmp_path: Path) -> None:
    default = BondingCurveRecorderConfig(output_root=tmp_path / "default")
    high = BondingCurveRecorderConfig(output_root=tmp_path / "high", tracking_profile="high_cap_full_path_proof")
    settings = tracking_profile_settings("high_cap_full_path_proof")

    assert default.tracking_profile == "conservative_default"
    assert default.max_active_tracking != 800
    assert default.migration_aware_promotion_enabled is False
    assert settings["max_active_tracking"] == 800
    assert high.tracking_profile == "high_cap_full_path_proof"
    assert high.max_active_tracking == 800
    assert high.followup_queue_max_size == 2000
    assert high.migration_aware_promotion_enabled is True
    assert high.reserved_migration_candidate_slots == 150


def test_t01110_migration_promotes_capacity_deferred_mint_and_writes_event(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            migration_aware_promotion_enabled=True,
        )
    )
    recorder.process_birth(_launch("mint-active", received_at=100.0))
    deferred = recorder.process_birth(_launch("mint-cap-promote", received_at=101.0))

    assert deferred["admitted"] is False
    assert str(deferred["admission_reason"]).startswith("capacity_rejected")
    assert recorder.states["mint-cap-promote"].tracking_tier == "deferred_enrichment"

    status = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder).record(
        {
            "mint": "mint-cap-promote",
            "signature": "sig-cap-promote",
            "slot": 20,
            "received_at": 150.0,
            "pool_or_pair_address": "pool-cap-promote",
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
        }
    )

    state = recorder.states["mint-cap-promote"]
    events = _jsonl(tmp_path / "promotion_events.jsonl")
    assert status == "event"
    assert state.tracking_tier == "escalated"
    assert state.deep_tracking_admitted is True
    assert state.tracking_tier_reason == "global_migration_event"
    assert events[-1]["mint"] == "mint-cap-promote"
    assert events[-1]["previous_tracking_tier"] == "deferred_enrichment"
    assert events[-1]["promotion_trigger"] == "global_migration_event"


def test_t01110_progress_and_trade_thresholds_write_promotion_events(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            migration_aware_promotion_enabled=True,
            promote_on_trade_rows=3,
        )
    )
    recorder.process_birth(_launch("mint-active", received_at=100.0))
    recorder.process_birth(_launch("mint-progress-promote", received_at=101.0))
    recorder.process_birth(_launch("mint-trade-promote", received_at=102.0))

    recorder.record_observation(_obs("mint-progress-promote", 25.0, 10.0))
    for index in range(3):
        recorder.record_trade_event(
            {
                "mint": "mint-trade-promote",
                "received_at": 110.0 + index,
                "side": "buy",
                "quote_amount": 0.1,
                "trader_wallet": f"wallet-{index}",
            }
        )

    events = _jsonl(tmp_path / "promotion_events.jsonl")
    triggers_by_mint = {row["mint"]: row["promotion_trigger"] for row in events}
    assert recorder.states["mint-progress-promote"].deep_tracking_admitted is True
    assert recorder.states["mint-trade-promote"].deep_tracking_admitted is True
    assert triggers_by_mint["mint-progress-promote"] == "curve_progress_threshold"
    assert triggers_by_mint["mint-trade-promote"] == "trade_rows_threshold"


def test_t01110_low_priority_active_mint_can_be_evicted_for_migration_promotion(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_active_tracking=1,
            migration_aware_promotion_enabled=True,
            evict_low_priority_stale_mints_for_promotion=True,
        )
    )
    recorder.process_birth(_launch("mint-low-priority", received_at=100.0))
    recorder.process_birth(_launch("mint-migration-priority", received_at=101.0))

    GlobalMigrationDedupeWriter(tmp_path, recorder=recorder).record(
        {
            "mint": "mint-migration-priority",
            "signature": "sig-migration-priority",
            "slot": 20,
            "received_at": 500.0,
            "pool_or_pair_address": "pool-migration-priority",
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
        }
    )

    evictions = _jsonl(tmp_path / "promotion_evictions.jsonl")
    assert recorder.states["mint-low-priority"].stopped is True
    assert recorder.states["mint-low-priority"].stop_reason == "promotion_reserved_capacity_eviction"
    assert recorder.states["mint-migration-priority"].deep_tracking_admitted is True
    assert evictions[-1]["evicted_mint"] == "mint-low-priority"
    assert evictions[-1]["promoted_mint"] == "mint-migration-priority"


def test_t01110_capacity_promotion_simulation_reports_deferred_migration(tmp_path: Path) -> None:
    _write_t007bc_jsonl(
        tmp_path,
        "birth_audit.jsonl",
        [
            {
                "mint": "mint-capacity-migrated",
                "admitted": False,
                "admission_reason": "capacity_rejected_active_tracking_limit_after_prune",
                "thin_probe_scheduled": True,
                "received_at": 100.0,
                "slot": 10,
            }
        ],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "curve_observations.jsonl",
        [{"mint": "mint-capacity-migrated", "progress_pct": 55.0, "received_at": 120.0, "slot": 12}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "trade_flow_events.jsonl",
        [{"mint": "mint-capacity-migrated", "received_at": 121.0, "trade_count_since_launch": 6}],
    )
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [
            {
                "mint": "mint-capacity-migrated",
                "signature": "sig-capacity-migrated",
                "migration_received_at": 150.0,
                "received_at": 150.0,
                "slot": 20,
                "pool_or_pair_address": "pool-capacity-migrated",
                "quote_asset": "SOL",
            }
        ],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": "mint-capacity-migrated", "received_at": 151.0}])
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")

    summary = run_capacity_rejected_migration_promotion_simulation(tmp_path)
    rows = summary["rows"]

    assert summary["capacity_rejected_migration_rows"] == 1
    assert summary["would_promote_under_new_policy_count"] == 1
    assert summary["likely_decision_safe_if_promoted_earlier_count"] == 1
    assert rows[0]["mint"] == "mint-capacity-migrated"
    assert rows[0]["promotion_trigger"] in {"curve_progress_threshold", "trade_rows_threshold", "global_migration_candidate"}
    assert (tmp_path / "capacity_rejected_migration_promotion_simulation.json").exists()
    assert (tmp_path / "capacity_rejected_migration_audit.md").exists()


def test_t01110_reconciles_live_status_with_migration_linkage_full_paths(tmp_path: Path) -> None:
    mint = "mint-full-path"
    _write_t007bc_jsonl(tmp_path, "birth_audit.jsonl", [{"mint": mint, "admitted": True, "received_at": 100.0, "slot": 10}])
    _write_t007bc_jsonl(tmp_path, "curve_observations.jsonl", [{"mint": mint, "received_at": 120.0, "slot": 12}])
    _write_t007bc_jsonl(tmp_path, "trade_flow_events.jsonl", [{"mint": mint, "received_at": 121.0, "trade_flow_status": "available"}])
    _write_t007bc_jsonl(
        tmp_path,
        "global_migration_events.jsonl",
        [{"mint": mint, "migration_received_at": 150.0, "received_at": 150.0, "slot": 20, "pool_or_pair_address": "pool-full-path"}],
    )
    _write_t007bc_jsonl(tmp_path, "post_migration_observations.jsonl", [{"mint": mint, "received_at": 151.0}])
    (tmp_path / "live_status.json").write_text(json.dumps({"decision_safe_full_paths": 0}), encoding="utf-8")
    (tmp_path / "collector_summary.json").write_text(json.dumps({"global_migration_events_deduped": 1}), encoding="utf-8")

    summary = run_migration_full_path_status_reconciliation(tmp_path)
    audit = run_tracking_admission_audit(tmp_path)
    live_status = json.loads((tmp_path / "live_status.json").read_text(encoding="utf-8"))

    assert summary["decision_safe_full_paths"] == 1
    assert summary["live_status_previous_decision_safe_full_paths"] == 0
    assert summary["live_status_reconciled_decision_safe_full_paths"] == 1
    assert live_status["decision_safe_full_paths"] == 1
    assert live_status["row_derived_decision_safe_full_paths"] == 1
    assert audit["birth_seen_but_not_admitted_migrations"] == 0
    assert (tmp_path / "migration_full_path_status_reconciliation.md").exists()


def test_high_progress_token_is_not_pruned_due_to_thin_queue_pressure(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, max_active_tracking=1, thin_probe_queue_max_size=0)
    )
    recorder.process_birth(_launch("mint-high-progress"))
    recorder.record_observation(_obs("mint-high-progress", 65.0, 1.0))

    rejected = recorder.process_birth(_launch("mint-new"))

    assert rejected["admitted"] is False
    assert "mint-high-progress" in recorder.states
    assert recorder.states["mint-high-progress"].stopped is False
    assert recorder.build_summary()["thin_probe_deferred_count"] >= 1


def test_t007ag_guardrails_keep_valuation_ladder_suppressed_and_mayhem_untouched(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    recorder.process_birth(_launch("mint-guardrail"))
    recorder.record_observation({**_obs("mint-guardrail", 45.0, 1.0), "fdv_proxy": 250_000, "fdv_units": "usd"})

    summary = recorder.build_summary()
    assert summary["valuation_ladder_emission_policy"] == "market_cap_confirmed_only"
    assert summary["valuation_ladder_events_written"] == 0
    assert summary["valuation_ladder_suppressed_untrusted_count"] >= 1
    assert summary["mayhem_code_modified"] is False


def test_t007ap_report_writes_requested_output_aliases_and_analysis_result(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007aa_forward_thesis_dataset_report import run_report

    campaign = tmp_path / "campaign"
    output = tmp_path / "report"
    campaign.mkdir()
    (campaign / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-t007ap",
                "unique_birth_mints": 3,
                "admitted_births": 2,
                "valuation_ladder_emission_policy": "market_cap_confirmed_only",
                "valuation_ladder_events_written": 0,
                "trade_flow_events_written": 1,
                "organic_flow_events_written": 1,
                "buyer_breadth_available_count": 1,
                "holder_distribution_snapshots_written": 1,
                "dev_behavior_events_written": 1,
                "post_migration_observations_written": 2,
                "execution_cost_observations_written": 1,
                "post_migration_pool_state_partial_count": 1,
                "post_migration_pool_state_error_count": 1,
                "post_migration_quote_deferred_count": 2,
                "pool_liquidity_quote_present_count": 0,
                "pool_liquidity_usd_present_count": 0,
                "valid_60m_thesis_collection_passed": True,
            }
        ),
        encoding="utf-8",
    )
    (campaign / "campaign_manifest.json").write_text(json.dumps({"campaign_id": "campaign-t007ap"}), encoding="utf-8")
    (campaign / "trade_flow_events.jsonl").write_text(json.dumps({"trade_flow_status": "available"}) + "\n", encoding="utf-8")
    (campaign / "organic_flow_events.jsonl").write_text(json.dumps({"organic_share_status": "partial"}) + "\n", encoding="utf-8")
    (campaign / "global_migration_events.jsonl").write_text(json.dumps({"mint": "mint-a", "quote_asset": "SOL"}) + "\n", encoding="utf-8")
    (campaign / "post_migration_observations.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"mint": "mint-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 0, "pool_state_status": "partial", "executable_quote_status": "deferred"}),
                json.dumps({"mint": "mint-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 5, "pool_state_status": "error", "pool_state_error_reason": "pumpswap_market_decode_failed", "executable_quote_status": "deferred"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (campaign / "execution_cost_observations.jsonl").write_text(json.dumps({"execution_cost_status": "partial"}) + "\n", encoding="utf-8")

    result = run_report([campaign], output)
    required = {
        "analysis_result.json",
        "trade_flow_outcomes.csv",
        "post_migration_outcomes.csv",
        "execution_cost_outcomes.csv",
        "post_migration_exit_outcomes.csv",
        "execution_cost_quality.csv",
    }

    assert required <= {path.name for path in output.iterdir()}
    analysis = json.loads((output / "analysis_result.json").read_text(encoding="utf-8"))
    assert result["analysis_result_path"] == str(output / "analysis_result.json")
    assert analysis["campaign_count"] == 1
    assert analysis["campaigns"][0]["input_root"] == str(campaign)
    assert analysis["campaigns"][0]["run_id"] == "run-t007ap"
    assert analysis["campaigns"][0]["final_decision_label"] == "T007_60M_PIPELINE_VALIDATION_PARTIAL_NOT_THESIS_READY"
    assert analysis["campaigns"][0]["valuation_ladder_suppressed"] is True
    assert analysis["campaigns"][0]["mayhem_files_modified"] is False


def test_t007ap_pool_state_expected_unavailable_is_not_hard_error(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-unavailable",
            "pool_or_pair_address": "pool-unavailable",
            "quote_asset": "SOL",
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "not_available",
            "depth_status": "not_available",
            "pool_state_error_reason": "account_not_found",
        }
    )
    summary = recorder.build_summary()

    assert row["pool_state_status"] == "not_available"
    assert row["depth_status"] == "not_available"
    assert summary["post_migration_pool_state_not_available_count"] == 1
    assert summary["post_migration_pool_state_error_count"] == 0
    assert summary["post_migration_observation_errors"] == 0


def test_t007ap_pool_state_decode_exception_remains_hard_error(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-decode-error",
            "pool_or_pair_address": "pool-decode-error",
            "quote_asset": "SOL",
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 5,
            "observation_received_at": 1005.0,
            "pool_state_status": "error",
            "depth_status": "error",
            "pool_state_error_reason": "pumpswap_market_decode_failed",
            "pool_account_size": 301,
            "pool_discriminator": "f19a6d0411b16dbc",
        }
    )
    summary = recorder.build_summary()

    assert row["pool_state_status"] == "error"
    assert row["pool_state_error_reason"] == "pumpswap_market_decode_failed"
    assert summary["post_migration_pool_state_error_count"] == 1
    assert summary["post_migration_observation_errors"] == 1


def test_t007ap_pool_state_diagnosis_groups_reason_horizon_and_quote_asset(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007aa_forward_thesis_dataset_report import diagnose_pool_state_errors

    campaign = tmp_path / "campaign"
    output_json = tmp_path / "diagnosis.json"
    output_csv = tmp_path / "diagnosis.csv"
    campaign.mkdir()
    (campaign / "post_migration_observations.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"mint": "mint-a", "pool_or_pair_address": "pool-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 0, "pool_state_status": "error", "pool_state_error_reason": "account_not_found"}),
                json.dumps({"mint": "mint-a", "pool_or_pair_address": "pool-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 5, "pool_state_status": "partial", "pool_state_error_reason": "reserve_token_accounts_not_decoded_yet"}),
                json.dumps({"mint": "mint-b", "pool_or_pair_address": "pool-b", "quote_asset": "USDC", "horizon_seconds_after_migration": 15, "pool_state_status": "error", "pool_state_error_reason": "pumpswap_market_decode_failed", "pool_account_size": 301, "pool_discriminator": "bad"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    diagnosis = diagnose_pool_state_errors(campaign, output_json, output_csv)

    assert diagnosis["error_count"] == 2
    assert diagnosis["error_breakdown_by_classification"] == {"pool_account_fetch_failed": 1, "decode_exception": 1}
    assert diagnosis["error_breakdown_by_horizon_seconds"] == {"0": 1, "15": 1}
    assert diagnosis["error_breakdown_by_quote_asset"] == {"SOL": 1, "USDC": 1}
    rows = _jsonl(output_json.with_suffix(".jsonl")) if output_json.with_suffix(".jsonl").exists() else []
    assert output_json.exists()
    assert output_csv.exists()
    assert diagnosis["diagnosed_rows"][0]["same_pool_later_produced_partial_or_available"] is True
    assert rows == []


def test_t007ap_readiness_gate_blocks_2h_plus_when_pool_hard_error_rate_too_high() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        {
            "trade_flow_events_written": 10,
            "organic_flow_events_written": 10,
            "buyer_breadth_available_count": 10,
            "holder_distribution_snapshots_written": 10,
            "dev_behavior_events_written": 10,
            "post_migration_observations_written": 100,
            "execution_cost_observations_written": 10,
            "post_migration_pool_state_error_count": 49,
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "valid_60m_thesis_collection_passed": True,
        }
    )

    assert gate["can_run_2h_plus_scan"] is False
    assert "post_migration_pool_state_hard_error_rate_too_high" in gate["blocking_reasons"]
    assert gate["valuation_ladder_suppressed"] is True
    assert gate["mayhem_files_modified"] is False


def test_t007ap_pumpswap_301_byte_pool_account_decodes_as_metadata_variant() -> None:
    data = _pumpswap_fixture_account_data(SOL_MINT, USDC_MINT) + (b"\x00" * 56)

    decoded = _decode_pumpswap_market_account_data(data, account_pubkey="pool-301")

    assert decoded is not None
    assert decoded["data_size"] == 301
    assert decoded["pool_or_pair_address"] == "pool-301"
    assert decoded["base_mint"] == SOL_MINT
    assert decoded["quote_mint"] == USDC_MINT
    assert decoded["layout_variant"] == "pumpswap_pool_v1_301_identity_prefix"


def _t007aq_live_feature_payload(**overrides) -> dict:
    payload = {
        "unique_birth_mints": 10,
        "progress_decoded_exact_count": 10,
        "true_curve_threshold_crossings_written": 3,
        "curve_velocity_events_written": 10,
        "curve_acceleration_events_written": 5,
        "trade_flow_events_written": 10,
        "buyer_breadth_available_count": 4,
        "global_migration_events": 2,
        "token_path_summary_rows": 10,
        "decision_time_safety_violation_count": 0,
        "organic_flow_events_written": 10,
        "holder_distribution_snapshots_written": 10,
        "dev_behavior_events_written": 10,
        "post_migration_observations_written": 8,
        "execution_cost_observations_written": 2,
        "valuation_ladder_emission_policy": "market_cap_confirmed_only",
        "post_migration_pool_state_error_count": 0,
        "post_migration_quote_deferred_count": 8,
        "post_migration_quote_available_count": 0,
        "pool_liquidity_quote_present_count": 0,
        "pool_liquidity_usd_present_count": 0,
        "valid_60m_thesis_collection_passed": True,
    }
    payload.update(overrides)
    return payload


def test_t007aq_gate_blocks_full_thesis_60m_when_executable_quote_is_deferred() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(pool_liquidity_quote_present_count=3, pool_liquidity_usd_present_count=3),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert gate["quote_depth_required_for_scope"] is True
    assert gate["executable_quote_available"] is False
    assert gate["can_run_60m_thesis_scan"] is False
    assert gate["can_test_post_migration_exit_thesis"] is False
    assert gate["allowed_scan_scope"] == "10m_feature_proof_only"
    assert "executable_quote_not_available" in gate["blocking_reasons"]


def test_t007aq_gate_blocks_full_thesis_60m_when_liquidity_counts_are_zero() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(post_migration_quote_available_count=2, post_migration_quote_deferred_count=0),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert gate["pool_liquidity_available"] is False
    assert gate["quote_depth_status"] == "QUOTE_DEPTH_NOT_READY"
    assert gate["can_run_60m_thesis_scan"] is False
    assert "pool_liquidity_not_available" in gate["blocking_reasons"]


def test_t007aq_gate_allows_only_pre_migration_60m_when_quote_depth_missing_and_scope_excludes_exits() -> None:
    gate = evaluate_t007_thesis_ready_gate(_t007aq_live_feature_payload(), thesis_scope="h001_pre_migration")

    assert gate["quote_depth_required_for_scope"] is False
    assert gate["can_test_pre_migration_only_thesis"] is True
    assert gate["can_test_post_migration_exit_thesis"] is False
    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["allowed_scan_scope"] == "pre_migration_only_60m"


def test_t007aq_gate_blocks_2h_plus_until_full_quote_depth_passes() -> None:
    blocked = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(post_migration_quote_available_count=2, post_migration_quote_deferred_count=0),
        thesis_scope="full_post_migration_exit_depth",
    )
    ready = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(
            post_migration_quote_available_count=2,
            post_migration_quote_deferred_count=0,
            pool_liquidity_quote_present_count=2,
            pool_liquidity_usd_present_count=2,
            post_migration_decision_time_safe_executable_count=2,
            executable_quote_observations_written=2,
            price_impact_available_count=2,
            executable_quote_decision_time_safe_count=2,
            fee_model_confirmed_count=2,
            fee_model_status="confirmed",
            fee_proof_label="POST_PATCH_EVENT_FEE_PROOF_PASSED",
            event_endpoint_pass_count=2,
            event_endpoint_fail_count=0,
            decision_label="T007BA_60M_PARTIAL_DEPTH_VALIDATION_PASSED",
            source_duration_quality_status="complete",
            archive_status="complete",
            run_finalized=True,
            queue_drops=0,
            capacity_rejected=0,
            http_429=0,
            rpc_failures=0,
            decision_time_safety_violations=0,
            valuation_ladder_events=0,
            mayhem_files_modified=False,
            trading_paper_wallet_signing_execution_untouched=True,
        ),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert blocked["can_run_2h_plus_scan"] is False
    assert blocked["allowed_scan_scope"] == "10m_feature_proof_only"
    assert ready["quote_depth_status"] == "QUOTE_DEPTH_READY"
    assert ready["can_run_60m_thesis_scan"] is True
    assert ready["can_run_2h_plus_scan"] is True
    assert ready["can_run_one_2h_thesis_collection"] is True
    assert ready["can_run_4h_plus"] is False
    assert ready["allowed_scan_scope"] == "one_controlled_2h_thesis_collection"


def test_t007aq_quote_depth_diagnosis_files_are_created(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007aa_forward_thesis_dataset_report import write_quote_depth_diagnosis

    campaign = tmp_path / "campaign"
    output = tmp_path / "quote_depth"
    campaign.mkdir()
    (campaign / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-t007aq",
                "post_migration_pool_state_partial_count": 1,
                "post_migration_pool_state_error_count": 1,
                "pool_liquidity_quote_present_count": 0,
                "pool_liquidity_usd_present_count": 0,
                "post_migration_quote_deferred_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (campaign / "global_migration_events.jsonl").write_text(json.dumps({"mint": "mint-a", "quote_asset": "SOL"}) + "\n", encoding="utf-8")
    (campaign / "post_migration_observations.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"mint": "mint-a", "pool_or_pair_address": "pool-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 0, "pool_state_status": "partial", "pool_account_owner": PUMPSWAP_PROGRAM_ID_FOR_AUDIT, "pool_account_size": 245, "pool_discriminator": PUMPSWAP_MARKET_DISCRIMINATOR_BYTES.hex(), "pool_state_error_reason": "reserve_token_accounts_not_decoded_yet", "executable_quote_status": "deferred"}),
                json.dumps({"mint": "mint-a", "pool_or_pair_address": "pool-a", "quote_asset": "SOL", "horizon_seconds_after_migration": 5, "pool_state_status": "error", "pool_account_owner": PUMPSWAP_PROGRAM_ID_FOR_AUDIT, "pool_account_size": 301, "pool_discriminator": PUMPSWAP_MARKET_DISCRIMINATOR_BYTES.hex(), "pool_state_error_reason": "pumpswap_market_decode_failed", "executable_quote_status": "deferred"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    diagnosis = write_quote_depth_diagnosis(campaign, output)

    assert (output / "quote_depth_diagnosis.json").exists()
    assert (output / "quote_depth_diagnosis.md").exists()
    assert diagnosis["quote_depth_status"] == "QUOTE_DEPTH_NOT_READY"
    assert diagnosis["pool_state_partial_count"] == 1
    assert diagnosis["pool_state_error_count"] == 1
    assert diagnosis["liquidity_fields_not_populated_reason"] == "pool_reserve_decode_not_confirmed_or_executable_quote_not_available"
    assert diagnosis["executable_quotes_deferred_reason"] == "read_only_executable_quote_source_not_configured"


def _pumpswap_fixture_account_data_with_token_accounts(base_mint: str, quote_mint: str, base_token_account: str, quote_token_account: str) -> bytes:
    data = bytearray(_pumpswap_fixture_account_data(base_mint, quote_mint))
    data[139:171] = _base58_decode_string(base_token_account)
    data[171:203] = _base58_decode_string(quote_token_account)
    return bytes(data)


def test_t007ar_pumpswap_pool_state_probe_fetches_sol_quote_reserves_and_liquidity(monkeypatch) -> None:
    import base64
    import research.mtp_research.validation.forward_efficient_mover_observer as observer
    from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import PumpSwapPoolStateRpcProbe

    pool = "7bVhc426RvNkXsHumQzVyjHZ3fATtkfFiikbxjzpczKM"
    base_token_account = USDC_MINT
    quote_token_account = SOL_MINT
    account_data = _pumpswap_fixture_account_data_with_token_accounts(USDC_MINT, SOL_MINT, base_token_account, quote_token_account)
    calls = []

    def fake_post_json_rpc(_url, payload, _timeout):
        calls.append(payload["method"])
        if payload["method"] == "getAccountInfo":
            return {"result": {"context": {"slot": 123}, "value": {"owner": PUMPSWAP_PROGRAM_ID_FOR_AUDIT, "data": [base64.b64encode(account_data).decode("ascii"), "base64"]}}}
        if payload["method"] == "getTokenAccountBalance":
            account = payload["params"][0]
            if account == base_token_account:
                return {"result": {"context": {"slot": 124}, "value": {"amount": "1000000000", "decimals": 6, "uiAmount": 1000.0}}}
            if account == quote_token_account:
                return {"result": {"context": {"slot": 124}, "value": {"amount": "2000000000", "decimals": 9, "uiAmount": 2.0}}}
        raise AssertionError(payload)

    monkeypatch.setattr(observer, "_post_json_rpc", fake_post_json_rpc)

    row = PumpSwapPoolStateRpcProbe(rpc_url="http://unit.test").fetch_pool_state(pool)

    assert calls == ["getAccountInfo", "getTokenAccountBalance", "getTokenAccountBalance"]
    assert row["pool_state_status"] == "available"
    assert row["depth_status"] == "available"
    assert row["base_reserve_raw"] == 1_000_000_000
    assert row["quote_reserve_raw"] == 2_000_000_000
    assert row["base_reserve_scaled"] == 1000.0
    assert row["quote_reserve_scaled"] == 2.0
    assert row["pool_liquidity_quote"] == 2.0
    assert row["pool_base_token_account"] == base_token_account
    assert row["pool_quote_token_account"] == quote_token_account
    assert row["pool_decode_confidence"] == "token_account_reserves"


def test_t007ar_post_migration_observation_records_quote_to_usd_rate_for_sol_and_usdc(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    sol = recorder.record_post_migration_observation(
        {
            "mint": "mint-rate-sol",
            "pool_or_pair_address": "pool-rate-sol",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 2.0,
        }
    )
    usdc = recorder.record_post_migration_observation(
        {
            "mint": "mint-rate-usdc",
            "pool_or_pair_address": "pool-rate-usdc",
            "quote_asset": "USDC",
            "quote_mint": USDC_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 200.0,
        }
    )
    unknown = recorder.record_post_migration_observation(
        {
            "mint": "mint-rate-unknown",
            "pool_or_pair_address": "pool-rate-unknown",
            "quote_asset": "UNKNOWN",
            "quote_mint": "unknown-mint",
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_liquidity_quote": 200.0,
        }
    )

    assert sol["quote_to_usd_rate"] == 135.0
    assert sol["pool_liquidity_usd"] == 270.0
    assert usdc["quote_to_usd_rate"] == 1.0
    assert usdc["pool_liquidity_usd"] == 200.0
    assert unknown["quote_to_usd_rate"] is None
    assert unknown["pool_liquidity_usd"] is None


def test_t007as_direct_pool_math_writes_partial_exit_quotes_and_price_impact(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-quote-sol",
            "base_mint": "mint-quote-sol",
            "pool_or_pair_address": "pool-quote-sol",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "available",
            "depth_status": "available",
            "base_reserve_raw": 100_000_000,
            "quote_reserve_raw": 10_000_000_000,
            "base_reserve_scaled": 100.0,
            "quote_reserve_scaled": 10.0,
            "pool_liquidity_quote": 10.0,
        }
    )
    quotes = [quote for quote in _jsonl(tmp_path / "executable_quote_observations.jsonl") if quote.get("mint") == "mint-quote-sol"]
    impacts = [quote["price_impact_pct"] for quote in quotes]

    assert row["executable_quote_status"] == "partial"
    assert row["quote_source"] == "direct_pool_math"
    assert row["executable_quote_clip_count"] == 4
    assert row["min_price_impact_pct"] == min(impacts)
    assert row["max_price_impact_pct"] == max(impacts)
    assert len(quotes) == 4
    assert {quote["quote_status"] for quote in quotes} == {"partial"}
    assert {quote["quote_direction"] for quote in quotes} == {"exit_token_to_quote"}
    assert {quote["quote_source"] for quote in quotes} == {"direct_pool_math"}
    assert {quote["fee_model_status"] for quote in quotes} == {"unknown"}
    assert {quote["quote_confidence"] for quote in quotes} == {"low"}
    assert all(quote["decision_time_safe"] is True for quote in quotes)
    assert all(quote["valuation_ladder_used"] is False for quote in quotes)
    assert quotes[0]["quote_clip_notional_quote"] == 0.05
    assert quotes[0]["input_token_amount_estimated"] == pytest.approx(0.5)
    assert quotes[0]["expected_output_quote"] == pytest.approx(0.0497512437810945)
    assert quotes[0]["expected_output_quote_usd"] == pytest.approx(6.716417910447757)
    assert quotes[0]["pool_mid_price_quote_per_token"] == pytest.approx(0.1)
    assert quotes[0]["effective_exit_price_quote_per_token"] == pytest.approx(0.099502487562189)
    assert impacts == sorted(impacts)
    assert impacts[-1] > impacts[0]


def test_t007as_usdc_quote_uses_one_to_one_usd_and_unknown_quote_omits_usd(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    recorder.record_post_migration_observation(
        {
            "mint": "mint-quote-usdc",
            "pool_or_pair_address": "pool-quote-usdc",
            "quote_asset": "USDC",
            "quote_mint": USDC_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "available",
            "depth_status": "available",
            "base_reserve_scaled": 100.0,
            "quote_reserve_scaled": 1000.0,
            "pool_liquidity_quote": 1000.0,
        }
    )
    recorder.record_post_migration_observation(
        {
            "mint": "mint-quote-unknown",
            "pool_or_pair_address": "pool-quote-unknown",
            "quote_asset": "UNKNOWN",
            "quote_mint": "unknown-mint",
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "available",
            "depth_status": "available",
            "base_reserve_scaled": 100.0,
            "quote_reserve_scaled": 1000.0,
            "pool_liquidity_quote": 1000.0,
        }
    )
    quotes = _jsonl(tmp_path / "executable_quote_observations.jsonl")
    usdc_quote = next(quote for quote in quotes if quote.get("mint") == "mint-quote-usdc")
    unknown_quotes = [quote for quote in quotes if quote.get("mint") == "mint-quote-unknown"]

    assert usdc_quote["expected_output_quote_usd"] == usdc_quote["expected_output_quote"]
    assert unknown_quotes == []


def test_t007as_missing_reserves_mark_executable_quote_not_available(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100))

    row = recorder.record_post_migration_observation(
        {
            "mint": "mint-missing-reserves",
            "pool_or_pair_address": "pool-missing-reserves",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "available",
            "depth_status": "available",
        }
    )
    quotes = [quote for quote in _jsonl(tmp_path / "executable_quote_observations.jsonl") if quote.get("mint") == "mint-missing-reserves"]

    assert row["executable_quote_status"] == "not_available"
    assert row["quote_source"] == "direct_pool_math"
    assert row["error_reason"] == "missing_pool_reserves_for_direct_quote"
    assert quotes == []


def test_t007as_summary_counts_executable_quote_clips_and_fee_model_unknown(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))

    recorder.record_post_migration_observation(
        {
            "mint": "mint-summary-quotes",
            "pool_or_pair_address": "pool-summary-quotes",
            "quote_asset": "SOL",
            "quote_mint": SOL_MINT,
            "migration_received_at": 1000.0,
            "horizon_seconds_after_migration": 0,
            "observation_received_at": 1000.0,
            "pool_state_status": "available",
            "depth_status": "available",
            "base_reserve_scaled": 100.0,
            "quote_reserve_scaled": 10.0,
            "pool_liquidity_quote": 10.0,
        }
    )
    summary = recorder.build_summary()

    assert summary["executable_quote_observations_written"] == 4
    assert summary["executable_quote_partial_count"] == 4
    assert summary["executable_quote_available_count"] == 0
    assert summary["executable_quote_by_source"] == {"direct_pool_math": 4}
    assert summary["executable_quote_by_quote_asset"] == {"SOL": 4}
    assert summary["executable_quote_by_direction"] == {"exit_token_to_quote": 4}
    assert summary["executable_quote_clip_count"] == 4
    assert summary["price_impact_available_count"] == 4
    assert summary["fee_model_unknown_count"] == 4
    assert summary["valuation_ladder_events_written"] == 0
    assert summary["mayhem_code_modified"] is False


def test_t007as_gate_allows_only_partial_post_migration_depth_when_fee_model_unknown() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(
            post_migration_quote_available_count=0,
            post_migration_quote_deferred_count=0,
            executable_quote_observations_written=8,
            executable_quote_partial_count=8,
            price_impact_available_count=8,
            executable_quote_decision_time_safe_count=8,
            fee_model_unknown_count=8,
            pool_liquidity_quote_present_count=2,
            pool_liquidity_usd_present_count=2,
        ),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert gate["pool_liquidity_available"] is True
    assert gate["executable_quote_available"] is True
    assert gate["price_impact_available"] is True
    assert gate["quote_depth_status"] == "QUOTE_DEPTH_PARTIAL_FEE_UNKNOWN"
    assert gate["can_test_post_migration_exit_thesis"] is False
    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["allowed_scan_scope"] == "post_migration_depth_partial_60m"


def test_t007as_report_writes_executable_quote_outcomes(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007aa_forward_thesis_dataset_report import run_report

    campaign = tmp_path / "campaign"
    output = tmp_path / "report"
    campaign.mkdir()
    (campaign / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-t007as",
                "valuation_ladder_emission_policy": "market_cap_confirmed_only",
                "valuation_ladder_events_written": 0,
                "executable_quote_observations_written": 1,
                "executable_quote_partial_count": 1,
                "executable_quote_by_source": {"direct_pool_math": 1},
                "executable_quote_by_quote_asset": {"SOL": 1},
                "price_impact_available_count": 1,
                "fee_model_unknown_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (campaign / "campaign_manifest.json").write_text(json.dumps({"campaign_id": "campaign-t007as"}), encoding="utf-8")
    (campaign / "executable_quote_observations.jsonl").write_text(
        json.dumps({"mint": "mint-report-quote", "quote_status": "partial", "quote_source": "direct_pool_math", "quote_asset": "SOL", "price_impact_pct": 1.0, "fee_model_status": "unknown"}) + "\n",
        encoding="utf-8",
    )

    run_report([campaign], output)
    analysis = json.loads((output / "analysis_result.json").read_text(encoding="utf-8"))

    assert (output / "executable_quote_outcomes.csv").exists()
    assert analysis["campaigns"][0]["executable_quote_coverage"]["observations_written"] == 1
    assert analysis["campaigns"][0]["executable_quote_coverage"]["status_counts"] == {"partial": 1}


def test_t007at_quote_math_cannot_be_confirmed_without_source_and_replay_proof() -> None:
    from research.mtp_research.validation.t007at_fee_formula_confirmation import classify_quote_math_evidence

    status = classify_quote_math_evidence(
        {
            "formula_source_confirmed": True,
            "fee_model_complete": False,
            "replay_validation_passed": False,
        }
    )

    assert status["fee_model_status"] == "unknown"
    assert status["quote_confidence"] == "low"
    assert status["confirmed"] is False


def test_t007at_confirmed_fee_model_requires_source_fee_and_replay() -> None:
    from research.mtp_research.validation.t007at_fee_formula_confirmation import classify_quote_math_evidence

    status = classify_quote_math_evidence(
        {
            "formula_source_confirmed": True,
            "fee_model_complete": True,
            "replay_validation_passed": True,
            "lp_fee_bps": 30,
            "protocol_fee_bps": 5,
            "creator_fee_bps": 0,
            "rounding_confirmed": True,
        }
    )

    assert status["fee_model_status"] == "confirmed"
    assert status["quote_confidence"] == "high"
    assert status["confirmed"] is True


def test_t007at_assumed_formula_sets_medium_confidence() -> None:
    from research.mtp_research.validation.t007at_fee_formula_confirmation import classify_quote_math_evidence

    status = classify_quote_math_evidence(
        {
            "formula_source_confirmed": True,
            "fee_model_complete": False,
            "replay_validation_passed": True,
            "rounding_confirmed": False,
            "allow_assumed": True,
        }
    )

    assert status["fee_model_status"] == "assumed"
    assert status["quote_confidence"] == "medium"
    assert status["confirmed"] is False


def test_t007at_replay_validation_relative_error() -> None:
    from research.mtp_research.validation.t007at_fee_formula_confirmation import build_swap_replay_validation_row

    row = build_swap_replay_validation_row(
        {
            "signature": "sig-replay",
            "pool": "pool-replay",
            "mint": "mint-replay",
            "quote_asset": "SOL",
            "direction": "exit_token_to_quote",
            "input_amount_observed": 1.0,
            "output_amount_observed": 0.99,
            "reserve_base_before": 100.0,
            "reserve_quote_before": 100.0,
        },
        fee_bps_candidate=0.0,
    )

    assert row["predicted_output_no_fee"] == pytest.approx(0.9900990099009874)
    assert row["absolute_error"] == pytest.approx(0.000099009900987386)
    assert row["relative_error_pct"] == pytest.approx(0.01000100009973596)
    assert row["validation_status"] == "pass"


def test_t007at_gate_full_thesis_requires_confirmed_fee_model() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(
            post_migration_quote_available_count=0,
            post_migration_quote_deferred_count=0,
            executable_quote_observations_written=8,
            executable_quote_partial_count=8,
            price_impact_available_count=8,
            executable_quote_decision_time_safe_count=8,
            fee_model_unknown_count=8,
            pool_liquidity_quote_present_count=2,
            pool_liquidity_usd_present_count=2,
        ),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert gate["quote_depth_status"] == "QUOTE_DEPTH_PARTIAL_FEE_UNKNOWN"
    assert gate["can_test_post_migration_exit_thesis"] is False
    assert gate["allowed_scan_scope"] == "post_migration_depth_partial_60m"
    assert gate["can_run_2h_plus_scan"] is False


def test_t007at_gate_full_thesis_passes_only_with_confirmed_fee_model() -> None:
    gate = evaluate_t007_thesis_ready_gate(
        _t007aq_live_feature_payload(
            post_migration_quote_available_count=0,
            post_migration_quote_deferred_count=0,
            executable_quote_observations_written=8,
            executable_quote_available_count=8,
            price_impact_available_count=8,
            executable_quote_decision_time_safe_count=8,
            fee_model_confirmed_count=8,
            fee_model_unknown_count=0,
            pool_liquidity_quote_present_count=2,
            pool_liquidity_usd_present_count=2,
            valid_60m_thesis_collection_passed=False,
        ),
        thesis_scope="full_post_migration_exit_depth",
    )

    assert gate["quote_depth_status"] == "QUOTE_DEPTH_READY"
    assert gate["can_test_post_migration_exit_thesis"] is True
    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["allowed_scan_scope"] == "full_thesis_60m"


def test_t007at_report_writer_creates_required_no_scan_outputs(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007at_fee_formula_confirmation import write_t007at_fee_formula_confirmation_report

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    (archive / "collector_summary.json").write_text(json.dumps({"run_id": "run-t007at"}), encoding="utf-8")
    (archive / "trade_flow_events.jsonl").write_text(
        json.dumps({"signature": "sig-a", "mint": "mint-a", "side": "sell", "quote_asset": "SOL", "quote_amount": 1.0, "token_amount": 100.0}) + "\n",
        encoding="utf-8",
    )
    (archive / "post_migration_observations.jsonl").write_text(
        json.dumps({"mint": "mint-a", "pool_or_pair_address": "pool-a", "pool_base_reserve": 1000.0, "pool_quote_reserve": 10.0}) + "\n",
        encoding="utf-8",
    )

    result = write_t007at_fee_formula_confirmation_report(Path.cwd(), [archive], output)

    required = {
        "summary.md",
        "quote_math_status.json",
        "repo_source_inventory.md",
        "swap_replay_candidates.csv",
        "swap_replay_validation.csv",
        "fee_model_comparison.csv",
        "readiness_gate_after_t007at.json",
    }
    assert required <= {path.name for path in output.iterdir()}
    assert result["fee_model_status"] in {"unknown", "assumed", "confirmed"}
    assert result["live_scan_ran"] is False


def test_t007au_reconstruction_requires_before_and_after_reserves():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        build_replay_row,
    )

    candidate = {
        "signature": "sig-a",
        "pool": "pool-a",
        "mint": "mint-a",
        "input_amount": "10",
        "output_amount": "9",
        "direction": "base_to_quote",
        "slot": "123",
    }
    row, failure = build_replay_row(
        candidate,
        {
            "pool": "pool-a",
            "reserve_base_before": "100",
            "reserve_quote_before": "200",
            "reserve_base_after": "110",
        },
    )

    assert row is None
    assert failure is not None
    assert failure["failure_reason"] == "missing_after_quote_reserve"


def test_t007au_wrong_pool_rows_are_rejected():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        build_replay_row,
    )

    row, failure = build_replay_row(
        {"signature": "sig-a", "pool": "pool-a", "mint": "mint-a"},
        {
            "pool": "pool-b",
            "reserve_base_before": "100",
            "reserve_quote_before": "200",
            "reserve_base_after": "110",
            "reserve_quote_after": "190",
            "input_amount": "10",
            "output_amount": "9",
            "direction": "base_to_quote",
            "slot": "123",
        },
    )

    assert row is None
    assert failure is not None
    assert failure["failure_reason"] == "wrong_pool"


def test_t007au_missing_before_reserve_is_rejected():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        build_replay_row,
    )

    row, failure = build_replay_row(
        {"signature": "sig-a", "pool": "pool-a", "mint": "mint-a"},
        {
            "pool": "pool-a",
            "reserve_quote_before": "200",
            "reserve_base_after": "110",
            "reserve_quote_after": "190",
            "input_amount": "10",
            "output_amount": "9",
            "direction": "base_to_quote",
            "slot": "123",
        },
    )

    assert row is None
    assert failure is not None
    assert failure["failure_reason"] == "missing_before_base_reserve"


def test_t007au_read_only_rpc_mode_requires_explicit_flag():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        validate_rpc_reconstruction_options,
    )

    assert validate_rpc_reconstruction_options(enable_rpc=False, max_signatures=0)["enabled"] is False

    import pytest

    with pytest.raises(ValueError, match="explicit"):
        validate_rpc_reconstruction_options(enable_rpc=False, max_signatures=1)
    with pytest.raises(ValueError, match="max_signatures"):
        validate_rpc_reconstruction_options(enable_rpc=True, max_signatures=0)
    with pytest.raises(ValueError, match="cap"):
        validate_rpc_reconstruction_options(enable_rpc=True, max_signatures=101)


def test_t007au_guardrails_disable_wallet_trading_and_signing_paths():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        GUARDRAILS,
    )

    assert GUARDRAILS["read_only"] is True
    assert GUARDRAILS["wallet_paths_allowed"] is False
    assert GUARDRAILS["private_key_paths_allowed"] is False
    assert GUARDRAILS["trading_paths_allowed"] is False
    assert GUARDRAILS["signing_paths_allowed"] is False


def test_t007au_valuation_ladder_remains_suppressed():
    from research.mtp_research.validation.t007au_offline_swap_replay_reconstruction import (
        build_readiness_gate_after_t007au,
    )

    gate = build_readiness_gate_after_t007au(
        reconstructed_replay_rows=10,
        fee_model_status="high",
        quote_confidence="high",
    )

    assert gate["valuation_ladder_suppressed"] is True
    assert gate["full_post_migration_exit_thesis_allowed"] is True


def _t007av_pubkey(seed: int) -> str:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        base58_encode_bytes,
    )

    return base58_encode_bytes(bytes([seed]) * 32)


def _t007av_pack_pubkey(value: str) -> bytes:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        base58_decode_string,
    )

    return base58_decode_string(value)


def _t007av_buy_event_payload() -> tuple[str, dict]:
    import base64
    import struct
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        BUY_EVENT_DISCRIMINATOR_BYTES,
    )

    pool = _t007av_pubkey(1)
    user = _t007av_pubkey(2)
    user_base = _t007av_pubkey(3)
    user_quote = _t007av_pubkey(4)
    fee_recipient = _t007av_pubkey(5)
    fee_recipient_token = _t007av_pubkey(6)
    coin_creator = _t007av_pubkey(7)
    ix_name = b"buy"
    parts = [
        BUY_EVENT_DISCRIMINATOR_BYTES,
        struct.pack(
            "<q13Q",
            1_781_460_000,
            1_000,
            2_200,
            5_000,
            7_000,
            1_000_000,
            2_000_000,
            2_100,
            25,
            5,
            20,
            4,
            2_105,
            2_109,
        ),
        _t007av_pack_pubkey(pool),
        _t007av_pack_pubkey(user),
        _t007av_pack_pubkey(user_base),
        _t007av_pack_pubkey(user_quote),
        _t007av_pack_pubkey(fee_recipient),
        _t007av_pack_pubkey(fee_recipient_token),
        _t007av_pack_pubkey(coin_creator),
        struct.pack("<2Q", 5, 1),
        struct.pack("<?", True),
        struct.pack("<3QqQ", 0, 0, 0, 0, 900),
        struct.pack("<I", len(ix_name)),
        ix_name,
        struct.pack("<4Q", 0, 0, 0, 0),
    ]
    payload = b"".join(parts)
    return "Program data: " + base64.b64encode(payload).decode("ascii"), {"pool": pool, "user": user}


def _t007av_sell_event_payload() -> tuple[str, dict]:
    import base64
    import struct
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        SELL_EVENT_DISCRIMINATOR_BYTES,
    )

    pool = _t007av_pubkey(11)
    user = _t007av_pubkey(12)
    user_base = _t007av_pubkey(13)
    user_quote = _t007av_pubkey(14)
    fee_recipient = _t007av_pubkey(15)
    fee_recipient_token = _t007av_pubkey(16)
    coin_creator = _t007av_pubkey(17)
    parts = [
        SELL_EVENT_DISCRIMINATOR_BYTES,
        struct.pack(
            "<q13Q",
            1_781_460_001,
            1_000,
            1_800,
            4_000,
            8_000,
            1_001_000,
            1_998_000,
            1_900,
            25,
            5,
            20,
            4,
            1_905,
            1_891,
        ),
        _t007av_pack_pubkey(pool),
        _t007av_pack_pubkey(user),
        _t007av_pack_pubkey(user_base),
        _t007av_pack_pubkey(user_quote),
        _t007av_pack_pubkey(fee_recipient),
        _t007av_pack_pubkey(fee_recipient_token),
        _t007av_pack_pubkey(coin_creator),
        struct.pack("<7Q", 5, 1, 0, 0, 0, 0, 0),
    ]
    return "Program data: " + base64.b64encode(b"".join(parts)).decode("ascii"), {"pool": pool, "user": user}


def test_t007av_decodes_pumpswap_buy_event_fee_and_reserve_fields():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        decode_pumpswap_swap_events_from_logs,
    )

    log, expected = _t007av_buy_event_payload()
    rows = decode_pumpswap_swap_events_from_logs([log])

    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "buy"
    assert row["pool"] == expected["pool"]
    assert row["user"] == expected["user"]
    assert row["base_amount"] == 1_000
    assert row["quote_amount"] == 2_100
    assert row["user_quote_amount"] == 2_109
    assert row["lp_fee_basis_points"] == 25
    assert row["protocol_fee_basis_points"] == 20
    assert row["pool_base_token_reserves"] == 1_000_000
    assert row["pool_quote_token_reserves"] == 2_000_000
    assert row["event_decode_status"] == "decoded"
    assert row["decision_time_safe"] is True
    assert row["valuation_ladder_used"] is False


def test_t007av_decodes_pumpswap_sell_event_fee_and_reserve_fields():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        decode_pumpswap_swap_events_from_logs,
    )

    log, expected = _t007av_sell_event_payload()
    rows = decode_pumpswap_swap_events_from_logs([log])

    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "sell"
    assert row["pool"] == expected["pool"]
    assert row["user"] == expected["user"]
    assert row["base_amount"] == 1_000
    assert row["quote_amount"] == 1_900
    assert row["user_quote_amount"] == 1_891
    assert row["lp_fee"] == 5
    assert row["protocol_fee"] == 4
    assert row["event_decode_confidence"] == "idl_event_discriminator"


def test_t007av_buy_and_sell_instruction_discriminators_are_recognized():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        classify_pumpswap_instruction_discriminator,
        BUY_INSTRUCTION_DISCRIMINATOR_BYTES,
        SELL_INSTRUCTION_DISCRIMINATOR_BYTES,
    )

    assert classify_pumpswap_instruction_discriminator(BUY_INSTRUCTION_DISCRIMINATOR_BYTES + b"x") == "buy"
    assert classify_pumpswap_instruction_discriminator(SELL_INSTRUCTION_DISCRIMINATOR_BYTES + b"x") == "sell"
    assert classify_pumpswap_instruction_discriminator(b"not-real") is None


def test_t007av_pool_base_quote_token_account_mapping_is_preserved():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        enrich_swap_event_with_pool_metadata,
    )

    row = {"pool": "pool-a", "event_type": "sell"}
    enriched = enrich_swap_event_with_pool_metadata(
        row,
        {
            "pool_or_pair_address": "pool-a",
            "base_mint": "mint-a",
            "quote_mint": SOL_MINT,
            "pool_base_token_account": "base-vault",
            "pool_quote_token_account": "quote-vault",
        },
    )

    assert enriched["base_mint"] == "mint-a"
    assert enriched["quote_mint"] == SOL_MINT
    assert enriched["quote_asset"] == "SOL"
    assert enriched["pool_base_token_account"] == "base-vault"
    assert enriched["pool_quote_token_account"] == "quote-vault"


def test_t007av_candidate_inventory_excludes_pumpfun_only_trades():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        build_pumpswap_swap_candidate_inventory,
    )

    events = [{"signature": "sig-swap", "pool": "pool-a", "event_type": "buy", "mint": "mint-a"}]
    pools = [{"pool_or_pair_address": "pool-a", "pool_base_token_account": "base", "pool_quote_token_account": "quote"}]
    pumpfun_trades = [{"signature": "sig-pumpfun", "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}]

    rows = build_pumpswap_swap_candidate_inventory(events, pools, pumpfun_trades)

    assert [row["signature"] for row in rows] == ["sig-swap"]
    assert rows[0]["candidate_source"] == "decoded_pumpswap_swap_event"


def test_t007av_replay_validation_compares_predicted_vs_observed_output():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
        build_fee_formula_replay_validation_row,
    )

    row = build_fee_formula_replay_validation_row(
        {
            "signature": "sig-sell",
            "event_type": "sell",
            "pool": "pool-a",
            "mint": "mint-a",
            "quote_asset": "SOL",
            "base_amount": 1_000,
            "quote_amount": 1_900,
            "user_quote_amount": 1_891,
            "lp_fee_basis_points": 25,
            "protocol_fee_basis_points": 20,
            "lp_fee": 5,
            "protocol_fee": 4,
        }
    )

    assert row["predicted_quote_no_fee"] == 1_900
    assert row["predicted_quote_with_event_fees"] == 1_891
    assert row["absolute_error"] == 0
    assert row["validation_status"] == "pass"


def test_t007av_fee_model_cannot_be_confirmed_without_event_replay_rows():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import classify_fee_model_status

    status = classify_fee_model_status([])

    assert status["fee_model_status"] == "unknown"
    assert status["quote_confidence"] == "low"


def test_t007av_fee_model_confirmed_only_under_tolerance():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import classify_fee_model_status

    status = classify_fee_model_status([
        {"validation_status": "pass", "relative_error_pct": 0.0},
        {"validation_status": "pass", "relative_error_pct": 0.01},
    ])
    failed = classify_fee_model_status([
        {"validation_status": "fail", "relative_error_pct": 5.0},
    ])

    assert status["fee_model_status"] == "confirmed"
    assert status["quote_confidence"] == "high"
    assert failed["fee_model_status"] == "unknown"


def test_t007av_guardrails_keep_valuation_ladder_suppressed_and_no_mayhem_or_trading_paths():
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import T007AV_GUARDRAILS

    assert T007AV_GUARDRAILS["valuation_ladder_suppressed"] is True
    assert T007AV_GUARDRAILS["mayhem_files_modified"] is False
    assert T007AV_GUARDRAILS["wallet_private_key_trading_signing_execution_untouched"] is True


def test_t007av_global_pumpswap_lane_writes_decoded_swap_events(tmp_path: Path) -> None:
    class FakePumpSwapSwapRoute:
        source_name = "fake_pumpswap_swap_route"

        def availability(self):
            return {"source": self.source_name, "available": True, "programSubscribe": False}

        def iter_notifications(self, _duration):
            log, expected = _t007av_buy_event_payload()
            yield {
                "signature": "sig-pumpswap-buy",
                "slot": 123,
                "received_at": 1000.0,
                "logs": [log],
                "decoded_rows": [
                    {
                        "signature": "sig-pumpswap-buy",
                        "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                        "instruction_type": "buy",
                        "mint": "mint-pump",
                        "base_mint": "mint-pump",
                        "quote_mint": SOL_MINT,
                        "pool_or_pair_address": expected["pool"],
                        "pool_base_token_account": "base-vault",
                        "pool_quote_token_account": "quote-vault",
                    }
                ],
            }

    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))
    summary = run_global_pumpswap_migration_lane(
        recorder.config,
        recorder,
        source=FakePumpSwapSwapRoute(),
        duration_seconds=0,
    )
    rows = _jsonl(tmp_path / "pumpswap_swap_events.jsonl")

    assert summary["pumpswap_swap_events_decoded"] == 1
    assert summary["pumpswap_swap_buy_events"] == 1
    assert summary["pumpswap_swap_sell_events"] == 0
    assert recorder.build_summary()["pumpswap_swap_events_decoded"] == 1
    assert rows[0]["signature"] == "sig-pumpswap-buy"
    assert rows[0]["event_type"] == "buy"
    assert rows[0]["mint"] == "mint-pump"
    assert rows[0]["quote_asset"] == "SOL"
    assert rows[0]["pool_base_token_account"] == "base-vault"
    assert rows[0]["pool_quote_token_account"] == "quote-vault"
    assert rows[0]["valuation_ladder_used"] is False


def test_t007_launchd_runner_writes_auditable_one_shot_plist(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007_launchd_runner import create_launchd_job_bundle

    bundle = create_launchd_job_bundle(
        label="com.mtp.t007av.test",
        output_dir=tmp_path,
        program_arguments=["/bin/zsh", "-lc", "date > started.txt"],
        working_directory="/Users/dianeposs/Projects/meme-trader-pro",
        environment={"PYTHONPATH": "/Users/dianeposs/Projects/meme-trader-pro"},
    )

    plist_text = bundle.plist_path.read_text(encoding="utf-8")
    manifest = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

    assert bundle.plist_path.name == "com.mtp.t007av.test.plist"
    assert "<key>RunAtLoad</key>" in plist_text
    assert "<true/>" in plist_text
    assert "<key>KeepAlive</key>" in plist_text
    assert "<false/>" in plist_text
    assert "<key>WorkingDirectory</key>" in plist_text
    assert "/Users/dianeposs/Projects/meme-trader-pro" in plist_text
    assert "PYTHONPATH" in plist_text
    assert "nohup" not in plist_text
    assert manifest["uses_shell_backgrounding"] is False
    assert " &" not in " ".join(manifest["program_arguments"])
    assert manifest["label"] == "com.mtp.t007av.test"
    assert manifest["plist_path"] == str(bundle.plist_path)
    assert manifest["stdout_path"].endswith("stdout.log")
    assert manifest["stderr_path"].endswith("stderr.log")


def test_t007_launchd_status_command_preserves_runtime_exit_codes(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007_launchd_runner import build_status_recording_zsh_command

    command = build_status_recording_zsh_command(
        repo_root="/Users/dianeposs/Projects/meme-trader-pro",
        job_output_dir=tmp_path / "job",
        staging_root=tmp_path / "staging",
        archive_root=tmp_path / "archive",
        postprocess_output_dir=tmp_path / "post",
        collector_command=["python3", "-m", "collector"],
        postprocess_command=["python3", "-m", "postprocess"],
    )

    assert "COLLECTOR_EXIT=$?" in command
    assert "POST_EXIT=$?" in command
    assert 'int("")' not in command
    assert "os.environ.get(\"COLLECTOR_EXIT\"" in command
    assert "os.environ.get(\"POST_EXIT\"" in command
    assert 'exit "$FINAL_EXIT"' in command



def test_t007aw_route_audit_writes_pumpswap_transaction_candidates(tmp_path: Path) -> None:
    from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import (
        BondingCurveProgressRecorder,
        BondingCurveRecorderConfig,
        run_global_pumpswap_migration_lane,
    )

    class FakePumpSwapTransactionRoute:
        source_name = "fake_pumpswap_transaction_subscribe"

        def availability(self):
            return {"source": self.source_name, "available": True, "transactionSubscribe": True, "route_type": "transactionSubscribe_accountInclude"}

        def iter_notifications(self, _duration):
            return [
                {
                    "signature": "sig-route-audit",
                    "slot": 10,
                    "received_at": 100.0,
                    "route_name": "pumpswap_transaction_subscribe",
                    "filter_name": "accountInclude_pumpswap_program",
                    "includes_pumpswap_program": True,
                    "account_keys_count": 4,
                    "logs": ["Program log: Instruction: Buy"],
                    "instruction_program_ids": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
                    "decoded_candidate_instruction_names": ["buy"],
                    "contains_buy_discriminator": True,
                    "contains_sell_discriminator": False,
                    "contains_buy_event_log": False,
                    "contains_sell_event_log": False,
                    "contains_pool_account": True,
                    "contains_known_post_migration_pool": False,
                    "decoded_rows": [
                        {
                            "signature": "sig-route-audit",
                            "slot": 10,
                            "received_at": 100.0,
                            "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                            "instruction_type": "buy",
                            "pool_or_pair_address": "pool-a",
                            "mint": "mint-a",
                            "quote_mint": SOL_MINT,
                        }
                    ],
                }
            ]

    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))
    summary = run_global_pumpswap_migration_lane(recorder.config, recorder, source=FakePumpSwapTransactionRoute(), duration_seconds=0)
    rows = _jsonl(tmp_path / "pumpswap_transaction_route_audit.jsonl")

    assert summary["pumpswap_route_raw_notifications"] == 1
    assert summary["pumpswap_route_candidate_transactions"] == 1
    assert summary["pumpswap_route_with_logs"] == 1
    assert summary["pumpswap_route_buy_candidates"] == 1
    assert rows[0]["signature"] == "sig-route-audit"
    assert rows[0]["includes_pumpswap_program"] is True
    assert rows[0]["has_log_messages"] is True
    assert rows[0]["contains_buy_discriminator"] is True


def test_t007aw_balance_delta_fallback_writes_partial_swap_row_when_logs_missing(tmp_path: Path) -> None:
    from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import (
        BondingCurveProgressRecorder,
        BondingCurveRecorderConfig,
        run_global_pumpswap_migration_lane,
    )

    class FakePumpSwapBalanceDeltaRoute:
        source_name = "fake_pumpswap_transaction_subscribe"

        def availability(self):
            return {"source": self.source_name, "available": True, "transactionSubscribe": True, "route_type": "transactionSubscribe_accountInclude"}

        def iter_notifications(self, _duration):
            return [
                {
                    "signature": "sig-balance-delta",
                    "slot": 11,
                    "received_at": 101.0,
                    "route_name": "pumpswap_transaction_subscribe",
                    "filter_name": "accountInclude_pumpswap_program",
                    "includes_pumpswap_program": True,
                    "has_log_messages": False,
                    "logs": [],
                    "instruction_program_ids": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
                    "decoded_candidate_instruction_names": ["sell"],
                    "decoded_rows": [
                        {
                            "signature": "sig-balance-delta",
                            "slot": 11,
                            "received_at": 101.0,
                            "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                            "instruction_type": "sell",
                            "pool_or_pair_address": "pool-b",
                            "mint": "mint-b",
                            "base_mint": "mint-b",
                            "quote_mint": SOL_MINT,
                            "pool_base_token_account": "base-vault-b",
                            "pool_quote_token_account": "quote-vault-b",
                            "base_amount": 1000,
                            "quote_amount": 2,
                            "user": "user-b",
                            "swap_direction": "sell",
                        }
                    ],
                }
            ]

    recorder = BondingCurveProgressRecorder(BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135))
    summary = run_global_pumpswap_migration_lane(recorder.config, recorder, source=FakePumpSwapBalanceDeltaRoute(), duration_seconds=0)
    rows = _jsonl(tmp_path / "pumpswap_swap_events.jsonl")

    assert summary["pumpswap_route_with_logs"] == 0
    assert summary["pumpswap_swap_events_decoded"] == 1
    assert rows[0]["signature"] == "sig-balance-delta"
    assert rows[0]["event_type"] == "sell"
    assert rows[0]["decode_source"] == "balance_delta"
    assert rows[0]["event_decode_status"] == "partial"
    assert rows[0]["valuation_ladder_used"] is False



def test_t007aw_fee_candidate_inventory_includes_pumpswap_route_audit_and_excludes_non_pumpswap() -> None:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import build_pumpswap_swap_candidate_inventory

    rows = build_pumpswap_swap_candidate_inventory(
        [],
        [],
        [],
        route_audit_rows=[
            {"signature": "sig-pumpswap", "slot": 1, "includes_pumpswap_program": True, "contains_buy_discriminator": True},
            {"signature": "sig-not-pumpswap", "slot": 2, "includes_pumpswap_program": False, "contains_buy_discriminator": True},
        ],
    )

    assert [row["signature"] for row in rows] == ["sig-pumpswap"]
    assert rows[0]["candidate_source"] == "pumpswap_transaction_route_audit"
    assert rows[0]["include_for_replay"] is False
    assert rows[0]["exclusion_reason"] == "route_audit_only_missing_decoded_swap_amounts"



def test_t007aw_postprocessor_uses_existing_decoded_pumpswap_swap_events(tmp_path: Path) -> None:
    from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import write_t007av_report

    archive = tmp_path / "archive"
    output = tmp_path / "out"
    archive.mkdir()
    sell_event = {
        "signature": "sig-decoded-sell",
        "slot": 100,
        "event_type": "sell",
        "event_decode_status": "decoded",
        "pool": "pool-a",
        "mint": "mint-a",
        "quote_asset": "SOL",
        "base_amount": 1000,
        "quote_amount": 1900,
        "user_quote_amount": 1891,
        "lp_fee_basis_points": 25,
        "protocol_fee_basis_points": 20,
        "lp_fee": 5,
        "protocol_fee": 4,
        "valuation_ladder_used": False,
    }
    second_sell = {**sell_event, "signature": "sig-decoded-sell-2", "quote_amount": 2900, "user_quote_amount": 2886, "lp_fee": 8, "protocol_fee": 6}
    (archive / "pumpswap_swap_events.jsonl").write_text(
        "\n".join(json.dumps(row) for row in [sell_event, sell_event, second_sell]) + "\n",
        encoding="utf-8",
    )

    status = write_t007av_report([archive], output)
    events = _jsonl(output / "pumpswap_swap_events.jsonl")
    candidates = (output / "pumpswap_swap_candidate_inventory.csv").read_text(encoding="utf-8")

    assert status["pumpswap_swap_events_decoded"] == 2
    assert status["sell_event_count"] == 2
    assert status["fee_bps_populated_count"] == 2
    assert status["replay_validation_rows"] == 2
    assert status["fee_model_status"] == "confirmed"
    assert status["quote_confidence"] == "high"
    assert len(events) == 2
    assert "decoded_pumpswap_swap_event" in candidates


def test_persistent_lifecycle_store_records_recorder_artifacts_and_global_migrations(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=135)
    )
    mint = "mint-persistent"

    recorder._append_jsonl("birth_events.jsonl", _launch(mint, received_at=1000.0))
    recorder._append_jsonl(
        "curve_observations.jsonl",
        {
            **_obs(mint, progress=72.0, age=2.0),
            "decision_time": 1002.0,
            "quote_asset": "SOL",
            "bonding_curve_market_cap_usd": 31000.0,
        },
    )
    recorder._append_jsonl(
        "trade_flow_events.jsonl",
        {
            "mint": mint,
            "event_time": 1003.0,
            "trade_flow_available": True,
            "buyer_breadth_available": True,
            "organic_flow_available": True,
        },
    )
    recorder._append_jsonl(
        "true_curve_threshold_crossings.jsonl",
        {
            "mint": mint,
            "event_time": 1003.5,
            "threshold_pct": 70.0,
        },
    )
    recorder._append_jsonl(
        "holder_distribution_snapshots.jsonl",
        {
            "mint": mint,
            "event_time": 1004.0,
            "holder_distribution_available": True,
            "dev_behavior_available": True,
        },
    )

    writer = GlobalMigrationDedupeWriter(tmp_path, recorder=recorder)
    result = writer.record(
        {
            "mint": mint,
            "signature": "sig-global-migration",
            "slot": 123,
            "received_at": 1010.0,
            "pool_or_pair_address": "pool-persistent",
            "quote_asset": "SOL",
            "confidence": "confirmed",
            "detection_method": "pumpswap_pair_created_signal",
            "seen_in_birth_source": True,
            "admitted": True,
        }
    )
    recorder._append_jsonl(
        "post_migration_observations.jsonl",
        {
            "mint": mint,
            "event_time": 1011.0,
            "pool_or_pair_address": "pool-persistent",
            "quote_asset": "SOL",
            "post_migration_pool_state_available": True,
        },
    )
    recorder._append_jsonl(
        "executable_quote_observations.jsonl",
        {
            "mint": mint,
            "event_time": 1012.0,
            "pool_or_pair_address": "pool-persistent",
            "quote_asset": "SOL",
            "executable_quote_available": True,
        },
    )

    state = recorder.lifecycle_adapter.store.get_mint_state(mint)

    assert result == "event"
    assert state["birth_seen"] is True
    assert state["progress_decoded"] is True
    assert state["trade_flow_available"] is True
    assert state["holder_dev_available"] is True
    assert state["migration_seen"] is True
    assert state["post_migration_seen"] is True
    assert state["quote_ready"] is True
    assert state["coverage_class"] == "tracked_from_birth_full_path"


def test_route_latency_gate_includes_verified_commit_to_probe_enqueue_and_hot_path_drops(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_verified_birth_commit_to_probe_enqueue_p95_ms=100,
        )
    )
    recorder.verified_birth_commit_to_probe_enqueue_latencies_ms.extend([10.0, 250.0])
    recorder.summary_counters["source_verified_birth_commit_error_count"] = 1

    summary = recorder.build_summary()

    assert summary["decision_path_route_gate_passed"] is False
    assert "verified_birth_commit_to_probe_enqueue_p95_exceeded" in summary["decision_path_route_gate_failures"]
    assert "birth_hot_commit_errors_nonzero" in summary["decision_path_route_gate_failures"]
    assert summary["route_latency_gate_thresholds_ms"]["max_verified_birth_commit_to_probe_enqueue_p95_ms"] == 100


def test_verified_birth_commit_latency_is_recorded_once_per_mint(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100)
    )
    mint = "3sERStHyCYmMtzxokNuTPcyPcq89E9Kmp4nZVEVJpump"
    launch = {
        "mint": mint,
        "signature": "sig-hot-once",
        "slot": 123,
        "received_at": 1000.0,
        "normalized_at": 1000.0,
        "bonding_curve": str(bonding_curve_pda(mint)),
        "source_type": "transaction_subscribe",
        "decode_route": "direct_create",
    }

    recorder.record_source_verified_birth_commit(dict(launch))
    recorder.process_birth(dict(launch))
    recorder.record_source_verified_birth_commit(dict(launch))

    assert recorder.summary_counters["source_verified_birth_commit_count"] == 1
    assert recorder.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"] == 1
    assert len(recorder.birth_to_verified_birth_commit_latencies_ms) == 1


def test_process_birth_marks_admission_decision_before_birth_audit_projection(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100)
    )
    launch = _launch("decisionSplitMint111111111111111111111111111pump", received_at=1000.0)
    observed_before_projection: list[object] = []
    original_append = recorder._append_jsonl

    def spy_append(filename: str, row: dict) -> None:
        if filename == "birth_audit.jsonl":
            observed_before_projection.append(launch.get("_admission_decision_finished_at"))
        original_append(filename, row)

    recorder._append_jsonl = spy_append  # type: ignore[method-assign]

    recorder.process_birth(launch)

    assert observed_before_projection
    assert observed_before_projection[0] is not None


def test_birth_admission_complete_latency_is_materialization_gate_blocker(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_birth_to_admission_complete_p95_ms=1500,
        )
    )
    recorder.birth_to_admission_complete_latencies_ms.extend([2000.0, 3000.0, 4000.0])

    summary = recorder.build_summary()

    assert summary["birth_to_admission_complete_latency_ms"]["p95"] == 3900.0
    assert summary["birth_projection_latency_gate_scope"] == "diagnostic_only"
    assert summary["materialization_latency_gate_passed"] is False
    assert summary["materialization_latency_gate_failures"] == ["birth_to_admission_complete_p95_exceeded"]


def test_transaction_live_smoke_writes_hotpath_latency_spans(tmp_path: Path) -> None:
    mint = "mint-hotpath-span"
    source = FakeTransactionSubscribeAuditRoute(
        [
            {
                "received_at": 2000.0,
                "signature": "sig-hotpath-span",
                "slot": 20,
                "decoded_rows": [
                    {**_launch(mint, received_at=2000.0), "bonding_curve": f"curve-{mint}"}
                ],
            }
        ],
        actual_duration_seconds=1.0,
    )
    run_transaction_live_smoke(
        BondingCurveRecorderConfig(output_root=tmp_path, source_duration_seconds=1, sample_rate_percent=100),
        source=source,
        curve_probe=FakeCurveStateProbe({mint: {"progress_pct": 12.5, "fdv_units": "usd", "fdv_usd": 0}}),
        now_fn=lambda: 2000.2,
    )

    rows = _jsonl(tmp_path / "hotpath_latency_spans.jsonl")
    span = next(row for row in rows if row["mint"] == mint)
    assert span["birth_received_at"] == 2000.0
    assert span["verified_commit_finished_at"] is not None
    assert span["probe_enqueued_at"] is not None
    assert span["first_curve_observed_at"] is not None
    assert span["admission_decision_finished_at"] is not None
    assert span["projection_finished_at"] is not None
    assert span["bottleneck_stage"]


def test_bounded_finalization_defers_materialization_and_sets_final_gate(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(
            output_root=tmp_path,
            sample_rate_percent=100,
            max_finalization_wall_time_seconds=30,
            bounded_live_finalization_enabled=True,
        )
    )

    summary = recorder.finalize()
    live_status = json.loads((tmp_path / "live_status.json").read_text(encoding="utf-8"))

    assert summary["run_finalized"] is True
    assert summary["finalization_mode"] == "bounded_live_finalization"
    assert summary["offline_materialization_required"] is True
    assert summary["finalization_gate_passed"] is True
    assert live_status["run_status"] in {"finalized", "finalized_with_errors"}
    assert live_status["runtime_phase"] == "finalized"
    assert live_status["finalization_stuck_warning"] is False
