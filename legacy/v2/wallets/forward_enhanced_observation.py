from __future__ import annotations

import time
from typing import Any


MODE = "FORWARD_ENHANCED_OBSERVATION_REVIEW_ONLY"
VERSION = "forward_enhanced_observation.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def qualifies_for_enhanced_observation(wallet: dict[str, Any]) -> bool:
    return (
        wallet.get("decision_type") == "manual_review_required"
        and wallet.get("validation_status") == "repeatability_supported_manual_review"
        and safe_int(wallet.get("runner_rows")) > 0
        and bool(wallet.get("promotion_allowed")) is False
        and bool(wallet.get("wallet_trust_mutation_allowed")) is False
        and bool(wallet.get("wallet_list_mutation_allowed")) is False
    )


def build_watch_wallet(wallet: dict[str, Any]) -> dict[str, Any]:
    runner_rows = safe_int(wallet.get("runner_rows"))
    runner_mints = safe_int(wallet.get("runner_distinct_token_mints"))
    total_rows = safe_int(wallet.get("total_review_rows"))
    unknown_rows = safe_int(wallet.get("unknown_15m_rows"))
    return {
        "wallet": wallet.get("wallet"),
        "observation_lane": "enhanced_observation",
        "review_action": "WATCH_NEXT_FORWARD_TRADES",
        "trust_status": "not_trusted",
        "operator_recommendation": "continue observation; do not promote from this artifact alone",
        "evidence_summary": {
            "total_review_rows": total_rows,
            "runner_rows": runner_rows,
            "unknown_15m_rows": unknown_rows,
            "runner_distinct_token_mints": runner_mints,
            "runner_signal_span_seconds": wallet.get("runner_signal_span_seconds"),
            "dominant_runner_token_share": safe_float(wallet.get("dominant_runner_token_share")),
            "top_token_mints": wallet.get("top_token_mints") if isinstance(wallet.get("top_token_mints"), list) else [],
        },
        "minimum_next_forward_signals": 25,
        "minimum_distinct_next_token_mints": 10,
        "required_next_checks": [
            "capture next forward wallet events with decision-time market context",
            "confirm future runner behavior remains spread across different token mints",
            "confirm no new rug or bad-ecosystem linkage appears",
            "review again before any trust score or wallet-list change",
        ],
        "source_decision_type": wallet.get("decision_type"),
        "source_validation_status": wallet.get("validation_status"),
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "live_execution_mutation_allowed": False,
    }


def build_forward_enhanced_observation(
    *,
    rollup: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    wallets = [
        build_watch_wallet(row)
        for row in rollup.get("wallets") or []
        if isinstance(row, dict) and qualifies_for_enhanced_observation(row)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": rollup.get("live_execution_locked") is not False,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "summary": {
            "enhanced_observation_wallets": len(wallets),
            "promotions_allowed": 0,
            "wallet_trust_mutations_allowed": 0,
            "wallet_list_mutations_allowed": 0,
            "minimum_next_forward_signals_per_wallet": 25,
            "minimum_distinct_next_token_mints_per_wallet": 10,
        },
        "wallets": wallets,
        "operator_note": (
            "Enhanced observation means watch future behavior separately. "
            "It is not wallet trust approval and cannot mutate wallet lists or execution."
        ),
    }
