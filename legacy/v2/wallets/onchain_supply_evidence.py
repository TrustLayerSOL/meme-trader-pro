from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any

from wallets.historical_market_context_backfill import index_raw_transactions
from wallets.wallet_evidence_models import as_dict, safe_float


MODE = "ONCHAIN_SUPPLY_EVIDENCE_REVIEW_ONLY"
SUPPLY_EVIDENCE_VERSION = "onchain_supply_evidence.v1"


def positive_float(value: Any) -> float | None:
    parsed = safe_float(value, None)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def first_positive(*values: Any) -> float | None:
    for value in values:
        parsed = positive_float(value)
        if parsed is not None:
            return parsed
    return None


def context_supply(context: dict[str, Any]) -> tuple[float | None, str | None]:
    for key in ("token_supply", "total_supply", "circulating_supply", "supply"):
        supply = positive_float(context.get(key))
        if supply is not None:
            return supply, "decision_time_context"
    return None, None


def unsafe_current_supply(context: dict[str, Any]) -> float | None:
    return first_positive(context.get("current_supply"), context.get("current_token_supply"))


def token_decimals_from_raw(raw: dict[str, Any], token_mint: str) -> int | None:
    tx = as_dict(raw.get("transaction"))
    meta = as_dict(tx.get("meta"))
    for field in ("preTokenBalances", "postTokenBalances"):
        for row in meta.get(field) or []:
            if not isinstance(row, dict) or str(row.get("mint") or "") != token_mint:
                continue
            amount = as_dict(row.get("uiTokenAmount"))
            decimals = amount.get("decimals")
            if isinstance(decimals, int) and decimals >= 0:
                return decimals
    return None


def classify_supply_record(record: dict[str, Any], raw_by_signature: dict[str, dict[str, Any]]) -> dict[str, Any]:
    context = as_dict(record.get("decision_time_context"))
    token_mint = str(record.get("token_mint") or "").strip()
    signature = str(record.get("transaction_signature") or "").strip()
    raw = raw_by_signature.get(signature)
    block_reasons = {str(reason) for reason in record.get("block_reasons") or [] if str(reason).strip()}
    notes: list[str] = []
    ui_supply, source = context_supply(context)
    status = "needs_archival_supply"

    if ui_supply is not None:
        status = "supply_recovered"
        block_reasons.discard("blocked_missing_supply")
        block_reasons.discard("blocked_missing_market_cap")
    elif unsafe_current_supply(context) is not None:
        status = "unsafe_current_only"
        block_reasons.add("blocked_current_supply_not_decision_time_safe")
        block_reasons.add("blocked_missing_supply")
        notes.append("current supply cannot prove decision-time historical supply")
    else:
        block_reasons.add("blocked_missing_supply")
        notes.append("raw transaction token balances expose decimals but not total supply")

    decimals = token_decimals_from_raw(raw, token_mint) if raw else None
    return {
        "supply_evidence_version": SUPPLY_EVIDENCE_VERSION,
        "wallet": str(record.get("wallet") or "").strip(),
        "token_mint": token_mint,
        "timestamp": safe_float(record.get("timestamp") or context.get("timestamp"), None),
        "transaction_signature": signature,
        "status": status,
        "source": source,
        "decision_time_safe": status == "supply_recovered",
        "raw_supply": None,
        "ui_supply": ui_supply,
        "decimals": decimals,
        "block_reasons": sorted(block_reasons),
        "notes": notes,
    }


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    blocks = Counter(reason for record in records for reason in record.get("block_reasons") or [])
    by_token: dict[str, dict[str, Any]] = defaultdict(lambda: {"records": 0, "statuses": Counter(), "decimals": set()})
    for record in records:
        token = str(record.get("token_mint") or "unknown")
        by_token[token]["records"] += 1
        by_token[token]["statuses"].update([str(record.get("status") or "unknown")])
        if record.get("decimals") is not None:
            by_token[token]["decimals"].add(record["decimals"])
    return {
        "records_scanned": len(records),
        "supply_recovered_records": statuses.get("supply_recovered", 0),
        "needs_archival_supply_records": statuses.get("needs_archival_supply", 0),
        "unsafe_current_only_records": statuses.get("unsafe_current_only", 0),
        "status_counts": dict(sorted(statuses.items())),
        "block_reasons": dict(sorted(blocks.items())),
        "tokens_affected": len({record.get("token_mint") for record in records if record.get("token_mint")}),
        "tokens_with_decimals": sum(1 for row in by_token.values() if row["decimals"]),
        "next_required_actions": next_required_actions(records),
        "supply_requirements_by_token": {
            token: {
                "records": data["records"],
                "statuses": dict(sorted(data["statuses"].items())),
                "decimals": sorted(data["decimals"]),
            }
            for token, data in sorted(by_token.items())
        },
    }


def next_required_actions(records: list[dict[str, Any]]) -> list[str]:
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    actions: list[str] = []
    if statuses.get("needs_archival_supply"):
        actions.append("Fetch or reconstruct historical mint-account supply at or before the decision slot.")
    if statuses.get("unsafe_current_only"):
        actions.append("Keep current-only supply out of score-ready replay context.")
    if not actions:
        actions.append("All rows have decision-time supply evidence.")
    return actions


def build_onchain_supply_evidence_report(
    *,
    market_context_records: list[dict[str, Any]],
    raw_transactions: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    raw_by_signature = index_raw_transactions(raw_transactions)
    records = [
        classify_supply_record(record, raw_by_signature)
        for record in market_context_records or []
        if isinstance(record, dict)
    ]
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "supply_evidence_version": SUPPLY_EVIDENCE_VERSION,
        "summary": build_summary(records),
        "records": records,
    }
