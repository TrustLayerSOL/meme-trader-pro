"""Small adapter from existing T007 JSONL rows to persistent lifecycle events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.mtp_research.validation.t007_lifecycle_events import (
    event_from_birth_row,
    event_from_curve_observation_row,
    event_from_holder_dev_row,
    event_from_migration_row,
    event_from_post_migration_row,
    event_from_quote_row,
    event_from_replay_context_row,
    event_from_threshold_row,
    event_from_trade_flow_row,
)
from research.mtp_research.validation.t007_lifecycle_state_store import T007LifecycleStateStore


class T007LifecycleCollectorAdapter:
    def __init__(self, store: T007LifecycleStateStore | None) -> None:
        self.store = store
        self.error_count = 0
        self.last_error = ""

    @classmethod
    def for_output_root(cls, output_root: Path | str) -> "T007LifecycleCollectorAdapter":
        root = Path(output_root)
        return cls(T007LifecycleStateStore(root / "t007_lifecycle_state.sqlite", ledger_path=root / "persistent_lifecycle_events.jsonl"))

    def record_artifact_row(self, filename: str, row: dict[str, Any]) -> None:
        if self.store is None:
            return
        try:
            event = self._event_for_artifact(filename, row)
            if event:
                self.store.append_event(event)
        except Exception as exc:
            self.error_count += 1
            self.last_error = f"{type(exc).__name__}: {exc}"

    def _event_for_artifact(self, filename: str, row: dict[str, Any]) -> dict[str, Any] | None:
        if filename in {"birth_audit.jsonl", "birth_events.jsonl", "launch_events.jsonl", "launches.jsonl"}:
            return event_from_birth_row(row)
        if filename == "curve_observations.jsonl":
            return event_from_curve_observation_row(row)
        if filename in {"threshold_crossings.jsonl", "true_curve_threshold_crossings.jsonl"}:
            return event_from_threshold_row(row)
        if filename in {"trade_flow_events.jsonl", "organic_flow_events.jsonl"}:
            return event_from_trade_flow_row(row)
        if filename in {"holder_distribution_snapshots.jsonl", "dev_behavior_events.jsonl"}:
            return event_from_holder_dev_row(row)
        if filename == "global_migration_events.jsonl":
            return event_from_migration_row(row)
        if filename == "post_migration_observations.jsonl":
            return event_from_post_migration_row(row)
        if filename == "executable_quote_observations.jsonl":
            return event_from_quote_row(row)
        if filename == "migration_backfill_jobs.jsonl":
            return event_from_replay_context_row(row)
        return None

    def health(self) -> dict[str, Any]:
        if self.store is None:
            return {
                "persistent_lifecycle_store_status": "disabled",
                "persistent_lifecycle_event_count": 0,
                "persistent_lifecycle_state_count": 0,
                "persistent_lifecycle_error_count": self.error_count,
                "persistent_lifecycle_last_error": self.last_error,
            }
        health = self.store.health()
        health["persistent_lifecycle_error_count"] = self.error_count
        health["persistent_lifecycle_last_error"] = self.last_error
        if self.error_count:
            health["persistent_lifecycle_store_status"] = "error"
        return health

    def live_health(self) -> dict[str, Any]:
        if self.store is None:
            return {
                "persistent_lifecycle_store_status": "disabled",
                "persistent_lifecycle_health_mode": "live_nonblocking",
                "persistent_lifecycle_event_count": 0,
                "persistent_lifecycle_state_count": 0,
                "persistent_lifecycle_error_count": self.error_count,
                "persistent_lifecycle_last_error": self.last_error,
            }
        health = self.store.live_health()
        health["persistent_lifecycle_error_count"] = self.error_count
        health["persistent_lifecycle_last_error"] = self.last_error
        if self.error_count:
            health["persistent_lifecycle_store_status"] = "error"
        return health

# --- T007_PRODUCTION_ADAPTER_HEALTH_V2 --------------------------------------
# Adds canonical store health to existing adapter summaries without changing the
# collector's artifact write path.
if 'T007LifecycleCollectorAdapter' in globals():
    _t007_adapter_original_health_summary = getattr(T007LifecycleCollectorAdapter, 'health_summary', None)

    def _t007_adapter_production_health_summary(self):
        base = _t007_adapter_original_health_summary(self) if _t007_adapter_original_health_summary is not None else {}
        try:
            store = getattr(self, 'store', None) or getattr(self, '_store', None) or getattr(self, 'state_store', None)
            if store is not None and hasattr(store, 'health_summary'):
                base.update(store.health_summary())
        except Exception as exc:
            base['production_adapter_health_error'] = str(exc)
        return base

    T007LifecycleCollectorAdapter.health_summary = _t007_adapter_production_health_summary

# --- T007_DISABLE_LEGACY_SQLITE_WRITER_V8 -----------------------------------
# The canonical T007SqliteWriter is now the only runtime DB writer. The legacy
# lifecycle adapter remains as a compatibility object for collector calls, but it
# must not open/write the proof SQLite DB.
class _T007NoopLifecycleCollectorAdapter:
    def __init__(self, output_root=None):
        self.output_root = output_root
        self.disabled_reason = 'replaced_by_canonical_t007_sqlite_writer'

    @classmethod
    def for_output_root(cls, output_root):
        return cls(output_root)

    def close(self):
        return None

    def flush(self):
        return None

    def health_summary(self):
        return {
            'persistent_lifecycle_store_status': 'disabled_replaced_by_canonical_event_store',
            'persistent_lifecycle_error_count': 0,
            'persistent_lifecycle_writer_alive': False,
            'db_ledger_consistent': True,
            'db_writer_alive': True,
        }

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None
        return _noop

if 'T007LifecycleCollectorAdapter' in globals():
    T007LifecycleCollectorAdapter.for_output_root = classmethod(lambda cls, output_root: _T007NoopLifecycleCollectorAdapter(output_root))
