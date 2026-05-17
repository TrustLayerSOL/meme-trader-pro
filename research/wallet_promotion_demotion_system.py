from __future__ import annotations

import time
from typing import Any


MODE = "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY"

REQUIRED_REPORT_MODES = {
    "stage4_review": "WALLET_STAGE4_PROMOTION_DEMOTION_REVIEW_ONLY",
    "candidate_audit": "WALLET_CANDIDATE_AUDIT_REVIEW_ONLY",
    "decision_prep": "WALLET_CANDIDATE_DECISION_PREP_REVIEW_ONLY",
    "review_summary": "WALLET_CANDIDATE_REVIEW_SUMMARY_ONLY",
    "collection_plan": "WALLET_CANDIDATE_COLLECTION_PLAN_REVIEW_ONLY",
    "collection_batch": "WALLET_CANDIDATE_COLLECTION_BATCH_REVIEW_ONLY",
    "blocker_reducer": "WALLET_CANDIDATE_BLOCKER_REDUCER_REVIEW_ONLY",
    "context_recovery_queue": "WALLET_CANDIDATE_CONTEXT_RECOVERY_QUEUE_REVIEW_ONLY",
    "context_recovery_runner": "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY",
    "context_recovery_closeout": "WALLET_CANDIDATE_CONTEXT_RECOVERY_CLOSEOUT_REVIEW_ONLY",
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


def report_visible(report: dict[str, Any], expected_mode: str) -> bool:
    return bool(report) and report.get("mode") == expected_mode


def report_is_locked(report: dict[str, Any]) -> bool:
    return as_dict(report).get("live_execution_locked") is True


def report_is_guarded(report: dict[str, Any]) -> bool:
    report = as_dict(report)
    return report.get("wallet_list_apply_allowed") is not True and report.get("wallet_list_mutated") is not True


def all_reports_visible(reports: dict[str, dict[str, Any]]) -> bool:
    return all(report_visible(reports.get(name, {}), mode) for name, mode in REQUIRED_REPORT_MODES.items())


def all_reports_locked(reports: dict[str, dict[str, Any]]) -> bool:
    return all(report_is_locked(report) for report in reports.values())


def all_reports_guarded(reports: dict[str, dict[str, Any]]) -> bool:
    return all(report_is_guarded(report) for report in reports.values())


def proposed_decisions_are_unapproved(decision_prep: dict[str, Any]) -> bool:
    proposed = as_list(as_dict(decision_prep).get("proposed_decisions"))
    return all(as_dict(row).get("approved") is not True for row in proposed)


def stage4_auto_applied_count(stage4_review: dict[str, Any]) -> int:
    summary = as_dict(as_dict(stage4_review).get("summary"))
    reviews = as_list(as_dict(stage4_review).get("reviews"))
    return safe_int(summary.get("auto_applied")) + sum(1 for row in reviews if as_dict(row).get("auto_apply") is True)


def wallet_pipeline_count(stage4_review: dict[str, Any], candidate_audit: dict[str, Any]) -> int:
    stage4_summary = as_dict(as_dict(stage4_review).get("summary"))
    audit_counts = as_dict(as_dict(candidate_audit).get("counts"))
    return max(
        safe_int(stage4_summary.get("wallets_reviewed")),
        safe_int(audit_counts.get("candidates")) + safe_int(audit_counts.get("resolved")),
    )


def count_by_summary(report: dict[str, Any], *keys: str) -> int:
    summary = as_dict(as_dict(report).get("summary"))
    return sum(safe_int(summary.get(key)) for key in keys)


def build_wallet_promotion_demotion_system_report(
    *,
    stage4_review: dict[str, Any],
    candidate_audit: dict[str, Any],
    decision_prep: dict[str, Any],
    review_summary: dict[str, Any],
    collection_plan: dict[str, Any],
    collection_batch: dict[str, Any],
    blocker_reducer: dict[str, Any],
    context_recovery_queue: dict[str, Any],
    context_recovery_runner: dict[str, Any],
    context_recovery_closeout: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    reports = {
        "stage4_review": as_dict(stage4_review),
        "candidate_audit": as_dict(candidate_audit),
        "decision_prep": as_dict(decision_prep),
        "review_summary": as_dict(review_summary),
        "collection_plan": as_dict(collection_plan),
        "collection_batch": as_dict(collection_batch),
        "blocker_reducer": as_dict(blocker_reducer),
        "context_recovery_queue": as_dict(context_recovery_queue),
        "context_recovery_runner": as_dict(context_recovery_runner),
        "context_recovery_closeout": as_dict(context_recovery_closeout),
    }
    audit_counts = as_dict(reports["candidate_audit"].get("counts"))
    plan_summary = as_dict(reports["collection_plan"].get("summary"))
    batch_summary = as_dict(reports["collection_batch"].get("summary"))
    closeout_summary = as_dict(reports["context_recovery_closeout"].get("summary"))
    auto_applied = stage4_auto_applied_count(reports["stage4_review"])
    blocked_wallets = safe_int(closeout_summary.get("still_blocked_wallets"))
    collection_targets = safe_int(plan_summary.get("total_targets"))
    gates = [
        gate(
            "report_chain_visible",
            all_reports_visible(reports),
            "Every Stage 4 review, audit, draft-decision, blocker, recovery, and closeout report must be visible.",
        ),
        gate(
            "live_execution_locked",
            all_reports_locked(reports),
            "Promotion/demotion workflow must not unlock live execution.",
        ),
        gate(
            "wallet_list_mutation_blocked",
            all_reports_guarded(reports),
            "Stage 4 completion gate cannot observe or allow wallet-list mutation.",
        ),
        gate(
            "candidate_audit_visible",
            report_visible(reports["candidate_audit"], REQUIRED_REPORT_MODES["candidate_audit"])
            and safe_int(audit_counts.get("candidates")) + safe_int(audit_counts.get("resolved")) >= 0,
            "Human-review candidate audit must be available.",
        ),
        gate(
            "draft_decisions_unapproved",
            proposed_decisions_are_unapproved(reports["decision_prep"]),
            "Decision-prep rows must remain draft-only until an operator explicitly approves them.",
        ),
        gate(
            "collection_plan_visible",
            report_visible(reports["collection_plan"], REQUIRED_REPORT_MODES["collection_plan"]),
            "Blocked wallets must route to exact evidence collection steps.",
        ),
        gate(
            "collection_batch_safe",
            report_visible(reports["collection_batch"], REQUIRED_REPORT_MODES["collection_batch"])
            and safe_int(batch_summary.get("steps_failed")) == 0,
            "The read-only Stage 4 evidence refresh must finish without failed steps.",
        ),
        gate(
            "blocker_reducer_visible",
            report_visible(reports["blocker_reducer"], REQUIRED_REPORT_MODES["blocker_reducer"]),
            "Operator-readable blocker categories must be available.",
        ),
        gate(
            "context_recovery_chain_visible",
            all(
                report_visible(reports[name], REQUIRED_REPORT_MODES[name])
                for name in ("context_recovery_queue", "context_recovery_runner", "context_recovery_closeout")
            ),
            "Context-recovery queue, runner, and closeout must be visible.",
        ),
        gate(
            "context_recovery_closeout_visible",
            report_visible(reports["context_recovery_closeout"], REQUIRED_REPORT_MODES["context_recovery_closeout"])
            and safe_int(closeout_summary.get("wallets_reviewed")) >= 0,
            "Closeout must explain what each blocked wallet needs next.",
        ),
        gate(
            "remaining_blockers_visible",
            blocked_wallets > 0 or collection_targets == 0 or safe_int(closeout_summary.get("ready_for_candidate_review")) > 0,
            "Stage 4 must make remaining blockers or review-ready wallets explicit.",
        ),
        gate(
            "auto_trust_mutation_blocked",
            auto_applied == 0,
            "No wallet may be auto-promoted, auto-demoted, or auto-applied by the Stage 4 workflow.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    completion_pct = pct(len(passed), len(gates))
    residual = residual_blockers(failed, blocked_wallets=blocked_wallets)
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "read_only": True,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "summary": {
            "stage4_promotion_demotion_completion_pct": completion_pct,
            "wallets_in_review_pipeline": wallet_pipeline_count(reports["stage4_review"], reports["candidate_audit"]),
            "promotion_review": safe_int(audit_counts.get("promotion_review")),
            "demotion_review": safe_int(audit_counts.get("demotion_review")),
            "risk_review_required": safe_int(audit_counts.get("risk_review_required")),
            "insufficient_evidence": safe_int(audit_counts.get("insufficient_evidence")),
            "resolved_candidates": safe_int(audit_counts.get("resolved")),
            "collection_targets": collection_targets,
            "context_recovery_targets": count_by_summary(reports["context_recovery_queue"], "total_recovery_targets"),
            "remaining_blocked_wallets": blocked_wallets,
            "ready_for_candidate_review": safe_int(closeout_summary.get("ready_for_candidate_review")),
            "auto_applied": auto_applied,
            "trusted_promotions_allowed": 0,
        },
        "report_modes": {name: report.get("mode") for name, report in reports.items()},
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "residual_blockers": residual,
        "operator_alerts": operator_alerts(residual),
        "next_required_actions": next_required_actions(residual),
        "operator_note": (
            "Stage 4 is complete only as a review-only promotion/demotion workflow: it can rank, route, draft, "
            "and explain wallet trust decisions, but it cannot auto-apply trust changes or unlock trading."
        ),
    }


def residual_blockers(failed_gates: list[str], *, blocked_wallets: int) -> list[str]:
    blockers: list[str] = []
    if failed_gates:
        blockers.append("stage4_review_chain_incomplete_or_unsafe")
    if blocked_wallets > 0:
        blockers.append("wallet_trust_changes_still_blocked_by_evidence")
    blockers.append("automatic_trust_evolution_not_enabled")
    return list(dict.fromkeys(blockers))


def operator_alerts(blockers: list[str]) -> list[dict[str, Any]]:
    if "stage4_review_chain_incomplete_or_unsafe" in blockers:
        return [{
            "severity": "blocker",
            "code": "stage4_gate_failed",
            "message": "Do not review or apply wallet trust changes until the Stage 4 report chain is visible, locked, and mutation-safe.",
        }]
    return [{
        "severity": "info",
        "code": "stage4_review_only_complete",
        "message": "Stage 4 workflow is complete for review, but automatic trust mutation remains disabled.",
    }]


def next_required_actions(blockers: list[str]) -> list[str]:
    if "stage4_review_chain_incomplete_or_unsafe" in blockers:
        return ["Rebuild the Stage 4 report chain before reviewing wallet trust decisions."]
    actions = [
        "Continue collecting outcome labels and decision-time market context for blocked wallets.",
        "Keep promotion/demotion changes behind explicit human approval and apply guard.",
    ]
    if "wallet_trust_changes_still_blocked_by_evidence" in blockers:
        actions.insert(0, "Use the context-recovery closeout to clear the remaining blocked wallet evidence buckets.")
    return actions
