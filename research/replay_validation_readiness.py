from __future__ import annotations

import time
from typing import Any


MODE = "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY"
READINESS_VERSION = "replay_validation_readiness.v1"
KNOWN_OUTCOMES = ("runner", "rug", "dead", "loser", "flat")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def percent(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate_row(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def failed_gate_name(gate_name: str) -> str:
    aliases = {
        "live_execution_locked": "live_execution_not_locked",
        "replay_dataset_safe": "replay_dataset_unsafe_or_empty",
        "stage6_realism_complete": "stage6_realism_incomplete",
        "replay_scorecard_matches_event_count": "replay_scorecard_stale",
        "wallet_outcome_ledger_matches_event_count": "wallet_outcome_ledger_stale",
        "candidate_backfill_queue_classified": "candidate_backfill_queue_missing",
        "evidence_gaps_are_explicit": "evidence_gaps_not_explicit",
    }
    return aliases.get(gate_name, gate_name)


def known_15m_outcome_count(replay_summary: dict[str, Any]) -> int:
    window = as_dict(as_dict(replay_summary.get("window_outcome_counts")).get("15m"))
    return sum(safe_int(window.get(label)) for label in KNOWN_OUTCOMES)


def forward_calibration_summary(
    *,
    forward_outcome_resolution: dict[str, Any],
    daily_forward_calibration: dict[str, Any],
) -> dict[str, Any]:
    forward_summary = as_dict(forward_outcome_resolution.get("summary"))
    daily_summary = as_dict(daily_forward_calibration.get("summary"))
    daily_rows = daily_forward_calibration.get("days") if isinstance(daily_forward_calibration.get("days"), list) else []
    outcome_counts: dict[str, int] = {}
    for row in daily_rows:
        for label, count in as_dict(as_dict(row).get("outcomes_15m")).items():
            outcome_counts[str(label)] = outcome_counts.get(str(label), 0) + safe_int(count)

    records = safe_int(forward_summary.get("records_scanned")) or safe_int(daily_summary.get("records"))
    known_15m = safe_int(forward_summary.get("known_15m_outcomes")) or safe_int(
        daily_summary.get("known_15m_outcomes")
    )
    mutations = safe_int(forward_summary.get("wallet_list_mutations")) + safe_int(
        forward_summary.get("auto_trust_mutations")
    )
    mutations += safe_int(daily_summary.get("wallet_list_mutations")) + safe_int(
        daily_summary.get("auto_trust_mutations")
    )
    return {
        "records": records,
        "known_15m_outcomes": known_15m,
        "known_15m_outcome_rate": percent(known_15m, records),
        "pending_windows": safe_int(forward_summary.get("pending_windows")),
        "wallets_affected": safe_int(forward_summary.get("wallets_affected")),
        "tokens_affected": safe_int(forward_summary.get("tokens_affected")),
        "days": safe_int(daily_summary.get("days")) or len(daily_rows),
        "outcomes_15m": dict(sorted(outcome_counts.items())),
        "aggregate_window_outcome_counts": as_dict(forward_summary.get("window_outcome_counts")),
        "status_counts": as_dict(forward_summary.get("status_counts")),
        "mutation_count": mutations,
        "review_only": forward_outcome_resolution.get("review_only") is not False
        and daily_forward_calibration.get("review_only") is not False,
        "live_execution_locked": forward_outcome_resolution.get("live_execution_locked") is not False
        and daily_forward_calibration.get("live_execution_locked") is not False,
    }


def fillable_count(replay_summary: dict[str, Any]) -> int:
    fills = as_dict(replay_summary.get("fill_status_counts"))
    return (
        safe_int(fills.get("fillable_with_assumptions"))
        + safe_int(fills.get("partial_fill_limited"))
    )


def failed_liquidity_count(replay_summary: dict[str, Any]) -> int:
    fills = as_dict(replay_summary.get("fill_status_counts"))
    return safe_int(fills.get("failed_liquidity_floor"))


def fillability_evidence_count(replay_summary: dict[str, Any]) -> int:
    # Failed liquidity-floor rows are not positive fills, but they are still
    # usable fillability evidence because replay can model why entry failed.
    return fillable_count(replay_summary) + failed_liquidity_count(replay_summary)


def candidate_gap_total(summary: dict[str, Any]) -> int:
    return (
        safe_int(summary.get("needs_wallet_history"))
        + safe_int(summary.get("needs_outcome_label_backfill"))
        + safe_int(summary.get("needs_more_replay_events"))
        + safe_int(summary.get("risk_review"))
    )


def build_replay_validation_readiness_report(
    *,
    replay_summary: dict[str, Any],
    stage6_readiness: dict[str, Any],
    wallet_replay_scorecard: dict[str, Any],
    wallet_outcome_ledger: dict[str, Any],
    wallet_candidate_backfill_targets: dict[str, Any],
    forward_outcome_resolution: dict[str, Any] | None = None,
    daily_forward_calibration: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    replay_counts = as_dict(replay_summary.get("counts"))
    stage6_summary = as_dict(stage6_readiness.get("summary"))
    scorecard_counts = as_dict(wallet_replay_scorecard.get("counts"))
    ledger_counts = as_dict(wallet_outcome_ledger.get("counts"))
    target_summary = as_dict(wallet_candidate_backfill_targets.get("summary"))

    replay_events = safe_int(replay_counts.get("events"))
    unsafe_events = safe_int(replay_counts.get("unsafe_events"))
    scorecard_events = safe_int(scorecard_counts.get("events"))
    ledger_records = safe_int(ledger_counts.get("records"))
    stage6_pct = safe_int(stage6_summary.get("stage6_realism_contract_completion_pct"))
    data_score_readiness_pct = safe_int(stage6_summary.get("data_score_readiness_pct"))
    target_total = safe_int(target_summary.get("total_targets"))
    explicit_stage6_gaps = [str(gap) for gap in stage6_readiness.get("blocking_data_gaps") or [] if str(gap)]

    gates = [
        gate_row(
            "live_execution_locked",
            replay_summary.get("live_execution_locked") is True
            and stage6_readiness.get("live_execution_locked") is True
            and wallet_replay_scorecard.get("live_execution_locked") is True
            and wallet_outcome_ledger.get("live_execution_locked") is True
            and wallet_candidate_backfill_targets.get("live_execution_locked") is True,
            "Replay validation must remain review-only with live execution locked.",
        ),
        gate_row(
            "replay_dataset_safe",
            replay_events > 0 and unsafe_events == 0,
            "Historical replay must have events and zero decision-time leakage flags.",
        ),
        gate_row(
            "stage6_realism_complete",
            stage6_pct == 100,
            "Stage 8 depends on the completed Stage 6 realism gate.",
        ),
        gate_row(
            "replay_scorecard_matches_event_count",
            scorecard_events == replay_events and replay_events > 0,
            "Wallet replay scorecard must be rebuilt from the current replay event count.",
        ),
        gate_row(
            "wallet_outcome_ledger_matches_event_count",
            ledger_records == replay_events and replay_events > 0,
            "Wallet outcome ledger must be rebuilt from the current replay records.",
        ),
        gate_row(
            "candidate_backfill_queue_classified",
            "total_targets" in target_summary,
            "Candidate backfill queue must classify the next evidence action per wallet.",
        ),
        gate_row(
            "evidence_gaps_are_explicit",
            bool(explicit_stage6_gaps) or candidate_gap_total(target_summary) > 0 or data_score_readiness_pct == 100,
            "Stage 8 must expose what is missing instead of treating unknowns as proof.",
        ),
    ]
    passed_gates = [gate["name"] for gate in gates if gate["passed"]]
    failed_gates = [failed_gate_name(gate["name"]) for gate in gates if not gate["passed"]]

    known_15m = known_15m_outcome_count(replay_summary)
    fillable = fillable_count(replay_summary)
    failed_liquidity = failed_liquidity_count(replay_summary)
    fillability_evidence = fillability_evidence_count(replay_summary)
    known_15m_rate = percent(known_15m, replay_events)
    fillable_rate = percent(fillable, replay_events)
    failed_liquidity_rate = percent(failed_liquidity, replay_events)
    fillability_evidence_rate = percent(fillability_evidence, replay_events)
    unknown_liquidity = safe_int(as_dict(replay_summary.get("fill_status_counts")).get("unknown_liquidity"))
    unknown_liquidity_rate = percent(unknown_liquidity, replay_events)
    proof_readiness_pct = min(known_15m_rate, fillability_evidence_rate, data_score_readiness_pct)
    forward_summary = forward_calibration_summary(
        forward_outcome_resolution=as_dict(forward_outcome_resolution),
        daily_forward_calibration=as_dict(daily_forward_calibration),
    )

    evidence_gaps = evidence_gap_rows(
        known_15m_rate=known_15m_rate,
        fillability_evidence_rate=fillability_evidence_rate,
        data_score_readiness_pct=data_score_readiness_pct,
        target_summary=target_summary,
        stage6_gaps=explicit_stage6_gaps,
    )
    contract_pct = percent(len(passed_gates), len(gates))
    operator_summary = (
        "Stage 8 validation loop is complete; edge proof remains evidence-limited."
        if contract_pct == 100 and evidence_gaps
        else "Stage 8 validation loop and evidence proof gates are complete."
        if contract_pct == 100
        else "Stage 8 validation loop is incomplete; rebuild or repair failed validation artifacts."
    )
    if forward_summary["records"] > 0:
        operator_summary = (
            f"{operator_summary} Forward calibration is reported separately from historical proof readiness."
        )

    return {
        "generated_at": generated_at,
        "mode": MODE,
        "readiness_version": READINESS_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": operator_summary,
        "summary": {
            "stage8_validation_contract_completion_pct": contract_pct,
            "proof_readiness_pct": proof_readiness_pct,
            "events": replay_events,
            "unsafe_events": unsafe_events,
            "known_15m_outcomes": known_15m,
            "known_15m_outcome_rate": known_15m_rate,
            "forward_records": forward_summary["records"],
            "forward_known_15m_outcomes": forward_summary["known_15m_outcomes"],
            "forward_known_15m_outcome_rate": forward_summary["known_15m_outcome_rate"],
            "forward_pending_windows": forward_summary["pending_windows"],
            "forward_days": forward_summary["days"],
            "forward_mutation_count": forward_summary["mutation_count"],
            "fillable_events": fillable,
            "fillable_rate": fillable_rate,
            "failed_liquidity_events": failed_liquidity,
            "failed_liquidity_rate": failed_liquidity_rate,
            "fillability_evidence_events": fillability_evidence,
            "fillability_evidence_rate": fillability_evidence_rate,
            "unknown_liquidity_events": unknown_liquidity,
            "unknown_liquidity_rate": unknown_liquidity_rate,
            "stage6_realism_contract_completion_pct": stage6_pct,
            "stage6_data_score_readiness_pct": data_score_readiness_pct,
            "wallets_in_scorecard": safe_int(scorecard_counts.get("wallets")),
            "wallets_in_outcome_ledger": safe_int(ledger_counts.get("wallets")),
            "candidate_backfill_targets": target_total,
        },
        "passed_gates": passed_gates,
        "failed_gates": failed_gates,
        "gates": gates,
        "forward_calibration_summary": forward_summary,
        "evidence_gaps": evidence_gaps,
        "target_summary": target_summary,
        "stage6_blocking_data_gaps": explicit_stage6_gaps,
        "next_required_actions": next_required_actions(failed_gates=failed_gates, evidence_gaps=evidence_gaps),
    }


def evidence_gap_rows(
    *,
    known_15m_rate: int,
    fillability_evidence_rate: int,
    data_score_readiness_pct: int,
    target_summary: dict[str, Any],
    stage6_gaps: list[str],
) -> list[str]:
    gaps: list[str] = []
    if known_15m_rate < 70:
        gaps.append("low_known_outcome_coverage")
    if fillability_evidence_rate < 70:
        gaps.append("low_fillable_coverage")
    if data_score_readiness_pct < 70:
        gaps.append("low_market_context_score_readiness")
    for key in ("needs_wallet_history", "needs_outcome_label_backfill", "needs_more_replay_events", "risk_review"):
        if safe_int(target_summary.get(key)) > 0:
            gaps.append(key)
    gaps.extend(stage6_gaps)
    return sorted(dict.fromkeys(gaps))


def next_required_actions(*, failed_gates: list[str], evidence_gaps: list[str]) -> list[str]:
    actions: list[str] = []
    if failed_gates:
        actions.append("Rebuild or repair stale Stage 8 validation artifacts before interpreting wallet performance.")
    if "needs_wallet_history" in evidence_gaps:
        actions.append("Collect read-only wallet history for queued wallets before trusting promotion/demotion evidence.")
    if "needs_outcome_label_backfill" in evidence_gaps or "low_known_outcome_coverage" in evidence_gaps:
        actions.append("Backfill later outcome labels for replay events so accepted and rejected signals become comparable.")
    if "low_fillable_coverage" in evidence_gaps:
        actions.append("Improve decision-time liquidity coverage so replay can classify fillability instead of unknown liquidity.")
    if "low_market_context_score_readiness" in evidence_gaps:
        actions.append("Use Stage 6 data gaps as the market-context recovery queue before using wallet scores as proof.")
    if not actions:
        actions.append("Begin comparing wallet promotion/demotion changes against this validation baseline.")
    return actions
