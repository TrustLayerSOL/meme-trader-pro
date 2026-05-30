from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


MODE = "FORWARD_CALIBRATION_SCORECARD_REVIEW_ONLY"
VERSION = "forward_calibration_scorecard.v1"
KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser", "flat"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def outcome_15m(row: dict[str, Any]) -> str:
    windows = as_dict(row.get("outcome_window_labels"))
    return str(as_dict(windows.get("15m")).get("outcome_type") or "unknown").lower()


def is_known_outcome(label: str) -> bool:
    return str(label).lower() in KNOWN_OUTCOMES


def wallet_status(*, known: int, runner: int, rug: int, dead: int, loser: int, flat: int, blocked: int) -> str:
    if rug > 0 or dead > 0 or loser > runner:
        return "risk_review_candidate"
    if runner > 0:
        return "review_behavioral_signal"
    if known >= 2 and flat == known:
        return "flat_noise_candidate"
    if blocked > 0 and known == 0:
        return "blocked_missing_context"
    return "collect_more_forward_evidence"


def wallet_row(wallet: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(outcome_15m(row) for row in rows)
    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    known = sum(outcomes.get(label, 0) for label in KNOWN_OUTCOMES)
    blocked = sum(count for status, count in statuses.items() if status.startswith("blocked_"))
    runner = outcomes.get("runner", 0)
    rug = outcomes.get("rug", 0)
    dead = outcomes.get("dead", 0)
    loser = outcomes.get("loser", 0)
    flat = outcomes.get("flat", 0)
    total = len(rows)
    return {
        "wallet": wallet,
        "review_only": True,
        "records": total,
        "known_15m": known,
        "unknown_15m": outcomes.get("unknown", 0),
        "runner_15m": runner,
        "rug_15m": rug,
        "dead_15m": dead,
        "loser_15m": loser,
        "flat_15m": flat,
        "blocked_records": blocked,
        "known_15m_rate": round(known / total, 4) if total else 0.0,
        "runner_rate_known_15m": round(runner / known, 4) if known else 0.0,
        "rug_rate_known_15m": round(rug / known, 4) if known else 0.0,
        "flat_rate_known_15m": round(flat / known, 4) if known else 0.0,
        "status_counts": dict(sorted(statuses.items())),
        "outcomes_15m": dict(sorted(outcomes.items())),
        "tokens": len({row.get("token_mint") for row in rows if row.get("token_mint")}),
        "calibration_status": wallet_status(
            known=known,
            runner=runner,
            rug=rug,
            dead=dead,
            loser=loser,
            flat=flat,
            blocked=blocked,
        ),
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def rank_wallet(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    status_rank = {
        "review_behavioral_signal": 0,
        "risk_review_candidate": 1,
        "collect_more_forward_evidence": 2,
        "blocked_missing_context": 3,
        "flat_noise_candidate": 4,
    }.get(str(row.get("calibration_status")), 9)
    return (
        status_rank,
        -safe_int(row.get("runner_15m")),
        -safe_int(row.get("known_15m")),
        safe_int(row.get("rug_15m")) + safe_int(row.get("dead_15m")) + safe_int(row.get("loser_15m")),
        str(row.get("wallet") or ""),
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("calibration_status") or "unknown") for row in rows)
    return {
        "wallets": len(rows),
        "records": sum(safe_int(row.get("records")) for row in rows),
        "known_15m_outcomes": sum(safe_int(row.get("known_15m")) for row in rows),
        "runner_15m_outcomes": sum(safe_int(row.get("runner_15m")) for row in rows),
        "rug_15m_outcomes": sum(safe_int(row.get("rug_15m")) for row in rows),
        "dead_15m_outcomes": sum(safe_int(row.get("dead_15m")) for row in rows),
        "loser_15m_outcomes": sum(safe_int(row.get("loser_15m")) for row in rows),
        "flat_15m_outcomes": sum(safe_int(row.get("flat_15m")) for row in rows),
        "blocked_records": sum(safe_int(row.get("blocked_records")) for row in rows),
        "review_behavioral_signal_wallets": status_counts.get("review_behavioral_signal", 0),
        "risk_review_candidate_wallets": status_counts.get("risk_review_candidate", 0),
        "flat_noise_candidate_wallets": status_counts.get("flat_noise_candidate", 0),
        "blocked_missing_context_wallets": status_counts.get("blocked_missing_context", 0),
        "collect_more_forward_evidence_wallets": status_counts.get("collect_more_forward_evidence", 0),
        "wallet_list_mutations": 0,
        "auto_trust_mutations": 0,
    }


def build_forward_calibration_scorecard(
    records: list[dict[str, Any]],
    *,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated_at = time.time() if generated_at is None else float(generated_at)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records or []:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get("wallet") or "").strip()
        if wallet:
            grouped[wallet].append(row)
    rows = sorted((wallet_row(wallet, wallet_rows) for wallet, wallet_rows in grouped.items()), key=rank_wallet)
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
        "summary": summarize(rows),
        "wallets": rows,
        "operator_note": (
            "Forward calibration scorecard is review-only. It can identify flat/noise wallets "
            "or wallets needing deeper review, but it cannot promote, demote, trade, or mutate lists."
        ),
    }
