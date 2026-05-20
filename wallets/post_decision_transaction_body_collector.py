from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.archival_mint_history_collector import (
    build_signature_checkpoint,
    fetch_signature_page,
    fetch_transaction,
    normalize_signature_rows,
    rpc_failures,
)
from wallets.archival_mint_supply_reconstruction import token_mint, tx_slot
from wallets.post_decision_supply_coverage import checkpoint_for, checkpoint_signatures, raw_signatures
from wallets.supply_stability_evidence import current_snapshot_for, index_current_snapshots
from wallets.wallet_evidence_models import safe_int


MODE = "POST_DECISION_SUPPLY_TRANSACTION_COLLECTION_REVIEW_ONLY"
VERSION = "post_decision_supply_transaction_collection.v1"
TRANSACTION_BATCH_SIZE = 10


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in rows or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def checkpoint_target(mint: str, signatures: list[dict[str, Any]], *, refreshed_at: float | None = None) -> dict[str, Any]:
    slots = [safe_int(row.get("slot"), 0) for row in signatures if safe_int(row.get("slot"), 0) > 0]
    target = {
        "token_mint": mint,
        "pagination_complete": False,
        "oldest_signature_slot": min(slots) if slots else None,
        "newest_signature_slot": max(slots) if slots else None,
    }
    checkpoint = build_signature_checkpoint(target, signatures)
    if refreshed_at:
        checkpoint["checkpoint_collected_at"] = float(refreshed_at)
    return checkpoint


def refresh_checkpoint_from_head(
    *,
    rpc: Any,
    mint: str,
    existing_signatures: list[dict[str, Any]],
    decision_slot: int,
    current_slot: int,
    signature_page_limit: int,
    max_pages_per_mint: int,
    generated_at: float,
) -> tuple[list[dict[str, Any]], bool, list[str], dict[str, Any]]:
    existing_signature_ids = {str(row.get("signature") or "") for row in existing_signatures if row.get("signature")}
    fetched: list[dict[str, Any]] = []
    before: str | None = None
    overlap_found = False
    page_limit_reached = False

    for _page in range(max(0, int(max_pages_per_mint))):
        page = fetch_signature_page(rpc, mint, limit=signature_page_limit, before=before)
        page = normalize_signature_rows(page)
        if not page:
            break
        fetched = normalize_signature_rows(fetched + page)
        if any(str(row.get("signature") or "") in existing_signature_ids for row in page):
            overlap_found = True
            break
        oldest_page_slot = min(safe_int(row.get("slot"), 0) for row in page if safe_int(row.get("slot"), 0) > 0)
        if oldest_page_slot <= decision_slot:
            overlap_found = True
            break
        before = str(page[-1].get("signature") or "") or None
        if len(page) < int(signature_page_limit) or not before:
            break
    else:
        page_limit_reached = True

    merged = normalize_signature_rows(existing_signatures + fetched)
    block_reasons: list[str] = []
    if not overlap_found:
        block_reasons.append("head_refresh_did_not_overlap_existing_checkpoint")
    if page_limit_reached:
        block_reasons.append("signature_page_limit_reached")
    if current_slot <= 0:
        block_reasons.append("missing_current_snapshot_slot")
    trusted = overlap_found and current_slot > 0
    checkpoint = checkpoint_target(mint, merged, refreshed_at=generated_at if trusted else None)
    return merged, trusted, block_reasons, checkpoint


def build_post_decision_signatures(signatures: list[dict[str, Any]], *, decision_slot: int, current_slot: int) -> list[dict[str, Any]]:
    return [
        row
        for row in signatures
        if decision_slot < safe_int(row.get("slot"), 0) <= current_slot and str(row.get("signature") or "")
    ]


