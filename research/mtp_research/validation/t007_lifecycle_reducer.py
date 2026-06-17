"""State reducer for the T007 persistent lifecycle watcher."""

from __future__ import annotations

from typing import Any, Mapping

from research.mtp_research.validation.t007_lifecycle_events import (
    COVERAGE_MIGRATION_ONLY_UNTRACKED,
    COVERAGE_NOT_MIGRATED,
    COVERAGE_PREEXISTING_BEFORE_WATCHER,
    COVERAGE_REPLAY_UNRESOLVED,
    COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH,
    COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE,
    COVERAGE_TRUE_SOURCE_MISS,
    EVENT_BIRTH_SEEN,
    EVENT_CURVE_OBSERVED,
    EVENT_HOLDER_DEV_OBSERVED,
    EVENT_MIGRATION_SEEN,
    EVENT_POST_MIGRATION_OBSERVED,
    EVENT_QUOTE_OBSERVED,
    EVENT_REPLAY_BIRTH_CONTEXT,
    EVENT_THRESHOLD_CROSSED,
    EVENT_TRADE_FLOW_OBSERVED,
    STATE_BIRTH_SEEN,
    STATE_CURVE_ACCOUNT_VERIFIED,
    STATE_FULL_PATH_READY,
    STATE_MIGRATION_ONLY_UNTRACKED,
    STATE_MIGRATION_SEEN,
    STATE_POST_MIGRATION_POOL_READY,
    STATE_PREEXISTING_BEFORE_WATCHER,
    STATE_PROGRESS_TRACKING,
    STATE_QUOTE_READY,
    STATE_REPLAY_UNRESOLVED,
    STATE_THRESHOLD_CROSSED,
    STATE_TRUE_SOURCE_MISS,
)


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


def empty_state(mint: str) -> dict[str, Any]:
    return {
        "mint": mint,
        "lifecycle_state": "UNKNOWN",
        "coverage_class": COVERAGE_NOT_MIGRATED,
        "birth_seen": False,
        "birth_seen_live": False,
        "birth_backfilled_from_replay": False,
        "admitted": False,
        "curve_account_verified": False,
        "progress_tracking": False,
        "progress_decoded": False,
        "market_cap_confirmed": False,
        "threshold_crossed": False,
        "trade_flow_available": False,
        "holder_dev_available": False,
        "migration_seen": False,
        "post_migration_pool_ready": False,
        "post_migration_seen": False,
        "quote_ready": False,
        "replay_birth_found": False,
        "replay_unresolved": False,
        "preexisting_before_watcher": False,
        "true_source_miss": False,
        "first_birth_seen_at": None,
        "first_curve_verified_at": None,
        "first_progress_tracking_at": None,
        "first_threshold_crossed_at": None,
        "first_trade_flow_at": None,
        "first_holder_dev_at": None,
        "first_migration_seen_at": None,
        "first_post_migration_pool_ready_at": None,
        "first_quote_ready_at": None,
        "launch_time_from_replay": None,
        "campaign_start_time": None,
        "campaign_end_time": None,
        "last_event_at": None,
        "pool_address": None,
        "quote_asset": None,
    }


def _set_first(state: dict[str, Any], key: str, value: Any) -> None:
    number = _float(value)
    if number is None:
        return
    if state.get(key) is None or number < float(state[key]):
        state[key] = number


