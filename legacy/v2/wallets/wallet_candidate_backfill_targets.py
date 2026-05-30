from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def event_wallets(event: dict[str, Any]) -> list[str]:
    out = []
    seen = set()
    for row in event.get("wallets") or []:
        wallet = row.get("wallet") if isinstance(row, dict) else row
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            out.append(wallet)
            seen.add(wallet)
    return out


def outcome_15m(event: dict[str, Any]) -> str:
    windows = as_dict(as_dict(event.get("later_outcome")).get("windows"))
    return str(as_dict(windows.get("15m")).get("outcome_type") or "unknown").lower()


def fill_status(event: dict[str, Any]) -> str:
    return str(as_dict(event.get("execution_assumptions")).get("fill_status") or "unknown_liquidity")


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "mint": event.get("mint"),
        "source_record_type": event.get("source_record_type"),
        "signal_timestamp": event.get("signal_timestamp"),
        "fill_status": fill_status(event),
        "outcome_15m": outcome_15m(event),
    }


def group_events_by_wallet(replay_events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in replay_events or []:
        if not isinstance(event, dict):
            continue
        for wallet in event_wallets(event):
            grouped[wallet].append(event)
    return grouped


def choose_collection_step(plan_row: dict[str, Any], events: list[dict[str, Any]]) -> str:
    if str(plan_row.get("next_action") or "") == "RESOLVE_RISK_FLAGS":
        return "REVIEW_RISK_FLAGS_FIRST"
    if not events:
        return "COLLECT_WALLET_HISTORY"
    if any(outcome_15m(event) not in KNOWN_OUTCOMES for event in events):
        return "BACKFILL_OUTCOME_LABELS"
    missing = as_dict(plan_row.get("missing"))
    if safe_int(missing.get("fillable_events")) > 0 or safe_int(missing.get("replay_known_15m")) > 0:
        return "COLLECT_MORE_REPLAY_EVENTS"
    if safe_int(missing.get("known_outcomes")) > 0:
        return "COLLECT_OUTCOME_LABELS"
    return "HOLD_FOR_REVIEW"


def target_row(plan_row: dict[str, Any], events: list[dict[str, Any]], *, event_limit: int = 10) -> dict[str, Any]:
    unknown_events = [event for event in events if outcome_15m(event) not in KNOWN_OUTCOMES]
    fillable = [event for event in events if fill_status(event) == "fillable_with_assumptions"]
    step = choose_collection_step(plan_row, events)
    missing = as_dict(plan_row.get("missing"))
    return {
        "wallet": plan_row.get("wallet"),
        "priority_score": safe_float(plan_row.get("priority_score")),
        "quality_score": safe_float(plan_row.get("quality_score")),
        "source_next_action": plan_row.get("next_action"),
        "next_collection_step": step,
        "local_replay_events": len(events),
        "fillable_events": len(fillable),
        "unknown_15m_events": len(unknown_events),
        "missing": {
            "replay_known_15m": safe_int(missing.get("replay_known_15m")),
            "fillable_events": safe_int(missing.get("fillable_events")),
            "known_outcomes": safe_int(missing.get("known_outcomes")),
        },
        "risk_flags": plan_row.get("risk_flags") if isinstance(plan_row.get("risk_flags"), list) else [],
        "event_targets": [event_summary(event) for event in unknown_events[:event_limit]],
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    actions = Counter(str(row.get("next_collection_step") or "") for row in rows)
    return {
        "total_targets": len(rows),
        "needs_wallet_history": actions["COLLECT_WALLET_HISTORY"],
        "needs_outcome_label_backfill": actions["BACKFILL_OUTCOME_LABELS"] + actions["COLLECT_OUTCOME_LABELS"],
        "needs_more_replay_events": actions["COLLECT_MORE_REPLAY_EVENTS"],
        "risk_review": actions["REVIEW_RISK_FLAGS_FIRST"],
        "ready_or_hold": actions["HOLD_FOR_REVIEW"],
    }


def build_wallet_candidate_backfill_targets(
    *,
    candidate_evidence_plan: Any,
    replay_events: list[dict[str, Any]],
    generated_at: float | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped = group_events_by_wallet(replay_events)
    rows = []
    for plan_row in as_dict(candidate_evidence_plan).get("coverage_queue") or []:
        if not isinstance(plan_row, dict) or not plan_row.get("wallet"):
            continue
        wallet = str(plan_row.get("wallet"))
        rows.append(target_row(plan_row, grouped.get(wallet, [])))
    rows = sorted(rows, key=lambda row: (safe_float(row.get("priority_score")), safe_float(row.get("quality_score"))), reverse=True)
    if limit is not None:
        rows = rows[: int(limit)]
    return {
        "generated_at": generated_at,
        "mode": "WALLET_CANDIDATE_BACKFILL_TARGETS_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "summary": build_summary(rows),
        "targets": rows,
    }
