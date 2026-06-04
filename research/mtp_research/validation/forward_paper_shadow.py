"""Disabled paper/shadow decision scaffold for forward observations.

The scaffold writes rule-design configuration and empty decision logs only.
It does not execute trades, submit orders, send alerts, or calculate PnL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_root
from research.mtp_research.validation.partial_forward_strategy_preview import SAMPLE_LABEL


READINESS = "paper_shadow_scaffold_ready_disabled"


def initialize_forward_paper_shadow(
    *,
    data_root: Path | str | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    observation_root = root / "data" / "forward_observation" / "official_lifecycle_watch_v1"
    config_path = observation_root / "paper_shadow_rule_candidates.json"
    decisions_path = observation_root / "paper_shadow_decisions.jsonl"
    status_path = Path("theses") / "FORWARD_PAPER_SHADOW_STATUS.md"
    if not execute:
        return {
            "execute": False,
            "readiness": READINESS,
            "enabled": False,
            "config_path": str(config_path),
            "decisions_path": str(decisions_path),
            "status_path": str(status_path),
        }
    observation_root.mkdir(parents=True, exist_ok=True)
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
