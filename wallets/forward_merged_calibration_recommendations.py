from __future__ import annotations

import time
from typing import Any

from wallets.forward_calibration_recommendations import build_forward_calibration_recommendations


MODE = "FORWARD_MERGED_CALIBRATION_RECOMMENDATIONS_REVIEW_ONLY"
VERSION = "forward_merged_calibration_recommendations.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_forward_merged_calibration_recommendations(
    merged_scorecard: dict[str, Any],
    *,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    inner_scorecard = as_dict(merged_scorecard.get("scorecard"))
    recommendations = build_forward_calibration_recommendations(inner_scorecard, generated_at=generated_at)
    summary = as_dict(recommendations.get("summary"))
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": merged_scorecard.get("live_execution_locked") is not False
        and inner_scorecard.get("live_execution_locked") is not False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": {
            **summary,
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "merged_scorecard_summary": as_dict(merged_scorecard.get("summary")),
        "recommendations": recommendations.get("recommendations") or [],
        "operator_note": (
            "Merged forward recommendations are conservative review labels only. Repaired forward rows can move "
            "wallets into manual review, but they cannot promote wallets, mutate lists, or change execution."
        ),
    }
