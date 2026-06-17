"""Event model for the T007 persistent lifecycle watcher.

This module is research/data-plane only. It does not trade, paper trade, sign,
or route orders.
"""

from __future__ import annotations

from typing import Any, Mapping

STATE_BIRTH_SEEN = "BIRTH_SEEN"
STATE_CURVE_ACCOUNT_RESOLVED = "CURVE_ACCOUNT_RESOLVED"
STATE_CURVE_ACCOUNT_VERIFIED = "CURVE_ACCOUNT_VERIFIED"
STATE_PROGRESS_TRACKING = "PROGRESS_TRACKING"
STATE_THRESHOLD_CROSSED = "THRESHOLD_CROSSED"
STATE_MIGRATION_SEEN = "MIGRATION_SEEN"
STATE_POST_MIGRATION_POOL_READY = "POST_MIGRATION_POOL_READY"
STATE_QUOTE_READY = "QUOTE_READY"
STATE_FULL_PATH_READY = "FULL_PATH_READY"

STATE_PREEXISTING_BEFORE_WATCHER = "PREEXISTING_BEFORE_WATCHER"
STATE_MIGRATION_ONLY_UNTRACKED = "MIGRATION_ONLY_UNTRACKED"
STATE_REPLAY_UNRESOLVED = "REPLAY_UNRESOLVED"
STATE_TRUE_SOURCE_MISS = "TRUE_SOURCE_MISS"
STATE_CURVE_DECODE_FAILED = "CURVE_DECODE_FAILED"
STATE_CURVE_ACCOUNT_NOT_FOUND = "CURVE_ACCOUNT_NOT_FOUND"

EVENT_BIRTH_SEEN = "birth_seen"
EVENT_CURVE_VERIFIED = "curve_verified"
EVENT_CURVE_OBSERVED = "curve_observed"
EVENT_THRESHOLD_CROSSED = "threshold_crossed"
EVENT_TRADE_FLOW_OBSERVED = "trade_flow_observed"
EVENT_HOLDER_DEV_OBSERVED = "holder_dev_observed"
EVENT_MIGRATION_SEEN = "migration_seen"
EVENT_POST_MIGRATION_OBSERVED = "post_migration_observed"
EVENT_QUOTE_OBSERVED = "quote_observed"
EVENT_REPLAY_BIRTH_CONTEXT = "replay_birth_context"

COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH = "tracked_from_birth_full_path"
COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE = "tracked_from_birth_missing_feature"
COVERAGE_PREEXISTING_BEFORE_WATCHER = "preexisting_before_watcher"
COVERAGE_MIGRATION_ONLY_UNTRACKED = "migration_only_untracked"
COVERAGE_REPLAY_UNRESOLVED = "replay_unresolved"
COVERAGE_TRUE_SOURCE_MISS = "true_source_miss"
COVERAGE_NOT_MIGRATED = "not_migrated"


