"""Quarantine and preview pre-lifecycle-watch forward observations.

This module is descriptive and read-only with respect to data collection. It
does not call Helius, validate theses, run backtests, create alerts, or create
paper/live trading logic.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd


REPORT_ID = "pre_lifecycle_forward_pattern_preview_v0"
QUARANTINE_LABEL = "pre_lifecycle_watch_forward_sample"
FORWARD_FILE_NAMES = [
    "candidates.jsonl",
    "candidate_paths.jsonl",
    "candidate_events.jsonl",
    "candidate_metadata.jsonl",
    "candidate_holders.jsonl",
    "candidate_drawdowns.jsonl",
    "birth_watch_mints.jsonl",
    "birth_followup_paths.jsonl",
    "birth_followup_events.jsonl",
    "birth_followup_status.json",
    "checkpoint.json",
    "status.json",
]
TRIGGER_LEVELS = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
APPROVED_USES = [
    "FDV forward signal preview",
    "birth-to-trigger funnel analysis",
    "early behavior discovery",
    "collector/debug analysis",
    "feature availability audit",
]
PROHIBITED_USES = [
    "validation",
    "paper trading",
    "live trading",
    "final exit logic",
    "final strategy design",
    "final profitability claims",
]
GUARDRAILS = [
    "descriptive_analysis_only",
    "no_network_calls",
    "no_helius_calls",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_transaction_signing",
    "no_buy_orders",
    "no_sell_orders",
    "no_swaps",
    "no_order_routing",
    "no_live_trading",
    "no_paper_trading",
    "no_pnl",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_buy_sell_rules",
    "no_alerts",
    "no_threshold_optimization",
    "no_ml",
    "no_validation",
    "no_backtest",
]


@dataclass(frozen=True)
class LoadedJsonl:
    rows: list[dict[str, Any]]
    malformed_rows: int
    missing: bool


def build_pre_lifecycle_forward_pattern_preview(
    data_root: Path | str = "/Volumes/ORICO/MemeTraderPro",
    *,
    status_path: Path | str = Path("theses") / "PRE_LIFECYCLE_FORWARD_PATTERN_PREVIEW_STATUS.md",
    write_outputs: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    data_root = Path(data_root).expanduser()
    source_root = data_root / "data" / "forward_observation" / "efficient_movers"
    quarantine_root = data_root / "data" / "forward_observation" / "quarantined" / QUARANTINE_LABEL
    report_root = (
        data_root
        / "data"
        / "backtests"
        / "diagnostics"
        / "reports"
        / "forward_observation"
        / "pre_lifecycle_watch_pattern_preview"
    )

    if write_outputs:
        quarantine_root.mkdir(parents=True, exist_ok=True)
        report_root.mkdir(parents=True, exist_ok=True)
        _copy_forward_files(source_root, quarantine_root)

    loaded = _load_quarantined_files(quarantine_root if write_outputs else source_root)
    dataset = build_analysis_dataset(loaded)
    funnel = calculate_funnel_stats(dataset)
    fdv_signal_rows = build_fdv_signal_sanity_table(dataset)
    behavior_rows = build_broad_behavior_comparison_table(dataset)
    new_behavior_rows = build_new_behavior_candidates(dataset)
    manifest = build_quarantine_manifest(
        source_root=source_root,
        quarantine_root=quarantine_root,
        loaded=loaded,
        dataset=dataset,
        funnel=funnel,
    )
    recommendation = _recommendation(dataset, funnel, fdv_signal_rows)
    summary = {
        "report_id": REPORT_ID,
        "quarantine_label": QUARANTINE_LABEL,
        "data_root": str(data_root),
        "source_root": str(source_root),
        "quarantine_root": str(quarantine_root),
        "report_root": str(report_root),
        "rows_mints_analyzed": len(dataset),
        "funnel_stats": funnel,
        "fdv_signal_sanity": {
            "appears_forward": _fdv_signal_appears(fdv_signal_rows),
            "rows": fdv_signal_rows,
        },
        "broad_behavior_candidates": behavior_rows,
        "new_forward_only_behaviors": new_behavior_rows,
        "known_limitations": _known_limitations(),
        "recommendation": recommendation,
        "official_lifecycle_sample_reset_required": True,
        "approved_uses": APPROVED_USES,
        "prohibited_uses": PROHIBITED_USES,
        "guardrails": GUARDRAILS,
        "network_calls_made": 0,
    }

    paths: dict[str, Path] = {}
    if write_outputs:
        paths = write_outputs_for_preview(
            quarantine_root=quarantine_root,
            report_root=report_root,
            manifest=manifest,
            dataset=dataset,
            funnel=funnel,
            fdv_signal_rows=fdv_signal_rows,
            behavior_rows=behavior_rows,
            new_behavior_rows=new_behavior_rows,
            summary=summary,
            status_path=Path(status_path),
        )
    return summary, paths


def build_quarantine_manifest(
    *,
    source_root: Path,
    quarantine_root: Path,
    loaded: dict[str, LoadedJsonl | dict[str, Any]],
    dataset: list[dict[str, Any]],
    funnel: dict[str, Any],
) -> dict[str, Any]:
    source_files = []
    for name in FORWARD_FILE_NAMES:
        src = source_root / name
        dst = quarantine_root / name
        loaded_item = loaded.get(name)
        rows = len(loaded_item.rows) if isinstance(loaded_item, LoadedJsonl) else (1 if loaded_item else 0)
        source_files.append(
            {
                "file": name,
                "source_path": str(src),
                "quarantine_path": str(dst),
                "exists": src.exists(),
                "bytes": src.stat().st_size if src.exists() else 0,
                "row_count": rows,
                "malformed_rows": loaded_item.malformed_rows if isinstance(loaded_item, LoadedJsonl) else 0,
            }
        )
    times = [
        value
        for row in dataset
        for value in [_num(row.get("first_seen_time")), _num(row.get("first_followup_time"))]
        if value is not None
    ]
    return {
        "quarantine_label": QUARANTINE_LABEL,
        "reason": "Current forward data was collected before a durable active lifecycle watcher existed.",
        "source_files": source_files,
        "file_counts": {
            "expected_files": len(FORWARD_FILE_NAMES),
            "existing_files": sum(1 for row in source_files if row["exists"]),
        },
        "row_counts": {row["file"]: row["row_count"] for row in source_files},
        "first_observation_time": min(times) if times else None,
        "latest_observation_time": max(times) if times else None,
        "current_funnel_counts": funnel.get("counts", {}),
        "known_limitations": _known_limitations(),
        "approved_uses": APPROVED_USES,
        "prohibited_uses": PROHIBITED_USES,
        "network_calls_made": 0,
    }


def build_analysis_dataset(loaded: dict[str, LoadedJsonl | dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = _jsonl_rows(loaded, "candidates.jsonl")
    birth_watch = _jsonl_rows(loaded, "birth_watch_mints.jsonl")
    paths = _jsonl_rows(loaded, "candidate_paths.jsonl") + _jsonl_rows(loaded, "birth_followup_paths.jsonl")
    metadata_rows = _jsonl_rows(loaded, "candidate_metadata.jsonl")
    holder_rows = _jsonl_rows(loaded, "candidate_holders.jsonl")
    event_rows = _jsonl_rows(loaded, "candidate_events.jsonl") + _jsonl_rows(loaded, "birth_followup_events.jsonl")

    birth_by_mint: dict[str, dict[str, Any]] = {}
    for row in candidates + birth_watch:
        mint = _mint(row)
        if not mint or not _is_birth_candidate(row):
            continue
        existing = birth_by_mint.get(mint)
        if existing is None:
            birth_by_mint[mint] = row
        else:
            birth_by_mint[mint] = _merge_birth_rows(existing, row)

    paths_by_mint = _group_by_mint(paths)
    metadata_by_mint = _latest_by_mint(metadata_rows)
    holders_by_mint = _latest_by_mint(holder_rows)
    events_by_mint = _group_by_mint(event_rows)
    dataset = []
    for mint, birth in sorted(birth_by_mint.items(), key=lambda item: (_sort_time(item[1]), item[0])):
        mint_paths = sorted(
            [row for row in paths_by_mint.get(mint, []) if _num(row.get("fdv_proxy")) is not None],
            key=_sort_time,
        )
        row = _dataset_row(
            mint=mint,
            birth=birth,
            paths=mint_paths,
            metadata=metadata_by_mint.get(mint, {}),
            holder=holders_by_mint.get(mint, {}),
            events=events_by_mint.get(mint, []),
        )
        dataset.append(row)
    return dataset


def calculate_funnel_stats(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "birth_watch_mints": len(dataset),
        "deterministic_fdv_followup_mints": sum(1 for row in dataset if row.get("has_fdv_followup")),
    }
    for level in TRIGGER_LEVELS:
        counts[f"crossed_{level}"] = sum(1 for row in dataset if row.get(f"crossed_{level}"))
    rates = {
        "birth_to_fdv_followup": _rate(counts["deterministic_fdv_followup_mints"], counts["birth_watch_mints"]),
        "birth_to_10k": _rate(counts["crossed_10k"], counts["birth_watch_mints"]),
        "birth_to_20k": _rate(counts["crossed_20k"], counts["birth_watch_mints"]),
        "10k_to_20k": _rate(counts["crossed_20k"], counts["crossed_10k"]),
        "20k_to_50k": _rate(counts["crossed_50k"], counts["crossed_20k"]),
        "20k_to_100k": _rate(counts["crossed_100k"], counts["crossed_20k"]),
        "20k_to_500k": _rate(counts["crossed_500k"], counts["crossed_20k"]),
        "20k_to_1m": _rate(counts["crossed_1m"], counts["crossed_20k"]),
        "50k_to_100k": _rate(counts["crossed_100k"], counts["crossed_50k"]),
        "100k_to_500k": _rate(counts["crossed_500k"], counts["crossed_100k"]),
        "500k_to_1m": _rate(counts["crossed_1m"], counts["crossed_500k"]),
    }
    return {"counts": counts, "conversion_rates": rates}


def build_fdv_signal_sanity_table(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = [
        "fdv_per_event_at_10k",
        "fdv_per_buy_at_10k",
        "fdv_per_active_wallet_at_10k",
        "fdv_per_event_at_20k",
        "fdv_per_buy_at_20k",
        "fdv_per_active_wallet_at_20k",
        "event_count_at_10k",
        "buy_count_at_10k",
        "active_wallets_at_10k",
        "buy_sell_ratio_at_10k",
        "event_count_at_20k",
        "buy_count_at_20k",
        "active_wallets_at_20k",
        "buy_sell_ratio_at_20k",
    ]
    groups = _outcome_groups(dataset)
    rows = []
    for feature in features:
        row = _comparison_row(feature, groups, family="fdv_signal_sanity")
        row["resembles_historical_fdv_signal"] = (
            feature.startswith("fdv_per_")
            and row["classification"] in {"forward_promising_candidate", "data_limited"}
        )
        rows.append(row)
    return rows


def build_broad_behavior_comparison_table(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_families = {
        "speed_timing": [
            "create_to_10k_seconds",
            "create_to_20k_seconds",
            "10k_to_20k_seconds",
            "20k_to_50k_seconds",
            "20k_to_100k_seconds",
        ],
        "flow_activity": [
            "buy_count_at_10k",
            "sell_count_at_10k",
            "event_count_at_10k",
            "active_wallets_at_10k",
            "buy_sell_ratio_at_10k",
            "buy_count_at_20k",
            "sell_count_at_20k",
            "event_count_at_20k",
            "active_wallets_at_20k",
            "buy_sell_ratio_at_20k",
        ],
        "fdv_efficiency": [
            "fdv_per_event_at_10k",
            "fdv_per_buy_at_10k",
            "fdv_per_active_wallet_at_10k",
            "fdv_per_event_at_20k",
            "fdv_per_buy_at_20k",
            "fdv_per_active_wallet_at_20k",
        ],
        "metadata_attention": ["metadata_completeness_score", "social_link_count"],
        "microstructure_proxy": [
            "liquidity_proxy",
            "same_second_buy_count",
            "same_slot_buy_count",
            "synthetic_activity_proxy",
            "rapid_round_trip_count",
        ],
        "creator_holder": [
            "creator_net_flow_proxy",
            "holder_count",
            "top_holder_share_proxy",
            "top_10_holder_share_proxy",
        ],
    }
    groups = _outcome_groups(dataset)
    rows = []
    for family, features in feature_families.items():
        for feature in features:
            rows.append(_comparison_row(feature, groups, family=family))
    return rows


def build_new_behavior_candidates(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        ("true_create_to_trigger_time", "create_to_20k_seconds", "entry-side", "true launch-to-trigger timing was not reliable in historical snapshots"),
        ("first_followup_freshness", "create_to_first_followup_seconds", "entry-side", "WebSocket follow-up timing is directly observed"),
        ("intraminute_10k_to_20k_speed", "10k_to_20k_seconds", "path-side", "fast milestone spacing is visible from forward path rows"),
        ("path_before_first_20k_crossing", "fdv_per_event_at_10k", "entry-side", "10k-side path state can be captured before 20k continuation"),
        ("metadata_at_birth", "metadata_completeness_score", "entry-side", "metadata freshness can be audited at or near birth"),
        ("early_buy_burst_shape", "buy_count_at_10k", "entry-side", "early cumulative buy shape is visible in forward rows"),
        ("immediate_post_birth_inactivity", "has_fdv_followup", "collector/debug", "mints with no FDV follow-up are distinguishable from movers"),
        ("early_fdv_path_jumpiness", "fdv_per_event_at_20k", "path-side", "efficiency and path jumps are observable in forward rows"),
        ("early_drawdown_reclaim_behavior", "estimated_sell_impact_proxy", "path-side", "current sample is too partial for final exit interpretation"),
    ]
    rows = []
    for name, feature, timing, reason in candidates:
        available = sum(1 for row in dataset if _num(row.get(feature)) is not None or isinstance(row.get(feature), bool))
        rows.append(
            {
                "behavior": name,
                "feature_proxy": feature,
                "coverage_count": available,
                "coverage_pct": _rate(available, len(dataset)),
                "why_it_may_matter": reason,
                "feature_timing": timing,
                "deserves_tracking_in_official_lifecycle_sample": available > 0,
                "current_sample_too_partial_to_interpret": timing == "path-side",
                "classification": "data_limited" if available < 10 else "forward_promising_candidate",
            }
        )
    return rows


def write_outputs_for_preview(
    *,
    quarantine_root: Path,
    report_root: Path,
    manifest: dict[str, Any],
    dataset: list[dict[str, Any]],
    funnel: dict[str, Any],
    fdv_signal_rows: list[dict[str, Any]],
    behavior_rows: list[dict[str, Any]],
    new_behavior_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "quarantine_manifest_json": quarantine_root / "quarantine_manifest.json",
        "quarantine_manifest_md": quarantine_root / "quarantine_manifest.md",
        "analysis_dataset_jsonl": quarantine_root / "pre_lifecycle_watch_analysis_dataset.jsonl",
        "analysis_dataset_parquet": quarantine_root / "pre_lifecycle_watch_analysis_dataset.parquet",
        "summary_json": report_root / "pre_lifecycle_watch_pattern_preview_summary.json",
        "summary_markdown": report_root / "pre_lifecycle_watch_pattern_preview_summary.md",
        "funnel_csv": report_root / "pre_lifecycle_forward_funnel_stats.csv",
        "fdv_signal_csv": report_root / "pre_lifecycle_fdv_signal_sanity.csv",
        "behavior_csv": report_root / "pre_lifecycle_broad_behavior_comparison.csv",
        "new_behavior_csv": report_root / "pre_lifecycle_new_behavior_candidates.csv",
        "status_markdown": status_path,
    }
    _write_json(paths["quarantine_manifest_json"], manifest)
    paths["quarantine_manifest_md"].write_text(_manifest_markdown(manifest), encoding="utf-8")
    _write_jsonl(paths["analysis_dataset_jsonl"], dataset)
    pd.DataFrame(dataset).to_parquet(paths["analysis_dataset_parquet"], index=False)
    _write_json(paths["summary_json"], summary)
    paths["summary_markdown"].write_text(_summary_markdown(summary), encoding="utf-8")
    _write_csv(paths["funnel_csv"], _funnel_rows(funnel))
    _write_csv(paths["fdv_signal_csv"], fdv_signal_rows)
    _write_csv(paths["behavior_csv"], behavior_rows)
    _write_csv(paths["new_behavior_csv"], new_behavior_rows)
    paths["status_markdown"].parent.mkdir(parents=True, exist_ok=True)
    paths["status_markdown"].write_text(_status_markdown(summary), encoding="utf-8")
    return paths


def _dataset_row(
    *,
    mint: str,
    birth: dict[str, Any],
    paths: list[dict[str, Any]],
    metadata: dict[str, Any],
    holder: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    crossings = {level: _first_cross_row(paths, threshold) for level, threshold in TRIGGER_LEVELS.items()}
    row = {
        "mint": mint,
        "observation_id": birth.get("observation_id"),
        "creator": birth.get("creator"),
        "source_adapter": birth.get("source_adapter") or birth.get("source"),
        "create_time": _num(birth.get("launch_time") or birth.get("create_time") or birth.get("block_time")),
        "first_seen_time": _num(birth.get("observed_at") or birth.get("first_seen_time") or birth.get("create_observed_at")),
        "quarantine_label": QUARANTINE_LABEL,
        "freshness_class": birth.get("freshness_class"),
        "create_to_first_followup_seconds": _num(birth.get("seconds_create_to_first_followup_attempt")),
        "first_followup_before_10k": birth.get("first_followup_before_10k"),
        "first_followup_before_20k": birth.get("first_followup_before_20k"),
        "has_fdv_followup": bool(paths),
        "token_name": metadata.get("token_name") or birth.get("token_name"),
        "token_symbol": metadata.get("token_symbol") or birth.get("token_symbol"),
        "metadata_uri": metadata.get("metadata_uri") or birth.get("metadata_uri"),
        "image_uri": metadata.get("image_uri"),
        "website_url": metadata.get("website_url"),
        "twitter_x_url": metadata.get("twitter_x_url"),
        "telegram_url": metadata.get("telegram_url"),
        "holder_count": _num(holder.get("holder_count")),
        "top_holder_share_proxy": _num(holder.get("top_holder_share") or holder.get("top_holder_share_proxy")),
        "top_10_holder_share_proxy": _num(holder.get("top_10_holder_share") or holder.get("top_10_holder_share_proxy")),
        "liquidity_proxy": _latest_num(paths, "liquidity_proxy"),
        "same_second_buy_count": _same_bucket_buy_count(events, bucket="second"),
        "same_slot_buy_count": _same_bucket_buy_count(events, bucket="slot"),
        "rapid_round_trip_count": None,
        "synthetic_activity_proxy": _synthetic_activity_proxy(events),
        "creator_net_flow_proxy": None,
        "estimated_sell_impact_proxy": None,
    }
    row["first_followup_time"] = _sort_time(paths[0]) if paths else None
    row["social_link_count"] = sum(bool(row.get(key)) for key in ["website_url", "twitter_x_url", "telegram_url"])
    row["metadata_completeness_score"] = sum(
        bool(row.get(key)) for key in ["token_name", "token_symbol", "metadata_uri", "image_uri", "website_url", "twitter_x_url", "telegram_url"]
    )
    for level, cross_row in crossings.items():
        row[f"crossed_{level}"] = cross_row is not None
        row[f"first_crossed_{level}_time"] = _sort_time(cross_row) if cross_row else None
    for threshold in ["10k", "20k"]:
        cross_row = crossings[threshold]
        _add_threshold_features(row, threshold, cross_row)
    _add_time_deltas(row)
    return row


def _add_threshold_features(row: dict[str, Any], label: str, cross_row: dict[str, Any] | None) -> None:
    suffix = f"at_{label}"
    event_count = _num(cross_row.get("event_count")) if cross_row else None
    buy_count = _num(cross_row.get("buy_count")) if cross_row else None
    sell_count = _num(cross_row.get("sell_count")) if cross_row else None
    active_wallets = _num(cross_row.get("active_wallets") or cross_row.get("active_wallet_count")) if cross_row else None
    fdv = _num(cross_row.get("fdv_proxy")) if cross_row else None
    row[f"event_count_{suffix}"] = event_count
    row[f"buy_count_{suffix}"] = buy_count
    row[f"sell_count_{suffix}"] = sell_count
    row[f"active_wallets_{suffix}"] = active_wallets
    row[f"buy_sell_ratio_{suffix}"] = _safe_ratio(buy_count, sell_count)
    row[f"fdv_per_event_{suffix}"] = _safe_ratio(fdv, event_count)
    row[f"fdv_per_buy_{suffix}"] = _safe_ratio(fdv, buy_count)
    row[f"fdv_per_active_wallet_{suffix}"] = _safe_ratio(fdv, active_wallets)


def _add_time_deltas(row: dict[str, Any]) -> None:
    create = _num(row.get("create_time"))
    for level in ["10k", "20k", "50k", "100k", "500k", "1m"]:
        row[f"create_to_{level}_seconds"] = _delta(create, _num(row.get(f"first_crossed_{level}_time")))
    pairs = [
        ("10k", "20k"),
        ("20k", "50k"),
        ("20k", "100k"),
        ("20k", "500k"),
        ("20k", "1m"),
    ]
    for start, end in pairs:
        row[f"{start}_to_{end}_seconds"] = _delta(
            _num(row.get(f"first_crossed_{start}_time")),
            _num(row.get(f"first_crossed_{end}_time")),
        )


def _outcome_groups(dataset: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "crossed_20k_not_50k": [row for row in dataset if row["crossed_20k"] and not row["crossed_50k"]],
        "crossed_50k_not_100k": [row for row in dataset if row["crossed_50k"] and not row["crossed_100k"]],
        "crossed_100k_not_500k": [row for row in dataset if row["crossed_100k"] and not row["crossed_500k"]],
        "crossed_500k_not_1m": [row for row in dataset if row["crossed_500k"] and not row["crossed_1m"]],
        "crossed_1m": [row for row in dataset if row["crossed_1m"]],
    }


def _comparison_row(feature: str, groups: dict[str, list[dict[str, Any]]], *, family: str) -> dict[str, Any]:
    medians = {}
    iqrs = {}
    counts = {}
    for group, rows in groups.items():
        values = [_num(row.get(feature)) for row in rows]
        values = [value for value in values if value is not None]
        counts[group] = len(values)
        medians[group] = _median(values)
        iqrs[group] = _iqr(values)
    low = medians.get("crossed_20k_not_50k")
    high = medians.get("crossed_1m")
    effect = None if low is None or high is None else high - low
    coverage = sum(counts.values())
    classification = _classify_feature(coverage, effect)
    return {
        "feature_family": family,
        "feature": feature,
        "coverage": coverage,
        "coverage_by_group": json.dumps(counts, sort_keys=True),
        "median_by_group": json.dumps(medians, sort_keys=True),
        "iqr_by_group": json.dumps(iqrs, sort_keys=True),
        "direction": "higher_in_1m" if effect is not None and effect > 0 else ("lower_in_1m" if effect is not None and effect < 0 else "flat_or_unknown"),
        "effect_proxy": effect,
        "appears_newly_visible_forward": feature.startswith(("create_to", "10k_to", "20k_to")) or "metadata" in feature,
        "track_in_official_lifecycle_sample": classification != "no_clear_difference",
        "classification": classification,
    }


def _classify_feature(coverage: int, effect: float | None) -> str:
    if coverage < 10 or effect is None:
        return "data_limited"
    if abs(effect) < 1e-9:
        return "no_clear_difference"
    if effect > 0:
        return "forward_promising_candidate"
    return "possible_risk_filter"


def _fdv_signal_appears(rows: list[dict[str, Any]]) -> str:
    fdv_rows = [row for row in rows if row["feature"].startswith("fdv_per_") and row["classification"] == "forward_promising_candidate"]
    if len(fdv_rows) >= 2:
        return "preliminary_yes_but_quarantined"
    if any(row["classification"] == "data_limited" for row in rows if row["feature"].startswith("fdv_per_")):
        return "data_limited"
    return "not_clear"


def _recommendation(dataset: list[dict[str, Any]], funnel: dict[str, Any], fdv_signal_rows: list[dict[str, Any]]) -> str:
    if not dataset or funnel["counts"].get("crossed_20k", 0) < 20:
        return "B. Current partial sample is too incomplete for pattern analysis; use only for collector debug."
    if _fdv_signal_appears(fdv_signal_rows) in {"preliminary_yes_but_quarantined", "data_limited"}:
        return (
            "A. Current partial sample shows useful preliminary patterns, but official lifecycle sample should "
            "restart at zero after active watcher repair."
        )
    return "C. Current partial sample supports immediate lifecycle watcher design changes."


def _known_limitations() -> list[str]:
    return [
        "Collected before durable trigger-qualified active lifecycle watcher existed.",
        "Pass-based follow-up can miss continuous path, drawdown, reclaim, and terminal maturity states.",
        "Not suitable for validation, paper trading, live trading, final exit logic, or final strategy design.",
        "FDV proxy is not true market cap.",
        "Official clean lifecycle sample must restart from zero after active watcher repair.",
    ]


def _copy_forward_files(source_root: Path, quarantine_root: Path) -> None:
    for name in FORWARD_FILE_NAMES:
        src = source_root / name
        dst = quarantine_root / name
        if src.exists():
            shutil.copy2(src, dst)


def _load_quarantined_files(root: Path) -> dict[str, LoadedJsonl | dict[str, Any]]:
    loaded: dict[str, LoadedJsonl | dict[str, Any]] = {}
    for name in FORWARD_FILE_NAMES:
        path = root / name
        if name.endswith(".jsonl"):
            loaded[name] = _load_jsonl(path)
        elif path.exists():
            try:
                loaded[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loaded[name] = {}
        else:
            loaded[name] = {}
    return loaded


def _load_jsonl(path: Path) -> LoadedJsonl:
    if not path.exists():
        return LoadedJsonl(rows=[], malformed_rows=0, missing=True)
    rows = []
    malformed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    return LoadedJsonl(rows=rows, malformed_rows=malformed, missing=False)


def _jsonl_rows(loaded: dict[str, LoadedJsonl | dict[str, Any]], name: str) -> list[dict[str, Any]]:
    item = loaded.get(name)
    return item.rows if isinstance(item, LoadedJsonl) else []


def _is_birth_candidate(row: dict[str, Any]) -> bool:
    if row.get("freshness_lane") == "birth_watch":
        return True
    if row.get("candidate_classification") == "pumpfun_birth_candidate_observed":
        return True
    if row.get("create_signature") and (row.get("create_time") or row.get("launch_time")):
        return True
    if str(row.get("observation_id") or "").startswith("birth-") and (row.get("create_time") or row.get("launch_time")):
        return True
    return row.get("event_type") == "pumpfun_create"


def _mint(row: dict[str, Any]) -> str:
    return str(row.get("mint") or row.get("token_mint") or "")


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return grouped


def _latest_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for row in rows:
        mint = _mint(row)
        if mint and (mint not in latest or _sort_time(row) >= _sort_time(latest[mint])):
            latest[mint] = row
    return latest


def _merge_birth_rows(existing: dict[str, Any], newer: dict[str, Any]) -> dict[str, Any]:
    earlier, later = (newer, existing) if _sort_time(newer) < _sort_time(existing) else (existing, newer)
    merged = dict(earlier)
    for key, value in later.items():
        if _is_blank(merged.get(key)) and not _is_blank(value):
            merged[key] = value
    for time_key in ["create_time", "launch_time", "observed_at", "first_seen_time", "create_observed_at"]:
        values = [_num(existing.get(time_key)), _num(newer.get(time_key))]
        values = [value for value in values if value is not None]
        if values:
            merged[time_key] = min(values)
    return merged


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _first_cross_row(paths: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in paths:
        fdv = _num(row.get("fdv_proxy"))
        if fdv is not None and fdv >= threshold:
            return row
    return None


def _latest_num(rows: list[dict[str, Any]], key: str) -> float | None:
    for row in reversed(rows):
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _same_bucket_buy_count(events: list[dict[str, Any]], *, bucket: str) -> int | None:
    buckets = Counter()
    for row in events:
        side = str(row.get("side") or row.get("event_type") or "").lower()
        if "buy" not in side:
            continue
        key = row.get("slot") if bucket == "slot" else int(_sort_time(row)) if _sort_time(row) != float("inf") else None
        if key is not None:
            buckets[key] += 1
    return max(buckets.values()) if buckets else None


def _synthetic_activity_proxy(events: list[dict[str, Any]]) -> float | None:
    buys = sum(1 for row in events if "buy" in str(row.get("side") or row.get("event_type") or "").lower())
    sells = sum(1 for row in events if "sell" in str(row.get("side") or row.get("event_type") or "").lower())
    total = buys + sells
    return None if total == 0 else abs(buys - sells) / total


def _sort_time(row: dict[str, Any] | None) -> float:
    if not row:
        return float("inf")
    return (
        _num(
            row.get("timestamp")
            or row.get("observed_at")
            or row.get("create_observed_at")
            or row.get("observation_time")
            or row.get("block_time")
            or row.get("launch_time")
            or row.get("create_time")
        )
        or float("inf")
    )


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in {None, 0}:
        return None
    return num / den


def _rate(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return round(num / den, 6)


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _iqr(values: list[float]) -> float | None:
    if len(values) < 4:
        return None
    ordered = sorted(values)
    q1 = ordered[len(ordered) // 4]
    q3 = ordered[(len(ordered) * 3) // 4]
    return q3 - q1


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _funnel_rows(funnel: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"metric": key, "value": value, "kind": "count"} for key, value in funnel["counts"].items()]
    rows.extend({"metric": key, "value": value, "kind": "conversion_rate"} for key, value in funnel["conversion_rates"].items())
    return rows


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Pre-Lifecycle Watch Forward Sample Quarantine",
            "",
            f"- Label: `{manifest['quarantine_label']}`",
            f"- Reason: {manifest['reason']}",
            f"- Existing files: `{manifest['file_counts']['existing_files']}/{manifest['file_counts']['expected_files']}`",
            f"- First observation time: `{manifest['first_observation_time']}`",
            f"- Latest observation time: `{manifest['latest_observation_time']}`",
            "",
            "## Current Funnel Counts",
            *[f"- {key}: `{value}`" for key, value in manifest["current_funnel_counts"].items()],
            "",
            "## Approved Uses",
            *[f"- {item}" for item in APPROVED_USES],
            "",
            "## Prohibited Uses",
            *[f"- {item}" for item in PROHIBITED_USES],
            "",
            "## Known Limitations",
            *[f"- {item}" for item in _known_limitations()],
            "",
        ]
    )


def _summary_markdown(summary: dict[str, Any]) -> str:
    funnel = summary["funnel_stats"]
    return "\n".join(
        [
            "# Pre-Lifecycle Watch Pattern Preview",
            "",
            "This is a quarantined descriptive preview. It is not validation, backtesting, paper trading, live trading, or strategy design.",
            "",
            f"- Quarantine label: `{summary['quarantine_label']}`",
            f"- Mints analyzed: `{summary['rows_mints_analyzed']}`",
            f"- Crossed 10k: `{funnel['counts'].get('crossed_10k')}`",
            f"- Crossed 20k: `{funnel['counts'].get('crossed_20k')}`",
            f"- Crossed 50k: `{funnel['counts'].get('crossed_50k')}`",
            f"- Crossed 100k: `{funnel['counts'].get('crossed_100k')}`",
            f"- Crossed 500k: `{funnel['counts'].get('crossed_500k')}`",
            f"- Crossed 1m: `{funnel['counts'].get('crossed_1m')}`",
            f"- FDV signal forward read: `{summary['fdv_signal_sanity']['appears_forward']}`",
            f"- Recommendation: {summary['recommendation']}",
            "",
            "## Limitations",
            *[f"- {item}" for item in summary["known_limitations"]],
            "",
            "## Official Sample Reset",
            "- The official clean lifecycle sample should restart from zero after active watcher repair.",
            "",
        ]
    )


def _status_markdown(summary: dict[str, Any]) -> str:
    return _summary_markdown(summary)
