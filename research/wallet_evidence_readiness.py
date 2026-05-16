from __future__ import annotations

import time
from typing import Any


MODE = "WALLET_EVIDENCE_STAGE3_READINESS_REVIEW_ONLY"
READINESS_VERSION = "wallet_evidence_readiness.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def percent(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate_row(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def failed_gate_name(gate_name: str) -> str:
    aliases = {
        "live_execution_locked": "live_execution_not_locked",
        "wallet_history_targets_processed": "wallet_history_targets_unprocessed",
        "wallet_history_has_no_blocked_wallets": "wallet_history_has_blocked_wallets",
        "evidence_file_has_no_duplicates": "evidence_file_has_duplicates",
        "enrichment_matches_evidence_file": "enrichment_stale",
        "market_context_gaps_are_explicit": "market_context_gaps_not_explicit",
        "candidate_review_queue_exists": "candidate_review_queue_empty",
    }
    return aliases.get(gate_name, gate_name)


def build_wallet_evidence_readiness_report(
    *,
    candidate_backfill_targets: dict[str, Any],
    wallet_history_backfill: dict[str, Any],
    wallet_evidence_enrichment: dict[str, Any],
    wallet_missing_market_context: dict[str, Any],
    trusted_historical_market_context: dict[str, Any],
    evidence_duplicate_count: int = 0,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    target_summary = as_dict(candidate_backfill_targets.get("summary"))
    history_summary = as_dict(wallet_history_backfill.get("summary"))
    enrichment_summary = as_dict(wallet_evidence_enrichment.get("summary"))
    missing_context_summary = as_dict(wallet_missing_market_context.get("summary"))
    trusted_summary = as_dict(trusted_historical_market_context.get("summary"))

    needs_wallet_history = safe_int(target_summary.get("needs_wallet_history"))
    risk_review = safe_int(target_summary.get("risk_review"))
    wallets_processed = safe_int(history_summary.get("wallets_processed"))
    wallets_blocked = safe_int(history_summary.get("wallets_blocked"))
    ready_for_candidate_review = safe_int(history_summary.get("ready_for_candidate_review"))
    evidence_total_after_merge = safe_int(wallet_history_backfill.get("evidence_total_rows_after_merge"))
    enriched_rows = safe_int(enrichment_summary.get("total_evidence_rows"))
    rows_with_entry_context = safe_int(enrichment_summary.get("rows_with_entry_context"))
    rows_with_known_outcome = safe_int(enrichment_summary.get("rows_with_known_outcome"))
    missing_market_context_rows = safe_int(missing_context_summary.get("missing_market_context_rows"))
    score_ready_records = safe_int(trusted_summary.get("score_ready_records"))
    trusted_records_scanned = safe_int(trusted_summary.get("records_scanned"))

    gates = [
        gate_row(
            "live_execution_locked",
            candidate_backfill_targets.get("live_execution_locked") is True
            and wallet_history_backfill.get("live_execution_locked") is True
            and wallet_evidence_enrichment.get("live_execution_locked") is True
            and wallet_missing_market_context.get("live_execution_locked") is True
            and trusted_historical_market_context.get("live_execution_locked") is True,
            "Stage 3 evidence work must remain review-only with live execution locked.",
        ),
        gate_row(
            "wallet_history_targets_processed",
            needs_wallet_history > 0 and wallets_processed >= needs_wallet_history,
            "All current wallet-history collection targets must be processed or explicitly blocked.",
        ),
        gate_row(
            "wallet_history_has_no_blocked_wallets",
            wallets_processed > 0 and wallets_blocked == 0,
            "The current collection pass should not leave RPC or missing-data wallet blockers unclassified.",
        ),
        gate_row(
            "evidence_file_has_no_duplicates",
            safe_int(evidence_duplicate_count) == 0 and evidence_total_after_merge > 0,
            "Wallet evidence must be idempotent so repeated runs do not inflate wallet quality.",
        ),
        gate_row(
            "enrichment_matches_evidence_file",
            enriched_rows == evidence_total_after_merge and enriched_rows > 0,
            "Enrichment must be rebuilt from the current merged evidence file.",
        ),
        gate_row(
            "market_context_gaps_are_explicit",
            missing_market_context_rows > 0 or score_ready_records > 0,
            "Missing market context must be reported explicitly instead of hidden.",
        ),
        gate_row(
            "candidate_review_queue_exists",
            ready_for_candidate_review > 0,
            "Collected wallet evidence should produce review candidates before trust changes.",
        ),
    ]
    passed_gates = [gate["name"] for gate in gates if gate["passed"]]
    failed_gates = [failed_gate_name(gate["name"]) for gate in gates if not gate["passed"]]

    evidence_rows = max(1, enriched_rows)
    wallet_score_readiness_pct = min(
        percent(rows_with_entry_context, evidence_rows),
        percent(rows_with_known_outcome, evidence_rows),
        percent(score_ready_records, trusted_records_scanned),
    )
    evidence_gaps = evidence_gap_rows(
        risk_review=risk_review,
        rows_with_known_outcome=rows_with_known_outcome,
        enriched_rows=enriched_rows,
        missing_market_context_rows=missing_market_context_rows,
        score_ready_records=score_ready_records,
        trusted_records_scanned=trusted_records_scanned,
    )

    contract_pct = percent(len(passed_gates), len(gates))
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "readiness_version": READINESS_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": (
            "Stage 3 evidence collection contract is complete; wallet scores remain data-limited."
            if contract_pct == 100 and evidence_gaps
            else "Stage 3 evidence collection and score readiness are complete."
            if contract_pct == 100
            else "Stage 3 evidence collection contract is incomplete; inspect failed gates."
        ),
        "summary": {
            "stage3_evidence_contract_completion_pct": contract_pct,
            "wallet_score_readiness_pct": wallet_score_readiness_pct,
            "candidate_targets": safe_int(target_summary.get("total_targets")),
            "wallet_history_targets": needs_wallet_history,
            "wallets_processed": wallets_processed,
            "wallets_blocked": wallets_blocked,
            "ready_for_candidate_review": ready_for_candidate_review,
            "evidence_rows": evidence_total_after_merge,
            "evidence_duplicate_count": safe_int(evidence_duplicate_count),
            "unique_wallets": safe_int(enrichment_summary.get("unique_wallets")),
            "unique_mints": safe_int(enrichment_summary.get("unique_mints")),
            "rows_with_entry_context": rows_with_entry_context,
            "rows_with_known_outcome": rows_with_known_outcome,
            "missing_market_context_rows": missing_market_context_rows,
            "score_ready_market_context_records": score_ready_records,
            "risk_review_targets": risk_review,
        },
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "gates": gates,
        "evidence_gaps": evidence_gaps,
        "next_required_actions": next_required_actions(failed_gates=failed_gates, evidence_gaps=evidence_gaps),
    }


