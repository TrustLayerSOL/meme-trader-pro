"""Invariant checks for production lifecycle materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

FULL_PATH_REQUIRED_FLAGS = (
    "birth_verified",
    "curve_verified",
    "curve_state_decoded",
    "progress_available",
    "market_cap_available",
    "trade_flow_available",
    "holder_dev_available",
    "migration_seen",
    "pool_verified",
    "post_migration_pool_ready_verified",
    "quote_ready_verified",
)

@dataclass(frozen=True)
class InvariantViolation:
    code: str
    severity: str
    details: dict[str, Any]


def _bool(row: Mapping[str, Any], key: str) -> bool:
    value = row.get(key)
    if value is True:
        return True
    if isinstance(value, str) and value.lower() in {"1", "true", "yes"}:
        return True
    return bool(value) if isinstance(value, int) else False


def check_lifecycle_invariants(row: Mapping[str, Any]) -> list[InvariantViolation]:
    violations: list[InvariantViolation] = []
    if _bool(row, "decision_time_safe") and _bool(row, "replay_source"):
        violations.append(InvariantViolation("decision_safe_replay_source", "critical", dict(row)))
    if _bool(row, "migration_seen") and not (row.get("pool_address") or row.get("pool_or_pair_address")):
        violations.append(InvariantViolation("migration_seen_without_pool_address", "critical", dict(row)))
    if _bool(row, "quote_ready_verified") and not (row.get("quote_asset") or row.get("quote_mint")):
        violations.append(InvariantViolation("quote_ready_without_quote_identity", "critical", dict(row)))
    if _bool(row, "curve_state_decoded") and not _bool(row, "curve_verified"):
        violations.append(InvariantViolation("curve_decoded_without_curve_verified", "high", dict(row)))
    if _bool(row, "decision_safe_full_path"):
        missing = [flag for flag in FULL_PATH_REQUIRED_FLAGS if not _bool(row, flag)]
        if missing:
            violations.append(InvariantViolation("full_path_missing_required_flags", "critical", {"missing": missing, **dict(row)}))
        if _bool(row, "replay_source"):
            violations.append(InvariantViolation("full_path_uses_replay_source", "critical", dict(row)))
    return violations


def feature_status(value: Any, *, attempted: bool = True, source_gap: bool = False, parser_rejected: bool = False) -> tuple[str, str | None]:
    if value not in (None, "", False):
        return "available", None
    if source_gap:
        return "source_gap", "source_gap"
    if parser_rejected:
        return "unavailable", "parser_rejected_unsafe_evidence"
    if not attempted:
        return "not_attempted", "not_attempted"
    return "unavailable", "not_observed"
