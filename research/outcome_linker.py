from __future__ import annotations

from typing import Any

from research.outcome_labeler import label_later_token_outcome


DEFAULT_EVALUATION_HORIZON_SECONDS = 3600


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def build_later_outcome_from_snapshots(
    *,
    mint: str,
    signal_time: float,
    snapshots: list[dict[str, Any]],
    horizon_seconds: float = DEFAULT_EVALUATION_HORIZON_SECONDS,
) -> dict[str, Any]:
    start = safe_float(signal_time, None)
    if start is None:
        return unknown_outcome(mint, "missing signal time")
    end = start + max(0.0, float(horizon_seconds))
    later = [
        row for row in snapshots or []
        if isinstance(row, dict)
        and safe_float(row.get("time"), None) is not None
        and start <= (safe_float(row.get("time"), 0.0) or 0.0) <= end
    ]
    later.sort(key=lambda row: safe_float(row.get("time"), 0.0) or 0.0)
    priced = [row for row in later if safe_float(row.get("price"), None) not in (None, 0)]
    if not priced:
        return unknown_outcome(mint, "no later snapshots available")

    entry = priced[0]
    exit_row = priced[-1]
    high = max(priced, key=lambda row: safe_float(row.get("price"), 0.0) or 0.0)
    risk_labels = {str(row.get("risk_label") or "").upper() for row in later}
    close_reason = None
    if risk_labels & {"EMERGENCY", "DANGER", "HIGH_RISK"}:
        close_reason = "later snapshot carried emergency risk"

    outcome = {
        "status": "snapshot_evaluated",
        "source": "token_snapshots",
        "mint": mint,
        "signal_time": start,
        "evaluation_horizon_seconds": horizon_seconds,
        "first_snapshot_time": safe_float(entry.get("time")),
        "last_snapshot_time": safe_float(exit_row.get("time")),
        "snapshot_count": len(later),
        "entry_price": safe_float(entry.get("price")),
        "exit_price": safe_float(exit_row.get("price")),
        "highest_price_seen": safe_float(high.get("price")),
        "entry_liquidity_usd": safe_float(entry.get("liquidity")),
        "exit_liquidity_usd": safe_float(exit_row.get("liquidity")),
        "close_reason": close_reason,
    }
    return label_later_token_outcome(outcome=outcome)


def unknown_outcome(mint: str, reason: str) -> dict[str, Any]:
    return {
        "status": "unknown",
        "source": "token_snapshots",
        "mint": mint,
        "outcome_type": "unknown",
        "runner": False,
        "rug": False,
        "dead": False,
        "label_confidence": "low",
        "classification_reasons": [reason],
    }
