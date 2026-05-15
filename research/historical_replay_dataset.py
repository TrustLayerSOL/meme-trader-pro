from __future__ import annotations

import time
from collections import Counter
from copy import deepcopy
from typing import Any


HISTORICAL_REPLAY_EVENT_SCHEMA = "historical_replay_event.v1"
HISTORICAL_REPLAY_DATASET_SCHEMA = "historical_replay_dataset.v1"
DEFAULT_EVALUATION_WINDOWS = (
    ("30s", 30),
    ("2m", 120),
    ("5m", 300),
    ("15m", 900),
)
DEFAULT_LATENCY_SECONDS = 1.0
DEFAULT_LIQUIDITY_FLOOR_USD = 1_000

LEAKAGE_KEY_FRAGMENTS = (
    "future",
    "later",
    "afterward",
    "counterfactual",
    "outcome",
    "pnl_after",
    "max_favorable_excursion",
    "max_adverse_excursion",
)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def decision_context_from_signal(signal_context: dict[str, Any]) -> dict[str, Any]:
    ctx = as_dict(signal_context)
    market = deepcopy(as_dict(ctx.get("market")) or as_dict(ctx.get("market_info")))
    risk = deepcopy(as_dict(ctx.get("risk")))
    if not risk:
        risk = {
            "hard_block": ctx.get("hard_block"),
            "holder_concentration_risk": ctx.get("holder_concentration_risk"),
            "risk_label": ctx.get("risk_label"),
            "risk_score": ctx.get("risk_score"),
        }
    scoring = deepcopy(as_dict(ctx.get("scoring")))
    if not scoring:
        scoring = {
            "score": ctx.get("total_score"),
            "threshold": ctx.get("score_threshold"),
            "reasons_tail": deepcopy(as_list(ctx.get("score_reasons_tail"))),
        }
    return {
        "signal_type": ctx.get("signal_type"),
        "source": ctx.get("source"),
        "entry_timestamp": first_present(ctx.get("entry_timestamp"), ctx.get("captured_at")),
        "triggering_wallets": deepcopy(as_list(ctx.get("triggering_wallets"))),
        "wallet_quality": deepcopy(as_dict(ctx.get("wallet_quality"))),
        "cluster": deepcopy(as_dict(ctx.get("cluster"))),
        "market": market,
        "risk": risk,
        "scoring": scoring,
        "market_regime": deepcopy(as_dict(ctx.get("market_regime"))),
    }


def execution_assumptions_from_record(record: dict[str, Any]) -> dict[str, Any]:
    assumptions = as_dict(record.get("replay_assumptions"))
    signal_execution = as_dict(as_dict(record.get("signal_context")).get("execution_assumptions"))
    signal_context = as_dict(record.get("signal_context"))
    market = as_dict(signal_context.get("market")) or as_dict(signal_context.get("market_info"))
    entry_liquidity = safe_float(first_present(assumptions.get("liquidity_usd"), market.get("liquidity")), None)
    slippage_pct = safe_float(
        first_present(
            assumptions.get("slippage_estimate_pct"),
            signal_execution.get("estimated_slippage_pct"),
        ),
        None,
    )
    if slippage_pct is None:
        slippage_pct = default_slippage_pct(entry_liquidity)
    latency_seconds = safe_float(
        first_present(
            assumptions.get("latency_seconds"),
            signal_execution.get("delay_seconds"),
        ),
        DEFAULT_LATENCY_SECONDS,
    )
    liquidity_floor = safe_float(assumptions.get("liquidity_floor_usd"), DEFAULT_LIQUIDITY_FLOOR_USD)
    fill_status = "unknown_liquidity"
    if entry_liquidity is not None:
        fill_status = "failed_liquidity_floor" if entry_liquidity < (liquidity_floor or 0) else "fillable_with_assumptions"
    return {
        "fill_model": assumptions.get("fill_model", "realistic_fill_required"),
        "perfect_fills_allowed": bool(assumptions.get("perfect_fills_allowed", False)),
        "slippage_estimate_pct": slippage_pct,
        "slippage_bps": round(slippage_pct * 100, 4) if slippage_pct is not None else None,
        "latency_seconds": latency_seconds,
        "liquidity_usd": entry_liquidity,
        "entry_liquidity_usd": entry_liquidity,
        "liquidity_floor_usd": liquidity_floor,
        "fill_status": fill_status,
        "failed_fill_assumption": assumptions.get(
            "failed_fill_assumption",
            "fail replay entry when decision-time liquidity is below the configured floor",
        ),
        "max_position_liquidity_pct": safe_float(assumptions.get("max_position_liquidity_pct"), 1.0),
    }


