from __future__ import annotations

import time
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def wallet_address(row: Any) -> str | None:
    if isinstance(row, dict):
        wallet = row.get("wallet") or row.get("trackedWalletAddress") or row.get("address")
        return str(wallet) if wallet else None
    if row:
        return str(row)
    return None


def bad_wallet_set(rows: Any) -> set[str]:
    return {wallet for row in as_list(rows) if (wallet := wallet_address(row))}


def paper_watch_set(paper_watch_wallets: Any) -> set[str]:
    rows = as_list(as_dict(paper_watch_wallets).get("wallets"))
    return {wallet for row in rows if (wallet := wallet_address(row))}


def review_action(row: dict[str, Any]) -> str:
    review = as_dict(row.get("review"))
    return str(review.get("action") or row.get("review_action") or row.get("recommendation_action") or "").strip()


def behavior_labels(wallet: str, wallet_behavior: Any) -> list[str]:
    wallets = as_dict(as_dict(wallet_behavior).get("wallets"))
    row = as_dict(wallets.get(wallet))
    labels = row.get("labels")
    if isinstance(labels, list):
        return [str(label) for label in labels]
    return []


def candidate_score(row: dict[str, Any]) -> float:
    return safe_float(row.get("score") or row.get("candidate_score"))


def last_seen_age_hours(row: dict[str, Any], generated_at: float) -> float | None:
    last_seen = safe_float(row.get("last_seen") or row.get("last_seen_at"), 0)
    if last_seen <= 0:
        return None
    return max(0.0, (generated_at - last_seen) / 3600.0)


def sell_ratio(row: dict[str, Any]) -> float:
    sells = safe_float(row.get("sell_events"))
    buys = safe_float(row.get("buy_events"))
    total = buys + sells
    if total <= 0:
        return 0.0
    return round(sells / total, 4)


def quality_components(
    row: dict[str, Any],
    *,
    generated_at: float,
    already_paper_watch: bool,
    labels: list[str],
) -> tuple[float, list[str], list[str], str]:
    score = min(100.0, candidate_score(row)) * 0.45
    reasons: list[str] = []
    risks: list[str] = []

    winner_mints = safe_float(row.get("winner_mints"))
    early_buy_events = safe_float(row.get("early_buy_events"))
    unique_mints = safe_float(row.get("unique_mints"))
    ratio = sell_ratio(row)
    action = review_action(row)
    age_hours = last_seen_age_hours(row, generated_at)

    if winner_mints >= 2:
        score += min(18.0, winner_mints * 4.5)
        reasons.append("repeat runner overlap")
    elif winner_mints >= 1:
        score += 6.0
        reasons.append("runner overlap")

    if early_buy_events >= 6:
        score += min(14.0, early_buy_events * 0.9)
        reasons.append("early-entry evidence")
    elif early_buy_events >= 1:
        score += 3.0

    if unique_mints >= 4:
        score += min(8.0, unique_mints * 1.2)
        reasons.append("multi-token evidence")

    if action in {"PAPER_WATCH", "PROMOTION_REVIEW"}:
        score += 8.0
        reasons.append("review policy supports observation")
    elif action in {"HOLD_REVIEW", "SKIP_REVIEW"}:
        score -= 6.0
        risks.append("review policy hold")

    if already_paper_watch:
        score += 4.0
        reasons.append("already in paper-watch")

    if age_hours is None:
        risks.append("missing recency")
        score -= 4.0
    elif age_hours <= 24:
        score += 7.0
        reasons.append("recent activity")
    elif age_hours > 72:
        score -= 10.0
        risks.append("stale activity")

    if ratio >= 0.6:
        score -= 16.0
        risks.append("sell-heavy observation")
    elif ratio <= 0.2 and early_buy_events > 0:
        score += 4.0
        reasons.append("buy-side skew")

    risky_labels = {"copy-bait", "follower-trap", "rug-exit-fast", "late-buyer"}
    matched_risks = sorted(risky_labels.intersection(labels))
    if matched_risks:
        score -= 12.0
        risks.extend(matched_risks)

    if not reasons:
        reasons.append("limited evidence")

    if score >= 72:
        observation = "STRONG_OBSERVATION"
    elif score >= 52:
        observation = "PAPER_WATCH_REVIEW"
    elif score >= 32:
        observation = "HOLD_REVIEW"
    else:
        observation = "REJECT_REVIEW"
    return round(max(0.0, min(100.0, score)), 2), reasons, risks, observation


