from __future__ import annotations

import statistics
import time
from collections import Counter, defaultdict
from typing import Any

from wallets.forward_calibration_scorecard import KNOWN_OUTCOMES
from wallets.forward_calibration_scorecard import safe_int
from wallets.forward_merged_calibration_scorecard import merge_records


MODE = "FORWARD_WALLET_TRUST_REVIEW_PACKET_REVIEW_ONLY"
VERSION = "forward_wallet_trust_review_packet.v1"

TOP_WALLET = "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY"

REVIEW_ACTION = "REVIEW_FORWARD_SIGNAL_MANUALLY"
REVIEW_BUCKET = "review_behavioral_signal"

VALID_REVIEW_STATUSES = {
    "continue_trust_validation",
    "collect_more_evidence",
    "fix_context_before_review",
    "likely_flat_noise",
    "manual_review_required",
    "reject_for_now",
}

VALID_EVIDENCE_QUALITIES = {
    "clean_forward_context",
    "repaired_context",
    "blocked_missing_context",
    "blocked_missing_market_snapshot",
    "blocked_missing_outcome",
    "manual_review_required",
}

BUCKET_MAP = {
    "REVIEW_FORWARD_SIGNAL_MANUALLY": "review_behavioral_signal",
    "FIX_FORWARD_ENTRY_CONTEXT": "fix_context",
    "HOLD_NO_PROMOTION_FLAT_ONLY": "flat_noise_candidate",
    "COLLECT_MORE_FORWARD_EVIDENCE": "collect_more_evidence",
    "RISK_REVIEW_REQUIRED": "risk_review",
}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 6) if values else None


def average(values: list[float]) -> float | None:
    return round(float(sum(values) / len(values)), 6) if values else None


def outcome(row: dict[str, Any], window: str = "15m") -> str:
    labels = as_dict(row.get("outcome_window_labels"))
    return str(as_dict(labels.get(window)).get("outcome_type") or "unknown").lower()


def outcome_payload(row: dict[str, Any], window: str = "15m") -> dict[str, Any]:
    return as_dict(as_dict(row.get("outcome_window_labels")).get(window))


def known_outcome(label: str) -> bool:
    return str(label).lower() in KNOWN_OUTCOMES


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def has_market_context(row: dict[str, Any]) -> bool:
    ctx = entry_context(row)
    return bool(ctx.get("source") or ctx.get("price") or ctx.get("market_cap") or ctx.get("liquidity"))


def is_blocked(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    return status.startswith("blocked_") or bool(row.get("block_reasons"))


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = [str(item) for item in as_list(row.get("block_reasons")) if str(item)]
    status = str(row.get("status") or "")
    if status.startswith("blocked_") and status not in reasons:
        reasons.append(status)
    if not has_market_context(row) and "missing_forward_entry_context" not in reasons:
        reasons.append("missing_forward_entry_context")
    return reasons


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or "").strip()


def recommendation_rows(recommendations: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(recommendations.get("recommendations")) if isinstance(row, dict)]


