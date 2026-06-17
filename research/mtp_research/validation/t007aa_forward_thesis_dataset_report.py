"""T007AA forward thesis dataset report scaffold.

This module summarizes one or more T007 campaign folders. It is analysis-only:
no trading, paper trading, wallet, signing, or execution behavior is touched.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from research.mtp_research.collectors.bonding_curve_progress_recorder_v1 import evaluate_t007_thesis_ready_gate


REPORT_FILENAMES = [
    "summary.md",
    "analysis_result.json",
    "curve_progress_threshold_outcomes.csv",
    "curve_velocity_outcomes.csv",
    "curve_acceleration_outcomes.csv",
    "trade_efficiency_outcomes.csv",
    "buyer_growth_outcomes.csv",
    "trade_flow_outcomes.csv",
    "bot_share_outcomes.csv",
    "holder_distribution_outcomes.csv",
    "dev_behavior_outcomes.csv",
    "migration_timing_outcomes.csv",
    "post_migration_outcomes.csv",
    "post_migration_exit_outcomes.csv",
    "executable_quote_outcomes.csv",
    "execution_cost_outcomes.csv",
    "execution_cost_quality.csv",
    "data_quality_report.csv",
]

ARTIFACT_MAP = {
    "curve_progress_threshold_outcomes.csv": "true_curve_threshold_crossings.jsonl",
    "curve_velocity_outcomes.csv": "curve_velocity_events.jsonl",
    "curve_acceleration_outcomes.csv": "curve_acceleration_events.jsonl",
    "trade_efficiency_outcomes.csv": "curve_velocity_events.jsonl",
    "buyer_growth_outcomes.csv": "trade_flow_events.jsonl",
    "trade_flow_outcomes.csv": "trade_flow_events.jsonl",
    "bot_share_outcomes.csv": "organic_flow_events.jsonl",
    "holder_distribution_outcomes.csv": "holder_distribution_snapshots.jsonl",
    "dev_behavior_outcomes.csv": "dev_behavior_events.jsonl",
    "migration_timing_outcomes.csv": "global_migration_events.jsonl",
    "post_migration_outcomes.csv": "post_migration_observations.jsonl",
    "post_migration_exit_outcomes.csv": "post_migration_observations.jsonl",
    "executable_quote_outcomes.csv": "executable_quote_observations.jsonl",
    "execution_cost_outcomes.csv": "execution_cost_observations.jsonl",
    "execution_cost_quality.csv": "execution_cost_observations.jsonl",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def jsonl_row_stats(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"valid_rows": 0, "corrupt_rows": 0}
    valid_rows = 0
    corrupt_rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
            valid_rows += 1
        except json.JSONDecodeError:
            corrupt_rows += 1
    return {"valid_rows": valid_rows, "corrupt_rows": corrupt_rows}


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for key, value in row.items():
            if key.endswith("_status") or key in {"status", "feature_status", "trade_flow_status", "execution_cost_status"}:
                label = f"{key}:{value}"
                counts[label] = counts.get(label, 0) + 1
    return counts


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        label = str(value if value not in (None, "") else "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _real_post_migration_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("mint") or row.get("pool_or_pair_address") or row.get("horizon_seconds_after_migration") is not None
    ]


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def classify_pool_state_error(row: dict[str, Any]) -> str:
    reason = str(row.get("pool_state_error_reason") or row.get("error_reason") or "").lower()
    status = str(row.get("pool_state_status") or "").lower()
    if "account_not_found" in reason or "fetch_failed" in reason:
        return "pool_account_fetch_failed"
    if "not_available" in reason or "not ready" in reason:
        return "pool_not_ready_yet"
    if "missing_pool" in reason or (status == "error" and not row.get("pool_or_pair_address")):
        return "wrong_pool_address"
    if "quote_mint_mismatch" in reason or "quote mismatch" in reason:
        return "quote_mint_mismatch"
    if "timeout" in reason or "429" in reason or "rpc" in reason:
        return "rpc_transient"
    if "unsupported" in reason:
        return "unsupported_pool_layout"
    if "decode" in reason or "exception" in reason:
        return "decode_exception"
    return "unknown"


def build_pool_state_error_diagnosis(campaign_root: Path) -> dict[str, Any]:
    rows = _real_post_migration_rows(read_jsonl(campaign_root / "post_migration_observations.jsonl"))
    by_pool: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pool = str(row.get("pool_or_pair_address") or "")
        if pool:
            by_pool.setdefault(pool, []).append(row)
    diagnosed_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("pool_state_status") != "error" and row.get("depth_status") != "error":
            continue
        pool = str(row.get("pool_or_pair_address") or "")
        horizon = row.get("horizon_seconds_after_migration")
        later_success = False
        for other in by_pool.get(pool, []):
            other_horizon = other.get("horizon_seconds_after_migration")
            if other.get("pool_state_status") not in {"partial", "available"}:
                continue
            if horizon is None or other_horizon is None or float(other_horizon) > float(horizon):
                later_success = True
                break
        classification = classify_pool_state_error(row)
        diagnosed_rows.append(
            {
                "mint": row.get("mint"),
                "pool_or_pair_address": pool,
                "quote_asset": row.get("quote_asset") or "unknown",
                "horizon_seconds_after_migration": horizon,
                "pool_state_status": row.get("pool_state_status"),
                "depth_status": row.get("depth_status"),
                "error_reason": row.get("pool_state_error_reason") or row.get("error_reason") or "unknown",
                "classification": classification,
                "account_owner": row.get("pool_account_owner"),
                "account_size": row.get("pool_account_size"),
                "discriminator": row.get("pool_discriminator"),
                "same_pool_later_produced_partial_or_available": later_success,
                "expected_or_transient": classification in {"pool_not_ready_yet", "pool_account_fetch_failed", "rpc_transient"},
                "decoder_broken": classification in {"decode_exception", "unsupported_pool_layout"},
            }
        )
    by_classification = Counter(str(row["classification"]) for row in diagnosed_rows)
    by_reason = Counter(str(row["error_reason"]) for row in diagnosed_rows)
    by_quote_asset = Counter(str(row["quote_asset"]) for row in diagnosed_rows)
    by_horizon = Counter(str(row["horizon_seconds_after_migration"]) for row in diagnosed_rows)
    by_account_size = Counter(str(row.get("account_size") or "unknown") for row in diagnosed_rows)
    pools_with_later_success = sorted(
        {
            str(row.get("pool_or_pair_address") or "")
            for row in diagnosed_rows
            if row.get("same_pool_later_produced_partial_or_available")
        }
    )
    return {
        "campaign_root": str(campaign_root),
        "post_migration_observation_rows": len(rows),
        "error_count": len(diagnosed_rows),
        "error_breakdown_by_classification": dict(sorted(by_classification.items())),
        "error_breakdown_by_reason": dict(sorted(by_reason.items())),
        "error_breakdown_by_quote_asset": dict(sorted(by_quote_asset.items())),
        "error_breakdown_by_horizon_seconds": dict(sorted(by_horizon.items())),
        "error_breakdown_by_account_size": dict(sorted(by_account_size.items())),
        "pools_with_later_success_after_early_error": len(pools_with_later_success),
        "pools_with_later_success_after_early_error_addresses": pools_with_later_success,
        "diagnosed_rows": diagnosed_rows,
    }


def diagnose_pool_state_errors(campaign_root: Path, output_json: Path, output_csv: Path) -> dict[str, Any]:
    diagnosis = build_pool_state_error_diagnosis(campaign_root)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(diagnosis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(output_csv, diagnosis["diagnosed_rows"])
    return diagnosis


def build_quote_depth_diagnosis(campaign_root: Path) -> dict[str, Any]:
    summary = read_json(campaign_root / "collector_summary.json")
    migration_rows = read_jsonl(campaign_root / "global_migration_events.jsonl")
    post_rows = _real_post_migration_rows(read_jsonl(campaign_root / "post_migration_observations.jsonl"))
    pool_status_counts = _count_by(post_rows, "pool_state_status")
    quote_status_counts = _count_by(post_rows, "executable_quote_status")
    pool_error_rows = [
        row for row in post_rows if row.get("pool_state_status") == "error" or row.get("depth_status") == "error"
    ]
    account_metadata_present_count = sum(
        1
        for row in post_rows
        if row.get("pool_account_owner") or row.get("pool_account_size") is not None or row.get("pool_discriminator")
    )
    wrong_pool_address_count = sum(1 for row in post_rows if not row.get("pool_or_pair_address"))
    unsupported_layout_count = sum(
        1
        for row in pool_error_rows
        if classify_pool_state_error(row) in {"unsupported_pool_layout", "decode_exception"}
    )
    liquidity_quote_count = int(summary.get("pool_liquidity_quote_present_count") or 0)
    liquidity_usd_count = int(summary.get("pool_liquidity_usd_present_count") or 0)
    executable_available_count = int(summary.get("post_migration_quote_available_count") or 0)
    executable_deferred_count = int(summary.get("post_migration_quote_deferred_count") or quote_status_counts.get("deferred", 0))
    liquidity_available = liquidity_quote_count > 0 and liquidity_usd_count > 0
    executable_available = executable_available_count > 0
    quote_depth_status = (
        "QUOTE_DEPTH_LIVE"
        if liquidity_available and executable_available
        else "QUOTE_DEPTH_PARTIAL_ONLY"
        if liquidity_available or executable_available
        else "QUOTE_DEPTH_NOT_READY"
    )
    diagnosis = {
        "campaign_root": str(campaign_root),
        "run_id": summary.get("run_id"),
        "global_migration_rows": len(migration_rows),
        "post_migration_observation_rows": len(post_rows),
        "pool_state_partial_count": int(pool_status_counts.get("partial", 0)),
        "pool_state_error_count": int(pool_status_counts.get("error", 0)),
        "pool_state_not_available_count": int(pool_status_counts.get("not_available", 0)),
        "pool_state_available_count": int(pool_status_counts.get("available", 0)),
        "pool_state_error_reasons": _count_by(pool_error_rows, "pool_state_error_reason"),
        "quote_assets": _count_by(post_rows, "quote_asset"),
        "horizons_affected": _count_by(post_rows, "horizon_seconds_after_migration"),
        "pool_account_fetch_succeeded_count": account_metadata_present_count,
        "pool_account_owner_present_count": sum(1 for row in post_rows if row.get("pool_account_owner")),
        "pool_account_size_present_count": sum(1 for row in post_rows if row.get("pool_account_size") is not None),
        "pool_discriminator_present_count": sum(1 for row in post_rows if row.get("pool_discriminator")),
        "pool_address_looked_wrong_count": wrong_pool_address_count,
        "unsupported_or_decode_layout_count": unsupported_layout_count,
        "liquidity_quote_present_count": liquidity_quote_count,
        "liquidity_usd_present_count": liquidity_usd_count,
        "executable_quote_status_counts": quote_status_counts,
        "executable_quote_available_count": executable_available_count,
        "executable_quote_deferred_count": executable_deferred_count,
        "liquidity_fields_not_populated_reason": (
            "pool_reserve_decode_not_confirmed_or_executable_quote_not_available"
            if not liquidity_available
            else "liquidity_fields_populated"
        ),
        "executable_quotes_deferred_reason": (
            "read_only_executable_quote_source_not_configured"
            if executable_deferred_count > 0 and executable_available_count == 0
            else "executable_quote_available_or_not_observed"
        ),
        "pool_reserve_decode_live": False,
        "executable_quote_live": executable_available,
        "quote_depth_status": quote_depth_status,
        "blocker": (
            "direct PumpSwap reserve-token account decode or read-only executable quote source is still missing"
            if quote_depth_status != "QUOTE_DEPTH_LIVE"
            else "none"
        ),
    }
    return diagnosis


def write_quote_depth_diagnosis(campaign_root: Path, output_root: Path) -> dict[str, Any]:
    diagnosis = build_quote_depth_diagnosis(campaign_root)
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "quote_depth_diagnosis.json"
    md_path = output_root / "quote_depth_diagnosis.md"
    json_path.write_text(json.dumps(diagnosis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_lines = [
        "# T007AQ Quote/Depth Diagnosis",
        "",
        f"- Campaign root: `{diagnosis.get('campaign_root')}`",
        f"- Run id: `{diagnosis.get('run_id')}`",
        f"- Quote/depth status: `{diagnosis.get('quote_depth_status')}`",
        f"- Pool partial count: `{diagnosis.get('pool_state_partial_count')}`",
        f"- Pool error count: `{diagnosis.get('pool_state_error_count')}`",
        f"- Pool not_available count: `{diagnosis.get('pool_state_not_available_count')}`",
        f"- Pool available count: `{diagnosis.get('pool_state_available_count')}`",
        f"- Error reasons: `{diagnosis.get('pool_state_error_reasons')}`",
        f"- Quote assets: `{diagnosis.get('quote_assets')}`",
        f"- Horizons affected: `{diagnosis.get('horizons_affected')}`",
        f"- Pool account metadata present rows: `{diagnosis.get('pool_account_fetch_succeeded_count')}`",
        f"- Liquidity quote present count: `{diagnosis.get('liquidity_quote_present_count')}`",
        f"- Liquidity USD present count: `{diagnosis.get('liquidity_usd_present_count')}`",
        f"- Executable quote status counts: `{diagnosis.get('executable_quote_status_counts')}`",
        f"- Why liquidity is missing: `{diagnosis.get('liquidity_fields_not_populated_reason')}`",
        f"- Why executable quotes are deferred: `{diagnosis.get('executable_quotes_deferred_reason')}`",
        f"- Blocker: `{diagnosis.get('blocker')}`",
        "",
        "No reserves or liquidity are fabricated by this report.",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return diagnosis


def post_migration_observation_availability(
    summary: dict[str, Any],
    migration_rows: list[dict[str, Any]],
    post_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    post_rows = _real_post_migration_rows(post_rows)
    migration_mints = {str(row.get("mint") or "") for row in migration_rows if row.get("mint")}
    observed_mints = {str(row.get("mint") or "") for row in post_rows if row.get("mint")}
    horizons = sorted(
        {
            int(row.get("horizon_seconds_after_migration"))
            for row in post_rows
            if row.get("horizon_seconds_after_migration") is not None
        }
    )
    migrations_without_rows = sorted(mint for mint in migration_mints if mint not in observed_mints)
    by_quote_asset = _count_by(post_rows, "quote_asset")
    migrations_by_quote = _count_by(migration_rows, "quote_asset")
    missingness_by_quote: dict[str, dict[str, int]] = {}
    for quote_asset in sorted(set(by_quote_asset) | set(migrations_by_quote)):
        migration_count = migrations_by_quote.get(quote_asset, 0)
        observed_count = by_quote_asset.get(quote_asset, 0)
        missingness_by_quote[quote_asset] = {
            "migration_rows": migration_count,
            "post_migration_observation_rows": observed_count,
            "missing_observation_rows": max(0, migration_count - observed_count),
        }
    pool_state_counts = _count_by(post_rows, "pool_state_status")
    pool_error_count = int(pool_state_counts.get("error", 0))
    pool_status_total = sum(pool_state_counts.values())
    pool_error_breakdown = {
        reason: count
        for reason, count in _count_by(
            [row for row in post_rows if row.get("pool_state_status") == "error" or row.get("depth_status") == "error"],
            "pool_state_error_reason",
        ).items()
    }
    pool_diagnosis = build_pool_state_error_diagnosis(Path(summary.get("output_folder") or ".")) if summary.get("output_folder") else {}
    return {
        "observations_scheduled": summary.get("post_migration_observations_scheduled"),
        "observations_written": summary.get("post_migration_observations_written") or len(post_rows),
        "completed_by_horizon": summary.get("post_migration_observations_completed_by_horizon") or _count_by(
            post_rows, "horizon_seconds_after_migration"
        ),
        "pending_at_finalization": summary.get("post_migration_observations_pending_at_finalization"),
        "horizons_observed": horizons,
        "pool_state_status_counts": pool_state_counts,
        "post_migration_pool_state_available_count": int(pool_state_counts.get("available", 0)),
        "post_migration_pool_state_partial_count": int(pool_state_counts.get("partial", 0)),
        "post_migration_pool_state_not_available_count": int(pool_state_counts.get("not_available", 0)),
        "post_migration_pool_state_error_count": pool_error_count,
        "post_migration_pool_state_error_rate": _rate(pool_error_count, pool_status_total),
        "post_migration_pool_state_error_breakdown": pool_error_breakdown,
        "pools_with_later_success_after_early_error": pool_diagnosis.get("pools_with_later_success_after_early_error", 0),
        "depth_status_counts": _count_by(post_rows, "depth_status"),
        "pool_liquidity_quote_present_count": summary.get("pool_liquidity_quote_present_count")
        if summary.get("pool_liquidity_quote_present_count") is not None
        else sum(1 for row in post_rows if row.get("pool_liquidity_quote") is not None),
        "pool_liquidity_usd_present_count": summary.get("pool_liquidity_usd_present_count")
        if summary.get("pool_liquidity_usd_present_count") is not None
        else sum(1 for row in post_rows if row.get("pool_liquidity_usd") is not None),
        "quote_status_counts": _count_by(post_rows, "executable_quote_status"),
        "executable_quote_deferred_count": int(_count_by(post_rows, "executable_quote_status").get("deferred", 0)),
        "observations_by_quote_asset": summary.get("post_migration_observations_by_quote_asset") or by_quote_asset,
        "missingness_by_quote_asset": missingness_by_quote,
        "migrations_without_post_migration_observations": len(migrations_without_rows),
        "migrations_without_post_migration_observation_mints": migrations_without_rows[:25],
    }


def execution_cost_availability(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "observations_written": summary.get("execution_cost_observations_written") or len(rows),
        "status_counts": _count_by(rows, "execution_cost_status"),
        "source_counts": _count_by(rows, "execution_cost_source"),
        "observations_by_reason": summary.get("execution_cost_observations_by_reason") or _count_by(rows, "observation_reason"),
        "recent_prioritization_fee_sample_count": summary.get("recent_prioritization_fee_sample_count")
        if summary.get("recent_prioritization_fee_sample_count") is not None
        else sum(int(row.get("recent_prioritization_fee_sample_count") or 0) for row in rows),
        "failed_tx_share_status_counts": _count_by(rows, "failed_tx_share_status"),
        "failed_tx_share_available_count": summary.get("failed_tx_share_available_count"),
        "failed_tx_share_deferred_count": summary.get("failed_tx_share_deferred_count"),
    }


def executable_quote_availability(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    impacts = [
        float(row["price_impact_pct"])
        for row in rows
        if row.get("price_impact_pct") is not None
    ]
    clip_counts = _count_by(rows, "quote_clip_notional_quote")
    return {
        "observations_written": summary.get("executable_quote_observations_written") or len(rows),
        "status_counts": _count_by(rows, "quote_status"),
        "source_counts": summary.get("executable_quote_by_source") or _count_by(rows, "quote_source"),
        "quote_asset_counts": summary.get("executable_quote_by_quote_asset") or _count_by(rows, "quote_asset"),
        "direction_counts": summary.get("executable_quote_by_direction") or _count_by(rows, "quote_direction"),
        "clip_size_counts": clip_counts,
        "price_impact_available_count": summary.get("price_impact_available_count")
        if summary.get("price_impact_available_count") is not None
        else len(impacts),
        "price_impact_missing_count": summary.get("price_impact_missing_count")
        if summary.get("price_impact_missing_count") is not None
        else max(0, len(rows) - len(impacts)),
        "price_impact_min": min(impacts) if impacts else None,
        "price_impact_median": sorted(impacts)[len(impacts) // 2] if impacts else None,
        "price_impact_max": max(impacts) if impacts else None,
        "fee_model_status_counts": _count_by(rows, "fee_model_status"),
        "missingness_error_reasons": _count_by(
            [row for row in rows if row.get("quote_status") in {"error", "not_available"}],
            "error_reason",
        ),
    }


def summarize_campaign(root: Path) -> dict[str, Any]:
    summary = read_json(root / "collector_summary.json")
    manifest = read_json(root / "campaign_manifest.json")
    migration_rows = read_jsonl(root / "global_migration_events.jsonl")
    post_migration_rows = read_jsonl(root / "post_migration_observations.jsonl")
    executable_quote_rows = read_jsonl(root / "executable_quote_observations.jsonl")
    execution_cost_rows = read_jsonl(root / "execution_cost_observations.jsonl")
    artifact_stats = {
        artifact: jsonl_row_stats(root / artifact)
        for artifact in set(ARTIFACT_MAP.values()) | {
            "birth_audit.jsonl",
            "curve_observations.jsonl",
            "global_migration_candidates.jsonl",
            "token_path_summary.jsonl",
        }
    }
    artifact_counts = {artifact: stats["valid_rows"] for artifact, stats in artifact_stats.items()}
    corrupt_row_counts = {artifact: stats["corrupt_rows"] for artifact, stats in artifact_stats.items()}
    post_availability = post_migration_observation_availability(
        {**summary, "output_folder": str(root)},
        migration_rows,
        post_migration_rows,
    )
    status_summary: dict[str, int] = {}
    for artifact in ARTIFACT_MAP.values():
        for key, count in status_counts(read_jsonl(root / artifact)).items():
            status_summary[key] = status_summary.get(key, 0) + count
    gate_input = {
        **summary,
        "true_curve_threshold_crossings_written": artifact_counts.get("true_curve_threshold_crossings.jsonl", 0),
        "curve_velocity_events_written": artifact_counts.get("curve_velocity_events.jsonl", 0),
        "curve_acceleration_events_written": artifact_counts.get("curve_acceleration_events.jsonl", 0),
        "token_path_summary_rows": artifact_counts.get("token_path_summary.jsonl", 0),
        "post_migration_pool_state_error_count": post_availability.get("post_migration_pool_state_error_count", 0),
        "post_migration_observations_written": len(_real_post_migration_rows(post_migration_rows)),
        "executable_quote_observations_written": summary.get("executable_quote_observations_written") or artifact_counts.get("executable_quote_observations.jsonl", 0),
        "price_impact_available_count": summary.get("price_impact_available_count")
        if summary.get("price_impact_available_count") is not None
        else sum(1 for row in executable_quote_rows if row.get("price_impact_pct") is not None),
        "executable_quote_decision_time_safe_count": summary.get("executable_quote_decision_time_safe_count")
        if summary.get("executable_quote_decision_time_safe_count") is not None
        else sum(1 for row in executable_quote_rows if row.get("decision_time_safe") is True),
        "fee_model_unknown_count": summary.get("fee_model_unknown_count")
        if summary.get("fee_model_unknown_count") is not None
        else sum(1 for row in executable_quote_rows if row.get("fee_model_status") == "unknown"),
        "placeholder_feature_families": [
            family
            for family, artifact, counter in [
                ("holder_distribution_partial_snapshots", "holder_distribution_snapshots.jsonl", "holder_distribution_snapshots_written"),
                ("dev_creator_behavior_partial_features", "dev_behavior_events.jsonl", "dev_behavior_events_written"),
                ("post_migration_observations_partial", "post_migration_observations.jsonl", "post_migration_observations_written"),
                ("execution_cost_observations_partial", "execution_cost_observations.jsonl", "execution_cost_observations_written"),
            ]
            if artifact_counts.get(artifact, 0) > 0 and not summary.get(counter)
        ],
    }
    thesis_ready_gate = evaluate_t007_thesis_ready_gate(gate_input)
    return {
        "campaign_root": str(root),
        "campaign_id": manifest.get("campaign_id") or summary.get("run_id"),
        "run_id": summary.get("run_id"),
        "unique_births": summary.get("unique_birth_mints") or summary.get("total_births_detected"),
        "admitted_births": summary.get("admitted_births"),
        "valuation_ladder_policy": summary.get("valuation_ladder_emission_policy") or manifest.get("valuation_ladder_policy"),
        "valuation_ladder_events_written": summary.get("valuation_ladder_events_written"),
        "births_by_quote_asset": summary.get("births_by_quote_asset"),
        "migration_events_by_quote_asset": summary.get("global_migration_events_by_quote_asset") or summary.get("migration_events_by_quote_asset"),
        "post_migration_observation_availability": post_availability,
        "executable_quote_availability": executable_quote_availability(summary, executable_quote_rows),
        "execution_cost_availability": execution_cost_availability(summary, execution_cost_rows),
        "artifact_counts": artifact_counts,
        "corrupt_row_counts": corrupt_row_counts,
        "status_summary": status_summary,
        "thesis_ready_gate": thesis_ready_gate,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    if not fieldnames:
        fieldnames = ["status"]
        rows = [{"status": "no_rows"}]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_report(campaign_roots: list[Path], output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    campaign_summaries = [summarize_campaign(root) for root in campaign_roots]
    for filename in REPORT_FILENAMES:
        if filename in {"summary.md", "analysis_result.json"}:
            continue
        if filename == "data_quality_report.csv":
            rows = [
                {
                    "campaign_id": item.get("campaign_id"),
                    "run_id": item.get("run_id"),
                    "artifact": artifact,
                    "row_count": count,
                    "corrupt_row_count": (item.get("corrupt_row_counts") or {}).get(artifact, 0),
                    "valuation_ladder_policy": item.get("valuation_ladder_policy"),
                }
                for item in campaign_summaries
                for artifact, count in (item.get("artifact_counts") or {}).items()
            ]
        else:
            artifact = ARTIFACT_MAP.get(filename)
            rows = [
                {
                    "campaign_id": item.get("campaign_id"),
                    "run_id": item.get("run_id"),
                    "source_artifact": artifact,
                    "row_count": (item.get("artifact_counts") or {}).get(artifact, 0),
                    "status": "availability_only_no_rule_optimization",
                }
                for item in campaign_summaries
            ]
        write_csv(output_root / filename, rows)
    summary_md = output_root / "summary.md"
    lines = [
        "# T007AA Forward Thesis Dataset Report",
        "",
        "This report is analysis scaffolding only. It does not make trading recommendations.",
        "",
        f"Campaign folders analyzed: {len(campaign_summaries)}",
        "",
    ]
    for item in campaign_summaries:
        lines.extend(
            [
                f"## {item.get('campaign_id')}",
                "",
                f"- Run id: `{item.get('run_id')}`",
                f"- Unique births: `{item.get('unique_births')}`",
                f"- Admitted births: `{item.get('admitted_births')}`",
                f"- Valuation ladder policy: `{item.get('valuation_ladder_policy')}`",
                f"- Valuation ladder events: `{item.get('valuation_ladder_events_written')}`",
                f"- Births by quote asset: `{item.get('births_by_quote_asset')}`",
                f"- Migration events by quote asset: `{item.get('migration_events_by_quote_asset')}`",
                f"- Post-migration observation availability: `{item.get('post_migration_observation_availability')}`",
                f"- Execution-cost availability: `{item.get('execution_cost_availability')}`",
                f"- Thesis-ready gate 60m allowed: `{(item.get('thesis_ready_gate') or {}).get('can_run_60m_thesis_scan')}`",
                f"- Thesis-ready gate 2h+ allowed: `{(item.get('thesis_ready_gate') or {}).get('can_run_2h_plus_scan')}`",
                f"- Gate minimum next action: `{(item.get('thesis_ready_gate') or {}).get('minimum_next_action')}`",
                f"- Gate blockers: `{(item.get('thesis_ready_gate') or {}).get('blocking_reasons')}`",
                "",
            ]
        )
    summary_md.write_text("\n".join(lines), encoding="utf-8")
    analysis = {
        "report_id": "T007AP_REPORT_ALIAS_POOL_ERROR_REPAIR",
        "output_root": str(output_root),
        "campaign_count": len(campaign_summaries),
        "edge_claim_allowed": False,
        "trading_enabled": False,
        "paper_trading_enabled": False,
        "valuation_ladder_suppressed": all(
            (item.get("thesis_ready_gate") or {}).get("valuation_ladder_suppressed") is True
            for item in campaign_summaries
        ),
        "mayhem_files_modified": False,
        "campaigns": [],
    }
    for item in campaign_summaries:
        gate = item.get("thesis_ready_gate") or {}
        blockers = list(gate.get("blocking_reasons") or [])
        final_label = (
            "T007_60M_THESIS_VALIDATION_PASS_2H_READY"
            if gate.get("can_run_2h_plus_scan")
            else "T007_60M_PIPELINE_VALIDATION_PARTIAL_NOT_THESIS_READY"
            if gate.get("quote_depth_status") != "QUOTE_DEPTH_READY"
            else "T007_60M_THESIS_VALIDATION_PARTIAL"
        )
        analysis["campaigns"].append(
            {
                "input_root": item.get("campaign_root"),
                "campaign_id": item.get("campaign_id"),
                "run_id": item.get("run_id"),
                "artifact_row_counts": item.get("artifact_counts"),
                "corrupt_row_counts": item.get("corrupt_row_counts"),
                "feature_family_coverage": {
                    "live": gate.get("live_feature_families"),
                    "missing": gate.get("missing_feature_families"),
                    "deferred": gate.get("deferred_feature_families"),
                },
                "migration_post_migration_coverage": item.get("post_migration_observation_availability"),
                "execution_cost_coverage": item.get("execution_cost_availability"),
                "executable_quote_coverage": item.get("executable_quote_availability"),
                "readiness_gate_result": gate,
                "blocker_list": blockers,
                "final_decision_label": final_label,
                "valuation_ladder_suppressed": gate.get("valuation_ladder_suppressed"),
                "valuation_ladder_events_written": item.get("valuation_ladder_events_written"),
                "mayhem_files_modified": False,
            }
        )
    analysis_result_path = output_root / "analysis_result.json"
    analysis_result_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "output_root": str(output_root),
        "campaign_count": len(campaign_summaries),
        "analysis_result_path": str(analysis_result_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T007AA forward thesis dataset availability report.")
    parser.add_argument("campaign_roots", nargs="+", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/theses/t007aa_forward_thesis_dataset_report"),
    )
    args = parser.parse_args()
    result = run_report(args.campaign_roots, args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
