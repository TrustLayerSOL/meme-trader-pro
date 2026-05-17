from __future__ import annotations

import time
from typing import Any


MODE = "VALIDATION_PROOF_LAYER_REVIEW_ONLY"

CRITERION_MAP = {
    "decision_time_market_context_requires_reconstruction": {
        "code": "decision_time_market_context",
        "requirement": "Recover decision-time market context from trusted historical/on-chain evidence.",
        "minimum_standard": "No current-price substitution; enough prior context to evaluate wallet entries.",
    },
    "historical_liquidity_still_incomplete": {
        "code": "historical_liquidity",
        "requirement": "Recover replay-safe historical liquidity for candidate evidence rows.",
        "minimum_standard": "Liquidity/fillability coverage is high enough to model realistic entry and exit constraints.",
    },
    "historical_market_cap_still_incomplete": {
        "code": "historical_market_cap",
        "requirement": "Recover replay-safe historical market cap or the supply inputs required to compute it.",
        "minimum_standard": "Market-cap context exists at decision time for score-driving rows.",
    },
    "historical_price_still_incomplete": {
        "code": "historical_price",
        "requirement": "Recover replay-safe historical price for wallet evidence and replay rows.",
        "minimum_standard": "Entry/exit price context is reconstructed from prior or transaction-time evidence.",
    },
    "historical_supply_still_missing": {
        "code": "historical_supply",
        "requirement": "Recover decision-time token supply needed for market-cap calculations.",
        "minimum_standard": "No current-only supply assumptions are allowed in proof rows.",
    },
    "known_outcome_coverage_still_low": {
        "code": "known_outcome_coverage",
        "requirement": "Raise known later-outcome coverage for accepted, rejected, and wallet-observed signals.",
        "minimum_standard": "Enough known 30s/2m/5m/15m outcomes to compare traded and skipped signals honestly.",
    },
    "outcome_labels_require_new_or_unrecovered_history": {
        "code": "outcome_labels",
        "requirement": "Backfill missing outcome labels from replay-safe history only.",
        "minimum_standard": "Later outcome labels are separated from decision-time context.",
    },
    "outcome_labels_require_replay_safe_timelines": {
        "code": "replay_safe_timelines",
        "requirement": "Build replay-safe token timelines for outcome windows.",
        "minimum_standard": "No future data is used inside decision-time fields.",
    },
    "score_ready_market_context_absent": {
        "code": "score_ready_market_context",
        "requirement": "Create score-ready decision-time market context for wallet evidence rows.",
        "minimum_standard": "Price, liquidity, market cap, and supply are trusted enough for wallet scoring.",
    },
    "timeline_data_not_score_ready": {
        "code": "timeline_score_readiness",
        "requirement": "Promote token timelines from inventory-only to score-ready evidence.",
        "minimum_standard": "Timeline readiness is above the proof threshold before trusting scores.",
    },
    "unknown_outcomes_cannot_be_pattern_matched": {
        "code": "unknown_outcomes",
        "requirement": "Keep unknown outcomes out of runner/rug pattern labels.",
        "minimum_standard": "Unknown rows remain separate until they are explicitly labeled.",
    },
    "wallet_trust_changes_blocked": {
        "code": "wallet_trust_gate",
        "requirement": "Keep wallet promotion/demotion blocked until proof criteria pass.",
        "minimum_standard": "Wallet trust remains evidence proportional and human-review gated.",
    },
}

