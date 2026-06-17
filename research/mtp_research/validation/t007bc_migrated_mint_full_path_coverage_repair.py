from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_ARCHIVE_ROOT = Path(
    "/Volumes/ORICO/MemeTraderPro/data/forward/bonding_curve_progress_recorder_v1/"
    "t007bb_2h_thesis_collection_20260614_192608"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/Users/dianeposs/Projects/meme-trader-pro/outputs/theses/"
    "t007bc_migrated_mint_full_path_coverage_repair/t007bb_2h_reanalysis"
)

T007BC_GUARDRAILS: dict[str, bool] = {
    "live_scan_ran": False,
    "mayhem_files_modified": False,
    "valuation_ladder_suppressed": True,
    "trading_enabled": False,
    "paper_trading_enabled": False,
    "wallet_signing_execution_modified": False,
    "private_key_paths_modified": False,
}

T007BC_COVERAGE_STATUSES = {
    "full_path",
    "near_full_missing_execution_cost",
    "migration_plus_depth_only",
    "birth_seen_sample_rejected",
    "birth_seen_not_admitted",
    "birth_seen_admitted_missing_curve",
    "birth_seen_admitted_missing_trade_flow",
    "birth_seen_admitted_missing_migration_link",
    "migration_only_source_miss",
    "backfill_possible",
    "backfill_not_possible",
    "unknown",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)


