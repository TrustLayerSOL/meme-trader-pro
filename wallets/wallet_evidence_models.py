from __future__ import annotations

from typing import Any


PARSER_VERSION = "wallet_history_backfill.v1"
OUTCOME_WINDOWS = ("30s", "2m", "5m", "15m")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
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


def empty_window_labels() -> dict[str, dict[str, Any]]:
    return {
        label: {
            "outcome_type": "unknown",
            "runner": False,
            "rug": False,
            "dead": False,
            "label_confidence": "low",
            "missing": True,
        }
        for label in OUTCOME_WINDOWS
    }


def replay_outcomes_by_mint(replay_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    outcomes: dict[str, dict[str, Any]] = {}
    for event in replay_events or []:
        if not isinstance(event, dict):
            continue
        mint = str(event.get("mint") or "").strip()
        if not mint or mint in outcomes:
            continue
        later = as_dict(event.get("later_outcome"))
        windows = as_dict(later.get("windows"))
        outcomes[mint] = {
            "source": "historical_replay",
            "event_id": event.get("event_id"),
            "outcome_type": later.get("outcome_type") or "unknown",
            "runner": bool(later.get("runner")),
            "rug": bool(later.get("rug")),
            "dead": bool(later.get("dead")),
            "windows": {label: as_dict(windows.get(label)) or empty_window_labels()[label] for label in OUTCOME_WINDOWS},
        }
    return outcomes


def missing_fields_for_evidence(row: dict[str, Any]) -> list[str]:
    missing = []
    for key in ("wallet", "token_mint", "observed_action", "timestamp", "transaction_signature"):
        if row.get(key) in (None, ""):
            missing.append(key)
    if not as_dict(row.get("estimated_entry_context")).get("price"):
        missing.append("entry_price")
    if not as_dict(row.get("estimated_exit_context")).get("price"):
        missing.append("exit_price")
    if as_dict(row.get("later_token_outcome")).get("outcome_type") in (None, "", "unknown"):
        missing.append("later_token_outcome")
    return missing


def evidence_confidence(row: dict[str, Any]) -> int:
    score = 20
    if row.get("transaction_signature"):
        score += 20
    if row.get("timestamp"):
        score += 15
    if row.get("token_mint"):
        score += 15
    if row.get("observed_action") in {"buy", "sell"}:
        score += 10
    if row.get("token_amount_delta") not in (None, 0):
        score += 10
    if as_dict(row.get("later_token_outcome")).get("outcome_type") not in (None, "", "unknown"):
        score += 10
    return max(0, min(score, 100))


def build_evidence_record(
    *,
    wallet: str,
    token_mint: str,
    observed_action: str,
    timestamp: float | int | None,
    transaction_signature: str,
    token_amount_delta: float | None = None,
    later_token_outcome: dict[str, Any] | None = None,
    risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    later = as_dict(later_token_outcome) or {
        "source": "historical_replay",
        "outcome_type": "unknown",
        "runner": False,
        "rug": False,
        "dead": False,
        "windows": empty_window_labels(),
    }
    row = {
        "schema_version": "wallet_evidence.v1",
        "parser_version": PARSER_VERSION,
        "wallet": wallet,
        "token_mint": token_mint,
        "observed_action": observed_action,
        "timestamp": timestamp,
        "transaction_signature": transaction_signature,
        "token_amount_delta": token_amount_delta,
        "estimated_entry_context": {
            "price": None,
            "market_cap": None,
            "liquidity": None,
            "token_age_seconds": None,
            "decision_time_safe": True,
        },
        "estimated_exit_context": {
            "price": None,
            "market_cap": None,
            "liquidity": None,
            "decision_time_safe": True,
        },
        "later_token_outcome": later,
        "outcome_window_labels": as_dict(later.get("windows")) or empty_window_labels(),
        "risk_flags": risk_flags or [],
    }
    row["missing_fields"] = missing_fields_for_evidence(row)
    row["confidence_score"] = evidence_confidence(row)
    return row
