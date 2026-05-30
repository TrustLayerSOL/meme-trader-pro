from __future__ import annotations

import time
from collections import Counter
from typing import Any


MARKET_CONTEXT_BLOCKER = "missing_decision_time_market_context"
OUTCOME_LABEL_BLOCKER = "missing_outcome_labels"
TRANSACTION_BLOCKER = "blocked_missing_transaction"
LOW_CONFIDENCE_BLOCKER = "blocked_low_confidence"
MANUAL_RISK_BLOCKER = "manual_risk_review"


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


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _next_action(blockers: set[str]) -> str:
    if not blockers:
        return "READY_FOR_CANDIDATE_REVIEW"
    if MARKET_CONTEXT_BLOCKER in blockers and OUTCOME_LABEL_BLOCKER in blockers:
        return "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS"
    if MARKET_CONTEXT_BLOCKER in blockers:
        return "BACKFILL_MARKET_CONTEXT"
    if OUTCOME_LABEL_BLOCKER in blockers:
        return "BACKFILL_OUTCOME_LABELS"
    if TRANSACTION_BLOCKER in blockers:
        return "LINK_TRANSACTION_ARTIFACTS"
    if MANUAL_RISK_BLOCKER in blockers:
        return "MANUAL_RISK_REVIEW"
    if LOW_CONFIDENCE_BLOCKER in blockers:
        return "KEEP_BLOCKED_LOW_CONFIDENCE"
    return "KEEP_BLOCKED_REVIEW_REQUIRED"


def _priority(action: str) -> int:
    order = {
        "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": 0,
        "BACKFILL_MARKET_CONTEXT": 1,
        "BACKFILL_OUTCOME_LABELS": 2,
        "LINK_TRANSACTION_ARTIFACTS": 3,
        "MANUAL_RISK_REVIEW": 4,
        "KEEP_BLOCKED_LOW_CONFIDENCE": 5,
        "KEEP_BLOCKED_REVIEW_REQUIRED": 6,
        "READY_FOR_CANDIDATE_REVIEW": 7,
    }
    return order.get(action, 99)


def _closeout_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = as_dict(row.get("existing_evidence"))
    blockers = {_clean_str(blocker) for blocker in as_list(row.get("remaining_blockers")) if _clean_str(blocker)}
    action = _next_action(blockers)
    return {
        "wallet": row.get("wallet"),
        "source_bucket": row.get("source_bucket") or "unknown",
        "next_action": action,
        "remaining_blockers": sorted(blockers),
        "can_auto_apply": False,
        "wallet_list_apply_allowed": False,
        "evidence_snapshot": {
            "total_rows": safe_int(evidence.get("total_rows")),
            "rows_with_entry_context": safe_int(evidence.get("rows_with_entry_context")),
            "rows_with_known_outcomes": safe_int(evidence.get("rows_with_known_outcomes")),
            "missing_market_context_rows": safe_int(evidence.get("missing_market_context_rows")),
            "missing_outcome_label_rows": safe_int(evidence.get("missing_outcome_label_rows")),
            "linked_transaction_count": len(as_list(evidence.get("linked_transactions"))),
            "linked_mint_count": len(as_list(evidence.get("linked_mints"))),
        },
        "evidence_confidence": as_dict(row.get("confidence")).get("evidence_confidence") or "unknown",
        "replay_confidence": as_dict(row.get("confidence")).get("replay_confidence") or "unknown",
        "operator_note": _operator_note(action),
    }


def _operator_note(action: str) -> str:
    notes = {
        "BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS": "Needs both decision-time market context and later outcome labels before trust review.",
        "BACKFILL_MARKET_CONTEXT": "Needs decision-time market context before wallet evidence can be scored.",
        "BACKFILL_OUTCOME_LABELS": "Needs later outcome labels before wallet behavior can be evaluated.",
        "LINK_TRANSACTION_ARTIFACTS": "Needs transaction linkage before evidence can be trusted.",
        "MANUAL_RISK_REVIEW": "Needs manual risk review before any trust change.",
        "KEEP_BLOCKED_LOW_CONFIDENCE": "Existing evidence is too weak for trust changes.",
        "READY_FOR_CANDIDATE_REVIEW": "Evidence is reviewable, but this report still does not approve or apply trust changes.",
    }
    return notes.get(action, "Needs additional review before any trust change.")


def build_wallet_candidate_context_recovery_closeout(
    *,
    recovery_runner: dict[str, Any],
    generated_at: float | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    rows = [
        _closeout_row(row)
        for row in as_list(as_dict(recovery_runner).get("wallets"))
        if isinstance(row, dict) and row.get("wallet")
    ]
    action_counts = Counter(row["next_action"] for row in rows)
    blocker_counts: Counter[str] = Counter()
    for row in rows:
        blocker_counts.update(row["remaining_blockers"])
    rows.sort(key=lambda row: (
        _priority(row["next_action"]),
        -safe_int(row["evidence_snapshot"]["total_rows"]),
        str(row.get("wallet") or ""),
    ))
    capped = rows[: int(limit)]
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "wallets_reviewed": len(rows),
            "needs_market_context": blocker_counts[MARKET_CONTEXT_BLOCKER],
            "needs_outcome_labels": blocker_counts[OUTCOME_LABEL_BLOCKER],
            "needs_transaction_linkage": blocker_counts[TRANSACTION_BLOCKER],
            "needs_low_confidence_review": blocker_counts[LOW_CONFIDENCE_BLOCKER],
            "needs_manual_risk_review": blocker_counts[MANUAL_RISK_BLOCKER],
            "ready_for_candidate_review": action_counts["READY_FOR_CANDIDATE_REVIEW"],
            "still_blocked_wallets": len(rows) - action_counts["READY_FOR_CANDIDATE_REVIEW"],
        },
        "next_action_counts": dict(action_counts),
        "remaining_blocker_counts": dict(blocker_counts),
        "count": len(capped),
        "wallets": capped,
        "operator_note": "Read-only Stage 4 closeout. It classifies blocked recovery-runner wallets into exact next actions; it does not approve, promote, demote, trade, fetch external data, or mutate wallet lists.",
    }
