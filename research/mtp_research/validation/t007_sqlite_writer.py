"""Single-owner SQLite writer for T007 proof runs.

This is the canonical write path. It owns one sqlite3 write connection and is the
only component that should execute INSERT/UPDATE/DELETE against the proof DB.
JSONL/CSV artifacts are allowed only after this writer commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
from typing import Any, Mapping

from .t007_event_store import T007EventStore
from .t007_protocol_codecs import (
    PUMP_BONDING_CURVE_ACCOUNT_LEN,
    PUMP_BONDING_CURVE_DISCRIMINATOR,
    PUMP_PROGRAM_ID,
    PUMPSWAP_POOL_ACCOUNT_LEN,
    PUMPSWAP_POOL_DISCRIMINATOR,
    PUMPSWAP_PROGRAM_ID,
    SOL_MINT,
    USDC_MINT,
)

FATAL_SQLITE_MARKERS = (
    "database disk image is malformed",
    "disk i/o error",
    "file is not a database",
    "database corruption",
    "malformed",
)

class T007DbFatalError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json_dumps(value).encode("utf-8")).hexdigest()


def default_internal_run_root(run_id: str) -> Path:
    return Path.home() / "Library" / "Application Support" / "MemeTraderPro" / "runs" / str(run_id)

@dataclass(frozen=True)
class CommittedArtifactRow:
    raw_envelope_id: str
    domain_event_id: str | None
    db_path: str
    committed_at: str
    commit_sequence: int


class T007SqliteWriter:
    def __init__(self, artifact_root: str | Path, *, run_id: str | None = None, use_internal_db: bool = True) -> None:
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or self.artifact_root.name
        self.db_root = default_internal_run_root(self.run_id) if use_internal_db else self.artifact_root
        self.db_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_root / "t007_lifecycle_state.sqlite"
        self.pointer_path = self.artifact_root / "canonical_sqlite_db_pointer.json"
        self.connection: sqlite3.Connection | None = None
        self.started = False
        self.alive = False
        self.fatal = False
        self.error_count = 0
        self.last_error_class: str | None = None
        self.last_error_message: str | None = None
        self.last_successful_commit_at: str | None = None
        self.last_successful_commit_sequence = 0
        self.pending_queue_depth = 0
        self.oldest_pending_event_age_ms: float | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self.started:
                return
            self.connection = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None, check_same_thread=True)
            self._configure(self.connection)
            T007EventStore.initialize_schema(self.connection)
            self._install_extra_schema(self.connection)
            self.alive = True
            self.started = True
            self._write_pointer()
            self.quick_check_or_raise()

    def _configure(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA wal_autocheckpoint=1000")

    def _install_extra_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS run_consistency_checks (
              check_id TEXT PRIMARY KEY,
              collector_run_id TEXT NOT NULL,
              check_name TEXT NOT NULL,
              expected_count INTEGER,
              observed_count INTEGER,
              status TEXT NOT NULL,
              details_json TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS latency_histograms (
              collector_run_id TEXT NOT NULL,
              lane TEXT NOT NULL,
              event_type TEXT NOT NULL,
              metric_name TEXT NOT NULL,
              count INTEGER NOT NULL,
              p50_ms REAL,
              p95_ms REAL,
              p99_ms REAL,
              max_ms REAL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (collector_run_id, lane, event_type, metric_name)
            )
            """
        )
        connection.commit()

    def _write_pointer(self) -> None:
        payload = {
            "run_id": self.run_id,
            "canonical_db_path": str(self.db_path),
            "artifact_root": str(self.artifact_root),
            "storage_policy": "canonical_sqlite_internal_local_disk_artifacts_external_allowed_after_commit",
            "created_at": utc_now(),
        }
        self.pointer_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _connection(self) -> sqlite3.Connection:
        self.start()
        if self.connection is None:
            raise T007DbFatalError("canonical sqlite writer is not initialized")
        if self.fatal or not self.alive:
            raise T007DbFatalError(self.last_error_message or "canonical sqlite writer is not alive")
        return self.connection

    def _handle_error(self, exc: BaseException) -> None:
        message = str(exc)
        self.error_count += 1
        self.last_error_class = type(exc).__name__
        self.last_error_message = message
        fatal = isinstance(exc, sqlite3.DatabaseError) and any(marker in message.lower() for marker in FATAL_SQLITE_MARKERS)
        if fatal:
            self.fatal = True
            self.alive = False
        if fatal:
            self._write_emergency_status()
            raise T007DbFatalError(message) from exc

    def _write_emergency_status(self) -> None:
        payload = self.health_payload()
        payload["status"] = "T007_DB_FATAL"
        payload["created_at"] = utc_now()
        emergency = self.artifact_root / "t007_db_fatal_status.json"
        emergency.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    def quick_check_or_raise(self) -> str:
        connection = self._connection() if self.started else self.connection
        if connection is None:
            return "not_started"
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            status = row[0] if row else "missing"
            if status != "ok":
                raise sqlite3.DatabaseError(f"PRAGMA quick_check failed: {status}")
            return status
        except BaseException as exc:
            self._handle_error(exc)
            raise

    def integrity_check(self) -> str:
        connection = self._connection()
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return row[0] if row else "missing"
        except BaseException as exc:
            self._handle_error(exc)
            raise

    def wal_checkpoint(self) -> str:
        connection = self._connection()
        try:
            rows = list(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)"))
            return json_dumps(rows)
        except BaseException as exc:
            self._handle_error(exc)
            raise

    def bootstrap_run(self, manifest: Mapping[str, Any] | None = None) -> None:
        payload = dict(manifest or {})
        payload.setdefault("collector_run_id", self.run_id)
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("schema_version", "t007_canonical_sqlite_v1")
        payload.setdefault("db_path", str(self.db_path))
        payload.setdefault("artifact_root", str(self.artifact_root))
        payload.setdefault("status", "starting")
        payload.setdefault("created_at", utc_now())
        payload.setdefault("updated_at", payload["created_at"])
        payload.setdefault("pid", os.getpid())
        payload_hash = sha256_json(payload)
        connection = self._connection()
        self._execute_transaction([
            ("run_manifest", {**payload, "manifest_hash": payload_hash}),
            ("layout_registered", self._pump_curve_layout()),
            ("layout_registered", self._pumpswap_pool_layout()),
        ])

    def mark_running(self, payload: Mapping[str, Any] | None = None) -> None:
        row = dict(payload or {})
        now = utc_now()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE run_manifest SET status = 'running', source_started_at = COALESCE(source_started_at, ?), updated_at = ? WHERE collector_run_id = ?",
                (row.get("source_started_at") or now, now, row.get("collector_run_id") or self.run_id),
            )
            connection.execute("COMMIT")
        except BaseException as exc:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            self._handle_error(exc)
            raise

    def finalize_run(self, payload: Mapping[str, Any] | None = None) -> None:
        row = dict(payload or {})
        now = utc_now()
        connection = self._connection()
        status = row.get("status") or row.get("final_status") or "finalized"
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE run_manifest
                SET status = ?, source_finished_at = COALESCE(?, source_finished_at), actual_source_duration_seconds = COALESCE(?, actual_source_duration_seconds),
                    source_duration_quality = COALESCE(?, source_duration_quality), final_decision_label = COALESCE(?, final_decision_label),
                    blockers_json = COALESCE(?, blockers_json), updated_at = ?
                WHERE collector_run_id = ?
                """,
                (
                    status,
                    row.get("source_finished_at") or now,
                    row.get("actual_source_duration_seconds"),
                    row.get("source_duration_quality"),
                    row.get("final_decision_label"),
                    json_dumps(row.get("blockers")) if row.get("blockers") is not None else None,
                    now,
                    row.get("collector_run_id") or self.run_id,
                ),
            )
            connection.execute("COMMIT")
        except BaseException as exc:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            self._handle_error(exc)
            raise

    def record_artifact_row(self, raw: Mapping[str, Any], domain_event: Mapping[str, Any] | None) -> CommittedArtifactRow:
        raw_payload = dict(raw)
        domain_payload = dict(domain_event) if domain_event is not None else None
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            raw_id = T007EventStore.insert_raw_envelope_on_connection(connection, raw_payload)
            event_id = None
            if domain_payload is not None:
                event_id = T007EventStore.insert_domain_event_on_connection(connection, domain_payload)
                self._materialize_side_tables(connection, domain_payload, event_id)
            connection.execute("COMMIT")
            self.last_successful_commit_sequence += 1
            self.last_successful_commit_at = utc_now()
            return CommittedArtifactRow(raw_id, event_id, str(self.db_path), self.last_successful_commit_at, self.last_successful_commit_sequence)
        except BaseException as exc:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            self._handle_error(exc)
            raise

    def _execute_transaction(self, items: list[tuple[str, Mapping[str, Any]]]) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for kind, payload in items:
                if kind == "run_manifest":
                    self._insert_run_manifest(connection, payload)
                elif kind == "layout_registered":
                    self._insert_layout(connection, payload)
                elif kind == "consistency_check":
                    self._insert_consistency_check(connection, payload)
            connection.execute("COMMIT")
            self.last_successful_commit_sequence += 1
            self.last_successful_commit_at = utc_now()
        except BaseException as exc:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            self._handle_error(exc)
            raise

    def _insert_run_manifest(self, connection: sqlite3.Connection, payload: Mapping[str, Any]) -> None:
        row = dict(payload)
        row.setdefault("manifest_hash", sha256_json(row))
        row.setdefault("inserted_at", utc_now())
        connection.execute(
            """
            INSERT OR REPLACE INTO run_manifest
            (collector_run_id, manifest_hash, git_sha, schema_version, codec_version, parser_git_sha, program_ids_json, quote_mints_json,
             helius_endpoint, provider_region, commitment_config, subscription_config_hash, rate_limit_config_json, campaign_start_time,
             campaign_end_time, machine_id, started_at, stopped_at, stop_reason, payload_json, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("collector_run_id") or row.get("run_id") or self.run_id,
                row.get("manifest_hash"),
                row.get("git_sha") or row.get("code_git_sha"),
                str(row.get("schema_version") or "t007_canonical_sqlite_v1"),
                row.get("codec_version") or "t007_protocol_codecs_v1",
                row.get("parser_git_sha"),
                json_dumps(row.get("program_ids") or {"pump_fun": PUMP_PROGRAM_ID, "pumpswap": PUMPSWAP_PROGRAM_ID}),
                json_dumps(row.get("quote_mints") or {"SOL": SOL_MINT, "USDC": USDC_MINT}),
                row.get("helius_endpoint") or row.get("helius_endpoint_label"),
                row.get("provider_region"),
                row.get("commitment_config") or row.get("commitment") or "processed",
                row.get("subscription_config_hash") or sha256_json(row.get("subscription_config") or {}),
                json_dumps(row.get("rate_limit_config") or {}),
                row.get("campaign_start_time"),
                row.get("campaign_end_time"),
                row.get("machine_id") or os.uname().nodename,
                row.get("started_at") or row.get("source_start_requested_at") or utc_now(),
                row.get("stopped_at"),
                row.get("stop_reason"),
                json_dumps(row),
                row.get("inserted_at"),
            ),
        )

    def _insert_layout(self, connection: sqlite3.Connection, payload: Mapping[str, Any]) -> None:
        row = dict(payload)
        row.setdefault("layout_id", sha256_json({"protocol": row.get("protocol"), "account_kind": row.get("account_kind"), "account_length": row.get("account_length"), "discriminator": row.get("discriminator")}))
        row.setdefault("inserted_at", utc_now())
        row.setdefault("decode_confidence", "registered")
        connection.execute(
            """
            INSERT OR REPLACE INTO protocol_layout_versions
            (layout_id, protocol, program_id, account_kind, discriminator, account_length, codec_version, first_seen_slot, last_validated_slot,
             validation_fixture_signature, parser_git_sha, decode_confidence, payload_json, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("layout_id"), row.get("protocol"), row.get("program_id"), row.get("account_kind"), row.get("discriminator"), row.get("account_length"),
                row.get("codec_version") or "t007_protocol_codecs_v1", row.get("first_seen_slot"), row.get("last_validated_slot"), row.get("validation_fixture_signature"),
                row.get("parser_git_sha"), row.get("decode_confidence"), json_dumps(row), row.get("inserted_at"),
            ),
        )

    def _insert_consistency_check(self, connection: sqlite3.Connection, payload: Mapping[str, Any]) -> None:
        row = dict(payload)
        row.setdefault("collector_run_id", self.run_id)
        row.setdefault("created_at", utc_now())
        row.setdefault("check_id", sha256_json(row))
        connection.execute(
            "INSERT OR REPLACE INTO run_consistency_checks (check_id, collector_run_id, check_name, expected_count, observed_count, status, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row.get("check_id"), row.get("collector_run_id"), row.get("check_name"), row.get("expected_count"), row.get("observed_count"), row.get("status"), json_dumps(row.get("details") or row), row.get("created_at")),
        )

    def _materialize_side_tables(self, connection: sqlite3.Connection, event: Mapping[str, Any], event_id: str) -> None:
        event_type = str(event.get("event_type") or "")
        if event_type == "pumpswap_pool_seen" and (event.get("pool_address") or event.get("pool_or_pair_address")):
            pool_event = dict(event)
            pool_event["event_type"] = "pumpswap_pool_verified" if event.get("quote_asset") or event.get("quote_mint") else "pumpswap_pool_seen"
            T007EventStore._upsert_identity_from_event(connection, pool_event)
        if event_type == "curve_state_decoded":
            connection.execute("UPDATE mint_identity SET curve_verified = 1, progress_decoded = 1, updated_at = ? WHERE mint = ?", (utc_now(), event.get("mint")))

    def _pump_curve_layout(self) -> dict[str, Any]:
        return {
            "protocol": "pump_fun",
            "program_id": PUMP_PROGRAM_ID,
            "account_kind": "bonding_curve",
            "discriminator": PUMP_BONDING_CURVE_DISCRIMINATOR.hex(),
            "account_length": PUMP_BONDING_CURVE_ACCOUNT_LEN,
            "codec_version": "t007_protocol_codecs_v1",
            "decode_confidence": "registered",
        }

    def _pumpswap_pool_layout(self) -> dict[str, Any]:
        return {
            "protocol": "pumpswap",
            "program_id": PUMPSWAP_PROGRAM_ID,
            "account_kind": "pool",
            "discriminator": PUMPSWAP_POOL_DISCRIMINATOR.hex(),
            "account_length": PUMPSWAP_POOL_ACCOUNT_LEN,
            "codec_version": "t007_protocol_codecs_v1",
            "decode_confidence": "registered",
        }

    def counts(self) -> dict[str, int]:
        connection = self._connection()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out: dict[str, int] = {}
        for table in (
            "raw_source_envelopes",
            "domain_events",
            "mint_identity",
            "pool_identity",
            "run_manifest",
            "protocol_layout_versions",
            "lifecycle_invariant_violations",
            "run_consistency_checks",
            "latency_histograms",
        ):
            if table in tables:
                out[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return out

    def add_consistency_check(self, check_name: str, *, expected_count: int | None, observed_count: int | None, status: str, details: Mapping[str, Any] | None = None) -> None:
        self._execute_transaction([("consistency_check", {"check_name": check_name, "expected_count": expected_count, "observed_count": observed_count, "status": status, "details": dict(details or {})})])

    def health_payload(self) -> dict[str, Any]:
        counts = {}
        try:
            counts = self.counts() if self.started and self.alive and not self.fatal else {}
        except Exception:
            counts = {}
        return {
            "db_writer_alive": self.alive and not self.fatal,
            "db_writer_error_count": self.error_count,
            "db_last_error_class": self.last_error_class,
            "db_last_error_message": self.last_error_message,
            "db_last_successful_commit_at": self.last_successful_commit_at,
            "db_last_successful_commit_sequence": self.last_successful_commit_sequence,
            "db_pending_queue_depth": self.pending_queue_depth,
            "db_oldest_pending_event_age_ms": self.oldest_pending_event_age_ms,
            "canonical_db_path": str(self.db_path),
            "canonical_db_pointer_path": str(self.pointer_path),
            "db_fatal": self.fatal,
            **{f"db_{k}_count": v for k, v in counts.items()},
        }

    def close(self) -> None:
        with self._lock:
            if self.connection is not None:
                try:
                    self.wal_checkpoint()
                except Exception:
                    pass
                self.connection.close()
                self.connection = None
            self.alive = False
            self.started = False

# --- T007_CANONICAL_EVENT_NAME_GATE_V2 --------------------------------------
ALLOWED_DOMAIN_EVENTS = {
    'pump_birth_verified',
    'pump_birth_rejected',
    'curve_account_verified',
    'curve_state_decoded',
    'curve_state_decode_failed',
    'curve_account_not_found_retry',
    'curve_account_not_found_final',
    'trade_flow_window_updated',
    'holder_dev_snapshot_seen',
    'progress_threshold_evaluated',
    'progress_threshold_crossed',
    'pumpswap_pool_seen',
    'pumpswap_pool_verified',
    'post_migration_depth_seen',
    'quote_observation_seen',
    'source_gap_detected',
    'source_gap_backfilled',
    'lane_stall_detected',
    'replay_birth_context_seen',
    'replay_context_unresolved',
}
LEGACY_EVENT_NAME_REPLACEMENTS = {
    'curve_observed': 'curve_state_decoded',
    'trade_flow_observed': 'trade_flow_window_updated',
    'holder_dev_observed': 'holder_dev_snapshot_seen',
    'threshold_crossed': 'progress_threshold_crossed',
}

_original_record_artifact_row_gate_v2 = T007SqliteWriter.record_artifact_row

def _record_artifact_row_gate_v2(self, raw, domain_event):
    if domain_event is not None:
        event = dict(domain_event)
        event_type = str(event.get('event_type') or '')
        if event_type in LEGACY_EVENT_NAME_REPLACEMENTS:
            event['event_type'] = LEGACY_EVENT_NAME_REPLACEMENTS[event_type]
            event_type = event['event_type']
        if event_type not in ALLOWED_DOMAIN_EVENTS:
            raise ValueError(f'Non-canonical domain event type: {event_type}')
        domain_event = event
    return _original_record_artifact_row_gate_v2(self, raw, domain_event)

T007SqliteWriter.record_artifact_row = _record_artifact_row_gate_v2

# --- T007_RUN_MANIFEST_SCHEMA_EXTENSIONS_V3 ---------------------------------
def _t007_writer_add_column_v3(connection, table, column, definition):
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

_original_install_extra_schema_v3 = T007SqliteWriter._install_extra_schema

def _install_extra_schema_v3(self, connection):
    _original_install_extra_schema_v3(self, connection)
    for column, definition in (
        ('run_id', 'TEXT'),
        ('db_path', 'TEXT'),
        ('artifact_root', 'TEXT'),
        ('source_start_requested_at', 'TEXT'),
        ('source_started_at', 'TEXT'),
        ('source_finished_at', 'TEXT'),
        ('requested_duration_seconds', 'REAL'),
        ('actual_source_duration_seconds', 'REAL'),
        ('source_duration_quality', 'TEXT'),
        ('helius_endpoint_label', 'TEXT'),
        ('pid', 'INTEGER'),
        ('status', "TEXT NOT NULL DEFAULT 'starting'"),
        ('final_decision_label', 'TEXT'),
        ('blockers_json', 'TEXT'),
        ('updated_at', 'TEXT'),
    ):
        _t007_writer_add_column_v3(connection, 'run_manifest', column, definition)
    connection.commit()

T007SqliteWriter._install_extra_schema = _install_extra_schema_v3

# --- T007_INTERNAL_DB_ROOT_UNIQUE_BY_ARTIFACT_ROOT_V4 -----------------------
_original_t007_sqlite_writer_init_v4 = T007SqliteWriter.__init__

def _t007_sqlite_writer_init_v4(self, artifact_root, *, run_id=None, use_internal_db=True):
    # Keep canonical DB on internal disk, but include an artifact-root hash so
    # repeated test/proof run_ids cannot reuse a stale/corrupt DB from another root.
    root = Path(artifact_root)
    base_run_id = str(run_id or root.name)
    if use_internal_db:
        unique_run_id = f"{base_run_id}_{hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:10]}"
        _original_t007_sqlite_writer_init_v4(self, artifact_root, run_id=unique_run_id, use_internal_db=True)
        self.collector_run_id = base_run_id
    else:
        _original_t007_sqlite_writer_init_v4(self, artifact_root, run_id=base_run_id, use_internal_db=False)
        self.collector_run_id = base_run_id

T007SqliteWriter.__init__ = _t007_sqlite_writer_init_v4
