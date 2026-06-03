"""FDV-efficiency real-time observability audit.

Diagnostic-only report asking whether FDV-efficiency proxy features are
available at early valuation-proxy trigger snapshots. This module does not run
thesis validation, backtests, optimization, alerts, or execution logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.mtp_research.data_paths import data_lake_path


REPORT_ID = "fdv_efficiency_observability_audit_v0"
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
DEFAULT_TRIGGER_20K_PATH = data_lake_path(
    "data",
    "backtests",
    "diagnostics",
    "reports",
    "T011_expanded_rerun",
    "expanded_trigger_20k_feature_rows.csv",
)
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "fdv_efficiency_observability"
)
DEFAULT_STATUS_PATH = Path("theses/FDV_EFFICIENCY_OBSERVABILITY_STATUS.md")

TRIGGER_LEVELS = {"10k": 10_000.0, "15k": 15_000.0, "20k": 20_000.0, "30k": 30_000.0}
MILESTONE_LEVELS = {
    "10k": 10_000.0,
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
ACTIONABILITY_TARGETS = {
    "10k": ["20k", "50k", "100k", "500k", "1m"],
    "15k": ["20k", "50k", "100k", "500k", "1m"],
    "20k": ["50k", "100k", "500k", "1m"],
    "30k": ["50k", "100k", "500k", "1m"],
}
ACTIONABILITY_BUCKETS = (
    "under_5s",
    "5s_to_15s",
    "15s_to_30s",
    "30s_to_60s",
    "1m_to_2m",
    "2m_to_5m",
    "5m_plus",
    "never",
)
METHODOLOGY_FLAGS = [
    "diagnostic_report_only",
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
    "snapshot_level_replay_not_tick_level_execution",
]


def build_fdv_efficiency_observability_audit(
    *,
    master_path: Path | str = DEFAULT_MASTER_PATH,
    jsonl_fallback: Path | str = DEFAULT_MASTER_JSONL_PATH,
    snapshots_path: Path | str = DEFAULT_SNAPSHOTS_PATH,
    trigger_20k_path: Path | str = DEFAULT_TRIGGER_20K_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    status_path: Path | str = DEFAULT_STATUS_PATH,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    master = _load_master(master_path, jsonl_fallback)
    snapshots = _load_snapshots(snapshots_path)
    snapshots = _filter_to_master_universe(snapshots, master)
    trigger_rows, actionability_rows, latency_rows, recon_summary = reconstruct_trigger_observability(snapshots)
    trigger_frame = pd.DataFrame(trigger_rows)
    actionability_frame = pd.DataFrame(actionability_rows)
    latency_frame = pd.DataFrame(latency_rows)

    trigger_rows = _add_efficiency_visibility(trigger_frame).to_dict("records") if not trigger_frame.empty else []
    trigger_frame = pd.DataFrame(trigger_rows)
    coverage = _coverage_by_trigger(trigger_frame)
    actionability_summary = _actionability_summary(actionability_frame)
    latency_summary = _snapshot_latency_summary(latency_frame)
    earliest_visibility = _earliest_efficiency_visibility(trigger_frame, master)
    classification = _classify_feasibility(coverage, actionability_summary, latency_summary)
    report = {
        "report_id": REPORT_ID,
        "report_type": "fdv_efficiency_real_time_observability_audit",
        "methodology_flags": METHODOLOGY_FLAGS,
        "guardrails": _guardrails(),
        "source_paths": {
            "master_path": str(master_path),
            "jsonl_fallback": str(jsonl_fallback),
            "snapshots_path": str(snapshots_path),
            "trigger_20k_path": str(trigger_20k_path),
        },
        "rows_analyzed": int(_unique_launch_count(snapshots)),
        "master_rows_loaded": int(len(master)),
        "snapshot_rows_loaded": int(len(snapshots)),
        "trigger_levels_tested": list(TRIGGER_LEVELS.keys()),
        "milestone_levels_reconstructed": list(MILESTONE_LEVELS.keys()),
        "reconstruction_summary": recon_summary,
        "observability_coverage_by_trigger": coverage,
        "actionability_window_summary": actionability_summary,
        "snapshot_latency_summary": latency_summary,
        "earliest_efficiency_visibility": earliest_visibility,
        "classification": classification,
        "recommendation": _recommendation(classification),
        "limitations": [
            "Trigger times are reconstructed from lifecycle snapshots, not continuous tick data.",
            "FDV/valuation proxy only; true market-cap claims remain blocked.",
            "Actionability window is a timing diagnostic only and is not a tradability claim.",
            "No thesis, validation, walk-forward validation, backtest, optimization, alerts, or execution logic was run.",
        ],
    }
    _assert_guardrails(report)
    paths = _write_outputs(report, trigger_frame, actionability_frame, latency_frame, output, Path(status_path))
    return report, paths


def reconstruct_trigger_observability(
    snapshots: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    frame = _normalize_snapshots(snapshots)
    trigger_rows: list[dict[str, Any]] = []
    actionability_rows: list[dict[str, Any]] = []
    latency_rows: list[dict[str, Any]] = []
    for launch_id, launch_frame in frame.groupby("launch_key", sort=True):
        launch = launch_frame.sort_values(["snapshot_ts", "launch_age_seconds"]).reset_index(drop=True)
        crossing = _first_crossings(launch)
        for trigger_label, trigger_value in TRIGGER_LEVELS.items():
            trigger_idx = crossing.get(trigger_label)
            if trigger_idx is None:
                trigger_rows.append(_missing_trigger_row(launch, trigger_label, "trigger_not_observed_in_snapshots"))
                continue
            trigger_snapshot = launch.loc[trigger_idx]
            row = _trigger_row(launch, trigger_snapshot, trigger_idx, trigger_label, trigger_value)
            trigger_rows.append(row)
            latency_rows.append(_latency_row(launch, trigger_snapshot, trigger_idx, trigger_label))
            for target_label in ACTIONABILITY_TARGETS[trigger_label]:
                actionability_rows.append(_actionability_row(launch, crossing, row, target_label))
    summary = {
        "launches_seen": int(frame["launch_key"].nunique()) if not frame.empty else 0,
        "snapshot_rows_seen": int(len(frame)),
        "trigger_levels": list(TRIGGER_LEVELS.keys()),
        "milestone_levels": list(MILESTONE_LEVELS.keys()),
        "trigger_semantics": "first_snapshot_at_or_above_valuation_proxy_level",
        "coverage_by_trigger": _coverage_by_trigger(pd.DataFrame(trigger_rows)),
    }
    return trigger_rows, actionability_rows, latency_rows, summary


def bucket_actionability_window(seconds: float | int | None) -> str:
    if seconds is None or pd.isna(seconds):
        return "never"
    value = float(seconds)
    if value < 5:
        return "under_5s"
    if value <= 15:
        return "5s_to_15s"
    if value <= 30:
        return "15s_to_30s"
    if value <= 60:
        return "30s_to_60s"
    if value <= 120:
        return "1m_to_2m"
    if value <= 300:
        return "2m_to_5m"
    return "5m_plus"


def _normalize_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty:
        return pd.DataFrame()
    frame = snapshots.copy()
    frame["launch_key"] = _first_present(frame, ["launch_id", "token_mint", "mint"]).astype(str)
    frame["token_mint"] = _first_present(frame, ["token_mint", "mint"])
    frame["valuation_proxy_usd"] = _numeric(_first_present(frame, ["valuation_proxy_usd", "fdv_usd", "trigger_fdv_proxy"]))
    frame["snapshot_ts"] = _numeric(_first_present(frame, ["snapshot_ts", "block_time", "timestamp"]))
    frame["launch_ts"] = _numeric(_first_present(frame, ["launch_ts", "launch_time_ts"]))
    frame["launch_age_seconds"] = _numeric(_first_present(frame, ["launch_age_seconds", "trigger_age_seconds"]))
    frame["event_count"] = _numeric(_first_present(frame, ["tx_count", "event_count", "event_count_at_20k"]))
    frame["buy_count"] = _numeric(_first_present(frame, ["buy_count", "buy_count_at_20k"]))
    frame["sell_count"] = _numeric(_first_present(frame, ["sell_count", "sell_count_at_20k"]))
    frame["active_wallets"] = _numeric(_first_present(frame, ["active_wallets", "unique_actors", "active_wallets_at_20k", "unique_actors_at_20k"]))
    frame = frame[frame["valuation_proxy_usd"].notna() & frame["snapshot_ts"].notna() & frame["launch_key"].notna()].copy()
    return frame.sort_values(["launch_key", "snapshot_ts", "launch_age_seconds"]).reset_index(drop=True)


def _first_crossings(launch: pd.DataFrame) -> dict[str, int]:
    crossings: dict[str, int] = {}
    for label, value in MILESTONE_LEVELS.items():
        crossed = launch.index[launch["valuation_proxy_usd"] >= value].tolist()
        if crossed:
            crossings[label] = int(crossed[0])
    return crossings


def _trigger_row(
    launch: pd.DataFrame,
    trigger_snapshot: pd.Series,
    trigger_idx: int,
    trigger_label: str,
    trigger_value: float,
) -> dict[str, Any]:
    event_count = _safe_float(trigger_snapshot.get("event_count"))
    buy_count = _safe_float(trigger_snapshot.get("buy_count"))
    sell_count = _safe_float(trigger_snapshot.get("sell_count"))
    active_wallets = _safe_float(trigger_snapshot.get("active_wallets"))
    valuation = _safe_float(trigger_snapshot.get("valuation_proxy_usd"))
    trigger_time = _safe_float(trigger_snapshot.get("snapshot_ts"))
    return {
        "launch_id": str(trigger_snapshot.get("launch_id") or trigger_snapshot.get("launch_key")),
        "token_mint": _none_if_nan(trigger_snapshot.get("token_mint")),
        "trigger_level": trigger_label,
        "trigger_value": trigger_value,
        "trigger_time": trigger_time,
        "trigger_age_seconds": _safe_float(trigger_snapshot.get("launch_age_seconds")),
        "valuation_at_trigger": valuation,
        "event_count_at_trigger": event_count,
        "buy_count_at_trigger": buy_count,
        "sell_count_at_trigger": sell_count,
        "active_wallets_at_trigger": active_wallets,
        "buy_sell_ratio_at_trigger": _ratio(buy_count, sell_count),
        "fdv_per_event_at_trigger": _ratio(valuation, event_count),
        "fdv_per_buy_at_trigger": _ratio(valuation, buy_count),
        "fdv_per_active_wallet_at_trigger": _ratio(valuation, active_wallets),
        "feature_window_max_time": trigger_time,
        "feature_snapshot_index": trigger_idx,
        "observable_at_trigger": _observable(event_count, buy_count, active_wallets, valuation),
        "leakage_safe": bool(trigger_time <= _safe_float(trigger_snapshot.get("snapshot_ts"))),
        "missing_reason": None if _observable(event_count, buy_count, active_wallets, valuation) else "missing_required_trigger_feature",
        "feature_construction": "trigger_snapshot_fields_only",
        "future_outcome_used": False,
        "post_trigger_events_used": False,
    }


def _missing_trigger_row(launch: pd.DataFrame, trigger_label: str, reason: str) -> dict[str, Any]:
    first = launch.iloc[0]
    return {
        "launch_id": str(first.get("launch_id") or first.get("launch_key")),
        "token_mint": _none_if_nan(first.get("token_mint")),
        "trigger_level": trigger_label,
        "trigger_value": TRIGGER_LEVELS[trigger_label],
        "trigger_time": None,
        "trigger_age_seconds": None,
        "valuation_at_trigger": None,
        "event_count_at_trigger": None,
        "buy_count_at_trigger": None,
        "sell_count_at_trigger": None,
        "active_wallets_at_trigger": None,
        "buy_sell_ratio_at_trigger": None,
        "fdv_per_event_at_trigger": None,
        "fdv_per_buy_at_trigger": None,
        "fdv_per_active_wallet_at_trigger": None,
        "feature_window_max_time": None,
        "feature_snapshot_index": None,
        "observable_at_trigger": False,
        "leakage_safe": False,
        "missing_reason": reason,
        "feature_construction": "not_observed",
        "future_outcome_used": False,
        "post_trigger_events_used": False,
    }


def _actionability_row(launch: pd.DataFrame, crossing: dict[str, int], trigger_row: dict[str, Any], target_label: str) -> dict[str, Any]:
    target_idx = crossing.get(target_label)
    trigger_time = trigger_row["trigger_time"]
    target_time = None
    delta = None
    if target_idx is not None and trigger_time is not None:
        target_time = _safe_float(launch.loc[target_idx].get("snapshot_ts"))
        if target_time is not None and target_time >= float(trigger_time):
            delta = target_time - float(trigger_time)
    return {
        "launch_id": trigger_row["launch_id"],
        "token_mint": trigger_row["token_mint"],
        "trigger_level": trigger_row["trigger_level"],
        "target_level": target_label,
        "trigger_time": trigger_time,
        "target_time": target_time,
        "time_to_target_seconds": delta,
        "actionability_bucket": bucket_actionability_window(delta),
        "target_observed_after_trigger": delta is not None,
    }


def _latency_row(launch: pd.DataFrame, trigger_snapshot: pd.Series, trigger_idx: int, trigger_label: str) -> dict[str, Any]:
    trigger_time = _safe_float(trigger_snapshot.get("snapshot_ts"))
    prev_time = _safe_float(launch.loc[trigger_idx - 1].get("snapshot_ts")) if trigger_idx > 0 else None
    next_time = _safe_float(launch.loc[trigger_idx + 1].get("snapshot_ts")) if trigger_idx + 1 < len(launch) else None
    previous_events = _safe_float(launch.loc[trigger_idx - 1].get("event_count")) if trigger_idx > 0 else None
    next_events = _safe_float(launch.loc[trigger_idx + 1].get("event_count")) if trigger_idx + 1 < len(launch) else None
    trigger_events = _safe_float(trigger_snapshot.get("event_count"))
    seconds_since_previous = trigger_time - prev_time if trigger_time is not None and prev_time is not None else None
    seconds_to_next = next_time - trigger_time if trigger_time is not None and next_time is not None else None
    return {
        "launch_id": str(trigger_snapshot.get("launch_id") or trigger_snapshot.get("launch_key")),
        "token_mint": _none_if_nan(trigger_snapshot.get("token_mint")),
        "trigger_level": trigger_label,
        "previous_snapshot_time": prev_time,
        "trigger_snapshot_time": trigger_time,
        "next_snapshot_time": next_time,
        "seconds_since_previous_snapshot": seconds_since_previous,
        "seconds_to_next_snapshot": seconds_to_next,
        "events_between_previous_and_trigger": trigger_events - previous_events if trigger_events is not None and previous_events is not None else None,
        "events_between_trigger_and_next": next_events - trigger_events if next_events is not None and trigger_events is not None else None,
        "snapshot_gap_bucket": bucket_actionability_window(seconds_since_previous),
    }


def _add_efficiency_visibility(trigger_frame: pd.DataFrame) -> pd.DataFrame:
    frame = trigger_frame.copy()
    for trigger_label in TRIGGER_LEVELS:
        mask = (frame["trigger_level"] == trigger_label) & (frame["observable_at_trigger"] == True)  # noqa: E712
        if not mask.any():
            continue
        group = frame.loc[mask]
        high_event = group["fdv_per_event_at_trigger"] >= group["fdv_per_event_at_trigger"].quantile(2 / 3)
        high_buy = group["fdv_per_buy_at_trigger"] >= group["fdv_per_buy_at_trigger"].quantile(2 / 3)
        high_wallet = group["fdv_per_active_wallet_at_trigger"] >= group["fdv_per_active_wallet_at_trigger"].quantile(2 / 3)
        low_event_count = group["event_count_at_trigger"] <= group["event_count_at_trigger"].quantile(1 / 3)
        low_buy_count = group["buy_count_at_trigger"] <= group["buy_count_at_trigger"].quantile(1 / 3)
        support = high_event.astype(int) + high_buy.astype(int) + high_wallet.astype(int) + low_event_count.astype(int) + low_buy_count.astype(int)
        frame.loc[group.index, "fdv_efficiency_support_count_at_trigger"] = support
        frame.loc[group.index, "high_fdv_efficiency_at_trigger"] = support >= 3
    frame["fdv_efficiency_support_count_at_trigger"] = frame["fdv_efficiency_support_count_at_trigger"].fillna(0).astype(int)
    frame["high_fdv_efficiency_at_trigger"] = frame["high_fdv_efficiency_at_trigger"].fillna(False).astype(bool)
    return frame


def _coverage_by_trigger(trigger_frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result = {}
    for trigger in TRIGGER_LEVELS:
        subset = trigger_frame[trigger_frame["trigger_level"] == trigger] if not trigger_frame.empty else pd.DataFrame()
        result[trigger] = {
            "rows": int(len(subset)),
            "observable_rows": int(subset["observable_at_trigger"].sum()) if "observable_at_trigger" in subset else 0,
            "leakage_safe_rows": int(subset["leakage_safe"].sum()) if "leakage_safe" in subset else 0,
            "observable_pct": _pct(int(subset["observable_at_trigger"].sum()) if "observable_at_trigger" in subset else 0, len(subset)),
            "leakage_safe_pct": _pct(int(subset["leakage_safe"].sum()) if "leakage_safe" in subset else 0, len(subset)),
            "high_fdv_efficiency_rows": int(subset["high_fdv_efficiency_at_trigger"].sum()) if "high_fdv_efficiency_at_trigger" in subset else 0,
            "missing_reason_counts": dict(Counter(str(value) for value in subset.get("missing_reason", pd.Series(dtype=object)).dropna().tolist())),
        }
    return result


def _actionability_summary(actionability: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if actionability.empty:
        return rows
    for (trigger, target), subset in actionability.groupby(["trigger_level", "target_level"], sort=True):
        observed = subset["time_to_target_seconds"].dropna()
        bucket_counts = Counter(subset["actionability_bucket"].tolist())
        rows.append(
            {
                "trigger_level": trigger,
                "target_level": target,
                "rows": int(len(subset)),
                "target_observed_rows": int(subset["target_observed_after_trigger"].sum()),
                "median_time_seconds": _round_or_none(observed.median() if not observed.empty else None),
                "iqr_seconds": _round_or_none((observed.quantile(0.75) - observed.quantile(0.25)) if len(observed) > 1 else None),
                "pct_at_least_15s": _pct(int((observed >= 15).sum()), len(subset)),
                "pct_at_least_30s": _pct(int((observed >= 30).sum()), len(subset)),
                "pct_at_least_60s": _pct(int((observed >= 60).sum()), len(subset)),
                "pct_at_least_2m": _pct(int((observed >= 120).sum()), len(subset)),
                "pct_at_least_5m": _pct(int((observed >= 300).sum()), len(subset)),
                "bucket_counts": {bucket: int(bucket_counts.get(bucket, 0)) for bucket in ACTIONABILITY_BUCKETS},
            }
        )
    return rows


def _snapshot_latency_summary(latency: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if latency.empty:
        return rows
    for trigger, subset in latency.groupby("trigger_level", sort=True):
        gaps = pd.to_numeric(subset["seconds_since_previous_snapshot"], errors="coerce").dropna()
        rows.append(
            {
                "trigger_level": trigger,
                "rows": int(len(subset)),
                "median_snapshot_gap_seconds": _round_or_none(gaps.median() if not gaps.empty else None),
                "pct_gap_lte_5s": _pct(int((gaps <= 5).sum()), len(subset)),
                "pct_gap_lte_15s": _pct(int((gaps <= 15).sum()), len(subset)),
                "pct_gap_lte_30s": _pct(int((gaps <= 30).sum()), len(subset)),
                "pct_gap_lte_60s": _pct(int((gaps <= 60).sum()), len(subset)),
                "pct_gap_gt_60s": _pct(int((gaps > 60).sum()), len(subset)),
                "snapshot_gap_bucket_counts": dict(Counter(subset["snapshot_gap_bucket"].tolist())),
            }
        )
    return rows


def _earliest_efficiency_visibility(trigger_frame: pd.DataFrame, master: pd.DataFrame) -> dict[str, Any]:
    if trigger_frame.empty or "high_fdv_efficiency_at_trigger" not in trigger_frame:
        return {"rows": 0, "distribution": {}, "tier_distribution_by_earliest_trigger": {}}
    tier_lookup = _tier_lookup(master)
    trigger_order = list(TRIGGER_LEVELS.keys())
    rows = []
    for launch_id, group in trigger_frame[trigger_frame["high_fdv_efficiency_at_trigger"] == True].groupby("launch_id", sort=True):  # noqa: E712
        group_triggers = [trigger for trigger in trigger_order if trigger in set(group["trigger_level"].tolist())]
        if group_triggers:
            earliest = group_triggers[0]
            rows.append({"launch_id": launch_id, "earliest_trigger": earliest, "milestone_tier": tier_lookup.get(str(launch_id), "unknown")})
    distribution = Counter(row["earliest_trigger"] for row in rows)
    by_tier: dict[str, dict[str, int]] = {}
    for row in rows:
        by_tier.setdefault(row["earliest_trigger"], {})
        by_tier[row["earliest_trigger"]][row["milestone_tier"]] = by_tier[row["earliest_trigger"]].get(row["milestone_tier"], 0) + 1
    return {
        "rows": len(rows),
        "distribution": dict(distribution),
        "tier_distribution_by_earliest_trigger": by_tier,
        "interpretation": "Earlier trigger comparison uses fixed quantile-style descriptive buckets per trigger, not optimized cutoffs.",
    }


def _classify_feasibility(
    coverage: dict[str, dict[str, Any]],
    actionability: list[dict[str, Any]],
    latency: list[dict[str, Any]],
) -> str:
    observable_20k = coverage.get("20k", {}).get("observable_rows", 0)
    if observable_20k < 30:
        return "data_limited"
    if coverage.get("20k", {}).get("observable_pct", 0) < 50:
        return "fdv_efficiency_not_observable_with_current_data"
    time_20k_100k = _summary_lookup(actionability, "20k", "100k")
    latency_20k = next((row for row in latency if row["trigger_level"] == "20k"), {})
    pct_60 = time_20k_100k.get("pct_at_least_60s", 0)
    pct_30 = time_20k_100k.get("pct_at_least_30s", 0)
    gap_lte_60 = latency_20k.get("pct_gap_lte_60s", 0)
    if pct_60 >= 40 and gap_lte_60 >= 70:
        return "fdv_efficiency_observable_and_actionable"
    if pct_30 >= 20:
        return "fdv_efficiency_observable_but_latency_sensitive"
    return "fdv_efficiency_observable_too_late"


def _recommendation(classification: str) -> dict[str, Any]:
    if classification == "fdv_efficiency_observable_and_actionable":
        next_step = "consider_entry_path_research_design_without_execution_or_validation"
    elif classification == "fdv_efficiency_observable_but_latency_sensitive":
        next_step = "improve_trigger_latency_resolution_before_any_entry_path_research"
    elif classification == "fdv_efficiency_observable_too_late":
        next_step = "test_earlier_observability_sources_before_any_entry_path_research"
    elif classification == "fdv_efficiency_not_observable_with_current_data":
        next_step = "repair_trigger_feature_observability_before_interpretation"
    else:
        next_step = "collect_or_repair_trigger_data_before_interpretation"
    return {
        "next_step": next_step,
        "what_not_to_do_next": "Do not create execution rules, alerts, optimization runs, validation, or thesis promotion from this diagnostic audit.",
    }


def _write_outputs(
    report: dict[str, Any],
    trigger_frame: pd.DataFrame,
    actionability_frame: pd.DataFrame,
    latency_frame: pd.DataFrame,
    output: Path,
    status_path: Path,
) -> dict[str, Path]:
    paths = {
        "summary_json_path": output / "fdv_efficiency_observability_summary.json",
        "summary_md_path": output / "fdv_efficiency_observability_summary.md",
        "trigger_observability_path": output / "fdv_efficiency_trigger_observability.csv",
        "actionability_windows_path": output / "fdv_efficiency_actionability_windows.csv",
        "snapshot_latency_path": output / "fdv_efficiency_snapshot_latency.csv",
        "status_path": status_path,
    }
    paths["summary_json_path"].write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    paths["summary_md_path"].write_text(_summary_markdown(report), encoding="utf-8")
    trigger_frame.to_csv(paths["trigger_observability_path"], index=False)
    actionability_frame.to_csv(paths["actionability_windows_path"], index=False)
    latency_frame.to_csv(paths["snapshot_latency_path"], index=False)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(_status_markdown(report), encoding="utf-8")
    return paths


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# FDV-Efficiency Observability Audit",
        "",
        f"- Rows analyzed: `{report['rows_analyzed']}`",
        f"- Classification: `{report['classification']}`",
        f"- Recommendation: `{report['recommendation']['next_step']}`",
        "- Scope: diagnostic only; no thesis, validation, backtest, optimization, alerts, or execution logic.",
        "",
        "## Observability Coverage",
    ]
    for trigger, row in report["observability_coverage_by_trigger"].items():
        lines.append(f"- `{trigger}`: observable `{row['observable_rows']}/{row['rows']}` ({row['observable_pct']}%)")
    lines.extend(["", "## Actionability Windows"])
    for row in report["actionability_window_summary"]:
        if row["trigger_level"] in {"10k", "15k", "20k", "30k"} and row["target_level"] in {"100k", "500k", "1m"}:
            lines.append(
                f"- `{row['trigger_level']} -> {row['target_level']}`: median `{row['median_time_seconds']}`s, "
                f">=30s `{row['pct_at_least_30s']}%`, >=60s `{row['pct_at_least_60s']}%`"
            )
    lines.extend(["", "## Snapshot Latency"])
    for row in report["snapshot_latency_summary"]:
        lines.append(f"- `{row['trigger_level']}`: median gap `{row['median_snapshot_gap_seconds']}`s, <=60s `{row['pct_gap_lte_60s']}%`")
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# FDV-Efficiency Observability Status",
        "",
        "This audit was created because FDV-efficiency remains the strongest historical separator, but it must be observable early enough before future entry-path research is justified.",
        "",
        f"- Trigger levels tested: `{', '.join(report['trigger_levels_tested'])}`",
        f"- Rows analyzed: `{report['rows_analyzed']}`",
        f"- Classification: `{report['classification']}`",
        "",
        "## Observability Result",
    ]
    for trigger, row in report["observability_coverage_by_trigger"].items():
        lines.append(f"- {trigger}: observable `{row['observable_rows']}/{row['rows']}`; leakage-safe `{row['leakage_safe_rows']}/{row['rows']}`")
    lines.extend(["", "## Actionability Window Result"])
    for row in report["actionability_window_summary"]:
        if row["trigger_level"] == "20k" and row["target_level"] in {"100k", "500k"}:
            lines.append(
                f"- 20k to {row['target_level']}: median `{row['median_time_seconds']}` seconds; "
                f">=30s `{row['pct_at_least_30s']}%`; >=60s `{row['pct_at_least_60s']}%`"
            )
    lines.extend(["", "## Snapshot Latency Result"])
    for row in report["snapshot_latency_summary"]:
        lines.append(f"- {row['trigger_level']}: median previous-gap `{row['median_snapshot_gap_seconds']}` seconds; >60s `{row['pct_gap_gt_60s']}%`")
    lines.extend(
        [
            "",
            "## Limitations",
            "- Snapshot-level replay is not continuous tick-level observability.",
            "- FDV proxy is not true market cap.",
            "- Actionability window is a timing diagnostic only.",
            "",
            "## Next Recommendation",
            f"- `{report['recommendation']['next_step']}`",
            "",
            "No thesis, validation, walk-forward validation, backtest, alerts, execution logic, optimization, ML, or strategy generation was run.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_master(master_path: Path | str, jsonl_fallback: Path | str) -> pd.DataFrame:
    path = Path(master_path)
    fallback = Path(jsonl_fallback)
    if path.exists():
        return pd.read_parquet(path)
    if fallback.exists():
        return pd.read_json(fallback, orient="records", lines=True)
    return pd.DataFrame()


def _load_snapshots(snapshots_path: Path | str) -> pd.DataFrame:
    path = Path(snapshots_path)
    if not path.exists():
        raise FileNotFoundError(f"missing lifecycle snapshots: {path}")
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_json(path, orient="records", lines=True)


def _filter_to_master_universe(snapshots: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    if master.empty or snapshots.empty:
        return snapshots
    result = snapshots.copy()
    launch_ids = set(master.get("launch_id", pd.Series(dtype=object)).dropna().astype(str).tolist())
    mints = set(_first_present(master, ["token_mint", "mint"]).dropna().astype(str).tolist())
    mask = pd.Series(False, index=result.index)
    if "launch_id" in result.columns and launch_ids:
        mask = mask | result["launch_id"].astype(str).isin(launch_ids)
    token_col = _first_present(result, ["token_mint", "mint"])
    if mints:
        mask = mask | token_col.astype(str).isin(mints)
    filtered = result[mask].copy()
    return filtered if not filtered.empty else snapshots


def _tier_lookup(master: pd.DataFrame) -> dict[str, str]:
    if master.empty or "milestone_tier" not in master.columns:
        return {}
    lookup = {}
    for _, row in master.iterrows():
        tier = str(row.get("milestone_tier"))
        for key in (row.get("launch_id"), row.get("token_mint"), row.get("mint")):
            if key is not None and not pd.isna(key):
                lookup[str(key)] = tier
    return lookup


def _summary_lookup(rows: list[dict[str, Any]], trigger: str, target: str) -> dict[str, Any]:
    return next((row for row in rows if row["trigger_level"] == trigger and row["target_level"] == target), {})


def _unique_launch_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    if "launch_key" in frame.columns:
        return int(frame["launch_key"].nunique())
    if "launch_id" in frame.columns:
        return int(frame["launch_id"].nunique())
    if "token_mint" in frame.columns:
        return int(frame["token_mint"].nunique())
    return int(len(frame))


def _first_present(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series([None] * len(frame), index=frame.index, dtype=object)
    for column in columns:
        if column in frame.columns:
            result = result.where(result.notna(), frame[column])
    return result


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _observable(event_count: float | None, buy_count: float | None, active_wallets: float | None, valuation: float | None) -> bool:
    return bool(
        event_count is not None
        and buy_count is not None
        and active_wallets is not None
        and valuation is not None
        and event_count > 0
        and buy_count > 0
        and active_wallets > 0
    )


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _none_if_nan(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _round_or_none(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _pct(num: int | float, den: int | float) -> float:
    return round((float(num) / float(den)) * 100, 4) if den else 0.0


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
    if guardrails.get("thesis_runs") or guardrails.get("validation_runs") or guardrails.get("trading_logic_added"):
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
