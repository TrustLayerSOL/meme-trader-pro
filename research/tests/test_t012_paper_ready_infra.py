from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.t012_paper_position_ledger import (
    ensure_paper_position_artifacts,
    evaluate_principal_recovery,
    validate_paper_position_accounting_schema,
    validate_principal_recovery_schema,
)
from research.mtp_research.validation.t012_paper_artifact_materializer import (
    materialize_t012_paper_readiness_artifacts,
)
from research.mtp_research.validation.t012_paper_readiness_gate import run_t012_paper_readiness_audit
from research.mtp_research.validation.t012_paper_snapshot_contract import (
    build_post_entry_hot_flow_snapshot,
    build_pre_entry_decision_snapshot,
    write_t012_paper_snapshot_artifacts,
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_pre_entry_snapshot_schema_and_decision_time_safety(tmp_path: Path) -> None:
    row = build_pre_entry_decision_snapshot(
        run_id="run-1",
        mint="mint-1",
        token_symbol="TOK",
        birth_time=100.0,
        decision_time=130.0,
        decision_slot=12,
        birth_verified=True,
        bonding_curve_verified=True,
        curve_state_available=True,
        market_cap_available=True,
        curve_progress_pct=42.0,
        market_cap_usd=20_000.0,
        flow_30s={"event_count": 4, "buy_count": 3, "sell_count": 1, "unique_buyers": 2, "unique_sellers": 1},
        flow_60s={"event_count": 7, "buy_count": 5, "sell_count": 2, "unique_buyers": 4, "unique_sellers": 2},
        dev_wallet="creator-1",
        dev_previous_migrations=3,
        creator_sold_before_entry=False,
        max_source_lag_ms=250.0,
        source_provenance={"source": "fixture"},
        input_event_ids=["a", "b"],
    )

    assert row["stage"] == "T012_PRE_MIGRATION_PAPER_READY_INFRA"
    assert row["snapshot_type"] == "pre_entry_decision_snapshot"
    assert row["token_age_seconds"] == 30.0
    assert row["event_count_30s_since_birth"] == 4
    assert row["net_buy_count_30s_since_birth"] == 2
    assert row["buy_sell_ratio_30s_since_birth"] == 3.0
    assert row["event_count_60s"] == 7
    assert row["dev_previous_migrations_status"] == "available"
    assert row["dev_previous_migrations_decision_time_safe"] is True
    assert row["creator_sold_before_entry_status"] == "available"
    assert row["creator_sold_before_entry_decision_time_safe"] is True
    assert row["decision_time_safe"] is True
    assert row["paper_trading_enabled"] is False
    assert row["live_trading_enabled"] is False
    assert row["buy_sell_signal_generated"] is False


def test_post_entry_hot_flow_snapshot_schema_all_offsets(tmp_path: Path) -> None:
    rows = [
        build_post_entry_hot_flow_snapshot(
            run_id="run-1",
            mint="mint-1",
            paper_candidate_id="candidate-1",
            entry_reference_time=100.0,
            snapshot_offset_seconds=offset,
            snapshot_time=100.0 + offset,
            snapshot_slot=20 + offset,
            market_cap_at_reference=10_000.0,
            market_cap_now=10_000.0 + offset,
            curve_progress_at_reference=20.0,
            curve_progress_now=20.0 + offset / 10.0,
            buy_count_since_reference=offset,
            sell_count_since_reference=1,
            unique_buyers_since_reference=offset,
            unique_sellers_since_reference=1,
            source_provenance={"source": "fixture"},
            input_event_ids=[f"e-{offset}"],
        )
        for offset in [1, 5, 10, 30, 60]
    ]

    assert {row["snapshot_offset_seconds"] for row in rows} == {1, 5, 10, 30, 60}
    assert all(row["snapshot_type"] == "post_entry_hot_flow_snapshot" for row in rows)
    assert all(row["paper_candidate_id"] == "candidate-1" for row in rows)
    assert all(row["paper_trade_generated"] is False for row in rows)
    assert all(row["decision_time_safe"] is True for row in rows)


def test_paper_position_ledger_and_principal_recovery_schemas(tmp_path: Path) -> None:
    paths = ensure_paper_position_artifacts(tmp_path, run_id="run-1")

    assert paths["paper_position_ledger"].exists()
    assert paths["paper_position_events"].exists()
    assert paths["paper_position_accounting_snapshots"].exists()
    assert paths["paper_principal_recovery_events"].exists()
    assert validate_paper_position_accounting_schema(tmp_path)["schema_valid"] is True
    assert validate_principal_recovery_schema(tmp_path)["schema_valid"] is True

    recovered = evaluate_principal_recovery(
        paper_position_id="pos-1",
        mint="mint-1",
        total_cost_basis_quote=10.0,
        estimated_fees_quote=0.2,
        total_sell_proceeds_quote=10.3,
    )
    partial = evaluate_principal_recovery(
        paper_position_id="pos-2",
        mint="mint-2",
        total_cost_basis_quote=10.0,
        estimated_fees_quote=0.2,
        total_sell_proceeds_quote=5.0,
    )
    missing = evaluate_principal_recovery(
        paper_position_id="pos-3",
        mint="mint-3",
        total_cost_basis_quote=None,
        estimated_fees_quote=0.2,
        total_sell_proceeds_quote=5.0,
    )

    assert recovered["principal_recovered"] is True
    assert recovered["principal_recovery_status"] == "principal_recovered"
    assert recovered["principal_recovery_ratio"] > 1.0
    assert partial["principal_recovered"] is False
    assert partial["principal_recovery_status"] == "partially_recovered"
    assert missing["principal_recovery_status"] == "unknown_missing_cost_basis"


def test_t012_gate_fails_when_artifacts_missing_and_passes_full_fixture(tmp_path: Path) -> None:
    base_summary = {
        "run_id": "run-1",
        "run_status": "finalized",
        "run_finalized": True,
        "source_duration_quality_status": "complete",
        "queue_drops": 0,
        "source_event_queue_dropped_count": 0,
        "birth_priority_queue_dropped_count": 0,
        "trade_flow_queue_dropped_count": 0,
        "near_entry_hot_flow_ring_buffer_dropped_count": 0,
        "rpc_failures": 0,
        "http_429_count": 0,
        "paper_trading_enabled": False,
        "live_trading_enabled": False,
        "route_latency_histograms": {
            "birth_to_admission_complete_latency_ms": {"p95": 100.0, "count": 1},
            "birth_to_first_curve_observation_latency_ms": {"p95": 700.0, "count": 1},
            "normalized_birth_to_probe_start_latency_ms": {"p95": 400.0, "count": 1},
        },
    }
    (tmp_path / "collector_summary.json").write_text(json.dumps(base_summary), encoding="utf-8")

    failed = run_t012_paper_readiness_audit(tmp_path)
    assert failed["gate_passed"] is False
    assert "pre_entry_30s_snapshot_missing" in failed["blocking_reasons"]
    assert "paper_position_ledger_missing" in failed["blocking_reasons"]

    write_t012_paper_snapshot_artifacts(
        tmp_path,
        run_id="run-1",
        pre_entry_rows=[
            build_pre_entry_decision_snapshot(
                run_id="run-1",
                mint="mint-1",
                birth_time=100.0,
                decision_time=130.0,
                decision_slot=1,
                flow_30s={"event_count": 1, "buy_count": 1, "sell_count": 0},
                flow_60s={"event_count": 1, "buy_count": 1, "sell_count": 0},
                dev_wallet="creator",
                dev_previous_migrations=3,
                creator_sold_before_entry=False,
            )
        ],
        post_entry_rows=[
            build_post_entry_hot_flow_snapshot(
                run_id="run-1",
                mint="mint-1",
                paper_candidate_id="cand-1",
                entry_reference_time=100.0,
                snapshot_offset_seconds=offset,
                snapshot_time=100.0 + offset,
                snapshot_slot=offset,
            )
            for offset in [1, 5, 10, 30, 60]
        ],
    )
    ensure_paper_position_artifacts(tmp_path, run_id="run-1")

    passed = run_t012_paper_readiness_audit(tmp_path)
    assert passed["gate_id"] == "T012_PRE_MIGRATION_PAPER_READINESS_GATE"
    assert passed["gate_passed"] is True
    assert passed["paper_ready_status"] == "paper_infrastructure_ready"
    assert passed["paper_trading_enabled"] is False
    assert passed["live_trading_enabled"] is False
    assert passed["wallet_private_key_signing_execution_absent"] is True
    assert passed["paper_infrastructure_ready"] is True


def test_t012_snapshot_writer_creates_required_summary_files(tmp_path: Path) -> None:
    result = write_t012_paper_snapshot_artifacts(tmp_path, run_id="run-1", pre_entry_rows=[], post_entry_rows=[])

    assert result["pre_entry_decision_snapshots_path"].endswith("pre_entry_decision_snapshots.jsonl")
    assert (tmp_path / "pre_entry_decision_snapshots.jsonl").exists()
    assert (tmp_path / "post_entry_hot_flow_snapshots.jsonl").exists()
    assert (tmp_path / "paper_readiness_summary.md").exists()


def test_t012_gate_keeps_paper_and_lifecycle_readiness_separate(tmp_path: Path) -> None:
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "run_status": "finalized",
                "run_finalized": True,
                "source_duration_quality_status": "complete",
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429_count": 0,
                "can_run_60m_thesis_scan": False,
                "strict_full_path_migrated_mints": 0,
                "paper_trading_enabled": False,
                "live_trading_enabled": False,
                "route_latency_histograms": {
                    "birth_to_admission_complete_latency_ms": {"p95": 100.0, "count": 1},
                    "birth_to_first_curve_observation_latency_ms": {"p95": 700.0, "count": 1},
                    "normalized_birth_to_probe_start_latency_ms": {"p95": 400.0, "count": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    write_t012_paper_snapshot_artifacts(
        tmp_path,
        run_id="run-1",
        pre_entry_rows=[
            build_pre_entry_decision_snapshot(
                run_id="run-1",
                mint="mint-1",
                birth_time=100.0,
                decision_time=160.0,
                decision_slot=1,
                flow_30s={"event_count": 1},
                flow_60s={"event_count": 1},
                dev_previous_migrations=3,
                creator_sold_before_entry=False,
            )
        ],
        post_entry_rows=[
            build_post_entry_hot_flow_snapshot(
                run_id="run-1",
                mint="mint-1",
                paper_candidate_id="cand-1",
                entry_reference_time=100.0,
                snapshot_offset_seconds=offset,
                snapshot_time=100.0 + offset,
                snapshot_slot=offset,
            )
            for offset in [1, 5, 10, 30, 60]
        ],
    )
    ensure_paper_position_artifacts(tmp_path, run_id="run-1")

    gate = run_t012_paper_readiness_audit(tmp_path)

    assert gate["gate_passed"] is True
    assert gate["migration_full_path_required_for_pre_migration_paper"] is False
    assert gate["paper_trading_enabled"] is False
    assert gate["live_trading_enabled"] is False


def test_t012_gate_fails_specific_dev_and_principal_recovery_missing(tmp_path: Path) -> None:
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "run_status": "finalized",
                "run_finalized": True,
                "source_duration_quality_status": "complete",
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429_count": 0,
                "paper_trading_enabled": False,
                "live_trading_enabled": False,
                "route_latency_histograms": {
                    "birth_to_admission_complete_latency_ms": {"p95": 100.0, "count": 1},
                    "birth_to_first_curve_observation_latency_ms": {"p95": 700.0, "count": 1},
                    "normalized_birth_to_probe_start_latency_ms": {"p95": 400.0, "count": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    write_t012_paper_snapshot_artifacts(
        tmp_path,
        run_id="run-1",
        pre_entry_rows=[
            build_pre_entry_decision_snapshot(
                run_id="run-1",
                mint="mint-1",
                birth_time=100.0,
                decision_time=160.0,
                decision_slot=1,
                flow_30s={"event_count": 1},
                flow_60s={"event_count": 1},
                dev_previous_migrations=None,
                creator_sold_before_entry=None,
            )
        ],
        post_entry_rows=[
            build_post_entry_hot_flow_snapshot(
                run_id="run-1",
                mint="mint-1",
                paper_candidate_id="cand-1",
                entry_reference_time=100.0,
                snapshot_offset_seconds=offset,
                snapshot_time=100.0 + offset,
                snapshot_slot=offset,
            )
            for offset in [1, 5, 10, 30, 60]
        ],
    )
    paths = ensure_paper_position_artifacts(tmp_path, run_id="run-1")
    paths["paper_principal_recovery_events"].unlink()

    gate = run_t012_paper_readiness_audit(tmp_path)

    assert gate["gate_passed"] is False
    assert "dev_previous_migrations_decision_safe_missing" in gate["blocking_reasons"]
    assert "creator_sold_before_entry_decision_safe_missing" in gate["blocking_reasons"]
    assert "principal_recovery_tracking_schema_invalid" in gate["blocking_reasons"]


def test_t012_materializer_repairs_legacy_hot_flow_artifacts(tmp_path: Path) -> None:
    (tmp_path / "collector_summary.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "run_status": "finalized",
                "run_finalized": True,
                "source_duration_quality_status": "complete",
                "queue_drops": 0,
                "rpc_failures": 0,
                "http_429_count": 0,
                "paper_trading_enabled": False,
                "live_trading_enabled": False,
                "route_latency_histograms": {
                    "birth_to_admission_complete_latency_ms": {"p95": 50.0, "count": 1},
                    "birth_to_first_curve_observation_latency_ms": {"p95": 700.0, "count": 1},
                    "normalized_birth_to_probe_start_latency_ms": {"p95": 400.0, "count": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    with (tmp_path / "near_entry_hot_flow_snapshots.jsonl").open("w", encoding="utf-8") as handle:
        for offset in [1, 5, 10, 30, 60]:
            handle.write(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "mint": "mint-1",
                        "event_id": f"event-{offset}",
                        "entry_received_at": 100.0,
                        "window_seconds_after_entry": offset,
                        "buy_count_after_entry": offset,
                        "sell_count_after_entry": 1,
                        "unique_buyers_after_entry": offset,
                        "unique_sellers_after_entry": 1,
                        "largest_buy_quote_after_entry": 0.1,
                        "largest_sell_quote_after_entry": 0.01,
                    }
                )
                + "\n"
            )
    (tmp_path / "wallet_dev_checkpoints.jsonl").write_text(
        json.dumps(
            {
                "mint": "mint-1",
                "creator_address": "creator-1",
                "dev_previous_migrations": 3,
                "dev_previous_migrations_decision_time_safe": True,
                "creator_sold_before_entry": False,
                "creator_sold_before_entry_decision_time_safe": True,
                "db_commit_sequence": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = materialize_t012_paper_readiness_artifacts(tmp_path)
    gate = run_t012_paper_readiness_audit(tmp_path)

    assert result["materialized_snapshot_artifacts"] is True
    assert result["pre_entry_rows_materialized"] == 1
    assert result["post_entry_rows_materialized"] == 5
    assert gate["gate_passed"] is True
    assert gate["pre_entry_30s_snapshot_count"] == 1
    assert gate["pre_entry_60s_snapshot_count"] == 1
    assert gate["post_entry_1s_snapshot_count"] == 1
    assert gate["post_entry_5s_snapshot_count"] == 1
    assert gate["post_entry_10s_snapshot_count"] == 1
    assert gate["post_entry_30s_snapshot_count"] == 1
    assert gate["post_entry_60s_snapshot_count"] == 1
    assert gate["paper_position_ledger_exists"] is True
    assert gate["principal_recovery_tracking_schema_valid"] is True
