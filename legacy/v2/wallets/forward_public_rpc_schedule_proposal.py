from __future__ import annotations

import time
from typing import Any


MODE = "FORWARD_PUBLIC_RPC_SCHEDULE_PROPOSAL_REVIEW_ONLY"
USABLE_CANARY_RECOMMENDATION = "FREE_RPC_USABLE_SMALL_THROTTLED"
HEALTHY_PROVIDER_RECOMMENDATION = "USE_HEALTHY_FREE_PROVIDER"
DEFAULT_MAX_RPC_CALLS_PER_DAY = 120_000


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def canary_is_stable(report: dict[str, Any], *, max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY) -> bool:
    if report.get("recommendation") != USABLE_CANARY_RECOMMENDATION:
        return False
    if report.get("blockers"):
        return False
    if report.get("paid_rpc_allowed") is not False:
        return False
    if report.get("live_execution_locked") is not True:
        return False
    if as_int(as_dict(report.get("summary")).get("cycles_attempted")) <= 0:
        return False
    projected_rpc_day = as_int(as_dict(report.get("budget")).get("projected_rpc_calls_per_day"))
    return 0 < projected_rpc_day <= int(max_rpc_calls_per_day)


def build_forward_public_rpc_schedule_proposal(
    *,
    canary_reports: list[dict[str, Any]],
    provider_report: dict[str, Any] | None = None,
    generated_at: float | None = None,
    max_rpc_calls_per_day: int = DEFAULT_MAX_RPC_CALLS_PER_DAY,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    provider_report = provider_report or {}
    stable_count = sum(
        1 for report in canary_reports
        if canary_is_stable(report, max_rpc_calls_per_day=max_rpc_calls_per_day)
    )
    projected_values = [
        as_int(as_dict(report.get("budget")).get("projected_rpc_calls_per_day"))
        for report in canary_reports
    ]
    blockers: list[str] = []
    if stable_count < 3:
        blockers.append("needs_three_stable_canaries")
    if any(value > int(max_rpc_calls_per_day) for value in projected_values):
        blockers.append("projected_rpc_day_exceeds_cap")
    if provider_report.get("recommendation") not in (HEALTHY_PROVIDER_RECOMMENDATION, None):
        blockers.append("provider_rotation_not_healthy")

    ready = not blockers
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "schedule_enabled": False,
        "live_execution_locked": True,
        "paid_rpc_allowed": False,
        "wallet_list_mutations": 0,
        "trust_mutations": 0,
        "canaries_reviewed": len(canary_reports),
        "stable_canaries": stable_count,
        "provider_recommendation": provider_report.get("recommendation"),
        "provider_safe_urls": provider_report.get("recommended_free_rpc_safe_urls", []),
        "projected_rpc_calls_per_day_values": projected_values,
        "recommendation": "READY_FOR_CONSERVATIVE_RECURRING_PROPOSAL" if ready else "KEEP_MANUAL_ON_DEMAND_ONLY",
        "blockers": blockers,
        "proposed_schedule": build_proposed_schedule(max_rpc_calls_per_day=max_rpc_calls_per_day) if ready else {},
        "next_actions": next_actions(ready),
    }


def build_proposed_schedule(*, max_rpc_calls_per_day: int) -> dict[str, Any]:
    return {
        "enabled": False,
        "max_wallets": 10,
        "interval_seconds": 900,
        "signature_limit": 4,
        "max_transactions_per_wallet": 2,
        "request_pause_seconds": 1.0,
        "adaptive_degraded_max_wallets": 5,
        "max_rpc_calls_per_day": int(max_rpc_calls_per_day),
        "paid_rpc_allowed": False,
        "capture_market_context": True,
        "stop_rules": [
            "stop_on_provider_error",
            "stop_on_high_rpc_error_rate",
            "stop_if_projected_rpc_day_exceeds_cap",
            "stop_if_live_execution_not_locked",
            "stop_if_wallet_trust_or_list_mutation_requested",
        ],
    }


def next_actions(ready: bool) -> list[str]:
    if ready:
        return [
            "Review this proposal before enabling any recurring collection.",
            "If approved, schedule the same small canary-sized collection with stop-on-provider-errors.",
        ]
    return ["Keep forward collection manual/on-demand and rerun small canaries later."]
