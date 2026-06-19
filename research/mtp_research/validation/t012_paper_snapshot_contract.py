"""T012 pre-migration paper-readiness snapshot contract.

This module is infrastructure only. It never creates buy/sell signals, paper
trades, wallet keys, signing paths, or live execution paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

STAGE = "T012_PRE_MIGRATION_PAPER_READY_INFRA"
GUARDRAILS: dict[str, Any] = {
    "stage": STAGE,
    "paper_infrastructure_ready": False,
    "paper_trading_enabled": False,
    "live_trading_enabled": False,
    "buy_sell_signal_generated": False,
    "trading_rule_generated": False,
    "paper_trade_generated": False,
    "meme_trader_export_generated": False,
    "private_keys_signing_execution_added": False,
    "wallet_private_key_signing_execution_absent": True,
    "migration_full_path_required_for_pre_migration_paper": False,
}


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _safe_ratio(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _hash_ids(values: list[Any] | tuple[Any, ...] | None) -> str:
    encoded = json.dumps(list(values or []), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_id(*parts: Any) -> str:
    encoded = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _flow_value(flow: dict[str, Any] | None, *names: str) -> int:
    flow = flow or {}
    for name in names:
        if name in flow:
            return int(_int(flow.get(name)) or 0)
    return 0


def build_pre_entry_decision_snapshot(
    *,
    run_id: str,
    mint: str,
    token_symbol: str | None = None,
    birth_time: float | None,
    decision_time: float | None,
    decision_slot: int | None,
    birth_verified: bool = True,
    bonding_curve_verified: bool | None = None,
    curve_state_available: bool | None = None,
    market_cap_available: bool | None = None,
    curve_progress_pct: float | None = None,
    market_cap_usd: float | None = None,
    flow_30s: dict[str, Any] | None = None,
    flow_60s: dict[str, Any] | None = None,
    dev_wallet: str | None = None,
    dev_previous_migrations: int | None = None,
    creator_sold_before_entry: bool | None = None,
    snapshot_stale: bool = False,
    max_source_lag_ms: float | None = None,
    source_provenance: dict[str, Any] | None = None,
    input_event_ids: list[Any] | None = None,
) -> dict[str, Any]:
    flow_30s = flow_30s or {}
    flow_60s = flow_60s or {}
    buy_30 = _flow_value(flow_30s, "buy_count", "buy_count_30s_since_birth", "buy_count_after_entry")
    sell_30 = _flow_value(flow_30s, "sell_count", "sell_count_30s_since_birth", "sell_count_after_entry")
    buy_60 = _flow_value(flow_60s, "buy_count", "buy_count_60s", "buy_count_after_entry")
    sell_60 = _flow_value(flow_60s, "sell_count", "sell_count_60s", "sell_count_after_entry")
    age = None
    if birth_time is not None and decision_time is not None:
        age = max(0.0, float(decision_time) - float(birth_time))
    dev_safe = dev_previous_migrations is not None
    creator_safe = creator_sold_before_entry is not None
    decision_safe = bool(not snapshot_stale and birth_verified and dev_safe and creator_safe)
    return {
        **GUARDRAILS,
        "snapshot_id": _snapshot_id(run_id, mint, "pre", decision_time, decision_slot),
        "snapshot_type": "pre_entry_decision_snapshot",
        "run_id": run_id,
        "mint": mint,
        "token_symbol": token_symbol,
        "birth_time": birth_time,
        "token_age_seconds": age,
        "decision_time": decision_time,
        "decision_slot": decision_slot,
        "birth_verified": bool(birth_verified),
        "bonding_curve_verified": bonding_curve_verified,
        "curve_state_available": curve_state_available,
        "market_cap_available": market_cap_available,
        "curve_progress_pct": curve_progress_pct,
        "market_cap_usd": market_cap_usd,
        "event_count_30s_since_birth": _flow_value(flow_30s, "event_count", "event_count_30s_since_birth", "event_count_after_entry"),
        "buy_count_30s_since_birth": buy_30,
        "sell_count_30s_since_birth": sell_30,
        "net_buy_count_30s_since_birth": buy_30 - sell_30,
        "unique_buyers_30s_since_birth": _flow_value(flow_30s, "unique_buyers", "unique_buyers_30s_since_birth", "unique_buyers_after_entry"),
        "unique_sellers_30s_since_birth": _flow_value(flow_30s, "unique_sellers", "unique_sellers_30s_since_birth", "unique_sellers_after_entry"),
        "buy_sell_ratio_30s_since_birth": _safe_ratio(buy_30, sell_30),
        "event_count_60s": _flow_value(flow_60s, "event_count", "event_count_60s", "event_count_after_entry"),
        "buy_count_60s": buy_60,
        "sell_count_60s": sell_60,
        "net_buy_count_60s": buy_60 - sell_60,
        "unique_buyers_60s": _flow_value(flow_60s, "unique_buyers", "unique_buyers_60s", "unique_buyers_after_entry"),
        "unique_sellers_60s": _flow_value(flow_60s, "unique_sellers", "unique_sellers_60s", "unique_sellers_after_entry"),
        "buy_sell_ratio_60s": _safe_ratio(buy_60, sell_60),
        "dev_wallet": dev_wallet,
        "dev_previous_migrations": dev_previous_migrations,
        "dev_previous_migrations_status": "available" if dev_previous_migrations is not None else "unavailable_null",
        "dev_previous_migrations_decision_time_safe": dev_safe,
        "creator_sold_before_entry": creator_sold_before_entry,
        "creator_sold_before_entry_status": "available" if creator_sold_before_entry is not None else "unavailable_null",
        "creator_sold_before_entry_decision_time_safe": creator_safe,
        "snapshot_stale": bool(snapshot_stale),
        "max_source_lag_ms": max_source_lag_ms,
        "decision_time_safe": decision_safe,
        "source_provenance": source_provenance or {},
        "input_event_ids_hash": _hash_ids(input_event_ids),
    }


def build_post_entry_hot_flow_snapshot(
    *,
    run_id: str,
    mint: str,
    paper_candidate_id: str,
    entry_reference_time: float | None,
    snapshot_offset_seconds: int,
    snapshot_time: float | None,
    snapshot_slot: int | None,
    market_cap_at_reference: float | None = None,
    market_cap_now: float | None = None,
    curve_progress_at_reference: float | None = None,
    curve_progress_now: float | None = None,
    buy_count_since_reference: int = 0,
    sell_count_since_reference: int = 0,
    unique_buyers_since_reference: int = 0,
    unique_sellers_since_reference: int = 0,
    largest_buy_quote_since_reference: float | None = None,
    largest_sell_quote_since_reference: float | None = None,
    creator_sold_after_reference: bool | None = None,
    creator_sell_count_after_reference: int | None = None,
    creator_token_outflow_after_reference: float | None = None,
    migration_seen: bool = False,
    near_migration: bool = False,
    sell_pressure_caught_up: bool | None = None,
    flow_stalled: bool | None = None,
    snapshot_stale: bool = False,
    source_provenance: dict[str, Any] | None = None,
    input_event_ids: list[Any] | None = None,
) -> dict[str, Any]:
    cap_change = None
    if market_cap_at_reference not in (None, 0) and market_cap_now is not None:
        cap_change = (float(market_cap_now) - float(market_cap_at_reference)) / float(market_cap_at_reference) * 100.0
    progress_change = None
    if curve_progress_at_reference is not None and curve_progress_now is not None:
        progress_change = float(curve_progress_now) - float(curve_progress_at_reference)
    return {
        **GUARDRAILS,
        "snapshot_id": _snapshot_id(run_id, mint, "post", paper_candidate_id, snapshot_offset_seconds),
        "snapshot_type": "post_entry_hot_flow_snapshot",
        "run_id": run_id,
        "mint": mint,
        "paper_candidate_id": paper_candidate_id,
        "entry_reference_time": entry_reference_time,
        "snapshot_offset_seconds": int(snapshot_offset_seconds),
        "snapshot_time": snapshot_time,
        "snapshot_slot": snapshot_slot,
        "market_cap_at_reference": market_cap_at_reference,
        "market_cap_now": market_cap_now,
        "market_cap_change_pct_from_reference": cap_change,
        "market_cap_drawdown_from_local_high_pct": None,
        "curve_progress_at_reference": curve_progress_at_reference,
        "curve_progress_now": curve_progress_now,
        "curve_progress_change_from_reference": progress_change,
        "buy_count_since_reference": int(buy_count_since_reference or 0),
        "sell_count_since_reference": int(sell_count_since_reference or 0),
        "net_buy_count_since_reference": int(buy_count_since_reference or 0) - int(sell_count_since_reference or 0),
        "unique_buyers_since_reference": int(unique_buyers_since_reference or 0),
        "unique_sellers_since_reference": int(unique_sellers_since_reference or 0),
        "buy_sell_ratio_since_reference": _safe_ratio(int(buy_count_since_reference or 0), int(sell_count_since_reference or 0)),
        "largest_buy_quote_since_reference": largest_buy_quote_since_reference,
        "largest_sell_quote_since_reference": largest_sell_quote_since_reference,
        "creator_sold_after_reference": creator_sold_after_reference,
        "creator_sell_count_after_reference": creator_sell_count_after_reference,
        "creator_token_outflow_after_reference": creator_token_outflow_after_reference,
        "migration_seen": bool(migration_seen),
        "near_migration": bool(near_migration),
        "sell_pressure_caught_up": sell_pressure_caught_up,
        "flow_stalled": flow_stalled,
        "snapshot_stale": bool(snapshot_stale),
        "decision_time_safe": not bool(snapshot_stale),
        "source_provenance": source_provenance or {},
        "input_event_ids_hash": _hash_ids(input_event_ids),
    }


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def write_t012_paper_snapshot_artifacts(
    output_root: Path | str,
    *,
    run_id: str,
    pre_entry_rows: list[dict[str, Any]],
    post_entry_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    pre_path = root / "pre_entry_decision_snapshots.jsonl"
    post_path = root / "post_entry_hot_flow_snapshots.jsonl"
    for path in [pre_path, post_path]:
        if not path.exists():
            path.write_text("", encoding="utf-8")
    for row in pre_entry_rows:
        _append_jsonl(pre_path, {**GUARDRAILS, **row})
    for row in post_entry_rows:
        _append_jsonl(post_path, {**GUARDRAILS, **row})
    summary = {
        **GUARDRAILS,
        "run_id": run_id,
        "pre_entry_decision_snapshots_path": str(pre_path),
        "post_entry_hot_flow_snapshots_path": str(post_path),
        "pre_entry_snapshot_count": len(pre_entry_rows),
        "post_entry_hot_flow_snapshot_count": len(post_entry_rows),
        "post_entry_counts_by_offset": {
            str(offset): sum(1 for row in post_entry_rows if int(row.get("snapshot_offset_seconds") or 0) == offset)
            for offset in [1, 5, 10, 30, 60]
        },
    }
    (root / "paper_readiness_summary.md").write_text(
        "# T012 Paper Readiness Snapshot Summary\n\n"
        f"- Stage: `{STAGE}`\n"
        f"- Pre-entry snapshots: `{summary['pre_entry_snapshot_count']}`\n"
        f"- Post-entry hot-flow snapshots: `{summary['post_entry_hot_flow_snapshot_count']}`\n"
        "- Paper trading enabled: `false`\n"
        "- Live trading enabled: `false`\n",
        encoding="utf-8",
    )
    return summary
