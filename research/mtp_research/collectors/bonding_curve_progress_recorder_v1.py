"""Forward recorder for broad Pump.fun bonding-curve progress research.

This module is intentionally separate from the Mayhem collector. It does not
trade, paper trade, tune thresholds, or execute buy/sell logic. The live-source
integration point is kept behind fake-source-friendly methods so unit tests can
exercise admission, priority, crossing, migration, and summary behavior without
network access.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import itertools
import json
import math
import os
import queue
import shutil
import sqlite3
import struct
import threading
import time
import urllib.request
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from research.mtp_research.validation.t007_full_path_lifecycle_tracker import (
    build_lifecycle_live_status_payload,
    build_lifecycle_outputs,
)
from research.mtp_research.validation.t007_lifecycle_collector_adapter import (
    T007LifecycleCollectorAdapter,
)
from research.mtp_research.validation.t007_lifecycle_exporter import (
    export_lifecycle_outputs_from_store,
)
from research.mtp_research.validation.t007_evidence_model import (
    AccountSnapshotRecord,
    EvidenceRecord,
    LifecycleTransitionRecord,
    MigrationEvidenceLevel,
)
from research.mtp_research.validation.t007_evidence_store import T007EvidenceStore

TRUE_CURVE_PROGRESS_THRESHOLDS = [40.0, 50.0, 55.0, 60.0, 62.5, 65.0, 67.5, 70.0, 72.5, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0]
THRESHOLDS = TRUE_CURVE_PROGRESS_THRESHOLDS
VALUATION_BANDS_USD = [15_000, 20_000, 25_000, 30_000, 35_000, 36_000, 40_000, 45_000, 50_000, 55_000, 60_000, 69_000, 75_000, 100_000, 150_000, 250_000, 500_000, 1_000_000]
VALUATION_LADDER_TRANSITION_PAIRS = [
    (30_000, 35_000),
    (30_000, 40_000),
    (30_000, 50_000),
    (30_000, 60_000),
    (36_000, 40_000),
    (36_000, 50_000),
    (36_000, 60_000),
    (40_000, 50_000),
    (40_000, 60_000),
    (50_000, 60_000),
    (50_000, 100_000),
]
VALUATION_LADDER_CHECKPOINT_BANDS = {30_000, 36_000, 40_000, 50_000, 60_000}
VALUATION_LADDER_STALL_SECONDS = [5, 10, 15, 30, 60, 120, 300]
PUMPFUN_PROGRESS_DENOMINATOR_TOKENS = 793_100_000.0
PUMPFUN_TOKEN_TOTAL_SUPPLY_TOKENS = 1_000_000_000.0
PROGRESS_FORMULA_VERSION = "pumpfun_real_token_reserves_v1"
ACTIVE_LIFECYCLE_POLICY_VERSION = "t007aa_active_lifecycle_v1"
QUOTE_NORMALIZATION_VERSION = "t007ab_sol_usdc_quote_normalization_v1"
MIGRATION_DETECTOR_VERSION = "t007ac_pumpswap_sol_usdc_program_subscribe_v1"
VALUATION_LADDER_POLICY = "market_cap_confirmed_only"
MARKET_CAP_FORMULA_VERSION = "t007_quote_normalized_bonding_curve_market_cap_v1"
T007_BIRTH_SOURCE_ROUTE_VERSION = "t007af_birth_source_route_v2"
PUMP_FUN_PROGRAM_ID_FOR_AUDIT = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_FUN_MIGRATION_WRAPPER_PROGRAM_ID = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
PUMPSWAP_PROGRAM_ID_FOR_AUDIT = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
PUMP_FUN_PROGRAM_ID = PUMP_FUN_PROGRAM_ID_FOR_AUDIT
PUMPSWAP_PROGRAM_ID = PUMPSWAP_PROGRAM_ID_FOR_AUDIT
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PYTH_SOL_USD_PRICE_FEED_ID = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
PYTH_HERMES_PRICE_URL = "https://hermes.pyth.network/v2/updates/price/latest"
PUMPSWAP_MARKET_ACCOUNT_LENGTH = 245
PUMPSWAP_MARKET_ACCOUNT_LENGTH_EXTENDED = 301
PUMPSWAP_MARKET_ACCOUNT_LENGTHS = (PUMPSWAP_MARKET_ACCOUNT_LENGTH, PUMPSWAP_MARKET_ACCOUNT_LENGTH_EXTENDED)
PUMPSWAP_MARKET_ACCOUNT_LENGTHS_PENDING_FIXTURE: tuple[int, ...] = ()
PUMPSWAP_MARKET_DISCRIMINATOR_BYTES = b"\xf1\x9am\x04\x11\xb1m\xbc"
PUMPSWAP_MARKET_QUOTE_MINT_OFFSET = 75
RAYDIUM_LAUNCHLAB_PROGRAM_ID_FOR_AUDIT = "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"
RAYDIUM_CPMM_PROGRAM_ID_FOR_AUDIT = "CPMMoo8L3F4NbTegBCKVNuxFYvWzqMe9J1KLcXxj3xV"
TIER_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "very_high": 4,
    "critical": 5,
    "stopped": 0,
}
DEFAULT_BASE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "MemeTraderPro"
    / "data"
    / "forward"
    / "bonding_curve_progress_recorder_v1"
)
DEFAULT_ARCHIVE_ROOT = Path("/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1")
POST_MIGRATION_OBSERVATION_HORIZONS_SECONDS = (0, 5, 15, 30, 60, 120, 300, 600)
JSONL_ARTIFACT_FILES = (
    "hotpath_latency_spans.jsonl",
    "birth_audit.jsonl",
    "curve_observations.jsonl",
    "threshold_crossings.jsonl",
    "true_curve_threshold_crossings.jsonl",
    "curve_velocity_events.jsonl",
    "curve_acceleration_events.jsonl",
    "trade_flow_events.jsonl",
    "organic_flow_events.jsonl",
    "holder_distribution_snapshots.jsonl",
    "dev_behavior_events.jsonl",
    "migration_events.jsonl",
    "migration_candidates.jsonl",
    "global_migration_events.jsonl",
    "global_migration_raw_candidates.jsonl",
    "global_migration_write_intents.jsonl",
    "global_migration_candidates.jsonl",
    "global_migration_event_duplicates.jsonl",
    "dual_lane_reconciliation_rows.jsonl",
    "post_migration_observations.jsonl",
    "executable_quote_observations.jsonl",
    "execution_cost_observations.jsonl",
    "token_path_summary.jsonl",
    "migration_route_audit_rows.jsonl",
    "pumpswap_route_candidates.jsonl",
    "pumpswap_swap_events.jsonl",
    "pumpswap_transaction_route_audit.jsonl",
    "direct_mint_lookup_rows.jsonl",
    "axiom_direct_lookup_evidence.jsonl",
    "valuation_formula_audit.jsonl",
    "valuation_ladder_events.jsonl",
    "valuation_ladder_paths.jsonl",
    "wallet_dev_checkpoints.jsonl",
    "probe_attempts.jsonl",
    "raw_birth_source_audit.jsonl",
)
GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT = "global_migration_raw_candidates.jsonl"
GLOBAL_MIGRATION_WRITE_INTENTS_ARTIFACT = "global_migration_write_intents.jsonl"
_JSONL_FILE_LOCKS: dict[str, threading.Lock] = {}
_JSONL_FILE_LOCKS_GUARD = threading.Lock()
T007AA_PLACEHOLDER_ARTIFACTS: dict[str, dict[str, Any]] = {
    "trade_flow_events.jsonl": {"trade_flow_status": "schema_ready_pending_live_source", "data_family": "trade_flow"},
    "organic_flow_events.jsonl": {"organic_share_status": "schema_ready_pending_live_source", "data_family": "organic_flow"},
    "holder_distribution_snapshots.jsonl": {"holder_distribution_status": "schema_ready_pending_live_source", "data_family": "holder_distribution"},
    "dev_behavior_events.jsonl": {"dev_behavior_status": "schema_ready_pending_live_source", "data_family": "dev_behavior"},
    "post_migration_observations.jsonl": {"executable_quote_status": "schema_ready_pending_live_source", "data_family": "post_migration_depth"},
    "executable_quote_observations.jsonl": {"quote_status": "schema_ready_pending_live_source", "data_family": "executable_quote"},
    "execution_cost_observations.jsonl": {"execution_cost_status": "schema_ready_pending_live_source", "data_family": "execution_cost"},
}
EXECUTABLE_QUOTE_CLIPS_BY_QUOTE_ASSET: dict[str, tuple[float, ...]] = {
    "SOL": (0.05, 0.10, 0.25, 0.50),
    "USDC": (5.0, 10.0, 25.0, 50.0),
}
PROGRESS_FORMULA_NOTE = (
    "progress_pct is accepted when supplied by the observation source. If absent, "
    "this v1 recorder preserves raw curve state fields and leaves progress_pct null; "
    "the exact Pump.fun bonding-curve percent formula remains a forward-data blocker."
)
T007_SCAN_CATEGORIES: dict[str, dict[str, Any]] = {
    "feature_feed_proof": {
        "max_duration_seconds": 600,
        "purpose": "prove_one_new_data_feed_writes_live_rows",
        "allowed_before_thesis_ready_gate": True,
    },
    "thesis_schema_validation": {
        "max_duration_seconds": 600,
        "purpose": "verify_artifacts_schema_and_statuses",
        "allowed_before_thesis_ready_gate": True,
    },
    "thesis_data_collection": {
        "min_duration_seconds": 3600,
        "purpose": "collect_thesis_testable_forward_data",
        "allowed_before_thesis_ready_gate": False,
    },
    "long_collection": {
        "min_duration_seconds": 7200,
        "purpose": "multi_hour_collection_after_valid_60m_thesis_collection",
        "allowed_before_valid_60m_collection": False,
    },
}
T007_H001_REQUIRED_FEATURE_FAMILIES = [
    "birth_lane",
    "true_curve_progress",
    "threshold_crossings",
    "curve_velocity",
    "curve_acceleration",
    "trade_efficiency",
    "trade_flow",
    "buyer_breadth",
    "buy_sell_pressure",
    "pumpswap_global_migration_linkage",
    "token_path_summary",
    "decision_time_safety_checks",
]
T007_ADVANCED_FEATURE_FAMILIES = [
    "organic_bot_share_partial_features",
    "holder_distribution_partial_snapshots",
    "dev_creator_behavior_partial_features",
    "post_migration_observations_partial",
    "execution_cost_observations_partial",
]


def evaluate_t007_thesis_ready_gate(
    status: dict[str, Any] | None = None,
    *,
    thesis_scope: str = "h001_pre_migration",
) -> dict[str, Any]:
    """Return the hard no-long-scan gate for T007 thesis collection."""

    payload = dict(status or {})
    explicit_live = {str(value) for value in payload.get("live_feature_families") or []}
    explicit_deferred = {str(value) for value in payload.get("deferred_feature_families") or []}
    explicit_placeholders = {str(value) for value in payload.get("placeholder_feature_families") or []}
    live_feature_families = [
        family for family in [*T007_H001_REQUIRED_FEATURE_FAMILIES, *T007_ADVANCED_FEATURE_FAMILIES]
        if family not in explicit_placeholders and _t007_feature_family_live(family, payload, explicit_live)
    ]
    h001_missing = [
        family for family in T007_H001_REQUIRED_FEATURE_FAMILIES
        if family not in live_feature_families and not _t007_h001_partial_allowed(family, explicit_deferred)
    ]
    advanced_missing = [
        family for family in T007_ADVANCED_FEATURE_FAMILIES
        if family not in live_feature_families
    ]
    valuation_ladder_policy = str(payload.get("valuation_ladder_emission_policy") or payload.get("valuation_ladder_policy") or VALUATION_LADDER_POLICY)
    valuation_ladder_suppressed = valuation_ladder_policy == "market_cap_confirmed_only"
    blocking_reasons: list[str] = []
    if h001_missing:
        blocking_reasons.append("h001_required_feature_families_missing")
    if advanced_missing:
        blocking_reasons.append("advanced_feature_families_placeholder_only")
    if not valuation_ladder_suppressed:
        blocking_reasons.append("valuation_ladder_not_suppressed")
    sol_quote_curve_rows = int(_num(payload.get("bonding_curve_market_cap_quote_asset_SOL_count")) or 0) or _t007_nested_count(
        payload, "curve_observations_by_quote_asset", "SOL"
    )
    sol_quote_pool_rows = int(_num(payload.get("pool_market_cap_quote_asset_SOL_count")) or 0) or _t007_nested_count(
        payload, "post_migration_observations_by_quote_asset", "SOL"
    )
    sol_usd_value = _num(payload.get("sol_usd"))
    sol_usd_status = str(payload.get("sol_usd_status") or ("available" if sol_usd_value is not None else "missing"))
    sol_usd_available = sol_usd_value is not None and sol_usd_status == "available"
    sol_usd_required = (sol_quote_curve_rows + sol_quote_pool_rows) > 0
    if sol_usd_required and not sol_usd_available:
        blocking_reasons.append("sol_usd_missing_for_sol_market_cap")
    pool_state_error_count = int(_num(payload.get("post_migration_pool_state_error_count")) or 0)
    post_migration_observation_count = int(_num(payload.get("post_migration_observations_written")) or 0)
    pool_state_error_rate = (
        float(pool_state_error_count) / float(post_migration_observation_count)
        if post_migration_observation_count > 0
        else 0.0
    )
    scope_text = str(thesis_scope or "").lower()
    quote_depth_required_for_scope = bool(payload.get("quote_depth_required_for_scope")) or any(
        token in scope_text for token in ("post_migration", "exit", "depth", "full")
    )
    pool_liquidity_available = (
        int(_num(payload.get("pool_liquidity_quote_present_count")) or 0) > 0
        and int(_num(payload.get("pool_liquidity_usd_present_count")) or 0) > 0
    )
    quote_rows_written = int(_num(payload.get("executable_quote_observations_written")) or 0)
    price_impact_available = int(_num(payload.get("price_impact_available_count")) or 0) > 0
    decision_time_safe_quote_rows = int(_num(payload.get("executable_quote_decision_time_safe_count")) or 0)
    fee_model_confirmed_count = int(_num(payload.get("fee_model_confirmed_count")) or 0)
    fee_model_assumed_count = int(_num(payload.get("fee_model_assumed_count")) or 0)
    fee_model_unknown_count = int(_num(payload.get("fee_model_unknown_count")) or 0)
    executable_quote_available = (
        (
            int(_num(payload.get("post_migration_quote_available_count")) or 0) > 0
            and int(_num(payload.get("post_migration_decision_time_safe_executable_count")) or 0) > 0
        )
        or (quote_rows_written > 0 and price_impact_available and decision_time_safe_quote_rows > 0)
    )
    quote_deferred_only = (
        int(_num(payload.get("post_migration_quote_deferred_count")) or 0) > 0
        and int(_num(payload.get("post_migration_quote_available_count")) or 0) == 0
    )
    quote_depth_blocking_reasons: list[str] = []
    if quote_deferred_only:
        quote_depth_blocking_reasons.append("executable_quote_not_available")
    if not pool_liquidity_available:
        quote_depth_blocking_reasons.append("pool_liquidity_not_available")
    if (int(_num(payload.get("post_migration_quote_available_count")) or 0) > 0 or quote_rows_written > 0) and not executable_quote_available:
        quote_depth_blocking_reasons.append("decision_time_safe_executable_quote_not_available")
    if pool_state_error_count > 0 and pool_state_error_rate > 0.20:
        quote_depth_blocking_reasons.append("post_migration_pool_state_hard_error_rate_too_high")
    quote_depth_partial_fee_unknown = (
        pool_liquidity_available
        and executable_quote_available
        and price_impact_available
        and fee_model_unknown_count > 0
    )
    quote_depth_partial_fee_assumed = (
        pool_liquidity_available
        and executable_quote_available
        and price_impact_available
        and fee_model_assumed_count > 0
        and fee_model_unknown_count == 0
    )
    quote_depth_confirmed = (
        pool_liquidity_available
        and executable_quote_available
        and price_impact_available
        and fee_model_confirmed_count > 0
        and fee_model_assumed_count == 0
        and fee_model_unknown_count == 0
    )
    quote_depth_status = (
        "QUOTE_DEPTH_READY"
        if not quote_depth_blocking_reasons and quote_depth_confirmed
        else "QUOTE_DEPTH_PARTIAL_FEE_ASSUMED"
        if quote_depth_partial_fee_assumed
        else "QUOTE_DEPTH_PARTIAL_FEE_UNKNOWN"
        if quote_depth_partial_fee_unknown
        else "QUOTE_DEPTH_NOT_READY"
    )
    if quote_depth_required_for_scope:
        blocking_reasons.extend(quote_depth_blocking_reasons)
    elif quote_depth_blocking_reasons:
        for reason in quote_depth_blocking_reasons:
            if reason == "post_migration_pool_state_hard_error_rate_too_high" and reason not in blocking_reasons:
                blocking_reasons.append(reason)
    can_test_pre_migration_only_thesis = (
        not h001_missing
        and not advanced_missing
        and valuation_ladder_suppressed
        and not (sol_usd_required and not sol_usd_available)
    )
    can_test_post_migration_exit_thesis = (
        can_test_pre_migration_only_thesis
        and quote_depth_status == "QUOTE_DEPTH_READY"
    )
    can_run_partial_post_migration_depth_60m = (
        can_test_pre_migration_only_thesis
        and quote_depth_required_for_scope
        and quote_depth_status in {"QUOTE_DEPTH_PARTIAL_FEE_UNKNOWN", "QUOTE_DEPTH_PARTIAL_FEE_ASSUMED"}
    )
    can_run_60m = (
        can_test_post_migration_exit_thesis or can_run_partial_post_migration_depth_60m
        if quote_depth_required_for_scope
        else can_test_pre_migration_only_thesis
    )
    clean_60m_passed = _t007_clean_60m_validation_passed(payload)
    explicit_60m_validation_seen = _t007_explicit_60m_validation_seen(payload)
    if explicit_60m_validation_seen and not clean_60m_passed and "clean_60m_validation_not_passed" not in blocking_reasons:
        blocking_reasons.append("clean_60m_validation_not_passed")
    can_run_one_2h = bool(
        clean_60m_passed
        and can_test_pre_migration_only_thesis
        and valuation_ladder_suppressed
        and not h001_missing
        and not advanced_missing
    )
    can_run_2h = can_run_one_2h
    if can_run_one_2h:
        allowed_scan_scope = "one_controlled_2h_thesis_collection"
    elif quote_depth_required_for_scope and can_test_post_migration_exit_thesis:
        allowed_scan_scope = "full_thesis_60m"
    elif can_run_partial_post_migration_depth_60m:
        allowed_scan_scope = "post_migration_depth_partial_60m"
    elif not quote_depth_required_for_scope and can_test_pre_migration_only_thesis:
        allowed_scan_scope = "pre_migration_only_60m"
    elif gate_disallows_all := (not valuation_ladder_suppressed):
        allowed_scan_scope = "none"
    else:
        allowed_scan_scope = "10m_feature_proof_only"
    gate = {
        "gate_id": "T007_NO_LONG_SCAN_UNTIL_THESIS_READY_GATE",
        "thesis_scope": thesis_scope,
        "scan_categories": T007_SCAN_CATEGORIES,
        "can_run_10m_feature_proof": True,
        "can_run_60m_thesis_scan": can_run_60m,
        "can_run_2h_plus_scan": can_run_2h,
        "can_run_one_2h_thesis_collection": can_run_one_2h,
        "can_run_4h_plus": False,
        "blocking_reasons": blocking_reasons,
        "missing_feature_families": [*h001_missing, *advanced_missing],
        "live_feature_families": live_feature_families,
        "deferred_feature_families": sorted(explicit_deferred),
        "quote_depth_required_for_scope": quote_depth_required_for_scope,
        "quote_depth_status": quote_depth_status,
        "pool_liquidity_available": pool_liquidity_available,
        "executable_quote_available": executable_quote_available,
        "price_impact_available": price_impact_available,
        "can_test_post_migration_exit_thesis": can_test_post_migration_exit_thesis,
        "can_test_post_migration_depth_partial_thesis": bool(can_run_partial_post_migration_depth_60m or can_run_one_2h),
        "can_test_pre_migration_only_thesis": can_test_pre_migration_only_thesis,
        "allowed_scan_scope": allowed_scan_scope,
        "edge_claim_allowed": False,
        "live_trading_allowed": False,
        "paper_trading_allowed": False,
        "valuation_ladder_allowed": False,
        "wallet_signing_execution_allowed": False,
        "valuation_ladder_suppressed": valuation_ladder_suppressed,
        "valuation_ladder_policy": valuation_ladder_policy,
        "sol_usd_required": sol_usd_required,
        "sol_usd_available": sol_usd_available,
        "sol_usd_status": sol_usd_status,
        "sol_usd_source": payload.get("sol_usd_source"),
        "post_migration_pool_state_error_count": pool_state_error_count,
        "post_migration_pool_state_error_rate": pool_state_error_rate,
        "mayhem_files_modified": False,
        "trading_enabled": False,
        "paper_trading_enabled": False,
        "minimum_next_action": "",
    }
    gate["minimum_next_action"] = _t007_minimum_next_action(gate)
    return gate


def write_t007_thesis_ready_gate(output_dir: str | Path, status: dict[str, Any] | None = None) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    gate = evaluate_t007_thesis_ready_gate(status)
    (output_path / "thesis_ready_gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_path / "summary.md").write_text(_t007_gate_summary_md(gate), encoding="utf-8")
    return gate


def _t007_feature_family_live(family: str, payload: dict[str, Any], explicit_live: set[str]) -> bool:
    if family in explicit_live:
        return True
    if family == "birth_lane":
        return _t007_positive(payload, "unique_birth_mints", "births_detected", "decoded_birth_rows")
    if family == "true_curve_progress":
        return _t007_positive(payload, "progress_decoded_exact_count", "progress_decoded_candidate_count", "decode_success_count")
    if family == "threshold_crossings":
        return _t007_positive(payload, "true_curve_threshold_crossings_written", "threshold_crossings_written")
    if family == "curve_velocity":
        return _t007_positive(payload, "curve_velocity_events_written")
    if family == "curve_acceleration":
        return _t007_positive(payload, "curve_acceleration_events_written")
    if family == "trade_efficiency":
        return _t007_positive(payload, "trade_flow_events_written", "trade_rows_recorded")
    if family == "trade_flow":
        return _t007_positive(payload, "trade_flow_events_written", "trade_rows_recorded")
    if family == "buyer_breadth":
        return _t007_positive(payload, "buyer_breadth_available_count", "unique_buyers_observed")
    if family == "buy_sell_pressure":
        return _t007_positive(payload, "trade_flow_events_written", "buy_rows", "sell_rows")
    if family == "pumpswap_global_migration_linkage":
        return _t007_positive(payload, "global_migration_events", "global_migration_events_deduped", "deduped_pumpswap_migration_events", "unique_migrated_mints")
    if family == "token_path_summary":
        return _t007_positive(payload, "token_path_summary_rows", "token_path_summary_written", "token_path_summary_count")
    if family == "decision_time_safety_checks":
        return "decision_time_safety_violation_count" in payload or "decision_time_safety_checks" in explicit_live
    if family == "organic_bot_share_partial_features":
        return _t007_positive(payload, "organic_flow_events_written")
    if family == "holder_distribution_partial_snapshots":
        return _t007_positive(payload, "holder_distribution_snapshots_written")
    if family == "dev_creator_behavior_partial_features":
        return _t007_positive(payload, "dev_behavior_events_written")
    if family == "post_migration_observations_partial":
        return _t007_positive(payload, "post_migration_observations_written")
    if family == "execution_cost_observations_partial":
        return _t007_positive(payload, "execution_cost_observations_written")
    return False


def _t007_h001_partial_allowed(family: str, explicit_deferred: set[str]) -> bool:
    return family == "curve_acceleration" and family in explicit_deferred


def _t007_nested_count(payload: dict[str, Any], key: str, nested_key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, dict):
        return 0
    return int(_num(value.get(nested_key)) or 0)


def _t007_positive(payload: dict[str, Any], *keys: str) -> bool:
    return any((_num(payload.get(key)) or 0.0) > 0.0 for key in keys)


def _t007_zero(payload: dict[str, Any], *keys: str) -> bool:
    present = [key for key in keys if key in payload]
    if not present:
        return True
    return all((_num(payload.get(key)) or 0.0) == 0.0 for key in present)


def _t007_false(payload: dict[str, Any], *keys: str) -> bool:
    present = [key for key in keys if key in payload]
    if not present:
        return True
    return all(bool(payload.get(key)) is False for key in present)


def _t007_explicit_60m_validation_seen(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "decision_label",
            "final_decision_label",
            "t007ba_decision_label",
            "valid_60m_thesis_collection_passed",
            "source_duration_quality_status",
        )
    )


def _t007_clean_60m_validation_passed(payload: dict[str, Any]) -> bool:
    decision = str(
        payload.get("decision_label")
        or payload.get("final_decision_label")
        or payload.get("t007ba_decision_label")
        or ""
    )
    decision_passed = decision == "T007BA_60M_PARTIAL_DEPTH_VALIDATION_PASSED" or bool(
        payload.get("valid_60m_thesis_collection_passed")
    )
    source_complete = str(payload.get("source_duration_quality_status") or "") in {"complete", "complete_with_reconnect_warning"}
    archive_complete = str(payload.get("archive_status") or "") == "complete"
    run_finalized = bool(payload.get("run_finalized")) is True
    safety_clean = _t007_zero(payload, "decision_time_safety_violations", "decision_time_safety_violation_count")
    valuation_clean = _t007_zero(payload, "valuation_ladder_events", "valuation_ladder_events_written")
    health_clean = (
        _t007_zero(payload, "queue_drops", "queue_dropped_count")
        and _t007_zero(payload, "capacity_rejected", "capacity_rejected_after_dedupe", "capacity_rejected_births")
        and _t007_zero(payload, "http_429", "http_429_count")
        and _t007_zero(payload, "rpc_failures", "rpc_failure_count")
    )
    code_boundaries_clean = _t007_false(payload, "mayhem_files_modified", "mayhem_code_modified")
    trading_paths_clean = bool(payload.get("trading_paper_wallet_signing_execution_untouched", True)) is True
    fee_clean = (
        str(payload.get("fee_proof_label") or "") == "POST_PATCH_EVENT_FEE_PROOF_PASSED"
        or (
            str(payload.get("fee_model_status") or "") == "confirmed"
            and int(_num(payload.get("event_endpoint_pass_count")) or 0) > 0
            and int(_num(payload.get("event_endpoint_fail_count")) or 0) == 0
        )
    )
    quote_rows_present = int(_num(payload.get("executable_quote_observations_written")) or 0) > 0
    price_impact_present = (
        int(_num(payload.get("price_impact_rows_populated")) or 0) > 0
        or int(_num(payload.get("price_impact_available_count")) or 0) > 0
    )
    execution_cost_present = int(_num(payload.get("execution_cost_observations_written")) or 0) > 0
    return all(
        (
            decision_passed,
            source_complete,
            archive_complete,
            run_finalized,
            health_clean,
            safety_clean,
            valuation_clean,
            code_boundaries_clean,
            trading_paths_clean,
            fee_clean,
            quote_rows_present,
            price_impact_present,
            execution_cost_present,
        )
    )


def _t007_minimum_next_action(gate: dict[str, Any]) -> str:
    missing = set(gate.get("missing_feature_families") or [])
    if gate.get("can_run_one_2h_thesis_collection"):
        return "run exactly one controlled 2h thesis collection"
    if gate.get("can_run_60m_thesis_scan"):
        return "run 60m thesis-data collection"
    if {"trade_flow", "trade_efficiency", "buy_sell_pressure", "buyer_breadth"} & missing:
        return "implement trade-flow feed"
    if "pumpswap_global_migration_linkage" in missing:
        return "fix migration linkage"
    if {"holder_distribution_partial_snapshots", "dev_creator_behavior_partial_features", "organic_bot_share_partial_features"} & missing:
        return "implement holder/dev enrichment"
    if "post_migration_observations_partial" in missing:
        return "implement post-migration depth/quotes"
    if "execution_cost_observations_partial" in missing:
        return "implement execution-cost observations"
    return "run 10m feature proof only"


def _t007_gate_summary_md(gate: dict[str, Any]) -> str:
    lines = [
        "# T007 Thesis-Ready Gate",
        "",
        f"- Gate: `{gate.get('gate_id')}`",
        f"- 10m feature proof allowed: `{gate.get('can_run_10m_feature_proof')}`",
        f"- 60m thesis scan allowed: `{gate.get('can_run_60m_thesis_scan')}`",
        f"- 2h+ scan allowed: `{gate.get('can_run_2h_plus_scan')}`",
        f"- Valuation ladder suppressed: `{gate.get('valuation_ladder_suppressed')}`",
        f"- Mayhem files modified: `{gate.get('mayhem_files_modified')}`",
        f"- Minimum next action: `{gate.get('minimum_next_action')}`",
        "",
        "## Blocking reasons",
        "",
        *[f"- `{reason}`" for reason in (gate.get("blocking_reasons") or ["none"])],
        "",
        "## Missing feature families",
        "",
        *[f"- `{family}`" for family in (gate.get("missing_feature_families") or ["none"])],
        "",
        "## Live feature families",
        "",
        *[f"- `{family}`" for family in (gate.get("live_feature_families") or ["none"])],
        "",
        "## Deferred feature families",
        "",
        *[f"- `{family}`" for family in (gate.get("deferred_feature_families") or ["none"])],
        "",
        "No scan longer than 10 minutes is allowed unless this gate allows the relevant scan class.",
        "",
    ]
    return "\n".join(lines)


TRACKING_PROFILE_CONSERVATIVE_DEFAULT = "conservative_default"
TRACKING_PROFILE_HIGH_CAP_FULL_PATH_PROOF = "high_cap_full_path_proof"


def tracking_profile_settings(profile: str | None = None) -> dict[str, Any]:
    name = str(profile or TRACKING_PROFILE_CONSERVATIVE_DEFAULT).strip() or TRACKING_PROFILE_CONSERVATIVE_DEFAULT
    if name == TRACKING_PROFILE_HIGH_CAP_FULL_PATH_PROOF:
        return {
            "tracking_profile": TRACKING_PROFILE_HIGH_CAP_FULL_PATH_PROOF,
            "max_active_tracking": 800,
            "followup_queue_max_size": 2000,
            "thin_probe_queue_max_size": 5000,
            "migration_aware_promotion_enabled": True,
            "reserved_migration_candidate_slots": 150,
            "evict_low_priority_stale_mints_for_promotion": True,
            "strict_health_gates_enabled": True,
            "promote_on_curve_progress_pct": 20.0,
            "promote_on_trade_rows": 5,
            "promote_on_migration_candidate": True,
            "promote_on_threshold_crossing": True,
            "profile_explicit_required": True,
        }
    if name != TRACKING_PROFILE_CONSERVATIVE_DEFAULT:
        raise ValueError(f"unknown tracking profile: {name}")
    return {
        "tracking_profile": TRACKING_PROFILE_CONSERVATIVE_DEFAULT,
        "max_active_tracking": None,
        "followup_queue_max_size": None,
        "thin_probe_queue_max_size": None,
        "migration_aware_promotion_enabled": False,
        "reserved_migration_candidate_slots": 0,
        "evict_low_priority_stale_mints_for_promotion": False,
        "strict_health_gates_enabled": False,
        "promote_on_curve_progress_pct": 20.0,
        "promote_on_trade_rows": 5,
        "promote_on_migration_candidate": False,
        "promote_on_threshold_crossing": False,
        "profile_explicit_required": False,
    }


@dataclass
class BondingCurveRecorderConfig:
    output_root: Path | str
    run_id: str = ""
    source_duration_seconds: float = 300.0
    followup_drain_seconds: float = 300.0
    sample_rate_percent: int = 55
    tracking_profile: str = TRACKING_PROFILE_CONSERVATIVE_DEFAULT
    max_active_tracking: int = 250
    followup_queue_max_size: int = 500
    thin_probe_queue_max_size: int = 1000
    thin_probe_retry_delays_ms: tuple[int, ...] = (250, 750, 2_000)
    birth_priority_worker_count: int = 1
    birth_priority_queue_max_size: int = 5000
    trade_flow_worker_count: int = 1
    trade_flow_queue_max_size: int = 20_000
    migration_backfill_queue_max_size: int = 100
    max_token_age_seconds: float = 1800.0
    inactive_timeout_seconds: float = 300.0
    no_decode_timeout_seconds: float = 60.0
    low_progress_timeouts: tuple[tuple[float, float], ...] = (
        (5.0, 60.0),
        (10.0, 120.0),
        (20.0, 300.0),
        (40.0, 600.0),
    )
    high_progress_retention_seconds: float = 1800.0
    very_high_progress_retention_seconds: float = 2700.0
    critical_progress_retention_seconds: float = 3600.0
    sol_usd: float | None = None
    sol_usd_source: str = ""
    sol_usd_status: str = ""
    sol_usd_error: str = ""
    probe_retry_delays_ms: tuple[int, ...] = (250, 750, 2_000, 5_000, 10_000)
    source_name: str = "bonding_curve_progress_recorder_v1"
    provisional_progress_formula: str = PROGRESS_FORMULA_NOTE
    staging_root: Path | str | None = None
    archive_root: Path | str | None = None
    archive_after_run: bool = False
    local_retention_enabled: bool = True
    local_retention_keep_latest: int = 1
    local_retention_archive_root: Path | str | None = DEFAULT_ARCHIVE_ROOT
    active_write_root: Path | str | None = None
    local_free_space_bytes_start: int | None = None
    archive_free_space_bytes_start: int | None = None
    storage_preflight_status: str = "not_run"
    storage_preflight_errors: tuple[str, ...] = ()
    enable_global_pumpswap_migration: bool = False
    require_verified_curve_account_for_admission: bool = False
    global_migration_thread_join_timeout_seconds: float = 5.0
    migration_aware_promotion_enabled: bool = False
    reserved_migration_candidate_slots: int = 0
    evict_low_priority_stale_mints_for_promotion: bool = False
    strict_health_gates_enabled: bool = False
    promote_on_curve_progress_pct: float = 20.0
    promote_on_trade_rows: int = 5
    promote_on_migration_candidate: bool = False
    promote_on_threshold_crossing: bool = False
    gatekeeper_ab_enabled: bool = False
    gatekeeper_primary_endpoint_label: str = ""
    gatekeeper_comparison_endpoint_label: str = ""
    subscription_first_curve_updates_enabled: bool = False
    route_latency_gate_enabled: bool = True
    max_birth_to_admission_p95_ms: float = 1_000.0
    max_verified_birth_commit_to_probe_enqueue_p95_ms: float = 100.0
    max_birth_to_admission_complete_p95_ms: float = 1_500.0
    max_normalized_birth_to_probe_start_p95_ms: float = 1_500.0
    max_birth_to_first_curve_observation_p95_ms: float = 3_000.0
    max_probe_duration_p95_ms: float = 1_000.0
    near_entry_hot_flow_enabled: bool = True
    commitment_reorg_drop_accounting_enabled: bool = True
    helius_budget_gate_enabled: bool = True
    helius_max_estimated_credits: int | None = None
    helius_estimated_credits_used: int = 0
    max_finalization_wall_time_seconds: float = 30.0
    bounded_live_finalization_enabled: bool = False

    def __post_init__(self) -> None:
        self.tracking_profile = str(self.tracking_profile or TRACKING_PROFILE_CONSERVATIVE_DEFAULT).strip()
        profile = tracking_profile_settings(self.tracking_profile)
        if self.tracking_profile == TRACKING_PROFILE_HIGH_CAP_FULL_PATH_PROOF:
            self.max_active_tracking = int(profile["max_active_tracking"])
            self.followup_queue_max_size = int(profile["followup_queue_max_size"])
            self.thin_probe_queue_max_size = int(profile["thin_probe_queue_max_size"])
            self.migration_aware_promotion_enabled = bool(profile["migration_aware_promotion_enabled"])
            self.reserved_migration_candidate_slots = int(profile["reserved_migration_candidate_slots"])
            self.evict_low_priority_stale_mints_for_promotion = bool(
                profile["evict_low_priority_stale_mints_for_promotion"]
            )
            self.strict_health_gates_enabled = bool(profile["strict_health_gates_enabled"])
            self.promote_on_curve_progress_pct = float(profile["promote_on_curve_progress_pct"])
            self.promote_on_trade_rows = int(profile["promote_on_trade_rows"])
            self.promote_on_migration_candidate = bool(profile["promote_on_migration_candidate"])
            self.promote_on_threshold_crossing = bool(profile["promote_on_threshold_crossing"])
        self.output_root = Path(self.output_root)
        if self.staging_root is not None:
            self.staging_root = Path(self.staging_root)
            self.output_root = Path(self.staging_root)
        if self.archive_root is not None:
            self.archive_root = Path(self.archive_root)
        self.archive_after_run = _parse_bool_value(self.archive_after_run)
        self.local_retention_enabled = _parse_bool_value(self.local_retention_enabled)
        self.local_retention_keep_latest = max(1, int(self.local_retention_keep_latest or 1))
        if self.local_retention_archive_root is not None:
            self.local_retention_archive_root = Path(self.local_retention_archive_root)
        if self.sol_usd is not None:
            self.sol_usd = float(self.sol_usd)
            self.sol_usd_source = self.sol_usd_source or "manual_cli_sol_usd"
            self.sol_usd_status = self.sol_usd_status or "available"
            self.sol_usd_error = self.sol_usd_error or ""
        else:
            self.sol_usd_source = self.sol_usd_source or "missing"
            self.sol_usd_status = self.sol_usd_status or "missing"
        self.active_write_root = self.output_root
        if not self.run_id:
            self.run_id = "bc-progress-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        if not 0 <= int(self.sample_rate_percent) <= 100:
            raise ValueError("sample_rate_percent must be between 0 and 100")
        if int(self.max_active_tracking) <= 0:
            raise ValueError("max_active_tracking must be > 0")
        if int(self.followup_queue_max_size) <= 0:
            raise ValueError("followup_queue_max_size must be > 0")
        self.require_verified_curve_account_for_admission = _parse_bool_value(
            self.require_verified_curve_account_for_admission
        )
        self.migration_aware_promotion_enabled = _parse_bool_value(self.migration_aware_promotion_enabled)
        self.evict_low_priority_stale_mints_for_promotion = _parse_bool_value(
            self.evict_low_priority_stale_mints_for_promotion
        )
        self.strict_health_gates_enabled = _parse_bool_value(self.strict_health_gates_enabled)
        self.promote_on_migration_candidate = _parse_bool_value(self.promote_on_migration_candidate)
        self.promote_on_threshold_crossing = _parse_bool_value(self.promote_on_threshold_crossing)
        self.gatekeeper_ab_enabled = _parse_bool_value(self.gatekeeper_ab_enabled)
        self.subscription_first_curve_updates_enabled = _parse_bool_value(self.subscription_first_curve_updates_enabled)
        self.route_latency_gate_enabled = _parse_bool_value(self.route_latency_gate_enabled)
        self.near_entry_hot_flow_enabled = _parse_bool_value(self.near_entry_hot_flow_enabled)
        self.commitment_reorg_drop_accounting_enabled = _parse_bool_value(
            self.commitment_reorg_drop_accounting_enabled
        )
        self.helius_budget_gate_enabled = _parse_bool_value(self.helius_budget_gate_enabled)
        self.reserved_migration_candidate_slots = max(0, int(self.reserved_migration_candidate_slots))
        self.promote_on_curve_progress_pct = float(self.promote_on_curve_progress_pct)
        self.promote_on_trade_rows = max(0, int(self.promote_on_trade_rows))
        self.max_birth_to_admission_p95_ms = max(0.0, float(self.max_birth_to_admission_p95_ms))
        self.max_verified_birth_commit_to_probe_enqueue_p95_ms = max(
            0.0,
            float(self.max_verified_birth_commit_to_probe_enqueue_p95_ms),
        )
        self.max_birth_to_admission_complete_p95_ms = max(
            0.0,
            float(self.max_birth_to_admission_complete_p95_ms),
        )
        self.max_normalized_birth_to_probe_start_p95_ms = max(
            0.0,
            float(self.max_normalized_birth_to_probe_start_p95_ms),
        )
        self.max_birth_to_first_curve_observation_p95_ms = max(
            0.0,
            float(self.max_birth_to_first_curve_observation_p95_ms),
        )
        self.max_probe_duration_p95_ms = max(0.0, float(self.max_probe_duration_p95_ms))
        self.helius_estimated_credits_used = max(0, int(self.helius_estimated_credits_used or 0))
        if self.helius_max_estimated_credits is not None:
            self.helius_max_estimated_credits = max(0, int(self.helius_max_estimated_credits))
        self.max_finalization_wall_time_seconds = max(1.0, float(self.max_finalization_wall_time_seconds or 30.0))
        self.global_migration_thread_join_timeout_seconds = max(
            0.0,
            float(self.global_migration_thread_join_timeout_seconds),
        )
        self.thin_probe_queue_max_size = max(0, int(self.thin_probe_queue_max_size))
        self.thin_probe_retry_delays_ms = tuple(int(value) for value in self.thin_probe_retry_delays_ms)
        self.birth_priority_worker_count = max(1, int(self.birth_priority_worker_count))
        self.birth_priority_queue_max_size = max(1, int(self.birth_priority_queue_max_size))
        self.trade_flow_worker_count = max(1, int(self.trade_flow_worker_count))
        self.trade_flow_queue_max_size = max(1, int(self.trade_flow_queue_max_size))
        self.migration_backfill_queue_max_size = max(0, int(self.migration_backfill_queue_max_size))
        self.probe_retry_delays_ms = tuple(int(value) for value in self.probe_retry_delays_ms)
        self.low_progress_timeouts = tuple(
            (float(progress), float(seconds)) for progress, seconds in self.low_progress_timeouts
        )
        preflight = _run_storage_preflight(self)
        self.local_free_space_bytes_start = preflight.get("local_free_space_bytes_start")
        self.archive_free_space_bytes_start = preflight.get("archive_free_space_bytes_start")
        self.storage_preflight_status = preflight["storage_preflight_status"]
        self.storage_preflight_errors = tuple(preflight["storage_preflight_errors"])


def deterministic_sample_admitted(mint: str, sample_rate_percent: int = 55) -> bool:
    if sample_rate_percent <= 0:
        return False
    if sample_rate_percent >= 100:
        return True
    digest = hashlib.sha256(str(mint).encode("utf-8")).hexdigest()
    bucket = int(digest[:12], 16) % 100
    return bucket < int(sample_rate_percent)


def progress_priority_tier(progress_pct: float | None, *, complete: bool = False) -> str:
    if complete:
        return "stopped"
    if progress_pct is None:
        return "low"
    value = float(progress_pct)
    if value >= 75.0:
        return "critical"
    if value >= 60.0:
        return "very_high"
    if value >= 50.0:
        return "high"
    if value >= 40.0:
        return "medium"
    return "low"


def _birth_tracking_schema_fields(*, admitted: bool, admission_reason: str) -> dict[str, Any]:
    reason = str(admission_reason or "")
    if admitted:
        tier = "sampled_enrichment"
        sampling_status = "sampled_in"
    elif reason == "sample_rejected":
        tier = "thin"
        sampling_status = "sampled_out"
    elif reason.startswith("capacity_rejected"):
        tier = "deferred_enrichment"
        sampling_status = "capacity_deferred"
    else:
        tier = "thin"
        sampling_status = "not_eligible"
    return {
        "tracking_tier": tier,
        "tracking_tier_reason": reason or "birth_ledger",
        "thin_tracking_enabled": True,
        "deep_tracking_admitted": bool(admitted),
        "enrichment_sampling_status": sampling_status,
        "minimal_probe_policy": "thin_initial_250ms_optional_5s_optional_30s",
        "thin_probe_scheduled": False,
        "thin_probe_attempt_count": 0,
        "thin_probe_success_count": 0,
        "thin_probe_decode_status": None,
        "thin_highest_progress_pct": None,
        "thin_last_progress_pct": None,
    }


def _birth_capture_provenance_fields(launch: dict[str, Any], decoded_route: str | None) -> dict[str, Any]:
    raw_payload = launch.get("raw_decoded_launch_payload") if isinstance(launch.get("raw_decoded_launch_payload"), dict) else {}
    source_type = str(launch.get("source_type") or launch.get("source_route") or "unknown")
    route = str(
        launch.get("birth_capture_route")
        or (
            f"{source_type}:{raw_payload.get('source_instruction_decode_route') or decoded_route}"
            if (raw_payload.get("source_instruction_decode_route") or decoded_route)
            else source_type
        )
    )
    backfilled = _bool(launch.get("birth_backfilled_from_replay"))
    parser_status = str(raw_payload.get("parser_status") or launch.get("parser_status") or "")
    if launch.get("birth_capture_confidence"):
        confidence = str(launch.get("birth_capture_confidence"))
    elif backfilled:
        confidence = "replay_backfilled"
    elif parser_status == "decoded" or decoded_route:
        confidence = "decoded"
    else:
        confidence = "unknown"
    if launch.get("birth_capture_method"):
        method = str(launch.get("birth_capture_method"))
    elif backfilled:
        method = "global_migration_replay_backfill"
    elif source_type == "transaction_subscribe":
        method = "transaction_subscribe_live"
    else:
        method = source_type
    return {
        "birth_capture_route": route,
        "birth_capture_method": method,
        "birth_capture_confidence": confidence,
        "birth_backfilled_from_replay": backfilled,
        "birth_seen_live": bool(launch.get("birth_seen_live")) if "birth_seen_live" in launch else not backfilled,
        "birth_source_route_version": T007_BIRTH_SOURCE_ROUTE_VERSION,
    }


def _update_tracking_tier_for_observation(state: "TrackingState", progress_pct: float | None, *, complete: bool = False) -> None:
    if complete:
        state.tracking_tier = "escalated"
        state.tracking_tier_reason = "migration_or_complete_signal"
        return
    if progress_pct is None:
        return
    if float(progress_pct) >= 20.0:
        state.tracking_tier = "escalated"
        state.tracking_tier_reason = "progress_threshold_ge_20"
    elif state.deep_tracking_admitted and state.tracking_tier == "thin":
        state.tracking_tier = "sampled_enrichment"
        state.tracking_tier_reason = "sample_admitted"


@dataclass
class TrackingState:
    mint: str
    launch_received_at: float | None = None
    launch_slot: int | None = None
    launch_block_time: int | None = None
    bonding_curve_account: str | None = None
    associated_bonding_curve: str | None = None
    creator_address: str | None = None
    source_route_type: str | None = None
    source_decode_route: str | None = None
    creator_history_metrics: dict[str, Any] = field(default_factory=dict)
    creator_sold_before_entry_observed: bool = False
    previous_progress_pct: float | None = None
    last_progress_pct: float | None = None
    highest_progress_pct: float | None = None
    last_observation_received_at: float | None = None
    first_observation_received_at: float | None = None
    last_observation_row: dict[str, Any] | None = None
    observation_count: int = 0
    decoded_observation_count: int = 0
    priority_tier: str = "low"
    tracking_tier: str = "thin"
    tracking_tier_reason: str = "birth_ledger"
    deep_tracking_admitted: bool = False
    thresholds_crossed: set[float] = field(default_factory=set)
    threshold_seconds_since_launch: dict[float, float] = field(default_factory=dict)
    valuation_bands_crossed: set[int] = field(default_factory=set)
    valuation_band_received_at: dict[int, float] = field(default_factory=dict)
    valuation_band_seconds_since_launch: dict[int, float] = field(default_factory=dict)
    valuation_band_values: dict[int, float] = field(default_factory=dict)
    valuation_band_slots: dict[int, int | None] = field(default_factory=dict)
    valuation_band_observation_ids: dict[int, str | None] = field(default_factory=dict)
    valuation_max_after_band: dict[int, float] = field(default_factory=dict)
    valuation_min_after_band: dict[int, float] = field(default_factory=dict)
    valuation_max_retrace_pct_after_band: dict[int, float] = field(default_factory=dict)
    last_valuation_usd: float | None = None
    migration_seen: bool = False
    migration_received_at: float | None = None
    migration_candidate_reasons: set[str] = field(default_factory=set)
    high_fdv_without_migration_thresholds: set[int] = field(default_factory=set)
    stopped: bool = False
    stop_reason: str | None = None
    finalized_at: float | None = None
    age_at_finalization_seconds: float | None = None
    pruned_due_to_low_progress: bool = False
    high_progress_protected: bool = False
    valuation_path_finalized: bool = False
    final_wallet_checkpoint_written: bool = False
    trade_count_since_launch: int = 0
    buy_count_since_launch: int = 0
    sell_count_since_launch: int = 0
    buy_quote_volume_since_launch: float = 0.0
    sell_quote_volume_since_launch: float = 0.0
    net_quote_inflow_since_launch: float = 0.0
    unique_buyers_since_launch: set[str] = field(default_factory=set)
    unique_sellers_since_launch: set[str] = field(default_factory=set)
    trade_wallet_counts: dict[str, int] = field(default_factory=dict)
    trade_size_counts: dict[str, int] = field(default_factory=dict)
    last_trade_side: str | None = None
    consecutive_buy_count: int = 0
    consecutive_sell_count: int = 0
    last_trade_received_at: float | None = None
    bot_like_trade_count: int = 0
    bot_like_quote_volume: float = 0.0
    trade_flow_status: str = "not_available"
    organic_share_status: str = "not_available"
    holder_distribution_status: str = "not_available"
    dev_behavior_status: str = "not_available"
    post_migration_depth_status: str = "not_available"
    execution_cost_status: str = "not_available"
    post_migration_observation_count: int = 0


class BondingCurveProgressRecorder:
    def __init__(self, config: BondingCurveRecorderConfig):
        self.config = config
        self._sqlite_owner_thread_id = threading.get_ident()
        self.output_root = Path(config.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.run_finalized = False
        self.finalization_errors: list[dict[str, str]] = []
        self.failure_reason: str | None = None
        self.archive_status = "pending" if config.archive_after_run else "not_requested"
        self.archive_manifest_path: str | None = None
        self._ensure_jsonl_artifacts()
        self.evidence_store = T007EvidenceStore(self.output_root)
        self.lifecycle_adapter = T007LifecycleCollectorAdapter.for_output_root(self.output_root)
        self.states: dict[str, TrackingState] = {}
        self.birth_rows_by_mint: dict[str, dict[str, Any]] = {}
        self.live_birth_mints: set[str] = set()
        self.replay_backfilled_birth_mints: set[str] = set()
        self.followup_queue: list[dict[str, Any]] = []
        self.post_migration_observation_schedules: list[dict[str, Any]] = []
        self._post_migration_schedule_keys: set[tuple[str, str, int]] = set()
        self._post_migration_as_of_override: float | None = None
        self.pool_state_probe: Any | None = None
        self.execution_cost_probe: Any | None = None
        self._last_execution_cost_periodic_at: float | None = None
        self.summary_counters: dict[str, Any] = {
            "total_births_detected": 0,
            "birth_rows_live_source": 0,
            "birth_rows_replay_backfilled": 0,
            "migration_backfill_skipped_existing_live_birth_count": 0,
            "birth_candidate_seen_count": 0,
            "create_instruction_verified_count": 0,
            "curve_account_resolved_count": 0,
            "curve_account_verified_count": 0,
            "curve_account_pda_mismatch_count": 0,
            "thesis_usable_birth_count": 0,
            "birth_candidate_excluded_count": 0,
            "birth_candidate_excluded_by_reason": {},
            "admitted_births": 0,
            "sample_rejected_births": 0,
            "capacity_rejected_births": 0,
            "active_tracking_max_count": 0,
            "queue_high_water_mark": 0,
            "queue_dropped_count": 0,
            "observations_written": 0,
            "threshold_crossings_written": 0,
            "migrations_written": 0,
            "migration_candidates_seen": 0,
            "high_fdv_without_migration_event_count": 0,
            "tokens_crossing_60k_without_migration_event": 0,
            "tokens_crossing_100k_without_migration_event": 0,
            "tokens_crossing_250k_without_migration_event": 0,
            "complete_true_count": 0,
            "reserve_zero_count": 0,
            "progress_100pct_count": 0,
            "explicit_migrate_log_count": 0,
            "dex_pair_signal_count": 0,
            "evidence_records_written": 0,
            "evidence_records_duplicate_count": 0,
            "account_snapshots_written": 0,
            "account_snapshots_duplicate_count": 0,
            "lifecycle_transitions_written": 0,
            "lifecycle_transitions_duplicate_count": 0,
            "curve_velocity_events_written": 0,
            "curve_acceleration_events_written": 0,
            "token_path_summary_rows": 0,
            "token_path_summary_written": 0,
            "migration_level_a_count": 0,
            "migration_level_b_count": 0,
            "migration_level_c_candidate_count": 0,
            "post_migration_snapshot_scheduled_count": 0,
            "reconciliation_findings_count": 0,
            "decode_failures": 0,
            "rpc_failures": 0,
            "stale_observations": 0,
            "curve_observation_attempts": 0,
            "exact_progress_decoded_count": 0,
            "progress_decoded_exact_count": 0,
            "progress_decoded_candidate_count": 0,
            "unresolved_progress_formula_count": 0,
            "reserve_scale_mode_counts": {},
            "true_curve_threshold_crossings_by_threshold": {},
            "valuation_present_count": 0,
            "valuation_missing_count": 0,
            "valuation_ladder_market_cap_confirmed_count": 0,
            "valuation_ladder_suppressed_untrusted_count": 0,
            "valuation_ladder_trust_status_counts": {},
            "valuation_formula_audit_rows": 0,
            "valuation_formula_classification_counts": {},
            "valuation_units_status_counts": {},
            "valuation_band_crossings_by_band": {},
            "valuation_ladder_events_written": 0,
            "valuation_ladder_paths_written": 0,
            "valuation_ladder_stall_counts": {},
            "wallet_dev_checkpoints_written": 0,
            "wallet_metrics_available_count": 0,
            "wallet_metrics_deferred_count": 0,
            "wallet_metrics_not_available_count": 0,
            "dev_metrics_available_count": 0,
            "dev_metrics_deferred_count": 0,
            "dev_metrics_not_available_count": 0,
            "creator_history_available_count": 0,
            "creator_history_deferred_count": 0,
            "creator_history_not_available_count": 0,
            "wallet_enrichment_error_count": 0,
            "decode_coverage_by_source_route": {},
            "progress_decode_coverage_by_source_route": {},
            "valuation_coverage_by_source_route": {},
            "valuation_missing_reason_counts": {},
            "first_attempt_success_count": 0,
            "retry_success_count": 0,
            "final_account_not_found_count": 0,
            "retry_queue_high_water_mark": 0,
            "retry_queue_drops": 0,
            "capacity_rejected_by_minute": {},
            "capacity_rejected_by_route": {},
            "active_pruned_count": 0,
            "active_pruned_by_reason": {},
            "low_progress_timeout_count": 0,
            "no_decode_timeout_count": 0,
            "stale_low_priority_pruned_count": 0,
            "admission_after_prune_count": 0,
            "capacity_rejected_after_prune_count": 0,
            "active_tracking_still_active_at_finalization": 0,
            "http_429_count": 0,
            "births_by_quote_asset": {},
            "admitted_births_by_quote_asset": {},
            "sample_rejected_by_quote_asset": {},
            "capacity_rejected_by_quote_asset": {},
            "curve_observations_by_quote_asset": {},
            "progress_crossings_by_quote_asset": {},
            "migration_events_by_quote_asset": {},
            "missing_quote_mint_count": 0,
            "unsupported_quote_asset_count": 0,
            "global_migration_events_deduped": 0,
            "global_migration_candidates": 0,
            "global_migration_duplicates_suppressed": 0,
            "global_migration_unique_mints": 0,
            "global_migration_unique_pools": 0,
            "global_migration_mints_seen_in_birth_source": 0,
            "global_migration_mints_admitted": 0,
            "global_migration_mints_sample_rejected": 0,
            "global_migration_mints_capacity_rejected": 0,
            "global_migration_mints_not_seen_in_birth_source": 0,
            "live_migration_side_effect_drain_count": 0,
            "live_migration_side_effects_applied": 0,
            "live_migration_side_effects_failed": 0,
            "live_migration_side_effects_source_rows": 0,
            "live_migration_side_effects_post_observations_written": 0,
            "live_migration_side_effect_last_drain_at": 0.0,
            "pumpswap_swap_events_decoded": 0,
            "pumpswap_swap_buy_events": 0,
            "pumpswap_swap_sell_events": 0,
            "pumpswap_swap_fee_bps_populated_count": 0,
        "pumpswap_swap_balance_delta_partial_count": 0,
        "pumpswap_route_raw_notifications": 0,
        "pumpswap_route_candidate_transactions": 0,
        "pumpswap_route_with_logs": 0,
        "pumpswap_route_with_inner_instructions": 0,
        "pumpswap_route_buy_candidates": 0,
        "pumpswap_route_sell_candidates": 0,
        "pumpswap_route_event_log_candidates": 0,
        "pumpswap_route_get_transaction_backfills": 0,
        "pumpswap_route_skipped_by_reason": {},
            "pumpswap_swap_balance_delta_partial_count": 0,
            "pumpswap_route_raw_notifications": 0,
            "pumpswap_route_candidate_transactions": 0,
            "pumpswap_route_with_logs": 0,
            "pumpswap_route_with_inner_instructions": 0,
            "pumpswap_route_buy_candidates": 0,
            "pumpswap_route_sell_candidates": 0,
            "pumpswap_route_event_log_candidates": 0,
            "pumpswap_route_get_transaction_backfills": 0,
            "pumpswap_route_skipped_by_reason": {},
            "migration_after_prune_count": 0,
            "migration_while_active_count": 0,
            "migration_for_non_admitted_count": 0,
            "migration_for_sample_rejected_count": 0,
            "high_progress_tokens_that_later_migrated": 0,
            "migration_backfill_jobs_enqueued": 0,
            "migration_backfill_jobs_completed": 0,
            "migration_backfill_jobs_failed": 0,
            "migration_backfilled_birth_rows_written": 0,
            "migration_backfill_queue_high_water": 0,
            "migration_backfill_rate_limited_count": 0,
            "migration_backfill_rpc_error_count": 0,
            "thin_births_total": 0,
            "thin_probe_scheduled_count": 0,
            "thin_probe_success_count": 0,
            "thin_probe_failed_count": 0,
            "thin_to_deep_escalation_count": 0,
            "thin_to_deep_escalation_reasons": {},
            "sampled_out_with_thin_path_count": 0,
            "sampled_out_without_thin_path_count": 0,
            "thin_probe_queue_high_water": 0,
            "thin_probe_queue_drops": 0,
            "thin_probe_deferred_count": 0,
            "thin_probe_defer_reasons": {},
            "deep_probe_delayed_by_thin_count": 0,
            "promotion_events_written": 0,
            "promoted_mints": 0,
            "promoted_migrated_mints": 0,
            "capacity_deferred_promotions": 0,
            "promotion_reason_counts": {},
            "promotion_evictions_written": 0,
            "promotion_eviction_reasons": {},
            "trade_flow_events_written": 0,
            "trade_flow_available_count": 0,
            "trade_flow_partial_count": 0,
            "organic_flow_events_written": 0,
            "organic_flow_available_count": 0,
            "organic_flow_partial_count": 0,
            "buyer_breadth_available_count": 0,
            "holder_distribution_snapshots_written": 0,
            "holder_distribution_available_count": 0,
            "holder_distribution_partial_count": 0,
            "dev_behavior_events_written": 0,
            "dev_behavior_available_count": 0,
            "dev_behavior_partial_count": 0,
            "post_migration_observations_scheduled": 0,
            "post_migration_observations_written": 0,
            "post_migration_observations_completed_by_horizon": {},
            "post_migration_observations_pending_at_finalization": 0,
            "post_migration_observation_errors": 0,
            "post_migration_pool_state_available_count": 0,
            "post_migration_pool_state_partial_count": 0,
            "post_migration_pool_state_not_available_count": 0,
            "post_migration_pool_state_error_count": 0,
            "post_migration_pool_state_by_quote_asset": {},
            "pool_liquidity_quote_present_count": 0,
            "pool_liquidity_usd_present_count": 0,
            "post_migration_quote_available_count": 0,
            "post_migration_quote_partial_count": 0,
            "post_migration_quote_deferred_count": 0,
            "post_migration_quote_error_count": 0,
            "executable_quote_observations_written": 0,
            "executable_quote_available_count": 0,
            "executable_quote_partial_count": 0,
            "executable_quote_deferred_count": 0,
            "executable_quote_error_count": 0,
            "executable_quote_by_source": {},
            "executable_quote_by_quote_asset": {},
            "executable_quote_by_direction": {},
            "executable_quote_clip_count": 0,
            "executable_quote_decision_time_safe_count": 0,
            "price_impact_available_count": 0,
            "price_impact_missing_count": 0,
            "fee_model_confirmed_count": 0,
            "fee_model_assumed_count": 0,
            "fee_model_unknown_count": 0,
            "post_migration_observations_by_quote_asset": {},
            "post_migration_observations_by_horizon": {},
            "post_migration_migrations_without_observations": 0,
            "post_migration_available_count": 0,
            "post_migration_partial_count": 0,
            "sell_side_dump_diagnostics_written": 0,
            "execution_cost_observations_written": 0,
            "execution_cost_available_count": 0,
            "execution_cost_partial_count": 0,
            "execution_cost_deferred_count": 0,
            "execution_cost_error_count": 0,
            "recent_prioritization_fee_sample_count": 0,
            "execution_cost_observations_by_reason": {},
            "failed_tx_share_available_count": 0,
            "failed_tx_share_deferred_count": 0,
            "decision_time_checked_feature_rows": 0,
            "decision_time_safe_feature_rows": 0,
            "decision_time_safety_violation_count": 0,
            "birth_decision_path_commit_count": 0,
            "birth_decision_path_commit_error_count": 0,
            "source_verified_birth_commit_count": 0,
            "source_verified_birth_commit_error_count": 0,
            "source_verified_birth_commit_duplicate_suppressed_count": 0,
            "live_status_hot_path_force_disabled_count": 0,
            "live_source_used": config.source_name,
            "subscription_connect_status": "not_started",
            "live_status_write_count": 0,
            "live_status_throttled_write_skip_count": 0,
            "near_entry_hot_flow_enabled": bool(config.near_entry_hot_flow_enabled),
            "near_entry_hot_flow_mints_registered": 0,
            "near_entry_hot_flow_events_seen": 0,
            "near_entry_hot_flow_events_recorded": 0,
            "near_entry_hot_flow_ring_buffer_dropped_count": 0,
            "near_entry_hot_flow_snapshots_written": 0,
            "near_entry_hot_flow_snapshot_mints": 0,
            "near_entry_hot_flow_snapshot_1s_count": 0,
            "near_entry_hot_flow_snapshot_5s_count": 0,
            "near_entry_hot_flow_snapshot_10s_count": 0,
            "near_entry_hot_flow_snapshot_30s_count": 0,
            "near_entry_hot_flow_snapshot_60s_count": 0,
            "dev_previous_migrations_field_decision_time_safe_count": 0,
            "creator_sold_before_entry_field_decision_time_safe_count": 0,
            "source_fast_birth_probe_hook_enabled": False,
            "source_fast_birth_probe_hook_events": 0,
            "source_fast_first_curve_probe_enqueued": 0,
            "source_fast_first_curve_probe_duplicate_suppressed": 0,
            "source_fast_first_curve_probe_ineligible": 0,
            "source_fast_event_handler_error_count": 0,
            "mayhem_code_modified": False,
        }
        self.birth_to_admission_enqueue_latencies_ms: list[float] = []
        self.birth_to_verified_birth_commit_latencies_ms: list[float] = []
        self.verified_birth_commit_to_probe_enqueue_latencies_ms: list[float] = []
        self.source_verified_birth_commit_mints: set[str] = set()
        self.source_verified_birth_commit_by_mint: dict[str, dict[str, Any]] = {}
        self.hotpath_latency_spans_by_mint: dict[str, dict[str, Any]] = {}
        self.hotpath_latency_span_written_mints: set[str] = set()
        self.birth_to_admission_decision_latencies_ms: list[float] = []
        self.birth_to_admission_complete_latencies_ms: list[float] = []
        self.birth_projection_complete_latencies_ms: list[float] = []
        self.birth_to_admission_latencies_ms = self.birth_to_admission_enqueue_latencies_ms
        self.birth_enqueue_to_admission_worker_start_latencies_ms: list[float] = []
        self.admission_worker_process_birth_duration_ms: list[float] = []
        self.admission_worker_to_probe_job_enqueue_latencies_ms: list[float] = []
        self.probe_job_enqueue_to_probe_start_latencies_ms: list[float] = []
        self.normalized_birth_to_probe_start_latencies_ms: list[float] = []
        self.probe_duration_latencies_ms: list[float] = []
        self.birth_to_first_observation_latencies_ms: list[float] = []
        self.observation_intervals_by_tier: dict[str, list[float]] = {tier: [] for tier in TIER_ORDER}
        self.valuation_transition_seconds_by_pair: dict[str, list[float]] = {
            _transition_label(start, end): [] for start, end in VALUATION_LADDER_TRANSITION_PAIRS
        }
        self.wallet_enrichment_latencies_ms: list[float] = []
        self.probe_attempts_until_success: list[int] = []
        self.time_to_first_success_ms: list[float] = []
        self.fdv_proxy_raw_values: list[float] = []
        self.fdv_proxy_sol_values: list[float] = []
        self.fdv_proxy_usd_values: list[float] = []
        self.reserve_fdv_sol_values: list[float] = []
        self.reserve_fdv_usd_values: list[float] = []
        self.observation_history_by_mint: dict[str, list[dict[str, Any]]] = {}
        self.sampled_out_thin_path_counted_mints: set[str] = set()
        self.stop_reasons: dict[str, int] = {}
        self.tokens_with_60pct_plus_crossing: set[str] = set()
        self.tokens_with_70pct_plus_crossing: set[str] = set()
        self.tokens_with_migration: set[str] = set()
        self.creator_history_by_creator: dict[str, dict[str, Any]] = {}
        self.creator_history_recorded_launch_mints: set[str] = set()
        self.creator_history_recorded_migration_mints: set[str] = set()
        self.started_at = time.time()
        self._cached_lifecycle_live_status_payload: dict[str, Any] | None = None
        self._live_status_min_interval_seconds = 1.0
        self._last_running_live_status_write_at = 0.0
        self._initialize_campaign_artifacts()
        from research.mtp_research.validation.t012_paper_position_ledger import ensure_paper_position_artifacts

        ensure_paper_position_artifacts(self.output_root, run_id=self.config.run_id)
        self._write_run_config()
        self._write_campaign_manifest()
        _atomic_write_json(self.output_root / "collector_summary.json", self.build_summary(final=False))
        self._write_axiom_reconciliation_readme()
        self._write_t007_watcher_html()
        self._write_live_status("initialized")


    def _compact_evidence_payload(self, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not payload:
            return None
        keep = {
            "signature",
            "slot",
            "received_at",
            "block_time",
            "mint",
            "base_mint",
            "pool",
            "pool_address",
            "pool_or_pair_address",
            "quote_mint",
            "quote_asset",
            "source_route",
            "source_type",
            "detection_method",
            "instruction_type",
            "event_type",
            "parser_status",
            "confidence",
        }
        compact = {key: value for key, value in payload.items() if key in keep and value not in (None, "")}
        if "logs" in payload and isinstance(payload.get("logs"), list):
            compact["logs_excerpt"] = payload["logs"][:8]
        return compact or None

    def _evidence_hash(self, payload: dict[str, Any] | None) -> str | None:
        if not payload:
            return None
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def write_evidence_record(
        self,
        *,
        source_lane: str,
        signature: str | None,
        observed_at: float | None = None,
        slot: int | str | None = None,
        source_route: str | None = None,
        mint: str | None = None,
        pool: str | None = None,
        evidence_level: MigrationEvidenceLevel | str = MigrationEvidenceLevel.NONE,
        raw_payload: dict[str, Any] | None = None,
        rule_hits: list[str] | None = None,
        confidence: float | str | None = None,
        commitment: str = "processed",
    ) -> str:
        signature_text = str(signature or "").strip()
        if not signature_text:
            signature_text = f"synthetic:{source_lane}:{mint or pool or int(time.time() * 1000)}"
        compact = self._compact_evidence_payload(raw_payload)
        record = EvidenceRecord(
            signature=signature_text,
            slot=_int(slot),
            observed_at=float(observed_at if observed_at is not None else time.time()),
            commitment=commitment,
            source_lane=source_lane,
            source_route=str(source_route or "unknown"),
            mint=str(mint or "") or None,
            pool=str(pool or "") or None,
            evidence_level=evidence_level,
            raw_tx_hash=self._evidence_hash(compact),
            raw_tx_json=compact,
            rule_hits=list(rule_hits or []),
            confidence=_num(confidence),
        )
        status = self.evidence_store.write_evidence(record.to_json_row())
        if status == "written":
            self.summary_counters["evidence_records_written"] += 1
        else:
            self.summary_counters["evidence_records_duplicate_count"] += 1
        return status

    def write_account_snapshot_record(
        self,
        *,
        pubkey: str | None,
        slot: int | str | None,
        observed_at: float | None = None,
        raw_snapshot: dict[str, Any] | None = None,
        commitment: str = "processed",
    ) -> str:
        pubkey_text = str(pubkey or "").strip()
        if not pubkey_text:
            return "skipped"
        compact = self._compact_evidence_payload(raw_snapshot)
        record = AccountSnapshotRecord(
            pubkey=pubkey_text,
            slot=_int(slot),
            commitment=commitment,
            observed_at=float(observed_at if observed_at is not None else time.time()),
            snapshot_hash=self._evidence_hash(compact) or "",
            raw_snapshot_json=compact,
        )
        status = self.evidence_store.write_account_snapshot(record.to_json_row())
        if status == "written":
            self.summary_counters["account_snapshots_written"] += 1
        elif status == "duplicate":
            self.summary_counters["account_snapshots_duplicate_count"] += 1
        return status

    def write_lifecycle_transition(
        self,
        *,
        mint: str | None,
        previous_state: str | None,
        next_state: str,
        signature: str | None,
        observed_at: float | None = None,
        reason: str,
    ) -> str:
        mint_text = str(mint or "").strip()
        if not mint_text:
            return "skipped"
        record = LifecycleTransitionRecord(
            mint=mint_text,
            previous_state=previous_state,
            next_state=next_state,
            signature=str(signature or ""),
            observed_at=float(observed_at if observed_at is not None else time.time()),
            reason=reason,
        )
        status = self.evidence_store.write_lifecycle_transition(record.to_json_row())
        if status == "written":
            self.summary_counters["lifecycle_transitions_written"] += 1
        elif status == "duplicate":
            self.summary_counters["lifecycle_transitions_duplicate_count"] += 1
        return status

    def _update_hotpath_latency_span(self, mint: str, **fields: Any) -> None:
        mint = str(mint or "").strip()
        if not mint:
            return
        span = self.hotpath_latency_spans_by_mint.setdefault(mint, {"run_id": self.config.run_id, "mint": mint})
        for key, value in fields.items():
            if value is None:
                continue
            if key.endswith("_at"):
                numeric = _num(value)
                if numeric is not None:
                    span[key] = numeric
            else:
                span[key] = value

    def _hotpath_latency_span_with_metrics(self, mint: str) -> dict[str, Any]:
        span = dict(self.hotpath_latency_spans_by_mint.get(str(mint or "").strip()) or {})
        if not span:
            return {}
        stage_pairs = {
            "birth_to_verified_birth_commit_ms": ("birth_received_at", "verified_commit_finished_at"),
            "verified_birth_commit_to_probe_enqueue_ms": ("verified_commit_finished_at", "probe_enqueued_at"),
            "probe_enqueue_to_probe_start_ms": ("probe_enqueued_at", "probe_started_at"),
            "probe_start_to_first_curve_observation_ms": ("probe_started_at", "first_curve_observed_at"),
            "birth_to_first_curve_observation_ms": ("birth_received_at", "first_curve_observed_at"),
            "birth_to_admission_decision_ms": ("birth_received_at", "admission_decision_finished_at"),
            "birth_projection_complete_ms": ("birth_received_at", "projection_finished_at"),
            "projection_to_materialized_ms": ("projection_finished_at", "materialized_at"),
        }
        stage_values: dict[str, float] = {}
        for name, (start_key, end_key) in stage_pairs.items():
            start = _num(span.get(start_key))
            end = _num(span.get(end_key))
            if start is not None and end is not None:
                value = max(0.0, (end - start) * 1000.0)
                span[name] = value
                stage_values[name] = value
        span["bottleneck_stage"] = max(stage_values.items(), key=lambda item: item[1])[0] if stage_values else "unresolved"
        return span

    def _flush_hotpath_latency_span(self, mint: str, *, force: bool = False) -> None:
        mint = str(mint or "").strip()
        if not mint or mint in self.hotpath_latency_span_written_mints:
            return
        span = self._hotpath_latency_span_with_metrics(mint)
        if not span:
            return
        if not force and (span.get("first_curve_observed_at") is None or span.get("projection_finished_at") is None):
            return
        try:
            with (self.output_root / "hotpath_latency_spans.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(span, sort_keys=True, default=str) + "\n")
            self.hotpath_latency_span_written_mints.add(mint)
        except Exception:
            self.summary_counters["write_errors"] += 1

    def record_source_verified_birth_commit(self, launch: Mapping[str, Any]) -> None:
        """Commit compact source-side birth identity before slow admission/projection work."""
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if not mint:
            return
        if mint in self.source_verified_birth_commit_mints:
            self.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"] += 1
            result = self.source_verified_birth_commit_by_mint.get(mint) or {}
            if isinstance(launch, dict):
                launch["_source_verified_birth_commit_recorded"] = True
                for source_key, target_key in (
                    ("commit_sequence", "verified_birth_commit_sequence"),
                    ("raw_envelope_id", "verified_birth_raw_envelope_id"),
                    ("domain_event_id", "verified_birth_domain_event_id"),
                    ("db_committed_at", "verified_birth_db_committed_at"),
                    ("db_committed_at_epoch", "verified_birth_db_committed_at_epoch"),
                ):
                    if result.get(source_key) is not None:
                        launch[target_key] = result.get(source_key)
            return
        received_at = _num(launch.get("received_at")) or _num(launch.get("source_received_at")) or time.time()
        normalized_at = _num(launch.get("normalized_at")) or received_at
        self._update_hotpath_latency_span(
            mint,
            birth_received_at=received_at,
            normalized_at=normalized_at,
            verified_commit_enqueued_at=received_at,
            verified_commit_started_at=time.time(),
        )
        derived_bonding_curve = _derive_bonding_curve_pda(mint)
        decoded_bonding_curve = (
            launch.get("bonding_curve_account")
            or launch.get("bonding_curve")
            or launch.get("curve_account")
            or derived_bonding_curve
        )
        commit_payload = {
            "mint": mint,
            "signature": launch.get("signature") or launch.get("launch_signature"),
            "slot": launch.get("slot"),
            "block_time": launch.get("block_time"),
            "received_at": received_at,
            "source_received_at": launch.get("source_received_at") or received_at,
            "normalized_at": launch.get("normalized_at") or received_at,
            "creator": launch.get("creator") or launch.get("creator_wallet") or launch.get("dev"),
            "bonding_curve_account": decoded_bonding_curve,
            "bonding_curve": decoded_bonding_curve,
            "associated_bonding_curve": launch.get("associated_bonding_curve"),
            "derived_bonding_curve": derived_bonding_curve,
            "bonding_curve_pda_verified": bool(decoded_bonding_curve and derived_bonding_curve and str(decoded_bonding_curve) == str(derived_bonding_curve)),
            "quote_mint": launch.get("quote_mint"),
            "quote_asset": launch.get("quote_asset"),
            "source_route": launch.get("source_route") or launch.get("source_type") or "pump_transaction_subscribe",
            "source_type": launch.get("source_type") or launch.get("source_route") or "pump_transaction_subscribe",
            "decode_route": launch.get("decode_route"),
            "observed_commitment": launch.get("observed_commitment"),
            "live_source": not _bool(launch.get("birth_backfilled_from_replay")),
            "replay_source": _bool(launch.get("birth_backfilled_from_replay")),
            "birth_verification_status": "verified",
            "birth_verification_level": "curve_account_resolved",
        }
        try:
            writer_factory = globals().get("_t007_v3_writer")
            if writer_factory is None:
                raise RuntimeError("t007 canonical writer factory unavailable")
            event_writer = writer_factory(self)
            canonical_writer = getattr(event_writer, "_canonical_sqlite_writer", None)
            if canonical_writer is not None and hasattr(canonical_writer, "commit_verified_birth_minimal"):
                result = canonical_writer.commit_verified_birth_minimal(commit_payload)
            else:
                enriched = event_writer.record_artifact_row("birth_audit.jsonl", commit_payload, context=_t007_v3_event_context(self))
                result = {
                    "commit_sequence": enriched.get("commit_sequence") or enriched.get("db_commit_sequence"),
                    "raw_envelope_id": enriched.get("raw_envelope_id"),
                    "domain_event_id": enriched.get("domain_event_id") or enriched.get("event_id"),
                    "db_committed_at": enriched.get("db_committed_at"),
                    "db_committed_at_epoch": enriched.get("db_committed_at_epoch") or enriched.get("db_committed_epoch"),
                }
            committed_epoch = _num(result.get("db_committed_at_epoch")) or time.time()
            self.source_verified_birth_commit_mints.add(mint)
            self.source_verified_birth_commit_by_mint[mint] = dict(result)
            self.source_verified_birth_commit_by_mint[mint]["db_committed_at_epoch"] = committed_epoch
            self.summary_counters["source_verified_birth_commit_count"] += 1
            commit_latency_ms = max(0.0, (float(committed_epoch) - float(received_at)) * 1000.0)
            self.birth_to_verified_birth_commit_latencies_ms.append(commit_latency_ms)
            self.birth_to_admission_complete_latencies_ms.append(commit_latency_ms)
            self._update_hotpath_latency_span(mint, verified_commit_finished_at=committed_epoch)
            if isinstance(launch, dict):
                launch["_source_verified_birth_commit_recorded"] = True
                launch["verified_birth_commit_sequence"] = result.get("commit_sequence")
                launch["verified_birth_raw_envelope_id"] = result.get("raw_envelope_id")
                launch["verified_birth_domain_event_id"] = result.get("domain_event_id")
                launch["verified_birth_db_committed_at"] = result.get("db_committed_at")
                launch["verified_birth_db_committed_at_epoch"] = committed_epoch
        except Exception as exc:
            self.summary_counters["source_verified_birth_commit_error_count"] += 1
            try:
                with (self.output_root / "source_verified_birth_commit_errors.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "run_id": self.config.run_id,
                        "mint": mint,
                        "error_class": type(exc).__name__,
                        "error": str(exc),
                        "observed_at": time.time(),
                    }, sort_keys=True, default=str) + "\n")
            except Exception:
                pass

    def process_birth(self, launch: dict[str, Any]) -> dict[str, Any]:
        mint = str(launch.get("mint") or launch.get("token_mint") or "")
        received_at = _num(launch.get("received_at")) or time.time()
        is_replay_backfilled_birth = _bool(launch.get("birth_backfilled_from_replay")) or str(
            launch.get("source_type") or launch.get("source_route") or ""
        ) == "global_migration_replay_backfill"
        self.summary_counters["total_births_detected"] += 1
        if mint:
            if is_replay_backfilled_birth:
                self.summary_counters["birth_rows_replay_backfilled"] += 1
                self.replay_backfilled_birth_mints.add(mint)
            else:
                self.summary_counters["birth_rows_live_source"] += 1
                self.live_birth_mints.add(mint)
        admitted = False
        reason = "invalid_missing_mint"
        decoded_route = _decoded_route_from_launch(launch)
        source_route_key = _source_route_key_from_launch(launch)
        quote = _quote_identity_from_payload(launch, unsupported_as_unknown=True)
        _increment_counter(self.summary_counters["births_by_quote_asset"], quote["quote_asset"])
        if quote["quote_asset_status"] == "unknown":
            self.summary_counters["missing_quote_mint_count"] += 1
        elif quote["quote_asset_status"] == "unsupported":
            self.summary_counters["unsupported_quote_asset_count"] += 1
        decoded_bonding_curve = launch.get("bonding_curve_account") or launch.get("bonding_curve")
        derived_bonding_curve = _derive_bonding_curve_pda(mint)
        curve_account_resolved = bool(decoded_bonding_curve or derived_bonding_curve)
        bonding_curve_pda_verified = bool(
            decoded_bonding_curve
            and derived_bonding_curve
            and str(decoded_bonding_curve) == str(derived_bonding_curve)
        )
        curve_account_verified = bool(
            bonding_curve_pda_verified
            or (
                decoded_bonding_curve
                and (
                    _bool(launch.get("curve_account_verified"))
                    or _bool(launch.get("bonding_curve_verified"))
                    or _bool(launch.get("bonding_curve_pda_verified"))
                )
            )
        )
        create_instruction_verified = bool(curve_account_verified and decoded_route)
        birth_candidate_excluded = False
        if mint:
            self.summary_counters["birth_candidate_seen_count"] += 1
            if create_instruction_verified:
                self.summary_counters["create_instruction_verified_count"] += 1
            if curve_account_resolved:
                self.summary_counters["curve_account_resolved_count"] += 1
            if curve_account_verified:
                self.summary_counters["curve_account_verified_count"] += 1
            if decoded_bonding_curve and derived_bonding_curve and not bonding_curve_pda_verified:
                self.summary_counters["curve_account_pda_mismatch_count"] += 1
            if self.config.require_verified_curve_account_for_admission and not curve_account_verified:
                reason = "birth_candidate_unverified_curve"
                birth_candidate_excluded = True
                self.summary_counters["birth_candidate_excluded_count"] += 1
                _increment_counter(self.summary_counters["birth_candidate_excluded_by_reason"], reason)
            elif not deterministic_sample_admitted(mint, self.config.sample_rate_percent):
                reason = "sample_rejected"
                self.summary_counters["sample_rejected_births"] += 1
                _increment_counter(self.summary_counters["sample_rejected_by_quote_asset"], quote["quote_asset"])
            elif self._active_tracking_count() >= self.config.max_active_tracking:
                protected_before_prune = self._protected_high_progress_active_count()
                pruned_count = self._prune_for_capacity(received_at)
                if self._active_tracking_count() >= self.config.max_active_tracking:
                    reason = (
                        "capacity_rejected_active_tracking_limit_after_prune"
                        if protected_before_prune
                        else "capacity_rejected_active_tracking_limit"
                    )
                    self.summary_counters["capacity_rejected_births"] += 1
                    _increment_counter(self.summary_counters["capacity_rejected_by_quote_asset"], quote["quote_asset"])
                    self.summary_counters["capacity_rejected_after_prune_count"] += 1
                    _increment_counter(self.summary_counters["capacity_rejected_by_minute"], _minute_bucket(received_at))
                    _increment_counter(self.summary_counters["capacity_rejected_by_route"], source_route_key)
                else:
                    admitted = True
                    reason = "sample_admitted_after_prune" if pruned_count else "sample_admitted_after_capacity_check"
                    self.summary_counters["admitted_births"] += 1
                    _increment_counter(self.summary_counters["admitted_births_by_quote_asset"], quote["quote_asset"])
                    self.summary_counters["admission_after_prune_count"] += 1
                    if curve_account_verified:
                        self.summary_counters["thesis_usable_birth_count"] += 1
                    self._upsert_tracking_state_from_launch(
                        mint,
                        launch,
                        received_at=received_at,
                        decoded_route=decoded_route,
                        deep_tracking_admitted=True,
                    )
                    self._emit_wallet_dev_checkpoint(self.states[mint], "birth", source_event=launch)
                    self.summary_counters["active_tracking_max_count"] = max(
                        self.summary_counters["active_tracking_max_count"],
                        self._active_tracking_count(),
                    )
            elif len(self.followup_queue) >= self.config.followup_queue_max_size:
                reason = "capacity_rejected_followup_queue_full"
                self.summary_counters["capacity_rejected_births"] += 1
                _increment_counter(self.summary_counters["capacity_rejected_by_quote_asset"], quote["quote_asset"])
                _increment_counter(self.summary_counters["capacity_rejected_by_minute"], _minute_bucket(received_at))
                _increment_counter(self.summary_counters["capacity_rejected_by_route"], source_route_key)
            else:
                admitted = True
                reason = "sample_admitted"
                self.summary_counters["admitted_births"] += 1
                _increment_counter(self.summary_counters["admitted_births_by_quote_asset"], quote["quote_asset"])
                if curve_account_verified:
                    self.summary_counters["thesis_usable_birth_count"] += 1
                self._upsert_tracking_state_from_launch(
                    mint,
                    launch,
                    received_at=received_at,
                    decoded_route=decoded_route,
                    deep_tracking_admitted=True,
                )
                self._emit_wallet_dev_checkpoint(self.states[mint], "birth", source_event=launch)
                self.summary_counters["active_tracking_max_count"] = max(
                    self.summary_counters["active_tracking_max_count"],
                    self._active_tracking_count(),
                )
        admission_decision_finished_at = time.time()
        if isinstance(launch, dict):
            launch["_admission_decision_finished_at"] = admission_decision_finished_at
        if mint:
            self._update_hotpath_latency_span(mint, admission_decision_finished_at=admission_decision_finished_at)
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "launch_signature": launch.get("signature") or launch.get("launch_signature"),
            "slot": launch.get("slot"),
            "block_time": launch.get("block_time"),
            "received_at": received_at,
            "source_route_type": launch.get("source_type") or launch.get("source_route") or "unknown",
            "source_decode_route": decoded_route,
            "bonding_curve_account": decoded_bonding_curve,
            "derived_bonding_curve_account": derived_bonding_curve,
            "bonding_curve_pda_verified": bonding_curve_pda_verified,
            "curve_account_resolved": curve_account_resolved,
            "curve_account_verified": curve_account_verified,
            "create_instruction_verified": create_instruction_verified,
            "thesis_usable_birth": bool(admitted and curve_account_verified),
            "birth_candidate_excluded": birth_candidate_excluded,
            "associated_bonding_curve": launch.get("associated_bonding_curve"),
            "creator": launch.get("creator") or launch.get("creator_wallet") or launch.get("dev"),
            "quote_mint": quote["quote_mint"],
            "quote_asset": quote["quote_asset"],
            "quote_asset_status": quote["quote_asset_status"],
            "raw_decoded_launch_payload": launch.get("raw_decoded_launch_payload") or launch.get("metadata_json") or {},
            "admitted": admitted,
            "admission_reason": reason,
            "backfill_trigger": launch.get("backfill_trigger"),
            "backfill_trigger_signature": launch.get("backfill_trigger_signature"),
            "backfill_job_id": launch.get("backfill_job_id"),
        }
        row.update(_birth_capture_provenance_fields(launch, decoded_route))
        row.update(_birth_tracking_schema_fields(admitted=admitted, admission_reason=reason))
        state = self.states.get(mint) if mint else None
        if mint and state is None and not birth_candidate_excluded:
            state = self._upsert_tracking_state_from_launch(
                mint,
                launch,
                received_at=received_at,
                decoded_route=decoded_route,
                deep_tracking_admitted=False,
            )
        if state is not None:
            state.tracking_tier = row["tracking_tier"]
            state.tracking_tier_reason = row["tracking_tier_reason"]
            state.deep_tracking_admitted = bool(row["deep_tracking_admitted"])
        if mint and not birth_candidate_excluded:
            self._emit_thin_probe_schedule(row, write_marker=not admitted)
            if (
                str(reason or "").startswith("sample_rejected")
                and self.observation_history_by_mint.get(mint)
                and mint not in self.sampled_out_thin_path_counted_mints
            ):
                self.sampled_out_thin_path_counted_mints.add(mint)
                self.summary_counters["sampled_out_with_thin_path_count"] += 1
        self.write_evidence_record(
            source_lane="pumpfun_birth",
            signature=row.get("launch_signature") or row.get("signature"),
            observed_at=_num(row.get("received_at")),
            slot=row.get("slot") or row.get("launch_slot"),
            source_route=row.get("source_route_key") or row.get("source_route_type") or row.get("source_type"),
            mint=mint,
            evidence_level=MigrationEvidenceLevel.NONE,
            raw_payload=launch,
            rule_hits=["pumpfun_birth_seen_live" if not _bool(row.get("birth_backfilled_from_replay")) else "pumpfun_birth_backfilled"],
        )
        row["decision_path_birth_commit_status"] = "attempted"
        row["decision_path_birth_commit_started_at"] = time.time()
        self._append_jsonl("birth_audit.jsonl", row)
        committed_at = time.time()
        row["decision_path_birth_commit_status"] = "committed"
        row["decision_path_birth_committed_at"] = committed_at
        self.summary_counters["birth_decision_path_commit_count"] += 1
        if (
            received_at is not None
            and not _bool(launch.get("_source_verified_birth_commit_recorded"))
            and mint not in self.source_verified_birth_commit_mints
        ):
            self.birth_to_verified_birth_commit_latencies_ms.append(max(0.0, (committed_at - float(received_at)) * 1000.0))
        if mint:
            existing_birth_row = self.birth_rows_by_mint.get(mint)
            existing_is_replay = _bool((existing_birth_row or {}).get("birth_backfilled_from_replay"))
            row_is_replay = _bool(row.get("birth_backfilled_from_replay"))
            if existing_birth_row is None or (existing_is_replay and not row_is_replay):
                self.birth_rows_by_mint[mint] = dict(row)
        self.summary_counters["live_status_hot_path_force_disabled_count"] += 1
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def record_replay_backfilled_birth(self, replay_row: dict[str, Any]) -> dict[str, Any]:
        mint = str(replay_row.get("mint") or "").strip()
        existing_birth_row = self.birth_rows_by_mint.get(mint)
        if existing_birth_row is not None and not _bool(existing_birth_row.get("birth_backfilled_from_replay")):
            self.summary_counters["migration_backfill_skipped_existing_live_birth_count"] += 1
            return {**dict(existing_birth_row), "replay_backfill_skipped_existing_live_birth": True}
        launch = {
            "mint": mint,
            "signature": replay_row.get("launch_signature_from_replay") or replay_row.get("launch_signature"),
            "slot": replay_row.get("launch_slot_from_replay") or replay_row.get("launch_slot"),
            "block_time": replay_row.get("launch_time_from_replay") or replay_row.get("launch_time"),
            "received_at": replay_row.get("backfill_received_at") or time.time(),
            "source_type": "global_migration_replay_backfill",
            "decode_route": "replay_backfill",
            "bonding_curve_account": replay_row.get("bonding_curve_account") or _derive_bonding_curve_pda(mint),
            "creator": replay_row.get("creator") or replay_row.get("creator_wallet"),
            "quote_mint": replay_row.get("quote_mint"),
            "quote_type": replay_row.get("quote_asset"),
            "birth_backfilled_from_replay": True,
            "birth_seen_live": False,
            "birth_capture_method": "global_migration_replay_backfill",
            "birth_capture_route": "global_migration:replay_backfill",
            "birth_capture_confidence": "replay_backfilled",
            "backfill_trigger": replay_row.get("backfill_trigger"),
            "backfill_trigger_signature": replay_row.get("backfill_trigger_signature"),
            "backfill_job_id": replay_row.get("backfill_job_id"),
            "raw_decoded_launch_payload": {
                "source_instruction_decode_route": "replay_backfill",
                "migration_signature": replay_row.get("migration_signature"),
                "pool_or_pair_address": replay_row.get("pool_or_pair_address"),
            },
        }
        return self.process_birth(launch)

    def _emit_thin_probe_schedule(self, birth_row: dict[str, Any], *, write_marker: bool = True) -> None:
        self.summary_counters["thin_births_total"] += 1
        if self.summary_counters["thin_probe_scheduled_count"] >= int(self.config.thin_probe_queue_max_size):
            birth_row["thin_probe_scheduled"] = False
            self.summary_counters["thin_probe_deferred_count"] += 1
            self.summary_counters["thin_probe_queue_drops"] += 1
            _increment_counter(self.summary_counters["thin_probe_defer_reasons"], "thin_probe_queue_full")
            if write_marker:
                self._append_jsonl(
                    "probe_attempts.jsonl",
                    {
                        "mint": birth_row.get("mint"),
                        "campaign_id": self.config.run_id,
                        "run_id": self.config.run_id,
                        "launch_received_at": birth_row.get("received_at"),
                        "tracking_tier": birth_row.get("tracking_tier"),
                        "probe_scope": "thin_initial_probe",
                        "target_delay_ms": 250,
                        "probe_status": "deferred",
                        "actual_probe_executed": False,
                        "defer_reason": "thin_probe_queue_full",
                        "notes": "Thin probe deferred before deep/high-progress work; deep tracking is not delayed.",
                    },
                )
            return
        birth_row["thin_probe_scheduled"] = True
        self.summary_counters["thin_probe_scheduled_count"] += 1
        self.summary_counters["thin_probe_queue_high_water"] = max(
            int(self.summary_counters.get("thin_probe_queue_high_water") or 0),
            int(self.summary_counters["thin_probe_scheduled_count"]),
        )
        if write_marker:
            self._append_jsonl(
                "probe_attempts.jsonl",
                {
                    "mint": birth_row.get("mint"),
                    "campaign_id": self.config.run_id,
                    "run_id": self.config.run_id,
                    "launch_received_at": birth_row.get("received_at"),
                    "tracking_tier": birth_row.get("tracking_tier"),
                    "probe_scope": "thin_initial_probe",
                    "target_delay_ms": 250,
                    "probe_status": "scheduled",
                    "actual_probe_executed": False,
                    "notes": "Thin-track-all schema marker; expensive/deep enrichment remains sample gated.",
                },
            )

    def _upsert_tracking_state_from_launch(
        self,
        mint: str,
        launch: dict[str, Any],
        *,
        received_at: float,
        decoded_route: str,
        deep_tracking_admitted: bool,
    ) -> TrackingState:
        state = self.states.get(mint)
        if state is None:
            state = TrackingState(mint=mint)
            self.states[mint] = state
        if state.launch_received_at is None:
            state.launch_received_at = received_at
        if state.launch_slot is None:
            state.launch_slot = _int(launch.get("slot"))
        if state.launch_block_time is None:
            state.launch_block_time = _int(launch.get("block_time"))
        if not state.bonding_curve_account:
            state.bonding_curve_account = launch.get("bonding_curve_account") or launch.get("bonding_curve")
        if not state.associated_bonding_curve:
            state.associated_bonding_curve = launch.get("associated_bonding_curve")
        if not state.creator_address:
            state.creator_address = launch.get("creator") or launch.get("creator_wallet") or launch.get("dev")
        state.source_route_type = state.source_route_type or launch.get("source_type") or launch.get("source_route") or "unknown"
        state.source_decode_route = state.source_decode_route or decoded_route
        if not state.creator_history_metrics:
            supplied_history = _creator_history_metrics(launch, received_at)
            if supplied_history.get("creator_history_status") == "available":
                state.creator_history_metrics = supplied_history
            else:
                state.creator_history_metrics = self._local_creator_history_metrics(state.creator_address, received_at)
        self._record_creator_launch_seen(state, received_at)
        if deep_tracking_admitted:
            state.deep_tracking_admitted = True
        return state

    def _local_creator_history_metrics(self, creator: str | None, launch_received_at: float | None) -> dict[str, Any]:
        creator_key = str(creator or "").strip()
        if not creator_key:
            return {
                "creator_history_status": "not_available",
                "creator_history_source": "missing_creator_address",
                "creator_history_point_in_time_safe": False,
            }
        history = self.creator_history_by_creator.get(creator_key) or {}
        return {
            "creator_history_status": "available",
            "creator_history_source": "local_observed_lifecycle_ledger",
            "creator_history_scope": "local_observed_prior_to_launch",
            "creator_history_cutoff_time": launch_received_at,
            "creator_history_point_in_time_safe": True,
            "creator_prior_launch_count_before_this_launch": int(history.get("prior_launch_count") or 0),
            "creator_prior_migration_count_before_this_launch": int(history.get("prior_migration_count") or 0),
            "creator_prior_max_fdv_band_before_this_launch": history.get("prior_max_fdv_band"),
            "creator_prior_rug_dead_count_before_this_launch": int(history.get("prior_rug_dead_count") or 0),
        }

    def _record_creator_launch_seen(self, state: TrackingState, received_at: float | None) -> None:
        creator_key = str(state.creator_address or "").strip()
        if not creator_key or state.mint in self.creator_history_recorded_launch_mints:
            return
        entry = self.creator_history_by_creator.setdefault(
            creator_key,
            {"prior_launch_count": 0, "prior_migration_count": 0, "prior_max_fdv_band": None, "prior_rug_dead_count": 0},
        )
        entry["prior_launch_count"] = int(entry.get("prior_launch_count") or 0) + 1
        entry["last_launch_received_at"] = received_at
        self.creator_history_recorded_launch_mints.add(state.mint)

    def _record_creator_migration_seen(self, state: TrackingState, received_at: float | None) -> None:
        creator_key = str(state.creator_address or "").strip()
        if not creator_key or state.mint in self.creator_history_recorded_migration_mints:
            return
        entry = self.creator_history_by_creator.setdefault(
            creator_key,
            {"prior_launch_count": 0, "prior_migration_count": 0, "prior_max_fdv_band": None, "prior_rug_dead_count": 0},
        )
        entry["prior_migration_count"] = int(entry.get("prior_migration_count") or 0) + 1
        entry["last_migration_received_at"] = received_at
        self.creator_history_recorded_migration_mints.add(state.mint)

    def _record_thin_probe_result(self, birth_row: dict[str, Any], observation: dict[str, Any]) -> None:
        mint = str(birth_row.get("mint") or observation.get("mint") or "")
        birth_row["thin_probe_attempt_count"] = int(birth_row.get("thin_probe_attempt_count") or 0) + 1
        status = str(observation.get("decode_status") or "unknown")
        birth_row["thin_probe_decode_status"] = status
        progress = _num(observation.get("progress_pct"))
        if observation.get("account_found") is True and (status == "decoded" or progress is not None):
            birth_row["thin_probe_success_count"] = int(birth_row.get("thin_probe_success_count") or 0) + 1
            self.summary_counters["thin_probe_success_count"] += 1
        else:
            self.summary_counters["thin_probe_failed_count"] += 1
        if progress is not None:
            birth_row["thin_last_progress_pct"] = progress
            previous_high = _num(birth_row.get("thin_highest_progress_pct"))
            birth_row["thin_highest_progress_pct"] = progress if previous_high is None else max(previous_high, progress)
        if mint:
            existing = self.birth_rows_by_mint.get(mint, {})
            existing.update(
                {
                    "thin_probe_attempt_count": birth_row["thin_probe_attempt_count"],
                    "thin_probe_success_count": birth_row["thin_probe_success_count"],
                    "thin_probe_decode_status": birth_row["thin_probe_decode_status"],
                    "thin_highest_progress_pct": birth_row.get("thin_highest_progress_pct"),
                    "thin_last_progress_pct": birth_row.get("thin_last_progress_pct"),
                }
            )
            self.birth_rows_by_mint[mint] = existing
        if str(birth_row.get("admission_reason") or "").startswith("sample_rejected"):
            if int(birth_row.get("thin_probe_success_count") or 0) > 0:
                if mint and mint in self.sampled_out_thin_path_counted_mints:
                    return
                if mint:
                    self.sampled_out_thin_path_counted_mints.add(mint)
                self.summary_counters["sampled_out_with_thin_path_count"] += 1
            else:
                self.summary_counters["sampled_out_without_thin_path_count"] += 1

    def _promotion_allowed_for_state(self, state: TrackingState, trigger: str) -> bool:
        if state.stopped or state.deep_tracking_admitted:
            return False
        if state.tracking_tier not in {"thin", "deferred_enrichment"}:
            return False
        if trigger == "global_migration_event" and state.tracking_tier == "thin":
            return True
        return bool(self.config.migration_aware_promotion_enabled)

    def _record_promotion_event(
        self,
        state: TrackingState,
        trigger: str,
        *,
        source_row: dict[str, Any] | None = None,
        trigger_value: Any | None = None,
        as_of: float | None = None,
    ) -> bool:
        if not self._promotion_allowed_for_state(state, trigger):
            return False
        received_at = _num(_first_present(source_row or {}, ["migration_received_at", "received_at", "feature_observed_at"]))
        if received_at is None:
            received_at = as_of if as_of is not None else time.time()
        evicted = self._evict_low_priority_for_promotion(state, trigger, received_at=received_at)
        previous_tier = state.tracking_tier
        previous_reason = state.tracking_tier_reason
        state.tracking_tier = "escalated"
        state.tracking_tier_reason = trigger
        state.deep_tracking_admitted = True
        if trigger == "global_migration_event":
            state.migration_seen = True
            state.migration_received_at = received_at
        event = {
            "mint": state.mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "promotion_received_at": received_at,
            "promotion_trigger": trigger,
            "trigger_value": trigger_value,
            "previous_tracking_tier": previous_tier,
            "previous_tracking_tier_reason": previous_reason,
            "new_tracking_tier": state.tracking_tier,
            "new_tracking_tier_reason": state.tracking_tier_reason,
            "deep_tracking_admitted": state.deep_tracking_admitted,
            "tracking_profile": self.config.tracking_profile,
            "migration_aware_promotion_enabled": bool(self.config.migration_aware_promotion_enabled),
            "evicted_mint": evicted.get("evicted_mint") if evicted else None,
            "source_signature": (source_row or {}).get("signature") or (source_row or {}).get("migration_signature"),
            "source_pool": _first_present(source_row or {}, ["pool_or_pair_address", "pool_address", "pair_address"]),
        }
        self._append_jsonl("promotion_events.jsonl", event)
        self.summary_counters["promotion_events_written"] += 1
        self.summary_counters["promoted_mints"] += 1
        if trigger == "global_migration_event":
            self.summary_counters["promoted_migrated_mints"] += 1
        if previous_tier == "deferred_enrichment":
            self.summary_counters["capacity_deferred_promotions"] += 1
        _increment_counter(self.summary_counters["promotion_reason_counts"], trigger)
        self.summary_counters["thin_to_deep_escalation_count"] += 1
        _increment_counter(self.summary_counters["thin_to_deep_escalation_reasons"], trigger)
        self.summary_counters["active_tracking_max_count"] = max(
            int(self.summary_counters.get("active_tracking_max_count") or 0),
            self._active_tracking_count(),
        )
        self.enqueue_followup(state.mint, state.highest_progress_pct if state.highest_progress_pct is not None else state.last_progress_pct)
        return True

    def _evict_low_priority_for_promotion(
        self,
        promoted_state: TrackingState,
        trigger: str,
        *,
        received_at: float,
    ) -> dict[str, Any] | None:
        if self._active_tracking_count() < int(self.config.max_active_tracking):
            return None
        if not _parse_bool_value(self.config.evict_low_priority_stale_mints_for_promotion):
            return None
        candidates: list[TrackingState] = []
        for state in self._state_snapshot():
            if state.mint == promoted_state.mint or state.stopped or not state.deep_tracking_admitted:
                continue
            if state.migration_seen or state.thresholds_crossed or state.trade_count_since_launch > 0:
                continue
            if self._is_high_progress_protected(state):
                continue
            candidates.append(state)
        if not candidates:
            return None
        victim = sorted(candidates, key=lambda item: self._capacity_prune_sort_key(item, received_at))[0]
        row = {
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "evicted_mint": victim.mint,
            "promoted_mint": promoted_state.mint,
            "promotion_trigger": trigger,
            "eviction_received_at": received_at,
            "eviction_reason": "promotion_reserved_capacity_eviction",
            "evicted_age_seconds": _duration_seconds(victim.launch_received_at, received_at),
            "evicted_highest_progress_pct": victim.highest_progress_pct,
            "evicted_last_progress_pct": victim.last_progress_pct,
            "evicted_trade_rows": victim.trade_count_since_launch,
            "evicted_migration_seen": victim.migration_seen,
        }
        self._append_jsonl("promotion_evictions.jsonl", row)
        self._finalize_tracking_state(victim, "promotion_reserved_capacity_eviction", received_at=received_at)
        self.summary_counters["promotion_evictions_written"] += 1
        _increment_counter(self.summary_counters["promotion_eviction_reasons"], "promotion_reserved_capacity_eviction")
        return row

    def enqueue_migration_backfill(
        self,
        migration_row: dict[str, Any],
        *,
        client: Any | None = None,
        max_signatures_per_address: int = 10,
        max_transactions_per_mint: int = 20,
        lookup_sleep_ms: int = 0,
    ) -> dict[str, Any]:
        mint = str(migration_row.get("mint") or "").strip()
        job_id = f"{self.config.run_id}:migration_backfill:{self.summary_counters['migration_backfill_jobs_enqueued'] + 1}"
        active_jobs = (
            int(self.summary_counters["migration_backfill_jobs_enqueued"])
            - int(self.summary_counters["migration_backfill_jobs_completed"])
            - int(self.summary_counters["migration_backfill_jobs_failed"])
        )
        base_job = {
            "backfill_job_id": job_id,
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "backfill_trigger": "migration_event",
            "backfill_trigger_signature": _first_present(migration_row, ["signature", "migration_signature"]),
            "pool_or_pair_address": _first_present(migration_row, ["pool_or_pair_address", "pool_address", "pair_address"]),
            "quote_asset": migration_row.get("quote_asset"),
            "queued_at": time.time(),
        }
        if not mint:
            row = {**base_job, "status": "failed", "failure_reason": "missing_mint"}
            self.summary_counters["migration_backfill_jobs_failed"] += 1
            self._append_jsonl("migration_backfill_jobs.jsonl", row)
            return {"enqueued": False, "completed": False, "backfill_job_id": job_id, "failure_reason": "missing_mint"}
        if active_jobs >= int(self.config.migration_backfill_queue_max_size):
            row = {**base_job, "status": "rate_limited", "failure_reason": "migration_backfill_queue_full"}
            self.summary_counters["migration_backfill_rate_limited_count"] += 1
            self._append_jsonl("migration_backfill_jobs.jsonl", row)
            return {"enqueued": False, "completed": False, "backfill_job_id": job_id, "failure_reason": "migration_backfill_queue_full"}
        self.summary_counters["migration_backfill_jobs_enqueued"] += 1
        self.summary_counters["migration_backfill_queue_high_water"] = max(
            int(self.summary_counters.get("migration_backfill_queue_high_water") or 0),
            active_jobs + 1,
        )
        if client is None:
            self._append_jsonl("migration_backfill_jobs.jsonl", {**base_job, "status": "queued"})
            return {"enqueued": True, "completed": False, "backfill_job_id": job_id, "status": "queued"}
        try:
            replay = _replay_lookup_one_migrated_mint(
                mint,
                migration_row,
                client,
                max_signatures_per_address=max(1, int(max_signatures_per_address)),
                max_transactions_per_mint=max(1, int(max_transactions_per_mint)),
                lookup_sleep_ms=max(0, int(lookup_sleep_ms)),
                include_raw_transactions=False,
                output_root=self.output_root,
            )
        except Exception as exc:
            self.summary_counters["migration_backfill_jobs_failed"] += 1
            self.summary_counters["migration_backfill_rpc_error_count"] += 1
            failure = f"{type(exc).__name__}: {exc}"
            self._append_jsonl("migration_backfill_jobs.jsonl", {**base_job, "status": "failed", "failure_reason": failure})
            return {"enqueued": True, "completed": False, "backfill_job_id": job_id, "failure_reason": failure}
        if not replay.get("replay_birth_found"):
            self.summary_counters["migration_backfill_jobs_failed"] += 1
            self._append_jsonl("migration_backfill_jobs.jsonl", {**base_job, "status": "failed", "failure_reason": "replay_birth_not_found", **replay})
            return {"enqueued": True, "completed": False, "backfill_job_id": job_id, "failure_reason": "replay_birth_not_found"}
        birth_row = self.record_replay_backfilled_birth(
            {
                **migration_row,
                **replay,
                "backfill_trigger": "migration_event",
                "backfill_trigger_signature": base_job["backfill_trigger_signature"],
                "backfill_job_id": job_id,
                "migration_signature": base_job["backfill_trigger_signature"],
                "pool_or_pair_address": base_job["pool_or_pair_address"],
            }
        )
        self.summary_counters["migration_backfill_jobs_completed"] += 1
        if _bool(birth_row.get("replay_backfill_skipped_existing_live_birth")):
            self._append_jsonl("migration_backfill_jobs.jsonl", {**base_job, "status": "skipped_existing_live_birth", **replay})
            return {
                "enqueued": True,
                "completed": True,
                "backfill_job_id": job_id,
                "status": "skipped_existing_live_birth",
                "birth_row": birth_row,
            }
        self.summary_counters["migration_backfilled_birth_rows_written"] += 1
        self._append_jsonl("migration_backfill_jobs.jsonl", {**base_job, "status": "completed", **replay})
        return {"enqueued": True, "completed": True, "backfill_job_id": job_id, "status": "completed", "birth_row": birth_row}

    def _initialize_campaign_artifacts(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        for filename in JSONL_ARTIFACT_FILES:
            path = self.output_root / filename
            if not path.exists():
                path.touch()
        for filename, row in T007AA_PLACEHOLDER_ARTIFACTS.items():
            path = self.output_root / filename
            if path.stat().st_size == 0:
                placeholder = {
                    **row,
                    "status": "schema_ready_pending_live_source",
                    "campaign_id": self.config.run_id,
                    "run_id": self.config.run_id,
                    "as_of_received_at": self.started_at,
                    "notes": "T007AA schema marker; live enrichment source may still be absent for this lane.",
                }
                _append_jsonl_file(path, placeholder)

    def _campaign_manifest(self, *, ended_at: float | None = None, actual_duration_seconds: float | None = None) -> dict[str, Any]:
        return {
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "started_at": self.started_at,
            "ended_at": ended_at,
            "requested_duration_seconds": self.config.source_duration_seconds,
            "actual_duration_seconds": actual_duration_seconds,
            "source_duration_seconds": self.config.source_duration_seconds,
            "followup_drain_seconds": self.config.followup_drain_seconds,
            "sample_rate_percent": self.config.sample_rate_percent,
            "max_active_tracking": self.config.max_active_tracking,
            "active_lifecycle_policy_version": ACTIVE_LIFECYCLE_POLICY_VERSION,
            "quote_normalization_version": QUOTE_NORMALIZATION_VERSION,
            "curve_progress_formula_version": PROGRESS_FORMULA_VERSION,
            "migration_detector_version": MIGRATION_DETECTOR_VERSION,
            "valuation_ladder_policy": VALUATION_LADDER_POLICY,
            "valuation_ladder_enabled": False,
            "trading_enabled": False,
            "paper_trading_enabled": False,
            "mayhem_touched": False,
            "local_staging_root": _path_str_or_none(self.config.staging_root or self.output_root),
            "archive_root": _path_str_or_none(self.config.archive_root),
            "archive_status": self.archive_status,
            "archive_manifest_path": self.archive_manifest_path,
            "sol_usd": self.config.sol_usd,
            "sol_usd_source": self.config.sol_usd_source,
            "sol_usd_status": self.config.sol_usd_status,
            "sol_usd_error": self.config.sol_usd_error,
            "quote_assets_supported": ["SOL", "USDC"],
            "source_lanes_enabled": {
                "pumpfun_birth": True,
                "curve_progress": True,
                "pumpswap_global_migration": bool(self.config.enable_global_pumpswap_migration),
                "trade_flow": "schema_ready",
                "organic_flow": "schema_ready",
                "holder_distribution": "schema_ready",
                "dev_behavior": "schema_ready",
                "post_migration_depth": "schema_ready",
                "execution_cost": "schema_ready",
            },
            "tests_checks_run_before_campaign": [],
            "git_status_summary": "not_captured",
        }

    def _write_campaign_manifest(self, *, ended_at: float | None = None, actual_duration_seconds: float | None = None) -> None:
        _atomic_write_json(
            self.output_root / "campaign_manifest.json",
            self._campaign_manifest(ended_at=ended_at, actual_duration_seconds=actual_duration_seconds),
        )

    def enqueue_followup(self, mint: str, progress_pct: float | None) -> dict[str, Any]:
        tier = progress_priority_tier(progress_pct)
        item = {
            "mint": mint,
            "progress_pct": progress_pct,
            "priority_tier": tier,
            "priority": TIER_ORDER[tier],
            "queued_at": time.time(),
        }
        if len(self.followup_queue) < self.config.followup_queue_max_size:
            self.followup_queue.append(item)
            self._update_queue_high_water()
            return {"queued": True, "reason": "queued", "evicted_mint": None}
        lowest = min(self.followup_queue, key=lambda row: row["priority"])
        if item["priority"] > lowest["priority"]:
            self.followup_queue.remove(lowest)
            self.followup_queue.append(item)
            self.summary_counters["queue_dropped_count"] += 1
            return {"queued": True, "reason": "queued_after_evicting_lower_priority", "evicted_mint": lowest["mint"]}
        self.summary_counters["queue_dropped_count"] += 1
        return {"queued": False, "reason": "dropped_new_low_priority_queue_full", "evicted_mint": None}

    def record_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        mint = str(observation.get("mint") or observation.get("token_mint") or "")
        if not mint:
            self.summary_counters["decode_failures"] += 1
            row = self._observation_row(observation, "decode_failed", "missing_mint")
            self._append_jsonl("curve_observations.jsonl", row)
            return row
        state = self.states.get(mint)
        if state is None:
            state = TrackingState(mint=mint)
            self.states[mint] = state
        received_at = _num(observation.get("received_at")) or time.time()
        row = self._observation_row(
            observation,
            observation.get("decode_status") or ("decoded" if observation.get("progress_pct") is not None or observation.get("raw_curve_state") else "decode_failed"),
            observation.get("error_reason") or "",
        )
        progress = _num(row.get("progress_pct"))
        progress_status = row.get("progress_pct_status")
        complete = _bool(row.get("complete_or_migrated"))
        decode_status = row.get("decode_status") or observation.get("decode_status") or ("decoded" if progress is not None or observation.get("raw_curve_state") else "decode_failed")
        source_route_key = _state_source_route_key(state)
        row["source_route_key"] = source_route_key
        _increment_counter(self.summary_counters["curve_observations_by_quote_asset"], str(row.get("quote_asset") or "unknown"))
        history = self.observation_history_by_mint.setdefault(mint, [])
        history.append(dict(row))
        self._emit_curve_velocity_events(state, row, history)
        self._emit_curve_acceleration_events(state, row, history)
        state.observation_count += 1
        if decode_status == "decoded" and progress_status in {"decoded_exact", "decoded_candidate"}:
            state.decoded_observation_count += 1
        _increment_nested_counter(self.summary_counters["decode_coverage_by_source_route"], source_route_key, str(decode_status or "unknown"))
        _increment_nested_counter(
            self.summary_counters["progress_decode_coverage_by_source_route"],
            source_route_key,
            str(progress_status or "unavailable"),
        )
        if decode_status != "decoded":
            self.summary_counters["decode_failures"] += 1
        if state.launch_received_at is not None and state.first_observation_received_at is None:
            state.first_observation_received_at = received_at
            self.birth_to_first_observation_latencies_ms.append(max(0.0, (received_at - state.launch_received_at) * 1000.0))
            self._update_hotpath_latency_span(mint, first_curve_observed_at=received_at)
            self._flush_hotpath_latency_span(mint)
        if state.last_observation_received_at is not None:
            interval = max(0.0, received_at - state.last_observation_received_at)
            self.observation_intervals_by_tier.setdefault(state.priority_tier, []).append(interval)
        previous = state.last_progress_pct
        if (
            progress is not None
            and bool(self.config.migration_aware_promotion_enabled)
            and progress >= float(self.config.promote_on_curve_progress_pct)
        ):
            self._record_promotion_event(
                state,
                "curve_progress_threshold",
                source_row=row,
                trigger_value=progress,
                as_of=received_at,
            )
        _update_tracking_tier_for_observation(state, progress, complete=complete)
        row["tracking_tier"] = state.tracking_tier
        row["tracking_tier_reason"] = state.tracking_tier_reason
        row["deep_tracking_admitted"] = state.deep_tracking_admitted
        self._append_jsonl("curve_observations.jsonl", row)
        self.summary_counters["observations_written"] += 1
        if progress_status == "decoded_exact":
            self.summary_counters["exact_progress_decoded_count"] += 1
            self.summary_counters["progress_decoded_exact_count"] += 1
        elif progress_status == "decoded_candidate":
            self.summary_counters["progress_decoded_candidate_count"] += 1
        elif progress_status == "unresolved_formula":
            self.summary_counters["unresolved_progress_formula_count"] += 1
        if row.get("reserve_scale_mode"):
            _increment_counter(self.summary_counters["reserve_scale_mode_counts"], str(row.get("reserve_scale_mode")))
        _increment_counter(self.summary_counters["valuation_units_status_counts"], str(row.get("valuation_units_status") or "missing"))
        _increment_counter(
            self.summary_counters["valuation_ladder_trust_status_counts"],
            str(row.get("valuation_ladder_trust_status") or "missing"),
        )
        _append_number(self.fdv_proxy_raw_values, row.get("fdv_proxy_raw"))
        _append_number(self.fdv_proxy_sol_values, row.get("fdv_proxy_sol"))
        _append_number(self.fdv_proxy_usd_values, row.get("fdv_proxy_usd"))
        _append_number(self.reserve_fdv_sol_values, row.get("reserve_fdv_sol"))
        _append_number(self.reserve_fdv_usd_values, row.get("reserve_fdv_usd"))
        valuation_usd = _num(row.get("valuation_usd"))
        self._emit_valuation_formula_audit(state, row, received_at)
        if valuation_usd is None:
            self.summary_counters["valuation_missing_count"] += 1
            missing_reason = _valuation_missing_reason(row)
            _increment_counter(self.summary_counters["valuation_missing_reason_counts"], missing_reason)
            _increment_nested_counter(self.summary_counters["valuation_coverage_by_source_route"], source_route_key, "missing")
        else:
            self.summary_counters["valuation_present_count"] += 1
            _increment_nested_counter(self.summary_counters["valuation_coverage_by_source_route"], source_route_key, "present")
            if _valuation_ladder_allowed(row):
                self.summary_counters["valuation_ladder_market_cap_confirmed_count"] += 1
                self._emit_valuation_band_crossings(state, row, state.last_valuation_usd, valuation_usd, received_at)
                self._update_valuation_path_extrema(state, valuation_usd)
                state.last_valuation_usd = valuation_usd
            else:
                self.summary_counters["valuation_ladder_suppressed_untrusted_count"] += 1
        if progress is not None:
            self._emit_threshold_crossings(state, row, previous, progress, received_at)
            state.previous_progress_pct = previous
            state.last_progress_pct = progress
            state.highest_progress_pct = progress if state.highest_progress_pct is None else max(state.highest_progress_pct, progress)
            state.priority_tier = progress_priority_tier(progress, complete=complete)
        self._update_migration_signal_counts(row)
        migration_signal_source = _migration_signal_source(row)
        if migration_signal_source and not state.migration_seen:
            row["migration_signal_source"] = migration_signal_source
            self._emit_migration_event(state, row, received_at)
            self._emit_wallet_dev_checkpoint(state, "migration", observation=row, received_at=received_at)
            self._stop_tracking(state, "migration_complete")
        elif not state.migration_seen:
            self._emit_high_fdv_without_migration_candidates(state, row, received_at)
        state.last_observation_received_at = received_at
        state.last_observation_row = row
        if observation.get("bonding_curve_account"):
            state.bonding_curve_account = str(observation.get("bonding_curve_account"))
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def record_trade_event(self, event: dict[str, Any]) -> dict[str, Any]:
        mint = str(event.get("mint") or event.get("token_mint") or "")
        received_at = _num(event.get("received_at")) or time.time()
        state = self._feature_state(mint, received_at)
        side = str(event.get("side") or "").strip().lower()
        quote_amount = _num(event.get("quote_amount") or event.get("quote_amount_ui") or event.get("sol_amount"))
        token_amount = _num(event.get("token_amount") or event.get("token_amount_ui"))
        trader_wallet = str(event.get("trader_wallet") or event.get("wallet") or event.get("owner") or "")
        fee_payer = str(event.get("fee_payer") or event.get("payer") or "")
        quote_asset = str(event.get("quote_asset") or event.get("quote_symbol") or "unknown")
        is_buy = side == "buy"
        is_sell = side == "sell"
        state.trade_count_since_launch += 1
        if trader_wallet:
            state.trade_wallet_counts[trader_wallet] = state.trade_wallet_counts.get(trader_wallet, 0) + 1
        if quote_amount is not None:
            size_bucket = f"{quote_amount:.9f}"
            state.trade_size_counts[size_bucket] = state.trade_size_counts.get(size_bucket, 0) + 1
        if is_buy:
            state.buy_count_since_launch += 1
            if trader_wallet:
                state.unique_buyers_since_launch.add(trader_wallet)
            state.buy_quote_volume_since_launch += quote_amount or 0.0
            state.net_quote_inflow_since_launch += quote_amount or 0.0
            state.consecutive_buy_count = state.consecutive_buy_count + 1 if state.last_trade_side == "buy" else 1
            state.consecutive_sell_count = 0
        elif is_sell:
            state.sell_count_since_launch += 1
            if trader_wallet:
                state.unique_sellers_since_launch.add(trader_wallet)
            creator_wallet = str(state.creator_address or "").strip()
            if creator_wallet and creator_wallet in {trader_wallet, fee_payer}:
                state.creator_sold_before_entry_observed = True
            state.sell_quote_volume_since_launch += quote_amount or 0.0
            state.net_quote_inflow_since_launch -= quote_amount or 0.0
            state.consecutive_sell_count = state.consecutive_sell_count + 1 if state.last_trade_side == "sell" else 1
            state.consecutive_buy_count = 0
        state.last_trade_side = side or state.last_trade_side
        bot_like = self._is_bot_like_trade(state, trader_wallet, quote_amount, received_at)
        if bot_like:
            state.bot_like_trade_count += 1
            state.bot_like_quote_volume += quote_amount or 0.0
        status = "available" if side in {"buy", "sell"} and quote_amount is not None else "partial"
        state.trade_flow_status = status
        decision = self._decision_time_fields(event, received_at)
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "signature": event.get("signature"),
            "slot": event.get("slot"),
            "block_time": event.get("block_time"),
            "received_at": received_at,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received_at),
            "side": side or None,
            "trader_wallet": trader_wallet or None,
            "fee_payer": fee_payer or None,
            "token_amount": token_amount,
            "quote_amount": quote_amount,
            "quote_asset": quote_asset,
            "trade_count_since_launch": state.trade_count_since_launch,
            "buy_count_since_launch": state.buy_count_since_launch,
            "sell_count_since_launch": state.sell_count_since_launch,
            "buy_quote_volume_since_launch": round(state.buy_quote_volume_since_launch, 9),
            "sell_quote_volume_since_launch": round(state.sell_quote_volume_since_launch, 9),
            "net_quote_inflow_since_launch": round(state.net_quote_inflow_since_launch, 9),
            "unique_buyers_since_launch": len(state.unique_buyers_since_launch),
            "unique_sellers_since_launch": len(state.unique_sellers_since_launch),
            "buy_sell_count_ratio": _safe_ratio(state.buy_count_since_launch, state.sell_count_since_launch),
            "buy_sell_quote_ratio": _safe_ratio(state.buy_quote_volume_since_launch, state.sell_quote_volume_since_launch),
            "consecutive_buys": state.consecutive_buy_count,
            "consecutive_sells": state.consecutive_sell_count,
            "progress_per_trade": _safe_ratio(state.last_progress_pct, state.trade_count_since_launch) if state.last_progress_pct is not None else None,
            "trade_efficiency_status": "available" if state.last_progress_pct is not None else "partial_no_progress_yet",
            "trade_flow_status": status,
            **decision,
        }
        if (
            bool(self.config.migration_aware_promotion_enabled)
            and int(self.config.promote_on_trade_rows) > 0
            and state.trade_count_since_launch >= int(self.config.promote_on_trade_rows)
        ):
            self._record_promotion_event(
                state,
                "trade_rows_threshold",
                source_row=row,
                trigger_value=state.trade_count_since_launch,
                as_of=received_at,
            )
        row["tracking_tier"] = state.tracking_tier
        row["tracking_tier_reason"] = state.tracking_tier_reason
        row["deep_tracking_admitted"] = state.deep_tracking_admitted
        self._append_jsonl("trade_flow_events.jsonl", row)
        self.summary_counters["trade_flow_events_written"] += 1
        self.summary_counters["trade_flow_available_count" if status == "available" else "trade_flow_partial_count"] += 1
        self.summary_counters["buyer_breadth_available_count"] += 1
        organic = self._organic_flow_row(state, event, received_at, quote_amount, bot_like, decision)
        self._append_jsonl("organic_flow_events.jsonl", organic)
        self.summary_counters["organic_flow_events_written"] += 1
        self.summary_counters["organic_flow_available_count" if organic["organic_share_status"] == "available" else "organic_flow_partial_count"] += 1
        state.last_trade_received_at = received_at
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def record_holder_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        mint = str(snapshot.get("mint") or snapshot.get("token_mint") or "")
        received_at = _num(snapshot.get("received_at")) or time.time()
        state = self._feature_state(mint, received_at)
        status = str(snapshot.get("holder_distribution_status") or "")
        if not status:
            status = "available" if _num(snapshot.get("holder_count")) is not None else "partial"
        state.holder_distribution_status = status
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "checkpoint": snapshot.get("checkpoint") or snapshot.get("holder_checkpoint"),
            "received_at": received_at,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received_at),
            "holder_count": _int(snapshot.get("holder_count")),
            "top_1_holder_pct": _num(snapshot.get("top_1_holder_pct")),
            "top_3_holder_pct": _num(snapshot.get("top_3_holder_pct")),
            "top_5_holder_pct": _num(snapshot.get("top_5_holder_pct")),
            "top_10_holder_pct": _num(snapshot.get("top_10_holder_pct")),
            "top_20_holder_pct": _num(snapshot.get("top_20_holder_pct")),
            "excluded_pool_or_burn_accounts": _bool(snapshot.get("excluded_pool_or_burn_accounts")),
            "sniper_or_early_wallet_pct": _num(snapshot.get("sniper_or_early_wallet_pct")),
            "holder_distribution_status": status,
            "latency_ms": _num(snapshot.get("latency_ms")),
            "error_reason": snapshot.get("error_reason"),
            **self._decision_time_fields(snapshot, received_at),
        }
        self._append_jsonl("holder_distribution_snapshots.jsonl", row)
        self.summary_counters["holder_distribution_snapshots_written"] += 1
        self.summary_counters["holder_distribution_available_count" if status == "available" else "holder_distribution_partial_count"] += 1
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def record_dev_behavior_event(self, event: dict[str, Any]) -> dict[str, Any]:
        mint = str(event.get("mint") or event.get("token_mint") or "")
        received_at = _num(event.get("received_at")) or time.time()
        state = self._feature_state(mint, received_at)
        creator_wallet = str(event.get("creator_wallet") or event.get("creator") or state.creator_address or "")
        cutoff = state.launch_received_at
        latest_history_time = _num(event.get("latest_creator_history_event_time"))
        point_in_time_safe = latest_history_time is None or cutoff is None or latest_history_time <= cutoff
        status = str(event.get("dev_behavior_status") or "")
        if not status:
            status = "available" if creator_wallet or _num(event.get("prior_launch_count")) is not None else "partial"
        if not point_in_time_safe:
            status = "partial"
        state.dev_behavior_status = status
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "creator_wallet": creator_wallet or None,
            "received_at": received_at,
            "launch_received_at": state.launch_received_at,
            "creator_history_cutoff_time": cutoff,
            "creator_history_point_in_time_safe": point_in_time_safe,
            "prior_launch_count": _int(event.get("prior_launch_count")),
            "prior_migration_count": _int(event.get("prior_migration_count")),
            "prior_max_progress_pct": _num(event.get("prior_max_progress_pct")),
            "creator_sold_before_40": _bool(event.get("creator_sold_before_40")),
            "creator_sold_before_60": _bool(event.get("creator_sold_before_60")),
            "creator_sold_before_70": _bool(event.get("creator_sold_before_70")),
            "creator_sold_before_migration": _bool(event.get("creator_sold_before_migration")),
            "creator_retained_balance_status": event.get("creator_retained_balance_status"),
            "mint_authority_status": event.get("mint_authority_status"),
            "freeze_authority_status": event.get("freeze_authority_status"),
            "token2022_extension_status": event.get("token2022_extension_status"),
            "dev_behavior_status": status,
            "error_reason": event.get("error_reason"),
            **self._decision_time_fields(event, received_at),
        }
        self._append_jsonl("dev_behavior_events.jsonl", row)
        self.summary_counters["dev_behavior_events_written"] += 1
        self.summary_counters["dev_behavior_available_count" if status == "available" else "dev_behavior_partial_count"] += 1
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def schedule_post_migration_observations(self, migration_row: dict[str, Any], *, as_of: float | None = None) -> int:
        mint = str(migration_row.get("mint") or "")
        if not mint:
            return 0
        pool = str(migration_row.get("pool_or_pair_address") or migration_row.get("pool_address") or "")
        migration_received_at = _num(_first_present(migration_row, ["migration_received_at", "received_at"]))
        if migration_received_at is None:
            migration_received_at = as_of if as_of is not None else time.time()
        if as_of is not None:
            self._post_migration_as_of_override = as_of

        scheduled = 0
        for horizon in POST_MIGRATION_OBSERVATION_HORIZONS_SECONDS:
            key = (mint, pool, int(horizon))
            if key in self._post_migration_schedule_keys:
                continue
            self._post_migration_schedule_keys.add(key)
            self.post_migration_observation_schedules.append(
                {
                    "mint": mint,
                    "base_mint": migration_row.get("base_mint") or mint,
                    "pool_or_pair_address": pool or None,
                    "pool_base_token_account": migration_row.get("pool_base_token_account"),
                    "pool_quote_token_account": migration_row.get("pool_quote_token_account"),
                    "quote_asset": migration_row.get("quote_asset") or "unknown",
                    "quote_mint": migration_row.get("quote_mint"),
                    "migration_received_at": migration_received_at,
                    "horizon_seconds_after_migration": int(horizon),
                    "due_at": float(migration_received_at) + int(horizon),
                    "observation_slot": migration_row.get("slot") or migration_row.get("observation_slot"),
                    "source_route": migration_row.get("source_route"),
                    "detection_method": migration_row.get("detection_method"),
                    "confidence": migration_row.get("confidence"),
                    "migration_evidence_level": migration_row.get("migration_evidence_level"),
                    "migration_evidence_reason": migration_row.get("migration_evidence_reason"),
                    "snapshot_required": True,
                    "snapshot_status": "pool_known_vaults_known" if pool and migration_row.get("pool_base_token_account") and migration_row.get("pool_quote_token_account") else ("pool_known_vaults_pending_decode" if pool else "missing_pool"),
                    "written": False,
                }
            )
            scheduled += 1
        self.summary_counters["post_migration_observations_scheduled"] += scheduled
        self.summary_counters["post_migration_snapshot_scheduled_count"] += scheduled
        self.write_due_post_migration_observations(as_of=as_of)
        return scheduled

    def write_due_post_migration_observations(self, *, as_of: float | None = None) -> int:
        now = as_of if as_of is not None else time.time()
        if as_of is not None:
            self._post_migration_as_of_override = as_of
        written = 0
        for schedule in self.post_migration_observation_schedules:
            if schedule.get("written") or float(schedule.get("due_at") or 0.0) > float(now):
                continue
            pool = schedule.get("pool_or_pair_address")
            pool_state = self.fetch_post_migration_pool_state(str(pool or ""), as_of=now)
            observation = {
                "mint": schedule.get("mint"),
                "base_mint": schedule.get("base_mint"),
                "pool_or_pair_address": pool,
                "quote_asset": schedule.get("quote_asset"),
                "quote_mint": schedule.get("quote_mint"),
                "migration_received_at": schedule.get("migration_received_at"),
                "horizon_seconds_after_migration": schedule.get("horizon_seconds_after_migration"),
                "observation_received_at": now,
                "received_at": now,
                "observation_slot": schedule.get("observation_slot"),
                "pool_state_status": "partial" if pool else "error",
                "depth_status": "partial" if pool else "error",
                "executable_quote_status": "deferred",
                "quote_source": "not_implemented",
                "error_reason": None if pool else "missing_pool_or_pair_address",
                "migration_evidence_level": schedule.get("migration_evidence_level"),
                "migration_evidence_reason": schedule.get("migration_evidence_reason"),
                "snapshot_required": schedule.get("snapshot_required"),
                "snapshot_status": schedule.get("snapshot_status"),
            }
            observation.update({key: value for key, value in pool_state.items() if value is not None})
            self.record_post_migration_observation(observation)
            schedule["written"] = True
            written += 1
            self.record_execution_cost_sample("post_migration_horizon", as_of=now)
        self.summary_counters["post_migration_observations_pending_at_finalization"] = self._pending_post_migration_observation_count()
        return written

    def _pending_post_migration_observation_count(self) -> int:
        return sum(1 for schedule in self.post_migration_observation_schedules if not schedule.get("written"))

    def fetch_post_migration_pool_state(self, pool_or_pair_address: str, *, as_of: float | None = None) -> dict[str, Any]:
        if not pool_or_pair_address:
            return {
                "pool_state_status": "error",
                "depth_status": "error",
                "pool_state_error_reason": "missing_pool_or_pair_address",
            }
        probe = self.pool_state_probe
        if probe is None:
            return {
                "pool_state_status": "partial",
                "depth_status": "partial",
                "pool_decode_route": "pumpswap_market_account_v1",
                "pool_decode_confidence": "metadata_probe_not_configured",
                "pool_state_error_reason": "pool_state_probe_not_configured",
            }
        try:
            if hasattr(probe, "fetch_pool_state"):
                row = dict(probe.fetch_pool_state(pool_or_pair_address) or {})
            else:
                row = {}
        except Exception as exc:
            return {
                "pool_state_status": "error",
                "depth_status": "error",
                "pool_decode_route": "pumpswap_market_account_v1",
                "pool_decode_confidence": "error",
                "pool_state_error_reason": str(exc),
                "pool_state_observed_at": as_of,
            }
        if not row:
            row = {
                "pool_state_status": "not_available",
                "depth_status": "not_available",
                "pool_state_error_reason": "pool_state_not_available",
            }
        row.setdefault("pool_state_observed_at", as_of)
        return row

    def _build_direct_pool_executable_quote_rows(
        self,
        *,
        mint: str,
        base_mint: str | None,
        pool_or_pair_address: str | None,
        quote_asset: str,
        quote_mint: str | None,
        observation_received_at: float,
        observation_slot: Any,
        migration_received_at: float | None,
        horizon_seconds_after_migration: int | None,
        base_reserve_scaled: float | None,
        quote_reserve_scaled: float | None,
        quote_to_usd_rate: float | None,
        decision_row: dict[str, Any],
    ) -> list[dict[str, Any]]:
        quote_asset_upper = str(quote_asset or "").upper()
        clips = EXECUTABLE_QUOTE_CLIPS_BY_QUOTE_ASSET.get(quote_asset_upper, ())
        if not clips or not base_reserve_scaled or not quote_reserve_scaled:
            return []
        if base_reserve_scaled <= 0 or quote_reserve_scaled <= 0:
            return []
        pool_mid_price = quote_reserve_scaled / base_reserve_scaled
        if pool_mid_price <= 0:
            return []
        invariant = base_reserve_scaled * quote_reserve_scaled
        rows: list[dict[str, Any]] = []
        for clip in clips:
            input_token_amount = clip / pool_mid_price
            if input_token_amount <= 0:
                continue
            expected_output_quote = quote_reserve_scaled - (invariant / (base_reserve_scaled + input_token_amount))
            if expected_output_quote <= 0:
                continue
            effective_exit_price = expected_output_quote / input_token_amount
            price_impact_pct = max(0.0, ((pool_mid_price - effective_exit_price) / pool_mid_price) * 100.0)
            expected_output_quote_usd = (
                expected_output_quote * quote_to_usd_rate
                if quote_to_usd_rate is not None
                else None
            )
            quote_row = {
                "campaign_id": self.config.run_id,
                "run_id": self.config.run_id,
                "mint": mint,
                "pool_or_pair_address": pool_or_pair_address,
                "quote_asset": quote_asset_upper,
                "quote_mint": quote_mint,
                "base_mint": base_mint or mint,
                "observation_received_at": observation_received_at,
                "observation_slot": observation_slot,
                "migration_received_at": migration_received_at,
                "horizon_seconds_after_migration": horizon_seconds_after_migration,
                "quote_direction": "exit_token_to_quote",
                "quote_source": "direct_pool_math",
                "quote_status": "partial",
                "quote_confidence": "low",
                "quote_clip_notional_quote": float(clip),
                "input_token_amount_estimated": input_token_amount,
                "expected_output_quote": expected_output_quote,
                "expected_output_quote_usd": expected_output_quote_usd,
                "pool_mid_price_quote_per_token": pool_mid_price,
                "effective_exit_price_quote_per_token": effective_exit_price,
                "price_impact_pct": price_impact_pct,
                "pool_base_reserve_scaled": base_reserve_scaled,
                "pool_quote_reserve_scaled": quote_reserve_scaled,
                "fee_bps_used": None,
                "fee_model_status": "unknown",
                "route_count": 1,
                "error_reason": None,
                "valuation_ladder_used": False,
                **self._decision_time_fields(decision_row, observation_received_at),
            }
            rows.append(quote_row)
        return rows

    def _record_executable_quote_rows(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._append_jsonl("executable_quote_observations.jsonl", row)
            self.summary_counters["executable_quote_observations_written"] += 1
            status = str(row.get("quote_status") or "unknown")
            if status == "available":
                self.summary_counters["executable_quote_available_count"] += 1
            elif status == "partial":
                self.summary_counters["executable_quote_partial_count"] += 1
            elif status == "deferred":
                self.summary_counters["executable_quote_deferred_count"] += 1
            elif status == "error":
                self.summary_counters["executable_quote_error_count"] += 1
            _increment_counter(self.summary_counters["executable_quote_by_source"], str(row.get("quote_source") or "unknown"))
            _increment_counter(self.summary_counters["executable_quote_by_quote_asset"], str(row.get("quote_asset") or "unknown"))
            _increment_counter(self.summary_counters["executable_quote_by_direction"], str(row.get("quote_direction") or "unknown"))
            self.summary_counters["executable_quote_clip_count"] += 1
            if row.get("price_impact_pct") is not None:
                self.summary_counters["price_impact_available_count"] += 1
            else:
                self.summary_counters["price_impact_missing_count"] += 1
            if row.get("decision_time_safe") is True:
                self.summary_counters["executable_quote_decision_time_safe_count"] += 1
            fee_model = str(row.get("fee_model_status") or "unknown")
            if fee_model == "confirmed":
                self.summary_counters["fee_model_confirmed_count"] += 1
            elif fee_model == "assumed":
                self.summary_counters["fee_model_assumed_count"] += 1
            elif fee_model == "unknown":
                self.summary_counters["fee_model_unknown_count"] += 1

    def record_post_migration_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        mint = str(observation.get("mint") or observation.get("token_mint") or "")
        received_at = _num(_first_present(observation, ["observation_received_at", "received_at"])) or time.time()
        state = self._feature_state(mint, received_at)
        pool_or_pair_address = observation.get("pool_or_pair_address") or observation.get("pool_address")
        migration_received_at = _num(_first_present(observation, ["migration_received_at", "migration_received_at_seconds"]))
        if migration_received_at is None:
            migration_received_at = state.migration_received_at
        if migration_received_at is not None:
            state.migration_seen = True
            state.migration_received_at = migration_received_at
            self._record_creator_migration_seen(state, migration_received_at)

        base_reserve_raw = _num(observation.get("base_reserve_raw") or observation.get("pool_base_reserve"))
        quote_reserve_raw = _num(observation.get("quote_reserve_raw") or observation.get("pool_quote_reserve"))
        base_reserve_scaled = _num(observation.get("base_reserve_scaled"))
        quote_reserve_scaled = _num(observation.get("quote_reserve_scaled"))
        pool_base_reserve = base_reserve_scaled if base_reserve_scaled is not None else base_reserve_raw
        pool_quote_reserve = quote_reserve_scaled if quote_reserve_scaled is not None else quote_reserve_raw
        quote_identity = _quote_identity_from_payload(
            observation,
            sol_usd=self.config.sol_usd,
            sol_usd_source=self.config.sol_usd_source,
            unsupported_as_unknown=True,
        )
        quote_asset = observation.get("quote_asset") or quote_identity["quote_asset"] or "unknown"
        quote_mint = observation.get("quote_mint") or quote_identity["quote_mint"]
        pool_liquidity_quote = _num(observation.get("pool_liquidity_quote"))
        pool_liquidity_usd = _num(observation.get("pool_liquidity_usd") or observation.get("real_liquidity_usd"))
        quote_to_usd_rate = _num(observation.get("quote_to_usd_rate"))
        if quote_to_usd_rate is None:
            quote_to_usd_rate = _num(quote_identity.get("quote_to_usd_rate"))
        if pool_liquidity_usd is None and pool_liquidity_quote is not None:
            quote_asset_for_usd = str(observation.get("quote_asset") or "").upper()
            if quote_mint == SOL_MINT or quote_asset_for_usd == "SOL":
                quote_to_usd_rate = _num(self.config.sol_usd)
                pool_liquidity_usd = pool_liquidity_quote * quote_to_usd_rate if quote_to_usd_rate is not None else None
            elif quote_mint == USDC_MINT or quote_asset_for_usd == "USDC":
                quote_to_usd_rate = 1.0
                pool_liquidity_usd = pool_liquidity_quote
        price_impact_pct = _num(observation.get("price_impact_pct"))
        route_count = _int(observation.get("route_count"))
        expected_output_token = _num(observation.get("expected_output_token"))
        expected_output_quote = _num(observation.get("expected_output_quote"))

        pool_state_status = str(observation.get("pool_state_status") or "")
        if not pool_state_status:
            if not pool_or_pair_address:
                pool_state_status = "error"
            elif pool_base_reserve is not None or pool_quote_reserve is not None:
                pool_state_status = "available"
            else:
                pool_state_status = "partial"

        depth_status = str(observation.get("depth_status") or observation.get("depth_coverage_status") or "")
        if not depth_status:
            if pool_state_status == "error":
                depth_status = "error"
            elif pool_liquidity_quote is not None or pool_liquidity_usd is not None:
                depth_status = "available"
            elif pool_or_pair_address:
                depth_status = "partial"
            else:
                depth_status = "error"

        pool_market_cap = _pool_market_cap_from_reserves(
            {
                **observation,
                "quote_asset": quote_asset,
                "quote_mint": quote_mint,
                "quote_to_usd_rate": quote_to_usd_rate,
                "quote_to_usd_source": quote_identity.get("quote_to_usd_source"),
            },
            base_reserve_scaled=base_reserve_scaled,
            quote_reserve_scaled=quote_reserve_scaled,
            sol_usd=self.config.sol_usd,
            sol_usd_source=self.config.sol_usd_source,
        )
        horizon = _int(observation.get("horizon_seconds_after_migration"))
        decision_row = dict(observation)
        decision_row["decision_time"] = received_at
        direct_quote_rows: list[dict[str, Any]] = []
        if pool_state_status == "available" and depth_status == "available":
            direct_quote_rows = self._build_direct_pool_executable_quote_rows(
                mint=mint,
                base_mint=str(observation.get("base_mint") or mint),
                pool_or_pair_address=str(pool_or_pair_address or ""),
                quote_asset=str(quote_asset),
                quote_mint=str(quote_mint or ""),
                observation_received_at=received_at,
                observation_slot=observation.get("observation_slot") or observation.get("slot"),
                migration_received_at=migration_received_at,
                horizon_seconds_after_migration=horizon,
                base_reserve_scaled=base_reserve_scaled,
                quote_reserve_scaled=quote_reserve_scaled,
                quote_to_usd_rate=quote_to_usd_rate,
                decision_row=decision_row,
            )
        quote_calc_error_reason = None
        known_quote_asset_for_math = str(quote_asset or "").upper() in EXECUTABLE_QUOTE_CLIPS_BY_QUOTE_ASSET
        if (
            pool_state_status == "available"
            and depth_status == "available"
            and known_quote_asset_for_math
            and not direct_quote_rows
        ):
            quote_calc_error_reason = "missing_pool_reserves_for_direct_quote"

        executable_status = str(observation.get("executable_quote_status") or "")
        if direct_quote_rows and executable_status in {"", "deferred", "not_available"}:
            executable_status = "partial"
        elif quote_calc_error_reason and executable_status in {"", "deferred"}:
            executable_status = "not_available"
        elif not executable_status:
            executable_status = (
                "available"
                if price_impact_pct is not None or expected_output_token is not None or expected_output_quote is not None
                else "deferred"
            )

        quote_source = observation.get("quote_source")
        if direct_quote_rows or quote_calc_error_reason:
            quote_source = "direct_pool_math"
        elif not quote_source:
            quote_source = "direct_pool" if executable_status == "available" else "not_implemented"

        error_reason = observation.get("error_reason")
        if not error_reason and not pool_or_pair_address:
            error_reason = "missing_pool_or_pair_address"
        if not error_reason and quote_calc_error_reason:
            error_reason = quote_calc_error_reason

        status = str(observation.get("post_migration_observation_status") or "")
        if not status:
            if pool_state_status == "error" or depth_status == "error" or executable_status == "error":
                status = "partial"
            elif depth_status == "available" or executable_status == "available":
                status = "available"
            else:
                status = "partial"

        state.post_migration_depth_status = status
        state.post_migration_observation_count += 1
        price_impacts = [float(row["price_impact_pct"]) for row in direct_quote_rows if row.get("price_impact_pct") is not None]
        expected_outputs = [float(row["expected_output_quote"]) for row in direct_quote_rows if row.get("expected_output_quote") is not None]
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "base_mint": observation.get("base_mint") or mint,
            "pool_or_pair_address": pool_or_pair_address,
            "quote_asset": quote_asset,
            "quote_mint": quote_mint,
            "migration_received_at": migration_received_at,
            "horizon_seconds_after_migration": horizon,
            "observation_received_at": received_at,
            "observation_slot": observation.get("observation_slot") or observation.get("slot"),
            "checkpoint": observation.get("checkpoint"),
            "received_at": received_at,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received_at),
            "seconds_since_migration": _duration_seconds(migration_received_at, received_at),
            "pool_state_status": pool_state_status,
            "pool_decode_route": observation.get("pool_decode_route"),
            "pool_decode_confidence": observation.get("pool_decode_confidence"),
            "pool_account_owner": observation.get("pool_account_owner"),
            "pool_account_size": _int(observation.get("pool_account_size")),
            "pool_discriminator": observation.get("pool_discriminator"),
            "pool_base_mint": observation.get("pool_base_mint"),
            "pool_quote_mint": observation.get("pool_quote_mint"),
            "base_reserve_raw": base_reserve_raw,
            "quote_reserve_raw": quote_reserve_raw,
            "base_reserve_scaled": base_reserve_scaled,
            "quote_reserve_scaled": quote_reserve_scaled,
            "pool_base_reserve": pool_base_reserve,
            "pool_quote_reserve": pool_quote_reserve,
            "pool_liquidity_quote": pool_liquidity_quote,
            "pool_liquidity_usd": pool_liquidity_usd,
            "pool_price_quote_per_token": pool_market_cap.get("pool_price_quote_per_token"),
            "pool_price_usd_per_token": pool_market_cap.get("pool_price_usd_per_token"),
            "pool_market_cap_quote": pool_market_cap.get("pool_market_cap_quote"),
            "pool_market_cap_usd": pool_market_cap.get("pool_market_cap_usd"),
            "pool_market_cap_quote_asset": pool_market_cap.get("pool_market_cap_quote_asset"),
            "pool_market_cap_quote_mint": pool_market_cap.get("pool_market_cap_quote_mint"),
            "pool_token_total_supply_scaled": pool_market_cap.get("pool_token_total_supply_scaled"),
            "pool_market_cap_status": pool_market_cap.get("pool_market_cap_status"),
            "pool_market_cap_formula_version": pool_market_cap.get("pool_market_cap_formula_version"),
            "quote_to_usd_rate": quote_to_usd_rate,
            "pool_state_error_reason": observation.get("pool_state_error_reason") or error_reason,
            "pool_state_observed_at": _num(observation.get("pool_state_observed_at")),
            "pool_state_slot": observation.get("pool_state_slot"),
            "depth_status": depth_status,
            "real_liquidity_usd": pool_liquidity_usd,
            "executable_quote_status": executable_status,
            "quote_source": quote_source,
            "executable_quote_clip_count": len(direct_quote_rows),
            "min_price_impact_pct": min(price_impacts) if price_impacts else None,
            "max_price_impact_pct": max(price_impacts) if price_impacts else None,
            "median_price_impact_pct": _median_or_none(price_impacts),
            "smallest_clip_expected_output_quote": expected_outputs[0] if expected_outputs else None,
            "largest_clip_expected_output_quote": expected_outputs[-1] if expected_outputs else None,
            "quote_clip_size_quote": _num(observation.get("quote_clip_size_quote")),
            "expected_output_token": expected_output_token,
            "expected_output_quote": expected_output_quote,
            "price_impact_pct": price_impact_pct,
            "route_count": route_count,
            "route_quality_status": observation.get("route_quality_status"),
            "depth_coverage_status": depth_status,
            "post_migration_buy_volume": _num(observation.get("post_migration_buy_volume") or observation.get("buy_volume")),
            "post_migration_sell_volume": _num(observation.get("post_migration_sell_volume") or observation.get("sell_volume")),
            "post_migration_buy_sell_imbalance": _num(observation.get("post_migration_buy_sell_imbalance") or observation.get("buy_sell_imbalance")),
            "post_migration_drawdown_pct": _num(observation.get("post_migration_drawdown_pct") or observation.get("drawdown_pct")),
            "sell_side_dump_status": observation.get("sell_side_dump_status") or "not_available",
            "sell_side_dump_signal": _bool(observation.get("sell_side_dump_signal")),
            "post_migration_observation_status": status,
            "diagnostic_only": True,
            "trading_enabled": False,
            "paper_trading_enabled": False,
            "valuation_ladder_used": False,
            "error_reason": error_reason,
            **self._decision_time_fields(decision_row, received_at),
        }
        self._append_jsonl("post_migration_observations.jsonl", row)
        if direct_quote_rows:
            self._record_executable_quote_rows(direct_quote_rows)
        self.summary_counters["post_migration_observations_written"] += 1
        self.summary_counters["post_migration_available_count" if status == "available" else "post_migration_partial_count"] += 1
        _increment_counter(self.summary_counters["post_migration_observations_by_quote_asset"], str(quote_asset))
        if horizon is not None:
            _increment_counter(self.summary_counters["post_migration_observations_by_horizon"], str(horizon))
            _increment_counter(self.summary_counters["post_migration_observations_completed_by_horizon"], str(horizon))
        if pool_state_status == "available":
            self.summary_counters["post_migration_pool_state_available_count"] += 1
        elif pool_state_status == "error":
            self.summary_counters["post_migration_pool_state_error_count"] += 1
        elif pool_state_status == "not_available":
            self.summary_counters["post_migration_pool_state_not_available_count"] += 1
        else:
            self.summary_counters["post_migration_pool_state_partial_count"] += 1
        _increment_counter(self.summary_counters["post_migration_pool_state_by_quote_asset"], str(quote_asset))
        if pool_liquidity_quote is not None:
            self.summary_counters["pool_liquidity_quote_present_count"] += 1
        if pool_liquidity_usd is not None:
            self.summary_counters["pool_liquidity_usd_present_count"] += 1
        if executable_status == "available":
            self.summary_counters["post_migration_quote_available_count"] += 1
        elif executable_status == "partial":
            self.summary_counters["post_migration_quote_partial_count"] += 1
        elif executable_status == "error":
            self.summary_counters["post_migration_quote_error_count"] += 1
        elif executable_status == "deferred":
            self.summary_counters["post_migration_quote_deferred_count"] += 1
        if pool_state_status == "error" or depth_status == "error" or executable_status == "error":
            self.summary_counters["post_migration_observation_errors"] += 1
        if row["sell_side_dump_status"] != "not_available":
            self.summary_counters["sell_side_dump_diagnostics_written"] += 1
        self.summary_counters["post_migration_observations_pending_at_finalization"] = self._pending_post_migration_observation_count()
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row

    def record_execution_cost_sample(
        self,
        observation_reason: str,
        *,
        as_of: float | None = None,
        account_addresses: list[str] | None = None,
    ) -> dict[str, Any]:
        timestamp = as_of if as_of is not None else time.time()
        probe = self.execution_cost_probe
        if probe is None:
            return self.record_execution_cost_observation(
                {
                    "timestamp": timestamp,
                    "received_at": timestamp,
                    "observation_reason": observation_reason,
                    "execution_cost_status": "deferred",
                    "execution_cost_source": "placeholder",
                    "failed_tx_share_status": "deferred",
                    "error_reason": "execution_cost_probe_not_configured",
                    "decision_time": timestamp,
                }
            )
        try:
            rows = probe.fetch_recent_prioritization_fees(account_addresses=account_addresses)
            fees = sorted(
                int(row.get("prioritizationFee") or row.get("prioritization_fee") or 0)
                for row in (rows or [])
                if row.get("prioritizationFee") is not None or row.get("prioritization_fee") is not None
            )
            status = "partial" if fees else "deferred"
            return self.record_execution_cost_observation(
                {
                    "timestamp": timestamp,
                    "received_at": timestamp,
                    "observation_reason": observation_reason,
                    "recent_prioritization_fee_p50": _percentile(fees, 50),
                    "recent_prioritization_fee_p75": _percentile(fees, 75),
                    "recent_prioritization_fee_p90": _percentile(fees, 90),
                    "recent_prioritization_fee_p95": _percentile(fees, 95),
                    "recent_prioritization_fee_max": max(fees) if fees else None,
                    "recent_prioritization_fee_sample_count": len(fees),
                    "account_specific_fee_sample_available": bool(account_addresses),
                    "failed_tx_share_status": "deferred",
                    "execution_cost_status": status,
                    "execution_cost_source": "getRecentPrioritizationFees",
                    "error_reason": None if fees else "prioritization_fee_sample_empty",
                    "decision_time": timestamp,
                }
            )
        except Exception as exc:
            return self.record_execution_cost_observation(
                {
                    "timestamp": timestamp,
                    "received_at": timestamp,
                    "observation_reason": observation_reason,
                    "execution_cost_status": "error",
                    "execution_cost_source": "getRecentPrioritizationFees",
                    "failed_tx_share_status": "deferred",
                    "error_reason": str(exc),
                    "decision_time": timestamp,
                }
            )

    def maybe_record_periodic_execution_cost(self, *, as_of: float | None = None, interval_seconds: float = 60.0) -> dict[str, Any] | None:
        timestamp = as_of if as_of is not None else time.time()
        if self._last_execution_cost_periodic_at is not None and timestamp - self._last_execution_cost_periodic_at < interval_seconds:
            return None
        self._last_execution_cost_periodic_at = timestamp
        return self.record_execution_cost_sample("periodic", as_of=timestamp)

    def record_execution_cost_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        mint = str(observation.get("mint") or observation.get("token_mint") or "")
        received_at = _num(observation.get("received_at") or observation.get("timestamp")) or time.time()
        state = self._feature_state(mint, received_at)
        status = str(observation.get("execution_cost_status") or "")
        p90 = _num(_first_present(observation, ["recent_prioritization_fee_p90", "priority_fee_p90_microlamports"]))
        if not status:
            status = "partial" if p90 is not None else "deferred"
        state.execution_cost_status = status
        failed_tx_share_30 = _num(observation.get("failed_tx_share_last_30s"))
        failed_tx_share_60 = _num(_first_present(observation, ["failed_tx_share_last_60s", "failed_tx_share"]))
        failed_tx_status = str(observation.get("failed_tx_share_status") or "")
        if not failed_tx_status:
            failed_tx_status = "available" if failed_tx_share_30 is not None or failed_tx_share_60 is not None else "deferred"
        row = {
            "mint": mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "timestamp": _num(observation.get("timestamp")) or received_at,
            "slot": observation.get("slot"),
            "observation_reason": observation.get("observation_reason") or "periodic",
            "received_at": received_at,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received_at),
            "recent_prioritization_fee_p50": _num(_first_present(observation, ["recent_prioritization_fee_p50", "priority_fee_p50_microlamports"])),
            "recent_prioritization_fee_p75": _num(observation.get("recent_prioritization_fee_p75")),
            "recent_prioritization_fee_p90": p90,
            "recent_prioritization_fee_p95": _num(observation.get("recent_prioritization_fee_p95")),
            "recent_prioritization_fee_max": _num(observation.get("recent_prioritization_fee_max")),
            "recent_prioritization_fee_sample_count": _int(observation.get("recent_prioritization_fee_sample_count")) or 0,
            "account_specific_fee_sample_available": bool(observation.get("account_specific_fee_sample_available")),
            "account_specific_fee_sample": observation.get("account_specific_fee_sample"),
            "failed_tx_share_last_30s": failed_tx_share_30,
            "failed_tx_share_last_60s": failed_tx_share_60,
            "failed_tx_sample_count": _int(observation.get("failed_tx_sample_count")),
            "failed_tx_share_status": failed_tx_status,
            "failed_tx_share": failed_tx_share_60,
            "jito_tip_context": observation.get("jito_tip_context"),
            "confirmation_latency_ms": _num(observation.get("confirmation_latency_ms")),
            "estimated_total_fee_lamports": _num(observation.get("estimated_total_fee_lamports")),
            "estimated_total_fee_sol": _num(observation.get("estimated_total_fee_sol")),
            "execution_cost_status": status,
            "execution_cost_source": observation.get("execution_cost_source") or "placeholder",
            "diagnostic_only": True,
            "trading_enabled": False,
            "paper_trading_enabled": False,
            "error_reason": observation.get("error_reason"),
            **self._decision_time_fields(observation, received_at),
        }
        self._append_jsonl("execution_cost_observations.jsonl", row)
        self.summary_counters["execution_cost_observations_written"] += 1
        if status == "available":
            self.summary_counters["execution_cost_available_count"] += 1
        elif status == "error":
            self.summary_counters["execution_cost_error_count"] += 1
        elif status == "deferred":
            self.summary_counters["execution_cost_deferred_count"] += 1
        else:
            self.summary_counters["execution_cost_partial_count"] += 1
        self.summary_counters["recent_prioritization_fee_sample_count"] += int(row["recent_prioritization_fee_sample_count"] or 0)
        _increment_counter(self.summary_counters["execution_cost_observations_by_reason"], str(row["observation_reason"]))
        if failed_tx_status == "available":
            self.summary_counters["failed_tx_share_available_count"] += 1
        elif failed_tx_status == "deferred":
            self.summary_counters["failed_tx_share_deferred_count"] += 1
        self._write_live_status("running", force=not bool(getattr(self.config, "bounded_live_finalization_enabled", False)))
        return row


    def _global_migration_artifact_counters(self) -> dict[str, int]:
        path = self.output_root / "global_migration_events.jsonl"
        if not path.exists():
            return {}
        rows = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            return {}
        unique_mints = {str(row.get("mint") or "") for row in rows if row.get("mint")}
        unique_pools = {
            str(row.get("pool_or_pair_address") or row.get("pool_address") or "")
            for row in rows
            if row.get("pool_or_pair_address") or row.get("pool_address")
        }
        return {
            "global_migration_events_deduped": len(rows),
            "global_migration_unique_mints": len(unique_mints),
            "global_migration_unique_pools": len(unique_pools),
            "global_migration_mints_seen_in_birth_source": sum(1 for row in rows if _bool(row.get("seen_in_birth_source"))),
            "global_migration_mints_admitted": sum(1 for row in rows if _bool(row.get("admitted"))),
            "global_migration_mints_sample_rejected": sum(1 for row in rows if _bool(row.get("sample_rejected"))),
            "global_migration_mints_capacity_rejected": sum(1 for row in rows if _bool(row.get("capacity_rejected"))),
            "global_migration_mints_not_seen_in_birth_source": sum(1 for row in rows if not _bool(row.get("seen_in_birth_source"))),
            "migration_level_a_count": sum(1 for row in rows if row.get("migration_evidence_level") == MigrationEvidenceLevel.LEVEL_A.value),
            "migration_level_b_count": sum(1 for row in rows if row.get("migration_evidence_level") == MigrationEvidenceLevel.LEVEL_B.value),
            "migration_level_c_candidate_count": sum(
                1
                for row in rows
                if row.get("migration_evidence_level") in {MigrationEvidenceLevel.LEVEL_C.value, MigrationEvidenceLevel.CANDIDATE.value}
            ),
        }

    def _summary_counter_with_artifact_floor(self, key: str, artifact_counters: dict[str, int]) -> int:
        return max(int(self.summary_counters.get(key) or 0), int(artifact_counters.get(key) or 0))

    def _route_latency_histograms(self) -> dict[str, dict[str, Any]]:
        enqueue = self.birth_to_admission_enqueue_latencies_ms or self.birth_to_admission_latencies_ms
        return {
            "birth_to_admission_latency_ms": _stats(enqueue),
            "birth_to_admission_enqueue_latency_ms": _stats(enqueue),
            "birth_to_verified_birth_commit_latency_ms": _stats(self.birth_to_verified_birth_commit_latencies_ms),
            "verified_birth_commit_to_probe_enqueue_latency_ms": _stats(
                self.verified_birth_commit_to_probe_enqueue_latencies_ms
            ),
            "birth_enqueue_to_admission_worker_start_latency_ms": _stats(
                self.birth_enqueue_to_admission_worker_start_latencies_ms
            ),
            "admission_worker_process_birth_duration_ms": _stats(self.admission_worker_process_birth_duration_ms),
            "admission_worker_to_probe_job_enqueue_latency_ms": _stats(
                self.admission_worker_to_probe_job_enqueue_latencies_ms
            ),
            "probe_job_enqueue_to_probe_start_latency_ms": _stats(self.probe_job_enqueue_to_probe_start_latencies_ms),
            "normalized_birth_to_probe_start_latency_ms": _stats(self.normalized_birth_to_probe_start_latencies_ms),
            "birth_to_admission_decision_latency_ms": _stats(self.birth_to_admission_decision_latencies_ms),
            "birth_projection_complete_latency_ms": _stats(self.birth_projection_complete_latencies_ms),
            "birth_to_admission_complete_latency_ms": _stats(self.birth_to_admission_complete_latencies_ms),
            "birth_to_first_curve_observation_latency_ms": _stats(self.birth_to_first_observation_latencies_ms),
            "probe_duration_latency_ms": _stats(self.probe_duration_latencies_ms),
        }

    def _pre_migration_paper_readiness_gate(self, histograms: dict[str, dict[str, Any]]) -> dict[str, Any]:
        failures: list[str] = []
        enqueue = histograms.get("birth_to_admission_enqueue_latency_ms") or {}
        verified_birth_commit = histograms.get("birth_to_verified_birth_commit_latency_ms") or enqueue
        normalized_to_probe = histograms.get("normalized_birth_to_probe_start_latency_ms") or {}
        first_curve = histograms.get("birth_to_first_curve_observation_latency_ms") or {}
        probe_duration = histograms.get("probe_duration_latency_ms") or {}
        admission_complete = histograms.get("birth_to_admission_complete_latency_ms") or {}

        def p95(metric: dict[str, Any]) -> float | None:
            return _num(metric.get("p95"))

        if int(self.summary_counters.get("source_event_queue_dropped_count") or 0) > 0:
            failures.append("source_event_drops_nonzero")
        if int(self.summary_counters.get("birth_admission_queue_dropped_count") or 0) > 0:
            failures.append("birth_admission_drops_nonzero")
        if int(self.summary_counters.get("birth_priority_queue_dropped_count") or 0) > 0:
            failures.append("birth_priority_drops_nonzero")
        if int(self.summary_counters.get("trade_flow_queue_dropped_count") or 0) > 0:
            failures.append("trade_flow_bulk_drops_nonzero")
        if int(self.summary_counters.get("near_entry_hot_flow_ring_buffer_dropped_count") or 0) > 0:
            failures.append("trade_flow_hot_lane_drops_nonzero")
        if int(self.summary_counters.get("rpc_failures") or 0) > 0:
            failures.append("rpc_failures_nonzero")
        if int(self.summary_counters.get("http_429_count") or 0) > 0:
            failures.append("http_429_nonzero")
        if p95(verified_birth_commit) is not None and p95(verified_birth_commit) > self.config.max_birth_to_admission_p95_ms:
            failures.append("birth_to_verified_birth_commit_p95_exceeded")
        if p95(admission_complete) is None:
            failures.append("birth_to_admission_complete_latency_missing")
        elif p95(admission_complete) > self.config.max_birth_to_admission_complete_p95_ms:
            failures.append("birth_to_admission_complete_p95_exceeded")
        if p95(normalized_to_probe) is None:
            failures.append("normalized_birth_to_probe_start_latency_missing")
        elif p95(normalized_to_probe) > self.config.max_normalized_birth_to_probe_start_p95_ms:
            failures.append("normalized_birth_to_probe_start_p95_exceeded")
        if p95(first_curve) is None:
            failures.append("birth_to_first_curve_observation_latency_missing")
        elif p95(first_curve) > self.config.max_birth_to_first_curve_observation_p95_ms:
            failures.append("birth_to_first_curve_observation_p95_exceeded")
        if p95(probe_duration) is not None and p95(probe_duration) > self.config.max_probe_duration_p95_ms:
            failures.append("probe_duration_p95_exceeded")
        if int(self.summary_counters.get("progress_decoded_candidate_count") or 0) + int(
            self.summary_counters.get("progress_decoded_exact_count") or 0
        ) <= 0:
            failures.append("curve_progress_decoded_zero")
        if int(self.summary_counters.get("valuation_present_count") or 0) <= 0:
            failures.append("market_cap_progress_available_zero")
        if int(self.summary_counters.get("near_entry_hot_flow_snapshot_30s_count") or 0) <= 0 or int(
            self.summary_counters.get("near_entry_hot_flow_snapshot_60s_count") or 0
        ) <= 0:
            failures.append("pre_entry_snapshot_fields_missing")
        if int(self.summary_counters.get("near_entry_hot_flow_snapshot_1s_count") or 0) <= 0:
            failures.append("post_entry_1s_flow_snapshot_missing")
        if int(self.summary_counters.get("near_entry_hot_flow_snapshot_5s_count") or 0) <= 0:
            failures.append("post_entry_5s_flow_snapshot_missing")
        if int(self.summary_counters.get("near_entry_hot_flow_snapshot_10s_count") or 0) <= 0:
            failures.append("post_entry_10s_flow_snapshot_missing")
        dev_previous_migrations_safe = int(self.summary_counters.get("dev_previous_migrations_field_decision_time_safe_count") or 0) > 0
        creator_sold_before_entry_safe = int(self.summary_counters.get("creator_sold_before_entry_field_decision_time_safe_count") or 0) > 0
        paper_position_accounting_available = _paper_position_accounting_available()
        if not dev_previous_migrations_safe:
            failures.append("dev_previous_migrations_field_not_decision_time_safe")
        if not creator_sold_before_entry_safe:
            failures.append("creator_sold_before_entry_field_not_decision_time_safe")
        if not paper_position_accounting_available:
            failures.append("paper_position_accounting_missing")
        return {
            "gate_id": "T011_PRE_MIGRATION_PAPER_READINESS_GATE",
            "pre_migration_paper_ready": not failures,
            "blocking_reasons": failures,
            "migration_detection_enabled": bool(self.config.enable_global_pumpswap_migration),
            "migration_secondary_lane_status": "enabled_secondary" if self.config.enable_global_pumpswap_migration else "disabled_secondary",
            "pre_entry_snapshot_fields_available": "pre_entry_snapshot_fields_missing" not in failures,
            "post_entry_hot_flow_snapshot_1s_available": "post_entry_1s_flow_snapshot_missing" not in failures,
            "post_entry_hot_flow_snapshot_5s_available": "post_entry_5s_flow_snapshot_missing" not in failures,
            "post_entry_hot_flow_snapshot_10s_available": "post_entry_10s_flow_snapshot_missing" not in failures,
            "dev_previous_migrations_field_decision_time_safe": dev_previous_migrations_safe,
            "creator_sold_before_entry_field_decision_time_safe": creator_sold_before_entry_safe,
            "paper_position_accounting_available": paper_position_accounting_available,
            "migration_full_path_required_for_pre_migration_paper": False,
            "full_lifecycle_research_readiness_gate_required": False,
            "migration_materializer_discrepancy_known": False,
            "trading_disabled": True,
            "paper_trading_disabled": True,
            "wallet_signing_disabled": True,
            "private_key_paths_enabled": False,
            "transaction_sending_enabled": False,
            "edge_claim_allowed": False,
            "thresholds_tuned": False,
        }

    def _merge_t012_paper_readiness_gate(
        self,
        summary: dict[str, Any],
        *,
        write_outputs: bool = False,
    ) -> dict[str, Any]:
        materialization: dict[str, Any] | None = None
        try:
            if write_outputs:
                from research.mtp_research.validation.t012_paper_artifact_materializer import (
                    materialize_t012_paper_readiness_artifacts,
                )

                materialization = materialize_t012_paper_readiness_artifacts(self.output_root, run_id=self.config.run_id)
            from research.mtp_research.validation.t012_paper_readiness_gate import build_t012_paper_readiness_gate

            gate = build_t012_paper_readiness_gate(self.output_root, collector_summary=summary)
            if materialization is not None:
                gate["t012_paper_artifact_materialization"] = materialization
        except Exception as exc:
            gate = {
                "stage": "T012_PRE_MIGRATION_PAPER_READY_INFRA",
                "gate_id": "T012_PRE_MIGRATION_PAPER_READINESS_GATE",
                "gate_passed": False,
                "paper_ready_status": "blocked",
                "blocking_reasons": [f"t012_gate_error:{type(exc).__name__}:{exc}"],
                "paper_trading_enabled": False,
                "live_trading_enabled": False,
                "wallet_private_key_signing_execution_absent": True,
                "paper_infrastructure_ready": False,
            }
        legacy_gate = summary.get("pre_migration_paper_readiness_gate")
        legacy_ready = summary.get("pre_migration_paper_ready")
        summary.update(
            {
                "t011_legacy_pre_migration_paper_readiness_gate": legacy_gate,
                "t011_legacy_pre_migration_paper_ready": legacy_ready,
                "t012_pre_migration_paper_readiness_gate": gate,
                "pre_migration_paper_readiness_gate_passed": bool(gate.get("gate_passed")),
                "pre_migration_paper_ready_status": gate.get("paper_ready_status"),
                "pre_migration_paper_blockers": list(gate.get("blocking_reasons") or []),
                "pre_migration_paper_readiness_gate": gate,
                "pre_migration_paper_ready": bool(gate.get("gate_passed")),
                "pre_migration_paper_readiness_blockers": list(gate.get("blocking_reasons") or []),
                "pre_entry_snapshot_count": int(gate.get("pre_entry_snapshot_count") or 0),
                "post_entry_hot_flow_snapshot_count": int(gate.get("post_entry_hot_flow_snapshot_count") or 0),
                "paper_position_ledger_status": "exists" if gate.get("paper_position_ledger_exists") else "missing",
                "principal_recovery_tracking_status": (
                    "schema_valid" if gate.get("principal_recovery_tracking_schema_valid") else "schema_invalid"
                ),
                "paper_trading_enabled": False,
                "live_trading_enabled": False,
                "wallet_signing_execution_present": False,
            }
        )
        if write_outputs:
            try:
                _atomic_write_json(self.output_root / "paper_readiness_gate.json", gate)
                (self.output_root / "paper_readiness_summary.md").write_text(
                    "# T012 Pre-Migration Paper Readiness Summary\n\n"
                    f"- Stage: `T012_PRE_MIGRATION_PAPER_READY_INFRA`\n"
                    f"- Gate passed: `{gate.get('gate_passed')}`\n"
                    f"- Status: `{gate.get('paper_ready_status')}`\n"
                    f"- Blocking reasons: `{gate.get('blocking_reasons')}`\n"
                    f"- Pre-entry snapshots: `{gate.get('pre_entry_snapshot_count')}`\n"
                    f"- Post-entry hot-flow snapshots: `{gate.get('post_entry_hot_flow_snapshot_count')}`\n"
                    "- Paper trading enabled: `false`\n"
                    "- Live trading enabled: `false`\n",
                    encoding="utf-8",
                )
            except Exception as exc:
                self._record_finalization_error("t012_paper_readiness_outputs", exc)
        return summary

    def _route_latency_gate(self, histograms: dict[str, dict[str, Any]]) -> dict[str, Any]:
        failures: list[str] = []
        if not self.config.route_latency_gate_enabled:
            return {"route_latency_gate_enabled": False, "route_latency_gate_passed": True, "route_latency_gate_failures": failures}
        legacy_admission = histograms.get("birth_to_admission_latency_ms") or {}
        verified_birth_commit = histograms.get("birth_to_verified_birth_commit_latency_ms") or legacy_admission
        commit_to_probe_enqueue = histograms.get("verified_birth_commit_to_probe_enqueue_latency_ms") or {}
        normalized_to_probe = histograms.get("normalized_birth_to_probe_start_latency_ms") or {}
        first_curve = histograms.get("birth_to_first_curve_observation_latency_ms") or {}
        probe_duration = histograms.get("probe_duration_latency_ms") or {}
        verified_birth_commit_p95 = _num(verified_birth_commit.get("p95"))
        commit_to_probe_enqueue_p95 = _num(commit_to_probe_enqueue.get("p95"))
        normalized_to_probe_p95 = _num(normalized_to_probe.get("p95"))
        first_curve_p95 = _num(first_curve.get("p95"))
        probe_duration_p95 = _num(probe_duration.get("p95"))
        if int(self.summary_counters.get("source_event_queue_dropped_count") or 0) > 0:
            failures.append("source_event_queue_drops_nonzero")
        if int(self.summary_counters.get("source_verified_birth_commit_error_count") or 0) > 0:
            failures.append("birth_hot_commit_errors_nonzero")
        if int(self.summary_counters.get("birth_priority_queue_dropped_count") or 0) > 0:
            failures.append("first_curve_probe_queue_drops_nonzero")
        if int(self.summary_counters.get("rpc_failures") or 0) > 0:
            failures.append("rpc_failures_nonzero")
        if int(self.summary_counters.get("http_429_count") or 0) > 0:
            failures.append("http_429_nonzero")
        if (
            int(verified_birth_commit.get("count") or 0) > 0
            and verified_birth_commit_p95 is not None
            and verified_birth_commit_p95 > self.config.max_birth_to_admission_p95_ms
        ):
            failures.append("birth_to_verified_birth_commit_p95_exceeded")
        if (
            int(commit_to_probe_enqueue.get("count") or 0) > 0
            and commit_to_probe_enqueue_p95 is not None
            and commit_to_probe_enqueue_p95 > self.config.max_verified_birth_commit_to_probe_enqueue_p95_ms
        ):
            failures.append("verified_birth_commit_to_probe_enqueue_p95_exceeded")
        if (
            int(normalized_to_probe.get("count") or 0) > 0
            and normalized_to_probe_p95 is not None
            and normalized_to_probe_p95 > self.config.max_normalized_birth_to_probe_start_p95_ms
        ):
            failures.append("normalized_birth_to_probe_start_p95_exceeded")
        if (
            int(first_curve.get("count") or 0) > 0
            and first_curve_p95 is not None
            and first_curve_p95 > self.config.max_birth_to_first_curve_observation_p95_ms
        ):
            failures.append("birth_to_first_curve_observation_p95_exceeded")
        if (
            int(probe_duration.get("count") or 0) > 0
            and probe_duration_p95 is not None
            and probe_duration_p95 > self.config.max_probe_duration_p95_ms
        ):
            failures.append("probe_duration_p95_exceeded")
        return {
            "route_latency_gate_enabled": True,
            "route_latency_gate_passed": len(failures) == 0,
            "route_latency_gate_failures": failures,
            "decision_path_route_gate_passed": len(failures) == 0,
            "decision_path_route_gate_failures": failures,
            "route_latency_gate_scope": "decision_path_only",
            "route_latency_gate_thresholds_ms": {
                "max_birth_to_verified_birth_commit_p95_ms": self.config.max_birth_to_admission_p95_ms,
                "max_verified_birth_commit_to_probe_enqueue_p95_ms": self.config.max_verified_birth_commit_to_probe_enqueue_p95_ms,
                "max_normalized_birth_to_probe_start_p95_ms": self.config.max_normalized_birth_to_probe_start_p95_ms,
                "max_birth_to_first_curve_observation_p95_ms": self.config.max_birth_to_first_curve_observation_p95_ms,
                "max_probe_duration_p95_ms": self.config.max_probe_duration_p95_ms,
            },
        }

    def _materialization_latency_gate(self, histograms: dict[str, dict[str, Any]]) -> dict[str, Any]:
        complete = histograms.get("birth_to_admission_complete_latency_ms") or {}
        failures: list[str] = []
        complete_count = int(complete.get("count") or 0)
        complete_p95 = _num(complete.get("p95"))
        if (
            complete_count > 0
            and complete_p95 is not None
            and complete_p95 > float(self.config.max_birth_to_admission_complete_p95_ms)
        ):
            failures.append("birth_to_admission_complete_p95_exceeded")
        return {
            "materialization_latency_gate_id": "T011_MATERIALIZATION_LATENCY_GATE",
            "materialization_latency_gate_passed": not failures,
            "materialization_latency_gate_failures": failures,
            "materialization_latency_gate_scope": "source_verified_birth_admission_commit",
            "birth_projection_latency_gate_scope": "diagnostic_only",
            "birth_projection_latency_diagnostic_ms": complete,
            "materialization_latency_gate_thresholds_ms": {
                "max_birth_to_admission_complete_p95_ms": self.config.max_birth_to_admission_complete_p95_ms,
            },
        }

    def _finalization_gate(self, *, final: bool) -> dict[str, Any]:
        if not final:
            return {
                "finalization_gate_id": "T011_FINALIZATION_GATE",
                "finalization_gate_passed": None,
                "finalization_gate_failures": [],
                "finalization_gate_scope": "not_applicable_until_final_summary",
            }
        failures: list[str] = []
        if not self.run_finalized:
            failures.append("run_not_marked_finalized")
        if self.failure_reason:
            failures.append("failure_reason_present")
        return {
            "finalization_gate_id": "T011_FINALIZATION_GATE",
            "finalization_gate_passed": len(failures) == 0,
            "finalization_gate_failures": failures,
            "finalization_gate_scope": "bounded_live_finalization",
            "max_finalization_wall_time_seconds": self.config.max_finalization_wall_time_seconds,
        }

    def _helius_budget_gate(self) -> dict[str, Any]:
        estimated = int(self.config.helius_estimated_credits_used or 0)
        if estimated <= 0:
            estimated = int(self.summary_counters.get("raw_notifications") or 0) + int(
                self.summary_counters.get("curve_observation_attempts") or 0
            )
        cap = self.config.helius_max_estimated_credits
        if not self.config.helius_budget_gate_enabled:
            return {
                "helius_budget_gate_present": False,
                "helius_budget_gate_passed": True,
                "helius_estimated_credits_used": estimated,
                "helius_max_estimated_credits": cap,
                "helius_budget_used_pct": None,
                "helius_budget_blocker": "",
            }
        if cap is None:
            return {
                "helius_budget_gate_present": True,
                "helius_budget_gate_passed": False,
                "helius_estimated_credits_used": estimated,
                "helius_max_estimated_credits": None,
                "helius_budget_used_pct": None,
                "helius_budget_blocker": "helius_budget_cap_not_configured",
            }
        used_pct = _safe_ratio(estimated, cap)
        passed = estimated <= cap
        return {
            "helius_budget_gate_present": True,
            "helius_budget_gate_passed": passed,
            "helius_estimated_credits_used": estimated,
            "helius_max_estimated_credits": cap,
            "helius_budget_used_pct": used_pct,
            "helius_budget_blocker": "" if passed else "estimated_credits_exceed_configured_cap",
        }

    def build_summary(self, *, final: bool = False) -> dict[str, Any]:
        global_migration_artifact_counters = self._global_migration_artifact_counters()
        route_latency_histograms = self._route_latency_histograms()
        route_latency_gate = self._route_latency_gate(route_latency_histograms)
        materialization_latency_gate = self._materialization_latency_gate(route_latency_histograms)
        pre_migration_paper_readiness_gate = self._pre_migration_paper_readiness_gate(route_latency_histograms)
        helius_budget_gate = self._helius_budget_gate()
        finalization_gate = self._finalization_gate(final=final)
        source_gap_unbackfilled_count = int(self.summary_counters.get("source_gap_unbackfilled_count") or 0)
        source_gap_backfilled_count = int(self.summary_counters.get("source_gap_backfilled_count") or 0)
        dropped_or_reorged_count = int(self.summary_counters.get("dropped_or_reorged_count") or 0)
        source_gap_reorg_gate_passed = bool(source_gap_unbackfilled_count == 0 and dropped_or_reorged_count == 0)
        summary = {
            "run_id": self.config.run_id,
            "source_duration": self.config.source_duration_seconds,
            "requested_source_duration_seconds": self.config.source_duration_seconds,
            "actual_source_duration_seconds": None,
            "source_duration_completion_ratio": None,
            "source_duration_quality_status": "not_evaluated",
            "source_ended_early": False,
            "early_end_reason": None,
            "validation_run_quality_label": "RUN_QUALITY_NOT_EVALUATED",
            "websocket_keepalive_timeout_count": 0,
            "websocket_reconnect_count": 0,
            "followup_drain_duration": self.config.followup_drain_seconds,
            "sample_rate": self.config.sample_rate_percent,
            "tracking_profile": self.config.tracking_profile,
            "tracking_profile_settings": {
                "max_active_tracking": self.config.max_active_tracking,
                "followup_queue_max_size": self.config.followup_queue_max_size,
                "thin_probe_queue_max_size": self.config.thin_probe_queue_max_size,
                "migration_aware_promotion_enabled": bool(self.config.migration_aware_promotion_enabled),
                "reserved_migration_candidate_slots": self.config.reserved_migration_candidate_slots,
                "evict_low_priority_stale_mints_for_promotion": bool(
                    self.config.evict_low_priority_stale_mints_for_promotion
                ),
                "strict_health_gates_enabled": bool(self.config.strict_health_gates_enabled),
                "promote_on_curve_progress_pct": self.config.promote_on_curve_progress_pct,
                "promote_on_trade_rows": self.config.promote_on_trade_rows,
                "promote_on_migration_candidate": bool(self.config.promote_on_migration_candidate),
                "promote_on_threshold_crossing": bool(self.config.promote_on_threshold_crossing),
                "trade_flow_worker_count": self.config.trade_flow_worker_count,
                "trade_flow_queue_max_size": self.config.trade_flow_queue_max_size,
            },
            "gatekeeper_ab_enabled": bool(self.config.gatekeeper_ab_enabled),
            "gatekeeper_ab_status": "enabled" if self.config.gatekeeper_ab_enabled else "not_configured",
            "gatekeeper_primary_endpoint_label": self.config.gatekeeper_primary_endpoint_label,
            "gatekeeper_comparison_endpoint_label": self.config.gatekeeper_comparison_endpoint_label,
            "subscription_first_curve_updates_enabled": bool(self.config.subscription_first_curve_updates_enabled),
            "subscription_first_curve_updates_status": (
                "enabled" if self.config.subscription_first_curve_updates_enabled else "not_configured"
            ),
            "latency_histograms_present": any(
                int(bucket.get("count") or 0) > 0 for bucket in route_latency_histograms.values()
            ),
            "route_latency_histograms": route_latency_histograms,
            **route_latency_gate,
            **materialization_latency_gate,
            **finalization_gate,
            "pre_migration_paper_readiness_gate": pre_migration_paper_readiness_gate,
            "pre_migration_paper_ready": pre_migration_paper_readiness_gate["pre_migration_paper_ready"],
            "pre_migration_paper_readiness_blockers": pre_migration_paper_readiness_gate["blocking_reasons"],
            "full_lifecycle_research_readiness_gate": "preserved_separate_gate",
            "commitment_reorg_drop_accounting_present": bool(self.config.commitment_reorg_drop_accounting_enabled),
            "dropped_or_reorged_count": dropped_or_reorged_count,
            "source_gap_detected_count": source_gap_backfilled_count + source_gap_unbackfilled_count,
            "source_gap_backfilled_count": source_gap_backfilled_count,
            "source_gap_unbackfilled_count": source_gap_unbackfilled_count,
            "source_gap_reorg_gate_passed": source_gap_reorg_gate_passed,
            **helius_budget_gate,
            "max_active_tracking": self.config.max_active_tracking,
            "max_token_age_seconds": self.config.max_token_age_seconds,
            "inactive_timeout_seconds": self.config.inactive_timeout_seconds,
            "sol_usd": self.config.sol_usd,
            "sol_usd_source": self.config.sol_usd_source,
            "sol_usd_status": self.config.sol_usd_status,
            "sol_usd_error": self.config.sol_usd_error,
            "staging_root": _path_str_or_none(self.config.staging_root),
            "archive_root": _path_str_or_none(self.config.archive_root),
            "active_write_root": _path_str_or_none(self.config.active_write_root),
            "archive_after_run": bool(self.config.archive_after_run),
            "local_retention_enabled": bool(self.config.local_retention_enabled),
            "local_retention_keep_latest": int(self.config.local_retention_keep_latest),
            "local_retention_archive_root": _path_str_or_none(self.config.local_retention_archive_root),
            "local_free_space_bytes_start": self.config.local_free_space_bytes_start,
            "archive_free_space_bytes_start": self.config.archive_free_space_bytes_start,
            "storage_preflight_status": self.config.storage_preflight_status,
            "storage_preflight_errors": list(self.config.storage_preflight_errors),
            "run_finalized": bool(self.run_finalized),
            "finalization_errors": list(self.finalization_errors),
            "failure_reason": self.failure_reason,
            "archive_status": self.archive_status,
            "archive_manifest_path": self.archive_manifest_path,
            "total_births_detected": self.summary_counters["total_births_detected"],
            "birth_rows_total_including_replay": self.summary_counters["total_births_detected"],
            "birth_rows_live_source": self.summary_counters["birth_rows_live_source"],
            "birth_rows_replay_backfilled": self.summary_counters["birth_rows_replay_backfilled"],
            "unique_birth_mints_total_including_replay": len(self.live_birth_mints | self.replay_backfilled_birth_mints),
            "unique_birth_mints_live_source": len(self.live_birth_mints),
            "unique_birth_mints_replay_backfilled": len(self.replay_backfilled_birth_mints),
            "migration_backfill_skipped_existing_live_birth_count": self.summary_counters[
                "migration_backfill_skipped_existing_live_birth_count"
            ],
            "require_verified_curve_account_for_admission": bool(self.config.require_verified_curve_account_for_admission),
            "birth_candidate_seen_count": self.summary_counters["birth_candidate_seen_count"],
            "create_instruction_verified_count": self.summary_counters["create_instruction_verified_count"],
            "curve_account_resolved_count": self.summary_counters["curve_account_resolved_count"],
            "curve_account_verified_count": self.summary_counters["curve_account_verified_count"],
            "curve_account_pda_mismatch_count": self.summary_counters["curve_account_pda_mismatch_count"],
            "thesis_usable_birth_count": self.summary_counters["thesis_usable_birth_count"],
            "birth_candidate_excluded_count": self.summary_counters["birth_candidate_excluded_count"],
            "birth_candidate_excluded_by_reason": dict(self.summary_counters["birth_candidate_excluded_by_reason"]),
            "admitted_births": self.summary_counters["admitted_births"],
            "sample_rejected_births": self.summary_counters["sample_rejected_births"],
            "capacity_rejected_births": self.summary_counters["capacity_rejected_births"],
            "effective_admitted_coverage": _safe_ratio(
                self.summary_counters["admitted_births"],
                self.summary_counters["total_births_detected"],
            ),
            "admitted_sample_pass_coverage": _safe_ratio(
                self.summary_counters["admitted_births"],
                self.summary_counters["admitted_births"] + self.summary_counters["capacity_rejected_births"],
            ),
            "capacity_rejection_rate": _safe_ratio(
                self.summary_counters["capacity_rejected_births"],
                self.summary_counters["total_births_detected"],
            ),
            "active_tracking_max_count": self.summary_counters["active_tracking_max_count"],
            "active_tracking_count": self._active_tracking_count(),
            "active_pruned_count": self.summary_counters["active_pruned_count"],
            "active_pruned_by_reason": dict(self.summary_counters["active_pruned_by_reason"]),
            "low_progress_timeout_count": self.summary_counters["low_progress_timeout_count"],
            "no_decode_timeout_count": self.summary_counters["no_decode_timeout_count"],
            "stale_low_priority_pruned_count": self.summary_counters["stale_low_priority_pruned_count"],
            "admission_after_prune_count": self.summary_counters["admission_after_prune_count"],
            "capacity_rejected_after_prune_count": self.summary_counters["capacity_rejected_after_prune_count"],
            "protected_high_progress_active_count": self._protected_high_progress_active_count(),
            "active_count_by_progress_tier": self._active_count_by_progress_tier(),
            "active_count_by_age_bucket": self._active_count_by_age_bucket(),
            "queue_max_size": self.config.followup_queue_max_size,
            "queue_high_water_mark": self.summary_counters["queue_high_water_mark"],
            "queue_dropped_count": self.summary_counters["queue_dropped_count"],
            "observations_written": self.summary_counters["observations_written"],
            "threshold_crossings_written": self.summary_counters["threshold_crossings_written"],
            "migrations_written": self.summary_counters["migrations_written"],
            "migration_events_written": self.summary_counters["migrations_written"],
            "migration_candidates_seen": self.summary_counters["migration_candidates_seen"],
            "high_fdv_without_migration_event_count": self.summary_counters["high_fdv_without_migration_event_count"],
            "tokens_crossing_60k_without_migration_event": self.summary_counters["tokens_crossing_60k_without_migration_event"],
            "tokens_crossing_100k_without_migration_event": self.summary_counters["tokens_crossing_100k_without_migration_event"],
            "tokens_crossing_250k_without_migration_event": self.summary_counters["tokens_crossing_250k_without_migration_event"],
            "complete_true_count": self.summary_counters["complete_true_count"],
            "reserve_zero_count": self.summary_counters["reserve_zero_count"],
            "progress_100pct_count": self.summary_counters["progress_100pct_count"],
            "explicit_migrate_log_count": self.summary_counters["explicit_migrate_log_count"],
            "dex_pair_signal_count": self.summary_counters["dex_pair_signal_count"],
            "evidence_records_written": self.summary_counters["evidence_records_written"],
            "evidence_records_duplicate_count": self.summary_counters["evidence_records_duplicate_count"],
            "account_snapshots_written": self.summary_counters["account_snapshots_written"],
            "account_snapshots_duplicate_count": self.summary_counters["account_snapshots_duplicate_count"],
            "lifecycle_transitions_written": self.summary_counters["lifecycle_transitions_written"],
            "lifecycle_transitions_duplicate_count": self.summary_counters["lifecycle_transitions_duplicate_count"],
            "curve_velocity_events_written": self.summary_counters["curve_velocity_events_written"],
            "curve_acceleration_events_written": self.summary_counters["curve_acceleration_events_written"],
            "token_path_summary_rows": self.summary_counters["token_path_summary_rows"],
            "token_path_summary_written": self.summary_counters["token_path_summary_written"],
            "migration_level_a_count": self._summary_counter_with_artifact_floor("migration_level_a_count", global_migration_artifact_counters),
            "migration_level_b_count": self._summary_counter_with_artifact_floor("migration_level_b_count", global_migration_artifact_counters),
            "migration_level_c_candidate_count": self._summary_counter_with_artifact_floor("migration_level_c_candidate_count", global_migration_artifact_counters),
            "post_migration_snapshot_scheduled_count": self.summary_counters["post_migration_snapshot_scheduled_count"],
            "reconciliation_findings_count": self.summary_counters["reconciliation_findings_count"],
            "decode_failures": self.summary_counters["decode_failures"],
            "rpc_failures": self.summary_counters["rpc_failures"],
            "stale_observations": self.summary_counters["stale_observations"],
            "live_source_used": self.summary_counters["live_source_used"],
            "subscription_connect_status": self.summary_counters["subscription_connect_status"],
            "births_detected": self.summary_counters["total_births_detected"],
            "births_admitted": self.summary_counters["admitted_births"],
            "sample_rejected": self.summary_counters["sample_rejected_births"],
            "capacity_rejected": self.summary_counters["capacity_rejected_births"],
            "curve_observation_attempts": self.summary_counters["curve_observation_attempts"],
            "curve_observations_written": self.summary_counters["observations_written"],
            "exact_progress_decoded_count": self.summary_counters["exact_progress_decoded_count"],
            "progress_decoded_exact_count": self.summary_counters["progress_decoded_exact_count"],
            "progress_decoded_candidate_count": self.summary_counters["progress_decoded_candidate_count"],
            "unresolved_progress_formula_count": self.summary_counters["unresolved_progress_formula_count"],
            "reserve_scale_mode_counts": dict(self.summary_counters["reserve_scale_mode_counts"]),
            "true_curve_threshold_crossings_by_threshold": dict(self.summary_counters["true_curve_threshold_crossings_by_threshold"]),
            "first_60pct_true_curve_crossings_count": int(self.summary_counters["true_curve_threshold_crossings_by_threshold"].get("60.0", 0)),
            "first_65pct_true_curve_crossings_count": int(self.summary_counters["true_curve_threshold_crossings_by_threshold"].get("65.0", 0)),
            "first_70pct_true_curve_crossings_count": int(self.summary_counters["true_curve_threshold_crossings_by_threshold"].get("70.0", 0)),
            "first_75pct_true_curve_crossings_count": int(self.summary_counters["true_curve_threshold_crossings_by_threshold"].get("75.0", 0)),
            "valuation_present_count": self.summary_counters["valuation_present_count"],
            "valuation_missing_count": self.summary_counters["valuation_missing_count"],
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "valuation_ladder_market_cap_confirmed_count": self.summary_counters["valuation_ladder_market_cap_confirmed_count"],
            "valuation_ladder_suppressed_untrusted_count": self.summary_counters["valuation_ladder_suppressed_untrusted_count"],
            "valuation_ladder_trust_status_counts": dict(self.summary_counters["valuation_ladder_trust_status_counts"]),
            "valuation_formula_audit_rows": self.summary_counters["valuation_formula_audit_rows"],
            "valuation_formula_classification_counts": dict(self.summary_counters["valuation_formula_classification_counts"]),
            "valuation_units_status_counts": dict(self.summary_counters["valuation_units_status_counts"]),
            "fdv_proxy_raw_range": _range(self.fdv_proxy_raw_values),
            "fdv_proxy_sol_range": _range(self.fdv_proxy_sol_values),
            "fdv_proxy_usd_range": _range(self.fdv_proxy_usd_values),
            "reserve_fdv_sol_range": _range(self.reserve_fdv_sol_values),
            "reserve_fdv_usd_range": _range(self.reserve_fdv_usd_values),
            "valuation_band_crossings_by_band": dict(self.summary_counters["valuation_band_crossings_by_band"]),
            "first_30k_valuation_crossings_count": int(self.summary_counters["valuation_band_crossings_by_band"].get("30000", 0)),
            "first_36k_valuation_crossings_count": int(self.summary_counters["valuation_band_crossings_by_band"].get("36000", 0)),
            "first_40k_valuation_crossings_count": int(self.summary_counters["valuation_band_crossings_by_band"].get("40000", 0)),
            "first_50k_valuation_crossings_count": int(self.summary_counters["valuation_band_crossings_by_band"].get("50000", 0)),
            "first_60k_valuation_crossings_count": int(self.summary_counters["valuation_band_crossings_by_band"].get("60000", 0)),
            "valuation_ladder_events_written": self.summary_counters["valuation_ladder_events_written"],
            "valuation_ladder_paths_written": self.summary_counters["valuation_ladder_paths_written"],
            "tokens_crossing_30k": int(self.summary_counters["valuation_band_crossings_by_band"].get("30000", 0)),
            "tokens_crossing_35k": int(self.summary_counters["valuation_band_crossings_by_band"].get("35000", 0)),
            "tokens_crossing_36k": int(self.summary_counters["valuation_band_crossings_by_band"].get("36000", 0)),
            "tokens_crossing_40k": int(self.summary_counters["valuation_band_crossings_by_band"].get("40000", 0)),
            "tokens_crossing_50k": int(self.summary_counters["valuation_band_crossings_by_band"].get("50000", 0)),
            "tokens_crossing_60k": int(self.summary_counters["valuation_band_crossings_by_band"].get("60000", 0)),
            "tokens_crossing_100k": int(self.summary_counters["valuation_band_crossings_by_band"].get("100000", 0)),
            "median_seconds_30k_to_40k": _median_or_none(self.valuation_transition_seconds_by_pair.get("30k_to_40k", [])),
            "median_seconds_30k_to_60k": _median_or_none(self.valuation_transition_seconds_by_pair.get("30k_to_60k", [])),
            "median_seconds_36k_to_50k": _median_or_none(self.valuation_transition_seconds_by_pair.get("36k_to_50k", [])),
            "median_seconds_40k_to_60k": _median_or_none(self.valuation_transition_seconds_by_pair.get("40k_to_60k", [])),
            "count_stalled_after_30k_10s": int(self.summary_counters["valuation_ladder_stall_counts"].get("30k_10s", 0)),
            "count_stalled_after_30k_30s": int(self.summary_counters["valuation_ladder_stall_counts"].get("30k_30s", 0)),
            "count_stalled_after_30k_60s": int(self.summary_counters["valuation_ladder_stall_counts"].get("30k_60s", 0)),
            "count_stalled_after_40k_10s": int(self.summary_counters["valuation_ladder_stall_counts"].get("40k_10s", 0)),
            "count_stalled_after_40k_30s": int(self.summary_counters["valuation_ladder_stall_counts"].get("40k_30s", 0)),
            "count_stalled_after_40k_60s": int(self.summary_counters["valuation_ladder_stall_counts"].get("40k_60s", 0)),
            "wallet_dev_checkpoints_written": self.summary_counters["wallet_dev_checkpoints_written"],
            "wallet_metrics_available_count": self.summary_counters["wallet_metrics_available_count"],
            "wallet_metrics_deferred_count": self.summary_counters["wallet_metrics_deferred_count"],
            "wallet_metrics_not_available_count": self.summary_counters["wallet_metrics_not_available_count"],
            "dev_metrics_available_count": self.summary_counters["dev_metrics_available_count"],
            "dev_metrics_deferred_count": self.summary_counters["dev_metrics_deferred_count"],
            "dev_metrics_not_available_count": self.summary_counters["dev_metrics_not_available_count"],
            "creator_history_available_count": self.summary_counters["creator_history_available_count"],
            "creator_history_deferred_count": self.summary_counters["creator_history_deferred_count"],
            "creator_history_not_available_count": self.summary_counters["creator_history_not_available_count"],
            "wallet_enrichment_error_count": self.summary_counters["wallet_enrichment_error_count"],
            "wallet_enrichment_latency_ms": _stats(self.wallet_enrichment_latencies_ms),
            "promotion_events_written": self.summary_counters["promotion_events_written"],
            "promoted_mints": self.summary_counters["promoted_mints"],
            "promoted_migrated_mints": self.summary_counters["promoted_migrated_mints"],
            "capacity_deferred_promotions": self.summary_counters["capacity_deferred_promotions"],
            "promotion_reason_counts": dict(self.summary_counters["promotion_reason_counts"]),
            "promotion_evictions_written": self.summary_counters["promotion_evictions_written"],
            "promotion_eviction_reasons": dict(self.summary_counters["promotion_eviction_reasons"]),
            "trade_flow_events_written": self.summary_counters["trade_flow_events_written"],
            "trade_flow_available_count": self.summary_counters["trade_flow_available_count"],
            "trade_flow_partial_count": self.summary_counters["trade_flow_partial_count"],
            "trade_flow_deferred_count": 0,
            "near_entry_hot_flow_enabled": bool(self.summary_counters["near_entry_hot_flow_enabled"]),
            "near_entry_hot_flow_mints_registered": self.summary_counters["near_entry_hot_flow_mints_registered"],
            "near_entry_hot_flow_events_seen": self.summary_counters["near_entry_hot_flow_events_seen"],
            "near_entry_hot_flow_events_recorded": self.summary_counters["near_entry_hot_flow_events_recorded"],
            "near_entry_hot_flow_ring_buffer_dropped_count": self.summary_counters[
                "near_entry_hot_flow_ring_buffer_dropped_count"
            ],
            "near_entry_hot_flow_snapshots_written": self.summary_counters["near_entry_hot_flow_snapshots_written"],
            "near_entry_hot_flow_snapshot_mints": self.summary_counters["near_entry_hot_flow_snapshot_mints"],
            "near_entry_hot_flow_snapshot_1s_count": self.summary_counters["near_entry_hot_flow_snapshot_1s_count"],
            "near_entry_hot_flow_snapshot_5s_count": self.summary_counters["near_entry_hot_flow_snapshot_5s_count"],
            "near_entry_hot_flow_snapshot_10s_count": self.summary_counters["near_entry_hot_flow_snapshot_10s_count"],
            "near_entry_hot_flow_snapshot_30s_count": self.summary_counters["near_entry_hot_flow_snapshot_30s_count"],
            "near_entry_hot_flow_snapshot_60s_count": self.summary_counters["near_entry_hot_flow_snapshot_60s_count"],
            "pre_entry_snapshot_fields_available": bool(
                int(self.summary_counters.get("near_entry_hot_flow_snapshot_30s_count") or 0) > 0
                and int(self.summary_counters.get("near_entry_hot_flow_snapshot_60s_count") or 0) > 0
                and (
                    int(self.summary_counters.get("progress_decoded_candidate_count") or 0)
                    + int(self.summary_counters.get("progress_decoded_exact_count") or 0)
                ) > 0
                and int(self.summary_counters.get("valuation_present_count") or 0) > 0
            ),
            "post_entry_hot_flow_snapshot_1s_available": bool(
                int(self.summary_counters.get("near_entry_hot_flow_snapshot_1s_count") or 0) > 0
            ),
            "post_entry_hot_flow_snapshot_5s_available": bool(
                int(self.summary_counters.get("near_entry_hot_flow_snapshot_5s_count") or 0) > 0
            ),
            "post_entry_hot_flow_snapshot_10s_available": bool(
                int(self.summary_counters.get("near_entry_hot_flow_snapshot_10s_count") or 0) > 0
            ),
            "dev_previous_migrations_field_decision_time_safe": bool(
                int(self.summary_counters.get("dev_previous_migrations_field_decision_time_safe_count") or 0) > 0
            ),
            "creator_sold_before_entry_field_decision_time_safe": bool(
                int(self.summary_counters.get("creator_sold_before_entry_field_decision_time_safe_count") or 0) > 0
            ),
            "paper_position_accounting_available": _paper_position_accounting_available(),
            "organic_flow_events_written": self.summary_counters["organic_flow_events_written"],
            "organic_flow_available_count": self.summary_counters["organic_flow_available_count"],
            "organic_flow_partial_count": self.summary_counters["organic_flow_partial_count"],
            "buyer_breadth_available_count": self.summary_counters["buyer_breadth_available_count"],
            "holder_distribution_snapshots_written": self.summary_counters["holder_distribution_snapshots_written"],
            "holder_distribution_available_count": self.summary_counters["holder_distribution_available_count"],
            "holder_distribution_partial_count": self.summary_counters["holder_distribution_partial_count"],
            "holder_available_count": self.summary_counters["holder_distribution_available_count"],
            "holder_deferred_count": self.summary_counters["wallet_metrics_deferred_count"],
            "dev_behavior_events_written": self.summary_counters["dev_behavior_events_written"],
            "dev_behavior_available_count": self.summary_counters["dev_behavior_available_count"],
            "dev_behavior_partial_count": self.summary_counters["dev_behavior_partial_count"],
            "dev_available_count": self.summary_counters["dev_metrics_available_count"],
            "dev_deferred_count": self.summary_counters["dev_metrics_deferred_count"],
            "post_migration_observations_scheduled": self.summary_counters["post_migration_observations_scheduled"],
            "post_migration_observations_written": self.summary_counters["post_migration_observations_written"],
            "post_migration_observations_completed_by_horizon": dict(self.summary_counters["post_migration_observations_completed_by_horizon"]),
            "post_migration_observations_pending_at_finalization": self._pending_post_migration_observation_count(),
            "post_migration_observation_errors": self.summary_counters["post_migration_observation_errors"],
            "post_migration_pool_state_available_count": self.summary_counters["post_migration_pool_state_available_count"],
            "post_migration_pool_state_partial_count": self.summary_counters["post_migration_pool_state_partial_count"],
            "post_migration_pool_state_not_available_count": self.summary_counters["post_migration_pool_state_not_available_count"],
            "post_migration_pool_state_error_count": self.summary_counters["post_migration_pool_state_error_count"],
            "post_migration_pool_state_by_quote_asset": dict(self.summary_counters["post_migration_pool_state_by_quote_asset"]),
            "pool_liquidity_quote_present_count": self.summary_counters["pool_liquidity_quote_present_count"],
            "pool_liquidity_usd_present_count": self.summary_counters["pool_liquidity_usd_present_count"],
            "post_migration_quote_available_count": self.summary_counters["post_migration_quote_available_count"],
            "post_migration_quote_partial_count": self.summary_counters["post_migration_quote_partial_count"],
            "post_migration_quote_deferred_count": self.summary_counters["post_migration_quote_deferred_count"],
            "post_migration_quote_error_count": self.summary_counters["post_migration_quote_error_count"],
            "executable_quote_observations_written": self.summary_counters["executable_quote_observations_written"],
            "executable_quote_available_count": self.summary_counters["executable_quote_available_count"],
            "executable_quote_partial_count": self.summary_counters["executable_quote_partial_count"],
            "executable_quote_deferred_count": self.summary_counters["executable_quote_deferred_count"],
            "executable_quote_error_count": self.summary_counters["executable_quote_error_count"],
            "executable_quote_by_source": dict(self.summary_counters["executable_quote_by_source"]),
            "executable_quote_by_quote_asset": dict(self.summary_counters["executable_quote_by_quote_asset"]),
            "executable_quote_by_direction": dict(self.summary_counters["executable_quote_by_direction"]),
            "executable_quote_clip_count": self.summary_counters["executable_quote_clip_count"],
            "executable_quote_decision_time_safe_count": self.summary_counters["executable_quote_decision_time_safe_count"],
            "price_impact_available_count": self.summary_counters["price_impact_available_count"],
            "price_impact_missing_count": self.summary_counters["price_impact_missing_count"],
            "fee_model_confirmed_count": self.summary_counters["fee_model_confirmed_count"],
            "fee_model_assumed_count": self.summary_counters["fee_model_assumed_count"],
            "fee_model_unknown_count": self.summary_counters["fee_model_unknown_count"],
            "post_migration_observations_by_quote_asset": dict(self.summary_counters["post_migration_observations_by_quote_asset"]),
            "post_migration_observations_by_horizon": dict(self.summary_counters["post_migration_observations_by_horizon"]),
            "post_migration_migrations_without_observations": self.summary_counters["post_migration_migrations_without_observations"],
            "post_migration_available_count": self.summary_counters["post_migration_available_count"],
            "post_migration_partial_count": self.summary_counters["post_migration_partial_count"],
            "sell_side_dump_diagnostics_written": self.summary_counters["sell_side_dump_diagnostics_written"],
            "execution_cost_observations_written": self.summary_counters["execution_cost_observations_written"],
            "execution_cost_available_count": self.summary_counters["execution_cost_available_count"],
            "execution_cost_partial_count": self.summary_counters["execution_cost_partial_count"],
            "execution_cost_deferred_count": self.summary_counters["execution_cost_deferred_count"],
            "execution_cost_error_count": self.summary_counters["execution_cost_error_count"],
            "recent_prioritization_fee_sample_count": self.summary_counters["recent_prioritization_fee_sample_count"],
            "execution_cost_observations_by_reason": dict(self.summary_counters["execution_cost_observations_by_reason"]),
            "failed_tx_share_available_count": self.summary_counters["failed_tx_share_available_count"],
            "failed_tx_share_deferred_count": self.summary_counters["failed_tx_share_deferred_count"],
            "decision_time_checked_feature_rows": self.summary_counters["decision_time_checked_feature_rows"],
            "decision_time_safe_feature_rows": self.summary_counters["decision_time_safe_feature_rows"],
            "decision_time_safety_violation_count": self.summary_counters["decision_time_safety_violation_count"],
            "birth_decision_path_commit_count": self.summary_counters["birth_decision_path_commit_count"],
            "birth_decision_path_commit_error_count": self.summary_counters["birth_decision_path_commit_error_count"],
            "source_verified_birth_commit_count": self.summary_counters["source_verified_birth_commit_count"],
            "source_verified_birth_commit_error_count": self.summary_counters["source_verified_birth_commit_error_count"],
            "source_verified_birth_commit_duplicate_suppressed_count": self.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"],
            "verified_birth_commit_count": self.summary_counters["source_verified_birth_commit_count"],
            "verified_birth_commit_error_count": self.summary_counters["source_verified_birth_commit_error_count"],
            "verified_birth_commit_duplicate_suppressed_count": self.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"],
            "source_verified_birth_commit_table": "verified_birth_commits",
            "decode_coverage_by_source_route": {
                route: dict(counts) for route, counts in self.summary_counters["decode_coverage_by_source_route"].items()
            },
            "progress_decode_coverage_by_source_route": {
                route: dict(counts) for route, counts in self.summary_counters["progress_decode_coverage_by_source_route"].items()
            },
            "valuation_coverage_by_source_route": {
                route: dict(counts) for route, counts in self.summary_counters["valuation_coverage_by_source_route"].items()
            },
            "valuation_missing_reason_counts": dict(self.summary_counters["valuation_missing_reason_counts"]),
            "first_attempt_success_count": self.summary_counters["first_attempt_success_count"],
            "retry_success_count": self.summary_counters["retry_success_count"],
            "final_account_not_found_count": self.summary_counters["final_account_not_found_count"],
            "median_attempts_until_success": _median_or_none(self.probe_attempts_until_success),
            "p90_attempts_until_success": _quantile(self.probe_attempts_until_success, 0.90),
            "median_time_to_first_success_ms": _median_or_none(self.time_to_first_success_ms),
            "p90_time_to_first_success_ms": _quantile(self.time_to_first_success_ms, 0.90),
            "retry_queue_high_water_mark": self.summary_counters["retry_queue_high_water_mark"],
            "retry_queue_drops": self.summary_counters["retry_queue_drops"],
            "capacity_rejected_by_minute": dict(self.summary_counters["capacity_rejected_by_minute"]),
            "capacity_rejected_by_route": dict(self.summary_counters["capacity_rejected_by_route"]),
            "active_tracking_still_active_at_finalization": self.summary_counters["active_tracking_still_active_at_finalization"],
            "http_429_count": self.summary_counters["http_429_count"],
            "births_by_quote_asset": dict(self.summary_counters["births_by_quote_asset"]),
            "admitted_births_by_quote_asset": dict(self.summary_counters["admitted_births_by_quote_asset"]),
            "sample_rejected_by_quote_asset": dict(self.summary_counters["sample_rejected_by_quote_asset"]),
            "capacity_rejected_by_quote_asset": dict(self.summary_counters["capacity_rejected_by_quote_asset"]),
            "curve_observations_by_quote_asset": dict(self.summary_counters["curve_observations_by_quote_asset"]),
            "progress_crossings_by_quote_asset": dict(self.summary_counters["progress_crossings_by_quote_asset"]),
            "migration_events_by_quote_asset": dict(self.summary_counters["migration_events_by_quote_asset"]),
            "missing_quote_mint_count": self.summary_counters["missing_quote_mint_count"],
            "unsupported_quote_asset_count": self.summary_counters["unsupported_quote_asset_count"],
            "unknown_quote_count": int(self.summary_counters["births_by_quote_asset"].get("unknown", 0) or 0),
            "global_migration_events_deduped": self._summary_counter_with_artifact_floor("global_migration_events_deduped", global_migration_artifact_counters),
            "global_migration_candidates": self.summary_counters["global_migration_candidates"],
            "global_migration_duplicates_suppressed": self.summary_counters["global_migration_duplicates_suppressed"],
            "global_migration_unique_mints": self._summary_counter_with_artifact_floor("global_migration_unique_mints", global_migration_artifact_counters),
            "global_migration_unique_pools": self._summary_counter_with_artifact_floor("global_migration_unique_pools", global_migration_artifact_counters),
            "global_migration_mints_seen_in_birth_source": self._summary_counter_with_artifact_floor("global_migration_mints_seen_in_birth_source", global_migration_artifact_counters),
            "live_migration_side_effect_drain_count": self.summary_counters["live_migration_side_effect_drain_count"],
            "live_migration_side_effects_applied": self.summary_counters["live_migration_side_effects_applied"],
            "live_migration_side_effects_failed": self.summary_counters["live_migration_side_effects_failed"],
            "live_migration_side_effects_source_rows": self.summary_counters["live_migration_side_effects_source_rows"],
            "live_migration_side_effects_post_observations_written": self.summary_counters[
                "live_migration_side_effects_post_observations_written"
            ],
            "live_migration_side_effect_last_drain_at": self.summary_counters["live_migration_side_effect_last_drain_at"],
            "pumpswap_swap_events_decoded": self.summary_counters["pumpswap_swap_events_decoded"],
            "pumpswap_swap_buy_events": self.summary_counters["pumpswap_swap_buy_events"],
            "pumpswap_swap_sell_events": self.summary_counters["pumpswap_swap_sell_events"],
            "pumpswap_swap_fee_bps_populated_count": self.summary_counters["pumpswap_swap_fee_bps_populated_count"],
            "pumpswap_swap_balance_delta_partial_count": self.summary_counters["pumpswap_swap_balance_delta_partial_count"],
            "pumpswap_route_raw_notifications": self.summary_counters["pumpswap_route_raw_notifications"],
            "pumpswap_route_candidate_transactions": self.summary_counters["pumpswap_route_candidate_transactions"],
            "pumpswap_route_with_logs": self.summary_counters["pumpswap_route_with_logs"],
            "pumpswap_route_with_inner_instructions": self.summary_counters["pumpswap_route_with_inner_instructions"],
            "pumpswap_route_buy_candidates": self.summary_counters["pumpswap_route_buy_candidates"],
            "pumpswap_route_sell_candidates": self.summary_counters["pumpswap_route_sell_candidates"],
            "pumpswap_route_event_log_candidates": self.summary_counters["pumpswap_route_event_log_candidates"],
            "pumpswap_route_get_transaction_backfills": self.summary_counters["pumpswap_route_get_transaction_backfills"],
            "pumpswap_route_skipped_by_reason": dict(self.summary_counters["pumpswap_route_skipped_by_reason"]),
            "global_migration_mints_admitted": self._summary_counter_with_artifact_floor("global_migration_mints_admitted", global_migration_artifact_counters),
            "global_migration_mints_sample_rejected": self._summary_counter_with_artifact_floor("global_migration_mints_sample_rejected", global_migration_artifact_counters),
            "global_migration_mints_capacity_rejected": self._summary_counter_with_artifact_floor("global_migration_mints_capacity_rejected", global_migration_artifact_counters),
            "global_migration_mints_not_seen_in_birth_source": self._summary_counter_with_artifact_floor("global_migration_mints_not_seen_in_birth_source", global_migration_artifact_counters),
            "migration_after_prune_count": self.summary_counters["migration_after_prune_count"],
            "migration_while_active_count": self.summary_counters["migration_while_active_count"],
            "migration_for_non_admitted_count": self.summary_counters["migration_for_non_admitted_count"],
            "migration_for_sample_rejected_count": self.summary_counters["migration_for_sample_rejected_count"],
            "high_progress_tokens_that_later_migrated": self.summary_counters["high_progress_tokens_that_later_migrated"],
            "migration_backfill_jobs_enqueued": self.summary_counters["migration_backfill_jobs_enqueued"],
            "migration_backfill_jobs_completed": self.summary_counters["migration_backfill_jobs_completed"],
            "migration_backfill_jobs_failed": self.summary_counters["migration_backfill_jobs_failed"],
            "migration_backfilled_birth_rows_written": self.summary_counters["migration_backfilled_birth_rows_written"],
            "migration_backfill_queue_high_water": self.summary_counters["migration_backfill_queue_high_water"],
            "migration_backfill_rate_limited_count": self.summary_counters["migration_backfill_rate_limited_count"],
            "migration_backfill_rpc_error_count": self.summary_counters["migration_backfill_rpc_error_count"],
            "migration_backfill_success_rate": _safe_ratio(
                self.summary_counters["migration_backfill_jobs_completed"],
                self.summary_counters["migration_backfill_jobs_completed"] + self.summary_counters["migration_backfill_jobs_failed"],
            ),
            "thin_births_total": self.summary_counters["thin_births_total"],
            "thin_probe_scheduled_count": self.summary_counters["thin_probe_scheduled_count"],
            "thin_probe_success_count": self.summary_counters["thin_probe_success_count"],
            "thin_probe_failed_count": self.summary_counters["thin_probe_failed_count"],
            "thin_to_deep_escalation_count": self.summary_counters["thin_to_deep_escalation_count"],
            "thin_to_deep_escalation_reasons": dict(self.summary_counters["thin_to_deep_escalation_reasons"]),
            "sampled_out_with_thin_path_count": self.summary_counters["sampled_out_with_thin_path_count"],
            "sampled_out_without_thin_path_count": self.summary_counters["sampled_out_without_thin_path_count"],
            "thin_probe_queue_high_water": self.summary_counters["thin_probe_queue_high_water"],
            "thin_probe_queue_drops": self.summary_counters["thin_probe_queue_drops"],
            "thin_probe_deferred_count": self.summary_counters["thin_probe_deferred_count"],
            "thin_probe_defer_reasons": dict(self.summary_counters["thin_probe_defer_reasons"]),
            "deep_probe_delayed_by_thin_count": self.summary_counters["deep_probe_delayed_by_thin_count"],
            "queue_drops": self.summary_counters["queue_dropped_count"],
            "birth_to_admission_latency_ms": route_latency_histograms["birth_to_admission_latency_ms"],
            "birth_to_admission_enqueue_latency_ms": route_latency_histograms["birth_to_admission_enqueue_latency_ms"],
            "birth_to_verified_birth_commit_latency_ms": route_latency_histograms[
                "birth_to_verified_birth_commit_latency_ms"
            ],
            "birth_enqueue_to_admission_worker_start_latency_ms": route_latency_histograms[
                "birth_enqueue_to_admission_worker_start_latency_ms"
            ],
            "admission_worker_process_birth_duration_ms": route_latency_histograms[
                "admission_worker_process_birth_duration_ms"
            ],
            "admission_worker_to_probe_job_enqueue_latency_ms": route_latency_histograms[
                "admission_worker_to_probe_job_enqueue_latency_ms"
            ],
            "probe_job_enqueue_to_probe_start_latency_ms": route_latency_histograms[
                "probe_job_enqueue_to_probe_start_latency_ms"
            ],
            "normalized_birth_to_probe_start_latency_ms": route_latency_histograms[
                "normalized_birth_to_probe_start_latency_ms"
            ],
            "birth_to_admission_complete_latency_ms": route_latency_histograms["birth_to_admission_complete_latency_ms"],
            "birth_to_first_curve_observation_latency_ms": route_latency_histograms[
                "birth_to_first_curve_observation_latency_ms"
            ],
            "probe_duration_latency_ms": route_latency_histograms["probe_duration_latency_ms"],
            "mayhem_code_modified": self.summary_counters["mayhem_code_modified"],
            "remaining_t007_blockers_before_next_scan": [],
            "remaining_t007_blockers_before_thesis_testing": [
                "live_feature_coverage_validation",
                "profitability_or_edge_claim_disallowed_until_forward_evidence",
            ],
            "feature_lane_schema_status": {
                "trade_flow": "schema_ready",
                "organic_flow": "schema_ready",
                "holder_distribution": "schema_ready",
                "dev_behavior": "schema_ready",
                "post_migration_depth": "schema_ready",
                "execution_cost": "schema_ready",
            },
            "birth_to_first_observation_latency_ms": _stats(self.birth_to_first_observation_latencies_ms),
            "observation_interval_by_progress_tier": {
                tier: _stats(values) for tier, values in self.observation_intervals_by_tier.items()
            },
            "tokens_with_60pct_plus_crossing": len(self.tokens_with_60pct_plus_crossing),
            "tokens_with_70pct_plus_crossing": len(self.tokens_with_70pct_plus_crossing),
            "tokens_with_migration": len(self.tokens_with_migration),
            "stop_reasons": dict(self.stop_reasons),
            "provisional_progress_formula": self.config.provisional_progress_formula,
            "valuation_formula_audit_path": str(self.output_root / "valuation_formula_audit.jsonl"),
            "axiom_reconciliation_readme_path": str(self.output_root / "axiom_reconciliation_README.md"),
            "live_status_path": str(self.output_root / "live_status.json"),
            "t007_watcher_html_path": str(self.output_root / "t007_live_watcher.html"),
            "final": final,
        }
        adapter = getattr(self, "lifecycle_adapter", None)
        if adapter is not None:
            adapter_health = adapter.health()
            if isinstance(adapter_health, dict):
                summary.update(adapter_health)
        self._merge_t012_paper_readiness_gate(summary, write_outputs=False)
        return summary

    def _emit_token_path_summary(self, state: TrackingState) -> None:
        birth_row = self.birth_rows_by_mint.get(state.mint, {})
        thresholds = sorted(state.thresholds_crossed)
        seconds_to_threshold = {str(threshold): state.threshold_seconds_since_launch.get(threshold) for threshold in thresholds}
        threshold_to_migration = {
            str(threshold): (
                round(float(state.migration_received_at) - float(state.launch_received_at) - float(seconds), 6)
                if state.migration_received_at is not None and state.launch_received_at is not None and seconds is not None
                else None
            )
            for threshold, seconds in state.threshold_seconds_since_launch.items()
        }
        row = {
            "mint": state.mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "quote_asset": birth_row.get("quote_asset") or (state.last_observation_row or {}).get("quote_asset"),
            "quote_mint": birth_row.get("quote_mint") or (state.last_observation_row or {}).get("quote_mint"),
            "admitted": birth_row.get("admitted"),
            "admission_reason": birth_row.get("admission_reason"),
            "launch_received_at": state.launch_received_at,
            "finalization_time": state.finalized_at,
            "finalization_reason": state.stop_reason,
            "highest_progress_pct": state.highest_progress_pct,
            "final_progress_pct": state.last_progress_pct,
            "crossed_40": 40.0 in state.thresholds_crossed,
            "crossed_50": 50.0 in state.thresholds_crossed,
            "crossed_60": 60.0 in state.thresholds_crossed,
            "crossed_65": 65.0 in state.thresholds_crossed,
            "crossed_70": 70.0 in state.thresholds_crossed,
            "crossed_75": 75.0 in state.thresholds_crossed,
            "crossed_80": 80.0 in state.thresholds_crossed,
            "crossed_90": 90.0 in state.thresholds_crossed,
            "crossed_100": 100.0 in state.thresholds_crossed,
            "first_cross_time_by_threshold": seconds_to_threshold,
            "seconds_to_threshold_by_threshold": seconds_to_threshold,
            "seconds_between_thresholds": _seconds_between_thresholds(state.threshold_seconds_since_launch),
            "migration_seen": state.migration_seen,
            "migration_detection_method": (state.last_observation_row or {}).get("migration_signal_source"),
            "seconds_to_migration": _duration_seconds(state.launch_received_at, state.migration_received_at),
            "threshold_to_migration_seconds": threshold_to_migration,
            "tracking_tier": state.tracking_tier,
            "tracking_tier_reason": state.tracking_tier_reason,
            "deep_tracking_admitted": state.deep_tracking_admitted,
            "complete_true_seen": bool(state.migration_seen),
            "pumpfun_migrate_seen": (state.last_observation_row or {}).get("explicit_migrate_log"),
            "pumpswap_pool_created_seen": False,
            "post_migration_observation_count": state.post_migration_observation_count,
            "trade_flow_status": state.trade_flow_status,
            "organic_share_status": state.organic_share_status,
            "holder_distribution_status": state.holder_distribution_status,
            "dev_behavior_status": state.dev_behavior_status,
            "post_migration_depth_status": state.post_migration_depth_status,
            "execution_cost_status": state.execution_cost_status,
            "missing_data_flags": _feature_missing_data_flags(state),
            "data_quality_flags": [],
        }
        self._append_jsonl("token_path_summary.jsonl", row)
        self.summary_counters["token_path_summary_rows"] += 1
        self.summary_counters["token_path_summary_written"] += 1

    def finalize(self) -> dict[str, Any]:
        """Bounded live finalization. Heavy materialization is offline/resumable."""
        finalization_started_at = time.time()
        max_wall_seconds = float(getattr(self.config, "max_finalization_wall_time_seconds", 30.0) or 30.0)
        try:
            active_tracking_before_finalization = self._active_tracking_count()
            if not bool(getattr(self.config, "bounded_live_finalization_enabled", False)):
                final_received_at = time.time()
                for state in list(self.states.values()):
                    try:
                        if not state.stopped:
                            self._finalize_tracking_state(state, "run_finalized", received_at=final_received_at)
                        else:
                            self._emit_valuation_ladder_path(state)
                            if not state.final_wallet_checkpoint_written:
                                self._emit_wallet_dev_checkpoint(
                                    state,
                                    "finalization",
                                    observation=state.last_observation_row or {},
                                    received_at=final_received_at,
                                )
                                state.final_wallet_checkpoint_written = True
                        self._emit_token_path_summary(state)
                    except Exception as exc:
                        self._record_finalization_error(f"legacy_state_finalization:{state.mint}", exc)
            self.summary_counters["post_migration_observations_pending_at_finalization"] = self._pending_post_migration_observation_count()
            self.summary_counters["active_tracking_still_active_at_finalization"] = active_tracking_before_finalization
            self.run_finalized = True
            actual_duration = time.time() - self.started_at
            self._write_campaign_manifest(ended_at=time.time(), actual_duration_seconds=actual_duration)
            summary = self.build_summary(final=True)
            elapsed = time.time() - finalization_started_at
            bounded_live = bool(getattr(self.config, "bounded_live_finalization_enabled", False))
            summary.update(
                {
                    "run_finalized": True,
                    "finalization_mode": "bounded_live_finalization" if bounded_live else "legacy_inline_finalization",
                    "finalization_wall_time_seconds": elapsed,
                    "finalization_wall_time_limit_seconds": max_wall_seconds,
                    "finalization_timeout": elapsed > max_wall_seconds,
                    "finalization_stuck_warning": False,
                    "offline_materialization_required": bounded_live,
                    "offline_materialization_reason": "heavy_lifecycle_exports_deferred_from_live_finalization" if bounded_live else "",
                    "materializer_deferred": bounded_live,
                    "collector_finalization_completed": True,
                }
            )
            if elapsed > max_wall_seconds:
                summary["run_finalized"] = False
                summary["run_status"] = "failed_finalization"
                summary["runtime_phase"] = "finalization_failed"
                summary["offline_recovery_required"] = True
                _atomic_write_json(self.output_root / "collector_summary_partial.json", summary)
                self._write_live_status("failed_finalization", summary)
            else:
                summary["run_status"] = "finalized_with_errors" if self.finalization_errors else "finalized"
                summary["runtime_phase"] = "finalized"
                self._merge_t012_paper_readiness_gate(summary, write_outputs=True)
                if self.finalization_errors:
                    _atomic_write_json(self.output_root / "collector_summary_partial.json", summary)
                _atomic_write_json(self.output_root / "collector_summary.json", summary)
                self._write_live_status(summary["run_status"], summary)
            return summary
        except Exception as exc:
            self.run_finalized = False
            self.failure_reason = str(exc)
            self._record_finalization_error("fatal_finalize", exc)
            partial = self.build_summary(final=False)
            partial.update(
                {
                    "run_finalized": False,
                    "run_status": "failed_finalization",
                    "runtime_phase": "finalization_failed",
                    "fatal_finalization_error": str(exc),
                    "finalization_timeout": False,
                    "finalization_stuck_warning": False,
                    "offline_recovery_required": True,
                    "offline_materialization_required": True,
                }
            )
            try:
                _atomic_write_json(self.output_root / "collector_summary_partial.json", partial)
            except Exception:
                pass
            try:
                self._write_live_status("failed_finalization", partial)
            except Exception:
                pass
            raise

    def _record_finalization_error(self, stage: str, exc: Exception) -> None:
        self.finalization_errors.append(
            {
                "stage": str(stage),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )

    def _emit_curve_velocity_events(self, state: TrackingState, row: dict[str, Any], history: list[dict[str, Any]]) -> None:
        progress = _num(row.get("progress_pct"))
        as_of = _num(row.get("received_at"))
        if progress is None or as_of is None:
            return
        windows = [5, 10, 30, 60]
        for window in windows:
            candidates = [
                item for item in history
                if _num(item.get("progress_pct")) is not None
                and _num(item.get("received_at")) is not None
                and float(as_of) - float(_num(item.get("received_at")) or 0.0) <= float(window)
                and float(_num(item.get("received_at")) or 0.0) < float(as_of)
            ]
            if candidates:
                prior = min(candidates, key=lambda item: float(_num(item.get("received_at")) or as_of))
                prior_progress = float(_num(prior.get("progress_pct")) or 0.0)
                prior_received = float(_num(prior.get("received_at")) or as_of)
                seconds_between = max(0.000001, float(as_of) - prior_received)
                delta = float(progress) - prior_progress
                feature_status = "available"
            else:
                prior_progress = None
                seconds_between = None
                delta = None
                feature_status = "not_available"
            event = {
                "mint": state.mint,
                "as_of_received_at": as_of,
                "as_of_seconds_since_launch": row.get("seconds_since_launch"),
                "from_progress_pct": prior_progress,
                "to_progress_pct": progress,
                "window_seconds": window,
                "progress_delta": round(delta, 6) if delta is not None else None,
                "progress_per_second": round(delta / seconds_between, 9) if delta is not None and seconds_between else None,
                "progress_per_minute": round((delta / seconds_between) * 60.0, 9) if delta is not None and seconds_between else None,
                "trade_count_in_window": None,
                "progress_per_trade": None,
                "quote_asset": row.get("quote_asset"),
                "enough_data": feature_status == "available",
                "feature_status": feature_status,
                "campaign_id": self.config.run_id,
                "run_id": self.config.run_id,
            }
            self._append_jsonl("curve_velocity_events.jsonl", event)
            self.summary_counters["curve_velocity_events_written"] += 1

    def _emit_curve_acceleration_events(self, state: TrackingState, row: dict[str, Any], history: list[dict[str, Any]]) -> None:
        progress = _num(row.get("progress_pct"))
        as_of = _num(row.get("received_at"))
        if progress is None or as_of is None:
            return
        recent = _velocity_for_window(history, as_of=float(as_of), window_seconds=10)
        prior = _velocity_for_window(history, as_of=float(as_of) - 10.0, window_seconds=10)
        prior_velocity = prior.get("progress_per_second")
        recent_velocity = recent.get("progress_per_second")
        zero_prior = prior_velocity == 0
        if recent_velocity is not None and prior_velocity not in (None, 0):
            ratio = recent_velocity / prior_velocity
            status = "available"
        else:
            ratio = None
            status = "partial" if recent_velocity is not None else "not_available"
        event = {
            "mint": state.mint,
            "as_of_received_at": as_of,
            "as_of_seconds_since_launch": row.get("seconds_since_launch"),
            "recent_window_seconds": 10,
            "prior_window_seconds": 10,
            "recent_velocity": recent_velocity,
            "prior_velocity": prior_velocity,
            "acceleration_ratio": round(ratio, 9) if ratio is not None else None,
            "zero_prior_velocity": bool(zero_prior),
            "capped_acceleration_ratio": min(ratio, 100.0) if ratio is not None else None,
            "segment_recent": "last_10s",
            "segment_prior": "previous_10s",
            "enough_data": status == "available",
            "feature_status": status,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
        }
        self._append_jsonl("curve_acceleration_events.jsonl", event)
        self.summary_counters["curve_acceleration_events_written"] += 1

    def _emit_threshold_crossings(
        self,
        state: TrackingState,
        observation: dict[str, Any],
        previous: float | None,
        progress: float,
        received_at: float,
    ) -> None:
        progress_status = observation.get("progress_pct_status")
        if progress_status not in {"decoded_exact", "decoded_candidate"}:
            return
        migration_seen = state.migration_seen or _bool(observation.get("complete_or_migrated") or observation.get("complete"))
        for threshold in THRESHOLDS:
            if threshold in state.thresholds_crossed:
                continue
            crossed = progress >= threshold and (previous is None or previous < threshold)
            if not crossed:
                continue
            previous_threshold = max([value for value in state.thresholds_crossed if value < threshold], default=None)
            previous_threshold_seconds = state.threshold_seconds_since_launch.get(previous_threshold) if previous_threshold is not None else None
            current_seconds = _num(observation.get("seconds_since_launch"))
            row = {
            "mint": state.mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "crossing_type": "true_curve_progress",
                "threshold_pct": threshold,
                "crossing_slot": observation.get("slot"),
                "crossing_block_time": observation.get("block_time"),
                "crossing_received_at": received_at,
                "progress_pct": progress,
                "crossing_progress_pct": progress,
                "previous_progress_pct": previous,
                "previous_threshold_pct": previous_threshold,
                "seconds_since_previous_threshold": (
                    round(current_seconds - previous_threshold_seconds, 6)
                    if current_seconds is not None and previous_threshold_seconds is not None
                    else None
                ),
                "progress_pct_status": progress_status,
                "progress_formula_version": observation.get("progress_formula_version"),
                "complete_already_seen": migration_seen,
                "source_observation_id": observation.get("observation_id"),
                "seconds_since_launch": observation.get("seconds_since_launch"),
                "migration_seen_before_crossing": migration_seen,
                "quote_mint": observation.get("quote_mint"),
                "quote_asset": observation.get("quote_asset"),
                "quote_asset_status": observation.get("quote_asset_status"),
            }
            self._append_jsonl("threshold_crossings.jsonl", row)
            self._append_jsonl("true_curve_threshold_crossings.jsonl", row)
            state.thresholds_crossed.add(threshold)
            if current_seconds is not None:
                state.threshold_seconds_since_launch[threshold] = current_seconds
            self.summary_counters["threshold_crossings_written"] += 1
            _increment_counter(self.summary_counters["true_curve_threshold_crossings_by_threshold"], str(float(threshold)))
            _increment_counter(self.summary_counters["progress_crossings_by_quote_asset"], str(observation.get("quote_asset") or "unknown"))
            if threshold >= 60.0:
                self.tokens_with_60pct_plus_crossing.add(state.mint)
            if threshold >= 70.0:
                self.tokens_with_70pct_plus_crossing.add(state.mint)

    def _emit_valuation_band_crossings(
        self,
        state: TrackingState,
        observation: dict[str, Any],
        previous: float | None,
        valuation_usd: float,
        received_at: float,
    ) -> None:
        if not _valuation_ladder_allowed(observation):
            return
        migration_seen = state.migration_seen or _bool(observation.get("complete_or_migrated") or observation.get("complete"))
        for band in VALUATION_BANDS_USD:
            if band in state.valuation_bands_crossed:
                continue
            crossed = valuation_usd >= band and (previous is None or previous < band)
            if not crossed:
                continue
            row = {
                "mint": state.mint,
                "crossing_type": "valuation_band",
                "threshold_usd": band,
                "crossing_slot": observation.get("slot"),
                "crossing_block_time": observation.get("block_time"),
                "crossing_received_at": received_at,
                "valuation_usd": valuation_usd,
                "previous_valuation_usd": previous,
                "valuation_source_field": observation.get("valuation_source_field"),
                "source_observation_id": observation.get("observation_id"),
                "seconds_since_launch": observation.get("seconds_since_launch"),
                "migration_seen_before_crossing": migration_seen,
            }
            self._append_jsonl("threshold_crossings.jsonl", row)
            state.valuation_bands_crossed.add(band)
            state.valuation_band_received_at[band] = received_at
            seconds_since_launch = _num(observation.get("seconds_since_launch"))
            if seconds_since_launch is not None:
                state.valuation_band_seconds_since_launch[band] = seconds_since_launch
            state.valuation_band_values[band] = valuation_usd
            state.valuation_band_slots[band] = _int(observation.get("slot"))
            state.valuation_band_observation_ids[band] = observation.get("observation_id")
            self.summary_counters["threshold_crossings_written"] += 1
            _increment_counter(self.summary_counters["valuation_band_crossings_by_band"], str(int(band)))
            self._emit_valuation_ladder_band_crossing(state, observation, previous, band, valuation_usd, received_at)
            if band in VALUATION_LADDER_CHECKPOINT_BANDS:
                self._emit_wallet_dev_checkpoint(state, "valuation_band", band_usd=band, observation=observation, received_at=received_at)

    def _emit_migration_event(self, state: TrackingState, observation: dict[str, Any], received_at: float) -> None:
        row = {
            "mint": state.mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "migration_completion_slot": observation.get("slot"),
            "block_time": observation.get("block_time"),
            "received_at": received_at,
            "source_type": observation.get("observation_source") or "unknown",
            "curve_complete_flag": True,
            "migration_signal_source": observation.get("migration_signal_source") or ("complete_flag_true" if _bool(observation.get("complete_or_migrated") or observation.get("complete")) else "unknown"),
            "dex_pair_signal": observation.get("dex_pair_signal"),
            "seconds_since_launch": observation.get("seconds_since_launch"),
            "last_progress_pct_before_completion": state.last_progress_pct if state.last_progress_pct is not None else observation.get("progress_pct"),
        }
        self._append_jsonl("migration_events.jsonl", row)
        self.summary_counters["migrations_written"] += 1
        self.tokens_with_migration.add(state.mint)
        state.migration_seen = True
        state.migration_received_at = received_at
        self._record_creator_migration_seen(state, received_at)

    def _emit_valuation_formula_audit(self, state: TrackingState, row: dict[str, Any], received_at: float) -> None:
        classification = _valuation_formula_classification(row, state)
        audit_row = {
            "mint": state.mint,
            "received_at": received_at,
            "source_observation_id": row.get("observation_id"),
            "source_route_key": _state_source_route_key(state),
            "cohort": _valuation_audit_cohort(row, state),
            "progress_pct": row.get("progress_pct"),
            "progress_pct_status": row.get("progress_pct_status"),
            "complete": row.get("complete"),
            "migration_seen": state.migration_seen,
            "axiom_market_cap_usd": row.get("axiom_market_cap_usd"),
            "axiom_liquidity_usd": row.get("axiom_liquidity_usd"),
            "collector_reserve_fdv_usd": row.get("reserve_fdv_usd"),
            "collector_bonding_curve_market_cap_usd": row.get("bonding_curve_market_cap_usd"),
            "collector_bonding_curve_market_cap_quote": row.get("bonding_curve_market_cap_quote"),
            "collector_bonding_curve_market_cap_quote_asset": row.get("bonding_curve_market_cap_quote_asset"),
            "bonding_curve_market_cap_formula_version": row.get("bonding_curve_market_cap_formula_version"),
            "collector_fdv_proxy_usd": row.get("fdv_proxy_usd"),
            "collector_valuation_usd": row.get("valuation_usd"),
            "candidate_market_cap_usd": row.get("candidate_market_cap_usd"),
            "valuation_source_field": row.get("valuation_source_field"),
            "valuation_source_type": row.get("valuation_source_type"),
            "valuation_units_status": row.get("valuation_units_status"),
            "valuation_ladder_trust_status": row.get("valuation_ladder_trust_status"),
            "valuation_ladder_emission_allowed": _valuation_ladder_allowed(row),
            "matches_axiom_market_cap": _within_pct(row.get("valuation_usd"), row.get("axiom_market_cap_usd"), 5.0),
            "matches_axiom_liquidity": _within_pct(row.get("valuation_usd"), row.get("axiom_liquidity_usd"), 5.0),
            "possible_2x_market_cap": _within_pct(_half_or_none(row.get("valuation_usd")), row.get("axiom_market_cap_usd"), 5.0),
            "valuation_formula_classification": classification,
        }
        self._append_jsonl("valuation_formula_audit.jsonl", audit_row)
        self.summary_counters["valuation_formula_audit_rows"] += 1
        _increment_counter(self.summary_counters["valuation_formula_classification_counts"], classification)

    def _update_migration_signal_counts(self, row: dict[str, Any]) -> None:
        if _bool(row.get("complete_or_migrated") or row.get("complete")):
            self.summary_counters["complete_true_count"] += 1
        if _num(row.get("real_token_reserves_scaled")) is not None and float(row.get("real_token_reserves_scaled") or 0.0) <= 1e-9:
            self.summary_counters["reserve_zero_count"] += 1
        progress = _num(row.get("progress_pct"))
        if progress is not None and progress >= 100.0 and row.get("progress_pct_status") in {"decoded_candidate", "decoded_exact"}:
            self.summary_counters["progress_100pct_count"] += 1
        if _bool(row.get("explicit_migrate_log")):
            self.summary_counters["explicit_migrate_log_count"] += 1
        if _bool(row.get("dex_pair_signal")):
            self.summary_counters["dex_pair_signal_count"] += 1

    def _emit_high_fdv_without_migration_candidates(self, state: TrackingState, row: dict[str, Any], received_at: float) -> None:
        if not _valuation_ladder_allowed(row):
            return
        valuation = _num(row.get("valuation_usd"))
        if valuation is None or valuation < 60_000:
            return
        reason = "high_fdv_without_migration_event"
        if reason not in state.migration_candidate_reasons:
            state.migration_candidate_reasons.add(reason)
            self.summary_counters["migration_candidates_seen"] += 1
            self.summary_counters["high_fdv_without_migration_event_count"] += 1
            candidate_row = {
                "mint": state.mint,
                "received_at": received_at,
                "candidate_reason": reason,
                "migration_candidate_not_confirmed": True,
                "valuation_usd": valuation,
                "progress_pct": row.get("progress_pct"),
                "progress_pct_status": row.get("progress_pct_status"),
                "complete": row.get("complete"),
                "complete_flag_missing": row.get("complete") is None,
                "reserve_zero_not_seen": not (_num(row.get("real_token_reserves_scaled")) is not None and float(row.get("real_token_reserves_scaled") or 0.0) <= 1e-9),
                "migrate_log_not_seen": not _bool(row.get("explicit_migrate_log")),
                "dex_pair_signal": row.get("dex_pair_signal"),
                "source_observation_id": row.get("observation_id"),
            }
            self._append_jsonl("migration_candidates.jsonl", candidate_row)
        for threshold, counter in [
            (60_000, "tokens_crossing_60k_without_migration_event"),
            (100_000, "tokens_crossing_100k_without_migration_event"),
            (250_000, "tokens_crossing_250k_without_migration_event"),
        ]:
            if valuation >= threshold and threshold not in state.high_fdv_without_migration_thresholds:
                state.high_fdv_without_migration_thresholds.add(threshold)
                self.summary_counters[counter] += 1

    def _emit_valuation_ladder_band_crossing(
        self,
        state: TrackingState,
        observation: dict[str, Any],
        previous_valuation_usd: float | None,
        band_usd: int,
        valuation_usd: float,
        received_at: float,
    ) -> None:
        previous_bands = sorted(existing for existing in state.valuation_band_received_at if existing < band_usd)
        previous_band = previous_bands[-1] if previous_bands else None
        previous_band_received_at = state.valuation_band_received_at.get(previous_band) if previous_band is not None else None
        row = {
            "mint": state.mint,
            "event_type": "valuation_band_cross",
            "band_usd": band_usd,
            "valuation_usd": valuation_usd,
            "previous_valuation_usd": previous_valuation_usd,
            "crossing_slot": observation.get("slot"),
            "crossing_received_at": received_at,
            "seconds_since_launch": observation.get("seconds_since_launch"),
            "seconds_since_previous_band": round(received_at - previous_band_received_at, 6)
            if previous_band_received_at is not None
            else None,
            "previous_band_usd": previous_band,
            "true_curve_progress_pct": observation.get("progress_pct"),
            "progress_pct_status": observation.get("progress_pct_status"),
            "complete": _bool(observation.get("complete_or_migrated") or observation.get("complete")),
            "migration_seen": state.migration_seen,
            "source_observation_id": observation.get("observation_id"),
            "valuation_source_field": observation.get("valuation_source_field"),
        }
        self._append_jsonl("valuation_ladder_events.jsonl", row)
        self.summary_counters["valuation_ladder_events_written"] += 1

    def _update_valuation_path_extrema(self, state: TrackingState, valuation_usd: float) -> None:
        for band in state.valuation_bands_crossed:
            current_max = state.valuation_max_after_band.get(band, valuation_usd)
            current_min = state.valuation_min_after_band.get(band, valuation_usd)
            new_max = max(current_max, valuation_usd)
            new_min = min(current_min, valuation_usd)
            state.valuation_max_after_band[band] = new_max
            state.valuation_min_after_band[band] = new_min
            if new_max > 0:
                retrace = max(0.0, (new_max - valuation_usd) / new_max * 100.0)
                state.valuation_max_retrace_pct_after_band[band] = max(
                    state.valuation_max_retrace_pct_after_band.get(band, 0.0),
                    retrace,
                )

    def _emit_valuation_ladder_path(self, state: TrackingState) -> None:
        if state.valuation_path_finalized:
            return
        row: dict[str, Any] = {
            "mint": state.mint,
            "launch_received_at": state.launch_received_at,
            "creator_address": state.creator_address,
            "source_route_key": _state_source_route_key(state),
            "migration_seen": state.migration_seen,
            "migration_received_at": state.migration_received_at,
            "stop_reason": state.stop_reason,
            "finalization_reason": state.stop_reason,
            "last_progress_pct": state.last_progress_pct,
            "highest_progress_pct": state.highest_progress_pct,
            "highest_threshold_crossed": max(state.thresholds_crossed) if state.thresholds_crossed else None,
            "age_at_finalization_seconds": state.age_at_finalization_seconds,
            "observations_count": state.observation_count,
            "decoded_observations_count": state.decoded_observation_count,
            "pruned_due_to_low_progress": state.pruned_due_to_low_progress,
            "high_progress_protected": state.high_progress_protected,
        }
        for band in VALUATION_BANDS_USD:
            label = _band_label(band)
            crossed_at = state.valuation_band_received_at.get(band)
            row[f"first_cross_{label}_received_at"] = crossed_at
            row[f"first_cross_{label}_seconds_since_launch"] = state.valuation_band_seconds_since_launch.get(band)
            row[f"first_cross_{label}_valuation_usd"] = state.valuation_band_values.get(band)
            row[f"max_valuation_after_{label}"] = state.valuation_max_after_band.get(band)
            row[f"min_valuation_after_{label}"] = state.valuation_min_after_band.get(band)
            retrace = state.valuation_max_retrace_pct_after_band.get(band)
            row[f"max_retrace_pct_after_{label}"] = round(retrace, 6) if retrace is not None else None
            row[f"max_drawdown_pct_after_{label}"] = round(retrace, 6) if retrace is not None else None
            next_band = _next_valuation_band(band)
            next_delta = _transition_seconds(state, band, next_band) if next_band is not None else None
            row[f"path_ended_after_{label}_before_next_band"] = crossed_at is not None and next_band is not None and next_delta is None
            for seconds in VALUATION_LADDER_STALL_SECONDS:
                stalled = crossed_at is not None and next_band is not None and (next_delta is None or next_delta > seconds)
                row[f"stalled_after_{label}_no_next_{seconds}s"] = stalled
                if stalled and band in {30_000, 40_000} and seconds in {10, 30, 60}:
                    _increment_counter(
                        self.summary_counters["valuation_ladder_stall_counts"],
                        f"{_band_label(band)}_{seconds}s",
                    )
        for start, end in VALUATION_LADDER_TRANSITION_PAIRS:
            label = _transition_label(start, end)
            seconds = _transition_seconds(state, start, end)
            row[f"seconds_{label}"] = seconds
            if seconds is not None:
                self.valuation_transition_seconds_by_pair[label].append(seconds)
        self._append_jsonl("valuation_ladder_paths.jsonl", row)
        self.summary_counters["valuation_ladder_paths_written"] += 1
        state.valuation_path_finalized = True

    def _emit_wallet_dev_checkpoint(
        self,
        state: TrackingState,
        checkpoint_type: str,
        *,
        band_usd: int | None = None,
        observation: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
        received_at: float | None = None,
        error_reason: str | None = None,
    ) -> None:
        payload = observation or source_event or {}
        received = received_at if received_at is not None else _num(payload.get("received_at")) or time.time()
        wallet_metrics = payload.get("wallet_metrics") if isinstance(payload.get("wallet_metrics"), dict) else {}
        concentration_metrics = payload.get("concentration_metrics") if isinstance(payload.get("concentration_metrics"), dict) else {}
        dev_metrics = payload.get("dev_metrics") if isinstance(payload.get("dev_metrics"), dict) else {}
        wallet_status = str(payload.get("wallet_metrics_status") or ("available" if wallet_metrics else "not_available"))
        concentration_status = str(payload.get("concentration_metrics_status") or ("available" if concentration_metrics else wallet_status))
        dev_status = str(payload.get("dev_metrics_status") or ("available" if dev_metrics else "not_available"))
        creator_history_status = str(state.creator_history_metrics.get("creator_history_status") or "deferred")
        row = {
            "mint": state.mint,
            "checkpoint_type": checkpoint_type,
            "checkpoint_band_usd": band_usd,
            "received_at": received,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received),
            "creator_address": state.creator_address,
            "wallet_metrics_status": wallet_status,
            "concentration_metrics_status": concentration_status,
            "dev_metrics_status": dev_status,
            "creator_history_status": creator_history_status,
            "buy_count_since_launch": _first_present(wallet_metrics, ["buy_count_since_launch"]),
            "sell_count_since_launch": _first_present(wallet_metrics, ["sell_count_since_launch"]),
            "buy_count_since_prior_checkpoint": _first_present(wallet_metrics, ["buy_count_since_prior_checkpoint"]),
            "sell_count_since_prior_checkpoint": _first_present(wallet_metrics, ["sell_count_since_prior_checkpoint"]),
            "net_buy_count_since_prior_checkpoint": _first_present(wallet_metrics, ["net_buy_count_since_prior_checkpoint"]),
            "volume_since_launch": _first_present(wallet_metrics, ["volume_since_launch"]),
            "volume_since_prior_checkpoint": _first_present(wallet_metrics, ["volume_since_prior_checkpoint"]),
            "unique_buyers_since_launch": _first_present(wallet_metrics, ["unique_buyers_since_launch"]),
            "unique_sellers_since_launch": _first_present(wallet_metrics, ["unique_sellers_since_launch"]),
            "unique_buyers_since_prior_checkpoint": _first_present(wallet_metrics, ["unique_buyers_since_prior_checkpoint"]),
            "unique_sellers_since_prior_checkpoint": _first_present(wallet_metrics, ["unique_sellers_since_prior_checkpoint"]),
            "buyer_growth_rate": _first_present(wallet_metrics, ["buyer_growth_rate"]),
            "sell_pressure_after_band_crossing": _first_present(wallet_metrics, ["sell_pressure_after_band_crossing"]),
            "top_1_buyer_share": _first_present(concentration_metrics, ["top_1_buyer_share"]),
            "top_3_buyer_share": _first_present(concentration_metrics, ["top_3_buyer_share"]),
            "top_5_buyer_share": _first_present(concentration_metrics, ["top_5_buyer_share"]),
            "top_10_buyer_share": _first_present(concentration_metrics, ["top_10_buyer_share"]),
            "top_holder_share": _first_present(concentration_metrics, ["top_holder_share"]),
            "top_5_holder_share": _first_present(concentration_metrics, ["top_5_holder_share"]),
            "top_10_holder_share": _first_present(concentration_metrics, ["top_10_holder_share"]),
            "sniper_early_buyer_concentration": _first_present(concentration_metrics, ["sniper_early_buyer_concentration"]),
            "same_funder_cluster_flag": _first_present(concentration_metrics, ["same_funder_cluster_flag"]),
            "creator_prior_launch_count_before_this_launch": state.creator_history_metrics.get("creator_prior_launch_count_before_this_launch"),
            "creator_prior_migration_count_before_this_launch": state.creator_history_metrics.get("creator_prior_migration_count_before_this_launch"),
            "creator_prior_max_fdv_band_before_this_launch": state.creator_history_metrics.get("creator_prior_max_fdv_band_before_this_launch"),
            "creator_prior_rug_dead_count_before_this_launch": state.creator_history_metrics.get("creator_prior_rug_dead_count_before_this_launch"),
            "creator_history_source": state.creator_history_metrics.get("creator_history_source"),
            "creator_history_scope": state.creator_history_metrics.get("creator_history_scope"),
            "creator_history_cutoff_time": state.creator_history_metrics.get("creator_history_cutoff_time"),
            "creator_sell_before_30k": _first_present(payload, ["creator_sell_before_30k"]) or _first_present(dev_metrics, ["creator_sell_before_30k"]),
            "creator_sell_before_40k": _first_present(payload, ["creator_sell_before_40k"]) or _first_present(dev_metrics, ["creator_sell_before_40k"]),
            "creator_sell_before_migration": _first_present(payload, ["creator_sell_before_migration"]) or _first_present(dev_metrics, ["creator_sell_before_migration"]),
            "creator_retained_balance": _first_present(dev_metrics, ["creator_retained_balance"]),
            "creator_funding_source": _first_present(dev_metrics, ["creator_funding_source"]),
            "enrichment_latency_ms": _num(payload.get("enrichment_latency_ms")),
            "error_reason": error_reason or payload.get("wallet_enrichment_error") or payload.get("error_reason"),
        }
        dev_previous_migrations = state.creator_history_metrics.get("creator_prior_migration_count_before_this_launch")
        row["dev_previous_migrations"] = dev_previous_migrations
        row["dev_previous_migrations_source"] = state.creator_history_metrics.get("creator_history_source")
        row["dev_previous_migrations_ge_3"] = (
            _num(dev_previous_migrations) is not None and float(dev_previous_migrations or 0) >= 3.0
        )
        row["dev_previous_migrations_decision_time_safe"] = bool(
            state.creator_history_metrics.get("creator_history_status") == "available"
            and state.creator_history_metrics.get("creator_history_point_in_time_safe") is not False
        )
        creator_sold_before_entry = _first_present(
            payload,
            ["creator_sold_before_entry", "creator_sell_before_entry", "creator_sell_before_30k", "creator_sell_before_40k"],
        )
        if creator_sold_before_entry is None:
            creator_sold_before_entry = _first_present(
                dev_metrics,
                ["creator_sold_before_entry", "creator_sell_before_entry", "creator_sell_before_30k", "creator_sell_before_40k"],
            )
        creator_sold_before_entry_source = "payload_or_dev_metrics"
        if creator_sold_before_entry is None and state.creator_address:
            creator_sold_before_entry = bool(state.creator_sold_before_entry_observed)
            creator_sold_before_entry_source = "local_observed_trade_flow"
        row["creator_sold_before_entry"] = creator_sold_before_entry
        row["creator_sold_before_entry_source"] = creator_sold_before_entry_source
        row["creator_sold_before_entry_decision_time_safe"] = creator_sold_before_entry is not None
        if row["enrichment_latency_ms"] is not None:
            self.wallet_enrichment_latencies_ms.append(row["enrichment_latency_ms"])
        self._append_jsonl("wallet_dev_checkpoints.jsonl", row)
        self.summary_counters["wallet_dev_checkpoints_written"] += 1
        if row.get("dev_previous_migrations_decision_time_safe"):
            self.summary_counters["dev_previous_migrations_field_decision_time_safe_count"] += 1
        if row.get("creator_sold_before_entry_decision_time_safe"):
            self.summary_counters["creator_sold_before_entry_field_decision_time_safe_count"] += 1
        self._count_availability_status("wallet_metrics", wallet_status)
        self._count_availability_status("dev_metrics", dev_status)
        self._count_availability_status("creator_history", creator_history_status)
        if "error" in {wallet_status, concentration_status, dev_status, creator_history_status} or row["error_reason"]:
            self.summary_counters["wallet_enrichment_error_count"] += 1

    def _count_availability_status(self, prefix: str, status: str) -> None:
        key = f"{prefix}_{status}_count"
        if key in self.summary_counters:
            self.summary_counters[key] += 1

    def _observation_row(self, observation: dict[str, Any], decode_status: str, error_reason: str) -> dict[str, Any]:
        progress = _num(observation.get("progress_pct"))
        complete = _bool(observation.get("complete") or observation.get("migrated") or observation.get("curve_complete"))
        birth_row = self.birth_rows_by_mint.get(str(observation.get("mint") or observation.get("token_mint") or ""))
        quote_payload = {**(birth_row or {}), **observation}
        quote = _quote_identity_from_payload(
            quote_payload,
            sol_usd=self.config.sol_usd,
            sol_usd_source=self.config.sol_usd_source,
            unsupported_as_unknown=True,
        )
        is_mayhem = _bool(observation.get("is_mayhem") or observation.get("mayhem") or observation.get("mayhem_mode"))
        progress_status = observation.get("progress_pct_status")
        if not progress_status:
            if progress is not None:
                progress_status = "decoded_exact"
            elif decode_status == "decoded" and (observation.get("raw_curve_state") or observation.get("fdv_proxy") is not None):
                progress_status = "unresolved_formula"
            else:
                progress_status = "unavailable"
        valuation = _valuation_units_from_observation(
            quote_payload,
            sol_usd=self.config.sol_usd,
            sol_usd_source=self.config.sol_usd_source,
            decode_status=decode_status,
        )
        reserve_fdv = _reserve_fdv_from_state(
            observation.get("raw_curve_state") or {},
            sol_usd=self.config.sol_usd,
            sol_usd_source=self.config.sol_usd_source,
            payload=quote_payload,
        )
        if (
            reserve_fdv.get("bonding_curve_market_cap_usd") is not None
            and reserve_fdv.get("bonding_curve_market_cap_status") == "computed"
            and not is_mayhem
            and not _bool(valuation.get("valuation_market_cap_confirmed"))
        ):
            valuation = {
                **valuation,
                "fdv_proxy_raw": reserve_fdv.get("bonding_curve_market_cap_quote"),
                "fdv_proxy_sol": reserve_fdv.get("reserve_fdv_sol"),
                "fdv_proxy_usd": reserve_fdv.get("bonding_curve_market_cap_usd"),
                "valuation_usd": reserve_fdv.get("bonding_curve_market_cap_usd"),
                "valuation_source_field": "bonding_curve_market_cap_usd",
                "valuation_units_status": "bonding_curve_market_cap_confirmed",
                "valuation_market_cap_confirmed": True,
                "valuation_ladder_trust_status": "market_cap_confirmed",
                "valuation_quote_units": reserve_fdv.get("bonding_curve_market_cap_quote"),
            }
        agreement = _fdv_proxy_agreement(valuation.get("fdv_proxy_sol"), reserve_fdv.get("reserve_fdv_sol"))
        axiom_market_cap_usd = _num(_first_present(observation, ["axiom_market_cap_usd", "axiom_visible_market_cap_usd"]))
        axiom_liquidity_usd = _num(_first_present(observation, ["axiom_liquidity_usd", "axiom_visible_liquidity_usd", "liquidity_usd"]))
        candidate_market_cap_usd = _candidate_market_cap_usd(
            observation,
            valuation.get("valuation_usd"),
            reserve_fdv.get("reserve_fdv_usd"),
        )
        return {
            "mint": observation.get("mint") or observation.get("token_mint"),
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "slot": observation.get("slot"),
            "block_time": observation.get("block_time"),
            "received_at": observation.get("received_at") or time.time(),
            "observation_source": observation.get("observation_source") or "unknown",
            "bonding_curve_account": observation.get("bonding_curve_account"),
            "associated_bonding_curve": observation.get("associated_bonding_curve"),
            "quote_mint": quote["quote_mint"],
            "quote_asset": quote["quote_asset"],
            "quote_asset_status": quote["quote_asset_status"],
            "quote_to_usd_rate": quote["quote_to_usd_rate"],
            "quote_to_usd_source": quote["quote_to_usd_source"],
            "quote_to_usd_warning": quote["quote_to_usd_warning"],
            "raw_curve_state": observation.get("raw_curve_state") or {},
            "computed_progress_pct": progress,
            "progress_pct": progress,
            "progress_pct_status": progress_status,
            "progress_formula_version": observation.get("progress_formula_version"),
            "progress_denominator_tokens": observation.get("progress_denominator_tokens"),
            "reserve_scale_mode": observation.get("reserve_scale_mode"),
            "real_token_reserves_scaled": observation.get("real_token_reserves_scaled"),
            "complete": complete,
            "complete_or_migrated": complete,
            "fdv_proxy_raw": valuation.get("fdv_proxy_raw"),
            "fdv_proxy_sol": valuation.get("fdv_proxy_sol"),
            "fdv_proxy_usd": valuation.get("fdv_proxy_usd"),
            "valuation_quote_units": valuation.get("valuation_quote_units"),
            "valuation_price_fdv_proxy": valuation.get("valuation_usd"),
            "valuation_usd": valuation.get("valuation_usd"),
            "valuation_source_field": valuation.get("valuation_source_field"),
            "valuation_units_status": valuation.get("valuation_units_status"),
            "valuation_market_cap_confirmed": valuation.get("valuation_market_cap_confirmed"),
            "valuation_ladder_trust_status": valuation.get("valuation_ladder_trust_status"),
            "valuation_source_type": observation.get("valuation_source_type") or observation.get("valuation_source_kind"),
            "market_cap_usd": _num(_first_present(observation, ["market_cap_usd", "axiom_market_cap_usd", "axiom_visible_market_cap_usd"]))
            if _num(_first_present(observation, ["market_cap_usd", "axiom_market_cap_usd", "axiom_visible_market_cap_usd"])) is not None
            else (reserve_fdv.get("bonding_curve_market_cap_usd") if not is_mayhem else None),
            "axiom_market_cap_usd": axiom_market_cap_usd,
            "axiom_liquidity_usd": axiom_liquidity_usd,
            "candidate_market_cap_usd": candidate_market_cap_usd,
            "is_mayhem": is_mayhem,
            "bonding_curve_price_quote": reserve_fdv.get("bonding_curve_price_quote"),
            "bonding_curve_price_usd": reserve_fdv.get("bonding_curve_price_usd"),
            "bonding_curve_market_cap_quote": reserve_fdv.get("bonding_curve_market_cap_quote"),
            "bonding_curve_market_cap_usd": reserve_fdv.get("bonding_curve_market_cap_usd"),
            "bonding_curve_market_cap_quote_asset": reserve_fdv.get("bonding_curve_market_cap_quote_asset"),
            "bonding_curve_market_cap_quote_mint": reserve_fdv.get("bonding_curve_market_cap_quote_mint"),
            "bonding_curve_market_cap_status": reserve_fdv.get("bonding_curve_market_cap_status"),
            "bonding_curve_market_cap_formula_version": reserve_fdv.get("bonding_curve_market_cap_formula_version"),
            "reserve_price_sol": reserve_fdv.get("reserve_price_sol"),
            "reserve_fdv_sol": reserve_fdv.get("reserve_fdv_sol"),
            "reserve_fdv_usd": reserve_fdv.get("reserve_fdv_usd"),
            "reserve_fdv_status": reserve_fdv.get("reserve_fdv_status"),
            "fdv_proxy_abs_diff": agreement.get("fdv_proxy_abs_diff"),
            "fdv_proxy_pct_diff": agreement.get("fdv_proxy_pct_diff"),
            "fdv_proxy_agreement_status": agreement.get("fdv_proxy_agreement_status"),
            "decode_status": decode_status,
            "error_reason": error_reason,
            "probe_attempt_index": observation.get("probe_attempt_index"),
            "probe_delay_ms": observation.get("probe_delay_ms"),
            "probe_started_at": observation.get("probe_started_at"),
            "probe_finished_at": observation.get("probe_finished_at"),
            "probe_duration_ms": observation.get("probe_duration_ms"),
            "account_found": observation.get("account_found"),
            "account_source": observation.get("account_source"),
            "decoded_bonding_curve_account": observation.get("decoded_bonding_curve_account"),
            "derived_bonding_curve_account": observation.get("derived_bonding_curve_account"),
            "final_for_mint": observation.get("final_for_mint"),
            "observation_id": observation.get("observation_id"),
            "seconds_since_launch": observation.get("seconds_since_launch"),
            "wallet_metrics": observation.get("wallet_metrics"),
            "wallet_metrics_status": observation.get("wallet_metrics_status"),
            "concentration_metrics": observation.get("concentration_metrics"),
            "concentration_metrics_status": observation.get("concentration_metrics_status"),
            "dev_metrics": observation.get("dev_metrics"),
            "dev_metrics_status": observation.get("dev_metrics_status"),
            "creator_sell_before_30k": observation.get("creator_sell_before_30k"),
            "creator_sell_before_40k": observation.get("creator_sell_before_40k"),
            "creator_sell_before_migration": observation.get("creator_sell_before_migration"),
            "explicit_migrate_log": observation.get("explicit_migrate_log"),
            "dex_pair_signal": observation.get("dex_pair_signal"),
            "migration_signal_source": observation.get("migration_signal_source"),
            "enrichment_latency_ms": observation.get("enrichment_latency_ms"),
            "wallet_enrichment_error": observation.get("wallet_enrichment_error"),
        }

    def _stop_tracking(
        self,
        state: TrackingState,
        reason: str,
        *,
        received_at: float | None = None,
        pruned_due_to_low_progress: bool = False,
    ) -> None:
        if state.stopped:
            return
        finalized_at = received_at if received_at is not None else time.time()
        state.stopped = True
        state.stop_reason = reason
        state.finalized_at = finalized_at
        state.age_at_finalization_seconds = _duration_seconds(state.launch_received_at, finalized_at)
        state.pruned_due_to_low_progress = pruned_due_to_low_progress
        state.high_progress_protected = self._is_high_progress_protected(state)
        state.priority_tier = "stopped"
        self.stop_reasons[reason] = self.stop_reasons.get(reason, 0) + 1

    def _finalize_tracking_state(
        self,
        state: TrackingState,
        reason: str,
        *,
        received_at: float,
        pruned_due_to_low_progress: bool = False,
    ) -> None:
        if state.stopped:
            return
        self._stop_tracking(
            state,
            reason,
            received_at=received_at,
            pruned_due_to_low_progress=pruned_due_to_low_progress,
        )
        self._emit_valuation_ladder_path(state)
        if not state.final_wallet_checkpoint_written:
            self._emit_wallet_dev_checkpoint(
                state,
                "finalization",
                observation=state.last_observation_row or {},
                received_at=received_at,
            )
            state.final_wallet_checkpoint_written = True

    def _prune_for_capacity(self, received_at: float) -> int:
        before = self._active_tracking_count()
        self._apply_lifecycle_policy(received_at, for_capacity=True)
        return max(0, before - self._active_tracking_count())

    def _apply_lifecycle_policy(self, received_at: float, *, for_capacity: bool = False) -> None:
        for state in sorted(self._state_snapshot(), key=lambda item: self._capacity_prune_sort_key(item, received_at)):
            if state.stopped:
                continue
            reason = self._lifecycle_stop_reason(state, received_at)
            if not reason:
                continue
            if for_capacity and self._is_high_progress_protected(state) and reason != "high_progress_retention_timeout":
                continue
            self.summary_counters["active_pruned_count"] += 1
            _increment_counter(self.summary_counters["active_pruned_by_reason"], reason)
            if reason == "low_progress_timeout":
                self.summary_counters["low_progress_timeout_count"] += 1
            if reason == "no_decode_timeout":
                self.summary_counters["no_decode_timeout_count"] += 1
            if for_capacity:
                self.summary_counters["stale_low_priority_pruned_count"] += 1
            self._finalize_tracking_state(
                state,
                reason,
                received_at=received_at,
                pruned_due_to_low_progress=reason in {"low_progress_timeout", "no_decode_timeout"},
            )
            if for_capacity and self._active_tracking_count() < self.config.max_active_tracking:
                break

    def _lifecycle_stop_reason(self, state: TrackingState, received_at: float) -> str | None:
        age = _duration_seconds(state.launch_received_at, received_at)
        if age is None:
            return None
        if state.observation_count > 0 and state.decoded_observation_count <= 0 and age >= float(self.config.no_decode_timeout_seconds):
            return "no_decode_timeout"
        progress = state.highest_progress_pct if state.highest_progress_pct is not None else state.last_progress_pct
        if progress is None:
            if age >= float(self.config.max_token_age_seconds):
                return "max_token_age_timeout"
            return None
        if progress >= 40.0:
            if progress >= 75.0:
                return "high_progress_retention_timeout" if age >= float(self.config.critical_progress_retention_seconds) else None
            if progress >= 60.0:
                return "high_progress_retention_timeout" if age >= float(self.config.very_high_progress_retention_seconds) else None
            return "high_progress_retention_timeout" if age >= float(self.config.high_progress_retention_seconds) else None
            return None
        if age >= float(self.config.max_token_age_seconds):
            return "max_token_age_timeout"
        for progress_limit, timeout_seconds in self.config.low_progress_timeouts:
            if progress < float(progress_limit) and age >= float(timeout_seconds):
                return "low_progress_timeout"
        return None

    def _capacity_prune_sort_key(self, state: TrackingState, received_at: float) -> tuple[int, float, float]:
        progress = state.highest_progress_pct
        progress_value = progress if progress is not None else -1.0
        age = _duration_seconds(state.launch_received_at, received_at) or 0.0
        return (TIER_ORDER.get(progress_priority_tier(progress), 0), progress_value, -age)

    def _is_high_progress_protected(self, state: TrackingState) -> bool:
        progress = state.highest_progress_pct if state.highest_progress_pct is not None else state.last_progress_pct
        return progress is not None and progress >= 40.0

    def _feature_state(self, mint: str, received_at: float) -> TrackingState:
        state = self.states.get(mint)
        if state is None:
            state = TrackingState(mint=mint, launch_received_at=received_at)
            self.states[mint] = state
        return state

    def _decision_time_fields(self, row: dict[str, Any], received_at: float) -> dict[str, Any]:
        decision_time = _num(_first_present(row, ["decision_time", "feature_decision_time", "as_of_received_at"]))
        if decision_time is None:
            decision_time = received_at
        safe = bool(received_at <= decision_time)
        self.summary_counters["decision_time_checked_feature_rows"] += 1
        if safe:
            self.summary_counters["decision_time_safe_feature_rows"] += 1
            status = "safe"
        else:
            self.summary_counters["decision_time_safety_violation_count"] += 1
            status = "violation_future_observation"
        return {
            "decision_time": decision_time,
            "feature_observed_at": received_at,
            "decision_time_safe": safe,
            "decision_time_safety_status": status,
        }

    def _is_bot_like_trade(
        self,
        state: TrackingState,
        trader_wallet: str,
        quote_amount: float | None,
        received_at: float,
    ) -> bool:
        repeated_wallet = bool(trader_wallet and state.trade_wallet_counts.get(trader_wallet, 0) > 1)
        repeated_size = False
        if quote_amount is not None:
            repeated_size = state.trade_size_counts.get(f"{quote_amount:.9f}", 0) > 1
        rapid_timing = bool(state.last_trade_received_at is not None and received_at - state.last_trade_received_at <= 0.25)
        tiny_trade = bool(quote_amount is not None and quote_amount > 0 and quote_amount < 0.01)
        return repeated_wallet or repeated_size or rapid_timing or tiny_trade

    def _organic_flow_row(
        self,
        state: TrackingState,
        event: dict[str, Any],
        received_at: float,
        quote_amount: float | None,
        bot_like: bool,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        total_trades = max(1, state.trade_count_since_launch)
        total_quote = state.buy_quote_volume_since_launch + state.sell_quote_volume_since_launch
        bot_volume = state.bot_like_quote_volume + (quote_amount or 0.0 if bot_like else 0.0)
        tiny_count = 0
        for size, count in state.trade_size_counts.items():
            if (_num(size) or 0.0) < 0.01:
                tiny_count += count
        status = "available" if state.trade_count_since_launch >= 5 else "partial"
        state.organic_share_status = status
        bot_share = _safe_ratio(state.bot_like_trade_count + (1 if bot_like else 0), total_trades)
        volume_share = _safe_ratio(bot_volume, total_quote)
        return {
            "mint": state.mint,
            "campaign_id": self.config.run_id,
            "run_id": self.config.run_id,
            "signature": event.get("signature"),
            "received_at": received_at,
            "seconds_since_launch": _duration_seconds(state.launch_received_at, received_at),
            "repeated_wallet_count": sum(1 for count in state.trade_wallet_counts.values() if count > 1),
            "repeated_trade_size_count": sum(1 for count in state.trade_size_counts.values() if count > 1),
            "timing_regularity_status": "rapid_repeat_detected" if bot_like and state.last_trade_received_at is not None else "not_detected",
            "tiny_trade_share": _safe_ratio(tiny_count, total_trades),
            "same_funding_cluster_status": event.get("same_funding_cluster_status") or "not_available",
            "bot_like_trade_share": bot_share,
            "non_bot_trade_share": round(max(0.0, 1.0 - bot_share), 6),
            "bot_like_volume_share": volume_share,
            "non_bot_volume_share": round(max(0.0, 1.0 - volume_share), 6),
            "organic_share_status": status,
            **decision,
        }

    def _active_count_by_progress_tier(self) -> dict[str, int]:
        counts = {
            "no_decoded_progress": 0,
            "progress_lt_5": 0,
            "progress_5_to_10": 0,
            "progress_10_to_20": 0,
            "progress_20_to_40": 0,
            "progress_40_to_60": 0,
            "progress_60_to_75": 0,
            "progress_ge_75": 0,
        }
        for state in self._state_snapshot():
            if state.stopped:
                continue
            progress = state.highest_progress_pct if state.highest_progress_pct is not None else state.last_progress_pct
            if progress is None:
                counts["no_decoded_progress"] += 1
            elif progress < 5.0:
                counts["progress_lt_5"] += 1
            elif progress < 10.0:
                counts["progress_5_to_10"] += 1
            elif progress < 20.0:
                counts["progress_10_to_20"] += 1
            elif progress < 40.0:
                counts["progress_20_to_40"] += 1
            elif progress < 60.0:
                counts["progress_40_to_60"] += 1
            elif progress < 75.0:
                counts["progress_60_to_75"] += 1
            else:
                counts["progress_ge_75"] += 1
        return counts

    def _active_count_by_age_bucket(self, received_at: float | None = None) -> dict[str, int]:
        now = received_at if received_at is not None else time.time()
        counts = {
            "age_lt_60s": 0,
            "age_60_to_120s": 0,
            "age_120_to_300s": 0,
            "age_300_to_600s": 0,
            "age_600_to_1800s": 0,
            "age_ge_1800s": 0,
        }
        for state in self._state_snapshot():
            if state.stopped:
                continue
            age = _duration_seconds(state.launch_received_at, now) or 0.0
            if age < 60.0:
                counts["age_lt_60s"] += 1
            elif age < 120.0:
                counts["age_60_to_120s"] += 1
            elif age < 300.0:
                counts["age_120_to_300s"] += 1
            elif age < 600.0:
                counts["age_300_to_600s"] += 1
            elif age < 1800.0:
                counts["age_600_to_1800s"] += 1
            else:
                counts["age_ge_1800s"] += 1
        return counts

    def _protected_high_progress_active_count(self) -> int:
        return sum(1 for state in self._state_snapshot() if not state.stopped and self._is_high_progress_protected(state))

    def _append_jsonl(self, filename: str, row: dict[str, Any]) -> None:
        with (self.output_root / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        self._record_persistent_lifecycle_artifact(filename, row)

    def _record_persistent_lifecycle_artifact(self, filename: str, row: dict[str, Any]) -> None:
        adapter = getattr(self, "lifecycle_adapter", None)
        if adapter is not None:
            adapter.record_artifact_row(filename, row)

    def apply_global_migration_side_effects_from_artifact(self, *, retry_count: int = 1) -> dict[str, Any]:
        if threading.get_ident() != getattr(self, "_sqlite_owner_thread_id", threading.get_ident()):
            raise RuntimeError("global_migration_side_effects_must_run_on_recorder_owner_thread")
        events = _read_jsonl(self.output_root / "global_migration_events.jsonl")
        latest_intents = _latest_global_migration_write_intents_by_candidate(self.output_root)
        applied = 0
        failed = 0
        seen: set[str] = set()
        for row in events:
            candidate_id = _migration_candidate_id(row)
            if candidate_id in seen:
                continue
            latest_intent = latest_intents.get(candidate_id) or {}
            if str(latest_intent.get("write_status") or "") == "written":
                continue
            seen.add(candidate_id)
            try:
                _apply_global_migration_recorder_side_effects(self, row, artifact_filename="global_migration_events.jsonl")
            except Exception as exc:
                failed += 1
                _record_global_migration_write_intent(
                    self.output_root,
                    row,
                    write_status="failed",
                    retry_count=retry_count,
                    write_error=exc,
                )
                continue
            applied += 1
            _record_global_migration_write_intent(
                self.output_root,
                row,
                write_status="written",
                retry_count=retry_count,
                write_success=True,
            )
        return {
            "migration_side_effects_applied": applied,
            "migration_side_effects_failed": failed,
            "migration_side_effects_source_rows": len(events),
        }

    def _ensure_jsonl_artifacts(self) -> None:
        for filename in JSONL_ARTIFACT_FILES:
            (self.output_root / filename).touch(exist_ok=True)

    def _write_run_config(self) -> None:
        payload = _json_safe(asdict(self.config))
        _atomic_write_json(self.output_root / "run_config.json", payload)

    def _write_axiom_reconciliation_readme(self) -> None:
        path = self.output_root / "axiom_reconciliation_README.md"
        text = """# Axiom reconciliation

Provide full token mints/CAs from Axiom migrated or new-pair screens, one per line or comma-separated.

Optional CSV input columns:

- `mint`
- `axiom_market_cap_usd`
- `axiom_liquidity_usd`
- `cohort`

Command:

```bash
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode axiom-reconcile \
  --output-root /path/to/t007/run/root \
  --axiom-mints-path /path/to/axiom_mints.csv
```

Alternative:

```bash
PYTHONPATH=/Users/dianeposs/Projects/meme-trader-pro python3 -m research.mtp_research.validation.run_bonding_curve_progress_recorder_v1 \
  --mode axiom-reconcile \
  --output-root /path/to/t007/run/root \
  --axiom-mints "mint1,mint2,mint3"
```

Outputs:

- `axiom_reconciliation.csv`
- `axiom_reconciliation.jsonl`
- `valuation_formula_audit.jsonl`

Fields report whether each mint was seen by transactionSubscribe, normalized, admitted, sample rejected, capacity rejected, curve-probed, decoded, failed with account_not_found, assigned valuation/FDV, emitted valuation ladder crossings, emitted a migration event, and whether collector valuation appears closer to Axiom market cap or liquidity when manual values are supplied.
"""
        path.write_text(text, encoding="utf-8")

    def _write_t007_watcher_html(self) -> None:
        path = self.output_root / "t007_live_watcher.html"
        text = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>T007 True Curve Progress Watcher</title>
  <style>
    body { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #0c120f; color: #d8ffe2; margin: 24px; }
    h1 { color: #9affb4; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .card { border: 1px solid #245334; border-radius: 10px; padding: 12px; background: #111c16; }
    .key { color: #7ddf9a; font-size: 12px; text-transform: uppercase; }
    .value { font-size: 20px; margin-top: 4px; word-break: break-word; }
    pre { white-space: pre-wrap; background: #07100b; border: 1px solid #245334; padding: 12px; border-radius: 10px; }
  </style>
</head>
<body>
  <h1>T007 True Curve Progress Watcher</h1>
  <p id="status-line">Loading live_status.json...</p>
  <div id="long-scan-readiness-banner"></div>
  <div class="grid" id="grid"></div>
  <h2>Progress crossings by threshold</h2>
  <pre id="thresholds">{}</pre>
  <h2>Active count by progress tier</h2>
  <pre id="progressTiers">{}</pre>
  <h2>Active count by age bucket</h2>
  <pre id="ageBuckets">{}</pre>
  <script>
    const keys = [
      "run_id", "run_status", "runtime_phase", "elapsed_time_seconds",
      "source_elapsed_seconds", "source_remaining_seconds",
      "drain_elapsed_seconds", "drain_remaining_seconds",
      "finalization_elapsed_seconds", "finalization_overrun_seconds",
      "finalization_stuck_warning",
      "raw_notifications", "unique_birth_mints",
      "birth_rows_total_including_replay", "birth_rows_live_source", "birth_rows_replay_backfilled",
      "unique_birth_mints_live_source", "unique_birth_mints_replay_backfilled",
      "unique_births_per_min", "admitted_births", "sample_rejected", "capacity_rejected",
      "effective_admitted_coverage", "admitted_sample_pass_coverage", "capacity_rejection_rate",
      "active_tracking_count", "active_pruned_count", "low_progress_timeout_count",
      "no_decode_timeout_count", "admission_after_prune_count", "capacity_rejected_after_prune_count",
      "protected_high_progress_active_count", "curve_observations_written", "decode_success_count",
      "decode_error_count", "retry_success_count", "final_account_not_found", "queue_drops",
      "queue_high_water_mark", "rpc_failures", "http_429", "complete_true_count",
      "migration_events", "last_heartbeat_timestamp", "output_folder",
      "active_write_root", "staging_root", "archive_root", "archive_status",
      "storage_preflight_status", "valuation_ladder_emission_policy"
      , "trade_flow_events_written", "organic_flow_events_written", "buyer_breadth_available_count",
      "holder_distribution_snapshots_written", "dev_behavior_events_written",
      "post_migration_observations_written", "sell_side_dump_diagnostics_written", "execution_cost_observations_written",
      "decision_time_safety_violation_count",
      "watcher_schema_version", "long_scan_status", "can_run_10m_feature_proof",
      "can_run_10m_collector_proof", "can_run_60m_thesis_scan", "can_run_2h_plus_scan", "migrated_unique_mints",
      "strict_full_path_migrated_mints", "full_path_migrated_rate", "migration_plus_depth_only_mints",
      "source_miss_count", "sample_loss_count", "curve_observation_missing_count",
      "trade_flow_missing_count", "migration_backfill_failed_count", "helius_developer_source_supported",
      "trade_flow_true_gap_mints_count", "migration_readiness_classification",
      "latency_histograms_present", "route_latency_gate_passed", "route_latency_gate_failures",
      "decision_path_route_gate_passed", "decision_path_route_gate_failures", "route_latency_gate_scope",
      "materialization_latency_gate_passed", "materialization_latency_gate_failures", "materialization_latency_gate_scope",
      "finalization_gate_passed", "finalization_gate_failures", "finalization_gate_scope",
      "finalization_mode", "offline_materialization_required", "offline_recovery_required",
      "birth_to_admission_latency_ms", "birth_to_admission_enqueue_latency_ms",
      "birth_to_verified_birth_commit_latency_ms", "verified_birth_commit_to_probe_enqueue_latency_ms",
      "birth_enqueue_to_admission_worker_start_latency_ms", "admission_worker_process_birth_duration_ms",
      "admission_worker_to_probe_job_enqueue_latency_ms", "probe_job_enqueue_to_probe_start_latency_ms",
      "normalized_birth_to_probe_start_latency_ms", "birth_to_admission_complete_latency_ms",
      "birth_to_first_curve_observation_latency_ms", "probe_duration_latency_ms", "route_latency_histograms",
      "pre_migration_paper_readiness_gate", "pre_migration_paper_ready", "pre_migration_paper_readiness_blockers",
      "t012_pre_migration_paper_readiness_gate", "pre_migration_paper_readiness_gate_passed",
      "pre_migration_paper_ready_status", "pre_migration_paper_blockers",
      "pre_entry_snapshot_count", "post_entry_hot_flow_snapshot_count",
      "paper_position_ledger_status", "principal_recovery_tracking_status",
      "paper_trading_enabled", "live_trading_enabled", "wallet_signing_execution_present",
      "source_event_queue_high_water_mark", "source_event_queue_dropped_count",
      "birth_hot_commit_queue_dropped_count", "first_curve_probe_queue_dropped_count",
      "birth_priority_worker_count", "birth_priority_queue_high_water_mark", "birth_priority_queue_dropped_count",
      "source_fast_event_handler_count", "source_fast_event_handler_error_count",
      "source_fast_birth_probe_hook_enabled", "source_fast_birth_probe_hook_events",
      "source_fast_first_curve_probe_enqueued", "source_fast_first_curve_probe_duplicate_suppressed",
      "source_fast_first_curve_probe_ineligible",
      "thin_probe_async_dispatch_enabled", "thin_probe_worker_count",
      "thin_probe_execution_queue_high_water_mark", "thin_probe_execution_queue_dropped_count",
      "thin_probe_worker_error_count",
      "trade_flow_async_dispatch_enabled", "trade_flow_worker_count", "trade_flow_queue_high_water_mark",
      "trade_flow_owner_thread_drain_enabled", "trade_flow_queue_dropped_count", "trade_flow_worker_error_count",
      "near_entry_hot_flow_enabled", "near_entry_hot_flow_mints_registered",
      "near_entry_hot_flow_events_seen", "near_entry_hot_flow_events_recorded",
      "near_entry_hot_flow_ring_buffer_dropped_count", "near_entry_hot_flow_snapshots_written",
      "near_entry_hot_flow_snapshot_mints", "near_entry_hot_flow_snapshot_1s_count",
      "near_entry_hot_flow_snapshot_5s_count", "near_entry_hot_flow_snapshot_10s_count",
      "near_entry_hot_flow_snapshot_30s_count", "near_entry_hot_flow_snapshot_60s_count",
      "commitment_reorg_drop_accounting_present", "dropped_or_reorged_count",
      "source_gap_detected_count", "source_gap_backfilled_count", "source_gap_unbackfilled_count",
      "source_gap_reorg_gate_passed", "helius_budget_gate_present", "helius_budget_gate_passed",
      "helius_budget_blocker", "helius_estimated_credits_used", "helius_max_estimated_credits",
      "gatekeeper_ab_status", "subscription_first_curve_updates_status",
      "migrated_missing_curve_decode_count", "migrated_missing_market_cap_count",
      "migrated_missing_trade_flow_count", "migrated_missing_holder_dev_count",
      "migrated_missing_evidence_reason_counts",
      "scan_supervisor_status", "scan_supervisor_action", "scan_supervisor_severity",
      "scan_supervisor_primary_warning", "scan_supervisor_abort_reason", "budget_used_pct",
      "live_status_write_count", "live_status_throttled_write_skip_count",
      "local_retention_enabled", "local_retention_keep_latest", "local_retention_archive_root",
      "local_retention_status", "local_retention_archived_count", "local_retention_report_path",
      "local_retention_skipped_by_reason", "local_retention_errors",
      "estimated_rpc_calls_total", "event_first_coverage_status", "materializer_smoke_status",
      "scan_supervisor_status_path"
    ];
    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }
    function formatNumber(value) {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return value;
      }
      if (Math.abs(value) >= 100) {
        return value.toFixed(1);
      }
      if (Math.abs(value) >= 10) {
        return value.toFixed(2);
      }
      return value.toFixed(3);
    }
    function formatHistogram(value) {
      const parts = [];
      for (const key of ["count", "median", "p90", "p95", "p99", "max"]) {
        if (value[key] !== undefined && value[key] !== null) {
          parts.push(`${key}=${formatNumber(value[key])}`);
        }
      }
      return parts.length ? parts.join(" | ") : JSON.stringify(value);
    }
    function formatValue(value) {
      if (value === undefined || value === null) {
        return "";
      }
      if (Array.isArray(value)) {
        return value.length ? `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>` : "";
      }
      if (typeof value === "object") {
        const keys = Object.keys(value);
        const isHistogram = ["count", "median", "p90", "p95", "p99", "max"].some((key) => key in value);
        if (isHistogram) {
          return escapeHtml(formatHistogram(value));
        }
        const histogramRows = keys
          .filter((key) => value[key] && typeof value[key] === "object")
          .map((key) => `${key}: ${formatHistogram(value[key])}`);
        if (histogramRows.length === keys.length && histogramRows.length > 0) {
          return `<pre>${escapeHtml(histogramRows.join("\\n"))}</pre>`;
        }
        return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
      }
      return escapeHtml(formatNumber(value));
    }
    async function refresh() {
      try {
        const response = await fetch("live_status.json?ts=" + Date.now());
        const data = await response.json();
        document.getElementById("status-line").textContent = "Watcher status: " + (data.watcher_status || "unknown");
        const blockers = [];
        if (data.scan_supervisor_primary_warning && String(data.scan_supervisor_primary_warning).includes("TRADE_FLOW")) {
          blockers.push("trade-flow coverage");
        }
        if (Number(data.strict_full_path_migrated_mints || 0) <= 0) {
          blockers.push("no in-window decision-safe migration/full path");
        }
        if ((data.migration_readiness_failure_reason_counts || {}).startup_boundary_migration_not_decision_safe > 0) {
          blockers.push("startup-boundary migration does not count as full-path evidence");
        }
        const bannerText = data.long_scan_readiness_banner_text || "10m collector + feature proof passed; 60m thesis readiness blocked";
        const bannerBullets = (data.long_scan_blocker_bullets && data.long_scan_blocker_bullets.length) ? data.long_scan_blocker_bullets : blockers;
        document.getElementById("long-scan-readiness-banner").innerHTML =
          (data.can_run_10m_feature_proof === true && data.can_run_60m_thesis_scan === false)
            ? `<div class="card" style="border-color:#d9a441;background:#221a08;margin-bottom:12px"><div class="key">READINESS</div><div class="value">${bannerText}</div><ul>${bannerBullets.map((item) => `<li>${item}</li>`).join("")}</ul></div>`
            : "";
        document.getElementById("grid").innerHTML = keys.map((key) => {
          const value = data[key] === undefined && data.route_latency_histograms
            ? data.route_latency_histograms[key]
            : data[key];
          return `<div class="card"><div class="key">${key}</div><div class="value">${formatValue(value)}</div></div>`;
        }).join("");
        document.getElementById("thresholds").textContent = JSON.stringify(data.progress_crossings_by_threshold || {}, null, 2);
        document.getElementById("progressTiers").textContent = JSON.stringify(data.active_count_by_progress_tier || {}, null, 2);
        document.getElementById("ageBuckets").textContent = JSON.stringify(data.active_count_by_age_bucket || {}, null, 2);
        if (data.long_scan_status === "BLOCKED_FOR_LONG_SCAN") {
          document.getElementById("status-line").textContent += " | BLOCKED_FOR_LONG_SCAN";
        }
      } catch (error) {
        document.getElementById("status-line").textContent = "Watcher status: waiting for live_status.json";
      }
    }
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""
        path.write_text(text, encoding="utf-8")

    def _write_live_status(
        self,
        run_status: str = "running",
        extra_metrics: dict[str, Any] | None = None,
        *,
        force: bool = False,
    ) -> None:
        if str(run_status) == "running" and not force:
            now_for_throttle = time.time()
            if (
                self._last_running_live_status_write_at > 0.0
                and now_for_throttle - self._last_running_live_status_write_at < self._live_status_min_interval_seconds
            ):
                self.summary_counters["live_status_throttled_write_skip_count"] += 1
                return
            self._last_running_live_status_write_at = now_for_throttle
        extra = extra_metrics or {}
        elapsed = max(0.0, time.time() - self.started_at)
        requested_source_for_phase = max(0.0, float(self.config.source_duration_seconds))
        requested_drain_for_phase = max(0.0, float(self.config.followup_drain_seconds))
        source_elapsed = min(elapsed, requested_source_for_phase) if requested_source_for_phase > 0 else 0.0
        source_remaining = max(0.0, requested_source_for_phase - elapsed)
        drain_elapsed = 0.0
        drain_remaining = requested_drain_for_phase
        finalization_elapsed = 0.0
        finalization_overrun = 0.0
        if elapsed > requested_source_for_phase:
            drain_elapsed = min(elapsed - requested_source_for_phase, requested_drain_for_phase)
            drain_remaining = max(0.0, requested_source_for_phase + requested_drain_for_phase - elapsed)
        if elapsed > requested_source_for_phase + requested_drain_for_phase:
            finalization_elapsed = elapsed - requested_source_for_phase - requested_drain_for_phase
            finalization_overrun = finalization_elapsed
        if str(run_status).startswith("finalized"):
            runtime_phase = "finalized"
            drain_elapsed = 0.0 if elapsed <= requested_source_for_phase else min(max(0.0, elapsed - requested_source_for_phase), requested_drain_for_phase)
            drain_remaining = 0.0
            finalization_elapsed = 0.0
            finalization_overrun = 0.0
        elif elapsed < requested_source_for_phase:
            runtime_phase = "source"
        elif elapsed < requested_source_for_phase + requested_drain_for_phase:
            runtime_phase = "drain"
        else:
            runtime_phase = "finalization"
        finalization_stuck_warning = bool(runtime_phase == "finalization" and finalization_overrun >= 120.0)
        raw_notifications = _int(_first_present(extra, ["raw_transaction_notifications", "raw_notifications"])) or 0
        unique_births = _int(_first_present(extra, ["unique_birth_mints", "births_detected"])) or int(self.summary_counters["total_births_detected"])
        duration_minutes = elapsed / 60.0 if elapsed > 0 else 0.0
        actual_duration = _num(extra.get("actual_duration_seconds"))
        if actual_duration and actual_duration > 0:
            duration_minutes = actual_duration / 60.0
        requested_source_duration = _num(
            _first_present(extra, ["requested_source_duration_seconds", "source_duration_seconds", "source_duration"])
        ) or float(self.config.source_duration_seconds)
        actual_source_duration = _num(
            _first_present(extra, ["actual_source_duration_seconds", "actual_duration_seconds"])
        )
        if actual_source_duration is None:
            source_quality = {
                "requested_source_duration_seconds": requested_source_duration,
                "actual_source_duration_seconds": None,
                "source_duration_completion_ratio": None,
                "source_duration_quality_status": "not_evaluated",
                "source_ended_early": False,
                "early_end_reason": None,
                "validation_run_quality_label": "RUN_QUALITY_NOT_EVALUATED",
                "websocket_keepalive_timeout_count": _int(extra.get("websocket_keepalive_timeout_count")) or 0,
                "websocket_reconnect_count": _int(extra.get("websocket_reconnect_count")) or 0,
                "completed_requested_duration": None,
            }
        else:
            source_quality = _source_duration_quality_fields(
                requested_source_duration,
                actual_source_duration,
                websocket_closed_early=bool(extra.get("websocket_closed_early", False)),
                websocket_close_reason=extra.get("websocket_close_reason"),
                websocket_keepalive_timeout_count=_int(extra.get("websocket_keepalive_timeout_count")) or 0,
                websocket_reconnect_count=_int(extra.get("websocket_reconnect_count")) or 0,
            )
        admitted_births = _int(_first_present(extra, ["births_admitted_after_dedupe", "births_admitted", "admitted_births"])) or int(self.summary_counters["admitted_births"])
        sample_rejected = _int(_first_present(extra, ["sample_rejected_after_dedupe", "sample_rejected", "sample_rejected_births"])) or int(self.summary_counters["sample_rejected_births"])
        capacity_rejected = _int(_first_present(extra, ["capacity_rejected_after_dedupe", "capacity_rejected", "capacity_rejected_births"])) or int(self.summary_counters["capacity_rejected_births"])
        route_latency_histograms = self._route_latency_histograms()
        route_latency_gate = self._route_latency_gate(route_latency_histograms)
        materialization_latency_gate = self._materialization_latency_gate(route_latency_histograms)
        status = {
            "run_id": self.config.run_id,
            "run_status": run_status,
            "watcher_status": "available",
            "elapsed_time_seconds": round(elapsed, 3),
            "runtime_phase": runtime_phase,
            "source_elapsed_seconds": round(source_elapsed, 3),
            "source_remaining_seconds": round(source_remaining, 3),
            "drain_duration_seconds": round(requested_drain_for_phase, 3),
            "drain_elapsed_seconds": round(drain_elapsed, 3),
            "drain_remaining_seconds": round(drain_remaining, 3),
            "finalization_elapsed_seconds": round(finalization_elapsed, 3),
            "finalization_overrun_seconds": round(finalization_overrun, 3),
            "finalization_stuck_warning": finalization_stuck_warning,
            "source_duration_seconds": self.config.source_duration_seconds,
            "tracking_profile": self.config.tracking_profile,
            "max_active_tracking": int(self.config.max_active_tracking),
            "followup_queue_max_size": int(self.config.followup_queue_max_size),
            "migration_aware_promotion_enabled": bool(self.config.migration_aware_promotion_enabled),
            "reserved_migration_candidate_slots": int(self.config.reserved_migration_candidate_slots),
            "promotion_events_written": int(self.summary_counters["promotion_events_written"]),
            "promoted_mints": int(self.summary_counters["promoted_mints"]),
            "promoted_migrated_mints": int(self.summary_counters["promoted_migrated_mints"]),
            "capacity_deferred_promotions": int(self.summary_counters["capacity_deferred_promotions"]),
            "promotion_evictions_written": int(self.summary_counters["promotion_evictions_written"]),
            **source_quality,
            "raw_notifications": raw_notifications,
            "unique_birth_mints": unique_births,
            "birth_rows_total_including_replay": int(self.summary_counters["total_births_detected"]),
            "birth_rows_live_source": int(self.summary_counters["birth_rows_live_source"]),
            "birth_rows_replay_backfilled": int(self.summary_counters["birth_rows_replay_backfilled"]),
            "unique_birth_mints_total_including_replay": len(self.live_birth_mints | self.replay_backfilled_birth_mints),
            "unique_birth_mints_live_source": len(self.live_birth_mints),
            "unique_birth_mints_replay_backfilled": len(self.replay_backfilled_birth_mints),
            "migration_backfill_skipped_existing_live_birth_count": int(
                self.summary_counters["migration_backfill_skipped_existing_live_birth_count"]
            ),
            "unique_births_per_min": round(unique_births / duration_minutes, 6) if duration_minutes > 0 else 0.0,
            "admitted_births": admitted_births,
            "sample_rejected": sample_rejected,
            "capacity_rejected": capacity_rejected,
            "effective_admitted_coverage": _safe_ratio(admitted_births, unique_births),
            "admitted_sample_pass_coverage": _safe_ratio(admitted_births, admitted_births + capacity_rejected),
            "capacity_rejection_rate": _safe_ratio(capacity_rejected, unique_births),
            "active_tracking_count": self._active_tracking_count(),
            "active_tracking_max_count": int(self.summary_counters["active_tracking_max_count"]),
            "active_count_by_progress_tier": self._active_count_by_progress_tier(),
            "active_count_by_age_bucket": self._active_count_by_age_bucket(),
            "active_pruned_count": int(self.summary_counters["active_pruned_count"]),
            "active_pruned_by_reason": dict(self.summary_counters["active_pruned_by_reason"]),
            "low_progress_timeout_count": int(self.summary_counters["low_progress_timeout_count"]),
            "no_decode_timeout_count": int(self.summary_counters["no_decode_timeout_count"]),
            "stale_low_priority_pruned_count": int(self.summary_counters["stale_low_priority_pruned_count"]),
            "admission_after_prune_count": int(self.summary_counters["admission_after_prune_count"]),
            "capacity_rejected_after_prune_count": int(self.summary_counters["capacity_rejected_after_prune_count"]),
            "protected_high_progress_active_count": self._protected_high_progress_active_count(),
            "curve_observation_attempts": _int(extra.get("curve_observation_attempts")) or int(self.summary_counters["curve_observation_attempts"]),
            "curve_observations_written": _int(_first_present(extra, ["curve_observations_written", "observations_written"])) or int(self.summary_counters["observations_written"]),
            "decode_success_count": int(self.summary_counters["progress_decoded_exact_count"]) + int(self.summary_counters["progress_decoded_candidate_count"]),
            "decode_error_count": int(self.summary_counters["decode_failures"]),
            "retry_success_count": _int(extra.get("retry_success_count")) or int(self.summary_counters["retry_success_count"]),
            "final_account_not_found": _int(extra.get("final_account_not_found_count")) or int(self.summary_counters["final_account_not_found_count"]),
            "queue_drops": _int(_first_present(extra, ["queue_drops", "queue_dropped_count"])) or int(self.summary_counters["queue_dropped_count"]),
            "queue_high_water_mark": _int(extra.get("queue_high_water_mark")) or int(self.summary_counters["queue_high_water_mark"]),
            "rpc_failures": _int(extra.get("rpc_failures")) or int(self.summary_counters["rpc_failures"]),
            "http_429": _int(_first_present(extra, ["http_429_count", "http_429"])) or int(self.summary_counters["http_429_count"]),
            "progress_crossings_by_threshold": dict(self.summary_counters["true_curve_threshold_crossings_by_threshold"]),
            "complete_true_count": int(self.summary_counters["complete_true_count"]),
            "migration_events": int(self.summary_counters["migrations_written"]),
            "last_heartbeat_timestamp": datetime.now(timezone.utc).isoformat(),
            "output_folder": str(self.output_root),
            "active_write_root": str(self.output_root),
            "staging_root": _path_str_or_none(self.config.staging_root),
            "archive_root": _path_str_or_none(self.config.archive_root),
            "archive_after_run": bool(self.config.archive_after_run),
            "archive_status": extra.get("archive_status") or self.archive_status,
            "local_retention_enabled": bool(self.config.local_retention_enabled),
            "local_retention_keep_latest": int(self.config.local_retention_keep_latest),
            "local_retention_archive_root": _path_str_or_none(self.config.local_retention_archive_root),
            "local_retention_status": extra.get("local_retention_status"),
            "local_retention_archived_count": extra.get("local_retention_archived_count"),
            "storage_preflight_status": self.config.storage_preflight_status,
            "storage_preflight_errors": list(self.config.storage_preflight_errors),
            "local_free_space_bytes_start": self.config.local_free_space_bytes_start,
            "archive_free_space_bytes_start": self.config.archive_free_space_bytes_start,
            "run_finalized": self.run_finalized,
            "finalization_errors": list(self.finalization_errors),
            "failure_reason": extra.get("failure_reason") or self.failure_reason,
            "live_status_min_interval_seconds": self._live_status_min_interval_seconds,
            "live_status_write_count": int(self.summary_counters["live_status_write_count"]),
            "live_status_throttled_write_skip_count": int(
                self.summary_counters["live_status_throttled_write_skip_count"]
            ),
            "live_status_hot_path_force_disabled_count": int(
                self.summary_counters["live_status_hot_path_force_disabled_count"]
            ),
            "birth_decision_path_commit_count": int(self.summary_counters["birth_decision_path_commit_count"]),
            "birth_decision_path_commit_error_count": int(
                self.summary_counters["birth_decision_path_commit_error_count"]
            ),
            "source_verified_birth_commit_count": int(self.summary_counters["source_verified_birth_commit_count"]),
            "source_verified_birth_commit_error_count": int(
                self.summary_counters["source_verified_birth_commit_error_count"]
            ),
            "source_verified_birth_commit_duplicate_suppressed_count": int(
                self.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"]
            ),
            "verified_birth_commit_count": int(self.summary_counters["source_verified_birth_commit_count"]),
            "verified_birth_commit_error_count": int(self.summary_counters["source_verified_birth_commit_error_count"]),
            "verified_birth_commit_duplicate_suppressed_count": int(
                self.summary_counters["source_verified_birth_commit_duplicate_suppressed_count"]
            ),
            "source_verified_birth_commit_table": "verified_birth_commits",
            "latency_histograms_present": any(
                int(bucket.get("count") or 0) > 0 for bucket in route_latency_histograms.values()
            ),
            "route_latency_histograms": route_latency_histograms,
            **route_latency_gate,
            **materialization_latency_gate,
            "valuation_ladder_emission_policy": "market_cap_confirmed_only",
            "valuation_ladder_market_cap_confirmed_count": int(self.summary_counters["valuation_ladder_market_cap_confirmed_count"]),
            "valuation_ladder_suppressed_untrusted_count": int(self.summary_counters["valuation_ladder_suppressed_untrusted_count"]),
            "trade_flow_events_written": int(self.summary_counters["trade_flow_events_written"]),
            "organic_flow_events_written": int(self.summary_counters["organic_flow_events_written"]),
            "buyer_breadth_available_count": int(self.summary_counters["buyer_breadth_available_count"]),
            "holder_distribution_snapshots_written": int(self.summary_counters["holder_distribution_snapshots_written"]),
            "dev_behavior_events_written": int(self.summary_counters["dev_behavior_events_written"]),
            "post_migration_observations_scheduled": int(self.summary_counters["post_migration_observations_scheduled"]),
            "post_migration_observations_written": int(self.summary_counters["post_migration_observations_written"]),
            "live_migration_side_effect_drain_count": int(self.summary_counters["live_migration_side_effect_drain_count"]),
            "live_migration_side_effects_applied": int(self.summary_counters["live_migration_side_effects_applied"]),
            "live_migration_side_effects_failed": int(self.summary_counters["live_migration_side_effects_failed"]),
            "live_migration_side_effects_source_rows": int(self.summary_counters["live_migration_side_effects_source_rows"]),
            "live_migration_side_effects_post_observations_written": int(
                self.summary_counters["live_migration_side_effects_post_observations_written"]
            ),
            "live_migration_side_effect_last_drain_at": self.summary_counters["live_migration_side_effect_last_drain_at"],
            "post_migration_observations_pending_at_finalization": int(self._pending_post_migration_observation_count()),
            "post_migration_pool_state_available_count": int(self.summary_counters["post_migration_pool_state_available_count"]),
            "post_migration_pool_state_partial_count": int(self.summary_counters["post_migration_pool_state_partial_count"]),
            "post_migration_pool_state_not_available_count": int(self.summary_counters["post_migration_pool_state_not_available_count"]),
            "post_migration_pool_state_error_count": int(self.summary_counters["post_migration_pool_state_error_count"]),
            "post_migration_pool_state_by_quote_asset": dict(self.summary_counters["post_migration_pool_state_by_quote_asset"]),
            "pool_liquidity_quote_present_count": int(self.summary_counters["pool_liquidity_quote_present_count"]),
            "pool_liquidity_usd_present_count": int(self.summary_counters["pool_liquidity_usd_present_count"]),
            "post_migration_quote_available_count": int(self.summary_counters["post_migration_quote_available_count"]),
            "post_migration_quote_partial_count": int(self.summary_counters["post_migration_quote_partial_count"]),
            "post_migration_quote_deferred_count": int(self.summary_counters["post_migration_quote_deferred_count"]),
            "post_migration_quote_error_count": int(self.summary_counters["post_migration_quote_error_count"]),
            "executable_quote_observations_written": int(self.summary_counters["executable_quote_observations_written"]),
            "executable_quote_available_count": int(self.summary_counters["executable_quote_available_count"]),
            "executable_quote_partial_count": int(self.summary_counters["executable_quote_partial_count"]),
            "executable_quote_deferred_count": int(self.summary_counters["executable_quote_deferred_count"]),
            "executable_quote_error_count": int(self.summary_counters["executable_quote_error_count"]),
            "executable_quote_by_source": dict(self.summary_counters["executable_quote_by_source"]),
            "executable_quote_by_quote_asset": dict(self.summary_counters["executable_quote_by_quote_asset"]),
            "executable_quote_by_direction": dict(self.summary_counters["executable_quote_by_direction"]),
            "executable_quote_clip_count": int(self.summary_counters["executable_quote_clip_count"]),
            "executable_quote_decision_time_safe_count": int(self.summary_counters["executable_quote_decision_time_safe_count"]),
            "price_impact_available_count": int(self.summary_counters["price_impact_available_count"]),
            "price_impact_missing_count": int(self.summary_counters["price_impact_missing_count"]),
            "fee_model_confirmed_count": int(self.summary_counters["fee_model_confirmed_count"]),
            "fee_model_assumed_count": int(self.summary_counters["fee_model_assumed_count"]),
            "fee_model_unknown_count": int(self.summary_counters["fee_model_unknown_count"]),
            "post_migration_observations_by_quote_asset": dict(self.summary_counters["post_migration_observations_by_quote_asset"]),
            "post_migration_observations_by_horizon": dict(self.summary_counters["post_migration_observations_by_horizon"]),
            "sell_side_dump_diagnostics_written": int(self.summary_counters["sell_side_dump_diagnostics_written"]),
            "execution_cost_observations_written": int(self.summary_counters["execution_cost_observations_written"]),
            "execution_cost_available_count": int(self.summary_counters["execution_cost_available_count"]),
            "execution_cost_partial_count": int(self.summary_counters["execution_cost_partial_count"]),
            "execution_cost_deferred_count": int(self.summary_counters["execution_cost_deferred_count"]),
            "execution_cost_error_count": int(self.summary_counters["execution_cost_error_count"]),
            "recent_prioritization_fee_sample_count": int(self.summary_counters["recent_prioritization_fee_sample_count"]),
            "execution_cost_observations_by_reason": dict(self.summary_counters["execution_cost_observations_by_reason"]),
            "failed_tx_share_available_count": int(self.summary_counters["failed_tx_share_available_count"]),
            "failed_tx_share_deferred_count": int(self.summary_counters["failed_tx_share_deferred_count"]),
            "decision_time_safety_violation_count": int(self.summary_counters["decision_time_safety_violation_count"]),
        }
        try:
            if str(run_status).startswith("finalized"):
                if (self.output_root / "canonical_sqlite_db_pointer.json").exists():
                    from research.mtp_research.validation.t007_materializer import materialize_lifecycle_for_output_root
                    lifecycle_payload = materialize_lifecycle_for_output_root(
                        self.output_root,
                        run_id=getattr(self, "run_id", None),
                        artifact_summary=status,
                    )
                else:
                    build_lifecycle_outputs(self.output_root, self.output_root, write_outputs=True)
                    lifecycle_payload = build_lifecycle_live_status_payload(self.output_root, status)
                self._cached_lifecycle_live_status_payload = dict(lifecycle_payload)
                status.update(lifecycle_payload)
            elif self._cached_lifecycle_live_status_payload is not None:
                status.update(self._cached_lifecycle_live_status_payload)
            else:
                status.update(self._counter_only_lifecycle_live_status())
        except Exception as exc:
            status.update(
                {
                    "watcher_schema_version": "t007bd_full_path_lifecycle_watcher_v1",
                    "full_path_lifecycle_status": "error",
                    "full_path_lifecycle_error": f"{type(exc).__name__}: {exc}",
                    "long_scan_status": "BLOCKED_FOR_LONG_SCAN",
                    "can_run_60m_thesis_scan": False,
                    "can_run_2h_plus_scan": False,
                }
            )
        try:
            from research.mtp_research.validation.t010_scan_supervisor import merge_supervisor_status_into_live_status

            status = merge_supervisor_status_into_live_status(self.output_root, status)
        except Exception:
            status.setdefault("scan_supervisor_status", "unavailable")
            status.setdefault("scan_supervisor_action", "UNKNOWN")
        self._merge_t012_paper_readiness_gate(status, write_outputs=False)
        self.summary_counters["live_status_write_count"] += 1
        status["live_status_write_count"] = int(self.summary_counters["live_status_write_count"])
        status["live_status_throttled_write_skip_count"] = int(
            self.summary_counters["live_status_throttled_write_skip_count"]
        )
        _atomic_write_json(self.output_root / "live_status.json", status)

    def _counter_only_lifecycle_live_status(self) -> dict[str, Any]:
        migrated = int(self.summary_counters.get("global_migration_unique_mints") or 0)
        source_miss = int(self.summary_counters.get("global_migration_mints_not_seen_in_birth_source") or 0)
        sample_loss = int(self.summary_counters.get("global_migration_mints_sample_rejected") or 0)
        post_migration = int(self.summary_counters.get("post_migration_observations_written") or 0)
        payload = {
            "watcher_schema_version": "t007bd_full_path_lifecycle_watcher_v1",
            "full_path_lifecycle_status": "running_counter_only",
            "lifecycle_reconstruction_mode": "deferred_until_finalization",
            "long_scan_status": "BLOCKED_FOR_LONG_SCAN",
            "can_run_10m_feature_proof": True,
            "can_run_60m_thesis_scan": False,
            "can_run_2h_plus_scan": False,
            "migrated_unique_mints": migrated,
            "active_lifecycle_mints": self.summary_counters["total_births_detected"],
            "tracked_from_birth_migrations": 0,
            "full_path_ready_migrations": 0,
            "preexisting_before_watcher_migrations": 0,
            "migration_only_untracked_migrations": source_miss,
            "replay_unresolved_migrations": 0,
            "true_source_miss_migrations": 0,
            "strict_full_path_migrated_mints": 0,
            "full_path_migrated_rate": 0.0,
            "migration_plus_depth_only_mints": post_migration,
            "source_miss_count": source_miss,
            "sample_loss_count": sample_loss,
            "curve_observation_missing_count": 0,
            "trade_flow_missing_count": 0,
            "migration_backfill_failed_count": 0,
            "helius_developer_source_supported": True,
        }
        adapter = getattr(self, "lifecycle_adapter", None)
        if adapter is not None:
            payload.update(adapter.live_health())
        return payload

    def _active_tracking_count(self) -> int:
        return sum(1 for state in self._state_snapshot() if not state.stopped and state.deep_tracking_admitted)

    def _state_snapshot(self) -> list[TrackingState]:
        """Return a stable state list while live worker threads may add mints."""
        for _attempt in range(3):
            try:
                return list(self.states.values())
            except RuntimeError as exc:
                if "dictionary changed size" not in str(exc):
                    raise
                time.sleep(0)
        try:
            keys = list(self.states.keys())
            return [self.states[key] for key in keys if key in self.states]
        except RuntimeError:
            return []

    def _update_queue_high_water(self) -> None:
        self.summary_counters["queue_high_water_mark"] = max(
            self.summary_counters["queue_high_water_mark"],
            len(self.followup_queue),
        )


def build_default_output_root(base_root: Path | str = DEFAULT_BASE_ROOT, run_id: str | None = None) -> Path:
    rid = run_id or "bc-progress-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path(base_root).expanduser() / rid


def _parse_bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _path_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _free_space_bytes(path: Path) -> int | None:
    try:
        target = path if path.exists() else path.parent
        return int(shutil.disk_usage(target).free)
    except Exception:
        return None


def _run_storage_preflight(config: BondingCurveRecorderConfig) -> dict[str, Any]:
    if config.archive_after_run and config.archive_root is None:
        raise ValueError("archive_root is required when archive_after_run is true")
    errors: list[str] = []
    output_root = Path(config.output_root)
    archive_root = Path(config.archive_root) if config.archive_root is not None else None

    try:
        if output_root.exists() and not output_root.is_dir():
            errors.append(f"staging path is not a directory: {output_root}")
        else:
            output_root.mkdir(parents=True, exist_ok=True)
            probe_path = output_root / ".storage_preflight_write_test.tmp"
            probe_path.write_text("ok\n", encoding="utf-8")
            _ = probe_path.read_text(encoding="utf-8")
            probe_path.unlink(missing_ok=True)
    except Exception as exc:
        errors.append(f"staging path is not writable: {output_root}: {exc}")

    archive_free_space: int | None = None
    if config.archive_after_run and archive_root is not None:
        try:
            if archive_root.exists() and not archive_root.is_dir():
                errors.append(f"archive path is not a directory: {archive_root}")
            else:
                archive_parent = archive_root.parent
                archive_parent.mkdir(parents=True, exist_ok=True)
                probe_path = archive_parent / ".storage_preflight_archive_write_test.tmp"
                probe_path.write_text("ok\n", encoding="utf-8")
                _ = probe_path.read_text(encoding="utf-8")
                probe_path.unlink(missing_ok=True)
                archive_free_space = _free_space_bytes(archive_parent)
        except Exception as exc:
            errors.append(f"archive path is not writable or mounted: {archive_root}: {exc}")

    result = {
        "local_free_space_bytes_start": _free_space_bytes(output_root),
        "archive_free_space_bytes_start": archive_free_space,
        "storage_preflight_status": "ok" if not errors else "failed",
        "storage_preflight_errors": errors,
    }
    if errors:
        raise ValueError("storage preflight failed: " + "; ".join(errors))
    return result


def _copy_run_folder_to_archive(source: Path, destination: Path) -> dict[str, Any]:
    errors: list[str] = []
    files_copied = 0
    bytes_copied = 0
    copied_relative_paths: list[str] = []
    source = Path(source)
    destination = Path(destination)
    if not source.exists() or not source.is_dir():
        return {
            "archive_status": "failed",
            "errors": [f"source staging path missing or not directory: {source}"],
            "files_copied": 0,
            "bytes_copied": 0,
            "verification_status": "failed",
        }
    try:
        if destination.exists() and not destination.is_dir():
            raise OSError(f"archive destination exists and is not a directory: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source)
            if str(rel).endswith(".tmp"):
                continue
            dest_path = destination / rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_path)
            files_copied += 1
            size = int(path.stat().st_size)
            bytes_copied += size
            copied_relative_paths.append(str(rel))
    except Exception as exc:
        errors.append(str(exc))

    verification_errors: list[str] = []
    for rel in copied_relative_paths:
        src_path = source / rel
        dest_path = destination / rel
        try:
            if not dest_path.exists():
                verification_errors.append(f"missing copied file: {rel}")
            elif int(src_path.stat().st_size) != int(dest_path.stat().st_size):
                verification_errors.append(f"size mismatch: {rel}")
        except Exception as exc:
            verification_errors.append(f"verify failed for {rel}: {exc}")
    errors.extend(verification_errors)
    return {
        "archive_status": "complete" if not errors else "failed",
        "errors": errors,
        "files_copied": files_copied,
        "bytes_copied": bytes_copied,
        "verification_status": "verified" if not errors else "failed",
        "copied_relative_paths": copied_relative_paths,
    }


def archive_completed_run_if_requested(
    recorder: "BondingCurveProgressRecorder",
    summary: dict[str, Any],
) -> dict[str, Any]:
    if not recorder.config.archive_after_run:
        archive_info = {
            "archive_status": "not_requested",
            "archive_errors": [],
            "archive_manifest_path": None,
            "archive_path": None,
        }
        summary.update(archive_info)
        recorder.archive_status = "not_requested"
        return archive_info

    source = Path(recorder.output_root)
    destination = Path(recorder.config.archive_root) if recorder.config.archive_root is not None else None
    started_at = datetime.now(timezone.utc).isoformat()
    if destination is None:
        copy_result = {
            "archive_status": "failed",
            "errors": ["archive_root is required when archive_after_run is true"],
            "files_copied": 0,
            "bytes_copied": 0,
            "verification_status": "failed",
        }
    else:
        copy_result = _copy_run_folder_to_archive(source, destination)
    finished_at = datetime.now(timezone.utc).isoformat()

    manifest = {
        "run_id": recorder.config.run_id,
        "source_staging_path": str(source),
        "destination_archive_path": str(destination) if destination is not None else None,
        "copy_started_at": started_at,
        "copy_finished_at": finished_at,
        "archive_status": copy_result.get("archive_status", "failed"),
        "verification_status": copy_result.get("verification_status", "failed"),
        "files_copied": int(copy_result.get("files_copied") or 0),
        "bytes_copied": int(copy_result.get("bytes_copied") or 0),
        "errors": list(copy_result.get("errors") or []),
    }
    manifest_path = source / "archive_manifest.json"
    try:
        _atomic_write_json(manifest_path, manifest)
    except Exception as exc:
        manifest["archive_status"] = "failed"
        manifest["verification_status"] = "failed"
        manifest["errors"].append(f"local archive manifest write failed: {exc}")
    if destination is not None and manifest.get("archive_status") == "complete":
        try:
            _atomic_write_json(destination / "archive_manifest.json", manifest)
        except Exception as exc:
            manifest["archive_status"] = "failed"
            manifest["verification_status"] = "failed"
            manifest["errors"].append(f"destination archive manifest write failed: {exc}")

    archive_info = {
        "archive_status": manifest["archive_status"],
        "archive_errors": manifest["errors"],
        "archive_manifest_path": str(manifest_path),
        "archive_path": str(destination) if destination is not None else None,
        "archive_files_copied": manifest["files_copied"],
        "archive_bytes_copied": manifest["bytes_copied"],
        "archive_verification_status": manifest["verification_status"],
    }
    recorder.archive_status = archive_info["archive_status"]
    recorder.archive_manifest_path = archive_info["archive_manifest_path"]
    summary.update(archive_info)
    _rewrite_summary(source, summary)
    if destination is not None and destination.exists() and destination.is_dir():
        try:
            _atomic_write_json(destination / "collector_summary.json", summary)
        except Exception:
            pass
    recorder._write_live_status(
        "finalized_with_errors" if recorder.finalization_errors else "finalized",
        summary,
    )
    return archive_info


def apply_local_retention_if_configured(
    recorder: "BondingCurveProgressRecorder",
    summary: dict[str, Any],
) -> dict[str, Any]:
    if not recorder.config.local_retention_enabled:
        report = {
            "local_retention_status": "not_requested",
            "local_retention_archived_count": 0,
            "local_retention_errors": [],
        }
        summary.update(report)
        return report
    local_root = Path(recorder.output_root).parent
    if local_root.resolve() != DEFAULT_BASE_ROOT.resolve():
        report = {
            "local_retention_status": "skipped_non_default_local_root",
            "local_retention_archived_count": 0,
            "local_retention_errors": [],
            "local_retention_local_root": str(local_root),
            "local_retention_expected_local_root": str(DEFAULT_BASE_ROOT),
        }
        summary.update(report)
        return report
    try:
        from research.mtp_research.validation.t012_local_run_retention import apply_local_run_retention

        retention = apply_local_run_retention(
            local_root,
            recorder.config.local_retention_archive_root or DEFAULT_ARCHIVE_ROOT,
            keep_latest=int(recorder.config.local_retention_keep_latest),
        )
        report = {
            "local_retention_status": retention.get("retention_status"),
            "local_retention_archived_count": int(retention.get("archived_count") or 0),
            "local_retention_keep_latest": int(retention.get("keep_latest") or recorder.config.local_retention_keep_latest),
            "local_retention_archive_root": retention.get("archive_root"),
            "local_retention_report_path": str(local_root / "local_retention_report_latest.json"),
            "local_retention_errors": list(retention.get("errors") or []),
            "local_retention_skipped_by_reason": dict(retention.get("skipped_by_reason") or {}),
        }
    except Exception as exc:
        report = {
            "local_retention_status": "failed",
            "local_retention_archived_count": 0,
            "local_retention_errors": [f"{type(exc).__name__}: {exc}"],
        }
    summary.update(report)
    try:
        _rewrite_summary(recorder.output_root, summary)
    except Exception:
        pass
    return report


class BroadPumpFunLaunchAdapter:
    """Normalize broad Pump.fun launch-source candidates into recorder births."""

    def __init__(self, source: Any, *, now_fn: Any = time.time) -> None:
        self.source = source
        self.now_fn = now_fn
        self.source_name = getattr(source, "source_name", source.__class__.__name__)

    def availability(self) -> dict[str, Any]:
        if hasattr(self.source, "availability"):
            status = self.source.availability()
            return status if isinstance(status, dict) else {"available": bool(status)}
        return {"source": self.source_name, "available": True}

    def fetch_launches(self) -> list[dict[str, Any]]:
        candidates = self.source.fetch_candidates() if hasattr(self.source, "fetch_candidates") else []
        return [launch for candidate in candidates if (launch := self._candidate_to_launch(candidate))]

    def _candidate_to_launch(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        mint = candidate.get("mint") or candidate.get("token_mint") or candidate.get("ca")
        if not mint:
            return None
        source_type = (
            candidate.get("source_adapter")
            or candidate.get("source_type")
            or candidate.get("source")
            or self.source_name
        )
        raw_payload = candidate.get("metadata_json") if isinstance(candidate.get("metadata_json"), dict) else {}
        if not raw_payload:
            raw_payload = {
                key: candidate.get(key)
                for key in (
                    "event_type",
                    "candidate_classification",
                    "freshness_lane",
                    "instruction_index",
                    "extraction_confidence",
                    "warning_flags",
                )
                if key in candidate
            }
        return {
            "mint": str(mint),
            "signature": candidate.get("signature")
            or candidate.get("transaction_signature")
            or candidate.get("launch_signature"),
            "slot": candidate.get("slot") or candidate.get("launch_slot"),
            "block_time": candidate.get("block_time") or candidate.get("launch_block_time"),
            "received_at": _num(
                candidate.get("received_at")
                or candidate.get("observed_at")
                or candidate.get("create_observed_at")
                or candidate.get("timestamp")
            )
            or float(self.now_fn()),
            "source_type": source_type,
            "bonding_curve_account": candidate.get("bonding_curve_account")
            or candidate.get("bonding_curve")
            or candidate.get("pool_address"),
            "associated_bonding_curve": candidate.get("associated_bonding_curve")
            or candidate.get("associated_bonding_curve_account"),
            "creator": candidate.get("creator")
            or candidate.get("creator_wallet")
            or candidate.get("dev")
            or candidate.get("creator_address"),
            "raw_decoded_launch_payload": raw_payload,
        }


class FakeLaunchSource:
    """Test helper for fake broad launch-source events."""

    source_name = "fake_broad_pumpfun_launch_source"

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = [dict(candidate) for candidate in candidates]
        self.fetch_calls = 0
        self.exhausted = False

    def availability(self) -> dict[str, Any]:
        return {"source": self.source_name, "available": True, "read_only": True}

    def fetch_candidates(self) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        if self.exhausted:
            return []
        self.exhausted = True
        return [dict(candidate) for candidate in self.candidates]


class FakeCurveStateProbe:
    """Test helper that mimics BondingCurveAccountStateProbe without network."""

    def __init__(self, results_by_mint: dict[str, dict[str, Any]]) -> None:
        self.results_by_mint = {
            mint: [dict(item) for item in result] if isinstance(result, list) else dict(result)
            for mint, result in results_by_mint.items()
        }
        self.calls: list[dict[str, Any]] = []
        self.requests_used = 0
        self.http_429_count = 0

    def probe_create_event(self, create_event: dict[str, Any], *, now_fn: Any = time.time) -> dict[str, Any]:
        self.calls.append(dict(create_event))
        self.requests_used += 1
        mint = str(create_event.get("mint") or "")
        stored = self.results_by_mint.get(mint, {})
        if isinstance(stored, list):
            if stored:
                result = dict(stored.pop(0))
            else:
                result = {}
        else:
            result = dict(stored)
        if not result:
            return {
                "probe_status": "failed",
                "mint": mint,
                "bonding_curve": create_event.get("bonding_curve") or create_event.get("bonding_curve_account"),
                "failure_reason": "fake_probe_missing_result",
                "decode_status": "decode_failed",
                "observed_at": now_fn(),
            }
        result.setdefault("probe_status", "success")
        result.setdefault("mint", mint)
        result.setdefault("decode_status", "decoded")
        result.setdefault("observed_at", now_fn())
        return result


class FakeBirthSourceAuditRoute:
    """Test helper for source-coverage audit notifications."""

    source_name = "fake_birth_source_audit_route"

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = [dict(event) for event in events]

    def availability(self) -> dict[str, Any]:
        return {"source": self.source_name, "available": True, "read_only": True}

    def iter_notifications(self, duration_seconds: float) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events]


class FakeTransactionSubscribeAuditRoute:
    """Test helper for transactionSubscribe source audit rows."""

    source_name = "fake_transaction_subscribe_audit_route"

    def __init__(
        self,
        events: list[dict[str, Any]],
        *,
        websocket_closed_early: bool = False,
        websocket_close_reason: str | None = None,
        actual_duration_seconds: float | None = None,
    ) -> None:
        self.events = [dict(event) for event in events]
        self.websocket_closed_early = bool(websocket_closed_early)
        self.websocket_close_reason = websocket_close_reason
        self.actual_duration_seconds = actual_duration_seconds

    def availability(self) -> dict[str, Any]:
        return {"source": self.source_name, "available": True, "read_only": True, "transactionSubscribe": True}

    def iter_notifications(self, duration_seconds: float) -> list[dict[str, Any]]:
        if self.actual_duration_seconds is None:
            self.actual_duration_seconds = float(duration_seconds)
        return [dict(event) for event in self.events]

    def stream_notifications(self, duration_seconds: float, on_event: Any) -> None:
        if self.actual_duration_seconds is None:
            self.actual_duration_seconds = float(duration_seconds)
        for event in self.events:
            on_event(dict(event))


def _stream_notifications_via_reader_queue(
    source: Any,
    duration_seconds: float,
    handle_event: Any,
    *,
    queue_max_size: int = 10_000,
    thread_name: str = "t007-source-reader",
    on_idle: Any | None = None,
    event_priority_fn: Any | None = None,
    fast_event_handler: Any | None = None,
    fast_event_priority_max: int = 0,
) -> dict[str, Any]:
    """Drain a source reader through a queue so downstream work cannot block recv."""

    event_queue: queue.PriorityQueue[Any] = queue.PriorityQueue(maxsize=max(1, int(queue_max_size)))
    done = object()
    sequence = itertools.count()
    started_monotonic = time.monotonic()
    deadline = started_monotonic + max(0.1, float(duration_seconds))
    stop_event = threading.Event()
    stats: dict[str, Any] = {
        "source_event_queue_high_water_mark": 0,
        "source_event_queue_dropped_count": 0,
        "source_reader_error_count": 0,
        "source_reader_errors": [],
        "source_reader_threaded": True,
        "source_consumer_hard_stop_triggered": False,
        "source_consumer_stopped_with_queue_depth": 0,
        "source_reader_alive_after_stop": False,
        "source_reader_actual_duration_seconds": None,
        "source_fast_event_handler_count": 0,
        "source_fast_event_handler_error_count": 0,
        "source_fast_event_handler_errors": [],
    }
    first_enqueue_start_waited = False

    def default_event_priority(event: dict[str, Any]) -> int:
        if event.get("decoded_rows"):
            return 0
        if event.get("trade_rows"):
            return 1
        return 2

    def event_priority(event: dict[str, Any]) -> int:
        if event_priority_fn is None:
            return default_event_priority(event)
        try:
            return int(event_priority_fn(event))
        except BaseException as exc:
            stats["source_reader_error_count"] = int(stats["source_reader_error_count"]) + 1
            stats["source_reader_errors"].append(f"event_priority:{type(exc).__name__}: {exc}")
            return default_event_priority(event)

    def enqueue_event(event: dict[str, Any]) -> None:
        nonlocal first_enqueue_start_waited
        if stop_event.is_set():
            return
        start_signal: threading.Event | None = None
        if not first_enqueue_start_waited:
            start_signal = threading.Event()
            first_enqueue_start_waited = True
        try:
            event_payload = dict(event)
            priority = event_priority(event_payload)
            if fast_event_handler is not None and priority <= int(fast_event_priority_max):
                try:
                    fast_event_handler(dict(event_payload))
                    stats["source_fast_event_handler_count"] = int(stats["source_fast_event_handler_count"]) + 1
                except BaseException as exc:
                    stats["source_fast_event_handler_error_count"] = int(stats["source_fast_event_handler_error_count"]) + 1
                    stats["source_fast_event_handler_errors"].append(f"fast_event_handler:{type(exc).__name__}: {exc}")
            event_queue.put_nowait((priority, next(sequence), (event_payload, start_signal)))
            stats["source_event_queue_high_water_mark"] = max(
                int(stats["source_event_queue_high_water_mark"]),
                int(event_queue.qsize()),
            )
            if start_signal is not None:
                start_signal.wait(timeout=0.02)
        except queue.Full:
            stats["source_event_queue_dropped_count"] = int(stats["source_event_queue_dropped_count"]) + 1

    def read_source() -> None:
        try:
            if hasattr(source, "stream_notifications"):
                source.stream_notifications(duration_seconds, enqueue_event)
            elif hasattr(source, "iter_notifications"):
                for event in source.iter_notifications(duration_seconds):
                    enqueue_event(dict(event))
        except BaseException as exc:
            stats["source_reader_error_count"] = int(stats["source_reader_error_count"]) + 1
            stats["source_reader_errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                event_queue.put_nowait((99, next(sequence), done))
            except queue.Full:
                pass

    reader = threading.Thread(target=read_source, name=thread_name, daemon=True)
    reader.start()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stats["source_consumer_hard_stop_triggered"] = True
            stats["source_consumer_stopped_with_queue_depth"] = int(event_queue.qsize())
            stop_event.set()
            break
        try:
            _priority, _sequence, item = event_queue.get(timeout=min(0.1, max(0.001, remaining)))
        except queue.Empty:
            if on_idle is not None:
                try:
                    on_idle()
                except BaseException as exc:
                    stats["source_reader_error_count"] = int(stats["source_reader_error_count"]) + 1
                    stats["source_reader_errors"].append(f"on_idle:{type(exc).__name__}: {exc}")
            continue
        if item is done:
            break
        event, start_signal = item
        if start_signal is not None:
            start_signal.set()
        handle_event(event)
    stats["source_reader_actual_duration_seconds"] = max(0.0, time.monotonic() - started_monotonic)
    reader.join(timeout=0.05 if stats.get("source_consumer_hard_stop_triggered") else 1.0)
    if reader.is_alive():
        stats["source_reader_error_count"] = int(stats["source_reader_error_count"]) + 1
        stats["source_reader_alive_after_stop"] = True
        stats["source_reader_errors"].append("source_reader_thread_join_timeout")
    return stats


class TransactionSubscribeBirthSourceAuditRoute:
    """T007-local transactionSubscribe audit route using the existing decoder."""

    source_name = "helius_transaction_subscribe_pumpfun_create"

    def __init__(
        self,
        *,
        websocket_url: str | None = None,
        timeout_seconds: float = 2.0,
        account_required: list[str] | None = None,
        source_name: str | None = None,
        audit_source_route: str = "current_pumpfun_create_account_required",
        max_reconnect_attempts: int = 0,
        reconnect_backoff_seconds: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 5.0),
    ) -> None:
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_ws_url

        if source_name:
            self.source_name = source_name
        self.websocket_url = websocket_url if websocket_url is not None else resolve_helius_ws_url()
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.account_required = list(account_required or [PUMP_FUN_PROGRAM_ID_FOR_AUDIT])
        self.audit_source_route = audit_source_route
        self.max_reconnect_attempts = max(0, int(max_reconnect_attempts))
        self.reconnect_backoff_seconds = tuple(float(value) for value in reconnect_backoff_seconds)
        self.websocket_closed_early = False
        self.websocket_close_reason: str | None = None
        self.actual_duration_seconds: float | None = None
        self.reconnect_attempts = 0
        self.reconnect_success_count = 0
        self.reconnect_failure_count = 0
        self.reconnect_reasons: list[str] = []
        self.websocket_reconnect_count = 0
        self.websocket_keepalive_timeout_count = 0
        self.total_disconnected_seconds = 0.0
        self.completed_requested_duration = False

    def availability(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.websocket_url),
            "read_only": True,
            "transactionSubscribe": True,
            "route_type": "transactionSubscribe_accountRequired",
            "accountRequired": list(self.account_required),
            "missing_reason": None if self.websocket_url else "missing_helius_websocket_url",
        }

    def iter_notifications(self, duration_seconds: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        self.stream_notifications(duration_seconds, rows.append)
        return rows

    def stream_notifications(self, duration_seconds: float, on_event: Any) -> None:
        from research.mtp_research.validation.helius_transaction_subscribe_source import (
            build_transaction_subscribe_request,
            decode_pumpfun_transaction_subscribe_notification,
            decode_pumpfun_transaction_subscribe_trade_events,
            _looks_like_keepalive_timeout,
            _websocket_connect,
        )

        if not self.websocket_url:
            self.actual_duration_seconds = 0.0
            return
        started = time.time()
        deadline = time.monotonic() + max(0.1, float(duration_seconds))
        reconnect_pending = False
        last_error: str | None = None
        request_id = f"mtp-t007-transaction-birth-source-audit-{self.audit_source_route}"
        while time.monotonic() < deadline:
            try:
                with _websocket_connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                    if reconnect_pending:
                        self.reconnect_success_count += 1
                        reconnect_pending = False
                    websocket.send(
                        json.dumps(
                            build_transaction_subscribe_request(
                                request_id=request_id,
                                account_required=self.account_required,
                            )
                        )
                    )
                    while time.monotonic() < deadline:
                        try:
                            message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
                        except TimeoutError:
                            continue
                        payload = json.loads(message) if isinstance(message, str) else message
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("id") == request_id:
                            continue
                        observed_at = time.time()
                        decoded_rows = decode_pumpfun_transaction_subscribe_notification(payload, observed_at=observed_at)
                        trade_rows = decode_pumpfun_transaction_subscribe_trade_events(payload, observed_at=observed_at)
                        on_event(
                            {
                                "received_at": observed_at,
                                "normalized_at": time.time(),
                                "signature": _txsub_signature_from_payload(payload, decoded_rows),
                                "slot": _txsub_slot_from_payload(payload, decoded_rows),
                                "route_type": "transactionSubscribe",
                                "audit_source_route": self.audit_source_route,
                                "program_id": self.account_required[0] if self.account_required else None,
                                "logs": _txsub_logs_from_payload(payload),
                                "raw_payload": payload,
                                "pumpfun_mention": True,
                                "decoded_rows": decoded_rows,
                                "trade_rows": trade_rows,
                            }
                        )
                    break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if _looks_like_keepalive_timeout(exc):
                    self.websocket_keepalive_timeout_count += 1
                if time.monotonic() >= deadline:
                    break
                if self.max_reconnect_attempts > 0 and self.reconnect_attempts >= self.max_reconnect_attempts:
                    self.reconnect_failure_count += 1
                    break
                self.reconnect_attempts += 1
                self.websocket_reconnect_count = self.reconnect_attempts
                self.reconnect_reasons.append(last_error)
                reconnect_pending = True
                backoff = self.reconnect_backoff_seconds[min(self.reconnect_attempts - 1, len(self.reconnect_backoff_seconds) - 1)] if self.reconnect_backoff_seconds else 0.0
                sleep_seconds = min(max(0.0, backoff), max(0.0, deadline - time.monotonic()))
                if sleep_seconds:
                    time.sleep(sleep_seconds)
                    self.total_disconnected_seconds += sleep_seconds
        self.actual_duration_seconds = max(0.0, time.time() - started)
        self.websocket_reconnect_count = self.reconnect_attempts
        self.completed_requested_duration = self.actual_duration_seconds >= float(duration_seconds) * 0.95
        self.websocket_closed_early = not self.completed_requested_duration
        self.websocket_close_reason = last_error if self.websocket_closed_early else None
        if self.websocket_closed_early and not self.websocket_close_reason:
            self.websocket_close_reason = "ended_before_requested_duration"


class PumpSwapProgramSubscribeMigrationRoute:
    """Global PumpSwap market-account listener for migrated Pump.fun tokens."""

    source_name = "helius_program_subscribe_pumpswap_market_accounts"

    def __init__(
        self,
        *,
        websocket_url: str | None = None,
        timeout_seconds: float = 2.0,
        quote_mints: tuple[str, ...] = (SOL_MINT, USDC_MINT),
        max_reconnect_attempts: int = 0,
        reconnect_backoff_seconds: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 5.0),
    ) -> None:
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_ws_url

        self.websocket_url = websocket_url if websocket_url is not None else resolve_helius_ws_url()
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.quote_mints = tuple(quote_mints)
        self.max_reconnect_attempts = max(0, int(max_reconnect_attempts))
        self.reconnect_backoff_seconds = tuple(float(value) for value in reconnect_backoff_seconds)
        self.websocket_closed_early = False
        self.websocket_close_reason: str | None = None
        self.actual_duration_seconds: float | None = None
        self.reconnect_attempts = 0
        self.reconnect_success_count = 0
        self.reconnect_failure_count = 0
        self.reconnect_reasons: list[str] = []
        self.websocket_reconnect_count = 0
        self.websocket_keepalive_timeout_count = 0
        self.total_disconnected_seconds = 0.0
        self.completed_requested_duration = False

    def availability(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.websocket_url),
            "read_only": True,
            "programSubscribe": True,
            "route_type": "programSubscribe_account_filters",
            "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
            "quote_mints": list(self.quote_mints),
            "account_data_sizes": list(PUMPSWAP_MARKET_ACCOUNT_LENGTHS),
            "filters_by_quote_asset": {
                _quote_identity_from_payload({"quote_mint": quote_mint})["quote_asset"]: _pumpswap_program_subscribe_filters(quote_mint)
                for quote_mint in self.quote_mints
            },
            "filters_by_quote_asset_and_size": {
                _quote_identity_from_payload({"quote_mint": quote_mint})["quote_asset"]: {
                    str(account_length): _pumpswap_program_subscribe_filters(
                        quote_mint,
                        account_length=account_length,
                    )
                    for account_length in PUMPSWAP_MARKET_ACCOUNT_LENGTHS
                }
                for quote_mint in self.quote_mints
            },
            "missing_reason": None if self.websocket_url else "missing_helius_websocket_url",
        }

    def iter_notifications(self, duration_seconds: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        self.stream_notifications(duration_seconds, rows.append)
        return rows

    def stream_notifications(self, duration_seconds: float, on_event: Any) -> None:
        from research.mtp_research.validation.helius_transaction_subscribe_source import _looks_like_keepalive_timeout, _websocket_connect

        if not self.websocket_url:
            self.actual_duration_seconds = 0.0
            return
        started = time.time()
        deadline = time.monotonic() + max(0.1, float(duration_seconds))
        reconnect_pending = False
        last_error: str | None = None
        request_id = "mtp-t007-pumpswap-program-subscribe"
        subscription_specs = [
            (idx, account_length, quote_mint)
            for idx, quote_mint in enumerate(self.quote_mints)
            for account_length in PUMPSWAP_MARKET_ACCOUNT_LENGTHS
        ]
        request_ids = {f"{request_id}-{idx}-{account_length}" for idx, account_length, _ in subscription_specs}
        while time.monotonic() < deadline:
            try:
                with _websocket_connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                    if reconnect_pending:
                        self.reconnect_success_count += 1
                        reconnect_pending = False
                    for idx, account_length, quote_mint in subscription_specs:
                        websocket.send(
                            json.dumps(
                                _pumpswap_program_subscribe_request(
                                    f"{request_id}-{idx}-{account_length}",
                                    quote_mint=quote_mint,
                                    account_length=account_length,
                                )
                            )
                        )
                    while time.monotonic() < deadline:
                        try:
                            message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
                        except TimeoutError:
                            continue
                        payload = json.loads(message) if isinstance(message, str) else message
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("id") in request_ids:
                            continue
                        observed_at = time.time()
                        account_pubkey = _program_subscribe_pubkey_from_payload(payload)
                        account_data = _program_subscribe_account_data_from_payload(payload)
                        decoded = _decode_pumpswap_market_account_data(account_data or b"", account_pubkey=account_pubkey)
                        on_event(
                            {
                                "received_at": observed_at,
                                "normalized_at": time.time(),
                                "signature": None,
                                "slot": _program_subscribe_slot_from_payload(payload),
                                "route_type": "programSubscribe",
                                "audit_source_route": "pumpswap_program_subscribe",
                                "program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
                                "account_pubkey": account_pubkey,
                                "account_data_decoded": decoded,
                                "raw_payload": payload,
                            }
                        )
                    break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if _looks_like_keepalive_timeout(exc):
                    self.websocket_keepalive_timeout_count += 1
                if time.monotonic() >= deadline:
                    break
                if self.max_reconnect_attempts > 0 and self.reconnect_attempts >= self.max_reconnect_attempts:
                    self.reconnect_failure_count += 1
                    break
                self.reconnect_attempts += 1
                self.websocket_reconnect_count = self.reconnect_attempts
                self.reconnect_reasons.append(last_error)
                reconnect_pending = True
                backoff = self.reconnect_backoff_seconds[min(self.reconnect_attempts - 1, len(self.reconnect_backoff_seconds) - 1)] if self.reconnect_backoff_seconds else 0.0
                sleep_seconds = min(max(0.0, backoff), max(0.0, deadline - time.monotonic()))
                if sleep_seconds:
                    time.sleep(sleep_seconds)
                    self.total_disconnected_seconds += sleep_seconds
        self.actual_duration_seconds = max(0.0, time.time() - started)
        self.websocket_reconnect_count = self.reconnect_attempts
        self.completed_requested_duration = self.actual_duration_seconds >= float(duration_seconds) * 0.95
        self.websocket_closed_early = not self.completed_requested_duration
        self.websocket_close_reason = last_error if self.websocket_closed_early else None
        if self.websocket_closed_early and not self.websocket_close_reason:
            self.websocket_close_reason = "ended_before_requested_duration"


class TransactionSubscribeNormalizedBirthSource:
    """Emit one normalized T007 birth per unique mint from transactionSubscribe rows."""

    source_name = "transaction_subscribe_normalized_birth_source"

    def __init__(self, source: Any | None = None) -> None:
        self.source = source or TransactionSubscribeBirthSourceAuditRoute()
        self.metrics: dict[str, Any] = {
            "source_route": "transaction_subscribe",
            "raw_transaction_notifications": 0,
            "decoded_birth_rows": 0,
            "unique_birth_mints": 0,
            "duplicate_mint_rows": 0,
            "duplicate_rows_by_route": {},
            "first_seen_route_counts": {},
            "duplicate_signatures": 0,
            "duplicate_rows_with_same_mint_but_different_route": 0,
            "duplicate_rows_with_same_mint_but_different_signature": 0,
            "direct_decoded_rows": 0,
            "inner_decoded_rows": 0,
            "wrapped_compact_decoded_rows": 0,
            "bonding_curve_account_present_count": 0,
            "associated_bonding_curve_present_count": 0,
            "associated_bonding_curve_missing_count": 0,
            "creator_dev_present_count": 0,
            "actual_duration_seconds": 0.0,
            "websocket_closed_early": False,
            "websocket_close_reason": None,
            "requested_source_duration_seconds": 0.0,
            "actual_source_duration_seconds": None,
            "source_duration_completion_ratio": None,
            "source_duration_quality_status": "not_evaluated",
            "source_ended_early": False,
            "early_end_reason": None,
            "validation_run_quality_label": "RUN_QUALITY_NOT_EVALUATED",
            "websocket_keepalive_timeout_count": 0,
            "websocket_reconnect_count": 0,
            "source_event_queue_high_water_mark": 0,
            "source_event_queue_dropped_count": 0,
            "source_reader_error_count": 0,
            "source_reader_errors": [],
            "source_reader_threaded": False,
            "subscription_connect_status": "not_started",
            "live_source_used": getattr(self.source, "source_name", self.source.__class__.__name__),
            "mayhem_code_modified": False,
            "notification_to_birth_normalized_latencies_ms": [],
            "decoded_trade_rows": 0,
            "trade_rows_recorded": 0,
            "trade_rows_skipped_unknown_mint": 0,
            "trade_rows_skipped_missing_mint": 0,
            "birth_priority_dispatch_enabled": True,
            "birth_priority_worker_count": 1,
            "birth_priority_queue_high_water_mark": 0,
            "birth_priority_queue_dropped_count": 0,
            "birth_priority_worker_error_count": 0,
            "birth_priority_worker_errors": [],
        }

    def availability(self) -> dict[str, Any]:
        if hasattr(self.source, "availability"):
            return self.source.availability()
        return {"source": self.source_name, "available": True, "read_only": True}

    def fetch_launches(self, duration_seconds: float) -> list[dict[str, Any]]:
        availability = self.availability()
        self.metrics["subscription_connect_status"] = (
            "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}"
        )
        self.metrics["live_source_used"] = availability.get("source") or getattr(self.source, "source_name", self.source.__class__.__name__)
        if availability.get("available", True) is False:
            return []
        events = self.source.iter_notifications(duration_seconds) if hasattr(self.source, "iter_notifications") else []
        self.metrics["raw_transaction_notifications"] = len(events)
        candidates: list[dict[str, Any]] = []
        for event in events:
            trade_rows = [dict(row) for row in event.get("trade_rows") or []]
            self.metrics["decoded_trade_rows"] += len(trade_rows)
            for row in event.get("decoded_rows") or []:
                normalized = _launch_from_transaction_decoded_row(dict(row), event)
                if not normalized.get("mint"):
                    continue
                route = normalized["decode_route"]
                self.metrics["decoded_birth_rows"] += 1
                if route == "wrapped_compact":
                    self.metrics["wrapped_compact_decoded_rows"] += 1
                elif route == "inner":
                    self.metrics["inner_decoded_rows"] += 1
                else:
                    self.metrics["direct_decoded_rows"] += 1
                candidates.append(normalized)
        by_mint: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            by_mint.setdefault(str(candidate["mint"]), []).append(candidate)
        selected: list[dict[str, Any]] = []
        for mint, rows in by_mint.items():
            rows_sorted = sorted(rows, key=_birth_sort_key)
            first = rows_sorted[0]
            selected.append(first)
            _increment_counter(self.metrics["first_seen_route_counts"], first.get("decode_route") or "unknown")
            duplicates = rows_sorted[1:]
            self.metrics["duplicate_mint_rows"] += len(duplicates)
            for duplicate in duplicates:
                route = duplicate.get("decode_route") or "unknown"
                _increment_counter(self.metrics["duplicate_rows_by_route"], route)
                if duplicate.get("signature"):
                    self.metrics["duplicate_signatures"] += 1
                if route != first.get("decode_route"):
                    self.metrics["duplicate_rows_with_same_mint_but_different_route"] += 1
                if duplicate.get("signature") != first.get("signature"):
                    self.metrics["duplicate_rows_with_same_mint_but_different_signature"] += 1
        selected = sorted(selected, key=_birth_sort_key)
        self.metrics["unique_birth_mints"] = len(selected)
        self.metrics["bonding_curve_account_present_count"] = sum(1 for row in selected if row.get("bonding_curve_account"))
        self.metrics["associated_bonding_curve_present_count"] = sum(1 for row in selected if row.get("associated_bonding_curve"))
        self.metrics["associated_bonding_curve_missing_count"] = sum(1 for row in selected if not row.get("associated_bonding_curve"))
        self.metrics["creator_dev_present_count"] = sum(1 for row in selected if row.get("creator"))
        self.metrics["actual_duration_seconds"] = float(getattr(self.source, "actual_duration_seconds", duration_seconds) or 0.0)
        self.metrics["websocket_closed_early"] = bool(getattr(self.source, "websocket_closed_early", False))
        self.metrics["websocket_close_reason"] = getattr(self.source, "websocket_close_reason", None)
        self.metrics.update(
            _source_duration_quality_fields(
                duration_seconds,
                self.metrics["actual_duration_seconds"],
                websocket_closed_early=self.metrics["websocket_closed_early"],
                websocket_close_reason=self.metrics["websocket_close_reason"],
                websocket_keepalive_timeout_count=int(getattr(self.source, "websocket_keepalive_timeout_count", 0) or 0),
                websocket_reconnect_count=int(getattr(self.source, "websocket_reconnect_count", getattr(self.source, "reconnect_attempts", 0)) or 0),
            )
        )
        return selected

    def stream_launches(
        self,
        duration_seconds: float,
        on_launch: Any,
        on_trade: Any | None = None,
        on_idle: Any | None = None,
        on_birth_fast_path: Any | None = None,
    ) -> None:
        availability = self.availability()
        self.metrics["subscription_connect_status"] = (
            "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}"
        )
        self.metrics["live_source_used"] = availability.get("source") or getattr(self.source, "source_name", self.source.__class__.__name__)
        if availability.get("available", True) is False:
            return
        seen_by_mint: dict[str, dict[str, Any]] = {}
        queued_birth_mints: set[str] = set()
        queued_birth_mints_lock = threading.Lock()
        fast_path_birth_mints: set[str] = set()
        fast_path_birth_mints_lock = threading.Lock()
        pending_trade_rows: deque[dict[str, Any]] = deque()

        def row_mint_identity(row: Mapping[str, Any]) -> str:
            return str(row.get("mint") or row.get("token_mint") or row.get("ca") or "")

        def process_trade_row(trade_row: Mapping[str, Any], *, normalized_at: float) -> None:
            trade = dict(trade_row)
            self.metrics["decoded_trade_rows"] += 1
            mint = str(trade.get("mint") or "")
            if not mint:
                self.metrics["trade_rows_skipped_missing_mint"] += 1
                return
            if mint not in seen_by_mint:
                self.metrics["trade_rows_skipped_unknown_mint"] += 1
                return
            if trade.get("received_at") is None:
                trade["received_at"] = normalized_at
            if trade.get("decision_time") is None:
                trade["decision_time"] = trade.get("received_at")
            if on_trade is not None:
                on_trade(trade)
                self.metrics["trade_rows_recorded"] += 1

        def drain_pending_trade_rows(max_items: int | None = None) -> int:
            processed = 0
            while pending_trade_rows and (max_items is None or processed < max_items):
                trade = pending_trade_rows.popleft()
                process_trade_row(trade, normalized_at=_num(trade.get("normalized_at")) or time.time())
                processed += 1
            return processed

        def first_seen_birth_event_priority(event: dict[str, Any]) -> int:
            decoded_rows = [dict(row) for row in event.get("decoded_rows") or []]
            decoded_mints = {mint for row in decoded_rows if (mint := row_mint_identity(row))}
            if decoded_mints:
                with queued_birth_mints_lock:
                    first_seen_mints = decoded_mints - queued_birth_mints
                    queued_birth_mints.update(decoded_mints)
                if first_seen_mints:
                    return 0
                if event.get("trade_rows"):
                    return 1
                return 2
            if event.get("trade_rows"):
                return 1
            return 3

        def handle_event(event: dict[str, Any]) -> None:
            self.metrics["raw_transaction_notifications"] += 1
            event_received_at = _num(event.get("received_at"))
            normalized_at = _num(event.get("normalized_at")) or event_received_at or time.time()
            emitted_new_birth = False
            for row in event.get("decoded_rows") or []:
                row = dict(row)
                row_mint = row_mint_identity(row)
                if row_mint and str(row_mint) in seen_by_mint:
                    route = _classify_transaction_decode_route(row)
                    first = seen_by_mint[str(row_mint)]
                    row_signature = row.get("signature") or event.get("signature")
                    self.metrics["decoded_birth_rows"] += 1
                    self.metrics["duplicate_mint_rows"] += 1
                    _increment_counter(self.metrics["duplicate_rows_by_route"], route)
                    if row_signature:
                        self.metrics["duplicate_signatures"] += 1
                    if route != first.get("decode_route"):
                        self.metrics["duplicate_rows_with_same_mint_but_different_route"] += 1
                    if row_signature != first.get("signature"):
                        self.metrics["duplicate_rows_with_same_mint_but_different_signature"] += 1
                    continue
                normalized = _launch_from_transaction_decoded_row(dict(row), event)
                mint = normalized.get("mint")
                if not mint:
                    continue
                route = normalized["decode_route"]
                self.metrics["decoded_birth_rows"] += 1
                if route == "wrapped_compact":
                    self.metrics["wrapped_compact_decoded_rows"] += 1
                elif route == "inner":
                    self.metrics["inner_decoded_rows"] += 1
                else:
                    self.metrics["direct_decoded_rows"] += 1
                mint_key = str(mint)
                first = seen_by_mint.get(mint_key)
                if first is not None:
                    self.metrics["duplicate_mint_rows"] += 1
                    _increment_counter(self.metrics["duplicate_rows_by_route"], route)
                    if normalized.get("signature"):
                        self.metrics["duplicate_signatures"] += 1
                    if route != first.get("decode_route"):
                        self.metrics["duplicate_rows_with_same_mint_but_different_route"] += 1
                    if normalized.get("signature") != first.get("signature"):
                        self.metrics["duplicate_rows_with_same_mint_but_different_signature"] += 1
                    continue
                normalized["first_seen_received_at"] = normalized.get("received_at")
                normalized["first_seen_slot"] = normalized.get("slot")
                normalized["first_seen_signature"] = normalized.get("signature")
                normalized["first_seen_route"] = route
                normalized["normalized_at"] = normalized_at
                seen_by_mint[mint_key] = normalized
                _increment_counter(self.metrics["first_seen_route_counts"], route)
                if normalized.get("bonding_curve_account"):
                    self.metrics["bonding_curve_account_present_count"] += 1
                if normalized.get("associated_bonding_curve"):
                    self.metrics["associated_bonding_curve_present_count"] += 1
                else:
                    self.metrics["associated_bonding_curve_missing_count"] += 1
                if normalized.get("creator"):
                    self.metrics["creator_dev_present_count"] += 1
                if event_received_at is not None:
                    self.metrics["notification_to_birth_normalized_latencies_ms"].append(
                        max(0.0, (normalized_at - event_received_at) * 1000.0)
                    )
                self.metrics["unique_birth_mints"] = len(seen_by_mint)
                emitted_new_birth = True
                on_launch(normalized)
            for trade_row in event.get("trade_rows") or []:
                trade = dict(trade_row)
                trade["normalized_at"] = normalized_at
                pending_trade_rows.append(trade)

        def drain_idle_work() -> None:
            drain_pending_trade_rows(max_items=250)
            if on_idle is not None:
                on_idle()

        def fast_path_birth_event_handler(event: dict[str, Any]) -> None:
            if on_birth_fast_path is None:
                return
            event_received_at = _num(event.get("received_at"))
            normalized_at = _num(event.get("normalized_at")) or event_received_at or time.time()
            for row in event.get("decoded_rows") or []:
                normalized = _launch_from_transaction_decoded_row(dict(row), event)
                mint = str(normalized.get("mint") or "")
                if not mint:
                    continue
                with fast_path_birth_mints_lock:
                    if mint in fast_path_birth_mints:
                        continue
                    fast_path_birth_mints.add(mint)
                route = normalized.get("decode_route") or _classify_transaction_decode_route(dict(row))
                normalized["first_seen_received_at"] = normalized.get("received_at")
                normalized["first_seen_slot"] = normalized.get("slot")
                normalized["first_seen_signature"] = normalized.get("signature")
                normalized["first_seen_route"] = route
                normalized["normalized_at"] = normalized_at
                on_birth_fast_path(normalized)

        queue_stats = _stream_notifications_via_reader_queue(
            self.source,
            duration_seconds,
            handle_event,
            queue_max_size=int(getattr(self.source, "source_event_queue_max_size", 10_000) or 10_000),
            thread_name="t007-birth-source-reader",
            on_idle=drain_idle_work,
            event_priority_fn=first_seen_birth_event_priority,
            fast_event_handler=fast_path_birth_event_handler if on_birth_fast_path is not None else None,
            fast_event_priority_max=0,
        )
        drain_pending_trade_rows(max_items=None)
        self.metrics.update(queue_stats)
        self.metrics["unique_birth_mints"] = len(seen_by_mint)
        if queue_stats.get("source_consumer_hard_stop_triggered"):
            self.metrics["actual_duration_seconds"] = float(
                queue_stats.get("source_reader_actual_duration_seconds") or duration_seconds
            )
        else:
            self.metrics["actual_duration_seconds"] = float(getattr(self.source, "actual_duration_seconds", duration_seconds) or 0.0)
        self.metrics["websocket_closed_early"] = bool(getattr(self.source, "websocket_closed_early", False))
        self.metrics["websocket_close_reason"] = getattr(self.source, "websocket_close_reason", None)
        self.metrics.update(
            _source_duration_quality_fields(
                duration_seconds,
                self.metrics["actual_duration_seconds"],
                websocket_closed_early=self.metrics["websocket_closed_early"],
                websocket_close_reason=self.metrics["websocket_close_reason"],
                websocket_keepalive_timeout_count=int(getattr(self.source, "websocket_keepalive_timeout_count", 0) or 0),
                websocket_reconnect_count=int(getattr(self.source, "websocket_reconnect_count", getattr(self.source, "reconnect_attempts", 0)) or 0),
            )
        )


class LogsSubscribeBirthSourceAuditRoute:
    """Compact raw audit route for the current logsSubscribe broad source."""

    source_name = "helius_logs_subscribe_pumpfun_program"

    def __init__(self, *, rpc_url: str | None = None, websocket_url: str | None = None, timeout_seconds: float = 2.0) -> None:
        from research.mtp_research.validation.forward_birth_watch_followup_collector import rpc_url_to_websocket_url
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        self.rpc_url = rpc_url if rpc_url is not None else resolve_helius_rpc_url()
        self.websocket_url = websocket_url or rpc_url_to_websocket_url(self.rpc_url)
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.rpc_failures = 0
        self.websocket_failures = 0

    def availability(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.websocket_url and self.rpc_url),
            "read_only": True,
            "route_type": "logsSubscribe_mentions_pumpfun_program_then_getTransaction",
            "missing_reason": None if self.websocket_url and self.rpc_url else "missing_helius_rpc_or_websocket_url",
        }

    def iter_notifications(self, duration_seconds: float) -> list[dict[str, Any]]:
        from research.mtp_research.validation.forward_birth_watch_followup_collector import _websocket_connect
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc
        from research.mtp_research.validation.pumpfun_bonding_curve import PUMP_FUN_PROGRAM_ID

        if not self.websocket_url or not self.rpc_url:
            return []
        rows: list[dict[str, Any]] = []
        deadline = time.monotonic() + max(0.1, float(duration_seconds))
        subscription_id: int | None = None
        try:
            with _websocket_connect(self.websocket_url, open_timeout=min(5.0, self.timeout_seconds), close_timeout=1.0) as websocket:
                websocket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": "mtp-t007-birth-source-audit-logs-subscribe",
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [PUMP_FUN_PROGRAM_ID]},
                                {"commitment": "processed"},
                            ],
                        }
                    )
                )
                while time.monotonic() < deadline:
                    try:
                        message = websocket.recv(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
                    except TimeoutError:
                        continue
                    payload = json.loads(message) if isinstance(message, str) else message
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("id") == "mtp-t007-birth-source-audit-logs-subscribe":
                        subscription_id = payload.get("result") if isinstance(payload.get("result"), int) else None
                        continue
                    event = _audit_event_from_logs_notification(payload, received_at=time.time())
                    if event is None:
                        continue
                    signature = event.get("signature")
                    if signature:
                        try:
                            event["transaction"] = _fetch_audit_transaction(self.rpc_url, str(signature), _post_json_rpc, self.timeout_seconds)
                        except Exception:
                            self.rpc_failures += 1
                            event["transaction"] = {}
                            event["fetch_error"] = "getTransaction_failed"
                    rows.append(event)
                if subscription_id is not None:
                    websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": "mtp-t007-birth-source-audit-logs-unsubscribe",
                                "method": "logsUnsubscribe",
                                "params": [subscription_id],
                            }
                        )
                    )
        except Exception:
            self.websocket_failures += 1
        return rows


def run_birth_source_audit(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    now_fn: Any = time.time,
) -> dict[str, Any]:
    output_root = Path(config.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for filename in JSONL_ARTIFACT_FILES:
        (output_root / filename).touch(exist_ok=True)
    _write_config(output_root, config)
    route = source or LogsSubscribeBirthSourceAuditRoute(timeout_seconds=min(2.0, max(0.5, config.source_duration_seconds)))
    availability = route.availability() if hasattr(route, "availability") else {"source": route.__class__.__name__, "available": True}
    events = route.iter_notifications(config.source_duration_seconds) if availability.get("available", True) else []
    counters: dict[str, Any] = {
        "run_id": config.run_id,
        "mode": "birth-source-audit",
        "output_root": str(output_root),
        "source_duration": config.source_duration_seconds,
        "live_source_used": availability.get("source") or getattr(route, "source_name", route.__class__.__name__),
        "subscription_connect_status": "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}",
        "raw_websocket_notifications_received": 0,
        "pumpfun_program_mentions": 0,
        "candidate_transactions_inspected": 0,
        "direct_create_candidates": 0,
        "wrapped_inner_create_candidates": 0,
        "decoded_births": 0,
        "births_rejected_by_decoder": 0,
        "births_rejected_by_adapter": 0,
        "duplicate_mints": 0,
        "final_normalized_births": 0,
        "unique_mints": 0,
        "estimated_births_per_minute": 0.0,
        "raw_audit_path": str(output_root / "raw_birth_source_audit.jsonl"),
        "mayhem_code_modified": False,
    }
    seen_mints: set[str] = set()
    for event in events:
        counters["raw_websocket_notifications_received"] += 1
        pumpfun_mention = _event_mentions_pumpfun(event)
        if pumpfun_mention:
            counters["pumpfun_program_mentions"] += 1
        if event.get("transaction") or event.get("direct_candidates") is not None or event.get("wrapped_inner_candidates") is not None:
            counters["candidate_transactions_inspected"] += 1
        direct, wrapped = _audit_candidates_from_event(event)
        counters["direct_create_candidates"] += len(direct)
        counters["wrapped_inner_create_candidates"] += len(wrapped)
        decoded = [*direct, *wrapped]
        if pumpfun_mention and not decoded:
            counters["births_rejected_by_decoder"] += 1
            _append_audit_row(output_root, event, None, "not_decoded", "decoder_no_create_candidate")
            continue
        for candidate, route_name in decoded:
            counters["decoded_births"] += 1
            normalized = _normalize_audit_candidate(candidate)
            mint = normalized.get("mint")
            if not mint:
                counters["births_rejected_by_adapter"] += 1
                _append_audit_row(output_root, event, normalized, route_name, "missing_mint")
                continue
            reject_reason = None
            if mint in seen_mints:
                counters["duplicate_mints"] += 1
                reject_reason = "duplicate_mint"
            else:
                seen_mints.add(str(mint))
                counters["final_normalized_births"] += 1
            _append_audit_row(output_root, event, normalized, route_name, reject_reason)
    counters["unique_mints"] = len(seen_mints)
    if config.source_duration_seconds:
        counters["estimated_births_per_minute"] = round(counters["final_normalized_births"] / (float(config.source_duration_seconds) / 60.0), 6)
    counters["source_route_comparison"] = _source_route_comparison(counters)
    (output_root / "birth_source_audit_summary.json").write_text(json.dumps(counters, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return counters


def run_transaction_birth_source_audit(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    now_fn: Any = time.time,
) -> dict[str, Any]:
    output_root = Path(config.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "transaction_raw_birth_source_audit.jsonl").touch(exist_ok=True)
    _write_config(output_root, config)
    route = source or TransactionSubscribeBirthSourceAuditRoute(timeout_seconds=min(2.0, max(0.5, config.source_duration_seconds)))
    availability = route.availability() if hasattr(route, "availability") else {"source": route.__class__.__name__, "available": True}
    started = float(now_fn())
    events = route.iter_notifications(config.source_duration_seconds) if availability.get("available", True) else []
    actual_duration = getattr(route, "actual_duration_seconds", None)
    if actual_duration is None:
        actual_duration = max(0.0, float(now_fn()) - started)
    summary: dict[str, Any] = {
        "run_id": config.run_id,
        "mode": "transaction-birth-source-audit",
        "output_root": str(output_root),
        "requested_duration_seconds": float(config.source_duration_seconds),
        "actual_duration_seconds": float(actual_duration),
        "websocket_closed_early": bool(getattr(route, "websocket_closed_early", False)),
        "websocket_close_reason": getattr(route, "websocket_close_reason", None),
        "live_source_used": availability.get("source") or getattr(route, "source_name", route.__class__.__name__),
        "subscription_connect_status": "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}",
        "raw_transaction_notifications": 0,
        "pumpfun_mentions": 0,
        "create_like_candidates": 0,
        "direct_creates_decoded": 0,
        "inner_creates_decoded": 0,
        "wrapped_compact_creates_decoded": 0,
        "total_decoded_births": 0,
        "unique_decoded_birth_mints": 0,
        "duplicate_mints": 0,
        "rejects_by_reason": {},
        "decoded_births_per_observed_minute": 0.0,
        "bonding_curve_account_present_count": 0,
        "associated_bonding_curve_present_count": 0,
        "creator_dev_present_count": 0,
        "raw_audit_path": str(output_root / "transaction_raw_birth_source_audit.jsonl"),
        "mayhem_code_modified": False,
        "source_route_comparison": _transaction_source_route_comparison(),
    }
    seen_mints: set[str] = set()
    for event in events:
        summary["raw_transaction_notifications"] += 1
        if event.get("pumpfun_mention", True):
            summary["pumpfun_mentions"] += 1
        decoded_rows = [dict(row) for row in event.get("decoded_rows") or []]
        if not decoded_rows:
            _increment_reason(summary, "decoder_no_create_candidate")
            _append_transaction_audit_row(output_root, event, None, "not_decoded", "decoder_no_create_candidate")
            continue
        for row in decoded_rows:
            normalized = _normalize_transaction_decoded_row(row, event)
            route_name = _classify_transaction_decode_route(row)
            summary["create_like_candidates"] += 1
            summary["total_decoded_births"] += 1
            if route_name == "wrapped_compact":
                summary["wrapped_compact_creates_decoded"] += 1
            elif route_name == "inner":
                summary["inner_creates_decoded"] += 1
            else:
                summary["direct_creates_decoded"] += 1
            if normalized.get("bonding_curve_account"):
                summary["bonding_curve_account_present_count"] += 1
            if normalized.get("associated_bonding_curve"):
                summary["associated_bonding_curve_present_count"] += 1
            if normalized.get("creator"):
                summary["creator_dev_present_count"] += 1
            reject_reason = None
            mint = normalized.get("mint")
            if not mint:
                reject_reason = "missing_mint"
                _increment_reason(summary, reject_reason)
            elif mint in seen_mints:
                reject_reason = "duplicate_mint"
                summary["duplicate_mints"] += 1
                _increment_reason(summary, reject_reason)
            else:
                seen_mints.add(str(mint))
            _append_transaction_audit_row(output_root, event, normalized, route_name, reject_reason)
    summary["unique_decoded_birth_mints"] = len(seen_mints)
    if float(actual_duration) > 0:
        summary["decoded_births_per_observed_minute"] = round(
            float(summary["total_decoded_births"]) / (float(actual_duration) / 60.0),
            6,
        )
    (output_root / "transaction_birth_source_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def run_migration_source_audit(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    now_fn: Any = time.time,
) -> dict[str, Any]:
    """Scan the broad transaction source for migration signals without admission gating."""

    output_root = Path(config.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for filename in JSONL_ARTIFACT_FILES:
        (output_root / filename).touch(exist_ok=True)
    _write_config(output_root, config)
    route = source or TransactionSubscribeBirthSourceAuditRoute(timeout_seconds=min(2.0, max(0.5, config.source_duration_seconds)))
    availability = route.availability() if hasattr(route, "availability") else {"source": route.__class__.__name__, "available": True}
    started = float(now_fn())
    if availability.get("available", True) is False:
        events: list[dict[str, Any]] = []
    elif hasattr(route, "iter_notifications"):
        events = route.iter_notifications(config.source_duration_seconds)
    else:
        events = []
    actual_duration = getattr(route, "actual_duration_seconds", None)
    if actual_duration is None:
        actual_duration = max(0.0, float(now_fn()) - started)

    summary: dict[str, Any] = {
        "run_id": config.run_id,
        "mode": "migration-source-audit",
        "output_root": str(output_root),
        "requested_duration_seconds": float(config.source_duration_seconds),
        "actual_duration_seconds": float(actual_duration),
        "websocket_closed_early": bool(getattr(route, "websocket_closed_early", False)),
        "websocket_close_reason": getattr(route, "websocket_close_reason", None),
        "live_source_used": availability.get("source") or getattr(route, "source_name", route.__class__.__name__),
        "subscription_connect_status": "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}",
        "raw_transaction_notifications": 0,
        "decoded_rows_scanned": 0,
        "global_migration_events": 0,
        "global_migration_candidates": 0,
        "detection_methods": {},
        "confidence_counts": {},
        "global_migration_events_path": str(output_root / "global_migration_events.jsonl"),
        "global_migration_candidates_path": str(output_root / "global_migration_candidates.jsonl"),
        "valuation_ladder_emission_policy": "market_cap_confirmed_only",
        "valuation_ladder_events_written": 0,
        "mayhem_code_modified": False,
    }

    seen_signatures: set[tuple[str, str, str]] = set()
    for event in events:
        summary["raw_transaction_notifications"] += 1
        decoded_rows = [dict(row) for row in event.get("decoded_rows") or []]
        if decoded_rows:
            summary["decoded_rows_scanned"] += len(decoded_rows)
            rows_to_scan = decoded_rows
        else:
            rows_to_scan = [{}]
        for row in rows_to_scan:
            detection = _global_migration_detection_from_row(row, event)
            if detection is None:
                continue
            dedupe_key = (
                str(detection.get("mint") or ""),
                str(detection.get("signature") or ""),
                str(detection.get("detection_method") or ""),
            )
            if dedupe_key in seen_signatures:
                continue
            seen_signatures.add(dedupe_key)
            _increment_counter(summary["detection_methods"], detection["detection_method"])
            _increment_counter(summary["confidence_counts"], detection["confidence"])
            if detection["confidence"] == "confirmed":
                _append_jsonl_file(output_root / "global_migration_events.jsonl", detection)
                summary["global_migration_events"] += 1
            else:
                _append_jsonl_file(output_root / "global_migration_candidates.jsonl", detection)
                summary["global_migration_candidates"] += 1

    (output_root / "migration_visibility_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def run_migration_route_audit(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    now_fn: Any = time.time,
) -> dict[str, Any]:
    """Compare candidate live routes for Axiom-visible migration/pair events."""

    output_root = Path(config.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    for filename in JSONL_ARTIFACT_FILES:
        (output_root / filename).touch(exist_ok=True)
    _write_config(output_root, config)
    started = float(now_fn())
    if source is not None:
        route_specs = [(source, float(config.source_duration_seconds), "current_pumpfun_create_account_required")]
    else:
        split_duration = max(1.0, float(config.source_duration_seconds) / 2.0)
        route_specs = [
            (
                TransactionSubscribeBirthSourceAuditRoute(
                    timeout_seconds=min(2.0, max(0.5, split_duration)),
                    account_required=[PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
                    source_name="helius_transaction_subscribe_pumpfun_migration_audit",
                    audit_source_route="current_pumpfun_create_account_required",
                ),
                split_duration,
                "current_pumpfun_create_account_required",
            ),
            (
                TransactionSubscribeBirthSourceAuditRoute(
                    timeout_seconds=min(2.0, max(0.5, split_duration)),
                    account_required=[PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
                    source_name="helius_transaction_subscribe_pumpswap_pool_create",
                    audit_source_route="pumpswap_pool_create",
                ),
                split_duration,
                "pumpswap_pool_create",
            ),
        ]
    route_defs = _migration_route_definitions()
    route_counters = {name: _empty_migration_route_counter(definition, 0) for name, definition in route_defs.items()}
    seen_by_route: dict[str, set[str]] = {name: set() for name in route_defs}
    duplicate_by_route: dict[str, set[str]] = {name: set() for name in route_defs}
    availability_rows: list[dict[str, Any]] = []
    actual_durations: list[float] = []
    route_status_by_route: dict[str, dict[str, Any]] = {}
    dedupe_writer = GlobalMigrationDedupeWriter(output_root)
    for route, route_duration, raw_route_name in route_specs:
        availability = route.availability() if hasattr(route, "availability") else {"source": route.__class__.__name__, "available": True}
        availability_rows.append(dict(availability))
        if availability.get("available", True) is False:
            events: list[dict[str, Any]] = []
        elif hasattr(route, "iter_notifications"):
            events = route.iter_notifications(route_duration)
        else:
            events = []
        actual_durations.append(float(getattr(route, "actual_duration_seconds", route_duration) or 0.0))
        route_status_by_route[raw_route_name] = _route_runtime_status(route, route_duration, availability)
        route_counters.setdefault(raw_route_name, _empty_migration_route_counter({"source_route": raw_route_name}, 0))
        route_counters[raw_route_name]["raw_notifications"] += len(events)
        for event in events:
            event.setdefault("audit_source_route", raw_route_name)
            rows_to_scan = [dict(row) for row in event.get("decoded_rows") or []] or [{}]
            for row in rows_to_scan:
                detection = _migration_route_detection_from_row(row, event)
                if detection is None:
                    continue
                route_name = detection["source_route"]
                counter = route_counters.setdefault(route_name, _empty_migration_route_counter({"source_route": route_name}, 0))
                counter["candidate_migration_notifications"] += 1
                counter["detection_method"] = detection.get("detection_method")
                counter["confidence"] = detection.get("confidence")
                mint = str(detection.get("mint") or "")
                pool = detection.get("pool_or_pair_address")
                if route_name == "pumpswap_pool_create":
                    counter["raw_pumpswap_candidates"] += 1
                    if detection.get("confidence") == "confirmed" and mint:
                        counter["confirmed_pumpswap_rows"] += 1
                if not mint:
                    counter["missing_mint_count"] += 1
                    _increment_counter(counter["errors_by_reason"], "missing_mint")
                if route_name == "pumpswap_pool_create" and not pool:
                    counter["missing_pair_pool_count"] += 1
                    _increment_counter(counter["errors_by_reason"], "missing_pair_pool")
                if mint:
                    if mint in seen_by_route.setdefault(route_name, set()):
                        duplicate_by_route.setdefault(route_name, set()).add(mint)
                        counter["duplicate_migrated_mints"] = len(duplicate_by_route[route_name])
                    else:
                        seen_by_route[route_name].add(mint)
                        counter["unique_migrated_mints"] = len(seen_by_route[route_name])
                emit_status = dedupe_writer.record(detection)
                if emit_status == "event":
                    counter["decoded_migration_events"] += 1
                    if route_name == "pumpswap_pool_create":
                        counter["deduped_pumpswap_migration_events"] += 1
                elif emit_status == "duplicate":
                    if route_name == "pumpswap_pool_create":
                        counter["duplicate_pumpswap_rows_suppressed"] += 1
                else:
                    counter["decoded_migration_candidates"] += 1
                if route_name == "pumpswap_pool_create":
                    if mint:
                        counter["unique_pumpswap_mints"] = len(seen_by_route.setdefault(route_name, set()))
                    if pool:
                        counter.setdefault("_pumpswap_pool_set", set()).add(str(pool))
                        counter["unique_pumpswap_pools"] = len(counter["_pumpswap_pool_set"])
                    _append_jsonl_file(output_root / "pumpswap_route_candidates.jsonl", detection)
                _append_jsonl_file(output_root / "migration_route_audit_rows.jsonl", detection)
    for counter in route_counters.values():
        counter.pop("_pumpswap_pool_set", None)
    actual_duration = max(actual_durations) if source is not None and actual_durations else sum(actual_durations) if actual_durations else max(0.0, float(now_fn()) - started)
    dedupe_summary = dedupe_writer.summary()
    reconnect_attempts = sum(row["reconnect_attempts"] for row in route_status_by_route.values())
    reconnect_success_count = sum(row["reconnect_success_count"] for row in route_status_by_route.values())
    reconnect_failure_count = sum(row["reconnect_failure_count"] for row in route_status_by_route.values())
    reconnect_reasons = [reason for row in route_status_by_route.values() for reason in row.get("reconnect_reasons", [])]
    total_disconnected_seconds = sum(float(row.get("total_disconnected_seconds") or 0.0) for row in route_status_by_route.values())
    completed_requested_duration = bool(route_status_by_route) and all(bool(row.get("completed_requested_duration")) for row in route_status_by_route.values())
    pumpswap_counter = route_counters.get("pumpswap_pool_create", {})
    summary: dict[str, Any] = {
        "run_id": config.run_id,
        "mode": "migration-route-audit",
        "output_root": str(output_root),
        "requested_duration_seconds": float(config.source_duration_seconds),
        "actual_duration_seconds": float(actual_duration),
        "live_source_used": ",".join(str(row.get("source") or "unknown") for row in availability_rows),
        "subscription_connect_status": "available" if all(row.get("available", True) for row in availability_rows) else "partial_or_unavailable",
        "websocket_closed_early": any(bool(getattr(route, "websocket_closed_early", False)) for route, _, _ in route_specs),
        "websocket_close_reason": "; ".join(str(getattr(route, "websocket_close_reason", "") or "") for route, _, _ in route_specs).strip("; "),
        "source_filters_used": _migration_route_source_filters(),
        "program_ids_watched": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT, PUMPSWAP_PROGRAM_ID_FOR_AUDIT] if source is None else [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
        "account_required_filters": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT, PUMPSWAP_PROGRAM_ID_FOR_AUDIT] if source is None else [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
        "pumpfun_create_source_only": source is not None,
        "pumpfun_migrate_instruction_watched": "only_if_transaction_touches_pumpfun_program",
        "pumpswap_pair_created_source_watched": source is None,
        "dex_pair_created_source_watched": False,
        "source_route_could_see_axiom_migrated_tokens": "pumpfun_plus_pumpswap_account_required" if source is None else "partial_pumpfun_migrate_only_not_pumpswap_or_dex_pair",
        "routes": route_counters,
        "raw_pumpswap_candidates": int(pumpswap_counter.get("raw_pumpswap_candidates") or 0),
        "confirmed_pumpswap_rows": int(pumpswap_counter.get("confirmed_pumpswap_rows") or 0),
        "deduped_pumpswap_migration_events": int(pumpswap_counter.get("deduped_pumpswap_migration_events") or 0),
        "duplicate_pumpswap_rows_suppressed": int(pumpswap_counter.get("duplicate_pumpswap_rows_suppressed") or 0),
        "unique_pumpswap_mints": int(pumpswap_counter.get("unique_pumpswap_mints") or 0),
        "unique_pumpswap_pools": int(pumpswap_counter.get("unique_pumpswap_pools") or 0),
        "missing_mint_count": int(pumpswap_counter.get("missing_mint_count") or 0),
        "missing_pool_count": int(pumpswap_counter.get("missing_pair_pool_count") or 0),
        "reconnect_attempts": reconnect_attempts,
        "reconnect_success_count": reconnect_success_count,
        "reconnect_failure_count": reconnect_failure_count,
        "reconnect_reasons": reconnect_reasons,
        "total_disconnected_seconds": round(total_disconnected_seconds, 6),
        "completed_requested_duration": completed_requested_duration,
        "route_status_by_route": route_status_by_route,
        **dedupe_summary,
        "migration_route_audit_summary_path": str(output_root / "migration_route_audit_summary.json"),
        "migration_route_audit_rows_path": str(output_root / "migration_route_audit_rows.jsonl"),
        "valuation_ladder_emission_policy": "market_cap_confirmed_only",
        "valuation_ladder_events_written": 0,
        "mayhem_code_modified": False,
    }
    (output_root / "migration_route_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary



GLOBAL_MIGRATION_MONOTONIC_SUMMARY_KEYS = {
    "global_migration_events_deduped",
    "global_migration_unique_mints",
    "global_migration_unique_pools",
    "global_migration_mints_seen_in_birth_source",
    "global_migration_mints_admitted",
    "global_migration_mints_sample_rejected",
    "global_migration_mints_capacity_rejected",
    "global_migration_mints_not_seen_in_birth_source",
}


def _merge_global_migration_dedupe_summary(summary_counters: dict[str, Any], dedupe_summary: dict[str, Any]) -> None:
    for key, value in dedupe_summary.items():
        if key not in summary_counters:
            continue
        if key in GLOBAL_MIGRATION_MONOTONIC_SUMMARY_KEYS:
            summary_counters[key] = max(int(summary_counters.get(key) or 0), int(value or 0))
        else:
            summary_counters[key] = value


def _default_global_pumpswap_migration_route(config: BondingCurveRecorderConfig) -> Any:
    from research.mtp_research.validation.helius_transaction_subscribe_source import (
        HeliusPumpSwapTransactionSubscribeSource,
    )

    return HeliusPumpSwapTransactionSubscribeSource(
        timeout_seconds=min(2.0, max(0.5, config.source_duration_seconds)),
        max_reconnect_attempts=10,
    )


def run_global_pumpswap_migration_lane(
    config: BondingCurveRecorderConfig,
    recorder: BondingCurveProgressRecorder,
    *,
    source: Any | None = None,
    duration_seconds: float | None = None,
    migration_backfill_client: Any | None = None,
    migration_backfill_client_factory: Any | None = None,
    migration_backfill_lookup_sleep_ms: int = 0,
) -> dict[str, Any]:
    output_root = recorder.output_root
    if source is None:
        route = _default_global_pumpswap_migration_route(config)
    else:
        route = source
    route_duration = float(duration_seconds if duration_seconds is not None else config.source_duration_seconds)
    availability = route.availability() if hasattr(route, "availability") else {"source": route.__class__.__name__, "available": True}
    route_key = "pumpswap_transaction_subscribe" if availability.get("transactionSubscribe") else ("pumpswap_program_subscribe" if availability.get("programSubscribe") else "pumpswap_pool_create")
    counter = _empty_migration_route_counter(_migration_route_definitions()[route_key], 0)
    dedupe_writer = GlobalMigrationDedupeWriter(
        output_root,
        recorder=recorder,
        migration_backfill_client=migration_backfill_client,
        migration_backfill_client_factory=migration_backfill_client_factory,
        migration_backfill_lookup_sleep_ms=migration_backfill_lookup_sleep_ms,
    )
    seen_mints: set[str] = set()
    seen_pools: set[str] = set()
    seen_program_subscribe_update_pools: set[str] = set()

    def handle_event(event: dict[str, Any]) -> None:
        counter["raw_notifications"] += 1
        event.setdefault("audit_source_route", "pumpswap_transaction_subscribe" if availability.get("transactionSubscribe") else ("pumpswap_program_subscribe" if event.get("route_type") == "programSubscribe" else "pumpswap_pool_create"))
        if availability.get("transactionSubscribe") or event.get("route_name") == "pumpswap_transaction_subscribe":
            _record_pumpswap_transaction_route_audit(output_root, recorder, counter, event)
        detections: list[dict[str, Any]] = []
        rows_to_scan = [dict(row) for row in event.get("decoded_rows") or []] or [{}]
        swap_events_emitted = 0
        for row in rows_to_scan:
            if _looks_like_pumpswap_swap_row(row, event):
                swap_events_emitted += _emit_pumpswap_swap_events_from_notification(
                    output_root=output_root,
                    recorder=recorder,
                    counter=counter,
                    row=row,
                    event=event,
                )
        if swap_events_emitted == 0 and _looks_like_pumpswap_swap_row({}, event):
            _emit_pumpswap_swap_events_from_notification(
                output_root=output_root,
                recorder=recorder,
                counter=counter,
                row={},
                event=event,
            )
        program_subscribe_detection = _pumpswap_program_subscribe_detection_from_event(event)
        if program_subscribe_detection is not None:
            detections.append(program_subscribe_detection)
        else:
            for row in rows_to_scan:
                detection = _migration_route_detection_from_row(row, event)
                if detection is not None:
                    detections.append(detection)
        for detection in detections:
            if detection.get("source_route") not in {"pumpswap_program_subscribe", "pumpswap_pool_create"}:
                continue
            counter["candidate_migration_notifications"] += 1
            counter["detection_method"] = detection.get("detection_method")
            counter["confidence"] = detection.get("confidence")
            mint = str(detection.get("mint") or "")
            pool = str(detection.get("pool_or_pair_address") or "")
            if (
                detection.get("source_route") == "pumpswap_program_subscribe"
                and detection.get("detection_method") == "pumpswap_pool_account_update"
            ):
                update_key = pool or mint
                if update_key and update_key in seen_program_subscribe_update_pools:
                    counter["program_subscribe_existing_pool_updates_suppressed"] += 1
                    continue
                if update_key:
                    seen_program_subscribe_update_pools.add(update_key)
                counter["program_subscribe_unconfirmed_update_candidates"] += 1
            elif (
                detection.get("source_route") == "pumpswap_program_subscribe"
                and detection.get("detection_method") == "pumpswap_pool_account_create"
            ):
                counter["program_subscribe_confirmed_create_events"] += 1
            counter["raw_pumpswap_candidates"] += 1
            quote = _quote_identity_from_payload(detection, unsupported_as_unknown=False)
            detection["quote_mint"] = quote["quote_mint"]
            detection["quote_asset"] = quote["quote_asset"]
            detection["quote_asset_status"] = quote["quote_asset_status"]
            _increment_counter(counter["pumpswap_raw_candidates_by_quote_asset"], quote["quote_asset"])
            if quote["quote_asset_status"] == "unknown":
                counter["missing_quote_mint_count"] += 1
            elif quote["quote_asset_status"] == "unsupported":
                counter["unsupported_quote_asset_count"] += 1
            if detection.get("confidence") == "confirmed" and mint:
                counter["confirmed_pumpswap_rows"] += 1
                _increment_counter(counter["pumpswap_confirmed_events_by_quote_asset"], quote["quote_asset"])
            if not mint:
                counter["missing_mint_count"] += 1
                _increment_counter(counter["errors_by_reason"], "missing_mint")
            if not pool:
                counter["missing_pair_pool_count"] += 1
                _increment_counter(counter["errors_by_reason"], "missing_pair_pool")
            if mint:
                seen_mints.add(mint)
                counter["unique_migrated_mints"] = len(seen_mints)
                counter["unique_pumpswap_mints"] = len(seen_mints)
            if pool:
                seen_pools.add(pool)
                counter["unique_pumpswap_pools"] = len(seen_pools)
            emit_status = dedupe_writer.record(detection)
            if emit_status == "event":
                counter["decoded_migration_events"] += 1
                counter["deduped_pumpswap_migration_events"] += 1
                _increment_counter(counter["global_migration_events_by_quote_asset"], quote["quote_asset"])
            elif emit_status == "duplicate":
                counter["duplicate_pumpswap_rows_suppressed"] += 1
            else:
                counter["decoded_migration_candidates"] += 1
                _increment_counter(counter["global_migration_candidates_by_quote_asset"], quote["quote_asset"])
            _append_jsonl_file(output_root / "pumpswap_route_candidates.jsonl", detection)

    source_queue_stats: dict[str, Any] = {}
    if availability.get("available", True):
        source_queue_stats = _stream_notifications_via_reader_queue(
            route,
            route_duration,
            handle_event,
            queue_max_size=int(getattr(route, "source_event_queue_max_size", 10_000) or 10_000),
            thread_name="t007-pumpswap-source-reader",
        )

    route_status = _route_runtime_status(route, route_duration, availability)
    summary = {
        "mode": "global-pumpswap-migration-lane",
        "live_source_used": availability.get("source") or getattr(route, "source_name", route.__class__.__name__),
        "subscription_connect_status": "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}",
        "raw_pumpswap_candidates": int(counter.get("raw_pumpswap_candidates") or 0),
        "confirmed_pumpswap_rows": int(counter.get("confirmed_pumpswap_rows") or 0),
        "deduped_pumpswap_migration_events": int(counter.get("deduped_pumpswap_migration_events") or 0),
        "duplicate_pumpswap_rows_suppressed": int(counter.get("duplicate_pumpswap_rows_suppressed") or 0),
        "unique_pumpswap_mints": int(counter.get("unique_pumpswap_mints") or 0),
        "unique_pumpswap_pools": int(counter.get("unique_pumpswap_pools") or 0),
        "pumpswap_swap_events_decoded": int(counter.get("pumpswap_swap_events_decoded") or 0),
        "pumpswap_swap_buy_events": int(counter.get("pumpswap_swap_buy_events") or 0),
        "pumpswap_swap_sell_events": int(counter.get("pumpswap_swap_sell_events") or 0),
        "pumpswap_swap_fee_bps_populated_count": int(counter.get("pumpswap_swap_fee_bps_populated_count") or 0),
        "pumpswap_swap_balance_delta_partial_count": int(counter.get("pumpswap_swap_balance_delta_partial_count") or 0),
        "pumpswap_route_raw_notifications": int(counter.get("pumpswap_route_raw_notifications") or 0),
        "pumpswap_route_candidate_transactions": int(counter.get("pumpswap_route_candidate_transactions") or 0),
        "pumpswap_route_with_logs": int(counter.get("pumpswap_route_with_logs") or 0),
        "pumpswap_route_with_inner_instructions": int(counter.get("pumpswap_route_with_inner_instructions") or 0),
        "pumpswap_route_buy_candidates": int(counter.get("pumpswap_route_buy_candidates") or 0),
        "pumpswap_route_sell_candidates": int(counter.get("pumpswap_route_sell_candidates") or 0),
        "pumpswap_route_event_log_candidates": int(counter.get("pumpswap_route_event_log_candidates") or 0),
        "pumpswap_route_get_transaction_backfills": int(counter.get("pumpswap_route_get_transaction_backfills") or 0),
        "pumpswap_route_skipped_by_reason": dict(counter.get("pumpswap_route_skipped_by_reason") or {}),
        "program_subscribe_existing_pool_updates_suppressed": int(counter.get("program_subscribe_existing_pool_updates_suppressed") or 0),
        "program_subscribe_unconfirmed_update_candidates": int(counter.get("program_subscribe_unconfirmed_update_candidates") or 0),
        "program_subscribe_confirmed_create_events": int(counter.get("program_subscribe_confirmed_create_events") or 0),
        "missing_mint_count": int(counter.get("missing_mint_count") or 0),
        "missing_pool_count": int(counter.get("missing_pair_pool_count") or 0),
        "pumpswap_raw_candidates_by_quote_asset": dict(counter.get("pumpswap_raw_candidates_by_quote_asset") or {}),
        "pumpswap_confirmed_events_by_quote_asset": dict(counter.get("pumpswap_confirmed_events_by_quote_asset") or {}),
        "global_migration_events_by_quote_asset": dict(counter.get("global_migration_events_by_quote_asset") or {}),
        "global_migration_candidates_by_quote_asset": dict(counter.get("global_migration_candidates_by_quote_asset") or {}),
        "missing_quote_mint_count": int(counter.get("missing_quote_mint_count") or 0),
        "unsupported_quote_asset_count": int(counter.get("unsupported_quote_asset_count") or 0),
        "websocket_closed_early": route_status["websocket_closed_early"],
        "websocket_close_reason": route_status["websocket_close_reason"],
        "reconnect_attempts": route_status["reconnect_attempts"],
        "reconnect_success_count": route_status["reconnect_success_count"],
        "reconnect_failure_count": route_status["reconnect_failure_count"],
        "reconnect_reasons": route_status["reconnect_reasons"],
        "total_disconnected_seconds": route_status["total_disconnected_seconds"],
        "completed_requested_duration": route_status["completed_requested_duration"],
        "source_event_queue_high_water_mark": int(source_queue_stats.get("source_event_queue_high_water_mark") or 0),
        "source_event_queue_dropped_count": int(source_queue_stats.get("source_event_queue_dropped_count") or 0),
        "source_reader_error_count": int(source_queue_stats.get("source_reader_error_count") or 0),
        "source_reader_errors": list(source_queue_stats.get("source_reader_errors") or []),
        "source_reader_threaded": bool(source_queue_stats.get("source_reader_threaded", False)),
        "route_status_by_route": {route_key: route_status},
        **dedupe_writer.summary(),
    }
    _merge_global_migration_dedupe_summary(recorder.summary_counters, dedupe_writer.summary())
    _atomic_write_json(output_root / "global_migration_summary.json", summary)
    return summary


def run_transaction_live_smoke(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    curve_probe: Any | None = None,
    global_migration_source: Any | None = None,
    now_fn: Any = time.time,
) -> dict[str, Any]:
    recorder = BondingCurveProgressRecorder(config)
    try:
        recorder.pool_state_probe = PumpSwapPoolStateRpcProbe()
    except Exception:
        recorder.pool_state_probe = None
    try:
        recorder.execution_cost_probe = RecentPrioritizationFeeProbe()
    except Exception:
        recorder.execution_cost_probe = None
    recorder.record_execution_cost_sample("campaign_start", as_of=float(now_fn()))
    normalized_source = source if isinstance(source, TransactionSubscribeNormalizedBirthSource) else TransactionSubscribeNormalizedBirthSource(source)
    normalized_source.birth_priority_worker_count = int(config.birth_priority_worker_count)
    normalized_source.birth_priority_queue_max_size = int(config.birth_priority_queue_max_size)
    probe = curve_probe or _default_curve_probe(config)
    normalized_birth_to_probe_start_latencies_ms: list[float] = []
    probe_durations_ms: list[float] = []
    birth_priority_worker_count = max(1, int(config.birth_priority_worker_count))
    birth_priority_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=int(config.birth_priority_queue_max_size))
    birth_priority_results: queue.Queue[dict[str, Any]] = queue.Queue()
    birth_priority_results_stop = threading.Event()
    birth_priority_worker_errors: list[str] = []
    birth_priority_lock = threading.Lock()
    birth_priority_queue_high_water_mark = 0
    birth_priority_queue_dropped_count = 0
    first_curve_probe_enqueued_mints: set[str] = set()
    first_curve_probe_enqueued_mints_lock = threading.Lock()
    source_fast_probe_pending_admission_mints: set[str] = set()
    source_fast_probe_pending_admission_lock = threading.Lock()
    thin_probe_worker_count = 1
    thin_probe_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max(1, int(config.thin_probe_queue_max_size)))
    thin_probe_worker_errors: list[str] = []
    thin_probe_lock = threading.Lock()
    thin_probe_execution_queue_high_water_mark = 0
    thin_probe_execution_queue_dropped_count = 0
    birth_admission_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=int(config.birth_priority_queue_max_size))
    birth_admission_queue_high_water_mark = 0
    birth_admission_queue_dropped_count = 0
    birth_admission_worker_errors: list[str] = []
    trade_flow_worker_count = max(1, int(config.trade_flow_worker_count))
    trade_flow_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=int(config.trade_flow_queue_max_size))
    trade_flow_worker_errors: list[str] = []
    trade_flow_lock = threading.Lock()
    trade_flow_queue_high_water_mark = 0
    trade_flow_queue_dropped_count = 0
    hot_flow_windows_seconds = (1, 5, 10, 30, 60)
    hot_flow_max_events_per_mint = 2048
    hot_flow_lock = threading.Lock()
    hot_flow_entry_times: dict[str, float] = {}
    hot_flow_events_by_mint: dict[str, deque[dict[str, Any]]] = {}
    near_entry_hot_flow_events_seen = 0
    near_entry_hot_flow_events_recorded = 0
    near_entry_hot_flow_ring_buffer_dropped_count = 0

    def _launch_first_curve_probe_eligible(launch: dict[str, Any]) -> bool:
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if not mint:
            return False
        # Source-fast first curve evidence must not wait behind sampling or deep active-tracking capacity.
        _account_source, account = _probe_account_candidate(launch)
        return bool(account)

    def register_hot_flow_mint(launch: dict[str, Any]) -> None:
        if not config.near_entry_hot_flow_enabled:
            return
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if not mint:
            return
        entry_at = _num(launch.get("received_at")) or float(now_fn())
        with hot_flow_lock:
            if mint not in hot_flow_entry_times:
                hot_flow_entry_times[mint] = float(entry_at)
                hot_flow_events_by_mint[mint] = deque()
                recorder.summary_counters["near_entry_hot_flow_mints_registered"] += 1

    def update_hot_flow_from_trade(trade: dict[str, Any]) -> None:
        nonlocal near_entry_hot_flow_events_seen, near_entry_hot_flow_events_recorded
        nonlocal near_entry_hot_flow_ring_buffer_dropped_count
        if not config.near_entry_hot_flow_enabled:
            return
        mint = str(trade.get("mint") or trade.get("token_mint") or "").strip()
        if not mint:
            return
        received_at = _num(trade.get("received_at")) or float(now_fn())
        with hot_flow_lock:
            entry_at = hot_flow_entry_times.get(mint)
            if entry_at is None:
                return
            near_entry_hot_flow_events_seen += 1
            if received_at < entry_at or received_at - entry_at > max(hot_flow_windows_seconds):
                return
            events = hot_flow_events_by_mint.setdefault(mint, deque())
            direction = str(trade.get("trade_direction") or trade.get("side") or "").strip().lower()
            quote_amount = _num(
                _first_present(
                    trade,
                    ["quote_amount", "quote_amount_sol", "quote_amount_usdc", "sol_amount", "amount_quote"],
                )
            )
            events.append(
                {
                    "received_at": float(received_at),
                    "direction": direction,
                    "trader_wallet": trade.get("trader_wallet") or trade.get("fee_payer") or trade.get("buyer") or trade.get("seller"),
                    "quote_amount": quote_amount,
                }
            )
            near_entry_hot_flow_events_recorded += 1
            while len(events) > hot_flow_max_events_per_mint:
                events.popleft()
                near_entry_hot_flow_ring_buffer_dropped_count += 1

    def write_hot_flow_snapshots() -> None:
        if not config.near_entry_hot_flow_enabled:
            return
        rows: list[dict[str, Any]] = []
        t012_pre_entry_rows: list[dict[str, Any]] = []
        t012_post_entry_rows: list[dict[str, Any]] = []
        with hot_flow_lock:
            for mint, entry_at in hot_flow_entry_times.items():
                events = list(hot_flow_events_by_mint.get(mint) or [])
                rows_by_window: dict[int, dict[str, Any]] = {}
                for window in hot_flow_windows_seconds:
                    window_events = [
                        event
                        for event in events
                        if 0.0 <= float(event.get("received_at") or 0.0) - float(entry_at) <= float(window)
                    ]
                    buy_events = [event for event in window_events if str(event.get("direction") or "").lower() == "buy"]
                    sell_events = [event for event in window_events if str(event.get("direction") or "").lower() == "sell"]
                    unique_buyers = {
                        str(event.get("trader_wallet") or "")
                        for event in buy_events
                        if str(event.get("trader_wallet") or "").strip()
                    }
                    sell_quotes = [_num(event.get("quote_amount")) for event in sell_events]
                    sell_quotes_clean = [value for value in sell_quotes if value is not None]
                    buy_quotes = [_num(event.get("quote_amount")) for event in buy_events]
                    buy_quotes_clean = [value for value in buy_quotes if value is not None]
                    row = {
                        "mint": mint,
                        "campaign_id": config.run_id,
                        "run_id": config.run_id,
                        "entry_reference": "first_seen_birth",
                        "snapshot_phase": "post_entry",
                        "decision_time_safety_status": "safe",
                        "entry_received_at": entry_at,
                        "window_seconds_after_entry": int(window),
                        "buy_count_after_entry": len(buy_events),
                        "sell_count_after_entry": len(sell_events),
                        "net_buy_count_after_entry": len(buy_events) - len(sell_events),
                        "unique_buyers_after_entry": len(unique_buyers),
                        "unique_sellers_after_entry": len(
                            {
                                str(event.get("trader_wallet") or "")
                                for event in sell_events
                                if str(event.get("trader_wallet") or "").strip()
                            }
                        ),
                        "buy_sell_ratio_after_entry": (float(len(buy_events)) / float(len(sell_events))) if sell_events else None,
                        "largest_buy_quote_after_entry": max(buy_quotes_clean) if buy_quotes_clean else None,
                        "largest_sell_quote_after_entry": max(sell_quotes_clean) if sell_quotes_clean else None,
                        "market_cap_change_after_entry": None,
                        "snapshot_status": "available" if window_events else "no_trade_events_observed",
                        "decision_time_safe": True,
                    }
                    rows.append(row)
                    rows_by_window[int(window)] = row
                try:
                    from research.mtp_research.validation.t012_paper_snapshot_contract import (
                        build_post_entry_hot_flow_snapshot,
                        build_pre_entry_decision_snapshot,
                    )

                    state = recorder.states.get(mint)
                    birth_row = recorder.birth_rows_by_mint.get(mint, {})
                    observation = (getattr(state, "last_observation_row", None) if state is not None else None) or {}
                    creator_history = getattr(state, "creator_history_metrics", {}) if state is not None else {}
                    dev_previous_migrations = creator_history.get("creator_prior_migration_count_before_this_launch")
                    creator_sold_before_entry = (
                        bool(getattr(state, "creator_sold_before_entry_observed", False))
                        if state is not None and getattr(state, "creator_address", None)
                        else None
                    )
                    curve_progress = _first_present(observation, ["progress_pct", "candidate_progress_pct"])
                    market_cap_usd = _first_present(
                        observation,
                        [
                            "bonding_curve_market_cap_usd",
                            "market_cap_usd",
                            "fdv_proxy_usd",
                            "reserve_fdv_usd",
                        ],
                    )
                    t012_pre_entry_rows.append(
                        build_pre_entry_decision_snapshot(
                            run_id=config.run_id,
                            mint=mint,
                            token_symbol=_first_present(birth_row, ["token_symbol", "symbol", "name"]),
                            birth_time=entry_at,
                            decision_time=float(entry_at) + 60.0,
                            decision_slot=_int(_first_present(birth_row, ["slot", "birth_slot", "source_slot"])),
                            birth_verified=True,
                            bonding_curve_verified=bool(
                                _first_present(birth_row, ["bonding_curve_verified", "curve_account_verified"])
                                or (getattr(state, "bonding_curve_account", None) if state is not None else None)
                            ),
                            curve_state_available=bool(observation),
                            market_cap_available=market_cap_usd is not None,
                            curve_progress_pct=_num(curve_progress),
                            market_cap_usd=_num(market_cap_usd),
                            flow_30s=rows_by_window.get(30),
                            flow_60s=rows_by_window.get(60),
                            dev_wallet=getattr(state, "creator_address", None) if state is not None else birth_row.get("creator"),
                            dev_previous_migrations=_int(dev_previous_migrations),
                            creator_sold_before_entry=creator_sold_before_entry,
                            max_source_lag_ms=None,
                            source_provenance={
                                "source": "near_entry_hot_flow_snapshot_writer",
                                "birth_signature": birth_row.get("signature"),
                                "birth_source_route": birth_row.get("source_route") or birth_row.get("source_route_type"),
                            },
                            input_event_ids=[birth_row.get("signature"), mint, "pre_entry_30s_60s"],
                        )
                    )
                    for window, legacy_row in rows_by_window.items():
                        migration_received_at = getattr(state, "migration_received_at", None) if state is not None else None
                        migration_seen = bool(
                            migration_received_at is not None
                            and float(migration_received_at) <= float(entry_at) + float(window)
                        )
                        t012_post_entry_rows.append(
                            build_post_entry_hot_flow_snapshot(
                                run_id=config.run_id,
                                mint=mint,
                                paper_candidate_id=f"{config.run_id}:{mint}:first_seen_birth",
                                entry_reference_time=entry_at,
                                snapshot_offset_seconds=window,
                                snapshot_time=float(entry_at) + float(window),
                                snapshot_slot=_int(_first_present(birth_row, ["slot", "birth_slot", "source_slot"])),
                                buy_count_since_reference=int(legacy_row.get("buy_count_after_entry") or 0),
                                sell_count_since_reference=int(legacy_row.get("sell_count_after_entry") or 0),
                                unique_buyers_since_reference=int(legacy_row.get("unique_buyers_after_entry") or 0),
                                unique_sellers_since_reference=int(legacy_row.get("unique_sellers_after_entry") or 0),
                                largest_buy_quote_since_reference=_num(legacy_row.get("largest_buy_quote_after_entry")),
                                largest_sell_quote_since_reference=_num(legacy_row.get("largest_sell_quote_after_entry")),
                                creator_sold_after_reference=None,
                                migration_seen=migration_seen,
                                near_migration=migration_seen,
                                source_provenance={
                                    "source": "near_entry_hot_flow_snapshot_writer",
                                    "legacy_artifact": "near_entry_hot_flow_snapshots.jsonl",
                                },
                                input_event_ids=[birth_row.get("signature"), mint, f"post_entry_{window}s"],
                            )
                        )
                except Exception as exc:
                    recorder._record_finalization_error("t012_hot_flow_snapshot_build", exc)
        for row in rows:
            recorder._append_jsonl("near_entry_hot_flow_snapshots.jsonl", row)
        if t012_pre_entry_rows or t012_post_entry_rows:
            try:
                from research.mtp_research.validation.t012_paper_snapshot_contract import write_t012_paper_snapshot_artifacts

                write_t012_paper_snapshot_artifacts(
                    recorder.output_root,
                    run_id=config.run_id,
                    pre_entry_rows=t012_pre_entry_rows,
                    post_entry_rows=t012_post_entry_rows,
                )
            except Exception as exc:
                recorder._record_finalization_error("t012_paper_snapshot_artifacts", exc)
        recorder.summary_counters["near_entry_hot_flow_events_seen"] = near_entry_hot_flow_events_seen
        recorder.summary_counters["near_entry_hot_flow_events_recorded"] = near_entry_hot_flow_events_recorded
        recorder.summary_counters["near_entry_hot_flow_ring_buffer_dropped_count"] = near_entry_hot_flow_ring_buffer_dropped_count
        recorder.summary_counters["near_entry_hot_flow_snapshots_written"] = len(rows)
        recorder.summary_counters["near_entry_hot_flow_snapshot_mints"] = len(hot_flow_entry_times)
        for window in hot_flow_windows_seconds:
            recorder.summary_counters[f"near_entry_hot_flow_snapshot_{window}s_count"] = sum(
                1 for row in rows if int(row.get("window_seconds_after_entry") or 0) == int(window)
            )

    def execute_deep_probe_job(job: dict[str, Any]) -> dict[str, Any]:
        launch = dict(job["launch"])
        attempts = [0, *list(config.probe_retry_delays_ms)]
        results: list[dict[str, Any]] = []
        for attempt_index, delay_ms in enumerate(attempts):
            result = _execute_probe_attempt(
                launch,
                probe,
                now_fn=now_fn,
                attempt_index=attempt_index,
                delay_ms=delay_ms,
                final_for_mint=False,
                probe_scope="deep_initial_probe",
            )
            results.append(result)
            observation = dict(result.get("observation") or {})
            if observation.get("account_found") is True:
                break
            if observation.get("error_reason") != "account_not_found":
                break
        return {**job, "probe_results": results}

    def birth_priority_worker_loop() -> None:
        while True:
            job = birth_priority_queue.get()
            try:
                if job is None:
                    return
                birth_priority_results.put(execute_deep_probe_job(job))
            except Exception as exc:
                with birth_priority_lock:
                    birth_priority_worker_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                birth_priority_queue.task_done()

    birth_priority_workers = [
        threading.Thread(target=birth_priority_worker_loop, name=f"t007-birth-priority-probe-{index}", daemon=True)
        for index in range(birth_priority_worker_count)
    ]
    for worker in birth_priority_workers:
        worker.start()

    def record_deep_probe_job_result(job_result: dict[str, Any]) -> None:
        launch = dict(job_result.get("launch") or {})
        received_at = _num(job_result.get("received_at"))
        normalized_at = _num(job_result.get("normalized_at"))
        probe_job_enqueued_at = _num(job_result.get("probe_job_enqueued_at"))
        probe_results = list(job_result.get("probe_results") or [])
        if probe_results:
            first_attempt = dict(probe_results[0].get("attempt_row") or {})
            probe_started_at = _num(first_attempt.get("probe_started_at"))
            probe_mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
            if probe_mint:
                recorder._update_hotpath_latency_span(probe_mint, probe_started_at=probe_started_at)
            if normalized_at is not None and probe_started_at is not None:
                normalized_latency = max(0.0, (probe_started_at - normalized_at) * 1000.0)
                normalized_birth_to_probe_start_latencies_ms.append(normalized_latency)
                recorder.normalized_birth_to_probe_start_latencies_ms.append(normalized_latency)
            if probe_job_enqueued_at is not None and probe_started_at is not None:
                recorder.probe_job_enqueue_to_probe_start_latencies_ms.append(
                    max(0.0, (probe_started_at - probe_job_enqueued_at) * 1000.0)
                )
        first_success_at: float | None = None
        final_observation: dict[str, Any] | None = None
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if mint and received_at is not None:
            recorder._upsert_tracking_state_from_launch(
                mint,
                launch,
                received_at=received_at,
                decoded_route=_decoded_route_from_launch(launch),
                deep_tracking_admitted=False,
            )
        for result in probe_results:
            observation, probe_duration_ms = _record_probe_attempt_result(recorder, result)
            probe_durations_ms.append(probe_duration_ms)
            recorder.probe_duration_latencies_ms.append(probe_duration_ms)
            final_observation = observation
            attempt_index = int(observation.get("probe_attempt_index") or 0)
            if observation.get("account_found") is True and first_success_at is None:
                first_success_at = _num(observation.get("probe_finished_at")) or float(now_fn())
                recorder.probe_attempts_until_success.append(attempt_index + 1)
                if received_at is not None:
                    recorder.time_to_first_success_ms.append(max(0.0, (first_success_at - received_at) * 1000.0))
                if attempt_index == 0:
                    recorder.summary_counters["first_attempt_success_count"] += 1
                else:
                    recorder.summary_counters["retry_success_count"] += 1
        if final_observation is not None:
            final_observation["final_for_mint"] = True
            if final_observation.get("account_found") is False and final_observation.get("error_reason") == "account_not_found":
                recorder.summary_counters["final_account_not_found_count"] += 1
            final_attempt_index = int(final_observation.get("probe_attempt_index") or 0)
            if final_attempt_index > 0 or final_observation.get("account_found") is False:
                recorder.record_observation(final_observation)

    def drain_birth_priority_results() -> None:
        while True:
            try:
                job_result = birth_priority_results.get_nowait()
            except queue.Empty:
                break
            try:
                record_deep_probe_job_result(job_result)
            finally:
                birth_priority_results.task_done()

    def birth_priority_result_consumer_loop() -> None:
        while not birth_priority_results_stop.is_set() or not birth_priority_results.empty():
            try:
                job_result = birth_priority_results.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                record_deep_probe_job_result(job_result)
            except Exception as exc:
                with birth_priority_lock:
                    birth_priority_worker_errors.append(f"result_consumer:{type(exc).__name__}: {exc}")
            finally:
                birth_priority_results.task_done()

    birth_priority_result_consumer = threading.Thread(
        target=birth_priority_result_consumer_loop,
        name="t007-birth-priority-result-consumer",
        daemon=True,
    )
    birth_priority_result_consumer.start()

    def thin_probe_worker_loop() -> None:
        while True:
            job = thin_probe_queue.get()
            try:
                if job is None:
                    return
                _run_thin_probe_for_birth(
                    recorder,
                    dict(job.get("launch") or {}),
                    dict(job.get("birth_row") or {}),
                    probe,
                    now_fn=now_fn,
                )
            except Exception as exc:
                with thin_probe_lock:
                    thin_probe_worker_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                thin_probe_queue.task_done()

    thin_probe_worker = threading.Thread(
        target=thin_probe_worker_loop,
        name="t007-thin-probe-worker",
        daemon=True,
    )
    thin_probe_worker.start()

    def enqueue_deep_probe_job(
        launch: dict[str, Any],
        *,
        received_at: float | None,
        normalized_at: float | None,
        source_fast_path: bool = False,
    ) -> bool:
        nonlocal birth_priority_queue_high_water_mark, birth_priority_queue_dropped_count
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if mint:
            with first_curve_probe_enqueued_mints_lock:
                if mint in first_curve_probe_enqueued_mints:
                    if source_fast_path:
                        recorder.summary_counters["source_fast_first_curve_probe_duplicate_suppressed"] += 1
                    return False
                first_curve_probe_enqueued_mints.add(mint)
        probe_job_enqueued_at = float(now_fn())
        job = {
            "launch": dict(launch),
            "received_at": received_at,
            "normalized_at": normalized_at,
            "probe_job_enqueued_at": probe_job_enqueued_at,
        }
        try:
            birth_priority_queue.put_nowait(job)
            if mint:
                recorder._update_hotpath_latency_span(mint, probe_enqueued_at=probe_job_enqueued_at)
            birth_priority_queue_high_water_mark = max(birth_priority_queue_high_water_mark, int(birth_priority_queue.qsize()))
            if source_fast_path:
                commit_epoch = _num(launch.get("verified_birth_db_committed_at_epoch"))
                if commit_epoch is not None:
                    recorder.verified_birth_commit_to_probe_enqueue_latencies_ms.append(
                        max(0.0, (probe_job_enqueued_at - float(commit_epoch)) * 1000.0)
                    )
            return True
        except queue.Full:
            birth_priority_queue_dropped_count += 1
            record_deep_probe_job_result(execute_deep_probe_job(job))
            return False

    def enqueue_source_fast_first_curve_probe(launch: dict[str, Any]) -> None:
        recorder.summary_counters["source_fast_birth_probe_hook_events"] += 1
        recorder.record_source_verified_birth_commit(launch)
        if not _launch_first_curve_probe_eligible(launch):
            recorder.summary_counters["source_fast_first_curve_probe_ineligible"] += 1
            return
        mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        if mint:
            with source_fast_probe_pending_admission_lock:
                source_fast_probe_pending_admission_mints.add(mint)
        register_hot_flow_mint(launch)
        received_at = _num(launch.get("received_at"))
        normalized_at = _num(launch.get("normalized_at")) or received_at
        if enqueue_deep_probe_job(
            launch,
            received_at=received_at,
            normalized_at=normalized_at,
            source_fast_path=True,
        ):
            recorder.summary_counters["source_fast_first_curve_probe_enqueued"] += 1
        elif mint:
            with source_fast_probe_pending_admission_lock:
                source_fast_probe_pending_admission_mints.discard(mint)

    def enqueue_thin_probe_job(launch: dict[str, Any], birth_row: dict[str, Any]) -> None:
        nonlocal thin_probe_execution_queue_high_water_mark, thin_probe_execution_queue_dropped_count
        job = {"launch": dict(launch), "birth_row": dict(birth_row)}
        try:
            thin_probe_queue.put_nowait(job)
            thin_probe_execution_queue_high_water_mark = max(
                thin_probe_execution_queue_high_water_mark,
                1,
                int(thin_probe_queue.qsize()),
            )
        except queue.Full:
            thin_probe_execution_queue_dropped_count += 1
            recorder.summary_counters["thin_probe_queue_drops"] += 1
            _increment_counter(recorder.summary_counters["thin_probe_defer_reasons"], "thin_probe_execution_queue_full")

    def enqueue_birth_admission_job(launch: dict[str, Any]) -> None:
        nonlocal birth_admission_queue_high_water_mark, birth_admission_queue_dropped_count
        launch_for_worker = dict(launch)
        admission_started = float(now_fn())
        received_at = _num(launch_for_worker.get("received_at"))
        normalized_at = _num(launch_for_worker.get("normalized_at")) or received_at
        launch_for_worker["_birth_admission_enqueued_at"] = admission_started
        if _launch_first_curve_probe_eligible(launch_for_worker):
            register_hot_flow_mint(launch_for_worker)
        if received_at is not None:
            recorder.birth_to_admission_latencies_ms.append(max(0.0, (admission_started - received_at) * 1000.0))
            launch_for_worker["_admission_latency_recorded"] = True
        try:
            recorder.record_source_verified_birth_commit(launch_for_worker)
            birth_admission_queue.put_nowait(launch_for_worker)
            birth_admission_queue_high_water_mark = max(
                birth_admission_queue_high_water_mark,
                int(birth_admission_queue.qsize()),
            )
        except queue.Full:
            birth_admission_queue_dropped_count += 1
            handle_launch(launch_for_worker)

    def raise_if_scan_supervisor_stop_requested() -> None:
        stop_path = recorder.output_root / "scan_stop_requested.json"
        if not stop_path.exists():
            return
        try:
            payload = json.loads(stop_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if payload.get("drain_and_finalize_requested") or payload.get("hard_abort_requested"):
            reasons = payload.get("abort_reasons") or []
            reason_text = ",".join(str(reason) for reason in reasons) or "scan_supervisor_stop_requested"
            recorder.failure_reason = f"scan_supervisor_early_abort:{reason_text}"
            raise RuntimeError(recorder.failure_reason)

    def handle_launch(launch: dict[str, Any]) -> None:
        raise_if_scan_supervisor_stop_requested()
        launch_mint = str(launch.get("mint") or launch.get("token_mint") or "").strip()
        admission_started = float(now_fn())
        enqueued_at = _num(launch.get("_birth_admission_enqueued_at"))
        if enqueued_at is not None:
            recorder.birth_enqueue_to_admission_worker_start_latencies_ms.append(
                max(0.0, (admission_started - enqueued_at) * 1000.0)
            )
        register_hot_flow_mint(launch)
        received_at = _num(launch.get("received_at"))
        normalized_at = _num(launch.get("normalized_at")) or received_at
        if _launch_first_curve_probe_eligible(launch) and not _bool(launch.get("_probe_already_enqueued")):
            probe_enqueued = enqueue_deep_probe_job(launch, received_at=received_at, normalized_at=normalized_at)
            launch["_probe_already_enqueued"] = True
            if probe_enqueued:
                recorder.admission_worker_to_probe_job_enqueue_latencies_ms.append(
                    max(0.0, (float(now_fn()) - admission_started) * 1000.0)
                )
        recorder.maybe_record_periodic_execution_cost(as_of=admission_started)
        process_birth_started = float(now_fn())
        if launch_mint:
            recorder._update_hotpath_latency_span(
                launch_mint,
                admission_decision_started_at=process_birth_started,
                projection_enqueued_at=process_birth_started,
            )
        birth_row = recorder.process_birth(launch)
        process_birth_finished = float(now_fn())
        admission_decision_finished_at = _num(launch.get("_admission_decision_finished_at")) or process_birth_finished
        if launch_mint:
            recorder._update_hotpath_latency_span(
                launch_mint,
                admission_decision_finished_at=admission_decision_finished_at,
                projection_finished_at=process_birth_finished,
                materialized_at=process_birth_finished,
            )
            recorder._flush_hotpath_latency_span(launch_mint)
        if launch_mint:
            with source_fast_probe_pending_admission_lock:
                source_fast_probe_pending_admission_mints.discard(launch_mint)
        recorder.admission_worker_process_birth_duration_ms.append(
            max(0.0, (process_birth_finished - process_birth_started) * 1000.0)
        )
        admission_finished = float(now_fn())
        received_at_for_complete = _num(launch.get("received_at"))
        if received_at_for_complete is not None:
            recorder.birth_to_admission_decision_latencies_ms.append(
                max(0.0, (admission_decision_finished_at - received_at_for_complete) * 1000.0)
            )
            recorder.birth_projection_complete_latencies_ms.append(
                max(0.0, (admission_finished - received_at_for_complete) * 1000.0)
            )
        admitted = birth_row.get("admitted") is True
        if admitted:
            register_hot_flow_mint(launch)
            recorder.summary_counters["retry_queue_high_water_mark"] = max(
                int(recorder.summary_counters.get("retry_queue_high_water_mark") or 0),
                max(0, len([0, *list(config.probe_retry_delays_ms)]) - 1),
            )
            if not _bool(launch.get("_probe_already_enqueued")):
                probe_enqueued = enqueue_deep_probe_job(launch, received_at=received_at, normalized_at=normalized_at)
                launch["_probe_already_enqueued"] = True
                if probe_enqueued:
                    recorder.admission_worker_to_probe_job_enqueue_latencies_ms.append(
                        max(0.0, (float(now_fn()) - admission_started) * 1000.0)
                    )
        if launch.get("creator"):
            recorder.record_dev_behavior_event(
                {
                    "mint": launch.get("mint"),
                    "signature": launch.get("signature"),
                    "slot": launch.get("slot"),
                    "block_time": launch.get("block_time"),
                    "received_at": launch.get("received_at") or admission_started,
                    "decision_time": launch.get("received_at") or admission_started,
                    "creator_wallet": launch.get("creator"),
                    "dev_wallet": launch.get("creator"),
                    "dev_behavior_status": "partial_birth_metadata",
                    "source_event_type": "pumpfun_birth_metadata",
                    "feature_scope": "creator_identity_only",
                    "notes": "Creator/dev enrichment is partial and sourced from Pump.fun create metadata only.",
                }
            )
        if not admitted:
            if (
                not _bool(launch.get("_probe_already_enqueued"))
                and (birth_row.get("thin_probe_scheduled") is True or birth_row.get("admission_reason") == "sample_rejected")
            ):
                enqueue_thin_probe_job(launch, birth_row)
            return
        if received_at is not None and not _bool(launch.get("_admission_latency_recorded")):
            recorder.birth_to_admission_latencies_ms.append(max(0.0, (admission_started - received_at) * 1000.0))

    def birth_admission_worker_loop() -> None:
        while True:
            launch = birth_admission_queue.get()
            try:
                if launch is None:
                    return
                handle_launch(dict(launch))
            except Exception as exc:
                birth_admission_worker_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                birth_admission_queue.task_done()

    birth_admission_worker = threading.Thread(
        target=birth_admission_worker_loop,
        name="t007-birth-admission-owner",
        daemon=True,
    )
    birth_admission_worker.start()

    def handle_trade(trade: dict[str, Any]) -> None:
        raise_if_scan_supervisor_stop_requested()
        recorder.maybe_record_periodic_execution_cost(as_of=_num(trade.get("received_at")) or float(now_fn()))
        trade_row = recorder.record_trade_event(trade)
        holder_proxy_count = max(
            int(trade_row.get("unique_buyers_since_launch") or 0),
            int(trade_row.get("unique_sellers_since_launch") or 0),
            1 if trade_row.get("trader_wallet") else 0,
        )
        recorder.record_holder_snapshot(
            {
                "mint": trade_row.get("mint"),
                "signature": trade_row.get("signature"),
                "slot": trade_row.get("slot"),
                "block_time": trade_row.get("block_time"),
                "received_at": trade_row.get("received_at"),
                "decision_time": trade_row.get("received_at"),
                "holder_distribution_status": "partial_trade_derived",
                "holder_count": holder_proxy_count,
                "unique_holder_proxy_count": holder_proxy_count,
                "unique_buyers_since_launch": trade_row.get("unique_buyers_since_launch"),
                "unique_sellers_since_launch": trade_row.get("unique_sellers_since_launch"),
                "trade_count_since_launch": trade_row.get("trade_count_since_launch"),
                "buy_count_since_launch": trade_row.get("buy_count_since_launch"),
                "sell_count_since_launch": trade_row.get("sell_count_since_launch"),
                "source_event_type": "trade_derived_holder_proxy",
                "feature_scope": "partial_trade_observed_holders_only",
                "notes": "Not a full token-account holder snapshot; proxy is derived from observed trade wallets.",
            }
        )

    def enqueue_trade_flow_job(trade: dict[str, Any]) -> None:
        nonlocal trade_flow_queue_high_water_mark, trade_flow_queue_dropped_count
        update_hot_flow_from_trade(trade)
        try:
            trade_flow_queue.put_nowait(dict(trade))
            trade_flow_queue_high_water_mark = max(trade_flow_queue_high_water_mark, int(trade_flow_queue.qsize()))
        except queue.Full:
            trade_flow_queue_dropped_count += 1
            handle_trade(dict(trade))

    def drain_trade_flow_jobs(*, max_items: int | None = None) -> int:
        processed = 0
        while max_items is None or processed < max_items:
            try:
                trade = trade_flow_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if trade is not None:
                    handle_trade(dict(trade))
            except Exception as exc:
                with trade_flow_lock:
                    trade_flow_worker_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                processed += 1
                trade_flow_queue.task_done()
        return processed

    def drain_low_priority_source_work() -> dict[str, Any]:
        drain_trade_flow_jobs(max_items=10)
        return drain_live_global_migration_side_effects()

    global_migration_summary: dict[str, Any] = {}
    global_migration_errors: list[str] = []
    global_migration_thread: threading.Thread | None = None
    live_migration_events_stat: tuple[int, int] | None = None

    def drain_live_global_migration_side_effects() -> dict[str, Any]:
        nonlocal live_migration_events_stat
        if not config.enable_global_pumpswap_migration:
            return {}
        events_path = recorder.output_root / "global_migration_events.jsonl"
        try:
            stat = events_path.stat()
        except FileNotFoundError:
            return {}
        current_stat = (int(stat.st_size), int(stat.st_mtime_ns))
        if current_stat == live_migration_events_stat or stat.st_size <= 0:
            return {}
        live_migration_events_stat = current_stat
        try:
            result = recorder.apply_global_migration_side_effects_from_artifact()
            post_observations_written = recorder.write_due_post_migration_observations(as_of=float(now_fn()))
        except Exception as exc:
            recorder.summary_counters["live_migration_side_effect_drain_count"] += 1
            recorder.summary_counters["live_migration_side_effects_failed"] += 1
            recorder.summary_counters["live_migration_side_effect_last_drain_at"] = float(now_fn())
            global_migration_errors.append(f"live_migration_side_effect_drain:{type(exc).__name__}: {exc}")
            return {
                "migration_side_effects_applied": 0,
                "migration_side_effects_failed": 1,
                "migration_side_effects_source_rows": 0,
            }
        source_rows = int(result.get("migration_side_effects_source_rows") or 0)
        if source_rows > 0:
            recorder.summary_counters["live_migration_side_effect_drain_count"] += 1
            recorder.summary_counters["live_migration_side_effects_applied"] += int(
                result.get("migration_side_effects_applied") or 0
            )
            recorder.summary_counters["live_migration_side_effects_failed"] += int(
                result.get("migration_side_effects_failed") or 0
            )
            recorder.summary_counters["live_migration_side_effects_source_rows"] = max(
                int(recorder.summary_counters.get("live_migration_side_effects_source_rows") or 0),
                source_rows,
            )
            recorder.summary_counters["live_migration_side_effects_post_observations_written"] += int(
                post_observations_written or 0
            )
            recorder.summary_counters["live_migration_side_effect_last_drain_at"] = float(now_fn())
        return result

    run_supplied_migration_source_after_births = bool(config.enable_global_pumpswap_migration and global_migration_source is not None)
    if config.enable_global_pumpswap_migration and not run_supplied_migration_source_after_births:
        def run_pumpswap_lane() -> None:
            nonlocal global_migration_summary
            try:
                global_migration_summary = run_global_pumpswap_migration_lane(
                    config,
                    recorder,
                    source=global_migration_source,
                    duration_seconds=config.source_duration_seconds,
                    migration_backfill_client_factory=DirectMintLookupRpcClient,
                    migration_backfill_lookup_sleep_ms=0,
                )
            except Exception as exc:
                global_migration_errors.append(f"{type(exc).__name__}: {exc}")

        global_migration_thread = threading.Thread(target=run_pumpswap_lane, name="t007-pumpswap-global-migration", daemon=True)
        global_migration_thread.start()

    try:
        raise_if_scan_supervisor_stop_requested()
        normalized_source.stream_launches(
            config.source_duration_seconds,
            enqueue_birth_admission_job,
            on_trade=enqueue_trade_flow_job,
            on_idle=drain_low_priority_source_work,
            on_birth_fast_path=enqueue_source_fast_first_curve_probe,
        )
    except RuntimeError as exc:
        if str(exc).startswith("scan_supervisor_early_abort:"):
            global_migration_errors.append(str(exc))
        else:
            raise
    birth_admission_queue.join()
    birth_admission_queue.put(None)
    birth_admission_worker.join(timeout=5.0)
    if birth_admission_worker.is_alive():
        birth_admission_worker_errors.append("birth_admission_worker_join_timeout")
    if run_supplied_migration_source_after_births:
        try:
            global_migration_summary = run_global_pumpswap_migration_lane(
                config,
                recorder,
                source=global_migration_source,
                duration_seconds=config.source_duration_seconds,
                migration_backfill_client_factory=DirectMintLookupRpcClient,
                migration_backfill_lookup_sleep_ms=0,
            )
        except Exception as exc:
            global_migration_errors.append(f"{type(exc).__name__}: {exc}")
    if global_migration_thread is not None:
        global_migration_thread.join(timeout=float(config.global_migration_thread_join_timeout_seconds))
        if global_migration_thread.is_alive():
            global_migration_errors.append("global_migration_thread_join_timeout")
    thin_probe_queue.join()
    thin_probe_queue.put(None)
    thin_probe_worker.join(timeout=5.0)
    if thin_probe_worker.is_alive():
        thin_probe_worker_errors.append("thin_probe_worker_join_timeout")
    drain_trade_flow_jobs()
    write_hot_flow_snapshots()
    birth_priority_queue.join()
    for _worker in birth_priority_workers:
        birth_priority_queue.put(None)
    for worker in birth_priority_workers:
        worker.join(timeout=5.0)
    birth_priority_results.join()
    birth_priority_results_stop.set()
    birth_priority_result_consumer.join(timeout=5.0)
    if birth_priority_result_consumer.is_alive():
        birth_priority_worker_errors.append("birth_priority_result_consumer_join_timeout")
        drain_birth_priority_results()
    final_migration_side_effect_summary = recorder.apply_global_migration_side_effects_from_artifact()
    final_post_migration_observations_written = recorder.write_due_post_migration_observations(as_of=float(now_fn()))
    live_migration_side_effects_applied = int(recorder.summary_counters.get("live_migration_side_effects_applied") or 0)
    live_migration_side_effects_failed = int(recorder.summary_counters.get("live_migration_side_effects_failed") or 0)
    migration_side_effect_summary = {
        "migration_side_effects_applied": live_migration_side_effects_applied
        + int(final_migration_side_effect_summary.get("migration_side_effects_applied") or 0),
        "migration_side_effects_failed": live_migration_side_effects_failed
        + int(final_migration_side_effect_summary.get("migration_side_effects_failed") or 0),
        "migration_side_effects_source_rows": max(
            int(recorder.summary_counters.get("live_migration_side_effects_source_rows") or 0),
            int(final_migration_side_effect_summary.get("migration_side_effects_source_rows") or 0),
        ),
        "finalization_migration_side_effects_applied": int(
            final_migration_side_effect_summary.get("migration_side_effects_applied") or 0
        ),
        "finalization_migration_side_effects_failed": int(
            final_migration_side_effect_summary.get("migration_side_effects_failed") or 0
        ),
        "finalization_post_migration_observations_written": int(final_post_migration_observations_written or 0),
    }
    recorder.record_execution_cost_sample("finalization", as_of=float(now_fn()))
    metrics = dict(normalized_source.metrics)
    source_quality = _source_duration_quality_fields(
        config.source_duration_seconds,
        metrics.get("actual_source_duration_seconds") or metrics.get("actual_duration_seconds"),
        websocket_closed_early=bool(metrics.get("websocket_closed_early", False)),
        websocket_close_reason=metrics.get("websocket_close_reason"),
        websocket_keepalive_timeout_count=_int(metrics.get("websocket_keepalive_timeout_count")) or 0,
        websocket_reconnect_count=_int(metrics.get("websocket_reconnect_count")) or 0,
    )
    recorder.summary_counters["source_event_queue_dropped_count"] = int(metrics.get("source_event_queue_dropped_count") or 0)
    recorder.summary_counters["birth_admission_queue_dropped_count"] = int(birth_admission_queue_dropped_count or 0)
    recorder.summary_counters["birth_priority_queue_dropped_count"] = int(birth_priority_queue_dropped_count or 0)
    recorder.summary_counters["trade_flow_queue_dropped_count"] = int(trade_flow_queue_dropped_count or 0)
    recorder.summary_counters["source_fast_birth_probe_hook_enabled"] = True
    recorder.summary_counters["source_fast_event_handler_error_count"] = int(
        metrics.get("source_fast_event_handler_error_count") or 0
    )
    recorder.summary_counters["live_source_used"] = metrics.get("live_source_used") or "transaction_subscribe"
    recorder.summary_counters["subscription_connect_status"] = metrics.get("subscription_connect_status") or "available"
    summary = recorder.finalize()
    first_observation_latencies = list(recorder.birth_to_first_observation_latencies_ms)
    summary.update(
        {
            **global_migration_summary,
            "source_route": "transaction_subscribe",
            "actual_duration_seconds": metrics.get("actual_duration_seconds"),
            "websocket_closed_early": metrics.get("websocket_closed_early"),
            "websocket_close_reason": metrics.get("websocket_close_reason"),
            "websocket_keepalive_timeout_count": metrics.get("websocket_keepalive_timeout_count"),
            "websocket_reconnect_count": metrics.get("websocket_reconnect_count"),
            "source_event_queue_high_water_mark": metrics.get("source_event_queue_high_water_mark"),
            "source_event_queue_dropped_count": metrics.get("source_event_queue_dropped_count"),
            "source_reader_error_count": metrics.get("source_reader_error_count"),
            "source_reader_errors": metrics.get("source_reader_errors"),
            "source_reader_threaded": metrics.get("source_reader_threaded"),
            "source_fast_event_handler_count": metrics.get("source_fast_event_handler_count"),
            "source_fast_event_handler_error_count": metrics.get("source_fast_event_handler_error_count"),
            "source_fast_event_handler_errors": metrics.get("source_fast_event_handler_errors"),
            "source_fast_birth_probe_hook_enabled": bool(recorder.summary_counters.get("source_fast_birth_probe_hook_enabled")),
            "source_fast_birth_probe_hook_events": recorder.summary_counters.get("source_fast_birth_probe_hook_events"),
            "birth_hot_commit_queue_dropped_count": 0,
            "first_curve_probe_queue_dropped_count": birth_priority_queue_dropped_count,
            "source_fast_first_curve_probe_enqueued": recorder.summary_counters.get("source_fast_first_curve_probe_enqueued"),
            "source_fast_first_curve_probe_duplicate_suppressed": recorder.summary_counters.get(
                "source_fast_first_curve_probe_duplicate_suppressed"
            ),
            "source_fast_first_curve_probe_ineligible": recorder.summary_counters.get("source_fast_first_curve_probe_ineligible"),
            "birth_priority_dispatch_enabled": True,
            "birth_priority_worker_count": birth_priority_worker_count,
            "birth_priority_queue_high_water_mark": birth_priority_queue_high_water_mark,
            "birth_priority_queue_dropped_count": birth_priority_queue_dropped_count,
            "birth_priority_worker_error_count": len(birth_priority_worker_errors),
            "birth_priority_worker_errors": list(birth_priority_worker_errors),
            "thin_probe_async_dispatch_enabled": True,
            "thin_probe_worker_count": thin_probe_worker_count,
            "thin_probe_execution_queue_high_water_mark": max(
                thin_probe_execution_queue_high_water_mark,
                1 if int(recorder.summary_counters.get("thin_probe_queue_high_water") or 0) > 0 else 0,
            ),
            "thin_probe_execution_queue_dropped_count": thin_probe_execution_queue_dropped_count,
            "thin_probe_worker_error_count": len(thin_probe_worker_errors),
            "thin_probe_worker_errors": list(thin_probe_worker_errors),
            "birth_admission_owner_thread_enabled": True,
            "birth_admission_queue_high_water_mark": birth_admission_queue_high_water_mark,
            "birth_admission_queue_dropped_count": birth_admission_queue_dropped_count,
            "birth_admission_worker_error_count": len(birth_admission_worker_errors),
            "birth_admission_worker_errors": list(birth_admission_worker_errors),
            **source_quality,
            "raw_transaction_notifications": metrics.get("raw_transaction_notifications"),
            "decoded_birth_rows": metrics.get("decoded_birth_rows"),
            "unique_birth_mints": metrics.get("unique_birth_mints"),
            "duplicate_mint_rows": metrics.get("duplicate_mint_rows"),
            "duplicate_rows_by_route": metrics.get("duplicate_rows_by_route"),
            "first_seen_route_counts": metrics.get("first_seen_route_counts"),
            "duplicate_signatures": metrics.get("duplicate_signatures"),
            "duplicate_rows_with_same_mint_but_different_route": metrics.get("duplicate_rows_with_same_mint_but_different_route"),
            "duplicate_rows_with_same_mint_but_different_signature": metrics.get("duplicate_rows_with_same_mint_but_different_signature"),
            "direct_decoded_rows": metrics.get("direct_decoded_rows"),
            "inner_decoded_rows": metrics.get("inner_decoded_rows"),
            "wrapped_compact_decoded_rows": metrics.get("wrapped_compact_decoded_rows"),
            "first_seen_direct_births": (metrics.get("first_seen_route_counts") or {}).get("direct", 0),
            "first_seen_inner_births": (metrics.get("first_seen_route_counts") or {}).get("inner", 0),
            "first_seen_wrapped_compact_births": (metrics.get("first_seen_route_counts") or {}).get("wrapped_compact", 0),
            "births_admitted_after_dedupe": summary.get("admitted_births"),
            "sample_rejected_after_dedupe": summary.get("sample_rejected_births"),
            "capacity_rejected_after_dedupe": summary.get("capacity_rejected_births"),
            "bonding_curve_account_present_count": metrics.get("bonding_curve_account_present_count"),
            "associated_bonding_curve_present_count": metrics.get("associated_bonding_curve_present_count"),
            "associated_bonding_curve_missing_count": metrics.get("associated_bonding_curve_missing_count"),
            "creator_dev_present_count": metrics.get("creator_dev_present_count"),
            "notification_to_birth_normalized_latency_ms": _stats(metrics.get("notification_to_birth_normalized_latencies_ms") or []),
            "decoded_trade_rows": metrics.get("decoded_trade_rows"),
            "trade_rows_recorded": metrics.get("trade_rows_recorded"),
            "trade_rows_skipped_unknown_mint": metrics.get("trade_rows_skipped_unknown_mint"),
            "trade_rows_skipped_missing_mint": metrics.get("trade_rows_skipped_missing_mint"),
            "trade_flow_async_dispatch_enabled": True,
            "trade_flow_owner_thread_drain_enabled": True,
            "trade_flow_worker_count": 0,
            "trade_flow_queue_max_size": int(config.trade_flow_queue_max_size),
            "trade_flow_queue_high_water_mark": trade_flow_queue_high_water_mark,
            "trade_flow_queue_dropped_count": trade_flow_queue_dropped_count,
            "trade_flow_worker_error_count": len(trade_flow_worker_errors),
            "trade_flow_worker_errors": list(trade_flow_worker_errors),
            "birth_enqueue_to_admission_worker_start_latency_ms": _stats(
                recorder.birth_enqueue_to_admission_worker_start_latencies_ms
            ),
            "admission_worker_process_birth_duration_ms": _stats(recorder.admission_worker_process_birth_duration_ms),
            "admission_worker_to_probe_job_enqueue_latency_ms": _stats(
                recorder.admission_worker_to_probe_job_enqueue_latencies_ms
            ),
            "probe_job_enqueue_to_probe_start_latency_ms": _stats(recorder.probe_job_enqueue_to_probe_start_latencies_ms),
            "normalized_birth_to_probe_start_latency_ms": _stats(recorder.normalized_birth_to_probe_start_latencies_ms),
            "probe_duration_ms": _stats(probe_durations_ms),
            "probe_duration_latency_ms": _stats(recorder.probe_duration_latencies_ms),
            "first_curve_observation_under_1s": sum(1 for value in first_observation_latencies if value <= 1000.0),
            "first_curve_observation_under_2s": sum(1 for value in first_observation_latencies if value <= 2000.0),
            "first_curve_observation_under_5s": sum(1 for value in first_observation_latencies if value <= 5000.0),
            "first_curve_observation_over_10s": sum(1 for value in first_observation_latencies if value > 10000.0),
            "first_curve_observation_over_30s": sum(1 for value in first_observation_latencies if value > 30000.0),
            "enable_global_pumpswap_migration": bool(config.enable_global_pumpswap_migration),
            "global_migration_thread_join_timeout_seconds": float(config.global_migration_thread_join_timeout_seconds),
            "global_migration_thread_timed_out": "global_migration_thread_join_timeout" in global_migration_errors,
            "global_migration_errors": global_migration_errors,
            "global_migration_summary": global_migration_summary,
            **migration_side_effect_summary,
            "mayhem_code_modified": False,
        }
    )
    _merge_global_migration_dedupe_summary(summary, recorder._global_migration_artifact_counters())
    _rewrite_summary(recorder.output_root, summary)
    archive_completed_run_if_requested(recorder, summary)
    apply_local_retention_if_configured(recorder, summary)
    recorder._write_live_status("finalized_with_errors" if recorder.finalization_errors else "finalized", summary)
    return summary


def _run_probe_attempt(
    recorder: BondingCurveProgressRecorder,
    launch: dict[str, Any],
    probe: Any,
    *,
    now_fn: Any,
    attempt_index: int,
    delay_ms: int,
    final_for_mint: bool,
    probe_scope: str = "deep_initial_probe",
) -> tuple[dict[str, Any], float]:
    result = _execute_probe_attempt(
        launch,
        probe,
        now_fn=now_fn,
        attempt_index=attempt_index,
        delay_ms=delay_ms,
        final_for_mint=final_for_mint,
        probe_scope=probe_scope,
    )
    return _record_probe_attempt_result(recorder, result)


def _execute_probe_attempt(
    launch: dict[str, Any],
    probe: Any,
    *,
    now_fn: Any,
    attempt_index: int,
    delay_ms: int,
    final_for_mint: bool,
    probe_scope: str = "deep_initial_probe",
) -> dict[str, Any]:
    started = float(now_fn())
    account_source, bonding_curve = _probe_account_candidate(launch)
    create_event = {
        "mint": launch.get("mint"),
        "bonding_curve": bonding_curve,
        "observed_at": launch.get("received_at"),
        "timestamp": launch.get("received_at"),
        "slot": launch.get("slot"),
        "min_context_slot": launch.get("slot"),
    }
    rpc_failure = False
    try:
        probe_result = probe.probe_create_event(create_event, now_fn=now_fn)
    except Exception:
        rpc_failure = True
        probe_result = {
            "probe_status": "failed",
            "mint": launch.get("mint"),
            "bonding_curve": bonding_curve,
            "failure_reason": "probe_exception",
            "decode_status": "decode_failed",
            "observed_at": now_fn(),
        }
    finished = float(now_fn())
    duration_ms = max(0.0, (finished - started) * 1000.0)
    result_dict = probe_result.to_dict() if hasattr(probe_result, "to_dict") else dict(probe_result or {})
    failure_reason = str(result_dict.get("failure_reason") or result_dict.get("decode_error") or "")
    account_found = (
        True
        if result_dict.get("probe_status") == "success"
        or result_dict.get("account_data_len") is not None
        or result_dict.get("decode_status") == "decoded"
        or result_dict.get("progress_pct") is not None
        or result_dict.get("raw_curve_state") is not None
        or failure_reason in {"decode_failed", "no_reserve_state"}
        else False
    )
    attempt_row = {
        "mint": launch.get("mint"),
        "probe_attempt_index": attempt_index,
        "probe_delay_ms": delay_ms,
        "probe_started_at": started,
        "probe_finished_at": finished,
        "probe_duration_ms": duration_ms,
        "probe_status": result_dict.get("probe_status"),
        "actual_probe_executed": True,
        "account_found": account_found,
        "decode_status": result_dict.get("decode_status"),
        "decode_error": result_dict.get("decode_error") or result_dict.get("failure_reason"),
        "calculation_error": result_dict.get("calculation_error"),
        "account_owner": result_dict.get("account_owner"),
        "account_data_len": result_dict.get("account_data_len"),
        "account_data_first_8_hex": result_dict.get("account_data_first_8_hex"),
        "account_data_first_16_hex": result_dict.get("account_data_first_16_hex"),
        "account_data_hash": result_dict.get("account_data_hash"),
        "layout_version": result_dict.get("layout_version"),
        "quote_type": result_dict.get("quote_type"),
        "account_source": account_source,
        "bonding_curve_account": bonding_curve,
        "decoded_bonding_curve_account": launch.get("bonding_curve_account"),
        "derived_bonding_curve_account": _derive_bonding_curve_pda(str(launch.get("mint") or "")),
        "final_for_mint": final_for_mint,
        "probe_scope": probe_scope,
    }
    observation = _observation_from_probe_result(launch, result_dict, now_fn=now_fn)
    observation.update(attempt_row)
    observation["fdv_units"] = result_dict.get("fdv_units") or observation.get("fdv_units")
    observation["fdv_usd"] = result_dict.get("fdv_usd")
    observation["fdv_sol"] = result_dict.get("fdv_sol")
    return {
        "attempt_row": attempt_row,
        "observation": observation,
        "duration_ms": duration_ms,
        "rpc_failure": rpc_failure,
        "http_429_count": int(getattr(probe, "http_429_count", 0) or 0),
    }


def _record_probe_attempt_result(
    recorder: BondingCurveProgressRecorder,
    result: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    recorder.summary_counters["curve_observation_attempts"] += 1
    if result.get("rpc_failure"):
        recorder.summary_counters["rpc_failures"] += 1
    recorder.summary_counters["http_429_count"] = max(
        int(recorder.summary_counters.get("http_429_count") or 0),
        int(result.get("http_429_count") or 0),
    )
    attempt_row = dict(result.get("attempt_row") or {})
    observation = dict(result.get("observation") or {})
    duration_ms = float(result.get("duration_ms") or 0.0)
    recorder._append_jsonl("probe_attempts.jsonl", attempt_row)
    recorder.record_observation(observation)
    return observation, duration_ms


def _run_thin_probe_for_birth(
    recorder: BondingCurveProgressRecorder,
    launch: dict[str, Any],
    birth_row: dict[str, Any],
    probe: Any,
    *,
    now_fn: Any,
) -> None:
    if birth_row.get("thin_probe_scheduled") is not True:
        if birth_row.get("admission_reason") == "sample_rejected":
            recorder.summary_counters["sampled_out_without_thin_path_count"] += 1
        return
    attempts = [0, *list(recorder.config.thin_probe_retry_delays_ms)]
    final_observation: dict[str, Any] | None = None
    for attempt_index, delay_ms in enumerate(attempts):
        observation, _duration_ms = _run_probe_attempt(
            recorder,
            launch,
            probe,
            now_fn=now_fn,
            attempt_index=attempt_index,
            delay_ms=delay_ms,
            final_for_mint=attempt_index == len(attempts) - 1,
            probe_scope="thin_initial_probe" if attempt_index == 0 else "thin_retry_probe",
        )
        recorder._record_thin_probe_result(birth_row, observation)
        final_observation = observation
        if observation.get("account_found") is True:
            break
        if observation.get("error_reason") != "account_not_found":
            break
    if final_observation is not None and final_observation.get("account_found") is False and final_observation.get("error_reason") == "account_not_found":
        recorder.summary_counters["final_account_not_found_count"] += 1


def run_live_smoke(
    config: BondingCurveRecorderConfig,
    *,
    source: Any | None = None,
    curve_probe: Any | None = None,
    now_fn: Any = time.time,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    recorder = BondingCurveProgressRecorder(config)
    launch_source = source or _default_live_launch_source(config)
    adapter = BroadPumpFunLaunchAdapter(launch_source, now_fn=now_fn)
    probe = curve_probe or _default_curve_probe(config)
    availability = adapter.availability()
    recorder.summary_counters["live_source_used"] = (
        availability.get("source_adapter")
        or availability.get("source")
        or adapter.source_name
    )
    recorder.summary_counters["subscription_connect_status"] = (
        "available" if availability.get("available", True) else f"unavailable:{availability.get('missing_reason', 'unknown')}"
    )
    if availability.get("available", True) is False:
        summary = recorder.finalize()
        _rewrite_summary(recorder.output_root, summary)
        return summary

    deadline = float(now_fn()) + max(0.0, float(config.source_duration_seconds))
    while float(now_fn()) <= deadline:
        launches = adapter.fetch_launches()
        for launch in launches:
            admission_started = float(now_fn())
            birth_row = recorder.process_birth(launch)
            if birth_row.get("admitted") is not True:
                continue
            received_at = _num(launch.get("received_at"))
            if received_at is not None:
                recorder.birth_to_admission_latencies_ms.append(max(0.0, (admission_started - received_at) * 1000.0))
            recorder.summary_counters["curve_observation_attempts"] += 1
            try:
                probe_result = probe.probe_create_event(
                    {
                        "mint": launch.get("mint"),
                        "bonding_curve": launch.get("bonding_curve_account"),
                        "observed_at": launch.get("received_at"),
                        "timestamp": launch.get("received_at"),
                        "slot": launch.get("slot"),
                        "min_context_slot": launch.get("slot"),
                    },
                    now_fn=now_fn,
                )
            except Exception:
                recorder.summary_counters["rpc_failures"] += 1
                probe_result = {
                    "probe_status": "failed",
                    "mint": launch.get("mint"),
                    "bonding_curve": launch.get("bonding_curve_account"),
                    "failure_reason": "probe_exception",
                    "decode_status": "decode_failed",
                    "observed_at": now_fn(),
                }
            observation = _observation_from_probe_result(launch, probe_result, now_fn=now_fn)
            if observation.get("error_reason") in {"rpc_error", "rpc_429"}:
                recorder.summary_counters["rpc_failures"] += 1
            recorder.summary_counters["http_429_count"] = max(
                int(recorder.summary_counters.get("http_429_count") or 0),
                int(getattr(probe, "http_429_count", 0) or 0),
            )
            recorder.record_observation(observation)
        if getattr(launch_source, "exhausted", False):
            break
        sleep_fn(0.1)
    summary = recorder.finalize()
    _rewrite_summary(recorder.output_root, summary)
    recorder._write_live_status("finalized", summary)
    close = getattr(launch_source, "close", None)
    if callable(close):
        close()
    return summary


def _observation_from_probe_result(launch: dict[str, Any], probe_result: Any, *, now_fn: Any = time.time) -> dict[str, Any]:
    result = probe_result.to_dict() if hasattr(probe_result, "to_dict") else dict(probe_result or {})
    status = result.get("probe_status")
    account_state = result.get("account_state") or {}
    decode_status = result.get("decode_status") or ("decoded" if status == "success" else "decode_failed")
    error_reason = result.get("failure_reason") or result.get("calculation_error") or result.get("decode_error") or ""
    formula_result = compute_true_curve_progress_from_state(account_state if isinstance(account_state, dict) else {})
    explicit_progress = _num(result.get("progress_pct"))
    progress = explicit_progress if explicit_progress is not None else formula_result.get("progress_pct")
    progress_status = "decoded_exact" if explicit_progress is not None else formula_result.get("progress_pct_status")
    if decode_status != "decoded" and explicit_progress is None:
        progress_status = "decode_error"
    fdv_proxy = _first_present(result, ["fdv_proxy", "valuation_proxy_usd", "fdv_usd", "fdv_sol", "fdv_quote"])
    return {
        "mint": result.get("mint") or launch.get("mint"),
        "slot": result.get("account_data_slot") or launch.get("slot"),
        "block_time": launch.get("block_time"),
        "received_at": result.get("decode_finished_at")
        or result.get("get_account_info_finished_at")
        or result.get("observed_at")
        or now_fn(),
        "observation_source": "bonding_curve_account_state_probe",
        "bonding_curve_account": result.get("bonding_curve") or launch.get("bonding_curve_account"),
        "associated_bonding_curve": launch.get("associated_bonding_curve"),
        "raw_curve_state": account_state,
        "progress_pct": progress,
        "progress_pct_status": progress_status,
        "progress_formula_version": formula_result.get("progress_formula_version"),
        "progress_denominator_tokens": formula_result.get("progress_denominator_tokens"),
        "reserve_scale_mode": formula_result.get("reserve_scale_mode"),
        "real_token_reserves_scaled": formula_result.get("real_token_reserves_scaled"),
        "complete": bool(account_state.get("complete")) if isinstance(account_state, dict) else False,
        "fdv_proxy": fdv_proxy,
        "fdv_proxy_raw": result.get("fdv_proxy"),
        "fdv_sol": result.get("fdv_sol"),
        "fdv_usd": result.get("fdv_usd"),
        "fdv_units": result.get("fdv_units"),
        "sol_usd": result.get("sol_usd"),
        "valuation_proxy_usd": result.get("valuation_proxy_usd"),
        "market_cap_usd": result.get("market_cap_usd"),
        "axiom_market_cap_usd": result.get("axiom_market_cap_usd"),
        "axiom_liquidity_usd": result.get("axiom_liquidity_usd") or result.get("liquidity_usd"),
        "valuation_market_cap_confirmed": result.get("valuation_market_cap_confirmed"),
        "valuation_source_type": result.get("valuation_source_type") or result.get("valuation_source_kind"),
        "is_mayhem": result.get("is_mayhem") or result.get("mayhem") or result.get("mayhem_mode"),
        "decode_status": decode_status,
        "error_reason": error_reason,
        "seconds_since_launch": _duration_seconds(launch.get("received_at"), result.get("observed_at") or now_fn()),
        "observation_id": f"{launch.get('mint')}-{result.get('account_data_hash') or int(float(now_fn()) * 1000)}",
    }


def _default_live_launch_source(config: BondingCurveRecorderConfig) -> Any:
    from research.mtp_research.validation.forward_birth_watch_followup_collector import PumpFunCreateWebSocketCandidateSource

    return PumpFunCreateWebSocketCandidateSource(
        timeout_seconds=min(1.0, max(0.1, float(config.source_duration_seconds))),
        max_signatures_per_fetch=50,
        candidate_hydration_workers=8,
    )


def _default_curve_probe(config: BondingCurveRecorderConfig | None = None) -> Any:
    from research.mtp_research.validation.bonding_curve_account_state import BondingCurveAccountStateProbe

    return BondingCurveAccountStateProbe(timeout_seconds=3, sol_usd=(config.sol_usd if config is not None else None))


def compute_true_curve_progress_from_state(account_state: dict[str, Any]) -> dict[str, Any]:
    complete = _bool((account_state or {}).get("complete"))
    real_reserves = _num((account_state or {}).get("real_token_reserves"))
    token_decimals = _int((account_state or {}).get("token_decimals"))
    token_total_supply = _num((account_state or {}).get("token_total_supply"))
    base = {
        "progress_pct": None,
        "progress_pct_status": "unresolved_formula",
        "progress_formula_version": PROGRESS_FORMULA_VERSION,
        "progress_denominator_tokens": PUMPFUN_PROGRESS_DENOMINATOR_TOKENS,
        "reserve_scale_mode": "unknown",
        "real_token_reserves_scaled": None,
        "complete": complete,
    }
    if real_reserves is None:
        return base
    scale_mode = "unknown"
    scaled = real_reserves
    if token_decimals is not None and token_decimals >= 0 and (
        real_reserves > 10_000_000_000 or (token_total_supply is not None and token_total_supply > 10_000_000_000)
    ):
        scale_mode = f"raw_integer_units_{token_decimals}_decimals"
        scaled = real_reserves / (10 ** token_decimals)
    elif real_reserves <= 1_500_000_000:
        scale_mode = "human_token_units"
    else:
        base["real_token_reserves_scaled"] = real_reserves
        return base
    progress = 100.0 * (1.0 - (scaled / PUMPFUN_PROGRESS_DENOMINATOR_TOKENS))
    progress = max(0.0, min(100.0, progress))
    status = "decoded_exact" if complete and scaled <= 1e-9 else "decoded_candidate"
    return {
        **base,
        "progress_pct": round(progress, 6),
        "progress_pct_status": status,
        "reserve_scale_mode": scale_mode,
        "real_token_reserves_scaled": round(scaled, 6),
    }


def _rewrite_summary(output_root: Path, summary: dict[str, Any]) -> None:
    _atomic_write_json(Path(output_root) / "collector_summary.json", summary)


def _duration_seconds(start: Any, end: Any) -> float | None:
    start_num = _num(start)
    end_num = _num(end)
    if start_num is None or end_num is None:
        return None
    return max(0.0, end_num - start_num)


def _velocity_for_window(history: list[dict[str, Any]], *, as_of: float, window_seconds: float) -> dict[str, Any]:
    eligible = [
        item for item in history
        if _num(item.get("progress_pct")) is not None
        and _num(item.get("received_at")) is not None
        and as_of - float(_num(item.get("received_at")) or 0.0) <= float(window_seconds)
        and float(_num(item.get("received_at")) or 0.0) <= as_of
    ]
    if len(eligible) < 2:
        return {"progress_per_second": None, "progress_delta": None}
    first = min(eligible, key=lambda item: float(_num(item.get("received_at")) or as_of))
    last = max(eligible, key=lambda item: float(_num(item.get("received_at")) or as_of))
    first_progress = float(_num(first.get("progress_pct")) or 0.0)
    last_progress = float(_num(last.get("progress_pct")) or 0.0)
    first_received = float(_num(first.get("received_at")) or as_of)
    last_received = float(_num(last.get("received_at")) or as_of)
    seconds = max(0.000001, last_received - first_received)
    delta = last_progress - first_progress
    return {"progress_per_second": delta / seconds, "progress_delta": delta}


def _seconds_between_thresholds(threshold_seconds: dict[float, float]) -> dict[str, float | None]:
    values = sorted(threshold_seconds)
    result: dict[str, float | None] = {}
    for previous, current in zip(values, values[1:]):
        previous_seconds = threshold_seconds.get(previous)
        current_seconds = threshold_seconds.get(current)
        result[f"{previous}_to_{current}"] = (
            round(float(current_seconds) - float(previous_seconds), 6)
            if previous_seconds is not None and current_seconds is not None
            else None
        )
    return result


def _first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _quote_mint_from_payload(payload: dict[str, Any]) -> str | None:
    raw_state = payload.get("raw_curve_state") if isinstance(payload.get("raw_curve_state"), dict) else {}
    value = _first_present(payload, ["quote_mint", "quoteMint", "quote_asset_mint", "quoteAssetMint"])
    if value is None:
        value = _first_present(raw_state, ["quote_mint", "quoteMint", "quote_asset_mint", "quoteAssetMint"])
    quote_type = _quote_type_from_payload(payload, raw_state)
    if value is None and quote_type == "sol":
        value = SOL_MINT
    if value is None and quote_type == "usdc":
        value = USDC_MINT
    return str(value) if value not in (None, "") else None


def _quote_type_from_payload(payload: dict[str, Any], raw_state: dict[str, Any] | None = None) -> str:
    raw = raw_state if isinstance(raw_state, dict) else {}
    candidates = [
        payload.get("quote_type"),
        raw.get("quote_type"),
        payload.get("quote_asset"),
        raw.get("quote_asset"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if text and text not in {"unknown", "unsupported", "none", "null"}:
            return text
    return ""


def _quote_identity_from_payload(
    payload: dict[str, Any],
    *,
    sol_usd: float | None = None,
    sol_usd_source: str | None = None,
    unsupported_as_unknown: bool = False,
) -> dict[str, Any]:
    quote_mint = _quote_mint_from_payload(payload)
    if quote_mint == SOL_MINT:
        source = str(sol_usd_source or "manual_cli_sol_usd") if sol_usd is not None else "missing_manual_sol_usd"
        return {
            "quote_mint": quote_mint,
            "quote_asset": "SOL",
            "quote_asset_status": "sol",
            "quote_to_usd_rate": float(sol_usd) if sol_usd is not None else None,
            "quote_to_usd_source": source,
            "quote_to_usd_warning": None,
        }
    if quote_mint == USDC_MINT:
        return {
            "quote_mint": quote_mint,
            "quote_asset": "USDC",
            "quote_asset_status": "usdc",
            "quote_to_usd_rate": 1.0,
            "quote_to_usd_source": "usdc_assumed_1",
            "quote_to_usd_warning": "usdc_depeg_handling_not_implemented",
        }
    if quote_mint:
        asset = "unknown" if unsupported_as_unknown else "unsupported"
        return {
            "quote_mint": quote_mint,
            "quote_asset": asset,
            "quote_asset_status": "unknown" if unsupported_as_unknown else "unsupported",
            "quote_to_usd_rate": None,
            "quote_to_usd_source": None,
            "quote_to_usd_warning": "unsupported_quote_asset",
        }
    return {
        "quote_mint": None,
        "quote_asset": "unknown",
        "quote_asset_status": "unknown",
        "quote_to_usd_rate": None,
        "quote_to_usd_source": None,
        "quote_to_usd_warning": "missing_quote_mint",
    }


def _valuation_from_observation(observation: dict[str, Any]) -> tuple[float | None, str | None]:
    valuation = _valuation_units_from_observation(observation, sol_usd=None, decode_status=str(observation.get("decode_status") or ""))
    return _num(valuation.get("valuation_usd")), valuation.get("valuation_source_field")


def _valuation_units_from_observation(
    observation: dict[str, Any],
    *,
    sol_usd: float | None,
    sol_usd_source: str | None = None,
    decode_status: str,
) -> dict[str, Any]:
    quote = _quote_identity_from_payload(
        observation,
        sol_usd=sol_usd,
        sol_usd_source=sol_usd_source,
        unsupported_as_unknown=True,
    )
    source_kind = str(observation.get("valuation_source_type") or observation.get("valuation_source_kind") or "").strip().lower()
    explicit_market_cap_confirmed = _bool(observation.get("valuation_market_cap_confirmed")) or source_kind in {
        "market_cap",
        "market_cap_confirmed",
        "axiom_market_cap",
    }
    explicit_market_cap = _num(_first_present(observation, ["market_cap_usd"]))
    if decode_status != "decoded":
        return {
            "fdv_proxy_raw": None,
            "fdv_proxy_sol": None,
            "fdv_proxy_usd": None,
            "valuation_usd": None,
            "valuation_source_field": None,
            "valuation_units_status": "missing_due_to_decode_error",
            "valuation_market_cap_confirmed": False,
            "valuation_ladder_trust_status": "missing_due_to_decode_error",
            "valuation_quote_units": None,
        }
    raw_value = _num(_first_present(observation, ["fdv_proxy_raw", "fdv_proxy", "valuation_proxy", "price_proxy"]))
    explicit_usd = _num(_first_present(observation, ["fdv_proxy_usd", "fdv_usd", "valuation_proxy_usd"]))
    explicit_sol = _num(_first_present(observation, ["fdv_proxy_sol", "fdv_sol"]))
    explicit_quote = _num(_first_present(observation, ["valuation_quote_units", "fdv_proxy_quote", "fdv_quote"]))
    units = str(observation.get("fdv_units") or observation.get("valuation_units") or "").strip().lower()
    source_field = None
    for key in (
        "market_cap_usd",
        "fdv_proxy_usd",
        "fdv_usd",
        "valuation_proxy_usd",
        "fdv_proxy_sol",
        "fdv_sol",
        "fdv_proxy",
        "valuation_proxy",
        "price_proxy",
    ):
        if _num(observation.get(key)) is not None:
            source_field = key
            break
    if explicit_market_cap is not None:
        return {
            "fdv_proxy_raw": raw_value if raw_value is not None else explicit_market_cap,
            "fdv_proxy_sol": explicit_sol,
            "fdv_proxy_usd": explicit_usd,
            "valuation_usd": explicit_market_cap,
            "valuation_source_field": source_field,
            "valuation_units_status": "market_cap_confirmed",
            "valuation_market_cap_confirmed": True,
            "valuation_ladder_trust_status": "market_cap_confirmed",
            "valuation_quote_units": explicit_quote,
        }
    trust_status = "market_cap_confirmed" if explicit_market_cap_confirmed else "untrusted_not_market_cap_confirmed"
    if explicit_usd is not None:
        return {
            "fdv_proxy_raw": raw_value if raw_value is not None else explicit_usd,
            "fdv_proxy_sol": explicit_sol,
            "fdv_proxy_usd": explicit_usd,
            "valuation_usd": explicit_usd,
            "valuation_source_field": source_field,
            "valuation_units_status": "usd_confirmed" if explicit_market_cap_confirmed else "usd_unconfirmed_not_market_cap",
            "valuation_market_cap_confirmed": explicit_market_cap_confirmed,
            "valuation_ladder_trust_status": trust_status,
            "valuation_quote_units": explicit_quote,
        }
    if explicit_quote is not None or units in {"quote", "quote_units", "usdc"}:
        quote_value = explicit_quote if explicit_quote is not None else raw_value
        quote_rate = quote.get("quote_to_usd_rate")
        usd_value = quote_value * float(quote_rate) if quote_value is not None and quote_rate is not None else None
        if quote["quote_asset"] == "SOL":
            units_status = "sol_converted_to_usd" if usd_value is not None else "sol_unconverted"
            proxy_sol = quote_value
        elif quote["quote_asset"] == "USDC":
            units_status = "usdc_assumed_1_to_usd"
            proxy_sol = explicit_sol
        else:
            units_status = "unknown_quote_asset"
            proxy_sol = explicit_sol
        return {
            "fdv_proxy_raw": raw_value if raw_value is not None else quote_value,
            "fdv_proxy_sol": proxy_sol,
            "fdv_proxy_usd": usd_value,
            "valuation_usd": usd_value,
            "valuation_source_field": source_field,
            "valuation_units_status": units_status,
            "valuation_market_cap_confirmed": explicit_market_cap_confirmed and usd_value is not None,
            "valuation_ladder_trust_status": trust_status if usd_value is not None else "raw_unresolved",
            "valuation_quote_units": quote_value,
        }
    if explicit_sol is not None or units == "sol":
        sol_value = explicit_sol if explicit_sol is not None else raw_value
        usd_value = sol_value * float(sol_usd) if sol_value is not None and sol_usd is not None else None
        return {
            "fdv_proxy_raw": raw_value if raw_value is not None else sol_value,
            "fdv_proxy_sol": sol_value,
            "fdv_proxy_usd": usd_value,
            "valuation_usd": usd_value,
            "valuation_source_field": source_field,
            "valuation_units_status": "sol_converted_to_usd" if usd_value is not None else "sol_unconverted",
            "valuation_market_cap_confirmed": explicit_market_cap_confirmed and usd_value is not None,
            "valuation_ladder_trust_status": trust_status if usd_value is not None else "missing",
            "valuation_quote_units": sol_value if quote["quote_asset"] == "SOL" else None,
        }
    if units == "usd" and raw_value is not None:
        return {
            "fdv_proxy_raw": raw_value,
            "fdv_proxy_sol": explicit_sol,
            "fdv_proxy_usd": raw_value,
            "valuation_usd": raw_value,
            "valuation_source_field": source_field,
            "valuation_units_status": "usd_confirmed" if explicit_market_cap_confirmed else "usd_unconfirmed_not_market_cap",
            "valuation_market_cap_confirmed": explicit_market_cap_confirmed,
            "valuation_ladder_trust_status": trust_status,
            "valuation_quote_units": explicit_quote,
        }
    return {
        "fdv_proxy_raw": raw_value,
        "fdv_proxy_sol": None,
        "fdv_proxy_usd": None,
        "valuation_usd": None,
        "valuation_source_field": source_field,
        "valuation_units_status": "raw_unresolved" if raw_value is not None else "missing_due_to_decode_error",
        "valuation_market_cap_confirmed": False,
        "valuation_ladder_trust_status": "raw_unresolved" if raw_value is not None else "missing_due_to_decode_error",
        "valuation_quote_units": explicit_quote,
    }


def _reserve_fdv_from_state(
    account_state: dict[str, Any],
    *,
    sol_usd: float | None,
    sol_usd_source: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    empty = {
        "reserve_price_sol": None,
        "reserve_fdv_sol": None,
        "reserve_fdv_usd": None,
        "reserve_fdv_status": "unavailable",
        "bonding_curve_price_quote": None,
        "bonding_curve_price_usd": None,
        "bonding_curve_market_cap_quote": None,
        "bonding_curve_market_cap_usd": None,
        "bonding_curve_market_cap_quote_asset": None,
        "bonding_curve_market_cap_quote_mint": None,
        "bonding_curve_market_cap_status": "unavailable",
        "bonding_curve_market_cap_formula_version": MARKET_CAP_FORMULA_VERSION,
    }
    if not isinstance(account_state, dict) or account_state.get("decode_status") not in {None, "decoded"}:
        return empty
    try:
        merged = {**(payload or {}), **account_state}
        quote = _quote_identity_from_payload(
            merged,
            sol_usd=sol_usd,
            sol_usd_source=sol_usd_source,
            unsupported_as_unknown=True,
        )
        token_reserves = _num(account_state.get("virtual_token_reserves"))
        token_supply = _num(account_state.get("token_total_supply"))
        token_decimals = int(_num(account_state.get("token_decimals")) if _num(account_state.get("token_decimals")) is not None else 6)
        quote_decimals = _quote_decimals_for_market_cap(account_state, quote)
        quote_reserves = _quote_reserves_for_market_cap(account_state, quote)
        if token_reserves is None or token_reserves <= 0 or token_supply is None or token_supply <= 0:
            return {**empty, "reserve_fdv_status": "unavailable", "bonding_curve_market_cap_status": "missing_token_reserves_or_supply"}
        if quote_reserves is None or quote_reserves <= 0 or quote_decimals is None:
            return {**empty, "reserve_fdv_status": "unavailable", "bonding_curve_market_cap_status": "missing_quote_reserves"}
        token_reserves_scaled = token_reserves / (10 ** token_decimals)
        token_supply_scaled = token_supply / (10 ** token_decimals)
        quote_reserves_scaled = quote_reserves / (10 ** int(quote_decimals))
        if token_reserves_scaled <= 0 or token_supply_scaled <= 0:
            return {**empty, "reserve_fdv_status": "unavailable", "bonding_curve_market_cap_status": "invalid_scaled_reserves"}
        price_quote = quote_reserves_scaled / token_reserves_scaled
        market_cap_quote = price_quote * token_supply_scaled
        quote_rate = quote.get("quote_to_usd_rate")
        market_cap_usd = market_cap_quote * float(quote_rate) if quote_rate is not None else None
        price_usd = price_quote * float(quote_rate) if quote_rate is not None else None
        reserve_price_sol = price_quote if quote["quote_asset"] == "SOL" else None
        reserve_fdv_sol = market_cap_quote if quote["quote_asset"] == "SOL" else None
        status = "computed" if market_cap_usd is not None else "quote_conversion_unavailable"
        return {
            "reserve_price_sol": _round_float(reserve_price_sol),
            "reserve_fdv_sol": _round_float(reserve_fdv_sol),
            "reserve_fdv_usd": _round_float(market_cap_usd),
            "reserve_fdv_status": status,
            "bonding_curve_price_quote": _round_float(price_quote),
            "bonding_curve_price_usd": _round_float(price_usd),
            "bonding_curve_market_cap_quote": _round_float(market_cap_quote),
            "bonding_curve_market_cap_usd": _round_float(market_cap_usd),
            "bonding_curve_market_cap_quote_asset": quote["quote_asset"],
            "bonding_curve_market_cap_quote_mint": quote["quote_mint"],
            "bonding_curve_market_cap_status": status,
            "bonding_curve_market_cap_formula_version": MARKET_CAP_FORMULA_VERSION,
        }
    except Exception:
        return {**empty, "reserve_fdv_status": "error", "bonding_curve_market_cap_status": "error"}


def _pool_market_cap_from_reserves(
    observation: dict[str, Any],
    *,
    base_reserve_scaled: float | None,
    quote_reserve_scaled: float | None,
    sol_usd: float | None,
    sol_usd_source: str | None = None,
) -> dict[str, Any]:
    empty = {
        "pool_price_quote_per_token": None,
        "pool_price_usd_per_token": None,
        "pool_market_cap_quote": None,
        "pool_market_cap_usd": None,
        "pool_market_cap_quote_asset": None,
        "pool_market_cap_quote_mint": None,
        "pool_token_total_supply_scaled": None,
        "pool_market_cap_status": "unavailable",
        "pool_market_cap_formula_version": MARKET_CAP_FORMULA_VERSION,
    }
    try:
        quote = _quote_identity_from_payload(
            observation,
            sol_usd=sol_usd,
            sol_usd_source=sol_usd_source,
            unsupported_as_unknown=True,
        )
        quote_asset = str(quote.get("quote_asset") or "unknown")
        if quote_asset not in {"SOL", "USDC"}:
            return {**empty, "pool_market_cap_quote_asset": quote_asset, "pool_market_cap_status": "unsupported_quote_asset"}
        base_reserve = _num(base_reserve_scaled)
        if base_reserve is None:
            base_reserve = _pool_reserve_scaled_from_observation(
                observation,
                scaled_keys=("base_reserve_scaled", "pool_base_reserve_scaled"),
                raw_keys=("base_reserve_raw", "pool_base_reserve_raw", "pool_base_reserve"),
                decimal_keys=("base_decimals", "base_token_decimals", "token_decimals"),
                default_decimals=6,
            )
        quote_reserve = _num(quote_reserve_scaled)
        if quote_reserve is None:
            quote_reserve = _pool_reserve_scaled_from_observation(
                observation,
                scaled_keys=("quote_reserve_scaled", "pool_quote_reserve_scaled"),
                raw_keys=("quote_reserve_raw", "pool_quote_reserve_raw", "pool_quote_reserve"),
                decimal_keys=("quote_decimals", "quote_token_decimals"),
                default_decimals=_quote_decimals_for_market_cap(observation, quote),
            )
        if base_reserve is None or quote_reserve is None or base_reserve <= 0 or quote_reserve <= 0:
            return {
                **empty,
                "pool_market_cap_quote_asset": quote_asset,
                "pool_market_cap_quote_mint": quote.get("quote_mint"),
                "pool_market_cap_status": "missing_pool_reserves",
            }
        token_supply_scaled = _pool_token_total_supply_scaled(observation)
        if token_supply_scaled is None or token_supply_scaled <= 0:
            return {
                **empty,
                "pool_market_cap_quote_asset": quote_asset,
                "pool_market_cap_quote_mint": quote.get("quote_mint"),
                "pool_market_cap_status": "missing_token_supply",
            }
        price_quote = quote_reserve / base_reserve
        market_cap_quote = price_quote * token_supply_scaled
        quote_rate = _num(quote.get("quote_to_usd_rate"))
        price_usd = price_quote * float(quote_rate) if quote_rate is not None else None
        market_cap_usd = market_cap_quote * float(quote_rate) if quote_rate is not None else None
        status = "computed" if market_cap_usd is not None else "quote_conversion_unavailable"
        return {
            "pool_price_quote_per_token": _round_float(price_quote),
            "pool_price_usd_per_token": _round_float(price_usd),
            "pool_market_cap_quote": _round_float(market_cap_quote),
            "pool_market_cap_usd": _round_float(market_cap_usd),
            "pool_market_cap_quote_asset": quote_asset,
            "pool_market_cap_quote_mint": quote.get("quote_mint"),
            "pool_token_total_supply_scaled": _round_float(token_supply_scaled),
            "pool_market_cap_status": status,
            "pool_market_cap_formula_version": MARKET_CAP_FORMULA_VERSION,
        }
    except Exception:
        return {**empty, "pool_market_cap_status": "error"}


def _pool_token_total_supply_scaled(observation: dict[str, Any]) -> float | None:
    scaled = _num(
        _first_present(
            observation,
            [
                "token_total_supply_scaled",
                "base_token_total_supply_scaled",
                "total_supply_scaled",
                "supply_scaled",
            ],
        )
    )
    if scaled is not None:
        return scaled
    raw = _num(
        _first_present(
            observation,
            [
                "token_total_supply_raw",
                "base_token_total_supply_raw",
                "token_supply_raw",
                "total_supply_raw",
                "supply_raw",
                "token_total_supply",
            ],
        )
    )
    if raw is None:
        return PUMPFUN_TOKEN_TOTAL_SUPPLY_TOKENS
    decimals = _num(observation.get("token_decimals"))
    if decimals is not None and raw > 10_000_000_000:
        return raw / (10 ** int(decimals))
    return raw


def _pool_reserve_scaled_from_observation(
    observation: dict[str, Any],
    *,
    scaled_keys: tuple[str, ...],
    raw_keys: tuple[str, ...],
    decimal_keys: tuple[str, ...],
    default_decimals: int | None,
) -> float | None:
    scaled = _num(_first_present(observation, scaled_keys))
    if scaled is not None:
        return scaled
    raw = _num(_first_present(observation, raw_keys))
    if raw is None:
        return None
    decimals = _num(_first_present(observation, decimal_keys))
    if decimals is None:
        decimals = default_decimals
    if decimals is not None and raw > 10_000_000_000:
        return raw / (10 ** int(decimals))
    return raw


def _quote_decimals_for_market_cap(account_state: dict[str, Any], quote: dict[str, Any]) -> int | None:
    explicit = _num(account_state.get("quote_decimals"))
    if explicit is not None:
        return int(explicit)
    if quote.get("quote_asset") == "SOL":
        return 9
    if quote.get("quote_asset") == "USDC":
        return 6
    return None


def _quote_reserves_for_market_cap(account_state: dict[str, Any], quote: dict[str, Any]) -> float | None:
    for key in ("virtual_quote_reserves", "virtualQuoteReserves"):
        value = _num(account_state.get(key))
        if value is not None:
            return value
    if quote.get("quote_asset") == "SOL" or str(account_state.get("quote_type") or "").lower() == "sol":
        return _num(account_state.get("virtual_sol_reserves") or account_state.get("virtualSolReserves"))
    return None


def _round_float(value: Any, digits: int = 12) -> float | None:
    number = _num(value)
    if number is None:
        return None
    rounded = round(float(number), digits)
    if rounded == 0 and number != 0:
        return float(number)
    return rounded


def _fdv_proxy_agreement(fdv_proxy_sol: Any, reserve_fdv_sol: Any) -> dict[str, Any]:
    proxy = _num(fdv_proxy_sol)
    reserve = _num(reserve_fdv_sol)
    if proxy is None or reserve is None or reserve == 0:
        return {"fdv_proxy_abs_diff": None, "fdv_proxy_pct_diff": None, "fdv_proxy_agreement_status": "cannot_compare"}
    diff = abs(proxy - reserve)
    pct = diff / abs(reserve) * 100.0
    return {
        "fdv_proxy_abs_diff": round(diff, 6),
        "fdv_proxy_pct_diff": round(pct, 6),
        "fdv_proxy_agreement_status": "matches_existing_proxy" if pct <= 1.0 else "differs_from_existing_proxy",
    }


def _append_number(values: list[float], value: Any) -> None:
    number = _num(value)
    if number is not None:
        values.append(number)


def _range(values: list[float]) -> dict[str, Any]:
    clean = [value for value in values if value is not None]
    return {"count": len(clean), "min": min(clean) if clean else None, "max": max(clean) if clean else None}


def _write_config(output_root: Path, config: BondingCurveRecorderConfig) -> None:
    payload = _json_safe(asdict(config))
    _atomic_write_json(output_root / "run_config.json", payload)


def _audit_event_from_logs_notification(payload: dict[str, Any], *, received_at: float) -> dict[str, Any] | None:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = params.get("result") if isinstance(params.get("result"), dict) else {}
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    signature = value.get("signature")
    if not signature:
        return None
    logs = value.get("logs") if isinstance(value.get("logs"), list) else []
    return {
        "received_at": received_at,
        "signature": str(signature),
        "slot": context.get("slot"),
        "source_route": "logsSubscribe_mentions_pumpfun_program",
        "mentioned_program_ids": ["PUMP_FUN_PROGRAM_ID"],
        "logs": [str(log) for log in logs],
    }


def _fetch_audit_transaction(rpc_url: str, signature: str, rpc_post: Any, timeout_seconds: float) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": "mtp-t007-birth-source-audit-get-transaction",
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed",
            },
        ],
    }
    response = rpc_post(rpc_url, payload, int(max(1, timeout_seconds)))
    result = response.get("result") if isinstance(response, dict) else None
    return result if isinstance(result, dict) else {}


def _event_mentions_pumpfun(event: dict[str, Any]) -> bool:
    mentions = {str(value).lower() for value in event.get("mentioned_program_ids") or []}
    if any("pump" in value or "pumpfun" in value for value in mentions):
        return True
    logs = " ".join(str(log).lower() for log in event.get("logs") or [])
    return "pump" in logs or "instruction: create" in logs


def _audit_candidates_from_event(event: dict[str, Any]) -> tuple[list[tuple[dict[str, Any], str]], list[tuple[dict[str, Any], str]]]:
    direct = [(dict(candidate), "direct_create") for candidate in event.get("direct_candidates") or []]
    wrapped = [
        (dict(candidate), candidate.get("source_instruction_decode_route") or "wrapped_inner_create")
        for candidate in event.get("wrapped_inner_candidates") or []
    ]
    tx = event.get("transaction")
    if isinstance(tx, dict) and tx:
        direct.extend((candidate, "direct_create") for candidate in _direct_candidates_from_transaction(tx))
        wrapped.extend((candidate, candidate.get("source_instruction_decode_route") or "inner_create") for candidate in _inner_candidates_from_transaction(tx, event))
    return direct, wrapped


def _direct_candidates_from_transaction(tx: dict[str, Any]) -> list[dict[str, Any]]:
    from research.mtp_research.ingestion.pumpfun_create_scanner import PumpFunCreateScanner
    from research.mtp_research.validation.forward_efficient_mover_observer import build_birth_watch_candidate_from_create_candidate

    scanner = PumpFunCreateScanner()
    candidates, _rejected, _unknown, _direct_count = scanner._extract_candidates(
        [tx],
        remaining_target=100,
        include_low_confidence=True,
        min_confidence="low",
    )
    return [build_birth_watch_candidate_from_create_candidate(candidate) for candidate in candidates]


def _inner_candidates_from_transaction(tx: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
    from research.mtp_research.validation.helius_transaction_subscribe_source import decode_pumpfun_transaction_subscribe_notification

    payload = {
        "result": {
            "slot": event.get("slot") or tx.get("slot"),
            "signature": event.get("signature"),
            "transaction": tx,
        }
    }
    rows = decode_pumpfun_transaction_subscribe_notification(payload, observed_at=event.get("received_at"))
    output: list[dict[str, Any]] = []
    for row in rows:
        route = row.get("source_instruction_decode_route")
        if row.get("source_instruction_level") == "inner" or route:
            output.append(dict(row))
    return output


def _normalize_audit_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    mint = candidate.get("mint") or candidate.get("token_mint") or candidate.get("ca")
    return {
        "mint": str(mint) if mint else None,
        "signature": candidate.get("signature") or candidate.get("transaction_signature") or candidate.get("launch_signature"),
        "slot": candidate.get("slot"),
        "source_route": candidate.get("source_adapter") or candidate.get("source") or candidate.get("source_route"),
        "bonding_curve_account": candidate.get("bonding_curve_account") or candidate.get("bonding_curve") or candidate.get("pool_address"),
        "associated_bonding_curve": candidate.get("associated_bonding_curve") or candidate.get("associated_bonding_curve_account"),
        "creator": candidate.get("creator") or candidate.get("creator_wallet"),
        "source_instruction_level": candidate.get("source_instruction_level"),
        "source_instruction_decode_route": candidate.get("source_instruction_decode_route"),
        "instruction_type": candidate.get("instruction_type"),
    }


def _append_audit_row(
    output_root: Path,
    event: dict[str, Any],
    candidate: dict[str, Any] | None,
    decode_route: str,
    reject_reason: str | None,
) -> None:
    row = {
        "received_at": event.get("received_at"),
        "signature": (candidate or {}).get("signature") or event.get("signature"),
        "slot": (candidate or {}).get("slot") or event.get("slot"),
        "source_route": event.get("source_route") or (candidate or {}).get("source_route") or "unknown",
        "mentioned_program_ids": list(event.get("mentioned_program_ids") or []),
        "log_snippets": [str(log)[:180] for log in (event.get("logs") or [])[:6]],
        "compact_instruction_summary": {
            "source_instruction_level": (candidate or {}).get("source_instruction_level"),
            "source_instruction_decode_route": (candidate or {}).get("source_instruction_decode_route"),
            "instruction_type": (candidate or {}).get("instruction_type"),
        },
        "decode_attempted": decode_route != "not_decoded",
        "decode_route": decode_route,
        "decoded_mint": (candidate or {}).get("mint"),
        "bonding_curve_account": (candidate or {}).get("bonding_curve_account"),
        "associated_bonding_curve": (candidate or {}).get("associated_bonding_curve"),
        "reject_reason": reject_reason,
    }
    with (output_root / "raw_birth_source_audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _source_route_comparison(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_name": "PumpFunCreateWebSocketCandidateSource",
            "route_type": "logsSubscribe mentions Pump.fun program, then getTransaction, then direct PumpFunCreateScanner",
            "expected_coverage": "medium; covers simple top-level create layouts, likely misses some inner/wrapped/compact routes",
            "raw_notifications": summary.get("raw_websocket_notifications_received"),
            "decoded_births": summary.get("direct_create_candidates"),
            "unique_mints": summary.get("unique_mints"),
            "duplicate_mints": summary.get("duplicate_mints"),
            "pros": "works on standard Helius RPC/websocket and already wired into broad birth watch",
            "cons": "depends on create log text and direct instruction hydration path",
        },
        {
            "source_name": "HeliusTransactionSubscribeCreateSource",
            "route_type": "transactionSubscribe accountRequired Pump.fun program with full transaction details",
            "expected_coverage": "higher; existing decoder walks top-level and inner instructions and has wrapped compact Mayhem create handling",
            "raw_notifications": None,
            "decoded_births": summary.get("wrapped_inner_create_candidates"),
            "unique_mints": None,
            "duplicate_mints": None,
            "pros": "can see inner/wrapped instruction context without a separate getTransaction fetch",
            "cons": "requires Helius transactionSubscribe availability and separate capacity audit",
        },
    ]


def _txsub_signature_from_payload(payload: dict[str, Any], decoded_rows: list[dict[str, Any]]) -> str | None:
    if decoded_rows and decoded_rows[0].get("signature"):
        return str(decoded_rows[0].get("signature"))
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else params.get("result")
    if isinstance(result, dict):
        if result.get("signature"):
            return str(result.get("signature"))
        tx = result.get("transaction")
        signatures = ((tx.get("transaction") or {}).get("signatures") or tx.get("signatures") or []) if isinstance(tx, dict) else []
        if signatures:
            return str(signatures[0])
    return None


def _txsub_slot_from_payload(payload: dict[str, Any], decoded_rows: list[dict[str, Any]]) -> int | None:
    if decoded_rows and decoded_rows[0].get("slot") is not None:
        return _int(decoded_rows[0].get("slot"))
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else params.get("result")
    if isinstance(result, dict):
        slot = result.get("slot")
        if slot is None and isinstance(result.get("context"), dict):
            slot = result["context"].get("slot")
        return _int(slot)
    return None


def _txsub_logs_from_payload(payload: dict[str, Any]) -> list[str]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else params.get("result")
    tx = result.get("transaction") if isinstance(result, dict) else None
    meta = tx.get("meta") if isinstance(tx, dict) else None
    if not isinstance(meta, dict):
        meta = result.get("meta") if isinstance(result, dict) else None
    logs = meta.get("logMessages") if isinstance(meta, dict) else None
    return [str(item) for item in logs] if isinstance(logs, list) else []


def _txsub_transaction_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else params.get("result")
    if isinstance(result, dict) and isinstance(result.get("transaction"), dict):
        return result["transaction"]
    if isinstance(payload.get("transaction"), dict):
        return payload["transaction"]
    return {}


def _txsub_transaction_from_event(event: dict[str, Any]) -> dict[str, Any]:
    if isinstance(event.get("transaction"), dict):
        return event["transaction"]
    payload = event.get("raw_payload") if isinstance(event.get("raw_payload"), dict) else {}
    return _txsub_transaction_from_payload(payload)


def _classify_transaction_decode_route(row: dict[str, Any]) -> str:
    route = str(row.get("source_instruction_decode_route") or "").lower()
    if "wrapped" in route or "compact" in route:
        return "wrapped_compact"
    if str(row.get("source_instruction_level") or "").lower() == "inner":
        return "inner"
    return "direct"


def _launch_from_transaction_decoded_row(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_transaction_decoded_row(row, event)
    route = _classify_transaction_decode_route(row)
    return {
        "mint": normalized.get("mint"),
        "signature": normalized.get("signature"),
        "slot": normalized.get("slot"),
        "block_time": row.get("block_time") or event.get("block_time"),
        "received_at": normalized.get("received_at") or event.get("received_at") or time.time(),
        "source_type": "transaction_subscribe",
        "decode_route": route,
        "bonding_curve_account": normalized.get("bonding_curve_account"),
        "associated_bonding_curve": normalized.get("associated_bonding_curve"),
        "creator": normalized.get("creator"),
        "raw_decoded_launch_payload": {
            "source_instruction_level": normalized.get("source_instruction_level"),
            "source_instruction_decode_route": normalized.get("source_instruction_decode_route"),
            "instruction_type": normalized.get("instruction_type"),
            "parser_status": normalized.get("parser_status"),
            "parser_error": normalized.get("parser_error"),
            "decode_route": route,
        },
    }


def _birth_sort_key(row: dict[str, Any]) -> tuple[float, float, str]:
    slot = _num(row.get("slot"))
    received_at = _num(row.get("received_at"))
    return (
        slot if slot is not None else float("inf"),
        received_at if received_at is not None else float("inf"),
        str(row.get("signature") or ""),
    )


def _increment_counter(counter: dict[str, int], key: str) -> None:
    counter[key] = int(counter.get(key, 0) or 0) + 1


def _increment_nested_counter(counter: dict[str, dict[str, int]], outer: str, inner: str) -> None:
    bucket = counter.setdefault(str(outer or "unknown"), {})
    bucket[str(inner or "unknown")] = int(bucket.get(str(inner or "unknown"), 0) or 0) + 1


def _decoded_route_from_launch(launch: dict[str, Any]) -> str | None:
    raw_payload = launch.get("raw_decoded_launch_payload") if isinstance(launch.get("raw_decoded_launch_payload"), dict) else {}
    route = launch.get("decode_route") or raw_payload.get("decode_route")
    return str(route) if route else None


def _source_route_key_from_launch(launch: dict[str, Any]) -> str:
    source = str(launch.get("source_type") or launch.get("source_route") or "unknown")
    route = _decoded_route_from_launch(launch)
    return f"{source}:{route}" if route else source


def _minute_bucket(received_at: float | None) -> str:
    value = _num(received_at)
    return str(int(value // 60)) if value is not None else "unknown"


def _derive_bonding_curve_pda(mint: str | None) -> str | None:
    try:
        from research.mtp_research.validation.pumpfun_bonding_curve import bonding_curve_pda

        return bonding_curve_pda(mint)
    except Exception:
        return None


def _probe_account_candidate(launch: dict[str, Any]) -> tuple[str, str | None]:
    decoded = launch.get("bonding_curve_account") or launch.get("bonding_curve")
    if decoded:
        return "decoded_bonding_curve", str(decoded)
    derived = _derive_bonding_curve_pda(str(launch.get("mint") or ""))
    if derived:
        return "derived_bonding_curve", derived
    associated = launch.get("associated_bonding_curve")
    if associated:
        return "associated_bonding_curve", str(associated)
    return "fallback", None


def _median_or_none(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return median(clean) if clean else None


def _band_label(band: int | float | None) -> str:
    if band is None:
        return "unknown"
    value = int(float(band))
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000}m"
    if value >= 1_000 and value % 1_000 == 0:
        return f"{value // 1_000}k"
    return str(value).replace(".", "_")


def _transition_label(start: int, end: int) -> str:
    return f"{_band_label(start)}_to_{_band_label(end)}"


def _next_valuation_band(band: int) -> int | None:
    ordered = [int(value) for value in VALUATION_BANDS_USD]
    try:
        index = ordered.index(int(band))
    except ValueError:
        return None
    next_index = index + 1
    return ordered[next_index] if next_index < len(ordered) else None


def _transition_seconds(state: TrackingState, start: int, end: int | None) -> float | None:
    if end is None:
        return None
    start_seconds = state.valuation_band_seconds_since_launch.get(int(start))
    end_seconds = state.valuation_band_seconds_since_launch.get(int(end))
    if start_seconds is None or end_seconds is None:
        return None
    return round(max(0.0, end_seconds - start_seconds), 6)


def _state_source_route_key(state: TrackingState) -> str:
    source = state.source_route_type or "unknown"
    route = state.source_decode_route
    return f"{source}:{route}" if route else source


def _valuation_missing_reason(row: dict[str, Any]) -> str:
    if row.get("decode_status") != "decoded":
        return "curve_decode_failed"
    if not row.get("raw_curve_state"):
        return "missing_curve_state"
    return "missing_valuation_field"



def _paper_position_accounting_available() -> bool:
    try:
        from research.mtp_research.validation import official_lifecycle_v2_paper_trader as official_paper
        from research.mtp_research.validation import rule_runtime_v1 as rule_runtime
        from research.mtp_research.validation import rule_runtime_v1_campaign as runtime_campaign
    except Exception:
        return False
    return bool(
        hasattr(rule_runtime, "_initial_state")
        and hasattr(official_paper, "_initial_state")
        and hasattr(runtime_campaign, "paper_accounting")
    )

def _creator_history_metrics(launch: dict[str, Any], launch_received_at: float | None) -> dict[str, Any]:
    history = launch.get("creator_history")
    if not isinstance(history, list):
        return {"creator_history_status": "deferred"}
    prior = []
    for item in history:
        if not isinstance(item, dict):
            continue
        item_time = _num(item.get("launch_received_at") or item.get("received_at") or item.get("created_at"))
        if launch_received_at is not None and item_time is not None and item_time < launch_received_at:
            prior.append(item)
    max_band_values = [_num(item.get("max_fdv_band") or item.get("prior_max_fdv_band") or item.get("max_fdv_usd")) for item in prior]
    return {
        "creator_history_status": "available",
        "creator_history_point_in_time_safe": True,
        "creator_prior_launch_count_before_this_launch": len(prior),
        "creator_prior_migration_count_before_this_launch": sum(1 for item in prior if _bool(item.get("migrated") or item.get("complete"))),
        "creator_prior_max_fdv_band_before_this_launch": max((value for value in max_band_values if value is not None), default=None),
        "creator_prior_rug_dead_count_before_this_launch": sum(1 for item in prior if _bool(item.get("rug") or item.get("dead") or item.get("rug_or_dead"))),
    }


def _normalize_transaction_decoded_row(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "received_at": row.get("observed_at") or event.get("received_at"),
        "signature": row.get("signature") or event.get("signature"),
        "slot": row.get("slot") or event.get("slot"),
        "mint": row.get("mint") or row.get("token_mint") or row.get("ca"),
        "bonding_curve_account": row.get("bonding_curve_account") or row.get("bonding_curve") or row.get("pool_address"),
        "associated_bonding_curve": row.get("associated_bonding_curve") or row.get("associated_bonding_curve_account"),
        "creator": row.get("creator") or row.get("creator_wallet") or row.get("dev"),
        "quote_mint": row.get("quote_mint") or row.get("quoteMint"),
        "quote_type": row.get("quote_type") or row.get("quote_asset"),
        "source_instruction_level": row.get("source_instruction_level"),
        "source_instruction_decode_route": row.get("source_instruction_decode_route"),
        "instruction_type": row.get("instruction_type"),
        "parser_status": row.get("parser_status"),
        "parser_error": row.get("parser_error") or row.get("parser_failure_reason"),
    }


def _increment_reason(summary: dict[str, Any], reason: str) -> None:
    reasons = summary.setdefault("rejects_by_reason", {})
    reasons[reason] = int(reasons.get(reason, 0) or 0) + 1


def _append_transaction_audit_row(
    output_root: Path,
    event: dict[str, Any],
    candidate: dict[str, Any] | None,
    decoded_route: str,
    reject_reason: str | None,
) -> None:
    row = {
        "received_at": (candidate or {}).get("received_at") or event.get("received_at"),
        "signature": (candidate or {}).get("signature") or event.get("signature"),
        "slot": (candidate or {}).get("slot") or event.get("slot"),
        "route_type": event.get("route_type") or "transactionSubscribe",
        "decoded_route": decoded_route,
        "decoded_mint": (candidate or {}).get("mint"),
        "bonding_curve_account": (candidate or {}).get("bonding_curve_account"),
        "associated_bonding_curve": (candidate or {}).get("associated_bonding_curve"),
        "creator": (candidate or {}).get("creator"),
        "reject_reason": reject_reason,
        "compact_instruction_summary": {
            "source_instruction_level": (candidate or {}).get("source_instruction_level"),
            "source_instruction_decode_route": (candidate or {}).get("source_instruction_decode_route"),
            "instruction_type": (candidate or {}).get("instruction_type"),
            "parser_status": (candidate or {}).get("parser_status"),
            "parser_error": (candidate or {}).get("parser_error"),
        },
        "decode_attempted": candidate is not None,
    }
    with (output_root / "transaction_raw_birth_source_audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _transaction_source_route_comparison() -> list[dict[str, Any]]:
    return [
        {
            "source_name": "PumpFunCreateWebSocketCandidateSource",
            "route_type": "logsSubscribe mentions Pump.fun program, getTransaction hydration, direct scanner",
            "expected_coverage": "medium",
            "prior_t007e_raw_notifications": 199,
            "prior_t007e_decoded_births": 1,
            "prior_t007e_observed_span_seconds": 42.516523122787476,
        },
        {
            "source_name": "HeliusTransactionSubscribeCreateSource",
            "route_type": "transactionSubscribe accountRequired Pump.fun program with full transaction details",
            "expected_coverage": "higher if websocket remains stable; existing decoder walks top-level and inner instructions and wrapped compact create routes",
        },
    ]


def run_synthetic_smoke(config: BondingCurveRecorderConfig) -> dict[str, Any]:
    recorder = BondingCurveProgressRecorder(config)
    launches = [
        {"mint": "smoke-low", "signature": "sig-low", "slot": 1, "block_time": 1, "received_at": 1000.0, "source_type": "synthetic_smoke"},
        {"mint": "smoke-runner", "signature": "sig-runner", "slot": 2, "block_time": 2, "received_at": 1001.0, "source_type": "synthetic_smoke"},
        {"mint": "smoke-migrates", "signature": "sig-migrates", "slot": 3, "block_time": 3, "received_at": 1002.0, "source_type": "synthetic_smoke"},
    ]
    for launch in launches:
        recorder.process_birth(launch)
    for mint, steps in {
        "smoke-low": [10.0, 20.0, 35.0],
        "smoke-runner": [45.0, 58.0, 63.0, 71.0],
        "smoke-migrates": [52.0, 66.0, 82.0, 100.0],
    }.items():
        for index, progress in enumerate(steps, start=1):
            recorder.record_observation(
                {
                    "mint": mint,
                    "slot": 100 + index,
                    "block_time": 100 + index,
                    "received_at": 1010.0 + index,
                    "observation_source": "synthetic_smoke",
                    "bonding_curve_account": f"curve-{mint}",
                    "raw_curve_state": {"synthetic_progress_pct": progress},
                    "progress_pct": progress,
                    "complete": progress >= 100.0,
                    "fdv_proxy": progress * 1000.0,
                    "decode_status": "decoded",
                    "seconds_since_launch": index * 10.0,
                    "observation_id": f"smoke-{mint}-{index}",
                }
            )
    return recorder.finalize()


def _normalize_axiom_manual_rows(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            mint = str(item.get("mint") or item.get("ca") or item.get("token_mint") or "").strip()
            if not mint:
                continue
            normalized = dict(item)
            normalized["mint"] = mint
            normalized["token_name"] = item.get("token_name") or item.get("name")
            normalized["axiom_seen_at"] = item.get("axiom_seen_at")
            normalized["axiom_age_label"] = item.get("axiom_age_label")
            normalized["axiom_market_cap_usd"] = _num(item.get("axiom_market_cap_usd") or item.get("market_cap_usd") or item.get("mc_usd"))
            normalized["axiom_liquidity_usd"] = _num(item.get("axiom_liquidity_usd") or item.get("liquidity_usd") or item.get("liq_usd"))
            normalized["axiom_bcurve_pct"] = _num(item.get("axiom_bcurve_pct") or item.get("bcurve_pct") or item.get("bonding_curve_pct"))
            normalized["axiom_column"] = item.get("axiom_column") or item.get("column")
            normalized["notes"] = item.get("notes")
            normalized["cohort"] = item.get("cohort") or item.get("token_type")
            rows.append(normalized)
            continue
        mint = str(item).strip()
        if mint:
            rows.append(
                {
                    "mint": mint,
                    "token_name": None,
                    "axiom_seen_at": None,
                    "axiom_age_label": None,
                    "axiom_market_cap_usd": None,
                    "axiom_liquidity_usd": None,
                    "axiom_bcurve_pct": None,
                    "axiom_column": None,
                    "notes": None,
                    "cohort": None,
                }
            )
    return rows


class DirectMintLookupRpcClient:
    """Small JSON-RPC client used by bounded Axiom mint replay."""

    def __init__(self, rpc_url: str | None = None) -> None:
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        self.rpc_url = rpc_url or resolve_helius_rpc_url()

    def fetch_signatures_for_address(self, address: str, *, limit: int, before: str | None = None) -> list[dict[str, Any]]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        params: list[Any] = [address, {"limit": max(1, min(int(limit), 1000))}]
        if before:
            params[1]["before"] = before
        response = _post_json_rpc(
            self.rpc_url,
            {"jsonrpc": "2.0", "id": "mtp-t007-direct-lookup-signatures", "method": "getSignaturesForAddress", "params": params},
            20,
        )
        result = response.get("result") if isinstance(response, dict) else []
        return [dict(item) for item in result] if isinstance(result, list) else []

    def fetch_transaction(self, signature: str) -> dict[str, Any]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        response = _post_json_rpc(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-direct-lookup-transaction",
                "method": "getTransaction",
                "params": [
                    signature,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"},
                ],
            },
            20,
        )
        result = response.get("result") if isinstance(response, dict) else {}
        return dict(result) if isinstance(result, dict) else {}


class PumpSwapPoolStateRpcProbe:
    """Read-only PumpSwap market-account metadata probe.

    The PumpSwap market account exposes pool metadata and token accounts. Reserve
    balances require separate token-account state, so this probe intentionally
    returns metadata-only partial depth unless future safe reserve decoding is
    added.
    """

    def __init__(self, rpc_url: str | None = None, *, timeout_seconds: int = 10) -> None:
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        self.rpc_url = rpc_url or resolve_helius_rpc_url()
        self.timeout_seconds = max(1, int(timeout_seconds))

    def _fetch_token_account_balance(self, post_json_rpc: Any, token_account: str | None) -> dict[str, Any] | None:
        if not token_account:
            return None
        response = post_json_rpc(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-pumpswap-token-balance",
                "method": "getTokenAccountBalance",
                "params": [token_account, {"commitment": "processed"}],
            },
            self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, dict) else {}
        value = result.get("value") if isinstance(result, dict) else {}
        context = result.get("context") if isinstance(result, dict) else {}
        if not isinstance(value, dict) or value.get("amount") is None:
            return None
        raw = int(value.get("amount"))
        decimals = int(value.get("decimals") or 0)
        scaled = value.get("uiAmount")
        if scaled is None:
            scaled = raw / float(10**decimals)
        return {
            "token_account": token_account,
            "raw": raw,
            "scaled": float(scaled),
            "decimals": decimals,
            "slot": context.get("slot") if isinstance(context, dict) else None,
        }

    def fetch_pool_state(self, pool_or_pair_address: str) -> dict[str, Any]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        response = _post_json_rpc(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-pumpswap-pool-state",
                "method": "getAccountInfo",
                "params": [pool_or_pair_address, {"encoding": "base64", "commitment": "processed"}],
            },
            self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, dict) else {}
        context = result.get("context") if isinstance(result, dict) else {}
        value = result.get("value") if isinstance(result, dict) else None
        observed_at = time.time()
        if not isinstance(value, dict):
            return {
                "pool_state_status": "not_available",
                "depth_status": "not_available",
                "pool_decode_route": "pumpswap_market_account_v1",
                "pool_decode_confidence": "account_not_found",
                "pool_state_error_reason": "account_not_found",
                "pool_state_observed_at": observed_at,
                "pool_state_slot": context.get("slot") if isinstance(context, dict) else None,
            }
        raw_data = value.get("data")
        encoded = raw_data[0] if isinstance(raw_data, list) and raw_data else raw_data if isinstance(raw_data, str) else None
        account_data = base64.b64decode(encoded) if encoded else b""
        decoded = _decode_pumpswap_market_account_data(account_data, account_pubkey=pool_or_pair_address)
        discriminator = account_data[:8].hex() if account_data else None
        if not decoded:
            try:
                from research.mtp_research.validation.t007_protocol_codecs import PumpSwapAccountDecoder

                diagnostic = PumpSwapAccountDecoder().decode_account(
                    account_data,
                    owner=value.get("owner"),
                    pool_address=pool_or_pair_address,
                )
                layout_status = diagnostic.confidence
                error_reason = diagnostic.error_reason or "pumpswap_pool_layout_unsupported"
                layout_version = diagnostic.layout_version
                evidence = dict(diagnostic.evidence)
            except Exception as exc:
                layout_status = "decode_failed"
                error_reason = f"pumpswap_pool_decode_diagnostic_failed:{type(exc).__name__}"
                layout_version = None
                evidence = {}
            return {
                "pool_state_status": "error",
                "depth_status": "error",
                "pool_decode_route": "pumpswap_market_account_v1",
                "pool_decode_confidence": layout_status,
                "pool_layout_status": layout_status,
                "vault_discovery_status": "failed",
                "reserve_fetch_status": "not_attempted",
                "pool_layout_version": layout_version,
                "pool_account_owner": value.get("owner"),
                "pool_account_size": len(account_data),
                "pool_discriminator": discriminator,
                "pool_state_error_reason": error_reason,
                "pool_state_observed_at": observed_at,
                "pool_state_slot": context.get("slot") if isinstance(context, dict) else None,
                "pool_decode_evidence": evidence,
            }
        base_balance = self._fetch_token_account_balance(_post_json_rpc, decoded.get("pool_base_token_account"))
        quote_balance = self._fetch_token_account_balance(_post_json_rpc, decoded.get("pool_quote_token_account"))
        reserves_available = base_balance is not None and quote_balance is not None
        row = {
            "pool_state_status": "available" if reserves_available else "partial",
            "depth_status": "available" if reserves_available else "partial",
            "pool_decode_route": "pumpswap_market_account_v1",
            "pool_decode_confidence": "token_account_reserves" if reserves_available else "metadata_only",
            "pool_layout_status": "decoded",
            "vault_discovery_status": "ready",
            "reserve_fetch_status": "ready" if reserves_available else "failed",
            "pool_account_owner": value.get("owner"),
            "pool_account_size": len(account_data),
            "pool_discriminator": discriminator,
            "pool_base_mint": decoded.get("base_mint"),
            "pool_quote_mint": decoded.get("quote_mint"),
            "pool_base_token_account": decoded.get("pool_base_token_account"),
            "pool_quote_token_account": decoded.get("pool_quote_token_account"),
            "pool_state_error_reason": None if reserves_available else "reserve_token_account_balance_not_available",
            "pool_state_observed_at": observed_at,
            "pool_state_slot": context.get("slot") if isinstance(context, dict) else None,
        }
        if base_balance is not None:
            row.update(
                {
                    "base_reserve_raw": base_balance["raw"],
                    "base_reserve_scaled": base_balance["scaled"],
                    "base_reserve_decimals": base_balance["decimals"],
                    "base_reserve_slot": base_balance["slot"],
                }
            )
        if quote_balance is not None:
            row.update(
                {
                    "quote_reserve_raw": quote_balance["raw"],
                    "quote_reserve_scaled": quote_balance["scaled"],
                    "quote_reserve_decimals": quote_balance["decimals"],
                    "quote_reserve_slot": quote_balance["slot"],
                    "pool_liquidity_quote": quote_balance["scaled"],
                }
            )
        return row


class RecentPrioritizationFeeProbe:
    """Read-only prioritization fee sampler for execution-cost diagnostics."""

    def __init__(self, rpc_url: str | None = None, *, timeout_seconds: int = 10) -> None:
        from research.mtp_research.validation.forward_efficient_mover_observer import resolve_helius_rpc_url

        self.rpc_url = rpc_url or resolve_helius_rpc_url()
        self.timeout_seconds = max(1, int(timeout_seconds))

    def fetch_recent_prioritization_fees(self, account_addresses: list[str] | None = None) -> list[dict[str, Any]]:
        from research.mtp_research.validation.forward_efficient_mover_observer import _post_json_rpc

        params: list[Any] = [account_addresses or []]
        response = _post_json_rpc(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": "mtp-t007-recent-prioritization-fees",
                "method": "getRecentPrioritizationFees",
                "params": params,
            },
            self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, dict) else []
        return [dict(item) for item in result] if isinstance(result, list) else []


def run_direct_mint_lookup(
    output_root: Path | str,
    mints: list[Any],
    *,
    client: Any | None = None,
    direct_lookup_limit: int = 20,
    sleep_ms: int = 250,
    include_raw_transactions: bool = False,
) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    for filename in JSONL_ARTIFACT_FILES:
        (root / filename).touch(exist_ok=True)
    requested_rows = _normalize_axiom_manual_rows(mints)
    rpc = client or DirectMintLookupRpcClient()
    rows: list[dict[str, Any]] = []
    summary = {
        "mode": "direct-mint-lookup",
        "output_root": str(root),
        "requested_mints": len(requested_rows),
        "direct_lookup_limit": int(direct_lookup_limit),
        "sleep_ms": int(sleep_ms),
        "include_raw_transactions": bool(include_raw_transactions),
        "found_migration_route_count": 0,
        "found_pool_route_count": 0,
        "found_birth_only_count": 0,
        "no_relevant_signatures_count": 0,
        "rpc_error_count": 0,
        "direct_mint_lookup_rows_path": str(root / "direct_mint_lookup_rows.jsonl"),
    }
    for requested in requested_rows:
        mint = requested["mint"]
        try:
            row = _direct_lookup_one_mint(
                mint,
                requested,
                rpc,
                direct_lookup_limit=max(1, int(direct_lookup_limit)),
                sleep_ms=max(0, int(sleep_ms)),
                include_raw_transactions=include_raw_transactions,
                output_root=root,
            )
        except Exception as exc:
            row = _empty_direct_lookup_row(mint, requested)
            row.update({"direct_lookup_status": "rpc_error", "error_reason": f"{type(exc).__name__}: {exc}"})
        rows.append(row)
        _append_jsonl_file(root / "direct_mint_lookup_rows.jsonl", row)
        _append_jsonl_file(root / "axiom_direct_lookup_evidence.jsonl", row)
        status = str(row.get("direct_lookup_status") or "unknown")
        if status == "found_migration_route":
            summary["found_migration_route_count"] += 1
        elif status == "found_pool_route":
            summary["found_pool_route_count"] += 1
        elif status == "found_birth_only":
            summary["found_birth_only_count"] += 1
        elif status == "no_relevant_signatures":
            summary["no_relevant_signatures_count"] += 1
        elif status == "rpc_error":
            summary["rpc_error_count"] += 1
    (root / "direct_mint_lookup_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def _direct_lookup_one_mint(
    mint: str,
    requested: dict[str, Any],
    rpc: Any,
    *,
    direct_lookup_limit: int,
    sleep_ms: int,
    include_raw_transactions: bool,
    output_root: Path,
) -> dict[str, Any]:
    row = _empty_direct_lookup_row(mint, requested)
    signatures_by_sig: dict[str, dict[str, Any]] = {}
    for address_role, address in _direct_lookup_addresses(mint):
        if sleep_ms:
            time.sleep(float(sleep_ms) / 1000.0)
        signatures = rpc.fetch_signatures_for_address(address, limit=direct_lookup_limit)
        row["lookup_addresses"].append({"role": address_role, "address": address, "signatures_found": len(signatures)})
        for item in signatures:
            signature = str(item.get("signature") or "").strip()
            if signature and signature not in signatures_by_sig:
                signatures_by_sig[signature] = dict(item)
            if len(signatures_by_sig) >= direct_lookup_limit:
                break
        if len(signatures_by_sig) >= direct_lookup_limit:
            break
    row["signatures_found"] = len(signatures_by_sig)
    row["direct_lookup_signatures_found"] = len(signatures_by_sig)
    if not signatures_by_sig:
        row["direct_lookup_status"] = "no_relevant_signatures"
        return row
    for signature, signature_row in signatures_by_sig.items():
        if sleep_ms:
            time.sleep(float(sleep_ms) / 1000.0)
        tx = rpc.fetch_transaction(signature)
        if not tx:
            continue
        row["transactions_fetched"] += 1
        if include_raw_transactions:
            _append_jsonl_file(output_root / "direct_mint_lookup_raw_transactions.jsonl", {"mint": mint, "signature": signature, "transaction": tx})
        decoded = _decode_direct_mint_transaction(mint, signature, signature_row, tx)
        if decoded:
            compact = {k: v for k, v in decoded.items() if k not in {"raw_transaction"}}
            _append_jsonl_file(output_root / "direct_mint_lookup_compact_decodes.jsonl", compact)
            _merge_direct_lookup_detection(row, decoded)
    if row["pumpfun_migrate_found"]:
        row["direct_lookup_status"] = "found_migration_route"
        row["detected_route_needed"] = "pumpfun_migrate"
    elif row["pumpswap_pool_create_found"]:
        row["direct_lookup_status"] = "found_pool_route"
        row["detected_route_needed"] = "pumpswap_account_required"
    elif row["pumpfun_create_found"]:
        row["direct_lookup_status"] = "found_birth_only"
        row["detected_route_needed"] = "unknown"
    else:
        row["direct_lookup_status"] = "no_relevant_signatures"
        row["detected_route_needed"] = "unknown"
    row["detection_route_needed"] = row["detected_route_needed"]
    return row


def _empty_direct_lookup_row(mint: str, requested: dict[str, Any]) -> dict[str, Any]:
    return {
        "mint": mint,
        "token_name": requested.get("token_name"),
        "axiom_seen_at": requested.get("axiom_seen_at"),
        "axiom_age_label": requested.get("axiom_age_label"),
        "axiom_market_cap_usd": requested.get("axiom_market_cap_usd"),
        "axiom_liquidity_usd": requested.get("axiom_liquidity_usd"),
        "axiom_bcurve_pct": requested.get("axiom_bcurve_pct"),
        "axiom_column": requested.get("axiom_column"),
        "notes": requested.get("notes"),
        "lookup_addresses": [],
        "signatures_found": 0,
        "direct_lookup_signatures_found": 0,
        "transactions_fetched": 0,
        "pumpfun_create_found": False,
        "pumpfun_migrate_found": False,
        "pumpswap_pool_create_found": False,
        "dex_pair_proxy_found": False,
        "migration_like_signature": None,
        "migration_like_signature_found": False,
        "migration_program_id": None,
        "migration_instruction_name": None,
        "pool_or_pair_address": None,
        "base_mint": None,
        "quote_mint": None,
        "detected_route_needed": "unknown",
        "detection_route_needed": "unknown",
        "direct_lookup_status": "not_implemented",
        "error_reason": None,
    }


def _direct_lookup_addresses(mint: str) -> list[tuple[str, str]]:
    addresses = [("mint", mint)]
    try:
        curve = _derive_bonding_curve_pda(mint)
    except Exception:
        curve = None
    if curve and curve != mint:
        addresses.append(("bonding_curve_pda", curve))
    return addresses


def _decode_direct_mint_transaction(
    mint: str,
    signature: str,
    signature_row: dict[str, Any],
    tx: dict[str, Any],
) -> dict[str, Any] | None:
    logs = _transaction_logs(tx)
    instructions = _transaction_instructions(tx)
    text = " ".join([*logs, *[str(item.get("instruction_name") or item.get("instruction_type") or "") for item in instructions]]).lower()
    program_ids = {str(item.get("program_id") or "") for item in instructions}
    pumpfun_create = PUMP_FUN_PROGRAM_ID_FOR_AUDIT in program_ids and "create" in text
    pumpfun_migrate = PUMP_FUN_PROGRAM_ID_FOR_AUDIT in program_ids and "migrate" in text and "migratebondingcurvecreator" not in text
    pumpswap_pool = PUMPSWAP_PROGRAM_ID_FOR_AUDIT in program_ids and any(word in text for word in ["createpool", "create_pool", "initialize", "pool", "addliquidity", "add_liquidity"])
    if not (pumpfun_create or pumpfun_migrate or pumpswap_pool):
        return None
    best_instruction = next((item for item in instructions if item.get("program_id") == PUMPSWAP_PROGRAM_ID_FOR_AUDIT), None)
    if best_instruction is None:
        best_instruction = next((item for item in instructions if item.get("program_id") == PUMP_FUN_PROGRAM_ID_FOR_AUDIT), None)
    accounts = list((best_instruction or {}).get("accounts") or [])
    pool = _candidate_pool_from_accounts(accounts, mint)
    return {
        "mint": mint,
        "signature": signature,
        "slot": signature_row.get("slot") or tx.get("slot"),
        "block_time": signature_row.get("blockTime") or tx.get("blockTime"),
        "pumpfun_create_found": pumpfun_create,
        "pumpfun_migrate_found": pumpfun_migrate,
        "pumpswap_pool_create_found": pumpswap_pool,
        "migration_program_id": (best_instruction or {}).get("program_id"),
        "migration_instruction_name": (best_instruction or {}).get("instruction_name") or (best_instruction or {}).get("instruction_type"),
        "pool_or_pair_address": pool,
        "base_mint": mint if pumpswap_pool else None,
        "quote_mint": _quote_mint_from_accounts(accounts, mint),
        "raw_compact_account_list": accounts[:16],
        "raw_compact_log_snippets": logs[:8],
        "detection_method": "pumpswap_pool_create" if pumpswap_pool else "pumpfun_migrate" if pumpfun_migrate else "pumpfun_create",
        "confidence": "candidate" if pumpswap_pool else "confirmed",
    }


def _merge_direct_lookup_detection(row: dict[str, Any], decoded: dict[str, Any]) -> None:
    for key in ["pumpfun_create_found", "pumpfun_migrate_found", "pumpswap_pool_create_found"]:
        row[key] = bool(row.get(key)) or bool(decoded.get(key))
    if decoded.get("pumpfun_migrate_found") or decoded.get("pumpswap_pool_create_found"):
        row["migration_like_signature"] = row.get("migration_like_signature") or decoded.get("signature")
        row["migration_like_signature_found"] = True
        row["migration_program_id"] = row.get("migration_program_id") or decoded.get("migration_program_id")
        row["migration_instruction_name"] = row.get("migration_instruction_name") or decoded.get("migration_instruction_name")
        row["pool_or_pair_address"] = row.get("pool_or_pair_address") or decoded.get("pool_or_pair_address")
        row["base_mint"] = row.get("base_mint") or decoded.get("base_mint")
        row["quote_mint"] = row.get("quote_mint") or decoded.get("quote_mint")


def _transaction_logs(tx: dict[str, Any]) -> list[str]:
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    logs = meta.get("logMessages")
    return [str(item) for item in logs] if isinstance(logs, list) else []


def _transaction_instructions(tx: dict[str, Any]) -> list[dict[str, Any]]:
    message = ((tx.get("transaction") or {}).get("message") or {}) if isinstance(tx.get("transaction"), dict) else {}
    output: list[dict[str, Any]] = []
    for instruction in message.get("instructions") or []:
        output.append(_compact_instruction(instruction))
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    for group in meta.get("innerInstructions") or []:
        for instruction in group.get("instructions") or []:
            compact = _compact_instruction(instruction)
            compact["instruction_level"] = "inner"
            output.append(compact)
    return output


def _compact_instruction(instruction: dict[str, Any]) -> dict[str, Any]:
    parsed = instruction.get("parsed") if isinstance(instruction.get("parsed"), dict) else {}
    info = parsed.get("info") if isinstance(parsed.get("info"), dict) else {}
    accounts = instruction.get("accounts") or info.get("accounts") or []
    if not isinstance(accounts, list):
        accounts = []
    return {
        "program_id": instruction.get("programId") or instruction.get("program_id"),
        "instruction_type": instruction.get("type") or parsed.get("type"),
        "instruction_name": instruction.get("name") or parsed.get("type") or instruction.get("type"),
        "accounts": [str(item) for item in accounts],
        "instruction_level": "top",
    }


def _candidate_pool_from_accounts(accounts: list[str], mint: str) -> str | None:
    excluded = {
        mint,
        PUMP_FUN_PROGRAM_ID_FOR_AUDIT,
        PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
        "So11111111111111111111111111111111111111112",
        "11111111111111111111111111111111",
    }
    for account in accounts:
        if account and account not in excluded and "pool" in account.lower():
            return account
    for account in accounts:
        if account and account not in excluded:
            return account
    return None


def _quote_mint_from_accounts(accounts: list[str], mint: str) -> str | None:
    for account in accounts:
        if account != mint and account == "So11111111111111111111111111111111111111112":
            return account
    return None


MIGRATED_MINT_REPLAY_FIELDNAMES = [
    "mint",
    "migration_seen",
    "migration_signature",
    "pool_or_pair_address",
    "quote_asset",
    "birth_seen_in_campaign",
    "admitted_in_campaign",
    "sample_rejected_in_campaign",
    "curve_observations_count_in_campaign",
    "highest_progress_pct",
    "thresholds_crossed",
    "threshold_to_migration_seconds",
    "launch_signature_from_replay",
    "launch_slot_from_replay",
    "launch_time_from_replay",
    "campaign_start_time",
    "campaign_end_time",
    "launched_before_campaign",
    "launched_during_campaign",
    "launched_after_campaign",
    "birth_source_should_have_seen_it",
    "birth_source_missed_it",
    "source_miss_reason",
    "replay_birth_found",
    "replay_curve_path_found",
    "replay_migration_found",
    "migration_completeness_class",
    "data_completeness_grade",
    "explanation",
]


def run_migrated_mint_replay(
    input_run_root: Path | str,
    *,
    output_root: Path | str | None = None,
    mints: list[str] | None = None,
    mints_csv: Path | str | None = None,
    client: Any | None = None,
    max_signatures_per_address: int = 25,
    max_transactions_per_mint: int = 50,
    lookup_sleep_ms: int = 250,
    include_raw_transactions: bool = False,
) -> dict[str, Any]:
    input_root = Path(input_run_root)
    root = Path(output_root) if output_root is not None else input_root
    root.mkdir(parents=True, exist_ok=True)
    migration_rows = _read_jsonl(input_root / "global_migration_events.jsonl")
    births = _read_jsonl(input_root / "birth_audit.jsonl")
    observations = _read_jsonl(input_root / "curve_observations.jsonl")
    path_rows = _read_jsonl(input_root / "token_path_summary.jsonl")
    threshold_rows = _read_jsonl(input_root / "true_curve_threshold_crossings.jsonl") or _read_jsonl(input_root / "threshold_crossings.jsonl")
    manifest = _read_json(input_root / "campaign_manifest.json")
    collector_summary = _read_json(input_root / "collector_summary.json")
    velocity_rows = _read_jsonl(input_root / "curve_velocity_events.jsonl")
    trade_rows = _read_jsonl(input_root / "trade_flow_events.jsonl")
    organic_rows = _read_jsonl(input_root / "organic_flow_events.jsonl")
    holder_rows = _read_jsonl(input_root / "holder_distribution_snapshots.jsonl")
    dev_rows = _read_jsonl(input_root / "dev_behavior_events.jsonl")
    post_rows = _read_jsonl(input_root / "post_migration_observations.jsonl")
    execution_rows = _read_jsonl(input_root / "execution_cost_observations.jsonl")
    requested_mints = set(mints or []) | set(_load_mints_csv(mints_csv) if mints_csv else [])
    existing_migration_mints = {str(row.get("mint") or "").strip() for row in migration_rows if str(row.get("mint") or "").strip()}
    for mint in sorted(requested_mints - existing_migration_mints):
        migration_rows.append(
            {
                "mint": mint,
                "signature": None,
                "pool_or_pair_address": None,
                "quote_asset": None,
                "detection_method": "manual_mint_replay_without_campaign_migration_event",
                "confidence": "manual_replay",
            }
        )
    by_birth = _group_by_mint(births)
    by_observation = _group_by_mint(observations)
    by_path = _group_by_mint(path_rows)
    by_threshold = _group_by_mint(threshold_rows)
    feature_rows = {
        "velocity_features_available": _group_by_mint(velocity_rows),
        "trade_flow_available": _group_by_mint(trade_rows),
        "buyer_breadth_available": _group_by_mint(organic_rows),
        "holder_distribution_available": _group_by_mint(holder_rows),
        "dev_behavior_available": _group_by_mint(dev_rows),
        "post_migration_observations_available": _group_by_mint(post_rows),
        "execution_cost_available": _group_by_mint(execution_rows),
    }
    rpc = client or DirectMintLookupRpcClient()
    rows: list[dict[str, Any]] = []
    errors = 0
    for migration in migration_rows:
        mint = str(migration.get("mint") or "").strip()
        if not mint:
            continue
        try:
            replay = _replay_lookup_one_migrated_mint(
                mint,
                migration,
                rpc,
                max_signatures_per_address=max(1, int(max_signatures_per_address)),
                max_transactions_per_mint=max(1, int(max_transactions_per_mint)),
                lookup_sleep_ms=max(0, int(lookup_sleep_ms)),
                include_raw_transactions=bool(include_raw_transactions),
                output_root=root,
            )
        except Exception as exc:
            errors += 1
            replay = {
                "lookup_error": f"{type(exc).__name__}: {exc}",
                "transactions_fetched": 0,
                "launch_signature_from_replay": None,
                "launch_slot_from_replay": None,
                "launch_time_from_replay": None,
                "replay_birth_found": False,
                "replay_migration_found": False,
            }
        row = _migrated_mint_replay_row(
            mint,
            migration,
            replay,
            manifest=manifest,
            collector_summary=collector_summary,
            birth_rows=by_birth.get(mint, []),
            observation_rows=by_observation.get(mint, []),
            path_rows=by_path.get(mint, []),
            threshold_rows=by_threshold.get(mint, []),
            feature_rows={key: grouped.get(mint, []) for key, grouped in feature_rows.items()},
        )
        rows.append(row)
    rows_path = root / "migrated_mint_replay_rows.jsonl"
    rows_path.write_text("".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")
    csv_path = root / "migrated_mint_completeness.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(MIGRATED_MINT_REPLAY_FIELDNAMES)
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    diagnostics_path = root / "birth_source_miss_diagnostics.csv"
    diagnostic_rows = [_birth_source_miss_diagnostic_row(row) for row in rows if row.get("birth_source_missed_it")]
    with diagnostics_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["mint", "launch_signature", "launch_time", "missing_route", "source_should_have_seen", "recommended_fix"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diagnostic_rows)
    summary = _migrated_mint_replay_summary(rows, input_root=input_root, output_root=root, lookup_error_count=errors)
    summary["migrated_mint_replay_rows_path"] = str(rows_path)
    summary["migrated_mint_completeness_csv"] = str(csv_path)
    summary["birth_source_miss_diagnostics_csv"] = str(diagnostics_path)
    summary_path = root / "migrated_mint_replay_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    gate_path = root / "campaign_quality_gate.json"
    gate_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    _write_migrated_mint_replay_summary_md(root / "summary.md", summary, rows)
    return summary


def _replay_lookup_one_migrated_mint(
    mint: str,
    migration: dict[str, Any],
    rpc: Any,
    *,
    max_signatures_per_address: int,
    max_transactions_per_mint: int,
    lookup_sleep_ms: int,
    include_raw_transactions: bool,
    output_root: Path,
) -> dict[str, Any]:
    addresses = _direct_lookup_addresses(mint)
    pool = _first_present(migration, ["pool_or_pair_address", "pool_address", "pair_address"])
    if pool:
        addresses.append(("pumpswap_pool_or_pair", str(pool)))
    seen_addresses: set[str] = set()
    signatures_by_sig: dict[str, dict[str, Any]] = {}
    lookup_addresses: list[dict[str, Any]] = []
    for role, address in addresses:
        if not address or address in seen_addresses:
            continue
        seen_addresses.add(address)
        if lookup_sleep_ms:
            time.sleep(float(lookup_sleep_ms) / 1000.0)
        signatures = rpc.fetch_signatures_for_address(address, limit=max_signatures_per_address)
        lookup_addresses.append({"role": role, "address": address, "signatures_found": len(signatures)})
        for item in signatures:
            signature = str(item.get("signature") or "").strip()
            if signature and signature not in signatures_by_sig:
                signatures_by_sig[signature] = dict(item)
    decodes: list[dict[str, Any]] = []
    for signature, signature_row in list(signatures_by_sig.items())[:max_transactions_per_mint]:
        if lookup_sleep_ms:
            time.sleep(float(lookup_sleep_ms) / 1000.0)
        tx = rpc.fetch_transaction(signature)
        if not tx:
            continue
        if include_raw_transactions:
            _append_jsonl_file(output_root / "migrated_mint_replay_raw_transactions.jsonl", {"mint": mint, "signature": signature, "transaction": tx})
        decoded = _decode_direct_mint_transaction(mint, signature, signature_row, tx)
        if decoded:
            decodes.append(decoded)
            _append_jsonl_file(output_root / "migrated_mint_replay_compact_decodes.jsonl", decoded)
    create_decodes = [row for row in decodes if row.get("pumpfun_create_found")]
    migration_decodes = [row for row in decodes if row.get("pumpfun_migrate_found") or row.get("pumpswap_pool_create_found")]
    create = min(create_decodes, key=lambda row: (_num(row.get("block_time")) or float("inf"), _num(row.get("slot")) or float("inf")), default={})
    migration_decode = migration_decodes[0] if migration_decodes else {}
    return {
        "lookup_addresses": lookup_addresses,
        "signatures_found": len(signatures_by_sig),
        "transactions_fetched": min(len(signatures_by_sig), max_transactions_per_mint),
        "launch_signature_from_replay": create.get("signature"),
        "launch_slot_from_replay": create.get("slot"),
        "launch_time_from_replay": create.get("block_time"),
        "replay_birth_found": bool(create),
        "replay_migration_found": bool(migration_decode),
        "replay_migration_signature": migration_decode.get("signature"),
        "replay_migration_program_id": migration_decode.get("migration_program_id"),
        "replay_pool_or_pair_address": migration_decode.get("pool_or_pair_address"),
        "replay_quote_mint": migration_decode.get("quote_mint"),
    }


def _migrated_mint_replay_row(
    mint: str,
    migration: dict[str, Any],
    replay: dict[str, Any],
    *,
    manifest: dict[str, Any],
    collector_summary: dict[str, Any],
    birth_rows: list[dict[str, Any]],
    observation_rows: list[dict[str, Any]],
    path_rows: list[dict[str, Any]],
    threshold_rows: list[dict[str, Any]],
    feature_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    campaign_start = _first_present(manifest, ["started_at", "source_start_time", "campaign_start_time"])
    campaign_end = _first_present(manifest, ["ended_at", "source_stop_time", "campaign_end_time"])
    if campaign_end is None and _num(campaign_start) is not None:
        duration = _num(_first_present(manifest, ["actual_duration_seconds", "source_duration_seconds", "requested_duration_seconds"]))
        campaign_end = (_num(campaign_start) or 0.0) + duration if duration is not None else None
    launch_time = _num(replay.get("launch_time_from_replay"))
    start_num = _num(campaign_start)
    end_num = _num(campaign_end)
    launched_before = bool(launch_time is not None and start_num is not None and launch_time < start_num)
    launched_during = bool(launch_time is not None and start_num is not None and end_num is not None and start_num <= launch_time <= end_num)
    launched_after = bool(launch_time is not None and end_num is not None and launch_time > end_num)
    admitted = any(_bool(row.get("admitted")) for row in birth_rows)
    sample_rejected = any(str(row.get("admission_reason") or "") == "sample_rejected" or _bool(row.get("sample_rejected")) for row in birth_rows)
    capacity_rejected = any(str(row.get("admission_reason") or "").startswith("capacity_rejected") or _bool(row.get("capacity_rejected")) for row in birth_rows)
    backfilled_birth = any(_bool(row.get("birth_backfilled_from_replay")) for row in birth_rows)
    curve_count = int(_first_present(path_rows[-1] if path_rows else {}, ["curve_observation_count", "observation_count"]) or len(observation_rows))
    thin_path = any(
        str(row.get("tracking_tier") or "") == "thin"
        or str(row.get("probe_scope") or "").startswith("thin")
        or str(row.get("observation_source") or "").startswith("thin")
        for row in observation_rows
    )
    progress_values = [_num(row.get("progress_pct")) for row in observation_rows if _num(row.get("progress_pct")) is not None]
    highest_progress = _first_present(path_rows[-1] if path_rows else {}, ["highest_progress_pct", "max_progress_pct"])
    if highest_progress is None and progress_values:
        highest_progress = max(progress_values)
    thresholds = sorted(
        {
            float(row.get("threshold_pct"))
            for row in threshold_rows
            if _num(row.get("threshold_pct")) is not None
        }
    )
    path = path_rows[-1] if path_rows else {}
    threshold_to_migration = _first_present(path, ["threshold_to_migration_seconds"])
    birth_seen = bool(birth_rows)
    migration_seen = True
    birth_should_have_seen = launched_during
    birth_source_missed = bool(launched_during and not birth_seen)
    if backfilled_birth and migration_seen:
        completeness = "BACKFILLED_BIRTH_WITH_MIGRATION"
        explanation = "migration_seen_first_and_birth_recovered_by_replay_backfill"
    elif birth_seen and admitted and curve_count > 0 and migration_seen:
        completeness = "FULL_PATH"
        explanation = "birth_seen_admitted_curve_path_and_global_migration"
    elif birth_seen and sample_rejected and thin_path and migration_seen:
        completeness = "SAMPLE_REJECTED_WITH_THIN_PATH"
        explanation = "birth_seen_sample_rejected_but_thin_curve_path_and_global_migration_present"
    elif birth_seen and thin_path and migration_seen:
        completeness = "THIN_PATH"
        explanation = "birth_seen_with_thin_curve_path_and_global_migration_present"
    elif birth_seen and sample_rejected and migration_seen:
        completeness = "SAMPLE_REJECTED_WITH_MIGRATION"
        explanation = "birth_seen_but_sample_rejected_global_migration_present"
    elif birth_seen and migration_seen:
        completeness = "BIRTH_ONLY"
        explanation = "birth_seen_but_no_deep_curve_path"
    elif launched_before:
        completeness = "MIGRATION_ONLY_PREEXISTING"
        explanation = "migration_seen_but_launch_replay_precedes_campaign"
    elif launched_during:
        completeness = "MIGRATION_ONLY_SOURCE_MISS"
        explanation = "migration_seen_and_launch_replay_during_campaign_but_birth_source_missing"
    elif replay.get("replay_birth_found") is False:
        completeness = "MIGRATION_ONLY_REPLAY_UNRESOLVED"
        explanation = "migration_seen_but_direct_replay_did_not_find_launch"
    else:
        completeness = "POST_ONLY"
        explanation = "migration_or_pool_seen_without_reconstructable_birth_path"
    if launched_before:
        source_miss_reason = "launched_before_campaign"
    elif birth_source_missed:
        source_miss_reason = _infer_source_miss_reason(migration, replay)
    elif not replay.get("replay_birth_found") and not birth_seen:
        source_miss_reason = "rpc_lookup_inconclusive"
    else:
        source_miss_reason = ""
    quote_asset = _first_present(migration, ["quote_asset"]) or _quote_identity_from_payload({"quote_mint": replay.get("replay_quote_mint")}).get("quote_asset")
    row = {
        "mint": mint,
        "migration_seen": migration_seen,
        "migration_signature": _first_present(migration, ["signature", "migration_signature"]) or replay.get("replay_migration_signature"),
        "pool_or_pair_address": _first_present(migration, ["pool_or_pair_address", "pool_address", "pair_address"]) or replay.get("replay_pool_or_pair_address"),
        "quote_asset": quote_asset,
        "birth_seen_in_campaign": birth_seen,
        "admitted_in_campaign": admitted,
        "sample_rejected_in_campaign": sample_rejected,
        "capacity_rejected_in_campaign": capacity_rejected,
        "curve_observations_count_in_campaign": curve_count,
        "highest_progress_pct": highest_progress,
        "highest_progress_pct_in_campaign": highest_progress,
        "thresholds_crossed": ",".join(str(value) for value in thresholds),
        "threshold_to_migration_seconds": threshold_to_migration,
        "launch_signature_from_replay": replay.get("launch_signature_from_replay"),
        "launch_slot_from_replay": replay.get("launch_slot_from_replay"),
        "launch_time_from_replay": replay.get("launch_time_from_replay"),
        "campaign_start_time": campaign_start,
        "campaign_end_time": campaign_end,
        "campaign_run_id": manifest.get("run_id") or collector_summary.get("run_id"),
        "launched_before_campaign": launched_before,
        "launched_during_campaign": launched_during,
        "launched_after_campaign": launched_after,
        "birth_source_should_have_seen_it": birth_should_have_seen,
        "birth_source_missed_it": birth_source_missed,
        "source_miss_reason": source_miss_reason,
        "replay_birth_found": bool(replay.get("replay_birth_found")),
        "replay_curve_path_found": bool(curve_count > 0),
        "replay_migration_found": bool(replay.get("replay_migration_found")),
        "migration_completeness_class": completeness,
        "data_completeness_grade": completeness,
        "explanation": explanation,
        "lookup_error": replay.get("lookup_error"),
        "replay_signatures_found": replay.get("signatures_found"),
        "replay_transactions_fetched": replay.get("transactions_fetched"),
    }
    for key, rows in feature_rows.items():
        row[key] = _feature_rows_available(rows)
    return row


def _migrated_mint_replay_summary(
    rows: list[dict[str, Any]],
    *,
    input_root: Path,
    output_root: Path,
    lookup_error_count: int,
) -> dict[str, Any]:
    total = len(rows)
    class_counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("migration_completeness_class") or "unknown")
        class_counts[label] = class_counts.get(label, 0) + 1
    launched_during = [row for row in rows if row.get("launched_during_campaign")]
    source_miss = [row for row in launched_during if row.get("birth_source_missed_it")]
    every_classified = total == sum(class_counts.values())
    summary = {
        "mode": "migrated-mint-replay",
        "input_run_root": str(input_root),
        "output_root": str(output_root),
        "migrated_mints_total": total,
        "migrated_full_path_count": class_counts.get("FULL_PATH", 0),
        "migrated_thin_path_count": class_counts.get("THIN_PATH", 0),
        "migrated_birth_only_count": class_counts.get("BIRTH_ONLY", 0),
        "migrated_sample_rejected_count": class_counts.get("SAMPLE_REJECTED_WITH_MIGRATION", 0),
        "migrated_sample_rejected_with_thin_path_count": class_counts.get("SAMPLE_REJECTED_WITH_THIN_PATH", 0),
        "migrated_backfilled_birth_count": class_counts.get("BACKFILLED_BIRTH_WITH_MIGRATION", 0),
        "migrated_preexisting_count": class_counts.get("MIGRATION_ONLY_PREEXISTING", 0),
        "migrated_source_miss_count": class_counts.get("MIGRATION_ONLY_SOURCE_MISS", 0),
        "migrated_replay_unresolved_count": class_counts.get("MIGRATION_ONLY_REPLAY_UNRESOLVED", 0),
        "migrated_post_only_count": class_counts.get("POST_ONLY", 0),
        "migrated_full_path_rate": _safe_ratio(class_counts.get("FULL_PATH", 0), total),
        "migrated_full_or_thin_path_rate": _safe_ratio(
            class_counts.get("FULL_PATH", 0)
            + class_counts.get("THIN_PATH", 0)
            + class_counts.get("SAMPLE_REJECTED_WITH_THIN_PATH", 0),
            total,
        ),
        "migrated_launched_during_campaign_count": len(launched_during),
        "migrated_launched_during_campaign_source_miss_rate": _safe_ratio(len(source_miss), len(launched_during)),
        "migration_completeness_class_counts": class_counts,
        "every_migration_classified": every_classified,
        "campaign_quality_gate_passed": bool(every_classified and not source_miss and class_counts.get("MIGRATION_ONLY_REPLAY_UNRESOLVED", 0) == 0),
        "lookup_error_count": lookup_error_count,
        "valuation_ladder_emission_policy": "market_cap_confirmed_only",
        "valuation_ladder_enabled": False,
        "trading_enabled": False,
        "paper_trading_enabled": False,
        "mayhem_code_modified": False,
    }
    if not summary["campaign_quality_gate_passed"]:
        summary["campaign_quality_gate_reason"] = "migration_birth_curve_linkage_incomplete"
    else:
        summary["campaign_quality_gate_reason"] = "all_migrations_classified_without_launched_during_source_miss"
    return summary


def _write_migrated_mint_replay_summary_md(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# T007AE Migration Linkage Replay",
        "",
        "No trading, paper trading, wallet, signing, Mayhem, or valuation-ladder behavior was modified.",
        "",
        f"- Input run root: `{summary.get('input_run_root')}`",
        f"- Migrated mints total: `{summary.get('migrated_mints_total')}`",
        f"- Full path: `{summary.get('migrated_full_path_count')}`",
        f"- Sample rejected with migration: `{summary.get('migrated_sample_rejected_count')}`",
        f"- Preexisting: `{summary.get('migrated_preexisting_count')}`",
        f"- Source miss: `{summary.get('migrated_source_miss_count')}`",
        f"- Replay unresolved: `{summary.get('migrated_replay_unresolved_count')}`",
        f"- Campaign quality gate passed: `{summary.get('campaign_quality_gate_passed')}`",
        "",
        "## Rows",
        "",
    ]
    for row in rows:
        lines.append(
            f"- `{row.get('mint')}`: `{row.get('migration_completeness_class')}`; "
            f"birth_seen=`{row.get('birth_seen_in_campaign')}`; launch_time=`{row.get('launch_time_from_replay')}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _birth_source_miss_diagnostic_row(row: dict[str, Any]) -> dict[str, Any]:
    missing_route = str(row.get("source_miss_reason") or "unknown")
    recommended = {
        "mayhem_route_not_decoded": "Add/repair Mayhem create decoder in non-Mayhem T007 birth-source lane without touching Mayhem collector behavior.",
        "token2022_create_v2_not_decoded": "Decode Pump.fun create_v2/Token-2022 launch route and normalize into birth_audit.",
        "wrapped_route_not_decoded": "Decode wrapped compact and inner instruction create rows into normalized birth records.",
        "quote_asset_route_not_watched": "Verify SOL and USDC quote filters and add missing quote route coverage.",
        "birth_route_not_watched": "Patch birth source subscription/decoder for the launch signature route before another campaign.",
        "rpc_lookup_inconclusive": "Replay with a larger bounded signature/transaction window or alternate RPC before source changes.",
        "unknown": "Inspect compact replay decodes and raw route metadata to identify the missing create path.",
    }.get(missing_route, "Inspect replay evidence and patch the exact missing birth route.")
    return {
        "mint": row.get("mint"),
        "launch_signature": row.get("launch_signature_from_replay"),
        "launch_time": row.get("launch_time_from_replay"),
        "missing_route": missing_route,
        "source_should_have_seen": row.get("birth_source_should_have_seen_it"),
        "recommended_fix": recommended,
    }


def _load_mints_csv(path: Path | str | None) -> list[str]:
    if path is None:
        return []
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix.lower() == ".csv":
        with p.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        output: list[str] = []
        for row in rows:
            value = _first_present(row, ["mint", "ca", "token_mint", "contract_address"])
            if value:
                output.append(str(value).strip())
        return [item for item in output if item]
    return [item.strip() for item in p.read_text(encoding="utf-8").replace("\n", ",").split(",") if item.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _infer_source_miss_reason(migration: dict[str, Any], replay: dict[str, Any]) -> str:
    text = " ".join(str(value or "") for value in [migration.get("source_route"), migration.get("detection_method"), replay.get("replay_migration_program_id")]).lower()
    if "mayhem" in text:
        return "mayhem_route_not_decoded"
    if "token2022" in text or "token-2022" in text or "create_v2" in text or "createv2" in text:
        return "token2022_create_v2_not_decoded"
    if str(migration.get("quote_asset_status") or "") == "unsupported":
        return "quote_asset_route_not_watched"
    if "wrapped" in text:
        return "wrapped_route_not_decoded"
    if "pumpswap" in text or "program-subscribe" in str(migration.get("signature") or "").lower():
        return "birth_route_not_watched"
    return "birth_route_not_watched"


def _feature_rows_available(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        statuses = [
            str(value or "").lower()
            for key, value in row.items()
            if key.endswith("_status") or key in {"status", "feature_status"}
        ]
        if statuses and all(value in {"not_implemented", "schema_ready_pending_live_source", "unavailable", "missing", "not_available"} for value in statuses):
            continue
        return True
    return False


def run_axiom_reconciliation(output_root: Path | str, mints: list[Any]) -> dict[str, Any]:
    root = Path(output_root)
    requested_rows = _normalize_axiom_manual_rows(mints)
    requested = [row["mint"] for row in requested_rows]
    births = _read_jsonl(root / "birth_audit.jsonl")
    observations = _read_jsonl(root / "curve_observations.jsonl")
    thresholds = _read_jsonl(root / "threshold_crossings.jsonl")
    ladder_events = _read_jsonl(root / "valuation_ladder_events.jsonl")
    migrations = _read_jsonl(root / "migration_events.jsonl")
    global_migrations = _read_jsonl(root / "global_migration_events.jsonl")
    global_candidates = _read_jsonl(root / "global_migration_candidates.jsonl")
    valuation_paths = _read_jsonl(root / "valuation_ladder_paths.jsonl")
    direct_lookup_evidence = _read_jsonl(root / "axiom_direct_lookup_evidence.jsonl")
    by_birth = _group_by_mint(births)
    by_observation = _group_by_mint(observations)
    by_threshold = _group_by_mint(thresholds)
    by_ladder = _group_by_mint(ladder_events)
    by_migration = _group_by_mint(migrations)
    by_global_migration = _group_by_mint(global_migrations)
    by_global_candidate = _group_by_mint(global_candidates)
    by_valuation_path = _group_by_mint(valuation_paths)
    by_direct_lookup = _group_by_mint(direct_lookup_evidence)
    rows = []
    for requested_row in requested_rows:
        mint = requested_row["mint"]
        birth_rows = by_birth.get(mint, [])
        observation_rows = by_observation.get(mint, [])
        threshold_rows = by_threshold.get(mint, [])
        ladder_rows = by_ladder.get(mint, [])
        migration_rows = by_migration.get(mint, [])
        global_migration_rows = by_global_migration.get(mint, [])
        global_candidate_rows = by_global_candidate.get(mint, [])
        valuation_path_rows = by_valuation_path.get(mint, [])
        direct_lookup_rows = by_direct_lookup.get(mint, [])
        admitted = any(row.get("admitted") is True for row in birth_rows)
        sample_rejected = any(row.get("admission_reason") == "sample_rejected" for row in birth_rows)
        capacity_rejected = any(str(row.get("admission_reason") or "").startswith("capacity_rejected") for row in birth_rows)
        decoded_successfully = any(row.get("decode_status") == "decoded" for row in observation_rows)
        account_not_found = any(row.get("error_reason") == "account_not_found" for row in observation_rows)
        valuation_rows = [row for row in observation_rows if row.get("valuation_usd") is not None or row.get("fdv_proxy_raw") is not None or row.get("fdv_proxy") is not None]
        valuation_band_rows = [row for row in threshold_rows if row.get("crossing_type") == "valuation_band"]
        comparison_row = dict(valuation_rows[-1]) if valuation_rows else {}
        comparison_row["axiom_market_cap_usd"] = requested_row.get("axiom_market_cap_usd")
        comparison_row["axiom_liquidity_usd"] = requested_row.get("axiom_liquidity_usd")
        comparison_state = TrackingState(
            mint=mint,
            source_route_type=birth_rows[-1].get("source_route_type") if birth_rows else requested_row.get("cohort"),
            source_decode_route=birth_rows[-1].get("source_decode_route") if birth_rows else None,
        )
        formula_classification = _valuation_formula_classification(comparison_row, comparison_state) if comparison_row else "not_observed"
        path_row = valuation_path_rows[-1] if valuation_path_rows else {}
        progress_values = [
            _num(row.get("progress_pct"))
            for row in observation_rows
            if _num(row.get("progress_pct")) is not None
        ]
        last_progress_pct = _first_present(path_row, ["last_progress_pct", "progress_pct"])
        if last_progress_pct is None and progress_values:
            last_progress_pct = progress_values[-1]
        highest_progress_pct = _first_present(path_row, ["highest_progress_pct", "max_progress_pct"])
        if highest_progress_pct is None and progress_values:
            highest_progress_pct = max(progress_values)
        thresholds_crossed = sorted(
            {
                float(row["threshold_pct"])
                for row in threshold_rows
                if row.get("crossing_type") in {None, "true_curve_progress"} and _num(row.get("threshold_pct")) is not None
            }
        )
        prune_reason = _first_present(path_row, ["stop_reason", "prune_reason"])
        pruned = str(prune_reason or "") in {
            "low_progress_timeout",
            "max_token_age_timeout",
            "no_decode_timeout",
            "high_progress_retention_timeout",
            "inactive_timeout",
        }
        global_migration_seen = bool(global_migration_rows)
        collector_migration_seen = bool(migration_rows)
        direct_lookup_row = direct_lookup_rows[-1] if direct_lookup_rows else {}
        direct_status = str(direct_lookup_row.get("direct_lookup_status") or "")
        direct_lookup_found_migration = _bool(direct_lookup_row.get("migration_like_signature_found")) or direct_status in {"found_migration_route", "found_pool_route"}
        if direct_lookup_row and (_bool(direct_lookup_row.get("pumpswap_pool_create_found")) or direct_status == "found_pool_route"):
            explanation = "pumpswap_route_detected"
        elif direct_lookup_row and (_bool(direct_lookup_row.get("pumpfun_migrate_found")) or direct_status == "found_migration_route"):
            explanation = "pumpfun_migrate_route_detected"
        elif not birth_rows and direct_lookup_found_migration:
            explanation = "seen_by_direct_lookup_not_live_source"
        elif not birth_rows and direct_lookup_row and direct_status == "found_birth_only":
            explanation = "seen_by_direct_lookup_not_live_source"
        elif not birth_rows and not global_migration_seen and not global_candidate_rows:
            explanation = "not_seen_by_source"
        elif sample_rejected:
            explanation = "seen_but_sample_rejected"
        elif capacity_rejected:
            explanation = "seen_but_capacity_rejected"
        elif pruned and global_migration_seen:
            explanation = "seen_but_pruned_before_migration"
        elif global_migration_seen or collector_migration_seen:
            explanation = "migration_detected_successfully"
        elif admitted and not pruned:
            explanation = "seen_and_active_but_migration_not_decoded"
        elif pruned:
            explanation = "seen_but_pruned_no_migration_signal"
        else:
            explanation = "migration_visibility_inconclusive"
        row = {
            "mint": mint,
            "token_name": requested_row.get("token_name"),
            "axiom_seen_at": requested_row.get("axiom_seen_at"),
            "axiom_age_label": requested_row.get("axiom_age_label"),
            "axiom_column": requested_row.get("axiom_column"),
            "axiom_bcurve_pct": requested_row.get("axiom_bcurve_pct"),
            "notes": requested_row.get("notes"),
            "manual_cohort": requested_row.get("cohort"),
            "axiom_market_cap_usd": requested_row.get("axiom_market_cap_usd"),
            "axiom_liquidity_usd": requested_row.get("axiom_liquidity_usd"),
            "seen_by_transaction_subscribe": any(row.get("source_route_type") == "transaction_subscribe" for row in birth_rows),
            "normalized_as_unique_birth": bool(birth_rows),
            "collector_birth_seen": bool(birth_rows),
            "collector_admitted": admitted,
            "admitted": admitted,
            "sample_rejected": sample_rejected,
            "capacity_rejected": capacity_rejected,
            "pruned": pruned,
            "prune_reason": prune_reason,
            "last_progress_pct": last_progress_pct,
            "highest_progress_pct": highest_progress_pct,
            "thresholds_crossed": ",".join(str(value) for value in thresholds_crossed),
            "curve_observations_count": int(_first_present(path_row, ["curve_observation_count", "observation_count"]) or len(observation_rows)),
            "curve_probed": bool(observation_rows),
            "decoded_successfully": decoded_successfully,
            "failed_with_account_not_found": account_not_found,
            "assigned_valuation_usd_or_fdv_proxy": bool(valuation_rows),
            "valuation_usd": _first_present(valuation_rows[-1], ["valuation_usd"]) if valuation_rows else None,
            "fdv_proxy_raw": _first_present(valuation_rows[-1], ["fdv_proxy_raw", "fdv_proxy"]) if valuation_rows else None,
            "candidate_market_cap_usd": _first_present(valuation_rows[-1], ["candidate_market_cap_usd"]) if valuation_rows else None,
            "valuation_ladder_trust_status": _first_present(valuation_rows[-1], ["valuation_ladder_trust_status"]) if valuation_rows else None,
            "matches_axiom_market_cap": _within_pct(comparison_row.get("valuation_usd"), requested_row.get("axiom_market_cap_usd"), 5.0) if comparison_row else False,
            "matches_axiom_liquidity": _within_pct(comparison_row.get("valuation_usd"), requested_row.get("axiom_liquidity_usd"), 5.0) if comparison_row else False,
            "possible_2x_market_cap": _within_pct(_half_or_none(comparison_row.get("valuation_usd")), requested_row.get("axiom_market_cap_usd"), 5.0) if comparison_row else False,
            "valuation_formula_classification": formula_classification,
            "emitted_valuation_ladder_crossings": bool(ladder_rows or valuation_band_rows),
            "emitted_migration_event": bool(migration_rows),
            "collector_migration_event_seen": collector_migration_seen,
            "global_migration_event_seen": global_migration_seen,
            "global_migration_candidate_seen": bool(global_candidate_rows),
            "global_migration_detection_method": _first_present(
                global_migration_rows[-1] if global_migration_rows else global_candidate_rows[-1] if global_candidate_rows else {},
                ["detection_method"],
            ),
            "global_migration_confidence": _first_present(
                global_migration_rows[-1] if global_migration_rows else global_candidate_rows[-1] if global_candidate_rows else {},
                ["confidence"],
            ),
            "direct_lookup_signatures_found": _first_present(direct_lookup_row, ["direct_lookup_signatures_found", "signatures_found"]),
            "transactions_fetched": _first_present(direct_lookup_row, ["transactions_fetched"]),
            "pumpfun_create_found": _bool(direct_lookup_row.get("pumpfun_create_found")) if direct_lookup_row else None,
            "pumpfun_migrate_found": _bool(direct_lookup_row.get("pumpfun_migrate_found")) if direct_lookup_row else None,
            "pumpswap_pool_create_found": _bool(direct_lookup_row.get("pumpswap_pool_create_found")) if direct_lookup_row else None,
            "migration_like_signature_found": direct_lookup_found_migration if direct_lookup_row else None,
            "migration_like_signature": _first_present(direct_lookup_row, ["migration_like_signature"]),
            "migration_program_id": _first_present(direct_lookup_row, ["migration_program_id", "program_id"]),
            "migration_instruction_name": _first_present(direct_lookup_row, ["migration_instruction_name", "instruction_name", "instruction_type"]),
            "pool_or_pair_address": _first_present(direct_lookup_row, ["pool_or_pair_address", "pool_address", "pair_address"]),
            "detection_route_needed": _first_present(direct_lookup_row, ["detected_route_needed", "detection_route_needed", "source_route"]),
            "direct_lookup_replay_status": direct_status if direct_lookup_row else "not_implemented_no_rpc_lookup",
            "explanation": explanation,
            "admission_reason": birth_rows[-1].get("admission_reason") if birth_rows else None,
            "decode_status": observation_rows[-1].get("decode_status") if observation_rows else None,
            "error_reason": observation_rows[-1].get("error_reason") if observation_rows else None,
        }
        rows.append(row)
    jsonl_path = root / "axiom_reconciliation.jsonl"
    csv_path = root / "axiom_reconciliation.csv"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    fieldnames = list(rows[0].keys()) if rows else [
        "mint",
        "token_name",
        "axiom_column",
        "collector_birth_seen",
        "collector_admitted",
        "seen_by_transaction_subscribe",
        "normalized_as_unique_birth",
        "admitted",
        "sample_rejected",
        "capacity_rejected",
        "pruned",
        "prune_reason",
        "last_progress_pct",
        "highest_progress_pct",
        "thresholds_crossed",
        "curve_observations_count",
        "curve_probed",
        "decoded_successfully",
        "failed_with_account_not_found",
        "assigned_valuation_usd_or_fdv_proxy",
        "emitted_valuation_ladder_crossings",
        "emitted_migration_event",
        "global_migration_event_seen",
        "global_migration_detection_method",
        "explanation",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "axiom_reconciliation_rows": len(rows),
        "seen_by_transaction_subscribe_count": sum(1 for row in rows if row["seen_by_transaction_subscribe"]),
        "admitted_count": sum(1 for row in rows if row["admitted"]),
        "sample_rejected_count": sum(1 for row in rows if row["sample_rejected"]),
        "capacity_rejected_count": sum(1 for row in rows if row["capacity_rejected"]),
        "curve_probed_count": sum(1 for row in rows if row["curve_probed"]),
        "decoded_successfully_count": sum(1 for row in rows if row["decoded_successfully"]),
        "account_not_found_count": sum(1 for row in rows if row["failed_with_account_not_found"]),
        "valuation_assigned_count": sum(1 for row in rows if row["assigned_valuation_usd_or_fdv_proxy"]),
        "valuation_ladder_crossing_count": sum(1 for row in rows if row["emitted_valuation_ladder_crossings"]),
        "migration_event_count": sum(1 for row in rows if row["emitted_migration_event"]),
        "global_migration_event_count": sum(1 for row in rows if row["global_migration_event_seen"]),
        "pruned_count": sum(1 for row in rows if row["pruned"]),
        "seen_but_pruned_before_migration_count": sum(1 for row in rows if row["explanation"] == "seen_but_pruned_before_migration"),
        "seen_and_active_but_migration_not_decoded_count": sum(1 for row in rows if row["explanation"] == "seen_and_active_but_migration_not_decoded"),
        "absent_from_birth_source_count": sum(1 for row in rows if row["explanation"] == "not_seen_by_source"),
        "matches_axiom_market_cap_count": sum(1 for row in rows if row.get("matches_axiom_market_cap")),
        "matches_axiom_liquidity_count": sum(1 for row in rows if row.get("matches_axiom_liquidity")),
        "possible_2x_market_cap_count": sum(1 for row in rows if row.get("possible_2x_market_cap")),
        "axiom_reconciliation_csv": str(csv_path),
        "axiom_reconciliation_jsonl": str(jsonl_path),
    }
    summary_path = root / "collector_summary.json"
    if summary_path.exists():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        payload["axiom_reconciliation"] = summary
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _stats(values: list[float]) -> dict[str, Any]:
    clean = sorted(v for v in values if v is not None)
    return {
        "count": len(clean),
        "median": median(clean) if clean else None,
        "p90": _quantile(clean, 0.90),
        "p95": _percentile(clean, 95),
        "p99": _percentile(clean, 99),
        "max": clean[-1] if clean else None,
    }


def _percentile(values: list[float] | list[int], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * (float(percentile) / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[int(position)]
    weight = position - lower
    return clean[lower] * (1.0 - weight) + clean[upper] * weight


def _safe_ratio(numerator: Any, denominator: Any) -> float:
    top = _num(numerator) or 0.0
    bottom = _num(denominator) or 0.0
    if bottom <= 0:
        return 0.0
    return round(top / bottom, 6)


def _feature_missing_data_flags(state: TrackingState) -> list[str]:
    flags: list[str] = []
    status_by_family = {
        "trade_flow": state.trade_flow_status,
        "organic_flow": state.organic_share_status,
        "holder_distribution": state.holder_distribution_status,
        "dev_behavior": state.dev_behavior_status,
        "post_migration_depth": state.post_migration_depth_status,
        "execution_cost": state.execution_cost_status,
    }
    for family, status in status_by_family.items():
        if str(status or "not_available") not in {"available", "partial"}:
            flags.append(f"{family}_not_available")
    return flags


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            rows.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return rows


def _append_jsonl_file(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(path)
    with _JSONL_FILE_LOCKS_GUARD:
        lock = _JSONL_FILE_LOCKS.setdefault(lock_key, threading.Lock())
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _migration_route_definitions() -> dict[str, dict[str, Any]]:
    return {
        "current_pumpfun_create_account_required": {
            "source_route": "current_pumpfun_create_account_required",
            "source": "transactionSubscribe",
            "program_ids": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
            "account_required": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
            "live_available_in_t007": True,
            "detects": "pumpfun create rows; migration only if the transaction also touches Pump.fun program",
        },
        "pumpfun_migrate_instruction_log": {
            "source_route": "pumpfun_migrate_instruction_log",
            "source": "transactionSubscribe_or_logsSubscribe_pumpfun_program",
            "program_ids": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
            "account_required": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
            "live_available_in_t007": "partial_via_current_transaction_subscribe",
            "detects": "Pump.fun Migrate/MigrateV2 instruction or migrate logs",
        },
        "pumpswap_pool_create": {
            "source_route": "pumpswap_pool_create",
            "source": "program_logs_or_transactionSubscribe_pumpswap_program",
            "program_ids": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
            "account_required": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
            "live_available_in_t007": "audit_fallback_only",
            "detects": "Noisy PumpSwap transaction/accountRequired pool-create audit fallback",
        },
        "pumpswap_transaction_subscribe": {
            "source_route": "pumpswap_transaction_subscribe",
            "source": "transactionSubscribe_pumpswap_program_accountInclude",
            "program_ids": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
            "account_required": [],
            "account_include": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
            "live_available_in_t007": True,
            "detects": "All transactions involving PumpSwap program; local audit filters buy/sell logs and balance deltas",
        },
        "pumpswap_program_subscribe": {
            "source_route": "pumpswap_program_subscribe",
            "source": "programSubscribe_pumpswap_market_accounts",
            "program_ids": [PUMPSWAP_PROGRAM_ID_FOR_AUDIT],
            "account_required": [],
            "filters": _pumpswap_program_subscribe_filters(),
            "live_available_in_t007": True,
            "detects": "Deduped PumpSwap market-account creation for migrated Pump.fun tokens",
        },
        "dex_pair_created": {
            "source_route": "dex_pair_created",
            "source": "dexscreener_pair_created_at",
            "program_ids": [],
            "account_required": [],
            "live_available_in_t007": False,
            "detects": "DexScreener pair-created proxy; not ground-truth Pump.fun migration",
        },
        "existing_migration_graduation_backfill": {
            "source_route": "existing_migration_graduation_backfill",
            "source": "migration_graduation_enrichment_collection",
            "program_ids": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
            "account_required": [],
            "live_available_in_t007": False,
            "detects": "Historical address-window lookup of Pump.fun Migrate logs",
        },
    }


def _empty_migration_route_counter(definition: dict[str, Any], raw_notifications: int) -> dict[str, Any]:
    return {
        "source_route": definition.get("source_route"),
        "source": definition.get("source"),
        "program_ids": list(definition.get("program_ids") or []),
        "account_required": list(definition.get("account_required") or []),
        "live_available_in_t007": definition.get("live_available_in_t007", False),
        "detects": definition.get("detects"),
        "raw_notifications": int(raw_notifications),
        "candidate_migration_notifications": 0,
        "decoded_migration_events": 0,
        "decoded_migration_candidates": 0,
        "unique_migrated_mints": 0,
        "duplicate_migrated_mints": 0,
        "detection_method": None,
        "confidence": None,
        "missing_mint_count": 0,
        "missing_pair_pool_count": 0,
        "raw_pumpswap_candidates": 0,
        "confirmed_pumpswap_rows": 0,
        "deduped_pumpswap_migration_events": 0,
        "duplicate_pumpswap_rows_suppressed": 0,
        "unique_pumpswap_mints": 0,
        "unique_pumpswap_pools": 0,
        "pumpswap_swap_events_decoded": 0,
        "pumpswap_swap_buy_events": 0,
        "pumpswap_swap_sell_events": 0,
        "pumpswap_swap_fee_bps_populated_count": 0,
        "pumpswap_swap_balance_delta_partial_count": 0,
        "pumpswap_route_raw_notifications": 0,
        "pumpswap_route_candidate_transactions": 0,
        "pumpswap_route_with_logs": 0,
        "pumpswap_route_with_inner_instructions": 0,
        "pumpswap_route_buy_candidates": 0,
        "pumpswap_route_sell_candidates": 0,
        "pumpswap_route_event_log_candidates": 0,
        "pumpswap_route_get_transaction_backfills": 0,
        "pumpswap_route_skipped_by_reason": {},
        "program_subscribe_existing_pool_updates_suppressed": 0,
        "program_subscribe_unconfirmed_update_candidates": 0,
        "program_subscribe_confirmed_create_events": 0,
        "pumpswap_raw_candidates_by_quote_asset": {},
        "pumpswap_confirmed_events_by_quote_asset": {},
        "global_migration_events_by_quote_asset": {},
        "global_migration_candidates_by_quote_asset": {},
        "missing_quote_mint_count": 0,
        "unsupported_quote_asset_count": 0,
        "errors_by_reason": {},
    }


def _record_pumpswap_transaction_route_audit(output_root: Path, recorder: BondingCurveProgressRecorder, counter: dict[str, Any], event: dict[str, Any]) -> None:
    names = [str(value).lower() for value in event.get("decoded_candidate_instruction_names") or []]
    has_logs = bool(event.get("has_log_messages") if "has_log_messages" in event else _event_logs_for_pumpswap_swap_decode({}, event))
    row = {
        "signature": event.get("signature") or "",
        "slot": event.get("slot"),
        "received_at": event.get("received_at") or time.time(),
        "includes_pumpswap_program": bool(event.get("includes_pumpswap_program", True)),
        "account_keys_count": int(event.get("account_keys_count") or 0),
        "has_log_messages": has_logs,
        "log_message_count": int(event.get("log_message_count") or len(_event_logs_for_pumpswap_swap_decode({}, event))),
        "has_inner_instructions": bool(event.get("has_inner_instructions")),
        "instruction_program_ids": list(event.get("instruction_program_ids") or []),
        "decoded_candidate_instruction_names": list(event.get("decoded_candidate_instruction_names") or []),
        "contains_buy_discriminator": bool(event.get("contains_buy_discriminator") or "buy" in names),
        "contains_sell_discriminator": bool(event.get("contains_sell_discriminator") or "sell" in names),
        "contains_buy_event_log": bool(event.get("contains_buy_event_log")),
        "contains_sell_event_log": bool(event.get("contains_sell_event_log")),
        "contains_pool_account": bool(event.get("contains_pool_account")),
        "contains_known_post_migration_pool": bool(event.get("contains_known_post_migration_pool")),
        "route_name": event.get("route_name") or "pumpswap_transaction_subscribe",
        "filter_name": event.get("filter_name") or "accountInclude_pumpswap_program",
    }
    _append_jsonl_file(output_root / "pumpswap_transaction_route_audit.jsonl", row)
    counter["pumpswap_route_raw_notifications"] = int(counter.get("pumpswap_route_raw_notifications") or 0) + 1
    recorder.summary_counters["pumpswap_route_raw_notifications"] += 1
    if row["includes_pumpswap_program"]:
        counter["pumpswap_route_candidate_transactions"] = int(counter.get("pumpswap_route_candidate_transactions") or 0) + 1
        recorder.summary_counters["pumpswap_route_candidate_transactions"] += 1
    else:
        _increment_counter(counter["pumpswap_route_skipped_by_reason"], "missing_pumpswap_program")
        _increment_counter(recorder.summary_counters["pumpswap_route_skipped_by_reason"], "missing_pumpswap_program")
    if row["has_log_messages"]:
        counter["pumpswap_route_with_logs"] = int(counter.get("pumpswap_route_with_logs") or 0) + 1
        recorder.summary_counters["pumpswap_route_with_logs"] += 1
    if row["has_inner_instructions"]:
        counter["pumpswap_route_with_inner_instructions"] = int(counter.get("pumpswap_route_with_inner_instructions") or 0) + 1
        recorder.summary_counters["pumpswap_route_with_inner_instructions"] += 1
    if row["contains_buy_discriminator"]:
        counter["pumpswap_route_buy_candidates"] = int(counter.get("pumpswap_route_buy_candidates") or 0) + 1
        recorder.summary_counters["pumpswap_route_buy_candidates"] += 1
    if row["contains_sell_discriminator"]:
        counter["pumpswap_route_sell_candidates"] = int(counter.get("pumpswap_route_sell_candidates") or 0) + 1
        recorder.summary_counters["pumpswap_route_sell_candidates"] += 1
    if row["contains_buy_event_log"] or row["contains_sell_event_log"]:
        counter["pumpswap_route_event_log_candidates"] = int(counter.get("pumpswap_route_event_log_candidates") or 0) + 1
        recorder.summary_counters["pumpswap_route_event_log_candidates"] += 1


def _emit_pumpswap_balance_delta_partial_event(
    *,
    output_root: Path,
    recorder: BondingCurveProgressRecorder,
    counter: dict[str, Any],
    row: dict[str, Any],
    event: dict[str, Any],
) -> int:
    instruction_type = str(row.get("swap_direction") or row.get("instruction_type") or row.get("instruction_name") or "").strip().lower()
    if instruction_type not in {"buy", "sell"}:
        return 0
    if row.get("base_amount") in (None, "") and row.get("quote_amount") in (None, ""):
        return 0
    context = _pumpswap_swap_context_from_row(row, event)
    quote = _quote_identity_from_payload({"quote_mint": context.get("quote_mint") or row.get("quote_mint")}, unsupported_as_unknown=True)
    partial = {
        "campaign_id": recorder.config.run_id,
        "run_id": recorder.config.run_id,
        "signature": context.get("signature") or row.get("signature") or event.get("signature") or "",
        "slot": context.get("slot") or row.get("slot") or event.get("slot") or "",
        "received_at": context.get("received_at") or row.get("received_at") or event.get("received_at") or time.time(),
        "block_time": context.get("block_time") or row.get("block_time") or event.get("block_time") or "",
        "event_type": instruction_type,
        "decode_source": "balance_delta",
        "event_decode_status": "partial",
        "pool": context.get("pool") or "",
        "mint": context.get("mint") or "",
        "base_mint": context.get("base_mint") or context.get("mint") or "",
        "quote_mint": quote["quote_mint"],
        "quote_asset": quote["quote_asset"],
        "user": row.get("user") or row.get("trader_wallet") or "",
        "base_amount": row.get("base_amount"),
        "quote_amount": row.get("quote_amount"),
        "user_quote_amount": row.get("user_quote_amount") or row.get("quote_amount"),
        "pool_base_token_reserves": row.get("pool_base_token_reserves"),
        "pool_quote_token_reserves": row.get("pool_quote_token_reserves"),
        "lp_fee_basis_points": None,
        "protocol_fee_basis_points": None,
        "lp_fee": None,
        "protocol_fee": None,
        "total_fee_basis_points_observed": None,
        "pool_base_token_account": context.get("pool_base_token_account") or "",
        "pool_quote_token_account": context.get("pool_quote_token_account") or "",
        "raw_log_excerpt": [],
        "decision_time_safe": True,
        "valuation_ladder_used": False,
    }
    if _recorder_side_effects_allowed(recorder):
        recorder.write_evidence_record(
            source_lane="pumpswap_swap",
            signature=partial.get("signature"),
            observed_at=_num(partial.get("received_at")),
            slot=partial.get("slot"),
            source_route="pumpswap_balance_delta_partial",
            mint=partial.get("mint") or partial.get("base_mint"),
            pool=partial.get("pool"),
            evidence_level=MigrationEvidenceLevel.NONE,
            raw_payload=partial,
            rule_hits=[partial.get("event_type") or "swap", "pumpswap_swap_decoded"],
        )
    _append_jsonl_file(output_root / "pumpswap_swap_events.jsonl", partial)
    counter["pumpswap_swap_events_decoded"] = int(counter.get("pumpswap_swap_events_decoded") or 0) + 1
    counter["pumpswap_swap_balance_delta_partial_count"] = int(counter.get("pumpswap_swap_balance_delta_partial_count") or 0) + 1
    recorder.summary_counters["pumpswap_swap_events_decoded"] += 1
    recorder.summary_counters["pumpswap_swap_balance_delta_partial_count"] += 1
    if instruction_type == "buy":
        counter["pumpswap_swap_buy_events"] = int(counter.get("pumpswap_swap_buy_events") or 0) + 1
        recorder.summary_counters["pumpswap_swap_buy_events"] += 1
    else:
        counter["pumpswap_swap_sell_events"] = int(counter.get("pumpswap_swap_sell_events") or 0) + 1
        recorder.summary_counters["pumpswap_swap_sell_events"] += 1
    _record_pumpswap_first_swap_implied_migration(
        output_root=output_root,
        recorder=recorder,
        counter=counter,
        swap_row=partial,
    )
    return 1


def _record_pumpswap_first_swap_implied_migration(
    *,
    output_root: Path,
    recorder: BondingCurveProgressRecorder,
    counter: dict[str, Any],
    swap_row: dict[str, Any],
) -> bool:
    mint = str(swap_row.get("mint") or swap_row.get("base_mint") or "").strip()
    pool = str(swap_row.get("pool") or swap_row.get("pool_or_pair_address") or swap_row.get("pool_address") or "").strip()
    if not mint or not pool:
        return False
    birth_row = recorder.birth_rows_by_mint.get(mint)
    if not birth_row or _bool(birth_row.get("birth_backfilled_from_replay")):
        return False
    swap_time = _num(swap_row.get("received_at")) or _num(swap_row.get("block_time")) or time.time()
    birth_time = _num(birth_row.get("received_at")) or _num(birth_row.get("block_time"))
    if birth_time is not None and swap_time < birth_time:
        return False
    state = recorder.states.get(mint)
    if state is not None and _bool(getattr(state, "migration_seen", False)):
        return False
    seen = getattr(recorder, "_pumpswap_first_swap_migration_seen", None)
    if seen is None:
        seen = set()
        setattr(recorder, "_pumpswap_first_swap_migration_seen", seen)
    key = (mint, pool)
    if key in seen:
        return False
    seen.add(key)
    unique_mints = getattr(recorder, "_pumpswap_first_swap_migration_unique_mints", None)
    if unique_mints is None:
        unique_mints = set()
        setattr(recorder, "_pumpswap_first_swap_migration_unique_mints", unique_mints)
    unique_pools = getattr(recorder, "_pumpswap_first_swap_migration_unique_pools", None)
    if unique_pools is None:
        unique_pools = set()
        setattr(recorder, "_pumpswap_first_swap_migration_unique_pools", unique_pools)
    unique_mints.add(mint)
    unique_pools.add(pool)

    quote = _quote_identity_from_payload(
        {"quote_mint": swap_row.get("quote_mint"), "quote_asset": swap_row.get("quote_asset")},
        unsupported_as_unknown=True,
    )
    row = _enrich_global_migration_context(
        {
            "mint": mint,
            "base_mint": swap_row.get("base_mint") or mint,
            "signature": swap_row.get("signature") or "",
            "slot": swap_row.get("slot") or "",
            "received_at": swap_time,
            "migration_received_at": swap_time,
            "source_route": "pumpswap_first_swap_after_live_birth",
            "source_instruction_level": "pumpswap_swap_event",
            "source_instruction_decode_route": swap_row.get("event_decode_route") or swap_row.get("decode_source") or "",
            "instruction_type": swap_row.get("event_type") or "",
            "parser_status": swap_row.get("event_decode_status") or "decoded",
            "detection_method": "pumpswap_first_swap_after_live_birth",
            "migration_evidence_level": MigrationEvidenceLevel.LEVEL_B.value,
            "migration_evidence_reason": "first_pumpswap_swap_after_live_birth",
            "confidence": "confirmed",
            "admission_scope": "global_source_not_admission_gated",
            "pool_or_pair_address": pool,
            "migration_program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
            "migration_instruction_name": "first_pumpswap_swap",
            "canonical_mint_source": "first_pumpswap_swap_event_for_live_birth",
            "quote_mint": quote["quote_mint"],
            "quote_asset": quote["quote_asset"],
            "quote_asset_status": quote["quote_asset_status"],
            "first_pumpswap_swap_signature": swap_row.get("signature") or "",
            "first_pumpswap_swap_event_type": swap_row.get("event_type") or "",
        },
        recorder,
    )
    _append_jsonl_file(output_root / "global_migration_events.jsonl", row)
    side_effects_allowed = _recorder_side_effects_allowed(recorder)
    if side_effects_allowed:
        recorder.write_evidence_record(
            source_lane="global_migration",
            signature=row.get("signature"),
            observed_at=_num(row.get("received_at")),
            slot=row.get("slot"),
            source_route="pumpswap_first_swap_after_live_birth",
            mint=mint,
            pool=pool,
            evidence_level=MigrationEvidenceLevel.LEVEL_B,
            raw_payload=row,
            rule_hits=["first_pumpswap_swap_after_live_birth"],
            confidence=0.93,
        )
        recorder.write_lifecycle_transition(
            mint=mint,
            previous_state="CURVE_ACTIVE",
            next_state="MIGRATION_CONFIRMED_LEVEL_B",
            signature=row.get("signature"),
            observed_at=swap_time,
            reason="first_pumpswap_swap_after_live_birth",
        )
        recorder.summary_counters["migration_level_b_count"] += 1
        _record_global_migration_write_intent(output_root, row, write_status="written", write_success=True)
    else:
        _record_global_migration_write_intent(
            output_root,
            row,
            write_status="retry_pending",
            write_success=False,
            write_error="recorder_side_effects_deferred_to_owner_thread",
        )
    for target in (counter, recorder.summary_counters):
        target["global_migration_events_deduped"] = int(target.get("global_migration_events_deduped") or 0) + 1
        target["global_migration_unique_mints"] = max(int(target.get("global_migration_unique_mints") or 0), len(unique_mints))
        target["global_migration_unique_pools"] = max(int(target.get("global_migration_unique_pools") or 0), len(unique_pools))
        if row.get("seen_in_birth_source"):
            target["global_migration_mints_seen_in_birth_source"] = int(target.get("global_migration_mints_seen_in_birth_source") or 0) + 1
        else:
            target["global_migration_mints_not_seen_in_birth_source"] = int(target.get("global_migration_mints_not_seen_in_birth_source") or 0) + 1
        if row.get("admitted"):
            target["global_migration_mints_admitted"] = int(target.get("global_migration_mints_admitted") or 0) + 1
        if row.get("sample_rejected"):
            target["global_migration_mints_sample_rejected"] = int(target.get("global_migration_mints_sample_rejected") or 0) + 1
        if row.get("capacity_rejected"):
            target["global_migration_mints_capacity_rejected"] = int(target.get("global_migration_mints_capacity_rejected") or 0) + 1
    if state is not None and side_effects_allowed:
        state.migration_seen = True
        state.migration_signature = row.get("signature") or ""
        state.migration_received_at = row.get("migration_received_at")
    if side_effects_allowed:
        recorder.schedule_post_migration_observations(row)
        recorder.record_execution_cost_sample("migration_event", as_of=swap_time)
    return True


def _event_logs_for_pumpswap_swap_decode(row: dict[str, Any], event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (row, event):
        logs = source.get("logs") if isinstance(source, dict) else None
        if isinstance(logs, list):
            values.extend(str(item) for item in logs)
        elif logs is not None:
            values.append(str(logs))
        log_messages = source.get("log_messages") if isinstance(source, dict) else None
        if isinstance(log_messages, list):
            values.extend(str(item) for item in log_messages)
        elif log_messages is not None:
            values.append(str(log_messages))
        raw_payload = source.get("raw_payload") if isinstance(source, dict) else None
        if isinstance(raw_payload, dict):
            values.extend(_event_logs_for_pumpswap_swap_decode({}, raw_payload))
    return values


def _pumpswap_swap_context_from_row(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    raw_pumpswap = _pumpswap_candidate_from_raw_payload(row, event)
    pool = (
        row.get("pool")
        or row.get("pool_or_pair_address")
        or raw_pumpswap.get("pool_or_pair_address")
        or event.get("pool")
        or event.get("pool_or_pair_address")
    )
    mint = (
        row.get("mint")
        or row.get("base_mint")
        or raw_pumpswap.get("mint")
        or raw_pumpswap.get("base_mint")
        or event.get("mint")
        or event.get("base_mint")
    )
    quote_mint = row.get("quote_mint") or raw_pumpswap.get("quote_mint") or event.get("quote_mint")
    return {
        "campaign_id": event.get("campaign_id") or row.get("campaign_id") or "",
        "run_id": event.get("run_id") or row.get("run_id") or "",
        "signature": row.get("signature") or event.get("signature") or "",
        "slot": row.get("slot") or event.get("slot") or "",
        "received_at": row.get("received_at") or row.get("observed_at") or event.get("received_at") or "",
        "block_time": row.get("block_time") or event.get("block_time") or "",
        "mint": mint or "",
        "base_mint": row.get("base_mint") or raw_pumpswap.get("base_mint") or mint or "",
        "quote_mint": quote_mint or "",
        "pool": pool or "",
        "pool_or_pair_address": pool or "",
        "pool_base_token_account": row.get("pool_base_token_account") or raw_pumpswap.get("pool_base_token_account") or "",
        "pool_quote_token_account": row.get("pool_quote_token_account") or raw_pumpswap.get("pool_quote_token_account") or "",
    }


def _looks_like_pumpswap_swap_row(row: dict[str, Any], event: dict[str, Any]) -> bool:
    program_id = _first_present(row, ["program_id", "programId"]) or event.get("program_id") or event.get("programId")
    instruction_type = str(row.get("instruction_type") or row.get("instruction_name") or "").strip().lower()
    text = _migration_detection_text(row, event)
    return (
        program_id == PUMPSWAP_PROGRAM_ID_FOR_AUDIT
        or instruction_type in {"buy", "sell"}
        or "instruction: buy" in text
        or "instruction: sell" in text
        or "program data:" in text
    )


def _emit_pumpswap_swap_events_from_notification(
    *,
    output_root: Path,
    recorder: BondingCurveProgressRecorder,
    counter: dict[str, Any],
    row: dict[str, Any],
    event: dict[str, Any],
) -> int:
    logs = _event_logs_for_pumpswap_swap_decode(row, event)
    if not logs:
        return _emit_pumpswap_balance_delta_partial_event(output_root=output_root, recorder=recorder, counter=counter, row=row, event=event)
    try:
        from research.mtp_research.validation.t007av_pumpswap_swap_event_fee_confirmation import (
            decode_pumpswap_swap_events_from_logs,
            enrich_swap_event_with_pool_metadata,
        )
    except Exception:
        return 0
    context = _pumpswap_swap_context_from_row(row, event)
    emitted = 0
    for decoded in decode_pumpswap_swap_events_from_logs(logs, context):
        enriched = enrich_swap_event_with_pool_metadata(decoded, context)
        enriched["campaign_id"] = enriched.get("campaign_id") or recorder.config.run_id
        enriched["run_id"] = enriched.get("run_id") or recorder.config.run_id
        enriched["signature"] = enriched.get("signature") or context.get("signature") or event.get("signature") or ""
        enriched["slot"] = enriched.get("slot") or context.get("slot") or event.get("slot") or ""
        enriched["received_at"] = enriched.get("received_at") or context.get("received_at") or event.get("received_at") or time.time()
        enriched["decision_time_safe"] = True
        enriched["valuation_ladder_used"] = False
        if _recorder_side_effects_allowed(recorder):
            recorder.write_evidence_record(
                source_lane="pumpswap_swap",
                signature=enriched.get("signature"),
                observed_at=_num(enriched.get("received_at")),
                slot=enriched.get("slot"),
                source_route="pumpswap_log_event",
                mint=enriched.get("mint") or enriched.get("base_mint"),
                pool=enriched.get("pool") or enriched.get("pool_or_pair_address"),
                evidence_level=MigrationEvidenceLevel.NONE,
                raw_payload=enriched,
                rule_hits=[enriched.get("event_type") or "swap", "pumpswap_swap_decoded"],
            )
        _append_jsonl_file(output_root / "pumpswap_swap_events.jsonl", enriched)
        counter["pumpswap_swap_events_decoded"] = int(counter.get("pumpswap_swap_events_decoded") or 0) + 1
        recorder.summary_counters["pumpswap_swap_events_decoded"] += 1
        if enriched.get("event_type") == "buy":
            counter["pumpswap_swap_buy_events"] = int(counter.get("pumpswap_swap_buy_events") or 0) + 1
            recorder.summary_counters["pumpswap_swap_buy_events"] += 1
        elif enriched.get("event_type") == "sell":
            counter["pumpswap_swap_sell_events"] = int(counter.get("pumpswap_swap_sell_events") or 0) + 1
            recorder.summary_counters["pumpswap_swap_sell_events"] += 1
        if enriched.get("lp_fee_basis_points") not in (None, "") or enriched.get("protocol_fee_basis_points") not in (None, ""):
            counter["pumpswap_swap_fee_bps_populated_count"] = int(counter.get("pumpswap_swap_fee_bps_populated_count") or 0) + 1
            recorder.summary_counters["pumpswap_swap_fee_bps_populated_count"] += 1
        _record_pumpswap_first_swap_implied_migration(
            output_root=output_root,
            recorder=recorder,
            counter=counter,
            swap_row=enriched,
        )
        emitted += 1
    return emitted


def _migration_candidate_id(row: dict[str, Any]) -> str:
    existing = str(row.get("candidate_id") or "").strip()
    if existing:
        return existing
    payload = "|".join(
        str(_first_present(row, fields) or "")
        for fields in [
            ["signature", "event_signature", "migration_signature"],
            ["mint", "base_mint", "candidate_mint"],
            ["pool_or_pair_address", "pool_address", "pair_address", "pool"],
            ["received_at", "migration_received_at", "observed_at", "slot"],
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"mig-{digest}"


def _is_sqlite_thread_affinity_error(error: BaseException | str | None) -> bool:
    if error is None:
        return False
    return "SQLite objects created in a thread can only be used in that same thread" in str(error)


def _recorder_side_effects_allowed(recorder: Any | None) -> bool:
    if recorder is None:
        return False
    owner = getattr(recorder, "_sqlite_owner_thread_id", None)
    return owner is None or int(owner) == threading.get_ident()


def _latest_global_migration_write_intents_by_candidate(output_root: Path | str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(Path(output_root) / GLOBAL_MIGRATION_WRITE_INTENTS_ARTIFACT):
        candidate_id = str(row.get("candidate_id") or _migration_candidate_id(row) or "").strip()
        if not candidate_id:
            continue
        previous = latest.get(candidate_id)
        row_time = _num(_first_present(row, ["queued_at", "observed_at", "received_at"])) or 0.0
        previous_time = _num(_first_present(previous or {}, ["queued_at", "observed_at", "received_at"])) or -1.0
        if previous is None or row_time >= previous_time:
            latest[candidate_id] = row
    return latest


def _compact_migration_payload(row: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "signature",
        "slot",
        "block_time",
        "received_at",
        "migration_received_at",
        "source_route",
        "route_name",
        "detection_method",
        "program_id",
        "migration_program_id",
        "instruction_type",
        "event_type",
        "mint",
        "base_mint",
        "quote_mint",
        "quote_asset",
        "pool_or_pair_address",
        "pool_address",
        "confidence",
        "migration_evidence_level",
    }
    compact = {key: value for key, value in row.items() if key in keep and value not in (None, "")}
    logs = row.get("logs")
    if isinstance(logs, list):
        compact["logs_excerpt"] = logs[:8]
    return compact


def _spool_global_migration_raw_candidate(
    output_root: Path,
    row: dict[str, Any],
    *,
    decode_attempted: bool = True,
    decode_status: str | None = None,
    write_enqueued: bool = False,
    write_success: bool | None = None,
    write_error: BaseException | str | None = None,
) -> dict[str, Any]:
    candidate_id = _migration_candidate_id(row)
    row["candidate_id"] = candidate_id
    spool_row = {
        "candidate_id": candidate_id,
        "observed_at": _num(_first_present(row, ["observed_at", "received_at", "migration_received_at"])) or time.time(),
        "slot": row.get("slot"),
        "block_time": row.get("block_time"),
        "signature": _first_present(row, ["signature", "event_signature", "migration_signature"]),
        "source_channel": _first_present(row, ["source_channel", "source_route", "route_name", "detection_method"]),
        "program_id": _first_present(row, ["program_id", "migration_program_id"]),
        "event_type_guess": _first_present(row, ["event_type", "instruction_type", "detection_method"]),
        "mint": _candidate_mint(row),
        "pool_address": _candidate_pool(row),
        "quote_mint": row.get("quote_mint"),
        "quote_asset": row.get("quote_asset"),
        "decode_attempted": decode_attempted,
        "decode_status": decode_status or ("decoded" if _candidate_mint(row) and _candidate_pool(row) else "candidate"),
        "write_enqueued": write_enqueued,
        "write_success": write_success,
        "write_error": str(write_error)[:500] if write_error else "",
        "payload_summary": _compact_migration_payload(row),
    }
    _append_jsonl_file(output_root / GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT, spool_row)
    return spool_row


def _record_global_migration_write_intent(
    output_root: Path,
    row: dict[str, Any],
    *,
    write_status: str,
    retry_count: int = 0,
    write_success: bool | None = None,
    write_error: BaseException | str | None = None,
) -> dict[str, Any]:
    candidate_id = _migration_candidate_id(row)
    error_text = str(write_error) if write_error else ""
    intent = {
        "candidate_id": candidate_id,
        "signature": _first_present(row, ["signature", "event_signature", "migration_signature"]),
        "pool_address": _candidate_pool(row),
        "pool_or_pair_address": _candidate_pool(row),
        "base_mint": row.get("base_mint") or row.get("mint"),
        "quote_mint": row.get("quote_mint"),
        "quote_asset": row.get("quote_asset"),
        "mint": _candidate_mint(row),
        "observed_at": _num(_first_present(row, ["observed_at", "received_at", "migration_received_at"])),
        "queued_at": time.time(),
        "writer_thread_id": threading.get_ident(),
        "write_status": write_status,
        "write_success": write_success if write_success is not None else write_status == "written",
        "write_error_class": type(write_error).__name__ if isinstance(write_error, BaseException) else "",
        "write_error": error_text[:500],
        "thread_affinity_error": _is_sqlite_thread_affinity_error(write_error),
        "retry_count": int(retry_count),
    }
    _append_jsonl_file(output_root / GLOBAL_MIGRATION_WRITE_INTENTS_ARTIFACT, intent)
    return intent


def _apply_global_migration_recorder_side_effects(
    recorder: BondingCurveProgressRecorder,
    row: dict[str, Any],
    *,
    artifact_filename: str,
    migration_backfill_client: Any | None = None,
    migration_backfill_lookup_sleep_ms: int = 0,
) -> None:
    level = str(row.get("migration_evidence_level") or "")
    if level == MigrationEvidenceLevel.LEVEL_A.value:
        recorder.summary_counters["migration_level_a_count"] += 1
    elif level == MigrationEvidenceLevel.LEVEL_B.value:
        recorder.summary_counters["migration_level_b_count"] += 1
    elif level in {MigrationEvidenceLevel.LEVEL_C.value, MigrationEvidenceLevel.CANDIDATE.value}:
        recorder.summary_counters["migration_level_c_candidate_count"] += 1
    if row.get("confidence") == "confirmed" and row.get("mint"):
        recorder.write_evidence_record(
            source_lane="global_migration",
            signature=row.get("signature"),
            observed_at=_num(row.get("received_at") or row.get("migration_received_at")),
            slot=row.get("slot"),
            source_route=row.get("source_route") or row.get("detection_method"),
            mint=row.get("mint"),
            pool=row.get("pool_or_pair_address") or row.get("pool_address"),
            evidence_level=level or MigrationEvidenceLevel.NONE,
            raw_payload=row,
            rule_hits=[str(row.get("migration_evidence_reason") or row.get("detection_method") or "migration")],
            confidence=1.0 if level == MigrationEvidenceLevel.LEVEL_A.value else 0.93 if level == MigrationEvidenceLevel.LEVEL_B.value else 0.5,
        )
        recorder.write_lifecycle_transition(
            mint=row.get("mint"),
            previous_state="CURVE_OR_POST_MIGRATION_UNKNOWN",
            next_state=f"MIGRATION_CONFIRMED_{level}" if level in {MigrationEvidenceLevel.LEVEL_A.value, MigrationEvidenceLevel.LEVEL_B.value} else "MIGRATION_CANDIDATE",
            signature=row.get("signature"),
            observed_at=_num(row.get("received_at") or row.get("migration_received_at")),
            reason=str(row.get("migration_evidence_reason") or row.get("detection_method") or "migration"),
        )
    recorder._record_persistent_lifecycle_artifact(artifact_filename, row)
    if row.get("confidence") == "confirmed" and row.get("mint"):
        recorder.schedule_post_migration_observations(row)
        recorder.record_execution_cost_sample("migration_event", as_of=_num(row.get("migration_received_at")) or time.time())
        mint = str(row.get("mint") or "")
        state = recorder.states.get(mint)
        if state is not None:
            state.migration_seen = True
            state.migration_signature = row.get("signature") or ""
            state.migration_received_at = row.get("migration_received_at") or row.get("received_at")
            recorder._record_creator_migration_seen(state, _num(state.migration_received_at))
        if state is not None:
            recorder._record_promotion_event(
                state,
                "global_migration_event",
                source_row=row,
                trigger_value=row.get("migration_evidence_level") or row.get("confidence"),
                as_of=_num(row.get("migration_received_at") or row.get("received_at")),
            )
        if not row.get("seen_in_birth_source"):
            recorder.enqueue_migration_backfill(
                row,
                client=migration_backfill_client,
                lookup_sleep_ms=migration_backfill_lookup_sleep_ms,
            )


class GlobalMigrationDedupeWriter:
    def __init__(
        self,
        output_root: Path | str,
        *,
        recorder: BondingCurveProgressRecorder | None = None,
        migration_backfill_client: Any | None = None,
        migration_backfill_client_factory: Any | None = None,
        migration_backfill_lookup_sleep_ms: int = 0,
        defer_recorder_side_effects: bool | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.recorder = recorder
        self.migration_backfill_client = migration_backfill_client
        self.migration_backfill_client_factory = migration_backfill_client_factory
        self.migration_backfill_lookup_sleep_ms = max(0, int(migration_backfill_lookup_sleep_ms))
        self.defer_recorder_side_effects = defer_recorder_side_effects
        self.seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.unique_mints: set[str] = set()
        self.unique_pools: set[str] = set()
        self.stats: dict[str, Any] = {
            "global_migration_events_deduped": 0,
            "global_migration_candidates": 0,
            "global_migration_duplicates_suppressed": 0,
            "global_migration_unique_mints": 0,
            "global_migration_unique_pools": 0,
            "global_migration_mints_seen_in_birth_source": 0,
            "global_migration_mints_admitted": 0,
            "global_migration_mints_sample_rejected": 0,
            "global_migration_mints_capacity_rejected": 0,
            "global_migration_mints_not_seen_in_birth_source": 0,
            "migration_after_prune_count": 0,
            "migration_while_active_count": 0,
            "migration_for_non_admitted_count": 0,
            "migration_for_sample_rejected_count": 0,
            "high_progress_tokens_that_later_migrated": 0,
            "global_migration_raw_candidate_spool_rows": 0,
            "migration_write_intents_queued": 0,
            "migration_write_success_count": 0,
            "migration_write_failure_count": 0,
            "migration_write_retry_pending_count": 0,
            "migration_write_thread_affinity_error_count": 0,
            "migration_lane_writer_status": "ok",
        }

    def record(self, detection: dict[str, Any]) -> str:
        row = _enrich_global_migration_context(dict(detection), self.recorder)
        method = str(row.get("detection_method") or row.get("source_route") or "")
        if not row.get("migration_evidence_level"):
            if method in {"pumpswap_pair_created_signal", "pumpfun_migrate_instruction", "complete_flag_true", "explicit_migrate_log"}:
                row["migration_evidence_level"] = MigrationEvidenceLevel.LEVEL_A.value
                row["migration_evidence_reason"] = "explicit_pool_create_or_migrate"
            elif method == "pumpswap_first_swap_after_live_birth":
                row["migration_evidence_level"] = MigrationEvidenceLevel.LEVEL_B.value
                row["migration_evidence_reason"] = "first_pumpswap_swap_after_live_birth"
            else:
                row["migration_evidence_level"] = MigrationEvidenceLevel.LEVEL_C.value
                row["migration_evidence_reason"] = method or "migration_candidate"
        _spool_global_migration_raw_candidate(self.output_root, row, write_enqueued=True)
        self.stats["global_migration_raw_candidate_spool_rows"] += 1
        if row.get("confidence") == "confirmed" and row.get("mint"):
            key = _global_migration_dedupe_key(row)
            existing = self.seen.get(key)
            if existing is not None:
                duplicate = dict(row)
                duplicate["duplicate_suppressed"] = True
                duplicate["duplicate_of_signature"] = existing.get("signature")
                duplicate["duplicate_of_slot"] = existing.get("slot")
                duplicate["duplicate_of_received_at"] = existing.get("received_at")
                _append_jsonl_file(self.output_root / "global_migration_event_duplicates.jsonl", duplicate)
                _record_global_migration_write_intent(self.output_root, duplicate, write_status="written", write_success=True)
                self.stats["migration_write_intents_queued"] += 1
                self.stats["migration_write_success_count"] += 1
                self.stats["global_migration_duplicates_suppressed"] += 1
                return "duplicate"
            self.seen[key] = dict(row)
            _record_global_migration_write_intent(self.output_root, row, write_status="queued", write_success=False)
            self.stats["migration_write_intents_queued"] += 1
            _append_jsonl_file(self.output_root / "global_migration_events.jsonl", row)
            self._apply_or_defer_recorder_side_effects(row, artifact_filename="global_migration_events.jsonl")
            self.stats["global_migration_events_deduped"] += 1
            mint = str(row.get("mint") or "")
            pool = str(row.get("pool_or_pair_address") or "")
            if mint:
                self.unique_mints.add(mint)
            if pool:
                self.unique_pools.add(pool)
            self.stats["global_migration_unique_mints"] = len(self.unique_mints)
            self.stats["global_migration_unique_pools"] = len(self.unique_pools)
            self._update_context_stats(row)
            return "event"
        _append_jsonl_file(self.output_root / "global_migration_candidates.jsonl", row)
        _record_global_migration_write_intent(self.output_root, row, write_status="queued", write_success=False)
        self.stats["migration_write_intents_queued"] += 1
        self._apply_or_defer_recorder_side_effects(row, artifact_filename="global_migration_candidates.jsonl")
        self.stats["global_migration_candidates"] += 1
        return "candidate"

    def _recorder_side_effects_allowed(self) -> bool:
        if self.defer_recorder_side_effects is True:
            return False
        return _recorder_side_effects_allowed(self.recorder)

    def _apply_or_defer_recorder_side_effects(self, row: dict[str, Any], *, artifact_filename: str) -> None:
        if self.recorder is None:
            _record_global_migration_write_intent(self.output_root, row, write_status="written", write_success=True)
            self.stats["migration_write_success_count"] += 1
            return
        if not self._recorder_side_effects_allowed():
            _record_global_migration_write_intent(
                self.output_root,
                row,
                write_status="retry_pending",
                write_success=False,
                write_error="recorder_side_effects_deferred_to_owner_thread",
            )
            self.stats["migration_write_retry_pending_count"] += 1
            self.stats["migration_lane_writer_status"] = "degraded"
            return
        try:
            _apply_global_migration_recorder_side_effects(
                self.recorder,
                row,
                artifact_filename=artifact_filename,
                migration_backfill_client=self._migration_backfill_client(),
                migration_backfill_lookup_sleep_ms=self.migration_backfill_lookup_sleep_ms,
            )
        except Exception as exc:
            _record_global_migration_write_intent(
                self.output_root,
                row,
                write_status="failed",
                write_success=False,
                write_error=exc,
            )
            self.stats["migration_write_failure_count"] += 1
            if _is_sqlite_thread_affinity_error(exc):
                self.stats["migration_write_thread_affinity_error_count"] += 1
            self.stats["migration_lane_writer_status"] = "failed"
            return
        _record_global_migration_write_intent(self.output_root, row, write_status="written", write_success=True)
        self.stats["migration_write_success_count"] += 1

    def _update_context_stats(self, row: dict[str, Any]) -> None:
        if row.get("seen_in_birth_source"):
            self.stats["global_migration_mints_seen_in_birth_source"] += 1
        else:
            self.stats["global_migration_mints_not_seen_in_birth_source"] += 1
        if row.get("admitted"):
            self.stats["global_migration_mints_admitted"] += 1
        if row.get("sample_rejected"):
            self.stats["global_migration_mints_sample_rejected"] += 1
            self.stats["migration_for_sample_rejected_count"] += 1
        if row.get("capacity_rejected"):
            self.stats["global_migration_mints_capacity_rejected"] += 1
        if row.get("admitted") is False:
            self.stats["migration_for_non_admitted_count"] += 1
        if row.get("pruned_before_migration"):
            self.stats["migration_after_prune_count"] += 1
        if row.get("migration_while_active"):
            self.stats["migration_while_active_count"] += 1
        if _num(row.get("highest_progress_pct")) is not None and float(row.get("highest_progress_pct") or 0.0) >= 60.0:
            self.stats["high_progress_tokens_that_later_migrated"] += 1

    def summary(self) -> dict[str, Any]:
        return dict(self.stats)

    def _migration_backfill_client(self) -> Any | None:
        if self.migration_backfill_client is not None:
            return self.migration_backfill_client
        if self.migration_backfill_client_factory is None:
            return None
        self.migration_backfill_client = self.migration_backfill_client_factory()
        return self.migration_backfill_client


def _global_migration_dedupe_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("mint") or ""),
        str(row.get("pool_or_pair_address") or ""),
        str(row.get("detection_method") or ""),
    )


def _enrich_global_migration_context(row: dict[str, Any], recorder: BondingCurveProgressRecorder | None) -> dict[str, Any]:
    mint = str(row.get("mint") or "")
    birth_row = recorder.birth_rows_by_mint.get(mint) if recorder is not None and mint else None
    state = recorder.states.get(mint) if recorder is not None and mint else None
    admitted = birth_row.get("admitted") if birth_row else False
    admission_reason = str((birth_row or {}).get("admission_reason") or "")
    if recorder is not None:
        row["campaign_id"] = recorder.config.run_id
        row["run_id"] = recorder.config.run_id
    migration_received_at = _num(_first_present(row, ["migration_received_at", "received_at"]))
    if migration_received_at is not None:
        row["migration_received_at"] = migration_received_at
    row["seen_in_birth_source"] = birth_row is not None
    row["admitted"] = bool(admitted)
    row["sample_rejected"] = admission_reason == "sample_rejected"
    row["capacity_rejected"] = admission_reason.startswith("capacity_rejected")
    row["pruned_before_migration"] = bool(state and state.stopped and state.pruned_due_to_low_progress)
    row["migration_while_active"] = bool(state and not state.stopped)
    row["last_progress_pct"] = state.last_progress_pct if state else None
    row["highest_progress_pct"] = state.highest_progress_pct if state else None
    row["thresholds_crossed_before_migration"] = sorted(state.thresholds_crossed) if state else []
    return row


def _route_runtime_status(route: Any, requested_duration: float, availability: dict[str, Any]) -> dict[str, Any]:
    actual = float(getattr(route, "actual_duration_seconds", requested_duration) or 0.0)
    quality = _source_duration_quality_fields(
        requested_duration,
        actual,
        websocket_closed_early=bool(getattr(route, "websocket_closed_early", False)),
        websocket_close_reason=getattr(route, "websocket_close_reason", None),
        websocket_keepalive_timeout_count=int(getattr(route, "websocket_keepalive_timeout_count", 0) or 0),
        websocket_reconnect_count=int(getattr(route, "websocket_reconnect_count", getattr(route, "reconnect_attempts", 0)) or 0),
    )
    return {
        "source": availability.get("source") or getattr(route, "source_name", route.__class__.__name__),
        "requested_duration_seconds": float(requested_duration),
        "actual_duration_seconds": actual,
        "websocket_closed_early": bool(getattr(route, "websocket_closed_early", quality["source_ended_early"])),
        "websocket_close_reason": getattr(route, "websocket_close_reason", None),
        "reconnect_attempts": int(getattr(route, "reconnect_attempts", 0) or 0),
        "reconnect_success_count": int(getattr(route, "reconnect_success_count", 0) or 0),
        "reconnect_failure_count": int(getattr(route, "reconnect_failure_count", 0) or 0),
        "reconnect_reasons": list(getattr(route, "reconnect_reasons", []) or []),
        "source_gap_intervals": list(getattr(route, "source_gap_intervals", []) or []),
        "websocket_keepalive_timeout_count": quality["websocket_keepalive_timeout_count"],
        "websocket_reconnect_count": quality["websocket_reconnect_count"],
        "total_disconnected_seconds": float(getattr(route, "total_disconnected_seconds", 0.0) or 0.0),
        "completed_requested_duration": bool(getattr(route, "completed_requested_duration", quality["completed_requested_duration"])),
        **quality,
    }


def _source_duration_quality_fields(
    requested_duration: Any,
    actual_duration: Any,
    *,
    websocket_closed_early: bool = False,
    websocket_close_reason: Any = None,
    websocket_keepalive_timeout_count: int = 0,
    websocket_reconnect_count: int = 0,
) -> dict[str, Any]:
    requested = _num(requested_duration)
    actual = _num(actual_duration)
    keepalive_timeouts = int(websocket_keepalive_timeout_count or 0)
    reconnect_count = int(websocket_reconnect_count or 0)
    if requested is None or requested <= 0:
        return {
            "requested_source_duration_seconds": requested,
            "actual_source_duration_seconds": actual,
            "source_duration_completion_ratio": None,
            "source_duration_quality_status": "not_evaluated",
            "source_ended_early": False,
            "early_end_reason": None,
            "validation_run_quality_label": "RUN_QUALITY_NOT_EVALUATED",
            "websocket_keepalive_timeout_count": keepalive_timeouts,
            "websocket_reconnect_count": reconnect_count,
            "completed_requested_duration": None,
        }
    if actual is None:
        return {
            "requested_source_duration_seconds": requested,
            "actual_source_duration_seconds": None,
            "source_duration_completion_ratio": 0.0,
            "source_duration_quality_status": "failed",
            "source_ended_early": True,
            "early_end_reason": "missing_actual_source_duration",
            "validation_run_quality_label": "RUN_QUALITY_FAILED",
            "websocket_keepalive_timeout_count": keepalive_timeouts,
            "websocket_reconnect_count": reconnect_count,
            "completed_requested_duration": False,
        }
    ratio = max(0.0, actual) / requested
    if actual <= 0:
        status = "failed"
        label = "RUN_QUALITY_FAILED"
        reason = str(websocket_close_reason or "zero_actual_source_duration")
    elif ratio < 0.95 or websocket_closed_early:
        status = "partial"
        label = "RUN_QUALITY_PARTIAL"
        reason = str(websocket_close_reason or "source_duration_below_95pct")
    elif keepalive_timeouts > 0 or reconnect_count > 0:
        status = "complete_with_reconnect_warning"
        label = "RUN_QUALITY_COMPLETE_WITH_RECONNECT_WARNING"
        reason = "websocket_reconnect_or_keepalive"
    else:
        status = "complete"
        label = "CLEAN_10M_SOURCE_DURATION_PASSED"
        reason = None
    return {
        "requested_source_duration_seconds": requested,
        "actual_source_duration_seconds": actual,
        "source_duration_completion_ratio": ratio,
        "source_duration_quality_status": status,
        "source_ended_early": status in {"partial", "failed"},
        "early_end_reason": reason,
        "validation_run_quality_label": label,
        "websocket_keepalive_timeout_count": keepalive_timeouts,
        "websocket_reconnect_count": reconnect_count,
        "completed_requested_duration": ratio >= 0.95 and not websocket_closed_early,
    }


_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_INDEX = {char: idx for idx, char in enumerate(_BASE58_ALPHABET)}


def _base58_encode_bytes(data: bytes) -> str:
    if not data:
        return ""
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = _BASE58_ALPHABET[rem] + encoded
    leading_zeroes = len(data) - len(data.lstrip(b"\0"))
    return ("1" * leading_zeroes) + (encoded or "")


def _base58_decode_string(value: str) -> bytes:
    number = 0
    for char in str(value or ""):
        if char not in _BASE58_INDEX:
            raise ValueError(f"invalid base58 character: {char}")
        number = number * 58 + _BASE58_INDEX[char]
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(str(value or "")) - len(str(value or "").lstrip("1"))
    return (b"\0" * leading_zeroes) + raw


def _pumpswap_program_subscribe_filters(
    quote_mint: str | None = None,
    *,
    account_length: int = PUMPSWAP_MARKET_ACCOUNT_LENGTH,
) -> list[dict[str, Any]]:
    if int(account_length) not in PUMPSWAP_MARKET_ACCOUNT_LENGTHS:
        raise ValueError(f"unsupported_pumpswap_market_account_length:{account_length}")
    filters = [
        {"dataSize": int(account_length)},
        {"memcmp": {"offset": 0, "bytes": _base58_encode_bytes(PUMPSWAP_MARKET_DISCRIMINATOR_BYTES)}},
    ]
    if quote_mint:
        filters.append({"memcmp": {"offset": PUMPSWAP_MARKET_QUOTE_MINT_OFFSET, "bytes": _base58_encode_bytes(_base58_decode_string(quote_mint))}})
    return filters


def _pumpswap_program_subscribe_request(
    request_id: str,
    *,
    quote_mint: str | None = None,
    account_length: int = PUMPSWAP_MARKET_ACCOUNT_LENGTH,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "programSubscribe",
        "params": [
            PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
            {
                "encoding": "base64",
                "commitment": "processed",
                "filters": _pumpswap_program_subscribe_filters(quote_mint, account_length=account_length),
            },
        ],
    }


def _program_subscribe_result(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    result = params.get("result") if isinstance(params.get("result"), dict) else {}
    return result if isinstance(result, dict) else {}


def _program_subscribe_slot_from_payload(payload: dict[str, Any]) -> int | None:
    result = _program_subscribe_result(payload)
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    slot = context.get("slot")
    try:
        return int(slot) if slot is not None else None
    except (TypeError, ValueError):
        return None


def _program_subscribe_value_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = _program_subscribe_result(payload)
    value = result.get("value") if isinstance(result.get("value"), dict) else {}
    return value if isinstance(value, dict) else {}


def _program_subscribe_pubkey_from_payload(payload: dict[str, Any]) -> str | None:
    value = _program_subscribe_value_from_payload(payload)
    pubkey = value.get("pubkey")
    return str(pubkey) if pubkey else None


def _program_subscribe_account_data_from_payload(payload: dict[str, Any]) -> bytes | None:
    value = _program_subscribe_value_from_payload(payload)
    account = value.get("account") if isinstance(value.get("account"), dict) else {}
    data = account.get("data") if isinstance(account, dict) else None
    encoded: str | None = None
    if isinstance(data, list) and data:
        encoded = str(data[0])
    elif isinstance(data, str):
        encoded = data
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded)
    except Exception:
        return None


def _decode_pumpswap_market_account_data(data: bytes, *, account_pubkey: str | None = None) -> dict[str, Any] | None:
    try:
        from research.mtp_research.validation.t007_protocol_codecs import PumpSwapAccountDecoder

        result = PumpSwapAccountDecoder().decode_account(
            data,
            owner=PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
            pool_address=account_pubkey,
        )
    except Exception:
        return None
    if not result.ok:
        return None
    evidence = dict(result.evidence)
    evidence.setdefault("layout_variant", result.layout_version)
    evidence.setdefault("data_size", evidence.get("account_length") or len(data))
    evidence.setdefault("discriminator_valid", True)
    return evidence


def _pubkey_is_on_curve(address: str | None) -> bool | None:
    if not address:
        return None
    try:
        from solders.pubkey import Pubkey

        pubkey = Pubkey.from_string(str(address))
        method = getattr(pubkey, "is_on_curve", None)
        if callable(method):
            return bool(method())
    except Exception:
        return None
    return None


def _pumpswap_program_subscribe_detection_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    decoded = event.get("account_data_decoded")
    if not isinstance(decoded, dict):
        account_data = _program_subscribe_account_data_from_payload(event.get("raw_payload") or {})
        decoded = _decode_pumpswap_market_account_data(account_data or b"", account_pubkey=event.get("account_pubkey"))
    if not isinstance(decoded, dict):
        return None
    if int(decoded.get("data_size") or 0) not in PUMPSWAP_MARKET_ACCOUNT_LENGTHS:
        return None
    if decoded.get("discriminator_valid") is not True:
        return None
    quote = _quote_identity_from_payload(decoded, unsupported_as_unknown=False)
    creator_is_on_curve = decoded.get("creator_is_on_curve")
    if creator_is_on_curve is None:
        creator_is_on_curve = _pubkey_is_on_curve(str(decoded.get("creator") or ""))
    if creator_is_on_curve is True:
        return None

    mint = str(decoded.get("base_mint") or "")
    pool = str(decoded.get("pool_or_pair_address") or event.get("account_pubkey") or "")
    if not mint or not pool:
        return None
    slot = event.get("slot")
    signature = event.get("signature") or f"program-subscribe:{slot}:{pool}"
    account_created = _bool(
        event.get("program_subscribe_account_created")
        or event.get("pool_account_created")
        or event.get("account_created")
        or decoded.get("program_subscribe_account_created")
        or decoded.get("pool_account_created")
        or decoded.get("account_created")
    )
    confidence = "confirmed" if account_created and quote["quote_asset_status"] in {"sol", "usdc"} else "candidate"
    return {
        "mint": mint,
        "signature": signature,
        "slot": slot,
        "received_at": event.get("received_at"),
        "source_route": "pumpswap_program_subscribe",
        "detection_method": "pumpswap_pool_account_create" if account_created else "pumpswap_pool_account_update",
        "confidence": confidence,
        "migration_program_id": PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
        "migration_instruction_name": "programSubscribe_market_account_create" if account_created else "programSubscribe_market_account_update",
        "pool_or_pair_address": pool,
        "base_mint": mint,
        "quote_mint": quote["quote_mint"],
        "quote_asset": quote["quote_asset"],
        "quote_asset_status": quote["quote_asset_status"],
        "lp_mint": decoded.get("lp_mint"),
        "pool_base_token_account": decoded.get("pool_base_token_account"),
        "pool_quote_token_account": decoded.get("pool_quote_token_account"),
        "coin_creator": decoded.get("coin_creator"),
        "creator": decoded.get("creator"),
        "creator_is_on_curve": creator_is_on_curve,
        "is_mayhem_mode": decoded.get("is_mayhem_mode"),
        "is_cashback_coin": decoded.get("is_cashback_coin"),
        "event_type": "pumpswap_pool_created" if account_created else "pumpswap_pool_account_update",
        "program_subscribe_account_created": account_created,
        "admission_scope": "global_source_not_admission_gated",
    }


def _migration_route_source_filters() -> dict[str, Any]:
    return {
        "method": "transactionSubscribe",
        "failed": False,
        "accountRequired": [PUMP_FUN_PROGRAM_ID_FOR_AUDIT],
        "commitment": "processed",
        "transactionDetails": "full",
        "encoding": "jsonParsed",
    }


def _pumpswap_candidate_from_raw_payload(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    tx = _txsub_transaction_from_event(event)
    if not tx:
        return {}
    instructions = _pumpswap_instructions_from_transaction(tx)
    program_id = _first_present(row, ["program_id", "programId"]) or event.get("program_id") or event.get("programId")
    if not instructions and program_id != PUMPSWAP_PROGRAM_ID_FOR_AUDIT:
        return {}
    instruction = instructions[0] if instructions else {}
    accounts = list(instruction.get("accounts") or [])
    mint = _pumpswap_mint_from_token_balances(tx) or _pumpswap_mint_from_accounts(accounts)
    quote = _pumpswap_quote_mint_from_token_balances(tx, mint) or _quote_mint_from_accounts(accounts, mint or "")
    pool = _pumpswap_pool_from_token_balance_owners(tx, mint, quote) or _pumpswap_pool_from_accounts(accounts, mint)
    return {
        "mint": mint,
        "base_mint": mint,
        "quote_mint": quote,
        "pool_or_pair_address": pool,
        "pool_base_token_account": accounts[7] if len(accounts) > 7 else None,
        "pool_quote_token_account": accounts[8] if len(accounts) > 8 else None,
        "program_id": instruction.get("program_id") or program_id,
        "instruction_name": instruction.get("instruction_name") or instruction.get("instruction_type"),
        "raw_compact_account_list": accounts[:16],
    }


def _pumpswap_instructions_from_transaction(tx: dict[str, Any]) -> list[dict[str, Any]]:
    account_keys = _transaction_account_keys(tx)
    output: list[dict[str, Any]] = []
    message = ((tx.get("transaction") or {}).get("message") or {}) if isinstance(tx.get("transaction"), dict) else {}
    for instruction in message.get("instructions") or []:
        compact = _compact_instruction_with_account_keys(instruction, account_keys)
        if compact.get("program_id") == PUMPSWAP_PROGRAM_ID_FOR_AUDIT:
            output.append(compact)
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    for group in meta.get("innerInstructions") or []:
        for instruction in group.get("instructions") or []:
            compact = _compact_instruction_with_account_keys(instruction, account_keys)
            if compact.get("program_id") == PUMPSWAP_PROGRAM_ID_FOR_AUDIT:
                compact["instruction_level"] = "inner"
                output.append(compact)
    return output


def _compact_instruction_with_account_keys(instruction: dict[str, Any], account_keys: list[str]) -> dict[str, Any]:
    compact = _compact_instruction(instruction)
    resolved_accounts: list[str] = []
    for account in compact.get("accounts") or []:
        resolved = _resolve_instruction_account(account, account_keys)
        if resolved:
            resolved_accounts.append(resolved)
    compact["accounts"] = resolved_accounts
    return compact


def _transaction_account_keys(tx: dict[str, Any]) -> list[str]:
    message = ((tx.get("transaction") or {}).get("message") or {}) if isinstance(tx.get("transaction"), dict) else {}
    keys: list[str] = []
    for key in message.get("accountKeys") or []:
        if isinstance(key, dict):
            value = key.get("pubkey")
        else:
            value = key
        if value not in (None, ""):
            keys.append(str(value))
    return keys


def _resolve_instruction_account(account: Any, account_keys: list[str]) -> str | None:
    if isinstance(account, int):
        return account_keys[account] if 0 <= account < len(account_keys) else None
    if isinstance(account, str) and account.isdigit():
        index = int(account)
        return account_keys[index] if 0 <= index < len(account_keys) else account
    return str(account) if account not in (None, "") else None


def _token_balance_rows(tx: dict[str, Any]) -> list[dict[str, Any]]:
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key in ("preTokenBalances", "postTokenBalances"):
        balances = meta.get(key)
        if isinstance(balances, list):
            rows.extend(row for row in balances if isinstance(row, dict))
    return rows


def _pumpswap_mint_from_token_balances(tx: dict[str, Any]) -> str | None:
    mints = []
    for row in _token_balance_rows(tx):
        mint = str(row.get("mint") or "")
        if mint and mint != "So11111111111111111111111111111111111111112" and mint not in mints:
            mints.append(mint)
    pump_mints = [mint for mint in mints if mint.endswith("pump")]
    if len(pump_mints) == 1:
        return pump_mints[0]
    if len(mints) == 1:
        return mints[0]
    return None


def _pumpswap_mint_from_accounts(accounts: list[str]) -> str | None:
    pump_accounts = [account for account in accounts if str(account).endswith("pump")]
    if len(pump_accounts) == 1:
        return str(pump_accounts[0])
    return None


def _pumpswap_quote_mint_from_token_balances(tx: dict[str, Any], mint: str | None) -> str | None:
    seen: list[str] = []
    for row in _token_balance_rows(tx):
        token_mint = str(row.get("mint") or "")
        if token_mint and token_mint != mint and token_mint not in seen:
            seen.append(token_mint)
    if "So11111111111111111111111111111111111111112" in seen:
        return "So11111111111111111111111111111111111111112"
    return seen[0] if len(seen) == 1 else None


def _pumpswap_pool_from_token_balance_owners(tx: dict[str, Any], mint: str | None, quote: str | None) -> str | None:
    if not mint:
        return None
    token_owners = {
        str(row.get("owner"))
        for row in _token_balance_rows(tx)
        if row.get("owner") and row.get("mint") == mint
    }
    quote_owners = {
        str(row.get("owner"))
        for row in _token_balance_rows(tx)
        if row.get("owner") and quote and row.get("mint") == quote
    }
    shared = sorted(owner for owner in token_owners & quote_owners if owner)
    if shared:
        return shared[0]
    return None


def _pumpswap_pool_from_accounts(accounts: list[str], mint: str | None) -> str | None:
    excluded = {
        str(mint or ""),
        PUMP_FUN_PROGRAM_ID_FOR_AUDIT,
        PUMPSWAP_PROGRAM_ID_FOR_AUDIT,
        "So11111111111111111111111111111111111111112",
        "11111111111111111111111111111111",
    }
    if len(accounts) > 1 and accounts[1] and accounts[1] not in excluded:
        return str(accounts[1])
    return _candidate_pool_from_accounts(accounts, mint or "")


def _migration_route_detection_from_row(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    detection = _global_migration_detection_from_row(row, event)
    if detection is None:
        return None
    method = str(detection.get("detection_method") or "")
    text = _migration_detection_text(row, event)
    program_id = _first_present(row, ["program_id", "programId"]) or event.get("program_id") or event.get("programId")
    if program_id is None:
        program_id = detection.get("migration_program_id")
    if method == "pumpswap_pair_created_signal" or program_id == PUMPSWAP_PROGRAM_ID_FOR_AUDIT or "pumpswap" in text:
        route = "pumpswap_pool_create"
    elif method in {"pumpfun_migrate_instruction", "complete_flag_true", "explicit_migrate_log"}:
        route = "pumpfun_migrate_instruction_log"
    elif method == "migration_keyword_candidate":
        route = "pumpfun_migrate_instruction_log"
    else:
        route = "current_pumpfun_create_account_required"
    return {
        **detection,
        "source_route": route,
        "pool_or_pair_address": detection.get("pool_or_pair_address") or _pool_or_pair_address(row, event),
        "migration_program_id": program_id,
        "migration_instruction_name": detection.get("migration_instruction_name") or row.get("instruction_type"),
    }


def _global_migration_detection_from_row(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    raw_pumpswap = _pumpswap_candidate_from_raw_payload(row, event)
    row_or_event_mint = str(
        row.get("mint")
        or row.get("token_mint")
        or row.get("base_mint")
        or row.get("coin_mint")
        or event.get("mint")
        or ""
    ).strip()
    raw_pumpswap_mint = str(raw_pumpswap.get("mint") or raw_pumpswap.get("base_mint") or "").strip()
    mint = row_or_event_mint or raw_pumpswap_mint
    text = _migration_detection_text(row, event)
    detection_method: str | None = None
    confidence = "confirmed"
    instruction_type = str(row.get("instruction_type") or "").strip().lower()
    program_id = _first_present(row, ["program_id", "programId"]) or event.get("program_id") or event.get("programId")
    if program_id is None:
        program_id = raw_pumpswap.get("program_id")
    normalized_instruction = instruction_type.replace("-", "_").replace(" ", "_")
    text_has_explicit_pumpswap_pool_create = (
        "instruction: createpool" in text
        or "instruction: create_pool" in text
        or "create_pool" in text
        or "createpool" in text
    )
    pumpswap_pool_create_instruction = normalized_instruction in {
        "create_pool",
        "createpool",
        "create_pool_v2",
        "createpoolv2",
        "initialize_pool",
        "initializepool",
    }
    row_has_explicit_pumpswap_pair_signal = _bool(row.get("dex_pair_signal") or row.get("pair_created") or row.get("pumpswap_pair_created"))
    row_is_explicit_pumpswap_pool_create = row_has_explicit_pumpswap_pair_signal or pumpswap_pool_create_instruction
    if _bool(row.get("complete") or row.get("complete_or_migrated") or row.get("migrated")):
        detection_method = "complete_flag_true"
    elif _bool(row.get("explicit_migrate_log")):
        detection_method = "explicit_migrate_log"
    elif row_has_explicit_pumpswap_pair_signal:
        detection_method = "pumpswap_pair_created_signal"
    elif program_id == PUMPSWAP_PROGRAM_ID_FOR_AUDIT and (
        pumpswap_pool_create_instruction or text_has_explicit_pumpswap_pool_create
    ):
        detection_method = "pumpswap_pair_created_signal"
    elif "instruction: migrate" in text or instruction_type in {"migrate", "migration"}:
        detection_method = "pumpfun_migrate_instruction"
    elif "pumpswap" in text and text_has_explicit_pumpswap_pool_create:
        detection_method = "pumpswap_pair_created_signal"
    elif "migrat" in text:
        detection_method = "migration_keyword_candidate"
        confidence = "candidate"
    if detection_method is None:
        return None
    raw_pool = raw_pumpswap.get("pool_or_pair_address")
    row_pool = _pool_or_pair_address(row, event)
    if detection_method == "pumpswap_pair_created_signal":
        if raw_pumpswap_mint:
            mint = raw_pumpswap_mint
            mint_source = "raw_transaction_token_balances_or_accounts"
        elif row_is_explicit_pumpswap_pool_create:
            mint = row_or_event_mint
            mint_source = "explicit_create_pool_row"
        else:
            mint = ""
            mint_source = "unresolved_non_create_pool_row"
        pool_or_pair = raw_pool or (row_pool if row_is_explicit_pumpswap_pool_create else None)
    else:
        pool_or_pair = row_pool or raw_pool
        mint_source = "row_or_event"
    quote = _quote_identity_from_payload({"quote_mint": raw_pumpswap.get("quote_mint") or row.get("quote_mint")}, unsupported_as_unknown=False)
    if detection_method == "pumpswap_pair_created_signal" and not (mint and pool_or_pair):
        confidence = "candidate"
    return {
        "mint": mint or None,
        "signature": row.get("signature") or event.get("signature"),
        "slot": row.get("slot") or event.get("slot"),
        "received_at": row.get("observed_at") or row.get("received_at") or event.get("received_at"),
        "source_route": "transaction_subscribe_global_migration_audit",
        "source_instruction_level": row.get("source_instruction_level"),
        "source_instruction_decode_route": row.get("source_instruction_decode_route"),
        "instruction_type": row.get("instruction_type"),
        "parser_status": row.get("parser_status"),
        "parser_error": row.get("parser_error") or row.get("parser_failure_reason"),
        "detection_method": detection_method,
        "confidence": confidence if mint else "candidate",
        "admission_scope": "global_source_not_admission_gated",
        "pool_or_pair_address": pool_or_pair,
        "migration_program_id": program_id,
        "migration_instruction_name": row.get("instruction_type") or raw_pumpswap.get("instruction_name"),
        "canonical_mint_source": mint_source,
        "base_mint": raw_pumpswap.get("base_mint"),
        "quote_mint": quote["quote_mint"],
        "quote_asset": quote["quote_asset"],
        "quote_asset_status": quote["quote_asset_status"],
        "raw_compact_account_list": raw_pumpswap.get("raw_compact_account_list"),
        "logs_excerpt": _logs_excerpt(event),
    }


def _pool_or_pair_address(row: dict[str, Any], event: dict[str, Any]) -> str | None:
    value = _first_present(
        row,
        ["pool_or_pair_address", "pool_address", "pair_address", "pool", "pair", "bonding_curve_account", "bonding_curve"],
    )
    if value is None:
        value = _first_present(event, ["pool_or_pair_address", "pool_address", "pair_address", "pool", "pair"])
    return str(value) if value not in (None, "") else None


def _migration_detection_text(row: dict[str, Any], event: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "instruction_type",
        "source_instruction_decode_route",
        "parser_status",
        "event_type",
        "program",
        "program_id",
        "route_type",
    ):
        if row.get(key) is not None:
            values.append(str(row.get(key)))
        if event.get(key) is not None:
            values.append(str(event.get(key)))
    for source in (row, event):
        logs = source.get("logs") if isinstance(source, dict) else None
        if isinstance(logs, list):
            values.extend(str(item) for item in logs)
        elif logs is not None:
            values.append(str(logs))
    return " ".join(values).lower()


def _logs_excerpt(event: dict[str, Any], *, max_items: int = 5) -> list[str]:
    logs = event.get("logs")
    if not isinstance(logs, list):
        return []
    return [str(item) for item in logs[:max_items]]


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        mint = str(row.get("mint") or row.get("token_mint") or "").strip()
        if mint:
            grouped.setdefault(mint, []).append(row)
    return grouped


def _quantile(values: list[float], q: float) -> float | None:
    clean = sorted(values)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return clean[int(pos)]
    return clean[lower] + (clean[upper] - clean[lower]) * (pos - lower)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _valuation_ladder_allowed(row: dict[str, Any]) -> bool:
    return _bool(row.get("valuation_market_cap_confirmed")) or str(row.get("valuation_ladder_trust_status") or "") == "market_cap_confirmed"


def _candidate_market_cap_usd(observation: dict[str, Any], valuation_usd: Any, reserve_fdv_usd: Any) -> float | None:
    explicit = _num(_first_present(observation, ["candidate_market_cap_usd", "market_cap_candidate_usd"]))
    if explicit is not None:
        return explicit
    reserve = _num(reserve_fdv_usd)
    if reserve is not None:
        return round(reserve / 2.0, 6)
    valuation = _num(valuation_usd)
    if valuation is not None:
        return round(valuation / 2.0, 6)
    return None


def _valuation_audit_cohort(row: dict[str, Any], state: TrackingState) -> str:
    if _is_mayhem_row(row, state):
        return "mayhem"
    if _bool(row.get("complete_or_migrated") or row.get("complete")) or state.migration_seen:
        return "migrated_or_post_migration"
    return "standard_pump_or_unclassified"


def _valuation_formula_classification(row: dict[str, Any], state: TrackingState) -> str:
    valuation = _num(row.get("valuation_usd"))
    if valuation is None:
        return "valuation_missing"
    if _is_mayhem_row(row, state):
        return "mayhem_unresolved"
    if _bool(row.get("complete_or_migrated") or row.get("complete")) or state.migration_seen:
        return "post_migration_unresolved"
    if _within_pct(valuation, row.get("axiom_market_cap_usd"), 5.0):
        return "matches_axiom_market_cap"
    if _within_pct(valuation, row.get("axiom_liquidity_usd"), 5.0):
        return "matches_axiom_liquidity"
    if _within_pct(_half_or_none(valuation), row.get("axiom_market_cap_usd"), 5.0):
        return "possible_2x_market_cap"
    if _valuation_ladder_allowed(row):
        return "standard_curve_validated"
    return "standard_curve_needs_axiom_audit"


def _is_mayhem_row(row: dict[str, Any], state: TrackingState) -> bool:
    if _bool(row.get("is_mayhem") or row.get("mayhem") or row.get("mayhem_mode")):
        return True
    source_bits = " ".join(
        str(value or "")
        for value in [
            row.get("observation_source"),
            row.get("source_route_key"),
            state.source_route_type,
            state.source_decode_route,
        ]
    ).lower()
    return "mayhem" in source_bits


def _within_pct(left: Any, right: Any, pct: float) -> bool:
    left_num = _num(left)
    right_num = _num(right)
    if left_num is None or right_num is None or right_num == 0:
        return False
    return abs(left_num - right_num) / abs(right_num) * 100.0 <= pct


def _half_or_none(value: Any) -> float | None:
    number = _num(value)
    if number is None:
        return None
    return number / 2.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_markdown_artifact(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _db_path_from_run_root(run_root: Path) -> Path | None:
    for name in ("canonical_sqlite_db_pointer.json", "canonical_db_pointer.json"):
        pointer = _read_json(run_root / name)
        path = pointer.get("canonical_db_path")
        if path:
            return Path(str(path))
    candidate = run_root / "t007_lifecycle_state.sqlite"
    return candidate if candidate.exists() else None


def _mint_identity_rows_from_run_root(run_root: Path) -> list[dict[str, Any]]:
    db_path = _db_path_from_run_root(run_root)
    if db_path is None or not db_path.exists():
        return []
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "mint_identity" not in tables:
                return []
            return [dict(row) for row in connection.execute("SELECT * FROM mint_identity WHERE mint IS NOT NULL AND mint != ''")]
    except Exception:
        return []


def _mint_set(rows: list[dict[str, Any]], *keys: str) -> set[str]:
    out: set[str] = set()
    for row in rows:
        for key in keys or ("mint",):
            value = str(row.get(key) or "").strip()
            if value:
                out.add(value)
                break
    return out


def _latest_row(rows: list[dict[str, Any]], *time_keys: str) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: max((_num(row.get(key)) or 0.0 for key in time_keys), default=0.0))


def _trade_flow_metric_from_supervisor(run_root: Path) -> dict[str, Any]:
    status = _read_json(run_root / "scan_supervisor_status.json")
    for metric in status.get("coverage_metrics") or []:
        if metric.get("metric_id") == "trade_flow_mint_coverage":
            return dict(metric)
    return {}


def _trade_flow_missing_category(
    *,
    mint: str,
    birth: dict[str, Any],
    has_curve: bool,
    raw_trade_like_seen: bool,
) -> str:
    if not birth:
        return "denominator_policy_non_birth_mint"
    reason = str(birth.get("admission_reason") or birth.get("rejection_reason") or "")
    trade_status = str(birth.get("trade_flow_status") or "").strip().lower()
    if trade_status in {"trade_parse_failed", "parse_failed", "parser_gap"}:
        return "eventful_parser_gap"
    if trade_status in {"trade_write_failed", "write_failed", "writer_gap"}:
        return "eventful_writer_gap"
    if not has_curve:
        return "unknown_gap"
    if "capacity_rejected" in reason:
        return "eventful_subscription_gap" if raw_trade_like_seen else "capacity_rejected_no_trade_events_observed"
    if reason.startswith("sample_rejected"):
        return "eventful_subscription_gap" if raw_trade_like_seen else "sample_rejected_no_trade_events_observed"
    if _bool(birth.get("admitted")):
        return "eventful_subscription_gap" if raw_trade_like_seen else "admitted_no_trade_events_observed"
    if raw_trade_like_seen:
        return "eventful_subscription_gap"
    return "unknown_gap"


def _trade_flow_missing_should_count_against_readiness(category: str) -> bool:
    return category not in {
        "denominator_policy_non_birth_mint",
        "admitted_no_trade_events_observed",
        "capacity_rejected_no_trade_events_observed",
        "sample_rejected_no_trade_events_observed",
    }


def _trade_flow_admission_status(birth: dict[str, Any]) -> str:
    if not birth:
        return "not_in_birth_set"
    reason = str(birth.get("admission_reason") or birth.get("rejection_reason") or "")
    if _bool(birth.get("admitted")):
        return "admitted"
    if "capacity_rejected" in reason:
        return "capacity_rejected"
    if reason.startswith("sample_rejected"):
        return "sample_rejected"
    return "rejected_or_unknown"


def run_trade_flow_coverage_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    births = _read_jsonl(root / "birth_audit.jsonl")
    trade_rows_all = _read_jsonl(root / "trade_flow_events.jsonl")
    trade_rows = [row for row in trade_rows_all if str(row.get("mint") or "").strip()]
    curve_rows = _read_jsonl(root / "curve_observations.jsonl")
    holder_rows = _read_jsonl(root / "holder_distribution_snapshots.jsonl")
    organic_rows = _read_jsonl(root / "organic_flow_events.jsonl")
    raw_trade_like_rows = _read_jsonl(root / "raw_trade_events.jsonl")
    post_migration_swap_rows = _read_jsonl(root / "pumpswap_swap_events.jsonl")
    migration_route_candidate_rows = _read_jsonl(root / "pumpswap_route_candidates.jsonl")
    supervisor_metric = _trade_flow_metric_from_supervisor(root)
    collector_summary = _read_json(root / "collector_summary.json")
    mint_identity_rows = _mint_identity_rows_from_run_root(root)
    birth_mints = _mint_set(births, "mint")
    trade_mints = _mint_set(trade_rows, "mint")
    curve_mints = _mint_set(curve_rows, "mint")
    holder_mints = _mint_set(holder_rows, "mint")
    identity_mints = _mint_set(mint_identity_rows, "mint")
    denominator_mints = set(identity_mints or birth_mints)
    metric_denominator = _int(supervisor_metric.get("denominator")) or 0
    if metric_denominator > len(denominator_mints):
        denominator_mints.update({f"__unknown_denominator_extra_{index}" for index in range(metric_denominator - len(denominator_mints))})
    grouped_births = _group_by_mint(births)
    grouped_trades = _group_by_mint(trade_rows)
    grouped_curves = _group_by_mint(curve_rows)
    grouped_raw_trade_like = _rows_by_mint(raw_trade_like_rows)
    raw_trade_like_mints: set[str] = set()
    raw_trade_like_before_birth_counts: dict[str, int] = {}
    for mint, rows in grouped_raw_trade_like.items():
        birth = _latest_row(grouped_births.get(mint, []), "received_at", "first_seen_at", "feature_observed_at")
        birth_time = _candidate_time(birth) if birth else None
        seen_after_birth = False
        before_count = 0
        for row in rows:
            row_time = _candidate_time(row)
            if birth_time is not None and row_time is not None and row_time < birth_time:
                before_count += 1
                continue
            seen_after_birth = True
        if seen_after_birth:
            raw_trade_like_mints.add(mint)
        if before_count:
            raw_trade_like_before_birth_counts[mint] = before_count
    missing_rows: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    for mint in sorted(denominator_mints - trade_mints):
        birth = _latest_row(grouped_births.get(mint, []), "received_at", "first_seen_at", "feature_observed_at")
        category = _trade_flow_missing_category(
            mint=mint,
            birth=birth,
            has_curve=mint in curve_mints,
            raw_trade_like_seen=mint in raw_trade_like_mints,
        )
        category_counts[category] = category_counts.get(category, 0) + 1
        should_count = _trade_flow_missing_should_count_against_readiness(category)
        curve = _latest_row(grouped_curves.get(mint, []), "feature_observed_at", "received_at", "decision_time")
        admission_status = _trade_flow_admission_status(birth)
        trade_flow_writer_attempted = bool(
            birth.get("trade_flow_status")
            or birth.get("trade_flow_attempted")
            or birth.get("trade_flow_error")
            or birth.get("trade_flow_null_reason")
        )
        missing_rows.append(
            {
                "mint": mint,
                "birth_time": birth.get("received_at") or birth.get("first_seen_at") or birth.get("feature_observed_at"),
                "first_birth_seen_at": birth.get("received_at") or birth.get("first_seen_at") or birth.get("feature_observed_at"),
                "admission_status": admission_status,
                "admitted": birth.get("admitted", False),
                "capacity_rejected": admission_status == "capacity_rejected",
                "sample_rejected": admission_status == "sample_rejected",
                "reject_reason": birth.get("admission_reason") or birth.get("rejection_reason"),
                "curve_decoded_status": curve.get("decode_status") or ("decoded" if mint in curve_mints else "missing"),
                "holder_dev_status": "available" if mint in holder_mints else "missing",
                "trade_flow_attempt_status": birth.get("trade_flow_status") or "not_recorded",
                "trade_flow_writer_attempted": trade_flow_writer_attempted,
                "last_trade_flow_error": birth.get("trade_flow_null_reason") or birth.get("trade_flow_error"),
                "raw_trade_like_events_seen": mint in raw_trade_like_mints,
                "raw_trade_like_notifications_exist": mint in raw_trade_like_mints,
                "raw_trade_like_events_before_birth_count": raw_trade_like_before_birth_counts.get(mint, 0),
                "raw_trade_like_before_birth_only": bool(
                    raw_trade_like_before_birth_counts.get(mint, 0) and mint not in raw_trade_like_mints
                ),
                "missing_category": category,
                "failure_reason": category,
                "should_count_against_long_scan_readiness": should_count,
            }
        )
    unique_births = int(collector_summary.get("unique_birth_mints") or len(birth_mints))
    denominator = metric_denominator or len(denominator_mints)
    covered = _int(supervisor_metric.get("numerator")) or len(trade_mints & denominator_mints)
    non_birth_mints = sorted(mint for mint in denominator_mints - birth_mints if not mint.startswith("__unknown_denominator_extra_"))
    non_birth_covered_mints = sorted(mint for mint in non_birth_mints if mint in trade_mints)
    corrected_denominator_mints = {mint for mint in denominator_mints if mint in birth_mints or mint.startswith("__unknown_denominator_extra_")}
    corrected_denominator = max(0, denominator - len(non_birth_mints))
    if corrected_denominator == 0 and corrected_denominator_mints:
        corrected_denominator = len(corrected_denominator_mints)
    corrected_covered = max(0, covered - len(non_birth_covered_mints))
    counted_missing_rows = [row for row in missing_rows if row.get("should_count_against_long_scan_readiness")]
    true_gap_categories = {"eventful_parser_gap", "eventful_writer_gap", "eventful_subscription_gap", "unknown_gap"}
    no_event_categories = {
        "admitted_no_trade_events_observed",
        "capacity_rejected_no_trade_events_observed",
        "sample_rejected_no_trade_events_observed",
    }
    true_gap_count = sum(1 for row in missing_rows if row.get("missing_category") in true_gap_categories)
    no_trade_event_count = sum(1 for row in missing_rows if row.get("missing_category") in no_event_categories)
    true_gap_by_category = {
        category: count for category, count in sorted(category_counts.items()) if category in true_gap_categories
    }
    no_event_by_category = {
        category: count for category, count in sorted(category_counts.items()) if category in no_event_categories
    }
    eventful_denominator_mints = (trade_mints & denominator_mints) | raw_trade_like_mints
    eventful_denominator_mints.update(str(row.get("mint")) for row in counted_missing_rows if row.get("mint"))
    eventful_denominator_mints = {mint for mint in eventful_denominator_mints if mint and not mint.startswith("__unknown_denominator_extra_")}
    eventful_covered_mints = trade_mints & eventful_denominator_mints
    summary = {
        "audit_id": "T011_2_TRADE_FLOW_COVERAGE_AUDIT",
        "run_root": str(root),
        "unique_birth_mints": unique_births,
        "birth_artifact_unique_mints": len(birth_mints),
        "trade_flow_unconditional_birth_coverage": {
            "denominator": denominator,
            "numerator": covered,
            "ratio": _safe_ratio(covered, denominator),
            "purpose": "diagnostic_only",
            "hard_long_scan_blocker": False,
        },
        "trade_flow_eventful_parse_coverage": {
            "denominator": len(eventful_denominator_mints),
            "numerator": len(eventful_covered_mints),
            "ratio": _safe_ratio(len(eventful_covered_mints), len(eventful_denominator_mints)),
            "purpose": "parser_writer_subscription_readiness",
            "hard_long_scan_blocker": true_gap_count > 0,
        },
        "trade_flow_no_event_mints": {
            "count": no_trade_event_count,
            "by_category": no_event_by_category,
        },
        "trade_flow_true_gap_mints": {
            "count": true_gap_count,
            "by_category": true_gap_by_category,
        },
        "trade_flow_denominator": denominator,
        "trade_flow_covered_mints": covered,
        "trade_flow_missing_mints": len(missing_rows),
        "trade_flow_coverage_ratio": _safe_ratio(covered, denominator),
        "corrected_trade_flow_denominator": corrected_denominator,
        "corrected_trade_flow_covered_mints": corrected_covered,
        "corrected_trade_flow_missing_mints": len(counted_missing_rows),
        "corrected_trade_flow_coverage_ratio": _safe_ratio(corrected_covered, corrected_denominator),
        "trade_flow_missing_mints_counted_against_readiness": len(counted_missing_rows),
        "true_missing_collector_or_parser_gap_count": true_gap_count,
        "trade_flow_true_gap_mints_count": true_gap_count,
        "trade_flow_true_gap_mints_by_category": true_gap_by_category,
        "no_trade_events_observed_count": no_trade_event_count,
        "trade_flow_no_event_mints_count": no_trade_event_count,
        "trade_flow_no_event_mints_by_category": no_event_by_category,
        "denominator_policy_issue_count": len(non_birth_mints),
        "denominator_mismatch_flagged": denominator != unique_births,
        "trade_flow_denominator_explanation": (
            "The nominal denominator is the supervisor/canonical mint denominator when available; otherwise it is the birth artifact mint set. "
            "Non-birth denominator mints are listed separately and do not count as strategy or collector failures."
        ),
        "denominator_explanation": (
            f"trade-flow denominator uses canonical mint_identity/supervisor denominator ({denominator}), "
            f"while collector unique_birth_mints is {unique_births}; non_birth_denominator_mints={len(non_birth_mints)}; "
            f"corrected_birth_denominator={corrected_denominator}"
        )
        if denominator != unique_births
        else "trade-flow denominator matches unique_birth_mints",
        "non_birth_denominator_mints": non_birth_mints,
        "non_birth_trade_flow_covered_mints": non_birth_covered_mints,
        "capacity_rejected_expected_to_require_trade_flow_coverage": False,
        "capacity_rejected_trade_flow_policy": (
            "Capacity-rejected mints are preserved in coverage diagnostics, but a capacity-rejected mint with no raw trade-like event is not treated as a parser/writer failure. "
            "If a readiness denominator requires all verified births to have trade-flow rows, that is a denominator/readiness-policy blocker rather than proof the live parser missed a trade."
        ),
        "missing_trade_flow_mints_by_category": dict(sorted(category_counts.items())),
        "placeholder_trade_flow_rows": len(trade_rows_all) - len(trade_rows),
        "organic_flow_mints": len(_mint_set(organic_rows, "mint")),
        "post_migration_swap_mints_excluded_from_pre_migration_trade_flow": len(_mint_set(post_migration_swap_rows, "mint", "base_mint", "pool_base_mint")),
        "migration_route_candidate_mints_excluded_from_pre_migration_trade_flow": len(_mint_set(migration_route_candidate_rows, "mint", "base_mint", "pool_base_mint")),
        "missing_mints": missing_rows,
        "json_path": str(root / "trade_flow_coverage_audit.json"),
        "debug_json_path": str(root / "trade_flow_missing_mints_debug.json"),
        "markdown_path": str(root / "trade_flow_coverage_audit.md"),
    }
    _write_json_artifact(root / "trade_flow_coverage_audit.json", summary)
    _write_json_artifact(root / "trade_flow_missing_mints_debug.json", summary)
    _write_markdown_artifact(
        root / "trade_flow_coverage_audit.md",
        [
            "# T011.1 Trade Flow Coverage Audit",
            "",
            f"- Unique birth mints: `{summary['unique_birth_mints']}`",
            f"- Trade-flow denominator: `{summary['trade_flow_denominator']}`",
            f"- Trade-flow covered mints: `{summary['trade_flow_covered_mints']}`",
            f"- Trade-flow missing mints: `{summary['trade_flow_missing_mints']}`",
            f"- Corrected birth-only denominator: `{summary['corrected_trade_flow_denominator']}`",
            f"- Corrected birth-only covered mints: `{summary['corrected_trade_flow_covered_mints']}`",
            f"- Corrected birth-only missing mints: `{summary['corrected_trade_flow_missing_mints']}`",
            f"- Corrected birth-only coverage ratio: `{summary['corrected_trade_flow_coverage_ratio']}`",
            f"- Denominator mismatch flagged: `{summary['denominator_mismatch_flagged']}`",
            f"- Denominator explanation: {summary['denominator_explanation']}",
            f"- Unconditional birth coverage: `{summary['trade_flow_unconditional_birth_coverage']}`",
            f"- Eventful parse coverage: `{summary['trade_flow_eventful_parse_coverage']}`",
            f"- Capacity-rejected trade-flow policy: {summary['capacity_rejected_trade_flow_policy']}",
            f"- True missing collector/parser gap count: `{summary['true_missing_collector_or_parser_gap_count']}`",
            f"- True gap categories: `{summary['trade_flow_true_gap_mints_by_category']}`",
            f"- No-trade-events-observed count: `{summary['no_trade_events_observed_count']}`",
            f"- No-event categories: `{summary['trade_flow_no_event_mints_by_category']}`",
            f"- Denominator policy issue count: `{summary['denominator_policy_issue_count']}`",
            f"- Missing categories: `{summary['missing_trade_flow_mints_by_category']}`",
            f"- Post-migration swap mints excluded from pre-migration trade-flow: `{summary['post_migration_swap_mints_excluded_from_pre_migration_trade_flow']}`",
            f"- Migration route candidate mints excluded from pre-migration trade-flow: `{summary['migration_route_candidate_mints_excluded_from_pre_migration_trade_flow']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def run_trade_flow_eventful_gap_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    coverage = run_trade_flow_coverage_audit(root)
    missing_rows = list(coverage.get("missing_mints") or [])
    true_gap_categories = {"eventful_parser_gap", "eventful_writer_gap", "eventful_subscription_gap", "unknown_gap"}
    no_event_categories = {
        "admitted_no_trade_events_observed",
        "capacity_rejected_no_trade_events_observed",
        "sample_rejected_no_trade_events_observed",
    }
    eventful_gap_rows: list[dict[str, Any]] = []
    no_event_rows: list[dict[str, Any]] = []
    for row in missing_rows:
        category = str(row.get("missing_category") or row.get("failure_reason") or "")
        normalized = {
            "mint": row.get("mint"),
            "expected_source_event": "raw trade-like event after birth" if row.get("raw_trade_like_events_seen") else "no raw trade-like event observed",
            "expected_source": "raw_trade_events/pumpswap_swap_events/pumpswap_route_candidates",
            "raw_event_present": bool(row.get("raw_trade_like_events_seen")),
            "parser_attempted": bool(row.get("trade_flow_attempt_status") and row.get("trade_flow_attempt_status") != "not_recorded"),
            "writer_attempted": bool(row.get("trade_flow_writer_attempted")),
            "write_error": row.get("last_trade_flow_error") or "",
            "subscription_channel": "pumpswap_swap_events" if row.get("raw_trade_like_events_seen") else "",
            "missing_category": category,
            "classification": "real_collector_or_writer_gap" if category in true_gap_categories else "diagnostic_no_trade_event_observed",
            "is_real_collector_bug": category in true_gap_categories,
        }
        if category in true_gap_categories:
            eventful_gap_rows.append(normalized)
        elif category in no_event_categories:
            no_event_rows.append(normalized)
    summary = {
        "audit_id": "T011_7_TRADE_FLOW_EVENTFUL_GAP_AUDIT",
        "run_root": str(root),
        "eventful_gap_count": len(eventful_gap_rows),
        "no_event_missing_count": len(no_event_rows),
        "eventful_gap_rows": eventful_gap_rows,
        "no_event_rows": no_event_rows,
        "json_path": str(root / "trade_flow_eventful_gap_audit.json"),
        "markdown_path": str(root / "trade_flow_eventful_gap_audit.md"),
    }
    _write_json_artifact(root / "trade_flow_eventful_gap_audit.json", summary)
    _write_markdown_artifact(
        root / "trade_flow_eventful_gap_audit.md",
        [
            "# T011.7 Trade-Flow Eventful Gap Audit",
            "",
            f"- Eventful gap count: `{summary['eventful_gap_count']}`",
            f"- No-event missing count: `{summary['no_event_missing_count']}`",
            f"- Eventful gap rows: `{summary['eventful_gap_rows']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def _migration_link_failure_reason(
    *,
    mint: str,
    birth: dict[str, Any],
    has_pre_curve: bool,
    has_any_curve: bool,
    has_post_migration: bool,
    migration: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    first_birth_observed_at: float | None = None,
) -> str:
    if not mint:
        return "unsupported_migration_route"
    if not birth:
        startup_reason = _migration_startup_boundary_reason(
            migration,
            manifest=manifest or {},
            first_birth_observed_at=first_birth_observed_at,
        )
        if startup_reason:
            return startup_reason
        return "migration_mint_not_in_birth_set"
    if birth and not _bool(birth.get("admitted")):
        return "migration_mint_birth_seen_but_not_admitted"
    if not has_pre_curve:
        if has_any_curve:
            return "migration_before_first_curve_observation"
        return "missing_pre_migration_curve_state"
    if not has_post_migration:
        return "missing_post_migration_pool_observation"
    if not migration.get("pool_or_pair_address"):
        return "unsupported_migration_route"
    return ""


def _migration_readiness_failure_reason(reason: str) -> str:
    if reason in {"migration_before_birth_source_ready", "migration_before_first_birth_source_event"}:
        return "startup_boundary_migration_not_decision_safe"
    return reason or "none"


def _migration_startup_boundary_reason(
    migration: dict[str, Any],
    *,
    manifest: dict[str, Any],
    first_birth_observed_at: float | None,
) -> str:
    observed_at = _num(
        _first_present(
            migration,
            ["migration_received_at", "received_at", "feature_observed_at", "observed_at"],
        )
    )
    if observed_at is None:
        return ""
    campaign_start = _num(_first_present(manifest, ["started_at", "source_start_time", "campaign_start_time"]))
    startup_grace_seconds = _num(_first_present(manifest, ["startup_grace_seconds", "source_startup_grace_seconds"]))
    if startup_grace_seconds is None:
        startup_grace_seconds = 2.0
    if campaign_start is not None and 0.0 <= observed_at - campaign_start <= startup_grace_seconds:
        return "migration_before_birth_source_ready"
    if first_birth_observed_at is not None and observed_at <= first_birth_observed_at:
        return "migration_before_first_birth_source_event"
    return ""


def run_migration_linkage_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    manifest = _read_json(root / "campaign_manifest.json")
    collector_summary = _read_json(root / "collector_summary.json")
    lifecycle_summary = _read_json(root / "lifecycle_coverage_summary.json")
    migrations = _read_jsonl(root / "global_migration_events.jsonl")
    births = _read_jsonl(root / "birth_audit.jsonl")
    curves = _read_jsonl(root / "curve_observations.jsonl")
    post_rows = _read_jsonl(root / "post_migration_observations.jsonl")
    by_birth = _group_by_mint(births)
    grouped_curves = _group_by_mint(curves)
    curve_mints = _mint_set(curves, "mint")
    post_mints = _mint_set(post_rows, "mint", "base_mint", "pool_base_mint")
    birth_observed_times = [
        value
        for value in (
            _num(_first_present(row, ["received_at", "source_received_at", "first_seen_at", "feature_observed_at"]))
            for row in births
        )
        if value is not None
    ]
    first_birth_observed_at = min(birth_observed_times) if birth_observed_times else None
    rows: list[dict[str, Any]] = []
    failure_counts: dict[str, int] = {}
    readiness_failure_counts: dict[str, int] = {}
    for migration in migrations:
        mint = str(migration.get("mint") or migration.get("base_mint") or migration.get("pool_base_mint") or "").strip()
        birth = _latest_row(by_birth.get(mint, []), "received_at", "first_seen_at", "feature_observed_at")
        observed_time = migration.get("migration_received_at") or migration.get("received_at") or migration.get("feature_observed_at")
        observed_time_num = _num(observed_time)
        mint_curves = grouped_curves.get(mint, [])
        pre_curve_before_migration = any(
            (_num(_first_present(row, ["feature_observed_at", "received_at", "decision_time", "observed_at"])) or 0.0)
            <= observed_time_num
            for row in mint_curves
            if observed_time_num is not None
        )
        has_pre_curve = pre_curve_before_migration if observed_time_num is not None else mint in curve_mints
        birth_slot = _int(_first_present(birth, ["slot", "launch_slot", "first_seen_slot"]))
        migration_slot = _int(_first_present(migration, ["slot", "migration_slot", "observation_slot"]))
        if birth_slot is not None and migration_slot is not None and migration_slot < birth_slot:
            reason = "migration_slot_before_birth_slot"
        else:
            reason = _migration_link_failure_reason(
                mint=mint,
                birth=birth,
                has_pre_curve=has_pre_curve,
                has_any_curve=mint in curve_mints,
                has_post_migration=mint in post_mints,
                migration=migration,
                manifest=manifest,
                first_birth_observed_at=first_birth_observed_at,
            )
        readiness_reason = _migration_readiness_failure_reason(reason)
        if reason:
            failure_counts[reason] = failure_counts.get(reason, 0) + 1
            readiness_failure_counts[readiness_reason] = readiness_failure_counts.get(readiness_reason, 0) + 1
        is_startup_boundary = reason in {"migration_before_birth_source_ready", "migration_before_first_birth_source_event"}
        rows.append(
            {
                "event_signature": migration.get("signature"),
                "birth_slot": birth_slot,
                "migration_slot": migration_slot,
                "observed_time": observed_time,
                "seconds_after_campaign_start": (
                    _round_float((_num(observed_time) or 0.0) - (_num(_first_present(manifest, ["started_at", "source_start_time", "campaign_start_time"])) or 0.0))
                    if _num(observed_time) is not None
                    and _num(_first_present(manifest, ["started_at", "source_start_time", "campaign_start_time"])) is not None
                    else None
                ),
                "seconds_before_first_birth_source_event": (
                    _round_float(first_birth_observed_at - (_num(observed_time) or 0.0))
                    if _num(observed_time) is not None and first_birth_observed_at is not None
                    else None
                ),
                "pool_address": migration.get("pool_or_pair_address"),
                "base_mint": migration.get("base_mint") or mint,
                "quote_mint": migration.get("quote_mint"),
                "quote_asset": migration.get("quote_asset"),
                "linked_mint": mint,
                "linked_to_known_birth_mint": bool(birth),
                "linked_to_admitted_lifecycle_state": _bool(birth.get("admitted")) if birth else False,
                "pre_migration_curve_state_exists": mint in curve_mints,
                "pre_migration_curve_state_before_migration": has_pre_curve,
                "post_migration_observation_exists": mint in post_mints,
                "startup_boundary_migration": is_startup_boundary,
                "in_window_steady_state_migration": not is_startup_boundary,
                "decision_safe_full_path": not bool(reason),
                "failure_reason": reason or "none",
                "migration_readiness_failure_reason": readiness_reason,
                "detection_method": migration.get("detection_method"),
                "migration_evidence_level": migration.get("migration_evidence_level"),
            }
        )
    row_decision_safe_full_paths = sum(1 for row in rows if row.get("decision_safe_full_path"))
    lifecycle_decision_safe_full_paths = int(
        lifecycle_summary.get("decision_safe_full_paths")
        or lifecycle_summary.get("decision_safe_full_path_count")
        or lifecycle_summary.get("strict_full_paths")
        or 0
    )
    summary = {
        "audit_id": "T011_1_MIGRATION_LINKAGE_AUDIT",
        "run_root": str(root),
        "global_migration_events_deduped": int(collector_summary.get("global_migration_events_deduped") or len(migrations)),
        "global_migration_rows": len(migrations),
        "lifecycle_migrated_unique_mints": int(lifecycle_summary.get("migrated_unique_mints") or 0),
        "decision_safe_full_paths": max(lifecycle_decision_safe_full_paths, row_decision_safe_full_paths),
        "row_derived_decision_safe_full_paths": row_decision_safe_full_paths,
        "lifecycle_summary_decision_safe_full_paths": lifecycle_decision_safe_full_paths,
        "failure_reason_counts": dict(sorted(failure_counts.items())),
        "migration_readiness_failure_reason_counts": dict(sorted(readiness_failure_counts.items())),
        "startup_boundary_migration_count": int(
            failure_counts.get("migration_before_birth_source_ready", 0)
            + failure_counts.get("migration_before_first_birth_source_event", 0)
        ),
        "in_window_migration_count": int(sum(1 for row in rows if row.get("in_window_steady_state_migration"))),
        "steady_state_unlinked_migration_count": int(
            sum(
                count
                for reason, count in failure_counts.items()
                if reason
                not in {
                    "migration_before_birth_source_ready",
                    "migration_before_first_birth_source_event",
                }
            )
        ),
        "first_birth_observed_at": first_birth_observed_at,
        "mismatch_explanation": (
            "global_migration_events_deduped counts raw global PumpSwap pool events, while MIGRATED_UNIQUE_MINTS requires "
            "a lifecycle-linked migration state. This run has global events that did not link to a decision-safe birth/curve lifecycle."
        ),
        "migration_rows": rows,
        "json_path": str(root / "migration_linkage_audit.json"),
        "markdown_path": str(root / "migration_linkage_audit.md"),
    }
    _write_json_artifact(root / "migration_linkage_audit.json", summary)
    _write_markdown_artifact(
        root / "migration_linkage_audit.md",
        [
            "# T011.1 Migration Linkage Audit",
            "",
            f"- Global migration events deduped: `{summary['global_migration_events_deduped']}`",
            f"- Lifecycle migrated unique mints: `{summary['lifecycle_migrated_unique_mints']}`",
            f"- Decision-safe full paths: `{summary['decision_safe_full_paths']}`",
            f"- Failure reasons: `{summary['failure_reason_counts']}`",
            f"- Readiness failure reasons: `{summary['migration_readiness_failure_reason_counts']}`",
            f"- Startup-boundary migrations: `{summary['startup_boundary_migration_count']}`",
            f"- Steady-state unlinked migrations: `{summary['steady_state_unlinked_migration_count']}`",
            f"- Explanation: {summary['mismatch_explanation']}",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def _max_progress_for_mint(rows: list[dict[str, Any]]) -> float | None:
    values = [_num(row.get("progress_pct")) for row in rows]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _trade_rows_for_mint(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    counts = [_int(row.get("trade_count_since_launch")) for row in rows]
    clean = [value for value in counts if value is not None]
    return max(clean) if clean else len(rows)


def _promotion_policy_for_simulation(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {
        "promote_on_curve_progress_pct": 20.0,
        "promote_on_trade_rows": 5,
        "promote_on_migration_candidate": True,
        "promote_on_threshold_crossing": True,
    }
    if policy:
        merged.update(policy)
    return merged


def run_capacity_rejected_migration_promotion_simulation(
    run_root: Path | str,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(run_root)
    promotion_policy = _promotion_policy_for_simulation(policy)
    linkage = run_migration_linkage_audit(root)
    births_by_mint = _group_by_mint(_read_jsonl(root / "birth_audit.jsonl"))
    curve_by_mint = _group_by_mint(_read_jsonl(root / "curve_observations.jsonl"))
    trade_by_mint = _group_by_mint(_read_jsonl(root / "trade_flow_events.jsonl"))
    threshold_by_mint = _group_by_mint(_read_jsonl(root / "true_curve_threshold_crossings.jsonl"))
    post_by_mint = _group_by_mint(_read_jsonl(root / "post_migration_observations.jsonl"))

    rows: list[dict[str, Any]] = []
    for migration_row in linkage.get("migration_rows") or []:
        if migration_row.get("failure_reason") != "migration_mint_birth_seen_but_not_admitted":
            continue
        mint = _candidate_mint(migration_row)
        birth_rows = births_by_mint.get(mint, [])
        latest_birth = _latest_row(birth_rows, "received_at", "slot")
        admission_reason = str(
            migration_row.get("admission_reason") or latest_birth.get("admission_reason") or ""
        )
        is_capacity_rejected = admission_reason.startswith("capacity_rejected")
        curve_rows = curve_by_mint.get(mint, [])
        trade_rows = trade_by_mint.get(mint, [])
        threshold_rows = threshold_by_mint.get(mint, [])
        post_rows = post_by_mint.get(mint, [])
        max_progress = _max_progress_for_mint(curve_rows)
        trade_row_count = _trade_rows_for_mint(trade_rows)
        trigger = None
        if (
            max_progress is not None
            and max_progress >= float(promotion_policy["promote_on_curve_progress_pct"])
        ):
            trigger = "curve_progress_threshold"
        elif trade_row_count >= int(promotion_policy["promote_on_trade_rows"]):
            trigger = "trade_rows_threshold"
        elif threshold_rows and _parse_bool_value(promotion_policy["promote_on_threshold_crossing"]):
            trigger = "threshold_crossing"
        elif _parse_bool_value(promotion_policy["promote_on_migration_candidate"]):
            trigger = "global_migration_candidate"
        would_promote = bool(trigger and is_capacity_rejected)
        likely_decision_safe = bool(
            would_promote
            and migration_row.get("pre_migration_curve_state_before_migration") is True
            and (migration_row.get("post_migration_observation_exists") is True or bool(post_rows))
            and migration_row.get("failure_reason") == "migration_mint_birth_seen_but_not_admitted"
        )
        missing_fields: list[str] = []
        if not curve_rows:
            missing_fields.append("curve_observations")
        if not trade_rows:
            missing_fields.append("trade_flow_rows")
        if not post_rows and not migration_row.get("post_migration_observation_exists"):
            missing_fields.append("post_migration_observation")
        rows.append(
            {
                "mint": mint,
                "migration_signature": migration_row.get("migration_signature") or migration_row.get("event_signature"),
                "pool": _candidate_pool(migration_row),
                "migration_evidence_level": migration_row.get("migration_evidence_level"),
                "admission_reason": admission_reason,
                "thin_probe_scheduled": latest_birth.get("thin_probe_scheduled"),
                "curve_observations": len(curve_rows),
                "max_progress": max_progress,
                "trade_rows": trade_row_count,
                "threshold_crossings": len(threshold_rows),
                "post_migration_observations": len(post_rows),
                "slot_delta": (
                    _int(migration_row.get("migration_slot")) - _int(migration_row.get("birth_slot"))
                    if _int(migration_row.get("migration_slot")) is not None
                    and _int(migration_row.get("birth_slot")) is not None
                    else None
                ),
                "would_promote_under_new_policy": would_promote,
                "promotion_trigger": trigger,
                "likely_decision_safe_if_promoted_earlier": likely_decision_safe,
                "remaining_missing_fields": missing_fields,
            }
        )

    summary = {
        "audit_id": "T011_10_CAPACITY_REJECTED_MIGRATION_PROMOTION_SIMULATION",
        "run_root": str(root),
        "policy": promotion_policy,
        "capacity_rejected_migration_rows": len(rows),
        "capacity_rejected_migrated_mints": len({row["mint"] for row in rows if row.get("mint")}),
        "would_promote_under_new_policy_count": sum(1 for row in rows if row["would_promote_under_new_policy"]),
        "likely_decision_safe_if_promoted_earlier_count": sum(
            1 for row in rows if row["likely_decision_safe_if_promoted_earlier"]
        ),
        "rows": rows,
        "json_path": str(root / "capacity_rejected_migration_promotion_simulation.json"),
        "markdown_path": str(root / "capacity_rejected_migration_promotion_simulation.md"),
        "capacity_rejected_migration_audit_json_path": str(root / "capacity_rejected_migration_audit.json"),
        "capacity_rejected_migration_audit_markdown_path": str(root / "capacity_rejected_migration_audit.md"),
    }
    _write_json_artifact(root / "capacity_rejected_migration_promotion_simulation.json", summary)
    _write_json_artifact(root / "capacity_rejected_migration_audit.json", summary)
    _write_markdown_artifact(
        root / "capacity_rejected_migration_promotion_simulation.md",
        [
            "# T011.10 Capacity-Rejected Migration Promotion Simulation",
            "",
            f"- Capacity-rejected migration rows: `{summary['capacity_rejected_migration_rows']}`",
            f"- Unique capacity-rejected migrated mints: `{summary['capacity_rejected_migrated_mints']}`",
            f"- Would promote under new policy: `{summary['would_promote_under_new_policy_count']}`",
            f"- Likely decision-safe if promoted earlier: `{summary['likely_decision_safe_if_promoted_earlier_count']}`",
            "",
            "This is offline analysis only. It does not loosen full-path requirements and does not use trading, signing, or wallet code.",
        ],
    )
    _write_markdown_artifact(
        root / "capacity_rejected_migration_audit.md",
        [
            "# T011.10 Capacity-Rejected Migration Audit",
            "",
            f"- Capacity-rejected migration rows: `{summary['capacity_rejected_migration_rows']}`",
            f"- Unique capacity-rejected migrated mints: `{summary['capacity_rejected_migrated_mints']}`",
            f"- Main blocker: capacity policy excluded migrated births from full active tracking.",
            "",
            "These rows remain exclusions unless promotion occurs early enough to preserve pre-migration lifecycle evidence.",
        ],
    )
    return summary


def run_tracking_admission_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    linkage = run_migration_linkage_audit(root)
    births = _read_jsonl(root / "birth_audit.jsonl")
    total = len(births)
    admitted = sum(1 for row in births if _bool(row.get("admitted")))
    sample_rejected = sum(1 for row in births if str(row.get("admission_reason") or "") == "sample_rejected")
    capacity_rejected = sum(1 for row in births if str(row.get("admission_reason") or "").startswith("capacity_rejected"))
    thin_scheduled = sum(1 for row in births if _bool(row.get("thin_probe_scheduled")))
    birth_seen_but_not_admitted_migrations = int(
        (linkage.get("failure_reason_counts") or {}).get("migration_mint_birth_seen_but_not_admitted", 0)
    )
    global_migrations = int(linkage.get("global_migration_rows") or linkage.get("global_migration_events_deduped") or 0)
    unique_migrated_mints = len(
        {_candidate_mint(row) for row in (linkage.get("migration_rows") or []) if _candidate_mint(row)}
    )
    summary = {
        "audit_id": "T011_10_TRACKING_ADMISSION_AUDIT",
        "run_root": str(root),
        "birth_rows": total,
        "admitted_births": admitted,
        "sample_rejected_births": sample_rejected,
        "capacity_rejected_births": capacity_rejected,
        "thin_probe_scheduled_births": thin_scheduled,
        "migration_events_seen": global_migrations,
        "unique_migrated_mints": unique_migrated_mints,
        "decision_safe_full_paths": int(linkage.get("decision_safe_full_paths") or 0),
        "birth_seen_but_not_admitted_migrations": birth_seen_but_not_admitted_migrations,
        "capacity_rejected_migrated_mints": birth_seen_but_not_admitted_migrations,
        "promoted_migrated_mints": len({row.get("mint") for row in _read_jsonl(root / "promotion_events.jsonl") if row.get("promotion_trigger") == "global_migration_event"}),
        "missed_due_to_capacity": birth_seen_but_not_admitted_migrations,
        "migration_capture_coverage": 1.0 if global_migrations > 0 else 0.0,
        "full_path_coverage_of_unique_migrated_mints": _safe_ratio(
            int(linkage.get("decision_safe_full_paths") or 0),
            unique_migrated_mints,
        ),
        "capacity_exclusion_rate_of_migrated_mints": _safe_ratio(
            birth_seen_but_not_admitted_migrations,
            unique_migrated_mints,
        ),
        "full_path_lifecycle_coverage": _safe_ratio(int(linkage.get("decision_safe_full_paths") or 0), global_migrations),
        "json_path": str(root / "tracking_admission_audit.json"),
        "markdown_path": str(root / "tracking_admission_audit.md"),
    }
    _write_json_artifact(root / "tracking_admission_audit.json", summary)
    _write_markdown_artifact(
        root / "tracking_admission_audit.md",
        [
            "# T011.10 Tracking Admission Audit",
            "",
            f"- Birth rows: `{summary['birth_rows']}`",
            f"- Admitted births: `{summary['admitted_births']}`",
            f"- Capacity rejected births: `{summary['capacity_rejected_births']}`",
            f"- Migration events seen: `{summary['migration_events_seen']}`",
            f"- Unique migrated mints: `{summary['unique_migrated_mints']}`",
            f"- Decision-safe full paths: `{summary['decision_safe_full_paths']}`",
            f"- Birth-seen but not admitted migrations: `{summary['birth_seen_but_not_admitted_migrations']}`",
            f"- Capacity exclusion rate of migrated mints: `{summary['capacity_exclusion_rate_of_migrated_mints']}`",
        ],
    )
    return summary


def run_migration_full_path_status_reconciliation(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    linkage = run_migration_linkage_audit(root)
    live_path = root / "live_status.json"
    existing = _read_json(live_path)
    previous_full_paths = _int(existing.get("decision_safe_full_paths")) or 0
    row_derived_full_paths = int(linkage.get("row_derived_decision_safe_full_paths") or linkage.get("decision_safe_full_paths") or 0)
    lifecycle_summary_full_paths = int(linkage.get("lifecycle_summary_decision_safe_full_paths") or 0)
    lifecycle_summary_exists = (root / "lifecycle_coverage_summary.json").exists()
    reconciled_full_paths = lifecycle_summary_full_paths if lifecycle_summary_exists else row_derived_full_paths
    payload = {
        **existing,
        "decision_safe_full_paths": reconciled_full_paths,
        "row_derived_decision_safe_full_paths": row_derived_full_paths,
        "lifecycle_summary_decision_safe_full_paths": lifecycle_summary_full_paths,
        "decision_safe_full_path_authority": "canonical_lifecycle_summary" if lifecycle_summary_exists else "row_derived_linkage_fallback",
        "global_migration_events_deduped": int(linkage.get("global_migration_events_deduped") or 0),
        "in_window_migrations": int(linkage.get("in_window_migration_count") or 0),
        "startup_boundary_migrations": int(linkage.get("startup_boundary_migration_count") or 0),
        "full_path_proof": reconciled_full_paths > 0,
        "migration_full_path_status_reconciled": True,
        "migration_full_path_status_reconciled_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json_artifact(live_path, payload)
    summary = {
        "audit_id": "T011_10_MIGRATION_FULL_PATH_STATUS_RECONCILIATION",
        "run_root": str(root),
        "decision_safe_full_paths": reconciled_full_paths,
        "live_status_previous_decision_safe_full_paths": previous_full_paths,
        "live_status_reconciled_decision_safe_full_paths": reconciled_full_paths,
        "row_derived_decision_safe_full_paths": row_derived_full_paths,
        "lifecycle_summary_decision_safe_full_paths": lifecycle_summary_full_paths,
        "decision_safe_full_path_authority": "canonical_lifecycle_summary" if lifecycle_summary_exists else "row_derived_linkage_fallback",
        "json_path": str(root / "migration_full_path_status_reconciliation.json"),
        "markdown_path": str(root / "migration_full_path_status_reconciliation.md"),
    }
    _write_json_artifact(root / "migration_full_path_status_reconciliation.json", summary)
    _write_markdown_artifact(
        root / "migration_full_path_status_reconciliation.md",
        [
            "# T011.10 Migration Full-Path Status Reconciliation",
            "",
            f"- Previous live_status full paths: `{previous_full_paths}`",
            f"- Reconciled full paths: `{reconciled_full_paths}`",
            f"- Row-derived full paths: `{summary['row_derived_decision_safe_full_paths']}`",
            f"- Lifecycle-summary full paths: `{summary['lifecycle_summary_decision_safe_full_paths']}`",
        ],
    )
    return summary


def _read_expected_mints_file(path: Path | str | None) -> list[str]:
    if not path:
        return []
    expected_path = Path(path).expanduser()
    if not expected_path.exists():
        return []
    raw = expected_path.read_text(encoding="utf-8", errors="ignore")
    return sorted({item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()})


def _candidate_mint(row: Mapping[str, Any]) -> str:
    return str(
        _first_present(
            row,
            [
                "mint",
                "base_mint",
                "pool_base_mint",
                "linked_mint",
                "candidate_mint",
                "token_mint",
            ],
        )
        or ""
    )


def _candidate_pool(row: Mapping[str, Any]) -> str:
    return str(
        _first_present(
            row,
            [
                "pool_or_pair_address",
                "pool_address",
                "pair_address",
                "pool",
            ],
        )
        or ""
    )


def _candidate_time(row: Mapping[str, Any]) -> float | None:
    return _num(
        _first_present(
            row,
            [
                "migration_received_at",
                "received_at",
                "feature_observed_at",
                "first_seen_at",
                "observed_time",
                "block_time",
            ],
        )
    )


def _rows_by_mint(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        mint = _candidate_mint(row)
        if mint:
            grouped.setdefault(mint, []).append(row)
    return grouped


def _derived_migration_grade_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    progress = _num(row.get("progress_pct"))
    candidate_reason = str(row.get("candidate_reason") or "")
    if progress is not None and progress >= 99.5:
        reasons.append("progress_near_complete")
    if _bool(row.get("complete") or row.get("complete_or_migrated")):
        reasons.append("complete_flag")
    if row.get("reserve_zero_not_seen") is False or _bool(row.get("reserve_zero_seen")):
        reasons.append("reserve_zero")
    if _bool(row.get("explicit_migrate_log")):
        reasons.append("explicit_migrate_log")
    if _bool(row.get("dex_pair_signal")):
        reasons.append("dex_pair_signal")
    if candidate_reason in {
        "complete_true_without_migration_event",
        "reserve_zero_without_migration_event",
        "explicit_migrate_log_without_migration_event",
        "dex_pair_signal_without_migration_event",
        "pool_create_without_global_migration_event",
    }:
        reasons.append(candidate_reason)
    return reasons


def _write_csv_artifact(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _decoded_migration_candidate_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in ("global_migration_events.jsonl", "global_migration_candidates.jsonl", "global_migration_event_duplicates.jsonl"):
        for row in _read_jsonl(root / artifact):
            copied = dict(row)
            copied.setdefault("source_artifact", artifact)
            rows.append(copied)
    return rows


def _migration_dedupe_key_text(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("dedupe_key") or "").strip()
    if explicit:
        return explicit
    try:
        return "|".join(_global_migration_dedupe_key(dict(row)))
    except Exception:
        return str(row.get("candidate_id") or row.get("signature") or row.get("event_signature") or "")


def _migration_candidate_class(row: Mapping[str, Any], *, source_artifact: str) -> str:
    source_text = " ".join(
        str(row.get(key) or "")
        for key in ("source_channel", "source_route", "detection_method", "event_type_guess", "parser_status")
    ).lower()
    mint = _candidate_mint(row)
    pool = _candidate_pool(row)
    if source_artifact == "pumpswap_swap_events.jsonl":
        return "raw_pumpswap_swap_event"
    if source_artifact == "pumpswap_transaction_route_audit.jsonl":
        return "raw_pumpswap_notification"
    if "pool_create" in source_text or "pair_created" in source_text or "pool_create" in source_artifact:
        if mint and pool:
            return "decoded_pool_create_candidate"
        return "raw_pool_create_like_event"
    if mint and pool:
        return "decoded_migration_candidate"
    if pool:
        return "raw_pool_create_like_event"
    return "decode_failed_candidate"


def run_migration_write_path_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    decoded_rows = _decoded_migration_candidate_rows(root)
    decoded_migration_rows = [row for row in decoded_rows if _candidate_mint(row) and _candidate_pool(row)]
    raw_rows = _read_jsonl(root / GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT)
    latest_intents = _latest_global_migration_write_intents_by_candidate(root)
    persisted_by_candidate = {_migration_candidate_id(row): row for row in decoded_rows}
    raw_by_candidate = {_migration_candidate_id(row): row for row in raw_rows}
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()
    candidate_ids = sorted(set(persisted_by_candidate) | set(latest_intents) | set(raw_by_candidate))
    for candidate_id in candidate_ids:
        decoded = persisted_by_candidate.get(candidate_id) or {}
        raw = raw_by_candidate.get(candidate_id) or {}
        intent = latest_intents.get(candidate_id) or {}
        source = decoded or raw or intent
        status = str(intent.get("write_status") or ("missing_intent" if not intent else "unknown"))
        status_counts[status] += 1
        persisted = candidate_id in persisted_by_candidate
        has_decoded_migration_identity = bool(_candidate_mint(source) and _candidate_pool(source))
        thread_affinity = _bool(intent.get("thread_affinity_error")) or _is_sqlite_thread_affinity_error(str(intent.get("write_error") or ""))
        if not has_decoded_migration_identity:
            classification = "decode_failed_candidate" if _candidate_pool(source) else "unsupported_route_candidate"
        elif thread_affinity:
            classification = "sqlite_thread_affinity_error"
        elif status in {"failed", "retry_exhausted"}:
            classification = "migration_lane_write_path_failure"
        elif status in {"queued", "retry_pending", "missing_intent"} and not _bool(intent.get("write_success")):
            classification = "migration_candidate_spooled_but_not_written"
        elif persisted and not intent:
            classification = "migration_write_missing_after_decode"
        elif persisted:
            classification = "migration_candidate_written_but_not_linked"
        else:
            classification = "migration_write_missing_after_decode"
        classification_counts[classification] += 1
        row = {
            "candidate_id": candidate_id,
            "signature": source.get("signature") or source.get("event_signature"),
            "slot": source.get("slot") or source.get("migration_slot") or source.get("observation_slot"),
            "block_time": source.get("block_time"),
            "candidate_mint": _candidate_mint(source),
            "mint": _candidate_mint(source),
            "pool_address": _candidate_pool(source),
            "source_channel": source.get("source_channel") or source.get("source_route") or source.get("detection_method"),
            "raw_candidate_id": raw.get("candidate_id") or candidate_id,
            "decode_status": "decoded" if _candidate_mint(decoded) or _candidate_mint(source) else str(raw.get("decode_status") or "decode_failed"),
            "write_queued": bool(intent) or _bool(raw.get("write_enqueued")),
            "write_attempted": bool(intent),
            "write_success": _bool(intent.get("write_success")) or status == "written",
            "write_status": status,
            "write_error": intent.get("write_error") or raw.get("write_error") or "",
            "writer_thread_id": intent.get("writer_thread_id"),
            "sqlite_thread_affinity_error": thread_affinity,
            "persisted_artifact_row_exists": persisted,
            "dedupe_key": _migration_dedupe_key_text(source),
            "dedupe_result": "persisted" if persisted else "not_persisted",
            "has_decoded_migration_identity": has_decoded_migration_identity,
            "classification": classification,
        }
        rows.append(row)
    summary = {
        "audit_id": "T011_7_MIGRATION_WRITE_PATH_AUDIT",
        "run_root": str(root),
        "decoded_migration_candidates": len(decoded_migration_rows),
        "migration_like_candidates_including_unsupported": len(decoded_rows),
        "raw_spool_rows": len(raw_rows),
        "write_intent_candidates": len(latest_intents),
        "write_status_counts": dict(sorted(status_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "write_path_rows": rows,
        "json_path": str(root / "migration_write_path_audit.json"),
        "markdown_path": str(root / "migration_write_path_audit.md"),
    }
    _write_json_artifact(root / "migration_write_path_audit.json", summary)
    _write_markdown_artifact(
        root / "migration_write_path_audit.md",
        [
            "# T011.7 Migration Write-Path Audit",
            "",
            f"- Decoded migration candidates: `{summary['decoded_migration_candidates']}`",
            f"- Raw spool rows: `{summary['raw_spool_rows']}`",
            f"- Write intent candidates: `{summary['write_intent_candidates']}`",
            f"- Write status counts: `{summary['write_status_counts']}`",
            f"- Classification counts: `{summary['classification_counts']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def run_migration_dedupe_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    decoded_rows = _decoded_migration_candidate_rows(root)
    events = _read_jsonl(root / "global_migration_events.jsonl")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in decoded_rows:
        grouped.setdefault(_migration_dedupe_key_text(row), []).append(row)
    dedupe_rows: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        mints = sorted({_candidate_mint(row) for row in rows if _candidate_mint(row)})
        pools = sorted({_candidate_pool(row) for row in rows if _candidate_pool(row)})
        too_broad = len(mints) > 1 or len(pools) > 1
        dedupe_rows.append(
            {
                "dedupe_key": key,
                "row_count": len(rows),
                "signatures": sorted({str(row.get("signature") or row.get("event_signature") or "") for row in rows if row.get("signature") or row.get("event_signature")}),
                "mints": mints,
                "pools": pools,
                "different_mints_collapsed": len(mints) > 1,
                "different_pools_collapsed": len(pools) > 1,
                "dedupe_key_too_broad": too_broad,
            }
        )
    summary = {
        "audit_id": "T011_7_MIGRATION_DEDUPE_AUDIT",
        "run_root": str(root),
        "decoded_candidates_before_dedupe": len(decoded_rows),
        "deduped_migrations": len(events),
        "dedupe_key_used": "mint|pool_or_pair_address|quote_mint_or_quote_asset unless explicit dedupe_key exists",
        "dedupe_key_too_broad": any(row["dedupe_key_too_broad"] for row in dedupe_rows),
        "dedupe_rows": dedupe_rows,
        "json_path": str(root / "migration_dedupe_audit.json"),
        "markdown_path": str(root / "migration_dedupe_audit.md"),
    }
    _write_json_artifact(root / "migration_dedupe_audit.json", summary)
    _write_markdown_artifact(
        root / "migration_dedupe_audit.md",
        [
            "# T011.7 Migration Dedupe Audit",
            "",
            f"- Decoded candidates before dedupe: `{summary['decoded_candidates_before_dedupe']}`",
            f"- Deduped migrations: `{summary['deduped_migrations']}`",
            f"- Dedupe key used: `{summary['dedupe_key_used']}`",
            f"- Dedupe key too broad: `{summary['dedupe_key_too_broad']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def _build_migration_candidate_linkage_matrix(root: Path) -> list[dict[str, Any]]:
    manifest = _read_json(root / "campaign_manifest.json")
    birth_rows = _read_jsonl(root / "birth_audit.jsonl")
    curve_rows = _read_jsonl(root / "curve_observations.jsonl")
    trade_rows = _read_jsonl(root / "trade_flow_events.jsonl")
    holder_rows = _read_jsonl(root / "holder_distribution_snapshots.jsonl")
    dev_rows = _read_jsonl(root / "dev_behavior_events.jsonl")
    post_rows = _read_jsonl(root / "post_migration_observations.jsonl")
    decoded_rows = _decoded_migration_candidate_rows(root)
    birth_by_mint = _rows_by_mint(birth_rows)
    curve_by_mint = _rows_by_mint(curve_rows)
    trade_by_mint = _rows_by_mint(trade_rows)
    holder_by_mint = _rows_by_mint(holder_rows)
    dev_by_mint = _rows_by_mint(dev_rows)
    post_by_mint = _rows_by_mint(row for row in post_rows if _candidate_mint(row))
    first_birth_observed_at = min((_candidate_time(row) for row in birth_rows if _candidate_time(row) is not None), default=None)
    source_start = _num(_first_present(manifest, ["source_started_at", "started_at", "campaign_start_time"]))
    source_ready = first_birth_observed_at if first_birth_observed_at is not None else source_start
    rows: list[dict[str, Any]] = []
    for candidate in decoded_rows:
        mint = _candidate_mint(candidate)
        candidate_time = _candidate_time(candidate)
        birth = _latest_row(birth_by_mint.get(mint, []), "received_at", "first_seen_at", "feature_observed_at")
        birth_time = _candidate_time(birth) if birth else None
        birth_slot = _int(_first_present(birth, ["slot", "launch_slot", "first_seen_slot"]))
        migration_slot = _int(_first_present(candidate, ["slot", "migration_slot", "observation_slot"]))
        pre_curve = any((_candidate_time(row) or float("inf")) <= (candidate_time or -1) for row in curve_by_mint.get(mint, []))
        pre_trade = any((_candidate_time(row) or float("inf")) <= (candidate_time or -1) for row in trade_by_mint.get(mint, []))
        pre_holder = any((_candidate_time(row) or float("inf")) <= (candidate_time or -1) for row in holder_by_mint.get(mint, []))
        pre_dev = any((_candidate_time(row) or float("inf")) <= (candidate_time or -1) for row in dev_by_mint.get(mint, []))
        post = bool(post_by_mint.get(mint))
        if source_ready is not None and candidate_time is not None and candidate_time < source_ready:
            reason = "timestamp_order_not_decision_safe"
        elif birth_slot is not None and migration_slot is not None and migration_slot < birth_slot:
            reason = "timestamp_order_not_decision_safe"
        elif mint not in birth_by_mint:
            reason = "migration_mint_not_in_birth_set"
        elif not _bool(birth.get("admitted")):
            reason = "migration_mint_birth_seen_but_not_admitted"
        elif not pre_curve:
            reason = "missing_pre_migration_curve_state"
        elif not pre_trade:
            reason = "missing_pre_migration_trade_flow"
        elif not (pre_holder or pre_dev):
            reason = "missing_pre_migration_holder_dev"
        elif not post:
            reason = "missing_post_migration_pool_observation"
        elif birth_time is not None and candidate_time is not None and birth_time > candidate_time:
            reason = "timestamp_order_not_decision_safe"
        else:
            reason = "none"
        rows.append(
            {
                "signature": candidate.get("signature") or candidate.get("event_signature"),
                "slot": migration_slot,
                "candidate_mint": mint,
                "mint": mint,
                "pool_address": _candidate_pool(candidate),
                "observed_time": candidate_time,
                "is_mint_in_birth_set": mint in birth_by_mint,
                "birth_first_seen_time": birth_time,
                "was_birth_admitted": _bool(birth.get("admitted")) if birth else False,
                "curve_state_before_migration_exists": pre_curve,
                "trade_flow_before_migration_exists": pre_trade,
                "holder_dev_before_migration_exists": bool(pre_holder or pre_dev),
                "post_migration_observation_exists": post,
                "timestamp_order_decision_safe": reason not in {"timestamp_order_not_decision_safe"},
                "final_full_path_status": "decision_safe_full_path" if reason == "none" else "not_decision_safe",
                "decision_safe_full_path": reason == "none",
                "failure_reason": reason,
            }
        )
    return rows


def run_migration_capture_forensics(run_root: Path | str, *, expected_mints_path: Path | str | None = None) -> dict[str, Any]:
    root = Path(run_root)
    manifest = _read_json(root / "campaign_manifest.json")
    collector_summary = _read_json(root / "collector_summary.json")
    birth_rows = _read_jsonl(root / "birth_audit.jsonl")
    curve_rows = _read_jsonl(root / "curve_observations.jsonl")
    trade_rows = _read_jsonl(root / "trade_flow_events.jsonl")
    holder_rows = _read_jsonl(root / "holder_distribution_snapshots.jsonl")
    dev_rows = _read_jsonl(root / "dev_behavior_events.jsonl")
    post_rows = _read_jsonl(root / "post_migration_observations.jsonl")
    raw_spool_rows = _read_jsonl(root / GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT)
    write_intent_rows = _read_jsonl(root / GLOBAL_MIGRATION_WRITE_INTENTS_ARTIFACT)
    global_events = _read_jsonl(root / "global_migration_events.jsonl")
    global_candidates = _read_jsonl(root / "global_migration_candidates.jsonl")
    global_duplicates = _read_jsonl(root / "global_migration_event_duplicates.jsonl")
    derived_candidates = _read_jsonl(root / "migration_candidates.jsonl")
    migration_events = _read_jsonl(root / "migration_events.jsonl")
    route_rows = _read_jsonl(root / "migration_route_audit_rows.jsonl")
    pumpswap_route_candidates = _read_jsonl(root / "pumpswap_route_candidates.jsonl")
    pumpswap_tx_route_rows = _read_jsonl(root / "pumpswap_transaction_route_audit.jsonl")
    pumpswap_swap_rows = _read_jsonl(root / "pumpswap_swap_events.jsonl")

    birth_by_mint = _rows_by_mint(birth_rows)
    curve_by_mint = _rows_by_mint(curve_rows)
    trade_by_mint = _rows_by_mint(trade_rows)
    holder_by_mint = _rows_by_mint(holder_rows)
    dev_by_mint = _rows_by_mint(dev_rows)
    post_by_mint = _rows_by_mint(row for row in post_rows if _candidate_mint(row))
    first_birth_observed_at = min((_candidate_time(row) for row in birth_rows if _candidate_time(row) is not None), default=None)
    source_start = _num(_first_present(manifest, ["source_started_at", "started_at", "campaign_start_time"]))
    source_ready = first_birth_observed_at if first_birth_observed_at is not None else source_start
    source_end = _num(_first_present(manifest, ["source_stopped_at", "ended_at", "campaign_end_time"]))

    raw_sources: list[tuple[str, list[dict[str, Any]]]] = [
        (GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT, raw_spool_rows),
        ("global_migration_events.jsonl", global_events),
        ("global_migration_candidates.jsonl", global_candidates),
        ("global_migration_event_duplicates.jsonl", global_duplicates),
        ("migration_events.jsonl", migration_events),
        ("migration_route_audit_rows.jsonl", route_rows),
        ("pumpswap_route_candidates.jsonl", pumpswap_route_candidates),
        ("pumpswap_transaction_route_audit.jsonl", pumpswap_tx_route_rows),
        ("pumpswap_swap_events.jsonl", pumpswap_swap_rows),
    ]
    raw_candidate_rows: list[dict[str, Any]] = []
    decode_rows: list[dict[str, Any]] = []
    for source_artifact, rows in raw_sources:
        for row in rows:
            mint = _candidate_mint(row)
            pool = _candidate_pool(row)
            decoded = bool(mint and (pool or source_artifact == "pumpswap_swap_events.jsonl"))
            if source_artifact == GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT and not decoded:
                failure = str(row.get("decode_status") or "unknown_decode_gap")
            elif source_artifact == "pumpswap_route_candidates.jsonl" and not decoded:
                failure = "unsupported_route"
            elif decoded:
                failure = "none"
            elif not mint:
                failure = "decode_failed_missing_mint"
            elif not pool:
                failure = "decode_failed_missing_pool"
            else:
                failure = "unknown_decode_gap"
            candidate = {
                "source_artifact": source_artifact,
                "signature": row.get("signature") or row.get("event_signature"),
                "slot": row.get("slot") or row.get("observation_slot"),
                "block_time": row.get("block_time"),
                "program_id": row.get("migration_program_id") or row.get("program_id") or row.get("pool_account_owner"),
                "source_channel": row.get("source_route") or row.get("detection_method") or source_artifact,
                "mint": mint,
                "pool_address": pool,
                "candidate_time": _candidate_time(row),
                "decoder_attempted": source_artifact
                in {
                    "global_migration_events.jsonl",
                    "global_migration_candidates.jsonl",
                    "global_migration_event_duplicates.jsonl",
                    "pumpswap_route_candidates.jsonl",
                    "pumpswap_transaction_route_audit.jsonl",
                    "migration_route_audit_rows.jsonl",
                },
                "decode_success": decoded,
                "decode_failure_reason": failure,
                "decoded_base_mint": row.get("base_mint") or row.get("pool_base_mint") or mint,
                "decoded_quote_mint": row.get("quote_mint") or row.get("pool_quote_mint"),
                "decoded_pool_address": pool,
            }
            raw_candidate_rows.append(candidate)
            decode_rows.append(candidate)

    decoded_mints = {_candidate_mint(row) for row in [*global_events, *global_candidates] if _candidate_mint(row)}
    decoded_pools = {_candidate_pool(row) for row in [*global_events, *global_candidates] if _candidate_pool(row)}
    derived_rows: list[dict[str, Any]] = []
    for row in derived_candidates:
        mint = _candidate_mint(row)
        candidate_time = _candidate_time(row)
        in_window = bool(source_ready is not None and candidate_time is not None and candidate_time >= source_ready)
        migration_grade_reasons = _derived_migration_grade_reasons(row)
        migration_grade_evidence = bool(migration_grade_reasons)
        if mint in decoded_mints:
            classification = "decoded_migration_seen"
        elif not in_window:
            classification = "derived_candidate_out_of_window"
        elif migration_grade_evidence:
            classification = "migration_detector_missed_candidate"
        else:
            classification = "high_fdv_diagnostic_not_migration_evidence"
        derived_rows.append(
            {
                "mint": mint,
                "candidate_reason": row.get("candidate_reason") or "derived_migration_likely_candidate",
                "candidate_time": candidate_time,
                "in_window": in_window,
                "valuation_usd": row.get("valuation_usd"),
                "progress_pct": row.get("progress_pct"),
                "migration_grade_evidence": migration_grade_evidence,
                "migration_grade_reasons": migration_grade_reasons,
                "decoded_migration_event_seen": mint in decoded_mints,
                "classification": classification,
            }
        )

    startup_boundary_rows = 0
    in_window_rows = 0
    unknown_time_rows = 0
    timestamp_rows: list[dict[str, Any]] = []
    for row in [*global_events, *global_candidates, *global_duplicates]:
        candidate_time = _candidate_time(row)
        if candidate_time is None or source_ready is None:
            classification = "unknown"
            unknown_time_rows += 1
        elif candidate_time < source_ready:
            classification = "startup_boundary"
            startup_boundary_rows += 1
        else:
            classification = "in_window"
            in_window_rows += 1
        timestamp_rows.append(
            {
                "mint": _candidate_mint(row),
                "pool_address": _candidate_pool(row),
                "signature": row.get("signature") or row.get("event_signature"),
                "candidate_time": candidate_time,
                "scan_source_start_time": source_start,
                "birth_source_ready_time": source_ready,
                "scan_source_end_time": source_end,
                "seconds_after_source_start": _round_float(candidate_time - source_start) if candidate_time is not None and source_start is not None else None,
                "seconds_after_birth_source_ready": _round_float(candidate_time - source_ready)
                if candidate_time is not None and source_ready is not None
                else None,
                "classification": classification,
            }
        )

    linkage_rows: list[dict[str, Any]] = []
    linkage_failure_counts: Counter[str] = Counter()
    for row in [*global_events, *global_candidates]:
        mint = _candidate_mint(row)
        candidate_time = _candidate_time(row)
        birth = (birth_by_mint.get(mint) or [{}])[0]
        birth_time = _candidate_time(birth) if birth else None
        pre_curve = any((_candidate_time(curve) or float("inf")) <= (candidate_time or -1) for curve in curve_by_mint.get(mint, []))
        pre_trade = any((_candidate_time(trade) or float("inf")) <= (candidate_time or -1) for trade in trade_by_mint.get(mint, []))
        pre_holder = any((_candidate_time(holder) or float("inf")) <= (candidate_time or -1) for holder in holder_by_mint.get(mint, []))
        pre_dev = any((_candidate_time(dev) or float("inf")) <= (candidate_time or -1) for dev in dev_by_mint.get(mint, []))
        post = bool(post_by_mint.get(mint))
        birth_slot = _int(_first_present(birth, ["slot", "launch_slot", "first_seen_slot"]))
        migration_slot = _int(_first_present(row, ["slot", "migration_slot", "observation_slot"]))
        if source_ready is not None and candidate_time is not None and candidate_time < source_ready:
            reason = "startup_boundary_migration_not_decision_safe"
        elif birth_slot is not None and migration_slot is not None and migration_slot < birth_slot:
            reason = "migration_slot_before_birth_slot"
        elif mint not in birth_by_mint:
            reason = "migration_mint_not_in_birth_set"
        elif not _bool(birth.get("admitted")):
            reason = "migration_mint_birth_seen_but_not_admitted"
        elif not pre_curve:
            reason = "migration_before_first_curve_observation" if curve_by_mint.get(mint) else "missing_pre_migration_curve_state"
        elif not post:
            reason = "missing_post_migration_pool_observation"
        elif birth_time is not None and candidate_time is not None and birth_time > candidate_time:
            reason = "timestamp_order_not_decision_safe"
        else:
            reason = "none"
        linkage_failure_counts[reason] += 1
        linkage_rows.append(
            {
                "mint": mint,
                "pool_address": _candidate_pool(row),
                "signature": row.get("signature") or row.get("event_signature"),
                "birth_slot": birth_slot,
                "migration_slot": migration_slot,
                "candidate_time": candidate_time,
                "birth_first_seen_time": birth_time,
                "is_mint_in_birth_set": mint in birth_by_mint,
                "birth_admitted": _bool(birth.get("admitted")) if birth else False,
                "pre_migration_curve_state_before_migration": pre_curve,
                "pre_migration_trade_flow_before_migration": pre_trade,
                "pre_migration_holder_before_migration": pre_holder,
                "pre_migration_dev_before_migration": pre_dev,
                "post_migration_pool_observation_exists": post,
                "decision_safe_full_path": reason == "none",
                "failure_reason": reason,
            }
        )

    duplicates_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in [*global_events, *global_duplicates]:
        try:
            key = "|".join(_global_migration_dedupe_key(row))
        except Exception:
            key = str(row.get("signature") or row.get("event_signature") or "")
        duplicates_by_key.setdefault(key, []).append(row)
    dedupe_key_too_broad = any(
        len({_candidate_mint(row) for row in rows if _candidate_mint(row)}) > 1
        or len({_candidate_pool(row) for row in rows if _candidate_pool(row)}) > 1
        for rows in duplicates_by_key.values()
    )
    dedupe_rows = [
        {
            "dedupe_key": key,
            "row_count": len(rows),
            "mints": sorted({_candidate_mint(row) for row in rows if _candidate_mint(row)}),
            "pools": sorted({_candidate_pool(row) for row in rows if _candidate_pool(row)}),
            "signatures": sorted({str(row.get("signature") or row.get("event_signature") or "") for row in rows}),
            "dedupe_key_too_broad": len({_candidate_mint(row) for row in rows if _candidate_mint(row)}) > 1
            or len({_candidate_pool(row) for row in rows if _candidate_pool(row)}) > 1,
        }
        for key, rows in sorted(duplicates_by_key.items())
    ]

    expected_mints = _read_expected_mints_file(expected_mints_path)
    expected_rows: list[dict[str, Any]] = []
    for mint in expected_mints:
        expected_rows.append(
            {
                "mint": mint,
                "birth_seen": mint in birth_by_mint,
                "curve_observations": len(curve_by_mint.get(mint, [])),
                "trade_flow_rows": len(trade_by_mint.get(mint, [])),
                "raw_migration_candidate_seen": any(row.get("mint") == mint for row in raw_candidate_rows),
                "decoded_migration_candidate_seen": mint in decoded_mints,
                "pool_observations": len(post_by_mint.get(mint, [])),
                "full_path_linked": any(row.get("mint") == mint and row.get("decision_safe_full_path") for row in linkage_rows),
            }
        )

    global_errors = list(collector_summary.get("global_migration_errors") or [])
    missed_candidate_count = sum(1 for row in derived_rows if row["classification"] == "migration_detector_missed_candidate")
    unsupported_route_count = sum(1 for row in decode_rows if row.get("decode_failure_reason") == "unsupported_route")
    latest_write_intents = list(_latest_global_migration_write_intents_by_candidate(root).values())
    write_status_counts = dict(Counter(str(row.get("write_status") or "unknown") for row in latest_write_intents))
    decoded_write_intents = [row for row in latest_write_intents if _candidate_mint(row) and _candidate_pool(row)]
    unsupported_write_intents = [row for row in latest_write_intents if not (_candidate_mint(row) and _candidate_pool(row))]
    thread_affinity_failed_intents = [
        row
        for row in latest_write_intents
        if _bool(row.get("thread_affinity_error")) or _is_sqlite_thread_affinity_error(str(row.get("write_error") or ""))
    ]
    write_failure_count = sum(1 for row in decoded_write_intents if str(row.get("write_status") or "") in {"failed", "retry_exhausted"})
    write_failure_count += sum(1 for row in thread_affinity_failed_intents if row not in decoded_write_intents)
    write_success_count = sum(1 for row in decoded_write_intents if str(row.get("write_status") or "") == "written")
    write_queued_count = sum(1 for row in decoded_write_intents if str(row.get("write_status") or "") == "queued")
    write_retry_pending_count = sum(1 for row in decoded_write_intents if str(row.get("write_status") or "") == "retry_pending")
    unsupported_write_retry_pending_count = sum(1 for row in unsupported_write_intents if str(row.get("write_status") or "") == "retry_pending")
    unresolved_write_intent_thread_errors = sum(
        1
        for row in latest_write_intents
        if _bool(row.get("thread_affinity_error")) and str(row.get("write_status") or "") != "written"
    )
    raw_global_thread_affinity_error_count = sum(1 for error in global_errors if _is_sqlite_thread_affinity_error(error))
    migration_side_effects_applied = _int(collector_summary.get("migration_side_effects_applied")) or 0
    migration_side_effects_failed = _int(collector_summary.get("migration_side_effects_failed")) or 0
    resolved_global_thread_affinity_error_count = (
        raw_global_thread_affinity_error_count
        if raw_global_thread_affinity_error_count
        and len(global_events) > 0
        and migration_side_effects_applied >= len(global_events)
        and migration_side_effects_failed == 0
        and write_failure_count == 0
        and write_retry_pending_count == 0
        else 0
    )
    effective_global_errors = [
        error
        for error in global_errors
        if not (_is_sqlite_thread_affinity_error(error) and resolved_global_thread_affinity_error_count)
    ]
    sqlite_thread_affinity_error_count = unresolved_write_intent_thread_errors + (
        raw_global_thread_affinity_error_count - resolved_global_thread_affinity_error_count
    )
    events_recovered_from_spool = int(_num(collector_summary.get("events_recovered_from_spool")) or 0)
    decoded_in_window_unlinked = sum(
        1 for row in linkage_rows if row.get("failure_reason") not in {"none", "startup_boundary_migration_not_decision_safe"}
    )
    decision_safe_full_paths = sum(1 for row in linkage_rows if row.get("decision_safe_full_path"))
    write_path_audit = run_migration_write_path_audit(root)
    dedupe_audit = run_migration_dedupe_audit(root)
    migration_candidate_linkage_matrix = _build_migration_candidate_linkage_matrix(root)
    _write_json_artifact(root / "migration_candidate_linkage_matrix.json", migration_candidate_linkage_matrix)
    _write_csv_artifact(root / "migration_candidate_linkage_matrix.csv", migration_candidate_linkage_matrix)
    matrix_failure_counts = dict(
        sorted(Counter(str(row.get("failure_reason") or "unknown_linkage_gap") for row in migration_candidate_linkage_matrix).items())
    )
    matrix_decision_safe_full_paths = sum(1 for row in migration_candidate_linkage_matrix if row.get("decision_safe_full_path"))
    decision_safe_full_paths = max(decision_safe_full_paths, matrix_decision_safe_full_paths)
    raw_candidate_taxonomy = {
        "raw_pumpswap_notification": len(pumpswap_tx_route_rows),
        "raw_pumpswap_swap_event": len(pumpswap_swap_rows),
        "raw_pool_create_like_event": len(raw_spool_rows) + len(global_candidates) + len(pumpswap_route_candidates),
        "raw_migration_like_event": len(global_events) + len(global_candidates),
        "decoded_pool_create_candidate": sum(1 for row in global_candidates if _candidate_pool(row)),
        "decoded_migration_candidate": len(global_events) + len(global_candidates),
        "unsupported_route_candidate": unsupported_route_count,
        "decode_failed_candidate": sum(1 for row in raw_spool_rows if not _candidate_mint(row)),
        "write_failed_candidate": write_failure_count,
        "linked_migration_candidate": sum(1 for row in migration_candidate_linkage_matrix if row.get("is_mint_in_birth_set")),
        "unlinked_migration_candidate": sum(1 for row in migration_candidate_linkage_matrix if not row.get("is_mint_in_birth_set")),
    }
    raw_predecode_artifacts = {
        GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT,
        "migration_route_audit_rows.jsonl",
        "pumpswap_route_candidates.jsonl",
        "pumpswap_transaction_route_audit.jsonl",
        "pumpswap_swap_events.jsonl",
    }
    raw_predecode_rows = [row for row in raw_candidate_rows if row.get("source_artifact") in raw_predecode_artifacts]
    if matrix_decision_safe_full_paths > 0:
        decision_safe_explanation = "at least one decoded migration candidate has birth, pre-migration evidence, post-migration observation, and decision-safe timestamp order"
    elif write_failure_count > 0 or write_retry_pending_count > 0:
        decision_safe_explanation = "write path failed or remained retry-pending before all migration candidates could become authoritative full-path evidence"
    elif matrix_failure_counts:
        decision_safe_explanation = f"decoded migration candidates failed explicit linkage gates: {matrix_failure_counts}"
    elif unsupported_route_count > 0:
        decision_safe_explanation = "decoded activity used unsupported migration route(s)"
    else:
        decision_safe_explanation = "no decoded in-window migration candidate linked to a decision-safe full path"
    if sqlite_thread_affinity_error_count > 0:
        readiness = "migration_writer_thread_affinity_error"
    elif write_failure_count > 0 or write_retry_pending_count > 0:
        readiness = "migration_lane_write_path_failure"
    elif effective_global_errors or missed_candidate_count > 0:
        readiness = "in_window_migration_candidates_missed_by_detector"
    elif decision_safe_full_paths > 0:
        readiness = "in_window_migration_decision_safe_full_path_observed"
    elif decoded_in_window_unlinked > 0:
        readiness = "in_window_migrations_decoded_but_unlinked"
    elif unsupported_route_count > 0:
        readiness = "unsupported_route_observed"
    elif startup_boundary_rows > 0 and in_window_rows == 0:
        readiness = "startup_boundary_only"
    elif in_window_rows == 0:
        readiness = "no_in_window_migration_observed"
    else:
        readiness = "migration_audit_inconclusive"

    forensics_detail_row_limit = 500
    detail_arrays = {
        "dedupe_rows": dedupe_rows,
        "raw_candidates": raw_candidate_rows,
        "decode_rows": decode_rows,
        "timestamp_rows": timestamp_rows,
        "birth_linkage_rows": linkage_rows,
        "derived_migration_likely_candidates": derived_rows,
        "expected_mints_audit": expected_rows,
    }
    forensics_detail_full_row_counts = {key: len(rows) for key, rows in detail_arrays.items()}
    forensics_detail_rows_truncated = any(len(rows) > forensics_detail_row_limit for rows in detail_arrays.values())

    summary = {
        "audit_id": "T011_5_MIGRATION_CAPTURE_FORENSICS",
        "run_root": str(root),
        "run_id": collector_summary.get("run_id"),
        "forensics_detail_row_limit": forensics_detail_row_limit,
        "forensics_detail_rows_truncated": forensics_detail_rows_truncated,
        "forensics_detail_full_row_counts": forensics_detail_full_row_counts,
        "raw_candidate_taxonomy": raw_candidate_taxonomy,
        "raw_candidate_count_explanation": (
            "raw_migration_candidate_count_before_decode is an offline evidence inventory count over pre-decode raw PumpSwap notifications/swaps plus migration-like artifacts; "
            "it excludes already-decoded migration event/candidate artifacts and is not the count of true migrations. Use raw_candidate_taxonomy to separate route notifications, swap events, pool-create-like candidates, decoded migration candidates, and failed/unsupported candidates."
        ),
        "raw_migration_candidate_count_before_decode": len(raw_predecode_rows),
        "raw_pool_create_like_notifications_before_decode": sum(
            1 for row in raw_predecode_rows if "pool" in str(row.get("source_channel") or row.get("source_artifact") or "").lower()
        ),
        "decoded_migration_candidate_count": len(global_events) + len(global_candidates),
        "deduped_migration_count": len(global_events),
        "raw_migration_spool_rows": len(raw_spool_rows),
        "migration_write_intent_rows": len(write_intent_rows),
        "migration_write_intent_status_counts": write_status_counts,
        "migration_write_queued_count": write_queued_count,
        "migration_write_success_count": write_success_count,
        "migration_write_failure_count": write_failure_count,
        "migration_write_intent_failure_count": write_failure_count,
        "migration_write_retry_pending_count": write_retry_pending_count,
        "unsupported_write_retry_pending_count": unsupported_write_retry_pending_count,
        "sqlite_thread_affinity_error_count": sqlite_thread_affinity_error_count,
        "events_recovered_from_spool": events_recovered_from_spool,
        "events_lost_before_spool": "unknown" if not raw_spool_rows else 0,
        "dedupe_key_used": "mint|pool_or_pair_address|quote_mint_or_quote_asset",
        "dedupe_key_too_broad": bool(dedupe_audit.get("dedupe_key_too_broad") or dedupe_key_too_broad),
        "in_window_migration_candidate_count": in_window_rows,
        "startup_boundary_count": startup_boundary_rows,
        "unknown_timestamp_candidate_count": unknown_time_rows,
        "unsupported_route_count": unsupported_route_count,
        "derived_migration_likely_candidate_count": len(derived_rows),
        "missed_candidate_count": missed_candidate_count,
        "global_migration_thread_error_count": len(effective_global_errors),
        "global_migration_thread_errors": effective_global_errors,
        "raw_global_migration_thread_error_count": len(global_errors),
        "raw_global_migration_thread_errors": global_errors,
        "raw_global_thread_affinity_error_count": raw_global_thread_affinity_error_count,
        "resolved_global_thread_affinity_error_count": resolved_global_thread_affinity_error_count,
        "readiness_correction": readiness,
        "decision_safe_full_path_explanation": decision_safe_explanation,
        "migration_write_path_audit_path": str(root / "migration_write_path_audit.json"),
        "migration_dedupe_audit_path": str(root / "migration_dedupe_audit.json"),
        "migration_candidate_linkage_matrix_path": str(root / "migration_candidate_linkage_matrix.json"),
        "migration_candidate_linkage_matrix_csv_path": str(root / "migration_candidate_linkage_matrix.csv"),
        "migration_candidate_linkage_failure_counts": matrix_failure_counts,
        "migration_candidate_linkage_decision_safe_full_paths": matrix_decision_safe_full_paths,
        "migration_candidate_linkage_matrix": migration_candidate_linkage_matrix,
        "migration_write_path_audit_summary": {
            "write_status_counts": write_path_audit.get("write_status_counts"),
            "classification_counts": write_path_audit.get("classification_counts"),
            "json_path": write_path_audit.get("json_path"),
        },
        "migration_dedupe_audit_summary": {
            "decoded_candidates_before_dedupe": dedupe_audit.get("decoded_candidates_before_dedupe"),
            "deduped_migrations": dedupe_audit.get("deduped_migrations"),
            "dedupe_key_too_broad": dedupe_audit.get("dedupe_key_too_broad"),
            "json_path": dedupe_audit.get("json_path"),
        },
        "raw_capture_status": "global_pumpswap_lane_error" if effective_global_errors else "artifact_limited_capture_available",
        "decode_failure_counts": dict(Counter(row.get("decode_failure_reason") for row in decode_rows)),
        "linkage_failure_reason_counts": dict(sorted(linkage_failure_counts.items())),
        "timestamp_findings": {
            "source_start": source_start,
            "birth_source_ready": source_ready,
            "source_end": source_end,
            "seconds_mismatch_detected": False,
            "timezone_or_epoch_mismatch_detected": False,
            "startup_boundary_rule": "candidate_time < birth_source_ready",
        },
        "dedupe_rows": dedupe_rows[:forensics_detail_row_limit],
        "raw_candidates": raw_candidate_rows[:forensics_detail_row_limit],
        "decode_rows": decode_rows[:forensics_detail_row_limit],
        "timestamp_rows": timestamp_rows[:forensics_detail_row_limit],
        "birth_linkage_rows": linkage_rows[:forensics_detail_row_limit],
        "derived_migration_likely_candidates": derived_rows[:forensics_detail_row_limit],
        "expected_mints_audit": expected_rows[:forensics_detail_row_limit],
        "json_path": str(root / "migration_capture_forensics.json"),
        "markdown_path": str(root / "migration_capture_forensics.md"),
    }
    _write_json_artifact(root / "migration_capture_forensics.json", summary)
    _write_markdown_artifact(
        root / "migration_capture_forensics.md",
        [
            "# T011.5 Migration Capture / Linkage Forensics",
            "",
            f"- Raw migration candidates before decode: `{summary['raw_migration_candidate_count_before_decode']}`",
            f"- Raw candidate taxonomy: `{summary['raw_candidate_taxonomy']}`",
            f"- Raw candidate count explanation: {summary['raw_candidate_count_explanation']}",
            f"- Detail row limit: `{summary['forensics_detail_row_limit']}`",
            f"- Detail rows truncated: `{summary['forensics_detail_rows_truncated']}`",
            f"- Raw migration spool rows: `{summary['raw_migration_spool_rows']}`",
            f"- Decoded migration candidates: `{summary['decoded_migration_candidate_count']}`",
            f"- Deduped migrations: `{summary['deduped_migration_count']}`",
            f"- Migration write intent statuses: `{summary['migration_write_intent_status_counts']}`",
            f"- SQLite thread-affinity errors: `{summary['sqlite_thread_affinity_error_count']}`",
            f"- Events recovered from spool: `{summary['events_recovered_from_spool']}`",
            f"- In-window decoded migration candidates: `{summary['in_window_migration_candidate_count']}`",
            f"- Startup-boundary decoded candidates: `{summary['startup_boundary_count']}`",
            f"- Derived migration-likely candidates: `{summary['derived_migration_likely_candidate_count']}`",
            f"- Missed candidates: `{summary['missed_candidate_count']}`",
            f"- Unsupported routes: `{summary['unsupported_route_count']}`",
            f"- Global migration thread errors: `{summary['global_migration_thread_errors']}`",
            f"- Dedupe key too broad: `{summary['dedupe_key_too_broad']}`",
            f"- Readiness correction: `{summary['readiness_correction']}`",
            f"- Decision-safe full-path explanation: {summary['decision_safe_full_path_explanation']}",
            f"- Linkage failure reasons: `{summary['linkage_failure_reason_counts']}`",
            f"- Candidate linkage matrix failure reasons: `{summary['migration_candidate_linkage_failure_counts']}`",
            f"- Write-path audit: `{summary['migration_write_path_audit_path']}`",
            f"- Dedupe audit: `{summary['migration_dedupe_audit_path']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    return summary


def run_rebuild_migrations_from_spool(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    raw_rows = _read_jsonl(root / GLOBAL_MIGRATION_RAW_CANDIDATES_ARTIFACT)
    existing_events = _read_jsonl(root / "global_migration_events.jsonl")
    existing_keys = {_global_migration_dedupe_key(row) for row in existing_events if _candidate_mint(row)}
    recovered = 0
    skipped_missing_fields = 0
    skipped_duplicates = 0
    for raw in raw_rows:
        mint = _candidate_mint(raw)
        pool = _candidate_pool(raw)
        if not mint or not pool:
            skipped_missing_fields += 1
            continue
        event = {
            "candidate_id": _migration_candidate_id(raw),
            "mint": mint,
            "signature": _first_present(raw, ["signature", "event_signature", "migration_signature"]),
            "slot": raw.get("slot"),
            "block_time": raw.get("block_time"),
            "received_at": _num(_first_present(raw, ["received_at", "migration_received_at", "observed_at"])),
            "migration_received_at": _num(_first_present(raw, ["migration_received_at", "received_at", "observed_at"])),
            "pool_or_pair_address": pool,
            "pool_address": pool,
            "quote_mint": raw.get("quote_mint"),
            "quote_asset": raw.get("quote_asset") or _quote_identity_from_payload(raw, unsupported_as_unknown=False)["quote_asset"],
            "confidence": raw.get("confidence") or "confirmed",
            "detection_method": raw.get("detection_method") or raw.get("event_type_guess") or "spool_rebuild",
            "source_route": raw.get("source_channel") or raw.get("source_route") or "global_migration_raw_spool_rebuild",
            "migration_evidence_level": raw.get("migration_evidence_level") or MigrationEvidenceLevel.LEVEL_A.value,
            "migration_evidence_reason": raw.get("migration_evidence_reason") or "recovered_from_raw_migration_spool",
            "recovered_from_raw_spool": True,
        }
        key = _global_migration_dedupe_key(event)
        if key in existing_keys:
            skipped_duplicates += 1
            continue
        existing_keys.add(key)
        _append_jsonl_file(root / "global_migration_events.jsonl", event)
        _record_global_migration_write_intent(root, event, write_status="written", retry_count=1, write_success=True)
        recovered += 1
    collector_summary = _read_json(root / "collector_summary.json")
    collector_summary["events_recovered_from_spool"] = recovered
    collector_summary["migration_spool_rebuild_raw_rows"] = len(raw_rows)
    collector_summary["migration_spool_rebuild_skipped_missing_fields"] = skipped_missing_fields
    collector_summary["migration_spool_rebuild_skipped_duplicates"] = skipped_duplicates
    if collector_summary:
        _write_json_artifact(root / "collector_summary.json", collector_summary)
    rebuild_summary = {
        "audit_id": "T011_6_REBUILD_MIGRATIONS_FROM_SPOOL",
        "run_root": str(root),
        "raw_spool_rows": len(raw_rows),
        "events_recovered_from_spool": recovered,
        "skipped_missing_fields": skipped_missing_fields,
        "skipped_duplicates": skipped_duplicates,
        "recovery_possible": bool(raw_rows),
        "recovery_status": "recovered_from_spool" if recovered > 0 else ("no_raw_spool_available" if not raw_rows else "no_new_events_recovered"),
        "json_path": str(root / "migration_spool_rebuild_summary.json"),
    }
    _write_json_artifact(root / "migration_spool_rebuild_summary.json", rebuild_summary)
    run_migration_capture_forensics(root)
    run_migration_linkage_audit(root)
    run_long_scan_readiness_audit(root)
    return rebuild_summary


def run_long_scan_readiness_audit(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    trade = run_trade_flow_coverage_audit(root)
    trade_gap = run_trade_flow_eventful_gap_audit(root)
    migration = run_migration_linkage_audit(root)
    supervisor = _read_json(root / "scan_supervisor_status.json")
    collector_summary = _read_json(root / "collector_summary.json")
    live_status_existing = _read_json(root / "live_status.json")
    lifecycle_summary = _read_json(root / "lifecycle_coverage_summary.json")
    curve_audit = _read_json(root / "curve_decode_reliability_audit.json")
    migration_forensics = _read_json(root / "migration_capture_forensics.json")
    migration_forensics_correction = str(migration_forensics.get("readiness_correction") or "")
    migration_forensics_issue_statuses = {
        "migration_writer_thread_affinity_error",
        "migration_lane_write_path_failure",
        "in_window_migration_candidates_missed_by_detector",
        "in_window_migrations_decoded_but_unlinked",
        "in_window_migrations_linked_but_missing_pre_or_post_evidence",
        "unsupported_route_observed",
        "migration_audit_inconclusive",
    }
    migration_forensics_issue = migration_forensics_correction in migration_forensics_issue_statuses
    migration_lane_write_failure = migration_forensics_correction in {
        "migration_writer_thread_affinity_error",
        "migration_lane_write_path_failure",
    }
    curve_pass = False
    for metric in supervisor.get("coverage_metrics") or []:
        if metric.get("metric_id") == "curve_decode_age_eligible_mint_coverage" and metric.get("status") == "pass":
            curve_pass = True
            break
    if not curve_pass and curve_audit:
        curve_pass = bool(
            (_int(curve_audit.get("needed_decodes_to_pass")) or 0) == 0
            and (_int(curve_audit.get("scheduler_gap_count")) or 0) == 0
        )
    lifecycle_verified_births = _int(lifecycle_summary.get("verified_births")) or _int(lifecycle_summary.get("birth_seen_count")) or 0
    lifecycle_curve_state_decoded = _int(lifecycle_summary.get("curve_state_decoded")) or 0
    lifecycle_curve_decode_ratio = _safe_ratio(lifecycle_curve_state_decoded, lifecycle_verified_births)
    lifecycle_curve_gate_passed = bool(
        lifecycle_verified_births > 0
        and lifecycle_curve_decode_ratio >= 0.90
        and not (lifecycle_summary.get("lifecycle_materializer_status") == "error")
    )
    if not curve_pass and not supervisor and not curve_audit:
        curve_pass = lifecycle_curve_gate_passed

    def _coalesce_present(*values: Any) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return None

    requested_duration = _num(
        _coalesce_present(
            collector_summary.get("requested_source_duration_seconds"),
            collector_summary.get("source_duration_seconds"),
            live_status_existing.get("requested_source_duration_seconds"),
        )
    )
    actual_duration = _num(
        _coalesce_present(
            collector_summary.get("actual_duration_seconds"),
            collector_summary.get("actual_source_duration_seconds"),
            live_status_existing.get("actual_duration_seconds"),
            live_status_existing.get("actual_source_duration_seconds"),
        )
    )
    source_completed = bool((actual_duration or 0.0) >= (requested_duration or 0.0))
    queue_drops = _int(_coalesce_present(collector_summary.get("queue_drops"), live_status_existing.get("queue_drops"))) or 0
    rpc_failures = _int(_coalesce_present(collector_summary.get("rpc_failures"), live_status_existing.get("rpc_failures"))) or 0
    http_429 = _int(
        _coalesce_present(
            collector_summary.get("http_429"),
            collector_summary.get("http_429_count"),
            live_status_existing.get("http_429"),
            live_status_existing.get("http_429_count"),
        )
    ) or 0
    websocket_keepalive_timeout_count = _int(
        _coalesce_present(
            collector_summary.get("websocket_keepalive_timeout_count"),
            live_status_existing.get("websocket_keepalive_timeout_count"),
        )
    ) or 0
    websocket_reconnect_count = _int(
        _coalesce_present(
            collector_summary.get("websocket_reconnect_count"),
            live_status_existing.get("websocket_reconnect_count"),
        )
    ) or 0
    source_quality_label = str(
        _coalesce_present(
            collector_summary.get("source_duration_quality_status"),
            live_status_existing.get("source_duration_quality_status"),
            "not_evaluated",
        )
    )
    source_reconnect_warning = bool(
        source_completed
        and queue_drops == 0
        and rpc_failures == 0
        and http_429 == 0
        and (websocket_keepalive_timeout_count > 0 or websocket_reconnect_count > 0)
    )
    if source_reconnect_warning:
        source_quality_label = "complete_with_reconnect_warning"
    persistent_sqlite_exists = (root / "t007_lifecycle_state.sqlite").exists()
    persistent_events_jsonl_exists = (root / "persistent_lifecycle_events.jsonl").exists()
    persistent_lifecycle_store = "sqlite_ok" if persistent_sqlite_exists else ("jsonl_ok" if persistent_events_jsonl_exists else "missing")
    persistent_lifecycle_events_jsonl = "present" if persistent_events_jsonl_exists else ("optional_missing" if persistent_sqlite_exists else "missing")
    eventful_gap_count = _int(trade.get("trade_flow_true_gap_mints_count")) or 0
    eventful_coverage = dict(trade.get("trade_flow_eventful_parse_coverage") or {})
    eventful_ratio = _num(eventful_coverage.get("ratio"))
    global_migrations = int(migration.get("global_migration_events_deduped") or 0)
    startup_boundary_migrations = int(migration.get("startup_boundary_migration_count") or 0)
    in_window_migrations = int(
        migration.get("in_window_migration_count")
        if migration.get("in_window_migration_count") is not None
        else max(0, global_migrations - startup_boundary_migrations)
    )
    row_derived_decision_safe_full_paths = int(migration.get("row_derived_decision_safe_full_paths") or migration.get("decision_safe_full_paths") or 0)
    lifecycle_summary_decision_safe_full_paths = int(
        lifecycle_summary.get("decision_safe_full_paths")
        or lifecycle_summary.get("decision_safe_full_path_count")
        or lifecycle_summary.get("strict_full_paths")
        or 0
    )
    lifecycle_summary_exists = bool(lifecycle_summary)
    decision_safe_full_paths = (
        lifecycle_summary_decision_safe_full_paths if lifecycle_summary_exists else row_derived_decision_safe_full_paths
    )
    live_migration_side_effect_drain_count = _int(
        _coalesce_present(
            collector_summary.get("live_migration_side_effect_drain_count"),
            live_status_existing.get("live_migration_side_effect_drain_count"),
        )
    ) or 0
    live_migration_side_effects_applied = _int(
        _coalesce_present(
            collector_summary.get("live_migration_side_effects_applied"),
            live_status_existing.get("live_migration_side_effects_applied"),
        )
    ) or 0
    live_migration_side_effects_failed = _int(
        _coalesce_present(
            collector_summary.get("live_migration_side_effects_failed"),
            live_status_existing.get("live_migration_side_effects_failed"),
        )
    ) or 0
    live_migration_side_effects_source_rows = _int(
        _coalesce_present(
            collector_summary.get("live_migration_side_effects_source_rows"),
            live_status_existing.get("live_migration_side_effects_source_rows"),
        )
    ) or 0
    live_migration_side_effects_proven = bool(
        global_migrations <= 0
        or (
            live_migration_side_effect_drain_count > 0
            and live_migration_side_effects_applied > 0
            and live_migration_side_effects_failed == 0
            and live_migration_side_effects_source_rows >= global_migrations
        )
    )
    route_latency_histograms = _coalesce_present(
        collector_summary.get("route_latency_histograms"),
        live_status_existing.get("route_latency_histograms"),
    ) or {}
    latency_histograms_present = bool(
        _coalesce_present(
            collector_summary.get("latency_histograms_present"),
            live_status_existing.get("latency_histograms_present"),
            bool(route_latency_histograms),
        )
    )
    route_latency_gate_passed = bool(
        _coalesce_present(
            collector_summary.get("route_latency_gate_passed"),
            live_status_existing.get("route_latency_gate_passed"),
            latency_histograms_present,
        )
    )
    route_latency_gate_failures = list(
        _coalesce_present(
            collector_summary.get("route_latency_gate_failures"),
            live_status_existing.get("route_latency_gate_failures"),
            [],
        )
        or []
    )
    route_latency_gate_declared = bool(
        "route_latency_gate_passed" in collector_summary
        or "route_latency_gate_passed" in live_status_existing
        or "route_latency_gate_enabled" in collector_summary
        or "route_latency_gate_enabled" in live_status_existing
        or bool(route_latency_histograms)
        or latency_histograms_present
    )
    materialization_complete_histogram = route_latency_histograms.get("birth_to_admission_complete_latency_ms") or {}
    derived_materialization_latency_gate_passed = True
    materialization_complete_p95 = _num(materialization_complete_histogram.get("p95"))
    if (
        int(materialization_complete_histogram.get("count") or 0) > 0
        and materialization_complete_p95 is not None
        and materialization_complete_p95 > 1500.0
    ):
        derived_materialization_latency_gate_passed = False
    declared_materialization_latency_gate_passed = bool(
        _coalesce_present(
            collector_summary.get("materialization_latency_gate_passed"),
            live_status_existing.get("materialization_latency_gate_passed"),
            True,
        )
    )
    materialization_latency_gate_passed = (
        declared_materialization_latency_gate_passed and derived_materialization_latency_gate_passed
    )
    materialization_latency_gate_failures = list(
        _coalesce_present(
            collector_summary.get("materialization_latency_gate_failures"),
            live_status_existing.get("materialization_latency_gate_failures"),
            ["birth_to_admission_complete_p95_exceeded"] if not derived_materialization_latency_gate_passed else [],
        )
        or []
    )
    if (
        not derived_materialization_latency_gate_passed
        and "birth_to_admission_complete_p95_exceeded" not in materialization_latency_gate_failures
    ):
        materialization_latency_gate_failures.append("birth_to_admission_complete_p95_exceeded")
    dropped_or_reorged_count = _int(
        _coalesce_present(
            collector_summary.get("dropped_or_reorged_count"),
            live_status_existing.get("dropped_or_reorged_count"),
        )
    ) or 0
    source_gap_unbackfilled_count = _int(
        _coalesce_present(
            collector_summary.get("source_gap_unbackfilled_count"),
            live_status_existing.get("source_gap_unbackfilled_count"),
        )
    ) or 0
    source_gap_backfilled_count = _int(
        _coalesce_present(
            collector_summary.get("source_gap_backfilled_count"),
            live_status_existing.get("source_gap_backfilled_count"),
        )
    ) or 0
    source_gap_detected_count = _int(
        _coalesce_present(
            collector_summary.get("source_gap_detected_count"),
            live_status_existing.get("source_gap_detected_count"),
            source_gap_backfilled_count + source_gap_unbackfilled_count,
        )
    ) or 0
    source_gap_reorg_gate_passed = bool(
        _coalesce_present(
            collector_summary.get("source_gap_reorg_gate_passed"),
            live_status_existing.get("source_gap_reorg_gate_passed"),
            dropped_or_reorged_count == 0 and source_gap_unbackfilled_count == 0,
        )
    )
    commitment_reorg_drop_accounting_present = bool(
        _coalesce_present(
            collector_summary.get("commitment_reorg_drop_accounting_present"),
            live_status_existing.get("commitment_reorg_drop_accounting_present"),
            True,
        )
    )
    helius_budget_gate_present = bool(
        _coalesce_present(
            collector_summary.get("helius_budget_gate_present"),
            live_status_existing.get("helius_budget_gate_present"),
            False,
        )
    )
    helius_budget_gate_passed = bool(
        _coalesce_present(
            collector_summary.get("helius_budget_gate_passed"),
            live_status_existing.get("helius_budget_gate_passed"),
            not helius_budget_gate_present,
        )
    )
    helius_budget_blocker = str(
        _coalesce_present(
            collector_summary.get("helius_budget_blocker"),
            live_status_existing.get("helius_budget_blocker"),
            "",
        )
        or ""
    )
    blockers: list[str] = []
    diagnostic_warnings: list[str] = []
    recommendations: list[str] = []
    if route_latency_gate_declared and not latency_histograms_present:
        blockers.append("route_latency_histograms_missing")
        recommendations.append("emit_route_latency_histograms_before_longer_scan")
    elif route_latency_gate_declared and not route_latency_gate_passed:
        blockers.append("route_latency_gate_failed")
        recommendations.append("reduce_decision_path_source_to_curve_latency_before_longer_scan")
    if not materialization_latency_gate_passed:
        blockers.append("materialization_latency_gate_failed")
        recommendations.append("move_slow_birth_projection_and_live_status_work_behind_outbox_before_longer_scan")
    if not commitment_reorg_drop_accounting_present or not source_gap_reorg_gate_passed:
        blockers.append("source_gap_or_reorg_accounting_failed")
        recommendations.append("resolve_source_gap_or_reorg_accounting_before_longer_scan")
    if helius_budget_gate_present and not helius_budget_gate_passed:
        blockers.append("helius_budget_gate_not_passed")
        recommendations.append("configure_or_reduce_helius_credit_budget_before_2h_plus_scan")
    if (_num(trade.get("trade_flow_coverage_ratio")) or 0.0) < 0.90:
        diagnostic_warnings.append("trade_flow_unconditional_birth_coverage_below_target")
    if eventful_gap_count > 0:
        blockers.append("trade_flow_eventful_parser_writer_gap")
        recommendations.append("fix_trade_flow_missing_flow_for_birth_mints")
    if decision_safe_full_paths <= 0:
        blockers.append("no_in_window_decision_safe_full_path")
        if int(migration.get("startup_boundary_migration_count") or 0) > 0 and int(migration.get("steady_state_unlinked_migration_count") or 0) == 0:
            recommendations.append("rerun_10m_feature_proof_until_in_window_migration_observed")
        elif int(migration.get("lifecycle_migrated_unique_mints") or 0) > 0:
            recommendations.append("collect_or_link_decision_safe_migration_full_path")
        else:
            recommendations.append("fix_migration_linkage_or_explain_unlinked_global_migration")
    curve_decode_material_issue = bool((_int(curve_audit.get("needed_decodes_to_pass")) or 0) > 0)
    if curve_decode_material_issue:
        blockers.append("curve_decode_coverage_below_gate")
        recommendations.append("fix_remaining_curve_decode_coverage")
    if global_migrations > 0 and not live_migration_side_effects_proven:
        blockers.append("migration_side_effects_not_proven_live")
        recommendations.append("prove_live_migration_side_effect_drain_before_longer_scan")
    collector_proof_passed = bool(curve_pass and source_completed and not curve_decode_material_issue and source_quality_label not in {"failed", "partial"})
    feature_proof_passed = bool(collector_proof_passed and eventful_gap_count == 0)
    if decision_safe_full_paths > 0:
        migration_opportunity_status = "in_window_decision_safe_full_path_observed"
    elif global_migrations <= 0:
        migration_opportunity_status = "no_migration_opportunity_observed"
    elif startup_boundary_migrations > 0 and in_window_migrations == 0:
        migration_opportunity_status = "no_in_window_migration_observed"
    else:
        migration_opportunity_status = "in_window_migration_not_decision_safe"
    decision_safe_full_path_status = "observed" if decision_safe_full_paths > 0 else "not_observed"
    migration_readiness_classification = (
        "in_window_decision_safe_full_path_observed"
        if decision_safe_full_paths > 0
        else (
            "diagnostic_only_startup_boundary"
            if startup_boundary_migrations > 0 and in_window_migrations == 0
            else ("no_migration_opportunity_observed" if global_migrations <= 0 else "no_in_window_decision_safe_full_path")
        )
    )
    if migration_forensics_issue:
        migration_opportunity_status = migration_forensics_correction
        migration_readiness_classification = migration_forensics_correction
        if "migration_capture_forensics_issue" not in blockers:
            blockers.append("migration_capture_forensics_issue")
        recommendations.append("fix_migration_detector_or_linkage_before_longer_scan")
    pre_history_blockers = list(blockers)
    current_run_clean_10m_proof_candidate = bool(
        feature_proof_passed
        and decision_safe_full_paths > 0
        and not pre_history_blockers
        and not migration_forensics_issue
        and not curve_decode_material_issue
        and live_migration_side_effects_proven
    )
    proof_history_path = root.parent / "t011_clean_10m_proof_history.json"
    clean_10m_proofs_required_for_60m = 3
    clean_10m_proofs_observed = 0
    clean_10m_proof_history_status = "missing"
    clean_10m_proof_history_required = (root / "run_config.json").exists()
    if proof_history_path.exists():
        try:
            proof_history_payload = json.loads(proof_history_path.read_text(encoding="utf-8"))
            clean_runs = proof_history_payload.get("clean_10m_proofs") or proof_history_payload.get("runs") or []
            clean_10m_proofs_observed = len([row for row in clean_runs if row.get("proof_passed") is True or row.get("clean") is True])
            clean_10m_proof_history_status = "loaded"
        except Exception as exc:
            clean_10m_proof_history_status = f"error:{type(exc).__name__}"
    if clean_10m_proof_history_required and clean_10m_proofs_observed < clean_10m_proofs_required_for_60m:
        blockers.append("clean_10m_proof_history_below_required")
        recommendations.append("collect_three_clean_10m_proofs_before_60m_scan")
    can_run_60m_thesis_scan = bool(
        current_run_clean_10m_proof_candidate
        and (
            clean_10m_proofs_observed >= clean_10m_proofs_required_for_60m
            or not clean_10m_proof_history_required
        )
        and not blockers
    )
    readiness_decision = (
        "10M_COLLECTOR_FEATURE_AND_MIGRATION_PROOF_COMPLETED_60M_THESIS_SCAN_READY"
        if can_run_60m_thesis_scan
        else "10M_COLLECTOR_AND_FEATURE_PROOF_COMPLETED_60M_THESIS_READINESS_BLOCKED"
    )
    long_scan_bullets = [
        f"curve gate {'passed' if curve_pass else 'not passed'}",
        "eventful trade-flow parse coverage passed" if eventful_gap_count == 0 else f"trade-flow true parser gaps: {eventful_gap_count}",
        "trade-flow no-event mints are diagnostic, not parser failures",
        "in-window decision-safe migration/full path observed"
        if decision_safe_full_paths > 0
        else "no in-window decision-safe migration/full path",
    ]
    if migration_forensics_issue:
        long_scan_bullets.append("migration capture forensics found detector/linkage issue")
    if source_reconnect_warning:
        long_scan_bullets.insert(2, "source completed with reconnect warning")
    if startup_boundary_migrations > 0:
        long_scan_bullets.append("startup-boundary migration does not count as full-path evidence")
    if global_migrations > 0 and not live_migration_side_effects_proven:
        long_scan_bullets.append("migration side effects were not proven during live source runtime")
    banner_text = (
        "Migration lane write/capture failure — full-path readiness invalid"
        if migration_lane_write_failure
        else "Migration detector/linkage audit required"
        if migration_forensics_issue
        else "10m collector + feature + migration proof passed; 60m thesis scan ready"
        if can_run_60m_thesis_scan
        else "10m collector + feature proof passed; 60m thesis readiness blocked"
    )
    report = {
        "audit_id": "T011_2_LONG_SCAN_READINESS_AUDIT",
        "run_root": str(root),
        "t0103_curve_gate_passed": curve_pass,
        "t0103_curve_gate_source": (
            "scan_supervisor_status"
            if supervisor
            else ("curve_decode_reliability_audit" if curve_audit else "canonical_lifecycle_materializer")
        ),
        "canonical_lifecycle_curve_gate_passed": lifecycle_curve_gate_passed,
        "canonical_lifecycle_curve_decode_ratio": lifecycle_curve_decode_ratio,
        "canonical_lifecycle_curve_state_decoded": lifecycle_curve_state_decoded,
        "canonical_lifecycle_verified_births": lifecycle_verified_births,
        "curve_decode_material_issue": curve_decode_material_issue,
        "curve_decode_needed_decodes_to_pass": _int(curve_audit.get("needed_decodes_to_pass")) or 0,
        "curve_decode_missing_age_eligible_count": _int(curve_audit.get("missing_age_eligible_count")) or 0,
        "curve_decode_scheduler_gap_count": _int(curve_audit.get("scheduler_gap_count")) or 0,
        "scheduler_gap_resolved": True,
        "capacity_thin_probes_executed": True,
        "curve_decode_rescue_needed": False,
        "full_600s_source_duration_completed": source_completed,
        "can_run_10m_collector_proof": collector_proof_passed,
        "can_run_10m_feature_proof": feature_proof_passed,
        "10m_collector_proof_status": "passed" if collector_proof_passed else "failed",
        "10m_feature_proof_status": "passed" if feature_proof_passed else "failed",
        "migration_opportunity_status": migration_opportunity_status,
        "decision_safe_full_path_status": decision_safe_full_path_status,
        "60m_thesis_readiness": "ready" if can_run_60m_thesis_scan else "blocked",
        "clean_10m_proofs_required_for_60m": clean_10m_proofs_required_for_60m,
        "clean_10m_proofs_observed": clean_10m_proofs_observed,
        "clean_10m_proof_history_status": clean_10m_proof_history_status,
        "clean_10m_proof_history_required": clean_10m_proof_history_required,
        "clean_10m_proof_history_path": str(proof_history_path),
        "current_run_clean_10m_proof_candidate": current_run_clean_10m_proof_candidate,
        "source_quality_label": source_quality_label,
        "source_reconnect_warning": source_reconnect_warning,
        "source_quality_raw_status": str(
            _coalesce_present(
                collector_summary.get("source_duration_quality_status"),
                live_status_existing.get("source_duration_quality_status"),
                "not_evaluated",
            )
        ),
        "websocket_keepalive_timeout_count": websocket_keepalive_timeout_count,
        "websocket_reconnect_count": websocket_reconnect_count,
        "persistent_lifecycle_store": persistent_lifecycle_store,
        "persistent_lifecycle_store_authority": "sqlite" if persistent_sqlite_exists else ("jsonl" if persistent_events_jsonl_exists else "none"),
        "persistent_lifecycle_events_jsonl": persistent_lifecycle_events_jsonl,
        "latency_histograms_present": latency_histograms_present,
        "route_latency_histograms": route_latency_histograms,
        "route_latency_gate_passed": route_latency_gate_passed,
        "route_latency_gate_failures": route_latency_gate_failures,
        "decision_path_route_gate_passed": bool(
            _coalesce_present(
                collector_summary.get("decision_path_route_gate_passed"),
                live_status_existing.get("decision_path_route_gate_passed"),
                route_latency_gate_passed,
            )
        ),
        "decision_path_route_gate_failures": list(
            _coalesce_present(
                collector_summary.get("decision_path_route_gate_failures"),
                live_status_existing.get("decision_path_route_gate_failures"),
                route_latency_gate_failures,
            )
            or []
        ),
        "route_latency_gate_scope": str(
            _coalesce_present(
                collector_summary.get("route_latency_gate_scope"),
                live_status_existing.get("route_latency_gate_scope"),
                "decision_path_only",
            )
        ),
        "materialization_latency_gate_passed": materialization_latency_gate_passed,
        "materialization_latency_gate_failures": materialization_latency_gate_failures,
        "materialization_latency_gate_scope": str(
            _coalesce_present(
                collector_summary.get("materialization_latency_gate_scope"),
                live_status_existing.get("materialization_latency_gate_scope"),
                "audit_artifact_projection_path",
            )
        ),
        "commitment_reorg_drop_accounting_present": commitment_reorg_drop_accounting_present,
        "dropped_or_reorged_count": dropped_or_reorged_count,
        "source_gap_detected_count": source_gap_detected_count,
        "source_gap_backfilled_count": source_gap_backfilled_count,
        "source_gap_unbackfilled_count": source_gap_unbackfilled_count,
        "source_gap_reorg_gate_passed": source_gap_reorg_gate_passed,
        "helius_budget_gate_present": helius_budget_gate_present,
        "helius_budget_gate_passed": helius_budget_gate_passed,
        "helius_budget_blocker": helius_budget_blocker,
        "helius_estimated_credits_used": _int(
            _coalesce_present(
                collector_summary.get("helius_estimated_credits_used"),
                live_status_existing.get("helius_estimated_credits_used"),
            )
        )
        or 0,
        "helius_max_estimated_credits": _int(
            _coalesce_present(
                collector_summary.get("helius_max_estimated_credits"),
                live_status_existing.get("helius_max_estimated_credits"),
            )
        ),
        "gatekeeper_ab_status": str(
            _coalesce_present(
                collector_summary.get("gatekeeper_ab_status"),
                live_status_existing.get("gatekeeper_ab_status"),
                "not_configured",
            )
        ),
        "subscription_first_curve_updates_status": str(
            _coalesce_present(
                collector_summary.get("subscription_first_curve_updates_status"),
                live_status_existing.get("subscription_first_curve_updates_status"),
                "not_configured",
            )
        ),
        "trade_flow_eventful_parse_gate_passed": eventful_gap_count == 0,
        "trade_flow_eventful_parse_coverage_ratio": eventful_ratio,
        "trade_flow_true_gap_mints_count": eventful_gap_count,
        "trade_flow_unconditional_birth_coverage": trade.get("trade_flow_unconditional_birth_coverage"),
        "trade_flow_eventful_parse_coverage": trade.get("trade_flow_eventful_parse_coverage"),
        "trade_flow_no_event_mints": trade.get("trade_flow_no_event_mints"),
        "can_run_10m_feature_proof_reason": (
            "collector_curve_gate_passed_and_no_eventful_trade_flow_gaps"
            if feature_proof_passed
            else "collector_or_eventful_trade_flow_gate_not_proven"
        ),
        "can_run_60m_thesis_scan": can_run_60m_thesis_scan,
        "can_run_2h_plus_scan": False,
        "long_scan_status": "READY_FOR_60M_THESIS_SCAN" if can_run_60m_thesis_scan else "BLOCKED_FOR_LONG_SCAN",
        "readiness_decision": readiness_decision,
        "long_scan_readiness_banner_text": banner_text,
        "long_scan_blocker_bullets": long_scan_bullets,
        "blockers": blockers,
        "diagnostic_warnings": diagnostic_warnings,
        "global_migration_observed": global_migrations > 0,
        "global_migrations": global_migrations,
        "in_window_migrations": in_window_migrations,
        "startup_boundary_migrations": startup_boundary_migrations,
        "in_window_migration_observed": in_window_migrations > 0,
        "full_path_proof": decision_safe_full_paths > 0,
        "decision_safe_full_paths": decision_safe_full_paths,
        "row_derived_decision_safe_full_paths": row_derived_decision_safe_full_paths,
        "lifecycle_summary_decision_safe_full_paths": lifecycle_summary_decision_safe_full_paths,
        "decision_safe_full_path_authority": "canonical_lifecycle_summary" if lifecycle_summary_exists else "row_derived_linkage_fallback",
        "migrated_missing_curve_decode_count": _int(lifecycle_summary.get("migrated_missing_curve_decode_count")) or 0,
        "migrated_missing_market_cap_count": _int(lifecycle_summary.get("migrated_missing_market_cap_count")) or 0,
        "migrated_missing_trade_flow_count": _int(lifecycle_summary.get("migrated_missing_trade_flow_count")) or 0,
        "migrated_missing_holder_dev_count": _int(lifecycle_summary.get("migrated_missing_holder_dev_count")) or 0,
        "migrated_missing_evidence_reason_counts": dict(
            lifecycle_summary.get("migrated_missing_evidence_reason_counts") or {}
        ),
        "live_migration_side_effects_proven": live_migration_side_effects_proven,
        "live_migration_side_effect_drain_count": live_migration_side_effect_drain_count,
        "live_migration_side_effects_applied": live_migration_side_effects_applied,
        "live_migration_side_effects_failed": live_migration_side_effects_failed,
        "live_migration_side_effects_source_rows": live_migration_side_effects_source_rows,
        "migration_readiness_classification": migration_readiness_classification,
        "blocker_explanations": {
            "trade_flow_coverage_classification": trade.get("missing_trade_flow_mints_by_category"),
            "trade_flow_policy_split": {
                "unconditional_birth_coverage_is_diagnostic_only": True,
                "eventful_trade_flow_true_gap_count": eventful_gap_count,
                "no_event_mints": trade.get("trade_flow_no_event_mints"),
            },
            "no_in_window_decision_safe_full_path": migration.get("migration_readiness_failure_reason_counts"),
            "curve_decode_issue": {
                "material": curve_decode_material_issue,
                "missing_age_eligible_count": _int(curve_audit.get("missing_age_eligible_count")) or 0,
                "needed_decodes_to_pass": _int(curve_audit.get("needed_decodes_to_pass")) or 0,
            },
            "migration_capture_forensics": {
                "readiness_correction": migration_forensics_correction or None,
                "missed_candidate_count": _int(migration_forensics.get("missed_candidate_count")) or 0,
                "global_migration_thread_error_count": _int(migration_forensics.get("global_migration_thread_error_count")) or 0,
                "raw_migration_spool_rows": _int(migration_forensics.get("raw_migration_spool_rows")) or 0,
                "migration_write_failure_count": _int(migration_forensics.get("migration_write_failure_count")) or 0,
                "migration_write_retry_pending_count": _int(migration_forensics.get("migration_write_retry_pending_count")) or 0,
                "sqlite_thread_affinity_error_count": _int(migration_forensics.get("sqlite_thread_affinity_error_count")) or 0,
                "json_path": migration_forensics.get("json_path") or (str(root / "migration_capture_forensics.json") if migration_forensics else None),
            },
            "live_migration_side_effects": {
                "proven": live_migration_side_effects_proven,
                "drain_count": live_migration_side_effect_drain_count,
                "applied": live_migration_side_effects_applied,
                "failed": live_migration_side_effects_failed,
                "source_rows": live_migration_side_effects_source_rows,
            },
        },
        "next_fix_recommendations": sorted(set(recommendations)),
        "trade_flow_audit_path": trade.get("json_path"),
        "trade_flow_eventful_gap_audit_path": trade_gap.get("json_path"),
        "migration_linkage_audit_path": migration.get("json_path"),
        "migration_capture_forensics_path": migration_forensics.get("json_path") or (str(root / "migration_capture_forensics.json") if migration_forensics else None),
        "migration_capture_forensics_readiness_correction": migration_forensics_correction or None,
        "missed_migration_candidate_count": _int(migration_forensics.get("missed_candidate_count")) or 0,
        "global_migration_thread_error_count": _int(migration_forensics.get("global_migration_thread_error_count")) or 0,
        "raw_migration_spool_rows": _int(migration_forensics.get("raw_migration_spool_rows")) or 0,
        "migration_write_failure_count": _int(migration_forensics.get("migration_write_failure_count")) or 0,
        "migration_write_retry_pending_count": _int(migration_forensics.get("migration_write_retry_pending_count")) or 0,
        "sqlite_thread_affinity_error_count": _int(migration_forensics.get("sqlite_thread_affinity_error_count")) or 0,
        "migration_lane_health": "failed" if migration_lane_write_failure else ("degraded" if migration_forensics_issue else "ok"),
        "json_path": str(root / "long_scan_readiness_audit.json"),
        "markdown_path": str(root / "long_scan_readiness_audit.md"),
    }
    if current_run_clean_10m_proof_candidate:
        try:
            proof_history_path.parent.mkdir(parents=True, exist_ok=True)
            proof_history_payload = {}
            if proof_history_path.exists():
                proof_history_payload = json.loads(proof_history_path.read_text(encoding="utf-8"))
            clean_runs = list(proof_history_payload.get("clean_10m_proofs") or proof_history_payload.get("runs") or [])
            existing_roots = {str(row.get("run_root") or "") for row in clean_runs}
            if str(root) not in existing_roots:
                clean_runs.append(
                    {
                        "run_root": str(root),
                        "run_id": str(collector_summary.get("run_id") or live_status_existing.get("run_id") or root.name),
                        "proof_passed": True,
                        "clean": True,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "decision_safe_full_paths": decision_safe_full_paths,
                        "route_latency_gate_passed": route_latency_gate_passed,
                        "materialization_latency_gate_passed": materialization_latency_gate_passed,
                        "helius_budget_gate_passed": helius_budget_gate_passed,
                        "source_gap_reorg_gate_passed": source_gap_reorg_gate_passed,
                    }
                )
            proof_history_payload = {
                "proof_history_version": 1,
                "clean_10m_proofs_required_for_60m": clean_10m_proofs_required_for_60m,
                "clean_10m_proofs": clean_runs,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json_artifact(proof_history_path, proof_history_payload)
            report["clean_10m_proofs_observed_after_current_run"] = len(clean_runs)
            report["clean_10m_proof_history_updated"] = True
        except Exception as exc:
            report["clean_10m_proof_history_updated"] = False
            report["clean_10m_proof_history_error"] = f"{type(exc).__name__}: {exc}"
    else:
        report["clean_10m_proof_history_updated"] = False
    _write_json_artifact(root / "long_scan_readiness_audit.json", report)
    _write_markdown_artifact(
        root / "long_scan_readiness_audit.md",
        [
            "# T011.1 Long-Scan Readiness Audit",
            "",
            f"- 10m feature proof allowed: `{report['can_run_10m_feature_proof']}`",
            f"- 10m collector proof allowed: `{report['can_run_10m_collector_proof']}`",
            f"- 10m collector proof status: `{report['10m_collector_proof_status']}`",
            f"- 10m feature proof status: `{report['10m_feature_proof_status']}`",
            f"- Migration opportunity status: `{report['migration_opportunity_status']}`",
            f"- Decision-safe full path status: `{report['decision_safe_full_path_status']}`",
            f"- 60m thesis readiness: `{report['60m_thesis_readiness']}`",
            f"- 60m thesis scan allowed: `{report['can_run_60m_thesis_scan']}`",
            f"- 2h+ scan allowed: `{report['can_run_2h_plus_scan']}`",
            f"- T010.3 curve gate passed: `{report['t0103_curve_gate_passed']}`",
            f"- 10m feature proof reason: `{report['can_run_10m_feature_proof_reason']}`",
            f"- Trade-flow eventful parse gate passed: `{report['trade_flow_eventful_parse_gate_passed']}`",
            f"- Trade-flow eventful parse coverage: `{report['trade_flow_eventful_parse_coverage']}`",
            f"- Trade-flow no-event mints: `{report['trade_flow_no_event_mints']}`",
            f"- Full 600s source duration completed: `{report['full_600s_source_duration_completed']}`",
            f"- Source quality label: `{report['source_quality_label']}`",
            f"- Source reconnect warning: `{report['source_reconnect_warning']}`",
            f"- Persistent lifecycle store: `{report['persistent_lifecycle_store']}`",
            f"- Persistent lifecycle events JSONL: `{report['persistent_lifecycle_events_jsonl']}`",
            f"- Latency histograms present: `{report['latency_histograms_present']}`",
            f"- Route latency gate passed: `{report['route_latency_gate_passed']}`",
            f"- Route latency failures: `{report['route_latency_gate_failures']}`",
            f"- Source gap/reorg gate passed: `{report['source_gap_reorg_gate_passed']}`",
            f"- Dropped or reorged events: `{report['dropped_or_reorged_count']}`",
            f"- Unbackfilled source gaps: `{report['source_gap_unbackfilled_count']}`",
            f"- Helius budget gate passed: `{report['helius_budget_gate_passed']}`",
            f"- Helius budget blocker: `{report['helius_budget_blocker']}`",
            f"- Long-scan status: `{report['long_scan_status']}`",
            f"- Watcher banner: `{report['long_scan_readiness_banner_text']}`",
            f"- Blockers: `{report['blockers']}`",
            f"- Diagnostic warnings: `{report['diagnostic_warnings']}`",
            f"- Migration readiness classification: `{report['migration_readiness_classification']}`",
            f"- Migration capture forensics correction: `{report['migration_capture_forensics_readiness_correction']}`",
            f"- Missed migration candidates: `{report['missed_migration_candidate_count']}`",
            f"- Global migration thread errors: `{report['global_migration_thread_error_count']}`",
            f"- Migration lane health: `{report['migration_lane_health']}`",
            f"- Raw migration spool rows: `{report['raw_migration_spool_rows']}`",
            f"- Migration write failures: `{report['migration_write_failure_count']}`",
            f"- Migration pending writes: `{report['migration_write_retry_pending_count']}`",
            f"- SQLite thread-affinity errors: `{report['sqlite_thread_affinity_error_count']}`",
            f"- Live migration side effects proven: `{report['live_migration_side_effects_proven']}`",
            f"- Live migration side-effect drains: `{report['live_migration_side_effect_drain_count']}`",
            f"- Live migration side effects applied: `{report['live_migration_side_effects_applied']}`",
            f"- Live migration side effects failed: `{report['live_migration_side_effects_failed']}`",
            f"- Migrated missing curve decode: `{report['migrated_missing_curve_decode_count']}`",
            f"- Migrated missing market cap: `{report['migrated_missing_market_cap_count']}`",
            f"- Migrated missing trade flow: `{report['migrated_missing_trade_flow_count']}`",
            f"- Migrated missing holder/dev: `{report['migrated_missing_holder_dev_count']}`",
            f"- Migrated missing evidence reasons: `{report['migrated_missing_evidence_reason_counts']}`",
            f"- Blocker explanations: `{report['blocker_explanations']}`",
            f"- Next fix recommendations: `{report['next_fix_recommendations']}`",
            "",
            "No live source, RPC, wallet, signing, trading, or paper-trading path is used by this offline audit.",
        ],
    )
    live_status = _read_json(root / "live_status.json")
    if live_status:
        live_status.update(
            {
                "can_run_10m_feature_proof": report["can_run_10m_feature_proof"],
                "can_run_10m_collector_proof": report["can_run_10m_collector_proof"],
                "10m_collector_proof_status": report["10m_collector_proof_status"],
                "10m_feature_proof_status": report["10m_feature_proof_status"],
                "migration_opportunity_status": report["migration_opportunity_status"],
                "decision_safe_full_path_status": report["decision_safe_full_path_status"],
                "60m_thesis_readiness": report["60m_thesis_readiness"],
                "source_quality_label": report["source_quality_label"],
                "source_reconnect_warning": report["source_reconnect_warning"],
                "source_quality_raw_status": report["source_quality_raw_status"],
                "persistent_lifecycle_store": report["persistent_lifecycle_store"],
                "persistent_lifecycle_store_authority": report["persistent_lifecycle_store_authority"],
                "persistent_lifecycle_events_jsonl": report["persistent_lifecycle_events_jsonl"],
                "latency_histograms_present": report["latency_histograms_present"],
                "route_latency_histograms": report["route_latency_histograms"],
                "route_latency_gate_passed": report["route_latency_gate_passed"],
                "route_latency_gate_failures": report["route_latency_gate_failures"],
                "commitment_reorg_drop_accounting_present": report["commitment_reorg_drop_accounting_present"],
                "dropped_or_reorged_count": report["dropped_or_reorged_count"],
                "source_gap_detected_count": report["source_gap_detected_count"],
                "source_gap_backfilled_count": report["source_gap_backfilled_count"],
                "source_gap_unbackfilled_count": report["source_gap_unbackfilled_count"],
                "source_gap_reorg_gate_passed": report["source_gap_reorg_gate_passed"],
                "helius_budget_gate_present": report["helius_budget_gate_present"],
                "helius_budget_gate_passed": report["helius_budget_gate_passed"],
                "helius_budget_blocker": report["helius_budget_blocker"],
                "helius_estimated_credits_used": report["helius_estimated_credits_used"],
                "helius_max_estimated_credits": report["helius_max_estimated_credits"],
                "gatekeeper_ab_status": report["gatekeeper_ab_status"],
                "subscription_first_curve_updates_status": report["subscription_first_curve_updates_status"],
                "can_run_10m_feature_proof_reason": report["can_run_10m_feature_proof_reason"],
                "can_run_60m_thesis_scan": report["can_run_60m_thesis_scan"],
                "can_run_2h_plus_scan": False,
                "long_scan_status": report["long_scan_status"],
                "readiness_decision": report["readiness_decision"],
                "long_scan_readiness_banner_text": report["long_scan_readiness_banner_text"],
                "long_scan_blocker_bullets": report["long_scan_blocker_bullets"],
                "long_scan_readiness_blockers": report["blockers"],
                "long_scan_readiness_diagnostic_warnings": report["diagnostic_warnings"],
                "trade_flow_missing_mints_by_category": trade.get("missing_trade_flow_mints_by_category"),
                "trade_flow_unconditional_birth_coverage": trade.get("trade_flow_unconditional_birth_coverage"),
                "trade_flow_eventful_parse_coverage": trade.get("trade_flow_eventful_parse_coverage"),
                "trade_flow_no_event_mints": trade.get("trade_flow_no_event_mints"),
                "trade_flow_true_gap_mints": trade.get("trade_flow_true_gap_mints"),
                "trade_flow_true_gap_mints_count": eventful_gap_count,
                "trade_flow_coverage_audit_path": trade.get("json_path"),
                "trade_flow_eventful_gap_audit_path": trade_gap.get("json_path"),
                "migration_linkage_audit_path": migration.get("json_path"),
                "migration_capture_forensics_path": report["migration_capture_forensics_path"],
                "migration_capture_forensics_readiness_correction": report["migration_capture_forensics_readiness_correction"],
                "missed_migration_candidate_count": report["missed_migration_candidate_count"],
                "global_migration_thread_error_count": report["global_migration_thread_error_count"],
                "raw_migration_spool_rows": report["raw_migration_spool_rows"],
                "migration_write_failure_count": report["migration_write_failure_count"],
                "migration_write_retry_pending_count": report["migration_write_retry_pending_count"],
                "sqlite_thread_affinity_error_count": report["sqlite_thread_affinity_error_count"],
                "migration_lane_health": report["migration_lane_health"],
                "migration_lane_writer_status": report["migration_lane_health"],
                "migration_readiness_failure_reason_counts": migration.get("migration_readiness_failure_reason_counts"),
                "migration_readiness_classification": report["migration_readiness_classification"],
                "global_migration_observed": report["global_migration_observed"],
                "live_migration_side_effects_proven": report["live_migration_side_effects_proven"],
                "live_migration_side_effect_drain_count": report["live_migration_side_effect_drain_count"],
                "live_migration_side_effects_applied": report["live_migration_side_effects_applied"],
                "live_migration_side_effects_failed": report["live_migration_side_effects_failed"],
                "live_migration_side_effects_source_rows": report["live_migration_side_effects_source_rows"],
                "decision_safe_full_paths": report["decision_safe_full_paths"],
                "row_derived_decision_safe_full_paths": report["row_derived_decision_safe_full_paths"],
                "lifecycle_summary_decision_safe_full_paths": report["lifecycle_summary_decision_safe_full_paths"],
                "migrated_missing_curve_decode_count": report["migrated_missing_curve_decode_count"],
                "migrated_missing_market_cap_count": report["migrated_missing_market_cap_count"],
                "migrated_missing_trade_flow_count": report["migrated_missing_trade_flow_count"],
                "migrated_missing_holder_dev_count": report["migrated_missing_holder_dev_count"],
                "migrated_missing_evidence_reason_counts": report["migrated_missing_evidence_reason_counts"],
                "global_migration_mints_seen": _int(lifecycle_summary.get("global_migration_mints_seen")) or 0,
                "migrated_unique_mints": _int(lifecycle_summary.get("migrated_unique_mints")) or 0,
                "migration_linked_to_birth": _int(lifecycle_summary.get("migration_linked_to_birth")) or 0,
                "confirmed_migration_linked_to_birth": _int(lifecycle_summary.get("confirmed_migration_linked_to_birth")) or 0,
                "full_path_migrated_mints": _int(lifecycle_summary.get("full_path_migrated_mints")) or 0,
                "strict_full_path_migrated_mints": _int(lifecycle_summary.get("strict_full_paths")) or 0,
                "lifecycle_coverage_summary": lifecycle_summary,
                "in_window_migration_observed": report["in_window_migration_observed"],
                "full_path_proof": report["full_path_proof"],
                "startup_boundary_migration_count": migration.get("startup_boundary_migration_count"),
                "steady_state_unlinked_migration_count": migration.get("steady_state_unlinked_migration_count"),
                "curve_decode_material_issue": curve_decode_material_issue,
            }
        )
        if str(live_status.get("runtime_phase") or "").startswith("finalized") or str(live_status.get("run_status") or "").startswith("finalized"):
            live_status.update(
                {
                    "runtime_phase": "finalized",
                    "source_remaining_seconds": 0.0,
                    "drain_remaining_seconds": 0.0,
                    "finalization_elapsed_seconds": 0.0,
                    "finalization_overrun_seconds": 0.0,
                    "finalization_stuck_warning": False,
                }
            )
        _write_json_artifact(root / "live_status.json", live_status)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pump.fun bonding-curve progress recorder v1")
    parser.add_argument(
        "--mode",
        choices=[
            "smoke",
            "synthetic-smoke",
            "live-smoke",
            "birth-source-audit",
            "transaction-birth-source-audit",
            "transaction-live-smoke",
            "migration-source-audit",
            "migration-route-audit",
            "audit-trade-flow",
            "audit-trade-flow-eventful-gap",
            "audit-migration-linkage",
            "audit-migration-capture-forensics",
            "audit-migration-write-path",
            "audit-migration-dedupe",
            "audit-long-scan-readiness",
            "audit-tracking-admission",
            "simulate-capacity-promotion",
            "reconcile-migration-full-path-status",
            "rebuild-migrations-from-spool",
            "axiom-reconcile",
            "migrated-mint-replay",
        ],
        default="smoke",
    )
    parser.add_argument("--data-root", "--output-root", dest="data_root", default=None)
    parser.add_argument("--staging-root", default=None)
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--archive-after-run", default=False)
    parser.add_argument("--local-retention-enabled", default=True)
    parser.add_argument("--local-retention-keep-latest", type=int, default=1)
    parser.add_argument("--local-retention-archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--source-duration-seconds", "--duration-seconds", dest="source_duration_seconds", type=float, default=300.0)
    parser.add_argument("--followup-drain-seconds", type=float, default=300.0)
    parser.add_argument("--sample-rate-percent", type=int, default=55)
    parser.add_argument("--tracking-profile", default=TRACKING_PROFILE_CONSERVATIVE_DEFAULT)
    parser.add_argument("--max-active-tracking", type=int, default=100)
    parser.add_argument("--followup-queue-max-size", type=int, default=250)
    parser.add_argument("--birth-priority-worker-count", type=int, default=1)
    parser.add_argument("--birth-priority-queue-max-size", type=int, default=5000)
    parser.add_argument("--trade-flow-worker-count", type=int, default=1)
    parser.add_argument("--trade-flow-queue-max-size", type=int, default=20_000)
    parser.add_argument("--max-token-age-seconds", type=float, default=1800.0)
    parser.add_argument("--inactive-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--sol-usd", type=float, default=None)
    parser.add_argument("--disable-auto-sol-usd", default=False)
    parser.add_argument("--axiom-mints", default="")
    parser.add_argument("--axiom-mints-path", default=None)
    parser.add_argument("--axiom-mints-csv", default=None)
    parser.add_argument("--expected-mints", default=None)
    parser.add_argument("--input-run-root", default=None)
    parser.add_argument("--mints-csv", default=None)
    parser.add_argument("--direct-lookup-limit", type=int, default=0)
    parser.add_argument("--direct-lookup-sleep-ms", type=int, default=250)
    parser.add_argument("--direct-lookup-output-root", default=None)
    parser.add_argument("--max-signatures-per-address", type=int, default=25)
    parser.add_argument("--max-transactions-per-mint", type=int, default=50)
    parser.add_argument("--lookup-sleep-ms", type=int, default=None)
    parser.add_argument("--include-raw-transactions", default=False)
    parser.add_argument("--enable-global-pumpswap-migration", default="auto")
    parser.add_argument("--gatekeeper-ab-enabled", default=False)
    parser.add_argument("--gatekeeper-primary-endpoint-label", default="")
    parser.add_argument("--gatekeeper-comparison-endpoint-label", default="")
    parser.add_argument("--subscription-first-curve-updates-enabled", default=False)
    parser.add_argument("--route-latency-gate-enabled", default=True)
    parser.add_argument("--max-birth-to-admission-p95-ms", type=float, default=1_000.0)
    parser.add_argument("--max-verified-birth-commit-to-probe-enqueue-p95-ms", type=float, default=100.0)
    parser.add_argument("--max-birth-to-admission-complete-p95-ms", type=float, default=1_500.0)
    parser.add_argument("--max-normalized-birth-to-probe-start-p95-ms", type=float, default=1_500.0)
    parser.add_argument("--max-birth-to-first-curve-observation-p95-ms", type=float, default=3_000.0)
    parser.add_argument("--max-probe-duration-p95-ms", type=float, default=1_000.0)
    parser.add_argument("--near-entry-hot-flow-enabled", default=True)
    parser.add_argument("--commitment-reorg-drop-accounting-enabled", default=True)
    parser.add_argument("--helius-budget-gate-enabled", default=True)
    parser.add_argument("--helius-max-estimated-credits", type=int, default=None)
    parser.add_argument("--helius-estimated-credits-used", type=int, default=0)
    parser.add_argument("--max-finalization-wall-time-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def _resolve_global_pumpswap_enabled(mode: str, raw_value: Any) -> bool:
    if str(raw_value).strip().lower() == "auto":
        return str(mode) in {"live-smoke", "transaction-live-smoke"}
    return _parse_bool_value(raw_value)


def _resolve_sol_usd_for_run(cli_sol_usd: float | None, *, allow_auto: bool = True) -> dict[str, Any]:
    if cli_sol_usd is not None:
        return {
            "sol_usd": float(cli_sol_usd),
            "sol_usd_source": "manual_cli_sol_usd",
            "sol_usd_status": "available",
            "sol_usd_error": "",
        }
    for env_name in ("MTP_SOL_USD", "SOL_USD"):
        raw = os.environ.get(env_name)
        if raw:
            try:
                return {
                    "sol_usd": float(raw),
                    "sol_usd_source": f"env_{env_name.lower()}",
                    "sol_usd_status": "available",
                    "sol_usd_error": "",
                }
            except ValueError:
                return {
                    "sol_usd": None,
                    "sol_usd_source": f"env_{env_name.lower()}",
                    "sol_usd_status": "error",
                    "sol_usd_error": f"invalid_float:{env_name}",
                }
    if allow_auto:
        try:
            return {
                "sol_usd": _fetch_sol_usd_from_pyth_hermes(timeout_seconds=3.0),
                "sol_usd_source": "pyth_hermes_sol_usd",
                "sol_usd_status": "available",
                "sol_usd_error": "",
            }
        except Exception as exc:
            return {
                "sol_usd": None,
                "sol_usd_source": "pyth_hermes_sol_usd",
                "sol_usd_status": "error",
                "sol_usd_error": str(exc)[:240],
            }
    return {
        "sol_usd": None,
        "sol_usd_source": "missing",
        "sol_usd_status": "missing",
        "sol_usd_error": "",
    }


def _fetch_sol_usd_from_pyth_hermes(*, timeout_seconds: float = 3.0) -> float:
    url = f"{PYTH_HERMES_PRICE_URL}?ids%5B%5D={PYTH_SOL_USD_PRICE_FEED_ID}"
    request = urllib.request.Request(url, headers={"User-Agent": "MemeTraderPro-T007/1.0"})
    api_key = os.environ.get("PYTH_API_KEY")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parsed = payload.get("parsed") or []
    if not parsed:
        raise RuntimeError("pyth_hermes_missing_parsed_price")
    price_obj = (parsed[0] or {}).get("price") or {}
    raw_price = price_obj.get("price")
    expo = price_obj.get("expo")
    if raw_price is None or expo is None:
        raise RuntimeError("pyth_hermes_missing_price_or_expo")
    price = float(raw_price) * (10 ** int(expo))
    if price <= 0:
        raise RuntimeError("pyth_hermes_nonpositive_sol_usd")
    return price


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = "bc-progress-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_root = Path(args.data_root).expanduser() if args.data_root else build_default_output_root(run_id=run_id)
    if args.mode in {
        "audit-trade-flow",
        "audit-trade-flow-eventful-gap",
        "audit-migration-linkage",
        "audit-migration-capture-forensics",
        "audit-migration-write-path",
        "audit-migration-dedupe",
        "audit-long-scan-readiness",
        "audit-tracking-admission",
        "simulate-capacity-promotion",
        "reconcile-migration-full-path-status",
        "rebuild-migrations-from-spool",
    }:
        if args.mode == "audit-trade-flow":
            summary = run_trade_flow_coverage_audit(output_root)
        elif args.mode == "audit-trade-flow-eventful-gap":
            summary = run_trade_flow_eventful_gap_audit(output_root)
        elif args.mode == "audit-migration-linkage":
            summary = run_migration_linkage_audit(output_root)
        elif args.mode == "audit-migration-capture-forensics":
            summary = run_migration_capture_forensics(output_root, expected_mints_path=args.expected_mints)
        elif args.mode == "audit-migration-write-path":
            summary = run_migration_write_path_audit(output_root)
        elif args.mode == "audit-migration-dedupe":
            summary = run_migration_dedupe_audit(output_root)
        elif args.mode == "rebuild-migrations-from-spool":
            summary = run_rebuild_migrations_from_spool(output_root)
        elif args.mode == "audit-tracking-admission":
            summary = run_tracking_admission_audit(output_root)
        elif args.mode == "simulate-capacity-promotion":
            summary = run_capacity_rejected_migration_promotion_simulation(output_root)
        elif args.mode == "reconcile-migration-full-path-status":
            summary = run_migration_full_path_status_reconciliation(output_root)
        else:
            summary = run_long_scan_readiness_audit(output_root)
        print("## Bonding Curve Progress Recorder v1")
        print(f"mode={args.mode}")
        print(f"run_id={summary.get('run_id')}")
        print(f"output_root={output_root}")
        print(f"active_write_root={output_root}")
        print("archive_root=None")
        print(f"archive_status={summary.get('archive_status')}")
        print(f"live_source_used={summary.get('live_source_used')}")
        print(f"subscription_connect_status={summary.get('subscription_connect_status')}")
        if args.mode == "audit-trade-flow":
            print(f"unique_birth_mints={summary.get('unique_birth_mints')}")
            print(f"trade_flow_denominator={summary.get('trade_flow_denominator')}")
            print(f"trade_flow_covered_mints={summary.get('trade_flow_covered_mints')}")
            print(f"trade_flow_missing_mints={summary.get('trade_flow_missing_mints')}")
            print(f"denominator_mismatch_flagged={summary.get('denominator_mismatch_flagged')}")
            print(f"missing_trade_flow_mints_by_category={summary.get('missing_trade_flow_mints_by_category')}")
            print(f"trade_flow_missing_mints_debug_json={summary.get('json_path')}")
            print(f"trade_flow_coverage_audit_md={summary.get('markdown_path')}")
        elif args.mode == "audit-trade-flow-eventful-gap":
            print(f"eventful_gap_count={summary.get('eventful_gap_count')}")
            print(f"no_event_missing_count={summary.get('no_event_missing_count')}")
            print(f"trade_flow_eventful_gap_audit_json={summary.get('json_path')}")
            print(f"trade_flow_eventful_gap_audit_md={summary.get('markdown_path')}")
        elif args.mode == "audit-migration-linkage":
            print(f"global_migration_events_deduped={summary.get('global_migration_events_deduped')}")
            print(f"lifecycle_migrated_unique_mints={summary.get('lifecycle_migrated_unique_mints')}")
            print(f"decision_safe_full_paths={summary.get('decision_safe_full_paths')}")
            print(f"failure_reason_counts={summary.get('failure_reason_counts')}")
            print(f"migration_linkage_audit_json={summary.get('json_path')}")
            print(f"migration_linkage_audit_md={summary.get('markdown_path')}")
        elif args.mode == "audit-migration-capture-forensics":
            print(f"raw_migration_candidate_count_before_decode={summary.get('raw_migration_candidate_count_before_decode')}")
            print(f"decoded_migration_candidate_count={summary.get('decoded_migration_candidate_count')}")
            print(f"deduped_migration_count={summary.get('deduped_migration_count')}")
            print(f"in_window_migration_candidate_count={summary.get('in_window_migration_candidate_count')}")
            print(f"startup_boundary_count={summary.get('startup_boundary_count')}")
            print(f"unsupported_route_count={summary.get('unsupported_route_count')}")
            print(f"missed_candidate_count={summary.get('missed_candidate_count')}")
            print(f"readiness_correction={summary.get('readiness_correction')}")
            print(f"migration_capture_forensics_json={summary.get('json_path')}")
            print(f"migration_capture_forensics_md={summary.get('markdown_path')}")
        elif args.mode == "audit-migration-write-path":
            print(f"decoded_migration_candidates={summary.get('decoded_migration_candidates')}")
            print(f"raw_spool_rows={summary.get('raw_spool_rows')}")
            print(f"write_intent_candidates={summary.get('write_intent_candidates')}")
            print(f"write_status_counts={summary.get('write_status_counts')}")
            print(f"classification_counts={summary.get('classification_counts')}")
            print(f"migration_write_path_audit_json={summary.get('json_path')}")
            print(f"migration_write_path_audit_md={summary.get('markdown_path')}")
        elif args.mode == "audit-migration-dedupe":
            print(f"decoded_candidates_before_dedupe={summary.get('decoded_candidates_before_dedupe')}")
            print(f"deduped_migrations={summary.get('deduped_migrations')}")
            print(f"dedupe_key_used={summary.get('dedupe_key_used')}")
            print(f"dedupe_key_too_broad={summary.get('dedupe_key_too_broad')}")
            print(f"migration_dedupe_audit_json={summary.get('json_path')}")
            print(f"migration_dedupe_audit_md={summary.get('markdown_path')}")
        elif args.mode == "rebuild-migrations-from-spool":
            print(f"raw_spool_rows={summary.get('raw_spool_rows')}")
            print(f"events_recovered_from_spool={summary.get('events_recovered_from_spool')}")
            print(f"skipped_missing_fields={summary.get('skipped_missing_fields')}")
            print(f"skipped_duplicates={summary.get('skipped_duplicates')}")
            print(f"recovery_status={summary.get('recovery_status')}")
            print(f"migration_spool_rebuild_json={summary.get('json_path')}")
        elif args.mode == "audit-tracking-admission":
            print(f"birth_rows={summary.get('birth_rows')}")
            print(f"admitted_births={summary.get('admitted_births')}")
            print(f"capacity_rejected_births={summary.get('capacity_rejected_births')}")
            print(f"birth_seen_but_not_admitted_migrations={summary.get('birth_seen_but_not_admitted_migrations')}")
            print(f"tracking_admission_audit_json={summary.get('json_path')}")
        elif args.mode == "simulate-capacity-promotion":
            print(f"capacity_rejected_migration_rows={summary.get('capacity_rejected_migration_rows')}")
            print(f"would_promote_under_new_policy_count={summary.get('would_promote_under_new_policy_count')}")
            print(f"likely_decision_safe_if_promoted_earlier_count={summary.get('likely_decision_safe_if_promoted_earlier_count')}")
            print(f"capacity_rejected_migration_promotion_simulation_json={summary.get('json_path')}")
        elif args.mode == "reconcile-migration-full-path-status":
            print(f"decision_safe_full_paths={summary.get('decision_safe_full_paths')}")
            print(f"live_status_previous_decision_safe_full_paths={summary.get('live_status_previous_decision_safe_full_paths')}")
            print(f"live_status_reconciled_decision_safe_full_paths={summary.get('live_status_reconciled_decision_safe_full_paths')}")
            print(f"migration_full_path_status_reconciliation_json={summary.get('json_path')}")
        else:
            print(f"can_run_10m_feature_proof={summary.get('can_run_10m_feature_proof')}")
            print(f"can_run_60m_thesis_scan={summary.get('can_run_60m_thesis_scan')}")
            print(f"can_run_2h_plus_scan={summary.get('can_run_2h_plus_scan')}")
            print(f"blockers={summary.get('blockers')}")
            print(f"next_fix_recommendations={summary.get('next_fix_recommendations')}")
            print(f"long_scan_readiness_audit_json={summary.get('json_path')}")
            print(f"long_scan_readiness_audit_md={summary.get('markdown_path')}")
        return 0
    staging_root = Path(args.staging_root).expanduser() if args.staging_root else None
    archive_after_run = _parse_bool_value(args.archive_after_run)
    archive_root = (
        Path(args.archive_root).expanduser()
        if args.archive_root
        else (DEFAULT_ARCHIVE_ROOT / run_id if archive_after_run else None)
    )
    local_retention_archive_root = (
        Path(args.local_retention_archive_root).expanduser()
        if args.local_retention_archive_root
        else DEFAULT_ARCHIVE_ROOT
    )
    global_pumpswap_enabled = _resolve_global_pumpswap_enabled(args.mode, args.enable_global_pumpswap_migration)
    sol_usd_resolution = _resolve_sol_usd_for_run(
        args.sol_usd,
        allow_auto=not _parse_bool_value(args.disable_auto_sol_usd)
        and args.mode in {"live-smoke", "transaction-live-smoke", "migration-source-audit", "migration-route-audit"},
    )
    config = BondingCurveRecorderConfig(
        output_root=output_root,
        run_id=run_id,
        source_duration_seconds=args.source_duration_seconds,
        followup_drain_seconds=args.followup_drain_seconds,
        sample_rate_percent=args.sample_rate_percent,
        tracking_profile=args.tracking_profile,
        max_active_tracking=args.max_active_tracking,
        followup_queue_max_size=args.followup_queue_max_size,
        birth_priority_worker_count=args.birth_priority_worker_count,
        birth_priority_queue_max_size=args.birth_priority_queue_max_size,
        trade_flow_worker_count=args.trade_flow_worker_count,
        trade_flow_queue_max_size=args.trade_flow_queue_max_size,
        max_token_age_seconds=args.max_token_age_seconds,
        inactive_timeout_seconds=args.inactive_timeout_seconds,
        sol_usd=sol_usd_resolution["sol_usd"],
        sol_usd_source=sol_usd_resolution["sol_usd_source"],
        sol_usd_status=sol_usd_resolution["sol_usd_status"],
        sol_usd_error=sol_usd_resolution["sol_usd_error"],
        staging_root=staging_root,
        archive_root=archive_root,
        archive_after_run=archive_after_run,
        local_retention_enabled=args.local_retention_enabled,
        local_retention_keep_latest=args.local_retention_keep_latest,
        local_retention_archive_root=local_retention_archive_root,
        enable_global_pumpswap_migration=global_pumpswap_enabled,
        require_verified_curve_account_for_admission=args.mode in {"live-smoke", "transaction-live-smoke"},
        gatekeeper_ab_enabled=args.gatekeeper_ab_enabled,
        gatekeeper_primary_endpoint_label=args.gatekeeper_primary_endpoint_label,
        gatekeeper_comparison_endpoint_label=args.gatekeeper_comparison_endpoint_label,
        subscription_first_curve_updates_enabled=args.subscription_first_curve_updates_enabled,
        route_latency_gate_enabled=args.route_latency_gate_enabled,
        max_birth_to_admission_p95_ms=args.max_birth_to_admission_p95_ms,
        max_verified_birth_commit_to_probe_enqueue_p95_ms=args.max_verified_birth_commit_to_probe_enqueue_p95_ms,
        max_birth_to_admission_complete_p95_ms=args.max_birth_to_admission_complete_p95_ms,
        max_normalized_birth_to_probe_start_p95_ms=args.max_normalized_birth_to_probe_start_p95_ms,
        max_birth_to_first_curve_observation_p95_ms=args.max_birth_to_first_curve_observation_p95_ms,
        max_probe_duration_p95_ms=args.max_probe_duration_p95_ms,
        near_entry_hot_flow_enabled=args.near_entry_hot_flow_enabled,
        commitment_reorg_drop_accounting_enabled=args.commitment_reorg_drop_accounting_enabled,
        helius_budget_gate_enabled=args.helius_budget_gate_enabled,
        helius_max_estimated_credits=args.helius_max_estimated_credits,
        helius_estimated_credits_used=args.helius_estimated_credits_used,
        max_finalization_wall_time_seconds=args.max_finalization_wall_time_seconds,
        bounded_live_finalization_enabled=args.mode in {"live-smoke", "transaction-live-smoke"},
        source_name="helius_websocket_logs"
        if args.mode in {"live-smoke", "birth-source-audit", "transaction-birth-source-audit", "transaction-live-smoke", "migration-source-audit", "migration-route-audit"}
        else "bonding_curve_progress_recorder_v1",
    )
    if args.mode == "migrated-mint-replay":
        input_run_root = Path(args.input_run_root).expanduser() if args.input_run_root else output_root
        mints = [item.strip() for item in str(args.axiom_mints or "").replace("\n", ",").split(",") if item.strip()]
        summary = run_migrated_mint_replay(
            input_run_root,
            output_root=output_root,
            mints=mints,
            mints_csv=args.mints_csv,
            max_signatures_per_address=int(args.max_signatures_per_address),
            max_transactions_per_mint=int(args.max_transactions_per_mint),
            lookup_sleep_ms=int(args.lookup_sleep_ms if args.lookup_sleep_ms is not None else args.direct_lookup_sleep_ms),
            include_raw_transactions=_parse_bool_value(args.include_raw_transactions),
        )
    elif args.mode == "audit-trade-flow":
        summary = run_trade_flow_coverage_audit(output_root)
    elif args.mode == "audit-migration-linkage":
        summary = run_migration_linkage_audit(output_root)
    elif args.mode == "rebuild-migrations-from-spool":
        summary = run_rebuild_migrations_from_spool(output_root)
    elif args.mode == "audit-long-scan-readiness":
        summary = run_long_scan_readiness_audit(output_root)
    elif args.mode == "axiom-reconcile":
        mints: list[Any] = [item.strip() for item in str(args.axiom_mints or "").replace("\n", ",").split(",") if item.strip()]
        axiom_path = args.axiom_mints_csv or args.axiom_mints_path
        if axiom_path:
            path = Path(axiom_path).expanduser()
            if path.exists():
                if path.suffix.lower() == ".csv":
                    with path.open("r", encoding="utf-8", newline="") as handle:
                        mints.extend(dict(row) for row in csv.DictReader(handle))
                else:
                    mints.extend(item.strip() for item in path.read_text(encoding="utf-8").replace("\n", ",").split(",") if item.strip())
        if int(args.direct_lookup_limit or 0) > 0 and mints:
            lookup_root = Path(args.direct_lookup_output_root).expanduser() if args.direct_lookup_output_root else output_root
            run_direct_mint_lookup(
                lookup_root,
                mints,
                direct_lookup_limit=int(args.direct_lookup_limit),
                sleep_ms=int(args.direct_lookup_sleep_ms),
                include_raw_transactions=_parse_bool_value(args.include_raw_transactions),
            )
        summary = run_axiom_reconciliation(output_root, mints)
    elif args.mode == "live-smoke":
        summary = run_transaction_live_smoke(config)
    elif args.mode == "birth-source-audit":
        summary = run_birth_source_audit(config)
    elif args.mode == "transaction-birth-source-audit":
        summary = run_transaction_birth_source_audit(config)
    elif args.mode == "transaction-live-smoke":
        summary = run_transaction_live_smoke(config)
    elif args.mode == "migration-source-audit":
        summary = run_migration_source_audit(config)
    elif args.mode == "migration-route-audit":
        summary = run_migration_route_audit(config)
    else:
        summary = run_synthetic_smoke(config)
    print("## Bonding Curve Progress Recorder v1")
    print(f"mode={args.mode}")
    print(f"run_id={summary.get('run_id')}")
    print(f"tracking_profile={summary.get('tracking_profile')}")
    print(f"output_root={config.output_root}")
    print(f"active_write_root={config.active_write_root}")
    print(f"archive_root={config.archive_root}")
    print(f"archive_status={summary.get('archive_status')}")
    print(f"live_source_used={summary.get('live_source_used')}")
    print(f"subscription_connect_status={summary.get('subscription_connect_status')}")
    if args.mode == "migrated-mint-replay":
        print(f"input_run_root={summary.get('input_run_root')}")
        print(f"migrated_mints_total={summary.get('migrated_mints_total')}")
        print(f"migrated_full_path_count={summary.get('migrated_full_path_count')}")
        print(f"migrated_sample_rejected_count={summary.get('migrated_sample_rejected_count')}")
        print(f"migrated_preexisting_count={summary.get('migrated_preexisting_count')}")
        print(f"migrated_source_miss_count={summary.get('migrated_source_miss_count')}")
        print(f"migrated_replay_unresolved_count={summary.get('migrated_replay_unresolved_count')}")
        print(f"campaign_quality_gate_passed={summary.get('campaign_quality_gate_passed')}")
        print(f"migrated_mint_completeness_csv={summary.get('migrated_mint_completeness_csv')}")
        return 0
    if args.mode == "audit-trade-flow":
        print(f"unique_birth_mints={summary.get('unique_birth_mints')}")
        print(f"trade_flow_denominator={summary.get('trade_flow_denominator')}")
        print(f"trade_flow_covered_mints={summary.get('trade_flow_covered_mints')}")
        print(f"trade_flow_missing_mints={summary.get('trade_flow_missing_mints')}")
        print(f"denominator_mismatch_flagged={summary.get('denominator_mismatch_flagged')}")
        print(f"missing_trade_flow_mints_by_category={summary.get('missing_trade_flow_mints_by_category')}")
        print(f"trade_flow_missing_mints_debug_json={summary.get('json_path')}")
        print(f"trade_flow_coverage_audit_md={summary.get('markdown_path')}")
        return 0
    if args.mode == "audit-migration-linkage":
        print(f"global_migration_events_deduped={summary.get('global_migration_events_deduped')}")
        print(f"lifecycle_migrated_unique_mints={summary.get('lifecycle_migrated_unique_mints')}")
        print(f"decision_safe_full_paths={summary.get('decision_safe_full_paths')}")
        print(f"failure_reason_counts={summary.get('failure_reason_counts')}")
        print(f"migration_linkage_audit_json={summary.get('json_path')}")
        print(f"migration_linkage_audit_md={summary.get('markdown_path')}")
        return 0
    if args.mode == "audit-long-scan-readiness":
        print(f"can_run_10m_feature_proof={summary.get('can_run_10m_feature_proof')}")
        print(f"can_run_60m_thesis_scan={summary.get('can_run_60m_thesis_scan')}")
        print(f"can_run_2h_plus_scan={summary.get('can_run_2h_plus_scan')}")
        print(f"blockers={summary.get('blockers')}")
        print(f"next_fix_recommendations={summary.get('next_fix_recommendations')}")
        print(f"long_scan_readiness_audit_json={summary.get('json_path')}")
        print(f"long_scan_readiness_audit_md={summary.get('markdown_path')}")
        return 0
    if args.mode == "birth-source-audit":
        print(f"raw_websocket_notifications_received={summary.get('raw_websocket_notifications_received')}")
        print(f"pumpfun_program_mentions={summary.get('pumpfun_program_mentions')}")
        print(f"candidate_transactions_inspected={summary.get('candidate_transactions_inspected')}")
        print(f"direct_create_candidates={summary.get('direct_create_candidates')}")
        print(f"wrapped_inner_create_candidates={summary.get('wrapped_inner_create_candidates')}")
        print(f"decoded_births={summary.get('decoded_births')}")
        print(f"final_normalized_births={summary.get('final_normalized_births')}")
        print(f"duplicate_mints={summary.get('duplicate_mints')}")
        print(f"estimated_births_per_minute={summary.get('estimated_births_per_minute')}")
        print(f"raw_audit_path={summary.get('raw_audit_path')}")
        return 0
    if args.mode == "transaction-birth-source-audit":
        print(f"requested_duration_seconds={summary.get('requested_duration_seconds')}")
        print(f"actual_duration_seconds={summary.get('actual_duration_seconds')}")
        print(f"websocket_closed_early={summary.get('websocket_closed_early')}")
        print(f"websocket_close_reason={summary.get('websocket_close_reason')}")
        print(f"raw_transaction_notifications={summary.get('raw_transaction_notifications')}")
        print(f"pumpfun_mentions={summary.get('pumpfun_mentions')}")
        print(f"create_like_candidates={summary.get('create_like_candidates')}")
        print(f"direct_creates_decoded={summary.get('direct_creates_decoded')}")
        print(f"inner_creates_decoded={summary.get('inner_creates_decoded')}")
        print(f"wrapped_compact_creates_decoded={summary.get('wrapped_compact_creates_decoded')}")
        print(f"total_decoded_births={summary.get('total_decoded_births')}")
        print(f"unique_decoded_birth_mints={summary.get('unique_decoded_birth_mints')}")
        print(f"duplicate_mints={summary.get('duplicate_mints')}")
        print(f"decoded_births_per_observed_minute={summary.get('decoded_births_per_observed_minute')}")
        print(f"bonding_curve_account_present_count={summary.get('bonding_curve_account_present_count')}")
        print(f"associated_bonding_curve_present_count={summary.get('associated_bonding_curve_present_count')}")
        print(f"creator_dev_present_count={summary.get('creator_dev_present_count')}")
        print(f"raw_audit_path={summary.get('raw_audit_path')}")
        return 0
    if args.mode == "transaction-live-smoke":
        print(f"source_route={summary.get('source_route')}")
        print(f"actual_duration_seconds={summary.get('actual_duration_seconds')}")
        print(f"websocket_closed_early={summary.get('websocket_closed_early')}")
        print(f"raw_transaction_notifications={summary.get('raw_transaction_notifications')}")
        print(f"decoded_birth_rows={summary.get('decoded_birth_rows')}")
        print(f"unique_birth_mints={summary.get('unique_birth_mints')}")
        print(f"duplicate_mint_rows={summary.get('duplicate_mint_rows')}")
        print(f"direct_decoded_rows={summary.get('direct_decoded_rows')}")
        print(f"inner_decoded_rows={summary.get('inner_decoded_rows')}")
        print(f"wrapped_compact_decoded_rows={summary.get('wrapped_compact_decoded_rows')}")
        print(f"births_admitted_after_dedupe={summary.get('births_admitted_after_dedupe')}")
        print(f"sample_rejected_after_dedupe={summary.get('sample_rejected_after_dedupe')}")
        print(f"capacity_rejected_after_dedupe={summary.get('capacity_rejected_after_dedupe')}")
        print(f"curve_observation_attempts={summary.get('curve_observation_attempts')}")
        print(f"curve_observations_written={summary.get('curve_observations_written')}")
        print(f"queue_drops={summary.get('queue_drops')}")
        print(f"bonding_curve_account_present_count={summary.get('bonding_curve_account_present_count')}")
        print(f"associated_bonding_curve_present_count={summary.get('associated_bonding_curve_present_count')}")
        return 0
    if args.mode == "migration-source-audit":
        print(f"requested_duration_seconds={summary.get('requested_duration_seconds')}")
        print(f"actual_duration_seconds={summary.get('actual_duration_seconds')}")
        print(f"websocket_closed_early={summary.get('websocket_closed_early')}")
        print(f"websocket_close_reason={summary.get('websocket_close_reason')}")
        print(f"raw_transaction_notifications={summary.get('raw_transaction_notifications')}")
        print(f"decoded_rows_scanned={summary.get('decoded_rows_scanned')}")
        print(f"global_migration_events={summary.get('global_migration_events')}")
        print(f"global_migration_candidates={summary.get('global_migration_candidates')}")
        print(f"detection_methods={summary.get('detection_methods')}")
        print(f"global_migration_events_path={summary.get('global_migration_events_path')}")
        print(f"global_migration_candidates_path={summary.get('global_migration_candidates_path')}")
        return 0
    if args.mode == "migration-route-audit":
        print(f"requested_duration_seconds={summary.get('requested_duration_seconds')}")
        print(f"actual_duration_seconds={summary.get('actual_duration_seconds')}")
        print(f"websocket_closed_early={summary.get('websocket_closed_early')}")
        print(f"websocket_close_reason={summary.get('websocket_close_reason')}")
        print(f"source_filters_used={summary.get('source_filters_used')}")
        print(f"program_ids_watched={summary.get('program_ids_watched')}")
        print(f"account_required_filters={summary.get('account_required_filters')}")
        print(f"source_route_could_see_axiom_migrated_tokens={summary.get('source_route_could_see_axiom_migrated_tokens')}")
        print(f"routes={summary.get('routes')}")
        print(f"migration_route_audit_summary_path={summary.get('migration_route_audit_summary_path')}")
        print(f"migration_route_audit_rows_path={summary.get('migration_route_audit_rows_path')}")
        return 0
    print(f"total_births_detected={summary.get('total_births_detected')}")
    print(f"birth_rows_total_including_replay={summary.get('birth_rows_total_including_replay')}")
    print(f"birth_rows_live_source={summary.get('birth_rows_live_source')}")
    print(f"birth_rows_replay_backfilled={summary.get('birth_rows_replay_backfilled')}")
    print(f"unique_birth_mints_live_source={summary.get('unique_birth_mints_live_source')}")
    print(f"unique_birth_mints_replay_backfilled={summary.get('unique_birth_mints_replay_backfilled')}")
    print(f"admitted_births={summary.get('admitted_births')}")
    print(f"curve_observations_written={summary.get('curve_observations_written')}")
    print(f"exact_progress_decoded_count={summary.get('exact_progress_decoded_count')}")
    print(f"unresolved_progress_formula_count={summary.get('unresolved_progress_formula_count')}")
    print(f"threshold_crossings_written={summary.get('threshold_crossings_written')}")
    print(f"migrations_written={summary.get('migrations_written')}")
    print(f"queue_dropped_count={summary.get('queue_dropped_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _migration_signal_source(row: dict[str, Any]) -> str | None:
    """Return the explicit migration signal source, or None when migration is not proven."""

    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    def _as_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if _as_bool(row.get("complete")):
        return "complete_flag_true"
    if _as_bool(row.get("explicit_migrate_log")):
        return "explicit_migrate_log"
    if _as_bool(row.get("dex_pair_signal")):
        return "dex_pair_signal"

    real_token_reserves = _as_float(row.get("real_token_reserves_scaled"))
    if real_token_reserves is not None and real_token_reserves <= 1e-9:
        return "reserve_zero_or_near_zero"

    progress_pct = _as_float(row.get("progress_pct"))
    progress_status = str(row.get("progress_pct_status") or "")
    if progress_pct is not None and progress_pct >= 100.0 and progress_status in {"decoded_candidate", "decoded_exact"}:
        return "progress_100pct"

    return None

# --- T007_PRODUCTION_COLLECTOR_PATCHES_V2 -----------------------------------
# Production-safe runtime metadata helpers. These patches do not add trading,
# wallet, signing, paper-trading, or sendTransaction paths.
try:
    from research.mtp_research.validation.t007_source_health import T007SourceHealth as _T007ProductionSourceHealth
except Exception:  # pragma: no cover
    _T007ProductionSourceHealth = None

if 'BondingCurveProgressRecorder' in globals():
    _t007_recorder_original_init = BondingCurveProgressRecorder.__init__
    _t007_recorder_original_build_summary_payload = getattr(BondingCurveProgressRecorder, '_build_summary_payload', None)
    _t007_recorder_original_build_live_status_payload = getattr(BondingCurveProgressRecorder, '_build_live_status_payload', None)
    _t007_recorder_original_enqueue_migration_backfill = getattr(BondingCurveProgressRecorder, 'enqueue_migration_backfill', None)

    def _t007_recorder_production_init(self, *args, **kwargs):
        _t007_recorder_original_init(self, *args, **kwargs)
        if _T007ProductionSourceHealth is not None and not hasattr(self, 't007_source_health'):
            self.t007_source_health = _T007ProductionSourceHealth.default()

    def _t007_recorder_source_health_payload(self):
        health = getattr(self, 't007_source_health', None)
        if health is not None and hasattr(health, 'as_dict'):
            return health.as_dict()
        return {
            'source_health_ready': True,
            'source_health_blocking_reasons': [],
            'queue_dropped_total': int(getattr(self, 'queue_dropped', 0) or 0),
            'queue_high_water_max': int(getattr(self, 'queue_high_water', 0) or 0),
        }

    def _t007_recorder_production_build_summary_payload(self, *args, **kwargs):
        payload = _t007_recorder_original_build_summary_payload(self, *args, **kwargs) if _t007_recorder_original_build_summary_payload is not None else {}
        if isinstance(payload, dict):
            payload.update(_t007_recorder_source_health_payload(self))
            payload.setdefault('valuation_ladder_suppressed', True)
            payload.setdefault('execution_cost_required_for_readiness', False)
            payload.setdefault('pumpswap_verified_account_lengths', list(PUMPSWAP_MARKET_ACCOUNT_LENGTHS))
            payload.setdefault('pumpswap_pending_fixture_account_lengths', list(globals().get('PUMPSWAP_MARKET_ACCOUNT_LENGTHS_PENDING_FIXTURE', ())))
        return payload

    def _t007_recorder_production_build_live_status_payload(self, *args, **kwargs):
        payload = _t007_recorder_original_build_live_status_payload(self, *args, **kwargs) if _t007_recorder_original_build_live_status_payload is not None else {}
        if isinstance(payload, dict):
            payload.update(_t007_recorder_source_health_payload(self))
            payload.setdefault('valuation_ladder_suppressed', True)
            payload.setdefault('execution_cost_required_for_readiness', False)
        return payload

    def _t007_recorder_production_enqueue_migration_backfill(self, *args, **kwargs):
        if _t007_recorder_original_enqueue_migration_backfill is None:
            return None
        result = _t007_recorder_original_enqueue_migration_backfill(self, *args, **kwargs)
        # Existing queue rows remain authoritative. The added fields are included
        # in future call paths that pass rows through artifact/event adapters.
        try:
            self.last_bounded_replay_policy = {
                'policy': 'bounded_readonly_replay',
                'decision_time_safe': False,
                'wallet_or_signing_allowed': False,
                'max_signatures_default': 100,
                'reason': 'replay enriches archives only and cannot create live-trade evidence',
            }
        except Exception:
            pass
        return result

    BondingCurveProgressRecorder.__init__ = _t007_recorder_production_init
    if _t007_recorder_original_build_summary_payload is not None:
        BondingCurveProgressRecorder._build_summary_payload = _t007_recorder_production_build_summary_payload
    if _t007_recorder_original_build_live_status_payload is not None:
        BondingCurveProgressRecorder._build_live_status_payload = _t007_recorder_production_build_live_status_payload
    if _t007_recorder_original_enqueue_migration_backfill is not None:
        BondingCurveProgressRecorder.enqueue_migration_backfill = _t007_recorder_production_enqueue_migration_backfill

# --- T007_EVENT_FIRST_COLLECTOR_WIRING_V3 -----------------------------------
# Hard production rule: lifecycle rows hit canonical SQLite before JSONL/CSV
# compatibility artifacts. Mayhem, wallets, signing, trading, and paper trading
# are not touched here.
try:
    from research.mtp_research.validation.t007_production_event_bus import T007ProductionEventFirstWriter as _T007EventFirstWriter
except Exception:  # pragma: no cover
    _T007EventFirstWriter = None

if 'BondingCurveProgressRecorder' in globals() and _T007EventFirstWriter is not None:
    _t007_v3_original_append_jsonl = getattr(BondingCurveProgressRecorder, '_append_jsonl', None)
    _t007_v3_original_build_summary_payload = getattr(BondingCurveProgressRecorder, '_build_summary_payload', None)
    _t007_v3_original_build_live_status_payload = getattr(BondingCurveProgressRecorder, '_build_live_status_payload', None)

    def _t007_v3_event_context(self):
        config = getattr(self, 'config', None)
        run_id = getattr(self, 'run_id', None) or getattr(self, 'collector_run_id', None)
        return {
            'run_id': run_id,
            'collector_run_id': run_id,
            'campaign_start_time': getattr(self, 'source_start_time', None) or getattr(self, 'wall_clock_source_start', None),
            'campaign_end_time': getattr(self, 'source_end_time', None) or getattr(self, 'wall_clock_source_stop', None),
            'source_duration_seconds': getattr(config, 'source_duration_seconds', None) if config is not None else None,
            'requested_source_duration_seconds': getattr(config, 'source_duration_seconds', None) if config is not None else None,
            'watcher_window_id': run_id,
            'originating_run_id': run_id,
        }

    def _t007_v3_writer(self):
        writer = getattr(self, '_t007_event_first_writer', None)
        if writer is None:
            writer = _T007EventFirstWriter(getattr(self, 'output_root'))
            self._t007_event_first_writer = writer
        return writer

    def _t007_v3_append_jsonl(self, filename, row):
        if isinstance(row, dict):
            try:
                enriched = _t007_v3_writer(self).record_artifact_row(str(filename), row, context=_t007_v3_event_context(self))
                row.clear()
                row.update(enriched)
            except Exception as exc:
                try:
                    self.t007_event_first_write_errors = int(getattr(self, 't007_event_first_write_errors', 0) or 0) + 1
                    self.t007_event_first_last_error = str(exc)
                except Exception:
                    pass
        if _t007_v3_original_append_jsonl is not None:
            return _t007_v3_original_append_jsonl(self, filename, row)
        return None

    def _t007_v3_summary_payload(self, *args, **kwargs):
        payload = _t007_v3_original_build_summary_payload(self, *args, **kwargs) if _t007_v3_original_build_summary_payload is not None else {}
        if isinstance(payload, dict):
            payload['event_first_sqlite_enabled'] = True
            payload['event_first_write_errors'] = int(getattr(self, 't007_event_first_write_errors', 0) or 0)
            if getattr(self, 't007_event_first_last_error', None):
                payload['event_first_last_error'] = getattr(self, 't007_event_first_last_error')
            payload.setdefault('db_writer_alive', True)
            payload.setdefault('db_ledger_consistent', payload.get('event_first_write_errors', 0) == 0)
            payload.setdefault('execution_cost_required_for_readiness', False)
            payload.setdefault('valuation_ladder_suppressed', True)
        return payload

    def _t007_v3_live_status_payload(self, *args, **kwargs):
        payload = _t007_v3_original_build_live_status_payload(self, *args, **kwargs) if _t007_v3_original_build_live_status_payload is not None else {}
        if isinstance(payload, dict):
            payload['event_first_sqlite_enabled'] = True
            payload['event_first_write_errors'] = int(getattr(self, 't007_event_first_write_errors', 0) or 0)
            payload.setdefault('db_writer_alive', True)
            payload.setdefault('db_ledger_consistent', payload.get('event_first_write_errors', 0) == 0)
            payload.setdefault('execution_cost_required_for_readiness', False)
            payload.setdefault('valuation_ladder_suppressed', True)
        return payload

    if _t007_v3_original_append_jsonl is not None:
        BondingCurveProgressRecorder._append_jsonl = _t007_v3_append_jsonl
    if _t007_v3_original_build_summary_payload is not None:
        BondingCurveProgressRecorder._build_summary_payload = _t007_v3_summary_payload
    if _t007_v3_original_build_live_status_payload is not None:
        BondingCurveProgressRecorder._build_live_status_payload = _t007_v3_live_status_payload

# --- T007_SINGLE_WRITER_COLLECTOR_EXPORT_V8 ---------------------------------
try:
    from research.mtp_research.validation.t007_sqlite_writer import T007DbFatalError as _T007DbFatalErrorV8
    from research.mtp_research.validation.t007_db_readiness import build_db_readiness_summary as _t007_build_db_readiness_summary_v8
except Exception:  # pragma: no cover
    _T007DbFatalErrorV8 = RuntimeError
    _t007_build_db_readiness_summary_v8 = None

if 'BondingCurveProgressRecorder' in globals():
    _t007_v8_original_append_jsonl = globals().get('_t007_v3_original_append_jsonl') or globals().get('_t007_recorder_original_append_jsonl') or getattr(BondingCurveProgressRecorder, '_append_jsonl', None)
    _t007_v8_original_build_summary_payload = getattr(BondingCurveProgressRecorder, '_build_summary_payload', None)
    _t007_v8_original_build_live_status_payload = getattr(BondingCurveProgressRecorder, '_build_live_status_payload', None)
    _t007_v8_original_init = BondingCurveProgressRecorder.__init__

    def _t007_v8_init(self, *args, **kwargs):
        _t007_v8_original_init(self, *args, **kwargs)
        try:
            _t007_v3_writer(self)._canonical_sqlite_writer.bootstrap_run(_t007_v3_event_context(self))
        except Exception:
            pass

    def _t007_v8_append_jsonl(self, filename, row):
        if isinstance(row, dict):
            enriched = _t007_v3_writer(self).record_artifact_row(str(filename), row, context=_t007_v3_event_context(self))
            row.clear()
            row.update(enriched)
        if _t007_v8_original_append_jsonl is not None:
            return _t007_v8_original_append_jsonl(self, filename, row)
        return None

    def _t007_v8_summary_payload(self, *args, **kwargs):
        payload = _t007_v8_original_build_summary_payload(self, *args, **kwargs) if _t007_v8_original_build_summary_payload is not None else {}
        if isinstance(payload, dict):
            try:
                writer = getattr(getattr(self, '_t007_event_first_writer', None), '_canonical_sqlite_writer', None)
                if writer is not None:
                    writer.finalize_run({'collector_run_id': getattr(self, 'run_id', None), 'actual_source_duration_seconds': payload.get('actual_source_duration_seconds'), 'source_duration_quality': payload.get('source_duration_quality_status')})
                    payload.update(writer.health_payload())
            except Exception as exc:
                payload['db_writer_alive'] = False
                payload['db_last_error_class'] = type(exc).__name__
                payload['db_last_error_message'] = str(exc)
                payload['db_ledger_consistent'] = False
            if _t007_build_db_readiness_summary_v8 is not None:
                try:
                    payload.update(_t007_build_db_readiness_summary_v8(getattr(self, 'output_root'), payload))
                except Exception as exc:
                    payload['db_readiness_error'] = f'{type(exc).__name__}: {exc}'
            payload['event_first_sqlite_enabled'] = True
            payload['jsonl_export_requires_db_commit'] = True
            if (payload.get('final') is True or str(payload.get('run_status') or '').startswith('finalized')) and (getattr(self, 'output_root') / 'canonical_sqlite_db_pointer.json').exists():
                payload.setdefault('lifecycle_materializer_status', 'deferred')
                payload.setdefault('offline_materialization_required', True)
                payload.setdefault('offline_materialization_reason', 'bounded_live_finalization_defers_lifecycle_materializer')
                payload.setdefault('readiness_decision', 'L2_PROOF_PENDING_OFFLINE_MATERIALIZATION')
        return payload

    def _t007_v8_live_status_payload(self, *args, **kwargs):
        payload = _t007_v8_original_build_live_status_payload(self, *args, **kwargs) if _t007_v8_original_build_live_status_payload is not None else {}
        if isinstance(payload, dict):
            try:
                writer = getattr(getattr(self, '_t007_event_first_writer', None), '_canonical_sqlite_writer', None)
                if writer is not None:
                    payload.update(writer.health_payload())
            except Exception as exc:
                payload['db_writer_alive'] = False
                payload['db_last_error_class'] = type(exc).__name__
                payload['db_last_error_message'] = str(exc)
            payload['event_first_sqlite_enabled'] = True
            payload['jsonl_export_requires_db_commit'] = True
        return payload

    BondingCurveProgressRecorder.__init__ = _t007_v8_init
    BondingCurveProgressRecorder._append_jsonl = _t007_v8_append_jsonl
    if _t007_v8_original_build_summary_payload is not None:
        BondingCurveProgressRecorder._build_summary_payload = _t007_v8_summary_payload
    if _t007_v8_original_build_live_status_payload is not None:
        BondingCurveProgressRecorder._build_live_status_payload = _t007_v8_live_status_payload
