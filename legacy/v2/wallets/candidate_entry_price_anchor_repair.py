from __future__ import annotations

import glob
import time
from collections import Counter
from pathlib import Path
from typing import Any

from wallets.candidate_walk_forward_validation import entry_context
from wallets.candidate_walk_forward_validation import event_id
from wallets.candidate_walk_forward_validation import safe_float
from wallets.candidate_walk_forward_validation import sorted_rows
from wallets.candidate_walk_forward_validation import wallet_address
from wallets.wallet_history_parser import parse_wallet_token_deltas


MODE = "CANDIDATE_ENTRY_PRICE_ANCHOR_REPAIR_REVIEW_ONLY"
VERSION = "candidate_entry_price_anchor_repair.v1"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def target_wallets(context_quality_lift: dict[str, Any]) -> list[str]:
    wallets: list[str] = []
    for row in as_list(context_quality_lift.get("wallets")):
        if not isinstance(row, dict):
            continue
        if row.get("recommended_context_action") != "repair_entry_timestamp":
            continue
        wallet = str(row.get("wallet_address") or "").strip()
        if wallet:
            wallets.append(wallet)
    return wallets


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("block_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason)]
    if isinstance(reasons, str) and reasons:
        return [reasons]
    return []


def is_missing_entry_price_row(row: dict[str, Any], targets: set[str]) -> bool:
    return (
        wallet_address(row) in targets
        and str(row.get("status") or "") == "blocked_missing_forward_entry_context"
        and "missing_forward_entry_price" in block_reasons(row)
    )


def raw_signature(row: dict[str, Any]) -> str:
    return str(row.get("signature") or row.get("transaction_signature") or "").strip()


def raw_wallet(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or "").strip()


def raw_anchor_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        raw_wallet(row),
        raw_signature(row),
        str(row.get("token_mint") or "").strip(),
        str(row.get("observed_action") or row.get("action") or "").strip(),
    )


def parse_raw_anchor_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        if raw.get("execution_price_quote") not in (None, "") and raw.get("token_mint"):
            anchors.append(dict(raw))
            continue
        tx = raw.get("transaction") if isinstance(raw.get("transaction"), dict) else {}
        wallet = raw_wallet(raw)
        signature = raw_signature(raw)
        if wallet and tx:
            anchors.extend(
                parse_wallet_token_deltas(
                    tx,
                    wallet=wallet,
                    signature=signature,
                    outcome_by_mint={},
                    risk_flags=[],
                )
            )
    return anchors


def anchor_index(raw_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for anchor in parse_raw_anchor_rows(raw_rows):
        key = raw_anchor_key(anchor)
        if all(key) and key not in indexed:
            indexed[key] = anchor
    return indexed


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        wallet_address(row),
        str(row.get("transaction_signature") or "").strip(),
        str(row.get("token_mint") or "").strip(),
        str(row.get("observed_action") or row.get("action") or "").strip(),
    )


def anchor_price(anchor: dict[str, Any]) -> float | None:
    price = safe_float(anchor.get("execution_price_quote"), None)
    if price is None or price <= 0:
        return None
    return price


