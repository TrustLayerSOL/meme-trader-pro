"""Efficient-mover drawdown recovery versus terminal collapse report.

Descriptive path/exit-side diagnostic only. This module does not run
validation, backtests, optimization, alerts, or execution logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.efficient_mover_continuation_anatomy import (
    build_efficient_mover_universe,
    label_continuation_paths,
)


REPORT_ID = "efficient_mover_drawdown_recovery_report_v0"
DEFAULT_MASTER_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.parquet",
)
DEFAULT_MASTER_JSONL_PATH = data_lake_path(
    "data",
    "backtests",
    "structural_enrichment",
    "tier1_tier2_enrichment",
    "master_tier1_tier2_enriched_runner_fingerprint.jsonl",
)
DEFAULT_SNAPSHOTS_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T011_expanded_rerun",
    "combined_expanded_lifecycle_snapshots.jsonl",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "efficient_mover_drawdown_recovery"
)
DEFAULT_STATUS_PATH = Path("theses/EFFICIENT_MOVER_DRAWDOWN_RECOVERY_STATUS.md")

DRAWDOWN_LEVELS = {"20pct": 0.20, "30pct": 0.30, "40pct": 0.40, "50pct": 0.50}
MILESTONES = {"50k": 50_000.0, "100k": 100_000.0, "200k": 200_000.0, "500k": 500_000.0, "1m": 1_000_000.0}
FEATURES_TO_COMPARE = [
    "bounce_pct_30s",
    "bounce_pct_60s",
    "bounce_pct_2m",
    "bounce_pct_5m",
    "reclaim_speed_seconds",
    "buy_count_change_after_drawdown",
    "sell_count_change_after_drawdown",
    "buy_sell_ratio_after_drawdown",
    "event_count_change_after_drawdown",
    "active_wallets_change_after_drawdown",
    "liquidity_proxy_change_after_drawdown",
    "creator_net_flow_proxy",
    "synthetic_activity_proxy",
]
METHODOLOGY_FLAGS = [
    "descriptive_path_exit_side_diagnostic_only",
    "not_a_thesis",
    "no_thesis_execution",
    "no_validation_execution",
    "no_walk_forward_validation",
    "no_backtest",
    "no_paper_trading",
    "no_live_trading",
    "no_auto_buy_sell",
    "no_private_key_logic",
    "no_wallet_execution",
    "no_order_routing",
    "no_alerts",
    "no_buy_rules",
    "no_sell_rules",
    "no_trading_logic",
    "no_profitability_claims",
    "no_strategy_generation",
    "no_threshold_optimization",
    "no_grid_search",
    "no_ml_black_boxes",
    "fdv_proxy_not_true_market_cap",
    "fixed_drawdown_levels_not_tuned",
]


def build_efficient_mover_drawdown_recovery_report(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    master = _load_master(master_path, jsonl_fallback)
    efficient = label_continuation_paths(build_efficient_mover_universe(master))
    efficient = efficient[efficient["fdv_baseline_high"] == True].copy().reset_index(drop=True)  # noqa: E712
    snapshots = normalize_path_snapshots(_load_snapshots(snapshots_path))
    snapshots = _filter_snapshots_to_efficient(snapshots, efficient)
    drawdown_rows = build_drawdown_event_rows(efficient, snapshots)
    feature_rows = recoverable_vs_terminal_features(drawdown_rows)
    trailing = trailing_stop_30pct_diagnostic(drawdown_rows)
    candidates = exit_side_candidate_features(feature_rows)
    readiness = classify_readiness(efficient, snapshots, drawdown_rows, feature_rows, candidates)
    report = {
        "report_id": REPORT_ID,
        "report_type": "efficient_mover_drawdown_recovery_vs_terminal_collapse",
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {
            "master_path": str(master_path),
            "jsonl_fallback": str(jsonl_fallback),
            "snapshots_path": str(snapshots_path),
        },
        "efficient_mover_universe": summarize_universe(efficient, snapshots),
        "path_data_coverage": path_data_coverage(efficient, snapshots),
        "drawdown_event_counts_by_level": dict(Counter(row["drawdown_level"] for row in drawdown_rows)),
        "drawdown_classification_counts": dict(Counter(row["drawdown_classification"] for row in drawdown_rows)),
        "trailing_stop_30pct_diagnostic": trailing,
        "recoverable_vs_terminal_features": feature_rows,
        "exit_side_candidate_features": candidates,
        "readiness_classification": readiness,
        "next_recommendation": next_recommendation(readiness, trailing, candidates),
        "limitations": [
            "Snapshot-level paths are not continuous tick-level paths.",
            "Drawdown labels are descriptive FDV/valuation-proxy path labels, not trade outcomes.",
            "Several holder/top-holder/creator-flow deltas are unavailable at drawdown timestamp and are marked as missing when absent.",
            "No sell rules, validation, backtest, optimization, alerts, or execution logic was created.",
        ],
    }
    _assert_guardrails(report)
    paths = write_outputs(report, drawdown_rows, feature_rows, trailing, candidates, output, Path(status_path))
    return report, paths


def normalize_path_snapshots(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    result["launch_id"] = _first_present(result, ["launch_id", "token_mint", "mint"]).astype(str)
    result["token_mint"] = _first_present(result, ["token_mint", "mint"])
    result["timestamp"] = _numeric(_first_present(result, ["snapshot_ts", "block_time", "timestamp"]))
    result["fdv_proxy"] = _numeric(_first_present(result, ["valuation_proxy_usd", "fdv_usd", "true_market_cap_usd"]))
    result["event_count_cumulative"] = _numeric(_first_present(result, ["tx_count", "event_count"]))
    result["buy_count_cumulative"] = _numeric(_first_present(result, ["buy_count"]))
    result["sell_count_cumulative"] = _numeric(_first_present(result, ["sell_count"]))
    result["active_wallets_cumulative"] = _numeric(_first_present(result, ["active_wallets", "unique_actors"]))
    result["liquidity_proxy"] = _numeric(_first_present(result, ["liquidity_proxy", "bonding_curve_liquidity_proxy_sol"]))
    result = result[result["launch_id"].notna() & result["timestamp"].notna() & result["fdv_proxy"].notna()].copy()
    return result.sort_values(["launch_id", "timestamp"]).reset_index(drop=True)


def detect_drawdown_events(path: pd.DataFrame) -> list[dict[str, Any]]:
    if path.empty:
        return []
    ordered = path.sort_values("timestamp").reset_index(drop=True)
    trigger_rows = ordered[ordered["fdv_proxy"] >= 20_000]
    if trigger_rows.empty:
        return []
    trigger_idx = int(trigger_rows.index[0])
    trigger_time = _safe_float(ordered.loc[trigger_idx, "timestamp"])
    local_high_fdv = _safe_float(ordered.loc[trigger_idx, "fdv_proxy"]) or 0.0
    local_high_time = trigger_time
    seen_levels: set[str] = set()
    events: list[dict[str, Any]] = []
    for idx in range(trigger_idx + 1, len(ordered)):
        row = ordered.loc[idx]
        fdv = _safe_float(row.get("fdv_proxy")) or 0.0
        ts = _safe_float(row.get("timestamp"))
        if fdv > local_high_fdv:
            local_high_fdv = fdv
            local_high_time = ts
            continue
        if local_high_fdv <= 0:
            continue
        drawdown_fraction = max(0.0, (local_high_fdv - fdv) / local_high_fdv)
        for label, threshold in DRAWDOWN_LEVELS.items():
            if label in seen_levels or drawdown_fraction < threshold:
                continue
            seen_levels.add(label)
            events.append(
                {
                    "launch_id": str(row.get("launch_id")),
                    "token_mint": row.get("token_mint"),
                    "drawdown_level": label,
                    "drawdown_threshold": threshold,
                    "trigger_20k_time": trigger_time,
                    "local_high_time": local_high_time,
                    "local_high_fdv": local_high_fdv,
                    "drawdown_time": ts,
                    "drawdown_fdv": fdv,
                    "drawdown_pct": round(drawdown_fraction * 100, 4),
                    "time_from_20k_to_local_high": local_high_time - trigger_time if local_high_time is not None and trigger_time is not None else None,
                    "time_from_local_high_to_drawdown": ts - local_high_time if ts is not None and local_high_time is not None else None,
                    "available_path_resolution": _path_resolution(ordered),
                    "snapshot_count_after_20k": int(len(ordered) - trigger_idx),
                }
            )
    return events


def classify_drawdown_event(event: dict[str, Any], path: pd.DataFrame) -> dict[str, Any]:
    ordered = path.sort_values("timestamp").reset_index(drop=True)
    after = ordered[ordered["timestamp"] > event["drawdown_time"]].copy()
    result = dict(event)
    if len(after) < 1:
        result.update(_classification_fields("data_limited_drawdown", "insufficient_post_drawdown_path"))
        return result
    local_high = float(event["local_high_fdv"])
    drawdown_time = float(event["drawdown_time"])
    reclaimed = after[after["fdv_proxy"] >= local_high]
    new_high = after[after["fdv_proxy"] > local_high]
    min_after = float(after["fdv_proxy"].min()) if not after.empty else None
    result["reclaimed_prior_high_within_30s"] = _within(reclaimed, drawdown_time, 30)
    result["reclaimed_prior_high_within_60s"] = _within(reclaimed, drawdown_time, 60)
    result["reclaimed_prior_high_within_2m"] = _within(reclaimed, drawdown_time, 120)
    result["reclaimed_prior_high_within_5m"] = _within(reclaimed, drawdown_time, 300)
    result["made_new_high_within_2m"] = _within(new_high, drawdown_time, 120)
    result["made_new_high_within_5m"] = _within(new_high, drawdown_time, 300)
    result["reclaim_speed_seconds"] = _first_delta(reclaimed, drawdown_time)
    result["reached_500k_after_drawdown"] = bool((after["fdv_proxy"] >= 500_000).any())
    result["reached_1m_after_drawdown"] = bool((after["fdv_proxy"] >= 1_000_000).any())
    result["dropped_50pct_from_local_high_after_30pct_drawdown"] = bool(min_after is not None and min_after <= local_high * 0.50)
    result["dropped_70pct_from_local_high_after_30pct_drawdown"] = bool(min_after is not None and min_after <= local_high * 0.30)
    result["dropped_80pct_from_local_high_after_30pct_drawdown"] = bool(min_after is not None and min_after <= local_high * 0.20)
    result["failed_to_reclaim_within_5m"] = not result["reclaimed_prior_high_within_5m"]
    result["failed_to_reclaim_within_10m"] = not _within(reclaimed, drawdown_time, 600)
    result["reached_higher_milestone_after_drawdown"] = _reached_higher_milestone(local_high, after)
    result["never_reached_next_milestone_after_drawdown"] = not result["reached_higher_milestone_after_drawdown"]
    if result["reclaimed_prior_high_within_5m"] or result["made_new_high_within_5m"] or result["reached_higher_milestone_after_drawdown"]:
        result.update(_classification_fields("recoverable_drawdown_proxy", "reclaimed_or_made_new_high_or_reached_higher_milestone"))
    elif result["failed_to_reclaim_within_10m"] or result["dropped_70pct_from_local_high_after_30pct_drawdown"]:
        result.update(_classification_fields("terminal_drawdown_proxy", "failed_reclaim_or_deeper_drawdown_proxy"))
    else:
        result.update(_classification_fields("data_limited_drawdown", "insufficient_resolution_for_recovery_or_terminal_proxy"))
    result.update(_drawdown_feature_deltas(result, ordered))
    return result


def build_drawdown_event_rows(efficient: pd.DataFrame, snapshots: pd.DataFrame) -> list[dict[str, Any]]:
    master_lookup = efficient.set_index("launch_id").to_dict("index") if "launch_id" in efficient.columns else {}
    rows = []
    for launch_id, path in snapshots.groupby("launch_id", sort=True):
        for event in detect_drawdown_events(path):
            classified = classify_drawdown_event(event, path)
            master_row = master_lookup.get(str(launch_id), {})
            classified.update(
                {
                    "milestone_tier": master_row.get("milestone_tier"),
                    "creator": master_row.get("creator"),
                    "launch_date": master_row.get("launch_date"),
                    "creator_net_flow_proxy": master_row.get("creator_net_flow_sol_before_20k"),
                    "synthetic_activity_proxy": master_row.get("synthetic_activity_proxy"),
                    "top_holder_share_proxy": master_row.get("top_holder_share_proxy"),
                    "top_10_holder_share_proxy": master_row.get("top_10_holder_share_proxy"),
                    "holder_retention_proxy": master_row.get("holder_retention_proxy"),
                    "holder_churn_proxy": master_row.get("holder_churn_proxy"),
                }
            )
            rows.append(classified)
    return rows


def recoverable_vs_terminal_features(drawdown_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(drawdown_rows)
    if frame.empty:
        return []
    rows = []
    for level in DRAWDOWN_LEVELS:
        level_frame = frame[frame["drawdown_level"] == level]
        recover = level_frame[level_frame["drawdown_classification"] == "recoverable_drawdown_proxy"]
        terminal = level_frame[level_frame["drawdown_classification"] == "terminal_drawdown_proxy"]
        for feature in FEATURES_TO_COMPARE:
            rec_values = _numeric(recover.get(feature, pd.Series(dtype=object))).dropna()
            term_values = _numeric(terminal.get(feature, pd.Series(dtype=object))).dropna()
            coverage = _pct(int(_numeric(level_frame.get(feature, pd.Series(dtype=object))).notna().sum()), len(level_frame))
            row = {
                "drawdown_level": level,
                "feature": feature,
                "recoverable_rows": int(len(rec_values)),
                "terminal_rows": int(len(term_values)),
                "coverage_pct": coverage,
                "recoverable_median": _median(rec_values),
                "terminal_median": _median(term_values),
                "recoverable_iqr": _iqr(rec_values),
                "terminal_iqr": _iqr(term_values),
                "effect_size_proxy": _effect_size(rec_values, term_values),
                "top_date_concentration_pct": _top_share_pct(level_frame, "launch_date"),
                "top_creator_concentration_pct": _top_share_pct(level_frame, "creator"),
            }
            row["classification"] = classify_feature_candidate(row)
            rows.append(row)
    return rows


def classify_feature_candidate(row: dict[str, Any]) -> str:
    if row["coverage_pct"] < 25 or row["recoverable_rows"] < 3 or row["terminal_rows"] < 3:
        return "data_limited"
    if row["top_date_concentration_pct"] >= 60 or row["top_creator_concentration_pct"] >= 60:
        return "data_limited"
    effect = row["effect_size_proxy"] or 0.0
    if abs(effect) < 0.1:
        return "no_clear_difference"
    if effect > 0:
        return "recovery_positive_candidate"
    return "terminal_collapse_warning_candidate"


def trailing_stop_30pct_diagnostic(drawdown_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in drawdown_rows if row.get("drawdown_level") == "30pct"]
    recoverable = [row for row in rows if row.get("drawdown_classification") == "recoverable_drawdown_proxy"]
    terminal = [row for row in rows if row.get("drawdown_classification") == "terminal_drawdown_proxy"]
    limited = [row for row in rows if row.get("drawdown_classification") == "data_limited_drawdown"]
    too_early = [row for row in rows if row.get("reached_higher_milestone_after_drawdown") or row.get("reclaimed_prior_high_within_5m")]
    return {
        "diagnostic_name": "30pct_trailing_stop_diagnostic",
        "drawdown_30pct_events": len(rows),
        "recoverable_count": len(recoverable),
        "terminal_count": len(terminal),
        "data_limited_count": len(limited),
        "recoverable_pct": _pct(len(recoverable), len(rows)),
        "terminal_pct": _pct(len(terminal), len(rows)),
        "data_limited_pct": _pct(len(limited), len(rows)),
        "later_reached_higher_milestone_count": sum(bool(row.get("reached_higher_milestone_after_drawdown")) for row in rows),
        "would_have_exited_too_early_count": len(too_early),
        "appears_too_blunt": bool(rows and _pct(len(too_early), len(rows)) >= 25),
        "interpretation": "Descriptive diagnostic only; this does not create a stop, sell rule, or execution recommendation.",
    }


def exit_side_candidate_features(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row
        for row in feature_rows
        if row["classification"] in {"recovery_positive_candidate", "terminal_collapse_warning_candidate", "path_latency_candidate"}
    ]
    candidates = sorted(candidates, key=lambda row: (-abs(row.get("effect_size_proxy") or 0), row["drawdown_level"], row["feature"]))
    return [
        {
            "candidate_id": f"DDR-{idx:03d}",
            "drawdown_level": row["drawdown_level"],
            "feature": row["feature"],
            "classification": row["classification"],
            "coverage_pct": row["coverage_pct"],
            "effect_size_proxy": row["effect_size_proxy"],
            "why_it_may_matter": _candidate_interpretation(row),
            "missing_data_needed": "higher path resolution or feature coverage" if row["coverage_pct"] < 70 else "none_before_exit_thesis_design",
            "ready_for_exit_thesis": bool(row["coverage_pct"] >= 50 and abs(row.get("effect_size_proxy") or 0) >= 0.25),
        }
        for idx, row in enumerate(candidates[:10], start=1)
    ]


def classify_readiness(
    efficient: pd.DataFrame,
    snapshots: pd.DataFrame,
    drawdown_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str:
    if snapshots.empty or len(drawdown_rows) == 0:
        return "drawdown_recovery_report_blocked_by_path_resolution"
    counts = Counter(row["drawdown_classification"] for row in drawdown_rows if row["drawdown_level"] == "30pct")
    if counts.get("recoverable_drawdown_proxy", 0) < 10 or counts.get("terminal_drawdown_proxy", 0) < 10:
        return "drawdown_recovery_report_data_limited"
    path_coverage = _pct(snapshots["launch_id"].nunique(), len(efficient))
    if path_coverage < 70:
        return "drawdown_recovery_report_blocked_by_path_resolution"
    ready_candidates = [candidate for candidate in candidates if candidate["ready_for_exit_thesis"]]
    if ready_candidates:
        return "drawdown_recovery_report_ready_for_exit_thesis"
    if feature_rows:
        return "drawdown_recovery_report_inconclusive"
    return "drawdown_recovery_report_data_limited"


def summarize_universe(efficient: pd.DataFrame, snapshots: pd.DataFrame) -> dict[str, Any]:
    return {
        "definition": "same fixed high-FDV-efficiency universe used in prior audits",
        "rows": int(len(efficient)),
        "milestone_tier_distribution": dict(Counter(efficient.get("milestone_tier", pd.Series(dtype=object)).dropna().astype(str).tolist())),
        "date_distribution_top10": dict(Counter(efficient.get("launch_date", pd.Series(dtype=object)).dropna().astype(str).tolist()).most_common(10)),
        "creator_distribution_top10": dict(Counter(efficient.get("creator", pd.Series(dtype=object)).dropna().astype(str).tolist()).most_common(10)),
        "launches_with_path_data": int(snapshots["launch_id"].nunique()) if not snapshots.empty else 0,
        "path_data_coverage_pct": _pct(int(snapshots["launch_id"].nunique()) if not snapshots.empty else 0, len(efficient)),
    }


def path_data_coverage(efficient: pd.DataFrame, snapshots: pd.DataFrame) -> dict[str, Any]:
    per_launch = snapshots.groupby("launch_id")["timestamp"].agg(["count", "min", "max"]).reset_index() if not snapshots.empty else pd.DataFrame()
    return {
        "efficient_mover_rows": int(len(efficient)),
        "launches_with_path_rows": int(len(per_launch)),
        "snapshot_rows": int(len(snapshots)),
        "median_snapshots_per_launch": _median(_numeric(per_launch["count"])) if not per_launch.empty else None,
        "median_path_span_seconds": _median(_numeric(per_launch["max"] - per_launch["min"])) if not per_launch.empty else None,
        "path_resolution_note": "snapshot_level_fdv_proxy_path",
    }


def next_recommendation(readiness: str, trailing: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if readiness == "drawdown_recovery_report_ready_for_exit_thesis":
        action = "run_formal_descriptive_exit_path_thesis_for_top_candidate_without_rules"
    elif readiness == "drawdown_recovery_report_blocked_by_path_resolution":
        action = "improve_path_resolution_before_exit_thesis"
    elif readiness == "drawdown_recovery_report_data_limited":
        action = "expand_or_repair_drawdown_path_coverage_before_exit_thesis"
    else:
        action = "manual_review_drawdown_examples_before_formal_exit_thesis"
    return {
        "action": action,
        "do_not_execute_in_this_sprint": True,
        "what_not_to_do_next": "Do not create sell rules, stops, validation, optimization, or execution logic from this diagnostic report.",
    }


def write_outputs(
    report: dict[str, Any],
    drawdown_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    trailing: dict[str, Any],
    candidates: list[dict[str, Any]],
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "efficient_mover_drawdown_recovery_summary.json",
        "summary_markdown_path": output / "efficient_mover_drawdown_recovery_summary.md",
        "drawdown_events_path": output / "drawdown_events.csv",
        "recoverable_vs_terminal_features_path": output / "recoverable_vs_terminal_features.csv",
        "trailing_stop_30pct_diagnostic_path": output / "trailing_stop_30pct_diagnostic.csv",
        "exit_side_candidate_features_path": output / "exit_side_candidate_features.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_markdown_path"].write_text(_summary_markdown(report), encoding="utf-8")
    pd.DataFrame(drawdown_rows).to_csv(paths["drawdown_events_path"], index=False)
    pd.DataFrame(feature_rows).to_csv(paths["recoverable_vs_terminal_features_path"], index=False)
    pd.DataFrame([trailing]).to_csv(paths["trailing_stop_30pct_diagnostic_path"], index=False)
    pd.DataFrame(candidates).to_csv(paths["exit_side_candidate_features_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _filter_snapshots_to_efficient(snapshots: pd.DataFrame, efficient: pd.DataFrame) -> pd.DataFrame:
    launch_ids = set(efficient.get("launch_id", pd.Series(dtype=object)).dropna().astype(str).tolist())
    mints = set(efficient.get("token_mint", pd.Series(dtype=object)).dropna().astype(str).tolist())
    if snapshots.empty:
        return snapshots
    return snapshots[(snapshots["launch_id"].astype(str).isin(launch_ids)) | (snapshots["token_mint"].astype(str).isin(mints))].copy()


def _classification_fields(classification: str, reason: str) -> dict[str, Any]:
    return {
        "drawdown_classification": classification,
        "drawdown_classification_reason": reason,
        "reclaimed_prior_high_within_30s": False,
        "reclaimed_prior_high_within_60s": False,
        "reclaimed_prior_high_within_2m": False,
        "reclaimed_prior_high_within_5m": False,
        "made_new_high_within_2m": False,
        "made_new_high_within_5m": False,
        "reclaim_speed_seconds": None,
        "reached_500k_after_drawdown": False,
        "reached_1m_after_drawdown": False,
        "reached_higher_milestone_after_drawdown": False,
        "never_reached_next_milestone_after_drawdown": True,
        "failed_to_reclaim_within_5m": True,
        "failed_to_reclaim_within_10m": True,
    }


def _drawdown_feature_deltas(event: dict[str, Any], path: pd.DataFrame) -> dict[str, Any]:
    drawdown_row = _nearest_snapshot(path, event["drawdown_time"])
    result = {}
    for label, seconds in [("30s", 30), ("60s", 60), ("2m", 120), ("5m", 300)]:
        future = _nearest_snapshot(path, float(event["drawdown_time"]) + seconds)
        result[f"bounce_pct_{label}"] = _pct_change(future.get("fdv_proxy"), event["drawdown_fdv"]) if future is not None else None
    if drawdown_row is not None:
        for src, dst in [
            ("buy_count_cumulative", "buy_count_change_after_drawdown"),
            ("sell_count_cumulative", "sell_count_change_after_drawdown"),
            ("event_count_cumulative", "event_count_change_after_drawdown"),
            ("active_wallets_cumulative", "active_wallets_change_after_drawdown"),
            ("liquidity_proxy", "liquidity_proxy_change_after_drawdown"),
        ]:
            after_5m = _nearest_snapshot(path, float(event["drawdown_time"]) + 300)
            result[dst] = _delta(after_5m.get(src) if after_5m is not None else None, drawdown_row.get(src))
        buy_delta = result.get("buy_count_change_after_drawdown")
        sell_delta = result.get("sell_count_change_after_drawdown")
        result["buy_sell_ratio_after_drawdown"] = _ratio(buy_delta, sell_delta)
    return result


def _within(rows: pd.DataFrame, start_ts: float, seconds: int) -> bool:
    if rows.empty:
        return False
    return bool(((rows["timestamp"] - start_ts) <= seconds).any())


def _first_delta(rows: pd.DataFrame, start_ts: float) -> float | None:
    if rows.empty:
        return None
    return _safe_float(rows.iloc[0]["timestamp"]) - start_ts


def _reached_higher_milestone(local_high: float, after: pd.DataFrame) -> bool:
    next_levels = [value for value in MILESTONES.values() if value > local_high]
    if not next_levels:
        return bool((after["fdv_proxy"] > local_high).any())
    return bool((after["fdv_proxy"] >= min(next_levels)).any())


def _path_resolution(path: pd.DataFrame) -> str:
    gaps = _numeric(path["timestamp"]).sort_values().diff().dropna()
    if gaps.empty:
        return "single_snapshot"
    median_gap = gaps.median()
    if median_gap <= 30:
        return "lte_30s_snapshot_resolution"
    if median_gap <= 60:
        return "lte_60s_snapshot_resolution"
    return "coarse_snapshot_resolution"


def _nearest_snapshot(path: pd.DataFrame, ts: float) -> pd.Series | None:
    if path.empty:
        return None
    indexed = path.assign(distance=(path["timestamp"] - ts).abs()).sort_values(["distance", "timestamp"])
    return indexed.iloc[0] if not indexed.empty else None


def _pct_change(new: Any, old: Any) -> float | None:
    new_f = _safe_float(new)
    old_f = _safe_float(old)
    if new_f is None or old_f is None or old_f == 0:
        return None
    return round(((new_f - old_f) / old_f) * 100, 4)


def _delta(new: Any, old: Any) -> float | None:
    new_f = _safe_float(new)
    old_f = _safe_float(old)
    if new_f is None or old_f is None:
        return None
    return round(new_f - old_f, 4)


def _ratio(num: Any, den: Any) -> float | None:
    num_f = _safe_float(num)
    den_f = _safe_float(den)
    if num_f is None or den_f is None or den_f == 0:
        return None
    return round(num_f / den_f, 4)


def _effect_size(recoverable: pd.Series, terminal: pd.Series) -> float:
    if recoverable.empty or terminal.empty:
        return 0.0
    raw = float(recoverable.median() - terminal.median())
    if abs(raw) < 1e-12:
        return 0.0
    pooled = pd.concat([recoverable, terminal])
    iqr = pooled.quantile(0.75) - pooled.quantile(0.25)
    if iqr and not pd.isna(iqr):
        return round(raw / float(iqr), 4)
    return round(raw, 4)


def _candidate_interpretation(row: dict[str, Any]) -> str:
    if row["classification"] == "recovery_positive_candidate":
        return "Higher feature values are descriptively associated with recoverable drawdown proxies."
    if row["classification"] == "terminal_collapse_warning_candidate":
        return "Higher feature values are descriptively associated with terminal drawdown proxies."
    return "Path latency or feature coverage needs more review."


def _load_master(master_path: Path | str, jsonl_fallback: Path | str) -> pd.DataFrame:
    path = Path(master_path)
    fallback = Path(jsonl_fallback)
    if path.exists():
        return pd.read_parquet(path)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    raise FileNotFoundError(f"missing enriched master {path} and fallback {fallback}")


def _load_snapshots(path: Path | str) -> pd.DataFrame:
    raw = Path(path)
    if not raw.exists():
        raise FileNotFoundError(f"missing snapshots {raw}")
    if raw.suffix == ".parquet":
        return pd.read_parquet(raw)
    if raw.suffix == ".csv":
        return pd.read_csv(raw)
    return pd.read_json(raw, orient="records", lines=True)


def _first_present(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series([None] * len(frame), index=frame.index, dtype=object)
    for column in columns:
        if column in frame.columns:
            result = result.where(result.notna(), frame[column])
    return result


def _numeric(series: Any) -> pd.Series:
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return pd.to_numeric(series, errors="coerce")


def _median(series: pd.Series) -> float | None:
    return _round_or_none(series.median() if not series.empty else None)


def _iqr(series: pd.Series) -> float | None:
    return _round_or_none((series.quantile(0.75) - series.quantile(0.25)) if len(series) > 1 else None)


def _top_share_pct(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    counts = Counter(str(value) for value in frame[column].dropna().tolist())
    return _pct(counts.most_common(1)[0][1], len(frame)) if counts else 0.0


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Efficient-Mover Drawdown Recovery Report",
        "",
        f"- Efficient-mover rows: `{report['efficient_mover_universe']['rows']}`",
        f"- Readiness: `{report['readiness_classification']}`",
        f"- 30% diagnostic: `{report['trailing_stop_30pct_diagnostic']}`",
        "- Scope: descriptive path/exit-side diagnostic only; no sell rules, validation, backtest, optimization, alerts, or execution logic.",
    ]
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Efficient-Mover Drawdown Recovery Status",
        "",
        "This report was created to distinguish recoverable drawdown proxies from terminal drawdown proxies inside the high-FDV-efficiency universe.",
        "",
        "## Efficient-Mover Population",
        f"- `{report['efficient_mover_universe']}`",
        "",
        "## Drawdown Event Counts",
        f"- By level: `{report['drawdown_event_counts_by_level']}`",
        f"- By classification: `{report['drawdown_classification_counts']}`",
        "",
        "## 30% Trailing Stop Diagnostic",
        f"- `{report['trailing_stop_30pct_diagnostic']}`",
        "",
        "## Strongest Candidate Features",
    ]
    lines.extend([f"- {row['feature']} ({row['drawdown_level']}): {row['classification']}" for row in report["exit_side_candidate_features"][:10]] or ["- None with sufficient support."])
    lines.extend(
        [
            "",
            "## Readiness",
            f"- `{report['readiness_classification']}`",
            "",
            "## Next Recommendation",
            f"- `{report['next_recommendation']['action']}`",
            "",
            "## Limitations",
        ]
    )
    lines.extend([f"- {item}" for item in report["limitations"]])
    lines.append("")
    return "\n".join(lines)


def _guardrails() -> dict[str, Any]:
    return {
        "thesis_runs": 0,
        "validation_runs": 0,
        "walk_forward_runs": 0,
        "backtests_run": 0,
        "paper_trading_runs": 0,
        "live_trading_runs": 0,
        "trading_logic_added": False,
        "buy_rules_created": False,
        "sell_rules_created": False,
        "threshold_optimization": False,
        "grid_search": False,
        "ml": False,
        "alerts_created": False,
    }


def _assert_guardrails(report: dict[str, Any]) -> None:
    text = json.dumps(report, default=_json_default).lower()
    for blocked in ("insider", "scammer", "wash trader", "manipulator", "guaranteed smart money"):
        if blocked in text:
            raise ValueError(f"unsupported label leaked into report: {blocked}")
    guardrails = report.get("guardrails", {})
    if guardrails.get("validation_runs") or guardrails.get("trading_logic_added") or guardrails.get("sell_rules_created"):
        raise ValueError("guardrail violation")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return str(value)
