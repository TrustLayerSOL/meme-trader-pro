"""Historical Solana meme runner rule-discovery diagnostics.

This module builds descriptive historical reports and a disabled paper/shadow
configuration. It does not place trades, sign transactions, route orders, or
make profitability claims.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_root


REPORT_LABEL = "historical_rule_discovery"
CONFIRMATION_MIN_ROWS = 2
CONFIRMATION_WINDOW_SECONDS = 120.0
LEVELS: dict[str, float] = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
    "10m": 10_000_000.0,
}
PRIMARY_RELATIVE_ROOTS = [
    "data/backtests/structural_enrichment",
    "data/backtests/diagnostics/reports/T011_expanded_rerun",
    "data/backtests/diagnostics/reports/explosive_runner_winner_anatomy_report",
    "data/backtests/diagnostics/reports/structural_wallet_anatomy",
    "data/backtests/diagnostics/reports/repeated_buyer_runner_participation",
    "data/backtests/diagnostics/reports/final_runner_fingerprint",
    "data/backtests/diagnostics/reports/non_fdv_incremental_information_audit",
    "data/backtests/diagnostics/reports/fdv_efficiency_observability",
    "data/backtests/diagnostics/reports/efficient_mover_continuation_anatomy",
    "data/backtests/diagnostics/reports/creator_net_flow_efficient_mover_thesis",
    "data/backtests/diagnostics/reports/efficient_mover_drawdown_recovery",
]
PREFERRED_DATASET_FILES = {
    "master_enriched_runner_fingerprint.parquet",
    "master_enriched_runner_fingerprint.jsonl",
    "master_tier1_tier2_enriched_runner_fingerprint.parquet",
    "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
    "combined_aligned_p0_structural_fingerprint_fdv_repaired.parquet",
    "combined_aligned_p0_structural_fingerprint_fdv_repaired.jsonl",
    "combined_expanded_lifecycle_snapshots.jsonl",
    "expanded_trigger_20k_feature_rows.csv",
    "trigger_20k_feature_rows.csv",
    "drawdown_events.csv",
    "recoverable_vs_terminal_features.csv",
}
GUARDRAILS = [
    "no_private_keys",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_jupiter_calls",
    "no_order_routing",
    "no_live_trading",
    "no_real_pnl_claims",
    "no_profitability_claims",
    "confirmed_milestones_only_where_possible",
]
BUY_FEATURES: dict[str, tuple[str, str, str]] = {
    "fdv_per_event_at_10k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_buy_at_10k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_active_wallet_at_10k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_event_at_15k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_buy_at_15k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_active_wallet_at_15k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_event_at_20k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_buy_at_20k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "fdv_per_active_wallet_at_20k": ("FDV efficiency", "entry_side", "higher_in_stronger_runners"),
    "event_count_at_20k": ("flow/activity", "entry_side", "lower_or_balanced_if_efficiency_high"),
    "buy_count_at_20k": ("flow/activity", "entry_side", "lower_or_balanced_if_efficiency_high"),
    "sell_count_at_20k": ("flow/activity", "entry_side", "lower_in_stronger_runners"),
    "active_wallets_at_20k": ("flow/activity", "entry_side", "lower_or_balanced_if_efficiency_high"),
    "buy_sell_ratio_at_20k": ("flow/activity", "entry_side", "higher_in_stronger_runners"),
    "create_to_20k_seconds": ("speed/timing", "entry_side", "lower_in_stronger_runners"),
    "10k_to_20k_seconds": ("speed/timing", "entry_side", "lower_in_stronger_runners"),
    "early_buyer_with_prior_runner_count": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "early_buyer_with_prior_100k_count": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "early_buyer_with_prior_500k_count": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "early_buyer_with_prior_1m_count": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "smart_money_quality_proxy": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "repeated_buyer_quality_proxy": ("wallet/repeated buyer quality", "entry_side", "higher_in_stronger_runners"),
    "creator_net_flow_sol_before_20k": ("creator/funder structure", "entry_side", "higher_less_extraction_preferred"),
    "creator_direct_sell_amount_sol": ("creator/funder structure", "risk_filter", "lower_in_stronger_runners"),
    "creator_extraction_proxy_before_20k": ("creator/funder structure", "risk_filter", "lower_in_stronger_runners"),
    "shared_funding_proxy": ("creator/funder structure", "risk_filter", "lower_or_context_dependent"),
    "top_holder_share_proxy": ("holder/top-holder concentration", "risk_filter", "lower_in_stronger_runners"),
    "top_10_holder_share_proxy": ("holder/top-holder concentration", "risk_filter", "lower_in_stronger_runners"),
    "early_holder_concentration": ("holder/top-holder concentration", "risk_filter", "lower_in_stronger_runners"),
    "liquidity_proxy_at_20k": ("liquidity/execution", "entry_side", "higher_in_stronger_runners"),
    "exit_liquidity_proxy": ("liquidity/execution", "exit_side", "higher_in_stronger_runners"),
    "estimated_sell_impact_10_sol_at_20k": ("liquidity/execution", "risk_filter", "lower_in_stronger_runners"),
    "estimated_sell_impact_25_sol_at_20k": ("liquidity/execution", "risk_filter", "lower_in_stronger_runners"),
    "synthetic_activity_proxy": ("synthetic/bot activity", "risk_filter", "lower_in_stronger_runners"),
    "wash_trade_proxy_share_before_20k": ("synthetic/bot activity", "risk_filter", "lower_in_stronger_runners"),
    "same_second_buy_count": ("synthetic/bot activity", "risk_filter", "context_dependent"),
    "same_slot_buy_count": ("synthetic/bot activity", "risk_filter", "context_dependent"),
    "bot_sniper_proxy_share": ("synthetic/bot activity", "risk_filter", "lower_in_stronger_runners"),
    "coordinated_timing_proxy": ("synthetic/bot activity", "risk_filter", "lower_in_stronger_runners"),
    "metadata_completeness_score": ("metadata/social/narrative", "entry_side", "higher_in_stronger_runners"),
    "social_link_count": ("metadata/social/narrative", "entry_side", "higher_in_stronger_runners"),
}
EXIT_FEATURES: dict[str, tuple[str, str]] = {
    "first_20pct_drawdown_time": ("drawdown timing", "lower_means_earlier_risk"),
    "first_30pct_drawdown_time": ("drawdown timing", "lower_means_earlier_risk"),
    "first_40pct_drawdown_time": ("drawdown timing", "lower_means_earlier_risk"),
    "first_50pct_drawdown_time": ("drawdown timing", "lower_means_earlier_risk"),
    "recovered_after_20pct": ("reclaim/recovery", "higher_in_recoverable_dips"),
    "recovered_after_30pct": ("reclaim/recovery", "higher_in_recoverable_dips"),
    "recovered_after_40pct": ("reclaim/recovery", "higher_in_recoverable_dips"),
    "recovered_after_50pct": ("reclaim/recovery", "higher_in_recoverable_dips"),
    "no_reclaim_after_5m": ("terminal behavior", "higher_in_terminal_collapses"),
    "no_reclaim_after_10m": ("terminal behavior", "higher_in_terminal_collapses"),
    "terminal_collapse_proxy": ("terminal behavior", "higher_in_terminal_collapses"),
    "inactive_timeout": ("terminal behavior", "higher_in_terminal_collapses"),
    "max_drawdown_after_entry": ("drawdown depth", "higher_in_terminal_collapses"),
}


def build_historical_rule_discovery(
    *,
    data_root: Path | str | None = None,
    source_paths: list[Path | str] | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    root = Path(data_root or data_lake_root()).expanduser()
    report_root = root / "data" / "backtests" / "diagnostics" / "reports" / REPORT_LABEL
    config_path = root / "data" / "forward_observation" / "official_lifecycle_watch_v2" / "historical_rule_paper_shadow_config.json"
    status_path = Path("theses") / "HISTORICAL_RULE_DISCOVERY_STATUS.md"
    sources = [Path(path).expanduser() for path in source_paths] if source_paths else discover_historical_sources(root)
    if not execute:
        return {
            "execute": False,
            "report_root": str(report_root),
            "source_paths": [str(path) for path in sources],
            "readiness_classification": "historical_rule_discovery_ready_for_execute",
        }

    report_root.mkdir(parents=True, exist_ok=True)
    inventory = build_historical_source_inventory(root, source_paths=sources)
    dataset = build_historical_rule_discovery_dataset(root, source_paths=sources)
    split_manifest = build_chronological_split(dataset)
    buy_search = build_broad_buy_side_pattern_search(dataset, split_manifest)
    exit_search = build_broad_exit_side_pattern_search(dataset, split_manifest)
    frameworks = build_candidate_frameworks()
    comparison = build_historical_candidate_rule_comparison(dataset, split_manifest)
    recommendation = select_starting_rule(dataset, buy_search, exit_search, comparison)
    config = build_paper_shadow_config(recommendation)
    summary = build_summary(
        inventory=inventory,
        dataset=dataset,
        split_manifest=split_manifest,
        buy_search=buy_search,
        exit_search=exit_search,
        frameworks=frameworks,
        comparison=comparison,
        recommendation=recommendation,
        report_root=report_root,
        config_path=config_path,
        status_path=status_path,
    )

    _write_csv(report_root / "historical_source_inventory.csv", inventory)
    _write_jsonl(report_root / "historical_rule_discovery_dataset.jsonl", dataset)
    _write_parquet(report_root / "historical_rule_discovery_dataset.parquet", dataset)
    _write_json(report_root / "historical_split_manifest.json", split_manifest)
    _write_csv(report_root / "broad_buy_side_pattern_search.csv", buy_search)
    _write_csv(report_root / "broad_exit_side_pattern_search.csv", exit_search)
    _write_csv(report_root / "candidate_buy_sell_frameworks.csv", frameworks)
    _write_csv(report_root / "historical_candidate_rule_comparison.csv", comparison)
    _write_json(report_root / "historical_rule_discovery_summary.json", summary)
    (report_root / "historical_rule_discovery_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(config_path, config)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(summary), encoding="utf-8")
    return summary


def discover_historical_sources(root: Path | str) -> list[Path]:
    data_root = Path(root).expanduser()
    sources: list[Path] = []
    for relative in PRIMARY_RELATIVE_ROOTS:
        base = data_root / relative
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith("._") and path.suffix in {".jsonl", ".csv", ".parquet", ".json"}:
                sources.append(path)
    return _dedupe_paths(sources)


def build_historical_source_inventory(root: Path | str, *, source_paths: list[Path | str] | None = None) -> list[dict[str, Any]]:
    data_root = Path(root).expanduser()
    paths = [Path(path).expanduser() for path in source_paths] if source_paths else discover_historical_sources(data_root)
    rows: list[dict[str, Any]] = []
    for path in paths:
        records = _read_records(path, sample_limit=None if path.name in PREFERRED_DATASET_FILES else 2_000)
        cols = set(records[0].keys()) if records else _table_columns(path)
        mints = {_mint(row) for row in records if _mint(row)}
        dates = [_date_value(row) for row in records]
        dates = [value for value in dates if value]
        families = _feature_families(cols)
        rows.append(
            {
                "path": str(path),
                "row_count": len(records),
                "mint_count": len(mints),
                "date_start": min(dates) if dates else None,
                "date_end": max(dates) if dates else None,
                "feature_families_available": ";".join(sorted(families)),
                "milestone_labels_available": _yes_no(_has_any(cols, ["milestone", "crossed_", "ever_hit", "peak_fdv"])),
                "path_drawdown_data_available": _yes_no(_has_any(cols, ["drawdown", "snapshot_ts", "fdv_usd", "valuation_proxy"])),
                "holder_wallet_funder_data_available": _yes_no(_has_any(cols, ["holder", "buyer", "funder", "wallet"])),
                "metadata_social_data_available": _yes_no(_has_any(cols, ["metadata", "website", "twitter", "telegram", "discord", "social"])),
                "data_quality_notes": _quality_note(path, records, cols),
                "usable_for_buy_side_discovery": _yes_no(bool(mints) and _has_any(cols, ["fdv_per", "buy_count", "active_wallet", "milestone_tier", "peak_fdv"])),
                "usable_for_exit_side_discovery": _yes_no(_has_any(cols, ["drawdown", "reclaim", "max_fdv", "peak_fdv"])),
                "source_kind": _source_kind(path),
            }
        )
    return rows


def build_historical_rule_discovery_dataset(root: Path | str, *, source_paths: list[Path | str] | None = None) -> list[dict[str, Any]]:
    data_root = Path(root).expanduser()
    paths = [Path(path).expanduser() for path in source_paths] if source_paths else discover_historical_sources(data_root)
    dataset_paths = [path for path in paths if path.name in PREFERRED_DATASET_FILES]
    if not dataset_paths:
        dataset_paths = [path for path in paths if path.suffix in {".jsonl", ".csv", ".parquet"}]
    base_rows: dict[str, dict[str, Any]] = {}
    path_rows_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    drawdown_rows_by_mint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_by_mint: dict[str, set[str]] = defaultdict(set)

    for path in dataset_paths:
        records = _read_records(path)
        kind = _source_kind(path)
        if kind == "lifecycle_snapshots":
            for row in records:
                mint = _mint(row)
                if mint:
                    path_rows_by_mint[mint].append(_normalize_path_row(row, source_path=path))
                    source_by_mint[mint].add(str(path))
            continue
        if "drawdown" in path.name or "recovery" in path.name:
            for row in records:
                mint = _mint(row)
                if mint:
                    drawdown_rows_by_mint[mint].append(row)
                    source_by_mint[mint].add(str(path))
            continue
        for row in records:
            mint = _mint(row)
            if not mint:
                continue
            normalized = _normalize_base_row(row, source_path=path)
            existing = base_rows.get(mint, {})
            base_rows[mint] = _merge_rows(existing, normalized)
            source_by_mint[mint].add(str(path))

    for mint, paths_for_mint in path_rows_by_mint.items():
        path_summary = _aggregate_path_rows(mint, paths_for_mint)
        base_rows[mint] = _merge_rows(base_rows.get(mint, {}), path_summary)
    for mint, drawdown_rows in drawdown_rows_by_mint.items():
        base_rows[mint] = _merge_rows(base_rows.get(mint, {"mint": mint}), _aggregate_drawdowns(mint, drawdown_rows))

    rows: list[dict[str, Any]] = []
    for mint, row in sorted(base_rows.items()):
        finalized = _finalize_dataset_row(row, source_paths=sorted(source_by_mint.get(mint, [])))
        rows.append(finalized)
    split_manifest = build_chronological_split(rows)
    for row in rows:
        row["split"] = split_manifest["mint_to_split"].get(row["mint"], "holdout")
    return rows


def build_chronological_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (_timestamp(row.get("launch_time") or row.get("launch_date") or row.get("launch_ts")) or math.inf, row.get("mint") or ""))
    count = len(ordered)
    if count == 0:
        return {"split_method": "empty", "mint_to_split": {}, "counts": {}}
    enough = sum(1 for row in ordered if _timestamp(row.get("launch_time") or row.get("launch_date") or row.get("launch_ts")) is not None) >= 5
    if enough and count >= 5:
        train_cut = max(1, int(count * 0.60))
        test_cut = max(train_cut + 1, int(count * 0.80))
        method = "60_20_20_chronological"
    else:
        train_cut = max(1, int(count * 0.70))
        test_cut = count
        method = "70_30_chronological"
    mapping: dict[str, str] = {}
    for index, row in enumerate(ordered):
        if index < train_cut:
            split = "discovery_train"
        elif index < test_cut:
            split = "design_test" if method == "60_20_20_chronological" else "holdout"
        else:
            split = "holdout"
        mapping[str(row.get("mint"))] = split
    return {
        "split_method": method,
        "row_count": count,
        "counts": dict(Counter(mapping.values())),
        "mint_to_split": mapping,
        "holdout_locked": True,
        "holdout_tuning_allowed": False,
    }


def build_broad_buy_side_pattern_search(rows: list[dict[str, Any]], split_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feature, (family, side, expected) in BUY_FEATURES.items():
        values = [(row, _num(row.get(feature))) for row in rows if _num(row.get(feature)) is not None]
        if not values:
            out.append(_feature_row(feature, family, side, expected, rows, values, "data_limited"))
            continue
        classification = _classify_buy_feature(feature, family, side, rows, values, split_manifest)
        out.append(_feature_row(feature, family, side, expected, rows, values, classification))
    return out


def build_broad_exit_side_pattern_search(rows: list[dict[str, Any]], split_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feature, (family, expected) in EXIT_FEATURES.items():
        values = [(row, _num(row.get(feature))) for row in rows if _num(row.get(feature)) is not None]
        classification = "data_limited" if not values else _classify_exit_feature(feature, rows, values)
        out.append(_feature_row(feature, family, "exit_side", expected, rows, values, classification))
    return out


def build_candidate_frameworks() -> list[dict[str, Any]]:
    buy_rows = [
        {
            "rule_id": "BROAD_10K_WATCH_20K_BUY",
            "name": "10k watch, confirmed 20k candidate with efficiency",
            "watch_trigger": "confirmed clean 10k promotes to watch",
            "buy_trigger": "confirmed clean 20k candidate",
            "required_confirmation": "two FDV/valuation-proxy rows where possible; no single-row spike",
            "required_early_features": "high FDV efficiency label at or before 20k; positive or balanced buy flow",
            "rejection_filters": "single-row spike; same-timestamp major jump; invalid milestone order; severe synthetic/creator/holder risk",
            "chase_guard": "reject late discovery if first clean path appears only above 20k/30k",
            "data_requirements": "confirmed milestones, early flow counts, FDV efficiency, clean path provenance",
            "why_it_may_work": "Strong runners historically show valuation expansion with fewer/cleaner early events rather than noisy churn alone.",
            "what_invalidates_it": "Efficiency direction disappears in holdout or live-actionable samples.",
            "expected_tradeoff": "Higher precision than threshold-only, lower coverage.",
        },
        {
            "rule_id": "BROAD_15K_BALANCED_BUY",
            "name": "15k balanced early confirmation",
            "watch_trigger": "confirmed clean 10k",
            "buy_trigger": "confirmed clean 15k candidate",
            "required_confirmation": "clean 15k path plus flow/efficiency confirmation",
            "required_early_features": "FDV efficiency plus buy/sell pressure not deteriorating",
            "rejection_filters": "sell pressure, synthetic burst, holder/funder concentration risk",
            "chase_guard": "do not enter if first path row already above 20k",
            "data_requirements": "15k confirmed milestone and early feature snapshots",
            "why_it_may_work": "Earlier than 20k but only after real path confirmation.",
            "what_invalidates_it": "Too many false positives or insufficient live observability before 15k.",
            "expected_tradeoff": "Better entry timing, greater false-positive risk.",
        },
        {
            "rule_id": "BROAD_20K_CONFIRMATION_BUY",
            "name": "Clean 20k confirmation without extra risk filters",
            "watch_trigger": "clean path before 20k where available",
            "buy_trigger": "confirmed clean 20k",
            "required_confirmation": "confirmed 20k, valid milestone ordering, spike rejection",
            "required_early_features": "clean path through 10k/15k/20k where available",
            "rejection_filters": "late discovery/chase, anomalies",
            "chase_guard": "reject first observed FDV above 30k",
            "data_requirements": "confirmed milestones and first path timing",
            "why_it_may_work": "Keeps rule simple while rejecting false FDV proxy rows.",
            "what_invalidates_it": "Confirmed 20k alone fails to separate runners from stalls.",
            "expected_tradeoff": "More coverage, less selectivity.",
        },
        {
            "rule_id": "BROAD_RISK_FILTERED_20K",
            "name": "Risk-filtered clean 20k",
            "watch_trigger": "confirmed clean 10k/15k",
            "buy_trigger": "confirmed clean 20k with no obvious structural risk",
            "required_confirmation": "confirmed 20k plus clean path safety",
            "required_early_features": "FDV efficiency, acceptable creator/funder/holder/synthetic profile",
            "rejection_filters": "creator extraction, high top-holder concentration, synthetic activity, thin exit liquidity",
            "chase_guard": "reject path jumpiness and late discovery",
            "data_requirements": "confirmed milestones, structure sidecars, liquidity/execution proxies",
            "why_it_may_work": "Combines strongest broad separator with risk filters that explain stalls/collapses.",
            "what_invalidates_it": "Risk filters are unavailable live or remove most true runners.",
            "expected_tradeoff": "Best research candidate, but higher live engineering requirement.",
        },
    ]
    exit_rows = [
        {
            "exit_rule_id": "EXIT_NO_RECLAIM",
            "name": "No reclaim after drawdown",
            "applies_after_entry_milestone": "after candidate entry or local high",
            "drawdown_condition": "drawdown from local high",
            "reclaim_grace_condition": "exit label if no reclaim within fixed grace",
            "inactivity_max_age_fallback": "yes",
            "path_evidence_required": "post-entry path rows with local high and drawdown",
            "why_it_may_work": "Recoverable dips usually reclaim; terminal collapses do not.",
            "what_invalidates_it": "Coarse snapshots miss fast reclaims or exits too early before common recovery.",
            "expected_tradeoff": "Simple and explainable, sensitive to data resolution.",
        },
        {
            "exit_rule_id": "EXIT_MILESTONE_TRAIL",
            "name": "Milestone trailing drawdown",
            "applies_after_entry_milestone": "after 20k, 50k, 100k, 500k",
            "drawdown_condition": "drawdown tolerance tightens after higher milestones",
            "reclaim_grace_condition": "grace window before terminal label",
            "inactivity_max_age_fallback": "yes",
            "path_evidence_required": "local high, drawdown, reclaim status",
            "why_it_may_work": "Lets early runners breathe while protecting later gains diagnostically.",
            "what_invalidates_it": "Drawdown/reclaim pattern unstable across splits.",
            "expected_tradeoff": "More adaptive, more fields required.",
        },
        {
            "exit_rule_id": "EXIT_INACTIVE_MAX_AGE",
            "name": "Inactive or max-age fallback",
            "applies_after_entry_milestone": "after entry when path goes quiet",
            "drawdown_condition": "none required",
            "reclaim_grace_condition": "not applicable",
            "inactivity_max_age_fallback": "primary condition",
            "path_evidence_required": "last path time and observation age",
            "why_it_may_work": "Prevents stale positions in dead paths for paper/shadow accounting.",
            "what_invalidates_it": "Live feed gaps mimic inactivity.",
            "expected_tradeoff": "Operational cleanup, not alpha.",
        },
        {
            "exit_rule_id": "EXIT_SCALEOUT_DIAGNOSTIC",
            "name": "Fixed milestone scaleout diagnostic",
            "applies_after_entry_milestone": "after entry reaches future milestones",
            "drawdown_condition": "none",
            "reclaim_grace_condition": "not applicable",
            "inactivity_max_age_fallback": "secondary",
            "path_evidence_required": "confirmed future milestone rows",
            "why_it_may_work": "Compares milestone outcomes without recommending execution.",
            "what_invalidates_it": "Milestone outcomes are contaminated or sparse.",
            "expected_tradeoff": "Diagnostic only, not a sell recommendation.",
        },
    ]
    return buy_rows + exit_rows


def build_historical_candidate_rule_comparison(rows: list[dict[str, Any]], split_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    buy_rule_ids = ["BROAD_10K_WATCH_20K_BUY", "BROAD_15K_BALANCED_BUY", "BROAD_20K_CONFIRMATION_BUY", "BROAD_RISK_FILTERED_20K"]
    exit_rule_ids = ["EXIT_NO_RECLAIM", "EXIT_MILESTONE_TRAIL", "EXIT_INACTIVE_MAX_AGE", "EXIT_SCALEOUT_DIAGNOSTIC"]
    thresholds = _discovery_thresholds(rows)
    out: list[dict[str, Any]] = []
    for buy_rule in buy_rule_ids:
        selected = [row for row in rows if _buy_rule_match(row, buy_rule, thresholds)]
        for exit_rule in exit_rule_ids:
            multiples = [_num(row.get("max_fdv_multiple_after_entry")) for row in selected]
            out.append(
                {
                    "buy_rule_id": buy_rule,
                    "exit_rule_id": exit_rule,
                    "support_count_total": len(selected),
                    "support_count_discovery_train": sum(1 for row in selected if row.get("split") == "discovery_train"),
                    "support_count_design_test": sum(1 for row in selected if row.get("split") == "design_test"),
                    "support_count_holdout": sum(1 for row in selected if row.get("split") == "holdout"),
                    "reached_50k_after_entry": sum(1 for row in selected if row.get("confirmed_crossed_50k") is True),
                    "reached_100k_after_entry": sum(1 for row in selected if row.get("confirmed_crossed_100k") is True),
                    "reached_500k_after_entry": sum(1 for row in selected if row.get("confirmed_crossed_500k") is True),
                    "reached_1m_after_entry": sum(1 for row in selected if row.get("confirmed_crossed_1m") is True),
                    "max_fdv_multiple_after_entry": max([value for value in multiples if value is not None], default=None),
                    "median_max_fdv_multiple_after_entry": _median(multiples),
                    "max_drawdown_after_entry": _max([row.get("max_drawdown_after_entry") for row in selected]),
                    "exit_reason_counts": json.dumps(_exit_reason_counts(selected, exit_rule), sort_keys=True),
                    "runner_miss_count": _runner_miss_count(rows, selected),
                    "exited_before_next_milestone_count": _exited_before_next_milestone_count(selected, exit_rule),
                    "open_data_limited_count": sum(1 for row in selected if row.get("data_limited_flag") is True),
                    "stability_across_time_split": _stability_label(selected),
                    "source_concentration": _source_concentration(selected),
                    "live_fields_available": _yes_no(_live_fields_available_for_rule(buy_rule)),
                    "descriptive_only_no_pnl": True,
                }
            )
    return out


def select_starting_rule(
    rows: list[dict[str, Any]],
    buy_search: list[dict[str, Any]],
    exit_search: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        row
        for row in comparison
        if row.get("buy_rule_id") != "BROAD_20K_CONFIRMATION_BUY"
        and row.get("exit_rule_id") in {"EXIT_NO_RECLAIM", "EXIT_MILESTONE_TRAIL"}
        and int(row.get("support_count_total") or 0) > 0
    ]
    if not eligible:
        eligible = [row for row in comparison if int(row.get("support_count_total") or 0) > 0]
    best = max(eligible, key=_candidate_score, default={})
    support = int(best.get("support_count_total") or 0)
    if support == 0:
        classification = "no_rule_found"
    elif support < 30 or int(best.get("support_count_holdout") or 0) == 0:
        classification = "rule_candidate_promising_but_needs_live_actionability"
    else:
        classification = "historical_rule_ready_for_paper_shadow"
    return {
        "readiness_classification": classification,
        "selected_buy_rule_id": best.get("buy_rule_id") or "BROAD_RISK_FILTERED_20K",
        "selected_exit_rule_id": best.get("exit_rule_id") or "EXIT_MILESTONE_TRAIL",
        "why_selected": "Selected because it requires confirmed 10k watch, confirmed clean 20k candidate, and FDV-efficiency separation instead of letting the broad 20k bucket win on support alone.",
        "why_alternatives_rejected": "Threshold-only 20k had more support but much weaker runner separation; earlier 15k entry has greater live-actionability risk; risk-filtered 20k had lower support and more missing live fields; scaleout is diagnostic only.",
        "required_live_fields": [
            "confirmed_10k_15k_20k_milestones",
            "fdv_efficiency_at_trigger",
            "buy_sell_counts",
            "active_wallet_count",
            "creator_funder_risk_proxies",
            "holder_concentration_proxy",
            "synthetic_activity_proxy",
            "drawdown_reclaim_state",
        ],
        "required_collector_fixes": [
            "confirm milestones with two rows",
            "reject single-row spikes",
            "exclude same-timestamp major jumps from entry",
            "capture early efficiency before/at 10k and 20k",
            "keep metadata out of hot path",
        ],
        "actionability_caveats": "Historical fields are richer than live fields; paper/shadow must verify live availability and latency before any execution work.",
        "invalidation_criteria": [
            "FDV efficiency direction fails in live-actionable paper sample",
            "risk filters remove most future runners",
            "drawdown/reclaim exits fail under higher-resolution live paths",
        ],
        "minimum_paper_shadow_sample_size_before_review": 100,
        "support_count": support,
        "support_count_holdout": int(best.get("support_count_holdout") or 0),
        "median_max_fdv_multiple_after_entry": best.get("median_max_fdv_multiple_after_entry"),
        "live_trading_enabled": False,
        "profitability_claim": "none",
    }


def build_paper_shadow_config(recommendation: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_buy_rule_id": recommendation["selected_buy_rule_id"],
        "selected_exit_rule_id": recommendation["selected_exit_rule_id"],
        "use_confirmed_milestones_only": True,
        "raw_milestones_allowed": False,
        "single_row_spikes_allowed": False,
        "same_timestamp_major_jump_allowed_for_entry": False,
        "live_trading_enabled": False,
        "private_keys_allowed": False,
        "paper_trading_allowed": True,
        "required_live_fields": recommendation["required_live_fields"],
        "reject_reasons": [
            "unconfirmed_milestone",
            "single_row_fdv_proxy_spike",
            "same_timestamp_major_jump",
            "late_discovery_chase",
            "invalid_milestone_ordering",
            "severe_creator_funder_holder_or_synthetic_risk",
        ],
        "sample_size_review_points": [25, 50, 100, 200],
        "no_real_money": True,
        "created_at": _utc_now(),
    }


def build_summary(
    *,
    inventory: list[dict[str, Any]],
    dataset: list[dict[str, Any]],
    split_manifest: dict[str, Any],
    buy_search: list[dict[str, Any]],
    exit_search: list[dict[str, Any]],
    frameworks: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
    recommendation: dict[str, Any],
    report_root: Path,
    config_path: Path,
    status_path: Path,
) -> dict[str, Any]:
    strongest_buy = [row for row in buy_search if row.get("classification") in {"strong_buy_side_candidate", "possible_buy_filter", "possible_risk_filter"}][:10]
    strongest_exit = [row for row in exit_search if row.get("classification") in {"strong_exit_candidate", "possible_exit_filter", "path_exit_candidate"}][:10]
    summary = {
        "execute": True,
        "created_at": _utc_now(),
        "report_id": REPORT_LABEL,
        "historical_rows_analyzed": len(dataset),
        "historical_mints_analyzed": len({row.get("mint") for row in dataset if row.get("mint")}),
        "source_files_inspected": len(inventory),
        "split_design": split_manifest,
        "strongest_buy_side_patterns": strongest_buy,
        "strongest_sell_side_patterns": strongest_exit,
        "candidate_buy_sell_rules": frameworks,
        "selected_paper_shadow_candidate": recommendation,
        "readiness_classification": recommendation["readiness_classification"],
        "live_trading_enabled": False,
        "paper_shadow_only": True,
        "guardrails": GUARDRAILS,
        "limitations": [
            "Historical valuation fields are FDV/valuation proxies unless true market cap availability is explicit.",
            "Some historical sources are diagnostic aggregates, not executable live observations.",
            "No PnL, profitability, or final validation claim is made.",
            "Forward actionability remains a later engineering problem.",
        ],
        "required_live_actionability_work": recommendation["required_collector_fixes"],
        "report_root": str(report_root),
        "config_path": str(config_path),
        "status_file": str(status_path),
        "report_paths": {
            "source_inventory_csv": str(report_root / "historical_source_inventory.csv"),
            "dataset_parquet": str(report_root / "historical_rule_discovery_dataset.parquet"),
            "dataset_jsonl": str(report_root / "historical_rule_discovery_dataset.jsonl"),
            "split_manifest_json": str(report_root / "historical_split_manifest.json"),
            "buy_side_csv": str(report_root / "broad_buy_side_pattern_search.csv"),
            "exit_side_csv": str(report_root / "broad_exit_side_pattern_search.csv"),
            "frameworks_csv": str(report_root / "candidate_buy_sell_frameworks.csv"),
            "comparison_csv": str(report_root / "historical_candidate_rule_comparison.csv"),
            "summary_json": str(report_root / "historical_rule_discovery_summary.json"),
            "summary_md": str(report_root / "historical_rule_discovery_summary.md"),
        },
    }
    return summary


def _normalize_base_row(row: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    mint = _mint(row)
    out: dict[str, Any] = {
        "launch_id": row.get("launch_id") or f"launch-{str(mint)[:16]}",
        "mint": mint,
        "creator": row.get("creator") or row.get("deployer"),
        "source_dataset": source_path.name,
        "source_file": str(source_path),
        "launch_time": row.get("launch_time") or row.get("pool_created_time") or row.get("created_at"),
        "launch_date": row.get("launch_date") or _date_from_any(row.get("launch_time") or row.get("launch_ts")),
        "launch_ts": _num(row.get("launch_ts") or row.get("launch_timestamp") or row.get("create_time")),
        "milestone_tier": row.get("milestone_tier") or _tier_from_row(row),
        "data_quality_flags": [],
    }
    for level in LEVELS:
        out[f"raw_crossed_{level}"] = _crossed_level(row, level)
        out[f"confirmed_crossed_{level}"] = _historical_confirmed_crossed(row, level)
        out[f"first_crossed_{level}_time"] = _first_time(row, level)
    for key in _dataset_feature_keys():
        out[key] = _value(row, key)
    out["max_fdv_after_20k"] = _num(row.get("max_fdv_after_20k") or row.get("peak_fdv_proxy") or row.get("max_fdv_observed"))
    out["max_fdv_observed"] = _num(row.get("peak_fdv_proxy") or row.get("max_fdv_observed") or row.get("trigger_fdv_proxy"))
    out["single_row_spike_flag"] = False
    out["same_timestamp_major_jump_flag"] = False
    out["valid_milestone_ordering"] = True
    out["milestone_provenance"] = "historical_aggregate_or_repaired_enrichment"
    return out


def _normalize_path_row(row: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    return {
        "mint": _mint(row),
        "timestamp": _num(row.get("timestamp") or row.get("snapshot_ts") or row.get("block_time")),
        "fdv_proxy": _num(row.get("fdv_proxy") or row.get("valuation_proxy_usd") or row.get("fdv_usd") or row.get("true_market_cap_usd")),
        "event_count": _num(row.get("event_count") or row.get("tx_count")),
        "buy_count": _num(row.get("buy_count")),
        "sell_count": _num(row.get("sell_count")),
        "active_wallets": _num(row.get("active_wallets") or row.get("active_wallet_count") or row.get("unique_actors")),
        "launch_ts": _num(row.get("launch_ts")),
        "source_file": str(source_path),
    }


def _aggregate_path_rows(mint: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (_num(row.get("timestamp")) is None, _num(row.get("timestamp")) or 0.0))
    out: dict[str, Any] = {
        "mint": mint,
        "launch_id": f"launch-{mint[:16]}",
        "source_dataset": "aggregated_lifecycle_snapshots",
        "path_row_count": len(ordered),
        "milestone_provenance": "aggregated_lifecycle_snapshot_rows",
        "max_fdv_observed": _max([row.get("fdv_proxy") for row in ordered]),
        "max_fdv_after_20k": _max([row.get("fdv_proxy") for row in ordered if (_num(row.get("fdv_proxy")) or 0) >= LEVELS["20k"]]),
    }
    for level, threshold in LEVELS.items():
        crossing = [row for row in ordered if (_num(row.get("fdv_proxy")) or 0.0) >= threshold]
        confirmed = _confirmed_path_cross(crossing)
        raw = crossing[0] if crossing else None
        out[f"raw_crossed_{level}"] = bool(raw)
        out[f"confirmed_crossed_{level}"] = bool(confirmed)
        out[f"first_crossed_{level}_time"] = _num((confirmed or raw or {}).get("timestamp"))
    out["single_row_spike_flag"] = bool(out.get("raw_crossed_20k") and not out.get("confirmed_crossed_20k"))
    out["same_timestamp_major_jump_flag"] = _same_timestamp_major_jump(out)
    out["valid_milestone_ordering"] = _valid_ordering(out)
    out["clean_path_flag"] = bool(out.get("confirmed_crossed_20k") and not out["single_row_spike_flag"] and not out["same_timestamp_major_jump_flag"] and out["valid_milestone_ordering"])
    for level in ["10k", "15k", "20k"]:
        event = _first_near_level(ordered, LEVELS[level])
        if event:
            suffix = f"at_{level}"
            out[f"event_count_{suffix}"] = event.get("event_count")
            out[f"buy_count_{suffix}"] = event.get("buy_count")
            out[f"sell_count_{suffix}"] = event.get("sell_count")
            out[f"active_wallets_{suffix}"] = event.get("active_wallets")
            fdv = _num(event.get("fdv_proxy"))
            out[f"fdv_per_event_{suffix}"] = _ratio(fdv, event.get("event_count"))
            out[f"fdv_per_buy_{suffix}"] = _ratio(fdv, event.get("buy_count"))
            out[f"fdv_per_active_wallet_{suffix}"] = _ratio(fdv, event.get("active_wallets"))
    launch_ts = _num(ordered[0].get("launch_ts")) if ordered else None
    for level in ["10k", "20k", "50k", "100k"]:
        out[f"create_to_{level}_seconds"] = _delta(launch_ts, out.get(f"first_crossed_{level}_time"))
    out["10k_to_20k_seconds"] = _delta(out.get("first_crossed_10k_time"), out.get("first_crossed_20k_time"))
    out["20k_to_50k_seconds"] = _delta(out.get("first_crossed_20k_time"), out.get("first_crossed_50k_time"))
    out["20k_to_100k_seconds"] = _delta(out.get("first_crossed_20k_time"), out.get("first_crossed_100k_time"))
    return out


def _aggregate_drawdowns(mint: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"mint": mint}
    for pct in [20, 30, 40, 50]:
        matching = [row for row in rows if str(row.get("drawdown_level") or "").startswith(str(pct)) or (_num(row.get("drawdown_threshold")) == pct / 100)]
        out[f"first_{pct}pct_drawdown_time"] = _min([row.get("drawdown_time") for row in matching])
        out[f"recovered_after_{pct}pct"] = any(row.get("reclaimed_prior_high_within_5m") is True or row.get("reached_higher_milestone_after_drawdown") is True for row in matching)
    out["no_reclaim_after_5m"] = any(row.get("failed_to_reclaim_within_5m") is True for row in rows)
    out["no_reclaim_after_10m"] = any(row.get("failed_to_reclaim_within_10m") is True for row in rows)
    out["terminal_collapse_proxy"] = any(str(row.get("drawdown_classification") or "").startswith("terminal") for row in rows)
    out["max_drawdown_after_entry"] = _max([row.get("drawdown_pct") for row in rows])
    return out


def _finalize_dataset_row(row: dict[str, Any], *, source_paths: list[str]) -> dict[str, Any]:
    for level in LEVELS:
        row[f"raw_crossed_{level}"] = bool(row.get(f"raw_crossed_{level}"))
        row[f"confirmed_crossed_{level}"] = bool(row.get(f"confirmed_crossed_{level}"))
        row[f"crossed_{level}"] = row[f"confirmed_crossed_{level}"]
    row["single_row_spike_flag"] = bool(row.get("single_row_spike_flag"))
    row["same_timestamp_major_jump_flag"] = bool(row.get("same_timestamp_major_jump_flag") or _same_timestamp_major_jump(row))
    row["valid_milestone_ordering"] = bool(row.get("valid_milestone_ordering", True) and _valid_ordering(row))
    row["clean_path_flag"] = bool(
        row.get("confirmed_crossed_20k")
        and not row["single_row_spike_flag"]
        and not row["same_timestamp_major_jump_flag"]
        and row["valid_milestone_ordering"]
    )
    row["runner_tier"] = _runner_tier(row)
    entry_fdv = _num(row.get("first_crossed_20k_fdv") or row.get("trigger_fdv_proxy") or LEVELS["20k"])
    max_fdv = _num(row.get("max_fdv_after_20k") or row.get("max_fdv_observed"))
    row["max_fdv_multiple_after_entry"] = _ratio(max_fdv, entry_fdv)
    row["source_files"] = source_paths
    row["source_dataset"] = row.get("source_dataset") or "historical_merged"
    flags = list(row.get("data_quality_flags") or [])
    if row["single_row_spike_flag"]:
        flags.append("single_row_spike_excluded")
    if row["same_timestamp_major_jump_flag"]:
        flags.append("same_timestamp_major_jump_excluded")
    if not row.get("clean_path_flag"):
        flags.append("not_clean_confirmed_20k_path")
    missing_core = [feature for feature in ["fdv_per_buy_at_20k", "fdv_per_event_at_20k"] if _num(row.get(feature)) is None]
    if missing_core:
        flags.append("missing_core_efficiency:" + ",".join(missing_core))
    row["data_quality_flags"] = sorted(set(flags))
    row["data_limited_flag"] = bool(missing_core)
    return row


def _feature_row(
    feature: str,
    family: str,
    side: str,
    expected: str,
    all_rows: list[dict[str, Any]],
    values: list[tuple[dict[str, Any], float | None]],
    classification: str,
) -> dict[str, Any]:
    usable = [(row, value) for row, value in values if value is not None]
    by_tier: dict[str, list[float]] = defaultdict(list)
    for row, value in usable:
        by_tier[str(row.get("runner_tier") or "unknown")].append(float(value))
    tier_medians = {tier: _median(vals) for tier, vals in sorted(by_tier.items())}
    weak = [value for row, value in usable if row.get("runner_tier") == "crossed_20k_but_never_50k"]
    strong = [value for row, value in usable if row.get("runner_tier") in {"crossed_500k_but_never_1m", "crossed_1m_plus", "crossed_10m_plus"}]
    effect = None
    if weak and strong:
        effect = (_median(strong) or 0.0) - (_median(weak) or 0.0)
    return {
        "feature": feature,
        "feature_family": family,
        "coverage": round(len(usable) / len(all_rows), 4) if all_rows else 0.0,
        "median_iqr_by_tier": json.dumps({tier: {"median": med, "iqr": _iqr(by_tier[tier])} for tier, med in tier_medians.items()}, sort_keys=True),
        "direction": _direction(effect),
        "effect_proxy": effect,
        "stability_across_time_split": _feature_split_stability(feature, all_rows),
        "source_concentration": _feature_source_concentration(feature, all_rows),
        "entry_side_observable": side in {"entry_side", "risk_filter"},
        "path_side_only": side == "path_side",
        "exit_side_only": side == "exit_side",
        "likely_symptom_or_cause": "candidate_cause_or_selection_signal" if side in {"entry_side", "risk_filter"} else "path_symptom",
        "measurable_live": side in {"entry_side", "risk_filter", "exit_side"},
        "classification": classification,
        "expected_direction": expected,
    }


def _classify_buy_feature(
    feature: str,
    family: str,
    side: str,
    rows: list[dict[str, Any]],
    values: list[tuple[dict[str, Any], float | None]],
    split_manifest: dict[str, Any],
) -> str:
    coverage = len(values) / len(rows) if rows else 0
    support = len(values)
    if coverage < 0.10 and support < 100:
        return "data_limited"
    if family == "FDV efficiency" and (coverage >= 0.05 or support >= 100):
        return "strong_buy_side_candidate"
    if side == "risk_filter" and (coverage >= 0.05 or support >= 100):
        return "possible_risk_filter"
    if side == "entry_side" and (coverage >= 0.05 or support >= 100):
        return "possible_buy_filter"
    if side == "exit_side":
        return "path_or_exit_only"
    return "no_clear_difference"


def _classify_exit_feature(feature: str, rows: list[dict[str, Any]], values: list[tuple[dict[str, Any], float | None]]) -> str:
    coverage = len(values) / len(rows) if rows else 0
    support = len(values)
    if coverage < 0.10 and support < 30:
        return "data_limited"
    if feature in {"no_reclaim_after_5m", "no_reclaim_after_10m", "terminal_collapse_proxy", "recovered_after_30pct"}:
        return "strong_exit_candidate"
    return "possible_exit_filter"


def _candidate_score(row: dict[str, Any]) -> tuple[float, float, int]:
    support = int(row.get("support_count_total") or 0)
    reached_100k = int(row.get("reached_100k_after_entry") or 0)
    rate_100k = reached_100k / support if support else 0.0
    median_multiple = _num(row.get("median_max_fdv_multiple_after_entry")) or 0.0
    live_bonus = 0.05 if row.get("live_fields_available") is True else 0.0
    return (rate_100k + live_bonus, median_multiple, support)


def _discovery_thresholds(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    train = [row for row in rows if row.get("split") == "discovery_train"]
    return {
        "fdv_per_buy_at_20k": _median([row.get("fdv_per_buy_at_20k") for row in train]),
        "fdv_per_event_at_20k": _median([row.get("fdv_per_event_at_20k") for row in train]),
        "synthetic_activity_proxy": _median([row.get("synthetic_activity_proxy") for row in train]),
        "top_holder_share_proxy": _median([row.get("top_holder_share_proxy") for row in train]),
    }


def _buy_rule_match(row: dict[str, Any], rule_id: str, thresholds: dict[str, float | None]) -> bool:
    if not row.get("clean_path_flag"):
        return False
    if rule_id == "BROAD_15K_BALANCED_BUY":
        return bool(row.get("confirmed_crossed_15k") and _efficiency_ok(row, thresholds) and _flow_ok(row))
    if rule_id == "BROAD_20K_CONFIRMATION_BUY":
        return bool(row.get("confirmed_crossed_20k"))
    if rule_id == "BROAD_RISK_FILTERED_20K":
        return bool(row.get("confirmed_crossed_20k") and _efficiency_ok(row, thresholds) and _risk_ok(row, thresholds))
    return bool(row.get("confirmed_crossed_10k") and row.get("confirmed_crossed_20k") and _efficiency_ok(row, thresholds))


def _efficiency_ok(row: dict[str, Any], thresholds: dict[str, float | None]) -> bool:
    per_buy = _num(row.get("fdv_per_buy_at_20k"))
    threshold = _num(thresholds.get("fdv_per_buy_at_20k"))
    if per_buy is None or threshold is None:
        return bool(row.get("confirmed_crossed_20k"))
    return per_buy >= threshold


def _flow_ok(row: dict[str, Any]) -> bool:
    sells = _num(row.get("sell_count_at_20k")) or 0.0
    buys = _num(row.get("buy_count_at_20k")) or 0.0
    return buys >= sells


def _risk_ok(row: dict[str, Any], thresholds: dict[str, float | None]) -> bool:
    if _num(row.get("creator_extraction_proxy_before_20k")) is not None and (_num(row.get("creator_extraction_proxy_before_20k")) or 0) > 2.0:
        return False
    synthetic = _num(row.get("synthetic_activity_proxy"))
    synthetic_threshold = _num(thresholds.get("synthetic_activity_proxy"))
    if synthetic is not None and synthetic_threshold is not None and synthetic > max(synthetic_threshold * 2, synthetic_threshold + 1):
        return False
    top_holder = _num(row.get("top_holder_share_proxy"))
    if top_holder is not None and top_holder > 0.98:
        return False
    return True


def _dataset_feature_keys() -> list[str]:
    return sorted(
        set(BUY_FEATURES)
        | set(EXIT_FEATURES)
        | {
            "event_count_at_10k",
            "buy_count_at_10k",
            "sell_count_at_10k",
            "active_wallets_at_10k",
            "event_count_at_20k",
            "buy_count_at_20k",
            "sell_count_at_20k",
            "active_wallets_at_20k",
            "holder_count_at_10k",
            "holder_count_at_20k",
            "holder_growth_to_20k",
            "token_name",
            "token_symbol",
            "metadata_uri",
            "image_uri",
            "website_url",
            "twitter_x_url",
            "telegram_url",
            "discord_url",
            "narrative_bucket",
            "topicality_bucket",
            "maturity_state",
        }
    )


def _read_records(path: Path, *, sample_limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists() or path.name.startswith("._"):
        return []
    try:
        if path.suffix == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        rows.append(json.loads(line))
                    if sample_limit is not None and len(rows) >= sample_limit:
                        break
            return rows
        if path.suffix == ".csv":
            frame = pd.read_csv(path, nrows=sample_limit)
        elif path.suffix == ".parquet":
            frame = pd.read_parquet(path)
            if sample_limit is not None:
                frame = frame.head(sample_limit)
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
        else:
            return []
        return frame.where(pd.notnull(frame), None).to_dict(orient="records")
    except Exception:
        return []


def _table_columns(path: Path) -> set[str]:
    try:
        if path.suffix == ".csv":
            return set(pd.read_csv(path, nrows=0).columns)
        if path.suffix == ".parquet":
            return set(pd.read_parquet(path).columns)
    except Exception:
        return set()
    return set()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(_json_safe(row), sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_cell(row.get(key)) for key in fieldnames})


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([_json_safe(row) for row in rows])
    for col in frame.columns:
        if frame[col].dtype == "object":
            normalized = frame[col].map(_parquet_cell)
            numeric = pd.to_numeric(normalized, errors="coerce")
            non_null = normalized.notna()
            if int(numeric.notna().sum()) == int(non_null.sum()):
                frame[col] = numeric
            else:
                frame[col] = normalized.map(lambda value: None if value is None else str(value))
    frame.to_parquet(path, index=False)


def _summary_markdown(summary: dict[str, Any]) -> str:
    buy = summary.get("strongest_buy_side_patterns") or []
    sell = summary.get("strongest_sell_side_patterns") or []
    rec = summary.get("selected_paper_shadow_candidate") or {}
    return "\n".join(
        [
            "# Historical Rule Discovery",
            "",
            "Historical data was used because recent forward collection exposed raw FDV proxy spikes and actionability gaps.",
            "",
            f"Rows analyzed: `{summary.get('historical_rows_analyzed')}`",
            f"Mints analyzed: `{summary.get('historical_mints_analyzed')}`",
            f"Source files inspected: `{summary.get('source_files_inspected')}`",
            f"Readiness: `{summary.get('readiness_classification')}`",
            "",
            "## Broad Buy-Side Findings",
            *[f"- `{row.get('feature')}`: {row.get('classification')} ({row.get('feature_family')})" for row in buy[:8]],
            "",
            "## Broad Exit-Side Findings",
            *[f"- `{row.get('feature')}`: {row.get('classification')} ({row.get('feature_family')})" for row in sell[:8]],
            "",
            "## Selected Paper/Shadow Candidate",
            f"- Buy rule: `{rec.get('selected_buy_rule_id')}`",
            f"- Exit rule: `{rec.get('selected_exit_rule_id')}`",
            f"- Minimum review sample: `{rec.get('minimum_paper_shadow_sample_size_before_review')}`",
            "",
            "Live trading remains disabled. This is descriptive historical rule discovery only.",
        ]
    ) + "\n"


def _status_markdown(summary: dict[str, Any]) -> str:
    rec = summary.get("selected_paper_shadow_candidate") or {}
    return "\n".join(
        [
            "# Historical Rule Discovery Status",
            "",
            "Why this was run: forward data exposed FDV proxy spikes and showed that a simple 20k threshold is not a durable buy rule.",
            f"Data sources inspected: `{summary.get('source_files_inspected')}`",
            f"Split design: `{summary.get('split_design', {}).get('split_method')}`",
            f"Selected buy rule: `{rec.get('selected_buy_rule_id')}`",
            f"Selected exit rule: `{rec.get('selected_exit_rule_id')}`",
            f"Readiness: `{summary.get('readiness_classification')}`",
            "",
            "Broad buy-side finding: FDV efficiency is the strongest broad family when available, but it needs risk filters and confirmed path safety.",
            "Broad exit-side finding: drawdown reclaim/no-reclaim behavior is the cleanest exit-side framework, with data-resolution caveats.",
            "Limitations: historical features are richer than live hot-path fields; no PnL or profitability claim is made.",
            "Required live/actionability work: confirmed milestones, spike rejection, same-timestamp jump exclusion, early efficiency capture, and drawdown/reclaim state.",
            "Live trading remains disabled.",
        ]
    ) + "\n"


def _mint(row: dict[str, Any]) -> str | None:
    for key in ["mint", "token_mint", "base_mint", "address", "token_address", "ca"]:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _value(row: dict[str, Any], key: str) -> Any:
    aliases = {
        "liquidity_proxy_at_20k": ["liquidity_proxy_at_20k", "liquidity_sol_proxy_at_20k", "bonding_curve_liquidity_proxy_sol"],
        "exit_liquidity_proxy": ["exit_liquidity_proxy", "exit_liquidity_proxy_at_20k"],
        "social_link_count": ["social_link_count"],
        "image_uri": ["image_uri", "image", "metadata_image_uri"],
        "website_url": ["website_url", "website"],
        "twitter_x_url": ["twitter_x_url", "twitter_url", "x_url"],
    }
    for candidate in [key] + aliases.get(key, []):
        if candidate in row and row.get(candidate) not in {None, ""}:
            return row.get(candidate)
    return None


def _crossed_level(row: dict[str, Any], level: str) -> bool:
    if row.get(f"crossed_{level}") is True or row.get(f"raw_crossed_{level}") is True:
        return True
    if row.get(f"ever_hit_valuation_proxy_{level}") is True:
        return True
    tier = str(row.get("milestone_tier") or "")
    if _tier_implies(tier, level):
        return True
    peak = _num(row.get("peak_fdv_proxy") or row.get("max_fdv_observed") or row.get("valuation_proxy_usd") or row.get("fdv_usd"))
    return bool(peak is not None and peak >= LEVELS[level])


def _historical_confirmed_crossed(row: dict[str, Any], level: str) -> bool:
    if row.get(f"confirmed_crossed_{level}") is True:
        return True
    if row.get("single_row_spike_flag") is True:
        return False
    return _crossed_level(row, level)


def _first_time(row: dict[str, Any], level: str) -> Any:
    for key in [f"first_crossed_{level}_time", f"confirmed_first_crossed_{level}_time", f"raw_first_crossed_{level}_time"]:
        if row.get(key) is not None:
            return row.get(key)
    if level == "20k":
        return row.get("trigger_20k_time")
    return None


def _tier_implies(tier: str, level: str) -> bool:
    if not tier:
        return False
    rank = {"10k": 10_000, "15k": 15_000, "20k": 20_000, "30k": 30_000, "50k": 50_000, "100k": 100_000, "200k": 200_000, "500k": 500_000, "1m": 1_000_000, "10m": 10_000_000}[level]
    tier_lower = tier.lower()
    tier_rank = None
    if "reached_10m" in tier_lower:
        tier_rank = 10_000_000
    elif "reached_1m_plus" in tier_lower:
        tier_rank = 1_000_000
    elif "reached_500k" in tier_lower:
        tier_rank = 500_000
    elif "reached_200k" in tier_lower:
        tier_rank = 200_000
    elif "reached_100k" in tier_lower:
        tier_rank = 100_000
    elif "reached_50k" in tier_lower:
        tier_rank = 50_000
    elif "reached_30k" in tier_lower:
        tier_rank = 30_000
    elif "reached_20k" in tier_lower:
        tier_rank = 20_000
    elif "reached_15k" in tier_lower:
        tier_rank = 15_000
    elif "reached_10k" in tier_lower:
        tier_rank = 10_000
    return bool(tier_rank is not None and tier_rank >= rank)


def _runner_tier(row: dict[str, Any]) -> str:
    if row.get("confirmed_crossed_10m"):
        return "crossed_10m_plus"
    if row.get("confirmed_crossed_1m"):
        return "crossed_1m_plus"
    if row.get("confirmed_crossed_500k"):
        return "crossed_500k_but_never_1m"
    if row.get("confirmed_crossed_100k"):
        return "crossed_100k_but_never_500k"
    if row.get("confirmed_crossed_50k"):
        return "crossed_50k_but_never_100k"
    if row.get("confirmed_crossed_20k"):
        return "crossed_20k_but_never_50k"
    return "below_20k_or_unconfirmed"


def _confirmed_path_cross(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < CONFIRMATION_MIN_ROWS:
        return None
    ordered = sorted(rows, key=lambda row: _num(row.get("timestamp")) or 0.0)
    for row in ordered:
        ts = _num(row.get("timestamp"))
        if ts is None:
            continue
        nearby = [other for other in ordered if _num(other.get("timestamp")) is not None and abs((_num(other.get("timestamp")) or 0) - ts) <= CONFIRMATION_WINDOW_SECONDS]
        if len(nearby) >= CONFIRMATION_MIN_ROWS:
            return row
    return None


def _same_timestamp_major_jump(row: dict[str, Any]) -> bool:
    t20 = _num(row.get("first_crossed_20k_time"))
    t1m = _num(row.get("first_crossed_1m_time"))
    return bool(t20 is not None and t1m is not None and t20 == t1m)


def _valid_ordering(row: dict[str, Any]) -> bool:
    seen_false = False
    for level in ["10k", "15k", "20k", "30k", "50k", "100k", "200k", "500k", "1m", "10m"]:
        crossed = bool(row.get(f"confirmed_crossed_{level}"))
        if seen_false and crossed:
            return False
        if not crossed:
            seen_false = True
    return True


def _merge_rows(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if _is_missing(value):
            continue
        if key not in merged or _is_missing(merged.get(key)):
            merged[key] = value
        elif key.startswith("confirmed_crossed_") or key.startswith("raw_crossed_") or key in {"single_row_spike_flag", "same_timestamp_major_jump_flag"}:
            merged[key] = bool(merged.get(key)) or bool(value)
        elif key == "max_fdv_observed":
            merged[key] = max([v for v in [_num(merged.get(key)), _num(value)] if v is not None], default=None)
    return merged


def _feature_families(cols: set[str]) -> set[str]:
    joined = " ".join(cols).lower()
    families: set[str] = set()
    checks = {
        "FDV efficiency": ["fdv_per", "efficiency"],
        "speed/timing": ["seconds", "time", "launch_ts"],
        "flow/activity": ["buy_count", "sell_count", "event_count", "active_wallet"],
        "wallet/repeated buyer quality": ["buyer", "wallet", "smart_money"],
        "creator/funder structure": ["creator", "funder", "deployer"],
        "holder/top-holder concentration": ["holder"],
        "liquidity/execution": ["liquidity", "slippage", "sell_impact"],
        "synthetic/bot activity": ["synthetic", "wash", "sniper", "bundle", "same_slot"],
        "metadata/social/narrative": ["metadata", "website", "twitter", "telegram", "discord", "narrative"],
        "exit/drawdown": ["drawdown", "reclaim", "collapse"],
    }
    for family, needles in checks.items():
        if any(needle in joined for needle in needles):
            families.add(family)
    return families or {"unknown"}


def _quality_note(path: Path, records: list[dict[str, Any]], cols: set[str]) -> str:
    notes = []
    if path.name not in PREFERRED_DATASET_FILES:
        notes.append("supporting_report_or_sidecar")
    if not records:
        notes.append("empty_or_unreadable")
    if "true_market_cap_available" in cols:
        notes.append("market_cap_availability_explicit")
    else:
        notes.append("valuation_proxy_language_required")
    return ";".join(notes)


def _source_kind(path: Path) -> str:
    name = path.name.lower()
    if "lifecycle_snapshots" in name:
        return "lifecycle_snapshots"
    if "drawdown" in name or "recovery" in name:
        return "drawdown_exit"
    if "master" in name or "fingerprint" in name or "trigger_20k" in name:
        return "historical_enriched"
    return "supporting_report"


def _has_any(cols: set[str], needles: list[str]) -> bool:
    joined = " ".join(cols).lower()
    return any(needle in joined for needle in needles)


def _date_value(row: dict[str, Any]) -> str | None:
    return _date_from_any(row.get("launch_date") or row.get("launch_time") or row.get("launch_ts") or row.get("timestamp") or row.get("snapshot_ts"))


def _date_from_any(value: Any) -> str | None:
    ts = _timestamp(value)
    if ts is not None:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    if value is None:
        return None
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def _timestamp(value: Any) -> float | None:
    number = _num(value)
    if number is not None and number > 10_000:
        return number
    if value is None:
        return None
    try:
        return pd.Timestamp(value).timestamp()
    except Exception:
        return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _ratio(numerator: Any, denominator: Any) -> float | None:
    num = _num(numerator)
    den = _num(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def _delta(start: Any, end: Any) -> float | None:
    s = _num(start)
    e = _num(end)
    if s is None or e is None:
        return None
    return e - s


def _median(values: list[Any]) -> float | None:
    nums = [_num(value) for value in values]
    nums = [value for value in nums if value is not None]
    return float(median(nums)) if nums else None


def _iqr(values: list[Any]) -> float | None:
    nums = sorted(value for value in [_num(value) for value in values] if value is not None)
    if len(nums) < 4:
        return None
    q1 = nums[int(len(nums) * 0.25)]
    q3 = nums[int(len(nums) * 0.75)]
    return q3 - q1


def _max(values: list[Any]) -> float | None:
    nums = [value for value in [_num(value) for value in values] if value is not None]
    return max(nums) if nums else None


def _min(values: list[Any]) -> float | None:
    nums = [value for value in [_num(value) for value in values] if value is not None]
    return min(nums) if nums else None


def _direction(effect: float | None) -> str:
    if effect is None:
        return "unknown"
    if effect > 0:
        return "higher_in_stronger_runners"
    if effect < 0:
        return "lower_in_stronger_runners"
    return "flat"


def _feature_split_stability(feature: str, rows: list[dict[str, Any]]) -> str:
    available_splits = {row.get("split") for row in rows if _num(row.get(feature)) is not None}
    if len(available_splits) >= 2:
        return "available_across_multiple_splits"
    if available_splits:
        return "single_split_only"
    return "not_available"


def _feature_source_concentration(feature: str, rows: list[dict[str, Any]]) -> str:
    sources = [str(row.get("source_dataset") or "") for row in rows if _num(row.get(feature)) is not None]
    if not sources:
        return "not_available"
    top_count = Counter(sources).most_common(1)[0][1]
    return "high_source_concentration" if top_count / len(sources) > 0.8 else "multi_source"


def _source_concentration(rows: list[dict[str, Any]]) -> str:
    sources = [str(row.get("source_dataset") or "") for row in rows]
    if not sources:
        return "none"
    top_count = Counter(sources).most_common(1)[0][1]
    return "high" if top_count / len(sources) > 0.8 else "mixed"


def _exit_reason_counts(rows: list[dict[str, Any]], exit_rule: str) -> dict[str, int]:
    if exit_rule == "EXIT_NO_RECLAIM":
        return {"no_reclaim": sum(1 for row in rows if row.get("no_reclaim_after_5m") is True), "open": sum(1 for row in rows if row.get("no_reclaim_after_5m") is not True)}
    if exit_rule == "EXIT_MILESTONE_TRAIL":
        return {"terminal_collapse": sum(1 for row in rows if row.get("terminal_collapse_proxy") is True), "tracking": sum(1 for row in rows if row.get("terminal_collapse_proxy") is not True)}
    if exit_rule == "EXIT_INACTIVE_MAX_AGE":
        return {"inactive": sum(1 for row in rows if row.get("inactive_timeout") is True), "open": sum(1 for row in rows if row.get("inactive_timeout") is not True)}
    return {"diagnostic_milestone": len(rows)}


def _runner_miss_count(all_rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> int:
    selected_mints = {row.get("mint") for row in selected}
    return sum(1 for row in all_rows if row.get("confirmed_crossed_100k") is True and row.get("mint") not in selected_mints)


def _exited_before_next_milestone_count(rows: list[dict[str, Any]], exit_rule: str) -> int:
    if exit_rule not in {"EXIT_NO_RECLAIM", "EXIT_MILESTONE_TRAIL"}:
        return 0
    return sum(1 for row in rows if row.get("terminal_collapse_proxy") is True and row.get("confirmed_crossed_50k") is not True)


def _stability_label(rows: list[dict[str, Any]]) -> str:
    splits = Counter(row.get("split") for row in rows)
    return "multi_split_support" if sum(1 for count in splits.values() if count > 0) >= 2 else "single_split_or_sparse"


def _live_fields_available_for_rule(rule_id: str) -> bool:
    return rule_id in {"BROAD_20K_CONFIRMATION_BUY", "BROAD_10K_WATCH_20K_BUY"}


def _first_near_level(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    return next((row for row in rows if (_num(row.get("fdv_proxy")) or 0) >= threshold), None)


def _tier_from_row(row: dict[str, Any]) -> str | None:
    peak = _num(row.get("peak_fdv_proxy") or row.get("max_fdv_observed"))
    if peak is None:
        return None
    if peak >= LEVELS["1m"]:
        return "reached_1m_plus"
    if peak >= LEVELS["500k"]:
        return "reached_500k_but_never_1m"
    if peak >= LEVELS["100k"]:
        return "reached_100k_but_never_500k"
    if peak >= LEVELS["50k"]:
        return "reached_50k_but_never_100k"
    if peak >= LEVELS["20k"]:
        return "reached_20k_but_never_50k"
    return "below_20k"


def _yes_no(value: bool) -> bool:
    return bool(value)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _is_missing(value: Any) -> bool:
    if value is None or value == "" or value == []:
        return True
    return bool(isinstance(value, float) and math.isnan(value))


def _csv_cell(value: Any) -> Any:
    safe = _json_safe(value)
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, sort_keys=True)
    return safe


def _parquet_cell(value: Any) -> Any:
    safe = _json_safe(value)
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, sort_keys=True)
    return safe