def _first(row: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _mint(row: Mapping[str, Any]) -> str:
    return str(_first(row, ("mint", "token_mint", "base_mint", "created_mint")) or "")


def _event_time(row: Mapping[str, Any]) -> float | None:
    return _float(
        _first(
            row,
            (
                "decision_time",
                "observed_at",
                "received_at",
                "migration_received_at",
                "crossing_received_at",
                "block_time",
                "launch_time_from_replay",
            ),
        )
    )


def lifecycle_event(event_type: str, row: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    event = {
        "event_type": event_type,
        "mint": _mint(row),
        "observed_at": _event_time(row),
        "signature": _first(row, ("signature", "launch_signature", "migration_signature", "transaction_signature")),
        "slot": _first(row, ("slot", "launch_slot")),
        "source_route": _first(row, ("source_route", "source_route_key", "source_type", "detection_method", "observation_source")),
        "payload": dict(row),
    }
    event.update({key: value for key, value in extra.items() if value not in (None, "")})
    return event


def event_from_birth_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(
        EVENT_BIRTH_SEEN,
        row,
        birth_seen_live=not _bool(row.get("birth_backfilled_from_replay")) and not _bool(row.get("birth_candidate_excluded")),
        birth_backfilled_from_replay=_bool(row.get("birth_backfilled_from_replay")),
        admitted=_bool(row.get("admitted")),
        bonding_curve_account=_first(row, ("bonding_curve_account", "bonding_curve", "decoded_bonding_curve_account")),
        curve_account_verified=_bool(row.get("curve_account_verified")),
    )


def event_from_curve_observation_row(row: Mapping[str, Any]) -> dict[str, Any]:
    decoded = str(row.get("decode_status") or "").lower() == "decoded"
    account_found = row.get("account_found") is not False
    progress = _float(row.get("progress_pct") or row.get("computed_progress_pct"))
    market_cap = _float(
        _first(
            row,
            (
                "bonding_curve_market_cap_usd",
                "market_cap_usd",
                "fdv_proxy_usd",
                "valuation_usd",
            ),
        )
    )
    return lifecycle_event(
        EVENT_CURVE_OBSERVED,
        row,
        curve_account_verified=bool(decoded and account_found),
        progress_decoded=bool(decoded and progress is not None),
        progress_pct=progress,
        market_cap_confirmed=bool(market_cap is not None),
        market_cap_usd=market_cap,
        decode_status=row.get("decode_status"),
        bonding_curve_account=_first(row, ("bonding_curve_account", "bonding_curve")),
    )


def event_from_threshold_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(EVENT_THRESHOLD_CROSSED, row, threshold_pct=_float(row.get("threshold_pct")))


def event_from_trade_flow_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(EVENT_TRADE_FLOW_OBSERVED, row)


def event_from_holder_dev_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(EVENT_HOLDER_DEV_OBSERVED, row)


def event_from_migration_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(
        EVENT_MIGRATION_SEEN,
        row,
        pool_address=_first(row, ("pool_or_pair_address", "pool_address", "pair_address", "pool")),
        quote_asset=row.get("quote_asset"),
        migration_evidence_level=row.get("migration_evidence_level"),
    )


def event_from_post_migration_row(row: Mapping[str, Any]) -> dict[str, Any]:
    has_depth = any(row.get(key) not in (None, "") for key in ("base_reserve_raw", "quote_reserve_raw", "pool_liquidity_quote", "pool_liquidity_usd"))
    return lifecycle_event(
        EVENT_POST_MIGRATION_OBSERVED,
        row,
        pool_address=_first(row, ("pool_or_pair_address", "pool_address", "pair_address", "pool")),
        post_migration_pool_ready=has_depth or bool(row),
    )


def event_from_quote_row(row: Mapping[str, Any]) -> dict[str, Any]:
    has_quote = any(row.get(key) not in (None, "") for key in ("price_impact_pct", "expected_output_quote", "effective_exit_price_quote_per_token", "quote_status"))
    return lifecycle_event(
        EVENT_QUOTE_OBSERVED,
        row,
        quote_ready=has_quote or _bool(row.get("executable_quote_available")) or bool(row.get("quote_status")),
    )


def event_from_replay_context_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return lifecycle_event(
        EVENT_REPLAY_BIRTH_CONTEXT,
        row,
        launch_time_from_replay=_float(row.get("launch_time_from_replay")),
        campaign_start_time=_float(row.get("campaign_start_time")),
        campaign_end_time=_float(row.get("campaign_end_time")),
        failure_reason=row.get("failure_reason") or row.get("source_miss_reason"),
        replay_birth_found=_bool(row.get("replay_birth_found")),
    )

# --- T007_PRODUCTION_CANONICAL_EVENTS_V2 ------------------------------------
# Canonical event names used by the production SQLite ledger. Legacy artifact
# event names remain accepted by reducers/exporters for backward compatibility.
EVENT_RAW_TRANSACTION_SEEN = "raw_transaction_seen"
EVENT_SENTINEL_LOG_SEEN = "sentinel_log_seen"
EVENT_CANONICAL_SENTINEL_GAP_DETECTED = "canonical_sentinel_gap_detected"
EVENT_PUMP_BIRTH_VERIFIED = "pump_birth_verified"
EVENT_PUMP_BIRTH_REJECTED = "pump_birth_rejected"
EVENT_CURVE_ACCOUNT_VERIFIED = "curve_account_verified"
EVENT_CURVE_STATE_DECODED = "curve_state_decoded"
EVENT_CURVE_STATE_DECODE_FAILED = "curve_state_decode_failed"
EVENT_CURVE_ACCOUNT_NOT_FOUND_RETRY = "curve_account_not_found_retry"
EVENT_CURVE_ACCOUNT_NOT_FOUND_FINAL = "curve_account_not_found_final"
EVENT_PUMP_TRADE_SEEN = "pump_trade_seen"
EVENT_TRADE_FLOW_WINDOW_UPDATED = "trade_flow_window_updated"
EVENT_HOLDER_DEV_SNAPSHOT_SEEN = "holder_dev_snapshot_seen"
EVENT_PROGRESS_THRESHOLD_EVALUATED = "progress_threshold_evaluated"
EVENT_PROGRESS_THRESHOLD_CROSSED = "progress_threshold_crossed"
EVENT_PUMP_COMPLETE_SEEN = "pump_complete_seen"
EVENT_PUMP_MIGRATE_SEEN = "pump_migrate_seen"
EVENT_PUMPSWAP_POOL_SEEN = "pumpswap_pool_seen"
EVENT_PUMPSWAP_POOL_VERIFIED = "pumpswap_pool_verified"
EVENT_PUMPSWAP_SWAP_SEEN = "pumpswap_swap_seen"
EVENT_POST_MIGRATION_DEPTH_SEEN = "post_migration_depth_seen"
EVENT_QUOTE_OBSERVATION_SEEN = "quote_observation_seen"
EVENT_REPLAY_BIRTH_CONTEXT_SEEN = "replay_birth_context_seen"
EVENT_REPLAY_CONTEXT_UNRESOLVED = "replay_context_unresolved"
EVENT_SOURCE_GAP_DETECTED = "source_gap_detected"
EVENT_SOURCE_GAP_BACKFILLED = "source_gap_backfilled"
EVENT_LANE_STALL_DETECTED = "lane_stall_detected"
EVENT_BOUNDED_REPLAY_STARTED = "bounded_replay_started"
EVENT_BOUNDED_REPLAY_FINISHED = "bounded_replay_finished"
EVENT_BOUNDED_REPLAY_FAILED = "bounded_replay_failed"

COVERAGE_DECISION_SAFE_FULL_PATH = "decision_safe_full_path"
COVERAGE_PRE_MIGRATION_THESIS_USABLE = "pre_migration_thesis_usable"
COVERAGE_MIGRATION_WITH_PRE_DATA = "migration_with_pre_data"
COVERAGE_MIGRATION_ONLY = "migration_only"
COVERAGE_BIRTH_SAMPLE_OR_CAPACITY_REJECTED = "birth_seen_sample_or_capacity_rejected"
COVERAGE_SOURCE_MISS = "source_miss"
COVERAGE_SCHEMA_OR_LAYOUT_BLOCKED = "schema_or_layout_blocked"

LEGACY_TO_CANONICAL_EVENT_TYPE = {
    "birth_seen": EVENT_PUMP_BIRTH_VERIFIED,
    "curve_observation": EVENT_CURVE_STATE_DECODED,
    "threshold_crossing": EVENT_PROGRESS_THRESHOLD_CROSSED,
    "trade_flow": EVENT_TRADE_FLOW_WINDOW_UPDATED,
    "holder_dev": EVENT_HOLDER_DEV_SNAPSHOT_SEEN,
    "global_migration": EVENT_PUMPSWAP_POOL_VERIFIED,
    "migration": EVENT_PUMPSWAP_POOL_VERIFIED,
    "post_migration": EVENT_POST_MIGRATION_DEPTH_SEEN,
    "quote": EVENT_QUOTE_OBSERVATION_SEEN,
    "execution_cost": "execution_cost_seen",
    "replay_backfill": EVENT_REPLAY_BIRTH_CONTEXT_SEEN,
}

STRICT_DECISION_FEATURE_EVENTS = {
    EVENT_PUMP_BIRTH_VERIFIED,
    EVENT_CURVE_ACCOUNT_VERIFIED,
    EVENT_CURVE_STATE_DECODED,
    EVENT_TRADE_FLOW_WINDOW_UPDATED,
    EVENT_HOLDER_DEV_SNAPSHOT_SEEN,
    EVENT_PUMPSWAP_POOL_VERIFIED,
    EVENT_POST_MIGRATION_DEPTH_SEEN,
    EVENT_QUOTE_OBSERVATION_SEEN,
}

def canonical_event_type(event_type: str | None) -> str:
    if not event_type:
        return "unknown_event"
    return LEGACY_TO_CANONICAL_EVENT_TYPE.get(str(event_type), str(event_type))

def event_is_decision_time_safe(event_type: str | None, payload: dict | None = None) -> bool:
    canonical = canonical_event_type(event_type)
    if canonical.startswith("replay_") or canonical in {EVENT_SOURCE_GAP_BACKFILLED, EVENT_BOUNDED_REPLAY_FINISHED}:
        return False
    if payload and payload.get("replay_source") is True:
        return False
    return canonical in STRICT_DECISION_FEATURE_EVENTS
