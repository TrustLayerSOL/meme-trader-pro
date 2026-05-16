from __future__ import annotations

import time
from collections import Counter, defaultdict
from statistics import median
from typing import Any

from wallets.wallet_history_parser import QUOTE_MINTS


MODE = "WALLET_EVIDENCE_LIFECYCLE_REVIEW_ONLY"
LIFECYCLE_VERSION = "wallet_evidence_lifecycle.v1"


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def normalized_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    return action if action in {"buy", "sell"} else "unknown"


def evidence_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    return (
        safe_float(row.get("timestamp"), 0.0) or 0.0,
        str(row.get("transaction_signature") or ""),
    )


def group_lifecycle_rows(evidence_records: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = Counter()
    for row in evidence_records or []:
        if not isinstance(row, dict):
            skipped["non_dict_rows"] += 1
            continue
        wallet = str(row.get("wallet") or "").strip()
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if not wallet or not mint:
            skipped["missing_wallet_or_mint_rows"] += 1
            continue
        if mint in QUOTE_MINTS:
            skipped["quote_mint_rows"] += 1
            continue
        if safe_float(row.get("timestamp"), None) is None:
            skipped["missing_timestamp_rows"] += 1
            continue
        grouped[(wallet, mint)].append(row)
    for rows in grouped.values():
        rows.sort(key=evidence_sort_key)
    return dict(grouped), dict(skipped)


def first_row(rows: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    for row in rows:
        if normalized_action(row.get("observed_action")) == action:
            return row
    return None


def first_sell_after(rows: list[dict[str, Any]], timestamp: float) -> dict[str, Any] | None:
    for row in rows:
        if normalized_action(row.get("observed_action")) != "sell":
            continue
        row_time = safe_float(row.get("timestamp"), None)
        if row_time is not None and row_time >= timestamp:
            return row
    return None


def lifecycle_status(*, buy_rows: list[dict[str, Any]], sell_rows: list[dict[str, Any]], exit_row: dict[str, Any] | None) -> str:
    if buy_rows and exit_row:
        return "round_trip_observed"
    if buy_rows:
        return "buy_only_open_or_unseen_exit"
    if sell_rows:
        return "sell_only_missing_entry"
    return "unknown_action_only"


def token_delta(row: dict[str, Any]) -> float:
    return safe_float(row.get("token_amount_delta"), 0.0) or 0.0


def lifecycle_for_group(wallet: str, mint: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    buy_rows = [row for row in rows if normalized_action(row.get("observed_action")) == "buy"]
    sell_rows = [row for row in rows if normalized_action(row.get("observed_action")) == "sell"]
    entry_row = first_row(rows, "buy")
    entry_time = safe_float(entry_row.get("timestamp"), None) if entry_row else None
    exit_row = first_sell_after(rows, entry_time) if entry_time is not None else None
    exit_time = safe_float(exit_row.get("timestamp"), None) if exit_row else None
    hold_duration = round(exit_time - entry_time, 6) if entry_time is not None and exit_time is not None else None
    net_delta = round(sum(token_delta(row) for row in rows), 12)
    confidence_values = [safe_float(row.get("confidence_score"), 0.0) or 0.0 for row in rows]
    return {
        "wallet": wallet,
        "token_mint": mint,
        "lifecycle_status": lifecycle_status(buy_rows=buy_rows, sell_rows=sell_rows, exit_row=exit_row),
        "first_event_time": safe_float(rows[0].get("timestamp"), None) if rows else None,
        "last_event_time": safe_float(rows[-1].get("timestamp"), None) if rows else None,
        "first_buy_time": entry_time,
        "first_sell_after_buy_time": exit_time,
        "hold_duration_seconds": hold_duration,
        "entry_signature": entry_row.get("transaction_signature") if entry_row else None,
        "exit_signature": exit_row.get("transaction_signature") if exit_row else None,
        "event_count": len(rows),
        "buy_count": len(buy_rows),
        "sell_count": len(sell_rows),
        "net_token_amount_delta": net_delta,
        "transaction_count": len({row.get("transaction_signature") for row in rows if row.get("transaction_signature")}),
        "action_sequence": [normalized_action(row.get("observed_action")) for row in rows],
        "average_evidence_confidence_score": (
            round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
        ),
    }


def wallet_summary(wallet: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("lifecycle_status") or "unknown") for row in rows)
    hold_durations = [
        safe_float(row.get("hold_duration_seconds"), None)
        for row in rows
        if safe_float(row.get("hold_duration_seconds"), None) is not None
    ]
    return {
        "wallet": wallet,
        "lifecycle_mints": len(rows),
        "round_trip_lifecycles": statuses["round_trip_observed"],
        "buy_only_lifecycles": statuses["buy_only_open_or_unseen_exit"],
        "sell_only_lifecycles": statuses["sell_only_missing_entry"],
        "unknown_action_lifecycles": statuses["unknown_action_only"],
        "average_hold_duration_seconds": (
            round(sum(hold_durations) / len(hold_durations), 2) if hold_durations else None
        ),
        "median_hold_duration_seconds": round(median(hold_durations), 2) if hold_durations else None,
        "short_hold_round_trips": sum(1 for value in hold_durations if value <= 120),
        "long_hold_round_trips": sum(1 for value in hold_durations if value >= 900),
        "net_accumulation_mints": sum(1 for row in rows if (safe_float(row.get("net_token_amount_delta"), 0.0) or 0.0) > 0),
        "net_distribution_mints": sum(1 for row in rows if (safe_float(row.get("net_token_amount_delta"), 0.0) or 0.0) < 0),
    }


def summarize_report(
    *,
    input_rows: int,
    skipped: dict[str, int],
    lifecycle_rows: list[dict[str, Any]],
    wallet_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(str(row.get("lifecycle_status") or "unknown") for row in lifecycle_rows)
    hold_durations = [
        safe_float(row.get("hold_duration_seconds"), None)
        for row in lifecycle_rows
        if safe_float(row.get("hold_duration_seconds"), None) is not None
    ]
    return {
        "input_evidence_rows": input_rows,
        "lifecycle_rows": len(lifecycle_rows),
        "wallets": len(wallet_rows),
        "round_trip_lifecycles": statuses["round_trip_observed"],
        "wallets_with_round_trips": sum(1 for row in wallet_rows.values() if row.get("round_trip_lifecycles")),
        "buy_only_lifecycles": statuses["buy_only_open_or_unseen_exit"],
        "sell_only_lifecycles": statuses["sell_only_missing_entry"],
        "unknown_action_lifecycles": statuses["unknown_action_only"],
        "average_observed_hold_duration_seconds": (
            round(sum(hold_durations) / len(hold_durations), 2) if hold_durations else None
        ),
        "median_observed_hold_duration_seconds": round(median(hold_durations), 2) if hold_durations else None,
        "skipped_quote_mint_rows": int(skipped.get("quote_mint_rows", 0)),
        "skipped_missing_timestamp_rows": int(skipped.get("missing_timestamp_rows", 0)),
        "skipped_missing_wallet_or_mint_rows": int(skipped.get("missing_wallet_or_mint_rows", 0)),
        "skipped_non_dict_rows": int(skipped.get("non_dict_rows", 0)),
    }


def build_wallet_evidence_lifecycle_report(
    *,
    evidence_records: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped, skipped = group_lifecycle_rows(evidence_records)
    lifecycles = [
        lifecycle_for_group(wallet, mint, rows)
        for (wallet, mint), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1]))
    ]
    wallet_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lifecycles:
        wallet_groups[str(row.get("wallet") or "")].append(row)
    wallets = {
        wallet: wallet_summary(wallet, rows)
        for wallet, rows in sorted(wallet_groups.items())
        if wallet
    }
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "lifecycle_version": LIFECYCLE_VERSION,
        "review_only": True,
        "live_execution_locked": True,
        "operator_summary": "Wallet lifecycle evidence is behavioral only; it does not infer PnL or promote wallets.",
        "summary": summarize_report(
            input_rows=len(evidence_records or []),
            skipped=skipped,
            lifecycle_rows=lifecycles,
            wallet_rows=wallets,
        ),
        "wallets": wallets,
        "lifecycles": lifecycles,
    }
