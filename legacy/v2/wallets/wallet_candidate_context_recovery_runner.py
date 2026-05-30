from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _wallets_from_replay_event(event: dict[str, Any]) -> set[str]:
    context = as_dict(event.get("decision_context"))
    wallets: set[str] = set()
    for item in as_list(context.get("triggering_wallets")):
        if isinstance(item, dict):
            wallet = _clean_str(item.get("wallet") or item.get("address"))
        else:
            wallet = _clean_str(item)
        if wallet:
            wallets.add(wallet)
    wallet = _clean_str(context.get("wallet") or event.get("wallet"))
    if wallet:
        wallets.add(wallet)
    return wallets


def _has_decision_time_context(row: dict[str, Any]) -> bool:
    context = as_dict(row.get("estimated_entry_context") or row.get("decision_time_context"))
    if not context:
        return False
    for key in ("price", "market_cap", "market_cap_usd", "liquidity", "liquidity_usd", "fdv"):
        value = context.get(key)
        if value not in (None, "", 0, "0"):
            return True
    return False


def _has_known_outcome(row: dict[str, Any]) -> bool:
    outcome = as_dict(row.get("later_token_outcome") or row.get("later_outcome"))
    if not outcome:
        return False
    outcome_type = _clean_str(outcome.get("outcome_type") or outcome.get("label") or outcome.get("classification")).lower()
    return bool(outcome_type and outcome_type not in {"unknown", "missing", "unlabeled", "none"})


