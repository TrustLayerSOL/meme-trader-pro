from __future__ import annotations

import json
import time
from typing import Any, Callable

from wallets.forward_market_context import fetch_dexscreener_market_info
from wallets.forward_market_context import normalize_market_info


MODE = "FORWARD_MARKET_SNAPSHOT_CAPTURE_REVIEW_ONLY"
VERSION = "forward_market_snapshot_capture.v1"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def queue_rows(repair_queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in as_list(repair_queue.get("queue"))
        if isinstance(row, dict) and row.get("token_mint")
    ]


def selected_queue_rows(repair_queue: dict[str, Any], *, max_mints: int) -> list[dict[str, Any]]:
    return queue_rows(repair_queue)[: max(0, int(max_mints))]


def build_budget(*, selected_mints: int, max_market_context_calls: int) -> dict[str, Any]:
    selected = max(0, int(selected_mints))
    limit = max(0, int(max_market_context_calls))
    allowed = selected <= limit
    return {
        "selected_mints": selected,
        "estimated_market_context_calls": selected,
        "max_market_context_calls": limit,
        "budget_status": "within_budget" if allowed else "blocked_market_context_cycle_limit",
        "execute_allowed": allowed,
        "block_reason": None if allowed else "selected_mints_exceeds_max_market_context_calls",
    }


def capture_snapshot_for_queue_row(
    row: dict[str, Any],
    *,
    market_provider: Callable[[str], dict[str, Any] | None],
    observed_at: float,
) -> dict[str, Any] | None:
    mint = str(row.get("token_mint") or "")
    info = market_provider(mint)
    snapshot = normalize_market_info(mint, info or {}, observed_at=observed_at)
    if snapshot is None:
        return None
    payload = dict(snapshot.get("payload") or {})
    payload["repair_queue_source"] = "market_snapshot_repair_queue"
    payload["required_snapshot_start_time"] = row.get("required_snapshot_start_time")
    payload["required_snapshot_end_time"] = row.get("required_snapshot_end_time")
    payload["queued_blocked_row_count"] = row.get("blocked_row_count")
    snapshot["payload"] = payload
    snapshot["payload_json"] = json.dumps(payload, sort_keys=True)
    snapshot["repair_queue_capture"] = True
    return snapshot


def build_summary(
    *,
    repair_queue: dict[str, Any],
    selected_rows: list[dict[str, Any]],
    existing_market_snapshots: list[dict[str, Any]],
    captured_snapshots: list[dict[str, Any]],
    execute: bool,
) -> dict[str, Any]:
    return {
        "input_queue_rows": len(queue_rows(repair_queue)),
        "selected_mints": len(selected_rows),
        "dry_run_mints": len(selected_rows) if not execute else 0,
        "snapshots_captured": len(captured_snapshots),
        "provider_misses": len(selected_rows) - len(captured_snapshots) if execute else 0,
        "existing_market_snapshots": len(existing_market_snapshots or []),
        "combined_market_snapshots": len(existing_market_snapshots or []) + len(captured_snapshots),
        "repair_rows_written": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_market_snapshot_capture(
    *,
    repair_queue: dict[str, Any],
    existing_market_snapshots: list[dict[str, Any]],
    market_provider: Callable[[str], dict[str, Any] | None] | None = None,
    execute: bool = False,
    max_mints: int = 10,
    max_market_context_calls: int = 10,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    selected_rows = selected_queue_rows(repair_queue, max_mints=max_mints)
    budget = build_budget(selected_mints=len(selected_rows), max_market_context_calls=max_market_context_calls)
    captured_snapshots: list[dict[str, Any]] = []
    if execute and budget["execute_allowed"]:
        provider = market_provider or fetch_dexscreener_market_info
        for row in selected_rows:
            snapshot = capture_snapshot_for_queue_row(row, market_provider=provider, observed_at=generated_at)
            if snapshot is not None:
                captured_snapshots.append(snapshot)
    combined = [row for row in existing_market_snapshots or [] if isinstance(row, dict)] + captured_snapshots
    return {
        "generated_at": generated_at,
        "run_id": run_id,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "execute": bool(execute),
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "limits": {
            "max_mints": max_mints,
            "max_market_context_calls": max_market_context_calls,
        },
        "budget": budget,
        "summary": build_summary(
            repair_queue=repair_queue,
            selected_rows=selected_rows,
            existing_market_snapshots=existing_market_snapshots,
            captured_snapshots=captured_snapshots,
            execute=execute and budget["execute_allowed"],
        ),
        "selected_queue": selected_rows,
        "captured_snapshots": captured_snapshots,
        "combined_market_snapshots": combined,
        "operator_note": (
            "Market snapshot capture is review-only. It fetches bounded current market snapshots for queued "
            "token mints and writes isolated snapshot files; it does not overwrite canonical market context, "
            "mutate trust, mutate wallet lists, promote wallets, or execute trades."
        ),
    }
