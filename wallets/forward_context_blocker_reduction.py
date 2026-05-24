from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.forward_calibration_scorecard import safe_int


MODE = "FORWARD_CONTEXT_BLOCKER_REDUCTION_REVIEW_ONLY"
VERSION = "forward_context_blocker_reduction.v1"
FIX_CONTEXT_ACTION = "FIX_FORWARD_ENTRY_CONTEXT"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def recommendation_rows(recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(recommendations.get("recommendations")) if isinstance(row, dict)]


def fix_context_recommendations(recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in recommendation_rows(recommendations) if row.get("recommendation_action") == FIX_CONTEXT_ACTION]


def repair_plan_by_wallet(repair_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("wallet") or ""): row
        for row in as_list(repair_plan.get("wallets"))
        if isinstance(row, dict) and row.get("wallet")
    }


def rejected_by_wallet(rejected_records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rejected_records or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            grouped[wallet].append(row)
    return grouped


def rejected_reason_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("block_reason") or "unknown") for row in rows)


def unique_tokens(rows: list[dict[str, Any]]) -> int:
    return len({row.get("token_mint") for row in rows if row.get("token_mint")})


def recommended_context_action(*, missing_later_snapshot: int, missing_quote_anchor: int, quote_without_snapshot: int, needs_market_snapshot: int) -> str:
    if missing_later_snapshot > 0 and missing_quote_anchor == 0:
        return "repair_market_snapshot"
    if missing_quote_anchor > 0 and missing_later_snapshot == 0:
        return "repair_entry_timestamp"
    if quote_without_snapshot > 0 and quote_without_snapshot >= needs_market_snapshot:
        return "repair_market_snapshot"
    if missing_quote_anchor > 0:
        return "repair_entry_timestamp"
    return "manual_review_required"


def next_operator_step(action: str) -> str:
    return {
        "repair_market_snapshot": "capture or import later market snapshots for the listed token mints, then rerun the resolver",
        "repair_entry_timestamp": "extract a valid same-transaction execution price quote or timestamp anchor, then rerun the resolver",
        "repair_token_metadata": "repair token metadata before using the row in wallet review",
        "repair_outcome_label": "rerun forward outcome resolution after context is repaired",
        "collect_more_forward_rows": "continue bounded forward public-RPC collection",
        "exclude_from_review_until_context_fixed": "keep wallet out of trust validation until context is repaired",
        "manual_review_required": "inspect row-level blockers before choosing repair route",
    }.get(action, "manual review required")


def priority_for_action(action: str) -> int:
    return {
        "repair_market_snapshot": 0,
        "repair_entry_timestamp": 1,
        "manual_review_required": 2,
        "collect_more_forward_rows": 3,
        "exclude_from_review_until_context_fixed": 4,
    }.get(action, 9)


def priority_reason(action: str, *, missing_later_snapshot: int, missing_quote_anchor: int) -> str:
    if action == "repair_market_snapshot":
        return f"{missing_later_snapshot} blocked rows already have quote anchors but need later market snapshots"
    if action == "repair_entry_timestamp":
        return f"{missing_quote_anchor} blocked rows lack valid execution price quotes"
    return "mixed or unclear context blockers require manual inspection"


