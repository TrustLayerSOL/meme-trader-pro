from __future__ import annotations

import time
from copy import deepcopy
from collections import Counter
from typing import Any

from wallets.onchain_later_outcome_backfill import build_onchain_later_outcome_backfill_report
from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import safe_float


MODE = "CANDIDATE_ONCHAIN_LATER_SNAPSHOT_RECOVERY_REVIEW_ONLY"
VERSION = "candidate_onchain_later_snapshot_recovery.v1"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def anchor_by_event(anchor_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        event_id(row): row
        for row in anchor_records or []
        if isinstance(row, dict) and event_id(row)
    }


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def candidate_record_from_anchor(deferred: dict[str, Any], anchor: dict[str, Any]) -> dict[str, Any]:
    ctx = entry_context(anchor)
    mint = str(anchor.get("token_mint") or deferred.get("token_address") or "").strip()
    wallet = str(anchor.get("wallet") or deferred.get("wallet_address") or "").strip()
    signal_time = safe_float(anchor.get("signal_time") or deferred.get("signal_time"), None)
    return {
        "decision_id": event_id(anchor) or event_id(deferred),
        "mint": mint,
        "wallets": [{"wallet": wallet}],
        "signal_context": {
            "mint": mint,
            "entry_timestamp": signal_time,
            "market": {
                "price": ctx.get("price") or ctx.get("execution_price_quote"),
                "liquidity": ctx.get("liquidity"),
                "quote_mint": ctx.get("quote_mint"),
            },
        },
        "decision": {"decision_timestamp": signal_time},
        "decision_context": {"candidate_onchain_recovery": True},
        "later_token_outcome": anchor.get("later_token_outcome") or {"outcome_type": "unknown", "windows": {}},
        "source_forward_record": {
            "event_id": event_id(anchor) or event_id(deferred),
            "wallet": wallet,
            "token_mint": mint,
            "transaction_signature": anchor.get("transaction_signature") or deferred.get("transaction_signature"),
            "observed_action": anchor.get("observed_action") or deferred.get("observed_action"),
        },
    }


def blocked_row(deferred: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "event_id": event_id(deferred),
        "wallet_address": deferred.get("wallet_address"),
        "token_address": deferred.get("token_address"),
        "signal_time": deferred.get("signal_time"),
        "block_reason": reason,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def recovered_15m_window(record: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("known_15m_added"):
        return None
    outcome = as_dict(record.get("later_token_outcome"))
    window = as_dict(as_dict(outcome.get("windows")).get("15m"))
    if str(window.get("outcome_type") or "unknown").lower() == "unknown":
        return None
    return window


def apply_recovered_outcomes_to_anchor_records(
    *,
    anchor_records: list[dict[str, Any]],
    recovery_records: list[dict[str, Any]],
    generated_at: float,
) -> list[dict[str, Any]]:
    recovered_by_event: dict[str, dict[str, Any]] = {}
    for row in recovery_records or []:
        if not isinstance(row, dict):
            continue
        window = recovered_15m_window(row)
        if not window:
            continue
        eid = event_id(row)
        if eid:
            recovered_by_event[eid] = row

    recovered_forward_records: list[dict[str, Any]] = []
    for anchor in anchor_records or []:
        if not isinstance(anchor, dict):
            continue
        recovery = recovered_by_event.get(event_id(anchor))
        if not recovery:
            continue
        next_row = deepcopy(anchor)
        outcome = deepcopy(as_dict(recovery.get("later_token_outcome")))
        labels = deepcopy(as_dict(next_row.get("outcome_window_labels")))
        windows = as_dict(outcome.get("windows"))
        for window_name, label in windows.items():
            if isinstance(label, dict):
                labels[str(window_name)] = deepcopy(label)
        next_row["outcome_window_labels"] = labels
        next_row["later_token_outcome"] = outcome
        next_row["status"] = "candidate_onchain_later_outcome_recovered"
        next_row["block_reasons"] = []
        next_row["candidate_onchain_later_snapshot_recovery"] = {
            "generated_at": generated_at,
            "method": "preserved_raw_transaction_later_snapshot",
            "source": "candidate_onchain_later_snapshot_recovery",
            "review_only": True,
            "known_15m_added": True,
        }
        next_row["wallet_list_mutation_allowed"] = False
        next_row["wallet_trust_mutation_allowed"] = False
        next_row["can_mutate_wallet_trust"] = False
        recovered_forward_records.append(next_row)
    return recovered_forward_records


def combine_anchor_and_recovered_records(
    *,
    anchor_records: list[dict[str, Any]],
    recovered_forward_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recovered_by_event = {
        event_id(row): row
        for row in recovered_forward_records or []
        if isinstance(row, dict) and event_id(row)
    }
    combined: list[dict[str, Any]] = []
    used: set[str] = set()
    for anchor in anchor_records or []:
        if not isinstance(anchor, dict):
            continue
        eid = event_id(anchor)
        if eid and eid in recovered_by_event:
            combined.append(deepcopy(recovered_by_event[eid]))
            used.add(eid)
        else:
            combined.append(deepcopy(anchor))
    for eid, row in sorted(recovered_by_event.items()):
        if eid not in used:
            combined.append(deepcopy(row))
    return combined


def build_candidate_onchain_later_snapshot_recovery(
    *,
    deferred_rows: list[dict[str, Any]],
    anchor_records: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    quote_price_series: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    anchors = anchor_by_event(anchor_records)
    candidate_records: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    for row in deferred_rows or []:
        if not isinstance(row, dict):
            continue
        anchor = anchors.get(event_id(row))
        if not anchor:
            blocked_rows.append(blocked_row(row, "missing_anchor_record"))
            continue
        candidate_records.append(candidate_record_from_anchor(row, anchor))
    backfill = build_onchain_later_outcome_backfill_report(
        records=candidate_records,
        raw_transactions=raw_transactions,
        quote_price_series=quote_price_series or [],
        generated_at=generated_at,
    )
    records = [row for row in as_list(backfill.get("records")) if isinstance(row, dict)]
    recovered_forward_records = apply_recovered_outcomes_to_anchor_records(
        anchor_records=anchor_records,
        recovery_records=records,
        generated_at=generated_at,
    )
    combined_repaired_records = combine_anchor_and_recovered_records(
        anchor_records=anchor_records,
        recovered_forward_records=recovered_forward_records,
    )
    status_counts = Counter(str(row.get("status") or "unknown") for row in records)
    summary = dict(as_dict(backfill.get("summary")))
    summary.update(
        {
            "deferred_rows_scanned": len([row for row in deferred_rows or [] if isinstance(row, dict)]),
            "candidate_records_built": len(candidate_records),
            "recovered_forward_records": len(recovered_forward_records),
            "combined_repaired_records": len(combined_repaired_records),
            "blocked_missing_anchor_rows": len(blocked_rows),
            "raw_transactions_scanned": len([row for row in raw_transactions or [] if isinstance(row, dict)]),
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        }
    )
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
        "summary": summary,
        "status_counts": dict(sorted(status_counts.items())),
        "blocked_rows": blocked_rows,
        "candidate_records": candidate_records,
        "records": records,
        "recovered_forward_records": recovered_forward_records,
        "combined_repaired_records": combined_repaired_records,
        "operator_note": (
            "Candidate onchain later-snapshot recovery is evaluation-only. It uses preserved raw transactions after "
            "the signal timestamp and does not write to decision context, trust, wallet lists, or execution paths."
        ),
    }
