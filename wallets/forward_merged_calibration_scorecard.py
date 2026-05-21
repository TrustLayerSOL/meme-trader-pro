from __future__ import annotations

import time
from typing import Any

from wallets.forward_calibration_scorecard import build_forward_calibration_scorecard
from wallets.forward_calibration_scorecard import safe_int


MODE = "FORWARD_MERGED_CALIBRATION_SCORECARD_REVIEW_ONLY"
VERSION = "forward_merged_calibration_scorecard.v1"


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def merge_records(original_records: list[dict[str, Any]], repaired_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    repaired_by_event = {
        event_id(row): row
        for row in repaired_records or []
        if isinstance(row, dict) and event_id(row)
    }
    merged: list[dict[str, Any]] = []
    replaced = 0
    seen_repaired: set[str] = set()
    for row in original_records or []:
        if not isinstance(row, dict):
            continue
        row_event = event_id(row)
        if row_event and row_event in repaired_by_event:
            merged.append(repaired_by_event[row_event])
            seen_repaired.add(row_event)
            replaced += 1
        else:
            merged.append(row)
    for row_event, row in repaired_by_event.items():
        if row_event not in seen_repaired:
            merged.append(row)
    return merged, replaced


def build_summary(
    *,
    original_records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]],
    merged_records: list[dict[str, Any]],
    replaced: int,
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    score_summary = scorecard.get("summary") if isinstance(scorecard.get("summary"), dict) else {}
    return {
        "original_records": len(original_records or []),
        "repaired_records": len(repaired_records or []),
        "replaced_original_blocked_records": replaced,
        "merged_records": len(merged_records),
        "wallets": safe_int(score_summary.get("wallets")),
        "known_15m_outcomes": safe_int(score_summary.get("known_15m_outcomes")),
        "runner_15m_outcomes": safe_int(score_summary.get("runner_15m_outcomes")),
        "rug_15m_outcomes": safe_int(score_summary.get("rug_15m_outcomes")),
        "dead_15m_outcomes": safe_int(score_summary.get("dead_15m_outcomes")),
        "loser_15m_outcomes": safe_int(score_summary.get("loser_15m_outcomes")),
        "flat_15m_outcomes": safe_int(score_summary.get("flat_15m_outcomes")),
        "blocked_records": safe_int(score_summary.get("blocked_records")),
        "review_behavioral_signal_wallets": safe_int(score_summary.get("review_behavioral_signal_wallets")),
        "risk_review_candidate_wallets": safe_int(score_summary.get("risk_review_candidate_wallets")),
        "flat_noise_candidate_wallets": safe_int(score_summary.get("flat_noise_candidate_wallets")),
        "blocked_missing_context_wallets": safe_int(score_summary.get("blocked_missing_context_wallets")),
        "collect_more_forward_evidence_wallets": safe_int(score_summary.get("collect_more_forward_evidence_wallets")),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_merged_calibration_scorecard(
    *,
    original_records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    merged, replaced = merge_records(original_records, repaired_records)
    scorecard = build_forward_calibration_scorecard(merged, generated_at=generated_at)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(
            original_records=original_records,
            repaired_records=repaired_records,
            merged_records=merged,
            replaced=replaced,
            scorecard=scorecard,
        ),
        "scorecard": scorecard,
        "operator_note": (
            "Merged forward calibration is review-only. Repaired rows replace matching blocked rows by event_id "
            "for analysis only; wallet trust, wallet lists, and execution remain locked."
        ),
    }
