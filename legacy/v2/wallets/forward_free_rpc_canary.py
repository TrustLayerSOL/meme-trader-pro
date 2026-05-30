from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any, Callable

from wallets.forward_wallet_activity import DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS
from wallets.forward_wallet_activity import DEFAULT_FORWARD_MAX_WALLETS
from wallets.forward_wallet_activity import DEFAULT_MAX_RPC_CALLS_PER_CYCLE
from wallets.forward_wallet_activity import DEFAULT_MAX_RPC_CALLS_PER_DAY
from wallets.forward_wallet_activity import estimate_api_budget


MODE = "FORWARD_FREE_RPC_CANARY_REVIEW_ONLY"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def planned_cycles(*, duration_seconds: int, cycle_interval_seconds: int) -> int:
    duration = max(0, int(duration_seconds))
    interval = max(1, int(cycle_interval_seconds))
    return max(1, math.ceil(duration / interval)) if duration else 0


def recommend_canary(summary: dict[str, Any], provider_counts: dict[str, int], budget: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if not budget.get("execute_allowed", False):
        return "BLOCKED_BUDGET", [str(budget.get("block_reason") or "api_budget_blocked")]

    attempted = as_int(summary.get("cycles_attempted"))
    if attempted <= 0:
        return "NO_CYCLES_RUN", ["no_cycles_attempted"]

    preflight_blocked = as_int(summary.get("wallets_blocked_rpc_preflight"))
    rpc_errors = as_int(summary.get("wallets_blocked_rpc_error"))
    processed = as_int(summary.get("wallets_processed"))
    evidence = as_int(summary.get("evidence_rows_created"))
    if provider_counts.get("blocked_unhealthy", 0):
        blockers.append("blocked_unhealthy")
    if preflight_blocked > 0:
        blockers.append("rpc_preflight_blocked_wallets")
    if processed > 0 and rpc_errors / max(1, processed) >= 0.5:
        blockers.append("high_rpc_error_rate")
    if not processed and preflight_blocked:
        blockers.append("no_wallets_processed")

    if blockers:
        return "FREE_RPC_UNSTABLE", blockers
    if evidence > 0:
        return "FREE_RPC_USABLE_SMALL_THROTTLED", []
    return "FREE_RPC_REACHABLE_LOW_YIELD", ["no_evidence_rows_created"]


def build_forward_free_rpc_canary_report(
    *,
    cycle_runner: Callable[..., dict[str, Any]],
    sleep: Callable[[float], None] = time.sleep,
    generated_at: float | None = None,
    duration_seconds: int = 1800,
    cycle_interval_seconds: int = 300,
    max_wallets: int = DEFAULT_FORWARD_MAX_WALLETS,
    signature_limit: int = 8,
    max_transactions_per_wallet: int = 3,
    lookback_seconds: int = 86400,
    request_pause_seconds: float = 1.5,
    max_rpc_calls_per_cycle: int = DEFAULT_MAX_RPC_CALLS_PER_CYCLE,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
    capture_market_context: bool = True,
    max_market_mints: int = 25,
    max_market_context_calls_per_cycle: int = 100,
    adaptive_degraded_max_wallets: int = DEFAULT_ADAPTIVE_DEGRADED_MAX_WALLETS,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    cycles = planned_cycles(duration_seconds=duration_seconds, cycle_interval_seconds=cycle_interval_seconds)
    budget = estimate_api_budget(
        selected_wallets=max_wallets,
        signature_limit=signature_limit,
        max_transactions_per_wallet=max_transactions_per_wallet,
        interval_seconds=cycle_interval_seconds,
        max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
        max_rpc_calls_per_day=max_rpc_calls_per_day,
    )

    cycle_reports: list[dict[str, Any]] = []
    provider_statuses: Counter[str] = Counter()
    totals = Counter()

    if budget.get("execute_allowed", False):
        for idx in range(cycles):
            report = cycle_runner(
                execute=True,
                max_wallets=max_wallets,
                lookback_seconds=lookback_seconds,
                signature_limit=signature_limit,
                max_transactions_per_wallet=max_transactions_per_wallet,
                request_pause_seconds=request_pause_seconds,
                max_rpc_calls_per_cycle=max_rpc_calls_per_cycle,
                max_rpc_calls_per_day=max_rpc_calls_per_day,
                rpc_preflight=True,
                adaptive_free_rpc_throttle=True,
                adaptive_degraded_max_wallets=adaptive_degraded_max_wallets,
                capture_market_context=capture_market_context,
                max_market_mints=max_market_mints,
                max_market_context_calls_per_cycle=max_market_context_calls_per_cycle,
                interval_seconds=cycle_interval_seconds,
                rpc_mode="free_public_rpc",
                paid_rpc_allowed=False,
            )
            cycle_reports.append(report)
            summary = as_dict(report.get("summary"))
            market_summary = as_dict(as_dict(report.get("market_context")).get("summary"))
            provider_statuses[str(as_dict(report.get("rpc_preflight")).get("status") or "unknown")] += 1
            for key in (
                "wallets_processed",
                "wallets_collected",
                "wallets_blocked_rpc_error",
                "wallets_blocked_rpc_preflight",
                "wallets_throttled_by_rpc_preflight",
                "evidence_rows_created",
            ):
                totals[key] += as_int(summary.get(key))
            totals["market_snapshots_collected"] += as_int(market_summary.get("snapshots_collected"))
            if idx < cycles - 1:
                sleep(cycle_interval_seconds)

    summary = {
        "cycles_planned": cycles,
        "cycles_attempted": len(cycle_reports),
        "wallets_processed": totals["wallets_processed"],
        "wallets_collected": totals["wallets_collected"],
        "wallets_blocked_rpc_error": totals["wallets_blocked_rpc_error"],
        "wallets_blocked_rpc_preflight": totals["wallets_blocked_rpc_preflight"],
        "wallets_throttled_by_rpc_preflight": totals["wallets_throttled_by_rpc_preflight"],
        "evidence_rows_created": totals["evidence_rows_created"],
        "market_snapshots_collected": totals["market_snapshots_collected"],
    }
    recommendation, blockers = recommend_canary(summary, dict(provider_statuses), budget)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutations": 0,
        "trust_mutations": 0,
        "paid_rpc_allowed": False,
        "limits": {
            "duration_seconds": int(duration_seconds),
            "cycle_interval_seconds": int(cycle_interval_seconds),
            "max_wallets": int(max_wallets),
            "signature_limit": int(signature_limit),
            "max_transactions_per_wallet": int(max_transactions_per_wallet),
            "request_pause_seconds": float(request_pause_seconds),
            "adaptive_degraded_max_wallets": int(adaptive_degraded_max_wallets),
            "capture_market_context": bool(capture_market_context),
        },
        "budget": budget,
        "summary": summary,
        "provider_status_counts": dict(provider_statuses),
        "blockers": blockers,
        "recommendation": recommendation,
        "cycle_reports": cycle_reports,
        "next_actions": next_actions_for_recommendation(recommendation),
    }


def next_actions_for_recommendation(recommendation: str) -> list[str]:
    if recommendation == "BLOCKED_BUDGET":
        return ["Lower max_wallets, signature_limit, transaction limit, or run frequency before running the canary."]
    if recommendation == "FREE_RPC_UNSTABLE":
        return ["Keep using small manual/on-demand cycles only; do not start a long public-RPC schedule."]
    if recommendation == "FREE_RPC_USABLE_SMALL_THROTTLED":
        return ["Run another small canary later and compare yield before considering a longer schedule."]
    return ["Let more current activity accumulate, then rerun the canary with the same small settings."]
