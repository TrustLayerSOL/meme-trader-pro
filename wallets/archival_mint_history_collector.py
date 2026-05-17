from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.archival_mint_supply_reconstruction import tx_slot
from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_MINT_HISTORY_COLLECTION_REVIEW_ONLY"
VERSION = "archival_mint_history_collection.v1"


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in requirements or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def rpc_failures(rpc: Any) -> list[dict[str, Any]]:
    failures = getattr(rpc, "failures", [])
    return failures if isinstance(failures, list) else []


def fetch_signature_page(rpc: Any, mint: str, *, limit: int, before: str | None = None) -> list[dict[str, Any]]:
    opts: dict[str, Any] = {"limit": int(limit)}
    if before:
        opts["before"] = before
    result = rpc.call("getSignaturesForAddress", [mint, opts])
    return [row for row in result or [] if isinstance(row, dict)] if isinstance(result, list) else []


def fetch_transaction(rpc: Any, signature: str) -> dict[str, Any] | None:
    result = rpc.call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed",
            },
        ],
    )
    return result if isinstance(result, dict) else None


def normalize_signature_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        signature = str(row.get("signature") or "").strip()
        if not signature or signature in seen:
            continue
        seen.add(signature)
        normalized.append({
            "signature": signature,
            "slot": safe_int(row.get("slot"), 0),
        })
    normalized.sort(key=lambda item: safe_int(item.get("slot"), 0), reverse=True)
    return normalized


def checkpoint_for(existing_checkpoint: dict[str, Any] | None, mint: str) -> dict[str, Any]:
    row = existing_checkpoint.get(mint) if isinstance(existing_checkpoint, dict) else {}
    return row if isinstance(row, dict) else {}


def checkpoint_signatures(row: dict[str, Any]) -> list[dict[str, Any]]:
    signatures = row.get("signatures") if isinstance(row, dict) else []
    return normalize_signature_rows(signatures if isinstance(signatures, list) else [])


def build_signature_checkpoint(target: dict[str, Any], signatures: list[dict[str, Any]]) -> dict[str, Any]:
    pagination_complete = bool(target.get("pagination_complete"))
    return {
        "version": VERSION,
        "token_mint": target.get("token_mint"),
        "pagination_complete": pagination_complete,
        "next_before": None if pagination_complete or not signatures else signatures[-1].get("signature"),
        "signatures": signatures,
        "signatures_fetched_total": len(signatures),
        "oldest_signature_slot": target.get("oldest_signature_slot"),
        "newest_signature_slot": target.get("newest_signature_slot"),
        "can_mutate_wallet_trust": False,
    }


def build_target(requirement: dict[str, Any]) -> dict[str, Any]:
    earliest = safe_int(requirement.get("earliest_decision_slot"), 0)
    latest = safe_int(requirement.get("latest_decision_slot"), 0)
    return {
        "version": VERSION,
        "token_mint": token_mint(requirement),
        "decision_slot": earliest or None,
        "latest_decision_slot": latest or None,
        "row_count": safe_int(requirement.get("row_count"), 0),
        "status": "pending_mint_history_collection",
        "signatures_fetched": 0,
        "transactions_preserved": 0,
        "oldest_signature_slot": None,
        "newest_signature_slot": None,
        "pagination_complete": False,
        "block_reasons": [],
        "can_mutate_wallet_trust": False,
    }


