from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.candidate_walk_forward_validation import entry_context
from wallets.candidate_walk_forward_validation import event_id
from wallets.candidate_walk_forward_validation import has_valid_entry_context
from wallets.candidate_walk_forward_validation import is_clean_proof_row
from wallets.candidate_walk_forward_validation import merge_repaired_records
from wallets.candidate_walk_forward_validation import outcome_15m
from wallets.candidate_walk_forward_validation import rate
from wallets.candidate_walk_forward_validation import safe_float
from wallets.candidate_walk_forward_validation import sorted_rows
from wallets.candidate_walk_forward_validation import wallet_address


MODE = "CANDIDATE_CONTEXT_QUALITY_LIFT_REVIEW_ONLY"
VERSION = "candidate_context_quality_lift.v1"
TARGET_FAILED_GATES = {"max_excluded_rate_exceeded", "min_context_completion_rate_not_met"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("block_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason)]
    if isinstance(reasons, str) and reasons:
        return [reasons]
    status = str(row.get("status") or "")
    return [status] if status.startswith("blocked_") else []


def target_wallets(readiness_gate: dict[str, Any]) -> list[dict[str, Any]]:
    wallets = []
    for row in as_list(readiness_gate.get("wallets")):
        if not isinstance(row, dict):
            continue
        failed = set(str(gate) for gate in as_list(row.get("failed_gates")))
        if row.get("paper_readiness_status") == "not_ready" and failed.intersection(TARGET_FAILED_GATES):
            wallets.append(row)
    return wallets


def has_quote_anchor(row: dict[str, Any]) -> bool:
    ctx = entry_context(row)
    return any(
        ctx.get(key) not in (None, "")
        for key in ("execution_price_quote", "quote_amount_delta", "snapshot_time")
    )


def is_open_blocker(row: dict[str, Any]) -> bool:
    return not is_clean_proof_row(row)


def blocker_reason(row: dict[str, Any]) -> str:
    reasons = block_reasons(row)
    if reasons:
        return reasons[0]
    if outcome_15m(row) == "unknown":
        return "missing_outcome_label"
    if not has_valid_entry_context(row):
        return "missing_forward_entry_context"
    return "manual_review_required"


def recommended_action(reason_counts: Counter[str], open_rows: list[dict[str, Any]]) -> str:
    if not open_rows:
        return "collect_more_clean_candidate_rows"
    missing_snapshot = sum(count for reason, count in reason_counts.items() if "snapshot" in reason)
    missing_quote = sum(
        count
        for reason, count in reason_counts.items()
        if "quote" in reason or "timestamp" in reason or "entry_price" in reason or "entry_context" in reason
    )
    missing_outcome = sum(count for reason, count in reason_counts.items() if "outcome" in reason)
    if missing_snapshot >= missing_quote and missing_snapshot > 0:
        return "repair_market_snapshot"
    if missing_quote > 0:
        return "repair_entry_timestamp"
    if missing_outcome > 0:
        return "repair_outcome_label"
    if any(not row.get("token_mint") for row in open_rows):
        return "repair_token_metadata"
    return "manual_review_required"


def next_operator_step(action: str) -> str:
    return {
        "repair_market_snapshot": "capture later market snapshots for blocked token mints, then rerun entry-context resolution",
        "repair_entry_timestamp": "recover execution quote anchors or transaction timestamps, then rerun entry-context resolution",
        "repair_token_metadata": "repair token metadata before using rows in validation",
        "repair_outcome_label": "rerun outcome resolution after entry context is valid",
        "collect_more_clean_candidate_rows": "continue bounded forward collection for this candidate wallet",
        "manual_review_required": "inspect blocked rows manually before choosing repair route",
    }.get(action, "manual review required")


def priority_for_action(action: str) -> int:
    return {
        "repair_market_snapshot": 0,
        "repair_entry_timestamp": 1,
        "repair_outcome_label": 2,
        "repair_token_metadata": 3,
        "manual_review_required": 4,
        "collect_more_clean_candidate_rows": 5,
    }.get(action, 9)


def blocker_event(row: dict[str, Any]) -> dict[str, Any]:
    ctx = entry_context(row)
    return {
        "event_id": event_id(row),
        "wallet_address": wallet_address(row),
        "token_address": row.get("token_mint"),
        "token_symbol": row.get("token_symbol"),
        "observed_at": row.get("signal_time") or row.get("observed_at"),
        "action": row.get("observed_action") or row.get("action"),
        "blocker_reason": blocker_reason(row),
        "has_quote_anchor": has_quote_anchor(row),
        "has_valid_entry_context": has_valid_entry_context(row),
        "outcome_15m": outcome_15m(row),
        "liquidity_at_entry": ctx.get("liquidity"),
        "market_cap_at_entry": ctx.get("market_cap"),
        "price_at_entry": ctx.get("price"),
    }


def wallet_quality_row(readiness_row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted_rows(rows)
    clean = [row for row in ordered if is_clean_proof_row(row)]
    open_rows = [row for row in ordered if is_open_blocker(row)]
    reason_counts = Counter(blocker_reason(row) for row in open_rows)
    action = recommended_action(reason_counts, open_rows)
    candidate_records = len(ordered)
    unique_tokens = len({row.get("token_mint") for row in open_rows if row.get("token_mint")})
    event_rows = [blocker_event(row) for row in open_rows[:50]]
    return {
        "wallet_address": readiness_row.get("wallet_address"),
        "paper_readiness_status": readiness_row.get("paper_readiness_status"),
        "failed_readiness_gates": as_list(readiness_row.get("failed_gates")),
        "candidate_records": candidate_records,
        "clean_proof_rows": len(clean),
        "open_blocker_rows": len(open_rows),
        "context_completion_rate": rate(len(clean), candidate_records),
        "excluded_rate": rate(len(open_rows), candidate_records),
        "unique_blocked_tokens": unique_tokens,
        "missing_later_market_snapshot_rows": sum(count for reason, count in reason_counts.items() if "snapshot" in reason),
        "missing_valid_execution_price_quote_rows": sum(
            count
            for reason, count in reason_counts.items()
            if "quote" in reason or "timestamp" in reason or "entry_price" in reason or "entry_context" in reason
        ),
        "missing_outcome_label_rows": sum(count for reason, count in reason_counts.items() if "outcome" in reason),
        "blocker_reason_counts": dict(sorted(reason_counts.items())),
        "recommended_context_action": action,
        "priority_rank": priority_for_action(action),
        "next_operator_step": next_operator_step(action),
        "sample_blocker_events": event_rows,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def sort_wallet(row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        safe_int(row.get("priority_rank")),
        -safe_int(row.get("open_blocker_rows")),
        -safe_int(row.get("unique_blocked_tokens")),
        str(row.get("wallet_address") or ""),
    )


def build_candidate_context_quality_lift(
    *,
    readiness_gate: dict[str, Any],
    records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    repaired_records = repaired_records or []
    merged_records = merge_repaired_records(records, repaired_records)
    targets = target_wallets(readiness_gate)
    target_addresses = [str(row.get("wallet_address") or "") for row in targets if row.get("wallet_address")]
    by_wallet = {wallet: [] for wallet in target_addresses}
    for row in merged_records:
        wallet = wallet_address(row)
        if wallet in by_wallet:
            by_wallet[wallet].append(row)
    readiness_by_wallet = {str(row.get("wallet_address")): row for row in targets}
    wallets = sorted(
        [
            wallet_quality_row(readiness_by_wallet[wallet], by_wallet.get(wallet, []))
            for wallet in target_addresses
        ],
        key=sort_wallet,
    )
    blocker_events = [
        event
        for wallet in wallets
        for event in as_list(wallet.get("sample_blocker_events"))
    ]
    action_counts = Counter(str(row.get("recommended_context_action")) for row in wallets)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "auto_trust_mutation_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "wallets_in_queue": len(wallets),
            "open_blocker_rows": sum(safe_int(row.get("open_blocker_rows")) for row in wallets),
            "clean_proof_rows": sum(safe_int(row.get("clean_proof_rows")) for row in wallets),
            "unique_blocked_tokens": sum(safe_int(row.get("unique_blocked_tokens")) for row in wallets),
            "repair_market_snapshot_wallets": safe_int(action_counts.get("repair_market_snapshot")),
            "repair_entry_timestamp_wallets": safe_int(action_counts.get("repair_entry_timestamp")),
            "collect_more_clean_candidate_rows_wallets": safe_int(action_counts.get("collect_more_clean_candidate_rows")),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "wallets": wallets,
        "blocker_events": blocker_events,
        "operator_note": (
            "Candidate context quality lift is targeted to walk-forward survivor wallets that failed readiness "
            "because of context or excluded-row quality. It does not promote wallets, mutate trust, mutate lists, or execute trades."
        ),
    }
