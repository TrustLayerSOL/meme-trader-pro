from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.archival_mint_history_collector import ready_requirements, token_mint
from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_MINT_HISTORY_PROGRESS_REVIEW_ONLY"
VERSION = "archival_mint_history_progress.v1"


def checkpoint_for(signature_checkpoint: dict[str, Any], mint: str) -> dict[str, Any]:
    row = signature_checkpoint.get(mint) if isinstance(signature_checkpoint, dict) else {}
    return row if isinstance(row, dict) else {}


def build_progress_row(requirement: dict[str, Any], signature_checkpoint: dict[str, Any]) -> dict[str, Any]:
    mint = token_mint(requirement)
    checkpoint = checkpoint_for(signature_checkpoint, mint)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    signature_count = safe_int(checkpoint.get("signatures_fetched_total"), 0)
    oldest_slot = safe_int(checkpoint.get("oldest_signature_slot"), 0)
    newest_slot = safe_int(checkpoint.get("newest_signature_slot"), 0)
    pagination_complete = bool(checkpoint.get("pagination_complete"))
    reached_decision_slot = bool(decision_slot > 0 and oldest_slot > 0 and oldest_slot <= decision_slot)

    status = "no_signature_checkpoint"
    next_action = "RUN_BOUNDED_MINT_HISTORY_COLLECTION"
    if decision_slot <= 0:
        status = "blocked_missing_decision_slot"
        next_action = "REBUILD_ARCHIVAL_SUPPLY_PLAN_WITH_DECISION_SLOT"
    elif pagination_complete:
        status = "signature_history_complete"
        next_action = "RUN_SUPPLY_RECONSTRUCTION"
    elif signature_count > 0 and reached_decision_slot:
        status = "checkpoint_reached_decision_slot_but_not_history_start"
        next_action = "CONTINUE_PAGINATION_TO_ACCOUNT_HISTORY_START"
    elif signature_count > 0:
        status = "checkpoint_before_decision_not_reached"
        next_action = "CONTINUE_PAGINATION_TOWARD_DECISION_SLOT"

    return {
        "version": VERSION,
        "token_mint": mint,
        "decision_slot": decision_slot or None,
        "row_count": safe_int(requirement.get("row_count"), 0),
        "signature_count": signature_count,
        "oldest_signature_slot": oldest_slot or None,
        "newest_signature_slot": newest_slot or None,
        "pagination_complete": pagination_complete,
        "reached_decision_slot": reached_decision_slot,
        "status": status,
        "next_action": next_action,
        "can_mutate_wallet_trust": False,
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    return {
        "requirements_scanned": len(rows),
        "checkpointed_tokens": sum(1 for row in rows if safe_int(row.get("signature_count"), 0) > 0),
        "tokens_with_complete_history": statuses.get("signature_history_complete", 0),
        "tokens_reached_decision_slot": sum(1 for row in rows if row.get("reached_decision_slot")),
        "tokens_missing_checkpoint": statuses.get("no_signature_checkpoint", 0),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
    }


def build_archival_mint_history_progress_report(
    *,
    archival_supply_plan: dict[str, Any],
    signature_checkpoint: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    signature_checkpoint = signature_checkpoint if isinstance(signature_checkpoint, dict) else {}
    rows = [build_progress_row(row, signature_checkpoint) for row in ready_requirements(archival_supply_plan)]
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(rows),
        "rows": rows,
        "operator_note": (
            "This report summarizes mint-history checkpoint depth only. "
            "It cannot unlock supply reconstruction unless pagination is complete."
        ),
    }
