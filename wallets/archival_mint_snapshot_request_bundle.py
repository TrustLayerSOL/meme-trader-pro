from __future__ import annotations

import time
from collections import Counter
from pathlib import PurePosixPath
from typing import Any


MODE = "ARCHIVAL_MINT_SNAPSHOT_REQUEST_BUNDLE_REVIEW_ONLY"
VERSION = "archival_mint_snapshot_request_bundle.v1"


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


def normalize_chunk_size(batch_chunk_size: int | None) -> int:
    try:
        size = int(batch_chunk_size or 0)
    except (TypeError, ValueError):
        size = 0
    return size if size > 0 else 100


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if not items:
        return []
    return [items[index : index + size] for index in range(0, len(items), size)]


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


def chunk_path(batch_request_path: str, index: int) -> str:
    path = PurePosixPath(batch_request_path)
    suffix = path.suffix or ".json"
    stem = path.name[: -len(suffix)] if path.name.endswith(suffix) else path.name
    return str(path.with_name(f"{stem}.part{index:03d}{suffix}"))


def build_batch_request_chunks(requests: list[dict[str, Any]], batch_request_path: str, chunk_size: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for index, rows in enumerate(chunked(requests, chunk_size), start=1):
        payloads = [row["jsonrpc_payload"] for row in rows]
        request_ids = [str(payload.get("id") or "") for payload in payloads if isinstance(payload, dict)]
        chunks.append(
            {
                "index": index,
                "path": chunk_path(batch_request_path, index),
                "request_count": len(rows),
                "request_ids": request_ids,
                "first_request_id": request_ids[0] if request_ids else None,
                "last_request_id": request_ids[-1] if request_ids else None,
                "jsonrpc_payload": payloads,
            }
        )
    return chunks


def build_summary(requests: list[dict[str, Any]], *, chunk_count: int = 0, chunk_size: int = 100) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in requests)
    return {
        "requests_bundled": len(requests),
        "target_tokens": len({row.get("token_mint") for row in requests if row.get("token_mint")}),
        "provider_calls_performed": 0,
        "request_packet_ready": 1 if requests else 0,
        "request_chunk_count": chunk_count,
        "max_requests_per_chunk": chunk_size,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
    }


def expected_response_rows(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for request in requests:
        payload = request.get("jsonrpc_payload") if isinstance(request.get("jsonrpc_payload"), dict) else {}
        rows.append(
            {
                "request_id": str(payload.get("id") or ""),
                "token_mint": str(request.get("token_mint") or "").strip(),
                "max_acceptable_snapshot_slot": request.get("max_acceptable_snapshot_slot"),
            }
        )
    return rows


def build_response_template(requests: list[dict[str, Any]], raw_response_path: str) -> dict[str, Any]:
    return {
        "responses": [],
        "expected_responses": expected_response_rows(requests),
        "raw_response_save_path": raw_response_path,
        "operator_note": (
            "Paste provider JSON-RPC responses into the responses array or replace this template with "
            "the provider's batch response. Each response must preserve its request id."
        ),
    }


def build_archival_mint_snapshot_request_bundle_report(
    *,
    snapshot_collection_report: dict[str, Any],
    raw_response_path: str = "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
    batch_request_path: str = "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_request.json",
    response_template_path: str = "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_response_template.json",
    batch_chunk_size: int = 100,
    allowed_token_mints: set[str] | list[str] | tuple[str, ...] | None = None,
    source_filter: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    all_requests = pending_requests(snapshot_collection_report)
    allowed_tokens = normalize_allowed_token_mints(allowed_token_mints)
    requests = filter_requests_by_token_mints(all_requests, allowed_tokens)
    batch_payload = [row["jsonrpc_payload"] for row in requests]
    chunk_size = normalize_chunk_size(batch_chunk_size)
    batch_chunks = build_batch_request_chunks(requests, batch_request_path, chunk_size)
    summary = build_summary(requests, chunk_count=len(batch_chunks), chunk_size=chunk_size)
    summary["source_filter"] = source_filter
    summary["allowed_token_count"] = len(allowed_tokens) if allowed_tokens is not None else None
    summary["filtered_out_requests"] = len(all_requests) - len(requests)
    response_import_command = (
        "./trading_env/bin/python utils/import_archival_mint_supply_snapshots.py "
        f"--raw-response-path {raw_response_path}"
    )
    post_import_commands = [
        response_import_command,
        "./trading_env/bin/python utils/build_archival_supply_evidence.py",
        "./trading_env/bin/python utils/build_score_ready_market_context.py",
        "./trading_env/bin/python utils/build_proof_readiness_blocker_reduction.py",
    ]
    return {
        "generated_at": time.time() if generated_at is None else float(generated_at),
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "provider_calls_performed": False,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": summary,
        "source_collection_mode": snapshot_collection_report.get("mode") if isinstance(snapshot_collection_report, dict) else None,
        "batch_request_save_path": batch_request_path,
        "response_template_save_path": response_template_path,
        "raw_response_save_path": raw_response_path,
        "response_import_command": response_import_command,
        "post_import_commands": post_import_commands,
        "batch_jsonrpc_payload": batch_payload,
        "batch_request_chunks": batch_chunks,
        "response_template": build_response_template(requests, raw_response_path),
        "requests": requests,
        "operator_note": (
            "This bundle prepares saved-response provider handoff data only. "
            "It performs no provider calls and cannot mutate wallet trust or trading state."
        ),
    }
