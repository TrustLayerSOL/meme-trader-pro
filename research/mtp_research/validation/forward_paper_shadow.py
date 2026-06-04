"""Paper/shadow decision scaffold for forward observations.

The default scaffold writes rule-design configuration and empty decision logs only.
An explicit paper-simulation mode can track simulated bankroll/PnL. Neither mode
executes trades, submits orders, sends alerts, or touches wallet logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.validation.partial_forward_strategy_preview import SAMPLE_LABEL


READINESS = "paper_shadow_scaffold_ready_disabled"
PAPER_READINESS = "paper_bankroll_tracker_ready"
DEFAULT_STARTING_BANKROLL_USD = 100.0
DEFAULT_MAX_POSITION_FRACTION = 0.10


def initialize_forward_paper_shadow(
    *,
    data_root: Path | str | None = None,
    execute: bool = False,
    enable_paper_simulation: bool = False,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    max_position_fraction: float = DEFAULT_MAX_POSITION_FRACTION,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    observation_root = root / "data" / "forward_observation" / "official_lifecycle_watch_v1"
    config_path = observation_root / "paper_shadow_rule_candidates.json"
    decisions_path = observation_root / "paper_shadow_decisions.jsonl"
    bankroll_state_path = observation_root / "paper_bankroll_state.json"
    bankroll_ledger_path = observation_root / "paper_bankroll_ledger.jsonl"
    rule_performance_path = observation_root / "paper_rule_performance.json"
    status_path = Path("theses") / "FORWARD_PAPER_SHADOW_STATUS.md"
    if not execute:
        return {
            "execute": False,
            "readiness": PAPER_READINESS if enable_paper_simulation else READINESS,
            "enabled": enable_paper_simulation,
            "config_path": str(config_path),
            "decisions_path": str(decisions_path),
            "bankroll_state_path": str(bankroll_state_path),
            "bankroll_ledger_path": str(bankroll_ledger_path),
            "rule_performance_path": str(rule_performance_path),
            "status_path": str(status_path),
        }
    observation_root.mkdir(parents=True, exist_ok=True)
    if enable_paper_simulation:
        state = build_paper_bankroll_state(
            starting_bankroll_usd=starting_bankroll_usd,
            max_position_fraction=max_position_fraction,
        )
        config = build_paper_bankroll_config(state)
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        decisions_path.touch(exist_ok=True)
        bankroll_ledger_path.touch(exist_ok=True)
        bankroll_state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rule_performance_path.write_text(json.dumps(state["rule_performance"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status_path.write_text(
            _paper_status_markdown(
                config_path=config_path,
                ledger_path=bankroll_ledger_path,
                state_path=bankroll_state_path,
                performance_path=rule_performance_path,
                state=state,
            ),
            encoding="utf-8",
        )
        return {
            "execute": True,
            "readiness": PAPER_READINESS,
            "enabled": True,
            "config_path": str(config_path),
            "decisions_path": str(decisions_path),
            "bankroll_state_path": str(bankroll_state_path),
            "bankroll_ledger_path": str(bankroll_ledger_path),
            "rule_performance_path": str(rule_performance_path),
            "status_path": str(status_path),
            "current_bankroll_usd": state["total_bankroll_usd"],
            "next_max_position_usd": state["next_max_position_usd"],
            "decision_log_rows": sum(1 for _ in decisions_path.open(encoding="utf-8")) if decisions_path.exists() else 0,
        }

    config = build_disabled_rule_config()
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decisions_path.touch(exist_ok=True)
    status_path.write_text(_status_markdown(config_path, decisions_path), encoding="utf-8")
    return {
        "execute": True,
        "readiness": READINESS,
        "enabled": False,
        "config_path": str(config_path),
        "decisions_path": str(decisions_path),
        "status_path": str(status_path),
        "decision_log_rows": sum(1 for _ in decisions_path.open(encoding="utf-8")) if decisions_path.exists() else 0,
    }


def build_paper_bankroll_state(
    *,
    starting_bankroll_usd: float = DEFAULT_STARTING_BANKROLL_USD,
    max_position_fraction: float = DEFAULT_MAX_POSITION_FRACTION,
) -> dict[str, Any]:
    if starting_bankroll_usd <= 0:
        raise ValueError("starting_bankroll_usd must be positive")
    if max_position_fraction <= 0 or max_position_fraction > 1:
        raise ValueError("max_position_fraction must be between 0 and 1")
    total = _round_money(starting_bankroll_usd)
    return {
        "sample_label": SAMPLE_LABEL,
        "enabled": True,
        "mode": "paper_simulation_only",
        "no_live_trade_flag": True,
        "starting_bankroll_usd": total,
        "cash_bankroll_usd": total,
        "total_bankroll_usd": total,
        "max_position_fraction": max_position_fraction,
        "next_max_position_usd": _round_money(total * max_position_fraction),
        "open_positions": {},
        "rule_performance": {},
        "guardrails": [
            "paper_simulation_only",
            "no_wallet_execution",
            "no_transaction_signing",
            "no_order_routing",
            "no_live_trading",
            "no_private_keys",
            "no_alerts",
            "no_real_trade_flag",
        ],
    }


def build_paper_bankroll_config(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_label": SAMPLE_LABEL,
        "enabled": True,
        "mode": "paper_simulation_only",
        "starting_bankroll_usd": state["starting_bankroll_usd"],
        "max_position_fraction": state["max_position_fraction"],
        "position_sizing_rule": "invest_10_percent_of_current_paper_bankroll_per_buy",
        "next_max_position_usd": state["next_max_position_usd"],
        "decision_types": ["paper_buy", "paper_sell", "paper_skip"],
        "ledger_schema": {
            "timestamp": "float|int|str",
            "mint": "str",
            "rule_id": "str",
            "side": "paper_buy|paper_sell|paper_skip",
            "paper_price_usd": "float|null",
            "bankroll_before_usd": "float",
            "allocation_usd": "float",
            "position_units": "float",
            "bankroll_after_usd": "float",
            "realized_pnl_usd": "float",
            "no_live_trade_flag": "bool",
        },
        "candidate_entry_rules": [
            "PBCL_ENTRY_10K_EFFICIENCY_HIGH_BUCKET",
            "PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY",
            "PBCL_ENTRY_15K_SPEED_FLOW_BALANCED",
        ],
        "candidate_exit_rules": [
            "PBCL_EXIT_NO_RECLAIM_10M",
            "PBCL_EXIT_TRAILING_DRAWDOWN_WITH_GRACE",
            "PBCL_EXIT_MAX_AGE_OR_INACTIVE",
        ],
        "guardrails": state["guardrails"],
    }


def apply_paper_decision(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(state))
    side = decision.get("side")
    if side == "paper_buy":
        ledger_row = _apply_paper_buy(updated, decision)
    elif side == "paper_sell":
        ledger_row = _apply_paper_sell(updated, decision)
    elif side == "paper_skip":
        ledger_row = _paper_skip_row(updated, decision)
    else:
        raise ValueError("side must be paper_buy, paper_sell, or paper_skip")
    _refresh_next_position_size(updated)
    return {"state": updated, "ledger_row": ledger_row}


def summarize_rule_performance(ledger_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    performance: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        rule_id = str(row.get("rule_id") or "unknown_rule")
        stats = performance.setdefault(rule_id, _empty_rule_stats())
        side = row.get("side")
        if side == "paper_buy":
            stats["buys"] += 1
        elif side == "paper_sell":
            stats["sells"] += 1
            pnl = float(row.get("realized_pnl_usd") or 0)
            stats["realized_pnl_usd"] = _round_money(stats["realized_pnl_usd"] + pnl)
            if pnl > 0:
                stats["wins"] += 1
            elif pnl < 0:
                stats["losses"] += 1
        else:
            stats["skips"] += 1
    return performance


def build_disabled_rule_config() -> dict[str, Any]:
    return {
        "sample_label": SAMPLE_LABEL,
        "enabled": False,
        "mode": "disabled_shadow_design_only",
        "no_real_trade_flag": True,
        "decision_types": ["would_enter", "would_exit", "would_skip"],
        "future_decision_log_schema": {
            "mint": "str",
            "timestamp": "float",
            "hypothetical_rule_id": "str",
            "decision_type": "would_enter|would_exit|would_skip",
            "observed_fdv_proxy": "float|null",
            "reason": "str",
            "input_features": "dict",
            "no_real_trade_flag": "bool",
        },
        "candidate_entry_rules": [
            "PBCL_ENTRY_10K_EFFICIENCY_HIGH_BUCKET",
            "PBCL_ENTRY_20K_CONFIRMATION_EFFICIENCY",
            "PBCL_ENTRY_15K_SPEED_FLOW_BALANCED",
        ],
        "candidate_exit_rules": [
            "PBCL_EXIT_NO_RECLAIM_10M",
            "PBCL_EXIT_TRAILING_DRAWDOWN_WITH_GRACE",
            "PBCL_EXIT_MAX_AGE_OR_INACTIVE",
        ],
        "guardrails": [
            "disabled_by_default",
            "no_wallet_execution",
            "no_transaction_signing",
            "no_order_routing",
            "no_live_trading",
            "no_enabled_paper_trading",
            "no_profitability_claims",
            "no_pnl",
        ],
    }


def _apply_paper_buy(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    price = _positive_price(decision)
    mint = _required_str(decision, "mint")
    rule_id = _required_str(decision, "rule_id")
    bankroll_before = float(state["total_bankroll_usd"])
    cash_before = float(state["cash_bankroll_usd"])
    allocation = min(_round_money(bankroll_before * float(state["max_position_fraction"])), cash_before)
    units = allocation / price
    state["cash_bankroll_usd"] = _round_money(cash_before - allocation)
    existing = state["open_positions"].get(mint)
    if existing:
        existing["quantity"] = _round_units(existing["quantity"] + units)
        existing["cost_basis_usd"] = _round_money(existing["cost_basis_usd"] + allocation)
    else:
        state["open_positions"][mint] = {
            "mint": mint,
            "entry_rule_id": rule_id,
            "quantity": _round_units(units),
            "cost_basis_usd": allocation,
            "entry_price_usd": price,
            "opened_at": decision.get("timestamp"),
        }
    state["total_bankroll_usd"] = _round_money(state["cash_bankroll_usd"] + _open_position_cost_basis(state))
    stats = state["rule_performance"].setdefault(rule_id, _empty_rule_stats())
    stats["buys"] += 1
    return {
        "timestamp": decision.get("timestamp"),
        "mint": mint,
        "rule_id": rule_id,
        "side": "paper_buy",
        "paper_price_usd": price,
        "bankroll_before_usd": _round_money(bankroll_before),
        "allocation_usd": allocation,
        "position_units": _round_units(units),
        "bankroll_after_usd": state["total_bankroll_usd"],
        "realized_pnl_usd": 0,
        "no_live_trade_flag": True,
    }


def _apply_paper_sell(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    price = _positive_price(decision)
    mint = _required_str(decision, "mint")
    rule_id = _required_str(decision, "rule_id")
    position = state["open_positions"].get(mint)
    if not position:
        raise ValueError(f"cannot paper_sell {mint}: no open paper position")
    bankroll_before = float(state["total_bankroll_usd"])
    quantity = float(position["quantity"])
    proceeds = _round_money(quantity * price)
    cost_basis = float(position["cost_basis_usd"])
    realized_pnl = _round_money(proceeds - cost_basis)
    state["cash_bankroll_usd"] = _round_money(float(state["cash_bankroll_usd"]) + proceeds)
    state["open_positions"].pop(mint, None)
    state["total_bankroll_usd"] = _round_money(state["cash_bankroll_usd"] + _open_position_cost_basis(state))
    entry_rule_id = str(position.get("entry_rule_id") or "unknown_entry_rule")
    entry_stats = state["rule_performance"].setdefault(entry_rule_id, _empty_rule_stats())
    entry_stats["realized_pnl_usd"] = _round_money(entry_stats["realized_pnl_usd"] + realized_pnl)
    exit_stats = state["rule_performance"].setdefault(rule_id, _empty_rule_stats())
    exit_stats["sells"] += 1
    exit_stats["realized_pnl_usd"] = _round_money(exit_stats["realized_pnl_usd"] + realized_pnl)
    if realized_pnl > 0:
        entry_stats["wins"] += 1
        exit_stats["wins"] += 1
    elif realized_pnl < 0:
        entry_stats["losses"] += 1
        exit_stats["losses"] += 1
    return {
        "timestamp": decision.get("timestamp"),
        "mint": mint,
        "rule_id": rule_id,
        "entry_rule_id": entry_rule_id,
        "side": "paper_sell",
        "paper_price_usd": price,
        "bankroll_before_usd": _round_money(bankroll_before),
        "allocation_usd": 0,
        "position_units": _round_units(quantity),
        "bankroll_after_usd": state["total_bankroll_usd"],
        "realized_pnl_usd": realized_pnl,
        "no_live_trade_flag": True,
    }


def _paper_skip_row(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    rule_id = _required_str(decision, "rule_id")
    stats = state["rule_performance"].setdefault(rule_id, _empty_rule_stats())
    stats["skips"] += 1
    return {
        "timestamp": decision.get("timestamp"),
        "mint": decision.get("mint"),
        "rule_id": rule_id,
        "side": "paper_skip",
        "paper_price_usd": decision.get("paper_price_usd"),
        "bankroll_before_usd": state["total_bankroll_usd"],
        "allocation_usd": 0,
        "position_units": 0,
        "bankroll_after_usd": state["total_bankroll_usd"],
        "realized_pnl_usd": 0,
        "no_live_trade_flag": True,
    }


def _empty_rule_stats() -> dict[str, Any]:
    return {
        "buys": 0,
        "sells": 0,
        "skips": 0,
        "wins": 0,
        "losses": 0,
        "realized_pnl_usd": 0,
    }


def _refresh_next_position_size(state: dict[str, Any]) -> None:
    state["next_max_position_usd"] = _round_money(float(state["total_bankroll_usd"]) * float(state["max_position_fraction"]))


def _open_position_cost_basis(state: dict[str, Any]) -> float:
    return _round_money(sum(float(position["cost_basis_usd"]) for position in state["open_positions"].values()))


def _positive_price(decision: dict[str, Any]) -> float:
    price = float(decision.get("paper_price_usd") or 0)
    if price <= 0:
        raise ValueError("paper_price_usd must be positive")
    return price


def _required_str(decision: dict[str, Any], key: str) -> str:
    value = decision.get(key)
    if not value:
        raise ValueError(f"{key} is required")
    return str(value)


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _round_units(value: float) -> float:
    return round(float(value), 12)


def _status_markdown(config_path: Path, decisions_path: Path) -> str:
    return "\n".join(
        [
            "# Forward Paper/Shadow Status",
            "",
            f"Readiness: `{READINESS}`",
            "",
            "The scaffold is disabled by default. It only stores candidate rule designs and a future decision-log schema.",
            "",
            f"Config: `{config_path}`",
            f"Decision log: `{decisions_path}`",
            "",
            "No live trades, paper trades, wallet actions, orders, swaps, alerts, PnL, or profitability claims are enabled.",
        ]
    ) + "\n"


def _paper_status_markdown(
    *,
    config_path: Path,
    ledger_path: Path,
    state_path: Path,
    performance_path: Path,
    state: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Forward Paper/Shadow Status",
            "",
            f"Readiness: `{PAPER_READINESS}`",
            "",
            "Paper simulation is explicitly enabled for research tracking only.",
            "",
            f"Starting paper bankroll: `${state['starting_bankroll_usd']}`",
            f"Current paper bankroll: `${state['total_bankroll_usd']}`",
            f"Max paper allocation per buy: `{state['max_position_fraction']:.2%}` of current bankroll",
            f"Next max paper position: `${state['next_max_position_usd']}`",
            "",
            f"Config: `{config_path}`",
            f"State: `{state_path}`",
            f"Ledger: `{ledger_path}`",
            f"Rule performance: `{performance_path}`",
            "",
            "This is paper-only accounting. No live trades, wallet actions, orders, swaps, alerts, private keys, or execution logic are enabled.",
        ]
    ) + "\n"
