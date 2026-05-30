from __future__ import annotations

import time
from typing import Any


MODE = "FORWARD_SIGNAL_DECISION_PREP_REVIEW_ONLY"
VERSION = "forward_signal_decision_prep.v1"
SUPPORTED_STATUS = "repeatability_supported_manual_review"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def wallet_rows_by_wallet(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_by_wallet: dict[str, list[dict[str, Any]]] = {}
    for wallet_packet in packet.get("wallets") or []:
        if not isinstance(wallet_packet, dict):
            continue
        wallet = str(wallet_packet.get("wallet") or "").strip()
        if not wallet:
            continue
        rows = [row for row in wallet_packet.get("rows") or [] if isinstance(row, dict)]
        rows_by_wallet[wallet] = rows
    return rows_by_wallet


def sample_rows(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in rows[:limit]:
        compact.append(
            {
                "event_id": row.get("event_id"),
                "token_mint": row.get("token_mint"),
                "signal_time": row.get("signal_time"),
                "repaired_price": row.get("repaired_price"),
                "outcome_15m": row.get("outcome_15m"),
            }
        )
    return compact


def decision_for_wallet(wallet: dict[str, Any], rows_by_wallet: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    wallet_address = str(wallet.get("wallet") or "").strip()
    rows = rows_by_wallet.get(wallet_address, [])
    return {
        "wallet": wallet_address,
        "decision_type": "manual_review_required",
        "approved": False,
        "promotion_allowed": False,
        "review_only": True,
        "evidence": {
            "validation_status": wallet.get("validation_status"),
            "runner_rows": safe_int(wallet.get("runner_rows")),
            "total_review_rows": safe_int(wallet.get("total_review_rows")),
            "runner_distinct_token_mints": safe_int(wallet.get("runner_distinct_token_mints")),
            "runner_signal_span_seconds": wallet.get("runner_signal_span_seconds"),
            "dominant_runner_token_share": wallet.get("dominant_runner_token_share"),
            "packet_rows_available": len(rows),
        },
        "sample_rows": sample_rows(rows),
        "required_human_checks": [
            "confirm this wallet is not linked to known bad/rug behavior",
            "inspect runner rows across token mints for repeatability",
            "confirm evidence quality is enough for continued observation",
            "do not promote from this artifact alone",
        ],
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "live_execution_mutation_allowed": False,
    }


def held_out_wallet(wallet: dict[str, Any]) -> dict[str, Any]:
    return {
        "wallet": wallet.get("wallet"),
        "validation_status": wallet.get("validation_status"),
        "held_out_reason": "validator_status_not_repeatability_supported",
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_summary(decisions: list[dict[str, Any]], held_out: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prepared_decisions": len(decisions),
        "manual_review_required": sum(1 for row in decisions if row.get("decision_type") == "manual_review_required"),
        "held_out_wallets": len(held_out),
        "promotions_allowed": 0,
        "trust_mutations_allowed": 0,
        "wallet_list_mutations_allowed": 0,
    }


def build_forward_signal_decision_prep(
    *,
    validator: dict[str, Any],
    packet: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    rows_by_wallet = wallet_rows_by_wallet(packet)
    decisions: list[dict[str, Any]] = []
    held_out: list[dict[str, Any]] = []
    for wallet in validator.get("wallets") or []:
        if not isinstance(wallet, dict):
            continue
        if wallet.get("validation_status") == SUPPORTED_STATUS:
            decisions.append(decision_for_wallet(wallet, rows_by_wallet))
        else:
            held_out.append(held_out_wallet(wallet))
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": validator.get("live_execution_locked") is not False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "summary": build_summary(decisions, held_out),
        "decisions": decisions,
        "held_out_wallets": held_out,
        "operator_note": (
            "Decision prep is a human-review handoff only. It does not approve wallet promotion, trust mutation, "
            "wallet-list mutation, or execution changes."
        ),
    }