def default_slippage_pct(entry_liquidity: float | None) -> float:
    if entry_liquidity is None:
        return 5.0
    if entry_liquidity < 2_500:
        return 10.0
    if entry_liquidity < 10_000:
        return 5.0
    if entry_liquidity < 50_000:
        return 2.5
    return 1.5


def evaluation_windows() -> list[dict[str, int | str]]:
    return [{"label": label, "seconds": seconds} for label, seconds in DEFAULT_EVALUATION_WINDOWS]


def build_replay_event(record: dict[str, Any], *, generated_at: float | None = None) -> dict[str, Any]:
    record = as_dict(record)
    signal_context = as_dict(record.get("signal_context"))
    decision = deepcopy(as_dict(record.get("decision")))
    decision_context = decision_context_from_signal(signal_context)
    event = {
        "schema_version": HISTORICAL_REPLAY_EVENT_SCHEMA,
        "event_id": first_present(record.get("decision_id"), signal_context.get("decision_id"), record.get("mint")),
        "generated_at": generated_at if generated_at is not None else time.time(),
        "source_record_type": record.get("record_type"),
        "source": first_present(record.get("source"), signal_context.get("source")),
        "mint": first_present(record.get("mint"), signal_context.get("mint")),
        "wallets": deepcopy(as_list(record.get("wallets"))),
        "signal_timestamp": first_present(
            decision.get("decision_timestamp"),
            signal_context.get("entry_timestamp"),
            signal_context.get("captured_at"),
        ),
        "decision": decision,
        "decision_context": decision_context,
        "evaluation_windows": evaluation_windows(),
        "execution_assumptions": execution_assumptions_from_record(record),
        "later_outcome": deepcopy(as_dict(record.get("later_token_outcome")) or {"status": "unknown"}),
    }
    event["research_safety"] = validate_decision_time_safety(event)
    return event


def validate_decision_time_safety(event: dict[str, Any]) -> dict[str, Any]:
    leakage_paths = []
    walk_for_leakage(as_dict(event).get("decision_context"), "decision_context", leakage_paths)
    return {
        "decision_time_safe": len(leakage_paths) == 0,
        "future_outcome_separated": len(leakage_paths) == 0,
        "leakage_paths": leakage_paths,
        "notes": [
            "decision_context must contain only data available at or before signal time",
            "later_outcome is evaluation-only and must not feed signal reconstruction",
        ],
    }


def walk_for_leakage(value: Any, path: str, leakage_paths: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            key_lower = str(key).lower()
            if any(fragment in key_lower for fragment in LEAKAGE_KEY_FRAGMENTS):
                leakage_paths.append(child_path)
            walk_for_leakage(child, child_path, leakage_paths)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            walk_for_leakage(child, f"{path}[{idx}]", leakage_paths)


def build_historical_replay_dataset(
    records: list[dict[str, Any]],
    *,
    generated_at: float | None = None,
) -> dict[str, Any]:
    generated = generated_at if generated_at is not None else time.time()
    events = [
        build_replay_event(record, generated_at=generated)
        for record in records or []
        if isinstance(record, dict)
    ]
    counts: Counter[str] = Counter(event.get("source_record_type") or "unknown" for event in events)
    counts["events"] = len(events)
    counts["unsafe_events"] = sum(
        1 for event in events if not as_dict(event.get("research_safety")).get("decision_time_safe")
    )
    fill_status_counts: Counter[str] = Counter(
        str(as_dict(event.get("execution_assumptions")).get("fill_status") or "unknown")
        for event in events
    )
    return {
        "schema_version": HISTORICAL_REPLAY_DATASET_SCHEMA,
        "generated_at": generated,
        "mode": "HISTORICAL_REPLAY_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": dict(counts),
        "evaluation_windows": [window["label"] for window in evaluation_windows()],
        "fill_status_counts": dict(fill_status_counts),
        "events": events,
    }
