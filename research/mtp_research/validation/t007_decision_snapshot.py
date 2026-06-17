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
