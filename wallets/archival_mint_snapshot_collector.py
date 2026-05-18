from __future__ import annotations

import time
from collections import Counter
from typing import Any, Callable

from wallets.wallet_evidence_models import as_dict, safe_int


MODE = "ARCHIVAL_MINT_SUPPLY_SNAPSHOT_COLLECTION_REVIEW_ONLY"
VERSION = "archival_mint_snapshot_collector.v1"


RpcPost = Callable[[str, dict[str, Any], int], dict[str, Any]]


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def ready_requirements(plan: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = plan.get("token_requirements") if isinstance(plan, dict) else []
    return [
        row
        for row in requirements or []
        if isinstance(row, dict) and row.get("status") == "ready_for_archival_supply_fetch" and token_mint(row)
    ]


def ready_candidate_targets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("candidate_rows") if isinstance(plan, dict) else []
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        token = token_mint(row)
        slot = safe_int(row.get("decision_slot"), 0)
        if not token or slot <= 0:
            continue
        key = (token, slot)
        target = grouped.setdefault(
            key,
            {
                "token_mint": token,
                "requested_snapshot_slot": slot,
                "max_acceptable_snapshot_slot": slot,
                "latest_decision_slot": slot,
                "row_count": 0,
                "wallets": set(),
                "transaction_signatures": set(),
                "target_source": "candidate_decision_slot",
            },
        )
        target["row_count"] += 1
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            target["wallets"].add(wallet)
        signature = str(row.get("transaction_signature") or "").strip()
        if signature:
            target["transaction_signatures"].add(signature)

    targets: list[dict[str, Any]] = []
    for target in grouped.values():
        wallets = sorted(target.pop("wallets"))
        signatures = sorted(target.pop("transaction_signatures"))
        target["wallet_count"] = len(wallets)
        target["wallets"] = wallets[:50]
        target["transaction_signature_count"] = len(signatures)
        target["transaction_signatures"] = signatures[:50]
        targets.append(target)
    targets.sort(key=lambda row: (str(row.get("token_mint") or ""), safe_int(row.get("max_acceptable_snapshot_slot"), 0)))
    return targets


def snapshot_targets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_targets = ready_candidate_targets(plan)
    if candidate_targets:
        return candidate_targets
    targets: list[dict[str, Any]] = []
    for row in ready_requirements(plan):
        earliest_slot = safe_int(row.get("earliest_decision_slot"), 0)
        latest_slot = safe_int(row.get("latest_decision_slot"), 0)
        targets.append(
            {
                "token_mint": token_mint(row),
                "requested_snapshot_slot": earliest_slot or None,
                "max_acceptable_snapshot_slot": earliest_slot or None,
                "latest_decision_slot": latest_slot or None,
                "row_count": safe_int(row.get("row_count"), 0),
                "wallet_count": safe_int(row.get("wallet_count"), 0),
                "target_source": "token_earliest_decision_slot",
            }
        )
    return targets


def build_rpc_payload(token: str, request_id: int) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "getAccountInfo",
        "params": [
            token,
            {
                "encoding": "jsonParsed",
            },
        ],
    }


def parsed_mint_info(response: dict[str, Any]) -> dict[str, Any]:
    result = as_dict(response.get("result"))
    value = as_dict(result.get("value"))
    data = value.get("data")
    if not isinstance(data, dict):
        return {}
    parsed = as_dict(data.get("parsed"))
    return as_dict(parsed.get("info"))


def response_slot(response: dict[str, Any]) -> int | None:
    result = as_dict(response.get("result"))
    context = as_dict(result.get("context"))
    slot = safe_int(context.get("slot"), 0)
    return slot if slot > 0 else None


def response_supply(response: dict[str, Any]) -> tuple[str | None, int | None]:
    info = parsed_mint_info(response)
    raw_supply = info.get("supply")
    decimals = safe_int(info.get("decimals"), -1)
    if raw_supply in (None, "") or decimals < 0:
        return None, None
    raw_supply_text = str(raw_supply)
    if safe_int(raw_supply_text, -1) < 0:
        return None, None
    return raw_supply_text, decimals


