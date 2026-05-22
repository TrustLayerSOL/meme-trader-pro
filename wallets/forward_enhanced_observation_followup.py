from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "FORWARD_ENHANCED_OBSERVATION_FOLLOWUP_REVIEW_ONLY"
VERSION = "forward_enhanced_observation_followup.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def outcome_15m(row: dict[str, Any]) -> str:
    label = as_dict(as_dict(row.get("outcome_window_labels")).get("15m"))
    return str(label.get("outcome_type") or as_dict(row.get("later_token_outcome")).get("outcome_type") or "unknown").lower()


def is_blocked(row: dict[str, Any]) -> bool:
    reasons = row.get("block_reasons")
    return isinstance(reasons, list) and bool(reasons)


def wallet_records_after(records: list[dict[str, Any]], wallet: str, after_time: float) -> list[dict[str, Any]]:
    selected = []
    for row in records:
        if str(row.get("wallet") or "") != wallet:
            continue
        if safe_float(row.get("signal_time")) <= after_time:
            continue
        selected.append(row)
    return selected


def build_wallet_followup(wallet: dict[str, Any], records: list[dict[str, Any]], baseline_time: float) -> dict[str, Any]:
    wallet_id = str(wallet.get("wallet") or "")
    selected = wallet_records_after(records, wallet_id, baseline_time)
    outcomes = Counter(outcome_15m(row) for row in selected)
    distinct_mints = {str(row.get("token_mint") or "") for row in selected if str(row.get("token_mint") or "").strip()}
    minimum_signals = safe_int(wallet.get("minimum_next_forward_signals"), 25)
    minimum_mints = safe_int(wallet.get("minimum_distinct_next_token_mints"), 10)
    meets = len(selected) >= minimum_signals and len(distinct_mints) >= minimum_mints
    return {
        "wallet": wallet_id,
        "baseline_generated_at": baseline_time,
        "observation_lane": wallet.get("observation_lane") or "enhanced_observation",
        "trust_status": "not_trusted",
        "new_forward_records": len(selected),
        "new_distinct_token_mints": len(distinct_mints),
        "new_runner_15m": outcomes.get("runner", 0),
        "new_flat_15m": outcomes.get("flat", 0),
        "new_rug_15m": outcomes.get("rug", 0),
        "new_unknown_15m": outcomes.get("unknown", 0),
        "new_blocked_records": sum(1 for row in selected if is_blocked(row)),
        "minimum_next_forward_signals": minimum_signals,
        "minimum_distinct_next_token_mints": minimum_mints,
        "meets_review_threshold": meets,
        "review_status": "ready_for_human_followup_review" if meets else "collect_more_forward_evidence",
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "live_execution_mutation_allowed": False,
    }


def build_forward_enhanced_observation_followup(
    *,
    watchlist: dict[str, Any],
    records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    baseline_time = safe_float(watchlist.get("generated_at"))
    wallets = [
        build_wallet_followup(row, records, baseline_time)
        for row in watchlist.get("wallets") or []
        if isinstance(row, dict) and str(row.get("wallet") or "").strip()
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": watchlist.get("live_execution_locked") is not False,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "summary": {
            "followup_wallets": len(wallets),
            "wallets_meeting_review_threshold": sum(1 for row in wallets if row.get("meets_review_threshold")),
            "wallets_collecting_more_evidence": sum(1 for row in wallets if not row.get("meets_review_threshold")),
            "new_forward_records": sum(safe_int(row.get("new_forward_records")) for row in wallets),
            "new_runner_15m": sum(safe_int(row.get("new_runner_15m")) for row in wallets),
            "new_rug_15m": sum(safe_int(row.get("new_rug_15m")) for row in wallets),
            "new_blocked_records": sum(safe_int(row.get("new_blocked_records")) for row in wallets),
            "promotions_allowed": 0,
            "wallet_trust_mutations_allowed": 0,
            "wallet_list_mutations_allowed": 0,
        },
        "wallets": wallets,
        "operator_note": (
            "This follow-up counts only forward rows after the enhanced-observation watchlist timestamp. "
            "It is a review queue, not a trust or execution mutation."
        ),
    }