def scorecard_rows(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    inner = as_dict(scorecard.get("scorecard"))
    return [row for row in as_list(inner.get("wallets")) if isinstance(row, dict)]


def review_wallets(
    *,
    recommendations: dict[str, Any],
    merged_scorecard: dict[str, Any],
    bucket: str,
    limit: int,
) -> list[str]:
    wanted_action = {
        "review_behavioral_signal": REVIEW_ACTION,
        "fix_context": "FIX_FORWARD_ENTRY_CONTEXT",
        "flat_noise_candidate": "HOLD_NO_PROMOTION_FLAT_ONLY",
        "collect_more_evidence": "COLLECT_MORE_FORWARD_EVIDENCE",
        "risk_review": "RISK_REVIEW_REQUIRED",
    }.get(bucket)
    rows = [
        row for row in recommendation_rows(recommendations)
        if not wanted_action or row.get("recommendation_action") == wanted_action
    ]
    by_wallet_score = {str(row.get("wallet")): row for row in scorecard_rows(merged_scorecard)}

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        wallet = str(row.get("wallet") or "")
        score = by_wallet_score.get(wallet, {})
        return (
            -safe_int(row.get("runner_15m") or score.get("runner_15m")),
            -safe_int(row.get("known_15m") or score.get("known_15m")),
            safe_int(row.get("blocked_records") or score.get("blocked_records")),
            wallet,
        )

    wallets = [str(row.get("wallet") or "") for row in sorted(rows, key=sort_key) if row.get("wallet")]
    return wallets[: max(0, limit)]


def evidence_quality(row: dict[str, Any], repaired_ids: set[str]) -> str:
    if event_id(row) in repaired_ids or row.get("entry_context_repair"):
        return "repaired_context"
    reasons = block_reasons(row)
    if any("market_snapshot" in reason for reason in reasons):
        return "blocked_missing_market_snapshot"
    if any("context" in reason or "quote" in reason for reason in reasons):
        return "blocked_missing_context"
    if outcome(row) == "unknown":
        return "blocked_missing_outcome"
    if has_market_context(row):
        return "clean_forward_context"
    return "manual_review_required"


def event_evidence_row(row: dict[str, Any], repaired_ids: set[str], source_file: str) -> dict[str, Any]:
    ctx = entry_context(row)
    out = outcome_payload(row)
    label = outcome(row)
    reasons = block_reasons(row)
    return {
        "wallet_address": wallet_address(row),
        "token_address": row.get("token_mint"),
        "token_symbol": row.get("token_symbol"),
        "action": row.get("observed_action"),
        "observed_at": row.get("signal_time"),
        "decision_time_snapshot_at": ctx.get("snapshot_time"),
        "market_context_available": has_market_context(row),
        "liquidity_at_entry": ctx.get("liquidity"),
        "market_cap_at_entry": ctx.get("market_cap"),
        "price_at_entry": ctx.get("price"),
        "outcome_15m": label,
        "return_15m_pct": out.get("pnl_pct"),
        "runner_label": label == "runner",
        "flat_label": label == "flat",
        "loser_label": label == "loser",
        "blocked_reason": ";".join(reasons),
        "repaired_context": event_id(row) in repaired_ids or bool(row.get("entry_context_repair")),
        "source_file": source_file,
        "evidence_quality": evidence_quality(row, repaired_ids),
        "notes": evidence_notes(row, repaired_ids),
        "event_id": event_id(row),
        "transaction_signature": row.get("transaction_signature"),
    }


def evidence_notes(row: dict[str, Any], repaired_ids: set[str]) -> str:
    quality = evidence_quality(row, repaired_ids)
    if quality == "clean_forward_context":
        return "decision-time forward context present"
    if quality == "repaired_context":
        return "context repaired for review only"
    if quality == "blocked_missing_context":
        return "missing entry context blocks trust review"
    if quality == "blocked_missing_market_snapshot":
        return "missing market snapshot blocks context validation"
    if quality == "blocked_missing_outcome":
        return "outcome window is not mature or not resolved"
    return "manual review required before interpretation"


def wallet_summary(
    wallet: str,
    rows: list[dict[str, Any]],
    repaired_ids: set[str],
    recommendation_bucket: str,
) -> dict[str, Any]:
    labels = Counter(outcome(row) for row in rows)
    known = sum(labels.get(label, 0) for label in KNOWN_OUTCOMES)
    total = len(rows)
    runner = labels.get("runner", 0)
    flat = labels.get("flat", 0)
    loser = labels.get("loser", 0)
    blocked = sum(1 for row in rows if is_blocked(row))
    repaired = sum(1 for row in rows if event_id(row) in repaired_ids or row.get("entry_context_repair"))
    market_rows = [row for row in rows if has_market_context(row)]
    liquidity_values = [v for row in rows if (v := safe_float(entry_context(row).get("liquidity"))) is not None]
    market_caps = [v for row in rows if (v := safe_float(entry_context(row).get("market_cap"))) is not None]
    delays = [v for row in rows if (v := safe_float(entry_context(row).get("snapshot_lag_seconds"))) is not None]
    completion = rate(total - blocked, total)
    runner_known = rate(runner, known)
    flat_known = rate(flat, known)
    loser_known = rate(loser, known)
    repeatability = repeatability_score(
        runner=runner,
        known=known,
        token_count=len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        context_completion_rate=completion,
    )
    noise = noise_score(flat=flat, known=known, blocked=blocked, total=total)
    review_status = status_for_wallet(
        total=total,
        known=known,
        runner=runner,
        flat=flat,
        loser=loser,
        blocked=blocked,
        context_completion_rate=completion,
    )
    return {
        "wallet_address": wallet,
        "recommendation_bucket": recommendation_bucket,
        "total_forward_records": total,
        "known_15m_outcomes": known,
        "runner_15m_count": runner,
        "flat_15m_count": flat,
        "loser_15m_count": loser,
        "blocked_record_count": blocked,
        "repaired_record_count": repaired,
        "runner_rate_known_only": runner_known,
        "runner_rate_all_records": rate(runner, total),
        "flat_rate_known_only": flat_known,
        "loser_rate_known_only": loser_known,
        "context_completion_rate": completion,
        "market_snapshot_coverage": rate(len(market_rows), total),
        "average_liquidity_at_entry": average(liquidity_values),
        "median_liquidity_at_entry": median(liquidity_values),
        "average_market_cap_at_entry": average(market_caps),
        "median_market_cap_at_entry": median(market_caps),
        "average_entry_delay_seconds": average(delays),
        "timing_quality": timing_quality(delays),
        "repeatability_score": repeatability,
        "noise_score": noise,
        "review_status": review_status,
        "review_reason": review_reason(review_status, runner=runner, known=known, blocked=blocked, flat=flat),
        "next_required_evidence": next_required_evidence(review_status),
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def repeatability_score(*, runner: int, known: int, token_count: int, context_completion_rate: float) -> float:
    breadth = min(token_count / 10.0, 1.0)
    runner_component = rate(runner, known) if known else 0.0
    sample_component = min(known / 25.0, 1.0)
    score = (runner_component * 0.45) + (breadth * 0.2) + (sample_component * 0.2) + (context_completion_rate * 0.15)
    return round(score, 4)


def noise_score(*, flat: int, known: int, blocked: int, total: int) -> float:
    flat_component = rate(flat, known) if known else 0.0
    blocked_component = rate(blocked, total)
    return round((flat_component * 0.65) + (blocked_component * 0.35), 4)


def timing_quality(delays: list[float]) -> str:
    avg = average(delays)
    if avg is None:
        return "manual_review_required"
    if avg <= 30:
        return "strong_forward_context"
    if avg <= 120:
        return "acceptable_forward_context"
    return "delayed_context_review_required"


def status_for_wallet(
    *,
    total: int,
    known: int,
    runner: int,
    flat: int,
    loser: int,
    blocked: int,
    context_completion_rate: float,
) -> str:
    if total == 0:
        return "collect_more_evidence"
    if context_completion_rate < 0.5 and blocked > known:
        return "fix_context_before_review"
    if loser > runner:
        return "manual_review_required"
    runner_rate = rate(runner, known)
    if runner > 0 and known >= 25 and context_completion_rate >= 0.5 and runner_rate >= 0.02:
        return "continue_trust_validation"
    if runner > 0 and known >= 25 and runner_rate < 0.01:
        return "likely_flat_noise"
    if runner > 0:
        return "manual_review_required"
    if known >= 2 and flat == known:
        return "likely_flat_noise"
    return "collect_more_evidence"


def review_reason(status: str, *, runner: int, known: int, blocked: int, flat: int) -> str:
    if status == "continue_trust_validation":
        return "runner evidence exists across a meaningful known-outcome sample, but wallet remains not trusted"
    if status == "fix_context_before_review":
        return "blocked context dominates the wallet sample"
    if status == "likely_flat_noise":
        return "known outcomes are flat-only so far"
    if status == "manual_review_required":
        return f"manual review required before interpreting {runner} runner rows, {flat} flat rows, and {blocked} blocked rows"
    if status == "reject_for_now":
        return "current evidence does not justify continued review"
    return f"sample is not decisive yet: {known} known outcomes and {blocked} blocked rows"


def next_required_evidence(status: str) -> str:
    return {
        "continue_trust_validation": "collect more clean forward rows across distinct token mints before any trust discussion",
        "collect_more_evidence": "continue public-RPC forward collection until 15m windows mature",
        "fix_context_before_review": "repair decision-time entry context before wallet review",
        "likely_flat_noise": "hold as negative evidence unless future forward runners appear",
        "manual_review_required": "human review of event rows, liquidity, and context quality",
        "reject_for_now": "exclude from review until materially new evidence appears",
    }.get(status, "manual review required")


def context_gap_analysis(
    *,
    merged_records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]],
    resolver_report: dict[str, Any],
) -> dict[str, Any]:
    blocked = [row for row in merged_records if is_blocked(row) or not has_market_context(row)]
    blocked_by_wallet: Counter[str] = Counter(wallet_address(row) for row in blocked if wallet_address(row))
    reason_counts: Counter[str] = Counter()
    for row in blocked:
        reasons = block_reasons(row) or ["unknown_context_gap"]
        reason_counts.update(reasons)
    rejected = as_dict(resolver_report.get("summary")).get("rejected_reason_counts")
    if isinstance(rejected, dict):
        for reason, count in rejected.items():
            reason_counts[str(reason)] += safe_int(count)
    repairable_reasons = {
        "missing_forward_entry_context",
        "blocked_missing_forward_entry_context",
        "missing_later_market_snapshot",
        "missing_valid_execution_price_quote",
    }
    repairable = sum(
        1 for row in blocked
        if any(reason in repairable_reasons for reason in block_reasons(row))
    )
    total_blocked = len(blocked)
    return {
        "total_blocked_records": total_blocked,
        "blocked_wallet_count": len(blocked_by_wallet),
        "blocked_by_wallet": dict(sorted(blocked_by_wallet.items(), key=lambda item: (-item[1], item[0]))),
        "blocked_by_reason": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "repairable_blocked_count": repairable,
        "non_repairable_blocked_count": max(0, total_blocked - repairable),
        "acceptable_blockers_for_review": [],
        "fatal_blockers_for_trust_review": sorted(reason_counts),
        "repaired_record_count": len(repaired_records or []),
        "context_completion_rate": rate(len(merged_records) - total_blocked, len(merged_records)),
        "top_context_blocked_wallets": [
            {"wallet_address": wallet, "blocked_record_count": count}
            for wallet, count in blocked_by_wallet.most_common(10)
        ],
        "recommended_context_actions": recommended_context_actions(reason_counts, blocked_by_wallet),
    }


