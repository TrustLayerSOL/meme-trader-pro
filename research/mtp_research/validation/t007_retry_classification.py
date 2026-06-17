"""Retry/failure classification for Pump.fun curve account visibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class CurveProbeClassification:
    event_type: str
    status: str
    final: bool
    reason: str
    retry_after_ms: int | None = None


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.lower() in {"1", "true", "yes", "y"}:
        return True
    return False


def classify_curve_probe(row: Mapping[str, Any], *, retry_budget_exhausted: bool | None = None) -> CurveProbeClassification:
    status = str(row.get("decode_status") or row.get("status") or row.get("curve_probe_status") or "").lower()
    reason = str(row.get("reason") or row.get("error") or row.get("decode_error") or "").lower()
    decoded = _truthy(row.get("progress_decoded")) or _truthy(row.get("decoded")) or status in {"decoded", "ok", "success"}
    account_found = row.get("account_found")
    if decoded:
        return CurveProbeClassification("curve_state_decoded", "verified", True, "decoded")
    not_found = account_found is False or "account_not_found" in status or "account not found" in reason or "could not find account" in reason
    unsupported = "unsupported" in status or "unknown_layout" in status or "unsupported" in reason or "discriminator" in reason
    exhausted = bool(retry_budget_exhausted) or _truthy(row.get("retry_budget_exhausted")) or _truthy(row.get("final"))
    if not_found and not exhausted:
        return CurveProbeClassification("curve_account_not_found_retry", "visibility_delay_retry", False, "account_not_found_retry", 250)
    if not_found:
        return CurveProbeClassification("curve_account_not_found_final", "failed", True, "account_not_found_final")
    if unsupported:
        return CurveProbeClassification("curve_state_decode_failed", "unsupported_layout", True, "unsupported_layout")
    return CurveProbeClassification("curve_state_decode_failed", "failed", True, reason or "decode_failed_final")
