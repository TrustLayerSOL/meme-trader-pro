from __future__ import annotations

from typing import Any


def behavior_score(profile: dict[str, Any]) -> dict[str, Any]:
    """Review-only score for sorting wallet profiles, not an execution trigger."""
    metrics = profile.get("metrics") if isinstance(profile.get("metrics"), dict) else profile
    score = 50.0
    reasons: list[str] = []

    win_rate = metrics.get("win_rate")
    if isinstance(win_rate, (int, float)):
        score += max(-20, min(20, (win_rate - 50.0) * 0.5))
        reasons.append(f"win_rate={win_rate:.2f}")

    roi = metrics.get("wallet_roi")
    if isinstance(roi, (int, float)):
        score += max(-20, min(20, roi))
        reasons.append(f"wallet_roi={roi:.4f}")

    rug_score = metrics.get("rug_association_score")
    if isinstance(rug_score, (int, float)) and rug_score > 0:
        score -= min(25, rug_score * 40)
        reasons.append(f"rug_association_score={rug_score:.4f}")

    runners = metrics.get("participation_frequency_in_runners")
    if isinstance(runners, int) and runners > 0:
        score += min(10, runners * 2)
        reasons.append(f"runner_participation={runners}")

    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "reasons": reasons,
        "review_only": True,
    }

