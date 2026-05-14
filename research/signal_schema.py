from __future__ import annotations

import time
from typing import Any

from core.signal_context import build_signal_context
from research.outcome_labeler import label_later_token_outcome


UNIFIED_SIGNAL_OUTCOME_VERSION = 1


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


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def normalize_decision(decision: dict[str, Any] | None, rejection_reason: str | None = None) -> dict[str, Any]:
    decision = as_dict(decision)
    should_trade = bool(decision.get("should_trade"))
    action = first_present(
        decision.get("action"),
        decision.get("final_action"),
        "accepted_trade" if should_trade else "skip",
    )
    return {
        "action": action,
        "should_trade": should_trade,
        "reason": first_present(rejection_reason, decision.get("reason"), decision.get("action_reason")),
        "paper_lane": decision.get("paper_lane"),
        "decision_timestamp": first_present(decision.get("timestamp"), decision.get("updated_at")),
    }


def normalize_later_outcome(
    outcome: dict[str, Any] | None,
    trade: dict[str, Any] | None = None,
    signal_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome = dict(outcome) if isinstance(outcome, dict) else {}
    trade = as_dict(trade)
    if not outcome:
        outcome = {"status": "unknown"}
    if trade:
        outcome.setdefault("status", trade.get("status"))
        outcome.setdefault("pnl", first_present(trade.get("total_pnl"), trade.get("pnl")))
        outcome.setdefault("pnl_pct", first_present(trade.get("total_pnl_pct"), trade.get("pnl_pct")))
        outcome.setdefault("entry_price", trade.get("entry_price"))
        outcome.setdefault("exit_price", first_present(trade.get("close_price"), trade.get("exit_price"), trade.get("current_price")))
        outcome.setdefault("entry_time", trade.get("entry_time"))
        outcome.setdefault("exit_time", first_present(trade.get("close_time"), trade.get("exit_time")))
        outcome.setdefault("hold_seconds", hold_seconds(trade))
    return label_later_token_outcome(outcome=outcome, trade=trade, signal_context=signal_context)


def hold_seconds(trade: dict[str, Any]) -> float | None:
    entry = safe_float(trade.get("entry_time"), None)
    close = safe_float(first_present(trade.get("close_time"), trade.get("exit_time")), None)
    if entry is None or close is None or close < entry:
        return None
    return round(close - entry, 4)


def replay_assumptions(signal_context: dict[str, Any]) -> dict[str, Any]:
    execution = as_dict(signal_context.get("execution_assumptions"))
    market = as_dict(signal_context.get("market"))
    return {
        "fill_model": "realistic_fill_required",
        "perfect_fills_allowed": False,
        "slippage_estimate_pct": execution.get("estimated_slippage_pct"),
        "latency_seconds": execution.get("delay_seconds"),
        "liquidity_usd": market.get("liquidity"),
        "failed_fill_assumption": "must be modeled before replay can claim edge",
    }


def build_signal_outcome_record(
    *,
    signal_context: dict[str, Any],
    decision: dict[str, Any] | None = None,
    later_token_outcome: dict[str, Any] | None = None,
    trade: dict[str, Any] | None = None,
    rejection_reason: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    signal_context = dict(signal_context) if isinstance(signal_context, dict) else {}
    decision_row = normalize_decision(decision, rejection_reason)
    wallets = signal_context.get("triggering_wallets") if isinstance(signal_context.get("triggering_wallets"), list) else []
    should_trade = bool(decision_row.get("should_trade"))
    record_type = "accepted_trade" if should_trade else "rejected_signal"
    if trade and as_dict(trade).get("status") == "failed":
        record_type = "failed_trade"
    return {
        "schema_version": UNIFIED_SIGNAL_OUTCOME_VERSION,
        "record_type": record_type,
        "generated_at": time.time(),
        "mint": first_present(signal_context.get("mint"), as_dict(trade).get("mint"), as_dict(trade).get("token_mint")),
        "decision_id": first_present(signal_context.get("decision_id"), as_dict(trade).get("decision_id")),
        "source": source or signal_context.get("source"),
        "wallets": wallets,
        "signal_context": signal_context,
        "decision": decision_row,
        "later_token_outcome": normalize_later_outcome(later_token_outcome, trade, signal_context),
        "replay_assumptions": replay_assumptions(signal_context),
        "research_safety": {
            "decision_time_safe": True,
            "future_outcome_separated": True,
            "shared_context_schema": True,
            "live_execution_locked": True,
            "notes": [
                "decision fields must be generated only from data available at or before signal time",
                "later_token_outcome is for evaluation only and must not feed decision reconstruction",
            ],
        },
    }


def build_record_from_rejection(row: dict[str, Any]) -> dict[str, Any]:
    row = as_dict(row)
    ctx = as_dict(row.get("signal context") or row.get("signal_context"))
    return build_signal_outcome_record(
        signal_context=ctx,
        decision={
            "action": "skip",
            "should_trade": False,
            "paper_lane": row.get("lane") or ctx.get("paper_lane"),
            "reason": row.get("rejection reason") or row.get("rejection_reason"),
        },
        later_token_outcome=as_dict(row.get("what would have happened afterward if traded") or row.get("counterfactual")),
        rejection_reason=row.get("rejection reason") or row.get("rejection_reason"),
        source=row.get("source") or ctx.get("source"),
    )


def build_trade_signal_context(trade: dict[str, Any]) -> dict[str, Any]:
    trade = as_dict(trade)
    metadata = as_dict(trade.get("signal_metadata"))
    market_info = as_dict(metadata.get("market_info"))
    if trade.get("entry_liquidity_usd") is not None:
        market_info.setdefault("liquidity", trade.get("entry_liquidity_usd"))
    if trade.get("entry_market_cap") is not None:
        market_info.setdefault("market_cap", trade.get("entry_market_cap"))
    payload = {
        "mint": first_present(trade.get("mint"), trade.get("token_mint")),
        "decision_id": first_present(trade.get("decision_id"), metadata.get("decision_id")),
        "signal_type": first_present(metadata.get("signal_type"), metadata.get("type"), trade.get("signal_type")),
        "paper_lane": first_present(trade.get("paper_lane"), metadata.get("paper_lane")),
        "timestamp": first_present(trade.get("entry_time"), metadata.get("timestamp")),
        "wallets": trade.get("wallets"),
        "wallet_performance": metadata.get("wallet_performance"),
        "market_info": market_info,
        "token_age_seconds": metadata.get("token_age_seconds"),
        "risk_label": metadata.get("risk_label"),
        "risk_score": metadata.get("risk_score"),
        "hard_block": metadata.get("hard_block"),
        "holder_concentration_risk": metadata.get("holder_concentration_risk"),
        "estimated_slippage_pct": first_present(
            metadata.get("estimated_slippage_pct"),
            metadata.get("slippage_estimate_pct"),
            trade.get("entry_slippage_pct"),
        ),
        "execution_delay_seconds": metadata.get("execution_delay_seconds"),
        "score_reasons": first_present(metadata.get("score_reasons"), metadata.get("reasons")),
    }
    return build_signal_context(payload, {"should_trade": True, "paper_lane": payload["paper_lane"]}, source="paper_trade")


def build_record_from_trade(trade: dict[str, Any]) -> dict[str, Any]:
    trade = as_dict(trade)
    ctx = build_trade_signal_context(trade)
    return build_signal_outcome_record(
        signal_context=ctx,
        decision={
            "action": "paper_open_attempt",
            "should_trade": True,
            "paper_lane": first_present(trade.get("paper_lane"), as_dict(trade.get("signal_metadata")).get("paper_lane")),
            "reason": first_present(trade.get("entry_reason"), trade.get("reason")),
            "timestamp": trade.get("entry_time"),
        },
        trade=trade,
        source="paper_trade",
    )
