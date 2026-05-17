from __future__ import annotations

import time
from typing import Any


MODE = "PRODUCTIZATION_OPERATOR_WORKFLOW_REVIEW_ONLY"

STEP_SPECS = [
    {
        "name": "Evidence Layer",
        "state_key": "evidence_layer",
        "completion_key": "evidence_layer_completion_pct",
        "readiness_key": "wallet_score_readiness_pct",
        "report_path": "data/reports/wallet_backfills/evidence_layer_completion_report.json",
        "api_endpoint": "/api/evidence-layer-completion",
        "build_command": "python utils/build_evidence_layer_completion.py",
    },
    {
        "name": "Replayable Token Timelines",
        "state_key": "replayable_timelines",
        "completion_key": "replayable_token_timelines_completion_pct",
        "readiness_key": "timeline_data_readiness_pct",
        "report_path": "data/reports/historical_backfill/replayable_token_timelines_report.json",
        "api_endpoint": "/api/replayable-token-timelines",
        "build_command": "python utils/build_replayable_token_timelines.py",
    },
    {
        "name": "Similar-Rug Pattern Matching",
        "state_key": "similar_rug_patterns",
        "completion_key": "similar_rug_pattern_completion_pct",
        "readiness_key": "rug_pattern_data_readiness_pct",
        "report_path": "data/reports/historical_backfill/similar_rug_patterns_report.json",
        "api_endpoint": "/api/similar-rug-patterns",
        "build_command": "python utils/build_similar_rug_patterns.py",
    },
    {
        "name": "Alerting / Dashboard Layer",
        "state_key": "alerting_dashboard_layer",
        "completion_key": "alerting_dashboard_layer_completion_pct",
        "readiness_key": "research_data_readiness_pct",
        "report_path": "data/reports/dashboard/alerting_dashboard_layer_report.json",
        "api_endpoint": "/api/alerting-dashboard-layer",
        "build_command": "python utils/build_alerting_dashboard_layer.py",
    },
    {
        "name": "Validation / Proof Layer",
        "state_key": "validation_proof_layer",
        "completion_key": "validation_proof_layer_completion_pct",
        "readiness_key": "proof_readiness_pct",
        "report_path": "data/reports/replay_validation/validation_proof_layer_report.json",
        "api_endpoint": "/api/validation-proof-layer",
        "build_command": "python utils/build_validation_proof_layer.py",
    },
]


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


