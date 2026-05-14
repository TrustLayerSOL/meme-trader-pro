from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.wallet_promotion_engine import MIN_KNOWN_OUTCOMES


REVIEW_ACTIONS = {"PROMOTION_REVIEW", "DEMOTION_REVIEW"}


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
        return int(value)
    except (TypeError, ValueError):
        return default


def ledger_wallets(outcome_ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = as_dict(outcome_ledger).get("wallets")
    if isinstance(rows, dict):
        return {str(wallet): row for wallet, row in rows.items() if isinstance(row, dict)}
    if isinstance(rows, list):
        return {str(row.get("wallet")): row for row in rows if isinstance(row, dict) and row.get("wallet")}
    return {}


def comparison_by_wallet(baseline_comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = as_dict(baseline_comparison).get("wallets")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("wallet")): row for row in rows if isinstance(row, dict) and row.get("wallet")}


def candidate_row(wallet: str, ledger_row: dict[str, Any], comparison_row: dict[str, Any] | None = None) -> dict[str, Any]:
    recommendation = as_dict(ledger_row.get("recommendation"))
    action = str(recommendation.get("action") or "HOLD_MORE_DATA")
    known = safe_int(ledger_row.get("known_outcomes"))
    total = safe_int(ledger_row.get("total_signals"))
    sample_passed = known >= MIN_KNOWN_OUTCOMES
    source_coverage = round(known / total, 4) if total else 0.0
    audit_notes: list[str] = []
    if not sample_passed:
        audit_notes.append("known outcome sample below audit threshold")
    if source_coverage < 0.5:
        audit_notes.append("less than half of observed signals have known outcomes")
    if not audit_notes:
        audit_notes.append("review recommendation has enough known outcomes for human audit")

    return {
        "wallet": wallet,
        "recommendation_action": action,
        "audit_status": "HUMAN_REVIEW_REQUIRED" if sample_passed else "INSUFFICIENT_EVIDENCE",
        "review_only": True,
        "wallet_list_apply_allowed": False,
        "comparison_status": as_dict(comparison_row).get("comparison_status"),
        "evidence_gates": {
            "known_outcome_sample_passed": sample_passed,
            "minimum_known_outcomes": MIN_KNOWN_OUTCOMES,
            "source_coverage": source_coverage,
            "recommendation_is_review_only": bool(recommendation.get("review_only", True)),
        },
        "evidence": {
            "total_signals": total,
            "accepted_signals": safe_int(ledger_row.get("accepted_signals")),
            "rejected_or_observed_signals": safe_int(ledger_row.get("rejected_signals")),
            "known_outcomes": known,
            "runner_participation": safe_int(ledger_row.get("runner_participation")),
            "rug_participation": safe_int(ledger_row.get("rug_participation")),
            "dead_participation": safe_int(ledger_row.get("dead_participation")),
            "runner_participation_rate": safe_float(ledger_row.get("runner_participation_rate")),
            "rug_participation_rate": safe_float(ledger_row.get("rug_participation_rate")),
            "average_pnl_after_signal": ledger_row.get("average_pnl_after_signal"),
            "promotion_score": ledger_row.get("promotion_score"),
            "demotion_score": ledger_row.get("demotion_score"),
            "confidence": as_dict(ledger_row.get("confidence")),
            "recommendation_reasons": recommendation.get("reasons") if isinstance(recommendation.get("reasons"), list) else [],
        },
        "audit_notes": audit_notes,
    }


def build_wallet_candidate_audit(
    *,
    outcome_ledger: dict[str, Any],
    baseline_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = ledger_wallets(outcome_ledger)
    comparisons = comparison_by_wallet(as_dict(baseline_comparison))
    candidates = []
    for wallet, row in ledger.items():
        action = str(as_dict(row.get("recommendation")).get("action") or "")
        if action in REVIEW_ACTIONS:
            candidates.append(candidate_row(wallet, row, comparisons.get(wallet)))

    candidates.sort(
        key=lambda row: (
            action_rank(row["recommendation_action"]),
            row["evidence"]["known_outcomes"],
            safe_float(row["evidence"].get("average_pnl_after_signal")),
            row["wallet"],
        ),
        reverse=True,
    )
    counts = Counter(row["recommendation_action"] for row in candidates)
    audit_counts = Counter(row["audit_status"] for row in candidates)
    return {
        "generated_at": time.time(),
        "mode": "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "counts": {
            "candidates": len(candidates),
            "promotion_review": counts.get("PROMOTION_REVIEW", 0),
            "demotion_review": counts.get("DEMOTION_REVIEW", 0),
            "human_review_required": audit_counts.get("HUMAN_REVIEW_REQUIRED", 0),
            "insufficient_evidence": audit_counts.get("INSUFFICIENT_EVIDENCE", 0),
        },
        "candidates": candidates,
    }


def action_rank(action: str) -> int:
    return {"PROMOTION_REVIEW": 20, "DEMOTION_REVIEW": 10}.get(str(action), 0)