def apply_event(state: Mapping[str, Any] | None, event: Mapping[str, Any]) -> dict[str, Any]:
    mint = str(event.get("mint") or (state or {}).get("mint") or "")
    next_state = dict(state or empty_state(mint))
    event_type = str(event.get("event_type") or "")
    observed_at = _float(event.get("observed_at"))
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if observed_at is not None:
        next_state["last_event_at"] = max(_float(next_state.get("last_event_at")) or observed_at, observed_at)

    if event_type == EVENT_BIRTH_SEEN:
        next_state["birth_seen"] = True
        next_state["birth_seen_live"] = bool(next_state.get("birth_seen_live") or _bool(event.get("birth_seen_live")))
        next_state["birth_backfilled_from_replay"] = bool(next_state.get("birth_backfilled_from_replay") or _bool(event.get("birth_backfilled_from_replay")))
        next_state["admitted"] = bool(next_state.get("admitted") or _bool(event.get("admitted")))
        if event.get("bonding_curve_account"):
            next_state["bonding_curve_account"] = event.get("bonding_curve_account")
        if _bool(event.get("curve_account_verified")):
            next_state["curve_account_verified"] = True
            _set_first(next_state, "first_curve_verified_at", observed_at)
        _set_first(next_state, "first_birth_seen_at", observed_at)
    elif event_type == EVENT_CURVE_OBSERVED:
        next_state["progress_tracking"] = True
        next_state["progress_decoded"] = bool(next_state.get("progress_decoded") or _bool(event.get("progress_decoded")))
        next_state["market_cap_confirmed"] = bool(next_state.get("market_cap_confirmed") or _bool(event.get("market_cap_confirmed")))
        _set_first(next_state, "first_progress_tracking_at", observed_at)
        if _bool(event.get("curve_account_verified")):
            next_state["curve_account_verified"] = True
            _set_first(next_state, "first_curve_verified_at", observed_at)
        progress = _float(event.get("progress_pct"))
        if progress is not None:
            next_state["highest_progress_pct"] = max(_float(next_state.get("highest_progress_pct")) or progress, progress)
    elif event_type == EVENT_THRESHOLD_CROSSED:
        next_state["threshold_crossed"] = True
        _set_first(next_state, "first_threshold_crossed_at", observed_at)
    elif event_type == EVENT_TRADE_FLOW_OBSERVED:
        next_state["trade_flow_available"] = True
        _set_first(next_state, "first_trade_flow_at", observed_at)
    elif event_type == EVENT_HOLDER_DEV_OBSERVED:
        next_state["holder_dev_available"] = True
        _set_first(next_state, "first_holder_dev_at", observed_at)
    elif event_type == EVENT_MIGRATION_SEEN:
        next_state["migration_seen"] = True
        if event.get("pool_address"):
            next_state["pool_address"] = event.get("pool_address")
        if event.get("quote_asset"):
            next_state["quote_asset"] = event.get("quote_asset")
        _set_first(next_state, "first_migration_seen_at", observed_at)
    elif event_type == EVENT_POST_MIGRATION_OBSERVED:
        next_state["post_migration_pool_ready"] = bool(next_state.get("post_migration_pool_ready") or _bool(event.get("post_migration_pool_ready")))
        next_state["post_migration_seen"] = bool(next_state.get("post_migration_seen") or next_state.get("post_migration_pool_ready"))
        if event.get("pool_address"):
            next_state["pool_address"] = event.get("pool_address")
        _set_first(next_state, "first_post_migration_pool_ready_at", observed_at)
    elif event_type == EVENT_QUOTE_OBSERVED:
        next_state["quote_ready"] = bool(next_state.get("quote_ready") or _bool(event.get("quote_ready")))
        _set_first(next_state, "first_quote_ready_at", observed_at)
    elif event_type == EVENT_REPLAY_BIRTH_CONTEXT:
        launch_time = _float(event.get("launch_time_from_replay"))
        campaign_start = _float(event.get("campaign_start_time"))
        campaign_end = _float(event.get("campaign_end_time"))
        next_state["launch_time_from_replay"] = launch_time
        next_state["campaign_start_time"] = campaign_start
        next_state["campaign_end_time"] = campaign_end
        next_state["replay_birth_found"] = bool(_bool(event.get("replay_birth_found")) or launch_time is not None)
        next_state["replay_unresolved"] = bool(event.get("failure_reason") or (not next_state["replay_birth_found"] and not launch_time))
        next_state["preexisting_before_watcher"] = bool(launch_time is not None and campaign_start is not None and launch_time < campaign_start)
        next_state["true_source_miss"] = bool(
            launch_time is not None
            and campaign_start is not None
            and campaign_end is not None
            and campaign_start <= launch_time <= campaign_end
            and not next_state.get("birth_seen_live")
        )

    next_state["coverage_class"] = classify_coverage(next_state)
    next_state["lifecycle_state"] = classify_lifecycle_state(next_state)
    return next_state


def classify_coverage(state: Mapping[str, Any]) -> str:
    if not _bool(state.get("migration_seen")):
        return COVERAGE_NOT_MIGRATED
    if _bool(state.get("birth_seen_live")) and all(
        _bool(state.get(key))
        for key in (
            "curve_account_verified",
            "threshold_crossed",
            "trade_flow_available",
            "holder_dev_available",
            "post_migration_pool_ready",
            "quote_ready",
        )
    ):
        return COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH
    if _bool(state.get("birth_seen_live")):
        return COVERAGE_TRACKED_FROM_BIRTH_MISSING_FEATURE
    if _bool(state.get("preexisting_before_watcher")):
        return COVERAGE_PREEXISTING_BEFORE_WATCHER
    if _bool(state.get("true_source_miss")):
        return COVERAGE_TRUE_SOURCE_MISS
    if _bool(state.get("replay_unresolved")):
        return COVERAGE_REPLAY_UNRESOLVED
    return COVERAGE_MIGRATION_ONLY_UNTRACKED


def classify_lifecycle_state(state: Mapping[str, Any]) -> str:
    coverage = str(state.get("coverage_class") or "")
    if coverage == COVERAGE_PREEXISTING_BEFORE_WATCHER:
        return STATE_PREEXISTING_BEFORE_WATCHER
    if coverage == COVERAGE_TRUE_SOURCE_MISS:
        return STATE_TRUE_SOURCE_MISS
    if coverage == COVERAGE_REPLAY_UNRESOLVED:
        return STATE_REPLAY_UNRESOLVED
    if coverage == COVERAGE_MIGRATION_ONLY_UNTRACKED:
        return STATE_MIGRATION_ONLY_UNTRACKED
    if coverage == COVERAGE_TRACKED_FROM_BIRTH_FULL_PATH:
        return STATE_FULL_PATH_READY
    if _bool(state.get("quote_ready")):
        return STATE_QUOTE_READY
    if _bool(state.get("post_migration_pool_ready")):
        return STATE_POST_MIGRATION_POOL_READY
    if _bool(state.get("migration_seen")):
        return STATE_MIGRATION_SEEN
    if _bool(state.get("threshold_crossed")):
        return STATE_THRESHOLD_CROSSED
    if _bool(state.get("progress_tracking")):
        return STATE_PROGRESS_TRACKING
    if _bool(state.get("curve_account_verified")):
        return STATE_CURVE_ACCOUNT_VERIFIED
    if _bool(state.get("birth_seen")):
        return STATE_BIRTH_SEEN
    return "UNKNOWN"
