from __future__ import annotations

import time
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any


WINDOWS = ("30s", "2m", "5m", "15m")
KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser", "flat"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def wallet_ids(event: dict[str, Any]) -> list[str]:
    wallets = event.get("wallets") if isinstance(event.get("wallets"), list) else []
    out = []
    seen = set()
    for row in wallets:
        wallet = row.get("wallet") if isinstance(row, dict) else row
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            out.append(wallet)
            seen.add(wallet)
    return out


def event_regime_tags(event: dict[str, Any]) -> list[str]:
    context = as_dict(event.get("decision_context"))
    regime = as_dict(context.get("market_regime"))
    tags = regime.get("tags") if isinstance(regime.get("tags"), list) else []
    return [str(tag) for tag in tags if tag]


def event_windows(event: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return as_dict(as_dict(event.get("later_outcome")).get("windows"))


def outcome_type_for_window(event: dict[str, Any], window: str) -> str:
    outcome = as_dict(event_windows(event).get(window))
    return str(outcome.get("outcome_type") or "unknown").lower()


def window_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    total = len(events)
    for window in WINDOWS:
        counts: Counter[str] = Counter(outcome_type_for_window(event, window) for event in events)
        known = sum(counts.get(label, 0) for label in KNOWN_OUTCOMES)
        row = {
            "total": total,
            "known": known,
            "unknown": counts.get("unknown", 0),
            "runner": counts.get("runner", 0),
            "rug": counts.get("rug", 0),
            "dead": counts.get("dead", 0),
            "loser": counts.get("loser", 0),
            "flat": counts.get("flat", 0),
            "known_rate": round(known / total, 4) if total else 0.0,
            "runner_rate_known": round(counts.get("runner", 0) / known, 4) if known else 0.0,
            "rug_rate_known": round(counts.get("rug", 0) / known, 4) if known else 0.0,
        }
        out[window] = row
    return out


def fill_counts(events: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        str(as_dict(event.get("execution_assumptions")).get("fill_status") or "unknown_liquidity")
        for event in events
    )


def partner_rows(wallet: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for event in events:
        ids = wallet_ids(event)
        if wallet not in ids:
            continue
        for other in ids:
            if other != wallet:
                counts[other] += 1
    return [{"wallet": name, "count": count} for name, count in counts.most_common()]


def regime_breakdown(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        for tag in event_regime_tags(event):
            counts[tag] += 1
    return dict(counts)


def signal_quality(windows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    known_15m = windows.get("15m", {}).get("known_rate", 0.0)
    runner_15m = windows.get("15m", {}).get("runner_rate_known", 0.0)
    rug_15m = windows.get("15m", {}).get("rug_rate_known", 0.0)
    if known_15m < 0.2:
        status = "insufficient_replay_coverage"
    elif runner_15m > rug_15m:
        status = "positive_replay_signal"
    elif rug_15m > runner_15m:
        status = "negative_replay_signal"
    else:
        status = "mixed_replay_signal"
    return {
        "known_rate_30s": windows.get("30s", {}).get("known_rate", 0.0),
        "known_rate_2m": windows.get("2m", {}).get("known_rate", 0.0),
        "known_rate_5m": windows.get("5m", {}).get("known_rate", 0.0),
        "known_rate_15m": known_15m,
        "runner_rate_known_15m": runner_15m,
        "rug_rate_known_15m": rug_15m,
        "review_status": status,
    }


def wallet_row(wallet: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    fills = fill_counts(events)
    windows = window_stats(events)
    return {
        "wallet": wallet,
        "review_only": True,
        "total_events": len(events),
        "fillable_events": fills.get("fillable_with_assumptions", 0),
        "failed_liquidity_events": fills.get("failed_liquidity_floor", 0),
        "unknown_liquidity_events": fills.get("unknown_liquidity", 0),
        "windows": windows,
        "signal_quality": signal_quality(windows),
        "regime_breakdown": regime_breakdown(events),
        "co_entry_partners": partner_rows(wallet, events),
    }


def top_co_entry_pairs(events: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for event in events:
        ids = sorted(wallet_ids(event))
        for left, right in combinations(ids, 2):
            counts[(left, right)] += 1
    return [
        {"wallets": [left, right], "count": count}
        for (left, right), count in counts.most_common(limit)
    ]


def build_wallet_replay_scorecard(events: list[dict[str, Any]]) -> dict[str, Any]:
    valid_events = [event for event in events or [] if isinstance(event, dict)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in valid_events:
        for wallet in wallet_ids(event):
            grouped[wallet].append(event)
    rows = {wallet: wallet_row(wallet, rows) for wallet, rows in sorted(grouped.items())}
    pairs = top_co_entry_pairs(valid_events)
    return {
        "generated_at": time.time(),
        "mode": "WALLET_REPLAY_SCORECARD_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "events": len(valid_events),
            "wallets": len(rows),
            "co_entry_pairs": len(pairs),
        },
        "ecosystems": {
            "top_co_entry_pairs": pairs,
            "repeated_pair_count": sum(1 for pair in pairs if pair["count"] >= 2),
        },
        "wallets": rows,
    }