def recommended_context_actions(reason_counts: Counter[str], blocked_by_wallet: Counter[str]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if reason_counts.get("missing_later_market_snapshot"):
        actions.append({"action": "repair_market_snapshot", "reason": "missing_later_market_snapshot"})
    if reason_counts.get("missing_valid_execution_price_quote"):
        actions.append({"action": "repair_entry_timestamp", "reason": "missing_valid_execution_price_quote"})
    if reason_counts.get("missing_forward_entry_context") or reason_counts.get("blocked_missing_forward_entry_context"):
        actions.append({"action": "manual_review_required", "reason": "missing_forward_entry_context"})
    for wallet, count in blocked_by_wallet.most_common(5):
        actions.append(
            {
                "action": "exclude_from_review_until_context_fixed",
                "wallet_address": wallet,
                "blocked_record_count": count,
            }
        )
    return actions


def behavior_bucket_report(scorecard: dict[str, Any], recommendations: dict[str, Any]) -> dict[str, Any]:
    score_rows = {str(row.get("wallet")): row for row in scorecard_rows(scorecard)}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in recommendation_rows(recommendations):
        action = str(rec.get("recommendation_action") or "")
        bucket = BUCKET_MAP.get(action, "rejected_for_now")
        wallet = str(rec.get("wallet") or "")
        source = score_rows.get(wallet, rec)
        buckets[bucket].append(source)
    for bucket in ["review_behavioral_signal", "fix_context", "flat_noise_candidate", "collect_more_evidence", "risk_review", "rejected_for_now"]:
        buckets.setdefault(bucket, [])
    rows: list[dict[str, Any]] = []
    for bucket, wallet_rows in sorted(buckets.items()):
        known = sum(safe_int(row.get("known_15m")) for row in wallet_rows)
        runner = sum(safe_int(row.get("runner_15m")) for row in wallet_rows)
        flat = sum(safe_int(row.get("flat_15m")) for row in wallet_rows)
        loser = sum(safe_int(row.get("loser_15m")) for row in wallet_rows)
        blocked = sum(safe_int(row.get("blocked_records")) for row in wallet_rows)
        records = sum(safe_int(row.get("records")) for row in wallet_rows)
        rows.append(
            {
                "bucket": bucket,
                "wallet_count": len(wallet_rows),
                "total_records": records,
                "known_outcomes": known,
                "runner_count": runner,
                "flat_count": flat,
                "loser_count": loser,
                "blocked_count": blocked,
                "context_completion_rate": rate(records - blocked, records),
                "average_runner_rate": rate(runner, known),
                "notes": bucket_notes(bucket),
                "recommended_operator_action": bucket_action(bucket),
            }
        )
    return {
        "buckets": rows,
        "summary": {
            "bucket_count": len(rows),
            "wallets": sum(row["wallet_count"] for row in rows),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
    }


def bucket_notes(bucket: str) -> str:
    return {
        "review_behavioral_signal": "review-only candidates with runner evidence; not trusted",
        "fix_context": "context gaps block trust review",
        "flat_noise_candidate": "flat-only evidence should be preserved as negative evidence",
        "collect_more_evidence": "sample is not yet decisive",
        "risk_review": "risk markers require manual review",
        "rejected_for_now": "no current basis for continued trust validation",
    }.get(bucket, "manual review required")


def bucket_action(bucket: str) -> str:
    return {
        "review_behavioral_signal": "manual_review_required",
        "fix_context": "repair_market_snapshot",
        "flat_noise_candidate": "exclude_from_review_until_context_fixed",
        "collect_more_evidence": "collect_more_forward_rows",
        "risk_review": "manual_review_required",
        "rejected_for_now": "exclude_from_review_until_context_fixed",
    }.get(bucket, "manual_review_required")


def rpc_collection_health(canary_reports: list[dict[str, Any]], expected_heartbeat_interval_seconds: int) -> dict[str, Any]:
    latest = canary_reports[-1] if canary_reports else {}
    latest_limits = as_dict(latest.get("limits"))
    latest_budget = as_dict(latest.get("budget"))
    latest_summary = as_dict(latest.get("summary"))
    internal_interval = safe_int(latest_limits.get("cycle_interval_seconds") or latest_budget.get("interval_seconds"))
    projected = safe_int(latest_budget.get("projected_rpc_calls_per_day") or latest.get("projected_rpc_calls_per_day"))
    max_day = safe_int(latest_budget.get("max_rpc_calls_per_day"), 120000)
    provider_blocked = sum(1 for report in canary_reports if provider_blocked_report(report))
    wallet_checks = sum(safe_int(as_dict(report.get("summary")).get("wallets_processed")) for report in canary_reports)
    rows = sum(safe_int(as_dict(report.get("summary")).get("evidence_rows_created")) for report in canary_reports)
    snapshots = sum(safe_int(as_dict(report.get("summary")).get("market_snapshots_collected")) for report in canary_reports)
    if provider_blocked:
        status = "warning_provider_blocked"
    elif max_day and projected >= max_day * 0.8:
        status = "warning_near_rpc_budget"
    elif internal_interval and internal_interval != expected_heartbeat_interval_seconds:
        status = "healthy_but_interval_mismatch"
    elif not canary_reports:
        status = "error_collection_unhealthy"
    else:
        status = "healthy_under_budget"
    return {
        "configured_internal_cycle_interval": internal_interval,
        "expected_heartbeat_interval": expected_heartbeat_interval_seconds,
        "projected_rpc_day": projected,
        "max_allowed_rpc_day": max_day,
        "provider_blocked_files": provider_blocked,
        "wallet_checks": wallet_checks,
        "collected_activity_rows": rows,
        "market_snapshots_captured": snapshots,
        "latest_wallets_processed": safe_int(latest_summary.get("wallets_processed")),
        "latest_evidence_rows_created": safe_int(latest_summary.get("evidence_rows_created")),
        "latest_market_snapshots_collected": safe_int(latest_summary.get("market_snapshots_collected")),
        "status": status,
    }


def provider_blocked_report(report: dict[str, Any]) -> bool:
    blockers = {str(item) for item in as_list(report.get("blockers"))}
    summary = as_dict(report.get("summary"))
    provider_status_counts = as_dict(report.get("provider_status_counts"))
    provider_blockers = {
        "provider_blocked",
        "provider_preflight_failed",
        "free_rpc_unavailable",
        "all_public_rpc_blocked",
        "rpc_preflight_blocked",
    }
    return (
        bool(blockers & provider_blockers)
        or safe_int(summary.get("wallets_blocked_rpc_preflight")) > 0
        or safe_int(provider_status_counts.get("blocked")) > 0
    )


def safety_lock_verification(
    *,
    safety_report: dict[str, Any],
    recommendations: dict[str, Any],
    behavior_buckets: dict[str, Any],
) -> dict[str, Any]:
    rec_summary = as_dict(recommendations.get("summary"))
    bucket_summary = as_dict(behavior_buckets.get("summary"))
    live_allowed = bool(safety_report.get("live_allowed"))
    live_enabled = bool(safety_report.get("live_enabled"))
    paper_enabled = bool(safety_report.get("paper_enabled"))
    overall = str(safety_report.get("overall") or "")
    promotions = safe_int(rec_summary.get("promotions_allowed"))
    wallet_lists = safe_int(rec_summary.get("wallet_list_mutations")) + safe_int(bucket_summary.get("wallet_list_mutations"))
    trust_mutations = safe_int(rec_summary.get("auto_trust_mutations")) + safe_int(bucket_summary.get("auto_trust_mutations"))
    locked = overall == "PAPER_SAFE" and not live_allowed and not live_enabled and paper_enabled and promotions == 0 and wallet_lists == 0 and trust_mutations == 0
    return {
        "execution_mode": overall,
        "live_trading_allowed": live_allowed,
        "live_trading_enabled": live_enabled,
        "paper_mode_enabled": paper_enabled,
        "promotions_allowed": promotions,
        "wallet_list_mutations": wallet_lists,
        "wallet_trust_mutations": trust_mutations,
        "no_live_execution_command_enabled": not live_allowed and not live_enabled,
        "no_auto_promotion_path_enabled": promotions == 0 and trust_mutations == 0,
        "safety_status": "locked_safe" if locked else "unsafe_block_run",
        "checks": safety_report.get("checks") or [],
    }


def top_wallet_case_study(wallet_summary_row: dict[str, Any] | None) -> dict[str, Any]:
    row = wallet_summary_row or {}
    wallet = row.get("wallet_address") or TOP_WALLET
    runner = safe_int(row.get("runner_15m_count"))
    flat = safe_int(row.get("flat_15m_count"))
    blocked = safe_int(row.get("blocked_record_count"))
    known = safe_int(row.get("known_15m_outcomes"))
    return {
        "wallet_address": wallet,
        "why_interesting": "largest review candidate by known forward outcomes and runner history" if runner else "top requested wallet remains under review",
        "why_not_trusted_yet": "runner evidence is mixed with flat outcomes and context completeness must remain high before any trust discussion",
        "runner_history": runner,
        "flat_history": flat,
        "blocked_context_issues": blocked,
        "known_15m_outcomes": known,
        "liquidity_context": {
            "average_liquidity_at_entry": row.get("average_liquidity_at_entry"),
            "median_liquidity_at_entry": row.get("median_liquidity_at_entry"),
        },
        "repeatability_assessment": {
            "repeatability_score": row.get("repeatability_score", 0.0),
            "noise_score": row.get("noise_score", 0.0),
            "review_status": row.get("review_status", "collect_more_evidence"),
        },
        "additional_evidence_needed": "more clean forward rows across distinct token mints with decision-time market context",
        "current_conclusion": [
            "strongest_review_candidate" if wallet == TOP_WALLET else "continue_forward_validation",
            "continue_forward_validation",
            "not_trusted",
            "no_promotion_allowed",
        ],
    }


def build_forward_wallet_trust_review_packet(
    *,
    original_records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]],
    merged_scorecard: dict[str, Any],
    recommendations: dict[str, Any],
    resolver_report: dict[str, Any] | None = None,
    canary_reports: list[dict[str, Any]] | None = None,
    safety_report: dict[str, Any] | None = None,
    bucket: str = REVIEW_BUCKET,
    limit: int = 3,
    expected_heartbeat_interval_seconds: int = 900,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    resolver_report = resolver_report or {}
    canary_reports = canary_reports or []
    safety_report = safety_report or {}
    merged_records, _ = merge_records(original_records, repaired_records)
    repaired_ids = {event_id(row) for row in repaired_records if event_id(row)}
    selected_wallets = review_wallets(
        recommendations=recommendations,
        merged_scorecard=merged_scorecard,
        bucket=bucket,
        limit=limit,
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in merged_records:
        wallet = wallet_address(row)
        if wallet in selected_wallets:
            grouped[wallet].append(row)
    wallet_summaries = [
        wallet_summary(wallet, grouped.get(wallet, []), repaired_ids, bucket)
        for wallet in selected_wallets
    ]
    event_rows = [
        event_evidence_row(row, repaired_ids, "forward_outcome_records+forward_entry_context_resolved_records")
        for wallet in selected_wallets
        for row in sorted(grouped.get(wallet, []), key=lambda item: (safe_float(item.get("signal_time"), 0.0) or 0.0, event_id(item)))
    ]
    gap = context_gap_analysis(
        merged_records=merged_records,
        repaired_records=repaired_records,
        resolver_report=resolver_report,
    )
    buckets = behavior_bucket_report(merged_scorecard, recommendations)
    rpc_health = rpc_collection_health(canary_reports, expected_heartbeat_interval_seconds)
    safety = safety_lock_verification(
        safety_report=safety_report,
        recommendations=recommendations,
        behavior_buckets=buckets,
    )
    if safety["safety_status"] != "locked_safe":
        for row in wallet_summaries:
            row["review_status"] = "manual_review_required"
            row["review_reason"] = "safety lock verification did not return locked_safe"
    top_summary = next((row for row in wallet_summaries if row.get("wallet_address") == TOP_WALLET), None)
    case_study = top_wallet_case_study(top_summary)
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
        "bucket": bucket,
        "limit": limit,
        "summary": {
            "review_wallets": len(wallet_summaries),
            "event_evidence_rows": len(event_rows),
            "context_blocked_records": gap["total_blocked_records"],
            "behavior_buckets": len(buckets["buckets"]),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
            "safety_status": safety["safety_status"],
            "rpc_health_status": rpc_health["status"],
        },
        "wallets": wallet_summaries,
        "event_evidence": event_rows,
        "context_gap_analysis": gap,
        "wallet_behavior_buckets": buckets,
        "rpc_collection_health": rpc_health,
        "safety_lock_verification": safety,
        "top_wallet_case_study": case_study,
        "operator_note": (
            "This packet is a review-only trust-validation artifact. It cannot promote wallets, "
            "mutate trust, mutate wallet lists, execute trades, or claim profitability."
        ),
    }
