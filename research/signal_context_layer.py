from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "SIGNAL_CONTEXT_LAYER_REVIEW_ONLY"

REQUIRED_RECORD_KEYS = {
    "record_type",
    "mint",
    "source",
    "wallets",
    "signal_context",
    "decision",
    "later_token_outcome",
    "replay_assumptions",
    "research_safety",
}

REQUIRED_CONTEXT_KEYS = {
    "mint",
    "source",
    "signal_type",
    "entry_timestamp",
    "triggering_wallets",
    "wallet_quality",
    "cluster",
    "market",
    "risk",
    "execution_assumptions",
    "scoring",
    "market_regime",
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


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def has_required_record_shape(record: dict[str, Any]) -> bool:
    return REQUIRED_RECORD_KEYS.issubset(set(record.keys()))


def has_required_context_shape(record: dict[str, Any]) -> bool:
    context = as_dict(record.get("signal_context"))
    return REQUIRED_CONTEXT_KEYS.issubset(set(context.keys()))


def has_decision_time_market(record: dict[str, Any]) -> bool:
    market = as_dict(as_dict(record.get("signal_context")).get("market"))
    return any(market.get(key) not in (None, "", [], {}) for key in ("price", "liquidity", "market_cap", "token_age_seconds"))


def source_is_wallet_observation(record: dict[str, Any]) -> bool:
    return str(record.get("source") or "") == "wallet_performance_signal"


def safety(record: dict[str, Any]) -> dict[str, Any]:
    return as_dict(record.get("research_safety"))


def build_signal_context_layer_report(
    records: list[dict[str, Any]],
    *,
    generated_at: float | None = None,
) -> dict[str, Any]:
    rows = [row for row in records or [] if isinstance(row, dict)]
    record_types: Counter[str] = Counter(str(row.get("record_type") or "unknown") for row in rows)
    accepted_count = record_types.get("accepted_trade", 0)
    failed_count = record_types.get("failed_trade", 0)
    rejected_count = record_types.get("rejected_signal", 0)
    wallet_observation_count = sum(1 for row in rows if source_is_wallet_observation(row))
    shared_schema_count = sum(1 for row in rows if has_required_record_shape(row))
    context_shape_count = sum(1 for row in rows if has_required_context_shape(row))
    market_context_count = sum(1 for row in rows if has_decision_time_market(row))
    decision_time_safe_count = sum(1 for row in rows if safety(row).get("decision_time_safe") is True)
    outcome_separated_count = sum(1 for row in rows if safety(row).get("future_outcome_separated") is True)
    accepted_context_count = sum(
        1
        for row in rows
        if row.get("record_type") in {"accepted_trade", "failed_trade"} and as_dict(row.get("signal_context"))
    )
    rejected_context_count = sum(
        1
        for row in rows
        if row.get("record_type") == "rejected_signal" and as_dict(row.get("signal_context"))
    )
    total_trade_records = accepted_count + failed_count
    gates = [
        gate(
            "live_execution_locked",
            all(safety(row).get("live_execution_locked") is True for row in rows) if rows else True,
            "Signal-context reporting must stay live-execution locked.",
        ),
        gate(
            "wallet_list_mutation_blocked",
            True,
            "Signal-context reporting cannot mutate wallet trust or wallet lists.",
        ),
        gate(
            "shared_signal_outcome_schema_present",
            bool(rows) and shared_schema_count == len(rows),
            "Accepted, failed, rejected, and observed records must share one comparable top-level schema.",
        ),
        gate(
            "accepted_trade_context_adapter_present",
            total_trade_records > 0 and accepted_context_count == total_trade_records,
            "Accepted and failed paper trades must produce decision-time signal context.",
        ),
        gate(
            "rejected_signal_context_adapter_present",
            rejected_count > 0 and rejected_context_count == rejected_count,
            "Rejected/no-trade records must preserve signal context.",
        ),
        gate(
            "decision_time_safety_enforced",
            bool(rows) and decision_time_safe_count == len(rows),
            "Decision-time context must stay separated from later outcomes.",
        ),
        gate(
            "future_outcomes_separated",
            bool(rows) and outcome_separated_count == len(rows),
            "Later token outcomes must remain evaluation-only.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    residual_blockers = residual_data_blockers(
        total=len(rows),
        context_shape_count=context_shape_count,
        market_context_count=market_context_count,
        wallet_observation_count=wallet_observation_count,
    )
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "read_only": True,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "stage2_signal_context_completion_pct": pct(len(passed), len(gates)),
            "total_records": len(rows),
            "accepted_trade_records": accepted_count,
            "failed_trade_records": failed_count,
            "rejected_signal_records": rejected_count,
            "wallet_observation_records": wallet_observation_count,
            "shared_schema_records": shared_schema_count,
            "canonical_context_records": context_shape_count,
            "decision_time_market_context_records": market_context_count,
            "decision_time_safe_records": decision_time_safe_count,
            "future_outcome_separated_records": outcome_separated_count,
            "context_shape_coverage_pct": pct(context_shape_count, len(rows)),
            "decision_time_market_context_coverage_pct": pct(market_context_count, len(rows)),
        },
        "record_type_counts": dict(record_types),
        "residual_data_blockers": residual_blockers,
        "operator_alerts": build_operator_alerts(residual_blockers),
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "next_required_actions": next_required_actions(residual_blockers),
        "operator_note": (
            "Stage 2 is complete when accepted paper trades, failed paper attempts, rejected signals, and wallet "
            "observations can be reviewed through one decision-time-safe context contract. Completion does not mean "
            "all historical market fields are score-ready."
        ),
    }


def residual_data_blockers(
    *,
    total: int,
    context_shape_count: int,
    market_context_count: int,
    wallet_observation_count: int,
) -> list[str]:
    blockers: list[str] = []
    if total <= 0:
        blockers.append("no_signal_context_records")
        return blockers
    if context_shape_count < total:
        blockers.append("legacy_context_rows_need_canonical_field_backfill")
    if market_context_count < total:
        blockers.append("decision_time_market_context_still_partial")
    if wallet_observation_count <= 0:
        blockers.append("wallet_observation_context_missing")
    return blockers


def build_operator_alerts(blockers: list[str]) -> list[dict[str, Any]]:
    if not blockers:
        return [{
            "severity": "info",
            "code": "stage2_context_contract_ready",
            "message": "Signal context contract is complete; continue proof work before wallet trust changes.",
        }]
    return [{
        "severity": "warning",
        "code": "stage2_data_gaps_visible",
        "message": f"Stage 2 contract is packaged, but {len(blockers)} data-quality gaps remain visible.",
    }]


def next_required_actions(blockers: list[str]) -> list[str]:
    actions = [
        "Use this report to compare accepted trades, failed paper attempts, rejected signals, and wallet observations.",
        "Keep later outcomes out of decision-time context.",
    ]
    if "decision_time_market_context_still_partial" in blockers:
        actions.append("Improve historical decision-time market context before trusting wallet scores.")
    if "legacy_context_rows_need_canonical_field_backfill" in blockers:
        actions.append("Backfill older context rows into the canonical context field set where source data exists.")
    return actions
