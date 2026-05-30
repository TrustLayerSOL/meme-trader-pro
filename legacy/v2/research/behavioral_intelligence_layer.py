from __future__ import annotations

import time
from typing import Any


MODE = "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY"
STAGE5_MODE = "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY"
STAGE7_MODE = "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY"
PROOF_MODE = "VALIDATION_PROOF_LAYER_REVIEW_ONLY"


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


def stage5_visible(report: dict[str, Any]) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == STAGE5_MODE
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(summary.get("stage5_wallet_ecosystem_completion_pct")) == 100
    )


def stage7_visible(report: dict[str, Any]) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == STAGE7_MODE
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and report.get("regime_score_driving_allowed") is not True
        and safe_int(summary.get("stage7_regime_detection_completion_pct")) == 100
    )


def proof_visible(report: dict[str, Any]) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == PROOF_MODE
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(summary.get("validation_proof_layer_completion_pct")) == 100
    )


def dominant_regime(regime_rows: list[Any]) -> dict[str, Any]:
    rows = [row for row in regime_rows if isinstance(row, dict)]
    if not rows:
        return {"regime": "unknown", "events": 0, "known_15m_outcomes": 0, "outcomes_15m": {}}
    return sorted(rows, key=lambda row: (safe_int(row.get("events")), safe_int(row.get("known_15m_outcomes"))), reverse=True)[0]


def readiness_from_sources(stage5: dict[str, Any], stage7: dict[str, Any], proof: dict[str, Any]) -> int:
    stage5_summary = as_dict(stage5.get("summary"))
    stage7_summary = as_dict(stage7.get("summary"))
    proof_summary = as_dict(proof.get("summary"))
    return min(
        safe_int(stage5_summary.get("relationship_data_readiness_pct")),
        safe_int(stage7_summary.get("regime_data_readiness_pct")),
        safe_int(proof_summary.get("proof_readiness_pct")),
    )


def pattern_status(*, proof_readiness_pct: int, regime: str, known_outcomes: int) -> str:
    if proof_readiness_pct <= 0:
        return "blocked_needs_evidence"
    if regime == "unknown" or known_outcomes <= 0:
        return "blocked_needs_regime_outcomes"
    if proof_readiness_pct < 100:
        return "needs_behavioral_review"
    return "ready_for_baseline_comparison"


def behavioral_pattern_candidates(stage5: dict[str, Any], stage7: dict[str, Any], proof: dict[str, Any]) -> list[dict[str, Any]]:
    regime = dominant_regime(as_list(stage7.get("regime_rows")))
    proof_summary = as_dict(proof.get("summary"))
    proof_readiness = safe_int(proof_summary.get("proof_readiness_pct"))
    regime_name = str(regime.get("regime") or "unknown")
    known_outcomes = safe_int(regime.get("known_15m_outcomes"))
    rows = []
    for index, cluster in enumerate(as_list(stage5.get("cluster_candidates")), start=1):
        if not isinstance(cluster, dict):
            continue
        wallets = [str(wallet).strip() for wallet in as_list(cluster.get("wallets")) if str(wallet).strip()]
        if not wallets:
            continue
        rows.append(
            {
                "pattern_id": f"behavioral-cluster-{index:03d}",
                "pattern_type": "repeated_co_entry_cluster",
                "classification": "review_only_behavioral_cluster",
                "wallets": wallets,
                "wallet_count": safe_int(cluster.get("wallet_count"), len(wallets)),
                "repeated_edges": safe_int(cluster.get("repeated_edges")),
                "total_shared_events": safe_int(cluster.get("total_shared_events")),
                "ecosystem_review_priority": str(cluster.get("review_priority") or "observe_more"),
                "dominant_regime": regime_name,
                "regime_events": safe_int(regime.get("events")),
                "regime_known_15m_outcomes": known_outcomes,
                "regime_outcomes_15m": as_dict(regime.get("outcomes_15m")),
                "proof_readiness_pct": proof_readiness,
                "pattern_status": pattern_status(
                    proof_readiness_pct=proof_readiness,
                    regime=regime_name,
                    known_outcomes=known_outcomes,
                ),
                "can_drive_wallet_trust": False,
                "mutation_allowed": False,
            }
        )
    return sorted(rows, key=lambda row: (safe_int(row.get("repeated_edges")), safe_int(row.get("total_shared_events"))), reverse=True)


