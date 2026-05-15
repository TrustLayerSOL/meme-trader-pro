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


def _pct(value: Any) -> str:
    return f"{safe_float(value) * 100:.1f}%"


def _wallet_line(row: dict[str, Any]) -> str:
    return (
        f"- `{row['wallet']}`: known 15m `{row['known_15m']}`, "
        f"fillable `{row['fillable_events']}`, "
        f"runner/rug `{_pct(row['runner_rate_known_15m'])}` / `{_pct(row['rug_rate_known_15m'])}`, "
        f"status `{row['review_status']}`"
    )


def _pair_line(row: dict[str, Any]) -> str:
    wallets = row.get("wallets") if isinstance(row.get("wallets"), list) else []
    left = str(wallets[0]) if len(wallets) > 0 else "unknown"
    right = str(wallets[1]) if len(wallets) > 1 else "unknown"
    return f"- `{left}` + `{right}`: `{safe_int(row.get('count'))}` shared replay events"


def _section(title: str, rows: list[dict[str, Any]], line_fn) -> str:
    if not rows:
        return f"## {title}\n\nNo rows met the current review threshold."
    return f"## {title}\n\n" + "\n".join(line_fn(row) for row in rows)


def render_wallet_replay_review_markdown(review: dict[str, Any]) -> str:
    review = as_dict(review)
    summary = as_dict(review.get("summary"))
    thresholds = as_dict(review.get("thresholds"))
    reviewable = [row for row in review.get("reviewable_wallets") or [] if isinstance(row, dict)]
    low_coverage = [row for row in review.get("low_coverage_wallets") or [] if isinstance(row, dict)]
    pairs = [row for row in review.get("co_entry_review") or [] if isinstance(row, dict)]
    return "\n\n".join(
        [
            "# Wallet Replay Ecosystem Review",
            "Review-only. This report is for wallet research and must not enable live execution.",
            "## Summary\n\n"
            f"- Wallets analyzed: `{safe_int(summary.get('wallets'))}`\n"
            f"- Reviewable wallets: `{safe_int(summary.get('reviewable_wallets'))}`\n"
            f"- Low-coverage wallets: `{safe_int(summary.get('low_coverage_wallets'))}`\n"
            f"- Repeated co-entry pairs: `{safe_int(summary.get('co_entry_pairs'))}`\n"
            f"- Minimum known events: `{safe_int(thresholds.get('min_known_events'))}`\n"
            f"- Minimum fillable events: `{safe_int(thresholds.get('min_fillable_events'))}`",
            _section("Reviewable Wallets", reviewable, _wallet_line),
            _section("Low-Coverage Wallets", low_coverage, _wallet_line),
            _section("Repeated Co-Entry Pairs", pairs, _pair_line),
            "## Operator Next Step\n\nReview wallets and pairs with enough known/fillable evidence first. Treat low-coverage rows as data collection targets, not promotion candidates.",
        ]
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
    report = {
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
    report["operator_report_markdown"] = render_wallet_replay_review_markdown(report)
    return report
