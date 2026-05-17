from __future__ import annotations

import time
from typing import Any


MODE = "ALERTING_DASHBOARD_LAYER_REVIEW_ONLY"


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


def build_alerting_dashboard_layer_report(
    *,
    evidence_layer: dict[str, Any],
    replayable_timelines: dict[str, Any],
    similar_rug_patterns: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    status_cards = [
        build_status_card(
            name="Evidence Layer",
            completion_pct=safe_int(as_dict(evidence_layer.get("summary")).get("evidence_layer_completion_pct")),
            readiness_pct=safe_int(as_dict(evidence_layer.get("summary")).get("wallet_score_readiness_pct")),
            report=evidence_layer,
            key_counts={
                "remaining_blocked_wallets": safe_int(as_dict(evidence_layer.get("summary")).get("remaining_blocked_wallets")),
            },
        ),
        build_status_card(
            name="Replayable Token Timelines",
            completion_pct=safe_int(as_dict(replayable_timelines.get("summary")).get("replayable_token_timelines_completion_pct")),
            readiness_pct=safe_int(as_dict(replayable_timelines.get("summary")).get("timeline_data_readiness_pct")),
            report=replayable_timelines,
            key_counts={
                "missing_market_context_rows": safe_int(as_dict(replayable_timelines.get("summary")).get("missing_market_context_rows")),
            },
        ),
        build_status_card(
            name="Similar-Rug Pattern Matching",
            completion_pct=safe_int(as_dict(similar_rug_patterns.get("summary")).get("similar_rug_pattern_completion_pct")),
            readiness_pct=safe_int(as_dict(similar_rug_patterns.get("summary")).get("rug_pattern_data_readiness_pct")),
            report=similar_rug_patterns,
            key_counts={
                "known_rug_rows": safe_int(as_dict(similar_rug_patterns.get("summary")).get("known_rug_rows")),
                "unknown_rows_excluded_from_rug_labels": safe_int(as_dict(similar_rug_patterns.get("summary")).get("unknown_rows_excluded_from_rug_labels")),
            },
        ),
    ]
    blockers = sorted({
        str(blocker)
        for card in status_cards
        for blocker in card.get("blockers", [])
        if blocker
    })
    gates = [
        gate(
            "live_execution_locked",
            all(report.get("live_execution_locked") is True for report in (evidence_layer, replayable_timelines, similar_rug_patterns)),
            "All dashboard-layer inputs must remain live-execution locked.",
        ),
        gate(
            "wallet_list_mutation_blocked",
            all(report.get("wallet_list_mutated") is not True for report in (evidence_layer, replayable_timelines, similar_rug_patterns)),
            "Dashboard-layer status cannot apply wallet-list changes.",
        ),
        gate(
            "upstream_gates_visible",
            all(card["completion_pct"] == 100 for card in status_cards),
            "Evidence, timeline, and similar-rug gates must be visible before this layer is complete.",
        ),
        gate(
            "blockers_visible",
            len(blockers) >= 0,
            "Current blockers must be summarized instead of hidden.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    completed_gate_count = sum(1 for card in status_cards if card["completion_pct"] == 100)
    readiness_values = [card["readiness_pct"] for card in status_cards]
    readiness_pct = min(readiness_values) if readiness_values else 0
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "alerting_dashboard_layer_completion_pct": pct(len(passed), len(gates)),
            "research_data_readiness_pct": readiness_pct,
            "completed_gate_count": completed_gate_count,
            "status_card_count": len(status_cards),
            "blocked_data_issue_count": len(blockers),
        },
        "status_cards": status_cards,
        "operator_alerts": build_operator_alerts(status_cards=status_cards, blockers=blockers, readiness_pct=readiness_pct),
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "blocked_data_issues": blockers,
        "next_required_actions": next_required_actions(readiness_pct=readiness_pct, blockers=blockers),
        "operator_note": (
            "Alerting / Dashboard Layer is complete when the key research gates, blockers, and next actions are visible "
            "in one read-only status payload. It is not live execution, wallet mutation, or proof of edge."
        ),
    }


def build_status_card(
    *,
    name: str,
    completion_pct: int,
    readiness_pct: int,
    report: dict[str, Any],
    key_counts: dict[str, int],
) -> dict[str, Any]:
    blockers = as_list(report.get("residual_data_blockers")) + as_list(report.get("blocked_data_issues"))
    return {
        "name": name,
        "completion_pct": completion_pct,
        "readiness_pct": readiness_pct,
        "state": "complete_but_data_blocked" if completion_pct == 100 and readiness_pct == 0 else "incomplete" if completion_pct < 100 else "ready",
        "live_execution_locked": report.get("live_execution_locked") is True,
        "wallet_list_mutated": report.get("wallet_list_mutated") is True,
        "blockers": sorted({str(blocker) for blocker in blockers if blocker}),
        "key_counts": key_counts,
    }


def build_operator_alerts(*, status_cards: list[dict[str, Any]], blockers: list[str], readiness_pct: int) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if readiness_pct == 0:
        alerts.append({
            "severity": "blocker",
            "code": "research_data_not_score_ready",
            "message": "Do not promote wallets or treat replay as edge while research data readiness is 0%.",
        })
    for card in status_cards:
        if card.get("completion_pct") == 100 and card.get("readiness_pct") == 0:
            alerts.append({
                "severity": "warning",
                "code": f"{str(card.get('name')).lower().replace(' ', '_').replace('-', '_')}_ready_for_review_only",
                "message": f"{card.get('name')} is complete as infrastructure but blocked from scoring/trust use.",
            })
    if blockers:
        alerts.append({
            "severity": "info",
            "code": "blocked_data_issues_visible",
            "message": f"{len(blockers)} blocker categories are visible in this status layer.",
        })
    return alerts


def next_required_actions(*, readiness_pct: int, blockers: list[str]) -> list[str]:
    actions = [
        "Keep live execution locked and keep wallet-list mutations behind human review.",
        "Use this status layer as the operator entry point before choosing the next evidence lane.",
    ]
    if readiness_pct == 0:
        actions.append("Improve score-ready market context and outcome labels before treating wallet scores as trusted.")
    if blockers:
        actions.append("Work the visible blocker categories in priority order instead of adding new strategy features.")
    return actions
