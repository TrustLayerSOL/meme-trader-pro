from __future__ import annotations

import time
from typing import Any


MODE = "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY"
STAGE4_MODE = "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY"
STAGE9_MODE = "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY"
TRUST_MODE = "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY"
PROOF_MODE = "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY"
REGIME_MODE = "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY"

MAX_EVENTS = 6


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


def report_visible(report: dict[str, Any], mode: str, completion_key: str) -> bool:
    summary = as_dict(report.get("summary"))
    return (
        report.get("mode") == mode
        and report.get("live_execution_locked") is True
        and report.get("wallet_list_mutated") is not True
        and safe_int(summary.get(completion_key)) == 100
    )


def proof_phrase(proof_summary: dict[str, Any]) -> str:
    return (
        f"Proof readiness: {safe_int(proof_summary.get('proof_readiness_pct'))}%. "
        f"Known 15m outcomes: {safe_int(proof_summary.get('known_15m_outcomes'))}/"
        f"{safe_int(proof_summary.get('known_15m_required'))}. "
        f"Fillability evidence: {safe_int(proof_summary.get('fillability_evidence_rate'), safe_int(proof_summary.get('fillable_rate')))}%/"
        f"{safe_int(proof_summary.get('fillable_rate_required'))}% required."
    )


def event(
    *,
    event_id: str,
    event_type: str,
    channel: str,
    title: str,
    message: str,
    confidence: str,
    evidence_level: str,
    source: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "channel": channel,
        "title": title,
        "message": message,
        "confidence": confidence,
        "evidence_level": evidence_level,
        "source": source,
        "can_drive_trade": False,
        "can_mutate_wallet_trust": False,
        "live_execution_locked": True,
    }


def wallet_review_event(stage4: dict[str, Any], proof_summary: dict[str, Any]) -> dict[str, Any] | None:
    summary = as_dict(stage4.get("summary"))
    promotion_review = safe_int(summary.get("promotion_review"))
    demotion_review = safe_int(summary.get("demotion_review"))
    blocked = safe_int(summary.get("remaining_blocked_wallets"))
    if promotion_review <= 0 and demotion_review <= 0 and blocked <= 0:
        return None
    return event(
        event_id="wallet-review-state",
        event_type="wallet_review_transition",
        channel="#wallet-review",
        title="Wallet behavior review update",
        message=(
            "MemeTraderPro: Wallet behavior review update.\n\n"
            f"Review queue: {promotion_review} promotion-review, {demotion_review} demotion-review, "
            f"{blocked} still blocked by evidence.\n\n"
            f"{proof_phrase(proof_summary)}\n"
            "Trust changes remain human-review gated. Live execution remains locked."
        ),
        confidence="bounded",
        evidence_level="review_queue",
        source="wallet_promotion_demotion_system",
    )


def top_behavioral_cluster(behavioral: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in as_list(behavioral.get("behavioral_pattern_candidates")) if isinstance(row, dict)]
    if not rows:
        return None
    rows.sort(key=lambda row: (safe_int(row.get("repeated_edges")), safe_int(row.get("total_shared_events"))), reverse=True)
    top = rows[0]
    if safe_int(top.get("repeated_edges")) < 5 and str(top.get("ecosystem_review_priority")) != "high":
        return None
    return top