def build_behavioral_intelligence_layer_report(
    *,
    wallet_ecosystem_intelligence: dict[str, Any] | None,
    market_regime_detection: dict[str, Any] | None,
    validation_proof_layer: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    stage5 = as_dict(wallet_ecosystem_intelligence)
    stage7 = as_dict(market_regime_detection)
    proof = as_dict(validation_proof_layer)
    patterns = behavioral_pattern_candidates(stage5, stage7, proof)
    stage7_summary = as_dict(stage7.get("summary"))
    proof_summary = as_dict(proof.get("summary"))
    regime = dominant_regime(as_list(stage7.get("regime_rows")))
    data_readiness = readiness_from_sources(stage5, stage7, proof)
    gates = [
        gate("stage5_ecosystem_visible", stage5_visible(stage5), "Stage 9 requires the completed review-only Stage 5 ecosystem graph."),
        gate("stage7_regime_visible", stage7_visible(stage7), "Stage 9 requires the completed review-only Stage 7 regime segmentation."),
        gate("validation_proof_visible", proof_visible(proof), "Stage 9 requires the completed review-only validation/proof checklist."),
        gate("behavioral_pattern_candidates_visible", len(patterns) > 0, "Repeated behavioral pattern candidates must be visible for review."),
        gate("co_entry_cluster_patterns_indexed", all(row.get("pattern_type") == "repeated_co_entry_cluster" for row in patterns), "Co-entry cluster candidates must be indexed as behavioral patterns."),
        gate("regime_context_linked", bool(str(regime.get("regime") or "").strip()), "Pattern review must carry regime context, including unknown when that is all we have."),
        gate("proof_limitations_carried_forward", "proof_readiness_pct" in proof_summary, "Stage 9 must carry proof limitations forward instead of claiming edge."),
        gate("live_execution_locked", True, "Stage 9 must not unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "Stage 9 must not mutate tracked wallet lists."),
        gate("trust_mutation_blocked", True, "Stage 9 must not auto-promote or auto-demote wallets."),
        gate("behavioral_score_driving_blocked", True, "Stage 9 patterns are review-only until validation proves they are reliable."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    residual_blockers = residual_data_blockers(
        stage5=stage5,
        stage7=stage7,
        proof=proof,
        data_readiness=data_readiness,
    )
    return {
        "mode": MODE,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "behavioral_score_driving_allowed": False,
        "summary": {
            "stage9_behavioral_intelligence_completion_pct": pct(len(passed), len(gates)),
            "behavioral_data_readiness_pct": data_readiness,
            "pattern_candidates": len(patterns),
            "cluster_candidates_ingested": safe_int(as_dict(stage5.get("summary")).get("cluster_candidates")),
            "regime_rows_ingested": len(as_list(stage7.get("regime_rows"))),
            "dominant_regime": str(regime.get("regime") or "unknown"),
            "proof_readiness_pct": safe_int(proof_summary.get("proof_readiness_pct")),
            "known_15m_outcomes": safe_int(stage7_summary.get("known_15m_outcomes")),
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "behavioral_pattern_candidates": patterns,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "residual_data_blockers": residual_blockers,
        "operator_note": (
            "Stage 9 is a review-only behavioral intelligence layer. It connects wallet ecosystems, regime context, "
            "and proof limitations into pattern candidates, but those patterns cannot drive wallet trust or live execution."
        ),
    }


def residual_data_blockers(
    *,
    stage5: dict[str, Any],
    stage7: dict[str, Any],
    proof: dict[str, Any],
    data_readiness: int,
) -> list[str]:
    blockers: list[str] = []
    if not stage5_visible(stage5):
        blockers.append("stage5_ecosystem_report_missing_or_incomplete")
    if not stage7_visible(stage7):
        blockers.append("stage7_regime_report_missing_or_incomplete")
    if not proof_visible(proof):
        blockers.append("validation_proof_report_missing_or_incomplete")
    if safe_int(as_dict(stage7.get("summary")).get("regime_data_readiness_pct")) < 100:
        blockers.append("regime_data_not_ready")
    if safe_int(as_dict(proof.get("summary")).get("proof_readiness_pct")) < 100:
        blockers.append("proof_readiness_not_ready")
    if data_readiness < 100:
        blockers.append("behavioral_patterns_review_only")
    blockers.extend(str(blocker) for blocker in as_list(stage5.get("residual_data_blockers")) if blocker)
    blockers.extend(str(blocker) for blocker in as_list(stage7.get("residual_data_blockers")) if blocker)
    return sorted(set(blockers))

