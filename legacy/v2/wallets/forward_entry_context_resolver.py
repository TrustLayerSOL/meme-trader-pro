from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallets.forward_outcome_resolution import KNOWN_OUTCOMES
from wallets.forward_outcome_resolution import is_known
from wallets.forward_outcome_resolution import normalize_snapshot
from wallets.forward_outcome_resolution import resolve_windows
from wallets.forward_outcome_resolution import select_overall_outcome
from wallets.forward_outcome_resolution import snapshots_by_mint
from wallets.wallet_evidence_models import as_dict
from wallets.wallet_evidence_models import empty_window_labels
from wallets.wallet_evidence_models import safe_float


MODE = "FORWARD_ENTRY_CONTEXT_RESOLVER_REVIEW_ONLY"
VERSION = "forward_entry_context_resolver.v1"
SOURCE = "forward_entry_context_resolver"


def is_blocked_entry_context(row: dict[str, Any]) -> bool:
    if str(row.get("status") or "") != "blocked_missing_forward_entry_context":
        return False
    return "missing_forward_entry_price" in [str(reason) for reason in row.get("block_reasons") or []]


def signal_time(row: dict[str, Any]) -> float | None:
    return safe_float(row.get("signal_time") or row.get("timestamp"), None)


def token_mint(row: dict[str, Any]) -> str:
    return str(row.get("token_mint") or row.get("mint") or "").strip()


def decision_entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def quote_anchor_price(row: dict[str, Any]) -> float | None:
    price = safe_float(decision_entry_context(row).get("execution_price_quote"), None)
    if price is None or price <= 0:
        return None
    return price


def later_snapshots_for_row(row: dict[str, Any], grouped_snapshots: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    mint = token_mint(row)
    ts = signal_time(row)
    if not mint or ts is None:
        return []
    return [
        snapshot
        for snapshot in grouped_snapshots.get(mint, [])
        if (safe_float(snapshot.get("time"), 0.0) or 0.0) >= ts
    ]


def repaired_entry_anchor(row: dict[str, Any]) -> dict[str, Any]:
    context = decision_entry_context(row)
    return {
        "time": signal_time(row),
        "mint": token_mint(row),
        "source": SOURCE,
        "price": quote_anchor_price(row),
        "liquidity": safe_float(context.get("liquidity"), None),
        "market_cap": safe_float(context.get("market_cap"), None),
        "risk_label": context.get("risk_label"),
        "repair_method": "same_transaction_quote_anchor",
        "execution_price_source": context.get("execution_price_source"),
    }


def repaired_decision_context(row: dict[str, Any]) -> dict[str, Any]:
    context = dict(decision_entry_context(row))
    context["price"] = quote_anchor_price(row)
    context["price_source"] = SOURCE
    context["repair_method"] = "same_transaction_quote_anchor"
    context["repair_confidence"] = "partial_forward_quote_anchor"
    context["decision_time_safe"] = True
    return {
        **as_dict(row.get("decision_context")),
        "estimated_entry_context": context,
    }


def unresolved_row(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "wallet": row.get("wallet"),
        "token_mint": token_mint(row),
        "signal_time": signal_time(row),
        "transaction_signature": row.get("transaction_signature"),
        "status": "blocked_forward_entry_context_repair",
        "block_reason": reason,
        "has_quote_anchor": quote_anchor_price(row) is not None,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def resolved_record(row: dict[str, Any], snapshots: list[dict[str, Any]], *, generated_at: float) -> dict[str, Any]:
    entry = repaired_entry_anchor(row)
    windows = resolve_windows(
        mint=token_mint(row),
        signal_time=signal_time(row) or 0.0,
        entry=entry,
        snapshots=snapshots,
        generated_at=generated_at,
    )
    record = {
        **row,
        "version": VERSION,
        "status": "forward_entry_context_repaired",
        "block_reasons": [],
        "decision_context": repaired_decision_context(row),
        "entry_context_repair": {
            "method": "same_transaction_quote_anchor",
            "source": SOURCE,
            "confidence": "partial_forward_quote_anchor",
            "snapshot_support": "later_market_snapshots_available",
            "later_snapshots_available": len(snapshots),
            "repaired_price": quote_anchor_price(row),
        },
        "outcome_window_labels": windows,
        "later_token_outcome": select_overall_outcome(windows),
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }
    if is_known(as_dict(windows.get("15m"))) or any(is_known(as_dict(window)) for window in windows.values()):
        record["status"] = "forward_outcome_labeled"
    elif any(str(as_dict(window).get("status") or "") == "pending_forward_window" for window in windows.values()):
        record["status"] = "pending_forward_outcome_windows"
    else:
        record["status"] = "forward_outcome_unknown_after_entry_repair"
    return record


def build_summary(resolved: list[dict[str, Any]], rejected: list[dict[str, Any]], blocked_rows: int, quote_candidates: int) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unknown") for row in resolved)
    reject_reasons = Counter(str(row.get("block_reason") or "unknown") for row in rejected)
    window_counts = Counter()
    known_15m = 0
    for record in resolved:
        windows = as_dict(record.get("outcome_window_labels"))
        if is_known(as_dict(windows.get("15m"))):
            known_15m += 1
        for window in windows.values():
            window_counts[str(as_dict(window).get("outcome_type") or "unknown")] += 1
    return {
        "blocked_rows_scanned": blocked_rows,
        "quote_anchor_candidates": quote_candidates,
        "resolved_rows": len(resolved),
        "known_15m_outcomes": known_15m,
        "records_with_any_known_window": sum(1 for row in resolved if any(is_known(as_dict(window)) for window in as_dict(row.get("outcome_window_labels")).values())),
        "blocked_no_later_snapshot_rows": reject_reasons.get("missing_later_market_snapshot", 0),
        "blocked_no_quote_anchor_rows": reject_reasons.get("missing_valid_execution_price_quote", 0),
        "resolved_status_counts": dict(sorted(statuses.items())),
        "rejected_reason_counts": dict(sorted(reject_reasons.items())),
        "window_outcome_counts": dict(sorted(window_counts.items())),
        "wallets_resolved": len({row.get("wallet") for row in resolved if row.get("wallet")}),
        "tokens_resolved": len({row.get("token_mint") for row in resolved if row.get("token_mint")}),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_entry_context_resolver_report(
    *,
    records: list[dict[str, Any]],
    market_snapshots: list[dict[str, Any]],
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped_snapshots = snapshots_by_mint(market_snapshots)
    blocked_rows = [row for row in records or [] if isinstance(row, dict) and is_blocked_entry_context(row)]
    resolved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    quote_candidates = 0
    for row in blocked_rows:
        if quote_anchor_price(row) is None:
            rejected.append(unresolved_row(row, "missing_valid_execution_price_quote"))
            continue
        quote_candidates += 1
        later_snapshots = later_snapshots_for_row(row, grouped_snapshots)
        if not later_snapshots:
            rejected.append(unresolved_row(row, "missing_later_market_snapshot"))
            continue
        resolved.append(resolved_record(row, later_snapshots, generated_at=generated_at))
    return {
        "generated_at": generated_at,
        "mode": MODE,
        "version": VERSION,
        "review_only": True,
        "read_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "summary": build_summary(resolved, rejected, len(blocked_rows), quote_candidates),
        "resolved_records": resolved,
        "rejected_records": rejected,
        "operator_note": (
            "Resolver is review-only. It only repairs blocked forward rows that have a valid same-transaction "
            "execution-price quote and at least one later market snapshot for the same mint."
        ),
    }
