from __future__ import annotations

import time
from collections import Counter
from typing import Any


STEP_TO_BLOCKER = {
    "MANUAL_RISK_REVIEW": "manual_risk_review",
    "COLLECT_OUTCOMES_AND_MARKET_CONTEXT": "missing_outcomes_and_market_context",
    "COLLECT_OUTCOME_LABELS": "missing_outcome_labels",
    "COLLECT_MORE_WALLET_EVIDENCE": "missing_wallet_evidence",
}

BLOCKER_PRIORITY = {
    "manual_risk_review": 0,
    "missing_outcomes_and_market_context": 1,
    "missing_outcome_labels": 2,
    "missing_wallet_evidence": 3,
}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _primary_blocker(row: dict[str, Any]) -> str:
    step = str(row.get("next_collection_step") or "")
    return STEP_TO_BLOCKER.get(step, "unknown_blocker")


def _target_card(row: dict[str, Any]) -> dict[str, Any]:
    missing = as_dict(row.get("missing"))
    blocker = _primary_blocker(row)
    return {
        "wallet": row.get("wallet"),
        "primary_blocker": blocker,
        "next_collection_step": row.get("next_collection_step"),
        "audit_status": row.get("audit_status"),
        "recommendation_action": row.get("recommendation_action"),
        "known_outcomes": safe_int(row.get("known_outcomes")),
        "round_trip_lifecycles": safe_int(row.get("round_trip_lifecycles")),
        "missing_known_outcomes": safe_int(missing.get("known_outcomes")),
        "missing_round_trip_lifecycles": safe_int(missing.get("round_trip_lifecycles")),
        "market_context_missing": bool(missing.get("market_context")),
        "risk_review_missing": bool(missing.get("risk_review")),
        "notes": [str(note) for note in as_list(row.get("notes"))[:3]],
    }


def _next_actions(blocker_counts: Counter[str], batch_summary: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if blocker_counts["manual_risk_review"]:
        actions.append({
            "action": "resolve_manual_risk_reviews",
            "count": blocker_counts["manual_risk_review"],
            "reason": "Risk-review wallets cannot move tiers until operator/risk review is complete.",
        })
    if blocker_counts["missing_outcomes_and_market_context"]:
        actions.append({
            "action": "collect_outcomes_and_market_context",
            "count": blocker_counts["missing_outcomes_and_market_context"],
            "reason": "These wallets need outcome labels and decision-time market context before trust changes.",
        })
    if blocker_counts["missing_outcome_labels"]:
        actions.append({
            "action": "backfill_outcome_labels",
            "count": blocker_counts["missing_outcome_labels"],
            "reason": "These wallets have some context but still need later outcome labels.",
        })
    if blocker_counts["missing_wallet_evidence"]:
        actions.append({
            "action": "collect_more_wallet_evidence",
            "count": blocker_counts["missing_wallet_evidence"],
            "reason": "These wallets need more observed wallet-history evidence before review.",
        })
    if safe_int(batch_summary.get("steps_failed")):
        actions.append({
            "action": "fix_failed_batch_steps",
            "count": safe_int(batch_summary.get("steps_failed")),
            "reason": "The report refresh did not finish cleanly.",
        })
    actions.append({
        "action": "rerun_stage4_batch_after_new_evidence",
        "count": safe_int(batch_summary.get("steps_planned")),
        "reason": "Refresh the full evidence chain after new context or risk decisions are added.",
    })
    return actions


def build_wallet_candidate_blocker_reducer(
    *,
    candidate_audit: dict[str, Any],
    collection_plan: dict[str, Any],
    collection_batch: dict[str, Any],
    generated_at: float | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    audit = as_dict(candidate_audit)
    plan = as_dict(collection_plan)
    batch = as_dict(collection_batch)
    audit_counts = as_dict(audit.get("counts"))
    plan_summary = as_dict(plan.get("summary"))
    batch_summary = as_dict(batch.get("summary"))
    target_rows = [_target_card(row) for row in as_list(plan.get("targets")) if isinstance(row, dict)]
    blocker_counts = Counter(row["primary_blocker"] for row in target_rows)
    target_rows.sort(key=lambda row: (
        BLOCKER_PRIORITY.get(row["primary_blocker"], 99),
        -row["missing_known_outcomes"],
        str(row.get("wallet") or ""),
    ))
    missing_known = sum(row["missing_known_outcomes"] for row in target_rows)
    missing_round_trips = sum(row["missing_round_trip_lifecycles"] for row in target_rows)
    actionable = safe_int(audit_counts.get("human_review_required"))
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "candidates": safe_int(audit_counts.get("candidates"), len(as_list(audit.get("candidates")))),
            "resolved_excluded": safe_int(plan_summary.get("resolved_excluded"), safe_int(audit_counts.get("resolved"))),
            "blocked_total": safe_int(plan_summary.get("total_targets"), len(target_rows)),
            "actionable_review": actionable,
            "batch_steps_passed": safe_int(batch_summary.get("steps_passed")),
            "batch_steps_failed": safe_int(batch_summary.get("steps_failed")),
        },
        "primary_blocker_counts": dict(blocker_counts),
        "missing_totals": {
            "known_outcomes": missing_known,
            "round_trip_lifecycles": missing_round_trips,
            "risk_review_wallets": blocker_counts["manual_risk_review"],
            "market_context_wallets": blocker_counts["missing_outcomes_and_market_context"],
            "outcome_label_wallets": blocker_counts["missing_outcome_labels"],
        },
        "batch_health": {
            "steps_planned": safe_int(batch_summary.get("steps_planned")),
            "steps_run": safe_int(batch_summary.get("steps_run")),
            "steps_passed": safe_int(batch_summary.get("steps_passed")),
            "steps_failed": safe_int(batch_summary.get("steps_failed")),
        },
        "count": min(len(target_rows), int(limit)),
        "top_blocked_wallets": target_rows[: int(limit)],
        "next_actions": _next_actions(blocker_counts, batch_summary),
        "operator_note": "Review-only blocker reducer. It explains why wallets are still blocked from promotion/demotion; it does not approve, apply, trade, or mutate wallet lists.",
    }
