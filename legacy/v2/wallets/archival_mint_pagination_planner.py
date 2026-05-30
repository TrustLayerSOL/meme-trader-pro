from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any

from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_MINT_PAGINATION_PLAN_REVIEW_ONLY"
VERSION = "archival_mint_pagination_plan.v1"


def progress_rows(progress_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = progress_report.get("rows") if isinstance(progress_report, dict) else []
    return [row for row in rows or [] if isinstance(row, dict)]


def slot_span_per_page(row: dict[str, Any], page_size: int) -> float | None:
    signature_count = safe_int(row.get("signature_count"), 0)
    newest_slot = safe_int(row.get("newest_signature_slot"), 0)
    oldest_slot = safe_int(row.get("oldest_signature_slot"), 0)
    if signature_count <= 0 or newest_slot <= oldest_slot:
        return None
    pages_seen = max(1, math.ceil(signature_count / max(1, int(page_size))))
    return (newest_slot - oldest_slot) / pages_seen


def estimate_pages_to_decision(row: dict[str, Any], page_size: int) -> int | None:
    decision_slot = safe_int(row.get("decision_slot"), 0)
    oldest_slot = safe_int(row.get("oldest_signature_slot"), 0)
    if decision_slot <= 0 or oldest_slot <= 0 or oldest_slot <= decision_slot:
        return 0
    slots_per_page = slot_span_per_page(row, page_size)
    if not slots_per_page or slots_per_page <= 0:
        return None
    return max(1, math.ceil((oldest_slot - decision_slot) / slots_per_page))


def build_plan_row(
    row: dict[str, Any],
    *,
    page_size: int,
    pages_per_batch: int,
    provider_threshold_signatures: int,
) -> dict[str, Any]:
    token = str(row.get("token_mint") or "").strip()
    signature_count = safe_int(row.get("signature_count"), 0)
    decision_slot = safe_int(row.get("decision_slot"), 0)
    reached_decision_slot = bool(row.get("reached_decision_slot"))
    pagination_complete = bool(row.get("pagination_complete"))
    estimated_pages = estimate_pages_to_decision(row, page_size)

    recommended_action = "RUN_INITIAL_BOUNDED_PAGINATION"
    reason = "no_signature_checkpoint"
    priority = 20

    if decision_slot <= 0:
        recommended_action = "REBUILD_ARCHIVAL_SUPPLY_PLAN_WITH_DECISION_SLOT"
        reason = "missing_decision_slot"
        priority = 90
    elif pagination_complete:
        recommended_action = "RUN_SUPPLY_RECONSTRUCTION"
        reason = "signature_history_complete"
        priority = 100
    elif signature_count <= 0:
        recommended_action = "RUN_INITIAL_BOUNDED_PAGINATION"
        reason = "no_signature_checkpoint"
        priority = 70
    elif reached_decision_slot and signature_count >= provider_threshold_signatures:
        recommended_action = "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"
        reason = "decision_slot_reached_but_account_history_still_incomplete_at_threshold"
        priority = 95
    elif reached_decision_slot:
        recommended_action = "CONTINUE_PAGINATION_TO_ACCOUNT_HISTORY_START"
        reason = "decision_slot_reached_history_start_not_proven"
        priority = 80
    else:
        recommended_action = "CONTINUE_PAGINATION_TOWARD_DECISION_SLOT"
        reason = "decision_slot_not_reached"
        priority = 60

    if recommended_action == "CONTINUE_PAGINATION_TOWARD_DECISION_SLOT" and estimated_pages is not None:
        priority = 85 if estimated_pages <= pages_per_batch else 65

    return {
        "version": VERSION,
        "token_mint": token,
        "decision_slot": decision_slot or None,
        "signature_count": signature_count,
        "oldest_signature_slot": row.get("oldest_signature_slot"),
        "newest_signature_slot": row.get("newest_signature_slot"),
        "pagination_complete": pagination_complete,
        "reached_decision_slot": reached_decision_slot,
        "estimated_pages_to_decision_slot": estimated_pages,
        "recommended_batch_pages": int(pages_per_batch),
        "recommended_page_size": int(page_size),
        "recommended_action": recommended_action,
        "reason": reason,
        "priority": priority,
        "can_mutate_wallet_trust": False,
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter(str(row.get("recommended_action") or "unknown") for row in rows)
    return {
        "tokens_planned": len(rows),
        "initial_pagination_tokens": actions.get("RUN_INITIAL_BOUNDED_PAGINATION", 0),
        "continue_pagination_tokens": (
            actions.get("CONTINUE_PAGINATION_TOWARD_DECISION_SLOT", 0)
            + actions.get("CONTINUE_PAGINATION_TO_ACCOUNT_HISTORY_START", 0)
        ),
        "provider_recommended_tokens": actions.get("CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER", 0),
        "complete_history_tokens": actions.get("RUN_SUPPLY_RECONSTRUCTION", 0),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "action_counts": dict(sorted(actions.items())),
    }


def build_archival_mint_pagination_plan_report(
    *,
    progress_report: dict[str, Any],
    page_size: int = 100,
    pages_per_batch: int = 10,
    provider_threshold_signatures: int = 2000,
    generated_at: float | None = None,
) -> dict[str, Any]:
    rows = [
        build_plan_row(
            row,
            page_size=page_size,
            pages_per_batch=pages_per_batch,
            provider_threshold_signatures=provider_threshold_signatures,
        )
        for row in progress_rows(progress_report)
    ]
    rows.sort(key=lambda item: (-safe_int(item.get("priority"), 0), str(item.get("token_mint") or "")))
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
        "page_size": int(page_size),
        "pages_per_batch": int(pages_per_batch),
        "provider_threshold_signatures": int(provider_threshold_signatures),
        "summary": build_summary(rows),
        "rows": rows,
        "operator_note": (
            "This planner is read-only. It estimates pagination next steps from checkpoint depth; "
            "it does not fetch data, infer supply, mutate trust, or enable execution."
        ),
    }
