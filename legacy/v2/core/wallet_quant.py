from __future__ import annotations

import time
from typing import Any

from wallets.wallet_metrics import build_wallet_behavior_profile
from wallets.wallet_relationships import summarize_wallet_relationships
from wallets.wallet_score import behavior_score


PROMOTION_MIN_ENTRIES = 6
PROMOTION_MIN_WIN_RATE = 55.0
DEMOTION_MIN_ENTRIES = 5


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_wallet_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("wallets") or value.get("items") or value.get("candidates") or []
    if not isinstance(value, list):
        return []
    wallets: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            wallet = item.get("wallet") or item.get("trackedWalletAddress") or item.get("address")
        else:
            wallet = item
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            wallets.append(wallet)
            seen.add(wallet)
    return wallets


def wallet_quant_row(
    wallet: str,
    performance: dict[str, Any] | None = None,
    behavior: dict[str, Any] | None = None,
    current_tier: str = "candidate",
) -> dict[str, Any]:
    performance = performance or {}
    behavior = behavior or {}
    entries = safe_int(performance.get("paper_entries") or performance.get("trades") or performance.get("signals") or 0)
    wins = safe_int(performance.get("wins") or performance.get("paper_wins") or 0)
    losses = safe_int(performance.get("losses") or performance.get("paper_losses") or 0)
    total_pnl = safe_float(performance.get("total_pnl") or performance.get("pnl") or 0.0)
    win_rate = (wins / entries * 100.0) if entries else 0.0
    labels = behavior.get("labels") if isinstance(behavior.get("labels"), list) else []
    rolling = behavior.get("rolling") if isinstance(behavior.get("rolling"), dict) else {}
    rolling_7d = rolling.get("7d") if isinstance(rolling.get("7d"), dict) else {}
    rolling_30d = rolling.get("30d") if isinstance(rolling.get("30d"), dict) else {}
    postmortem = behavior.get("postmortem") if isinstance(behavior.get("postmortem"), dict) else {}
    expectancy = safe_float(rolling_30d.get("expectancy"), total_pnl / entries if entries else 0.0)
    row = {
        "wallet": wallet,
        "tier": current_tier,
        "signal_count": safe_int(behavior.get("signal_count") or performance.get("signals") or 0),
        "paper_watch_entries": entries,
        "paper_watch_closed": wins + losses,
        "paper_watch_wins": wins,
        "paper_watch_losses": losses,
        "paper_watch_win_rate": round(win_rate, 2),
        "paper_watch_total_pnl": round(total_pnl, 6),
        "paper_watch_expectancy": round(expectancy, 6),
        "rolling_7d_entries": safe_int(rolling_7d.get("entries")),
        "rolling_30d_entries": safe_int(rolling_30d.get("entries")),
        "rolling_30d_win_rate": round(safe_float(rolling_30d.get("win_rate")), 2),
        "median_hold_seconds_30d": safe_float(rolling_30d.get("median_hold_seconds")),
        "avg_hold_seconds": safe_float(postmortem.get("avg_hold_seconds")),
        "failed_trades": safe_int(postmortem.get("failed_trades")),
        "closed_trades": safe_int(postmortem.get("closed_trades")),
        "exit_reasons": postmortem.get("exit_reasons") if isinstance(postmortem.get("exit_reasons"), dict) else {},
        "failure_reasons": postmortem.get("failure_reasons") if isinstance(postmortem.get("failure_reasons"), dict) else {},
        "labels": [str(label) for label in labels],
        "sample_quality": sample_quality(entries),
    }
    row["behavior_profile"] = build_wallet_behavior_profile(performance, behavior)
    row["wallet_relationships"] = summarize_wallet_relationships(behavior)
    row["behavior_score"] = behavior_score({"metrics": row["behavior_profile"]})
    row["recommendation"] = recommend_wallet_tier(row)
    return row


def sample_quality(entries: int) -> str:
    if entries >= 25:
        return "strong"
    if entries >= PROMOTION_MIN_ENTRIES:
        return "usable"
    if entries > 0:
        return "thin"
    return "none"


def recommend_wallet_tier(row: dict[str, Any]) -> dict[str, Any]:
    entries = safe_int(row.get("paper_watch_entries"))
    win_rate = safe_float(row.get("paper_watch_win_rate"))
    total_pnl = safe_float(row.get("paper_watch_total_pnl"))
    expectancy = safe_float(row.get("paper_watch_expectancy"))
    tier = str(row.get("tier") or "candidate")
    if entries < DEMOTION_MIN_ENTRIES:
        return {"action": "HOLD_MORE_DATA", "reasons": [f"sample below {DEMOTION_MIN_ENTRIES} entries"]}
    if total_pnl < 0 and expectancy < 0:
        return {"action": "DEMOTION_REVIEW", "reasons": ["negative total pnl", "negative expectancy"]}
    if entries >= PROMOTION_MIN_ENTRIES and win_rate >= PROMOTION_MIN_WIN_RATE and total_pnl > 0 and expectancy > 0:
        reasons = ["sample threshold met", "positive total pnl", "positive expectancy", f"win rate {win_rate:.1f}%"]
        return {"action": "PROMOTION_REVIEW" if tier != "trusted" else "KEEP_TRUSTED", "reasons": reasons}
    return {"action": "HOLD_MORE_DATA", "reasons": ["evidence not strong enough for promotion or demotion"]}


def build_wallet_quant_report(
    tracked_wallets: Any,
    paper_watch_wallets: Any,
    performance: dict[str, Any],
    behavior: dict[str, Any],
) -> dict[str, Any]:
    tracked = set(normalize_wallet_list(tracked_wallets))
    paper_watch = set(normalize_wallet_list(paper_watch_wallets))
    performance_wallets = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    behavior_wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    all_wallets = sorted(tracked | paper_watch | set(performance_wallets) | set(behavior_wallets))
    rows = []
    recommendation_counts: dict[str, int] = {}
    for wallet in all_wallets:
        tier = "trusted" if wallet in tracked else "paper_watch" if wallet in paper_watch else "candidate"
        row = wallet_quant_row(
            wallet=wallet,
            performance=performance_wallets.get(wallet) if isinstance(performance_wallets.get(wallet), dict) else {},
            behavior=behavior_wallets.get(wallet) if isinstance(behavior_wallets.get(wallet), dict) else {},
            current_tier=tier,
        )
        action = row["recommendation"]["action"]
        recommendation_counts[action] = recommendation_counts.get(action, 0) + 1
        rows.append(row)
    rows.sort(
        key=lambda item: (
            action_rank(item["recommendation"]["action"]),
            sample_quality_rank(item["sample_quality"]),
            item["paper_watch_entries"],
            item["signal_count"],
            item["paper_watch_expectancy"],
        ),
        reverse=True,
    )
    return {
        "generated_at": time.time(),
        "mode": "WALLET_QUANT_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "wallets": len(rows),
            "trusted": len(tracked),
            "paper_watch": len(paper_watch),
        },
        "recommendation_counts": recommendation_counts,
        "wallets": rows,
    }


def action_rank(action: str) -> int:
    return {
        "PROMOTION_REVIEW": 50,
        "DEMOTION_REVIEW": 40,
        "KEEP_TRUSTED": 30,
        "HOLD_MORE_DATA": 20,
    }.get(str(action), 0)


def sample_quality_rank(value: str) -> int:
    return {
        "strong": 30,
        "usable": 20,
        "thin": 10,
        "none": 0,
    }.get(str(value), 0)
