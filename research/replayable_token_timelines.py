from __future__ import annotations

import time
from typing import Any


MODE = "REPLAYABLE_TOKEN_TIMELINES_REVIEW_ONLY"


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


def first_int(values: list[Any], default: int = 0) -> int:
    for value in values:
        if value not in (None, ""):
            return safe_int(value, default)
    return default


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def build_replayable_token_timelines_report(
    *,
    evidence_layer_completion: dict[str, Any],
    recovery_closeout: dict[str, Any],
    missing_market_context: dict[str, Any],
    onchain_market_context: dict[str, Any],
    supply_evidence: dict[str, Any],
    stage6_readiness: dict[str, Any],
    stage8_readiness: dict[str, Any],
    generated_at: float | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    evidence_summary = as_dict(evidence_layer_completion.get("summary"))
    closeout_summary = as_dict(recovery_closeout.get("summary"))
    missing_summary = as_dict(missing_market_context.get("summary"))
    onchain_summary = as_dict(onchain_market_context.get("summary"))
    supply_summary = as_dict(supply_evidence.get("summary"))
    stage6_summary = as_dict(stage6_readiness.get("summary"))
    stage8_summary = as_dict(stage8_readiness.get("summary"))

    target_mints = safe_int(missing_summary.get("target_mints"))
    missing_context_rows = safe_int(missing_summary.get("missing_market_context_rows"))
    blocked_wallets = safe_int(closeout_summary.get("still_blocked_wallets"))
    needs_outcomes = safe_int(closeout_summary.get("needs_outcome_labels"))
    needs_market = safe_int(closeout_summary.get("needs_market_context"))
    needs_transactions = safe_int(closeout_summary.get("needs_transaction_linkage"))
    records_scanned = safe_int(onchain_summary.get("records_scanned"))
    price_recovered = safe_int(onchain_summary.get("price_recovered_records"))
    liquidity_recovered = safe_int(onchain_summary.get("liquidity_recovered_records"))
    score_ready_records = first_int([onchain_summary.get("score_ready_records"), onchain_summary.get("score_ready_candidate_records")])
    market_cap_recovered = first_int([onchain_summary.get("market_cap_recovered_records"), onchain_summary.get("score_ready_records")])
    supply_scanned = first_int([supply_summary.get("records_scanned"), supply_summary.get("candidate_rows")])
    supply_recovered = safe_int(supply_summary.get("supply_recovered_records"))

    gates = [
        gate(
            "live_execution_locked",
            evidence_layer_completion.get("live_execution_locked") is True
            and recovery_closeout.get("live_execution_locked") is True
            and missing_market_context.get("live_execution_locked") is True
            and onchain_market_context.get("live_execution_locked") is True
            and supply_evidence.get("live_execution_locked") is True
            and stage6_readiness.get("live_execution_locked") is True
            and stage8_readiness.get("live_execution_locked") is True,
            "Timeline work must stay review-only with live execution locked.",
        ),
        gate(
            "evidence_layer_complete",
            safe_int(evidence_summary.get("evidence_layer_completion_pct")) == 100,
            "Replayable timelines consume the completed Evidence Layer handoff.",
        ),
        gate(
            "blocked_wallets_routed",
            blocked_wallets > 0 and needs_transactions == 0,
            "Blocked wallets must be routed without hidden transaction-linkage blockers.",
        ),
        gate(
            "market_context_targets_inventoryed",
            target_mints > 0 and missing_context_rows > 0,
            "Missing decision-time market-context rows must be inventoried by token mint.",
        ),
        gate(
            "outcome_label_gap_inventoryed",
            needs_outcomes > 0,
            "Later outcome-label gaps must be explicit before timeline work can close.",
        ),
        gate(
            "onchain_context_classified",
            records_scanned >= missing_context_rows and records_scanned > 0,
            "On-chain market-context recovery must classify the missing-context records.",
        ),
        gate(
            "supply_requirements_classified",
            supply_scanned > 0 and supply_scanned <= max(missing_context_rows, records_scanned),
            "Historical supply requirements must be classified instead of inferred from current state.",
        ),
        gate(
            "decision_time_and_later_outcomes_separated",
            safe_int(stage6_summary.get("stage6_realism_contract_completion_pct")) == 100
            and safe_int(stage8_summary.get("stage8_validation_contract_completion_pct")) == 100,
            "Decision-time context and later outcomes must remain separated through Stage 6 and Stage 8 gates.",
        ),
        gate(
            "trust_changes_blocked",
            safe_int(evidence_summary.get("wallet_score_readiness_pct")) < 100
            and evidence_layer_completion.get("wallet_list_mutated") is not True,
            "Wallet trust changes must remain blocked until timeline and score data are fully ready.",
        ),
    ]

    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    completion_pct = pct(len(passed), len(gates))
    readiness_pct = min(
        pct(score_ready_records, max(1, records_scanned)),
        safe_int(stage8_summary.get("proof_readiness_pct")),
    )
    blockers = residual_blockers(
        needs_market=needs_market,
        needs_outcomes=needs_outcomes,
        price_recovered=price_recovered,
        liquidity_recovered=liquidity_recovered,
        market_cap_recovered=market_cap_recovered,
        supply_recovered=supply_recovered,
        stage6_gaps=as_list(stage6_readiness.get("blocking_data_gaps")),
        stage8_gaps=as_list(stage8_readiness.get("evidence_gaps")),
    )
    targets = build_timeline_targets(
        missing_market_context=missing_market_context,
        recovery_closeout=recovery_closeout,
        limit=limit,
    )
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "replayable_token_timelines_completion_pct": completion_pct,
            "timeline_data_readiness_pct": readiness_pct,
            "target_mints": target_mints,
            "missing_market_context_rows": missing_context_rows,
            "blocked_wallets_routed": blocked_wallets,
            "wallets_needing_market_context": needs_market,
            "wallets_needing_outcome_labels": needs_outcomes,
            "transaction_linkage_blockers": needs_transactions,
            "onchain_records_scanned": records_scanned,
            "price_recovered_records": price_recovered,
            "liquidity_recovered_records": liquidity_recovered,
            "market_cap_recovered_records": market_cap_recovered,
            "score_ready_records": score_ready_records,
            "supply_records_scanned": supply_scanned,
            "supply_recovered_records": supply_recovered,
        },
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "residual_data_blockers": blockers,
        "timeline_targets": targets,
        "next_required_actions": next_required_actions(blockers),
        "operator_note": (
            "Replayable Token Timelines are complete as a review/control layer when every blocked wallet and token context gap is inventoried, "
            "classified, and routed. This does not mean the historical data is score-ready."
        ),
    }


