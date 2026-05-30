from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "WALLET_STAGE4_PROMOTION_DEMOTION_REVIEW_ONLY"
STAGE4_VERSION = "wallet_stage4_review.v1"
MIN_KNOWN_OUTCOMES_FOR_PROMOTION = 20
MIN_ROUND_TRIPS_FOR_PROMOTION = 3


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def evidence_counts(row: dict[str, Any]) -> dict[str, int]:
    enrichment = as_dict(row.get("enrichment"))
    lifecycle = as_dict(row.get("lifecycle"))
    return {
        "known_outcome_rows": safe_int(enrichment.get("known_outcome_rows")),
        "rug_rows": safe_int(enrichment.get("rug_rows")),
        "runner_rows": safe_int(enrichment.get("runner_rows")),
        "missing_market_context_rows": safe_int(enrichment.get("missing_market_context_rows")),
        "round_trip_lifecycles": safe_int(lifecycle.get("round_trip_lifecycles")),
        "lifecycle_mints": safe_int(lifecycle.get("lifecycle_mints")),
    }


def blockers(row: dict[str, Any]) -> list[str]:
    values = row.get("evidence_blockers")
    return [str(value) for value in values] if isinstance(values, list) else []


def stage4_action(row: dict[str, Any]) -> tuple[str, list[str]]:
    bucket = str(row.get("recommendation_bucket") or "observe_more")
    promotion_gate = str(row.get("promotion_gate") or "do_not_promote_yet")
    counts = evidence_counts(row)
    row_blockers = blockers(row)
    reasons: list[str] = []

    if bucket == "risk_review" or "manual_risk_review_required" in row_blockers:
        return "RISK_REVIEW_REQUIRED", ["manual risk review is required before wallet-list changes"]

    if bucket == "hold_no_edge" or "held_for_negative_or_rug_evidence" in row_blockers:
        return "DEMOTION_OR_BLOCK_REVIEW", ["wallet is held out by negative or rug-associated evidence"]

    if promotion_gate != "trusted_review_possible" or row.get("trusted_promotion_allowed") is not True:
        reasons.append("trusted promotion gate is closed")

    if row_blockers:
        reasons.append("scorecard still has evidence blockers")

    if counts["known_outcome_rows"] < MIN_KNOWN_OUTCOMES_FOR_PROMOTION:
        reasons.append(f"known outcome sample below {MIN_KNOWN_OUTCOMES_FOR_PROMOTION}")

    if counts["round_trip_lifecycles"] < MIN_ROUND_TRIPS_FOR_PROMOTION:
        reasons.append(f"round-trip sample below {MIN_ROUND_TRIPS_FOR_PROMOTION}")

    if counts["rug_rows"] > 0:
        reasons.append("known rug rows block promotion review")

    if reasons:
        return "HOLD_MORE_DATA", sorted(set(reasons))

    return "PROMOTION_REVIEW_READY", ["all review gates passed; human approval still required"]


def review_row(row: dict[str, Any]) -> dict[str, Any]:
    action, reasons = stage4_action(row)
    return {
        "wallet": str(row.get("wallet") or "").strip(),
        "stage4_action": action,
        "auto_apply": False,
        "review_only": True,
        "source_bucket": row.get("recommendation_bucket"),
        "promotion_gate": row.get("promotion_gate"),
        "scorecard_next_action": row.get("next_action"),
        "evidence": evidence_counts(row),
        "evidence_blockers": blockers(row),
        "reasons": reasons,
    }


def summarize(rows: list[dict[str, Any]], scorecard_summary: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(str(row.get("stage4_action") or "HOLD_MORE_DATA") for row in rows)
    return {
        "stage4_review_completion_pct": 40,
        "source_stage3_engine_completion_pct": safe_int(scorecard_summary.get("stage3_engine_completion_pct")),
        "source_wallet_score_readiness_pct": safe_int(scorecard_summary.get("wallet_score_readiness_pct")),
        "wallets_reviewed": len(rows),
        "promotion_review_ready": counts["PROMOTION_REVIEW_READY"],
        "hold_more_data": counts["HOLD_MORE_DATA"],
        "risk_review_required": counts["RISK_REVIEW_REQUIRED"],
        "demotion_or_block_review": counts["DEMOTION_OR_BLOCK_REVIEW"],
        "auto_applied": sum(1 for row in rows if row.get("auto_apply") is True),
    }


def build_wallet_stage4_review_report(
    *,
    wallet_evidence_scorecard: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    scorecard_summary = as_dict(wallet_evidence_scorecard.get("summary"))
    wallet_rows = [
        row
        for row in wallet_evidence_scorecard.get("wallets") or []
        if isinstance(row, dict) and str(row.get("wallet") or "").strip()
    ]
    rows = [review_row(row) for row in wallet_rows]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "stage4_version": STAGE4_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": "Stage 4 consumes the Stage 3 scorecard but does not auto-promote, demote, mutate wallet lists, or trade.",
        "policy": {
            "minimum_known_outcomes_for_promotion": MIN_KNOWN_OUTCOMES_FOR_PROMOTION,
            "minimum_round_trips_for_promotion": MIN_ROUND_TRIPS_FOR_PROMOTION,
            "auto_apply_allowed": False,
            "live_execution_allowed": False,
        },
        "summary": summarize(rows, scorecard_summary),
        "reviews": rows,
    }
