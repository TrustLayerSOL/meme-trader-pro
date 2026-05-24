from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from wallets.wallet_evidence_models import safe_float


MODE = "FORWARD_MARKET_SNAPSHOT_REPAIR_QUEUE_REVIEW_ONLY"
VERSION = "forward_market_snapshot_repair_queue.v1"
TARGET_REASON = "missing_later_market_snapshot"
MAX_EVALUATION_WINDOW_SECONDS = 900


def is_missing_later_snapshot_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("block_reason") or "") != TARGET_REASON:
        return False
    return bool(row.get("token_mint")) and safe_float(row.get("signal_time"), None) is not None


def group_rows_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows or []:
        if is_missing_later_snapshot_row(row):
            grouped[str(row.get("token_mint") or "")].append(row)
    return dict(grouped)


def representative_rows(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: safe_float(item.get("signal_time"), 0.0) or 0.0)[:limit]:
        out.append(
            {
                "event_id": row.get("event_id"),
                "wallet": row.get("wallet"),
                "token_mint": row.get("token_mint"),
                "signal_time": safe_float(row.get("signal_time"), None),
                "transaction_signature": row.get("transaction_signature"),
                "has_quote_anchor": bool(row.get("has_quote_anchor")),
            }
        )
    return out


def queue_row(mint: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    signal_times = [safe_float(row.get("signal_time"), None) for row in rows]
    signal_times = [time_value for time_value in signal_times if time_value is not None]
    wallets = sorted({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
    min_time = min(signal_times) if signal_times else None
    max_time = max(signal_times) if signal_times else None
    return {
        "token_mint": mint,
        "blocked_row_count": len(rows),
        "wallet_count": len(wallets),
        "wallets": wallets,
        "required_snapshot_start_time": min_time,
        "required_snapshot_end_time": (max_time + MAX_EVALUATION_WINDOW_SECONDS) if max_time is not None else None,
        "earliest_signal_time": min_time,
        "latest_signal_time": max_time,
        "recommended_action": "collect_later_market_snapshot",
        "repair_priority": len(rows) * 100 + len(wallets),
        "reason": "rows already have quote anchors but need later market snapshots for outcome windows",
        "representative_rows": representative_rows(rows),
        "promotion_allowed": False,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def sort_queue_row(row: dict[str, Any]) -> tuple[int, int, str]:
    return (
        -int(row.get("blocked_row_count") or 0),
        -int(row.get("wallet_count") or 0),
        str(row.get("token_mint") or ""),
    )


def build_summary(rejected_records: list[dict[str, Any]], queue: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "input_rejected_records": len(rejected_records or []),
        "missing_later_market_snapshot_rows": sum(int(row.get("blocked_row_count") or 0) for row in queue),
        "queued_token_mints": len(queue),
        "queued_wallets": len({wallet for row in queue for wallet in row.get("wallets", [])}),
        "top_token_blocked_rows": int(queue[0].get("blocked_row_count") or 0) if queue else 0,
        "repair_rows_written": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_market_snapshot_repair_queue(
    *,
    rejected_records: list[dict[str, Any]],
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    grouped = group_rows_by_mint(rejected_records)
    queue = sorted((queue_row(mint, rows) for mint, rows in grouped.items()), key=sort_queue_row)
    return {
        "generated_at": generated_at,
        "run_id": run_id,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(rejected_records, queue),
        "queue": queue,
        "operator_note": (
            "Market snapshot repair queue is review-only. It identifies token/time windows that already "
            "have quote anchors but still need later market snapshots; it cannot mutate trust, mutate wallet "
            "lists, promote wallets, overwrite resolver files, or execute trades."
        ),
    }
