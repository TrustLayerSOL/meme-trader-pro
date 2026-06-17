"""Canonical SQLite event store for T007 lifecycle collection.

The store is append-only for raw envelopes/domain events and uses identity tables
only as materialized indexes. It is read-only with respect to trading: there are
no wallet, signing, sendTransaction, order, or execution paths here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import queue
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 2


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_id(payload: Mapping[str, Any]) -> str:
    parts = [
        str(payload.get("collector_run_id") or payload.get("run_id") or ""),
        str(payload.get("event_type") or payload.get("canonical_event_type") or ""),
        str(payload.get("mint") or ""),
        str(payload.get("pool_address") or payload.get("pool_or_pair_address") or ""),
        str(payload.get("signature") or payload.get("source_signature") or payload.get("migration_signature") or ""),
        str(payload.get("feature_observed_at") or payload.get("source_received_at") or payload.get("created_at") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class StoreHealth:
    writer_alive: bool
    pending_queue: int
    write_errors: int
    domain_events_written: int
    raw_envelopes_written: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "db_writer_alive": self.writer_alive,
            "db_pending_queue": self.pending_queue,
            "db_write_errors": self.write_errors,
            "db_domain_events_written": self.domain_events_written,
            "db_raw_envelopes_written": self.raw_envelopes_written,
        }


class T007EventStore:
    def __init__(self, db_path: str | Path, *, queue_max_size: int = 20000) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=queue_max_size)
        self._stop = threading.Event()
        self._started = False
        self._lock = threading.Lock()
        self._write_errors = 0
        self._domain_events_written = 0
        self._raw_envelopes_written = 0
        self._thread = threading.Thread(target=self._writer_loop, name="t007-event-store-writer", daemon=True)
        with sqlite3.connect(self.db_path) as connection:
            self.initialize_schema(connection)

    @staticmethod
    def initialize_schema(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('t007_event_store_schema_version', ?)", (str(SCHEMA_VERSION),))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_source_envelopes (
                envelope_id TEXT PRIMARY KEY,
                collector_run_id TEXT,
                lane TEXT NOT NULL,
                source_route TEXT,
                signature TEXT,
                slot INTEGER,
                block_time REAL,
                mint TEXT,
                pool_address TEXT,
                received_at TEXT,
                payload_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_events (
                event_id TEXT PRIMARY KEY,
                collector_run_id TEXT,
                event_type TEXT NOT NULL,
                mint TEXT,
                pool_address TEXT,
                signature TEXT,
                source_route TEXT,
                source_received_at REAL,
                feature_observed_at REAL,
                decision_time_safe INTEGER NOT NULL DEFAULT 0,
                live_source INTEGER NOT NULL DEFAULT 1,
                replay_source INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mint_identity (
                mint TEXT PRIMARY KEY,
                first_seen_run_id TEXT,
                first_seen_at REAL,
                birth_signature TEXT,
                bonding_curve TEXT,
                associated_bonding_curve TEXT,
                creator TEXT,
                quote_asset TEXT,
                quote_mint TEXT,
                curve_verified INTEGER NOT NULL DEFAULT 0,
                progress_decoded INTEGER NOT NULL DEFAULT 0,
                migration_seen INTEGER NOT NULL DEFAULT 0,
                post_migration_seen INTEGER NOT NULL DEFAULT 0,
                quote_seen INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pool_identity (
                pool_address TEXT PRIMARY KEY,
                mint TEXT,
                quote_asset TEXT,
                quote_mint TEXT,
                first_seen_run_id TEXT,
                first_seen_at REAL,
                migration_signature TEXT,
                pool_verified INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_watermarks (
                lane TEXT PRIMARY KEY,
                last_slot INTEGER,
                last_signature TEXT,
                last_message_at REAL,
                status TEXT,
                payload_json TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                collector_run_id TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_mint ON domain_events (mint)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_type ON domain_events (event_type)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_run ON domain_events (collector_run_id)")
        connection.commit()

    @staticmethod
    def insert_raw_envelope_on_connection(connection: sqlite3.Connection, payload: Mapping[str, Any]) -> str:
        envelope = dict(payload)
        envelope_id = str(envelope.get("envelope_id") or _event_id({**envelope, "event_type": "raw_source_envelope"}))
        connection.execute(
            """
            INSERT OR IGNORE INTO raw_source_envelopes
            (envelope_id, collector_run_id, lane, source_route, signature, slot, block_time, mint, pool_address, received_at, payload_json, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope_id,
                envelope.get("collector_run_id") or envelope.get("run_id"),
                str(envelope.get("lane") or envelope.get("source_lane") or "unknown"),
                envelope.get("source_route"),
                envelope.get("signature") or envelope.get("source_signature"),
                envelope.get("slot"),
                _safe_float(envelope.get("block_time")),
                envelope.get("mint"),
                envelope.get("pool_address") or envelope.get("pool_or_pair_address"),
                envelope.get("received_at") or envelope.get("source_received_at"),
                _json(envelope),
                _now(),
            ),
        )
        return envelope_id

    @staticmethod
    def insert_domain_event_on_connection(connection: sqlite3.Connection, payload: Mapping[str, Any]) -> str:
        event = dict(payload)
        event_type = str(event.get("canonical_event_type") or event.get("event_type") or "unknown_event")
        event["event_type"] = event_type
        event_id = str(event.get("event_id") or _event_id(event))
        mint = event.get("mint")
        pool_address = event.get("pool_address") or event.get("pool_or_pair_address")
        signature = event.get("signature") or event.get("source_signature") or event.get("migration_signature")
        source_received_at = _safe_float(event.get("source_received_at") or event.get("received_at"))
        feature_observed_at = _safe_float(event.get("feature_observed_at") or event.get("collector_observed_at") or event.get("created_at"))
        decision_time_safe = 1 if event.get("decision_time_safe") is True or event.get("decision_safe") is True else 0
        replay_source = 1 if event.get("replay_source") is True or event_type.startswith("replay_") else 0
        live_source = 0 if replay_source or event.get("live_source") is False else 1
        connection.execute(
            """
            INSERT OR IGNORE INTO domain_events
            (event_id, collector_run_id, event_type, mint, pool_address, signature, source_route, source_received_at, feature_observed_at, decision_time_safe, live_source, replay_source, payload_json, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.get("collector_run_id") or event.get("run_id"),
                event_type,
                mint,
                pool_address,
                signature,
                event.get("source_route"),
                source_received_at,
                feature_observed_at,
                decision_time_safe,
                live_source,
                replay_source,
                _json(event),
                _now(),
            ),
        )
        T007EventStore._upsert_identity_from_event(connection, event)
        return event_id

    @staticmethod
    def _upsert_identity_from_event(connection: sqlite3.Connection, event: Mapping[str, Any]) -> None:
        mint = event.get("mint")
        event_type = str(event.get("event_type") or event.get("canonical_event_type") or "")
        run_id = event.get("collector_run_id") or event.get("run_id")
        observed_at = _safe_float(event.get("feature_observed_at") or event.get("source_received_at") or event.get("created_at"))
        now = _now()
        if mint:
            existing = connection.execute("SELECT mint FROM mint_identity WHERE mint = ?", (mint,)).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO mint_identity
                    (mint, first_seen_run_id, first_seen_at, birth_signature, bonding_curve, associated_bonding_curve, creator, quote_asset, quote_mint, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mint,
                        run_id,
                        observed_at,
                        event.get("birth_signature") or event.get("signature") or event.get("source_signature"),
                        event.get("bonding_curve") or event.get("bonding_curve_account"),
                        event.get("associated_bonding_curve"),
                        event.get("creator"),
                        event.get("quote_asset"),
                        event.get("quote_mint"),
                        now,
                    ),
                )
            updates: dict[str, Any] = {"updated_at": now}
            if event.get("bonding_curve") or event.get("bonding_curve_account"):
                updates["bonding_curve"] = event.get("bonding_curve") or event.get("bonding_curve_account")
            if event.get("associated_bonding_curve"):
                updates["associated_bonding_curve"] = event.get("associated_bonding_curve")
            if event.get("creator"):
                updates["creator"] = event.get("creator")
            if event.get("quote_asset"):
                updates["quote_asset"] = event.get("quote_asset")
            if event.get("quote_mint"):
                updates["quote_mint"] = event.get("quote_mint")
            if event_type in {"curve_account_verified", "curve_state_decoded"}:
                updates["curve_verified"] = 1
            if event_type == "curve_state_decoded":
                updates["progress_decoded"] = 1
            if event_type in {"pumpswap_pool_seen", "pumpswap_pool_verified", "pump_migrate_seen"}:
                updates["migration_seen"] = 1
            if event_type == "post_migration_depth_seen":
                updates["post_migration_seen"] = 1
            if event_type == "quote_observation_seen":
                updates["quote_seen"] = 1
            assignments = ", ".join(f"{k} = ?" for k in updates)
            connection.execute(f"UPDATE mint_identity SET {assignments} WHERE mint = ?", (*updates.values(), mint))
        pool = event.get("pool_address") or event.get("pool_or_pair_address")
        if pool:
            existing = connection.execute("SELECT pool_address FROM pool_identity WHERE pool_address = ?", (pool,)).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO pool_identity
                    (pool_address, mint, quote_asset, quote_mint, first_seen_run_id, first_seen_at, migration_signature, pool_verified, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pool,
                        mint,
                        event.get("quote_asset"),
                        event.get("quote_mint"),
                        run_id,
                        observed_at,
                        event.get("migration_signature") or event.get("signature") or event.get("source_signature"),
                        1 if event_type == "pumpswap_pool_verified" else 0,
                        now,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE pool_identity
                    SET mint = COALESCE(?, mint), quote_asset = COALESCE(?, quote_asset), quote_mint = COALESCE(?, quote_mint),
                        migration_signature = COALESCE(?, migration_signature),
                        pool_verified = MAX(pool_verified, ?), updated_at = ?
                    WHERE pool_address = ?
                    """,
                    (
                        mint,
                        event.get("quote_asset"),
                        event.get("quote_mint"),
                        event.get("migration_signature") or event.get("signature") or event.get("source_signature"),
                        1 if event_type == "pumpswap_pool_verified" else 0,
                        now,
                        pool,
                    ),
                )

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def insert_raw_envelope(self, payload: Mapping[str, Any]) -> None:
        self.start()
        self.queue.put(("raw", dict(payload)))

    def append_domain_event(self, payload: Mapping[str, Any]) -> None:
        self.start()
        self.queue.put(("event", dict(payload)))

    def update_source_watermark(self, lane: str, payload: Mapping[str, Any]) -> None:
        self.start()
        row = dict(payload)
        row["lane"] = lane
        self.queue.put(("watermark", row))

    def insert_health_snapshot(self, payload: Mapping[str, Any]) -> None:
        self.start()
        self.queue.put(("health", dict(payload)))

    def _writer_loop(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            self.initialize_schema(connection)
            while not self._stop.is_set() or not self.queue.empty():
                try:
                    action, payload = self.queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    if action == "raw":
                        self.insert_raw_envelope_on_connection(connection, payload)
                        with self._lock:
                            self._raw_envelopes_written += 1
                    elif action == "event":
                        self.insert_domain_event_on_connection(connection, payload)
                        with self._lock:
                            self._domain_events_written += 1
                    elif action == "watermark":
                        lane = str(payload.get("lane") or "unknown")
                        connection.execute(
                            """
                            INSERT OR REPLACE INTO source_watermarks
                            (lane, last_slot, last_signature, last_message_at, status, payload_json, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                lane,
                                payload.get("last_slot") or payload.get("slot"),
                                payload.get("last_signature") or payload.get("signature"),
                                _safe_float(payload.get("last_message_at") or payload.get("source_received_at")),
                                payload.get("status"),
                                _json(payload),
                                _now(),
                            ),
                        )
                    elif action == "health":
                        snapshot_id = _event_id({**payload, "event_type": "source_health_snapshot", "created_at": _now()})
                        connection.execute(
                            "INSERT OR IGNORE INTO source_health_snapshots (snapshot_id, collector_run_id, created_at, payload_json) VALUES (?, ?, ?, ?)",
                            (snapshot_id, payload.get("collector_run_id") or payload.get("run_id"), _now(), _json(payload)),
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    with self._lock:
                        self._write_errors += 1
                finally:
                    self.queue.task_done()

    def flush(self) -> None:
        self.queue.join()

    def close(self) -> None:
        self._stop.set()
        if self._started:
            self.flush()
            self._thread.join(timeout=5)

    def counts(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as connection:
            self.initialize_schema(connection)
            return {
                "raw_source_envelopes": int(connection.execute("SELECT COUNT(*) FROM raw_source_envelopes").fetchone()[0]),
                "domain_events": int(connection.execute("SELECT COUNT(*) FROM domain_events").fetchone()[0]),
                "mint_identity": int(connection.execute("SELECT COUNT(*) FROM mint_identity").fetchone()[0]),
                "pool_identity": int(connection.execute("SELECT COUNT(*) FROM pool_identity").fetchone()[0]),
            }

    def export_domain_event_ledger(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection, output.open("w", encoding="utf-8") as handle:
            for (payload_json,) in connection.execute("SELECT payload_json FROM domain_events ORDER BY inserted_at, event_id"):
                handle.write(payload_json + "\n")
        return output

    def health(self) -> StoreHealth:
        with self._lock:
            return StoreHealth(
                writer_alive=(not self._started) or self._thread.is_alive(),
                pending_queue=self.queue.qsize(),
                write_errors=self._write_errors,
                domain_events_written=self._domain_events_written,
                raw_envelopes_written=self._raw_envelopes_written,
            )

# --- T007_EVENT_STORE_PROOF_HARDENING_V4 ------------------------------------
# Schema and PRAGMA hardening for proof-ladder production readiness.
try:
    _t007_v4_original_initialize_schema = T007EventStore.initialize_schema
    _t007_v4_original_insert_raw = T007EventStore.insert_raw_envelope_on_connection
    _t007_v4_original_insert_domain = T007EventStore.insert_domain_event_on_connection
except NameError:  # pragma: no cover
    _t007_v4_original_initialize_schema = None
    _t007_v4_original_insert_raw = None
    _t007_v4_original_insert_domain = None

if _t007_v4_original_initialize_schema is not None:
    def _t007_v4_add_column(connection, table, column, definition):
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _t007_v4_initialize_schema(connection):
        _t007_v4_original_initialize_schema(connection)
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        for table in ("raw_source_envelopes", "domain_events"):
            _t007_v4_add_column(connection, table, "observed_commitment", "TEXT")
            _t007_v4_add_column(connection, table, "first_seen_slot", "INTEGER")
            _t007_v4_add_column(connection, table, "first_seen_at", "REAL")
            _t007_v4_add_column(connection, table, "confirmed_slot", "INTEGER")
            _t007_v4_add_column(connection, table, "confirmed_at", "REAL")
            _t007_v4_add_column(connection, table, "finalized_slot", "INTEGER")
            _t007_v4_add_column(connection, table, "finalized_at", "REAL")
            _t007_v4_add_column(connection, table, "dropped_or_reorged", "INTEGER NOT NULL DEFAULT 0")
            _t007_v4_add_column(connection, table, "payload_hash", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "subscription_id", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "connection_id", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "provider_region", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "commitment", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "last_root_slot", "INTEGER")
        _t007_v4_add_column(connection, "source_watermarks", "missed_slot_start", "INTEGER")
        _t007_v4_add_column(connection, "source_watermarks", "missed_slot_end", "INTEGER")
        _t007_v4_add_column(connection, "source_watermarks", "gap_reason", "TEXT")
        _t007_v4_add_column(connection, "source_watermarks", "gap_repair_status", "TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS run_manifest (
                collector_run_id TEXT PRIMARY KEY,
                manifest_hash TEXT NOT NULL,
                git_sha TEXT,
                schema_version INTEGER,
                codec_version TEXT,
                parser_git_sha TEXT,
                program_ids_json TEXT,
                quote_mints_json TEXT,
                helius_endpoint TEXT,
                provider_region TEXT,
                commitment_config TEXT,
                subscription_config_hash TEXT,
                rate_limit_config_json TEXT,
                campaign_start_time REAL,
                campaign_end_time REAL,
                machine_id TEXT,
                started_at TEXT,
                stopped_at TEXT,
                stop_reason TEXT,
                payload_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS protocol_layout_versions (
                layout_id TEXT PRIMARY KEY,
                protocol TEXT NOT NULL,
                program_id TEXT NOT NULL,
                account_kind TEXT NOT NULL,
                discriminator TEXT,
                account_length INTEGER,
                codec_version TEXT,
                first_seen_slot INTEGER,
                last_validated_slot INTEGER,
                validation_fixture_signature TEXT,
                parser_git_sha TEXT,
                decode_confidence TEXT,
                payload_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lifecycle_invariant_violations (
                violation_id TEXT PRIMARY KEY,
                collector_run_id TEXT,
                mint TEXT,
                event_id TEXT,
                code TEXT NOT NULL,
                severity TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                mint TEXT NOT NULL,
                cutoff_time REAL NOT NULL,
                cutoff_slot INTEGER,
                commitment_floor TEXT,
                snapshot_schema_version INTEGER NOT NULL,
                input_event_count INTEGER NOT NULL,
                input_event_ids_hash TEXT NOT NULL,
                snapshot_payload_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_envelope_idempotency ON raw_source_envelopes (lane, source_route, signature, slot, payload_hash)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_domain_event_idempotency ON domain_events (event_type, mint, pool_address, signature, feature_observed_at, source_route, payload_hash)")
        connection.commit()

    def _t007_v4_payload_hash(payload):
        try:
            return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        except Exception:
            return None

    def _t007_v4_enrich_common(payload):
        row = dict(payload or {})
        commitment = row.get("observed_commitment") or row.get("commitment") or row.get("commitment_level") or "processed"
        row.setdefault("observed_commitment", commitment)
        row.setdefault("first_seen_slot", row.get("slot"))
        row.setdefault("first_seen_at", row.get("source_received_at") or row.get("received_at"))
        row.setdefault("confirmed_slot", row.get("confirmed_slot"))
        row.setdefault("confirmed_at", row.get("confirmed_at"))
        row.setdefault("finalized_slot", row.get("finalized_slot"))
        row.setdefault("finalized_at", row.get("finalized_at"))
        row.setdefault("dropped_or_reorged", 1 if row.get("dropped_or_reorged") is True else 0)
        row.setdefault("payload_hash", _t007_v4_payload_hash(row))
        return row

    def _t007_v4_insert_raw(connection, payload):
        row = _t007_v4_enrich_common(payload)
        envelope_id = _t007_v4_original_insert_raw(connection, row)
        try:
            connection.execute(
                """
                UPDATE raw_source_envelopes
                SET observed_commitment = ?, first_seen_slot = ?, first_seen_at = ?, confirmed_slot = ?, confirmed_at = ?, finalized_slot = ?, finalized_at = ?, dropped_or_reorged = ?, payload_hash = ?
                WHERE envelope_id = ?
                """,
                (
                    row.get("observed_commitment"), row.get("first_seen_slot"), row.get("first_seen_at"), row.get("confirmed_slot"), row.get("confirmed_at"), row.get("finalized_slot"), row.get("finalized_at"), row.get("dropped_or_reorged"), row.get("payload_hash"), envelope_id,
                ),
            )
        except Exception:
            pass
        return envelope_id

    def _t007_v4_insert_domain(connection, payload):
        row = _t007_v4_enrich_common(payload)
        event_id = _t007_v4_original_insert_domain(connection, row)
        try:
            connection.execute(
                """
                UPDATE domain_events
                SET observed_commitment = ?, first_seen_slot = ?, first_seen_at = ?, confirmed_slot = ?, confirmed_at = ?, finalized_slot = ?, finalized_at = ?, dropped_or_reorged = ?, payload_hash = ?
                WHERE event_id = ?
                """,
                (
                    row.get("observed_commitment"), row.get("first_seen_slot"), row.get("first_seen_at"), row.get("confirmed_slot"), row.get("confirmed_at"), row.get("finalized_slot"), row.get("finalized_at"), row.get("dropped_or_reorged"), row.get("payload_hash"), event_id,
                ),
            )
        except Exception:
            pass
        return event_id

    T007EventStore.initialize_schema = staticmethod(_t007_v4_initialize_schema)
    T007EventStore.insert_raw_envelope_on_connection = staticmethod(_t007_v4_insert_raw)
    T007EventStore.insert_domain_event_on_connection = staticmethod(_t007_v4_insert_domain)
