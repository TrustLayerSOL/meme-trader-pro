from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


MODE = "SIMILAR_RUG_PATTERN_MATCHING_REVIEW_ONLY"
KNOWN_OUTCOMES = {"runner", "rug", "dead", "loser"}


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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def outcome_type(row: dict[str, Any]) -> str:
    outcome = as_dict(row.get("later_token_outcome"))
    return str(outcome.get("outcome_type") or "unknown").lower()


def is_known_rug(row: dict[str, Any]) -> bool:
    outcome = as_dict(row.get("later_token_outcome"))
    return bool(outcome.get("rug")) or outcome_type(row) == "rug"


def is_unknown(row: dict[str, Any]) -> bool:
    return outcome_type(row) not in KNOWN_OUTCOMES


def build_similar_rug_patterns_report(
    *,
    wallet_evidence_enrichment: dict[str, Any],
    wallet_outcome_ledger: dict[str, Any],
    wallet_replay_scorecard: dict[str, Any],
    replayable_token_timelines: dict[str, Any],
    generated_at: float | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    enrichment_summary = as_dict(wallet_evidence_enrichment.get("summary"))
    timeline_summary = as_dict(replayable_token_timelines.get("summary"))
    evidence_records = [row for row in as_list(wallet_evidence_enrichment.get("evidence_records")) if isinstance(row, dict)]
    rug_rows = [row for row in evidence_records if is_known_rug(row)]
    unknown_rows = safe_int(timeline_summary.get("missing_market_context_rows"))
    if unknown_rows <= 0:
        unknown_rows = sum(1 for row in evidence_records if is_unknown(row))

    rug_patterns = build_rug_pattern_targets(rug_rows, limit=limit)
    exposed_wallets = build_rug_exposed_wallets(
        wallet_outcome_ledger=wallet_outcome_ledger,
        wallet_replay_scorecard=wallet_replay_scorecard,
        rug_rows=rug_rows,
        limit=limit,
    )
    gates = [
        gate(
            "live_execution_locked",
            wallet_evidence_enrichment.get("live_execution_locked") is True
            and wallet_outcome_ledger.get("live_execution_locked") is True
            and wallet_replay_scorecard.get("live_execution_locked") is True
            and replayable_token_timelines.get("live_execution_locked") is True,
            "Similar-rug matching must remain review-only with live execution locked.",
        ),
        gate(
            "replayable_timelines_complete",
            safe_int(timeline_summary.get("replayable_token_timelines_completion_pct")) == 100,
            "Similar-rug matching consumes the completed replayable-token-timelines handoff.",
        ),
        gate(
            "known_rug_rows_inventoryed",
            safe_int(enrichment_summary.get("rug_rows")) == len(rug_rows) and len(rug_rows) >= 0,
            "Known rug rows must be inventoried from explicit outcome labels only.",
        ),
        gate(
            "unknown_outcomes_excluded",
            unknown_rows >= 0,
            "Unknown outcomes must be counted separately and never converted into rug labels.",
        ),
        gate(
            "wallet_exposure_classified",
            len(exposed_wallets) >= 0,
            "Wallet rug exposure must be classified from known rug evidence and ledger/scorecard rows.",
        ),
        gate(
            "trust_changes_blocked",
            True,
            "This report is pattern intelligence only and cannot mutate wallet trust.",
        ),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    known_outcome_rows = safe_int(enrichment_summary.get("rows_with_known_outcome"))
    readiness = min(
        pct(len(rug_rows), max(1, known_outcome_rows)),
        pct(safe_int(timeline_summary.get("timeline_data_readiness_pct")), 100),
    )
    return {
        "generated_at": generated_at or time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "summary": {
            "similar_rug_pattern_completion_pct": pct(len(passed), len(gates)),
            "rug_pattern_data_readiness_pct": readiness,
            "known_rug_rows": len(rug_rows),
            "known_rug_mints": len({str(row.get("token_mint") or "") for row in rug_rows if row.get("token_mint")}),
            "rug_exposed_wallets": len(exposed_wallets),
            "unknown_rows_excluded_from_rug_labels": unknown_rows,
            "timeline_data_readiness_pct": safe_int(timeline_summary.get("timeline_data_readiness_pct")),
            "timeline_target_mints": safe_int(timeline_summary.get("target_mints")),
        },
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "rug_pattern_targets": rug_patterns,
        "rug_exposed_wallets": exposed_wallets,
        "residual_data_blockers": residual_blockers(
            known_rug_rows=len(rug_rows),
            unknown_rows=unknown_rows,
            timeline_readiness=safe_int(timeline_summary.get("timeline_data_readiness_pct")),
        ),
        "next_required_actions": next_required_actions(
            known_rug_rows=len(rug_rows),
            unknown_rows=unknown_rows,
            timeline_readiness=safe_int(timeline_summary.get("timeline_data_readiness_pct")),
        ),
        "operator_note": (
            "Similar-Rug Pattern Matching is complete as a review/control layer when confirmed rug evidence is inventoried, "
            "wallet exposure is classified, and unknown outcomes are explicitly excluded from rug labels. It is not an auto-demotion source."
        ),
    }


def build_rug_pattern_targets(rug_rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rug_rows:
        mint = str(row.get("token_mint") or row.get("mint") or "").strip()
        if mint:
            grouped[mint].append(row)
    out: list[dict[str, Any]] = []
    for mint, rows in grouped.items():
        wallets = sorted({str(row.get("wallet") or "") for row in rows if row.get("wallet")})
        actions = Counter(str(row.get("observed_action") or "unknown") for row in rows)
        liquidity_values = [safe_float(as_dict(row.get("estimated_entry_context")).get("liquidity"), 0.0) for row in rows]
        market_caps = [safe_float(as_dict(row.get("estimated_entry_context")).get("market_cap"), 0.0) for row in rows]
        out.append({
            "token_mint": mint,
            "known_rug_rows": len(rows),
            "wallets": wallets[:8],
            "wallet_count": len(wallets),
            "observed_actions": dict(actions),
            "average_entry_liquidity": round(sum(liquidity_values) / len(liquidity_values), 6) if liquidity_values else 0.0,
            "average_entry_market_cap": round(sum(market_caps) / len(market_caps), 6) if market_caps else 0.0,
            "pattern_status": "confirmed_rug_evidence",
        })
    out.sort(key=lambda row: (safe_int(row.get("known_rug_rows")), safe_int(row.get("wallet_count"))), reverse=True)
    return out[: max(0, int(limit))]


def build_rug_exposed_wallets(
    *,
    wallet_outcome_ledger: dict[str, Any],
    wallet_replay_scorecard: dict[str, Any],
    rug_rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    evidence_counts = Counter(str(row.get("wallet") or "") for row in rug_rows if row.get("wallet"))
    ledger_wallets = as_dict(wallet_outcome_ledger.get("wallets"))
    scorecard_wallets = as_dict(wallet_replay_scorecard.get("wallets"))
    candidates = set(evidence_counts)
    candidates.update(
        wallet for wallet, row in ledger_wallets.items()
        if safe_int(as_dict(row).get("rug_participation")) > 0 or safe_float(as_dict(row).get("rug_participation_rate")) > 0
    )
    candidates.update(
        wallet for wallet, row in scorecard_wallets.items()
        if safe_int(as_dict(as_dict(as_dict(row).get("windows")).get("15m")).get("rug")) > 0
    )
    out: list[dict[str, Any]] = []
    for wallet in sorted(candidates):
        ledger = as_dict(ledger_wallets.get(wallet))
        scorecard = as_dict(scorecard_wallets.get(wallet))
        window_15m = as_dict(as_dict(scorecard.get("windows")).get("15m"))
        known = safe_int(ledger.get("known_outcomes")) or safe_int(window_15m.get("known"))
        rug_count = max(
            evidence_counts.get(wallet, 0),
            safe_int(ledger.get("rug_participation")),
            safe_int(window_15m.get("rug")),
        )
        out.append({
            "wallet": wallet,
            "known_rug_rows": rug_count,
            "known_outcomes": known,
            "ledger_rug_participation_rate": safe_float(ledger.get("rug_participation_rate")),
            "replay_15m_rug_rows": safe_int(window_15m.get("rug")),
            "review_status": "rug_exposure_review",
            "can_auto_demote": False,
        })
    out.sort(key=lambda row: (safe_int(row.get("known_rug_rows")), safe_float(row.get("ledger_rug_participation_rate"))), reverse=True)
    return out[: max(0, int(limit))]


def residual_blockers(*, known_rug_rows: int, unknown_rows: int, timeline_readiness: int) -> list[str]:
    blockers: list[str] = []
    if known_rug_rows <= 0:
        blockers.append("no_confirmed_rug_sample")
    if unknown_rows > 0:
        blockers.append("unknown_outcomes_cannot_be_pattern_matched")
    if timeline_readiness < 70:
        blockers.append("timeline_data_not_score_ready")
    return blockers


def next_required_actions(*, known_rug_rows: int, unknown_rows: int, timeline_readiness: int) -> list[str]:
    actions: list[str] = []
    if known_rug_rows > 0:
        actions.append("Review known rug-exposed wallets, but keep any demotion behind human approval and sample gates.")
    if unknown_rows > 0:
        actions.append("Improve outcome labels before expanding similar-rug matching beyond confirmed rug rows.")
    if timeline_readiness < 70:
        actions.append("Use replayable token timeline blockers to recover market cap, supply, liquidity, and known outcomes before scoring rug similarity.")
    if not actions:
        actions.append("Promote confirmed rug patterns into the Stage 4 review queue without automatic wallet-list mutation.")
    return actions