def repaired_record(row: dict[str, Any], anchor: dict[str, Any], generated_at: float) -> dict[str, Any]:
    price = anchor_price(anchor)
    context = dict(entry_context(row))
    context.update(
        {
            "price": price,
            "execution_price_quote": price,
            "quote_mint": anchor.get("quote_mint"),
            "quote_amount_delta": anchor.get("quote_amount_delta"),
            "execution_price_source": anchor.get("execution_price_source") or "preserved_raw_transaction_quote_anchor",
            "price_source": "candidate_entry_price_anchor_repair",
            "repair_method": "preserved_raw_transaction_quote_anchor",
            "repair_confidence": "same_transaction_raw_quote_anchor",
            "decision_time_safe": True,
        }
    )
    return {
        **row,
        "version": VERSION,
        "decision_context": {
            **as_dict(row.get("decision_context")),
            "estimated_entry_context": context,
        },
        "entry_price_anchor_repair": {
            "method": "preserved_raw_transaction_quote_anchor",
            "source": "candidate_entry_price_anchor_repair",
            "confidence": "same_transaction_raw_quote_anchor",
            "repaired_price": price,
            "generated_at": generated_at,
        },
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def rejected_record(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "event_id": event_id(row),
        "wallet": wallet_address(row),
        "token_mint": row.get("token_mint"),
        "observed_action": row.get("observed_action") or row.get("action"),
        "signal_time": row.get("signal_time"),
        "transaction_signature": row.get("transaction_signature"),
        "status": "candidate_entry_price_anchor_rejected",
        "reject_reason": reason,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def audit_row(row: dict[str, Any], status: str, reason: str, price: float | None) -> dict[str, Any]:
    return {
        "event_id": event_id(row),
        "wallet_address": wallet_address(row),
        "token_address": row.get("token_mint"),
        "observed_action": row.get("observed_action") or row.get("action"),
        "signal_time": row.get("signal_time"),
        "transaction_signature": row.get("transaction_signature"),
        "repair_status": status,
        "reason": reason,
        "repaired_price": price,
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_candidate_entry_price_anchor_repair(
    *,
    context_quality_lift: dict[str, Any],
    records: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    targets = target_wallets(context_quality_lift)
    target_set = set(targets)
    missing_rows = [row for row in sorted_rows(records) if is_missing_entry_price_row(row, target_set)]
    anchors = anchor_index(raw_rows)
    repaired: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for row in missing_rows:
        anchor = anchors.get(row_key(row))
        if not anchor:
            rejected.append(rejected_record(row, "missing_preserved_raw_transaction_anchor"))
            audit_rows.append(audit_row(row, "rejected", "missing_preserved_raw_transaction_anchor", None))
            continue
        price = anchor_price(anchor)
        if price is None:
            rejected.append(rejected_record(row, "invalid_or_missing_execution_price_quote"))
            audit_rows.append(audit_row(row, "rejected", "invalid_or_missing_execution_price_quote", None))
            continue
        repaired.append(repaired_record(row, anchor, generated_at))
        audit_rows.append(audit_row(row, "anchor_repaired", "preserved_raw_transaction_quote_anchor", price))
    reject_counts = Counter(str(row.get("reject_reason") or "unknown") for row in rejected)
    by_wallet = Counter(wallet_address(row) for row in missing_rows)
    repaired_by_wallet = Counter(wallet_address(row) for row in repaired)
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "auto_trust_mutation_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "target_wallets": len(targets),
            "records_scanned": len(records),
            "raw_rows_scanned": len(raw_rows),
            "raw_anchor_rows": len(parse_raw_anchor_rows(raw_rows)),
            "missing_entry_price_rows": len(missing_rows),
            "anchor_repaired_rows": len(repaired),
            "rejected_rows": len(rejected),
            "wallets_with_anchor_repairs": len({row.get("wallet") for row in repaired if row.get("wallet")}),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "wallet_summary": [
            {
                "wallet_address": wallet,
                "missing_entry_price_rows": by_wallet.get(wallet, 0),
                "anchor_repaired_rows": repaired_by_wallet.get(wallet, 0),
                "rejected_rows": by_wallet.get(wallet, 0) - repaired_by_wallet.get(wallet, 0),
            }
            for wallet in targets
        ],
        "rejected_reason_counts": dict(sorted(reject_counts.items())),
        "audit_rows": audit_rows,
        "anchor_repaired_records": repaired,
        "rejected_records": rejected,
        "operator_note": (
            "Candidate entry-price anchor repair is review-only. Anchor-enriched records are written as a separate "
            "candidate artifact and are not applied to wallet trust, wallet lists, or live execution."
        ),
    }


def read_raw_glob(raw_glob: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in sorted(glob.glob(raw_glob)):
        path = Path(file_name)
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    parsed = __import__("json").loads(text)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
    return rows