def build_productization_operator_workflow_report(
    *,
    evidence_layer: dict[str, Any],
    replayable_timelines: dict[str, Any],
    similar_rug_patterns: dict[str, Any],
    alerting_dashboard_layer: dict[str, Any],
    validation_proof_layer: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    reports = {
        "evidence_layer": as_dict(evidence_layer),
        "replayable_timelines": as_dict(replayable_timelines),
        "similar_rug_patterns": as_dict(similar_rug_patterns),
        "alerting_dashboard_layer": as_dict(alerting_dashboard_layer),
        "validation_proof_layer": as_dict(validation_proof_layer),
    }
    workflow_steps = build_workflow_steps(reports)
    completion_values = [safe_int(step.get("completion_pct")) for step in workflow_steps]
    readiness_values = [safe_int(step.get("readiness_pct")) for step in workflow_steps]
    proof_summary = as_dict(reports["validation_proof_layer"].get("summary"))
    proof_criteria = as_list(reports["validation_proof_layer"].get("proof_criteria"))
    blocked_criteria_count = safe_int(proof_summary.get("blocked_criteria_count"))
    if not blocked_criteria_count:
        blocked_criteria_count = sum(1 for row in proof_criteria if as_dict(row).get("status") == "blocked")
    blocked_data_issues = sorted({
        str(blocker)
        for blocker in as_list(reports["alerting_dashboard_layer"].get("blocked_data_issues"))
        if blocker
    })
    review_paths = build_review_paths()
    gates = [
        gate(
            "report_chain_visible",
            all(value == 100 for value in completion_values),
            "All research-layer report gates must be available before the operator workflow is complete.",
        ),
        gate(
            "live_execution_locked",
            all(report.get("live_execution_locked") is True for report in reports.values()),
            "Productization workflow must not unlock or imply live execution.",
        ),
        gate(
            "wallet_list_mutation_blocked",
            all(report.get("wallet_list_mutated") is not True for report in reports.values()),
            "Productization workflow cannot mutate wallet lists or trust state.",
        ),
        gate(
            "review_paths_visible",
            "run_reports" in review_paths and "api_review" in review_paths,
            "Operator must have clear run and review paths.",
        ),
        gate(
            "proof_not_overclaimed",
            min(readiness_values) < 100 or blocked_criteria_count == 0,
            "Productization completion must stay separate from proof readiness.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    proof_readiness_pct = safe_int(proof_summary.get("proof_readiness_pct"))
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "read_only": True,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "productization_completion_pct": pct(len(passed), len(gates)),
            "operator_workflow_step_count": len(workflow_steps),
            "completed_workflow_step_count": sum(1 for value in completion_values if value == 100),
            "research_data_readiness_pct": min(readiness_values) if readiness_values else 0,
            "proof_readiness_pct": proof_readiness_pct,
            "blocked_data_issue_count": len(blocked_data_issues),
            "blocked_criteria_count": blocked_criteria_count,
        },
        "workflow_steps": workflow_steps,
        "review_paths": review_paths,
        "operator_alerts": build_operator_alerts(
            proof_readiness_pct=proof_readiness_pct,
            blocked_criteria_count=blocked_criteria_count,
        ),
        "blocked_data_issues": blocked_data_issues,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "next_required_actions": next_required_actions(blocked_criteria_count=blocked_criteria_count),
        "operator_note": (
            "Productization here means a clean read-only operator workflow for running and reviewing the quant "
            "research report chain. It is not live trading, wallet-list mutation, or proof of edge."
        ),
    }


def build_workflow_steps(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, spec in enumerate(STEP_SPECS, start=1):
        report = reports.get(str(spec["state_key"]), {})
        summary = as_dict(report.get("summary"))
        steps.append({
            "order": index,
            "name": spec["name"],
            "status": "complete" if safe_int(summary.get(str(spec["completion_key"]))) == 100 else "incomplete",
            "completion_pct": safe_int(summary.get(str(spec["completion_key"]))),
            "readiness_pct": safe_int(summary.get(str(spec["readiness_key"]))),
            "report_path": spec["report_path"],
            "api_endpoint": spec["api_endpoint"],
            "build_command": spec["build_command"],
            "live_execution_locked": report.get("live_execution_locked") is True,
            "wallet_list_mutated": report.get("wallet_list_mutated") is True,
        })
    return steps


def build_review_paths() -> dict[str, Any]:
    return {
        "run_reports": [step["build_command"] for step in STEP_SPECS],
        "api_review": [step["api_endpoint"] for step in STEP_SPECS] + ["/api/productization-operator-workflow"],
        "report_review": [step["report_path"] for step in STEP_SPECS] + [
            "data/reports/productization/operator_workflow_report.json"
        ],
    }


def build_operator_alerts(*, proof_readiness_pct: int, blocked_criteria_count: int) -> list[dict[str, Any]]:
    if proof_readiness_pct >= 100 and blocked_criteria_count == 0:
        return [{
            "severity": "info",
            "code": "operator_workflow_ready_for_review",
            "message": "Workflow is packaged; compare proof-ready changes against the prior baseline before any wallet trust update.",
        }]
    return [{
        "severity": "blocker",
        "code": "operator_workflow_review_only",
        "message": "Do not use this workflow as permission to trade, promote wallets, demote wallets, or claim edge.",
    }]


def next_required_actions(*, blocked_criteria_count: int) -> list[str]:
    actions = [
        "Run the report chain from the operator workflow before reviewing wallet evidence.",
        "Review the productization workflow endpoint before choosing the next evidence/proof lane.",
    ]
    if blocked_criteria_count:
        actions.append("Clear blocked proof criteria before using wallet scores for trust changes.")
    return actions
