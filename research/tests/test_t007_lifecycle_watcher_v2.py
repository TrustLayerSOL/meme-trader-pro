from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.run_t007_lifecycle_watcher_v2 import finalize_offline_lifecycle_root


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_full_path_fixture(root: Path, *, global_lane_enabled: bool = True, collector_summary: dict | None = None) -> None:
    mint = "mint-a"
    pool = "pool-a"
    (root / "run_config.json").write_text(
        json.dumps({"enable_global_pumpswap_migration": global_lane_enabled}) + "\n",
        encoding="utf-8",
    )
    if collector_summary is not None:
        (root / "collector_summary.json").write_text(json.dumps(collector_summary) + "\n", encoding="utf-8")
    _append(root / "birth_audit.jsonl", {"mint": mint, "slot": 10, "received_at": 1000.0, "launch_signature": "birth-sig"})
    _append(root / "curve_observations.jsonl", {"mint": mint, "slot": 20, "received_at": 1010.0, "progress_pct": 95.0, "decode_status": "decoded"})
    _append(root / "true_curve_threshold_crossings.jsonl", {"mint": mint, "slot": 21, "received_at": 1011.0, "threshold_pct": 95.0})
    _append(
        root / "migration_events.jsonl",
        {
            "signature": "sig-a",
            "slot": 30,
            "instruction_index": 0,
            "mint": mint,
            "pool_or_pair_address": pool,
            "migration_evidence_level": "LEVEL_A",
        },
    )
    _append(root / "pool_state_snapshots.jsonl", {"mint": mint, "pool_or_pair_address": pool, "depth_status": "available"})


def test_finalize_offline_lifecycle_root_does_not_start_live_scan(tmp_path: Path) -> None:
    _write_full_path_fixture(tmp_path)
    (tmp_path / "source_gap_health.json").write_text(json.dumps({"source_gap_gate_passed": True, "unbackfilled_gap_count": 0}) + "\n", encoding="utf-8")

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["live_scan_started"] is False
    assert result["summary"]["level_a_migration_count"] == 1
    assert result["gate"]["decision_label"] == "T007_DUAL_LANE_LEVEL_A_PROOF_READY"
    assert (tmp_path / "lifecycle_coverage_summary_v2.json").exists()
    assert (tmp_path / "thesis_ready_gate_v2.json").exists()


def test_finalize_offline_lifecycle_root_counts_existing_global_migration_schema(tmp_path: Path) -> None:
    (tmp_path / "run_config.json").write_text(json.dumps({"enable_global_pumpswap_migration": True}) + "\n", encoding="utf-8")
    _append(tmp_path / "birth_audit.jsonl", {"mint": "mint-global-a", "slot": 10, "received_at": 1000.0})
    _append(tmp_path / "curve_observations.jsonl", {"mint": "mint-global-a", "slot": 20, "received_at": 1010.0, "progress_pct": 95.0})
    _append(tmp_path / "true_curve_threshold_crossings.jsonl", {"mint": "mint-global-a", "slot": 21, "received_at": 1011.0, "threshold_pct": 95.0})
    _append(
        tmp_path / "global_migration_events.jsonl",
        {
            "signature": "sig-global-a",
            "slot": 30,
            "mint": "mint-global-a",
            "pool_or_pair_address": "pool-global-a",
            "migration_evidence_level": "LEVEL_A",
            "detection_method": "pumpswap_pair_created_signal",
            "source_route": "pumpswap_pool_create",
        },
    )
    _append(
        tmp_path / "post_migration_observations.jsonl",
        {
            "mint": "mint-global-a",
            "pool_or_pair_address": "pool-global-a",
            "pool_base_token_account": "base-vault-a",
            "pool_quote_token_account": "quote-vault-a",
        },
    )
    (tmp_path / "source_gap_health.json").write_text(json.dumps({"source_gap_gate_passed": True, "unbackfilled_gap_count": 0}) + "\n", encoding="utf-8")

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["summary"]["level_a_migration_count"] == 1
    assert result["summary"]["pool_state_ready_count"] == 1
    assert result["gate"]["decision_label"] == "T007_DUAL_LANE_LEVEL_A_PROOF_READY"


