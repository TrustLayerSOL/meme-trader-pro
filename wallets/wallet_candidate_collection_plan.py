from __future__ import annotations

import time
from collections import Counter
from typing import Any


MIN_KNOWN_OUTCOMES = 20
MIN_ROUND_TRIPS = 3


NEXT_ACTION_MAP = {
    "collect_outcomes_and_market_context": "COLLECT_OUTCOMES_AND_MARKET_CONTEXT",
    "collect_outcome_labels": "COLLECT_OUTCOME_LABELS",
    "manual_risk_review": "MANUAL_RISK_REVIEW",
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


def _next_step(row: dict[str, Any], evidence: dict[str, Any]) -> str:
    if row.get("audit_status") == "RISK_REVIEW_REQUIRED" or row.get("recommendation_action") == "RISK_REVIEW_REQUIRED":
        return "MANUAL_RISK_REVIEW"
    scorecard_next = str(evidence.get("scorecard_next_action") or "")
    return NEXT_ACTION_MAP.get(scorecard_next, "COLLECT_MORE_WALLET_EVIDENCE")


def target_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = as_dict(row.get("evidence"))
    known = safe_int(evidence.get("known_outcomes"))
    round_trips = safe_int(evidence.get("round_trip_lifecycles"))
    step = _next_step(row, evidence)
    return {
        "wallet": row.get("wallet"),
        "next_collection_step": step,
        "audit_status": row.get("audit_status"),
        "recommendation_action": row.get("recommendation_action"),
        "source_bucket": evidence.get("source_bucket"),
        "scorecard_next_action": evidence.get("scorecard_next_action"),
        "known_outcomes": known,
        "round_trip_lifecycles": round_trips,
        "missing": {
            "known_outcomes": max(0, MIN_KNOWN_OUTCOMES - known),
            "round_trip_lifecycles": max(0, MIN_ROUND_TRIPS - round_trips),
            "market_context": step == "COLLECT_OUTCOMES_AND_MARKET_CONTEXT",
            "risk_review": step == "MANUAL_RISK_REVIEW",
        },
        "blocked_from_trust_change": step == "MANUAL_RISK_REVIEW" or row.get("audit_status") != "HUMAN_REVIEW_REQUIRED",
        "notes": [str(note) for note in as_list(row.get("audit_notes"))[:3]],
    }


def build_wallet_candidate_collection_plan(
    candidate_audit: dict[str, Any],
    *,
    generated_at: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    audit = as_dict(candidate_audit)
    rows = [
        target_row(row)
        for row in as_list(audit.get("candidates"))
        if isinstance(row, dict)
        and row.get("wallet")
        and row.get("audit_status") in {"INSUFFICIENT_EVIDENCE", "RISK_REVIEW_REQUIRED"}
    ]
    rows.sort(key=lambda row: (
        row["next_collection_step"] != "MANUAL_RISK_REVIEW",
        row["next_collection_step"],
        row["missing"]["known_outcomes"],
        row["wallet"],
    ))
    counts = Counter(row["next_collection_step"] for row in rows)
    returned = rows[: int(limit)]
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "total_targets": len(rows),
            "returned_targets": len(returned),
            "collect_outcomes_and_market_context": counts["COLLECT_OUTCOMES_AND_MARKET_CONTEXT"],
            "collect_outcome_labels": counts["COLLECT_OUTCOME_LABELS"],
            "collect_more_wallet_evidence": counts["COLLECT_MORE_WALLET_EVIDENCE"],
            "manual_risk_review": counts["MANUAL_RISK_REVIEW"],
            "resolved_excluded": len(as_list(audit.get("resolved_candidates"))),
        },
        "targets": returned,
        "operator_note": "Review-only collection plan. Use this to gather evidence for insufficient/risk-blocked wallets before changing trust tiers.",
    }