def build_request(row: dict[str, Any], request_id: int) -> dict[str, Any]:
    token = token_mint(row)
    requested_slot = safe_int(row.get("requested_snapshot_slot"), 0)
    max_slot = safe_int(row.get("max_acceptable_snapshot_slot"), 0)
    latest_slot = safe_int(row.get("latest_decision_slot"), 0)
    return {
        "version": VERSION,
        "token_mint": token,
        "requested_snapshot_slot": requested_slot or None,
        "max_acceptable_snapshot_slot": max_slot or None,
        "latest_decision_slot": latest_slot or None,
        "row_count": safe_int(row.get("row_count"), 0),
        "wallet_count": safe_int(row.get("wallet_count"), 0),
        "target_source": row.get("target_source"),
        "transaction_signature_count": safe_int(row.get("transaction_signature_count"), 0),
        "transaction_signatures": list(row.get("transaction_signatures") or [])[:50],
        "status": "pending_archival_provider",
        "block_reasons": [],
        "jsonrpc_payload": build_rpc_payload(token, request_id),
        "can_mutate_wallet_trust": False,
    }


def collect_snapshot(
    *,
    request: dict[str, Any],
    rpc_url: str,
    rpc_post: RpcPost,
    timeout: int,
) -> dict[str, Any] | None:
    response = rpc_post(rpc_url, request["jsonrpc_payload"], timeout)
    slot = response_slot(response)
    raw_supply, decimals = response_supply(response)
    max_slot = safe_int(request.get("max_acceptable_snapshot_slot"), 0)

    if slot is None:
        request["status"] = "blocked_missing_snapshot_slot"
        request["block_reasons"] = ["missing_snapshot_slot"]
        return None
    if max_slot <= 0:
        request["status"] = "blocked_missing_decision_slot"
        request["block_reasons"] = ["missing_decision_slot"]
        return None
    if slot > max_slot:
        request["status"] = "blocked_snapshot_after_decision_slot"
        request["block_reasons"] = ["snapshot_slot_after_decision_slot"]
        request["snapshot_slot"] = slot
        return None
    if raw_supply is None or decimals is None:
        request["status"] = "blocked_invalid_archival_snapshot"
        request["block_reasons"] = ["invalid_supply_snapshot"]
        request["snapshot_slot"] = slot
        return None

    request["status"] = "archival_snapshot_collected"
    request["snapshot_slot"] = slot
    return {
        "version": VERSION,
        "token_mint": request["token_mint"],
        "slot": slot,
        "requested_snapshot_slot": request.get("requested_snapshot_slot"),
        "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
        "raw_supply": raw_supply,
        "decimals": decimals,
        "source": "archival_rpc_getAccountInfo",
        "decision_time_safe": True,
        "can_mutate_wallet_trust": False,
    }


def build_summary(requests: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in requests)
    block_reasons = Counter(reason for row in requests for reason in row.get("block_reasons") or [])
    return {
        "requirements_scanned": len(requests),
        "requests_prepared": len(requests),
        "snapshots_collected": len(snapshots),
        "blocked_too_new_snapshots": statuses.get("blocked_snapshot_after_decision_slot", 0),
        "blocked_rpc_errors": statuses.get("blocked_rpc_error", 0),
        "pending_archival_provider": statuses.get("pending_archival_provider", 0),
        "tokens_affected": len({row.get("token_mint") for row in requests if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(block_reasons.items())),
    }


def build_archival_mint_snapshot_collection_report(
    *,
    archival_supply_plan: dict[str, Any],
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post: RpcPost | None = None,
    timeout: int = 10,
    generated_at: float | None = None,
) -> dict[str, Any]:
    requests = [build_request(row, idx + 1) for idx, row in enumerate(snapshot_targets(archival_supply_plan))]
    snapshots: list[dict[str, Any]] = []

    if execute:
        for request in requests:
            if not rpc_url or not rpc_post:
                request["status"] = "blocked_rpc_unconfigured"
                request["block_reasons"] = ["missing_archival_rpc_transport"]
                continue
            try:
                snapshot = collect_snapshot(
                    request=request,
                    rpc_url=rpc_url,
                    rpc_post=rpc_post,
                    timeout=timeout,
                )
            except Exception as exc:  # pragma: no cover - defensive provider boundary.
                request["status"] = "blocked_rpc_error"
                request["block_reasons"] = ["rpc_error"]
                request["error"] = str(exc)
                continue
            if snapshot:
                snapshots.append(snapshot)

    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "execute_requested": bool(execute),
        "summary": build_summary(requests, snapshots),
        "requests": requests,
        "snapshots": snapshots,
        "operator_note": (
            "This collector prepares archival mint-account supply snapshot requests. "
            "It only accepts fetched snapshots whose provider context slot is at or before the decision slot."
        ),
    }
