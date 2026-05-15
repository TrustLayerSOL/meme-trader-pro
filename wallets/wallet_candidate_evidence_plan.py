from __future__ import annotations

import time
from collections import Counter
from typing import Any


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


def missing_counts(row: dict[str, Any], *, min_replay_known: int, min_fillable: int, min_outcomes: int) -> dict[str, int]:
    replay = as_dict(row.get("replay"))
    outcome = as_dict(row.get("outcome"))
    return {
        "replay_known_15m": max(0, min_replay_known - safe_int(replay.get("known_15m"))),
        "fillable_events": max(0, min_fillable - safe_int(replay.get("fillable_events"))),
        "known_outcomes": max(0, min_outcomes - safe_int(outcome.get("known_outcomes"))),
    }


def next_action(row: dict[str, Any], missing: dict[str, int]) -> str:
    action = str(as_dict(row.get("recommendation")).get("action") or "")
    risks = row.get("risk_flags") if isinstance(row.get("risk_flags"), list) else []
    if action == "RISK_REVIEW" or risks:
        return "RESOLVE_RISK_FLAGS"
    if action == "PROMOTION_REVIEW_READY" and not any(missing.values()):
        return "READY_FOR_HUMAN_REVIEW"
    needs_replay = missing["replay_known_15m"] > 0 or missing["fillable_events"] > 0
    needs_outcome = missing["known_outcomes"] > 0
    if needs_replay and needs_outcome:
        return "COLLECT_REPLAY_AND_OUTCOME_EVIDENCE"
    if needs_replay:
        return "COLLECT_REPLAY_EVIDENCE"
    if needs_outcome:
        return "COLLECT_OUTCOME_LABELS"
    return "HOLD_FOR_NEXT_REVIEW"


def priority_score(row: dict[str, Any], missing: dict[str, int], action: str) -> float:
    score = safe_float(row.get("quality_score"))
    gap_penalty = (missing["replay_known_15m"] + missing["fillable_events"] + missing["known_outcomes"]) * 1.5
    if action == "RESOLVE_RISK_FLAGS":
        score -= 20
    elif action == "READY_FOR_HUMAN_REVIEW":
        score += 25
    return round(max(0.0, score - gap_penalty), 2)


def queue_row(
    row: dict[str, Any],
    *,
    min_replay_known: int,
    min_fillable: int,
    min_outcomes: int,
) -> dict[str, Any]:
    replay = as_dict(row.get("replay"))
    outcome = as_dict(row.get("outcome"))
    missing = missing_counts(row, min_replay_known=min_replay_known, min_fillable=min_fillable, min_outcomes=min_outcomes)
    action = next_action(row, missing)
    return {
        "wallet": row.get("wallet"),
        "quality_score": safe_float(row.get("quality_score")),
        "current_recommendation": as_dict(row.get("recommendation")).get("action") or "OBSERVE_MORE",
        "next_action": action,
        "priority_score": priority_score(row, missing, action),
        "current": {
            "replay_known_15m": safe_int(replay.get("known_15m")),
            "fillable_events": safe_int(replay.get("fillable_events")),
            "known_outcomes": safe_int(outcome.get("known_outcomes")),
        },
        "targets": {
            "replay_known_15m": min_replay_known,
            "fillable_events": min_fillable,
            "known_outcomes": min_outcomes,
        },
        "missing": missing,
        "risk_flags": row.get("risk_flags") if isinstance(row.get("risk_flags"), list) else [],
        "evidence_gaps": row.get("evidence_gaps") if isinstance(row.get("evidence_gaps"), list) else [],
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    actions = Counter(str(row.get("next_action") or "") for row in rows)
    return {
        "total_candidates": len(rows),
        "ready_for_review": actions["READY_FOR_HUMAN_REVIEW"],
        "needs_replay_coverage": actions["COLLECT_REPLAY_EVIDENCE"] + actions["COLLECT_REPLAY_AND_OUTCOME_EVIDENCE"],
        "needs_outcome_coverage": actions["COLLECT_OUTCOME_LABELS"] + actions["COLLECT_REPLAY_AND_OUTCOME_EVIDENCE"],
        "risk_review": actions["RESOLVE_RISK_FLAGS"],
        "hold_for_next_review": actions["HOLD_FOR_NEXT_REVIEW"],
    }


def build_wallet_candidate_evidence_plan(
    *,
    candidate_quality_review: Any,
    generated_at: float | None = None,
    limit: int = 50,
    min_replay_known: int = 10,
    min_fillable: int = 10,
    min_outcomes: int = 10,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    rows = [
        queue_row(
            row,
            min_replay_known=min_replay_known,
            min_fillable=min_fillable,
            min_outcomes=min_outcomes,
        )
        for row in as_dict(candidate_quality_review).get("shortlist") or []
        if isinstance(row, dict) and row.get("wallet")
    ]
    rows = sorted(rows, key=lambda item: (safe_float(item.get("priority_score")), safe_float(item.get("quality_score"))), reverse=True)
    if limit is not None:
        rows = rows[: int(limit)]
    return {
        "generated_at": generated_at,
        "mode": "WALLET_CANDIDATE_EVIDENCE_PLAN_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "thresholds": {
            "min_replay_known_15m": min_replay_known,
            "min_fillable_events": min_fillable,
            "min_known_outcomes": min_outcomes,
        },
        "summary": build_summary(rows),
        "coverage_queue": rows,
    }
