from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.t007_full_path_lifecycle_tracker import (
    build_lifecycle_outputs,
    join_latest_prior_execution_cost,
)
from research.mtp_research.validation.t007_thesis_ready_gate import (
    evaluate_t007_full_path_readiness_gate,
)
from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import (
    BondingCurveProgressRecorder,
    BondingCurveRecorderConfig,
    PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
    _migration_route_detection_from_row,
)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_full_path_fixture(root: Path, mint: str) -> None:
    _append_jsonl(root / "birth_audit.jsonl", {"mint": mint, "admitted": True, "signature": f"birth-{mint}", "received_at": 100.0})
    _append_jsonl(root / "curve_observations.jsonl", {"mint": mint, "progress_pct": 61.0, "received_at": 101.0})
    _append_jsonl(root / "true_curve_threshold_crossings.jsonl", {"mint": mint, "threshold": 60.0, "received_at": 102.0})
    _append_jsonl(root / "curve_velocity_events.jsonl", {"mint": mint, "curve_velocity_status": "available", "received_at": 103.0})
    _append_jsonl(root / "trade_flow_events.jsonl", {"mint": mint, "trade_flow_status": "available", "received_at": 104.0})
    _append_jsonl(root / "holder_distribution_snapshots.jsonl", {"mint": mint, "holder_distribution_status": "partial_trade_derived", "received_at": 105.0})
    _append_jsonl(root / "dev_behavior_events.jsonl", {"mint": mint, "dev_behavior_status": "partial_birth_metadata", "received_at": 105.5})
    _append_jsonl(root / "global_migration_events.jsonl", {"mint": mint, "pool_or_pair_address": f"pool-{mint}", "quote_asset": "SOL", "signature": f"migration-{mint}", "migration_received_at": 110.0})
    _append_jsonl(root / "post_migration_observations.jsonl", {"mint": mint, "pool_liquidity_quote": 10.0, "pool_liquidity_usd": 1500.0, "received_at": 111.0})
    _append_jsonl(root / "executable_quote_observations.jsonl", {"mint": mint, "price_impact_pct": 0.6, "received_at": 112.0})
    _append_jsonl(root / "pumpswap_swap_events.jsonl", {"mint": mint, "event_type": "buy", "received_at": 113.0})
    _append_jsonl(root / "execution_cost_observations.jsonl", {"observation_reason": "prioritization_fee", "execution_cost_status": "available", "decision_time": 99.0})


def test_t007bb_shaped_migrated_coverage_blocks_long_scans(tmp_path: Path) -> None:
    _write_full_path_fixture(tmp_path, "full-path-mint")
    for index in range(3):
        mint = f"migration-depth-only-{index}"
        _append_jsonl(tmp_path / "global_migration_events.jsonl", {"mint": mint, "pool_or_pair_address": f"pool-{index}", "quote_asset": "SOL", "migration_received_at": 200.0 + index})
        _append_jsonl(tmp_path / "post_migration_observations.jsonl", {"mint": mint, "pool_liquidity_quote": 5.0, "pool_liquidity_usd": 700.0, "received_at": 201.0 + index})
        _append_jsonl(tmp_path / "executable_quote_observations.jsonl", {"mint": mint, "price_impact_pct": 1.1, "received_at": 202.0 + index})
    _append_jsonl(tmp_path / "birth_audit.jsonl", {"mint": "sampled-migrated", "admitted": False, "admission_reason": "sample_rejected", "received_at": 300.0})
    _append_jsonl(tmp_path / "global_migration_events.jsonl", {"mint": "sampled-migrated", "pool_or_pair_address": "pool-sampled", "quote_asset": "SOL", "migration_received_at": 310.0})

    result = build_lifecycle_outputs(tmp_path, tmp_path / "out")
    summary = result["summary"]
    gate = result["gate"]

    assert summary["migrated_unique_mints"] == 5
    assert summary["full_path_migrated_mints"] == 1
    assert summary["coverage_buckets"]["full_path"] == 1
    assert summary["coverage_buckets"]["migration_plus_depth_only"] == 3
    assert summary["coverage_buckets"]["birth_seen_sample_rejected"] == 1
    assert summary["sample_loss_count"] == 1
    assert summary["source_miss_count"] == 3
    assert gate["can_run_10m_feature_proof"] is True
    assert gate["can_run_60m_thesis_scan"] is False
    assert gate["can_run_2h_plus_scan"] is False
    assert "migrated_source_miss_count_nonzero" in gate["blocking_reasons"]
    assert (tmp_path / "out" / "lifecycle_coverage_matrix.csv").exists()
    assert (tmp_path / "out" / "lifecycle_coverage_summary.json").exists()


