from __future__ import annotations

import time
from typing import Any

from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_ACCOUNT_STATE_PROVIDER_REQUEST_BUNDLE_REVIEW_ONLY"
VERSION = "archival_account_state_provider_probe_request.v1"
RAW_RESPONSE_SAVE_PATH = "data/reports/historical_backfill/raw_provider_responses/archival_account_state_provider_probe_raw.json"

REQUIRED_PROVIDER_CAPABILITIES = [
    "historical_account_state_at_or_before_slot",
    "response_context_slot_returned",
    "jsonParsed_mint_account_data",
]

ACCEPTANCE_CRITERIA = [
    "raw response must be saved exactly before validation",
    "context.slot <= decision_slot",
    "response value must be the requested mint account",
    "parsed mint info must include supply and decimals",
    "current-only account state is not acceptable as historical evidence",
]


def get_probe_target(provider_probe: dict[str, Any]) -> dict[str, Any] | None:
    target = provider_probe.get("probe_target") if isinstance(provider_probe, dict) else None
    if not isinstance(target, dict):
        return None
    token = str(target.get("token_mint") or "").strip()
    decision_slot = safe_int(target.get("decision_slot"), 0)
    if not token or decision_slot <= 0:
        return None
    return {
        "token_mint": token,
        "decision_slot": decision_slot,
        "signature_count": safe_int(target.get("signature_count"), 0),
    }


def build_jsonrpc_payload(token_mint: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            token_mint,
            {
                "encoding": "jsonParsed",
            },
        ],
    }


def build_request_bundle(*, provider_id: str | None, target: dict[str, Any]) -> dict[str, Any]:
    token_mint = str(target.get("token_mint") or "").strip()
    decision_slot = safe_int(target.get("decision_slot"), 0)
    return {
        "version": VERSION,
        "provider_id": provider_id,
        "token_mint": token_mint,
        "decision_slot": decision_slot,
        "requested_historical_context_slot": decision_slot,
        "max_acceptable_context_slot": decision_slot,
        "standard_jsonrpc_payload": build_jsonrpc_payload(token_mint),
        "jsonrpc_payload": build_jsonrpc_payload(token_mint),
        "provider_requirement": (
            "Use an archival provider interface that returns mint account state at or before the requested "
            "decision slot. Standard current-state RPC responses are expected to be rejected if their "
            "context slot is newer than the decision slot."
        ),
        "raw_response_save_path": RAW_RESPONSE_SAVE_PATH,
        "can_mutate_wallet_trust": False,
    }


def build_summary(*, request_bundle: dict[str, Any] | None, request_status: str) -> dict[str, Any]:
    return {
        "request_bundles_prepared": 1 if request_bundle else 0,
        "blocked_request_bundles": 1 if request_status.startswith("blocked_") else 0,
        "provider_calls_performed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "supply_snapshot_imports": 0,
    }


def build_archival_account_state_provider_probe_request_report(
    *,
    provider_probe: dict[str, Any],
    generated_at: float | None = None,
) -> dict[str, Any]:
    target = get_probe_target(provider_probe)
    provider_id = str(provider_probe.get("provider_id") or "").strip() if isinstance(provider_probe, dict) else ""
    blockers: list[str] = []
    request_bundle: dict[str, Any] | None = None
    request_status = "request_bundle_prepared"

    if not target:
        request_status = "blocked_missing_probe_target"
        blockers = ["missing_probe_target"]
    elif not provider_id:
        request_status = "blocked_missing_provider_id"
        blockers = ["missing_provider_id"]
    else:
        request_bundle = build_request_bundle(provider_id=provider_id, target=target)

    validation_command = (
        "./trading_env/bin/python utils/build_archival_account_state_provider_probe.py "
        f"--raw-provider-response-path {RAW_RESPONSE_SAVE_PATH}"
    )

    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "provider_call_performed": False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "supply_snapshot_import_allowed": False,
        "supply_snapshot_imported": False,
        "request_status": request_status,
        "blockers": blockers,
        "required_provider_capabilities": REQUIRED_PROVIDER_CAPABILITIES,
        "acceptance_criteria": ACCEPTANCE_CRITERIA,
        "operator_steps": [
            "Use the request bundle with an archival account-state provider that can answer at or before the decision slot.",
            f"Save provider raw JSON response to {RAW_RESPONSE_SAVE_PATH}.",
            "Run the validation command in this report.",
            "Do not import supply unless a later manual review accepts the preserved response.",
        ],
        "validation_command": validation_command,
        "request_bundle": request_bundle,
        "summary": build_summary(request_bundle=request_bundle, request_status=request_status),
        "operator_note": (
            "This report prepares a manual archival provider request. It does not call a provider, store "
            "secrets, import supply snapshots, mutate wallet trust, or touch execution."
        ),
    }
