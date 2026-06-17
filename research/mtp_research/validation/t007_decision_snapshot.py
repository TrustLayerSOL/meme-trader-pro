"""Read-only decision-time snapshot builder for future live-trading readiness.

The builder intentionally contains no wallet, signing, order, or transaction-send
path. It only reconstructs what was known at a cutoff time from canonical events.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Any

FORBIDDEN_EXECUTION_INTENT_FIELDS = {
    "wallet",
    "private_key",
    "secret_key",
    "signer",
    "send_transaction",
    "order_id",
    "buy_amount",
    "sell_amount",
    "trade_intent",
}

@dataclass(frozen=True)
class DecisionSnapshot:
    mint: str
    cutoff_time: float
    features: dict[str, Any]
    event_count: int
    decision_time_safe: bool
    blocked_reasons: list[str]


def _scrub_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in FORBIDDEN_EXECUTION_INTENT_FIELDS}


def build_decision_snapshot(db_path: str | Path, *, mint: str, cutoff_time: float) -> DecisionSnapshot:
    features: dict[str, Any] = {}
    blocked: list[str] = []
    rows: list[tuple[str, str, float | None]] = []
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            SELECT event_type, payload_json, feature_observed_at
            FROM domain_events
            WHERE mint = ?
              AND replay_source = 0
              AND event_type NOT LIKE 'replay_%'
              AND (feature_observed_at IS NULL OR feature_observed_at <= ?)
            ORDER BY feature_observed_at, inserted_at
            """,
            (mint, cutoff_time),
        )
        rows = list(cursor)
    for event_type, payload_json, observed_at in rows:
        if event_type == "birth_backfilled_from_replay":
            continue
        payload = _scrub_feature_payload(json.loads(payload_json))
        if observed_at is not None and observed_at > cutoff_time:
            blocked.append("future_observation_excluded")
            continue
        if event_type in {"pump_birth_verified", "curve_account_verified", "curve_state_decoded", "trade_flow_window_updated", "holder_dev_snapshot_seen", "progress_threshold_crossed", "pumpswap_pool_verified", "post_migration_depth_seen", "quote_observation_seen"}:
            features[event_type] = payload
    missing = [
        name
        for name in ("pump_birth_verified", "curve_state_decoded", "trade_flow_window_updated", "pumpswap_pool_verified")
        if name not in features
    ]
    blocked.extend(f"missing:{name}" for name in missing)
    return DecisionSnapshot(
        mint=mint,
        cutoff_time=cutoff_time,
        features=features,
        event_count=len(rows),
        decision_time_safe=not missing,
        blocked_reasons=blocked,
    )

# --- T007_DECISION_SNAPSHOT_HASHING_V4 --------------------------------------
import hashlib as _t007_hashlib
from datetime import datetime as _t007_datetime, timezone as _t007_timezone

_original_build_decision_snapshot_v4 = build_decision_snapshot

def _t007_snapshot_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)
    return _t007_hashlib.sha256(payload.encode('utf-8')).hexdigest()

def build_hashed_decision_snapshot(db_path, *, mint, cutoff_time, cutoff_slot=None, commitment_floor='processed'):
    snapshot = _original_build_decision_snapshot_v4(db_path, mint=mint, cutoff_time=cutoff_time)
    event_ids_hash = _t007_snapshot_hash({'mint': mint, 'cutoff_time': cutoff_time, 'features': sorted(snapshot.features.keys()), 'event_count': snapshot.event_count})
    payload = {
        'mint': snapshot.mint,
        'cutoff_time': snapshot.cutoff_time,
        'cutoff_slot': cutoff_slot,
        'commitment_floor': commitment_floor,
        'snapshot_schema_version': 1,
        'features': snapshot.features,
        'event_count': snapshot.event_count,
        'decision_time_safe': snapshot.decision_time_safe,
        'blocked_reasons': snapshot.blocked_reasons,
    }
    snapshot_payload_hash = _t007_snapshot_hash(payload)
    snapshot_id = _t007_snapshot_hash({'mint': mint, 'cutoff_time': cutoff_time, 'cutoff_slot': cutoff_slot, 'commitment_floor': commitment_floor, 'payload_hash': snapshot_payload_hash})
    payload.update({
        'snapshot_id': snapshot_id,
        'input_event_count': snapshot.event_count,
        'input_event_ids_hash': event_ids_hash,
        'snapshot_payload_hash': snapshot_payload_hash,
        'created_at': _t007_datetime.now(_t007_timezone.utc).isoformat(),
    })
    return payload

def persist_hashed_decision_snapshot(db_path, *, mint, cutoff_time, cutoff_slot=None, commitment_floor='processed'):
    payload = build_hashed_decision_snapshot(db_path, mint=mint, cutoff_time=cutoff_time, cutoff_slot=cutoff_slot, commitment_floor=commitment_floor)
    with sqlite3.connect(db_path) as connection:
        from .t007_event_store import T007EventStore
        T007EventStore.initialize_schema(connection)
        connection.execute(
            "INSERT OR IGNORE INTO decision_snapshots (snapshot_id, mint, cutoff_time, cutoff_slot, commitment_floor, snapshot_schema_version, input_event_count, input_event_ids_hash, snapshot_payload_hash, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payload['snapshot_id'], mint, cutoff_time, cutoff_slot, commitment_floor, payload['snapshot_schema_version'], payload['input_event_count'], payload['input_event_ids_hash'], payload['snapshot_payload_hash'], json.dumps(payload, sort_keys=True, default=str), payload['created_at']),
        )
        connection.commit()
    return payload
