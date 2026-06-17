from __future__ import annotations

import json
import threading
from pathlib import Path

from research.mtp_research.validation.t007_lifecycle_events import (
    COVERAGE_PREEXISTING_BEFORE_WATCHER,
    COVERAGE_REPLAY_UNRESOLVED,
    COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH,
    COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE,
    COVERAGE_TRUE_SOURCE_MISS,
    STATE_PROGRESS_TRACKING,
    event_from_birth_row,
    event_from_curve_observation_row,
    event_from_migration_row,
    event_from_post_migration_row,
    event_from_quote_row,
    event_from_trade_flow_row,
    event_from_holder_dev_row,
    event_from_threshold_row,
    event_from_replay_context_row,
)
from research.mtp_research.validation.t007_lifecycle_exporter import export_lifecycle_outputs_from_store
from research.mtp_research.validation.t007_lifecycle_state_store import T007LifecycleStateStore


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_birth_to_curve_state_progression_preserves_decision_timestamps(tmp_path: Path) -> None:
    store = T007LifecycleStateStore(tmp_path / "state.sqlite", ledger_path=tmp_path / "lifecycle_events.jsonl")

    store.append_event(event_from_birth_row({"mint": "mint-a", "received_at": 100.0, "slot": 10, "signature": "sig-birth"}))
    store.append_event(
        event_from_curve_observation_row(
            {
                "mint": "mint-a",
                "received_at": 101.5,
                "decision_time": 101.5,
                "bonding_curve_account": "curve-a",
                "decode_status": "decoded",
                "progress_pct": 12.5,
            }
        )
    )

    state = store.get_mint_state("mint-a")
    assert state["lifecycle_state"] == STATE_PROGRESS_TRACKING
    assert state["birth_seen"] is True
    assert state["curve_account_verified"] is True
    assert state["first_birth_seen_at"] == 100.0
    assert state["first_curve_verified_at"] == 101.5
    assert state["last_event_at"] == 101.5
    assert _rows(tmp_path / "lifecycle_events.jsonl")[0]["event_type"] == "birth_seen"


def test_migration_coverage_classes_are_persistent_and_decision_time_safe(tmp_path: Path) -> None:
    store = T007LifecycleStateStore(tmp_path / "state.sqlite", ledger_path=tmp_path / "lifecycle_events.jsonl")

    for event in [
        event_from_birth_row({"mint": "full", "received_at": 100.0}),
        event_from_curve_observation_row({"mint": "full", "decision_time": 101.0, "decode_status": "decoded", "progress_pct": 50.0}),
        event_from_threshold_row({"mint": "full", "decision_time": 102.0, "threshold_pct": 50.0}),
        event_from_trade_flow_row({"mint": "full", "decision_time": 103.0, "buy_count": 3}),
        event_from_holder_dev_row({"mint": "full", "decision_time": 104.0, "holder_count": 12}),
        event_from_migration_row({"mint": "full", "migration_received_at": 105.0, "pool_or_pair_address": "pool-full"}),
        event_from_post_migration_row({"mint": "full", "decision_time": 106.0, "pool_or_pair_address": "pool-full", "base_reserve_raw": 1}),
        event_from_quote_row({"mint": "full", "decision_time": 107.0, "price_impact_pct": 0.1}),
    ]:
        store.append_event(event)

    for event in [
        event_from_birth_row({"mint": "missing", "received_at": 200.0}),
        event_from_curve_observation_row({"mint": "missing", "decision_time": 201.0, "decode_status": "decoded", "progress_pct": 40.0}),
        event_from_migration_row({"mint": "missing", "migration_received_at": 205.0, "pool_or_pair_address": "pool-missing"}),
    ]:
        store.append_event(event)

    store.append_event(event_from_migration_row({"mint": "pre", "migration_received_at": 300.0, "pool_or_pair_address": "pool-pre"}))
    store.append_event(event_from_replay_context_row({"mint": "pre", "launch_time_from_replay": 90.0, "campaign_start_time": 100.0}))
    store.append_event(event_from_migration_row({"mint": "miss", "migration_received_at": 300.0, "pool_or_pair_address": "pool-miss"}))
    store.append_event(event_from_replay_context_row({"mint": "miss", "launch_time_from_replay": 150.0, "campaign_start_time": 100.0, "campaign_end_time": 200.0}))
    store.append_event(event_from_migration_row({"mint": "unresolved", "migration_received_at": 300.0, "pool_or_pair_address": "pool-unresolved"}))
    store.append_event(event_from_replay_context_row({"mint": "unresolved", "failure_reason": "replay_birth_not_found"}))

    assert store.get_mint_state("full")["coverage_class"] == COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH
    assert store.get_mint_state("missing")["coverage_class"] == COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE
    assert store.get_mint_state("pre")["coverage_class"] == COVERAGE_PREEXISTING_BEFORE_WATCHER
    assert store.get_mint_state("miss")["coverage_class"] == COVERAGE_TRUE_SOURCE_MISS
    assert store.get_mint_state("unresolved")["coverage_class"] == COVERAGE_REPLAY_UNRESOLVED
    assert store.get_mint_state("full")["first_quote_ready_at"] == 107.0