def _mint_of(row: Mapping[str, Any]) -> str:
    for key in ("mint", "base_mint", "token_mint", "created_mint"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _pool_of(row: Mapping[str, Any]) -> str:
    for key in ("pool_or_pair_address", "pool_address", "pair_address", "pool"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _signature_of(row: Mapping[str, Any]) -> str:
    for key in ("signature", "migration_signature", "transaction_signature"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _event_time(row: Mapping[str, Any]) -> float | None:
    for key in (
        "decision_time",
        "feature_observed_at",
        "received_at",
        "migration_received_at",
        "crossing_received_at",
        "collector_observed_at",
        "block_time",
        "created_at",
        "timestamp",
    ):
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _first_time(rows: Iterable[Mapping[str, Any]]) -> float | None:
    times = [_event_time(row) for row in rows]
    times = [value for value in times if value is not None]
    return min(times) if times else None


def _group_by_mint(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        mint = _mint_of(row)
        if not mint:
            continue
        grouped.setdefault(mint, []).append(dict(row))
    return grouped


def _progress_value(row: Mapping[str, Any]) -> float | None:
    for key in ("computed_progress_pct", "progress_pct", "candidate_progress_pct", "highest_progress_pct", "last_progress_pct"):
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _highest_progress(rows: Iterable[Mapping[str, Any]]) -> float | None:
    values = [_progress_value(row) for row in rows]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _sample_rejected(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        reason = str(row.get("admission_reason") or row.get("rejection_reason") or "")
        if "sample_rejected" in reason or _boolish(row.get("sample_rejected")):
            return True
        if _boolish(row.get("admitted")) is False and "sample" in reason:
            return True
    return False


def _active_pruned(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        reason = str(row.get("active_pruned_reason") or row.get("prune_reason") or row.get("stop_reason") or "")
        if reason and reason.lower() not in {"none", "not_pruned"}:
            return True
        if _boolish(row.get("active_pruned")):
            return True
    return False


def join_latest_prior_execution_cost(event_timestamp: Any, execution_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Join a global execution-cost row without ever using future data."""

    event_time = _float_or_none(event_timestamp)
    if event_time is None:
        return {
            "status": "not_available",
            "event_timestamp": None,
            "joined_decision_time": None,
            "source_observation_reason": None,
            "execution_cost_status": None,
            "decision_time_safe": True,
        }
    best: Mapping[str, Any] | None = None
    best_time: float | None = None
    for row in execution_rows:
        row_time = _event_time(row)
        if row_time is None or row_time > event_time:
            continue
        if best_time is None or row_time > best_time:
            best = row
            best_time = row_time
    if best is None or best_time is None:
        return {
            "status": "not_available",
            "event_timestamp": event_time,
            "joined_decision_time": None,
            "source_observation_reason": None,
            "execution_cost_status": None,
            "decision_time_safe": True,
        }
    return {
        "status": "joined",
        "event_timestamp": event_time,
        "joined_decision_time": best_time,
        "source_observation_reason": best.get("observation_reason"),
        "execution_cost_status": best.get("execution_cost_status"),
        "decision_time_safe": best_time <= event_time,
    }


def _has_depth(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        for key in (
            "base_reserve_raw",
            "quote_reserve_raw",
            "pool_base_reserve",
            "pool_quote_reserve",
            "pool_liquidity_quote",
            "pool_liquidity_usd",
        ):
            if row.get(key) not in (None, ""):
                return True
    return bool(rows)


def _has_quote(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        for key in ("price_impact_pct", "expected_output_quote", "effective_exit_price_quote_per_token"):
            if row.get(key) not in (None, ""):
                return True
    return bool(rows)


def _first_missing_link(
    *,
    birth_seen: bool,
    admitted: bool,
    sample_rejected: bool,
    active_pruned: bool,
    curve_count: int,
    threshold_count: int,
    velocity_count: int,
    trade_flow_count: int,
    holder_dev_count: int,
    migration_linked: bool,
    post_count: int,
    quote_count: int,
    swap_count: int,
    execution_cost_joined: bool,
) -> str:
    if not birth_seen:
        return "birth_source_miss"
    if sample_rejected:
        return "sample_rejected"
    if not admitted:
        return "birth_seen_not_admitted"
    if active_pruned:
        return "admitted_but_pruned"
    if curve_count <= 0:
        return "curve_observation_missing"
    if threshold_count <= 0:
        return "threshold_not_crossed"
    if velocity_count <= 0:
        return "velocity_not_linked"
    if trade_flow_count <= 0:
        return "trade_flow_not_linked"
    if holder_dev_count <= 0:
        return "holder_dev_not_linked"
    if not migration_linked:
        return "migration_link_missing"
    if post_count <= 0:
        return "post_migration_observation_missing"
    if quote_count <= 0:
        return "executable_quote_missing"
    if swap_count <= 0:
        return "pumpswap_swap_event_missing"
    if not execution_cost_joined:
        return "execution_cost_join_missing"
    return "none"


def _classify_status(
    *,
    birth_seen: bool,
    admitted: bool,
    sample_rejected: bool,
    active_pruned: bool,
    curve_count: int,
    threshold_count: int,
    velocity_count: int,
    trade_flow_count: int,
    holder_dev_count: int,
    migration_linked: bool,
    post_count: int,
    quote_count: int,
    swap_count: int,
    execution_cost_joined: bool,
    backfill_feasible: bool,
) -> str:
    if (
        birth_seen
        and admitted
        and curve_count > 0
        and threshold_count > 0
        and velocity_count > 0
        and trade_flow_count > 0
        and holder_dev_count > 0
        and migration_linked
        and post_count > 0
        and quote_count > 0
        and swap_count > 0
        and execution_cost_joined
    ):
        return "full_path"
    if (
        birth_seen
        and admitted
        and curve_count > 0
        and threshold_count > 0
        and velocity_count > 0
        and trade_flow_count > 0
        and holder_dev_count > 0
        and migration_linked
        and post_count > 0
        and quote_count > 0
        and swap_count > 0
        and not execution_cost_joined
    ):
        return "near_full_missing_execution_cost"
    if not birth_seen:
        return "migration_only_source_miss" if not backfill_feasible else "backfill_possible"
    if post_count > 0 and quote_count > 0 and not (birth_seen and admitted and curve_count > 0):
        return "migration_plus_depth_only"
    if birth_seen and sample_rejected:
        return "birth_seen_sample_rejected"
    if birth_seen and not admitted:
        return "birth_seen_not_admitted"
    if birth_seen and admitted and active_pruned:
        return "birth_seen_admitted_missing_curve"
    if birth_seen and admitted and curve_count <= 0:
        return "birth_seen_admitted_missing_curve"
    if birth_seen and admitted and trade_flow_count <= 0:
        return "birth_seen_admitted_missing_trade_flow"
    if birth_seen and admitted and not migration_linked:
        return "birth_seen_admitted_missing_migration_link"
    return "unknown"


def _pre_migration_failure_cause(
    *,
    status: str,
    birth_seen: bool,
    admitted: bool,
    sample_rejected: bool,
    active_pruned: bool,
    curve_count: int,
    threshold_count: int,
    trade_flow_count: int,
    migration_linked: bool,
) -> str:
    if sample_rejected or status == "birth_seen_sample_rejected":
        return "sample_rejected"
    if not birth_seen:
        return "birth_source_miss"
    if birth_seen and not admitted:
        return "birth_seen_not_admitted"
    if active_pruned:
        return "admitted_but_pruned"
    if curve_count <= 0:
        return "curve_observation_missing"
    if threshold_count <= 0:
        return "threshold_not_crossed"
    if trade_flow_count <= 0:
        return "trade_flow_not_linked"
    if not migration_linked:
        return "migration_link_missing"
    if status in {"full_path", "near_full_missing_execution_cost", "migration_plus_depth_only"}:
        return "none"
    return "unknown"


def _backfill_methods(mint: str, migration: Mapping[str, Any], birth_rows: list[dict[str, Any]]) -> list[str]:
    methods = [f"getSignaturesForAddress:mint:{mint}"]
    pool = _pool_of(migration)
    if pool:
        methods.append(f"getSignaturesForAddress:pool:{pool}")
    signature = _signature_of(migration)
    if signature:
        methods.append(f"getTransaction:migration_signature:{signature}")
    for row in birth_rows:
        sig = _signature_of(row)
        if sig:
            methods.append(f"getTransaction:birth_signature:{sig}")
    return methods


def _backfill_feasibility(mint: str, migration: Mapping[str, Any], birth_rows: list[dict[str, Any]], curve_count: int) -> dict[str, Any]:
    methods = _backfill_methods(mint, migration, birth_rows)
    feasible = bool(methods)
    missing_targets = []
    if not birth_rows:
        missing_targets.append("birth_transaction")
    if curve_count <= 0:
        missing_targets.extend(["pumpfun_curve_trades_before_migration", "curve_reserve_progress_history", "threshold_crossings"])
    if not missing_targets:
        missing_targets.append("none")
    return {
        "mint": mint,
        "backfill_feasible": feasible,
        "backfill_status": "backfill_possible" if feasible else "backfill_not_possible",
        "allowed_methods": ";".join(methods),
        "missing_targets": ";".join(dict.fromkeys(missing_targets)),
        "disallowed_methods": "simulateTransaction;build_transactions;send_transactions;wallet;signing;private_key;trading;paper_trading",
    }


def _coverage_row_for_mint(
    mint: str,
    migration_rows: list[dict[str, Any]],
    grouped: dict[str, dict[str, list[dict[str, Any]]]],
    execution_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    migration = min(migration_rows, key=lambda row: _event_time(row) if _event_time(row) is not None else float("inf"))
    births = grouped["birth"].get(mint, [])
    curves = grouped["curve"].get(mint, [])
    thresholds = grouped["threshold"].get(mint, [])
    velocities = [*grouped["velocity"].get(mint, []), *grouped["acceleration"].get(mint, [])]
    trade_flows = [*grouped["trade_flow"].get(mint, []), *grouped["organic_flow"].get(mint, [])]
    holder_devs = [
        *grouped["holder"].get(mint, []),
        *grouped["dev"].get(mint, []),
    ]
    post = grouped["post"].get(mint, [])
    quotes = grouped["quote"].get(mint, [])
    swaps = grouped["swap"].get(mint, [])
    paths = grouped["path"].get(mint, [])
    birth_seen = bool(births)
    admitted = any(_boolish(row.get("admitted")) for row in births)
    sample_rejected = _sample_rejected(births)
    active_pruned = _active_pruned([*births, *paths])
    migration_linked = bool(birth_seen and migration_rows)
    backfill = _backfill_feasibility(mint, migration, births, len(curves))
    birth_time = _first_time(births)
    curve_time = _first_time(curves)
    threshold_time = _first_time(thresholds)
    migration_time = _event_time(migration)
    post_time = _first_time(post)
    quote_time = _first_time(quotes)
    execution_joins = {
        "birth": join_latest_prior_execution_cost(birth_time, execution_rows),
        "curve": join_latest_prior_execution_cost(curve_time, execution_rows),
        "threshold": join_latest_prior_execution_cost(threshold_time, execution_rows),
        "migration": join_latest_prior_execution_cost(migration_time, execution_rows),
        "post_migration": join_latest_prior_execution_cost(post_time, execution_rows),
        "quote": join_latest_prior_execution_cost(quote_time, execution_rows),
    }
    execution_cost_joined = any(join["status"] == "joined" for join in execution_joins.values())
    holder_dev_count = len(holder_devs)
    status = _classify_status(
        birth_seen=birth_seen,
        admitted=admitted,
        sample_rejected=sample_rejected,
        active_pruned=active_pruned,
        curve_count=len(curves),
        threshold_count=len(thresholds),
        velocity_count=len(velocities),
        trade_flow_count=len(trade_flows),
        holder_dev_count=holder_dev_count,
        migration_linked=migration_linked,
        post_count=len(post),
        quote_count=len(quotes),
        swap_count=len(swaps),
        execution_cost_joined=execution_cost_joined,
        backfill_feasible=bool(backfill["backfill_feasible"]),
    )
    first_missing = _first_missing_link(
        birth_seen=birth_seen,
        admitted=admitted,
        sample_rejected=sample_rejected,
        active_pruned=active_pruned,
        curve_count=len(curves),
        threshold_count=len(thresholds),
        velocity_count=len(velocities),
        trade_flow_count=len(trade_flows),
        holder_dev_count=holder_dev_count,
        migration_linked=migration_linked,
        post_count=len(post),
        quote_count=len(quotes),
        swap_count=len(swaps),
        execution_cost_joined=execution_cost_joined,
    )
    pre_failure = _pre_migration_failure_cause(
        status=status,
        birth_seen=birth_seen,
        admitted=admitted,
        sample_rejected=sample_rejected,
        active_pruned=active_pruned,
        curve_count=len(curves),
        threshold_count=len(thresholds),
        trade_flow_count=len(trade_flows),
        migration_linked=migration_linked,
    )
    highest_progress = _highest_progress([*curves, *paths, *migration_rows])
    row = {
        "mint": mint,
        "coverage_status": status,
        "full_path_ready": status == "full_path",
        "quote_asset": migration.get("quote_asset") or migration.get("quote_mint_symbol") or "",
        "pool_or_pair_address": _pool_of(migration),
        "migration_signature": _signature_of(migration),
        "global_migration_seen": True,
        "global_migration_event_rows": len(migration_rows),
        "birth_seen": birth_seen,
        "sample_rejected": sample_rejected,
        "admitted": admitted,
        "active_tracking_pruned_before_curve_or_migration": active_pruned,
        "curve_observations_count": len(curves),
        "highest_progress_pct": highest_progress,
        "threshold_crossings_count": len(thresholds),
        "velocity_acceleration_count": len(velocities),
        "trade_flow_count": len(trade_flows),
        "holder_dev_count": holder_dev_count,
        "migration_link_to_birth_or_admission": migration_linked,
        "post_migration_observations_count": len(post),
        "post_migration_depth_seen": _has_depth(post),
        "executable_quote_count": len(quotes),
        "executable_quote_seen": _has_quote(quotes),
        "pumpswap_swap_events_count": len(swaps),
        "execution_cost_context_join_exists": execution_cost_joined,
        "first_missing_link": first_missing,
        "pre_migration_failure_cause": pre_failure,
        "backfill_status": backfill["backfill_status"],
        "backfill_feasible": backfill["backfill_feasible"],
        "execution_cost_at_birth_status": execution_joins["birth"]["status"],
        "execution_cost_at_threshold_status": execution_joins["threshold"]["status"],
        "execution_cost_at_migration_status": execution_joins["migration"]["status"],
        "execution_cost_at_quote_status": execution_joins["quote"]["status"],
        "execution_cost_join_source": "latest_prior_global_execution_cost_observations.jsonl",
        "execution_cost_join_decision_time_safe": all(join["decision_time_safe"] for join in execution_joins.values()),
        "execution_cost_birth_join_time": execution_joins["birth"]["joined_decision_time"],
        "execution_cost_threshold_join_time": execution_joins["threshold"]["joined_decision_time"],
        "execution_cost_migration_join_time": execution_joins["migration"]["joined_decision_time"],
        "execution_cost_quote_join_time": execution_joins["quote"]["joined_decision_time"],
    }
    return row, backfill


def build_t007bc_full_path_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    migrated = int(summary.get("migrated_unique_mints") or 0)
    full = int(summary.get("strict_full_paths") or summary.get("full_path_migrated_mints") or 0)
    near = int(summary.get("near_full_migrated_mints") or 0)
    depth_only = int(summary.get("migration_plus_depth_only_mints") or 0)
    rates = {
        "migrated_birth_seen_rate": float(summary.get("migrated_birth_seen_rate") or 0.0),
        "migrated_admitted_rate": float(summary.get("migrated_admitted_rate") or 0.0),
        "migrated_curve_observation_rate": float(summary.get("migrated_curve_observation_rate") or 0.0),
        "migrated_trade_flow_rate": float(summary.get("migrated_trade_flow_rate") or 0.0),
        "migrated_post_migration_quote_rate": float(summary.get("migrated_post_migration_quote_rate") or 0.0),
        "migrated_execution_cost_join_rate": float(summary.get("migrated_execution_cost_join_rate") or 0.0),
    }
    thresholds = {
        "migrated_birth_seen_rate": 0.60,
        "migrated_admitted_rate": 0.40,
        "migrated_curve_observation_rate": 0.40,
        "migrated_trade_flow_rate": 0.40,
        "migrated_post_migration_quote_rate": 0.80,
        "migrated_execution_cost_join_rate": 0.80,
    }
    blocking: list[str] = []
    if full <= 0:
        blocking.append("full_path_migrated_mints_zero")
    for key, threshold in thresholds.items():
        if rates[key] < threshold:
            blocking.append(f"{key}_below_threshold")
    return {
        "gate_id": "T007BC_MIGRATED_MINT_FULL_PATH_COVERAGE_GATE",
        "migrated_unique_mints": migrated,
        "full_path_migrated_mints": full,
        "near_full_migrated_mints": near,
        "migration_plus_depth_only_mints": depth_only,
        **rates,
        "pass_thresholds": thresholds,
        "blocking_reasons": blocking,
        "full_birth_to_exit_thesis_allowed": False if blocking else True,
        "full_migrated_token_thesis_allowed": False if blocking else True,
        "post_migration_depth_only_analysis_allowed": depth_only > 0 or rates["migrated_post_migration_quote_rate"] > 0,
        "pre_migration_only_analysis_allowed": True,
        "pre_migration_only_denominator": "all_admitted_mints_not_migrated_only",
        "longer_full_path_collection_allowed": False if blocking else True,
        "edge_claim_allowed": False,
        "valuation_ladder_suppressed": True,
        "mayhem_files_modified": False,
        "trading_enabled": False,
        "paper_trading_enabled": False,
        "wallet_signing_execution_allowed": False,
    }


def _safe_rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _fieldnames(rows: list[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "mint",
        "coverage_status",
        "full_path_ready",
        "quote_asset",
        "pool_or_pair_address",
        "migration_signature",
        "global_migration_seen",
        "global_migration_event_rows",
        "birth_seen",
        "sample_rejected",
        "admitted",
        "active_tracking_pruned_before_curve_or_migration",
        "curve_observations_count",
        "highest_progress_pct",
        "threshold_crossings_count",
        "velocity_acceleration_count",
        "trade_flow_count",
        "holder_dev_count",
        "migration_link_to_birth_or_admission",
        "post_migration_observations_count",
        "post_migration_depth_seen",
        "executable_quote_count",
        "executable_quote_seen",
        "pumpswap_swap_events_count",
        "execution_cost_context_join_exists",
        "first_missing_link",
        "pre_migration_failure_cause",
        "backfill_status",
        "backfill_feasible",
        "execution_cost_at_birth_status",
        "execution_cost_at_threshold_status",
        "execution_cost_at_migration_status",
        "execution_cost_at_quote_status",
        "execution_cost_join_source",
        "execution_cost_join_decision_time_safe",
        "execution_cost_birth_join_time",
        "execution_cost_threshold_join_time",
        "execution_cost_migration_join_time",
        "execution_cost_quote_join_time",
    ]
    keys = sorted({key for row in rows for key in row})
    return preferred + [key for key in keys if key not in preferred]


def _summary_md(summary: Mapping[str, Any], gate: Mapping[str, Any]) -> str:
    buckets = summary.get("coverage_buckets") or {}
    first_missing = summary.get("first_missing_link_breakdown") or {}
    lines = [
        "# T007BC Migrated Mint Full Path Coverage Repair",
        "",
        "Offline reanalysis only. No live scan, no trading, no paper trading, no Mayhem changes, and no valuation ladder re-enable.",
        "",
        f"- Archive root: `{summary.get('archive_root')}`",
        f"- Migrated unique mints: `{summary.get('migrated_unique_mints')}`",
        f"- Raw global migration rows: `{summary.get('raw_global_migration_rows')}`",
        f"- Strict full paths: `{summary.get('strict_full_paths')}`",
        f"- Near-full migrated mints: `{summary.get('near_full_migrated_mints')}`",
        f"- Migration plus depth only: `{summary.get('migration_plus_depth_only_mints')}`",
        f"- Execution-cost join rate: `{summary.get('migrated_execution_cost_join_rate')}`",
        "",
        "## Coverage buckets",
        "",
        *[f"- {key}: `{value}`" for key, value in sorted(dict(buckets).items())],
        "",
        "## First missing link breakdown",
        "",
        *[f"- {key}: `{value}`" for key, value in sorted(dict(first_missing).items())],
        "",
        "## Gate",
        "",
        f"- Full birth-to-exit thesis allowed: `{gate.get('full_birth_to_exit_thesis_allowed')}`",
        f"- Full migrated-token thesis allowed: `{gate.get('full_migrated_token_thesis_allowed')}`",
        f"- Post-migration-depth-only analysis allowed: `{gate.get('post_migration_depth_only_analysis_allowed')}`",
        f"- Pre-migration-only analysis allowed: `{gate.get('pre_migration_only_analysis_allowed')}`",
        f"- Longer full-path collection allowed: `{gate.get('longer_full_path_collection_allowed')}`",
        f"- Blocking reasons: `{gate.get('blocking_reasons')}`",
    ]
    return "\n".join(lines) + "\n"


def _backfill_plan_md(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# T007BC Backfill Repair Plan",
            "",
            "Allowed read-only methods:",
            "",
            "- `getSignaturesForAddress` for mint, bonding curve account, creator, pool, and token vaults",
            "- `getTransaction` for known signatures",
            "- existing archived raw route notifications",
            "- existing global migration event signatures",
            "- existing birth audit signatures",
            "",
            "Not allowed:",
            "",
            "- `simulateTransaction` for trading",
            "- building or sending transactions",
            "- wallet, signing, private-key, trading, or paper-trading paths",
            "",
            "Recommended collector changes before a future full-path collection:",
            "",
            "1. Keep 70% dense tracking until capacity says otherwise.",
            "2. Keep 100% birth audit.",
            "3. Keep 100% global PumpSwap migration lane.",
            "4. Add cheap 100% thin pre-migration tracking for all births.",
            "5. Promote sampled-out mints when curve progress, velocity, buyer breadth, or migration importance appears.",
            "6. Add migration-triggered read-only backfill for sampled-out/source-missed mints.",
            "7. Persist event-time execution-cost joins in report artifacts.",
            "",
            f"Backfill possible mints: `{summary.get('backfill_possible_count')}`",
            f"Backfill not possible mints: `{summary.get('backfill_not_possible_count')}`",
        ]
    ) + "\n"


def analyze_t007bc_migrated_full_path_coverage(archive_root: Path | str, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    archive = Path(archive_root)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    collector_summary = _read_json(archive / "collector_summary.json")
    manifest = _read_json(archive / "campaign_manifest.json")
    migration_rows = _read_jsonl(archive / "global_migration_events.jsonl")
    migration_by_mint = _group_by_mint(migration_rows)
    grouped = {
        "birth": _group_by_mint(_read_jsonl(archive / "birth_audit.jsonl")),
        "curve": _group_by_mint(_read_jsonl(archive / "curve_observations.jsonl")),
        "threshold": _group_by_mint(_read_jsonl(archive / "true_curve_threshold_crossings.jsonl") or _read_jsonl(archive / "threshold_crossings.jsonl")),
        "velocity": _group_by_mint(_read_jsonl(archive / "curve_velocity_events.jsonl")),
        "acceleration": _group_by_mint(_read_jsonl(archive / "curve_acceleration_events.jsonl")),
        "trade_flow": _group_by_mint(_read_jsonl(archive / "trade_flow_events.jsonl")),
        "organic_flow": _group_by_mint(_read_jsonl(archive / "organic_flow_events.jsonl")),
        "holder": _group_by_mint(_read_jsonl(archive / "holder_distribution_snapshots.jsonl")),
        "dev": _group_by_mint(_read_jsonl(archive / "dev_behavior_events.jsonl")),
        "post": _group_by_mint(_read_jsonl(archive / "post_migration_observations.jsonl")),
        "quote": _group_by_mint(_read_jsonl(archive / "executable_quote_observations.jsonl")),
        "swap": _group_by_mint(_read_jsonl(archive / "pumpswap_swap_events.jsonl")),
        "path": _group_by_mint(_read_jsonl(archive / "token_path_summary.jsonl")),
    }
    execution_rows = _read_jsonl(archive / "execution_cost_observations.jsonl")
    coverage_rows: list[dict[str, Any]] = []
    backfill_rows: list[dict[str, Any]] = []
    for mint, rows in sorted(migration_by_mint.items()):
        coverage, backfill = _coverage_row_for_mint(mint, rows, grouped, execution_rows)
        coverage_rows.append(coverage)
        backfill_rows.append(backfill)
    total = len(coverage_rows)
    buckets = Counter(str(row.get("coverage_status") or "unknown") for row in coverage_rows)
    first_missing = Counter(str(row.get("first_missing_link") or "unknown") for row in coverage_rows)
    pre_failures = Counter(str(row.get("pre_migration_failure_cause") or "unknown") for row in coverage_rows)
    full_count = int(buckets.get("full_path", 0))
    near_full = int(buckets.get("near_full_missing_execution_cost", 0))
    depth_only = int(buckets.get("migration_plus_depth_only", 0))
    birth_seen = sum(1 for row in coverage_rows if row.get("birth_seen") is True)
    admitted = sum(1 for row in coverage_rows if row.get("admitted") is True)
    curve = sum(1 for row in coverage_rows if int(row.get("curve_observations_count") or 0) > 0)
    trade = sum(1 for row in coverage_rows if int(row.get("trade_flow_count") or 0) > 0)
    quote = sum(1 for row in coverage_rows if int(row.get("executable_quote_count") or 0) > 0)
    exec_join = sum(1 for row in coverage_rows if row.get("execution_cost_context_join_exists") is True)
    summary = {
        "task": "T007BC_Migrated_Mint_Full_Path_Coverage_Repair_NoScan",
        "archive_root": str(archive),
        "output_root": str(output),
        "collector_run_id": collector_summary.get("run_id") or manifest.get("run_id"),
        "generated_at_epoch": time.time(),
        "live_scan_run": False,
        "raw_global_migration_rows": len(migration_rows),
        "migrated_unique_mints": total,
        "strict_full_paths": full_count,
        "full_path_migrated_mints": full_count,
        "near_full_migrated_mints": near_full,
        "migration_plus_depth_only_mints": depth_only,
        "sampling_loss_count": int(pre_failures.get("sample_rejected", 0)),
        "source_miss_count": int(pre_failures.get("birth_source_miss", 0)),
        "join_mismatch_count": int(pre_failures.get("join_key_mismatch", 0)),
        "coverage_buckets": dict(sorted(buckets.items())),
        "first_missing_link_breakdown": dict(sorted(first_missing.items())),
        "pre_migration_failure_cause_breakdown": dict(sorted(pre_failures.items())),
        "migrated_birth_seen_rate": _safe_rate(birth_seen, total),
        "migrated_admitted_rate": _safe_rate(admitted, total),
        "migrated_curve_observation_rate": _safe_rate(curve, total),
        "migrated_trade_flow_rate": _safe_rate(trade, total),
        "migrated_post_migration_quote_rate": _safe_rate(quote, total),
        "migrated_execution_cost_join_rate": _safe_rate(exec_join, total),
        "birth_seen_mints": birth_seen,
        "admitted_mints": admitted,
        "curve_observation_mints": curve,
        "trade_flow_mints": trade,
        "post_migration_quote_mints": quote,
        "execution_cost_joined_mints": exec_join,
        "backfill_possible_count": sum(1 for row in backfill_rows if row.get("backfill_feasible") is True),
        "backfill_not_possible_count": sum(1 for row in backfill_rows if row.get("backfill_feasible") is not True),
        **T007BC_GUARDRAILS,
    }
    gate = build_t007bc_full_path_gate(summary)
    summary["readiness_gate"] = gate
    _write_csv(output / "migration_full_path_coverage_matrix.csv", coverage_rows, _fieldnames(coverage_rows))
    _write_json(output / "migration_full_path_coverage_summary.json", summary)
    (output / "migration_full_path_coverage_summary.md").write_text(_summary_md(summary, gate), encoding="utf-8")
    _write_csv(
        output / "backfill_feasibility_by_mint.csv",
        backfill_rows,
        ["mint", "backfill_feasible", "backfill_status", "allowed_methods", "missing_targets", "disallowed_methods"],
    )
    (output / "backfill_repair_plan.md").write_text(_backfill_plan_md(summary), encoding="utf-8")
    _write_json(output / "readiness_gate_after_t007bc.json", gate)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T007BC offline migrated-mint full-path coverage repair")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    summary = analyze_t007bc_migrated_full_path_coverage(Path(args.archive_root), Path(args.output_root))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