def behavioral_cluster_event(behavioral: dict[str, Any], proof_summary: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    cluster = top_behavioral_cluster(behavioral)
    if not cluster:
        return None, 0
    wallets = [str(wallet) for wallet in as_list(cluster.get("wallets")) if str(wallet).strip()]
    suppressed = len(wallets)
    message = (
        "MemeTraderPro: Unusual wallet cluster behavior detected for review.\n\n"
        f"Pattern: {cluster.get('pattern_id')} | repeated edges: {safe_int(cluster.get('repeated_edges'))} | "
        f"shared events: {safe_int(cluster.get('total_shared_events'))} | wallets: {safe_int(cluster.get('wallet_count'), len(wallets))}.\n"
        f"Dominant regime: {cluster.get('dominant_regime') or 'unknown'}.\n\n"
        f"{proof_phrase(proof_summary)}\n"
        "This is a behavioral review item, not a trading signal. Live execution remains locked."
    )
    return event(
        event_id=f"behavioral-cluster-{cluster.get('pattern_id')}",
        event_type="unusual_wallet_cluster_behavior",
        channel="#behavioral-patterns",
        title="Unusual wallet cluster behavior",
        message=message,
        confidence="limited",
        evidence_level="pattern_candidate",
        source="behavioral_intelligence_layer",
    ), suppressed


def proof_blocker_event(proof: dict[str, Any]) -> dict[str, Any] | None:
    summary = as_dict(proof.get("summary"))
    queue = [row for row in as_list(proof.get("reduction_queue")) if isinstance(row, dict)]
    if not queue:
        return None
    top = sorted(queue, key=lambda row: safe_int(row.get("priority"), 999))[0]
    message = (
        "MemeTraderPro: Replay-validation event.\n\n"
        f"Top blocker: {top.get('category')} | current: {safe_int(top.get('current'))} | "
        f"target: {safe_int(top.get('target'))} | gap: {safe_int(top.get('gap'))}.\n"
        f"Next action: {top.get('next_action')}.\n\n"
        f"{proof_phrase(summary)}\n"
        "This preserves replay discipline and prevents overclaiming edge. Live execution remains locked."
    )
    return event(
        event_id=f"proof-blocker-{top.get('category')}",
        event_type="important_replay_validation_event",
        channel="#replay-validation",
        title="Proof-readiness blocker update",
        message=message,
        confidence="high",
        evidence_level="proof_blocker_queue",
        source="proof_readiness_blocker_reduction",
    )


def regime_event(regime: dict[str, Any], proof_summary: dict[str, Any]) -> dict[str, Any] | None:
    summary = as_dict(regime.get("summary"))
    unknown_events = safe_int(summary.get("unknown_regime_events"))
    if unknown_events <= 0:
        return None
    message = (
        "MemeTraderPro: Regime monitor update.\n\n"
        f"Current dominant regime remains under-classified: {unknown_events} events are still tagged unknown. "
        f"Regime rows observed: {safe_int(summary.get('regime_tags_observed'))}.\n\n"
        f"{proof_phrase(proof_summary)}\n"
        "Regime labels remain review-only until outcome density improves. Live execution remains locked."
    )
    return event(
        event_id="regime-unknown-coverage",
        event_type="significant_regime_shift_or_gap",
        channel="#regime-monitor",
        title="Regime monitor update",
        message=message,
        confidence="limited",
        evidence_level="regime_gap",
        source="market_regime_detection",
    )


def evidence_milestone_event(proof: dict[str, Any]) -> dict[str, Any] | None:
    summary = as_dict(proof.get("summary"))
    missing = safe_int(summary.get("missing_market_context_rows"))
    if missing <= 0:
        return None
    message = (
        "MemeTraderPro: Evidence recovery milestone update.\n\n"
        f"Missing market-context rows still blocking proof: {missing}. "
        f"Score-ready market-context records: {safe_int(summary.get('score_ready_market_context_records'))}.\n\n"
        f"{proof_phrase(summary)}\n"
        "This is an evidence-transition alert, not proof of profitability. Live execution remains locked."
    )
    return event(
        event_id="evidence-recovery-market-context",
        event_type="major_evidence_recovery_milestone",
        channel="#research-updates",
        title="Evidence recovery status",
        message=message,
        confidence="high",
        evidence_level="blocker_counts",
        source="proof_readiness_blocker_reduction",
    )


def build_discord_events(
    *,
    wallet_promotion_demotion: dict[str, Any],
    behavioral_intelligence: dict[str, Any],
    proof_readiness_blocker_reduction: dict[str, Any],
    market_regime_detection: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    proof_summary = as_dict(proof_readiness_blocker_reduction.get("summary"))
    prepared: list[dict[str, Any]] = []
    suppressed = 0
    candidates = [
        wallet_review_event(wallet_promotion_demotion, proof_summary),
        proof_blocker_event(proof_readiness_blocker_reduction),
        regime_event(market_regime_detection, proof_summary),
        evidence_milestone_event(proof_readiness_blocker_reduction),
    ]
    cluster_event, cluster_suppressed = behavioral_cluster_event(behavioral_intelligence, proof_summary)
    suppressed += cluster_suppressed
    candidates.insert(1, cluster_event)
    seen: set[str] = set()
    for row in candidates:
        if not row or row["event_id"] in seen:
            continue
        prepared.append(row)
        seen.add(row["event_id"])
        if len(prepared) >= MAX_EVENTS:
            break
    return prepared, suppressed


def build_discord_intelligence_layer_report(
    *,
    wallet_promotion_demotion: dict[str, Any] | None,
    behavioral_intelligence: dict[str, Any] | None,
    behavioral_trust_validation: dict[str, Any] | None,
    proof_readiness_blocker_reduction: dict[str, Any] | None,
    market_regime_detection: dict[str, Any] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    stage4 = as_dict(wallet_promotion_demotion)
    stage9 = as_dict(behavioral_intelligence)
    trust = as_dict(behavioral_trust_validation)
    proof = as_dict(proof_readiness_blocker_reduction)
    regime = as_dict(market_regime_detection)
    events, suppressed = build_discord_events(
        wallet_promotion_demotion=stage4,
        behavioral_intelligence=stage9,
        proof_readiness_blocker_reduction=proof,
        market_regime_detection=regime,
    )
    gates = [
        gate(
            "wallet_review_visible",
            report_visible(stage4, STAGE4_MODE, "stage4_promotion_demotion_completion_pct"),
            "Discord review layer depends on the Stage 4 promotion/demotion review report.",
        ),
        gate(
            "behavioral_patterns_visible",
            report_visible(stage9, STAGE9_MODE, "stage9_behavioral_intelligence_completion_pct"),
            "Discord review layer depends on Stage 9 behavioral pattern candidates.",
        ),
        gate(
            "behavioral_trust_validation_visible",
            report_visible(trust, TRUST_MODE, "behavioral_validation_completion_pct"),
            "Discord review layer depends on behavioral trust validation.",
        ),
        gate(
            "proof_blockers_visible",
            report_visible(proof, PROOF_MODE, "blocker_reduction_completion_pct"),
            "Discord review layer depends on proof-readiness blockers.",
        ),
        gate(
            "regime_monitor_visible",
            report_visible(regime, REGIME_MODE, "stage7_regime_detection_completion_pct"),
            "Discord review layer depends on regime segmentation.",
        ),
        gate(
            "high_signal_events_only",
            len(events) <= MAX_EVENTS and all(event.get("can_drive_trade") is False for event in events),
            "Discord events must be sparse and non-trading.",
        ),
        gate("discord_dispatch_disabled_by_default", True, "Report generation never sends Discord messages."),
        gate("live_execution_locked", True, "Discord review layer cannot unlock execution."),
        gate("wallet_list_mutation_blocked", True, "Discord review layer cannot mutate wallet lists."),
        gate("trust_mutation_blocked", True, "Discord review layer cannot auto-promote or auto-demote wallets."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    channels = sorted({row["channel"] for row in events})
    return {
        "mode": MODE,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "behavioral_trust_changes_allowed": False,
        "discord_dispatch_enabled": False,
        "summary": {
            "discord_intelligence_layer_completion_pct": pct(len(passed), len(gates)),
            "events_prepared": len(events),
            "channels_touched": len(channels),
            "raw_wallet_events_suppressed": suppressed,
            "proof_readiness_pct": safe_int(as_dict(proof.get("summary")).get("proof_readiness_pct")),
            "behavioral_trust_justified": bool(as_dict(trust.get("summary")).get("behavioral_trust_justified")) is True,
            "wallet_list_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "channels": channels,
        "discord_events": events,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "next_required_actions": [
            "Keep Discord dispatch disabled until an operator configures a webhook locally.",
            "Send only sparse behavioral review transitions, proof blockers, regime changes, and evidence milestones.",
            "Keep all Discord copy explicit that proof readiness is limited and live execution is locked.",
        ],
        "operator_note": (
            "Discord intelligence is a sparse research-review layer. It surfaces meaningful behavioral and evidence "
            "state transitions without sending raw wallet spam, implying profitability, or touching execution."
        ),
    }
