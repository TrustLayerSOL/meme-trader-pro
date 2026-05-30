from __future__ import annotations

import json
import time
from typing import Any, Callable

from wallets.forward_market_context import fetch_dexscreener_market_info
from wallets.forward_market_context import normalize_market_info
from wallets.wallet_evidence_models import safe_float


MODE = "CANDIDATE_BOUNDED_SNAPSHOT_CAPTURE_REVIEW_ONLY"
VERSION = "candidate_bounded_snapshot_capture.v1"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def queue_rows(outcome_completion: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    seen: set[tuple[str, float | None, float | None]] = set()
    for row in as_list(outcome_completion.get("capture_queue")):
        if not isinstance(row, dict):
            continue
        mint = str(row.get("token_address") or row.get("token_mint") or "").strip()
        if not mint:
            continue
        start = safe_float(row.get("needed_snapshot_start"), None)
        end = safe_float(row.get("needed_snapshot_end"), None)
        key = (mint, start, end)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def token_address(row: dict[str, Any]) -> str:
    return str(row.get("token_address") or row.get("token_mint") or "").strip()


def needed_snapshot_end(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("needed_snapshot_end"), None)


def build_budget(*, eligible_rows: int, max_market_context_calls: int) -> dict[str, Any]:
    eligible = max(0, int(eligible_rows))
    limit = max(0, int(max_market_context_calls))
    allowed = eligible <= limit
    return {
        "capture_eligible_rows": eligible,
        "estimated_market_context_calls": eligible,
        "max_market_context_calls": limit,
        "budget_status": "within_budget" if allowed else "blocked_market_context_cycle_limit",
        "execute_allowed": allowed,
        "block_reason": None if allowed else "capture_eligible_rows_exceeds_max_market_context_calls",
    }


def deferred_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "wallet_address": row.get("wallet_address"),
        "token_address": token_address(row),
        "signal_time": row.get("signal_time"),
        "needed_snapshot_start": row.get("needed_snapshot_start"),
        "needed_snapshot_end": row.get("needed_snapshot_end"),
        "defer_reason": reason,
        "recommended_next_action": "archival_or_onchain_later_snapshot_recovery",
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def capture_snapshot(row: dict[str, Any], *, market_provider: Callable[[str], dict[str, Any] | None], observed_at: float) -> dict[str, Any] | None:
    mint = token_address(row)
    info = market_provider(mint)
    snapshot = normalize_market_info(mint, info or {}, observed_at=observed_at)
    if snapshot is None:
        return None
    payload = dict(snapshot.get("payload") or {})
    payload["candidate_snapshot_capture"] = True
    payload["capture_queue_source"] = "candidate_outcome_window_completion"
    payload["needed_snapshot_start"] = row.get("needed_snapshot_start")
    payload["needed_snapshot_end"] = row.get("needed_snapshot_end")
    payload["source_event_id"] = row.get("event_id")
    payload["source_wallet"] = row.get("wallet_address")
    snapshot["payload"] = payload
    snapshot["payload_json"] = json.dumps(payload, sort_keys=True)
    snapshot["candidate_snapshot_capture"] = True
    return snapshot


def build_candidate_bounded_snapshot_capture(
    *,
    outcome_completion: dict[str, Any],
    market_provider: Callable[[str], dict[str, Any] | None] | None = None,
    execute: bool = False,
    max_market_context_calls: int = 10,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    rows = queue_rows(outcome_completion)
    capture_eligible = [row for row in rows if needed_snapshot_end(row) is not None and generated_at <= (needed_snapshot_end(row) or 0.0)]
    expired = [row for row in rows if needed_snapshot_end(row) is None or generated_at > (needed_snapshot_end(row) or 0.0)]
    budget = build_budget(eligible_rows=len(capture_eligible), max_market_context_calls=max_market_context_calls)
    captured: list[dict[str, Any]] = []
    provider_misses = 0
    if execute and budget["execute_allowed"]:
        provider = market_provider or fetch_dexscreener_market_info
        for row in capture_eligible:
            snapshot = capture_snapshot(row, market_provider=provider, observed_at=generated_at)
            if snapshot is None:
                provider_misses += 1
            else:
                captured.append(snapshot)
    deferred = [deferred_row(row, "window_already_expired_for_current_snapshot_capture") for row in expired]
    if not budget["execute_allowed"]:
        deferred.extend(deferred_row(row, "market_context_budget_exceeded") for row in capture_eligible)
    elif not execute:
        deferred.extend(deferred_row(row, "dry_run_no_provider_call") for row in capture_eligible)
    return {
        "generated_at": generated_at,
        "run_id": run_id,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "execute": bool(execute),
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "auto_trust_mutation_allowed": False,
        "wallet_list_mutated": False,
        "limits": {"max_market_context_calls": int(max_market_context_calls)},
        "budget": budget,
        "summary": {
            "input_capture_queue_rows": len(as_list(outcome_completion.get("capture_queue"))),
            "deduped_capture_queue_rows": len(rows),
            "capture_eligible_rows": len(capture_eligible),
            "dry_run_capture_eligible_rows": len(capture_eligible) if not execute else 0,
            "deferred_expired_window_rows": len(expired),
            "current_snapshots_captured": len(captured),
            "provider_misses": provider_misses,
            "deferred_rows": len(deferred),
            "unique_tokens_captured": len({row.get("mint") for row in captured if row.get("mint")}),
            "unique_tokens_deferred": len({row.get("token_address") for row in deferred if row.get("token_address")}),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "capture_eligible_queue": capture_eligible,
        "captured_snapshots": captured,
        "deferred_queue": deferred,
        "operator_note": (
            "Candidate bounded snapshot capture is review-only. It refuses current captures for expired 15m windows "
            "because those would not be valid window evidence."
        ),
    }
