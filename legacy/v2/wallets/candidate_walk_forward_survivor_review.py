from __future__ import annotations

import statistics
import time
from collections import Counter
from typing import Any

from wallets.candidate_walk_forward_validation import ALLOWED_CONCLUSIONS
from wallets.candidate_walk_forward_validation import entry_context
from wallets.candidate_walk_forward_validation import event_id
from wallets.candidate_walk_forward_validation import event_time
from wallets.candidate_walk_forward_validation import has_valid_entry_context
from wallets.candidate_walk_forward_validation import is_blocked
from wallets.candidate_walk_forward_validation import is_clean_proof_row
from wallets.candidate_walk_forward_validation import merge_repaired_records
from wallets.candidate_walk_forward_validation import outcome_15m
from wallets.candidate_walk_forward_validation import rate
from wallets.candidate_walk_forward_validation import safe_float
from wallets.candidate_walk_forward_validation import sorted_rows
from wallets.candidate_walk_forward_validation import split_train_validation
from wallets.candidate_walk_forward_validation import wallet_address
from wallets.candidate_walk_forward_validation import window_metrics


MODE = "CANDIDATE_WALK_FORWARD_SURVIVOR_REVIEW_ONLY"
VERSION = "candidate_walk_forward_survivor_review.v1"
SURVIVOR_CONCLUSION = "continued_validation"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def outcome_payload(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("outcome_window_labels")).get("15m"))


def block_reasons(row: dict[str, Any]) -> list[str]:
    reasons = row.get("block_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason)]
    if isinstance(reasons, str) and reasons:
        return [reasons]
    status = str(row.get("status") or "")
    return [status] if status.startswith("blocked_") else []


def average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 6) if values else None


def numeric_context_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = safe_float(entry_context(row).get(key))
        if value is not None:
            values.append(value)
    return values


def evidence_quality(row: dict[str, Any], repaired_ids: set[str]) -> str:
    if event_id(row) in repaired_ids or row.get("entry_context_repair"):
        return "repaired_context"
    reasons = block_reasons(row)
    if is_blocked(row) or any("context" in reason or "quote" in reason for reason in reasons):
        return "blocked_missing_context"
    if not has_valid_entry_context(row):
        return "blocked_missing_context"
    if outcome_15m(row) == "unknown":
        return "blocked_missing_outcome"
    return "clean_forward_context"


def evidence_notes(row: dict[str, Any], repaired_ids: set[str], window: str) -> str:
    quality = evidence_quality(row, repaired_ids)
    if quality == "clean_forward_context":
        return f"{window}_window_clean_forward_context"
    if quality == "repaired_context":
        return f"{window}_window_context_repaired_for_review_only"
    if quality == "blocked_missing_context":
        return "excluded_from_proof_missing_or_invalid_entry_context"
    if quality == "blocked_missing_outcome":
        return "excluded_from_proof_missing_outcome"
    return "manual_review_required"


def event_evidence_row(row: dict[str, Any], repaired_ids: set[str], window: str) -> dict[str, Any]:
    ctx = entry_context(row)
    outcome = outcome_15m(row)
    payload = outcome_payload(row)
    return {
        "wallet_address": wallet_address(row),
        "token_address": row.get("token_mint"),
        "token_symbol": row.get("token_symbol"),
        "action": row.get("observed_action") or row.get("action"),
        "observed_at": row.get("signal_time") or row.get("observed_at"),
        "decision_time_snapshot_at": ctx.get("snapshot_time"),
        "market_context_available": has_valid_entry_context(row),
        "liquidity_at_entry": ctx.get("liquidity"),
        "market_cap_at_entry": ctx.get("market_cap"),
        "price_at_entry": ctx.get("price"),
        "outcome_15m": outcome,
        "return_15m_pct": payload.get("pnl_pct"),
        "runner_label": outcome == "runner",
        "flat_label": outcome == "flat",
        "loser_label": outcome in {"loser", "rug", "dead"},
        "blocked_reason": ";".join(block_reasons(row)),
        "repaired_context": event_id(row) in repaired_ids or bool(row.get("entry_context_repair")),
        "evidence_quality": evidence_quality(row, repaired_ids),
        "window": window,
        "event_id": event_id(row),
        "transaction_signature": row.get("transaction_signature"),
        "notes": evidence_notes(row, repaired_ids, window),
    }