def summarize_candidate(
    row: dict[str, Any],
    *,
    generated_at: float,
    paper_watch: set[str],
    wallet_behavior: Any,
) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "")
    labels = behavior_labels(wallet, wallet_behavior)
    score, reasons, risks, observation = quality_components(
        row,
        generated_at=generated_at,
        already_paper_watch=wallet in paper_watch,
        labels=labels,
    )
    return {
        "wallet": wallet,
        "quality_score": score,
        "candidate_score": candidate_score(row),
        "review_action": review_action(row),
        "recommended_observation": observation,
        "winner_mints": int(safe_float(row.get("winner_mints"))),
        "early_buy_events": int(safe_float(row.get("early_buy_events"))),
        "unique_mints": int(safe_float(row.get("unique_mints"))),
        "buy_events": int(safe_float(row.get("buy_events"))),
        "sell_events": int(safe_float(row.get("sell_events"))),
        "sell_ratio": sell_ratio(row),
        "last_seen": row.get("last_seen") or row.get("last_seen_at"),
        "age_hours": last_seen_age_hours(row, generated_at),
        "already_paper_watch": wallet in paper_watch,
        "labels": labels,
        "reasons": reasons,
        "risk_flags": risks,
    }


def summarize_blocked(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "wallet": wallet_address(row),
        "blocked_reason": reason,
        "candidate_score": candidate_score(row),
        "winner_mints": int(safe_float(row.get("winner_mints"))),
        "last_seen": row.get("last_seen") or row.get("last_seen_at"),
    }


def build_summary(ranked: list[dict[str, Any]], blocked: list[dict[str, Any]]) -> dict[str, int]:
    buckets = {
        "active_candidates": len(ranked),
        "blocked_candidates": len(blocked),
        "strong_observation": 0,
        "paper_watch_review": 0,
        "hold_review": 0,
        "reject_review": 0,
        "stale_candidates": 0,
    }
    for row in ranked:
        observation = str(row.get("recommended_observation") or "").lower()
        if observation == "strong_observation":
            buckets["strong_observation"] += 1
        elif observation == "paper_watch_review":
            buckets["paper_watch_review"] += 1
        elif observation == "hold_review":
            buckets["hold_review"] += 1
        elif observation == "reject_review":
            buckets["reject_review"] += 1
        if row.get("age_hours") is not None and safe_float(row.get("age_hours")) > 72:
            buckets["stale_candidates"] += 1
    return buckets


def build_wallet_candidate_quality_report(
    *,
    candidate_wallets: Any,
    paper_watch_wallets: Any,
    bad_wallets: Any,
    wallet_behavior: Any,
    generated_at: float | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    bad = bad_wallet_set(bad_wallets)
    paper_watch = paper_watch_set(paper_watch_wallets)
    active_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []

    for row in as_list(as_dict(candidate_wallets).get("candidates")):
        if not isinstance(row, dict):
            continue
        wallet = wallet_address(row)
        if not wallet:
            continue
        if wallet in bad:
            blocked_rows.append(summarize_blocked(row, "bad_wallet_list"))
            continue
        active_rows.append(summarize_candidate(row, generated_at=generated_at, paper_watch=paper_watch, wallet_behavior=wallet_behavior))

    for row in as_list(as_dict(candidate_wallets).get("blocked_candidates")):
        if isinstance(row, dict) and wallet_address(row):
            blocked_rows.append(summarize_blocked(row, str(row.get("blocked_reason") or "blocked_candidate_source")))

    ranked = sorted(
        active_rows,
        key=lambda row: (safe_float(row.get("quality_score")), safe_float(row.get("winner_mints")), str(row.get("wallet") or "")),
        reverse=True,
    )
    if limit is not None:
        ranked = ranked[: int(limit)]

    return {
        "generated_at": generated_at,
        "mode": "WALLET_CANDIDATE_QUALITY_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "summary": build_summary(ranked, blocked_rows),
        "source_summary": as_dict(candidate_wallets).get("summary") if isinstance(candidate_wallets, dict) else {},
        "ranked_candidates": ranked,
        "blocked_candidates": blocked_rows,
    }
