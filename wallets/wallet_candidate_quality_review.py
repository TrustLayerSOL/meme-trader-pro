from __future__ import annotations

import time
from collections import Counter
from typing import Any


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def replay_metrics(wallet: str, wallet_replay_scorecard: Any) -> dict[str, Any]:
    row = as_dict(as_dict(as_dict(wallet_replay_scorecard).get("wallets")).get(wallet))
    window_15m = as_dict(as_dict(row.get("windows")).get("15m"))
    quality = as_dict(row.get("signal_quality"))
    return {
        "total_events": safe_int(row.get("total_events")),
        "fillable_events": safe_int(row.get("fillable_events")),
        "known_15m": safe_int(window_15m.get("known")),
        "known_rate_15m": safe_float(quality.get("known_rate_15m")),
        "runner_rate_known_15m": safe_float(quality.get("runner_rate_known_15m")),
        "rug_rate_known_15m": safe_float(quality.get("rug_rate_known_15m")),
    }


def outcome_metrics(wallet: str, wallet_outcome_ledger: Any) -> dict[str, Any]:
    row = as_dict(as_dict(as_dict(wallet_outcome_ledger).get("wallets")).get(wallet))
    return {
        "known_outcomes": safe_int(row.get("known_outcomes")),
        "runner_participation_rate": safe_float(row.get("runner_participation_rate")),
        "rug_participation_rate": safe_float(row.get("rug_participation_rate")),
        "promotion_score": safe_float(row.get("promotion_score")),
        "demotion_score": safe_float(row.get("demotion_score")),
    }


def recommendation(
    candidate: dict[str, Any],
    replay: dict[str, Any],
    outcome: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    quality_score = safe_float(candidate.get("quality_score"))
    risks = candidate.get("risk_flags") if isinstance(candidate.get("risk_flags"), list) else []
    gaps: list[str] = []

    if risks:
        return {
            "action": "RISK_REVIEW",
            "auto_apply": False,
            "confidence": "low",
            "reasons": ["candidate has unresolved risk flags"],
        }, gaps

    if replay["known_15m"] < 10 or replay["fillable_events"] < 10:
        gaps.append("replay evidence below threshold")
    if outcome["known_outcomes"] < 10:
        gaps.append("outcome ledger sample below threshold")

    replay_positive = (
        replay["known_15m"] >= 10
        and replay["fillable_events"] >= 10
        and replay["runner_rate_known_15m"] >= 0.6
        and replay["rug_rate_known_15m"] == 0
    )
    outcome_positive = (
        outcome["known_outcomes"] >= 10
        and outcome["runner_participation_rate"] >= 0.6
        and outcome["rug_participation_rate"] == 0
    )
    if quality_score >= 72 and replay_positive and outcome_positive:
        return {
            "action": "PROMOTION_REVIEW_READY",
            "auto_apply": False,
            "confidence": "medium",
            "reasons": [
                "candidate quality is strong",
                "replay and outcome evidence pass conservative review gates",
            ],
        }, gaps

    if quality_score < 32:
        return {
            "action": "REJECT_REVIEW",
            "auto_apply": False,
            "confidence": "low",
            "reasons": ["candidate quality score is weak"],
        }, gaps

    return {
        "action": "OBSERVE_MORE",
        "auto_apply": False,
        "confidence": "low",
        "reasons": ["candidate quality is not enough without replay/outcome confirmation"],
    }, gaps


def review_row(candidate: dict[str, Any], wallet_replay_scorecard: Any, wallet_outcome_ledger: Any) -> dict[str, Any]:
    wallet = str(candidate.get("wallet") or "").strip()
    replay = replay_metrics(wallet, wallet_replay_scorecard)
    outcome = outcome_metrics(wallet, wallet_outcome_ledger)
    decision, gaps = recommendation(candidate, replay, outcome)
    return {
        "wallet": wallet,
        "quality_score": safe_float(candidate.get("quality_score")),
        "recommended_observation": candidate.get("recommended_observation"),
        "winner_mints": safe_int(candidate.get("winner_mints")),
        "early_buy_events": safe_int(candidate.get("early_buy_events")),
        "risk_flags": candidate.get("risk_flags") if isinstance(candidate.get("risk_flags"), list) else [],
        "replay": replay,
        "outcome": outcome,
        "evidence_gaps": gaps,
        "recommendation": decision,
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(as_dict(row.get("recommendation")).get("action") or "OBSERVE_MORE") for row in rows)
    return {
        "total_reviewed": len(rows),
        "promotion_review_ready": counts["PROMOTION_REVIEW_READY"],
        "observe_more": counts["OBSERVE_MORE"],
        "risk_review": counts["RISK_REVIEW"],
        "reject_review": counts["REJECT_REVIEW"],
    }


def build_wallet_candidate_quality_review(
    *,
    candidate_quality_report: Any,
    wallet_replay_scorecard: Any,
    wallet_outcome_ledger: Any,
    generated_at: float | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    candidates = [
        row
        for row in as_dict(candidate_quality_report).get("ranked_candidates") or []
        if isinstance(row, dict) and row.get("wallet")
    ][: int(limit)]
    rows = [review_row(row, wallet_replay_scorecard, wallet_outcome_ledger) for row in candidates]
    return {
        "generated_at": generated_at,
        "mode": "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "summary": summary(rows),
        "shortlist": rows,
    }
