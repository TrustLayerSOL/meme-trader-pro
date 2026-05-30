from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "WALLET_EVIDENCE_RECOMMENDATIONS_REVIEW_ONLY"
RECOMMENDATION_VERSION = "wallet_evidence_recommendations.v1"


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


def risk_flags(candidate: dict[str, Any]) -> list[str]:
    flags = candidate.get("risk_flags")
    return [str(flag) for flag in flags] if isinstance(flags, list) else []


def wallet_metrics(history_row: dict[str, Any]) -> dict[str, Any]:
    metrics = as_dict(history_row.get("metrics"))
    usable_rows = safe_int(metrics.get("total_usable_evidence_rows"), safe_int(history_row.get("evidence_rows_created")))
    return {
        "target_status": history_row.get("target_status") or history_row.get("status"),
        "priority_score": safe_float(history_row.get("priority_score")),
        "evidence_rows_created": safe_int(history_row.get("evidence_rows_created")),
        "buy_events": safe_int(history_row.get("buy_events")),
        "sell_events": safe_int(history_row.get("sell_events")),
        "unique_mints": safe_int(history_row.get("unique_mints")),
        "total_usable_evidence_rows": usable_rows,
        "runner_participation_rate": safe_float(metrics.get("runner_participation_rate")),
        "rug_participation_rate": safe_float(metrics.get("rug_participation_rate")),
        "repeated_rug_association": safe_int(metrics.get("repeated_rug_association")),
        "evidence_confidence_score": safe_float(metrics.get("evidence_confidence_score")),
        "minimum_additional_evidence_needed": safe_int(metrics.get("minimum_additional_evidence_needed")),
        "missing_data_ratio": safe_float(metrics.get("missing_data_ratio")),
    }


def trust_gate(wallet_evidence_readiness: dict[str, Any]) -> dict[str, Any]:
    summary = as_dict(wallet_evidence_readiness.get("summary"))
    score_ready_pct = safe_int(summary.get("wallet_score_readiness_pct"))
    score_ready_records = safe_int(summary.get("score_ready_market_context_records"))
    allowed = score_ready_pct >= 70 and score_ready_records > 0
    reason = (
        "wallet_score_readiness_passed"
        if allowed
        else f"wallet_score_readiness_pct={score_ready_pct}; score_ready_market_context_records={score_ready_records}"
    )
    return {
        "trusted_promotion_allowed": allowed,
        "promotion_gate": "trusted_review_possible" if allowed else "do_not_promote_yet",
        "reason": reason,
    }


def bucket_for_wallet(candidate: dict[str, Any], metrics: dict[str, Any]) -> tuple[str, list[str]]:
    flags = risk_flags(candidate)
    if flags or candidate.get("next_collection_step") == "REVIEW_RISK_FLAGS_FIRST":
        return "risk_review", ["unresolved_risk_flags"]

    if metrics["rug_participation_rate"] > 0 or metrics["repeated_rug_association"] > 0:
        return "hold_no_edge", ["known_rug_exposure"]

    if metrics["total_usable_evidence_rows"] >= 10 and metrics["minimum_additional_evidence_needed"] <= 0:
        return "paper_watch_candidate", ["usable_wallet_history_without_known_rug_exposure"]

    reasons = ["insufficient_wallet_history"]
    if metrics["total_usable_evidence_rows"] == 0:
        reasons.append("no_wallet_history_rows")
    if metrics["minimum_additional_evidence_needed"] > 0:
        reasons.append("additional_evidence_needed")
    return "observe_more", reasons


def recommendation_row(
    *,
    wallet: str,
    candidate: dict[str, Any],
    history_row: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    metrics = wallet_metrics(history_row)
    bucket, reason_codes = bucket_for_wallet(candidate, metrics)
    promotion_gate = str(gate["promotion_gate"])
    labels = [bucket]
    if promotion_gate == "do_not_promote_yet":
        labels.append(promotion_gate)
    return {
        "wallet": wallet,
        "bucket": bucket,
        "labels": labels,
        "promotion_gate": promotion_gate,
        "trusted_promotion_allowed": bool(gate["trusted_promotion_allowed"]) and bucket == "paper_watch_candidate",
        "auto_apply": False,
        "reason_codes": reason_codes,
        "candidate": {
            "priority_score": safe_float(candidate.get("priority_score")),
            "quality_score": safe_float(candidate.get("quality_score")),
            "next_collection_step": candidate.get("next_collection_step"),
            "risk_flags": risk_flags(candidate),
            "local_replay_events": safe_int(candidate.get("local_replay_events")),
            "fillable_events": safe_int(candidate.get("fillable_events")),
            "unknown_15m_events": safe_int(candidate.get("unknown_15m_events")),
        },
        "wallet_history": metrics,
    }


def history_by_wallet(wallet_history_backfill: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in wallet_history_backfill.get("wallets") or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            rows[wallet] = row
    return rows


def target_by_wallet(candidate_backfill_targets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in candidate_backfill_targets.get("targets") or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            rows[wallet] = row
    return rows


def ordered_wallets(targets: dict[str, dict[str, Any]], histories: dict[str, dict[str, Any]]) -> list[str]:
    wallets = list(targets)
    wallets.extend(wallet for wallet in histories if wallet not in targets)
    return wallets


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets = Counter(str(row.get("bucket") or "observe_more") for row in rows)
    label_counts = Counter(label for row in rows for label in row.get("labels", []))
    return {
        "wallets_reviewed": len(rows),
        "paper_watch_candidate": buckets["paper_watch_candidate"],
        "observe_more": buckets["observe_more"],
        "risk_review": buckets["risk_review"],
        "hold_no_edge": buckets["hold_no_edge"],
        "do_not_promote_yet": label_counts["do_not_promote_yet"],
        "trusted_promotions": sum(1 for row in rows if row.get("trusted_promotion_allowed") is True),
        "auto_applied": sum(1 for row in rows if row.get("auto_apply") is True),
    }


def next_actions(summary: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if safe_int(summary.get("risk_review")):
        actions.append("Manually resolve risk-review wallets before allowing them into paper-watch review.")
    if safe_int(summary.get("paper_watch_candidate")):
        actions.append("Keep paper-watch candidates in observation only until score-ready market context and outcome labels improve.")
    if safe_int(summary.get("hold_no_edge")):
        actions.append("Keep hold-no-edge wallets out of paper-watch until rug association is disproven with more evidence.")
    if safe_int(summary.get("observe_more")):
        actions.append("Collect more wallet-history and outcome evidence for observe-more wallets.")
    return actions or ["No wallets require recommendation action."]


def build_wallet_evidence_recommendations(
    *,
    candidate_backfill_targets: dict[str, Any],
    wallet_history_backfill: dict[str, Any],
    wallet_evidence_readiness: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    targets = target_by_wallet(candidate_backfill_targets)
    histories = history_by_wallet(wallet_history_backfill)
    gate = trust_gate(wallet_evidence_readiness)
    rows = [
        recommendation_row(
            wallet=wallet,
            candidate=targets.get(wallet, {}),
            history_row=histories.get(wallet, {}),
            gate=gate,
        )
        for wallet in ordered_wallets(targets, histories)
    ]
    summary = summarize(rows)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "recommendation_version": RECOMMENDATION_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": "Wallet evidence recommendations are review-only; no wallet is auto-promoted or traded.",
        "global_guard": gate,
        "summary": summary,
        "recommendations": rows,
        "next_required_actions": next_actions(summary),
    }