def _index_evidence(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = _clean_str(row.get("wallet"))
        if wallet:
            by_wallet[wallet].append(row)
    return by_wallet


def _index_missing_market_rows(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in as_list(report.get("targets")):
        if not isinstance(target, dict):
            continue
        wallets = [_clean_str(wallet) for wallet in as_list(target.get("wallets"))]
        for wallet in wallets:
            if wallet:
                by_wallet[wallet].append(target)
    return by_wallet


def _index_replay_events(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        for wallet in _wallets_from_replay_event(row):
            by_wallet[wallet].append(row)
    return by_wallet


def _index_backfill_records(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = _clean_str(row.get("wallet"))
        if wallet:
            by_wallet[wallet].append(row)
    return by_wallet


def _linked_mints(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({
        _clean_str(row.get("token_mint") or row.get("mint"))
        for row in rows
        if _clean_str(row.get("token_mint") or row.get("mint"))
    })


def _linked_transactions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({
        _clean_str(row.get("transaction_signature") or row.get("signature") or row.get("tx"))
        for row in rows
        if _clean_str(row.get("transaction_signature") or row.get("signature") or row.get("tx"))
    })


def _missing_market_row_count(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        total += max(1, safe_int(row.get("evidence_rows"), 1))
    return total


def _remaining_blockers(
    *,
    target: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    missing_market_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    backfill_rows: list[dict[str, Any]],
    rows_with_entry_context: int,
    rows_with_known_outcomes: int,
    linked_transactions: list[str],
) -> list[str]:
    blockers: list[str] = []
    if not rows_with_entry_context or missing_market_rows:
        blockers.append("missing_decision_time_market_context")
    if not rows_with_known_outcomes or safe_int(target.get("missing_known_outcomes")) > rows_with_known_outcomes:
        blockers.append("missing_outcome_labels")
    if not linked_transactions and not replay_rows and not backfill_rows:
        blockers.append("blocked_missing_transaction")
    if evidence_rows and not any(str(row.get("enrichment_status") or "").upper() == "ENRICHED" for row in evidence_rows):
        blockers.append("blocked_low_confidence")
    return list(dict.fromkeys(blockers))


def build_wallet_candidate_context_recovery_report(
    *,
    recovery_queue: dict[str, Any],
    enriched_evidence: list[Any] | None = None,
    missing_market_context: dict[str, Any] | None = None,
    replay_events: list[Any] | None = None,
    historical_backfill_records: list[Any] | None = None,
    generated_at: float | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    targets = [
        target
        for target in as_list(as_dict(recovery_queue).get("targets"))
        if isinstance(target, dict) and _clean_str(target.get("wallet"))
    ]
    evidence_by_wallet = _index_evidence(as_list(enriched_evidence))
    missing_market_by_wallet = _index_missing_market_rows(as_dict(missing_market_context))
    replay_by_wallet = _index_replay_events(as_list(replay_events))
    backfill_by_wallet = _index_backfill_records(as_list(historical_backfill_records))

    wallets: list[dict[str, Any]] = []
    totals = {
        "evidence_rows_linked": 0,
        "replay_events_linked": 0,
        "missing_market_context_rows_linked": 0,
        "historical_backfill_records_linked": 0,
        "recovered_rows": 0,
        "wallets_with_existing_artifacts": 0,
        "wallets_without_existing_artifacts": 0,
        "still_blocked_wallets": 0,
    }

    for target in targets:
        wallet = _clean_str(target.get("wallet"))
        evidence_rows = evidence_by_wallet.get(wallet, [])
        replay_rows = replay_by_wallet.get(wallet, [])
        missing_market_rows = missing_market_by_wallet.get(wallet, [])
        backfill_rows = backfill_by_wallet.get(wallet, [])
        linked_mints = _linked_mints([*evidence_rows, *missing_market_rows, *backfill_rows])
        linked_transactions = _linked_transactions([*evidence_rows, *backfill_rows])
        rows_with_entry_context = sum(1 for row in evidence_rows if _has_decision_time_context(row))
        rows_with_known_outcomes = sum(1 for row in evidence_rows if _has_known_outcome(row))
        recovered_rows = sum(1 for row in evidence_rows if _has_decision_time_context(row) and _has_known_outcome(row))
        missing_market_count = _missing_market_row_count(missing_market_rows)
        has_existing_artifacts = bool(evidence_rows or replay_rows or missing_market_rows or backfill_rows)
        remaining_blockers = _remaining_blockers(
            target=target,
            evidence_rows=evidence_rows,
            missing_market_rows=missing_market_rows,
            replay_rows=replay_rows,
            backfill_rows=backfill_rows,
            rows_with_entry_context=rows_with_entry_context,
            rows_with_known_outcomes=rows_with_known_outcomes,
            linked_transactions=linked_transactions,
        )
        status = "existing_artifacts_linked" if has_existing_artifacts else "blocked_no_existing_artifacts"
        if status == "blocked_no_existing_artifacts" and "blocked_missing_transaction" not in remaining_blockers:
            remaining_blockers.append("blocked_missing_transaction")

        totals["evidence_rows_linked"] += len(evidence_rows)
        totals["replay_events_linked"] += len(replay_rows)
        totals["missing_market_context_rows_linked"] += missing_market_count
        totals["historical_backfill_records_linked"] += len(backfill_rows)
        totals["recovered_rows"] += recovered_rows
        totals["wallets_with_existing_artifacts"] += 1 if has_existing_artifacts else 0
        totals["wallets_without_existing_artifacts"] += 0 if has_existing_artifacts else 1
        totals["still_blocked_wallets"] += 1 if remaining_blockers else 0

        wallets.append({
            "wallet": wallet,
            "source_bucket": target.get("source_bucket") or "unknown",
            "audit_status": target.get("audit_status"),
            "recommendation_action": target.get("recommendation_action"),
            "current_missing_known_outcomes": safe_int(target.get("missing_known_outcomes")),
            "current_missing_round_trip_lifecycles": safe_int(target.get("missing_round_trip_lifecycles")),
            "status": status,
            "remaining_blockers": remaining_blockers,
            "existing_evidence": {
                "total_rows": len(evidence_rows),
                "rows_with_entry_context": rows_with_entry_context,
                "rows_with_known_outcomes": rows_with_known_outcomes,
                "missing_market_context_rows": missing_market_count,
                "missing_outcome_label_rows": max(0, len(evidence_rows) - rows_with_known_outcomes),
                "linked_mints": linked_mints[:25],
                "linked_transactions": linked_transactions[:25],
            },
            "replay_events_linked": len(replay_rows),
            "missing_market_context_rows_linked": missing_market_count,
            "historical_backfill_records_linked": len(backfill_rows),
            "recovered_rows": recovered_rows,
            "confidence": {
                "evidence_confidence": "partial" if has_existing_artifacts else "blocked",
                "completeness_score": round(min(1.0, (rows_with_entry_context + rows_with_known_outcomes) / 4), 3),
                "replay_confidence": "linked" if replay_rows else "missing",
            },
            "recovery_method": "existing_artifact_linkage_only",
            "missing_data_warnings": remaining_blockers,
        })

    wallets.sort(key=lambda row: (
        0 if row["status"] == "existing_artifacts_linked" else 1,
        -safe_int(row["existing_evidence"]["total_rows"]),
        str(row["wallet"]),
    ))
    capped = wallets[: int(limit)]
    return {
        "generated_at": generated_at or time.time(),
        "mode": "WALLET_CANDIDATE_CONTEXT_RECOVERY_RUNNER_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "targets_processed": len(targets),
            **totals,
        },
        "count": len(capped),
        "wallets": capped,
        "operator_note": "Bounded read-only recovery runner. It links existing artifacts and preserves blockers; it does not fetch external data, fabricate market context, approve trust changes, trade, or mutate wallet lists.",
    }
