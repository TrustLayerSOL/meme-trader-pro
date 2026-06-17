from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.t007_lifecycle_event_store import T007LifecycleEventStore


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_lifecycle_store_writes_and_reconciles_level_a_artifacts(tmp_path: Path) -> None:
    store = T007LifecycleEventStore(tmp_path)
    migration = {
        "signature": "sig-a",
        "slot": 10,
        "instruction_index": 2,
        "event_index": 0,
        "mint": "mint-a",
        "pool_or_pair_address": "pool-a",
        "migration_evidence_level": "LEVEL_A",
        "detection_method": "pumpswap_create_pool_instruction",
    }

    assert store.write_migration_event(migration) == "written"
    assert store.write_migration_event(migration) == "duplicate"
    assert store.write_pool_state_snapshot({"pool_or_pair_address": "pool-a", "mint": "mint-a", "depth_status": "available"}) == "written"
    summary = store.finalize_summary(extra={"source_gap_gate_passed": True, "unbackfilled_gap_count": 0})

    assert len(_jsonl(tmp_path / "migration_events.jsonl")) == 1
    assert summary["level_a_migration_count"] == 1
    assert summary["global_migration_events_deduped"] == 1
    assert summary["pool_state_ready_count"] == 1
    assert summary["summary_raw_counter_match"] is True
    assert summary["trading_disabled"] is True
    assert summary["wallet_signing_disabled"] is True
    assert summary["event_sourced_data_plane_enabled"] is True
    assert summary["raw_provenance_required"] is True


def test_dual_lane_reconciliation_marks_migration_only_rows_no_trade(tmp_path: Path) -> None:
    (tmp_path / "run_config.json").write_text(json.dumps({"enable_global_pumpswap_migration": True}) + "\n", encoding="utf-8")
    store = T007LifecycleEventStore(tmp_path)

    assert store.write_migration_event(
        {
            "signature": "sig-migration-only",
            "slot": 100,
            "instruction_index": 0,
            "mint": "mint-migration-only",
            "pool_or_pair_address": "pool-migration-only",
            "migration_evidence_level": "LEVEL_A",
            "detection_method": "pumpswap_create_pool_instruction",
        }
    ) == "written"

    summary = store.finalize_summary(extra={"source_gap_gate_passed": True, "unbackfilled_gap_count": 0})
    rows = _jsonl(tmp_path / "dual_lane_reconciliation_rows.jsonl")

    assert summary["dual_lane_reconciliation_enabled"] is True
    assert summary["global_migration_lane_enabled"] is True
    assert summary["dual_lane_global_migration_count"] == 1
    assert summary["dual_lane_migration_only_count"] == 1
    assert summary["dual_lane_not_eligible_no_trade_count"] == 1
    assert summary["dual_lane_eligible_live_decision_count"] == 0
    assert rows[0]["mint"] == "mint-migration-only"
    assert rows[0]["birth_seen"] is False
    assert rows[0]["trade_eligible"] is False
    assert rows[0]["data_completeness_grade"] == "MIGRATION_ONLY_NO_TRADE"
    assert rows[0]["no_trade_reason"] == "missing_birth_and_pre_migration_curve_evidence"


def test_dual_lane_reconciliation_marks_full_pre_migration_path_trade_eligible(tmp_path: Path) -> None:
    (tmp_path / "run_config.json").write_text(json.dumps({"enable_global_pumpswap_migration": True}) + "\n", encoding="utf-8")
    store = T007LifecycleEventStore(tmp_path)
    mint = "mint-full-path"
    pool = "pool-full-path"

    (tmp_path / "birth_audit.jsonl").write_text(
        json.dumps({"mint": mint, "slot": 10, "received_at": 1000.0, "launch_signature": "birth-sig"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "curve_observations.jsonl").write_text(
        json.dumps({"mint": mint, "slot": 20, "received_at": 1010.0, "progress_pct": 95.0, "decode_status": "decoded"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "true_curve_threshold_crossings.jsonl").write_text(
        json.dumps({"mint": mint, "slot": 21, "received_at": 1011.0, "threshold_pct": 95.0}) + "\n",
        encoding="utf-8",
    )
    assert store.write_migration_event(
        {
            "signature": "sig-full-path",
            "slot": 30,
            "instruction_index": 0,
            "mint": mint,
            "pool_or_pair_address": pool,
            "migration_evidence_level": "LEVEL_A",
            "detection_method": "pumpswap_create_pool_instruction",
        }
    ) == "written"
    assert store.write_pool_state_snapshot({"pool_or_pair_address": pool, "mint": mint, "depth_status": "available"}) == "written"

    summary = store.finalize_summary(extra={"source_gap_gate_passed": True, "unbackfilled_gap_count": 0})
    rows = _jsonl(tmp_path / "dual_lane_reconciliation_rows.jsonl")

    assert summary["dual_lane_birth_linked_migration_count"] == 1
    assert summary["dual_lane_full_path_pre_migration_evidence_count"] == 1
    assert summary["decision_time_evidence_complete_count"] == 1
    assert summary["dual_lane_eligible_live_decision_count"] == 1
    assert rows[0]["coverage_bucket"] == "full_path_pre_migration_evidence"
    assert rows[0]["trade_eligible"] is True
    assert rows[0]["data_completeness_grade"] == "FULL_PATH_DECISION_TIME_COMPLETE"
