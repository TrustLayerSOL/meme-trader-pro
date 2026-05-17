from __future__ import annotations

import time
from typing import Any


MODE = "LIVE_SIGNAL_FOUNDATION_STAGE1_REVIEW_ONLY"
SIGNAL_CONTEXT_MODE = "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY"
REPLAY_MODE = "HISTORICAL_REPLAY_REVIEW_ONLY"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def signal_context_visible(report: dict[str, Any]) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == SIGNAL_CONTEXT_MODE
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(summary.get("stage2_signal_context_completion_pct")) == 100
    )


def historical_replay_visible(report: dict[str, Any]) -> bool:
    counts = as_dict(report.get("counts"))
    return (
        report.get("mode") == REPLAY_MODE
        and report.get("live_execution_locked") is True
        and safe_int(counts.get("events")) > 0
    )


def source_consistency_pct(signal_records: int, replay_events: int) -> int:
    if signal_records <= 0 or replay_events <= 0:
        return 0
    smaller = min(signal_records, replay_events)
    larger = max(signal_records, replay_events)
    return pct(smaller, larger)


def build_live_signal_foundation_report(
    *,
    signal_context_layer: dict[str, Any] | None,
    historical_replay_summary: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    signal_report = as_dict(signal_context_layer)
    replay_report = as_dict(historical_replay_summary)
    signal_summary = as_dict(signal_report.get("summary"))
    replay_counts = as_dict(replay_report.get("counts"))

    signal_records = safe_int(signal_summary.get("total_records"))
    replay_events = safe_int(replay_counts.get("events"))
    wallet_observations = safe_int(signal_summary.get("wallet_observation_records"))
    accepted = safe_int(signal_summary.get("accepted_trade_records"))
    failed = safe_int(signal_summary.get("failed_trade_records"))
    rejected = safe_int(signal_summary.get("rejected_signal_records"))
    decision_safe = safe_int(signal_summary.get("decision_time_safe_records"))
    outcome_separated = safe_int(signal_summary.get("future_outcome_separated_records"))
    unsafe_events = safe_int(replay_counts.get("unsafe_events"))
    consistency = source_consistency_pct(signal_records, replay_events)

    gates = [
        gate("signal_context_layer_visible", signal_context_visible(signal_report), "Stage 1 requires visible normalized signal-context records."),
        gate("historical_replay_visible", historical_replay_visible(replay_report), "Stage 1 requires persisted replay-safe event records."),
        gate("event_persistence_consistent", signal_records > 0 and replay_events > 0 and consistency >= 95, "Signal-context and replay event counts should agree closely."),
        gate("wallet_observations_visible", wallet_observations > 0, "Wallet observation records must exist for wallet-behavior research."),
        gate("signal_generation_visible", accepted + failed + rejected > 0, "Accepted, failed, or rejected signal decisions must be visible."),
        gate("token_context_visible", safe_int(signal_summary.get("decision_time_market_context_records")) > 0, "Some decision-time token/market context must be visible."),
        gate("replay_safety_clean", unsafe_events == 0 and decision_safe == signal_records and outcome_separated == signal_records, "Replay-safe storage must have zero unsafe events and separated future outcomes."),
        gate("live_execution_locked", True, "Stage 1 reporting must not unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "Stage 1 reporting must not mutate wallet lists."),
        gate("trust_mutation_blocked", True, "Stage 1 reporting must not auto-promote or auto-demote wallets."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed_gates = [row["name"] for row in gates if not row["passed"]]

    return {
        "mode": MODE,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "stage1_live_signal_foundation_completion_pct": pct(len(passed), len(gates)),
            "signal_records": signal_records,
            "historical_replay_events": replay_events,
            "source_consistency_pct": consistency,
            "accepted_trade_records": accepted,
            "failed_trade_records": failed,
            "rejected_signal_records": rejected,
            "wallet_observation_records": wallet_observations,
            "unsafe_events": unsafe_events,
            "decision_time_safe_records": decision_safe,
            "future_outcome_separated_records": outcome_separated,
            "decision_time_market_context_records": safe_int(signal_summary.get("decision_time_market_context_records")),
            "decision_time_market_context_coverage_pct": safe_int(signal_summary.get("decision_time_market_context_coverage_pct")),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "passed_gates": passed,
        "failed_gates": failed_gates,
        "gates": gates,
        "residual_data_blockers": residual_data_blockers(
            signal_records=signal_records,
            replay_events=replay_events,
            consistency=consistency,
            market_context_coverage=safe_int(signal_summary.get("decision_time_market_context_coverage_pct")),
        ),
        "operator_note": (
            "Stage 1 is complete when the live-signal foundation is observable, persisted, replay-safe, and locked. "
            "This does not mean every historical market-context field is score-ready."
        ),
    }


def residual_data_blockers(
    *,
    signal_records: int,
    replay_events: int,
    consistency: int,
    market_context_coverage: int,
) -> list[str]:
    blockers: list[str] = []
    if signal_records <= 0:
        blockers.append("signal_records_missing")
    if replay_events <= 0:
        blockers.append("historical_replay_events_missing")
    if consistency < 95:
        blockers.append("signal_replay_count_mismatch")
    if market_context_coverage < 100:
        blockers.append("decision_time_market_context_still_partial")
    return blockers

