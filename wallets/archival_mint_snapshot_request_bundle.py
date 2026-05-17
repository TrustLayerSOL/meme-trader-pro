from __future__ import annotations

import time
from collections import Counter
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


def build_summary(requests: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in requests)
    return {
        "requests_bundled": len(requests),
        "target_tokens": len({row.get("token_mint") for row in requests if row.get("token_mint")}),
        "provider_calls_performed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
        "status_counts": dict(sorted(statuses.items())),
    }


def build_archival_mint_snapshot_request_bundle_report(
    *,
    snapshot_collection_report: dict[str, Any],
    raw_response_path: str = "data/reports/historical_backfill/raw_provider_responses/archival_mint_supply_batch_raw.json",
    generated_at: float | None = None,
) -> dict[str, Any]:
    requests = pending_requests(snapshot_collection_report)
    batch_payload = [row["jsonrpc_payload"] for row in requests]
    response_import_command = (
        "./trading_env/bin/python utils/import_archival_mint_supply_snapshots.py "
        f"--raw-response-path {raw_response_path}"
    )
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
        "summary": build_summary(requests),
        "source_collection_mode": snapshot_collection_report.get("mode") if isinstance(snapshot_collection_report, dict) else None,
        "raw_response_save_path": raw_response_path,
        "response_import_command": response_import_command,
        "batch_jsonrpc_payload": batch_payload,
        "requests": requests,
        "operator_note": (
            "This bundle prepares saved-response provider handoff data only. "
            "It performs no provider calls and cannot mutate wallet trust or trading state."
        ),
    }
