from __future__ import annotations

import time
from collections import Counter
from typing import Any


MODE = "CANDIDATE_WALK_FORWARD_VALIDATION_REVIEW_ONLY"
VERSION = "candidate_walk_forward_validation.v1"

DEFAULT_CANDIDATE_WALLETS = [
    "2tgUbS9UMoQD6GkDZBiqKYCURnGrSb6ocYwRABrSJUvY",
    "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN",
    "D11LfGmruiKraNB9BtPqb1ELEYnNtpsNDuft32wArYV3",
]

ALLOWED_CONCLUSIONS = {"continued_validation", "degraded", "inconclusive", "rejected"}
KNOWN_OUTCOMES = {"runner", "flat", "loser", "rug", "dead"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def wallet_address(row: dict[str, Any]) -> str:
    return str(row.get("wallet") or row.get("wallet_address") or "").strip()


def entry_context(row: dict[str, Any]) -> dict[str, Any]:
    return as_dict(as_dict(row.get("decision_context")).get("estimated_entry_context"))


def outcome_15m(row: dict[str, Any]) -> str:
    labels = as_dict(row.get("outcome_window_labels"))
    return str(as_dict(labels.get("15m")).get("outcome_type") or "unknown").lower()


def event_time(row: dict[str, Any]) -> float:
    return safe_float(row.get("signal_time") or row.get("observed_at"), 0.0) or 0.0


def event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or "").strip()


def is_blocked(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    return status.startswith("blocked_") or bool(row.get("block_reasons"))


def has_valid_entry_context(row: dict[str, Any]) -> bool:
    ctx = entry_context(row)
    has_market_context = any(ctx.get(key) not in (None, "") for key in ("price", "liquidity", "market_cap"))
    has_quote_anchor = any(
        ctx.get(key) not in (None, "")
        for key in ("execution_price_quote", "quote_amount_delta", "snapshot_time")
    )
    return bool(has_market_context and has_quote_anchor)


def is_clean_proof_row(row: dict[str, Any]) -> bool:
    return not is_blocked(row) and outcome_15m(row) in KNOWN_OUTCOMES and has_valid_entry_context(row)


def sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (event_time(row), event_id(row)))


