from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.archival_mint_snapshot_collector import response_slot, response_supply
from wallets.wallet_evidence_models import safe_int


MODE = "ARCHIVAL_MINT_SNAPSHOT_RESPONSE_IMPORT_REVIEW_ONLY"
VERSION = "archival_mint_snapshot_response_import.v1"


def pending_requests(snapshot_collection_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = snapshot_collection_report.get("requests") if isinstance(snapshot_collection_report, dict) else []
    requests: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        payload = row.get("jsonrpc_payload")
        token_mint = str(row.get("token_mint") or "").strip()
        if row.get("status") != "pending_archival_provider" or not token_mint or not isinstance(payload, dict):
            continue
        requests.append(row)
    return requests


def normalize_allowed_token_mints(allowed_token_mints: set[str] | list[str] | tuple[str, ...] | None) -> set[str] | None:
    if allowed_token_mints is None:
        return None
    return {str(token).strip() for token in allowed_token_mints if str(token).strip()}


def filter_requests_by_token_mints(requests: list[dict[str, Any]], allowed_token_mints: set[str] | None) -> list[dict[str, Any]]:
    if allowed_token_mints is None:
        return requests
    if not allowed_token_mints:
        return []
    return [row for row in requests if str(row.get("token_mint") or "").strip() in allowed_token_mints]


def normalize_raw_responses(raw_provider_response: Any) -> list[dict[str, Any]]:
    if isinstance(raw_provider_response, list):
        return [row for row in raw_provider_response if isinstance(row, dict)]
    if isinstance(raw_provider_response, dict):
        responses = raw_provider_response.get("responses")
        if isinstance(responses, list):
            return [row for row in responses if isinstance(row, dict)]
        if "result" in raw_provider_response:
            return [raw_provider_response]
    return []


def response_id(response: dict[str, Any]) -> str:
    return str(response.get("id") or "")


def request_id(request: dict[str, Any]) -> str:
    payload = request.get("jsonrpc_payload")
    return str(payload.get("id") if isinstance(payload, dict) else "")


def build_snapshot(request: dict[str, Any], response: dict[str, Any]) -> tuple[dict[str, Any] | None, str, list[str]]:
    slot = response_slot(response)
    raw_supply, decimals = response_supply(response)
    max_slot = safe_int(request.get("max_acceptable_snapshot_slot"), 0)

    if slot is None:
        return None, "blocked_missing_snapshot_slot", ["missing_snapshot_slot"]
    if max_slot <= 0:
        return None, "blocked_missing_decision_slot", ["missing_decision_slot"]
    if slot > max_slot:
        return None, "blocked_snapshot_after_decision_slot", ["snapshot_slot_after_decision_slot"]
    if raw_supply is None or decimals is None:
        return None, "blocked_invalid_archival_snapshot", ["invalid_supply_snapshot"]

    return (
        {
            "version": VERSION,
            "evidence_key": request.get("evidence_key"),
            "request_id": request_id(request),
            "token_mint": str(request.get("token_mint") or "").strip(),
            "slot": slot,
            "provider_response_slot": slot,
            "requested_snapshot_slot": request.get("requested_snapshot_slot"),
            "requested_snapshot_time": request.get("requested_snapshot_time"),
            "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
            "raw_supply": raw_supply,
            "decimals": decimals,
            "source": "saved_archival_rpc_getAccountInfo_response",
            "provider_source": "saved_archival_rpc_getAccountInfo_response",
            "provider_metadata": {
                "response_id": response_id(response),
                "response_context_slot": slot,
                "source": "saved_response_file",
            },
            "wallets": list(request.get("wallets") or []),
            "transaction_signatures": list(request.get("transaction_signatures") or []),
            "candidate_references": list(request.get("candidate_references") or []),
            "decision_time_safe": True,
            "can_mutate_wallet_trust": False,
        },
        "archival_snapshot_imported",
        [],
    )


def build_summary(
    *,
    requests: list[dict[str, Any]],
    all_requests_count: int,
    allowed_token_count: int | None,
    source_filter: str | None,
    raw_responses: list[dict[str, Any]],
    import_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in import_rows)
    block_reasons = Counter(reason for row in import_rows for reason in row.get("block_reasons") or [])
    return {
        "requests_scanned": len(requests),
        "raw_responses_scanned": len(raw_responses),
        "snapshots_imported": len(snapshots),
        "blocked_too_new_snapshots": statuses.get("blocked_snapshot_after_decision_slot", 0),
        "blocked_missing_response": statuses.get("blocked_missing_response", 0),
        "blocked_invalid_snapshot_records": (
            statuses.get("blocked_missing_snapshot_slot", 0)
            + statuses.get("blocked_missing_decision_slot", 0)
            + statuses.get("blocked_invalid_archival_snapshot", 0)
        ),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "allowed_token_count": allowed_token_count,
        "filtered_out_requests": all_requests_count - len(requests),
        "source_filter": source_filter,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
    }


def build_archival_mint_snapshot_response_import_report(
    *,
    snapshot_collection_report: dict[str, Any],
    raw_provider_response: Any,
    allowed_token_mints: set[str] | list[str] | tuple[str, ...] | None = None,
    source_filter: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    all_requests = pending_requests(snapshot_collection_report)
    allowed_tokens = normalize_allowed_token_mints(allowed_token_mints)
    requests = filter_requests_by_token_mints(all_requests, allowed_tokens)
    raw_responses = normalize_raw_responses(raw_provider_response)
    responses_by_id = {response_id(row): row for row in raw_responses if response_id(row)}
    import_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []

    for request in requests:
        rid = request_id(request)
        token_mint = str(request.get("token_mint") or "").strip()
        response = responses_by_id.get(rid)
        if response is None:
            import_rows.append(
                {
                    "version": VERSION,
                    "evidence_key": request.get("evidence_key"),
                    "token_mint": token_mint,
                    "request_id": rid,
                    "requested_snapshot_slot": request.get("requested_snapshot_slot"),
                    "requested_snapshot_time": request.get("requested_snapshot_time"),
                    "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
                    "wallets": list(request.get("wallets") or []),
                    "transaction_signatures": list(request.get("transaction_signatures") or []),
                    "candidate_references": list(request.get("candidate_references") or []),
                    "status": "blocked_missing_response",
                    "block_reasons": ["missing_provider_response"],
                    "decision_time_safe": False,
                }
            )
            continue
        snapshot, status, block_reasons = build_snapshot(request, response)
        import_rows.append(
            {
                "version": VERSION,
                "evidence_key": request.get("evidence_key"),
                "token_mint": token_mint,
                "request_id": rid,
                "status": status,
                "block_reasons": block_reasons,
                "snapshot_slot": snapshot.get("slot") if snapshot else response_slot(response),
                "provider_response_slot": snapshot.get("provider_response_slot") if snapshot else response_slot(response),
                "requested_snapshot_slot": request.get("requested_snapshot_slot"),
                "requested_snapshot_time": request.get("requested_snapshot_time"),
                "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
                "wallets": list(request.get("wallets") or []),
                "transaction_signatures": list(request.get("transaction_signatures") or []),
                "candidate_references": list(request.get("candidate_references") or []),
                "decision_time_safe": bool(snapshot),
            }
        )
        if snapshot:
            snapshots.append(snapshot)

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
        "provider_calls_performed": False,
        "summary": build_summary(
            requests=requests,
            all_requests_count=len(all_requests),
            allowed_token_count=len(allowed_tokens) if allowed_tokens is not None else None,
            source_filter=source_filter,
            raw_responses=raw_responses,
            import_rows=import_rows,
            snapshots=snapshots,
        ),
        "import_rows": import_rows,
        "snapshots": snapshots,
        "operator_note": (
            "This importer accepts saved archival mint-account responses only when the provider context slot "
            "is at or before the decision slot. Current/future responses remain blocked."
        ),
    }
