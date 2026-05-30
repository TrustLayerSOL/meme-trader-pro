from __future__ import annotations

import time
from typing import Any


MODE = "ARCHIVAL_MINT_SNAPSHOT_PROVIDER_CAPTURE_REVIEW_ONLY"
VERSION = "archival_mint_snapshot_provider_capture.v1"


def safe_provider_error(error: BaseException) -> str:
    return error.__class__.__name__


def request_chunks(request_bundle_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = request_bundle_report.get("batch_request_chunks") if isinstance(request_bundle_report, dict) else []
    chunks: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        payload = row.get("jsonrpc_payload")
        if not isinstance(payload, list) or not payload:
            continue
        chunks.append(
            {
                "index": row.get("index"),
                "path": row.get("path"),
                "request_count": len(payload),
                "request_ids": list(row.get("request_ids") or []),
                "jsonrpc_payload": payload,
            }
        )
    return chunks


def normalize_provider_response(raw_response: Any) -> list[dict[str, Any]]:
    if isinstance(raw_response, list):
        return [row for row in raw_response if isinstance(row, dict)]
    if isinstance(raw_response, dict):
        responses = raw_response.get("responses")
        if isinstance(responses, list):
            return [row for row in responses if isinstance(row, dict)]
        if "result" in raw_response or "error" in raw_response:
            return [raw_response]
    return []


def build_summary(
    *,
    chunks: list[dict[str, Any]],
    provider_calls_performed: int,
    raw_response_chunks_preserved: int,
    combined_responses: int,
    capture_status: str,
) -> dict[str, Any]:
    return {
        "request_chunks_available": len(chunks),
        "requests_available": sum(int(row.get("request_count") or 0) for row in chunks),
        "provider_calls_performed": provider_calls_performed,
        "raw_response_chunks_preserved": raw_response_chunks_preserved,
        "combined_responses": combined_responses,
        "captures_ready_for_saved_import": 1 if capture_status == "provider_batch_responses_captured_for_saved_import" else 0,
        "blocked_captures": 1 if capture_status.startswith("blocked_") else 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "wallet_trust_mutations": 0,
        "supply_snapshot_imports": 0,
    }


def build_archival_mint_snapshot_provider_capture_report(
    *,
    request_bundle_report: dict[str, Any],
    execute: bool = False,
    rpc_url: str | None = None,
    rpc_post=None,
    timeout: int = 10,
    generated_at: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    chunks = request_chunks(request_bundle_report)
    endpoint_configured = bool(str(rpc_url or "").strip())
    blockers: list[str] = []
    provider_calls_performed = 0
    raw_response_chunks_preserved = 0
    raw_chunks: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    provider_call_error: str | None = None
    raw_batch: dict[str, Any] | None = None

    if not chunks:
        capture_status = "blocked_missing_request_chunks"
        blockers.append("missing_request_chunks")
    elif not endpoint_configured:
        capture_status = "blocked_missing_archival_provider_rpc_url"
        blockers.append("missing_archival_provider_rpc_url")
    elif not execute:
        capture_status = "dry_run_capture_not_executed"
    elif rpc_post is None:
        capture_status = "blocked_missing_rpc_post_handler"
        blockers.append("missing_rpc_post_handler")
    else:
        capture_status = "provider_batch_responses_captured_for_saved_import"
        for chunk in chunks:
            try:
                provider_calls_performed += 1
                raw_response = rpc_post(str(rpc_url or ""), chunk["jsonrpc_payload"], timeout)
            except Exception as exc:  # pragma: no cover - exercised through tests via report status
                capture_status = "blocked_provider_call_failed"
                provider_call_error = safe_provider_error(exc)
                blockers.append("provider_call_failed")
                raw_chunks = []
                responses = []
                raw_response_chunks_preserved = 0
                break
            chunk_responses = normalize_provider_response(raw_response)
            responses.extend(chunk_responses)
            raw_chunks.append(
                {
                    "chunk_index": chunk.get("index"),
                    "request_count": chunk.get("request_count"),
                    "request_ids": list(chunk.get("request_ids") or []),
                    "response_count": len(chunk_responses),
                    "raw_response": raw_response,
                }
            )
            raw_response_chunks_preserved += 1
        if capture_status == "provider_batch_responses_captured_for_saved_import":
            raw_batch = {
                "version": VERSION,
                "source": "archival_mint_snapshot_provider_capture",
                "responses": responses,
                "chunks": raw_chunks,
                "operator_note": (
                    "Saved archival provider responses only. Importer still validates each response "
                    "against its request id and decision-time slot boundary before creating evidence."
                ),
            }

    report = {
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
        "capture_status": capture_status,
        "provider_call_error": provider_call_error,
        "blockers": blockers,
        "request": {
            "chunk_count": len(chunks),
            "request_count": sum(int(row.get("request_count") or 0) for row in chunks),
            "raw_response_save_path": request_bundle_report.get("raw_response_save_path")
            if isinstance(request_bundle_report, dict)
            else None,
        },
        "captured_chunks": [
            {
                "chunk_index": row.get("chunk_index"),
                "request_count": row.get("request_count"),
                "response_count": row.get("response_count"),
            }
            for row in raw_chunks
        ],
        "summary": build_summary(
            chunks=chunks,
            provider_calls_performed=provider_calls_performed,
            raw_response_chunks_preserved=raw_response_chunks_preserved,
            combined_responses=len(responses),
            capture_status=capture_status,
        ),
        "operator_note": (
            "This lane captures the existing archival mint snapshot request chunks for saved-response import. "
            "It does not import supply, score wallets, mutate trust, or touch live execution."
        ),
    }
    return report, raw_batch
