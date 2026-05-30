from __future__ import annotations

import time
from typing import Any

from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_ACCOUNT_STATE_PROVIDER_PROBE_REVIEW_ONLY"
VERSION = "archival_account_state_provider_probe.v1"

TARGET_ACTION = "CONSIDER_ARCHIVAL_ACCOUNT_STATE_PROVIDER"
DEFAULT_PROVIDER_ID = "quicknode_solana_mainnet_archive"


def provider_candidates(provider_evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    providers = provider_evaluation.get("providers") if isinstance(provider_evaluation, dict) else []
    return [
        provider
        for provider in providers or []
        if isinstance(provider, dict)
        and provider.get("manual_probe_required")
        and provider.get("status") == "candidate_needs_manual_probe"
    ]


def probe_targets(pagination_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = pagination_plan.get("rows") if isinstance(pagination_plan, dict) else []
    targets = [
        row
        for row in rows or []
        if isinstance(row, dict)
        and row.get("recommended_action") == TARGET_ACTION
        and safe_int(row.get("decision_slot"), 0) > 0
        and str(row.get("token_mint") or "").strip()
    ]
    targets.sort(key=lambda item: (-safe_int(item.get("signature_count"), 0), str(item.get("token_mint") or "")))
    return targets


def select_provider_id(provider_evaluation: dict[str, Any]) -> str | None:
    candidates = provider_candidates(provider_evaluation)
    if not candidates:
        return None
    return str(candidates[0].get("provider_id") or DEFAULT_PROVIDER_ID)


def select_probe_target(pagination_plan: dict[str, Any]) -> dict[str, Any] | None:
    targets = probe_targets(pagination_plan)
    if not targets:
        return None
    target = targets[0]
    return {
        "version": VERSION,
        "token_mint": str(target.get("token_mint") or "").strip(),
        "decision_slot": safe_int(target.get("decision_slot"), 0),
        "signature_count": safe_int(target.get("signature_count"), 0),
        "recommended_action": TARGET_ACTION,
        "selection_reason": str(target.get("reason") or "provider_probe_candidate"),
    }


def json_path(raw: dict[str, Any], path: list[str]) -> Any:
    current: Any = raw
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_provider_context_slot(raw_provider_response: dict[str, Any]) -> int:
    return safe_int(json_path(raw_provider_response, ["result", "context", "slot"]), 0)


def extract_mint_info(raw_provider_response: dict[str, Any]) -> dict[str, Any]:
    value = json_path(raw_provider_response, ["result", "value"])
    if not isinstance(value, dict):
        return {}
    parsed = json_path(value, ["data", "parsed"])
    if not isinstance(parsed, dict):
        return {}
    info = parsed.get("info")
    if not isinstance(info, dict):
        return {}
    return {
        "parsed_type": parsed.get("type"),
        "mint_supply": info.get("supply"),
        "decimals": info.get("decimals"),
    }


def validate_raw_provider_response(
    *,
    raw_provider_response: dict[str, Any],
    probe_target: dict[str, Any],
) -> tuple[str, list[str], dict[str, Any]]:
    decision_slot = safe_int(probe_target.get("decision_slot"), 0)
    provider_context_slot = extract_provider_context_slot(raw_provider_response)
    mint_info = extract_mint_info(raw_provider_response)
    parsed_type = mint_info.get("parsed_type")
    mint_supply = mint_info.get("mint_supply")

    validation = {
        "version": VERSION,
        "token_mint": probe_target.get("token_mint"),
        "decision_slot": decision_slot or None,
        "provider_context_slot": provider_context_slot or None,
        "decision_time_safe": False,
        "parsed_type": parsed_type,
        "mint_supply": None if mint_supply is None else str(mint_supply),
        "decimals": mint_info.get("decimals"),
    }

    if decision_slot <= 0:
        return "blocked_missing_decision_slot", ["missing_decision_slot"], validation
    if provider_context_slot <= 0:
        return "blocked_missing_provider_context_slot", ["missing_provider_context_slot"], validation
    if provider_context_slot > decision_slot:
        return (
            "rejected_provider_response_after_decision_slot",
            ["provider_context_slot_after_decision_slot"],
            validation,
        )
    validation["decision_time_safe"] = True
    if not mint_info:
        return "blocked_missing_parsed_mint_data", ["missing_parsed_mint_data"], validation
    if parsed_type != "mint":
        return "blocked_not_mint_account", ["provider_response_not_mint_account"], validation
    if mint_supply in (None, ""):
        return "blocked_missing_mint_supply", ["missing_mint_supply"], validation
    return "provider_snapshot_ready_for_manual_review", [], validation


def build_summary(
    *,
    target_count: int,
    raw_response_evaluated: bool,
    probe_status: str,
) -> dict[str, Any]:
    return {
        "probe_targets": int(target_count),
        "raw_response_evaluated": bool(raw_response_evaluated),
        "snapshots_ready_for_manual_review": 1 if probe_status == "provider_snapshot_ready_for_manual_review" else 0,
        "rejected_future_slot_responses": 1 if probe_status == "rejected_provider_response_after_decision_slot" else 0,
        "blocked_responses": 1 if probe_status.startswith("blocked_") else 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "supply_snapshot_imports": 0,
    }


def build_archival_account_state_provider_probe_report(
    *,
    pagination_plan: dict[str, Any],
    provider_evaluation: dict[str, Any],
    raw_provider_response: dict[str, Any] | None = None,
    raw_provider_response_preserved: bool = False,
    generated_at: float | None = None,
) -> dict[str, Any]:
    provider_id = select_provider_id(provider_evaluation)
    target = select_probe_target(pagination_plan)
    target_count = len(probe_targets(pagination_plan))
    blockers: list[str] = []
    validation: dict[str, Any] = {"version": VERSION, "decision_time_safe": False}

    if not provider_id:
        probe_status = "blocked_no_candidate_provider"
        blockers.append("no_manual_probe_provider_candidate")
    elif not target:
        probe_status = "blocked_no_provider_probe_target"
        blockers.append("no_provider_recommended_token")
    elif raw_provider_response is None:
        probe_status = "dry_run_probe_target_selected"
    else:
        probe_status, blockers, validation = validate_raw_provider_response(
            raw_provider_response=raw_provider_response,
            probe_target=target,
        )

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
        "raw_provider_response_preserved": bool(raw_provider_response_preserved),
        "provider_id": provider_id,
        "probe_target": target,
        "probe_status": probe_status,
        "blockers": blockers,
        "validation": validation,
        "summary": build_summary(
            target_count=target_count,
            raw_response_evaluated=raw_provider_response is not None,
            probe_status=probe_status,
        ),
        "operator_note": (
            "This probe validates one candidate historical account-state response for manual review only. "
            "It rejects future-slot responses and never imports supply snapshots automatically."
        ),
    }