def residual_blockers(
    *,
    needs_market: int,
    needs_outcomes: int,
    price_recovered: int,
    liquidity_recovered: int,
    market_cap_recovered: int,
    supply_recovered: int,
    stage6_gaps: list[Any],
    stage8_gaps: list[Any],
) -> list[str]:
    blockers: list[str] = []
    if needs_market > 0:
        blockers.append("decision_time_market_context_requires_reconstruction")
    if needs_outcomes > 0:
        blockers.append("outcome_labels_require_replay_safe_timelines")
    if price_recovered <= 0 or "missing_price" in stage6_gaps:
        blockers.append("historical_price_still_incomplete")
    if liquidity_recovered <= 0 or "missing_liquidity" in stage6_gaps:
        blockers.append("historical_liquidity_still_incomplete")
    if market_cap_recovered <= 0 or "missing_market_cap" in stage6_gaps:
        blockers.append("historical_market_cap_still_incomplete")
    if supply_recovered <= 0 or "historical_supply_still_missing" in stage6_gaps:
        blockers.append("historical_supply_still_missing")
    if "low_known_outcome_coverage" in stage8_gaps:
        blockers.append("known_outcome_coverage_still_low")
    return sorted(dict.fromkeys(blockers))


def build_timeline_targets(
    *,
    missing_market_context: dict[str, Any],
    recovery_closeout: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    wallet_action_counts: dict[str, int] = {}
    for row in as_list(recovery_closeout.get("wallets")):
        if not isinstance(row, dict):
            continue
        action = str(row.get("next_action") or "")
        for wallet in [str(row.get("wallet") or "").strip()]:
            if wallet and action in {"BACKFILL_MARKET_CONTEXT_AND_OUTCOME_LABELS", "BACKFILL_MARKET_CONTEXT"}:
                wallet_action_counts[wallet] = wallet_action_counts.get(wallet, 0) + 1

    targets: list[dict[str, Any]] = []
    for row in as_list(missing_market_context.get("targets")):
        if not isinstance(row, dict):
            continue
        wallets = [str(wallet) for wallet in as_list(row.get("wallets")) if str(wallet)]
        targets.append({
            "token_mint": row.get("token_mint"),
            "next_timeline_step": timeline_step(row),
            "evidence_rows": safe_int(row.get("evidence_rows")),
            "known_outcome_rows": safe_int(row.get("known_outcome_rows")),
            "unknown_outcome_rows": safe_int(row.get("unknown_outcome_rows")),
            "wallets_affected": len(wallets),
            "blocked_wallets_sampled": sum(1 for wallet in wallets if wallet in wallet_action_counts),
            "backfill_window": row.get("backfill_window") if isinstance(row.get("backfill_window"), dict) else {},
            "observed_actions": row.get("observed_actions") if isinstance(row.get("observed_actions"), dict) else {},
            "sample_wallets": wallets[:8],
        })
    targets.sort(key=lambda item: (safe_int(item.get("evidence_rows")), safe_int(item.get("wallets_affected"))), reverse=True)
    return targets[: max(0, int(limit))]


def timeline_step(row: dict[str, Any]) -> str:
    unknown_outcomes = safe_int(row.get("unknown_outcome_rows"))
    known_outcomes = safe_int(row.get("known_outcome_rows"))
    if unknown_outcomes > 0 and known_outcomes == 0:
        return "RECONSTRUCT_MARKET_CONTEXT_AND_OUTCOME_WINDOWS"
    if unknown_outcomes > 0:
        return "RECONSTRUCT_MISSING_OUTCOME_WINDOWS"
    return "RECONSTRUCT_DECISION_TIME_MARKET_CONTEXT"


def next_required_actions(blockers: list[str]) -> list[str]:
    actions: list[str] = []
    if "decision_time_market_context_requires_reconstruction" in blockers:
        actions.append("Reconstruct decision-time price, liquidity, and market-cap context from local on-chain evidence where possible.")
    if "outcome_labels_require_replay_safe_timelines" in blockers or "known_outcome_coverage_still_low" in blockers:
        actions.append("Build replay-safe later outcome windows for blocked wallet-token interactions without using future data in decision context.")
    if "historical_supply_still_missing" in blockers:
        actions.append("Recover archival mint supply at or before the decision timestamp before treating market cap as score-ready.")
    if "historical_liquidity_still_incomplete" in blockers:
        actions.append("Improve pool or bonding-curve reserve reconstruction for rows still missing liquidity.")
    if not actions:
        actions.append("Use score-ready timelines to rebuild wallet evidence scorecards.")
    return actions