def evidence_gap_rows(
    *,
    risk_review: int,
    rows_with_known_outcome: int,
    enriched_rows: int,
    missing_market_context_rows: int,
    score_ready_records: int,
    trusted_records_scanned: int,
) -> list[str]:
    gaps: list[str] = []
    if risk_review > 0:
        gaps.append("risk_review_remaining")
    if percent(rows_with_known_outcome, max(1, enriched_rows)) < 70:
        gaps.append("low_known_outcome_coverage")
    if missing_market_context_rows > 0:
        gaps.append("missing_market_context")
    if trusted_records_scanned > 0 and score_ready_records == 0:
        gaps.append("no_score_ready_market_context")
    return gaps


def next_required_actions(*, failed_gates: list[str], evidence_gaps: list[str]) -> list[str]:
    actions: list[str] = []
    if failed_gates:
        actions.append("Repair failed Stage 3 evidence gates before interpreting wallet-quality metrics.")
    if "risk_review_remaining" in evidence_gaps:
        actions.append("Resolve risk-review wallets before allowing them into candidate-review or promotion queues.")
    if "low_known_outcome_coverage" in evidence_gaps:
        actions.append("Backfill later outcome labels so wallet evidence can measure runner/rug participation honestly.")
    if "missing_market_context" in evidence_gaps or "no_score_ready_market_context" in evidence_gaps:
        actions.append("Recover decision-time market context and archival supply before using wallet evidence for scoring.")
    if not actions:
        actions.append("Promote Stage 3 evidence into review-only wallet confidence comparisons.")
    return actions
