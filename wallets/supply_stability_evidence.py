from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.archival_mint_supply_reconstruction import grouped_events, token_mint
from wallets.archival_supply_evidence import snapshot_supply, snapshot_token
from wallets.wallet_evidence_models import safe_int


MODE = "SUPPLY_STABILITY_EVIDENCE_REVIEW_ONLY"
VERSION = "supply_stability_evidence.v1"


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in rows or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def index_current_snapshots(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        token = snapshot_token(row)
        raw_supply, decimals, ui_supply = snapshot_supply(row)
        if not token or raw_supply is None or decimals is None or ui_supply is None:
            continue
        existing = indexed.get(token)
        if existing is None or safe_int(row.get("slot"), 0) >= safe_int(existing.get("slot"), 0):
            indexed[token] = row
    return indexed


def completeness_for(history_completeness: dict[str, Any], token: str) -> dict[str, Any]:
    row = history_completeness.get(token) if isinstance(history_completeness, dict) else {}
    return row if isinstance(row, dict) else {}


def current_snapshot_for(current_by_token: dict[str, dict[str, Any]], token: str) -> dict[str, Any] | None:
    return current_by_token.get(token)


def build_requirement_result(
    *,
    requirement: dict[str, Any],
    current_snapshot: dict[str, Any] | None,
    events: list[dict[str, Any]],
    completeness: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    token = token_mint(requirement)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    complete_through = safe_int(completeness.get("complete_through_slot"), 0)
    post_decision_complete_through = safe_int(completeness.get("post_decision_complete_through_slot"), 0)
    result = {
        "version": VERSION,
        "token_mint": token,
        "decision_slot": decision_slot or None,
        "complete_through_slot": complete_through or None,
        "post_decision_complete_through_slot": post_decision_complete_through or None,
        "history_source": completeness.get("source"),
        "row_count": safe_int(requirement.get("row_count"), 0),
        "post_decision_supply_event_count": 0,
        "status": "blocked_incomplete_post_decision_history",
        "block_reasons": ["mint_history_not_complete_through_decision_slot"],
        "can_mutate_wallet_trust": False,
    }
    if decision_slot <= 0:
        result["status"] = "blocked_missing_decision_slot"
        result["block_reasons"] = ["missing_decision_slot"]
        return result, None
    if current_snapshot is None:
        result["status"] = "blocked_missing_current_supply_snapshot"
        result["block_reasons"] = ["missing_current_supply_snapshot"]
        return result, None
    if complete_through < decision_slot:
        return result, None

    post_decision_events = [event for event in events if safe_int(event.get("slot"), 0) > decision_slot]
    result["post_decision_supply_event_count"] = len(post_decision_events)
    if post_decision_events:
        result["status"] = "blocked_supply_changed_after_decision"
        result["block_reasons"] = ["mint_or_burn_after_decision_slot"]
        result["post_decision_event_signatures"] = [
            str(event.get("transaction_signature") or "") for event in post_decision_events[:10]
        ]
        return result, None

    current_snapshot_slot = safe_int(current_snapshot.get("slot"), 0)
    if current_snapshot_slot <= 0:
        result["status"] = "blocked_invalid_current_supply_snapshot"
        result["block_reasons"] = ["missing_current_supply_snapshot_slot"]
        return result, None
    if current_snapshot_slot > decision_slot and post_decision_complete_through < current_snapshot_slot:
        result["status"] = "blocked_incomplete_post_decision_history"
        result["block_reasons"] = ["post_decision_mint_history_not_proven"]
        return result, None

    raw_supply, decimals, ui_supply = snapshot_supply(current_snapshot)
    if raw_supply is None or decimals is None or ui_supply is None:
        result["status"] = "blocked_invalid_current_supply_snapshot"
        result["block_reasons"] = ["invalid_current_supply_snapshot"]
        return result, None

    result["status"] = "stable_current_supply_proven"
    result["block_reasons"] = []
    snapshot = {
        "version": VERSION,
        "token_mint": token,
        "slot": decision_slot,
        "requested_snapshot_slot": decision_slot,
        "max_acceptable_snapshot_slot": decision_slot,
        "current_snapshot_slot": current_snapshot_slot,
        "raw_supply": raw_supply,
        "ui_supply": ui_supply,
        "decimals": int(decimals),
        "source": "current_supply_stability_proof",
        "source_file": current_snapshot.get("source_file"),
        "current_supply_source": current_snapshot.get("source"),
        "history_source": completeness.get("source"),
        "decision_time_safe": True,
        "stability_window_start_slot": decision_slot,
        "stability_window_end_slot": current_snapshot_slot,
        "post_decision_complete_through_slot": post_decision_complete_through,
        "post_decision_supply_event_count": 0,
        "can_mutate_wallet_trust": False,
    }
    return result, snapshot


def build_summary(requirements: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in requirements)
    blocks = Counter(reason for row in requirements for reason in row.get("block_reasons") or [])
    return {
        "requirements_scanned": len(requirements),
        "snapshots_reconstructed": len(snapshots),
        "stable_current_supply_proven": statuses.get("stable_current_supply_proven", 0),
        "blocked_incomplete_post_decision_history": statuses.get("blocked_incomplete_post_decision_history", 0),
        "blocked_missing_current_supply_snapshot": statuses.get("blocked_missing_current_supply_snapshot", 0),
        "blocked_supply_changed_after_decision": statuses.get("blocked_supply_changed_after_decision", 0),
        "tokens_affected": len({row.get("token_mint") for row in requirements if row.get("token_mint")}),
        "tokens_recovered": len({row.get("token_mint") for row in snapshots if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
    }


def build_supply_stability_evidence_report(
    *,
    archival_supply_plan: dict[str, Any],
    current_supply_snapshots: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    history_completeness: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    current_by_token = index_current_snapshots(current_supply_snapshots)
    events_by_token = grouped_events(raw_transactions)
    history_completeness = history_completeness or {}
    requirement_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for requirement in ready_requirements(archival_supply_plan):
        token = token_mint(requirement)
        row, snapshot = build_requirement_result(
            requirement=requirement,
            current_snapshot=current_snapshot_for(current_by_token, token),
            events=events_by_token.get(token, []),
            completeness=completeness_for(history_completeness, token),
        )
        requirement_rows.append(row)
        if snapshot:
            snapshots.append(snapshot)

    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(requirement_rows, snapshots),
        "requirements": requirement_rows,
        "snapshots": snapshots,
        "operator_note": (
            "This lane uses current supply only when mint-account history covers the decision slot, "
            "post-decision history is explicitly proven through the current snapshot slot, and no mint/burn "
            "events occurred after the decision slot. It remains review-only."
        ),
    }
