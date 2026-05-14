from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


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


def avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def sample_quality(count: int) -> str:
    if count >= 50:
        return "strong"
    if count >= 20:
        return "usable"
    if count > 0:
        return "thin"
    return "none"


def wallet_ids(record: dict[str, Any]) -> list[str]:
    wallets = record.get("wallets") if isinstance(record.get("wallets"), list) else []
    out = []
    seen = set()
    for row in wallets:
        if isinstance(row, dict):
            wallet = row.get("wallet") or row.get("address")
        else:
            wallet = row
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            out.append(wallet)
            seen.add(wallet)
    return out


def regime_tags(record: dict[str, Any]) -> list[str]:
    ctx = as_dict(record.get("signal_context"))
    regime = as_dict(ctx.get("market_regime"))
    tags = regime.get("tags") if isinstance(regime.get("tags"), list) else []
    return [str(tag) for tag in tags if tag]


def market_number(record: dict[str, Any], key: str) -> float | None:
    ctx = as_dict(record.get("signal_context"))
    market = as_dict(ctx.get("market"))
    return safe_float(market.get(key), None)


def outcome_flags(record: dict[str, Any]) -> dict[str, bool]:
    outcome = as_dict(record.get("later_token_outcome"))
    status = str(outcome.get("status") or "").lower()
    return {
        "known": status not in {"", "unknown", "pending", "open"},
        "runner": bool(outcome.get("runner")) or status == "runner",
        "rug": bool(outcome.get("rug")) or status == "rug",
        "dead": bool(outcome.get("dead")) or status == "dead",
    }


def confidence(total_signals: int, known_outcomes: int) -> dict[str, Any]:
    coverage = round(known_outcomes / total_signals, 4) if total_signals else 0.0
    sample = sample_quality(known_outcomes)
    return {
        "sample_quality": sample,
        "known_outcome_rate": coverage,
        "score": round(min(100.0, known_outcomes * 4 + coverage * 20), 2),
    }


def wallet_outcome_row(wallet: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for record in records if isinstance(record, dict)]
    total = len(records)
    accepted = [record for record in records if record.get("record_type") in {"accepted_trade", "failed_trade"}]
    rejected = [record for record in records if record.get("record_type") == "rejected_signal"]
    known = []
    runner = 0
    rug = 0
    dead = 0
    pnl_values = []
    liquidity_values = []
    token_age_values = []
    regime_counts: Counter[str] = Counter()
    cluster_durations = []

    for record in records:
        flags = outcome_flags(record)
        if flags["known"]:
            known.append(record)
        runner += int(flags["runner"])
        rug += int(flags["rug"])
        dead += int(flags["dead"])
        pnl = safe_float(as_dict(record.get("later_token_outcome")).get("pnl_pct"), None)
        if pnl is not None:
            pnl_values.append(pnl)
        liquidity = market_number(record, "liquidity")
        if liquidity is not None:
            liquidity_values.append(liquidity)
        token_age = market_number(record, "token_age_seconds")
        if token_age is not None:
            token_age_values.append(token_age)
        for tag in regime_tags(record):
            regime_counts[tag] += 1
        cluster_duration = safe_float(as_dict(as_dict(record.get("signal_context")).get("cluster")).get("duration_seconds"), None)
        if cluster_duration is not None:
            cluster_durations.append(cluster_duration)

    conf = confidence(total, len(known))
    avg_pnl = avg(pnl_values)
    runner_rate = round(runner / len(known), 4) if known else 0.0
    rug_rate = round(rug / len(known), 4) if known else 0.0
    promotion_score = max(0.0, max(0.0, avg_pnl or 0.0) + runner_rate * 35)
    demotion_score = max(0.0, rug_rate * 55 + max(0.0, -(avg_pnl or 0.0)))

    return {
        "wallet": wallet,
        "review_only": True,
        "total_signals": total,
        "accepted_signals": len(accepted),
        "rejected_signals": len(rejected),
        "known_outcomes": len(known),
        "runner_participation": runner,
        "rug_participation": rug,
        "dead_participation": dead,
        "runner_participation_rate": runner_rate,
        "rug_participation_rate": rug_rate,
        "average_pnl_after_signal": avg_pnl,
        "average_liquidity": avg(liquidity_values),
        "average_token_age_seconds": avg(token_age_values),
        "average_cluster_duration_seconds": avg(cluster_durations),
        "market_regime_breakdown": dict(regime_counts),
        "promotion_score": round(promotion_score, 4),
        "demotion_score": round(demotion_score, 4),
        "confidence": conf,
        "recommendation": recommendation(promotion_score, demotion_score, conf),
    }


def recommendation(promotion_score: float, demotion_score: float, conf: dict[str, Any]) -> dict[str, Any]:
    sample = conf.get("sample_quality")
    if sample in {"none", "thin"}:
        return {"action": "HOLD_MORE_DATA", "reasons": ["sample below usable threshold"]}
    if demotion_score >= 35 and demotion_score > promotion_score:
        return {"action": "DEMOTION_REVIEW", "reasons": ["negative/rug outcome pressure exceeds promotion evidence"]}
    if promotion_score >= 35 and promotion_score > demotion_score:
        return {"action": "PROMOTION_REVIEW", "reasons": ["positive outcome pressure with usable sample"]}
    return {"action": "HOLD_MORE_DATA", "reasons": ["ledger evidence is not decisive"]}


def build_wallet_outcome_ledger(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for wallet in wallet_ids(record):
            grouped[wallet].append(record)

    rows = {wallet: wallet_outcome_row(wallet, rows) for wallet, rows in sorted(grouped.items())}
    recommendation_counts: Counter[str] = Counter(
        row["recommendation"]["action"] for row in rows.values()
    )
    return {
        "generated_at": time.time(),
        "mode": "WALLET_OUTCOME_LEDGER_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "wallets": len(rows),
            "records": len([record for record in records or [] if isinstance(record, dict)]),
        },
        "recommendation_counts": dict(recommendation_counts),
        "wallets": rows,
    }
