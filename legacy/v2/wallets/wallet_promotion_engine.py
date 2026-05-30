from __future__ import annotations

from typing import Any


MIN_KNOWN_OUTCOMES = 20
MAX_PROMOTION_RUG_RATE = 0.10
MIN_PROMOTION_RUNNER_RATE = 0.35
MAX_DEMOTION_RUG_RATE = 0.25


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


def recommend_from_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    known = safe_int(row.get("known_outcomes"))
    runner_rate = safe_float(row.get("runner_participation_rate"))
    rug_rate = safe_float(row.get("rug_participation_rate"))
    avg_pnl = safe_float(row.get("average_pnl_after_signal"))
    promotion_score = safe_float(row.get("promotion_score"))
    demotion_score = safe_float(row.get("demotion_score"))

    reasons: list[str] = []
    action = "HOLD_MORE_DATA"

    if known < MIN_KNOWN_OUTCOMES:
        reasons.append(f"known outcome sample below {MIN_KNOWN_OUTCOMES}")
    elif rug_rate >= MAX_DEMOTION_RUG_RATE and demotion_score >= 25:
        action = "DEMOTION_REVIEW"
        reasons.append("rug participation rate exceeds review threshold")
    elif avg_pnl < 0 and demotion_score > promotion_score:
        action = "DEMOTION_REVIEW"
        reasons.append("negative average outcome pressure exceeds promotion evidence")
    elif (
        runner_rate >= MIN_PROMOTION_RUNNER_RATE
        and rug_rate <= MAX_PROMOTION_RUG_RATE
        and avg_pnl > 0
        and promotion_score > demotion_score
    ):
        action = "PROMOTION_REVIEW"
        reasons.append("runner rate and positive average outcome meet review threshold")
    else:
        reasons.append("ledger evidence is not decisive")

    return {
        "action": action,
        "review_only": True,
        "minimum_known_outcomes": MIN_KNOWN_OUTCOMES,
        "evidence": {
            "known_outcomes": known,
            "runner_participation_rate": runner_rate,
            "rug_participation_rate": rug_rate,
            "average_pnl_after_signal": avg_pnl,
            "promotion_score": promotion_score,
            "demotion_score": demotion_score,
        },
        "reasons": reasons,
    }
