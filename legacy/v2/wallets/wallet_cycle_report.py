from __future__ import annotations

import time
from collections import Counter
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
        wallet = row.get("trackedWalletAddress") or row.get("wallet") or row.get("address")
        return str(wallet) if wallet else None
    if row:
        return str(row)
    return None


def tracked_count(rows: Any) -> int:
    return len({wallet for row in as_list(rows) if (wallet := wallet_address(row))})


def paper_watch_rows(paper_watch_wallets: Any) -> list[dict[str, Any]]:
    rows = as_dict(paper_watch_wallets).get("wallets")
    out = []
    for row in as_list(rows):
        wallet = wallet_address(row)
        if not wallet:
            continue
        out.append(dict(row) if isinstance(row, dict) else {"wallet": wallet})
    return out


def bad_wallet_count(rows: Any) -> int:
    return len({wallet for row in as_list(rows) if (wallet := wallet_address(row))})


def review_decision_counts(review_decisions: Any) -> dict[str, int]:
    counts = Counter()
    for row in as_list(as_dict(review_decisions).get("decisions")):
        if not isinstance(row, dict) or not row.get("approved"):
            continue
        decision = str(row.get("decision") or row.get("action") or "").strip().lower()
        if decision in {"approve_promotion", "promote", "promote_to_tracked"}:
            counts["approved_promotion"] += 1
        elif decision in {"approve_demotion", "demote", "demote_off_watch"}:
            counts["approved_demotion"] += 1
    return {
        "approved_promotion": counts["approved_promotion"],
        "approved_demotion": counts["approved_demotion"],
        "approved_total": counts["approved_promotion"] + counts["approved_demotion"],
    }


def candidate_summary(row: dict[str, Any]) -> dict[str, Any]:
    evidence = as_dict(row.get("evidence"))
    action = str(row.get("recommendation_action") or "")
    score_key = "promotion_score" if action == "PROMOTION_REVIEW" else "demotion_score"
    return {
        "wallet": row.get("wallet"),
        "recommendation_action": action,
        "audit_status": row.get("audit_status"),
        "known_outcomes": evidence.get("known_outcomes"),
        "score": evidence.get(score_key),
        "source": evidence.get("source"),
    }


def sort_candidate(row: dict[str, Any]) -> tuple[float, float, str]:
    evidence = as_dict(row.get("evidence"))
    action = str(row.get("recommendation_action") or "")
    primary = evidence.get("promotion_score") if action == "PROMOTION_REVIEW" else evidence.get("demotion_score")
    return (safe_float(primary), safe_float(evidence.get("known_outcomes")), str(row.get("wallet") or ""))


def pending_candidates(candidate_audit: Any, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    rows = [row for row in as_list(as_dict(candidate_audit).get("candidates")) if isinstance(row, dict)]
    promotions = [row for row in rows if row.get("recommendation_action") == "PROMOTION_REVIEW"]
    demotions = [row for row in rows if row.get("recommendation_action") == "DEMOTION_REVIEW"]
    return {
        "promotion_review": [candidate_summary(row) for row in sorted(promotions, key=sort_candidate, reverse=True)[:limit]],
        "demotion_review": [candidate_summary(row) for row in sorted(demotions, key=sort_candidate, reverse=True)[:limit]],
    }


def build_attention(counts: dict[str, int], review_queue: dict[str, int], replay: dict[str, int]) -> list[str]:
    attention = []
    if review_queue.get("promotion_review", 0) > 0:
        attention.append("promotion_reviews_pending")
    if review_queue.get("demotion_review", 0) > 0:
        attention.append("demotion_reviews_pending")
    if counts.get("blocked_paper_watch_wallets", 0) > 0:
        attention.append("bad_wallets_blocked_from_reentry")
    if replay.get("wallets", 0) == 0:
        attention.append("replay_scorecard_missing")
    return attention


def build_wallet_cycle_report(
    *,
    tracked_wallets: Any,
    paper_watch_wallets: Any,
    bad_wallets: Any,
    candidate_audit: Any,
    wallet_replay_scorecard: Any,
    review_decisions: Any,
    wallet_list_update_audit: Any,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    paper_rows = paper_watch_rows(paper_watch_wallets)
    blocked_rows = [row for row in paper_rows if row.get("status") == "demote_review"]
    active_rows = [row for row in paper_rows if row.get("status") != "demote_review"]
    audit_counts = as_dict(as_dict(candidate_audit).get("counts"))
    scorecard_counts = as_dict(as_dict(wallet_replay_scorecard).get("counts"))
    ecosystem = as_dict(as_dict(wallet_replay_scorecard).get("ecosystems"))
    latest_apply = as_list(as_dict(wallet_list_update_audit).get("updates"))
    counts = {
        "tracked_wallets": tracked_count(tracked_wallets),
        "paper_watch_wallets": len(paper_rows),
        "active_paper_watch_wallets": len(active_rows),
        "blocked_paper_watch_wallets": len(blocked_rows),
        "bad_wallets": bad_wallet_count(bad_wallets),
    }
    review_queue = {
        "promotion_review": int(audit_counts.get("promotion_review") or 0),
        "demotion_review": int(audit_counts.get("demotion_review") or 0),
        "resolved": int(audit_counts.get("resolved") or 0),
    }
    replay = {
        "events": int(scorecard_counts.get("events") or 0),
        "wallets": int(scorecard_counts.get("wallets") or 0),
        "co_entry_pairs": int(scorecard_counts.get("co_entry_pairs") or 0),
        "repeated_pair_count": int(ecosystem.get("repeated_pair_count") or 0),
    }
    return {
        "generated_at": generated_at,
        "mode": "WALLET_CYCLE_REPORT_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "counts": counts,
        "review_queue": review_queue,
        "review_decisions": review_decision_counts(review_decisions),
        "replay": replay,
        "latest_apply": latest_apply[0] if latest_apply else {},
        "pending_candidates": pending_candidates(candidate_audit),
        "attention": build_attention(counts, review_queue, replay),
    }
