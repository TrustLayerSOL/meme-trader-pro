from __future__ import annotations

import time
from typing import Any


MODE = "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY"
BEHAVIORAL_MODE = "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY"
PROOF_MODE = "VALIDATION_PROOF_LAYER_REVIEW_ONLY"
STAGE8_MODE = "REPLAY_VALIDATION_STAGE8_READINESS_REVIEW_ONLY"
EVIDENCE_MODE = "EVIDENCE_LAYER_COMPLETION_REVIEW_ONLY"

MIN_KNOWN_15M_OUTCOMES = 30
MIN_FILLABLE_RATE = 70
MIN_PROOF_READINESS = 100
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
    return (
        report.get("mode") == mode
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(as_dict(report.get("summary")).get(completion_key)) == 100
    )


def build_behavioral_trust_validation_report(
    *,
    behavioral_intelligence_layer: dict[str, Any] | None,
    validation_proof_layer: dict[str, Any] | None,
    stage8_validation: dict[str, Any] | None,
    evidence_layer: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    behavioral = as_dict(behavioral_intelligence_layer)
    proof = as_dict(validation_proof_layer)
    stage8 = as_dict(stage8_validation)
    evidence = as_dict(evidence_layer)
    behavioral_summary = as_dict(behavioral.get("summary"))
    proof_summary = as_dict(proof.get("summary"))
    stage8_summary = as_dict(stage8.get("summary"))
    evidence_summary = as_dict(evidence.get("summary"))

    patterns = [row for row in as_list(behavioral.get("behavioral_pattern_candidates")) if isinstance(row, dict)]
    proof_readiness = safe_int(proof_summary.get("proof_readiness_pct"))
    known_15m = safe_int(stage8_summary.get("known_15m_outcomes"))
    positive_fill_rate = safe_int(stage8_summary.get("fillable_rate"))
    fillability_evidence_rate = safe_int(
        stage8_summary.get("fillability_evidence_rate"),
        positive_fill_rate,
    )
    score_ready_market_context = safe_int(evidence_summary.get("score_ready_market_context_records"))
    pattern_rows = [
        validate_pattern(
            pattern,
            proof_readiness=proof_readiness,
            known_15m=known_15m,
            fillability_evidence_rate=fillability_evidence_rate,
            score_ready_market_context=score_ready_market_context,
        )
        for pattern in patterns
    ]
    trust_ready = [row for row in pattern_rows if row["trust_verdict"] == "justified_for_review"]
    blockers = blocked_data_issues(
        proof_readiness=proof_readiness,
        known_15m=known_15m,
        fillability_evidence_rate=fillability_evidence_rate,
        score_ready_market_context=score_ready_market_context,
        pattern_count=len(pattern_rows),
    )
    gates = [
        gate(
            "behavioral_layer_visible",
            completed(behavioral, mode=BEHAVIORAL_MODE, completion_key="stage9_behavioral_intelligence_completion_pct"),
            "Behavioral trust validation requires completed Stage 9 pattern candidates.",
        ),
        gate(
            "behavioral_patterns_visible",
            len(pattern_rows) > 0,
            "At least one behavioral pattern candidate must be present for validation.",
        ),
        gate(
            "validation_proof_visible",
            completed(proof, mode=PROOF_MODE, completion_key="validation_proof_layer_completion_pct"),
            "Validation proof checklist must be visible and locked.",
        ),
        gate(
            "stage8_validation_visible",
            completed(stage8, mode=STAGE8_MODE, completion_key="stage8_validation_contract_completion_pct"),
            "Stage 8 validation contract must be visible and locked.",
        ),
        gate(
            "evidence_layer_visible",
            completed(evidence, mode=EVIDENCE_MODE, completion_key="evidence_layer_completion_pct"),
            "Evidence layer must be visible and locked.",
        ),
        gate(
            "uncertainty_explicit",
            bool(blockers) or len(trust_ready) == len(pattern_rows),
            "Trust validation must expose blockers instead of inferring confidence.",
        ),
        gate("behavioral_trust_blocked", True, "This layer cannot apply behavioral trust changes."),
        gate("live_execution_locked", True, "This layer cannot unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "This layer cannot mutate wallet lists."),
        gate("auto_trust_mutation_blocked", True, "This layer cannot auto-promote or auto-demote wallets."),
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
            "behavioral_validation_completion_pct": pct(len(passed), len(gates)),
            "behavioral_trust_justified": len(pattern_rows) > 0 and len(trust_ready) == len(pattern_rows) and not blockers,
            "validated_patterns": len(pattern_rows),
            "trust_ready_patterns": len(trust_ready),
            "proof_readiness_pct": proof_readiness,
            "known_15m_outcomes": known_15m,
            "known_15m_required": MIN_KNOWN_15M_OUTCOMES,
            "positive_fill_rate": positive_fill_rate,
            "fillable_rate": positive_fill_rate,
            "fillability_evidence_rate": fillability_evidence_rate,
            "fillable_rate_required": MIN_FILLABLE_RATE,
            "score_ready_market_context_records": score_ready_market_context,
            "wallet_score_readiness_pct": safe_int(evidence_summary.get("wallet_score_readiness_pct")),
            "stage9_pattern_candidates": safe_int(behavioral_summary.get("pattern_candidates")),
            "blocked_issue_count": len(blockers),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "pattern_validations": pattern_rows,
        "blocked_data_issues": blockers,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "operator_note": (
            "Behavioral trust validation is a negative/positive evidence gate. It should only justify behavioral trust "
            "when replay-safe outcome density, fillability, proof readiness, and score-ready market context all meet the threshold."
        ),
    }


def validate_pattern(
    pattern: dict[str, Any],
    *,
    proof_readiness: int,
    known_15m: int,
    fillability_evidence_rate: int,
    score_ready_market_context: int,
) -> dict[str, Any]:
    reasons = []
    if proof_readiness < MIN_PROOF_READINESS:
        reasons.append("proof_readiness_below_threshold")
    if known_15m < MIN_KNOWN_15M_OUTCOMES:
        reasons.append("insufficient_known_outcome_density")
    if fillability_evidence_rate < MIN_FILLABLE_RATE:
        reasons.append("fillable_rate_below_threshold")
    if score_ready_market_context < MIN_SCORE_READY_MARKET_CONTEXT:
        reasons.append("market_context_not_score_ready")
    if pattern.get("can_drive_wallet_trust") is True or pattern.get("mutation_allowed") is True:
        reasons.append("upstream_pattern_mutation_not_allowed")
    verdict = "justified_for_review" if not reasons else "not_justified"
    return {
        "pattern_id": pattern.get("pattern_id"),
        "wallets": as_list(pattern.get("wallets")),
        "dominant_regime": str(pattern.get("dominant_regime") or "unknown"),
        "total_shared_events": safe_int(pattern.get("total_shared_events")),
        "regime_known_15m_outcomes": safe_int(pattern.get("regime_known_15m_outcomes")),
        "proof_readiness_pct": proof_readiness,
        "known_15m_outcomes": known_15m,
        "fillability_evidence_rate": fillability_evidence_rate,
        "score_ready_market_context_records": score_ready_market_context,
        "trust_verdict": verdict,
        "blocking_reasons": reasons,
        "can_drive_wallet_trust": False,
        "mutation_allowed": False,
    }


def blocked_data_issues(
    *,
    proof_readiness: int,
    known_15m: int,
    fillability_evidence_rate: int,
    score_ready_market_context: int,
    pattern_count: int,
) -> list[str]:
    blockers = []
    if pattern_count <= 0:
        blockers.append("behavioral_patterns_missing")
    if proof_readiness < MIN_PROOF_READINESS:
        blockers.append("proof_readiness_below_threshold")
    if known_15m < MIN_KNOWN_15M_OUTCOMES:
        blockers.append("insufficient_known_outcome_density")
    if fillability_evidence_rate < MIN_FILLABLE_RATE:
        blockers.append("fillable_rate_below_threshold")
    if score_ready_market_context < MIN_SCORE_READY_MARKET_CONTEXT:
        blockers.append("score_ready_market_context_absent")
    return blockers
