from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "FORWARD_SIGNAL_OPERATOR_ROLLUP_REVIEW_ONLY"
VERSION = "forward_signal_operator_rollup.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def rows_by_wallet(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for wallet_packet in packet.get("wallets") or []:
        if not isinstance(wallet_packet, dict):
            continue
        wallet = str(wallet_packet.get("wallet") or "").strip()
        if wallet:
            grouped[wallet] = [row for row in wallet_packet.get("rows") or [] if isinstance(row, dict)]
    return grouped


def map_by_wallet(payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in payload.get(key) or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            mapped[wallet] = row
    return mapped


def top_token_mints(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("token_mint") or "unknown") for row in rows if str(row.get("token_mint") or "").strip())
    return [{"token_mint": mint, "rows": count} for mint, count in counts.most_common(limit)]


def wallet_rollup(wallet: str, rows: list[dict[str, Any]], validator: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    runner_rows = [row for row in rows if str(row.get("outcome_15m") or "").lower() == "runner"]
    unknown_rows = [row for row in rows if str(row.get("outcome_15m") or "").lower() == "unknown"]
    return {
        "wallet": wallet,
        "decision_type": decision.get("decision_type", "manual_review_required"),
        "validation_status": validator.get("validation_status"),
        "runner_rows": safe_int(validator.get("runner_rows"), len(runner_rows)),
        "unknown_15m_rows": len(unknown_rows),
        "total_review_rows": len(rows),
        "runner_distinct_token_mints": safe_int(validator.get("runner_distinct_token_mints")),
        "runner_signal_span_seconds": validator.get("runner_signal_span_seconds"),
        "dominant_runner_token_share": validator.get("dominant_runner_token_share"),
        "top_token_mints": top_token_mints(runner_rows or rows),
        "required_human_checks": list(decision.get("required_human_checks") or []),
        "approved": bool(decision.get("approved")) is True,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "live_execution_mutation_allowed": False,
    }


def build_summary(wallets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "wallets": len(wallets),
        "manual_review_required": sum(1 for row in wallets if row.get("decision_type") == "manual_review_required"),
        "repeatability_supported": sum(1 for row in wallets if row.get("validation_status") == "repeatability_supported_manual_review"),
        "promotions_allowed": 0,
        "trust_mutations_allowed": 0,
        "wallet_list_mutations_allowed": 0,
    }


def build_forward_signal_operator_rollup(
    *,
    packet: dict[str, Any],
    validator: dict[str, Any],
    decision_prep: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    rows = rows_by_wallet(packet)
    validators = map_by_wallet(validator, "wallets")
    decisions = map_by_wallet(decision_prep, "decisions")
    wallets: list[dict[str, Any]] = []
    for wallet in sorted(set(rows) | set(validators) | set(decisions)):
        wallets.append(wallet_rollup(wallet, rows.get(wallet, []), validators.get(wallet, {}), decisions.get(wallet, {})))
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": validator.get("live_execution_locked") is not False and decision_prep.get("live_execution_locked") is not False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "summary": build_summary(wallets),
        "wallets": wallets,
        "operator_note": (
            "This rollup combines packet, validator, and decision-prep evidence for operator review only. "
            "It does not approve promotions or mutate trust, wallet lists, or execution."
        ),
    }
