from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_int


MODE = "ARCHIVAL_MINT_SUPPLY_RECONSTRUCTION_REVIEW_ONLY"
VERSION = "archival_mint_supply_reconstruction.v1"
MINT_EVENT_TYPES = {"mintTo", "mintToChecked"}
BURN_EVENT_TYPES = {"burn", "burnChecked"}


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in requirements or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def tx_body(row: dict[str, Any]) -> dict[str, Any]:
    tx = as_dict(row.get("transaction"))
    return tx if tx else row


def tx_slot(row: dict[str, Any]) -> int | None:
    body = tx_body(row)
    slot = safe_int(row.get("slot", body.get("slot")), 0)
    return slot if slot > 0 else None


def tx_signature(row: dict[str, Any]) -> str:
    body = tx_body(row)
    return str(row.get("signature") or body.get("signature") or "").strip()


def top_level_instructions(row: dict[str, Any]) -> list[dict[str, Any]]:
    body = tx_body(row)
    transaction = as_dict(body.get("transaction"))
    message = as_dict(transaction.get("message"))
    instructions = message.get("instructions")
    return [item for item in instructions or [] if isinstance(item, dict)]


def inner_instructions(row: dict[str, Any]) -> list[dict[str, Any]]:
    body = tx_body(row)
    meta = as_dict(body.get("meta"))
    rows: list[dict[str, Any]] = []
    for group in meta.get("innerInstructions") or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("instructions") or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def all_instructions(row: dict[str, Any]) -> list[dict[str, Any]]:
    return top_level_instructions(row) + inner_instructions(row)


def balance_decimals_by_mint(row: dict[str, Any]) -> dict[str, int]:
    body = tx_body(row)
    meta = as_dict(body.get("meta"))
    decimals: dict[str, int] = {}
    for field in ("preTokenBalances", "postTokenBalances"):
        for balance in meta.get(field) or []:
            if not isinstance(balance, dict):
                continue
            mint = str(balance.get("mint") or "").strip()
            ui_amount = as_dict(balance.get("uiTokenAmount"))
            parsed_decimals = safe_int(ui_amount.get("decimals"), -1)
            if mint and parsed_decimals >= 0:
                decimals[mint] = parsed_decimals
    return decimals


def token_amount(info: dict[str, Any]) -> tuple[int | None, int | None]:
    token_amount_row = as_dict(info.get("tokenAmount"))
    amount = info.get("amount", token_amount_row.get("amount"))
    decimals = info.get("decimals", token_amount_row.get("decimals"))
    parsed_amount = safe_int(amount, -1)
    parsed_decimals = safe_int(decimals, -1)
    if parsed_amount < 0:
        return None, None
    return parsed_amount, parsed_decimals if parsed_decimals >= 0 else None


