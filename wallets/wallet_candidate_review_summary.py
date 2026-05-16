from __future__ import annotations

import time
from collections import Counter
from typing import Any


ACTIONABLE_ACTIONS = {"PROMOTION_REVIEW", "DEMOTION_REVIEW"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _wallet_card(row: dict[str, Any]) -> dict[str, Any]:
    evidence = as_dict(row.get("evidence"))
    gates = as_dict(row.get("evidence_gates"))
    return {
        "wallet": row.get("wallet"),
        "recommendation_action": row.get("recommendation_action"),
        "audit_status": row.get("audit_status"),
        "evidence_source": evidence.get("source"),
        "source_bucket": evidence.get("source_bucket"),
        "scorecard_next_action": evidence.get("scorecard_next_action"),
        "stage4_action": gates.get("stage4_action"),
        "known_outcomes": safe_int(evidence.get("known_outcomes")),
        "round_trip_lifecycles": safe_int(evidence.get("round_trip_lifecycles")),
        "runner_participation": evidence.get("runner_participation"),
        "rug_participation": evidence.get("rug_participation"),
        "notes": [str(note) for note in as_list(row.get("audit_notes"))[:3]],
    }


def _bucketed_cards(rows: list[dict[str, Any]], *, limit: int) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "actionable_review": [],
        "risk_review_required": [],
        "insufficient_evidence": [],
        "other_review": [],
    }
    for row in rows:
        action = str(row.get("recommendation_action") or "")
        status = str(row.get("audit_status") or "")
        if action in ACTIONABLE_ACTIONS and status == "HUMAN_REVIEW_REQUIRED":
            buckets["actionable_review"].append(_wallet_card(row))
        elif status == "RISK_REVIEW_REQUIRED" or action == "RISK_REVIEW_REQUIRED":
            buckets["risk_review_required"].append(_wallet_card(row))
        elif status == "INSUFFICIENT_EVIDENCE":
            buckets["insufficient_evidence"].append(_wallet_card(row))
        else:
            buckets["other_review"].append(_wallet_card(row))
    return {name: cards[: int(limit)] for name, cards in buckets.items()}


def build_wallet_candidate_review_summary(
    candidate_audit: dict[str, Any],
    decision_prep: dict[str, Any] | None = None,
    *,
    generated_at: float | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    audit = as_dict(candidate_audit)
    prep = as_dict(decision_prep)
    rows = [row for row in as_list(audit.get("candidates")) if isinstance(row, dict)]
    resolved_rows = [row for row in as_list(audit.get("resolved_candidates")) if isinstance(row, dict)]
    action_counts = Counter(str(row.get("recommendation_action") or "UNKNOWN") for row in rows)
    status_counts = Counter(str(row.get("audit_status") or "UNKNOWN") for row in rows)
    actionable_count = sum(
        1 for row in rows
        if str(row.get("recommendation_action") or "") in ACTIONABLE_ACTIONS
        and str(row.get("audit_status") or "") == "HUMAN_REVIEW_REQUIRED"
    )
    risk_review_count = sum(
        1 for row in rows
        if str(row.get("recommendation_action") or "") == "RISK_REVIEW_REQUIRED"
        or str(row.get("audit_status") or "") == "RISK_REVIEW_REQUIRED"
    )
    bucketed = _bucketed_cards(rows, limit=limit)
    resolved = [_wallet_card(row) for row in resolved_rows[: int(limit)]]
    draft_summary = as_dict(prep.get("summary"))
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "candidates": len(rows),
            "resolved_candidates": len(resolved_rows),
            "actionable_review": actionable_count,
            "risk_review_required": risk_review_count,
            "insufficient_evidence": status_counts.get("INSUFFICIENT_EVIDENCE", 0),
            "draft_proposed_decisions": safe_int(draft_summary.get("proposed_decisions")),
            "draft_blocked_candidates": safe_int(draft_summary.get("blocked_candidates")),
        },
        "action_counts": dict(action_counts),
        "status_counts": dict(status_counts),
        "buckets": bucketed,
        "resolved_candidates": resolved,
        "operator_note": "Review-only summary. Use this to decide what needs risk review or more data before recording explicit wallet decisions.",
    }
