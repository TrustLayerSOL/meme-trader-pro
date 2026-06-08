"""Locked paper-shadow V2 buy/sell rule contract.

This module writes audit-ready configuration artifacts only. It does not create
wallet, signing, order-routing, swap, or live trading behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.mtp_research.data_paths import data_lake_root


RULE_V2_VARIANT_1_ID = "BUY_V2_Q75_EFFICIENCY_RISK"
RULE_V2_VARIANT_2_ID = "BUY_V2_Q75_EFFICIENCY_REPEAT_BUYER"
SHARED_RULE_V2_EXIT_ID = "EXIT_V2_PROFIT_LOCK_WITH_RUNNER"

RULE_V2_SHADOW_RELATIVE_ROOT = Path("data") / "forward_observation" / "rule_v2_shadow"

RULE_V2_SHADOW_OUTPUT_FILES = {
    "positions": "rule_v2_shadow_positions.jsonl",
    "buy_events": "rule_v2_shadow_buy_events.jsonl",
    "sell_events": "rule_v2_shadow_sell_events.jsonl",
    "full_paths": "rule_v2_shadow_full_paths.jsonl",
    "post_sell_analysis": "rule_v2_shadow_post_sell_analysis.jsonl",
    "variant_summary": "rule_v2_shadow_variant_summary.json",
    "daily_status": "rule_v2_shadow_daily_status.md",
    "locked_config": "rule_v2_shadow_locked_config.json",
    "lock_manifest": "rule_v2_shadow_lock_manifest.json",
}


def build_rule_v2_shadow_config() -> dict[str, Any]:
    """Return the locked V2 paper-shadow rule contract."""
    return {
        "config_id": "rule_v2_shadow_locked_20260607",
        "mode": "paper_shadow_only",
        "description": (
            "Two explicit V2 paper-shadow buy variants with one shared V2 profit-lock exit. "
            "This config is for simulated paper accounting and forward evidence capture only."
        ),
        "no_real_trade": True,
        "wallet_execution_enabled": False,
        "transaction_signing_enabled": False,
        "order_routing_enabled": False,
        "live_trading_enabled": False,
        "current_rule_d_overwritten": False,
        "starting_paper_cash_usd": 300.0,
        "position_fraction": 0.05,
        "paper_units_formula": "allocation_usd / paper_buy_fdv",
        "entry_gate": {
            "confirmed_clean_10k_required": True,
            "confirmed_clean_20k_required": True,
            "valid_fdv_units_required": True,
            "usd_fdv_required_when_units_usd": True,
            "silently_pass_sol_quote_or_raw_units": False,
            "buy_fdv_band_usd": {"min": 20_000.0, "max": 26_000.0},
            "above_band_handling": "reject_or_missed_chase_research_only",
            "fast_entry_burst_validation_path_allowed": True,
            "duplicate_open_bought_closed_reject": True,
            "fdv_anomaly_reject": True,
            "same_timestamp_major_jump_handling": "tag_actionability_or_missed_entry_research_only",
            "single_row_spike_reject_unless_softened": True,
            "valid_milestone_ordering_required": True,
            "supported_token_programs": {
                "spl": "pass",
                "pumpfun_token_2022": {
                    "status": "conditional_pass",
                    "requirements": [
                        "pumpfun_create_seen",
                        "bonding_curve_pda_verified",
                        "bonding_curve_decode_verified",
                        "fdv_units_present",
                        "fdv_calculation_status_verified",
                    ],
                },
                "unknown_or_unsupported": "hard_reject",
            },
            "holder_gate": {
                "missing_holder_depth": "label_only_variant_condition",
                "holder_count_lte_1": "hard_reject",
                "holder_count_2_to_4": "allow_with_low_holder_depth_label",
                "holder_count_gte_5": "pass",
            },
            "hard_reject_risk_labels": [],
            "label_only_risk_labels": [
                "dev_pump_suspect",
                "fake_volume_suspect",
                "missing_holder_depth",
                "mayhem_mode",
                "mayhem_assisted_momentum",
                "low_holder_depth_2_to_4",
            ],
        },
        "buy_variants": [
            {
                "variant_id": RULE_V2_VARIANT_1_ID,
                "name": "20k Q75 efficiency with risk filter",
                "role": "broader_main_variant",
                "base_entry_gate_required": True,
                "conditions": {
                    "creator_extraction_proxy_before_20k_max": 0,
                    "top_10_holder_share_proxy_max": 1,
                    "synthetic_activity_proxy_max": 1,
                    "fdv_efficiency_score_min": 10.65,
                },
                "fdv_efficiency_score_definition": (
                    "mean of fdv_per_event_at_20k, fdv_per_buy_at_20k, "
                    "and fdv_per_active_wallet_at_20k, divided by 1000"
                ),
                "historical_support": {
                    "support_count": 136,
                    "reached_50k_pct": 100.0,
                    "reached_100k_pct": 99.3,
                    "reached_500k_pct": 52.2,
                    "stalls_before_50k": 0,
                },
            },
            {
                "variant_id": RULE_V2_VARIANT_2_ID,
                "name": "20k Q75 efficiency with repeated buyer",
                "role": "stricter_high_conviction_variant",
                "inherits_variant": RULE_V2_VARIANT_1_ID,
                "base_entry_gate_required": True,
                "conditions": {
                    "creator_extraction_proxy_before_20k_max": 0,
                    "top_10_holder_share_proxy_max": 1,
                    "synthetic_activity_proxy_max": 1,
                    "fdv_efficiency_score_min": 10.65,
                },
                "additional_conditions": {"repeated_buyer_count_min": 1},
                "historical_support": {
                    "support_count": 38,
                    "reached_50k_pct": 100.0,
                    "reached_100k_pct": 100.0,
                    "reached_500k_pct": 55.3,
                    "stalls_before_50k": 0,
                },
            },
        ],
        "multi_variant_handling": {
            "token_can_pass_both_variants": True,
            "record_all_passing_variant_ids_on_lifecycle_record": True,
        },
        "shared_exit_rule": {
            "rule_id": SHARED_RULE_V2_EXIT_ID,
            "position_starts_open_pct": 100.0,
            "scale_outs": [
                {"sell_leg": "first_confirmed_50k", "confirmed_fdv_usd": 50_000.0, "percent_sold": 40.0},
                {"sell_leg": "first_confirmed_100k", "confirmed_fdv_usd": 100_000.0, "percent_sold": 30.0},
            ],
            "runner": {
                "remaining_percent_after_scale_outs": 30.0,
                "trail_after_200k_pct": 35.0,
                "trail_after_500k_pct": 25.0,
            },
            "stagnation_exit": {
                "local_high_min_gain_pct_above_buy": 50.0,
                "no_new_high_seconds": 120.0,
                "required_recent_fdv_slope": "flat_or_negative",
                "action": "sell_remaining_open_amount",
            },
            "no_reclaim_exit": {
                "drawdown_from_local_high_pct": 30.0,
                "reclaim_window_seconds": 600.0,
                "action": "sell_remaining_open_amount",
            },
            "pre_first_50k_exit": {
                "drawdown_no_reclaim": "30pct_drawdown_no_reclaim_after_10m_sell_all",
                "runup_stagnation": "50pct_runup_no_new_high_120s_flat_or_negative_slope_sell_all",
            },
        },
        "tracking": {
            "continue_full_path_after_sell": True,
            "minimum_fields": [
                "mint",
                "launch_id",
                "token_name",
                "token_symbol",
                "buy_variant_ids",
                "buy_timestamp",
                "buy_fdv",
                "entry_status",
                "fdv_efficiency_score",
                "fdv_per_event_at_20k",
                "fdv_per_buy_at_20k",
                "fdv_per_active_wallet_at_20k",
                "holder_count",
                "risk_labels",
                "creator_extraction_proxy_before_20k",
                "repeated_buyer_count",
                "top_10_holder_share_proxy",
                "synthetic_activity_proxy",
                "allocation_usd",
                "paper_units",
                "observed_fdv_path",
                "local_high_fdv",
                "milestones",
                "sell_events",
                "runner_open",
                "final_fdv_after_sell",
                "max_fdv_after_sell",
                "max_fdv_after_each_sell",
                "time_to_later_max_seconds",
                "missed_upside",
                "missed_upside_multiple",
                "hit_200k_after_sell",
                "hit_500k_after_sell",
                "hit_1m_after_sell",
                "sell_protected_from_collapse",
                "hindsight_best_exit",
            ],
            "post_sell_analysis_fields": [
                "max_fdv_after_each_sell",
                "time_to_later_max_seconds",
                "missed_upside_multiple",
                "hit_200k_after_sell",
                "hit_500k_after_sell",
                "hit_1m_after_sell",
                "sell_protected_from_collapse",
            ],
            "milestones_usd": [30_000, 40_000, 50_000, 75_000, 100_000, 200_000, 500_000, 1_000_000],
        },
        "output_files": RULE_V2_SHADOW_OUTPUT_FILES,
        "reporting": [
            "variant_1_candidates",
            "variant_1_buys",
            "variant_2_candidates",
            "variant_2_buys",
            "sells_by_reason",
            "open_runners",
            "max_fdv_after_sell_for_closed_positions",
            "missed_upside_summary",
            "blockers",
            "next_logical_step",
        ],
        "guardrails": [
            "paper_only",
            "shadow_only",
            "no_private_keys",
            "no_wallet_execution",
            "no_transaction_signing",
            "no_order_routing",
            "no_live_trading",
            "no_rule_d_overwrite",
            "preserve_historical_artifacts",
        ],
    }


def write_rule_v2_shadow_lock_artifacts(
    *,
    data_root: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Write the locked V2 config to the data lake and repo config folder."""
    root = Path(data_root or data_lake_root()).expanduser()
    repo = Path(repo_root or Path.cwd()).expanduser()
    shadow_root = root / RULE_V2_SHADOW_RELATIVE_ROOT
    repo_config_path = repo / "configs" / "rule_v2_shadow.json"
    config = build_rule_v2_shadow_config()
    locked_config_path = shadow_root / RULE_V2_SHADOW_OUTPUT_FILES["locked_config"]
    manifest_path = shadow_root / RULE_V2_SHADOW_OUTPUT_FILES["lock_manifest"]
    daily_status_path = shadow_root / RULE_V2_SHADOW_OUTPUT_FILES["daily_status"]
    variant_summary_path = shadow_root / RULE_V2_SHADOW_OUTPUT_FILES["variant_summary"]

    shadow_root.mkdir(parents=True, exist_ok=True)
    repo_config_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "locked": True,
        "locked_at": _utc_now(),
        "mode": config["mode"],
        "variant_ids": [variant["variant_id"] for variant in config["buy_variants"]],
        "shared_exit_rule_id": config["shared_exit_rule"]["rule_id"],
        "current_rule_d_overwritten": False,
        "repo_config_path": str(repo_config_path),
        "locked_config_path": str(locked_config_path),
        "daily_status_path": str(daily_status_path),
        "variant_summary_path": str(variant_summary_path),
        "output_root": str(shadow_root),
    }
    variant_summary = {
        "mode": config["mode"],
        "no_real_trade": True,
        "variant_1_candidates": 0,
        "variant_1_buys": 0,
        "variant_2_candidates": 0,
        "variant_2_buys": 0,
        "sells_by_reason": {},
        "open_runners": 0,
        "missed_upside_summary": {},
        "blockers": [],
        "next_logical_step": "run paper-only proof campaign and compare V2 variant buys, sells, and post-sell upside capture",
    }

    _write_json(repo_config_path, config)
    _write_json(locked_config_path, config)
    _write_json(manifest_path, manifest)
    _write_json(variant_summary_path, variant_summary)
    daily_status_path.write_text(_status_markdown(config, manifest, variant_summary), encoding="utf-8")

    return {
        **manifest,
        "locked": True,
        "report_paths": {
            "repo_config": str(repo_config_path),
            "locked_config": str(locked_config_path),
            "manifest": str(manifest_path),
            "daily_status": str(daily_status_path),
            "variant_summary": str(variant_summary_path),
        },
    }