def test_sqlite_state_survives_restart_and_exports_existing_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    ledger_path = tmp_path / "lifecycle_events.jsonl"
    store = T007LifecycleStateStore(db_path, ledger_path=ledger_path)
    store.append_event(event_from_birth_row({"mint": "mint-a", "received_at": 100.0}))
    store.append_event(event_from_migration_row({"mint": "mint-a", "migration_received_at": 120.0, "pool_or_pair_address": "pool-a", "quote_asset": "SOL"}))
    store.close()

    reopened = T007LifecycleStateStore(db_path, ledger_path=ledger_path)
    assert reopened.get_mint_state("mint-a")["migration_seen"] is True

    summary = export_lifecycle_outputs_from_store(reopened, tmp_path)
    assert summary["persistent_lifecycle_store_status"] == "available"
    assert summary["active_lifecycle_mints"] == 1
    assert summary["migrated_unique_mints"] == 1
    assert summary["tracked_from_birth_migrations"] == 1
    assert summary["full_path_ready_migrations"] == 0
    assert summary["preexisting_before_watcher_migrations"] == 0
    assert summary["migration_only_untracked_migrations"] == 0
    assert summary["replay_unresolved_migrations"] == 0
    assert summary["true_source_miss_migrations"] == 0
    assert (tmp_path / "lifecycle_coverage_summary.json").exists()
    assert (tmp_path / "lifecycle_coverage_matrix.csv").exists()
    assert (tmp_path / "migration_source_coverage_audit.csv").exists()
    assert (tmp_path / "migration_source_coverage_audit.jsonl").exists()


def test_lifecycle_store_serializes_cross_thread_event_producers(tmp_path: Path) -> None:
    store = T007LifecycleStateStore(tmp_path / "state.sqlite", ledger_path=tmp_path / "lifecycle_events.jsonl")
    errors: list[BaseException] = []

    def worker(prefix: str) -> None:
        try:
            for index in range(25):
                mint = f"{prefix}-{index}"
                store.append_event(event_from_birth_row({"mint": mint, "received_at": 100.0 + index}))
                store.append_event(
                    event_from_migration_row(
                        {
                            "mint": mint,
                            "migration_received_at": 200.0 + index,
                            "pool_or_pair_address": f"pool-{mint}",
                        }
                    )
                )
        except BaseException as exc:  # pragma: no cover - assertion below reports details.
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"thread-{i}",)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    store.flush()
    health = store.health()

    assert health["persistent_lifecycle_store_status"] == "available"
    assert health["persistent_lifecycle_error_count"] == 0
    assert health["persistent_lifecycle_event_count"] == 200
    assert health["persistent_lifecycle_state_count"] == 100
    assert store.get_mint_state("thread-3-24")["migration_seen"] is True
    assert len(_rows(tmp_path / "lifecycle_events.jsonl")) == 200


def test_lifecycle_event_ledger_is_regenerated_from_committed_sqlite_events(tmp_path: Path) -> None:
    store = T007LifecycleStateStore(tmp_path / "state.sqlite", ledger_path=tmp_path / "lifecycle_events.jsonl")
    store.append_event(event_from_birth_row({"mint": "mint-ledger", "received_at": 100.0}))
    store.flush()
    with (tmp_path / "lifecycle_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "quote_observed", "mint": "phantom", "observed_at": 999.0}) + "\n")

    health = store.health()
    rows = _rows(tmp_path / "lifecycle_events.jsonl")

    assert health["persistent_lifecycle_event_count"] == 1
    assert health["persistent_lifecycle_ledger_line_count"] == 1
    assert health["persistent_lifecycle_ledger_db_consistent"] is True
    assert [row["mint"] for row in rows] == ["mint-ledger"]


def test_live_health_does_not_regenerate_event_ledger(tmp_path: Path) -> None:
    store = T007LifecycleStateStore(tmp_path / "state.sqlite", ledger_path=tmp_path / "lifecycle_events.jsonl")
    store.append_event(event_from_birth_row({"mint": "mint-live-health", "received_at": 100.0}))
    store.flush()
    with (tmp_path / "lifecycle_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "quote_observed", "mint": "phantom", "observed_at": 999.0}) + "\n")

    health = store.live_health()
    rows = _rows(tmp_path / "lifecycle_events.jsonl")

    assert health["persistent_lifecycle_health_mode"] == "live_nonblocking"
    assert health["persistent_lifecycle_store_status"] == "available"
    assert health["persistent_lifecycle_event_count"] == 1
    assert len(rows) == 2
    assert rows[-1]["mint"] == "phantom"
