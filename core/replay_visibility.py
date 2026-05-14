from __future__ import annotations

import time
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_replay_record(row: dict[str, Any]) -> dict[str, Any]:
    ctx = as_dict(row.get("signal context") or row.get("signal_context"))
    cluster = as_dict(ctx.get("cluster"))
    execution = as_dict(ctx.get("execution_assumptions"))
    outcome = as_dict(row.get("what would have happened afterward if traded") or row.get("counterfactual"))
    return {
        "decision_id": row.get("decision_id") or ctx.get("decision_id"),
        "mint": row.get("mint") or ctx.get("mint"),
        "source": row.get("source") or ctx.get("source"),
        "lane": row.get("lane") or ctx.get("paper_lane"),
        "rejection_reason": row.get("rejection reason") or row.get("rejection_reason"),
        "trigger": {
            "wallets": ctx.get("triggering_wallets") if isinstance(ctx.get("triggering_wallets"), list) else [],
            "wallet_count": cluster.get("wallet_count"),
            "cluster_duration_seconds": cluster.get("duration_seconds"),
            "wallet_quality": ctx.get("wallet_quality"),
        },
        "market": as_dict(ctx.get("market")),
        "risk": as_dict(ctx.get("risk")),
        "market_regime": as_dict(ctx.get("market_regime")),
        "execution": {
            "estimated_slippage_pct": execution.get("estimated_slippage_pct"),
            "delay_seconds": execution.get("delay_seconds"),
            "buy_quote_pass": execution.get("buy_quote_pass"),
            "sell_quote_pass": execution.get("sell_quote_pass"),
            "fill_model": "review only; no perfect fills assumed",
        },
        "outcome": outcome,
        "replay_notes": [
            "no perfect fills; replay must use only pre-signal context plus later observed outcome labels",
            "counterfactual outcome is unknown until causal replay slice is available",
        ],
    }


def build_replay_visibility_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    records = [build_replay_record(row) for row in rows if isinstance(row, dict)]
    return {
        "generated_at": time.time(),
        "mode": "REPLAY_VISIBILITY_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {"records": len(records)},
        "records": records,
    }

