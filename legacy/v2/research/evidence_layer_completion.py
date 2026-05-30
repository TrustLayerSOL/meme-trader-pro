from __future__ import annotations

import time
from typing import Any


MODE = "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY"


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


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def build_evidence_layer_completion_report(
    *,
    wallet_evidence_readiness: dict[str, Any],
    wallet_evidence_scorecard: dict[str, Any],
    recovery_closeout: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    readiness_summary = as_dict(wallet_evidence_readiness.get("summary"))
    scorecard_summary = as_dict(wallet_evidence_scorecard.get("summary"))
    closeout_summary = as_dict(recovery_closeout.get("summary"))
    next_action_counts = as_dict(recovery_closeout.get("next_action_counts"))

    readiness_contract_pct = safe_int(readiness_summary.get("stage3_evidence_contract_completion_pct"))
    scorecard_contract_pct = safe_int(scorecard_summary.get("stage3_engine_completion_pct"))
    evidence_rows = safe_int(readiness_summary.get("evidence_rows"))
    duplicate_count = safe_int(readiness_summary.get("evidence_duplicate_count"))
    wallets_blocked = safe_int(readiness_summary.get("wallets_blocked"))
    still_blocked_wallets = safe_int(closeout_summary.get("still_blocked_wallets"))
    needs_outcome_labels = safe_int(closeout_summary.get("needs_outcome_labels"))
    needs_market_context = safe_int(closeout_summary.get("needs_market_context"))
    needs_transaction_linkage = safe_int(closeout_summary.get("needs_transaction_linkage"))

    gates = [
        gate(
            "live_execution_locked",
            wallet_evidence_readiness.get("live_execution_locked") is True
            and wallet_evidence_scorecard.get("live_execution_locked") is True
            and recovery_closeout.get("live_execution_locked") is True,
            "Evidence completion must remain review-only with live execution locked.",
        ),
        gate(
            "wallet_evidence_contract_complete",
            readiness_contract_pct == 100,
            "Stage 3 evidence collection contract must be complete before the Evidence Layer can close.",
        ),
        gate(
            "wallet_evidence_scorecard_complete",
            scorecard_contract_pct == 100,
            "The integrated evidence scorecard must be built and current.",
        ),
        gate(
            "evidence_rows_present",
            evidence_rows > 0,
            "The layer needs actual wallet evidence rows, not only empty reports.",
        ),
        gate(
            "evidence_rows_deduped",
            duplicate_count == 0,
            "Wallet evidence rows must be idempotent and deduplicated.",
        ),
        gate(
            "wallet_history_not_blocked",
            wallets_blocked == 0,
            "Wallet-history collection blockers must be resolved or moved into explicit downstream blockers.",
        ),
        gate(
            "classified_outcome_label_gap",
            needs_outcome_labels > 0 and (
                safe_int(next_action_counts.get("BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS"))
                + safe_int(next_action_counts.get("BACKFILL_OUTCOME_LABELS"))
                >= needs_outcome_labels
            ),
            "Outcome-label gaps must be explicit and assigned to exact next actions.",
        ),
        gate(
            "classified_market_context_gap",
            needs_market_context > 0 and safe_int(next_action_counts.get("BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS")) >= needs_market_context,
            "Market-context gaps must be explicit and assigned to exact next actions.",
        ),
        gate(
            "transaction_linkage_not_blocking",
            needs_transaction_linkage == 0,
            "Transaction linkage cannot be an unresolved hidden blocker.",
        ),
        gate(
            "trust_changes_blocked_until_quality_improves",
            safe_int(scorecard_summary.get("trusted_promotions_allowed")) == 0,
            "Wallet trust must remain locked while score-ready evidence is incomplete.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    completion_pct = int(round((len(passed) / max(1, len(gates))) * 100))
    residual = residual_blockers(
        needs_outcome_labels=needs_outcome_labels,
        needs_market_context=needs_market_context,
        still_blocked_wallets=still_blocked_wallets,
        readiness_gaps=as_list(wallet_evidence_readiness.get("evidence_gaps")),
        score_ready_market_context_records=safe_int(readiness_summary.get("score_ready_market_context_records")),
    )
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "evidence_layer_completion_pct": completion_pct,
            "wallet_score_readiness_pct": safe_int(readiness_summary.get("wallet_score_readiness_pct")),
            "evidence_rows": evidence_rows,
            "rows_with_known_outcome": safe_int(readiness_summary.get("rows_with_known_outcome")),
            "score_ready_market_context_records": safe_int(readiness_summary.get("score_ready_market_context_records")),
            "remaining_blocked_wallets": still_blocked_wallets,
            "needs_outcome_labels": needs_outcome_labels,
            "needs_market_context": needs_market_context,
            "needs_transaction_linkage": needs_transaction_linkage,
            "trusted_promotions_allowed": safe_int(scorecard_summary.get("trusted_promotions_allowed")),
        },
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "residual_data_blockers": residual,
        "operator_note": (
            "Evidence Layer is complete when every evidence gap is captured, deduped, classified, and routed. "
            "This does not mean wallet scores are trusted; score readiness remains blocked until outcome labels and score-ready market context exist."
        ),
        "next_required_actions": next_actions(residual),
    }


def residual_blockers(
    *,
    needs_outcome_labels: int,
    needs_market_context: int,
    still_blocked_wallets: int,
    readiness_gaps: list[Any],
    score_ready_market_context_records: int,
) -> list[str]:
    blockers: list[str] = []
    if needs_outcome_labels > 0 or "low_known_outcome_coverage" in readiness_gaps:
        blockers.append("outcome_labels_require_new_or_unrecovered_history")
    if needs_market_context > 0 or "missing_market_context" in readiness_gaps:
        blockers.append("decision_time_market_context_requires_reconstruction")
    if score_ready_market_context_records == 0:
        blockers.append("score_ready_market_context_absent")
    if still_blocked_wallets > 0:
        blockers.append("wallet_trust_changes_blocked")
    return blockers


def next_actions(residual: list[str]) -> list[str]:
    actions: list[str] = []
    if "outcome_labels_require_new_or_unrecovered_history" in residual:
        actions.append("Recover later outcome labels from replay-safe historical token timelines or new forward observations.")
    if "decision_time_market_context_requires_reconstruction" in residual:
        actions.append("Move blocked rows into the replayable token timeline lane for price/liquidity/market-cap reconstruction.")
    if "score_ready_market_context_absent" in residual:
        actions.append("Do not use wallet scores for trust changes until score-ready market context exists.")
    if "wallet_trust_changes_blocked" in residual:
        actions.append("Keep promotion/demotion locked behind human review and evidence gates.")
    if not actions:
        actions.append("Proceed to wallet candidate review with current evidence gates.")
    return actions
