from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from wallets.historical_market_context_backfill import index_raw_transactions
from wallets.wallet_evidence_models import as_dict, safe_float, safe_int


MODE = "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY"
VERSION = "archival_supply_recovery_plan.v1"
ARCHIVAL_SUPPLY_ACTION = "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT"
REQUIRED_EVIDENCE = "historical_mint_account_supply_at_or_before_decision_slot"


def is_archival_supply_candidate(row: dict[str, Any]) -> bool:
    next_action = str(row.get("next_action") or "").strip()
    readiness = str(row.get("readiness_status") or "").strip()
    return next_action == ARCHIVAL_SUPPLY_ACTION or readiness == "needs_archival_supply_for_market_cap"


def raw_slot(raw: dict[str, Any] | None) -> int | None:
    if not isinstance(raw, dict):
        return None
    tx = as_dict(raw.get("transaction"))
    slot = raw.get("slot", tx.get("slot"))
    parsed = safe_int(slot, 0)
    return parsed if parsed > 0 else None


def raw_block_time(raw: dict[str, Any] | None) -> float | None:
    if not isinstance(raw, dict):
        return None
    tx = as_dict(raw.get("transaction"))
    return safe_float(raw.get("blockTime", tx.get("blockTime")), None)


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def wallet(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or "").strip()


def signature(row: dict[str, Any]) -> str:
    return str(row.get("transaction_signature") or row.get("signature") or "").strip()


def build_token_requirement(token: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    wallets = sorted({wallet(row) for row in rows if wallet(row)})
    signatures = sorted({str(row.get("transaction_signature") or "") for row in rows if row.get("transaction_signature")})
    slots = sorted(
        {
            int(row["decision_slot"])
            for row in rows
            if isinstance(row.get("decision_slot"), int) and int(row["decision_slot"]) > 0
        }
    )
    block_times = sorted(
        {
            float(row["decision_block_time"])
            for row in rows
            if isinstance(row.get("decision_block_time"), (int, float))
        }
    )
    missing_slot_rows = [row for row in rows if not row.get("decision_slot")]
    status = "ready_for_archival_supply_fetch" if slots and not missing_slot_rows else "blocked_missing_decision_slot"
    blocked_by = [] if status == "ready_for_archival_supply_fetch" else ["missing_raw_transaction_slot"]

    return {
        "version": VERSION,
        "token_mint": token,
        "status": status,
        "required_evidence": REQUIRED_EVIDENCE,
        "row_count": len(rows),
        "wallet_count": len(wallets),
        "wallets": wallets,
        "transaction_signature_count": len(signatures),
        "transaction_signatures": signatures[:50],
        "earliest_decision_slot": slots[0] if slots else None,
        "latest_decision_slot": slots[-1] if slots else None,
        "earliest_decision_block_time": block_times[0] if block_times else None,
        "latest_decision_block_time": block_times[-1] if block_times else None,
        "rows_with_decision_slot": len(rows) - len(missing_slot_rows),
        "rows_missing_decision_slot": len(missing_slot_rows),
        "blocked_by": blocked_by,
        "can_mutate_wallet_trust": False,
        "fetch_instruction": (
            "Fetch the token mint account supply from an archival Solana source at or before each decision slot. "
            "Do not use current supply or inferred supply."
        ),
    }


def build_summary(candidate_rows: list[dict[str, Any]], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    rows_with_slot = sum(1 for row in candidate_rows if row.get("decision_slot"))
    rows_missing_slot = len(candidate_rows) - rows_with_slot
    tokens_to_fetch = sum(1 for row in requirements if row.get("status") == "ready_for_archival_supply_fetch")
    tokens_blocked = sum(1 for row in requirements if row.get("status") == "blocked_missing_decision_slot")
    completion = round((rows_with_slot / len(candidate_rows)) * 100) if candidate_rows else 100
    return {
        "plan_completion_pct": completion,
        "candidate_rows": len(candidate_rows),
        "tokens_to_fetch": tokens_to_fetch,
        "token_requirements": len(requirements),
        "rows_with_decision_slot": rows_with_slot,
        "rows_missing_decision_slot": rows_missing_slot,
        "tokens_blocked_missing_slot": tokens_blocked,
        "wallets_affected": len({wallet(row) for row in candidate_rows if wallet(row)}),
        "tokens_affected": len({token_mint(row) for row in candidate_rows if token_mint(row)}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_archival_supply_recovery_plan(
    *,
    score_ready_market_context_records: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    raw_by_signature = index_raw_transactions(raw_transactions)
    candidate_rows: list[dict[str, Any]] = []
    rows_by_token: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in score_ready_market_context_records or []:
        if not isinstance(row, dict) or not is_archival_supply_candidate(row):
            continue
        token = token_mint(row)
        if not token:
            continue
        tx_signature = signature(row)
        raw = raw_by_signature.get(tx_signature)
        slot = raw_slot(raw)
        block_time = raw_block_time(raw)
        candidate = {
            "version": VERSION,
            "wallet": wallet(row),
            "token_mint": token,
            "timestamp": safe_float(row.get("timestamp"), None),
            "transaction_signature": tx_signature,
            "decision_slot": slot,
            "decision_block_time": block_time,
            "readiness_status": row.get("readiness_status"),
            "next_action": ARCHIVAL_SUPPLY_ACTION,
            "source_decision_time_safe": row.get("decision_time_safe") is True,
            "required_evidence": REQUIRED_EVIDENCE,
            "source_blocked_by": list(row.get("blocked_by") or []),
            "missing_fields": [] if slot else ["decision_slot"],
            "blocked_by": [] if slot else ["missing_raw_transaction_slot"],
            "can_mutate_wallet_trust": False,
        }
        candidate_rows.append(candidate)
        rows_by_token[token].append(candidate)

    requirements = [build_token_requirement(token, rows) for token, rows in rows_by_token.items()]
    requirements.sort(
        key=lambda row: (
            0 if row.get("status") == "ready_for_archival_supply_fetch" else 1,
            str(row.get("token_mint") or ""),
        )
    )
    candidate_rows.sort(
        key=lambda row: (
            str(row.get("token_mint") or ""),
            row.get("decision_slot") or 0,
            str(row.get("wallet") or ""),
            str(row.get("transaction_signature") or ""),
        )
    )

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
        "summary": build_summary(candidate_rows, requirements),
        "token_requirements": requirements,
        "candidate_rows": candidate_rows,
        "operator_note": (
            "This plan only identifies archival mint-account supply requirements for near score-ready rows. "
            "It does not fetch supply, infer supply, substitute current supply, mutate wallet trust, or trade."
        ),
    }
