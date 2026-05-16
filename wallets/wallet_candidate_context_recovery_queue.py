from __future__ import annotations

import time
from collections import Counter
from typing import Any


SOURCE_BUCKET_PRIORITY = {
    "paper_watch_candidate": 0,
    "observe_more": 1,
    "risk_review": 2,
}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _recovery_target(row: dict[str, Any]) -> dict[str, Any]:
    missing = as_dict(row.get("missing"))
    source_bucket = str(row.get("source_bucket") or "unknown")
    return {
        "wallet": row.get("wallet"),
        "recovery_priority": SOURCE_BUCKET_PRIORITY.get(source_bucket, 99),
        "source_bucket": source_bucket,
        "audit_status": row.get("audit_status"),
        "recommendation_action": row.get("recommendation_action"),
        "known_outcomes": safe_int(row.get("known_outcomes")),
        "round_trip_lifecycles": safe_int(row.get("round_trip_lifecycles")),
        "missing_known_outcomes": safe_int(missing.get("known_outcomes")),
        "missing_round_trip_lifecycles": safe_int(missing.get("round_trip_lifecycles")),
        "required_context": ["outcome_labels", "decision_time_market_context"],
        "suggested_sources": [
            "wallet_history_evidence_enriched",
            "missing_market_context_report",
            "historical_replay_events",
            "raw_wallet_transactions",
            "trusted_historical_market_snapshot_gate",
        ],
        "notes": [str(note) for note in as_list(row.get("notes"))[:3]],
    }


def build_wallet_candidate_context_recovery_queue(
    *,
    collection_plan: dict[str, Any],
    blocker_reducer: dict[str, Any] | None = None,
    generated_at: float | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    plan = as_dict(collection_plan)
    reducer = as_dict(blocker_reducer)
    targets = [
        _recovery_target(row)
        for row in as_list(plan.get("targets"))
        if isinstance(row, dict)
        and row.get("wallet")
        and row.get("next_collection_step") == "COLLECT_OUTCOMES_AND_MARKET_CONTEXT"
    ]
    targets.sort(key=lambda row: (
        row["recovery_priority"],
        -row["missing_known_outcomes"],
        -row["missing_round_trip_lifecycles"],
        str(row.get("wallet") or ""),
    ))
    source_counts = Counter(row["source_bucket"] for row in targets)
    missing_known = sum(row["missing_known_outcomes"] for row in targets)
    missing_round_trips = sum(row["missing_round_trip_lifecycles"] for row in targets)
    blocker_counts = as_dict(reducer.get("primary_blocker_counts"))
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "total_recovery_targets": len(targets),
            "reported_blocker_count": safe_int(blocker_counts.get("missing_outcomes_and_market_context"), len(targets)),
            "paper_watch_targets": source_counts["paper_watch_candidate"],
            "observe_more_targets": source_counts["observe_more"],
            "other_targets": len(targets) - source_counts["paper_watch_candidate"] - source_counts["observe_more"],
            "missing_known_outcomes": missing_known,
            "missing_round_trip_lifecycles": missing_round_trips,
        },
        "source_bucket_counts": dict(source_counts),
        "count": min(len(targets), int(limit)),
        "targets": targets[: int(limit)],
        "operator_note": "Review-only context recovery queue. Use it to prioritize evidence collection for wallets blocked by missing outcomes plus market context; it does not fetch, approve, apply, trade, or mutate wallet lists.",
    }
