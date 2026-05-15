from __future__ import annotations

from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _wallet_review_row(wallet: str, row: dict[str, Any]) -> dict[str, Any]:
    windows = as_dict(row.get("windows"))
    window_15m = as_dict(windows.get("15m"))
    quality = as_dict(row.get("signal_quality"))
    total_events = safe_int(row.get("total_events"))
    fillable_events = safe_int(row.get("fillable_events"))
    known_15m = safe_int(window_15m.get("known"))
    unknown_15m = safe_int(window_15m.get("unknown"))
    runner_rate = safe_float(quality.get("runner_rate_known_15m"))
    rug_rate = safe_float(quality.get("rug_rate_known_15m"))
    fillable_rate = round(fillable_events / total_events, 4) if total_events else 0.0
    return {
        "wallet": wallet,
        "total_events": total_events,
        "fillable_events": fillable_events,
        "fillable_rate": fillable_rate,
        "known_15m": known_15m,
        "unknown_15m": unknown_15m,
        "known_rate_15m": safe_float(quality.get("known_rate_15m")),
        "runner_rate_known_15m": runner_rate,
        "rug_rate_known_15m": rug_rate,
        "runner_minus_rug_rate_15m": round(runner_rate - rug_rate, 4),
        "review_status": str(quality.get("review_status") or "unknown"),
        "regime_breakdown": as_dict(row.get("regime_breakdown")),
        "top_co_entry_partners": list(row.get("co_entry_partners") or [])[:5],
    }


def _reviewable(row: dict[str, Any], *, min_known_events: int, min_fillable_events: int) -> bool:
    return row["known_15m"] >= min_known_events and row["fillable_events"] >= min_fillable_events


def _low_coverage(row: dict[str, Any], *, min_known_events: int, min_fillable_events: int) -> bool:
    return row["total_events"] > 0 and not _reviewable(
        row,
        min_known_events=min_known_events,
        min_fillable_events=min_fillable_events,
    )


def _sort_reviewable(row: dict[str, Any]) -> tuple[float, int, int, float]:
    return (
        row["runner_minus_rug_rate_15m"],
        row["known_15m"],
        row["fillable_events"],
        row["known_rate_15m"],
    )


def _sort_low_coverage(row: dict[str, Any]) -> tuple[int, int, float]:
    return (
        row["total_events"],
        row["known_15m"],
        row["fillable_rate"],
    )


def build_wallet_replay_review(
    scorecard: dict[str, Any] | None,
    *,
    limit: int = 50,
    min_known_events: int = 5,
    min_fillable_events: int = 5,
    min_pair_count: int = 2,
) -> dict[str, Any]:
    scorecard = as_dict(scorecard)
    wallets = as_dict(scorecard.get("wallets"))
    rows = [
        _wallet_review_row(wallet, as_dict(row))
        for wallet, row in wallets.items()
        if wallet and isinstance(row, dict)
    ]
    reviewable = [
        row
        for row in rows
        if _reviewable(row, min_known_events=min_known_events, min_fillable_events=min_fillable_events)
    ]
    low_coverage = [
        row
        for row in rows
        if _low_coverage(row, min_known_events=min_known_events, min_fillable_events=min_fillable_events)
    ]
    pair_rows = [
        pair
        for pair in as_dict(scorecard.get("ecosystems")).get("top_co_entry_pairs", [])
        if isinstance(pair, dict) and safe_int(pair.get("count")) >= min_pair_count
    ]
    limit = max(1, int(limit or 50))
    return {
        "mode": "WALLET_REPLAY_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "thresholds": {
            "min_known_events": min_known_events,
            "min_fillable_events": min_fillable_events,
            "min_pair_count": min_pair_count,
        },
        "source_counts": as_dict(scorecard.get("counts")),
        "summary": {
            "wallets": len(rows),
            "reviewable_wallets": len(reviewable),
            "low_coverage_wallets": len(low_coverage),
            "co_entry_pairs": len(pair_rows),
        },
        "reviewable_wallets": sorted(reviewable, key=_sort_reviewable, reverse=True)[:limit],
        "low_coverage_wallets": sorted(low_coverage, key=_sort_low_coverage, reverse=True)[:limit],
        "co_entry_review": pair_rows[:limit],
    }