def collect_mint_history(
    *,
    target: dict[str, Any],
    rpc: Any,
    signature_page_limit: int,
    max_pages_per_mint: int,
    max_transactions_per_mint: int,
    existing_checkpoint: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    mint = str(target.get("token_mint") or "")
    decision_slot = safe_int(target.get("decision_slot"), 0)
    checkpoint = checkpoint_for(existing_checkpoint, mint)
    signatures = checkpoint_signatures(checkpoint)
    checkpoint_count = len(signatures)
    before = str(checkpoint.get("next_before") or "").strip() or None
    pagination_complete = bool(checkpoint.get("pagination_complete"))
    page_limit_reached = False

    if not pagination_complete:
        for _page in range(max(0, int(max_pages_per_mint))):
            page = fetch_signature_page(rpc, mint, limit=signature_page_limit, before=before)
            signatures = normalize_signature_rows(signatures + page)
            if len(page) < int(signature_page_limit):
                pagination_complete = True
                break
            if not page:
                pagination_complete = True
                break
            before = str(page[-1].get("signature") or "")
            if not before:
                break
        else:
            page_limit_reached = True

    slots = [safe_int(row.get("slot"), 0) for row in signatures if safe_int(row.get("slot"), 0) > 0]
    target["signatures_fetched"] = len(signatures)
    target["signatures_loaded_from_checkpoint"] = checkpoint_count
    target["signatures_fetched_this_run"] = max(0, len(signatures) - checkpoint_count)
    target["oldest_signature_slot"] = min(slots) if slots else None
    target["newest_signature_slot"] = max(slots) if slots else None
    target["pagination_complete"] = pagination_complete

    if not signatures:
        target["status"] = "blocked_no_mint_signatures"
        target["block_reasons"] = ["no_mint_signatures"]
        target["rpc_failures"] = rpc_failures(rpc)
        return target, [], None, build_signature_checkpoint(target, signatures)
    if not pagination_complete or page_limit_reached:
        target["status"] = "blocked_partial_mint_history"
        target["block_reasons"] = ["signature_page_limit_reached"]
        target["rpc_failures"] = rpc_failures(rpc)
        return target, [], None, build_signature_checkpoint(target, signatures)
    if decision_slot <= 0:
        target["status"] = "blocked_missing_decision_slot"
        target["block_reasons"] = ["missing_decision_slot"]
        return target, [], None, build_signature_checkpoint(target, signatures)

    transaction_budget = max(0, int(max_transactions_per_mint))
    eligible_signatures = [
        item
        for item in signatures
        if str(item.get("signature") or "") and 0 < safe_int(item.get("slot"), 0) <= decision_slot
    ]
    if len(eligible_signatures) > transaction_budget:
        target["status"] = "blocked_partial_mint_history"
        target["block_reasons"] = ["transaction_budget_exhausted"]
        target["eligible_signatures_before_decision"] = len(eligible_signatures)
        target["transaction_budget"] = transaction_budget
        target["rpc_failures"] = rpc_failures(rpc)
        return target, [], None, build_signature_checkpoint(target, signatures)

    raw_rows: list[dict[str, Any]] = []
    missing_transactions = 0
    for item in eligible_signatures:
        signature = str(item.get("signature") or "")
        slot = safe_int(item.get("slot"), 0)
        tx = fetch_transaction(rpc, signature)
        if not isinstance(tx, dict):
            missing_transactions += 1
            continue
        raw_slot = tx_slot(tx) or slot
        raw_rows.append({
            "version": VERSION,
            "source": "archival_mint_history_collection",
            "token_mint": mint,
            "signature": signature,
            "slot": raw_slot,
            "transaction": tx,
            "can_mutate_wallet_trust": False,
        })

    target["transactions_preserved"] = len(raw_rows)
    target["eligible_signatures_before_decision"] = len(eligible_signatures)
    if missing_transactions:
        target["status"] = "blocked_partial_mint_history"
        target["block_reasons"] = ["missing_mint_transactions"]
        target["missing_transactions"] = missing_transactions
        target["rpc_failures"] = rpc_failures(rpc)
        return target, raw_rows, None, build_signature_checkpoint(target, signatures)

    target["status"] = "mint_history_complete_through_decision_slot"
    completeness = {
        "source": "archival_mint_history_collection",
        "complete_through_slot": decision_slot,
        "signatures_fetched": len(signatures),
        "transactions_preserved": len(raw_rows),
        "oldest_signature_slot": target["oldest_signature_slot"],
        "newest_signature_slot": target["newest_signature_slot"],
    }
    return target, raw_rows, completeness, build_signature_checkpoint(target, signatures)


def build_summary(
    targets: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    *,
    requirements_available: int | None = None,
    target_limit: int | None = None,
) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in targets)
    blocks = Counter(reason for row in targets for reason in row.get("block_reasons") or [])
    return {
        "requirements_available": len(targets) if requirements_available is None else int(requirements_available),
        "requirements_scanned": len(targets),
        "target_limit": target_limit,
        "mint_history_targets": len(targets),
        "mint_histories_complete": statuses.get("mint_history_complete_through_decision_slot", 0),
        "blocked_incomplete_history": statuses.get("blocked_partial_mint_history", 0),
        "blocked_no_signatures": statuses.get("blocked_no_mint_signatures", 0),
        "raw_transactions_preserved": len(raw_transactions),
        "tokens_affected": len({row.get("token_mint") for row in targets if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
    }


def build_archival_mint_history_collection_report(
    *,
    archival_supply_plan: dict[str, Any],
    rpc: Any | None = None,
    execute: bool = False,
    signature_page_limit: int = 100,
    max_pages_per_mint: int = 5,
    max_transactions_per_mint: int = 500,
    max_targets: int | None = None,
    existing_signature_checkpoint: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    requirements = ready_requirements(archival_supply_plan)
    target_limit = max(0, int(max_targets)) if max_targets is not None else None
    limited_requirements = requirements[:target_limit] if target_limit is not None else requirements
    targets = [build_target(row) for row in limited_requirements]
    raw_transactions: list[dict[str, Any]] = []
    completeness: dict[str, Any] = {}
    signature_checkpoint: dict[str, Any] = dict(existing_signature_checkpoint or {}) if isinstance(existing_signature_checkpoint, dict) else {}

    if execute:
        for target in targets:
            if rpc is None:
                target["status"] = "blocked_rpc_unconfigured"
                target["block_reasons"] = ["missing_rpc_client"]
                continue
            updated, rows, complete, checkpoint_entry = collect_mint_history(
                target=target,
                rpc=rpc,
                signature_page_limit=signature_page_limit,
                max_pages_per_mint=max_pages_per_mint,
                max_transactions_per_mint=max_transactions_per_mint,
                existing_checkpoint=signature_checkpoint,
            )
            raw_transactions.extend(rows)
            signature_checkpoint[str(updated["token_mint"])] = checkpoint_entry
            if complete:
                completeness[str(updated["token_mint"])] = complete

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
        "execute_requested": bool(execute),
        "target_limit": target_limit,
        "summary": build_summary(
            targets,
            raw_transactions,
            requirements_available=len(requirements),
            target_limit=target_limit,
        ),
        "targets": targets,
        "history_completeness": completeness,
        "signature_checkpoint": signature_checkpoint,
        "raw_transactions": raw_transactions,
        "operator_note": (
            "This collector is read-only and only marks mint history complete when signature pagination reaches the end. "
            "Partial mint history remains blocked from supply reconstruction."
        ),
    }
