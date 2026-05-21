from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "FORWARD_SIGNAL_REVIEW_PACKET_REVIEW_ONLY"
VERSION = "forward_signal_review_packet.v1"
REVIEW_ACTION = "REVIEW_FORWARD_SIGNAL_MANUALLY"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
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


def review_wallets(recommendations: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in recommendations.get("recommendations") or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet and str(row.get("recommendation_action") or "") == REVIEW_ACTION:
            rows[wallet] = row
    return rows


def outcome_15m(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("outcome_window_labels")).get("15m"))


def repair_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(row.get("entry_context_repair"))


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    repair = repair_context(row)
    outcome = outcome_15m(row)
    return {
        "event_id": row.get("event_id"),
        "wallet": row.get("wallet"),
        "token_mint": row.get("token_mint"),
        "signal_time": safe_float(row.get("signal_time"), None),
        "transaction_signature": row.get("transaction_signature"),
        "observed_action": row.get("observed_action"),
        "repair_method": repair.get("method"),
        "repair_confidence": repair.get("confidence"),
        "repaired_price": safe_float(repair.get("repaired_price"), None),
        "later_snapshots_available": safe_int(repair.get("later_snapshots_available")),
        "outcome_15m": str(outcome.get("outcome_type") or "unknown").lower(),
        "outcome_15m_confidence": outcome.get("label_confidence"),
        "outcome_15m_reasons": list(outcome.get("classification_reasons") or []),
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def outcome_sort_rank(outcome: Any) -> int:
    value = str(outcome or "unknown").lower()
    if value == "runner":
        return 0
    if value in {"rug", "loss", "loser", "dead"}:
        return 1
    if value == "flat":
        return 2
    return 3


def wallet_packet(wallet: str, recommendation: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    compact_rows = sorted(
        (compact_row(row) for row in rows),
        key=lambda row: (
            outcome_sort_rank(row.get("outcome_15m")),
            safe_float(row.get("signal_time"), 0.0) or 0.0,
            str(row.get("event_id") or ""),
        ),
    )
    outcomes = Counter(str(row.get("outcome_15m") or "unknown") for row in compact_rows)
    return {
        "wallet": wallet,
        "review_only": True,
        "recommendation_action": REVIEW_ACTION,
        "recommendation_reasons": list(recommendation.get("recommendation_reasons") or []),
        "records": len(compact_rows),
        "known_15m": safe_int(recommendation.get("known_15m")),
        "runner_15m": safe_int(recommendation.get("runner_15m")),
        "flat_15m": safe_int(recommendation.get("flat_15m")),
        "blocked_records": safe_int(recommendation.get("blocked_records")),
        "outcomes_15m": dict(sorted(outcomes.items())),
        "rows": compact_rows,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(wallets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "review_wallets": len(wallets),
        "review_rows": sum(safe_int(row.get("records")) for row in wallets),
        "runner_15m_rows": sum(safe_int(as_dict(row.get("outcomes_15m")).get("runner")) for row in wallets),
        "flat_15m_rows": sum(safe_int(as_dict(row.get("outcomes_15m")).get("flat")) for row in wallets),
        "unknown_15m_rows": sum(safe_int(as_dict(row.get("outcomes_15m")).get("unknown")) for row in wallets),
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_signal_review_packet(
    *,
    recommendations: dict[str, Any],
    repaired_records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    review_map = review_wallets(recommendations)
    rows_by_wallet: dict[str, list[dict[str, Any]]] = {wallet: [] for wallet in review_map}
    for row in repaired_records or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet in rows_by_wallet:
            rows_by_wallet[wallet].append(row)
    wallets = [
        wallet_packet(wallet, recommendation, rows_by_wallet.get(wallet, []))
        for wallet, recommendation in sorted(review_map.items())
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": recommendations.get("live_execution_locked") is not False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(wallets),
        "wallets": wallets,
        "operator_note": (
            "Manual review packet is analysis-only. Review-forward-signal wallets are not promotions and cannot "
            "mutate wallet trust, wallet lists, or execution."
        ),
    }
