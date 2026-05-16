from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


MODE = "WALLET_EVIDENCE_SCORECARD_REVIEW_ONLY"
SCORECARD_VERSION = "wallet_evidence_scorecard.v1"


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def known_outcome(row: dict[str, Any]) -> bool:
    return as_dict(row.get("later_token_outcome")).get("outcome_type") not in (None, "", "unknown")


def has_entry_context(row: dict[str, Any]) -> bool:
    return as_dict(row.get("estimated_entry_context")).get("price") not in (None, "")


def enrichment_by_wallet(wallet_evidence_enrichment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in wallet_evidence_enrichment.get("evidence_records") or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            grouped[wallet].append(row)

    out: dict[str, dict[str, Any]] = {}
    for wallet, rows in grouped.items():
        statuses = Counter(str(row.get("enrichment_status") or "UNKNOWN") for row in rows)
        known_rows = sum(1 for row in rows if known_outcome(row))
        out[wallet] = {
            "evidence_rows": len(rows),
            "entry_context_rows": sum(1 for row in rows if has_entry_context(row)),
            "known_outcome_rows": known_rows,
            "missing_market_context_rows": statuses["MISSING_MARKET_CONTEXT"],
            "missing_outcome_label_rows": len(rows) - known_rows,
            "enriched_rows": statuses["ENRICHED"],
            "runner_rows": sum(1 for row in rows if as_dict(row.get("later_token_outcome")).get("runner")),
            "rug_rows": sum(1 for row in rows if as_dict(row.get("later_token_outcome")).get("rug")),
        }
    return out


def lifecycle_for_wallet(wallet: str, wallet_evidence_lifecycle: dict[str, Any]) -> dict[str, Any]:
    row = as_dict(as_dict(wallet_evidence_lifecycle.get("wallets")).get(wallet))
    return {
        "lifecycle_mints": safe_int(row.get("lifecycle_mints")),
        "round_trip_lifecycles": safe_int(row.get("round_trip_lifecycles")),
        "buy_only_lifecycles": safe_int(row.get("buy_only_lifecycles")),
        "sell_only_lifecycles": safe_int(row.get("sell_only_lifecycles")),
        "average_hold_duration_seconds": row.get("average_hold_duration_seconds"),
        "median_hold_duration_seconds": row.get("median_hold_duration_seconds"),
        "short_hold_round_trips": safe_int(row.get("short_hold_round_trips")),
        "long_hold_round_trips": safe_int(row.get("long_hold_round_trips")),
        "net_accumulation_mints": safe_int(row.get("net_accumulation_mints")),
        "net_distribution_mints": safe_int(row.get("net_distribution_mints")),
    }


def recommendation_rows(wallet_evidence_recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in wallet_evidence_recommendations.get("recommendations") or []
        if isinstance(row, dict) and str(row.get("wallet") or "").strip()
    ]


def evidence_blockers(
    *,
    bucket: str,
    promotion_gate: str,
    enrichment: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if bucket == "risk_review":
        blockers.append("manual_risk_review_required")
    if bucket == "hold_no_edge":
        blockers.append("held_for_negative_or_rug_evidence")
    if bucket == "observe_more":
        blockers.append("insufficient_wallet_history")
    if promotion_gate == "do_not_promote_yet":
        blockers.append("trusted_promotion_blocked")
    if safe_int(enrichment.get("missing_market_context_rows")) > 0:
        blockers.append("missing_market_context")
    if safe_int(enrichment.get("known_outcome_rows")) == 0 or safe_int(enrichment.get("missing_outcome_label_rows")) > 0:
        blockers.append("missing_known_outcomes")
    return sorted(set(blockers))


def next_action_for(bucket: str, blockers: list[str]) -> str:
    if "manual_risk_review_required" in blockers:
        return "manual_risk_review"
    if "held_for_negative_or_rug_evidence" in blockers:
        return "hold_out_of_paper_watch"
    if "missing_market_context" in blockers and "missing_known_outcomes" in blockers:
        return "collect_outcomes_and_market_context"
    if "missing_market_context" in blockers:
        return "collect_market_context"
    if "missing_known_outcomes" in blockers:
        return "collect_outcome_labels"
    if bucket == "observe_more":
        return "collect_more_wallet_history"
    if bucket == "paper_watch_candidate":
        return "keep_observing_paper_watch_candidate"
    return "review_manually"


def scorecard_row(
    recommendation: dict[str, Any],
    *,
    lifecycle_report: dict[str, Any],
    enrichment_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    wallet = str(recommendation.get("wallet") or "").strip()
    bucket = str(recommendation.get("bucket") or "observe_more")
    promotion_gate = str(recommendation.get("promotion_gate") or "do_not_promote_yet")
    enrichment = enrichment_lookup.get(wallet, {
        "evidence_rows": 0,
        "entry_context_rows": 0,
        "known_outcome_rows": 0,
        "missing_market_context_rows": 0,
        "missing_outcome_label_rows": 0,
        "enriched_rows": 0,
        "runner_rows": 0,
        "rug_rows": 0,
    })
    blockers = evidence_blockers(bucket=bucket, promotion_gate=promotion_gate, enrichment=enrichment)
    return {
        "wallet": wallet,
        "recommendation_bucket": bucket,
        "promotion_gate": promotion_gate,
        "trusted_promotion_allowed": False,
        "reason_codes": recommendation.get("reason_codes") if isinstance(recommendation.get("reason_codes"), list) else [],
        "wallet_history": as_dict(recommendation.get("wallet_history")),
        "lifecycle": lifecycle_for_wallet(wallet, lifecycle_report),
        "enrichment": enrichment,
        "evidence_blockers": blockers,
        "next_action": next_action_for(bucket, blockers),
    }


def summarize_scorecard(rows: list[dict[str, Any]], readiness_summary: dict[str, Any]) -> dict[str, Any]:
    buckets = Counter(str(row.get("recommendation_bucket") or "observe_more") for row in rows)
    next_actions = Counter(str(row.get("next_action") or "review_manually") for row in rows)
    return {
        "stage3_engine_completion_pct": 100,
        "stage3_evidence_contract_completion_pct": safe_int(readiness_summary.get("stage3_evidence_contract_completion_pct")),
        "wallet_score_readiness_pct": safe_int(readiness_summary.get("wallet_score_readiness_pct")),
        "score_ready_market_context_records": safe_int(readiness_summary.get("score_ready_market_context_records")),
        "wallets_reviewed": len(rows),
        "paper_watch_candidate": buckets["paper_watch_candidate"],
        "observe_more": buckets["observe_more"],
        "risk_review": buckets["risk_review"],
        "hold_no_edge": buckets["hold_no_edge"],
        "trusted_promotions_allowed": sum(1 for row in rows if row.get("trusted_promotion_allowed") is True),
        "wallets_with_round_trips": sum(1 for row in rows if safe_int(as_dict(row.get("lifecycle")).get("round_trip_lifecycles")) > 0),
        "wallets_with_known_outcomes": sum(1 for row in rows if safe_int(as_dict(row.get("enrichment")).get("known_outcome_rows")) > 0),
        "wallets_missing_market_context": sum(1 for row in rows if safe_int(as_dict(row.get("enrichment")).get("missing_market_context_rows")) > 0),
        "next_actions": dict(next_actions),
    }


def build_wallet_evidence_scorecard_report(
    *,
    wallet_evidence_readiness: dict[str, Any],
    wallet_evidence_recommendations: dict[str, Any],
    wallet_evidence_lifecycle: dict[str, Any],
    wallet_evidence_enrichment: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    readiness_summary = as_dict(wallet_evidence_readiness.get("summary"))
    enrichment_lookup = enrichment_by_wallet(wallet_evidence_enrichment)
    rows = [
        scorecard_row(row, lifecycle_report=wallet_evidence_lifecycle, enrichment_lookup=enrichment_lookup)
        for row in recommendation_rows(wallet_evidence_recommendations)
    ]
    summary = summarize_scorecard(rows, readiness_summary)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "scorecard_version": SCORECARD_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": (
            "Stage 3 evidence engine is complete as review infrastructure; wallet scores remain blocked "
            "until outcome and score-ready market-context coverage improve."
        ),
        "summary": summary,
        "wallets": rows,
    }
