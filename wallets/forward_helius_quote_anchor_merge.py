from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from wallets.forward_entry_context_resolver import build_forward_entry_context_resolver_report
from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import safe_float


MODE = "FORWARD_HELIUS_QUOTE_ANCHOR_MERGE_REVIEW_ONLY"
VERSION = "forward_helius_quote_anchor_merge.v1"


def row_key(*, wallet: str, mint: str, signature: str, event_id: str | None = None) -> tuple[str, str, str, str]:
    return (
        str(event_id or "").strip(),
        str(wallet or "").strip(),
        str(mint or "").strip(),
        str(signature or "").strip(),
    )


def fallback_key(key: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    return ("", key[1], key[2], key[3])


def record_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return row_key(
        event_id=str(row.get("event_id") or ""),
        wallet=str(row.get("wallet") or ""),
        mint=str(row.get("token_mint") or row.get("mint") or ""),
        signature=str(row.get("transaction_signature") or ""),
    )


def probe_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return row_key(
        event_id=str(row.get("event_id") or ""),
        wallet=str(row.get("wallet_address") or row.get("wallet") or ""),
        mint=str(row.get("token_mint") or row.get("mint") or ""),
        signature=str(row.get("transaction_signature") or ""),
    )


def is_recoverable_quote_probe_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("status") or "") != "quote_anchor_recoverable":
        return False
    price = safe_float(row.get("execution_price_quote"), None)
    return price is not None and price > 0


def recoverable_quote_anchors(quote_probe_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    anchors: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in quote_probe_rows or []:
        if not is_recoverable_quote_probe_row(row):
            continue
        key = probe_key(row)
        if not key[1] or not key[2] or not key[3]:
            continue
        anchors[key] = row
        anchors[fallback_key(key)] = row
    return anchors


def overlay_quote_anchor(record: dict[str, Any], anchor: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(record)
    decision_context = dict(as_dict(out.get("decision_context")))
    entry_context = dict(as_dict(decision_context.get("estimated_entry_context")))
    for key in [
        "execution_price_quote",
        "execution_price_source",
        "quote_mint",
        "quote_amount_delta",
        "native_sol_raw_lamports_delta",
        "native_sol_adjusted_lamports_delta",
        "native_sol_fee_lamports",
    ]:
        if anchor.get(key) not in (None, ""):
            entry_context[key] = anchor.get(key)
    entry_context["quote_anchor_source"] = "helius_quote_probe"
    entry_context["decision_time_safe"] = True
    decision_context["estimated_entry_context"] = entry_context
    out["decision_context"] = decision_context
    out["helius_quote_anchor_merge"] = {
        "source": "helius_quote_probe",
        "status": "quote_anchor_overlay_applied",
        "execution_price_quote": anchor.get("execution_price_quote"),
        "execution_price_source": anchor.get("execution_price_source"),
        "quote_mint": anchor.get("quote_mint"),
        "quote_amount_delta": anchor.get("quote_amount_delta"),
        "transaction_signature": anchor.get("transaction_signature"),
    }
    out["can_mutate_wallet_trust"] = False
    out["wallet_list_mutation_allowed"] = False
    return out


def augment_records_with_quote_anchors(
    records: list[dict[str, Any]],
    anchors: dict[tuple[str, str, str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    augmented: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        key = record_key(record)
        anchor = anchors.get(key) or anchors.get(fallback_key(key))
        if anchor is None:
            augmented.append(deepcopy(record))
            continue
        updated = overlay_quote_anchor(record, anchor)
        augmented.append(updated)
        matched.append(updated)
    return augmented, matched


def build_summary(
    *,
    records: list[dict[str, Any]],
    quote_probe_rows: list[dict[str, Any]],
    anchors: dict[tuple[str, str, str, str], dict[str, Any]],
    matched_records: list[dict[str, Any]],
    resolver_report: dict[str, Any],
) -> dict[str, Any]:
    resolver_summary = as_dict(resolver_report.get("summary"))
    return {
        "input_records": len(records or []),
        "input_quote_probe_rows": len(quote_probe_rows or []),
        "recoverable_quote_anchors": sum(1 for row in quote_probe_rows or [] if is_recoverable_quote_probe_row(row)),
        "records_augmented_with_quote_anchor": len(matched_records),
        "resolver_resolved_rows": int(resolver_summary.get("resolved_rows") or 0),
        "resolver_known_15m_outcomes": int(resolver_summary.get("known_15m_outcomes") or 0),
        "resolver_blocked_no_later_snapshot_rows": int(resolver_summary.get("blocked_no_later_snapshot_rows") or 0),
        "resolver_blocked_no_quote_anchor_rows": int(resolver_summary.get("blocked_no_quote_anchor_rows") or 0),
        "repair_rows_written_to_canonical_resolver": 0,
        "promotions_allowed": 0,
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_helius_quote_anchor_merge(
    *,
    records: list[dict[str, Any]],
    quote_probe_rows: list[dict[str, Any]],
    market_snapshots: list[dict[str, Any]],
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    run_id = run_id or str(int(generated_at))
    anchors = recoverable_quote_anchors(quote_probe_rows)
    augmented_records, matched_records = augment_records_with_quote_anchors(records, anchors)
    resolver_report = build_forward_entry_context_resolver_report(
        records=augmented_records,
        market_snapshots=market_snapshots,
        generated_at=generated_at,
    )
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
        "summary": build_summary(
            records=records,
            quote_probe_rows=quote_probe_rows,
            anchors=anchors,
            matched_records=matched_records,
            resolver_report=resolver_report,
        ),
        "augmented_records": matched_records,
        "resolver_report": resolver_report,
        "operator_note": (
            "Helius quote-anchor merge is review-only. It overlays recovered quote anchors onto a temporary "
            "record set and runs the existing entry-context resolver, but does not write canonical resolver "
            "files, mutate wallet trust, mutate wallet lists, promote wallets, or execute trades."
        ),
    }