def context_summary(clean_rows: list[dict[str, Any]]) -> dict[str, Any]:
    liquidity = numeric_context_values(clean_rows, "liquidity")
    market_cap = numeric_context_values(clean_rows, "market_cap")
    price = numeric_context_values(clean_rows, "price")
    return {
        "average_liquidity_at_entry": average(liquidity),
        "median_liquidity_at_entry": median(liquidity),
        "average_market_cap_at_entry": average(market_cap),
        "median_market_cap_at_entry": median(market_cap),
        "average_price_at_entry": average(price),
        "median_price_at_entry": median(price),
    }


def excluded_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(outcome_15m(row) for row in rows)
    return {
        "excluded_records": len(rows),
        "blocked_records": sum(1 for row in rows if is_blocked(row)),
        "missing_or_invalid_context_records": sum(1 for row in rows if not has_valid_entry_context(row)),
        "unknown_outcome_records": int(outcomes.get("unknown", 0)),
        "blocked_reasons": dict(sorted(Counter(reason for row in rows for reason in block_reasons(row)).items())),
    }


def runner_flat_loser_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = window_metrics(rows)
    return {
        "clean_records": metrics["clean_records"],
        "runner_count": metrics["runner_count"],
        "flat_count": metrics["flat_count"],
        "loser_count": metrics["loser_count"],
        "runner_rate": metrics["runner_rate"],
        "flat_rate": metrics["flat_rate"],
        "loser_rate": metrics["loser_rate"],
        "token_count": metrics["token_count"],
        "context": context_summary(rows),
    }


def top_validation_events(validation_rows: list[dict[str, Any]], repaired_ids: set[str], limit: int = 10) -> list[dict[str, Any]]:
    ordered = sorted(
        validation_rows,
        key=lambda row: (
            outcome_15m(row) != "runner",
            -(safe_float(outcome_payload(row).get("pnl_pct"), 0.0) or 0.0),
            event_time(row),
            event_id(row),
        ),
    )
    return [event_evidence_row(row, repaired_ids, "validation") for row in ordered[: max(0, limit)]]


