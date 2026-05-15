from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.wallet_evidence_models import as_dict, safe_float
from wallets.wallet_history_parser import QUOTE_MINTS


MODE = "WALLET_MISSING_MARKET_CONTEXT_REVIEW_ONLY"


def missing_market_context(row: dict[str, Any]) -> bool:
    if str(row.get("enrichment_status") or "") == "MISSING_MARKET_CONTEXT":
        return True
    missing_fields = row.get("missing_fields") if isinstance(row.get("missing_fields"), list) else []
    entry = as_dict(row.get("estimated_entry_context"))
    return "entry_price" in missing_fields or entry.get("price") in (None, "")


def known_outcome(row: dict[str, Any]) -> bool:
    return as_dict(row.get("later_token_outcome")).get("outcome_type") not in (None, "", "unknown")


def timestamp_value(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("timestamp"), None)


def group_missing_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict) or not missing_market_context(row):
            continue
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if mint in QUOTE_MINTS:
            continue
        key = (
            str(row.get("wallet") or ""),
            mint,
            str(row.get("observed_action") or ""),
            str(row.get("transaction_signature") or ""),
            str(row.get("timestamp") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def target_for_mint(
    mint: str,
    rows: list[dict[str, Any]],
    *,
    before_seconds: float,
    after_seconds: float,
    row_limit: int = 8,
) -> dict[str, Any]:
    timestamps = [timestamp_value(row) for row in rows]
    timestamps = [value for value in timestamps if value is not None]
    first_timestamp = min(timestamps) if timestamps else None
    last_timestamp = max(timestamps) if timestamps else None
    actions = Counter(str(row.get("observed_action") or "unknown") for row in rows)
    wallets = sorted({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
    known_rows = [row for row in rows if known_outcome(row)]
    max_confidence = max((safe_float(row.get("confidence_score"), 0.0) or 0.0 for row in rows), default=0.0)
    window = {
        "before_seconds": before_seconds,
        "after_seconds": after_seconds,
        "start_time": first_timestamp - before_seconds if first_timestamp is not None else None,
        "end_time": last_timestamp + after_seconds if last_timestamp is not None else None,
    }
    return {
        "token_mint": mint,
        "next_collection_step": "BACKFILL_MARKET_CONTEXT",
        "evidence_rows": len(rows),
        "unique_wallets": len(wallets),
        "wallets": wallets[:row_limit],
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "backfill_window": window,
        "observed_actions": dict(actions),
        "known_outcome_rows": len(known_rows),
        "unknown_outcome_rows": len(rows) - len(known_rows),
        "max_confidence_score": max_confidence,
        "sample_records": [sample_record(row) for row in sorted(rows, key=lambda item: timestamp_value(item) or 0.0)[:row_limit]],
    }


def sample_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "wallet": row.get("wallet"),
        "timestamp": row.get("timestamp"),
        "observed_action": row.get("observed_action"),
        "transaction_signature": row.get("transaction_signature"),
        "enrichment_status": row.get("enrichment_status"),
        "missing_fields": row.get("missing_fields") if isinstance(row.get("missing_fields"), list) else [],
        "outcome_type": as_dict(row.get("later_token_outcome")).get("outcome_type") or "unknown",
        "confidence_score": row.get("confidence_score"),
    }


def build_summary(targets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "target_mints": len(targets),
        "missing_market_context_rows": sum(int(row.get("evidence_rows") or 0) for row in targets),
        "wallets_affected": len({wallet for row in targets for wallet in row.get("wallets") or []}),
        "targets_with_known_outcomes": sum(1 for row in targets if int(row.get("known_outcome_rows") or 0) > 0),
        "highest_evidence_rows_for_one_mint": max((int(row.get("evidence_rows") or 0) for row in targets), default=0),
    }


def build_wallet_missing_market_context_targets(
    *,
    wallet_evidence_enrichment: Any,
    generated_at: float | None = None,
    before_seconds: float = 3600.0,
    after_seconds: float = 3600.0,
    limit: int | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    records = as_dict(wallet_evidence_enrichment).get("evidence_records") or []
    grouped = group_missing_rows(records if isinstance(records, list) else [])
    targets = [
        target_for_mint(
            mint,
            rows,
            before_seconds=max(0.0, float(before_seconds)),
            after_seconds=max(0.0, float(after_seconds)),
        )
        for mint, rows in grouped.items()
    ]
    targets.sort(
        key=lambda row: (
            int(row.get("evidence_rows") or 0),
            int(row.get("known_outcome_rows") or 0),
            safe_float(row.get("max_confidence_score"), 0.0) or 0.0,
        ),
        reverse=True,
    )
    if limit is not None:
        targets = targets[: max(0, int(limit))]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "summary": build_summary(targets),
        "targets": targets,
    }
