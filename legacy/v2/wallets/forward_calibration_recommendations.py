from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "FORWARD_CALIBRATION_RECOMMENDATIONS_REVIEW_ONLY"
VERSION = "forward_calibration_recommendations.v1"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def action_for(row: dict[str, Any]) -> tuple[str, list[str]]:
    status = str(row.get("calibration_status") or "")
    runner = safe_int(row.get("runner_15m"))
    rug = safe_int(row.get("rug_15m"))
    dead = safe_int(row.get("dead_15m"))
    loser = safe_int(row.get("loser_15m"))
    flat = safe_int(row.get("flat_15m"))
    known = safe_int(row.get("known_15m"))
    blocked = safe_int(row.get("blocked_records"))

    if status == "risk_review_candidate" or rug > 0 or dead > 0 or loser > runner:
        return "RISK_REVIEW_REQUIRED", ["forward evidence includes rug/dead/loser exposure"]
    if status == "review_behavioral_signal" or runner > 0:
        return "REVIEW_FORWARD_SIGNAL_MANUALLY", [
            "forward evidence includes non-flat runner behavior",
            "manual review required before any trust decision",
        ]
    if status == "flat_noise_candidate" or (known >= 2 and flat == known):
        return "HOLD_NO_PROMOTION_FLAT_ONLY", ["known forward outcomes are flat-only"]
    if status == "blocked_missing_context" or (blocked > 0 and known == 0):
        return "FIX_FORWARD_ENTRY_CONTEXT", ["forward rows are blocked by missing entry context"]
    return "COLLECT_MORE_FORWARD_EVIDENCE", ["forward sample is not informative enough"]


def recommendation_row(row: dict[str, Any]) -> dict[str, Any]:
    action, reasons = action_for(row)
    return {
        "wallet": row.get("wallet"),
        "review_only": True,
        "auto_apply": False,
        "recommendation_action": action,
        "recommendation_reasons": reasons,
        "source_calibration_status": row.get("calibration_status"),
        "records": safe_int(row.get("records")),
        "known_15m": safe_int(row.get("known_15m")),
        "runner_15m": safe_int(row.get("runner_15m")),
        "rug_15m": safe_int(row.get("rug_15m")),
        "dead_15m": safe_int(row.get("dead_15m")),
        "loser_15m": safe_int(row.get("loser_15m")),
        "flat_15m": safe_int(row.get("flat_15m")),
        "blocked_records": safe_int(row.get("blocked_records")),
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter(str(row.get("recommendation_action") or "UNKNOWN") for row in rows)
    return {
        "wallets": len(rows),
        "review_forward_signal_wallets": actions.get("REVIEW_FORWARD_SIGNAL_MANUALLY", 0),
        "risk_review_wallets": actions.get("RISK_REVIEW_REQUIRED", 0),
        "flat_only_hold_wallets": actions.get("HOLD_NO_PROMOTION_FLAT_ONLY", 0),
        "fix_context_wallets": actions.get("FIX_FORWARD_ENTRY_CONTEXT", 0),
        "collect_more_wallets": actions.get("COLLECT_MORE_FORWARD_EVIDENCE", 0),
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def rank_row(row: dict[str, Any]) -> tuple[int, int, str]:
    rank = {
        "REVIEW_FORWARD_SIGNAL_MANUALLY": 0,
        "RISK_REVIEW_REQUIRED": 1,
        "FIX_FORWARD_ENTRY_CONTEXT": 2,
        "COLLECT_MORE_FORWARD_EVIDENCE": 3,
        "HOLD_NO_PROMOTION_FLAT_ONLY": 4,
    }.get(str(row.get("recommendation_action")), 9)
    return (rank, -safe_int(row.get("known_15m")), str(row.get("wallet") or ""))


def build_forward_calibration_recommendations(
    scorecard: dict[str, Any],
    *,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    rows = [
        recommendation_row(row)
        for row in scorecard.get("wallets") or []
        if isinstance(row, dict) and str(row.get("wallet") or "").strip()
    ]
    rows = sorted(rows, key=rank_row)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": scorecard.get("live_execution_locked") is not False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(rows),
        "recommendations": rows,
        "operator_note": (
            "Forward recommendations are conservative review labels only. Flat-only outcomes are not "
            "promotion evidence, and no wallet trust or wallet-list mutation is allowed."
        ),
    }