def wallet_row(
    recommendation: dict[str, Any],
    repair_wallet: dict[str, Any],
    rejected_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons = rejected_reason_counts(rejected_rows)
    missing_later_snapshot = safe_int(reasons.get("missing_later_market_snapshot"))
    missing_quote_anchor = safe_int(reasons.get("missing_valid_execution_price_quote"))
    quote_without_snapshot = safe_int(repair_wallet.get("quote_anchor_without_snapshot_rows"))
    needs_market_snapshot = safe_int(repair_wallet.get("needs_market_snapshot_rows"))
    action = recommended_context_action(
        missing_later_snapshot=missing_later_snapshot,
        missing_quote_anchor=missing_quote_anchor,
        quote_without_snapshot=quote_without_snapshot,
        needs_market_snapshot=needs_market_snapshot,
    )
    blocked_records = safe_int(recommendation.get("blocked_records") or repair_wallet.get("blocked_rows"))
    records = safe_int(recommendation.get("records"))
    return {
        "wallet_address": recommendation.get("wallet"),
        "recommendation_bucket": "fix_context",
        "total_records": records,
        "known_15m_outcomes": safe_int(recommendation.get("known_15m")),
        "runner_15m_count": safe_int(recommendation.get("runner_15m")),
        "flat_15m_count": safe_int(recommendation.get("flat_15m")),
        "loser_15m_count": safe_int(recommendation.get("loser_15m")),
        "blocked_record_count": blocked_records,
        "context_completion_rate": rate(records - blocked_records, records),
        "repair_plan_blocked_rows": safe_int(repair_wallet.get("blocked_rows")),
        "unique_blocked_tokens": unique_tokens(rejected_rows) or safe_int(repair_wallet.get("tokens")),
        "quote_anchor_repair_rows": safe_int(repair_wallet.get("quote_anchor_repair_rows")),
        "quote_anchor_and_snapshot_rows": safe_int(repair_wallet.get("quote_anchor_and_snapshot_rows")),
        "quote_anchor_without_snapshot_rows": quote_without_snapshot,
        "needs_market_snapshot_rows": needs_market_snapshot,
        "partial_context_rows": safe_int(repair_wallet.get("partial_context_rows")),
        "missing_later_market_snapshot_rows": missing_later_snapshot,
        "missing_valid_execution_price_quote_rows": missing_quote_anchor,
        "repair_action": repair_wallet.get("repair_action") or "unknown",
        "recommended_context_action": action,
        "priority_rank": priority_for_action(action),
        "priority_reason": priority_reason(
            action,
            missing_later_snapshot=missing_later_snapshot,
            missing_quote_anchor=missing_quote_anchor,
        ),
        "next_operator_step": next_operator_step(action),
        "promotion_allowed": False,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def sort_wallet(row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        safe_int(row.get("priority_rank")),
        -safe_int(row.get("missing_later_market_snapshot_rows") or row.get("missing_valid_execution_price_quote_rows")),
        -safe_int(row.get("blocked_record_count")),
        str(row.get("wallet_address") or ""),
    )


def build_summary(wallets: list[dict[str, Any]], recommendations: dict[str, Any], resolver_report: dict[str, Any]) -> dict[str, Any]:
    actions = Counter(str(row.get("recommended_context_action") or "unknown") for row in wallets)
    rec_summary = as_dict(recommendations.get("summary"))
    resolver_summary = as_dict(resolver_report.get("summary"))
    return {
        "fix_context_wallets": len(wallets),
        "blocked_records": sum(safe_int(row.get("blocked_record_count")) for row in wallets),
        "repair_plan_blocked_rows": sum(safe_int(row.get("repair_plan_blocked_rows")) for row in wallets),
        "missing_later_market_snapshot_rows": sum(safe_int(row.get("missing_later_market_snapshot_rows")) for row in wallets),
        "missing_valid_execution_price_quote_rows": sum(safe_int(row.get("missing_valid_execution_price_quote_rows")) for row in wallets),
        "priority_market_snapshot_wallets": actions.get("repair_market_snapshot", 0),
        "priority_entry_timestamp_wallets": actions.get("repair_entry_timestamp", 0),
        "manual_review_wallets": actions.get("manual_review_required", 0),
        "resolver_resolved_rows": safe_int(resolver_summary.get("resolved_rows")),
        "resolver_known_15m_outcomes": safe_int(resolver_summary.get("known_15m_outcomes")),
        "promotions_allowed": safe_int(rec_summary.get("promotions_allowed")),
        "wallet_list_mutations": safe_int(rec_summary.get("wallet_list_mutations")),
        "auto_trust_mutations": safe_int(rec_summary.get("auto_trust_mutations")),
    }


def build_forward_context_blocker_reduction(
    *,
    recommendations: dict[str, Any],
    repair_plan: dict[str, Any],
    resolver_report: dict[str, Any],
    rejected_records: list[dict[str, Any]],
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    repair_by_wallet = repair_plan_by_wallet(repair_plan)
    rejected = rejected_by_wallet(rejected_records)
    wallets = sorted(
        [
            wallet_row(rec, repair_by_wallet.get(str(rec.get("wallet") or ""), {}), rejected.get(str(rec.get("wallet") or ""), []))
            for rec in fix_context_recommendations(recommendations)
        ],
        key=sort_wallet,
    )
    return {
        "generated_at": generated_at,
        "run_id": run_id,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(wallets, recommendations, resolver_report),
        "wallets": wallets,
        "operator_note": (
            "Context blocker reduction is review-only. It prioritizes missing entry-context fixes "
            "but cannot repair by guessing, promote wallets, mutate trust, mutate wallet lists, or execute trades."
        ),
    }