def test_finalize_offline_lifecycle_root_blocks_reconnects_without_backfill(tmp_path: Path) -> None:
    (tmp_path / "run_config.json").write_text(json.dumps({"enable_global_pumpswap_migration": True}) + "\n", encoding="utf-8")
    _append(tmp_path / "birth_audit.jsonl", {"mint": "mint-global-gap", "slot": 10, "received_at": 1000.0})
    _append(tmp_path / "curve_observations.jsonl", {"mint": "mint-global-gap", "slot": 20, "received_at": 1010.0, "progress_pct": 95.0})
    _append(tmp_path / "true_curve_threshold_crossings.jsonl", {"mint": "mint-global-gap", "slot": 21, "received_at": 1011.0, "threshold_pct": 95.0})
    _append(
        tmp_path / "global_migration_events.jsonl",
        {
            "signature": "sig-global-gap",
            "slot": 30,
            "mint": "mint-global-gap",
            "pool_or_pair_address": "pool-global-gap",
            "migration_evidence_level": "LEVEL_A",
            "detection_method": "pumpswap_pair_created_signal",
            "source_route": "pumpswap_pool_create",
        },
    )
    _append(
        tmp_path / "post_migration_observations.jsonl",
        {
            "mint": "mint-global-gap",
            "pool_or_pair_address": "pool-global-gap",
            "pool_base_token_account": "base-vault-gap",
            "pool_quote_token_account": "quote-vault-gap",
        },
    )
    (tmp_path / "live_status.json").write_text(
        json.dumps(
            {
                "requested_source_duration_seconds": 600,
                "actual_source_duration_seconds": 608,
                "source_duration_quality_status": "complete",
                "websocket_keepalive_timeout_count": 2,
                "websocket_reconnect_count": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["summary"]["level_a_migration_count"] == 1
    assert result["summary"]["source_gap_gate_passed"] is False
    assert result["summary"]["unbackfilled_gap_count"] == 2
    assert result["gate"]["decision_label"] == "T007_SOURCE_GAP_BACKFILL_BROKEN"
    assert "websocket_reconnects_without_backfill" in result["summary"]["source_gap_blocking_reasons"]


def test_finalize_blocks_when_global_pumpswap_lane_disabled(tmp_path: Path) -> None:
    _write_full_path_fixture(tmp_path, global_lane_enabled=False)
    (tmp_path / "source_gap_health.json").write_text(json.dumps({"source_gap_gate_passed": True, "unbackfilled_gap_count": 0}) + "\n", encoding="utf-8")

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["summary"]["global_migration_lane_enabled"] is False
    assert result["gate"]["decision_label"] == "T007_GLOBAL_MIGRATION_LANE_DISABLED"
    assert result["gate"]["can_run_60m_thesis_scan"] is False
    assert "global_pumpswap_migration_lane_disabled" in result["gate"]["blocking_reasons"]


def test_finalize_blocks_migration_only_level_a_without_decision_time_evidence(tmp_path: Path) -> None:
    (tmp_path / "run_config.json").write_text(json.dumps({"enable_global_pumpswap_migration": True}) + "\n", encoding="utf-8")
    _append(
        tmp_path / "global_migration_events.jsonl",
        {
            "signature": "sig-migration-only",
            "slot": 30,
            "mint": "mint-migration-only",
            "pool_or_pair_address": "pool-migration-only",
            "migration_evidence_level": "LEVEL_A",
        },
    )
    _append(tmp_path / "pool_state_snapshots.jsonl", {"mint": "mint-migration-only", "pool_or_pair_address": "pool-migration-only", "depth_status": "available"})
    (tmp_path / "source_gap_health.json").write_text(json.dumps({"source_gap_gate_passed": True, "unbackfilled_gap_count": 0}) + "\n", encoding="utf-8")

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["summary"]["dual_lane_migration_only_count"] == 1
    assert result["summary"]["dual_lane_eligible_live_decision_count"] == 0
    assert result["gate"]["decision_label"] == "T007_DUAL_LANE_READY_NO_DECISION_ELIGIBLE_VOLUME"
    assert result["gate"]["can_run_60m_thesis_scan"] is False


def test_finalize_blocks_thin_probe_drops_even_with_full_path_evidence(tmp_path: Path) -> None:
    _write_full_path_fixture(tmp_path, collector_summary={"thin_probe_queue_drops": 1})
    (tmp_path / "source_gap_health.json").write_text(json.dumps({"source_gap_gate_passed": True, "unbackfilled_gap_count": 0}) + "\n", encoding="utf-8")

    result = finalize_offline_lifecycle_root(tmp_path)

    assert result["summary"]["thin_probe_queue_drops"] == 1
    assert result["gate"]["decision_label"] == "T007_THIN_PROBE_CAPACITY_BROKEN"
    assert result["gate"]["can_run_60m_thesis_scan"] is False
    assert "thin_probe_queue_drops_nonzero" in result["gate"]["blocking_reasons"]


def test_runner_backfill_mode_requires_explicit_read_only_flag(tmp_path: Path) -> None:
    from research.mtp_research.validation.run_t007_lifecycle_watcher_v2 import main

    try:
        main(["--mode", "backfill-pumpswap-gaps", "--output-root", str(tmp_path), "--max-signatures", "5"])
    except SystemExit as exc:
        assert "explicit" in str(exc)
    else:
        raise AssertionError("expected SystemExit for missing explicit read-only flag")


def test_runner_tracked_mint_lookup_mode_requires_explicit_read_only_flag(tmp_path: Path) -> None:
    from research.mtp_research.validation.run_t007_lifecycle_watcher_v2 import main

    try:
        main(["--mode", "tracked-mint-lookup", "--output-root", str(tmp_path), "--max-transactions-per-address", "5"])
    except SystemExit as exc:
        assert "explicit" in str(exc)
    else:
        raise AssertionError("expected SystemExit for missing explicit read-only flag")