def checkpoint_spans_current_snapshot(signatures: list[dict[str, Any]], *, decision_slot: int, current_slot: int) -> bool:
    if decision_slot <= 0 or current_slot <= 0:
        return False
    slots = [safe_int(row.get("slot"), 0) for row in signatures if safe_int(row.get("slot"), 0) > 0]
    if not slots:
        return False
    return min(slots) <= decision_slot and max(slots) >= current_slot


def fetch_missing_transactions(
    *,
    rpc: Any,
    mint: str,
    missing_signatures: list[dict[str, Any]],
    max_transactions_per_mint: int,
) -> tuple[list[dict[str, Any]], int]:
    budget = max(0, int(max_transactions_per_mint))
    targets = missing_signatures[:budget]
    fetched_rows: list[dict[str, Any]] = []
    missing_fetches = 0
    tx_options = {
        "encoding": "jsonParsed",
        "maxSupportedTransactionVersion": 0,
        "commitment": "confirmed",
    }
    batch_call = getattr(rpc, "batch_call", None)
    if callable(batch_call):
        for start in range(0, len(targets), TRANSACTION_BATCH_SIZE):
            chunk = targets[start : start + TRANSACTION_BATCH_SIZE]
            calls = [
                ("getTransaction", [str(item.get("signature") or ""), tx_options])
                for item in chunk
            ]
            results = batch_call(calls)
            if not isinstance(results, list) or len(results) != len(chunk):
                results = [None for _item in chunk]
            for item, tx in zip(chunk, results):
                signature = str(item.get("signature") or "")
                slot = safe_int(item.get("slot"), 0)
                if not isinstance(tx, dict):
                    missing_fetches += 1
                    continue
                fetched_rows.append({
                    "version": VERSION,
                    "source": "post_decision_supply_transaction_collection",
                    "token_mint": mint,
                    "signature": signature,
                    "slot": tx_slot(tx) or slot,
                    "transaction": tx,
                    "can_mutate_wallet_trust": False,
                })
        return fetched_rows, missing_fetches

    for item in targets:
        signature = str(item.get("signature") or "")
        slot = safe_int(item.get("slot"), 0)
        tx = fetch_transaction(rpc, signature)
        if not isinstance(tx, dict):
            missing_fetches += 1
            continue
        fetched_rows.append({
            "version": VERSION,
            "source": "post_decision_supply_transaction_collection",
            "token_mint": mint,
            "signature": signature,
            "slot": tx_slot(tx) or slot,
            "transaction": tx,
            "can_mutate_wallet_trust": False,
        })
    return fetched_rows, missing_fetches


def estimate_missing_post_decision_transactions(
    *,
    requirement: dict[str, Any],
    current_snapshot: dict[str, Any] | None,
    signature_checkpoint: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
) -> int:
    mint = token_mint(requirement)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    current_slot = safe_int((current_snapshot or {}).get("slot"), 0)
    if decision_slot <= 0 or current_slot <= 0:
        return 1_000_000_000
    signatures = checkpoint_signatures(checkpoint_for(signature_checkpoint, mint))
    if not signatures:
        return 1_000_000_000
    raw_seen = raw_signatures(raw_transactions)
    post_decision = build_post_decision_signatures(signatures, decision_slot=decision_slot, current_slot=current_slot)
    return len([row for row in post_decision if str(row.get("signature") or "") not in raw_seen])