def reasons_to_continue_validation(train: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    reasons = ["walk_forward_conclusion_survived_validation_window"]
    if train["runner_count"] > 0 and validation["runner_count"] > 0:
        reasons.append("runner_behavior_present_in_train_and_validation")
    if validation["token_count"] > 1:
        reasons.append("validation_events_span_multiple_tokens")
    return reasons


def reasons_not_to_trust(
    *,
    proof_metric_records: int,
    excluded_records: int,
    validation: dict[str, Any],
) -> list[str]:
    reasons = [
        "candidate_validation_layer_only",
        "not_a_trade_signal",
        "no_wallet_trust_mutation_allowed",
        "paper_simulation_not_enabled_by_this_report",
    ]
    if proof_metric_records < 50:
        reasons.append("sample_size_below_paper_trade_gate")
    if excluded_records > 0:
        reasons.append("blocked_or_incomplete_rows_excluded_from_proof")
    if validation["clean_records"] < 25:
        reasons.append("validation_window_sample_still_small")
    return reasons


def wallet_survivor_report(
    *,
    wallet: str,
    rows: list[dict[str, Any]],
    repaired_ids: set[str],
    train_fraction: float,
    walk_forward_wallet: dict[str, Any],
) -> dict[str, Any]:
    ordered = sorted_rows(rows)
    clean_rows = [row for row in ordered if is_clean_proof_row(row)]
    excluded_rows = [row for row in ordered if not is_clean_proof_row(row)]
    train_rows, validation_rows = split_train_validation(clean_rows, train_fraction)
    train = runner_flat_loser_summary(train_rows)
    validation = runner_flat_loser_summary(validation_rows)
    excluded = excluded_summary(excluded_rows)
    train_events = [event_evidence_row(row, repaired_ids, "train") for row in train_rows]
    validation_events = [event_evidence_row(row, repaired_ids, "validation") for row in validation_rows]
    return {
        "wallet_address": wallet,
        "walk_forward_conclusion": walk_forward_wallet.get("conclusion"),
        "paper_simulation_readiness": "not_ready",
        "candidate_records": len(ordered),
        "proof_metric_records": len(clean_rows),
        "excluded_records": len(excluded_rows),
        "train": train,
        "validation": validation,
        "excluded_event_summary": excluded,
        "train_event_evidence": train_events,
        "validation_event_evidence": validation_events,
        "top_validation_events": top_validation_events(validation_rows, repaired_ids),
        "reasons_to_continue_validation": reasons_to_continue_validation(train, validation),
        "reasons_not_to_trust": reasons_not_to_trust(
            proof_metric_records=len(clean_rows),
            excluded_records=len(excluded_rows),
            validation=validation,
        ),
        "operator_action": "continue_candidate_only_forward_validation",
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def survivor_wallets_from_report(
    walk_forward_report: dict[str, Any],
    include_conclusions: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed = include_conclusions or {SURVIVOR_CONCLUSION}
    wallets = walk_forward_report.get("wallets") if isinstance(walk_forward_report.get("wallets"), list) else []
    return [
        row for row in wallets
        if isinstance(row, dict)
        and str(row.get("conclusion") or "") in allowed
        and str(row.get("wallet_address") or "")
    ]


def build_candidate_walk_forward_survivor_review(
    *,
    walk_forward_report: dict[str, Any],
    records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]] | None = None,
    generated_at: float | None = None,
    include_conclusions: list[str] | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    repaired_records = repaired_records or []
    allowed = set(include_conclusions or [SURVIVOR_CONCLUSION])
    invalid = sorted(allowed - ALLOWED_CONCLUSIONS)
    if invalid:
        raise ValueError(f"Unsupported walk-forward conclusions: {invalid}")
    train_fraction = safe_float(
        as_dict(walk_forward_report.get("train_validation_config")).get("train_fraction"),
        0.7,
    ) or 0.7
    merged_records = merge_repaired_records(records, repaired_records)
    repaired_ids = {event_id(row) for row in repaired_records if event_id(row)}
    survivors = survivor_wallets_from_report(walk_forward_report, allowed)
    survivor_addresses = [str(row.get("wallet_address")) for row in survivors]
    by_wallet = {wallet: [] for wallet in survivor_addresses}
    for row in merged_records:
        wallet = wallet_address(row)
        if wallet in by_wallet:
            by_wallet[wallet].append(row)
    wallet_reports = [
        wallet_survivor_report(
            wallet=wallet,
            rows=by_wallet.get(wallet, []),
            repaired_ids=repaired_ids,
            train_fraction=train_fraction,
            walk_forward_wallet=survivor,
        )
        for survivor in survivors
        for wallet in [str(survivor.get("wallet_address"))]
    ]
    all_events = [
        event
        for wallet in wallet_reports
        for event in (wallet.get("train_event_evidence") or []) + (wallet.get("validation_event_evidence") or [])
    ]
    total_proof_records = sum(int(wallet.get("proof_metric_records") or 0) for wallet in wallet_reports)
    total_excluded = sum(int(wallet.get("excluded_records") or 0) for wallet in wallet_reports)
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
        "train_validation_config": {
            "train_fraction": train_fraction,
            "candidate_wallets_only": True,
            "proof_metrics_exclude_blocked_rows": True,
            "included_conclusions": sorted(allowed),
        },
        "summary": {
            "input_records": len(records),
            "repaired_records": len(repaired_records),
            "merged_records": len(merged_records),
            "survivor_wallets": len(wallet_reports),
            "proof_metric_records": total_proof_records,
            "excluded_records": total_excluded,
            "train_event_rows": sum(int(wallet["train"]["clean_records"]) for wallet in wallet_reports),
            "validation_event_rows": sum(int(wallet["validation"]["clean_records"]) for wallet in wallet_reports),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "wallets": wallet_reports,
        "event_evidence": all_events,
        "operator_note": (
            "Survivor review explains candidate walk-forward rows only. "
            "It does not create trade signals, promote wallets, mutate trust, or enable paper trading."
        ),
    }