def merge_repaired_records(records: list[dict[str, Any]], repaired_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for row in records:
        eid = event_id(row)
        if eid:
            positions[eid] = len(merged)
        merged.append(dict(row))
    for row in repaired_records:
        next_row = dict(row)
        next_row["entry_context_repair"] = True
        eid = event_id(next_row)
        if eid and eid in positions:
            merged[positions[eid]] = next_row
        else:
            if eid:
                positions[eid] = len(merged)
            merged.append(next_row)
    return merged


def split_train_validation(rows: list[dict[str, Any]], train_fraction: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted_rows(rows)
    if not ordered:
        return [], []
    fraction = min(max(float(train_fraction), 0.0), 1.0)
    split_at = int(len(ordered) * fraction)
    if len(ordered) > 1:
        split_at = min(max(split_at, 1), len(ordered) - 1)
    return ordered[:split_at], ordered[split_at:]


def window_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(outcome_15m(row) for row in rows)
    clean = len(rows)
    runner = int(counts.get("runner", 0))
    flat = int(counts.get("flat", 0))
    loser = int(counts.get("loser", 0) + counts.get("rug", 0) + counts.get("dead", 0))
    return {
        "clean_records": clean,
        "runner_count": runner,
        "flat_count": flat,
        "loser_count": loser,
        "runner_rate": rate(runner, clean),
        "flat_rate": rate(flat, clean),
        "loser_rate": rate(loser, clean),
        "first_signal_time": event_time(rows[0]) if rows else None,
        "last_signal_time": event_time(rows[-1]) if rows else None,
        "event_ids": [event_id(row) for row in rows if event_id(row)],
        "token_count": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
    }


def conclusion_for_wallet(
    *,
    train: dict[str, Any],
    validation: dict[str, Any],
    min_train_clean_rows: int,
    min_validation_clean_rows: int,
    degradation_tolerance: float,
) -> str:
    if train["clean_records"] < min_train_clean_rows or validation["clean_records"] < min_validation_clean_rows:
        return "inconclusive"
    if train["runner_count"] <= 0:
        return "rejected"
    if validation["runner_count"] <= 0:
        return "degraded"
    if validation["runner_rate"] < train["runner_rate"] * float(degradation_tolerance):
        return "degraded"
    return "continued_validation"


def context_quality(candidate_rows: list[dict[str, Any]], clean_rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [row for row in candidate_rows if is_blocked(row)]
    missing_context = [row for row in candidate_rows if not has_valid_entry_context(row)]
    unknown = [row for row in candidate_rows if outcome_15m(row) not in KNOWN_OUTCOMES]
    return {
        "candidate_records": len(candidate_rows),
        "clean_records": len(clean_rows),
        "excluded_records": max(0, len(candidate_rows) - len(clean_rows)),
        "blocked_records": len(blocked),
        "missing_or_invalid_context_records": len(missing_context),
        "unknown_outcome_records": len(unknown),
        "clean_record_rate": rate(len(clean_rows), len(candidate_rows)),
        "blocked_record_rate": rate(len(blocked), len(candidate_rows)),
        "context_completion_rate": rate(len(candidate_rows) - len(missing_context), len(candidate_rows)),
    }


def reasons_to_continue(conclusion: str, train: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if train["runner_count"] > 0:
        reasons.append("training_window_runner_behavior_observed")
    if validation["runner_count"] > 0:
        reasons.append("validation_window_runner_behavior_persisted")
    if conclusion == "continued_validation":
        reasons.append("out_of_sample_validation_survived")
    return reasons or ["continue_only_if_more_clean_forward_rows_arrive"]


def reasons_not_to_trust(context: dict[str, Any], train: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    reasons = [
        "walk_forward_is_candidate_validation_only",
        "no_wallet_trust_mutation_allowed",
    ]
    if train["clean_records"] + validation["clean_records"] < 50:
        reasons.append("sample_size_below_paper_trade_gate")
    if context["excluded_records"] > 0:
        reasons.append("blocked_or_incomplete_rows_excluded_from_proof")
    if validation["clean_records"] == 0:
        reasons.append("missing_clean_validation_window")
    return reasons


def wallet_report(
    *,
    wallet: str,
    rows: list[dict[str, Any]],
    train_fraction: float,
    min_train_clean_rows: int,
    min_validation_clean_rows: int,
    degradation_tolerance: float,
) -> dict[str, Any]:
    clean = [row for row in sorted_rows(rows) if is_clean_proof_row(row)]
    train_rows, validation_rows = split_train_validation(clean, train_fraction)
    train = window_metrics(train_rows)
    validation = window_metrics(validation_rows)
    context = context_quality(rows, clean)
    conclusion = conclusion_for_wallet(
        train=train,
        validation=validation,
        min_train_clean_rows=min_train_clean_rows,
        min_validation_clean_rows=min_validation_clean_rows,
        degradation_tolerance=degradation_tolerance,
    )
    return {
        "wallet_address": wallet,
        "conclusion": conclusion,
        "candidate_records": len(rows),
        "proof_metric_records": len(clean),
        "train": train,
        "validation": validation,
        "context_quality": context,
        "reasons_to_continue_validating": reasons_to_continue(conclusion, train, validation),
        "reasons_not_to_trust": reasons_not_to_trust(context, train, validation),
        "promotion_allowed": False,
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def build_candidate_walk_forward_validation_report(
    *,
    records: list[dict[str, Any]],
    repaired_records: list[dict[str, Any]] | None = None,
    candidate_wallets: list[str] | None = None,
    generated_at: float | None = None,
    train_fraction: float = 0.7,
    min_train_clean_rows: int = 10,
    min_validation_clean_rows: int = 5,
    degradation_tolerance: float = 0.5,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    repaired_records = repaired_records or []
    merged_records = merge_repaired_records(records, repaired_records)
    candidates = [str(wallet) for wallet in (candidate_wallets or DEFAULT_CANDIDATE_WALLETS) if str(wallet)]
    candidate_set = set(candidates)
    candidate_records = [row for row in merged_records if wallet_address(row) in candidate_set]
    clean_records = [row for row in candidate_records if is_clean_proof_row(row)]
    by_wallet = {wallet: [] for wallet in candidates}
    for row in candidate_records:
        by_wallet.setdefault(wallet_address(row), []).append(row)
    wallets = [
        wallet_report(
            wallet=wallet,
            rows=by_wallet.get(wallet, []),
            train_fraction=train_fraction,
            min_train_clean_rows=min_train_clean_rows,
            min_validation_clean_rows=min_validation_clean_rows,
            degradation_tolerance=degradation_tolerance,
        )
        for wallet in candidates
    ]
    conclusion_counts = Counter(row["conclusion"] for row in wallets)
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
            "train_fraction": float(train_fraction),
            "min_train_clean_rows": int(min_train_clean_rows),
            "min_validation_clean_rows": int(min_validation_clean_rows),
            "degradation_tolerance": float(degradation_tolerance),
            "candidate_wallets_only": True,
            "proof_metrics_exclude_blocked_rows": True,
        },
        "frozen_wallet_candidate_snapshot": {
            "generated_at": generated_at,
            "candidate_wallets": candidates,
            "candidate_count": len(candidates),
        },
        "summary": {
            "input_records": len(records),
            "repaired_records": len(repaired_records),
            "merged_records": len(merged_records),
            "candidate_wallets": len(candidates),
            "candidate_records": len(candidate_records),
            "clean_records": len(clean_records),
            "excluded_records": max(0, len(candidate_records) - len(clean_records)),
            "continued_validation_wallets": int(conclusion_counts.get("continued_validation", 0)),
            "degraded_wallets": int(conclusion_counts.get("degraded", 0)),
            "inconclusive_wallets": int(conclusion_counts.get("inconclusive", 0)),
            "rejected_wallets": int(conclusion_counts.get("rejected", 0)),
            "promotions_allowed": 0,
            "wallet_list_mutations": 0,
            "wallet_trust_mutations": 0,
            "auto_trust_mutations": 0,
        },
        "context_quality_report": context_quality(candidate_records, clean_records),
        "persistence_degradation_summary": {
            "continued_validation_wallets": int(conclusion_counts.get("continued_validation", 0)),
            "degraded_wallets": int(conclusion_counts.get("degraded", 0)),
            "inconclusive_wallets": int(conclusion_counts.get("inconclusive", 0)),
            "rejected_wallets": int(conclusion_counts.get("rejected", 0)),
            "allowed_conclusions": sorted(ALLOWED_CONCLUSIONS),
        },
        "wallets": wallets,
        "operator_note": (
            "Candidate-only walk-forward validation is an evidence packet. "
            "It does not create trade signals, promote wallets, mutate trust, or broaden scanning."
        ),
    }