CRITERION_PRIORITY = {
    "score_ready_market_context": 10,
    "decision_time_market_context": 20,
    "known_outcome_coverage": 30,
    "replay_safe_timelines": 40,
    "outcome_labels": 50,
    "historical_price": 60,
    "historical_liquidity": 70,
    "historical_market_cap": 80,
    "historical_supply": 90,
    "timeline_score_readiness": 100,
    "unknown_outcomes": 110,
    "wallet_trust_gate": 120,
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


def build_validation_proof_layer_report(
    *,
    alerting_dashboard_layer: dict[str, Any],
    stage8_validation: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    alert_summary = as_dict(alerting_dashboard_layer.get("summary"))
    stage8_summary = as_dict(stage8_validation.get("summary"))
    blocker_codes = sorted({
        str(blocker)
        for blocker in as_list(alerting_dashboard_layer.get("blocked_data_issues"))
        if blocker
    })
    proof_criteria = build_proof_criteria(blocker_codes)
    proof_readiness_pct = min(
        safe_int(alert_summary.get("research_data_readiness_pct")),
        safe_int(stage8_summary.get("proof_readiness_pct")),
    )
    blocked_count = sum(1 for criterion in proof_criteria if criterion["status"] == "blocked")
    gates = [
        gate(
            "live_execution_locked",
            alerting_dashboard_layer.get("live_execution_locked") is True
            and stage8_validation.get("live_execution_locked") is True,
            "Proof reporting must remain live-execution locked.",
        ),
        gate(
            "wallet_list_mutation_blocked",
            alerting_dashboard_layer.get("wallet_list_mutated") is not True
            and stage8_validation.get("wallet_list_mutated") is not True,
            "Proof reporting cannot mutate wallet trust or wallet lists.",
        ),
        gate(
            "operator_status_complete",
            safe_int(alert_summary.get("alerting_dashboard_layer_completion_pct")) == 100,
            "Proof layer depends on the completed operator-status layer.",
        ),
        gate(
            "stage8_validation_complete",
            safe_int(stage8_summary.get("stage8_validation_contract_completion_pct")) == 100,
            "Proof layer depends on the completed Stage 8 validation contract.",
        ),
        gate(
            "proof_not_overclaimed",
            proof_readiness_pct < 100 or blocked_count == 0,
            "Proof readiness must stay separate from infrastructure completion.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "validation_proof_layer_completion_pct": pct(len(passed), len(gates)),
            "proof_readiness_pct": proof_readiness_pct,
            "criteria_count": len(proof_criteria),
            "blocked_criteria_count": blocked_count,
            "stage8_known_15m_outcomes": safe_int(stage8_summary.get("known_15m_outcomes")),
            "stage8_fillable_rate": safe_int(stage8_summary.get("fillable_rate")),
            "stage8_data_score_readiness_pct": safe_int(stage8_summary.get("stage6_data_score_readiness_pct")),
        },
        "proof_criteria": proof_criteria,
        "operator_alerts": build_operator_alerts(proof_readiness_pct=proof_readiness_pct, blocked_count=blocked_count),
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "next_required_actions": next_required_actions(proof_criteria),
        "operator_note": (
            "Validation / Proof Layer is a checklist for what must be true before wallet scores can be trusted. "
            "It does not prove edge while proof readiness is below 100%."
        ),
    }


def build_proof_criteria(blocker_codes: list[str]) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = []
    for blocker in blocker_codes:
        template = CRITERION_MAP.get(blocker, {
            "code": blocker,
            "requirement": f"Resolve blocker: {blocker}",
            "minimum_standard": "Document and clear this blocker before using the data for proof.",
        })
        criteria.append({
            "code": template["code"],
            "source_blocker": blocker,
            "status": "blocked",
            "requirement": template["requirement"],
            "minimum_standard": template["minimum_standard"],
            "can_drive_wallet_trust": False,
        })
    criteria.sort(key=lambda row: (CRITERION_PRIORITY.get(str(row["code"]), 999), str(row["code"])))
    return criteria


def build_operator_alerts(*, proof_readiness_pct: int, blocked_count: int) -> list[dict[str, Any]]:
    if proof_readiness_pct >= 100 and blocked_count == 0:
        return [{
            "severity": "info",
            "code": "proof_ready_for_review",
            "message": "Proof criteria are clear; compare wallet-score changes against the validation baseline before any trust updates.",
        }]
    return [{
        "severity": "blocker",
        "code": "proof_not_ready",
        "message": "Do not use this as permission to promote wallets, demote wallets, or claim edge until blocked proof criteria are cleared.",
    }]


def next_required_actions(proof_criteria: list[dict[str, Any]]) -> list[str]:
    if not proof_criteria:
        return ["No proof blockers are visible; compare wallet trust changes against the validation baseline before applying any list changes."]
    return [
        "Work blocked proof criteria before adding new strategy features.",
        "Prioritize score-ready market context, known outcomes, and replay-safe token timelines.",
        "Keep wallet trust changes review-only until proof criteria are cleared.",
    ]