def parsed_supply_events(raw_transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in raw_transactions or []:
        if not isinstance(row, dict):
            continue
        slot = tx_slot(row)
        if slot is None:
            continue
        signature = tx_signature(row)
        balance_decimals = balance_decimals_by_mint(row)
        for instruction in all_instructions(row):
            parsed = as_dict(instruction.get("parsed"))
            event_type = str(parsed.get("type") or "").strip()
            if event_type not in MINT_EVENT_TYPES and event_type not in BURN_EVENT_TYPES:
                continue
            info = as_dict(parsed.get("info"))
            mint = str(info.get("mint") or "").strip()
            amount, decimals = token_amount(info)
            if not mint or amount is None:
                continue
            if decimals is None:
                decimals = balance_decimals.get(mint)
            direction = 1 if event_type in MINT_EVENT_TYPES else -1
            events.append({
                "version": VERSION,
                "token_mint": mint,
                "slot": slot,
                "transaction_signature": signature,
                "event_type": event_type,
                "amount": amount,
                "decimals": decimals,
                "direction": direction,
            })
    events.sort(key=lambda item: (item["token_mint"], item["slot"], item.get("transaction_signature") or ""))
    return events


def grouped_events(raw_transactions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in parsed_supply_events(raw_transactions):
        grouped[event["token_mint"]].append(event)
    return grouped


def completeness_for(history_completeness: dict[str, Any], token: str) -> dict[str, Any]:
    row = history_completeness.get(token) if isinstance(history_completeness, dict) else {}
    return row if isinstance(row, dict) else {}


def build_requirement_result(
    *,
    requirement: dict[str, Any],
    events: list[dict[str, Any]],
    completeness: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    token = token_mint(requirement)
    decision_slot = safe_int(requirement.get("earliest_decision_slot"), 0)
    complete_through = safe_int(completeness.get("complete_through_slot"), 0)
    result = {
        "version": VERSION,
        "token_mint": token,
        "decision_slot": decision_slot or None,
        "complete_through_slot": complete_through or None,
        "history_source": completeness.get("source"),
        "row_count": safe_int(requirement.get("row_count"), 0),
        "supply_event_count": 0,
        "status": "blocked_incomplete_mint_history",
        "block_reasons": ["mint_history_not_complete_through_decision_slot"],
        "can_mutate_wallet_trust": False,
    }
    if decision_slot <= 0:
        result["status"] = "blocked_missing_decision_slot"
        result["block_reasons"] = ["missing_decision_slot"]
        return result, None
    if complete_through < decision_slot:
        return result, None

    prior_events = [event for event in events if safe_int(event.get("slot"), 0) <= decision_slot]
    result["supply_event_count"] = len(prior_events)
    if not prior_events:
        result["status"] = "blocked_no_mint_burn_events"
        result["block_reasons"] = ["no_mint_burn_events_before_decision_slot"]
        return result, None

    decimals = next((event.get("decimals") for event in prior_events if event.get("decimals") is not None), None)
    if decimals is None:
        result["status"] = "blocked_missing_decimals"
        result["block_reasons"] = ["missing_decimals"]
        return result, None

    raw_supply = sum(int(event["amount"]) * int(event["direction"]) for event in prior_events)
    if raw_supply < 0:
        result["status"] = "blocked_negative_reconstructed_supply"
        result["block_reasons"] = ["negative_reconstructed_supply"]
        return result, None

    result["status"] = "supply_reconstructed"
    result["block_reasons"] = []
    snapshot = {
        "version": VERSION,
        "token_mint": token,
        "slot": max(safe_int(event.get("slot"), 0) for event in prior_events),
        "requested_snapshot_slot": decision_slot,
        "max_acceptable_snapshot_slot": decision_slot,
        "raw_supply": str(raw_supply),
        "decimals": int(decimals),
        "source": "mint_burn_history_reconstruction",
        "source_file": completeness.get("source_file"),
        "history_source": completeness.get("source"),
        "decision_time_safe": True,
        "supply_event_count": len(prior_events),
        "can_mutate_wallet_trust": False,
    }
    return result, snapshot


def build_summary(requirements: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in requirements)
    blocks = Counter(reason for row in requirements for reason in row.get("block_reasons") or [])
    return {
        "requirements_scanned": len(requirements),
        "snapshots_reconstructed": len(snapshots),
        "blocked_incomplete_history": statuses.get("blocked_incomplete_mint_history", 0),
        "blocked_no_mint_burn_events": statuses.get("blocked_no_mint_burn_events", 0),
        "blocked_missing_decision_slot": statuses.get("blocked_missing_decision_slot", 0),
        "tokens_affected": len({row.get("token_mint") for row in requirements if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
    }


def build_archival_mint_supply_reconstruction_report(
    *,
    archival_supply_plan: dict[str, Any],
    raw_transactions: list[dict[str, Any]],
    history_completeness: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    events_by_token = grouped_events(raw_transactions)
    history_completeness = history_completeness or {}
    requirement_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for requirement in ready_requirements(archival_supply_plan):
        token = token_mint(requirement)
        row, snapshot = build_requirement_result(
            requirement=requirement,
            events=events_by_token.get(token, []),
            completeness=completeness_for(history_completeness, token),
        )
        requirement_rows.append(row)
        if snapshot:
            snapshots.append(snapshot)

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
        "summary": build_summary(requirement_rows, snapshots),
        "requirements": requirement_rows,
        "snapshots": snapshots,
        "operator_note": (
            "This reconstruction lane only produces supply snapshots from complete mint/burn history. "
            "Local wallet transaction artifacts without completeness proof remain blocked."
        ),
    }
