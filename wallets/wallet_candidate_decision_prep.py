from __future__ import annotations

import time
from typing import Any


ACTION_TO_DECISION = {
    "PROMOTION_REVIEW": "approve_promotion",
    "DEMOTION_REVIEW": "approve_demotion",
}


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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _selected_set(selected_wallets: list[str] | None) -> set[str] | None:
    if selected_wallets is None:
        return None
    selected = {str(wallet).strip() for wallet in selected_wallets if str(wallet).strip()}
    return selected


def _candidate_block_reason(row: dict[str, Any]) -> str | None:
    if row.get("review_resolved"):
        return "review_already_resolved"
    action = str(row.get("recommendation_action") or "")
    if action not in ACTION_TO_DECISION:
        return "not_actionable_review_action"
    if row.get("audit_status") != "HUMAN_REVIEW_REQUIRED":
        return "not_human_review_required"
    return None


def proposed_decision_for_candidate(row: dict[str, Any], *, reviewed_by: str = "operator") -> dict[str, Any] | None:
    wallet = str(row.get("wallet") or "").strip()
    if not wallet:
        return None
    decision = ACTION_TO_DECISION.get(str(row.get("recommendation_action") or ""))
    if not decision:
        return None
    evidence = as_dict(row.get("evidence"))
    gates = as_dict(row.get("evidence_gates"))
    reasons = evidence.get("recommendation_reasons") if isinstance(evidence.get("recommendation_reasons"), list) else []
    audit_notes = row.get("audit_notes") if isinstance(row.get("audit_notes"), list) else []
    note_parts = [str(reason) for reason in reasons[:3]]
    if not note_parts:
        note_parts = [str(note) for note in audit_notes[:3]]
    return {
        "wallet": wallet,
        "decision": decision,
        "approved": False,
        "requires_operator_approval": True,
        "approved_by": reviewed_by,
        "source": "wallet_candidate_decision_prep",
        "candidate_recommendation_action": row.get("recommendation_action"),
        "candidate_audit_status": row.get("audit_status"),
        "candidate_source": evidence.get("source") or "wallet_candidate_audit",
        "note": "; ".join(note_parts),
        "evidence_snapshot": {
            "known_outcomes": safe_int(evidence.get("known_outcomes")),
            "runner_participation": safe_float(evidence.get("runner_participation")),
            "rug_participation": safe_float(evidence.get("rug_participation")),
            "runner_participation_rate": safe_float(evidence.get("runner_participation_rate")),
            "rug_participation_rate": safe_float(evidence.get("rug_participation_rate")),
            "round_trip_lifecycles": safe_int(evidence.get("round_trip_lifecycles")),
            "source_bucket": evidence.get("source_bucket"),
            "stage4_action": gates.get("stage4_action"),
            "source_coverage": safe_float(gates.get("source_coverage")),
        },
    }


def build_wallet_candidate_decision_prep(
    candidate_audit: dict[str, Any],
    *,
    selected_wallets: list[str] | None = None,
    reviewed_by: str = "operator",
    generated_at: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    audit = as_dict(candidate_audit)
    selected = _selected_set(selected_wallets)
    proposed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    scanned = 0
    for row in as_list(audit.get("candidates")):
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if not wallet:
            continue
        if selected is not None and wallet not in selected:
            continue
        scanned += 1
        reason = _candidate_block_reason(row)
        if reason:
            blocked.append({
                "wallet": wallet,
                "reason": reason,
                "recommendation_action": row.get("recommendation_action"),
                "audit_status": row.get("audit_status"),
            })
            continue
        decision = proposed_decision_for_candidate(row, reviewed_by=reviewed_by)
        if decision:
            proposed.append(decision)
        else:
            blocked.append({
                "wallet": wallet,
                "reason": "decision_record_not_buildable",
                "recommendation_action": row.get("recommendation_action"),
                "audit_status": row.get("audit_status"),
            })

    proposed_total = len(proposed)
    blocked_total = len(blocked)
    returned_proposed = proposed[: int(limit)]
    returned_blocked = blocked[: int(limit)]
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "source": "wallet_candidate_audit",
        "selected_wallets": sorted(selected) if selected is not None else [],
        "summary": {
            "audit_candidates": safe_int(as_dict(audit.get("counts")).get("candidates"), len(as_list(audit.get("candidates")))),
            "scanned_candidates": scanned,
            "proposed_decisions": proposed_total,
            "blocked_candidates": blocked_total,
            "returned_proposed_decisions": len(returned_proposed),
            "returned_blocked_candidates": len(returned_blocked),
            "approve_promotion": len([row for row in proposed if row.get("decision") == "approve_promotion"]),
            "approve_demotion": len([row for row in proposed if row.get("decision") == "approve_demotion"]),
        },
        "proposed_decisions": returned_proposed,
        "blocked_candidates": returned_blocked,
        "operator_note": "Draft-only decision records. They are not approved and cannot mutate wallet lists until an operator explicitly records approval and runs the separate apply guard.",
    }