def build_target_result(
    *,
    requirement: dict[str, Any],
    current_snapshot: dict[str, Any] | None,
    checkpoint: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
    rpc: Any | None,
    execute: bool,
    signature_page_limit: int,
    max_pages_per_mint: int,
    max_transactions_per_mint: int,
    generated_at: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    mint = token_mint(requirement)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    current_slot = safe_int((current_snapshot or {}).get("slot"), 0)
    signatures = checkpoint_signatures(checkpoint)
    existing_raw = raw_signatures(raw_transactions)
    row = {
        "version": VERSION,
        "token_mint": mint,
        "decision_slot": decision_slot or None,
        "current_snapshot_slot": current_slot or None,
        "status": "pending_post_decision_transaction_collection",
        "checkpoint_refreshed": False,
        "post_decision_signature_count": 0,
        "missing_post_decision_transactions_before": 0,
        "missing_post_decision_transactions_after": 0,
        "raw_transactions_preserved": 0,
        "block_reasons": [],
        "can_mutate_wallet_trust": False,
    }
    if decision_slot <= 0:
        row["status"] = "blocked_missing_decision_slot"
        row["block_reasons"] = ["missing_decision_slot"]
        return row, [], checkpoint
    if current_snapshot is None or current_slot <= 0:
        row["status"] = "blocked_missing_current_supply_snapshot"
        row["block_reasons"] = ["missing_current_supply_snapshot"]
        return row, [], checkpoint
    if not signatures:
        row["status"] = "blocked_missing_signature_checkpoint"
        row["block_reasons"] = ["missing_signature_checkpoint"]
        return row, [], checkpoint
    if not execute:
        return row, [], checkpoint
    if rpc is None:
        row["status"] = "blocked_rpc_unconfigured"
        row["block_reasons"] = ["missing_rpc_client"]
        return row, [], checkpoint

    if checkpoint_spans_current_snapshot(signatures, decision_slot=decision_slot, current_slot=current_slot):
        updated_checkpoint = checkpoint_target(mint, signatures, refreshed_at=generated_at)
        row["checkpoint_covered_current_snapshot"] = True
    else:
        signatures, refreshed, refresh_blocks, updated_checkpoint = refresh_checkpoint_from_head(
            rpc=rpc,
            mint=mint,
            existing_signatures=signatures,
            decision_slot=decision_slot,
            current_slot=current_slot,
            signature_page_limit=signature_page_limit,
            max_pages_per_mint=max_pages_per_mint,
            generated_at=generated_at,
        )
        row["checkpoint_refreshed"] = refreshed
        row["signature_count"] = len(signatures)
        if not refreshed:
            row["status"] = "blocked_incomplete_head_refresh"
            row["block_reasons"] = refresh_blocks or ["head_refresh_incomplete"]
            row["rpc_failures"] = rpc_failures(rpc)
            return row, [], updated_checkpoint
    row["signature_count"] = len(signatures)
    if not signatures or min(safe_int(item.get("slot"), 0) for item in signatures) > decision_slot:
        row["status"] = "needs_more_signature_pagination"
        row["block_reasons"] = ["checkpoint_does_not_reach_decision_slot"]
        row["rpc_failures"] = rpc_failures(rpc)
        return row, [], updated_checkpoint

    post_decision = build_post_decision_signatures(signatures, decision_slot=decision_slot, current_slot=current_slot)
    missing = [
        item for item in post_decision if str(item.get("signature") or "").strip() not in existing_raw
    ]
    row["post_decision_signature_count"] = len(post_decision)
    row["missing_post_decision_transactions_before"] = len(missing)
    if len(missing) > max(0, int(max_transactions_per_mint)):
        row["status"] = "partial_post_decision_transaction_bodies_collected"
        row["block_reasons"] = ["transaction_budget_exhausted"]
        row["transaction_budget"] = max(0, int(max_transactions_per_mint))
    fetched_rows, missing_fetches = fetch_missing_transactions(
        rpc=rpc,
        mint=mint,
        missing_signatures=missing,
        max_transactions_per_mint=max_transactions_per_mint,
    )
    fetched_signatures = {row["signature"] for row in fetched_rows}
    row["raw_transactions_preserved"] = len(fetched_rows)
    row["missing_transaction_fetches"] = missing_fetches
    row["missing_post_decision_transactions_after"] = len([
        item for item in missing if str(item.get("signature") or "") not in fetched_signatures
    ])
    if missing_fetches and row["status"] == "pending_post_decision_transaction_collection":
        row["status"] = "partial_post_decision_transaction_bodies_collected"
        row["block_reasons"] = ["missing_transaction_bodies"]
    elif row["missing_post_decision_transactions_after"] == 0:
        row["status"] = "post_decision_transaction_bodies_collected"
        row["block_reasons"] = []
    elif row["status"] == "pending_post_decision_transaction_collection":
        row["status"] = "partial_post_decision_transaction_bodies_collected"
        row["block_reasons"] = ["post_decision_transaction_bodies_remaining"]
    row["rpc_failures"] = rpc_failures(rpc)
    return row, fetched_rows, updated_checkpoint


def build_summary(targets: list[dict[str, Any]], raw_transactions: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in targets)
    blocks = Counter(reason for row in targets for reason in row.get("block_reasons") or [])
    return {
        "requirements_scanned": len(targets),
        "targets_refreshed": sum(1 for row in targets if row.get("checkpoint_refreshed")),
        "bodies_collection_complete": statuses.get("post_decision_transaction_bodies_collected", 0),
        "partial_bodies_collected": statuses.get("partial_post_decision_transaction_bodies_collected", 0),
        "blocked_incomplete_refresh": statuses.get("blocked_incomplete_head_refresh", 0),
        "raw_transactions_preserved": len(raw_transactions),
        "tokens_affected": len({row.get("token_mint") for row in targets if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
    }


def build_post_decision_supply_transaction_collection_report(
    *,
    archival_supply_plan: dict[str, Any],
    current_supply_snapshots: list[dict[str, Any]],
    signature_checkpoint: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
    rpc: Any | None = None,
    execute: bool = False,
    signature_page_limit: int = 100,
    max_pages_per_mint: int = 2,
    max_transactions_per_mint: int = 500,
    max_targets: int | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report_generated_at = time.time() if generated_at is None else float(generated_at)
    current_by_token = index_current_snapshots(current_supply_snapshots)
    target_limit = max(0, int(max_targets)) if max_targets is not None else None
    requirements = ready_requirements(archival_supply_plan)
    requirements = sorted(
        requirements,
        key=lambda row: (
            estimate_missing_post_decision_transactions(
                requirement=row,
                current_snapshot=current_snapshot_for(current_by_token, token_mint(row)),
                signature_checkpoint=signature_checkpoint,
                raw_transactions=raw_transactions,
            ),
            str(token_mint(row)),
        ),
    )
    limited_requirements = requirements[:target_limit] if target_limit is not None else requirements
    updated_checkpoint = dict(signature_checkpoint or {}) if isinstance(signature_checkpoint, dict) else {}
    targets: list[dict[str, Any]] = []
    fetched_rows: list[dict[str, Any]] = []
    for requirement in limited_requirements:
        mint = token_mint(requirement)
        row, raw_rows, checkpoint_row = build_target_result(
            requirement=requirement,
            current_snapshot=current_snapshot_for(current_by_token, mint),
            checkpoint=checkpoint_for(updated_checkpoint, mint),
            raw_transactions=raw_transactions + fetched_rows,
            rpc=rpc,
            execute=execute,
            signature_page_limit=signature_page_limit,
            max_pages_per_mint=max_pages_per_mint,
            max_transactions_per_mint=max_transactions_per_mint,
            generated_at=report_generated_at,
        )
        targets.append(row)
        fetched_rows.extend(raw_rows)
        if checkpoint_row:
            updated_checkpoint[mint] = checkpoint_row

    return {
        "generated_at": report_generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "execute_requested": bool(execute),
        "target_limit": target_limit,
        "summary": build_summary(targets, fetched_rows),
        "targets": targets,
        "signature_checkpoint": updated_checkpoint,
        "raw_transactions": fetched_rows,
        "operator_note": (
            "This collector only refreshes mint-account signatures and preserves missing post-decision transaction bodies. "
            "It does not mark supply stable; the separate post-decision coverage report must validate completeness and no mint/burn events."
        ),
    }
