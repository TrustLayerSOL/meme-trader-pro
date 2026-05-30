from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.forward_outcome_resolution import is_known
from wallets.forward_outcome_resolution import KNOWN_OUTCOMES
from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import safe_float


MODE = "CANDIDATE_OUTCOME_WINDOW_COMPLETION_REVIEW_ONLY"
VERSION = "candidate_outcome_window_completion.v1"
FIFTEEN_MINUTES = 900


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or "").strip()


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def signal_time(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("signal_time") or row.get("timestamp"), None)


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def fifteen_window(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("outcome_window_labels")).get("15m"))


def known_15m(row: dict[str, Any]) -> bool:
    return is_known(fifteen_window(row))


def unresolved_15m(row: dict[str, Any]) -> bool:
    window = fifteen_window(row)
    if known_15m(row):
        return False
    outcome = str(window.get("outcome_type") or "unknown").lower()
    return outcome not in KNOWN_OUTCOMES


def classification_reasons(row: dict[str, Any]) -> list[str]:
    reasons = fifteen_window(row).get("classification_reasons")
    return [str(reason) for reason in reasons] if isinstance(reasons, list) else []


def queue_row(row: dict[str, Any], blocker_type: str) -> dict[str, Any]:
    ts = signal_time(row)
    return {
        "event_id": event_id(row),
        "wallet_address": wallet_address(row),
        "token_address": token_mint(row),
        "observed_action": row.get("observed_action") or row.get("action"),
        "signal_time": ts,
        "transaction_signature": row.get("transaction_signature"),
        "target_window": "15m",
        "evaluation_horizon_seconds": FIFTEEN_MINUTES,
        "needed_snapshot_start": ts,
        "needed_snapshot_end": ts + FIFTEEN_MINUTES if ts is not None else None,
        "blocker_type": blocker_type,
        "recommended_action": "capture_later_market_snapshot",
        "source_record_status": row.get("status"),
        "priority_rank": 0 if blocker_type == "missing_later_market_snapshot" else 1,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def audit_row(row: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    return {
        "event_id": event_id(row),
        "wallet_address": wallet_address(row),
        "token_address": token_mint(row),
        "signal_time": signal_time(row),
        "transaction_signature": row.get("transaction_signature"),
        "outcome_15m": str(fifteen_window(row).get("outcome_type") or "unknown"),
        "completion_status": status,
        "reason": reason,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def rejected_block_reason(row: dict[str, Any]) -> str:
    return str(row.get("block_reason") or row.get("reject_reason") or "unknown")


def build_candidate_outcome_window_completion(
    *,
    resolved_records: list[dict[str, Any]],
    rejected_records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    capture_queue: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    known_rows = 0
    unresolved_rows = 0
    rejected_missing_snapshot = 0
    structurally_blocked = 0

    for row in resolved_records or []:
        if not isinstance(row, dict):
            continue
        if known_15m(row):
            known_rows += 1
            audit_rows.append(audit_row(row, "known_15m", "already_labeled"))
            continue
        if unresolved_15m(row):
            unresolved_rows += 1
            reason = "missing_later_forward_market_snapshots"
            if classification_reasons(row):
                reason = ";".join(classification_reasons(row))
            capture_queue.append(queue_row(row, "missing_15m_outcome"))
            audit_rows.append(audit_row(row, "capture_required", reason))

    for row in rejected_records or []:
        if not isinstance(row, dict):
            continue
        reason = rejected_block_reason(row)
        if reason == "missing_later_market_snapshot":
            rejected_missing_snapshot += 1
            capture_queue.append(queue_row(row, "missing_later_market_snapshot"))
            audit_rows.append(audit_row(row, "capture_required", reason))
        else:
            structurally_blocked += 1
            audit_rows.append(audit_row(row, "structurally_blocked", reason))

    capture_queue.sort(
        key=lambda row: (
            int(row.get("priority_rank") or 9),
            str(row.get("token_address") or ""),
            float(row.get("signal_time") or 0.0),
            str(row.get("event_id") or ""),
        )
    )
    action_counts = Counter(str(row.get("recommended_action") or "unknown") for row in capture_queue)
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
            "records_scanned": len([row for row in resolved_records or [] if isinstance(row, dict)])
            + len([row for row in rejected_records or [] if isinstance(row, dict)]),
            "known_15m_rows": known_rows,
            "unresolved_15m_rows": unresolved_rows,
            "rejected_missing_later_snapshot_rows": rejected_missing_snapshot,
            "structurally_blocked_rows": structurally_blocked,
            "capture_queue_rows": len(capture_queue),
            "unique_tokens_to_capture": len({row.get("token_address") for row in capture_queue if row.get("token_address")}),
            "wallets_affected": len({row.get("wallet_address") for row in capture_queue if row.get("wallet_address")}),
            "capture_later_market_snapshot_actions": action_counts.get("capture_later_market_snapshot", 0),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "capture_queue": capture_queue,
        "audit_rows": audit_rows,
        "operator_note": (
            "Candidate outcome window completion is review-only. It queues missing later market snapshots "
            "for candidate repaired rows and does not invent labels, promote wallets, mutate trust, or execute trades."
        ),
    }
