from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.archival_mint_supply_reconstruction import grouped_events, token_mint
from wallets.supply_stability_evidence import current_snapshot_for, index_current_snapshots
from wallets.wallet_evidence_models import safe_int


MODE = "POST_DECISION_SUPPLY_COVERAGE_REVIEW_ONLY"
VERSION = "post_decision_supply_coverage.v1"


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in rows or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def checkpoint_for(signature_checkpoint: dict[str, Any], token: str) -> dict[str, Any]:
    row = signature_checkpoint.get(token) if isinstance(signature_checkpoint, dict) else {}
    return row if isinstance(row, dict) else {}


def checkpoint_collected_at(row: dict[str, Any]) -> float:
    for key in ("checkpoint_collected_at", "collected_at", "generated_at", "updated_at"):
        try:
            value = float(row.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def checkpoint_signatures(row: dict[str, Any]) -> list[dict[str, Any]]:
    signatures = row.get("signatures") if isinstance(row, dict) else []
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in signatures or []:
        if not isinstance(item, dict):
            continue
        signature = str(item.get("signature") or "").strip()
        slot = safe_int(item.get("slot"), 0)
        if not signature or signature in seen or slot <= 0:
            continue
        seen.add(signature)
        cleaned.append({"signature": signature, "slot": slot})
    cleaned.sort(key=lambda item: safe_int(item.get("slot"), 0), reverse=True)
    return cleaned


def raw_signatures(raw_transactions: list[dict[str, Any]]) -> set[str]:
    signatures: set[str] = set()
    for row in raw_transactions or []:
        if not isinstance(row, dict):
            continue
        signature = str(row.get("signature") or "").strip()
        if signature:
            signatures.add(signature)
    return signatures


def build_requirement_result(
    *,
    requirement: dict[str, Any],
    current_snapshot: dict[str, Any] | None,
    checkpoint: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    token = token_mint(requirement)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    checkpoint_time = checkpoint_collected_at(checkpoint)
    signatures = checkpoint_signatures(checkpoint)
    signature_slots = [safe_int(row.get("slot"), 0) for row in signatures]
    current_slot = safe_int((current_snapshot or {}).get("slot"), 0)
    current_collected_at = float((current_snapshot or {}).get("collected_at") or 0)
    raw_seen = raw_signatures(raw_transactions)
    post_decision_signatures = [
        row for row in signatures if decision_slot < safe_int(row.get("slot"), 0) <= current_slot
    ]
    missing_post_signatures = [
        row for row in post_decision_signatures if str(row.get("signature") or "").strip() not in raw_seen
    ]
    row = {
        "version": VERSION,
        "token_mint": token,
        "decision_slot": decision_slot or None,
        "current_snapshot_slot": current_slot or None,
        "current_snapshot_collected_at": current_collected_at or None,
        "checkpoint_collected_at": checkpoint_time or None,
        "signature_count": len(signatures),
        "post_decision_signature_count": len(post_decision_signatures),
        "missing_post_decision_transaction_count": len(missing_post_signatures),
        "post_decision_supply_event_count": 0,
        "status": "blocked_missing_checkpoint",
        "block_reasons": ["missing_signature_checkpoint"],
        "can_mutate_wallet_trust": False,
    }
    if decision_slot <= 0:
        row["status"] = "blocked_missing_decision_slot"
        row["block_reasons"] = ["missing_decision_slot"]
        return row, None
    if current_snapshot is None or current_slot <= 0:
        row["status"] = "blocked_missing_current_supply_snapshot"
        row["block_reasons"] = ["missing_current_supply_snapshot"]
        return row, None
    if not signatures:
        return row, None
    if checkpoint_time <= 0:
        row["status"] = "blocked_missing_checkpoint_collection_time"
        row["block_reasons"] = ["missing_checkpoint_collection_time"]
        return row, None
    if current_collected_at > 0 and checkpoint_time < current_collected_at:
        row["status"] = "blocked_checkpoint_before_current_snapshot"
        row["block_reasons"] = ["checkpoint_collected_before_current_snapshot"]
        return row, None
    if not signature_slots or min(signature_slots) > decision_slot:
        row["status"] = "needs_more_signature_pagination"
        row["block_reasons"] = ["checkpoint_does_not_reach_decision_slot"]
        return row, None
    if missing_post_signatures:
        row["status"] = "needs_post_decision_transaction_bodies"
        row["block_reasons"] = ["missing_post_decision_transaction_bodies"]
        row["missing_post_decision_signatures"] = [
            str(item.get("signature") or "") for item in missing_post_signatures[:25]
        ]
        return row, None

    post_events = [
        event for event in events if decision_slot < safe_int(event.get("slot"), 0) <= current_slot
    ]
    row["post_decision_supply_event_count"] = len(post_events)
    if post_events:
        row["status"] = "blocked_supply_changed_after_decision"
        row["block_reasons"] = ["mint_or_burn_after_decision_slot"]
        row["post_decision_event_signatures"] = [
            str(event.get("transaction_signature") or "") for event in post_events[:10]
        ]
        return row, None

    row["status"] = "post_decision_supply_stable"
    row["block_reasons"] = []
    update = {
        "source": "post_decision_supply_coverage",
        "version": VERSION,
        "post_decision_complete_through_slot": current_slot,
        "post_decision_signature_count": len(post_decision_signatures),
        "post_decision_raw_transactions_checked": len(post_decision_signatures),
        "post_decision_supply_event_count": 0,
        "checkpoint_collected_at": checkpoint_time,
        "current_snapshot_collected_at": current_collected_at or None,
        "can_mutate_wallet_trust": False,
    }
    return row, update


def build_summary(rows: list[dict[str, Any]], updates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    blocks = Counter(reason for row in rows for reason in row.get("block_reasons") or [])
    return {
        "requirements_scanned": len(rows),
        "stable_tokens": len(updates),
        "needs_post_decision_transaction_bodies": statuses.get("needs_post_decision_transaction_bodies", 0),
        "needs_more_signature_pagination": statuses.get("needs_more_signature_pagination", 0),
        "blocked_supply_changed_after_decision": statuses.get("blocked_supply_changed_after_decision", 0),
        "tokens_affected": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
    }


def build_post_decision_supply_coverage_report(
    *,
    archival_supply_plan: dict[str, Any],
    current_supply_snapshots: list[dict[str, Any]],
    signature_checkpoint: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    current_by_token = index_current_snapshots(current_supply_snapshots)
    events_by_token = grouped_events(raw_transactions)
    rows: list[dict[str, Any]] = []
    updates: dict[str, dict[str, Any]] = {}
    for requirement in ready_requirements(archival_supply_plan):
        token = token_mint(requirement)
        row, update = build_requirement_result(
            requirement=requirement,
            current_snapshot=current_snapshot_for(current_by_token, token),
            checkpoint=checkpoint_for(signature_checkpoint, token),
            raw_transactions=raw_transactions,
            events=events_by_token.get(token, []),
        )
        rows.append(row)
        if update:
            updates[token] = update

    return {
        "mode": MODE,
        "version": VERSION,
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(rows, updates),
        "rows": rows,
        "history_completeness_updates": updates,
        "operator_note": (
            "This report only proves current supply can be treated as stable after the decision slot when "
            "signature checkpoints were collected after the current supply snapshot, reached the decision slot, "
            "all post-decision transaction bodies are present, and no post-decision mint/burn events exist."
        ),
    }