def _status_markdown(config: dict[str, Any], manifest: dict[str, Any], variant_summary: dict[str, Any]) -> str:
    variant_ids = ", ".join(manifest["variant_ids"])
    return "\n".join(
        [
            "# Rule V2 Shadow Lock Status",
            "",
            f"Locked at: `{manifest['locked_at']}`",
            f"Mode: `{config['mode']}`",
            f"Buy variants: `{variant_ids}`",
            f"Shared exit: `{manifest['shared_exit_rule_id']}`",
            f"Starting paper cash: `${config['starting_paper_cash_usd']}`",
            f"Position fraction: `{config['position_fraction']:.2%}`",
            f"Current Rule D config overwritten: `{manifest['current_rule_d_overwritten']}`",
            "",
            "No real trades, wallet execution, transaction signing, swaps, or order routing are enabled.",
            "",
            "## Entry Gate",
            "",
            "- Confirmed clean 10k required.",
            "- Confirmed clean 20k required.",
            "- Buy FDV band is `$20,000` to `$26,000` unless explicit fast-entry burst validation applies.",
            "- Holder count <= 1 is a hard reject.",
            "- Missing holder depth, Mayhem, low holder depth, dev-pump, and fake-volume are labels or variant conditions, not universal hard rejects.",
            "",
            "## Variant Summary",
            "",
            f"- Variant 1 candidates/buys: `{variant_summary['variant_1_candidates']}` / `{variant_summary['variant_1_buys']}`",
            f"- Variant 2 candidates/buys: `{variant_summary['variant_2_candidates']}` / `{variant_summary['variant_2_buys']}`",
            f"- Open runners: `{variant_summary['open_runners']}`",
            f"- Blockers: `{variant_summary['blockers']}`",
            f"- Next logical step: `{variant_summary['next_logical_step']}`",
            "",
        ]
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
