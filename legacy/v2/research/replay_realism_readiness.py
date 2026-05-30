from __future__ import annotations

import time
from typing import Any

from research.historical_replay_dataset import DEFAULT_EVALUATION_WINDOWS


MODE = "REPLAY_REALISM_STAGE6_READINESS_REVIEW_ONLY"
READINESS_VERSION = "replay_realism_readiness.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def first_int(values: list[Any], default: int = 0) -> int:
    for value in values:
        if value not in (None, ""):
            return safe_int(value, default)
    return default


def expected_window_labels() -> list[str]:
    return [label for label, _seconds in DEFAULT_EVALUATION_WINDOWS]


def gate_row(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def derived_trust_gate_pct(summary: dict[str, Any], *, records_scanned: int, score_ready_records: int) -> int:
    explicit = summary.get("trust_gate_completion_pct")
    if explicit not in (None, ""):
        return safe_int(explicit)
    classified_rows = (
        score_ready_records
        + safe_int(summary.get("near_score_ready_records"))
        + safe_int(summary.get("blocked_missing_price_rows"))
        + safe_int(summary.get("blocked_missing_liquidity_rows"))
        + safe_int(summary.get("blocked_not_decision_time_safe_rows"))
        + safe_int(summary.get("needs_market_cap_recompute_rows"))
    )
    return pct(classified_rows, records_scanned)


def required_field_counts(summary: dict[str, Any]) -> dict[str, int]:
    explicit = as_dict(summary.get("required_field_counts"))
    if explicit:
        return {str(key): safe_int(value) for key, value in explicit.items()}
    return {
        "price": safe_int(summary.get("blocked_missing_price_rows")),
        "liquidity": safe_int(summary.get("blocked_missing_liquidity_rows")),
        "market_cap": safe_int(summary.get("near_score_ready_records")) + safe_int(summary.get("needs_market_cap_recompute_rows")),
    }


def build_replay_realism_readiness_report(
    *,
    replay_summary: dict[str, Any],
    trusted_market_context_report: dict[str, Any],
    supply_evidence_report: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    replay_counts = as_dict(replay_summary.get("counts"))
    fill_counts = as_dict(replay_summary.get("fill_status_counts"))
    trusted_summary = as_dict(trusted_market_context_report.get("summary"))
    supply_summary = as_dict(supply_evidence_report.get("summary"))

    events = safe_int(replay_counts.get("events"))
    unsafe_events = safe_int(replay_counts.get("unsafe_events"))
    score_ready_records = safe_int(trusted_summary.get("score_ready_records"))
    scanned_records = safe_int(trusted_summary.get("records_scanned"))
    supply_recovered = safe_int(supply_summary.get("supply_recovered_records"))
    supply_scanned = first_int([supply_summary.get("records_scanned"), supply_summary.get("candidate_rows")])
    unsafe_current_supply = safe_int(supply_summary.get("unsafe_current_only_records"))
    trusted_gate_pct = derived_trust_gate_pct(
        trusted_summary,
        records_scanned=scanned_records,
        score_ready_records=score_ready_records,
    )
    home_built_pct = safe_int(trusted_summary.get("home_built_onchain_reconstruction_pct"))

    gates = [
        gate_row(
            "live_execution_locked",
            replay_summary.get("live_execution_locked") is True
            and trusted_market_context_report.get("live_execution_locked") is True
            and supply_evidence_report.get("live_execution_locked") is True,
            "All Stage 6 reports must remain review-only with live execution locked.",
        ),
        gate_row(
            "decision_time_leakage_absent",
            unsafe_events == 0 and events > 0,
            "Historical replay events must keep future/later outcome fields out of decision context.",
        ),
        gate_row(
            "fixed_outcome_windows_declared",
            list(replay_summary.get("evaluation_windows") or []) == expected_window_labels(),
            "Replay must declare fixed 30s, 2m, 5m, and 15m evaluation windows.",
        ),
        gate_row(
            "fillability_classified",
            bool(fill_counts) and any(key in fill_counts for key in ("fillable_with_assumptions", "failed_liquidity_floor", "unknown_liquidity", "partial_fill_limited")),
            "Replay must classify fillability instead of assuming perfect fills.",
        ),
        gate_row(
            "trusted_market_context_blocks_incomplete_rows",
            trusted_gate_pct == 100,
            "Historical market context gate must classify every row and block incomplete rows from scoring.",
        ),
        gate_row(
            "unsafe_current_supply_rejected",
            unsafe_current_supply == 0 and supply_scanned > 0,
            "Current-only token supply must not be treated as decision-time historical supply.",
        ),
    ]
    passed_gates = [gate["name"] for gate in gates if gate["passed"]]
    failed_gates = [failed_gate_name(gate["name"]) for gate in gates if not gate["passed"]]

    blocking_data_gaps: list[str] = []
    if score_ready_records <= 0:
        blocking_data_gaps.append("no_score_ready_historical_market_context")
    if supply_recovered < supply_scanned and supply_scanned > 0:
        blocking_data_gaps.append("historical_supply_still_missing")
    required_fields = required_field_counts(trusted_summary)
    for field in ("price", "liquidity", "market_cap"):
        if safe_int(required_fields.get(field)) > 0:
            blocking_data_gaps.append(f"missing_{field}")

    contract_pct = pct(len(passed_gates), len(gates))
    data_score_readiness_pct = pct(score_ready_records, scanned_records)
    supply_readiness_pct = pct(supply_recovered, supply_scanned)

    operator_summary = (
        "Stage 6 realism gate is complete; market-context coverage remains blocked from scoring."
        if contract_pct == 100 and blocking_data_gaps
        else "Stage 6 realism gate and score-ready market context are complete."
        if contract_pct == 100
        else "Stage 6 realism gate is incomplete; resolve failed gates before trusting replay output."
    )

    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "readiness_version": READINESS_VERSION,
        "operator_summary": operator_summary,
        "summary": {
            "stage6_realism_contract_completion_pct": contract_pct,
            "data_score_readiness_pct": data_score_readiness_pct,
            "home_built_onchain_reconstruction_pct": home_built_pct,
            "historical_supply_readiness_pct": supply_readiness_pct,
            "events": events,
            "unsafe_events": unsafe_events,
            "score_ready_records": score_ready_records,
            "historical_market_context_records_scanned": scanned_records,
            "supply_recovered_records": supply_recovered,
            "supply_records_scanned": supply_scanned,
        },
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "blocking_data_gaps": sorted(set(blocking_data_gaps)),
        "gates": gates,
        "required_fields_remaining": required_fields,
        "fill_status_counts": fill_counts,
        "next_required_actions": next_required_actions(
            failed_gates=failed_gates,
            blocking_data_gaps=blocking_data_gaps,
        ),
    }


def next_required_actions(*, failed_gates: list[str], blocking_data_gaps: list[str]) -> list[str]:
    actions: list[str] = []
    if failed_gates:
        actions.append("Fix failed Stage 6 realism gates before expanding historical replay samples.")
    if "missing_price" in blocking_data_gaps:
        actions.append("Recover remaining decision-time prices from richer pool math or validated fallback snapshots.")
    if "missing_liquidity" in blocking_data_gaps:
        actions.append("Recover remaining decision-time liquidity from richer pool or bonding-curve evidence.")
    if "historical_supply_still_missing" in blocking_data_gaps or "missing_market_cap" in blocking_data_gaps:
        actions.append("Acquire archival mint-account supply or full mint/burn reconstruction before market cap can be score-ready.")
    if not actions:
        actions.append("Rebuild wallet replay scorecards using score-ready Stage 6 context.")
    return actions


def failed_gate_name(gate_name: str) -> str:
    aliases = {
        "decision_time_leakage_absent": "decision_time_leakage_present",
        "live_execution_locked": "live_execution_not_locked",
        "fixed_outcome_windows_declared": "fixed_outcome_windows_missing",
        "fillability_classified": "fillability_not_classified",
        "trusted_market_context_blocks_incomplete_rows": "trusted_market_context_gate_incomplete",
        "unsafe_current_supply_rejected": "unsafe_current_supply_present",
    }
    return aliases.get(gate_name, gate_name)