def test_execution_cost_join_rejects_future_rows() -> None:
    joined = join_latest_prior_execution_cost(
        100.0,
        [
            {"decision_time": 101.0, "execution_cost_status": "future"},
            {"decision_time": 90.0, "execution_cost_status": "prior"},
        ],
    )

    assert joined["status"] == "joined"
    assert joined["joined_decision_time"] == 90.0
    assert joined["execution_cost_status"] == "prior"
    assert joined["decision_time_safe"] is True


def test_gate_requires_full_path_rates_before_longer_scans() -> None:
    gate = evaluate_t007_full_path_readiness_gate(
        {
            "migrated_unique_mints": 94,
            "full_path_migrated_mints": 1,
            "source_miss_count": 67,
            "sample_loss_count": 6,
            "curve_observation_missing_count": 17,
            "migrated_post_migration_quote_rate": 0.92,
            "migrated_execution_cost_join_rate": 1.0,
            "queue_drops": 0,
            "thin_queue_drops": 0,
            "capacity_rejected": 0,
            "valuation_ladder_suppressed": True,
            "mayhem_untouched": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
        }
    )

    assert gate["can_run_10m_feature_proof"] is True
    assert gate["can_run_60m_thesis_scan"] is False
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["full_path_migrated_rate"] < gate["required_full_path_migrated_rate"]
    assert "full_path_migrated_rate_below_threshold" in gate["blocking_reasons"]
    assert gate["helius_developer_source_supported"] is True


def test_gate_allows_60m_only_after_strict_lifecycle_proof() -> None:
    gate = evaluate_t007_full_path_readiness_gate(
        {
            "migrated_unique_mints": 5,
            "full_path_migrated_mints": 5,
            "source_miss_count": 0,
            "sample_loss_count": 0,
            "curve_observation_missing_count": 0,
            "trade_flow_missing_count": 0,
            "migration_backfill_failed_count": 0,
            "migrated_birth_seen_rate": 1.0,
            "migrated_curve_observation_rate": 1.0,
            "migrated_trade_flow_rate": 1.0,
            "migrated_post_migration_quote_rate": 1.0,
            "migrated_execution_cost_join_rate": 1.0,
            "evidence_completeness_rate": 1.0,
            "queue_drops": 0,
            "thin_queue_drops": 0,
            "capacity_rejected": 0,
            "valuation_ladder_suppressed": True,
            "mayhem_untouched": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "valid_60m_thesis_scan_passed": False,
        }
    )

    assert gate["can_run_60m_thesis_scan"] is True
    assert gate["can_run_2h_plus_scan"] is False
    assert gate["blocking_reasons"] == ["valid_60m_thesis_scan_not_yet_passed_for_2h_plus"]


def test_gate_blocks_partial_source_duration_even_when_lifecycle_rates_pass() -> None:
    gate = evaluate_t007_full_path_readiness_gate(
        {
            "migrated_unique_mints": 5,
            "full_path_migrated_mints": 5,
            "source_miss_count": 0,
            "sample_loss_count": 0,
            "curve_observation_missing_count": 0,
            "trade_flow_missing_count": 0,
            "migration_backfill_failed_count": 0,
            "migrated_birth_seen_rate": 1.0,
            "migrated_curve_observation_rate": 1.0,
            "migrated_trade_flow_rate": 1.0,
            "migrated_post_migration_quote_rate": 1.0,
            "migrated_execution_cost_join_rate": 1.0,
            "source_duration_quality_status": "partial",
            "source_ended_early": True,
            "queue_drops": 0,
            "thin_queue_drops": 0,
            "capacity_rejected": 0,
            "valuation_ladder_suppressed": True,
            "mayhem_untouched": True,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
        }
    )

    assert gate["can_run_60m_thesis_scan"] is False
    assert "source_duration_partial" in gate["blocking_reasons"]
    assert "source_ended_early" in gate["blocking_reasons"]


