from __future__ import annotations

import time
from typing import Any

from wallets.archival_account_state_provider_probe import validate_raw_provider_response
from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_ACCOUNT_STATE_PROVIDER_RESPONSE_CAPTURE_REVIEW_ONLY"
VERSION = "archival_account_state_provider_response_capture.v1"


def get_request_bundle(request_report: dict[str, Any]) -> dict[str, Any] | None:
    bundle = request_report.get("request_bundle") if isinstance(request_report, dict) else None
    if not isinstance(bundle, dict):
        return None
    token_mint = str(bundle.get("token_mint") or "").strip()
    decision_slot = safe_int(bundle.get("decision_slot"), 0)
    payload = bundle.get("jsonrpc_payload") or bundle.get("standard_jsonrpc_payload")
    if not token_mint or decision_slot <= 0 or not isinstance(payload, dict):
        return None
    return {
        **bundle,
        "token_mint": token_mint,
        "decision_slot": decision_slot,
        "jsonrpc_payload": payload,
    }


def probe_target_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "token_mint": str(bundle.get("token_mint") or "").strip(),
        "decision_slot": safe_int(bundle.get("decision_slot"), 0),
        "signature_count": safe_int(bundle.get("signature_count"), 0),
    }


def safe_provider_error(error: BaseException) -> str:
    return f"{error.__class__.__name__}"


def execute_provider_request(
    *,
    rpc_url: str,
    payload: dict[str, Any],
    rpc_post,
    timeout: int,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = rpc_post(rpc_url, payload, timeout)
    except Exception as exc:  # pragma: no cover - exercised through report status
        return None, safe_provider_error(exc)
    if not isinstance(response, dict):
        return None, "invalid_provider_response_type"
    return response, None


def capture_status_from_validation(validation_status: str) -> str:
    if validation_status == "provider_snapshot_ready_for_manual_review":
        return "provider_response_captured_ready_for_manual_review"
    if validation_status.startswith("rejected_"):
        return "provider_response_captured_rejected"
    if validation_status.startswith("blocked_"):
        return "provider_response_captured_blocked"
    return "provider_response_captured_unknown"


def build_summary(
    *,
    capture_status: str,
    validation_status: str | None,
    provider_call_performed: bool,
    raw_provider_response_preserved: bool,
) -> dict[str, Any]:
    return {
        "captures_ready_for_manual_review": 1 if capture_status == "provider_response_captured_ready_for_manual_review" else 0,
        "blocked_captures": 1 if capture_status.startswith("blocked_") else 0,
        "captured_blocked_by_validation": 1 if capture_status == "provider_response_captured_blocked" else 0,
        "provider_calls_performed": 1 if provider_call_performed else 0,
        "raw_responses_preserved": 1 if raw_provider_response_preserved else 0,
        "rejected_future_slot_responses": 1 if validation_status == "rejected_provider_response_after_decision_slot" else 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "wallet_trust_mutations": 0,
        "supply_snapshot_imports": 0,
    }


def build_archival_account_state_provider_response_capture_report(
    *,
    request_report: dict[str, Any],
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=None,
    timeout: int = 10,
    raw_provider_response: dict[str, Any] | None = None,
    raw_provider_response_preserved: bool = False,
    generated_at: float | None = None,
) -> dict[str, Any]:
    bundle = get_request_bundle(request_report)
    endpoint_configured = bool(str(rpc_url or "").strip())
    blockers: list[str] = []
    validation: dict[str, Any] = {"version": VERSION, "decision_time_safe": False}
    validation_status: str | None = None
    provider_call_performed = False
    provider_call_error: str | None = None

    if not bundle:
        capture_status = "blocked_missing_request_bundle"
        blockers.append("missing_request_bundle")
    elif not endpoint_configured:
        capture_status = "blocked_missing_archival_provider_rpc_url"
        blockers.append("missing_archival_provider_rpc_url")
    elif not execute:
        capture_status = "dry_run_capture_not_executed"
    else:
        payload = bundle.get("jsonrpc_payload")
        if raw_provider_response is None:
            if rpc_post is None:
                capture_status = "blocked_missing_rpc_post_handler"
                blockers.append("missing_rpc_post_handler")
            else:
                provider_call_performed = True
                raw_provider_response, provider_call_error = execute_provider_request(
                    rpc_url=str(rpc_url or ""),
                    payload=payload,
                    rpc_post=rpc_post,
                    timeout=timeout,
                )
                if provider_call_error:
                    capture_status = "blocked_provider_call_failed"
                    blockers.append("provider_call_failed")
                else:
                    validation_status, validation_blockers, validation = validate_raw_provider_response(
                        raw_provider_response=raw_provider_response or {},
                        probe_target=probe_target_from_bundle(bundle),
                    )
                    blockers.extend(validation_blockers)
                    capture_status = capture_status_from_validation(validation_status)
        else:
            provider_call_performed = True
            validation_status, validation_blockers, validation = validate_raw_provider_response(
                raw_provider_response=raw_provider_response,
                probe_target=probe_target_from_bundle(bundle),
            )
            blockers.extend(validation_blockers)
            capture_status = capture_status_from_validation(validation_status)

    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "supply_snapshot_import_allowed": False,
        "supply_snapshot_imported": False,
        "execute_requested": bool(execute),
        "provider_endpoint_configured": endpoint_configured,
        "provider_call_performed": bool(provider_call_performed),
        "raw_provider_response_preserved": bool(raw_provider_response_preserved),
        "capture_status": capture_status,
        "validation_status": validation_status,
        "provider_call_error": provider_call_error,
        "blockers": blockers,
        "request": {
            "provider_id": None if not bundle else bundle.get("provider_id"),
            "token_mint": None if not bundle else bundle.get("token_mint"),
            "decision_slot": None if not bundle else safe_int(bundle.get("decision_slot"), 0),
            "max_acceptable_context_slot": None if not bundle else safe_int(bundle.get("max_acceptable_context_slot"), 0),
            "method": None if not bundle else (bundle.get("jsonrpc_payload") or {}).get("method"),
        },
        "validation": validation,
        "summary": build_summary(
            capture_status=capture_status,
            validation_status=validation_status,
            provider_call_performed=provider_call_performed,
            raw_provider_response_preserved=raw_provider_response_preserved,
        ),
        "operator_note": (
            "This lane captures one archival account-state provider response for review only. "
            "It stores no provider URL, imports no supply snapshots, and leaves wallet trust unchanged."
        ),
    }
