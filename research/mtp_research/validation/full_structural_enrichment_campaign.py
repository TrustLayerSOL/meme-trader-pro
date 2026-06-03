"""Full structural enrichment campaign for runner fingerprint discovery.

This module is intentionally ETL-only. It joins already collected local
structural artifacts, writes coverage reports, and fails closed on unnamed
external collection so Helius/DexScreener calls are not spent blindly.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path, data_lake_root
from research.mtp_research.ingestion.dexscreener_real_ingest import DexScreenerRealIngestor, KNOWN_QUOTE_MINTS
from research.mtp_research.ingestion.helius_backfill import HeliusHistoricalAdapter


REPORT_ID = "full_structural_enrichment_campaign_v0"
READINESS_READY_WITH_GAPS = "full_structural_enrichment_ready_with_documented_external_gaps"
READINESS_BLOCKED = "full_structural_enrichment_blocked"

DEFAULT_RAW_DIR = data_lake_path("data", "raw", "structural_enrichment", "full_campaign")
DEFAULT_PARSED_DIR = data_lake_path("data", "backtests", "structural_enrichment", "full_campaign")
DEFAULT_REPORT_DIR = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "full_structural_enrichment_campaign",
)
DEFAULT_MANIFEST_DIR = data_lake_path("manifests")
DEFAULT_STATUS_PATH = Path("theses/FULL_STRUCTURAL_ENRICHMENT_CAMPAIGN_STATUS.md")

DEFAULT_TRIGGER_ROWS_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T011_expanded_rerun",
    "expanded_trigger_20k_feature_rows.csv",
)
DEFAULT_COMBINED_REPAIRED_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "combined_aligned_p0_structural_fingerprint_fdv_repaired.parquet",
)
DEFAULT_TOP_HOLDER_LAYER_PATHS = [
    data_lake_path("data", "backtests", "structural_enrichment", "aligned_p0_medium_top_holder_replay.parquet"),
    data_lake_path("data", "backtests", "structural_enrichment", "top_holder_replay_pilot.parquet"),
]
DEFAULT_EARLY_BUYER_LAYER_PATHS = [
    data_lake_path("data", "backtests", "structural_enrichment", "aligned_p0_medium_early_buyer_wallet_history.parquet"),
    data_lake_path("data", "backtests", "structural_enrichment", "early_buyer_wallet_history_pilot.parquet"),
]
DEFAULT_CREATOR_FUNDER_LAYER_PATHS = [
    data_lake_path("data", "backtests", "structural_enrichment", "aligned_p0_medium_creator_funder_graph.parquet"),
    data_lake_path("data", "backtests", "structural_enrichment", "creator_funder_transfer_graph_pilot.parquet"),
]
DEFAULT_HOLDER_STATE_PATH = data_lake_path(
    "data", "backtests", "holder_state", "strict_cohort_holder_state_snapshots.parquet"
)
DEFAULT_ENTITY_PROXY_PATH = data_lake_path(
    "data", "backtests", "entity_proxy", "entity_proxy_strict_cohort.parquet"
)
DEFAULT_EVENTS_PATH = data_lake_path("data", "normalized", "pumpfun_lifecycle_events_classified.jsonl")
DEFAULT_SOL_USD_PATH = data_lake_path("data", "normalized", "valuation_inputs", "sol_usd_coingecko.jsonl")
DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_lifecycle_collected_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_MIGRATION_LABELS_PATH = data_lake_path(
    "data",
    "backtests",
    "migration_graduation",
    "combined_migration_graduation_labels_provenance_upgraded.jsonl",
)
DEFAULT_DEXSCREENER_PAIR_LABELS_PATH = data_lake_path(
    "data",
    "backtests",
    "migration_graduation",
    "dexscreener_pair_graduation_labels.parquet",
)

METHODOLOGY_FLAGS = [
    "research_only",
    "data_enrichment_only",
    "not_a_thesis",
    "no_backtest",
    "no_walk_forward_validation",
    "no_thesis_evaluation",
    "no_thesis_promotion",
    "no_paper_trading",
    "no_live_trading",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_trading_logic",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
    "observed_replay_not_full_chain_holder_state",
]


def run_full_structural_enrichment_campaign(
    *,
    data_root: Path | str | None = None,
    input_paths: dict[str, Any] | None = None,
    output_paths: dict[str, Path | str] | None = None,
    execute_helius: bool = False,
    execute_dexscreener: bool = False,
    max_helius_credits: int = 500_000,
    contract_authority_adapter: Any | None = None,
    contract_authority_workers: int = 8,
    dexscreener_token_adapter: Any | None = None,
    dexscreener_workers: int = 8,
) -> tuple[dict[str, Any], dict[str, Path]]:
    started = time.time()
    root = Path(data_root) if data_root is not None else data_lake_root()
    paths = _resolve_paths(root, output_paths)
    inputs = _resolve_input_paths(input_paths)
    _ensure_output_dirs(paths)

    base = _load_base_universe(inputs)
    base = _attach_local_candidate_creator_metadata(base, inputs["candidates"])
    combined = _load_optional_frame(inputs["combined_repaired"])
    fdv = _build_fdv_efficiency_layer(base, combined)
    top_holder = _build_top_holder_layer(base, combined, inputs["top_holder_layers"], inputs["holder_state"])
    early_buyer = _build_early_buyer_layer(base, combined, inputs["early_buyer_layers"])
    creator_funder = _build_creator_funder_layer(base, combined, inputs["creator_funder_layers"])
    cluster = _build_cluster_layer(base, inputs["entity_proxy"])
    distribution = _build_distribution_layer(base)
    visible_flow = _build_visible_attention_and_flow_layer(
        base,
        top_holder,
        inputs["events"],
        inputs["sol_usd"],
        inputs["migration_labels"],
    )
    attention_layers = _build_attention_visibility_layers(
        base,
        candidates_path=inputs["candidates"],
        dexscreener_pairs_path=inputs["dexscreener_pairs"],
        execute_dexscreener=execute_dexscreener,
        paths=paths,
        adapter=dexscreener_token_adapter,
        workers=dexscreener_workers,
    )
    topicality = attention_layers["topicality"]
    visibility = attention_layers["visibility"]
    metadata_quality = attention_layers["metadata_quality"]
    contract_result = _build_contract_authority_layer(
        base,
        execute_helius=execute_helius,
        paths=paths,
        adapter=contract_authority_adapter,
        workers=contract_authority_workers,
    )
    contract = contract_result["layer"]
    master = _build_master(
        base=base,
        fdv=fdv,
        top_holder=top_holder,
        early_buyer=early_buyer,
        creator_funder=creator_funder,
        cluster=cluster,
        distribution=distribution,
        visible_flow=visible_flow,
        topicality=topicality,
        visibility=visibility,
        metadata_quality=metadata_quality,
        contract=contract,
    )
    target_registry = _build_target_registry(master)
    budget = estimate_campaign_budget(
        launch_count=len(master),
        execute_helius=execute_helius,
        execute_dexscreener=execute_dexscreener,
        max_helius_credits=max_helius_credits,
    )
    layer_coverage = build_layer_coverage(master)
    readiness = READINESS_READY_WITH_GAPS if len(master) else READINESS_BLOCKED
    external_gaps = _external_gaps(layer_coverage)

    preflight = {
        "report_id": REPORT_ID,
        "preflight": True,
        "methodology_flags": METHODOLOGY_FLAGS,
        "launches_planned": int(len(master)),
        "target_registry": target_registry,
        "budget": budget,
        "safe_to_execute": bool(budget["safe_to_execute"]),
        "external_collection_policy": "fail_closed_without_named_bounded_targets",
    }
    _write_json(paths["preflight_json_path"], preflight)
    paths["preflight_markdown_path"].write_text(_preflight_markdown(preflight), encoding="utf-8")

    _write_layers(
        paths=paths,
        fdv=fdv,
        top_holder=top_holder,
        early_buyer=early_buyer,
        creator_funder=creator_funder,
        cluster=cluster,
        distribution=distribution,
        visible_flow=visible_flow,
        topicality=topicality,
        visibility=visibility,
        metadata_quality=metadata_quality,
        contract=contract,
        master=master,
    )

    report = {
        "report_id": REPORT_ID,
        "readiness_classification": readiness,
        "methodology_flags": METHODOLOGY_FLAGS,
        "launches_enriched": int(len(master)),
        "master_rows": int(len(master)),
        "raw_rows_added": 0,
        "expected_research_rows": int(len(master)),
        "helius": {
            "execute_requested": bool(execute_helius),
            "execute_completed": bool(contract_result["execute_completed"]),
            "requests_used": int(contract_result["requests_used"]),
            "credits_used": int(contract_result["requests_used"]),
            "reason_not_executed": budget["external_collection_reason"],
            "max_credits": int(max_helius_credits),
            "target": "contract_authority_getMultipleAccounts_batched" if execute_helius else None,
            "provider_errors": contract_result["errors"],
        },
        "dexscreener": {
            "execute_requested": bool(execute_dexscreener),
            "execute_completed": bool(attention_layers["dexscreener_execute_completed"]),
            "calls_used": int(attention_layers["dexscreener_calls_used"]),
            "reason_not_executed": budget["external_collection_reason"],
            "target": "dexscreener_tokens_batch_visibility_context" if execute_dexscreener else None,
            "provider_errors": attention_layers["dexscreener_errors"],
        },
        "budget": budget,
        "layer_coverage": layer_coverage,
        "attention_visibility": attention_layers["summary"],
        "visibility_source_audit": attention_layers["source_audit"],
        "external_gaps": external_gaps,
        "warnings": _warnings(layer_coverage, external_gaps),
        "runtime_seconds": round(time.time() - started, 3),
        "paths": {key: str(value) for key, value in paths.items()},
    }
    _write_reports(report, paths, master)
    return report, paths


def estimate_campaign_budget(
    *,
    launch_count: int,
    execute_helius: bool,
    execute_dexscreener: bool,
    max_helius_credits: int,
) -> dict[str, Any]:
    projected_helius = math.ceil(launch_count / 100) if execute_helius else 0
    projected_dexscreener = math.ceil(launch_count / 30) if execute_dexscreener else 0
    if execute_helius:
        status = "within_budget_contract_authority_batched" if projected_helius <= max_helius_credits else "blocked_projected_helius_above_budget"
        reason = "contract_authority_getMultipleAccounts_batched"
    elif execute_dexscreener:
        status = "within_budget_dexscreener_visibility_batched"
        reason = "dexscreener_tokens_batch_visibility_context"
    else:
        status = "within_budget_local_only"
        reason = "local_structural_artifacts_available_for_current_campaign"
    return {
        "launch_count": int(launch_count),
        "helius_execute_requested": bool(execute_helius),
        "dexscreener_execute_requested": bool(execute_dexscreener),
        "projected_helius_credits": int(projected_helius),
        "projected_dexscreener_calls": int(projected_dexscreener),
        "max_helius_credits": int(max_helius_credits),
        "budget_gate_status": status,
        "external_collection_reason": reason,
        "safe_to_execute": bool(projected_helius <= max_helius_credits),
    }


def build_layer_coverage(master: pd.DataFrame) -> dict[str, dict[str, Any]]:
    layer_columns = {
        "fdv_efficiency": "has_fdv_efficiency_layer",
        "top_holder_behavior": "has_top_holder_layer",
        "early_buyer_history": "has_early_buyer_history_layer",
        "creator_funder_graph": "has_creator_funder_layer",
        "cluster_coordination": "has_cluster_proxy_layer",
        "distribution_exit_behavior": "has_distribution_layer",
        "visible_attention_and_flow": "has_visible_attention_and_flow_layer",
        "topicality_context": "has_topicality_layer",
        "visibility_attention_context": "has_visibility_layer",
        "metadata_quality_context": "has_metadata_quality_layer",
        "contract_authority_context": "has_contract_layer",
    }
    total = int(len(master))
    coverage: dict[str, dict[str, Any]] = {}
    for layer, column in layer_columns.items():
        covered = int(master[column].fillna(False).astype(bool).sum()) if column in master else 0
        coverage[layer] = {
            "total_rows": total,
            "covered_rows": covered,
            "missing_rows": total - covered,
            "coverage_pct": round((covered / total) * 100, 4) if total else 0.0,
        }
    return coverage


def _resolve_paths(root: Path, overrides: dict[str, Path | str] | None) -> dict[str, Path]:
    parsed_dir = root / "data" / "backtests" / "structural_enrichment" / "full_campaign"
    report_dir = root / "data" / "backtests" / "diagnostics" / "reports" / "full_structural_enrichment_campaign"
    attention_report_dir = root / "data" / "backtests" / "diagnostics" / "reports" / "attention_visibility_enrichment"
    raw_dir = root / "data" / "raw" / "structural_enrichment" / "full_campaign"
    manifest_dir = root / "manifests"
    checkpoint_dir = parsed_dir / "checkpoints"
    paths = {
        "raw_dir": raw_dir,
        "parsed_dir": parsed_dir,
        "report_dir": report_dir,
        "attention_report_dir": attention_report_dir,
        "manifest_dir": manifest_dir,
        "checkpoint_dir": checkpoint_dir,
        "preflight_json_path": report_dir / "full_structural_enrichment_preflight.json",
        "preflight_markdown_path": report_dir / "full_structural_enrichment_preflight.md",
        "coverage_json_path": report_dir / "full_structural_enrichment_coverage.json",
        "coverage_markdown_path": report_dir / "full_structural_enrichment_coverage.md",
        "coverage_matrix_csv_path": report_dir / "full_structural_enrichment_matrix.csv",
        "layer_coverage_csv_path": report_dir / "full_structural_enrichment_layer_coverage.csv",
        "manifest_path": manifest_dir / "full_structural_enrichment_campaign_manifest.json",
        "status_path": DEFAULT_STATUS_PATH,
        "fdv_efficiency_parquet_path": parsed_dir / "fdv_efficiency_repaired.parquet",
        "top_holder_parquet_path": parsed_dir / "top_holder_milestone_behavior.parquet",
        "top_holder_jsonl_path": parsed_dir / "top_holder_milestone_behavior.jsonl",
        "early_buyer_parquet_path": parsed_dir / "early_buyer_wallet_history_enriched.parquet",
        "early_buyer_jsonl_path": parsed_dir / "early_buyer_wallet_history_enriched.jsonl",
        "creator_funder_parquet_path": parsed_dir / "creator_funder_transfer_graph_enriched.parquet",
        "creator_funder_jsonl_path": parsed_dir / "creator_funder_transfer_graph_enriched.jsonl",
        "cluster_parquet_path": parsed_dir / "cluster_coordination_proxies.parquet",
        "distribution_parquet_path": parsed_dir / "distribution_exit_behavior_enriched.parquet",
        "visible_attention_flow_parquet_path": parsed_dir / "visible_attention_and_flow_features.parquet",
        "visible_attention_flow_jsonl_path": parsed_dir / "visible_attention_and_flow_features.jsonl",
        "visibility_parquet_path": parsed_dir / "visibility_attention_context.parquet",
        "topicality_context_parquet_path": parsed_dir / "topicality_context.parquet",
        "visibility_context_parquet_path": parsed_dir / "visibility_context.parquet",
        "metadata_quality_context_parquet_path": parsed_dir / "metadata_quality_context.parquet",
        "visibility_source_audit_json_path": attention_report_dir / "visibility_source_audit.json",
        "visibility_source_audit_markdown_path": attention_report_dir / "visibility_source_audit.md",
        "attention_visibility_summary_json_path": attention_report_dir / "attention_visibility_coverage_summary.json",
        "attention_visibility_summary_markdown_path": attention_report_dir / "attention_visibility_coverage_summary.md",
        "contract_parquet_path": parsed_dir / "contract_authority_context.parquet",
        "contract_authority_raw_path": raw_dir / "contract_authority_get_multiple_accounts_raw.jsonl",
        "dexscreener_token_raw_path": raw_dir / "dexscreener_tokens_visibility_raw.jsonl",
        "master_parquet_path": parsed_dir / "master_enriched_runner_fingerprint.parquet",
        "master_jsonl_path": parsed_dir / "master_enriched_runner_fingerprint.jsonl",
    }
    if overrides:
        for key, value in overrides.items():
            paths[key] = Path(value)
    return paths


def _resolve_input_paths(input_paths: dict[str, Any] | None) -> dict[str, Any]:
    paths: dict[str, Any] = {
        "trigger_rows": DEFAULT_TRIGGER_ROWS_PATH,
        "combined_repaired": DEFAULT_COMBINED_REPAIRED_PATH,
        "top_holder_layers": DEFAULT_TOP_HOLDER_LAYER_PATHS,
        "early_buyer_layers": DEFAULT_EARLY_BUYER_LAYER_PATHS,
        "creator_funder_layers": DEFAULT_CREATOR_FUNDER_LAYER_PATHS,
        "holder_state": DEFAULT_HOLDER_STATE_PATH,
        "entity_proxy": DEFAULT_ENTITY_PROXY_PATH,
        "events": DEFAULT_EVENTS_PATH,
        "sol_usd": DEFAULT_SOL_USD_PATH,
        "candidates": DEFAULT_CANDIDATES_PATH,
        "migration_labels": DEFAULT_MIGRATION_LABELS_PATH,
        "dexscreener_pairs": DEFAULT_DEXSCREENER_PAIR_LABELS_PATH,
    }
    if input_paths:
        paths.update(input_paths)
    return paths


def _ensure_output_dirs(paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        if key.endswith("_dir"):
            path.mkdir(parents=True, exist_ok=True)
    for key, path in paths.items():
        if key.endswith("_path"):
            path.parent.mkdir(parents=True, exist_ok=True)


def _load_base_universe(inputs: dict[str, Any]) -> pd.DataFrame:
    trigger = _load_optional_frame(inputs["trigger_rows"])
    if trigger.empty:
        trigger = _load_optional_frame(inputs["combined_repaired"])
    if trigger.empty:
        return pd.DataFrame()
    frame = trigger.copy()
    if "mint" not in frame.columns and "token_mint" in frame.columns:
        frame["mint"] = frame["token_mint"]
    if "token_mint" not in frame.columns and "mint" in frame.columns:
        frame["token_mint"] = frame["mint"]
    if "launch_time" not in frame.columns:
        if "launch_ts" in frame.columns:
            frame["launch_time"] = pd.to_datetime(frame["launch_ts"], unit="s", utc=True, errors="coerce").astype(str)
        else:
            frame["launch_time"] = None
    if "launch_date" not in frame.columns:
        frame["launch_date"] = frame["launch_time"].astype(str).str.slice(0, 10)
    if "trigger_fdv_proxy" not in frame.columns and "peak_fdv_proxy" in frame.columns:
        frame["trigger_fdv_proxy"] = frame["peak_fdv_proxy"]
    frame = frame.drop_duplicates(subset=["launch_id"], keep="first")
    return frame.sort_values("launch_id").reset_index(drop=True)


def _attach_local_candidate_creator_metadata(base: pd.DataFrame, candidates_path: Path | str | None) -> pd.DataFrame:
    candidates = _load_optional_frame(candidates_path)
    if base.empty or candidates.empty:
        return base
    mint_column = "token_mint" if "token_mint" in candidates.columns else "mint" if "mint" in candidates.columns else None
    if mint_column is None or "token_mint" not in base.columns:
        return base
    candidate_rows = candidates[[mint_column]].copy()
    candidate_rows = candidate_rows.rename(columns={mint_column: "token_mint"})
    candidate_rows["candidate_creator_deployer"] = candidates.apply(_candidate_creator, axis=1)
    candidate_rows = candidate_rows.dropna(subset=["token_mint"]).drop_duplicates("token_mint", keep="first")
    merged = base.merge(candidate_rows, on="token_mint", how="left")
    if "creator" not in merged.columns:
        merged["creator"] = pd.NA
    merged["creator"] = merged["creator"].combine_first(merged["candidate_creator_deployer"])
    return merged.drop(columns=["candidate_creator_deployer"])


def _build_fdv_efficiency_layer(base: pd.DataFrame, combined: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "launch_id",
        "mint",
        "token_mint",
        "creator",
        "launch_time",
        "launch_ts",
        "milestone_tier",
        "trigger_fdv_proxy",
        "peak_fdv_proxy",
        "event_count_at_20k",
        "buy_count_at_20k",
        "sell_count_at_20k",
        "active_wallets_at_20k",
        "holder_count_at_20k",
        "fdv_per_event_at_20k",
        "fdv_per_buy_at_20k",
        "fdv_per_active_wallet_at_20k",
        "fdv_per_holder_at_20k",
    ]
    fdv = _select_existing(base, cols)
    combined_fdv = _select_existing(
        combined,
        [
            "launch_id",
            "fdv_per_event_at_20k",
            "fdv_per_buy_at_20k",
            "fdv_per_active_wallet_at_20k",
            "event_count_at_20k",
            "buy_count_at_20k",
            "sell_count_at_20k",
            "active_wallets_at_20k",
        ],
    )
    fdv = _merge_fill(fdv, combined_fdv, "launch_id")
    fdv = _derive_fdv_fields(fdv)
    fdv["fdv_efficiency_source"] = "local_repaired_fdv_proxy"
    fdv["true_market_cap_available"] = False
    fdv["market_cap_missing_reason"] = "true_historical_supply_market_cap_not_available"
    return fdv


def _build_top_holder_layer(
    base: pd.DataFrame,
    combined: pd.DataFrame,
    paths: list[Path | str],
    holder_state_path: Path | str | None,
) -> pd.DataFrame:
    layer = _select_existing(
        base,
        [
            "launch_id",
            "mint",
            "token_mint",
            "holder_count_at_20k",
            "top_holder_share_at_20k",
            "top_10_holder_share_at_20k",
            "creator_holder_share_at_20k",
        ],
    )
    combined_layer = _select_existing(
        combined,
        [
            "launch_id",
            "top_holder_share_proxy",
            "top_10_holder_share_proxy",
            "top_holder_addresses_available",
            "top_10_holder_addresses_available",
            "top_holder_behavior_proxy_available",
            "top_holder_replay_confidence",
            "full_chain_holder_snapshot_confirmed",
        ],
    )
    replay = _concat_existing(paths)
    replay_layer = pd.DataFrame()
    if not replay.empty:
        sort_columns = ["launch_id"]
        if "milestone_age_seconds" in replay.columns:
            sort_columns.append("milestone_age_seconds")
        replay = replay.sort_values(sort_columns, na_position="last")
        replay_layer = _select_existing(
            replay.drop_duplicates("launch_id", keep="first"),
            [
                "launch_id",
                "holder_count_proxy",
                "top_holder_owner",
                "top_holder_share_proxy",
                "top_10_holder_share_proxy",
                "holder_snapshot_confidence",
                "holder_snapshot_missing_reason",
                "is_confirmed_full_chain_snapshot",
            ],
        )
    holder_state = _load_optional_frame(holder_state_path)
    holder_state_layer = pd.DataFrame()
    if not holder_state.empty and "launch_id" in holder_state.columns:
        if "snapshot_age_seconds" in holder_state.columns:
            holder_state = holder_state.sort_values(["launch_id", "snapshot_age_seconds"], ascending=[True, False])
        holder_state_layer = _select_existing(
            holder_state.drop_duplicates("launch_id", keep="first"),
            [
                "launch_id",
                "holder_count",
                "top_holder_share",
                "top_10_holder_share",
                "creator_holder_share",
                "holder_snapshot_confidence",
                "holder_snapshot_missing_reason",
                "is_confirmed_full_chain_snapshot",
                "is_observed_delta_replay",
            ],
        )
        if "holder_count" in holder_state_layer.columns:
            holder_state_layer = holder_state_layer.rename(columns={"holder_count": "holder_count_proxy"})
        if "top_holder_share" in holder_state_layer.columns:
            holder_state_layer = holder_state_layer.rename(columns={"top_holder_share": "top_holder_share_proxy"})
        if "top_10_holder_share" in holder_state_layer.columns:
            holder_state_layer = holder_state_layer.rename(columns={"top_10_holder_share": "top_10_holder_share_proxy"})
        if "creator_holder_share" in holder_state_layer.columns:
            holder_state_layer = holder_state_layer.rename(columns={"creator_holder_share": "creator_holder_share_proxy"})
    layer = _merge_fill(layer, combined_layer, "launch_id")
    layer = _merge_fill(layer, replay_layer, "launch_id")
    layer = _merge_fill(layer, holder_state_layer, "launch_id")
    layer["top_holder_share_proxy"] = _coalesce(layer, ["top_holder_share_proxy", "top_holder_share_at_20k"])
    layer["top_10_holder_share_proxy"] = _coalesce(layer, ["top_10_holder_share_proxy", "top_10_holder_share_at_20k"])
    layer["holder_snapshot_source"] = "local_observed_delta_replay"
    layer["is_confirmed_full_chain_snapshot"] = layer.get("is_confirmed_full_chain_snapshot", False)
    layer["top_holder_milestone_behavior_missing_reason"] = layer["top_holder_share_proxy"].isna().map(
        lambda missing: "top_holder_proxy_unavailable" if missing else None
    )
    return layer


def _build_early_buyer_layer(base: pd.DataFrame, combined: pd.DataFrame, paths: list[Path | str]) -> pd.DataFrame:
    layer = _select_existing(base, ["launch_id", "mint", "token_mint", "creator"])
    combined_layer = _select_existing(
        combined,
        [
            "launch_id",
            "early_buyer_wallet_count",
            "early_buyer_with_prior_history_count",
            "early_buyer_with_prior_runner_count",
            "early_buyer_with_prior_100k_count",
            "early_buyer_with_prior_500k_count",
            "early_buyer_with_prior_1m_count",
            "early_buyer_prior_failure_count",
            "repeated_buyer_quality_proxy",
            "early_buyer_history_confidence",
        ],
    )
    history = _concat_existing(paths)
    history_layer = pd.DataFrame()
    if not history.empty and "current_launch_id" in history.columns:
        grouped = history.groupby("current_launch_id", dropna=False)
        history_layer = pd.DataFrame(
            {
                "launch_id": grouped.size().index,
                "early_buyer_wallet_count": grouped["wallet"].nunique().values if "wallet" in history else grouped.size().values,
                "early_buyer_with_prior_history_count": grouped["prior_transaction_count"].apply(
                    lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).gt(0).sum())
                ).values
                if "prior_transaction_count" in history
                else 0,
            }
        )
        history_layer["early_buyer_history_confidence"] = "bounded_wallet_history"
    layer = _merge_fill(layer, combined_layer, "launch_id")
    layer = _merge_fill(layer, history_layer, "launch_id")
    layer["early_buyer_history_missing_reason"] = layer.get("early_buyer_wallet_count", pd.Series(index=layer.index)).isna().map(
        lambda missing: "early_buyer_history_not_collected_for_launch" if missing else None
    )
    return layer


def _build_creator_funder_layer(base: pd.DataFrame, combined: pd.DataFrame, paths: list[Path | str]) -> pd.DataFrame:
    layer = _select_existing(base, ["launch_id", "mint", "token_mint", "creator", "launch_time", "launch_ts"])
    combined_layer = _select_existing(
        combined,
        [
            "launch_id",
            "candidate_funder_available",
            "candidate_funder",
            "candidate_funder_confidence",
            "shared_funding_proxy",
            "time_linked_funding_proxy",
            "launches_sharing_funder",
            "creators_sharing_funder",
            "common_funder_candidate_id",
            "creator_to_early_buyer_link_proxy",
            "creator_to_top_holder_link_proxy",
            "funder_graph_confidence",
        ],
    )
    funder = _concat_existing(paths)
    funder_layer = pd.DataFrame()
    if not funder.empty and "launch_id" in funder.columns:
        funder["_candidate_available_sort"] = funder.get("candidate_funder", pd.Series(index=funder.index)).notna().astype(int)
        funder = funder.sort_values(["launch_id", "_candidate_available_sort"], ascending=[True, False])
        funder_layer = _select_existing(
            funder.drop_duplicates("launch_id", keep="first"),
            [
                "launch_id",
                "candidate_funder",
                "candidate_funder_confidence",
                "candidate_funder_source",
                "creator_prior_funding_signature",
                "creator_prior_funding_time",
                "funding_age_seconds",
                "funding_amount_sol",
                "funding_amount_token",
                "funding_missing_reason",
                "common_funder_candidate_id",
                "launches_sharing_funder",
                "creators_sharing_funder",
                "shared_funding_proxy",
                "time_linked_funding_proxy",
                "creator_wallet_relation_proxy_count",
                "creator_wallet_relation_proxy_confidence",
            ],
        )
    layer = _merge_fill(layer, combined_layer, "launch_id")
    layer = _merge_fill(layer, funder_layer, "launch_id")
    layer["creator_funder_missing_reason"] = layer.get("candidate_funder", pd.Series(index=layer.index)).isna().map(
        lambda missing: "creator_funder_graph_not_collected_for_launch" if missing else None
    )
    return layer


def _build_cluster_layer(base: pd.DataFrame, entity_proxy_path: Path | str | None) -> pd.DataFrame:
    layer = _select_existing(
        base,
        [
            "launch_id",
            "repeated_actor_overlap_proxy",
            "repeated_buyer_overlap_proxy",
            "synchronized_participation_proxy",
            "circularity_proxy",
            "churn_proxy",
            "repeated_funder_flag",
        ],
    )
    entity = _load_optional_frame(entity_proxy_path)
    entity_layer = pd.DataFrame()
    if not entity.empty and "launch_id" in entity.columns:
        entity_layer = _select_existing(
            entity,
            [
                "launch_id",
                "creator_linked_share_proxy",
                "repeated_actor_overlap_proxy",
                "repeated_buyer_overlap_proxy",
                "synchronized_participation_proxy",
                "circularity_proxy",
                "churn_proxy",
                "proxy_confidence",
                "proxy_missing_reason",
                "event_count",
                "early_event_count_60s",
            ],
        )
    layer = _merge_fill(layer, entity_layer, "launch_id")
    layer["jito_bundle_data_available"] = False
    layer["jito_bundle_missing_reason"] = "bundle_level_data_not_available_in_local_artifacts"
    layer["cluster_coordination_source"] = "local_proxy_fields"
    return layer


def _build_distribution_layer(base: pd.DataFrame) -> pd.DataFrame:
    layer = _select_existing(
        base,
        [
            "launch_id",
            "buy_count_at_20k",
            "sell_count_at_20k",
            "net_buy_count_at_20k",
            "buy_sell_ratio_at_20k",
            "sell_count_growth_before_20k",
            "churn_proxy",
        ],
    )
    layer["exit_behavior_source"] = "local_event_flow_proxy"
    layer["confirmed_distribution_wallets_available"] = False
    layer["confirmed_distribution_missing_reason"] = "wallet_level_distribution_requires_additional_named_collection"
    return layer


def _build_visible_attention_and_flow_layer(
    base: pd.DataFrame,
    top_holder: pd.DataFrame,
    events_path: Path | str | None,
    sol_usd_path: Path | str | None,
    migration_labels_path: Path | str | None,
) -> pd.DataFrame:
    layer = _select_existing(
        base,
        [
            "launch_id",
            "mint",
            "token_mint",
            "launch_ts",
            "creator",
            "trigger_age_seconds",
            "creator_prior_migration_or_graduation_count",
            "top_holder_share_at_20k",
        ],
    )
    if "mint" not in layer.columns and "token_mint" in layer.columns:
        layer["mint"] = layer["token_mint"]
    if "token_mint" not in layer.columns and "mint" in layer.columns:
        layer["token_mint"] = layer["mint"]

    event_features = _first_minute_event_features(layer, events_path, sol_usd_path)
    holder_concentration = _select_existing(
        top_holder,
        ["launch_id", "top_holder_share_proxy", "top_holder_share_at_20k"],
    )
    prior_migration = _leakage_safe_prior_migration_features(base, migration_labels_path)
    layer = _merge_fill(layer, event_features, "launch_id")
    layer = _merge_fill(layer, holder_concentration, "launch_id")
    layer = _merge_fill(layer, prior_migration, "launch_id")
    layer["first_minute_usd_volume"] = _ensure_column(layer, "first_minute_usd_volume")
    layer["first_60s_buy_count"] = _ensure_column(layer, "first_60s_buy_count", default=0)
    layer["first_60s_unique_buyers"] = _ensure_column(layer, "first_60s_unique_buyers", default=0)
    layer["first_60s_transfer_spike_zscore"] = _ensure_column(layer, "first_60s_transfer_spike_zscore")
    layer["whale_buy_sequence_proxy"] = _ensure_column(layer, "whale_buy_sequence_proxy")
    layer["early_holder_concentration"] = _coalesce(
        layer, ["top_holder_share_proxy", "top_holder_share_at_20k"]
    )
    layer["deployer_prior_migration_count"] = _coalesce(
        layer, ["creator_prior_migration_or_graduation_count", "leakage_safe_prior_migration_count"]
    )
    layer["topicality_flag"] = pd.NA
    layer["topicality_missing_reason"] = "topicality_source_not_available_in_local_artifacts"
    layer["pair_migration_liquidity_delay_proxy"] = _coalesce(layer, ["trigger_age_seconds"])
    layer["pair_migration_liquidity_delay_proxy_source"] = layer[
        "pair_migration_liquidity_delay_proxy"
    ].notna().map(lambda ok: "trigger_20k_age_seconds_proxy" if ok else None)
    layer["visible_attention_and_flow_source"] = "local_events_and_milestone_proxies"
    layer["visible_attention_and_flow_missing_reason"] = layer.apply(_visible_flow_missing_reason, axis=1)
    return _select_existing(
        layer,
        [
            "launch_id",
            "first_minute_usd_volume",
            "first_minute_quote_sol_volume",
            "first_minute_usd_volume_source",
            "first_60s_buy_count",
            "first_60s_unique_buyers",
            "first_60s_transfer_count",
            "first_60s_transfer_spike_zscore",
            "whale_buy_sequence_proxy",
            "early_holder_concentration",
            "deployer_prior_migration_count",
            "deployer_prior_migration_count_source",
            "topicality_flag",
            "topicality_missing_reason",
            "pair_migration_liquidity_delay_proxy",
            "pair_migration_liquidity_delay_proxy_source",
            "visible_attention_and_flow_source",
            "visible_attention_and_flow_missing_reason",
        ],
    )


def _build_attention_visibility_layers(
    base: pd.DataFrame,
    *,
    candidates_path: Path | str | None,
    dexscreener_pairs_path: Path | str | None,
    execute_dexscreener: bool,
    paths: dict[str, Path],
    adapter: Any | None,
    workers: int,
) -> dict[str, Any]:
    context = _select_existing(base, ["launch_id", "mint", "token_mint", "launch_ts", "milestone_tier"])
    if "mint" not in context.columns and "token_mint" in context.columns:
        context["mint"] = context["token_mint"]
    if "token_mint" not in context.columns and "mint" in context.columns:
        context["token_mint"] = context["mint"]

    candidate_context = _candidate_attention_context(candidates_path)
    pair_context = _dexscreener_pair_label_context(dexscreener_pairs_path)
    context = _merge_fill(context, candidate_context, "mint")
    context = _merge_fill(context, pair_context, "mint")

    dex_result = {"rows": [], "raw_responses": [], "requests_used": 0, "errors": [], "execute_completed": False}
    if execute_dexscreener:
        mints = sorted(set(context["mint"].dropna().astype(str))) if "mint" in context.columns else []
        dex_client = adapter or DexScreenerTokenBatchAdapter.from_env()
        dex_result = dex_client.fetch_tokens_for_mints(mints, workers=workers, batch_size=30)
        dex_result["execute_completed"] = True
        dex_context = _dexscreener_token_context(context, dex_result.get("rows") or [])
        context = _merge_fill(context, dex_context, "launch_id")
        _write_jsonl(paths["dexscreener_token_raw_path"], dex_result.get("raw_responses", []))

    topicality = _topicality_layer(context)
    visibility = _visibility_context_layer(context)
    metadata_quality = _metadata_quality_layer(context)
    source_audit = _visibility_source_audit(
        base=context,
        candidate_context=candidate_context,
        pair_context=pair_context,
        execute_dexscreener=execute_dexscreener,
        dex_result=dex_result,
    )
    summary = _attention_visibility_summary(
        base=context,
        topicality=topicality,
        visibility=visibility,
        metadata_quality=metadata_quality,
        source_audit=source_audit,
    )
    return {
        "topicality": topicality,
        "visibility": visibility,
        "metadata_quality": metadata_quality,
        "source_audit": source_audit,
        "summary": summary,
        "dexscreener_execute_completed": bool(dex_result.get("execute_completed")),
        "dexscreener_calls_used": int(dex_result.get("requests_used") or 0),
        "dexscreener_errors": list(dex_result.get("errors") or []),
    }


class DexScreenerTokenBatchAdapter:
    def __init__(self, ingestor: DexScreenerRealIngestor | None = None):
        self.ingestor = ingestor or DexScreenerRealIngestor()

    @classmethod
    def from_env(cls) -> "DexScreenerTokenBatchAdapter":
        return cls(DexScreenerRealIngestor())

    def fetch_tokens_for_mints(
        self,
        mints: list[str],
        *,
        workers: int = 8,
        batch_size: int = 30,
    ) -> dict[str, Any]:
        batches = [mints[i : i + batch_size] for i in range(0, len(mints), batch_size)]
        raw_responses: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        requests_used = 0
        if not batches:
            return {
                "execute_completed": True,
                "requests_used": 0,
                "raw_responses": [],
                "rows": [],
                "errors": [],
            }
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(self.ingestor.fetch_tokens, batch): (index, batch)
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                index, batch = futures[future]
                try:
                    response_rows = list(future.result())
                except Exception as exc:
                    errors.append(f"batch_{index}: {exc}")
                    continue
                requests_used += 1
                rows.extend(response_rows)
                raw_responses.append({"batch_index": index, "mints": batch, "response_rows": response_rows})
        raw_responses.sort(key=lambda row: row["batch_index"])
        return {
            "execute_completed": True,
            "requests_used": requests_used,
            "raw_responses": raw_responses,
            "rows": rows,
            "errors": errors,
        }


def _candidate_attention_context(path: Path | str | None) -> pd.DataFrame:
    candidates = _load_optional_frame(path)
    if candidates.empty:
        return pd.DataFrame(columns=["mint"])
    mint_column = "token_mint" if "token_mint" in candidates.columns else "mint" if "mint" in candidates.columns else None
    if mint_column is None:
        return pd.DataFrame(columns=["mint"])
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        metadata = _metadata_dict(row.get("metadata_json"))
        rows.append(
            {
                "mint": row.get(mint_column),
                "token_name": _first_present(row, metadata, ["token_name", "name", "base_token_name"]),
                "token_symbol": _first_present(row, metadata, ["token_symbol", "symbol", "base_token_symbol"]),
                "metadata_uri": _first_present(row, metadata, ["metadata_uri", "uri"]),
                "image_uri": _first_present(row, metadata, ["image_uri", "image", "image_url", "logo_uri"]),
                "website_url": _first_present(row, metadata, ["website", "website_url", "url"]),
                "twitter_url": _first_present(row, metadata, ["twitter", "twitter_url", "x_url"]),
                "telegram_url": _first_present(row, metadata, ["telegram", "telegram_url"]),
                "discord_url": _first_present(row, metadata, ["discord", "discord_url"]),
                "metadata_source": "local_candidate_metadata",
                "visibility_source": "local_candidate_metadata",
            }
        )
    result = pd.DataFrame(rows)
    return result.dropna(subset=["mint"]).drop_duplicates("mint", keep="first")


def _dexscreener_pair_label_context(path: Path | str | None) -> pd.DataFrame:
    pairs = _load_optional_frame(path)
    if pairs.empty or "mint" not in pairs.columns:
        return pd.DataFrame(columns=["mint"])
    result = _select_existing(
        pairs,
        [
            "mint",
            "dex_pair_detected",
            "dexscreener_url",
            "pair_created_at",
            "dex_id",
            "liquidity_usd",
        ],
    ).drop_duplicates("mint", keep="first")
    if result.empty:
        return result
    result["pair_visible_on_dexscreener"] = result.get("dex_pair_detected", pd.Series(False, index=result.index)).fillna(False)
    result["dexscreener_profile_present"] = result["pair_visible_on_dexscreener"]
    result["visibility_source"] = "local_dexscreener_pair_labels"
    return result


def _dexscreener_token_context(base: pd.DataFrame, pair_rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not pair_rows or base.empty:
        return pd.DataFrame(columns=["launch_id"])
    pairs_by_mint: dict[str, list[dict[str, Any]]] = {}
    for pair in pair_rows:
        mint = _dexscreener_pair_token_mint(pair)
        if mint:
            pairs_by_mint.setdefault(str(mint), []).append(pair)
    rows = []
    for _, launch in base.iterrows():
        mint = launch.get("mint") or launch.get("token_mint")
        pair = _best_visibility_pair(launch, pairs_by_mint.get(str(mint), []))
        if not pair:
            continue
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        info = pair.get("info") if isinstance(pair.get("info"), dict) else {}
        links = _dexscreener_links(info)
        rows.append(
            {
                "launch_id": launch.get("launch_id"),
                "mint": mint,
                "token_name": base_token.get("name"),
                "token_symbol": base_token.get("symbol"),
                "image_uri": info.get("imageUrl") or info.get("openGraph"),
                "website_url": links.get("website_url"),
                "twitter_url": links.get("twitter_url"),
                "telegram_url": links.get("telegram_url"),
                "discord_url": links.get("discord_url"),
                "dexscreener_url": pair.get("url"),
                "pair_created_at": pair.get("pairCreatedAt"),
                "dex_id": pair.get("dexId"),
                "pair_visible_on_dexscreener": True,
                "dexscreener_profile_present": True,
                "dexscreener_boost_present": _has_active_boost(pair.get("boosts")),
                "dexscreener_paid_order_present": _has_paid_order(pair),
                "profile_image_present": _present_text(info.get("imageUrl") or info.get("openGraph")),
                "metadata_source": "dexscreener_tokens_batch",
                "visibility_source": "dexscreener_tokens_batch",
            }
        )
    return pd.DataFrame(rows).drop_duplicates("launch_id", keep="first") if rows else pd.DataFrame(columns=["launch_id"])


def _topicality_layer(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in context.iterrows():
        name = _clean_text(row.get("token_name"))
        symbol = _clean_text(row.get("token_symbol"))
        category, confidence = _categorize_topicality(name, symbol)
        rows.append(
            {
                "launch_id": row.get("launch_id"),
                "token_name": name,
                "token_symbol": symbol,
                "token_name_length": len(name) if name else pd.NA,
                "token_symbol_length": len(symbol) if symbol else pd.NA,
                "has_number_in_name": bool(re.search(r"\d", name)) if name else False,
                "has_number_in_symbol": bool(re.search(r"\d", symbol)) if symbol else False,
                "has_emoji_like_text": _has_emoji_like_text(f"{name} {symbol}"),
                "meme_category": category if category in {"animal", "generic meme", "internet culture"} else "unknown",
                "topicality_category": category,
                "narrative_bucket": category,
                "narrative_confidence": confidence,
                "topicality_flag": category not in {"unknown", "generic meme"},
                "metadata_available": _row_metadata_available(row),
                "metadata_source": _metadata_source(row),
                "topicality_missing_reason": None if category != "unknown" else "token_name_symbol_unavailable_or_uncategorized",
            }
        )
    return pd.DataFrame(rows)


def _visibility_context_layer(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in context.iterrows():
        website = _present_text(row.get("website_url"))
        twitter = _present_text(row.get("twitter_url"))
        telegram = _present_text(row.get("telegram_url"))
        discord = _present_text(row.get("discord_url"))
        image = _truthy(row.get("profile_image_present")) or _present_text(row.get("image_uri"))
        pair_visible = _truthy(row.get("pair_visible_on_dexscreener"))
        social_count = sum([website, twitter, telegram, discord])
        pair_ts = _pair_created_seconds(row.get("pair_created_at"))
        launch_ts = _int_or_none(row.get("launch_ts"))
        lag = pair_ts - launch_ts if pair_ts is not None and launch_ts is not None else pd.NA
        complete = bool(pair_visible and image and (social_count > 0 or website))
        visible = bool(pair_visible or image or social_count > 0)
        rows.append(
            {
                "launch_id": row.get("launch_id"),
                "website_present": website,
                "twitter_present": twitter,
                "telegram_present": telegram,
                "discord_present": discord,
                "social_link_count": social_count,
                "profile_image_present": image,
                "profile_complete_flag": complete,
                "dexscreener_profile_present": _truthy(row.get("dexscreener_profile_present")),
                "dexscreener_boost_present": _truthy(row.get("dexscreener_boost_present")),
                "dexscreener_paid_order_present": _truthy(row.get("dexscreener_paid_order_present")),
                "pair_visible_on_dexscreener": pair_visible,
                "visibility_source": row.get("visibility_source") if _present_text(row.get("visibility_source")) else None,
                "visibility_confidence": _visibility_confidence(pair_visible, social_count, image),
                "missing_reason": None if visible else "visibility_context_unavailable",
                "dexscreener_first_seen_available": pair_ts is not None,
                "time_to_dexscreener_visibility": lag,
                "visibility_lag_from_launch": lag,
                "dexscreener_calls_used": 0,
                "visibility_attention_context_available": visible,
                "visibility_attention_missing_reason": None if visible else "visibility_context_unavailable",
            }
        )
    return pd.DataFrame(rows)


def _metadata_quality_layer(context: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in context.iterrows():
        name = _present_text(row.get("token_name"))
        symbol = _present_text(row.get("token_symbol"))
        metadata_uri = _present_text(row.get("metadata_uri"))
        image = _present_text(row.get("image_uri")) or _truthy(row.get("profile_image_present"))
        website = _present_text(row.get("website_url"))
        twitter = _present_text(row.get("twitter_url"))
        telegram = _present_text(row.get("telegram_url"))
        score = sum([name, symbol, metadata_uri, image, website, twitter or telegram]) / 6
        available = score > 0
        rows.append(
            {
                "launch_id": row.get("launch_id"),
                "metadata_available": available,
                "metadata_uri_present": metadata_uri,
                "image_present": image,
                "website_present": website,
                "twitter_present": twitter,
                "telegram_present": telegram,
                "metadata_completeness_score": round(float(score), 4),
                "metadata_quality_bucket": _metadata_quality_bucket(score),
                "metadata_missing_reason": None if available else "metadata_context_unavailable",
            }
        )
    return pd.DataFrame(rows)


def _visibility_source_audit(
    *,
    base: pd.DataFrame,
    candidate_context: pd.DataFrame,
    pair_context: pd.DataFrame,
    execute_dexscreener: bool,
    dex_result: dict[str, Any],
) -> dict[str, Any]:
    total = int(len(base))
    base_mints = set(base["mint"].dropna().astype(str)) if "mint" in base else set()
    candidate_mints = set(candidate_context["mint"].dropna().astype(str)) if "mint" in candidate_context else set()
    candidate_covered = len(base_mints & candidate_mints)
    if not pair_context.empty and "mint" in pair_context:
        visible_pairs = pair_context[pair_context.get("pair_visible_on_dexscreener", pd.Series(False, index=pair_context.index)).fillna(False)]
        pair_covered = len(base_mints & set(visible_pairs["mint"].dropna().astype(str)))
    else:
        pair_covered = 0
    dex_mints = {
        str(_dexscreener_pair_token_mint(row))
        for row in dex_result.get("rows", [])
        if _dexscreener_pair_token_mint(row)
    }
    dex_covered = len(base_mints & dex_mints)
    return {
        "report_id": "attention_visibility_source_audit_v0",
        "sources": [
            _source_row("launch_metadata", "partial" if total else "unavailable", "local", 0, total, total, "launch id, mint, launch timestamp, milestone tier"),
            _source_row("token_metadata", "partial" if candidate_covered else "unavailable", "local", 0, candidate_covered, total, "candidate metadata only when name/symbol/link fields were captured"),
            _source_row("dexscreener_pair_labels", "partial" if pair_covered else "unavailable", "local", 0, pair_covered, total, "pair visibility, pair creation timestamp, dex URL when previously cached"),
            _source_row(
                "dexscreener_tokens_batch",
                "partial" if dex_result.get("rows") else ("available" if execute_dexscreener else "external_not_requested"),
                "external" if execute_dexscreener else "external",
                int(dex_result.get("requests_used") or math.ceil(total / 30) if total else 0),
                dex_covered,
                total,
                "base token name/symbol, pair metadata, image, websites, socials, boosts when returned",
            ),
            _source_row("dexscreener_token_profiles", "unavailable", "external", 1, 0, total, "latest-profile endpoint is not historical for this launch cohort"),
            _source_row("dexscreener_boosts_paid_orders", "partial" if any(_has_active_boost(row.get("boosts")) for row in dex_result.get("rows", [])) else "unavailable", "external", 0, 0, total, "boost indicators are parsed when present in token batch rows"),
        ],
        "external_requests_used": int(dex_result.get("requests_used") or 0),
        "provider_errors": list(dex_result.get("errors") or []),
    }


def _attention_visibility_summary(
    *,
    base: pd.DataFrame,
    topicality: pd.DataFrame,
    visibility: pd.DataFrame,
    metadata_quality: pd.DataFrame,
    source_audit: dict[str, Any],
) -> dict[str, Any]:
    total = int(len(base))
    topicality_covered = int((topicality["topicality_category"] != "unknown").sum()) if not topicality.empty else 0
    visibility_covered = int(visibility["visibility_attention_context_available"].fillna(False).sum()) if not visibility.empty else 0
    metadata_covered = int(metadata_quality["metadata_available"].fillna(False).sum()) if not metadata_quality.empty else 0
    readiness = _attention_visibility_readiness(total, topicality_covered, visibility_covered, metadata_covered)
    return {
        "report_id": "attention_visibility_coverage_summary_v0",
        "readiness_classification": readiness,
        "total_launches": total,
        "topicality_coverage": _coverage_counts(total, topicality_covered),
        "visibility_coverage": _coverage_counts(total, visibility_covered),
        "metadata_quality_coverage": _coverage_counts(total, metadata_covered),
        "coverage_by_milestone_tier": _attention_coverage_by_tier(base, topicality, visibility, metadata_quality),
        "missing_reason_counts": {
            "topicality": _counter_dict(topicality.get("topicality_missing_reason") if not topicality.empty else pd.Series(dtype=object)),
            "visibility": _counter_dict(visibility.get("visibility_attention_missing_reason") if not visibility.empty else pd.Series(dtype=object)),
            "metadata_quality": _counter_dict(metadata_quality.get("metadata_missing_reason") if not metadata_quality.empty else pd.Series(dtype=object)),
        },
        "source_coverage": source_audit["sources"],
        "external_requests_used": source_audit["external_requests_used"],
        "estimated_cost": {
            "helius_credits": 0,
            "dexscreener_requests_used": source_audit["external_requests_used"],
        },
        "guardrails": {
            "thesis_runs": 0,
            "backtests_run": 0,
            "validation_runs": 0,
            "paper_trading_runs": 0,
            "live_trading_runs": 0,
            "trading_logic_added": False,
            "threshold_optimization": False,
            "grid_search": False,
            "ml": False,
        },
    }


def _source_row(
    name: str,
    status: str,
    source_type: str,
    estimated_cost: int,
    covered_rows: int,
    total_rows: int,
    expected_coverage: str,
) -> dict[str, Any]:
    return {
        "source": name,
        "status": status,
        "source_type": source_type,
        "estimated_cost": estimated_cost,
        "covered_rows": int(covered_rows),
        "total_rows": int(total_rows),
        "coverage_pct": round((covered_rows / total_rows) * 100, 4) if total_rows else 0.0,
        "expected_coverage": expected_coverage,
    }


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _first_present(row: pd.Series, metadata: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in row and _present_text(row.get(key)):
            return row.get(key)
        value = metadata.get(key)
        if _present_text(value):
            return value
    return None


def _dexscreener_pair_token_mint(pair: dict[str, Any]) -> str | None:
    base = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
    quote = pair.get("quoteToken") if isinstance(pair.get("quoteToken"), dict) else {}
    base_address = base.get("address")
    quote_address = quote.get("address")
    if base_address in KNOWN_QUOTE_MINTS:
        return quote_address
    return base_address or quote_address


def _best_visibility_pair(launch: pd.Series, pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    solana_pairs = [pair for pair in pairs if pair.get("chainId") == "solana"]
    if not solana_pairs:
        return None
    launch_ts = _int_or_none(launch.get("launch_ts"))
    after_launch = [
        pair for pair in solana_pairs
        if launch_ts is not None and _pair_created_seconds(pair.get("pairCreatedAt")) is not None and _pair_created_seconds(pair.get("pairCreatedAt")) >= launch_ts
    ]
    pool = after_launch or solana_pairs
    return sorted(
        pool,
        key=lambda pair: (
            _pair_created_seconds(pair.get("pairCreatedAt")) is None,
            _pair_created_seconds(pair.get("pairCreatedAt")) or 0,
        ),
    )[0]


def _dexscreener_links(info: dict[str, Any]) -> dict[str, str | None]:
    result = {"website_url": None, "twitter_url": None, "telegram_url": None, "discord_url": None}
    websites = info.get("websites") if isinstance(info.get("websites"), list) else []
    for website in websites:
        if isinstance(website, dict) and _present_text(website.get("url")) and result["website_url"] is None:
            result["website_url"] = str(website.get("url"))
    socials = info.get("socials") if isinstance(info.get("socials"), list) else []
    for social in socials:
        if not isinstance(social, dict):
            continue
        kind = str(social.get("type") or social.get("label") or "").lower()
        url = social.get("url")
        if not _present_text(url):
            continue
        if ("twitter" in kind or kind == "x") and result["twitter_url"] is None:
            result["twitter_url"] = str(url)
        elif "telegram" in kind and result["telegram_url"] is None:
            result["telegram_url"] = str(url)
        elif "discord" in kind and result["discord_url"] is None:
            result["discord_url"] = str(url)
    return result


def _has_active_boost(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(_int_or_none(value.get("active")) or _int_or_none(value.get("amount")))
    return bool(value)


def _has_paid_order(pair: dict[str, Any]) -> bool:
    for key in ("paidOrder", "paidOrders", "orders"):
        value = pair.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, bool):
            return value
    return False


def _clean_text(value: Any) -> str | None:
    if not _present_text(value):
        return None
    return str(value).strip()


def _categorize_topicality(name: str | None, symbol: str | None) -> tuple[str, str]:
    text = f" {name or ''} {symbol or ''} ".lower()
    categories = [
        ("animal", ["dog", "doge", "cat", "shib", "frog", "pepe", "goat", "monkey", "ape", "bird", "fish"]),
        ("AI", [" ai ", "gpt", "robot", "agent", "neural", "compute"]),
        ("politics", ["trump", "biden", "maga", "vote", "president", "senate", "governor"]),
        ("celebrity", ["elon", "taylor", "kanye", "ye ", "drake", "celebrity"]),
        ("crypto", ["btc", "bitcoin", "eth", "ethereum", "sol ", "solana", "crypto", "pump"]),
        ("sports", ["sports", "nba", "nfl", "mlb", "soccer", "football", "ufc"]),
        ("internet culture", ["meme", "viral", "based", "chad", "wojak", "troll"]),
        ("event driven", ["2026", "2025", "launch", "event", "news"]),
    ]
    for category, keywords in categories:
        if any(keyword in text for keyword in keywords):
            return category, "medium"
    if _present_text(name) or _present_text(symbol):
        return "generic meme", "low"
    return "unknown", "none"


def _has_emoji_like_text(text: str) -> bool:
    if not text:
        return False
    return any(ord(char) > 127 for char in text) or bool(re.search(r":[a-z0-9_+-]+:", text.lower()))


def _row_metadata_available(row: pd.Series) -> bool:
    fields = [
        "token_name",
        "token_symbol",
        "metadata_uri",
        "image_uri",
        "website_url",
        "twitter_url",
        "telegram_url",
        "discord_url",
    ]
    return any(_present_text(row.get(field)) for field in fields)


def _metadata_source(row: pd.Series) -> str | None:
    for field in ("metadata_source", "visibility_source"):
        if _present_text(row.get(field)):
            return str(row.get(field))
    return None


def _visibility_confidence(pair_visible: bool, social_count: int, image: bool) -> str:
    if pair_visible and social_count and image:
        return "high"
    if pair_visible or social_count or image:
        return "medium"
    return "none"


def _metadata_quality_bucket(score: float) -> str:
    if score >= 0.75:
        return "complete"
    if score >= 0.33:
        return "partial"
    if score > 0:
        return "minimal"
    return "missing"


def _pair_created_seconds(value: Any) -> int | None:
    raw = _int_or_none(value)
    if raw is None:
        return None
    return raw // 1000 if raw > 10_000_000_000 else raw


def _attention_visibility_readiness(
    total: int,
    topicality_covered: int,
    visibility_covered: int,
    metadata_covered: int,
) -> str:
    if not total or (topicality_covered == 0 and visibility_covered == 0 and metadata_covered == 0):
        return "attention_visibility_layer_blocked"
    minimum_meaningful_rows = max(25, math.ceil(total * 0.05))
    if (
        topicality_covered >= minimum_meaningful_rows
        and visibility_covered >= minimum_meaningful_rows
        and metadata_covered >= minimum_meaningful_rows
    ):
        return "attention_visibility_layer_ready"
    return "attention_visibility_layer_partial"


def _coverage_counts(total: int, covered: int) -> dict[str, Any]:
    return {
        "covered_rows": int(covered),
        "total_rows": int(total),
        "missing_rows": int(total - covered),
        "coverage_pct": round((covered / total) * 100, 4) if total else 0.0,
    }


def _attention_coverage_by_tier(
    base: pd.DataFrame,
    topicality: pd.DataFrame,
    visibility: pd.DataFrame,
    metadata_quality: pd.DataFrame,
) -> dict[str, Any]:
    if base.empty or "milestone_tier" not in base.columns:
        return {}
    merged = _select_existing(base, ["launch_id", "milestone_tier"])
    merged = _merge_fill(merged, topicality[["launch_id", "topicality_category"]], "launch_id")
    merged = _merge_fill(merged, visibility[["launch_id", "visibility_attention_context_available"]], "launch_id")
    merged = _merge_fill(merged, metadata_quality[["launch_id", "metadata_available"]], "launch_id")
    result = {}
    for tier, group in merged.groupby("milestone_tier", dropna=False):
        total = len(group)
        result[str(tier)] = {
            "total_rows": int(total),
            "topicality_covered": int((group["topicality_category"] != "unknown").sum()) if "topicality_category" in group else 0,
            "visibility_covered": int(group.get("visibility_attention_context_available", pd.Series(False, index=group.index)).fillna(False).sum()),
            "metadata_quality_covered": int(group.get("metadata_available", pd.Series(False, index=group.index)).fillna(False).sum()),
        }
    return result


def _counter_dict(values: pd.Series) -> dict[str, int]:
    cleaned = [str(value) if _present_text(value) else "none" for value in values.tolist()]
    return dict(Counter(cleaned))


def _build_contract_authority_layer(
    base: pd.DataFrame,
    *,
    execute_helius: bool,
    paths: dict[str, Path],
    adapter: Any | None,
    workers: int,
) -> dict[str, Any]:
    layer = _select_existing(base, ["launch_id", "mint", "token_mint"])
    if "mint" not in layer.columns and "token_mint" in layer.columns:
        layer["mint"] = layer["token_mint"]
    if not execute_helius:
        layer["contract_authority_context_available"] = False
        layer["mint_authority_known"] = False
        layer["freeze_authority_known"] = False
        layer["contract_authority_missing_reason"] = "contract_authority_metadata_not_available_in_local_artifacts"
        return {"layer": layer, "execute_completed": False, "requests_used": 0, "errors": []}

    mints = sorted(set(layer["mint"].dropna().astype(str))) if "mint" in layer.columns else []
    client = adapter or HeliusMintAccountBatchAdapter.from_env()
    result = client.fetch_mint_accounts(mints, workers=workers, batch_size=100)
    _write_jsonl(paths["contract_authority_raw_path"], result.get("raw_responses", []))
    authority_rows = pd.DataFrame(result.get("rows") or [])
    if authority_rows.empty:
        layer["contract_authority_context_available"] = False
        layer["mint_authority_known"] = False
        layer["freeze_authority_known"] = False
        layer["contract_authority_missing_reason"] = "contract_authority_fetch_returned_no_rows"
    else:
        layer = layer.merge(authority_rows.drop_duplicates("mint"), on="mint", how="left", suffixes=("", "__authority"))
        layer["contract_authority_context_available"] = layer[
            "contract_authority_context_available"
        ].fillna(False)
        layer["mint_authority_known"] = layer.get("mint_authority", pd.Series(index=layer.index)).notna()
        layer["freeze_authority_known"] = layer.get("freeze_authority", pd.Series(index=layer.index)).notna()
        layer["contract_authority_missing_reason"] = layer[
            "contract_authority_missing_reason"
        ].where(
            ~layer["contract_authority_context_available"],
            None,
        )
    return {
        "layer": layer,
        "execute_completed": True,
        "requests_used": int(result.get("requests_used") or 0),
        "errors": list(result.get("errors") or []),
    }


class HeliusMintAccountBatchAdapter:
    def __init__(self, rpc: HeliusHistoricalAdapter | None = None):
        self.rpc = rpc or HeliusHistoricalAdapter.from_env(timeout_sec=45)

    @classmethod
    def from_env(cls) -> "HeliusMintAccountBatchAdapter":
        return cls(HeliusHistoricalAdapter.from_env(timeout_sec=45))

    def fetch_mint_accounts(
        self,
        mints: list[str],
        *,
        workers: int = 8,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        batches = [mints[i : i + batch_size] for i in range(0, len(mints), batch_size)]
        raw_responses: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        requests_used = 0
        if not batches:
            return {"requests_used": 0, "raw_responses": [], "rows": [], "errors": []}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(self._fetch_batch, batch, index): (index, batch)
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                index, batch = futures[future]
                try:
                    response = future.result()
                except Exception as exc:
                    errors.append(f"batch_{index}: {exc}")
                    continue
                requests_used += 1
                raw_responses.append({"batch_index": index, "mints": batch, "response": response})
                rows.extend(_parse_get_multiple_accounts_response(batch, response))
        raw_responses.sort(key=lambda row: row["batch_index"])
        rows.sort(key=lambda row: row["mint"])
        return {
            "requests_used": requests_used,
            "raw_responses": raw_responses,
            "rows": rows,
            "errors": errors,
        }

    def _fetch_batch(self, batch: list[str], batch_index: int) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": f"mtp-contract-authority-{batch_index}",
            "method": "getMultipleAccounts",
            "params": [
                batch,
                {"encoding": "jsonParsed"},
            ],
        }
        response = self.rpc._http_post(self.rpc.build_rpc_url(), payload, self.rpc.timeout_sec)
        if "error" in response:
            raise RuntimeError(f"Helius RPC error: {response['error']}")
        return response


def _parse_get_multiple_accounts_response(mints: list[str], response: dict[str, Any]) -> list[dict[str, Any]]:
    values = ((response.get("result") or {}).get("value") or [])
    rows: list[dict[str, Any]] = []
    for mint, account in zip(mints, values, strict=False):
        if not isinstance(account, dict):
            rows.append(
                {
                    "mint": mint,
                    "contract_authority_context_available": False,
                    "mint_authority": None,
                    "freeze_authority": None,
                    "decimals": None,
                    "supply": None,
                    "contract_authority_source": "helius_getMultipleAccounts_jsonParsed",
                    "contract_authority_missing_reason": "mint_account_missing",
                }
            )
            continue
        parsed = ((account.get("data") or {}).get("parsed") or {})
        info = parsed.get("info") or {}
        rows.append(
            {
                "mint": mint,
                "contract_authority_context_available": True,
                "mint_authority": info.get("mintAuthority"),
                "freeze_authority": info.get("freezeAuthority"),
                "decimals": info.get("decimals"),
                "supply": info.get("supply"),
                "contract_authority_source": "helius_getMultipleAccounts_jsonParsed",
                "contract_authority_missing_reason": None,
            }
        )
    return rows


def _build_master(
    *,
    base: pd.DataFrame,
    fdv: pd.DataFrame,
    top_holder: pd.DataFrame,
    early_buyer: pd.DataFrame,
    creator_funder: pd.DataFrame,
    cluster: pd.DataFrame,
    distribution: pd.DataFrame,
    visible_flow: pd.DataFrame,
    topicality: pd.DataFrame,
    visibility: pd.DataFrame,
    metadata_quality: pd.DataFrame,
    contract: pd.DataFrame,
) -> pd.DataFrame:
    master = _select_existing(
        base,
        [
            "launch_id",
            "mint",
            "token_mint",
            "creator",
            "launch_time",
            "launch_ts",
            "launch_date",
            "milestone_tier",
            "trigger_fdv_proxy",
            "peak_fdv_proxy",
        ],
    )
    for layer in [
        fdv,
        top_holder,
        early_buyer,
        creator_funder,
        cluster,
        distribution,
        visible_flow,
        topicality,
        visibility,
        metadata_quality,
        contract,
    ]:
        master = _merge_fill(master, layer, "launch_id")

    master["has_fdv_efficiency_layer"] = master.get("fdv_per_event_at_20k", pd.Series(index=master.index)).notna()
    master["has_top_holder_layer"] = master.get("top_holder_share_proxy", pd.Series(index=master.index)).notna()
    master["has_early_buyer_history_layer"] = master.get("early_buyer_wallet_count", pd.Series(index=master.index)).notna()
    master["has_creator_funder_layer"] = master.get("candidate_funder", pd.Series(index=master.index)).notna()
    master["has_cluster_proxy_layer"] = master.get("repeated_actor_overlap_proxy", pd.Series(index=master.index)).notna()
    master["has_distribution_layer"] = master.get("sell_count_at_20k", pd.Series(index=master.index)).notna()
    master["has_visible_attention_and_flow_layer"] = (
        master.get("first_60s_buy_count", pd.Series(index=master.index)).notna()
        | master.get("pair_migration_liquidity_delay_proxy", pd.Series(index=master.index)).notna()
        | master.get("early_holder_concentration", pd.Series(index=master.index)).notna()
    )
    master["has_topicality_layer"] = (
        master.get("topicality_category", pd.Series("unknown", index=master.index)).fillna("unknown") != "unknown"
    )
    master["has_visibility_layer"] = master.get("visibility_attention_context_available", pd.Series(False, index=master.index)).fillna(False)
    master["has_metadata_quality_layer"] = master.get("metadata_available", pd.Series(False, index=master.index)).fillna(False)
    master["has_contract_layer"] = master.get("contract_authority_context_available", pd.Series(False, index=master.index)).fillna(False)
    master["has_core_entry_side_layers"] = (
        master["has_fdv_efficiency_layer"] & master["has_cluster_proxy_layer"] & master["has_distribution_layer"]
    )
    master["has_core_hidden_structure_layers"] = (
        master["has_top_holder_layer"] & master["has_early_buyer_history_layer"] & master["has_creator_funder_layer"]
    )
    master["full_enrichment_confidence"] = master["has_core_entry_side_layers"].map(
        lambda ok: "local_core_entry_complete" if ok else "local_core_entry_partial"
    )
    master["full_enrichment_missing_reason"] = master.apply(_master_missing_reason, axis=1)
    return master.sort_values("launch_id").reset_index(drop=True)


def _master_missing_reason(row: pd.Series) -> str | None:
    missing = []
    if not bool(row.get("has_core_hidden_structure_layers")):
        missing.append("some_hidden_structure_layers_missing")
    if not bool(row.get("has_visibility_layer")):
        missing.append("visibility_context_not_fetched")
    if not bool(row.get("has_contract_layer")):
        missing.append("contract_authority_context_not_fetched")
    return ";".join(missing) if missing else None


def _build_target_registry(master: pd.DataFrame) -> dict[str, Any]:
    return {
        "launches": int(master["launch_id"].nunique()) if "launch_id" in master else 0,
        "mints": int(master["mint"].nunique(dropna=True)) if "mint" in master else 0,
        "creators": int(master["creator"].nunique(dropna=True)) if "creator" in master else 0,
        "candidate_funders": int(master["candidate_funder"].nunique(dropna=True)) if "candidate_funder" in master else 0,
        "early_buyer_launches": int(master.get("has_early_buyer_history_layer", pd.Series(dtype=bool)).sum()),
        "top_holder_launches": int(master.get("has_top_holder_layer", pd.Series(dtype=bool)).sum()),
    }


def _write_layers(
    *,
    paths: dict[str, Path],
    fdv: pd.DataFrame,
    top_holder: pd.DataFrame,
    early_buyer: pd.DataFrame,
    creator_funder: pd.DataFrame,
    cluster: pd.DataFrame,
    distribution: pd.DataFrame,
    visible_flow: pd.DataFrame,
    topicality: pd.DataFrame,
    visibility: pd.DataFrame,
    metadata_quality: pd.DataFrame,
    contract: pd.DataFrame,
    master: pd.DataFrame,
) -> None:
    _write_parquet(fdv, paths["fdv_efficiency_parquet_path"])
    _write_parquet_jsonl(top_holder, paths["top_holder_parquet_path"], paths["top_holder_jsonl_path"])
    _write_parquet_jsonl(early_buyer, paths["early_buyer_parquet_path"], paths["early_buyer_jsonl_path"])
    _write_parquet_jsonl(creator_funder, paths["creator_funder_parquet_path"], paths["creator_funder_jsonl_path"])
    _write_parquet(cluster, paths["cluster_parquet_path"])
    _write_parquet(distribution, paths["distribution_parquet_path"])
    _write_parquet_jsonl(visible_flow, paths["visible_attention_flow_parquet_path"], paths["visible_attention_flow_jsonl_path"])
    _write_parquet(topicality, paths["topicality_context_parquet_path"])
    _write_parquet(visibility, paths["visibility_parquet_path"])
    _write_parquet(visibility, paths["visibility_context_parquet_path"])
    _write_parquet(metadata_quality, paths["metadata_quality_context_parquet_path"])
    _write_parquet(contract, paths["contract_parquet_path"])
    _write_parquet_jsonl(master, paths["master_parquet_path"], paths["master_jsonl_path"])


def _write_reports(report: dict[str, Any], paths: dict[str, Path], master: pd.DataFrame) -> None:
    _write_json(paths["coverage_json_path"], report)
    paths["coverage_markdown_path"].write_text(_coverage_markdown(report), encoding="utf-8")
    _write_json(paths["visibility_source_audit_json_path"], report["visibility_source_audit"])
    paths["visibility_source_audit_markdown_path"].write_text(
        _visibility_source_audit_markdown(report["visibility_source_audit"]),
        encoding="utf-8",
    )
    _write_json(paths["attention_visibility_summary_json_path"], report["attention_visibility"])
    paths["attention_visibility_summary_markdown_path"].write_text(
        _attention_visibility_summary_markdown(report["attention_visibility"]),
        encoding="utf-8",
    )
    _write_csv(
        [
            {"layer": layer, **values}
            for layer, values in report["layer_coverage"].items()
        ],
        paths["layer_coverage_csv_path"],
    )
    _write_csv(_coverage_matrix_rows(master, report), paths["coverage_matrix_csv_path"])
    _write_json(paths["manifest_path"], {"report_id": REPORT_ID, "paths": report["paths"]})
    paths["status_path"].parent.mkdir(parents=True, exist_ok=True)
    paths["status_path"].write_text(_status_markdown(report), encoding="utf-8")


def _coverage_matrix_rows(master: pd.DataFrame, report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for column in sorted(master.columns):
        non_null = int(master[column].notna().sum())
        rows.append(
            {
                "field": column,
                "covered_rows": non_null,
                "missing_rows": int(len(master) - non_null),
                "coverage_pct": round((non_null / len(master)) * 100, 4) if len(master) else 0.0,
                "semantic_status": _field_semantic_status(column, report),
            }
        )
    return rows


def _field_semantic_status(column: str, report: dict[str, Any]) -> str:
    if "market_cap" in column:
        return "blocked_true_market_cap_not_claimed"
    if "authority" in column or "visibility" in column:
        return "explicit_external_gap"
    if "proxy" in column:
        return "proxy_not_confirmed_chain_state"
    return "local_enriched"


def _warnings(layer_coverage: dict[str, dict[str, Any]], external_gaps: list[dict[str, str]]) -> list[str]:
    warnings = ["true_market_cap_unavailable", "fdv_proxy_only"]
    warnings.extend(f"external_gap_{gap['field_family']}" for gap in external_gaps)
    for layer, values in layer_coverage.items():
        if values["coverage_pct"] < 100.0:
            warnings.append(f"partial_layer_coverage_{layer}")
    return sorted(set(warnings))


def _external_gaps(layer_coverage: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    gaps = [
        {
            "field_family": "confirmed_full_chain_top_holders",
            "status": "not_fetched",
            "reason": "current holder values are observed replay/proxy fields, not confirmed full-chain snapshots",
        },
    ]
    if (layer_coverage.get("visibility_attention_context") or {}).get("coverage_pct", 0) < 100.0:
        gaps.append(
            {
                "field_family": "visibility_attention_context",
                "status": "partial",
                "reason": "visibility/profile/social context is only available for rows with local or DexScreener evidence",
            }
        )
    if (layer_coverage.get("contract_authority_context") or {}).get("coverage_pct", 0) < 100.0:
        gaps.append(
            {
                "field_family": "contract_authority_context",
                "status": "not_fetched",
                "reason": "mint/freeze authority metadata was not present in local artifacts",
            }
        )
    return gaps


def _first_minute_event_features(
    base: pd.DataFrame,
    events_path: Path | str | None,
    sol_usd_path: Path | str | None,
) -> pd.DataFrame:
    launches = _select_existing(base, ["launch_id", "token_mint", "mint", "launch_ts"])
    if launches.empty:
        return pd.DataFrame()
    if "token_mint" not in launches.columns and "mint" in launches.columns:
        launches["token_mint"] = launches["mint"]
    result = launches[["launch_id"]].copy()
    events = _load_optional_frame(events_path)
    if events.empty or "token_mint" not in events.columns or "block_time" not in events.columns:
        result["first_minute_quote_sol_volume"] = pd.NA
        result["first_minute_usd_volume"] = pd.NA
        result["first_minute_usd_volume_source"] = "event_source_unavailable"
        result["first_60s_buy_count"] = 0
        result["first_60s_unique_buyers"] = 0
        result["first_60s_transfer_count"] = 0
        result["first_60s_transfer_spike_zscore"] = pd.NA
        result["whale_buy_sequence_proxy"] = pd.NA
        return result

    launch_map = launches.dropna(subset=["token_mint"]).drop_duplicates("token_mint")
    events = events.merge(
        launch_map[["launch_id", "token_mint", "launch_ts"]],
        on="token_mint",
        how="inner",
    )
    if events.empty:
        return _first_minute_empty_result(launches)
    events["block_time"] = pd.to_numeric(events["block_time"], errors="coerce")
    events["launch_ts"] = pd.to_numeric(events["launch_ts"], errors="coerce")
    events["launch_age_seconds"] = events["block_time"] - events["launch_ts"]
    first_minute = events[
        events["launch_age_seconds"].notna()
        & (events["launch_age_seconds"] >= 0)
        & (events["launch_age_seconds"] <= 60)
    ].copy()
    if first_minute.empty:
        return _first_minute_empty_result(launches)
    first_minute["is_buy_event"] = first_minute.apply(_is_first_minute_buy_event, axis=1)
    first_minute["quote_qty"] = pd.to_numeric(first_minute.get("quote_qty"), errors="coerce").fillna(0.0)
    transfer_counts = first_minute.groupby("launch_id").size().rename("first_60s_transfer_count")
    buys = first_minute[first_minute["is_buy_event"]].copy()
    if buys.empty:
        buy_features = pd.DataFrame(columns=["launch_id"])
    else:
        buy_group = buys.groupby("launch_id")
        buy_features = pd.DataFrame(
            {
                "launch_id": buy_group.size().index,
                "first_60s_buy_count": buy_group.size().values,
                "first_60s_unique_buyers": buy_group["actor"].nunique(dropna=True).values
                if "actor" in buys.columns
                else buy_group.size().values,
                "first_minute_quote_sol_volume": buy_group["quote_qty"].sum().values,
                "first_minute_max_quote_sol_buy": buy_group["quote_qty"].max().values,
            }
        )
        buy_features["whale_buy_sequence_proxy"] = _safe_div(
            buy_features["first_minute_max_quote_sol_buy"],
            buy_features["first_minute_quote_sol_volume"],
        )
        buy_features = buy_features.drop(columns=["first_minute_max_quote_sol_buy"])

    result = launches[["launch_id", "launch_ts"]].copy()
    result = result.merge(transfer_counts.reset_index(), on="launch_id", how="left")
    result = result.merge(buy_features, on="launch_id", how="left")
    result["first_60s_transfer_count"] = result["first_60s_transfer_count"].fillna(0).astype(int)
    result["first_60s_buy_count"] = result["first_60s_buy_count"].fillna(0).astype(int)
    result["first_60s_unique_buyers"] = result["first_60s_unique_buyers"].fillna(0).astype(int)
    result["first_minute_quote_sol_volume"] = result["first_minute_quote_sol_volume"].where(
        result["first_60s_buy_count"] > 0
    )
    sol_usd = _nearest_sol_usd_by_launch(result[["launch_id", "launch_ts"]], sol_usd_path)
    result = result.merge(sol_usd, on="launch_id", how="left")
    result["first_minute_usd_volume"] = result["first_minute_quote_sol_volume"] * result["sol_usd"]
    result["first_minute_usd_volume_source"] = result.apply(_first_minute_usd_source, axis=1)
    result["first_60s_transfer_spike_zscore"] = _zscore(result["first_60s_transfer_count"])
    return _select_existing(
        result,
        [
            "launch_id",
            "first_minute_usd_volume",
            "first_minute_quote_sol_volume",
            "first_minute_usd_volume_source",
            "first_60s_buy_count",
            "first_60s_unique_buyers",
            "first_60s_transfer_count",
            "first_60s_transfer_spike_zscore",
            "whale_buy_sequence_proxy",
        ],
    )


def _first_minute_empty_result(launches: pd.DataFrame) -> pd.DataFrame:
    result = launches[["launch_id"]].copy()
    result["first_minute_quote_sol_volume"] = pd.NA
    result["first_minute_usd_volume"] = pd.NA
    result["first_minute_usd_volume_source"] = "no_matching_first_60s_events"
    result["first_60s_buy_count"] = 0
    result["first_60s_unique_buyers"] = 0
    result["first_60s_transfer_count"] = 0
    result["first_60s_transfer_spike_zscore"] = 0.0
    result["whale_buy_sequence_proxy"] = pd.NA
    return result


def _is_first_minute_buy_event(row: pd.Series) -> bool:
    side = str(row.get("side") or row.get("event_type") or "").lower()
    venue = str(row.get("venue") or "").lower()
    if "create" in venue:
        return False
    return side in {"accumulate", "buy", "possible_buy"} or "buy" in venue


def _nearest_sol_usd_by_launch(launches: pd.DataFrame, sol_usd_path: Path | str | None) -> pd.DataFrame:
    sol = _load_optional_frame(sol_usd_path)
    result = launches[["launch_id"]].copy()
    if sol.empty or "ts" not in sol.columns or "sol_usd" not in sol.columns or "launch_ts" not in launches.columns:
        result["sol_usd"] = pd.NA
        return result
    left = launches[["launch_id", "launch_ts"]].copy()
    left["launch_ts"] = pd.to_numeric(left["launch_ts"], errors="coerce")
    right = sol[["ts", "sol_usd"]].copy()
    right["ts"] = pd.to_numeric(right["ts"], errors="coerce")
    right["sol_usd"] = pd.to_numeric(right["sol_usd"], errors="coerce")
    left = left.dropna(subset=["launch_ts"]).sort_values("launch_ts")
    right = right.dropna(subset=["ts", "sol_usd"]).sort_values("ts")
    if left.empty or right.empty:
        result["sol_usd"] = pd.NA
        return result
    merged = pd.merge_asof(left, right, left_on="launch_ts", right_on="ts", direction="nearest")
    return result.merge(merged[["launch_id", "sol_usd"]], on="launch_id", how="left")


def _first_minute_usd_source(row: pd.Series) -> str:
    if pd.notna(row.get("first_minute_usd_volume")):
        return "quote_qty_sol_times_local_sol_usd_cache"
    if int(row.get("first_60s_buy_count") or 0) == 0:
        return "no_first_60s_buy_events"
    if pd.isna(row.get("sol_usd")):
        return "sol_usd_cache_missing"
    return "quote_qty_missing"


def _zscore(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    std = numeric.std(ddof=0)
    if not std:
        return pd.Series([0.0] * len(numeric), index=values.index)
    return (numeric - numeric.mean()) / std


def _ensure_column(frame: pd.DataFrame, column: str, default: Any = pd.NA) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index)


def _visible_flow_missing_reason(row: pd.Series) -> str | None:
    missing = []
    if pd.isna(row.get("first_minute_usd_volume")):
        missing.append(str(row.get("first_minute_usd_volume_source") or "first_minute_usd_volume_unavailable"))
    if pd.isna(row.get("first_60s_transfer_spike_zscore")):
        missing.append("first_60s_transfer_spike_zscore_unavailable")
    if pd.isna(row.get("whale_buy_sequence_proxy")):
        missing.append("whale_buy_sequence_proxy_unavailable")
    if pd.isna(row.get("early_holder_concentration")):
        missing.append("early_holder_concentration_unavailable")
    if pd.isna(row.get("deployer_prior_migration_count")):
        missing.append("deployer_prior_migration_count_unavailable")
    if pd.isna(row.get("topicality_flag")):
        missing.append("topicality_source_not_available_in_local_artifacts")
    if pd.isna(row.get("pair_migration_liquidity_delay_proxy")):
        missing.append("pair_migration_liquidity_delay_proxy_unavailable")
    return ";".join(sorted(set(missing))) if missing else None


def _candidate_creator(row: pd.Series) -> str | None:
    metadata = row.get("metadata_json") if "metadata_json" in row else None
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    for key in ("creator", "creator_deployer", "creator_wallet"):
        value = row.get(key) if key in row else None
        if _present_text(value):
            return str(value)
        metadata_value = metadata.get(key)
        if _present_text(metadata_value):
            return str(metadata_value)
    return None


def _leakage_safe_prior_migration_features(
    base: pd.DataFrame,
    migration_labels_path: Path | str | None,
) -> pd.DataFrame:
    result = _select_existing(base, ["launch_id", "creator", "launch_ts"])
    if result.empty:
        return result
    result["leakage_safe_prior_migration_count"] = pd.NA
    result["deployer_prior_migration_count_source"] = pd.NA
    labels = _load_optional_frame(migration_labels_path)
    if labels.empty or "creator" not in labels.columns or "migration_time" not in labels.columns:
        result["deployer_prior_migration_count_source"] = "migration_label_source_unavailable"
        return result
    migrations = labels[["creator", "migration_time"]].copy()
    migrations["creator"] = migrations["creator"].astype(str)
    migrations["migration_ts"] = migrations["migration_time"].apply(_timestamp_to_seconds)
    migrations = migrations.dropna(subset=["creator", "migration_ts"])
    by_creator = {
        creator: sorted(group["migration_ts"].astype(int).tolist())
        for creator, group in migrations.groupby("creator")
    }
    counts = []
    sources = []
    for _, row in result.iterrows():
        creator = row.get("creator")
        launch_ts = _int_or_none(row.get("launch_ts"))
        if not _present_text(creator):
            counts.append(pd.NA)
            sources.append("creator_missing")
            continue
        if launch_ts is None:
            counts.append(pd.NA)
            sources.append("launch_time_missing")
            continue
        prior = [ts for ts in by_creator.get(str(creator), []) if ts < launch_ts]
        counts.append(len(prior))
        sources.append("local_migration_labels_leakage_safe")
    result["leakage_safe_prior_migration_count"] = counts
    result["deployer_prior_migration_count_source"] = sources
    return result


def _timestamp_to_seconds(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return int(value)
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return int(parsed.timestamp())


def _present_text(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return bool(text) and text.lower() not in {"nan", "none", "null"}


def _derive_fdv_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["fdv_per_event_at_20k"] = _coalesce(
        result,
        ["fdv_per_event_at_20k"],
        fallback=_safe_div(result.get("trigger_fdv_proxy"), result.get("event_count_at_20k")),
    )
    result["fdv_per_buy_at_20k"] = _coalesce(
        result,
        ["fdv_per_buy_at_20k"],
        fallback=_safe_div(result.get("trigger_fdv_proxy"), result.get("buy_count_at_20k")),
    )
    result["fdv_per_active_wallet_at_20k"] = _coalesce(
        result,
        ["fdv_per_active_wallet_at_20k"],
        fallback=_safe_div(result.get("trigger_fdv_proxy"), result.get("active_wallets_at_20k")),
    )
    result["fdv_per_holder_at_20k"] = _coalesce(
        result,
        ["fdv_per_holder_at_20k"],
        fallback=_safe_div(result.get("trigger_fdv_proxy"), result.get("holder_count_at_20k")),
    )
    return result


def _safe_div(numerator: Any, denominator: Any) -> pd.Series:
    if numerator is None or denominator is None:
        return pd.Series(dtype=float)
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce").replace(0, pd.NA)
    return num / den


def _coalesce(frame: pd.DataFrame, columns: list[str], fallback: pd.Series | None = None) -> pd.Series:
    values = fallback if fallback is not None else pd.Series([pd.NA] * len(frame), index=frame.index)
    for column in reversed(columns):
        if column in frame.columns:
            values = frame[column].combine_first(values)
    return values


def _merge_fill(left: pd.DataFrame, right: pd.DataFrame, key: str) -> pd.DataFrame:
    if right.empty or key not in right.columns:
        return left
    merged = left.merge(right.drop_duplicates(key), on=key, how="left", suffixes=("", "__new"))
    for column in list(merged.columns):
        if not column.endswith("__new"):
            continue
        original = column.removesuffix("__new")
        if original in merged.columns:
            merged[original] = merged[original].combine_first(merged[column])
            merged = merged.drop(columns=[column])
        else:
            merged = merged.rename(columns={column: original})
    return merged


def _select_existing(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[column for column in columns if column == "launch_id"])
    existing = [column for column in columns if column in frame.columns]
    return frame[existing].copy()


def _concat_existing(paths: list[Path | str]) -> pd.DataFrame:
    frames = [_load_optional_frame(path) for path in paths]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _load_optional_frame(path: Path | str | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    if p.suffix == ".csv":
        return pd.read_csv(p)
    if p.suffix == ".jsonl":
        return pd.read_json(p, orient="records", lines=True)
    return pd.read_parquet(p)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _write_parquet_jsonl(frame: pd.DataFrame, parquet_path: Path, jsonl_path: Path) -> None:
    _write_parquet(frame, parquet_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_json(jsonl_path, orient="records", lines=True, date_format="iso")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=_json_default))
            f.write("\n")


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _json_default(value: Any) -> Any:
    if pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
        return None
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _preflight_markdown(preflight: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Full Structural Enrichment Campaign Preflight",
            "",
            f"- Report id: {preflight['report_id']}",
            f"- Launches planned: {preflight['launches_planned']}",
            f"- Projected Helius credits: {preflight['budget']['projected_helius_credits']}",
            f"- Projected DexScreener calls: {preflight['budget']['projected_dexscreener_calls']}",
            f"- Budget gate: {preflight['budget']['budget_gate_status']}",
            f"- Safe to execute local ETL: {preflight['safe_to_execute']}",
            "",
            "External collection is fail-closed until named bounded targets exist.",
            "",
        ]
    )


def _coverage_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full Structural Enrichment Campaign Coverage",
        "",
        f"- Readiness: {report['readiness_classification']}",
        f"- Launches enriched: {report['launches_enriched']}",
        f"- Master rows: {report['master_rows']}",
        f"- Helius credits used: {report['helius']['credits_used']}",
        f"- DexScreener calls used: {report['dexscreener']['calls_used']}",
        "",
        "## Layer Coverage",
    ]
    for layer, values in report["layer_coverage"].items():
        lines.append(
            f"- {layer}: {values['covered_rows']} / {values['total_rows']} ({values['coverage_pct']}%)"
        )
    lines.extend(["", "## External Gaps"])
    for gap in report["external_gaps"]:
        lines.append(f"- {gap['field_family']}: {gap['reason']}")
    lines.extend(["", "## Warnings"])
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)


def _visibility_source_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Visibility Source Audit",
        "",
        f"- Report id: `{report.get('report_id')}`",
        f"- External requests used: `{report.get('external_requests_used', 0)}`",
        f"- Provider errors: `{report.get('provider_errors', [])}`",
        "",
        "## Sources",
    ]
    for source in report.get("sources", []):
        lines.append(
            f"- {source['source']}: `{source['status']}` / `{source['source_type']}` / "
            f"{source['covered_rows']} of {source['total_rows']} rows / estimated cost `{source['estimated_cost']}`. "
            f"{source['expected_coverage']}"
        )
    lines.append("")
    return "\n".join(lines)


def _attention_visibility_summary_markdown(report: dict[str, Any]) -> str:
    topicality = report.get("topicality_coverage", {})
    visibility = report.get("visibility_coverage", {})
    metadata = report.get("metadata_quality_coverage", {})
    lines = [
        "# Attention Visibility Coverage Summary",
        "",
        f"- Readiness classification: `{report.get('readiness_classification')}`",
        f"- Total launches: `{report.get('total_launches', 0)}`",
        f"- Topicality coverage: `{topicality.get('covered_rows', 0)} / {topicality.get('total_rows', 0)}`",
        f"- Visibility coverage: `{visibility.get('covered_rows', 0)} / {visibility.get('total_rows', 0)}`",
        f"- Metadata quality coverage: `{metadata.get('covered_rows', 0)} / {metadata.get('total_rows', 0)}`",
        f"- External requests used: `{report.get('external_requests_used', 0)}`",
        "",
        "This is data enrichment only. It does not run a thesis, validation, backtest, paper/live trading, optimization, or strategy workflow.",
        "",
        "## Missing Reasons",
    ]
    for family, counts in report.get("missing_reason_counts", {}).items():
        lines.append(f"- {family}: `{counts}`")
    lines.extend(["", "## Source Coverage"])
    for source in report.get("source_coverage", []):
        lines.append(f"- {source['source']}: `{source['status']}` ({source['coverage_pct']}%)")
    lines.append("")
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any]) -> str:
    visible = report["layer_coverage"].get("visible_attention_and_flow", {})
    attention = report["attention_visibility"]
    return "\n".join(
        [
            "# Full Structural Enrichment Campaign Status",
            "",
            f"- Readiness: {report['readiness_classification']}",
            f"- Launches enriched: {report['launches_enriched']}",
            f"- Master rows: {report['master_rows']}",
            f"- Helius credits used: {report['helius']['credits_used']}",
            f"- DexScreener calls used: {report['dexscreener']['calls_used']}",
            "- Scope: data enrichment only; no thesis, validation, backtest, paper/live trading, or strategy logic.",
            "",
            "## Visible Attention And Flow Features",
            "",
            f"- Layer coverage: {visible.get('covered_rows', 0)} / {visible.get('total_rows', 0)}",
            "- Added: first_minute_usd_volume, first_60s_buy_count, first_60s_unique_buyers, first_60s_transfer_spike_zscore, whale_buy_sequence_proxy, early_holder_concentration, deployer_prior_migration_count, topicality_flag, pair_migration_liquidity_delay_proxy.",
            f"- Attention/visibility readiness: {attention.get('readiness_classification')}",
            f"- Topicality coverage: {attention.get('topicality_coverage', {}).get('covered_rows', 0)} / {attention.get('topicality_coverage', {}).get('total_rows', 0)}",
            f"- Visibility coverage: {attention.get('visibility_coverage', {}).get('covered_rows', 0)} / {attention.get('visibility_coverage', {}).get('total_rows', 0)}",
            f"- Metadata quality coverage: {attention.get('metadata_quality_coverage', {}).get('covered_rows', 0)} / {attention.get('metadata_quality_coverage', {}).get('total_rows', 0)}",
            "",
            "## Next Action",
            "",
            "Use the master fingerprint dataset for descriptive review only, or build a separate bounded named-target plan for remaining external gaps.",
            "",
        ]
    )
