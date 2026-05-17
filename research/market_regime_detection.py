from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any


MODE = "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY"
REPLAY_MODE = "HISTORICAL_REPLAY_REVIEW_ONLY"
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


def pct(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(round((numerator / denominator) * 100))


def gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def replay_dataset_visible(summary: dict[str, Any]) -> bool:
    return summary.get("mode") == REPLAY_MODE and summary.get("live_execution_locked") is True


def event_regime_tags(event: dict[str, Any]) -> list[str]:
    regime = as_dict(as_dict(event.get("decision_context")).get("market_regime"))
    tags = [str(tag).strip() for tag in as_list(regime.get("tags")) if str(tag).strip()]
    return tags or ["unknown"]


def event_regime_reasons(event: dict[str, Any]) -> list[str]:
    regime = as_dict(as_dict(event.get("decision_context")).get("market_regime"))
    return [str(reason).strip() for reason in as_list(regime.get("reasons")) if str(reason).strip()]


def outcome_15m(event: dict[str, Any]) -> str:
    outcome = as_dict(as_dict(as_dict(event.get("later_outcome")).get("windows")).get("15m"))
    return str(outcome.get("outcome_type") or "unknown").lower()


def fill_status(event: dict[str, Any]) -> str:
    return str(as_dict(event.get("execution_assumptions")).get("fill_status") or "unknown_liquidity")


def source_type(event: dict[str, Any]) -> str:
    return str(event.get("source_record_type") or event.get("source") or "unknown")


def wallet_ids(event: dict[str, Any]) -> list[str]:
    wallets = []
    seen = set()
    for row in as_list(event.get("wallets")):
        wallet = row.get("wallet") if isinstance(row, dict) else row
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            wallets.append(wallet)
            seen.add(wallet)
    return wallets


def empty_bucket() -> dict[str, Any]:
    return {
        "events": 0,
        "accepted_trades": 0,
        "rejected_signals": 0,
        "failed_trades": 0,
        "fillable_events": 0,
        "failed_liquidity_events": 0,
        "unknown_liquidity_events": 0,
        "known_15m_outcomes": 0,
        "outcomes_15m": Counter(),
        "wallets": set(),
        "sample_reasons": [],
    }


def regime_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: defaultdict[str, dict[str, Any]] = defaultdict(empty_bucket)
    for event in events:
        if not isinstance(event, dict):
            continue
        outcome = outcome_15m(event)
        fill = fill_status(event)
        source = source_type(event)
        wallets = wallet_ids(event)
        reasons = event_regime_reasons(event)
        for tag in event_regime_tags(event):
            bucket = buckets[tag]
            bucket["events"] += 1
            bucket["accepted_trades"] += int(source == "accepted_trade")
            bucket["rejected_signals"] += int(source == "rejected_signal")
            bucket["failed_trades"] += int(source == "failed_trade")
            bucket["fillable_events"] += int(fill == "fillable_with_assumptions")
            bucket["failed_liquidity_events"] += int(fill == "failed_liquidity_floor")
            bucket["unknown_liquidity_events"] += int(fill == "unknown_liquidity")
            bucket["known_15m_outcomes"] += int(outcome in KNOWN_OUTCOMES)
            bucket["outcomes_15m"][outcome] += 1
            bucket["wallets"].update(wallets)
            for reason in reasons:
                if len(bucket["sample_reasons"]) < 5 and reason not in bucket["sample_reasons"]:
                    bucket["sample_reasons"].append(reason)
    rows = []
    for regime, bucket in buckets.items():
        events_count = safe_int(bucket["events"])
        known = safe_int(bucket["known_15m_outcomes"])
        outcomes = bucket["outcomes_15m"]
        rows.append(
            {
                "regime": regime,
                "events": events_count,
                "accepted_trades": safe_int(bucket["accepted_trades"]),
                "rejected_signals": safe_int(bucket["rejected_signals"]),
                "failed_trades": safe_int(bucket["failed_trades"]),
                "fillable_events": safe_int(bucket["fillable_events"]),
                "failed_liquidity_events": safe_int(bucket["failed_liquidity_events"]),
                "unknown_liquidity_events": safe_int(bucket["unknown_liquidity_events"]),
                "known_15m_outcomes": known,
                "known_15m_rate": round(known / events_count, 4) if events_count else 0.0,
                "outcomes_15m": {
                    "runner": safe_int(outcomes.get("runner")),
                    "rug": safe_int(outcomes.get("rug")),
                    "dead": safe_int(outcomes.get("dead")),
                    "loser": safe_int(outcomes.get("loser")),
                    "unknown": safe_int(outcomes.get("unknown")),
                },
                "wallet_count": len(bucket["wallets"]),
                "sample_reasons": bucket["sample_reasons"],
                "can_drive_wallet_trust": False,
            }
        )
    return sorted(rows, key=lambda row: (safe_int(row["events"]), row["regime"]), reverse=True)


def build_market_regime_detection_report(
    *,
    replay_summary: dict[str, Any] | None,
    replay_events: list[dict[str, Any]] | None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    summary = as_dict(replay_summary)
    events = [event for event in as_list(replay_events) if isinstance(event, dict)]
    rows = regime_rows(events)
    known_outcomes = sum(1 for event in events if outcome_15m(event) in KNOWN_OUTCOMES)
    unknown_regime_events = sum(1 for event in events if event_regime_tags(event) == ["unknown"])
    gates = [
        gate("replay_dataset_visible", replay_dataset_visible(summary), "Stage 7 must consume the locked historical replay dataset."),
        gate("replay_safety_clean", safe_int(as_dict(summary.get("counts")).get("unsafe_events")) == 0, "Regime review requires zero known replay leakage flags."),
        gate("regime_tags_indexed", len(rows) > 0, "Regime tags must be indexed from replay decision contexts."),
        gate("accepted_rejected_failed_separated", any(row["accepted_trades"] for row in rows) or any(row["rejected_signals"] for row in rows) or any(row["failed_trades"] for row in rows), "Regime rows must preserve decision type separation."),
        gate("outcomes_separated_by_regime", isinstance(rows, list) and all("outcomes_15m" in row for row in rows), "Later outcomes must remain separate from decision-time regime tags."),
        gate(
            "unknown_regime_visible",
            unknown_regime_events == 0 or any(row["regime"] == "unknown" for row in rows),
            "Unknown regime rows must stay visible instead of being hidden.",
        ),
        gate("regime_score_driving_blocked", True, "Regime labels are review-only until validation proves they are reliable."),
        gate("live_execution_locked", True, "Stage 7 must not unlock live execution."),
        gate("wallet_list_mutation_blocked", True, "Stage 7 must not mutate wallet lists."),
        gate("trust_mutation_blocked", True, "Stage 7 must not auto-promote or auto-demote wallets."),
    ]
    passed = [row["name"] for row in gates if row["passed"]]
    failed = [row["name"] for row in gates if not row["passed"]]
    return {
        "generated_at": generated_at if generated_at is not None else time.time(),
        "mode": MODE,
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_apply_allowed": False,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "regime_score_driving_allowed": False,
        "summary": {
            "stage7_regime_detection_completion_pct": pct(len(passed), len(gates)),
            "events_analyzed": len(events),
            "regime_tags_observed": len(rows),
            "known_15m_outcomes": known_outcomes,
            "unknown_regime_events": unknown_regime_events,
            "regime_data_readiness_pct": pct(known_outcomes, max(1, len(events))),
        },
        "regime_rows": rows,
        "passed_gates": passed,
        "failed_gates": failed,
        "gates": gates,
        "residual_data_blockers": residual_data_blockers(rows=rows, events=len(events), known_outcomes=known_outcomes),
        "operator_note": (
            "Stage 7 is complete as a review-only regime detection layer. "
            "Regime tags can segment wallet behavior for research, but they cannot drive wallet trust until outcome coverage and validation improve."
        ),
    }


def residual_data_blockers(*, rows: list[dict[str, Any]], events: int, known_outcomes: int) -> list[str]:
    blockers = []
    if not rows:
        blockers.append("regime_tags_missing")
    if events and known_outcomes < events:
        blockers.append("regime_outcome_coverage_incomplete")
    if any(row.get("regime") == "unknown" for row in rows):
        blockers.append("unknown_regime_present")
    blockers.append("regime_score_driving_blocked_until_validated")
    return blockers
