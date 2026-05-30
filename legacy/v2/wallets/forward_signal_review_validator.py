from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "FORWARD_SIGNAL_REVIEW_VALIDATOR_REVIEW_ONLY"
VERSION = "forward_signal_review_validator.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def runner_rows(wallet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in wallet.get("rows") or []:
        if isinstance(row, dict) and str(row.get("outcome_15m") or "").lower() == "runner":
            rows.append(row)
    return rows


def distinct_mints(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("token_mint") or "").strip() for row in rows if str(row.get("token_mint") or "").strip()}


def time_span(rows: list[dict[str, Any]]) -> float:
    times = [safe_float(row.get("signal_time"), None) for row in rows]
    clean_times = [value for value in times if value is not None]
    if len(clean_times) < 2:
        return 0.0
    return max(clean_times) - min(clean_times)


def dominant_token_share(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    counts = Counter(str(row.get("token_mint") or "unknown") for row in rows)
    return max(counts.values()) / len(rows)


def validation_status(*, runner_count: int, runner_distinct_mints: int, runner_span: float, dominant_share: float) -> str:
    if runner_count == 0:
        return "insufficient_runner_evidence"
    if runner_distinct_mints < 2 or dominant_share >= 0.75:
        return "concentrated_anomaly_hold_review"
    if runner_distinct_mints >= 5 and runner_span >= 3600:
        return "repeatability_supported_manual_review"
    return "limited_repeatability_hold_review"


def validate_wallet(wallet: dict[str, Any]) -> dict[str, Any]:
    runners = runner_rows(wallet)
    mint_set = distinct_mints(runners)
    runner_span = time_span(runners)
    dominant_share = dominant_token_share(runners)
    status = validation_status(
        runner_count=len(runners),
        runner_distinct_mints=len(mint_set),
        runner_span=runner_span,
        dominant_share=dominant_share,
    )
    return {
        "wallet": wallet.get("wallet"),
        "review_only": True,
        "validation_status": status,
        "runner_rows": len(runners),
        "total_review_rows": safe_int(wallet.get("records"), len(wallet.get("rows") or [])),
        "runner_distinct_token_mints": len(mint_set),
        "runner_signal_span_seconds": runner_span,
        "dominant_runner_token_share": round(dominant_share, 6),
        "unknown_15m_rows": sum(1 for row in wallet.get("rows") or [] if str(as_dict(row).get("outcome_15m") or "").lower() == "unknown"),
        "validation_reasons": validation_reasons(status),
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def validation_reasons(status: str) -> list[str]:
    if status == "repeatability_supported_manual_review":
        return [
            "runner evidence appears across multiple distinct token mints",
            "runner evidence spans more than one short time cluster",
            "manual review is still required before any trust decision",
        ]
    if status == "concentrated_anomaly_hold_review":
        return [
            "runner evidence is concentrated in too few token mints or one dominant cluster",
            "hold out of trust decisions until broader repeatability is observed",
        ]
    if status == "limited_repeatability_hold_review":
        return [
            "runner evidence is present but not broad enough for repeatability support",
            "collect or review more forward rows before any trust decision",
        ]
    return ["no usable runner evidence in the review packet"]


def build_summary(wallets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "validated_wallets": len(wallets),
        "repeatability_supported_wallets": sum(1 for row in wallets if row.get("validation_status") == "repeatability_supported_manual_review"),
        "concentrated_anomaly_wallets": sum(1 for row in wallets if row.get("validation_status") == "concentrated_anomaly_hold_review"),
        "limited_repeatability_wallets": sum(1 for row in wallets if row.get("validation_status") == "limited_repeatability_hold_review"),
        "insufficient_runner_wallets": sum(1 for row in wallets if row.get("validation_status") == "insufficient_runner_evidence"),
        "trust_mutations_allowed": 0,
        "wallet_list_mutations_allowed": 0,
    }


def build_forward_signal_review_validator(*, packet: dict[str, Any], generated_at: float | None = None) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    wallets = [validate_wallet(wallet) for wallet in packet.get("wallets") or [] if isinstance(wallet, dict)]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": packet.get("live_execution_locked") is not False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
        "summary": build_summary(wallets),
        "wallets": wallets,
        "operator_note": (
            "Validator checks concentration and repeatability only. It does not approve promotions, mutate trust, "
            "change wallet lists, or alter execution."
        ),
    }
