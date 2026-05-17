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
            "token_mint": str(request.get("token_mint") or "").strip(),
            "slot": slot,
            "requested_snapshot_slot": request.get("requested_snapshot_slot"),
            "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
            "raw_supply": raw_supply,
            "decimals": decimals,
            "source": "saved_archival_rpc_getAccountInfo_response",
            "decision_time_safe": True,
            "can_mutate_wallet_trust": False,
        },
        "archival_snapshot_imported",
        [],
    )


def build_summary(
    *,
    requests: list[dict[str, Any]],
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
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
    }


def build_archival_mint_snapshot_response_import_report(
    *,
    snapshot_collection_report: dict[str, Any],
    raw_provider_response: Any,
    generated_at: float | None = None,
) -> dict[str, Any]:
    requests = pending_requests(snapshot_collection_report)
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
                    "token_mint": token_mint,
                    "request_id": rid,
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
                "token_mint": token_mint,
                "request_id": rid,
                "status": status,
                "block_reasons": block_reasons,
                "snapshot_slot": snapshot.get("slot") if snapshot else response_slot(response),
                "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
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
