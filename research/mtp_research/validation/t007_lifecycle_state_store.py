"""SQLite-backed current-state store for T007 persistent lifecycle data.

Production model: all SQLite writes are serialized through one dedicated writer
thread. Collector callbacks may arrive from multiple source/probe threads, but
none of those producer threads touches the SQLite connection directly.
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from research.mtp_research.validation.t007_lifecycle_reducer import apply_event, empty_state


_STOP = object()


class T007LifecycleStateStore:
    def __init__(self, db_path: Path | str, *, ledger_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path = Path(ledger_path) if ledger_path is not None else self.db_path.with_name("lifecycle_events.jsonl")
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[Mapping[str, Any] | object] = queue.Queue()
        self._ready = threading.Event()
        self._closed = False
        self._init_error: BaseException | None = None
        self._error_count = 0
        self._last_error = ""
        self._status_lock = threading.Lock()
        self._writer = threading.Thread(target=self._writer_loop, name="t007-lifecycle-sqlite-writer", daemon=True)
        self._writer.start()
        if not self._ready.wait(timeout=10.0):
            raise TimeoutError("T007 lifecycle SQLite writer did not initialize within 10s")
        if self._init_error is not None:
            raise RuntimeError(f"T007 lifecycle SQLite writer failed to initialize: {self._init_error}") from self._init_error

    def append_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        mint = str(payload.get("mint") or "")
        if not mint:
            return {}
        if self._closed:
            raise RuntimeError("T007 lifecycle state store is closed")
        self._queue.put(payload)
        return {}

    def flush(self) -> None:
        if self._init_error is not None:
            raise RuntimeError(f"T007 lifecycle SQLite writer failed to initialize: {self._init_error}") from self._init_error
        self._queue.join()
        self.export_event_ledger()

    def export_event_ledger(self) -> int:
        tmp_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".tmp")
        count = 0
        with self._reader_connection() as connection, tmp_path.open("w", encoding="utf-8") as handle:
            rows = connection.execute("SELECT event_json FROM lifecycle_events ORDER BY id").fetchall()
            for row in rows:
                handle.write(str(row["event_json"]) + "\n")
                count += 1
        tmp_path.replace(self.ledger_path)
        return count

    def get_mint_state(self, mint: str) -> dict[str, Any]:
        self.flush()
        with self._reader_connection() as connection:
            row = connection.execute("SELECT state_json FROM mint_lifecycle_state WHERE mint = ?", (str(mint),)).fetchone()
        if row is None:
            return {}
        return _decode_state(row["state_json"])

    def all_states(self) -> list[dict[str, Any]]:
        self.flush()
        with self._reader_connection() as connection:
            rows = connection.execute("SELECT state_json FROM mint_lifecycle_state ORDER BY mint").fetchall()
        return [_decode_state(row["state_json"]) for row in rows]

    def event_count(self) -> int:
        self.flush()
        return self._db_counts()["event_count"]

    def health(self) -> dict[str, Any]:
        self.flush()
        counts = self._db_counts()
        with self._status_lock:
            error_count = self._error_count
            last_error = self._last_error
        ledger_line_count = _line_count(self.ledger_path)
        return {
            "persistent_lifecycle_store_status": "error" if error_count else "available",
            "persistent_lifecycle_health_mode": "full_flush_export",
            "persistent_lifecycle_db_path": str(self.db_path),
            "persistent_lifecycle_ledger_path": str(self.ledger_path),
            "persistent_lifecycle_event_count": counts["event_count"],
            "persistent_lifecycle_state_count": counts["state_count"],
            "persistent_lifecycle_ledger_line_count": ledger_line_count,
            "persistent_lifecycle_ledger_db_consistent": ledger_line_count == counts["event_count"],
            "persistent_lifecycle_error_count": error_count,
            "persistent_lifecycle_last_error": last_error,
            "persistent_lifecycle_queue_depth": self._queue.qsize(),
            "persistent_lifecycle_writer_alive": self._writer.is_alive(),
            "persistent_lifecycle_writer_model": "single_writer_thread",
        }

    def live_health(self) -> dict[str, Any]:
        counts = self._db_counts()
        with self._status_lock:
            error_count = self._error_count
            last_error = self._last_error
        return {
            "persistent_lifecycle_store_status": "error" if error_count else "available",
            "persistent_lifecycle_health_mode": "live_nonblocking",
            "persistent_lifecycle_db_path": str(self.db_path),
            "persistent_lifecycle_ledger_path": str(self.ledger_path),
            "persistent_lifecycle_event_count": counts["event_count"],
            "persistent_lifecycle_state_count": counts["state_count"],
            "persistent_lifecycle_ledger_line_count": _line_count(self.ledger_path),
            "persistent_lifecycle_ledger_db_consistent": None,
            "persistent_lifecycle_error_count": error_count,
            "persistent_lifecycle_last_error": last_error,
            "persistent_lifecycle_queue_depth": self._queue.qsize(),
            "persistent_lifecycle_writer_alive": self._writer.is_alive(),
            "persistent_lifecycle_writer_model": "single_writer_thread",
        }

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        self._queue.put(_STOP)
        self._queue.join()
        self._writer.join(timeout=10.0)

    def _writer_loop(self) -> None:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(self.db_path))
            connection.row_factory = sqlite3.Row
            self._initialize(connection)
        except BaseException as exc:
            self._init_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is _STOP:
                        return
                    self._append_event_on_connection(connection, item)  # type: ignore[arg-type]
                except BaseException as exc:
                    self._record_error(exc)
                finally:
                    self._queue.task_done()
        finally:
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS mint_lifecycle_state (mint TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_events (id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT NOT NULL, event_type TEXT NOT NULL, observed_at REAL, event_json TEXT NOT NULL, inserted_at REAL NOT NULL)"
        )
        for table in (
            "curve_observations",
            "threshold_crossings",
            "migration_events",
            "post_migration_observations",
            "feature_snapshots",
            "readiness_snapshots",
        ):
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT NOT NULL, observed_at REAL, row_json TEXT NOT NULL)"
            )
        connection.commit()

    def _append_event_on_connection(self, connection: sqlite3.Connection, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        mint = str(payload.get("mint") or "")
        if not mint:
            return {}
        observed_at = _float(payload.get("observed_at"))
        event_type = str(payload.get("event_type") or "unknown")
        current = self._get_mint_state_on_connection(connection, mint) or empty_state(mint)
        updated = apply_event(current, payload)
        encoded_event = json.dumps(payload, sort_keys=True, default=str)
        encoded_state = json.dumps(updated, sort_keys=True, default=str)
        now = time.time()
        with connection:
            connection.execute(
                "INSERT INTO lifecycle_events (mint, event_type, observed_at, event_json, inserted_at) VALUES (?, ?, ?, ?, ?)",
                (mint, event_type, observed_at, encoded_event, now),
            )
            connection.execute(
                "INSERT INTO mint_lifecycle_state (mint, state_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(mint) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
                (mint, encoded_state, now),
            )
            self._mirror_event_table(connection, mint, observed_at, payload)
        return updated

    def _get_mint_state_on_connection(self, connection: sqlite3.Connection, mint: str) -> dict[str, Any]:
        row = connection.execute("SELECT state_json FROM mint_lifecycle_state WHERE mint = ?", (str(mint),)).fetchone()
        if row is None:
            return {}
        return _decode_state(row["state_json"])

    def _mirror_event_table(
        self,
        connection: sqlite3.Connection,
        mint: str,
        observed_at: float | None,
        payload: Mapping[str, Any],
    ) -> None:
        event_type = str(payload.get("event_type") or "")
        table = {
            "curve_observed": "curve_observations",
            "threshold_crossed": "threshold_crossings",
            "migration_seen": "migration_events",
            "post_migration_observed": "post_migration_observations",
            "quote_observed": "feature_snapshots",
            "trade_flow_observed": "feature_snapshots",
            "holder_dev_observed": "feature_snapshots",
        }.get(event_type)
        if not table:
            return
        connection.execute(
            f"INSERT INTO {table} (mint, observed_at, row_json) VALUES (?, ?, ?)",
            (mint, observed_at, json.dumps(dict(payload), sort_keys=True, default=str)),
        )

    def _reader_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _db_counts(self) -> dict[str, int]:
        with self._reader_connection() as connection:
            event_row = connection.execute("SELECT COUNT(*) AS count FROM lifecycle_events").fetchone()
            state_row = connection.execute("SELECT COUNT(*) AS count FROM mint_lifecycle_state").fetchone()
        return {
            "event_count": int(event_row["count"] if event_row is not None else 0),
            "state_count": int(state_row["count"] if state_row is not None else 0),
        }

    def _record_error(self, exc: BaseException) -> None:
        with self._status_lock:
            self._error_count += 1
            self._last_error = f"{type(exc).__name__}: {exc}"


def _decode_state(payload: str) -> dict[str, Any]:
    row = json.loads(payload)
    for key, value in list(row.items()):
        if key.endswith("_seen") or key.endswith("_available") or key.endswith("_ready") or key in {
            "birth_seen",
            "birth_seen_live",
            "birth_backfilled_from_replay",
            "admitted",
            "curve_account_verified",
            "progress_tracking",
            "progress_decoded",
            "market_cap_confirmed",
            "threshold_crossed",
            "migration_seen",
            "replay_birth_found",
            "replay_unresolved",
            "preexisting_before_watcher",
            "true_source_miss",
        }:
            row[key] = bool(value)
    return row


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# --- T007_PRODUCTION_STATE_STORE_WRAPPERS_V2 --------------------------------
# Compatibility bridge: legacy lifecycle tables continue to be written, but the
# same events are mirrored into the canonical event-store tables in the same DB.
try:
    from .t007_event_store import T007EventStore as _T007ProductionEventStore
    from .t007_lifecycle_events import canonical_event_type as _t007_canonical_event_type
    from .t007_lifecycle_events import event_is_decision_time_safe as _t007_event_is_decision_time_safe
except Exception:  # pragma: no cover - import safety for partial tooling
    _T007ProductionEventStore = None
    _t007_canonical_event_type = None
    _t007_event_is_decision_time_safe = None

def _float(value):  # type: ignore[no-redef]
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _t007_production_payload(payload):
    row = dict(payload or {})
    event_type = row.get("event_type")
    if _t007_canonical_event_type is not None:
        row["event_type"] = _t007_canonical_event_type(event_type)
    if _t007_event_is_decision_time_safe is not None:
        row["decision_time_safe"] = _t007_event_is_decision_time_safe(event_type, row)
    row.setdefault("live_source", not bool(row.get("replay_source")))
    return row

if _T007ProductionEventStore is not None and 'T007LifecycleStateStore' in globals():
    _t007_original_initialize = T007LifecycleStateStore._initialize
    _t007_original_append_event_on_connection = T007LifecycleStateStore._append_event_on_connection
    _t007_original_health_summary = getattr(T007LifecycleStateStore, 'health_summary', None)

    def _t007_production_initialize(self):
        _t007_original_initialize(self)
        with self._connection() as connection:
            _T007ProductionEventStore.initialize_schema(connection)

    def _t007_production_append_event_on_connection(self, connection, payload):
        result = _t007_original_append_event_on_connection(self, connection, payload)
        _T007ProductionEventStore.insert_domain_event_on_connection(connection, _t007_production_payload(payload))
        return result

    def _t007_production_health_summary(self):
        base = _t007_original_health_summary(self) if _t007_original_health_summary is not None else {}
        try:
            with self._connection() as connection:
                _T007ProductionEventStore.initialize_schema(connection)
                domain_events = int(connection.execute("SELECT COUNT(*) FROM domain_events").fetchone()[0])
                raw_envelopes = int(connection.execute("SELECT COUNT(*) FROM raw_source_envelopes").fetchone()[0])
                legacy_events = int(connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0])
            base.update({
                "t007_event_store_schema_version": 2,
                "t007_domain_events": domain_events,
                "t007_raw_source_envelopes": raw_envelopes,
                "db_ledger_consistent": domain_events >= legacy_events,
                "db_writer_alive": True,
            })
        except Exception as exc:
            base.update({
                "t007_event_store_schema_version": 2,
                "db_ledger_consistent": False,
                "db_writer_alive": False,
                "db_health_error": str(exc),
            })
        return base

    T007LifecycleStateStore._initialize = _t007_production_initialize
    T007LifecycleStateStore._append_event_on_connection = _t007_production_append_event_on_connection
    T007LifecycleStateStore.health_summary = _t007_production_health_summary