def test_lifecycle_summary_carries_source_duration_health_from_live_status(tmp_path: Path) -> None:
    _write_full_path_fixture(tmp_path, "full-path-mint")
    (tmp_path / "live_status.json").write_text(
        json.dumps(
            {
                "source_duration_quality_status": "partial",
                "source_ended_early": True,
                "source_duration_completion_ratio": 0.91,
                "requested_source_duration_seconds": 600,
                "actual_source_duration_seconds": 548,
                "websocket_keepalive_timeout_count": 11,
                "websocket_reconnect_count": 10,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_lifecycle_outputs(tmp_path, tmp_path / "out")
    summary = result["summary"]
    gate = result["gate"]

    assert summary["source_duration_quality_status"] == "partial"
    assert summary["source_ended_early"] is True
    assert summary["websocket_keepalive_timeout_count"] == 11
    assert gate["can_run_60m_thesis_scan"] is False
    assert "source_duration_partial" in gate["blocking_reasons"]


def test_replay_backfilled_birth_does_not_satisfy_live_birth_coverage(tmp_path: Path) -> None:
    mint = "backfilled-mint"
    _append_jsonl(
        tmp_path / "birth_audit.jsonl",
        {
            "mint": mint,
            "admitted": True,
            "birth_backfilled_from_replay": True,
            "birth_seen_live": False,
            "received_at": 100.0,
        },
    )
    _append_jsonl(tmp_path / "curve_observations.jsonl", {"mint": mint, "progress_pct": 65.0, "received_at": 101.0})
    _append_jsonl(tmp_path / "global_migration_events.jsonl", {"mint": mint, "pool_or_pair_address": "pool-backfilled", "quote_asset": "SOL", "migration_received_at": 110.0})

    result = build_lifecycle_outputs(tmp_path, tmp_path / "out")
    row = result["rows"][0]
    summary = result["summary"]
    gate = result["gate"]

    assert row["birth_seen"] is False
    assert row["live_birth_seen"] is False
    assert row["backfilled_birth_available"] is True
    assert summary["source_miss_count"] == 1
    assert summary["backfilled_birth_not_live_count"] == 1
    assert gate["can_run_60m_thesis_scan"] is False


def test_post_migration_observation_does_not_crash_when_sol_usd_missing(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=None)
    )

    recorder.record_post_migration_observation(
        {
            "mint": "mint-no-sol-usd",
            "pool_or_pair_address": "pool-no-sol-usd",
            "quote_asset": "SOL",
            "pool_liquidity_quote": 1.25,
            "received_at": 100.0,
            "decision_time": 100.0,
            "post_migration_status": "available",
        }
    )

    rows = [json.loads(line) for line in (tmp_path / "post_migration_observations.jsonl").read_text().splitlines() if line.strip()]
    row = rows[-1]
    assert row["mint"] == "mint-no-sol-usd"
    assert row["quote_to_usd_rate"] is None
    assert row["pool_liquidity_usd"] is None


def test_finalized_live_status_writes_durable_lifecycle_outputs(tmp_path: Path) -> None:
    recorder = BondingCurveProgressRecorder(
        BondingCurveRecorderConfig(output_root=tmp_path, sample_rate_percent=100, sol_usd=None)
    )
    _append_jsonl(
        tmp_path / "global_migration_events.jsonl",
        {
            "mint": "migration-only-mint",
            "pool_or_pair_address": "pool-migration-only",
            "quote_asset": "SOL",
            "migration_received_at": 100.0,
        },
    )
    _append_jsonl(
        tmp_path / "post_migration_observations.jsonl",
        {
            "mint": "migration-only-mint",
            "pool_liquidity_quote": 1.0,
            "received_at": 101.0,
        },
    )
    _append_jsonl(
        tmp_path / "executable_quote_observations.jsonl",
        {
            "mint": "migration-only-mint",
            "price_impact_pct": 1.5,
            "received_at": 102.0,
        },
    )

    recorder._write_live_status("finalized")

    assert (tmp_path / "lifecycle_coverage_summary.json").exists()
    assert (tmp_path / "lifecycle_coverage_matrix.csv").exists()
    summary = json.loads((tmp_path / "lifecycle_coverage_summary.json").read_text(encoding="utf-8"))
    assert summary["migrated_unique_mints"] == 1
    assert summary["gate"]["can_run_60m_thesis_scan"] is False


def test_pumpswap_buy_sell_rows_do_not_count_as_migration_pool_creation() -> None:
    row = {
        "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
        "instruction_type": "buy",
        "mint": "already-migrated-mint",
        "pool_or_pair_address": "already-existing-pool",
        "quote_mint": "So11111111111111111111111111111111111111112",
    }
    event = {
        "signature": "swap-sig",
        "slot": 123,
        "logs": [
            "Program log: CreateIdempotent",
            "Program log: Instruction: Buy",
        ],
        "route_name": "pumpswap_transaction_subscribe",
    }

    assert _migration_route_detection_from_row(row, event) is None


def test_pumpswap_create_pool_row_counts_as_migration_pool_creation() -> None:
    row = {
        "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
        "instruction_type": "create_pool",
        "mint": "newly-migrated-mint",
        "pool_or_pair_address": "new-pool",
        "quote_mint": "So11111111111111111111111111111111111111112",
    }
    event = {
        "signature": "create-pool-sig",
        "slot": 124,
        "logs": ["Program log: Instruction: CreatePool"],
        "route_name": "pumpswap_transaction_subscribe",
    }

    detection = _migration_route_detection_from_row(row, event)
    assert detection is not None
    assert detection["confidence"] == "confirmed"
    assert detection["source_route"] == "pumpswap_pool_create"
