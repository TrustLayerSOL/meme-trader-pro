from __future__ import annotations

import time
from typing import Any


MODE = "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY"
BEHAVIORAL_TRUST_MODE = "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY"
PROOF_MODE = "VALIDATION_PROOF_LAYER_REVIEW_ONLY"
STAGE8_MODE = "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY"
EVIDENCE_MODE = "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY"
TIMELINE_MODE = "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY"

MIN_KNOWN_15M_OUTCOMES = 30
MIN_FILLABLE_RATE = 70
MIN_SCORE_READY_MARKET_CONTEXT = 1


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


def completed(report: dict[str, Any], *, mode: str, completion_key: str) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == mode
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(summary.get(completion_key)) == 100
    )


def locked_report_visible(report: dict[str, Any]) -> bool:
    return bool(report) and report.get("live_execution_locked") is True and report.get("wallet_list_mutated") is not True


def build_proof_readiness_blocker_reduction_report(
    *,
    behavioral_trust_validation: dict[str, Any] | None,
    validation_proof_layer: dict[str, Any] | None,
    stage8_validation: dict[str, Any] | None,
    evidence_layer: dict[str, Any] | None,
    replayable_token_timelines: dict[str, Any] | None,
    onchain_market_context: dict[str, Any] | None,
    supply_evidence: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    trust = as_dict(behavioral_trust_validation)
    proof = as_dict(validation_proof_layer)
    stage8 = as_dict(stage8_validation)
    evidence = as_dict(evidence_layer)
    timelines = as_dict(replayable_token_timelines)
    onchain = as_dict(onchain_market_context)
    supply = as_dict(supply_evidence)

    trust_summary = as_dict(trust.get("summary"))
    proof_summary = as_dict(proof.get("summary"))
    stage8_summary = as_dict(stage8.get("summary"))
    evidence_summary = as_dict(evidence.get("summary"))
    timeline_summary = as_dict(timelines.get("summary"))
    onchain_summary = as_dict(onchain.get("summary"))
    supply_summary = as_dict(supply.get("summary"))

    known_15m = first_positive_int(
        trust_summary.get("known_15m_outcomes"),
        stage8_summary.get("known_15m_outcomes"),
        proof_summary.get("stage8_known_15m_outcomes"),
    )
    known_required = max(safe_int(trust_summary.get("known_15m_required")), MIN_KNOWN_15M_OUTCOMES)
    positive_fill_rate = first_positive_int(
        trust_summary.get("fillable_rate"),
        stage8_summary.get("fillable_rate"),
        proof_summary.get("stage8_fillable_rate"),
    )
    fillability_evidence_rate = first_positive_int(
        trust_summary.get("fillability_evidence_rate"),
        stage8_summary.get("fillability_evidence_rate"),
        proof_summary.get("stage8_fillability_evidence_rate"),
        positive_fill_rate,
    )
    fillable_required = max(safe_int(trust_summary.get("fillable_rate_required")), MIN_FILLABLE_RATE)
    score_ready_context = first_positive_int(
        trust_summary.get("score_ready_market_context_records"),
        evidence_summary.get("score_ready_market_context_records"),
        timeline_summary.get("score_ready_records"),
        onchain_summary.get("score_ready_candidate_records"),
    )

    reduction_queue = build_reduction_queue(
        known_15m=known_15m,
        known_required=known_required,
        fillability_evidence_rate=fillability_evidence_rate,
        fillable_required=fillable_required,
        score_ready_context=score_ready_context,
        evidence_summary=evidence_summary,
        timeline_summary=timeline_summary,
        onchain_summary=onchain_summary,
        supply_summary=supply_summary,
        onchain_block_reasons=as_dict(onchain_summary.get("block_reasons")) or as_dict(onchain.get("block_reasons")),
        timeline_blockers=as_list(timelines.get("residual_data_blockers")),
    )

    gates = [
        gate(
            "behavioral_trust_validation_visible",
            completed(trust, mode=BEHAVIORAL_TRUST_MODE, completion_key="behavioral_validation_completion_pct"),
            "Behavioral trust validation must be visible before blocker reduction can be prioritized.",
        ),
        gate(
            "validation_proof_visible",
            completed(proof, mode=PROOF_MODE, completion_key="validation_proof_layer_completion_pct"),
            "Validation proof checklist must be visible before blocker reduction can be prioritized.",
        ),
        gate(
            "stage8_validation_visible",
            completed(stage8, mode=STAGE8_MODE, completion_key="stage8_validation_contract_completion_pct"),
            "Stage 8 validation summary must be visible before blocker reduction can be prioritized.",
        ),
        gate(
            "evidence_layer_visible",
            completed(evidence, mode=EVIDENCE_MODE, completion_key="evidence_layer_completion_pct"),
            "Evidence layer summary must be visible before blocker reduction can be prioritized.",
        ),
        gate(
            "timeline_inventory_visible",
            completed(timelines, mode=TIMELINE_MODE, completion_key="replayable_token_timelines_completion_pct"),
            "Replayable token timeline inventory must be visible before blocker reduction can be prioritized.",
        ),
        gate(
            "onchain_context_visible",
            locked_report_visible(onchain),
            "On-chain market-context recovery report must be visible and locked.",
        ),
        gate(
            "supply_evidence_visible",
            locked_report_visible(supply),
            "Supply evidence report must be visible and locked.",
        ),
        gate(
            "uncertainty_explicit",
            len(reduction_queue) > 0,
            "Blocker reduction must expose explicit work items instead of inferring confidence.",
        ),
        gate("trust_stays_blocked", True, "This report cannot justify wallet trust or apply trust changes."),
        gate("live_execution_locked", True, "This report cannot unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "This report cannot mutate wallet lists."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]

    return {
        "mode": MODE,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "behavioral_trust_changes_allowed": False,
        "summary": {
            "blocker_reduction_completion_pct": pct(len(passed), len(gates)),
            "proof_readiness_pct": safe_int(proof_summary.get("proof_readiness_pct")),
            "behavioral_trust_justified": bool(trust_summary.get("behavioral_trust_justified")) is True,
            "validated_patterns": safe_int(trust_summary.get("validated_patterns")),
            "trust_ready_patterns": safe_int(trust_summary.get("trust_ready_patterns")),
            "known_15m_outcomes": known_15m,
            "known_15m_required": known_required,
            "known_15m_needed": max(0, known_required - known_15m),
            "positive_fill_rate": positive_fill_rate,
            "fillable_rate": positive_fill_rate,
            "fillability_evidence_rate": fillability_evidence_rate,
            "fillable_rate_required": fillable_required,
            "fillable_rate_gap": max(0, fillable_required - fillability_evidence_rate),
            "fillability_evidence_gap": max(0, fillable_required - fillability_evidence_rate),
            "fillable_events": safe_int(stage8_summary.get("fillable_events")),
            "fillability_evidence_events": safe_int(stage8_summary.get("fillability_evidence_events")),
            "unknown_liquidity_events": safe_int(stage8_summary.get("unknown_liquidity_events")),
            "score_ready_market_context_records": score_ready_context,
            "score_ready_market_context_required": MIN_SCORE_READY_MARKET_CONTEXT,
            "remaining_blocked_wallets": safe_int(evidence_summary.get("remaining_blocked_wallets")),
            "wallets_needing_market_context": safe_int(timeline_summary.get("wallets_needing_market_context")),
            "wallets_needing_outcome_labels": safe_int(timeline_summary.get("wallets_needing_outcome_labels")),
            "missing_market_context_rows": safe_int(timeline_summary.get("missing_market_context_rows")),
            "target_mints": safe_int(timeline_summary.get("target_mints")),
            "next_action_count": len(reduction_queue),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "reduction_queue": reduction_queue,
        "blocked_data_issues": sorted(set([str(item) for item in as_list(trust.get("blocked_data_issues")) + as_list(timelines.get("residual_data_blockers")) if item])),
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "next_required_actions": [row["next_action"] for row in reduction_queue],
        "operator_note": (
            "Proof-readiness blocker reduction ranks the next work required before behavioral trust can be justified. "
            "It is not a scoring, promotion, demotion, or live-execution layer."
        ),
    }


def first_positive_int(*values: Any) -> int:
    for value in values:
        parsed = safe_int(value)
        if parsed > 0:
            return parsed
    return 0


def build_reduction_queue(
    *,
    known_15m: int,
    known_required: int,
    fillability_evidence_rate: int,
    fillable_required: int,
    score_ready_context: int,
    evidence_summary: dict[str, Any],
    timeline_summary: dict[str, Any],
    onchain_summary: dict[str, Any],
    supply_summary: dict[str, Any],
    onchain_block_reasons: dict[str, Any],
    timeline_blockers: list[Any],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    if score_ready_context < MIN_SCORE_READY_MARKET_CONTEXT:
        queue.append({
            "priority": 1,
            "category": "score_ready_market_context",
            "current": score_ready_context,
            "target": MIN_SCORE_READY_MARKET_CONTEXT,
            "gap": max(0, MIN_SCORE_READY_MARKET_CONTEXT - score_ready_context),
            "affected_wallets": safe_int(timeline_summary.get("wallets_needing_market_context")),
            "affected_rows": safe_int(timeline_summary.get("missing_market_context_rows")),
            "affected_tokens": safe_int(timeline_summary.get("target_mints")),
            "blocked_by": score_ready_blockers(onchain_summary, supply_summary, onchain_block_reasons, timeline_blockers),
            "next_action": "Recover decision-time supply/market-cap context for rows that already have price and liquidity evidence.",
            "can_drive_wallet_trust": False,
        })
    if known_15m < known_required:
        queue.append({
            "priority": 2,
            "category": "known_15m_outcome_density",
            "current": known_15m,
            "target": known_required,
            "gap": max(0, known_required - known_15m),
            "affected_wallets": safe_int(evidence_summary.get("needs_outcome_labels")) or safe_int(timeline_summary.get("wallets_needing_outcome_labels")),
            "affected_rows": safe_int(evidence_summary.get("evidence_rows")),
            "blocked_by": ["missing_replay_safe_outcome_windows"],
            "next_action": "Backfill 15m outcome labels from replay-safe token timelines while keeping later outcomes separate from decision-time context.",
            "can_drive_wallet_trust": False,
        })
    if fillability_evidence_rate < fillable_required:
        queue.append({
            "priority": 3,
            "category": "fillability_evidence_coverage",
            "current": fillability_evidence_rate,
            "target": fillable_required,
            "gap": max(0, fillable_required - fillability_evidence_rate),
            "affected_rows": safe_int(timeline_summary.get("missing_market_context_rows")),
            "blocked_by": fillability_blockers(onchain_block_reasons),
            "next_action": "Reduce unknown-liquidity and missing-reserve rows before treating replay fills as realistic.",
            "can_drive_wallet_trust": False,
        })
    if safe_int(supply_summary.get("supply_recovered_records")) <= 0 and safe_int(supply_summary.get("needs_archival_supply_records")) > 0:
        queue.append({
            "priority": 4,
            "category": "archival_supply_evidence",
            "current": safe_int(supply_summary.get("supply_recovered_records")),
            "target": safe_int(supply_summary.get("needs_archival_supply_records")),
            "gap": safe_int(supply_summary.get("needs_archival_supply_records")),
            "affected_rows": safe_int(supply_summary.get("records_scanned")),
            "blocked_by": ["missing_archival_mint_supply"],
            "next_action": "Fetch or reconstruct historical mint-account supply at or before the decision slot; do not use current supply.",
            "can_drive_wallet_trust": False,
        })
    queue.sort(key=lambda row: safe_int(row.get("priority"), 999))
    return queue


def score_ready_blockers(
    onchain_summary: dict[str, Any],
    supply_summary: dict[str, Any],
    onchain_block_reasons: dict[str, Any],
    timeline_blockers: list[Any],
) -> list[str]:
    blockers: list[str] = []
    if safe_int(supply_summary.get("supply_recovered_records")) <= 0:
        blockers.append("historical_supply")
    if safe_int(onchain_summary.get("market_cap_recovered_records")) <= 0:
        blockers.append("market_cap")
    if safe_int(onchain_summary.get("liquidity_recovered_records")) <= 0 or safe_int(onchain_block_reasons.get("blocked_missing_liquidity")) > 0:
        blockers.append("liquidity")
    if safe_int(onchain_summary.get("price_recovered_records")) <= 0 or safe_int(onchain_block_reasons.get("blocked_missing_price")) > 0:
        blockers.append("price")
    blockers.extend(str(item).replace("_still_missing", "").replace("_still_incomplete", "") for item in timeline_blockers if item)
    return sorted(set(blockers))


def fillability_blockers(onchain_block_reasons: dict[str, Any]) -> list[str]:
    blockers = []
    if safe_int(onchain_block_reasons.get("blocked_missing_liquidity")) > 0:
        blockers.append("missing_liquidity")
    if safe_int(onchain_block_reasons.get("blocked_missing_onchain_pool_reserves")) > 0:
        blockers.append("missing_onchain_pool_reserves")
    if safe_int(onchain_block_reasons.get("blocked_missing_quote_usd_price")) > 0:
        blockers.append("missing_quote_usd_price")
    return blockers or ["low_fillability_coverage"]
