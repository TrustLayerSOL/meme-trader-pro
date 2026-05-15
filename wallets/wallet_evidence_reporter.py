from __future__ import annotations

from statistics import median
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


def wallet_metrics(wallet: str, evidence_rows: list[dict[str, Any]], *, min_usable: int = 10) -> dict[str, Any]:
    rows = [row for row in evidence_rows or [] if isinstance(row, dict) and row.get("wallet") == wallet]
    usable = [row for row in rows if safe_float(row.get("confidence_score")) >= 60]
    runner_rows = [row for row in rows if as_dict(row.get("later_token_outcome")).get("runner")]
    rug_rows = [row for row in rows if as_dict(row.get("later_token_outcome")).get("rug")]
    known_rows = [
        row for row in rows
        if as_dict(row.get("later_token_outcome")).get("outcome_type") not in (None, "", "unknown")
    ]
    hold_durations = [
        safe_float(as_dict(row.get("estimated_exit_context")).get("hold_duration_seconds"), 0.0)
        for row in rows
        if safe_float(as_dict(row.get("estimated_exit_context")).get("hold_duration_seconds"), 0.0) > 0
    ]
    missing_total = sum(len(row.get("missing_fields") or []) for row in rows)
    possible_missing = max(1, len(rows) * 8)
    confidence = round(sum(safe_float(row.get("confidence_score")) for row in rows) / len(rows), 2) if rows else 0.0
    return {
        "wallet": wallet,
        "total_observed_token_interactions": len(rows),
        "total_usable_evidence_rows": len(usable),
        "runner_participation_rate": round(len(runner_rows) / len(known_rows), 4) if known_rows else 0.0,
        "rug_participation_rate": round(len(rug_rows) / len(known_rows), 4) if known_rows else 0.0,
        "average_hold_duration_seconds": round(sum(hold_durations) / len(hold_durations), 2) if hold_durations else None,
        "median_hold_duration_seconds": round(median(hold_durations), 2) if hold_durations else None,
        "early_entry_rate": 0.0,
        "repeat_runner_association": len({row.get("token_mint") for row in runner_rows}),
        "repeated_rug_association": len({row.get("token_mint") for row in rug_rows}),
        "missing_data_ratio": round(missing_total / possible_missing, 4),
        "evidence_confidence_score": confidence,
        "minimum_additional_evidence_needed": max(0, min_usable - len(usable)),
    }


def summarize_wallet_report(wallet_rows: list[dict[str, Any]], evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [row for row in wallet_rows if str(row.get("status") or "").startswith("BLOCKED")]
    partial = [row for row in wallet_rows if str(row.get("status") or "") == "PARTIAL_WALLET_HISTORY_COLLECTED"]
    collected = [row for row in wallet_rows if str(row.get("status") or "") == "COLLECTED"]
    promising = [
        row for row in wallet_rows
        if safe_float(as_dict(row.get("metrics")).get("runner_participation_rate")) > 0
        and safe_float(as_dict(row.get("metrics")).get("rug_participation_rate")) == 0
    ]
    high_rug = [
        row for row in wallet_rows
        if safe_float(as_dict(row.get("metrics")).get("rug_participation_rate")) >= 0.25
    ]
    insufficient = [
        row for row in wallet_rows
        if str(row.get("target_status") or "") == "insufficient_history"
    ]
    return {
        "wallets_processed": len(wallet_rows),
        "wallets_successfully_backfilled": len(collected),
        "collected_wallets": len(collected),
        "wallets_partially_backfilled": len(partial),
        "wallets_blocked": len(blocked),
        "total_evidence_rows_created": len(evidence_rows),
        "wallets_with_promising_evidence": len(promising),
        "wallets_with_high_rug_exposure": len(high_rug),
        "wallets_with_insufficient_data": len(insufficient),
    }
