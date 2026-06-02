"""Robustness-only review for T011 raw-flow continuation."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "t011_explosive_runner_raw_flow_robustness_v0"
REPORT_JSON = "T011_explosive_runner_raw_flow_robustness_summary.json"
REPORT_MD = "T011_explosive_runner_raw_flow_robustness_summary.md"
TRIGGERS = {"15k": 15_000.0, "20k": 20_000.0, "30k": 30_000.0}
MILESTONES = {"50k": 50_000.0, "100k": 100_000.0, "200k": 200_000.0, "500k": 500_000.0, "1m": 1_000_000.0}
ROBUST_CLASSIFICATIONS = {
    "robust_descriptive_signal",
    "unstable_descriptive_signal",
    "no_robust_signal",
    "data_limited",
}
TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]


def build_t011_raw_flow_robustness_report(
    *,
    t011_summary_path: Path | str,
    trigger_20k_rows_path: Path | str,
    snapshots_path: Path | str | None = None,
    tier_table_path: Path | str | None = None,
) -> dict[str, Any]:
    summary = _read_json(t011_summary_path)
    rows = _read_csv(trigger_20k_rows_path)
    rows = [_normalize_feature_row(row) for row in rows]
    rows = [row for row in rows if row.get("token_mint")]
    full_direction = _direction(rows)
    split_rows = []
    chronological = _chronological_robustness(rows, full_direction, split_rows)
    trigger_sensitivity = _trigger_sensitivity(snapshots_path, full_direction, split_rows)
    outliers = _outlier_sensitivity(rows, full_direction, split_rows)
    dominance = _dominance_checks(rows, full_direction, split_rows)
    flow = _flow_interpretation(rows)
    active_wallet = _active_wallet_reconciliation(rows)
    overlays = _overlay_robustness(rows)
    classification = _classify(rows, chronological, trigger_sensitivity, outliers, dominance)
    return {
        "report_id": REPORT_ID,
        "review_type": "robustness_only",
        "original_t011_classification": summary.get("final_classification"),
        "trigger_20k_count_analyzed": len(rows),
        "methodology_flags": [
            "research_only",
            "robustness_review_only",
            "no_thesis_promotion",
            "no_backtest",
            "no_walk_forward_validation",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_wallet_execution",
            "no_order_routing",
            "no_alerts",
            "no_trading_rules",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "fdv_proxy_not_true_market_cap",
        ],
        "inputs": {
            "t011_summary_path": str(t011_summary_path),
            "trigger_20k_rows_path": str(trigger_20k_rows_path),
            "snapshots_path": str(snapshots_path) if snapshots_path else None,
            "tier_table_path": str(tier_table_path) if tier_table_path else None,
        },
        "full_sample_direction": full_direction,
        "chronological_robustness": chronological,
        "trigger_sensitivity": trigger_sensitivity,
        "outlier_sensitivity": outliers,
        "dominance_checks": dominance,
        "flow_interpretation": flow,
        "active_wallet_breadth_reconciliation": active_wallet,
        "overlay_robustness": overlays,
        "robustness_classification": classification,
        "validation_design_recommended": classification == "robust_descriptive_signal",
        "warning_flags": _warning_flags(classification, rows, overlays),
        "limitations": _limitations(),
        "next_recommendation": _next_recommendation(classification),
        "split_table_rows": split_rows,
    }


def write_t011_raw_flow_robustness_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    split_csv = output / "robustness_split_table.csv"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown_summary(report), encoding="utf-8")
    _write_csv(report["split_table_rows"], split_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, split_csv), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": md_path, "split_table_path": split_csv, "status_path": status}


def _chronological_robustness(rows: list[dict[str, Any]], full_direction: dict[str, Any], split_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (_float_or_none(row.get("launch_ts")) or 0, row["token_mint"]))
    halves = _split_review("chronological_halves", _chunks(ordered, 2), full_direction, split_rows)
    thirds = _split_review("chronological_thirds", _chunks(ordered, 3), full_direction, split_rows)
    dates = _date_buckets(ordered)
    date_payload = _named_group_review("date_buckets", dates, full_direction, split_rows, min_group_size=20)
    return {"halves": halves, "thirds": thirds, "date_buckets": date_payload}


def _trigger_sensitivity(path: Path | str | None, full_direction: dict[str, Any], split_rows: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots = _read_jsonl(path) if path else []
    by_mint = _group_by_mint(snapshots)
    output = {}
    for name, threshold in TRIGGERS.items():
        trigger_rows = [_trigger_row_for_mint(mint, rows, name, threshold) for mint, rows in sorted(by_mint.items())]
        trigger_rows = [row for row in trigger_rows if row]
        direction = _direction(trigger_rows)
        payload = {
            "trigger_count": len(trigger_rows),
            "tier_counts": dict(Counter(row["milestone_tier"] for row in trigger_rows)),
            "direction": direction,
            "direction_matches_full_sample": _direction_matches(direction, full_direction),
            "median_by_tier": _median_by_tier(trigger_rows),
        }
        output[name] = payload
        _append_split_row(split_rows, "trigger_sensitivity", name, trigger_rows, direction, payload["direction_matches_full_sample"])
    if not snapshots:
        for name in TRIGGERS:
            output.setdefault(name, {"trigger_count": 0, "available": False, "direction_matches_full_sample": False})
    return output


def _outlier_sensitivity(rows: list[dict[str, Any]], full_direction: dict[str, Any], split_rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "exclude_top_1pct_peak_fdv_proxy": _exclude_top_pct(rows, 0.01),
        "exclude_top_5pct_peak_fdv_proxy": _exclude_top_pct(rows, 0.05),
        "exclude_1m_plus": [row for row in rows if row.get("milestone_tier") != "reached_1m_plus"],
        "exclude_extreme_drawdown_cases": rows,
    }
    output = {}
    for name, members in checks.items():
        direction = _direction(members)
        output[name] = {
            "rows_analyzed": len(members),
            "direction": direction,
            "direction_matches_full_sample": _direction_matches(direction, full_direction),
        }
        _append_split_row(split_rows, "outlier_sensitivity", name, members, direction, output[name]["direction_matches_full_sample"])
    return output


def _dominance_checks(rows: list[dict[str, Any]], full_direction: dict[str, Any], split_rows: list[dict[str, Any]]) -> dict[str, Any]:
    top_creator = _top_keys(rows, "creator", n=1, winner_only=False)
    top_3_creators_by_1m = _top_keys([row for row in rows if row.get("milestone_tier") == "reached_1m_plus"], "creator", n=3, winner_only=True)
    top_date = _top_dates(rows, n=1)
    top_3_dates = _top_dates(rows, n=3)
    checks = {
        "exclude_dominant_creator": _exclude_values(rows, "creator", top_creator),
        "exclude_top_3_creators_by_1m_count": _exclude_values(rows, "creator", top_3_creators_by_1m),
        "exclude_top_date": _exclude_dates(rows, top_date),
        "exclude_top_3_dates": _exclude_dates(rows, top_3_dates),
    }
    output = {
        "dominant_creator": top_creator,
        "top_3_creators_by_1m_count": top_3_creators_by_1m,
        "top_date": top_date,
        "top_3_dates": top_3_dates,
    }
    for name, members in checks.items():
        direction = _direction(members)
        output[name] = {
            "rows_analyzed": len(members),
            "direction": direction,
            "direction_matches_full_sample": _direction_matches(direction, full_direction),
        }
        _append_split_row(split_rows, "dominance_check", name, members, direction, output[name]["direction_matches_full_sample"])
    return output


def _flow_interpretation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners = [row for row in rows if _bool(row.get("crossed_100k_after_20k"))]
    non = [row for row in rows if not _bool(row.get("crossed_100k_after_20k"))]
    efficiency_fields = {
        "fdv_per_event": lambda row: _ratio(row.get("trigger_fdv_proxy"), row.get("event_count_at_20k")),
        "fdv_per_buy": lambda row: _ratio(row.get("trigger_fdv_proxy"), row.get("buy_count_at_20k")),
        "fdv_per_active_wallet": lambda row: _ratio(row.get("trigger_fdv_proxy"), row.get("active_wallets_at_20k")),
        "sell_event_share": lambda row: _ratio(row.get("sell_count_at_20k"), row.get("event_count_at_20k")),
        "net_buy_count": lambda row: _float_or_none(row.get("net_buy_count_at_20k")),
        "sells_per_active_wallet": lambda row: _ratio(row.get("sell_count_at_20k"), row.get("active_wallets_at_20k")),
    }
    summary = {}
    for field, func in efficiency_fields.items():
        summary[field] = {
            "winner_median": _median([func(row) for row in winners]),
            "non_winner_median": _median([func(row) for row in non]),
        }
        if summary[field]["winner_median"] is not None and summary[field]["non_winner_median"] is not None:
            summary[field]["delta"] = summary[field]["winner_median"] - summary[field]["non_winner_median"]
        else:
            summary[field]["delta"] = None
    low_flow = (_direction(rows).get("event_count_delta_100k_plus_vs_sub_100k") or 0) < 0
    efficient = (summary["fdv_per_event"].get("delta") or 0) > 0
    low_churn = (summary["sell_event_share"].get("delta") or 0) < 0
    if low_flow and efficient and low_churn:
        refined = "low_total_flow_low_churn_thin_squeeze_proxy"
    elif low_flow and efficient:
        refined = "low_total_flow_with_high_fdv_efficiency"
    elif low_flow:
        refined = "low_total_flow_without_clear_efficiency"
    else:
        refined = "no_clear_low_flow_refinement"
    return {"efficiency_and_churn": summary, "refined_pattern": refined}


def _active_wallet_reconciliation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners = [row for row in rows if _bool(row.get("crossed_100k_after_20k"))]
    non = [row for row in rows if not _bool(row.get("crossed_100k_after_20k"))]
    events_per_wallet_winners = [_ratio(row.get("event_count_at_20k"), row.get("active_wallets_at_20k")) for row in winners]
    events_per_wallet_non = [_ratio(row.get("event_count_at_20k"), row.get("active_wallets_at_20k")) for row in non]
    low_flow_rows = [row for row in rows if (_float_or_none(row.get("event_count_at_20k")) or 0) <= (_median([r.get("event_count_at_20k") for r in rows]) or 0)]
    low_flow_with_breadth = [
        row for row in low_flow_rows if (_float_or_none(row.get("active_wallets_at_20k")) or 0) >= (_median([r.get("active_wallets_at_20k") for r in rows]) or 0)
    ]
    return {
        "winner_event_count_median": _median([row.get("event_count_at_20k") for row in winners]),
        "non_winner_event_count_median": _median([row.get("event_count_at_20k") for row in non]),
        "winner_active_wallet_median": _median([row.get("active_wallets_at_20k") for row in winners]),
        "non_winner_active_wallet_median": _median([row.get("active_wallets_at_20k") for row in non]),
        "winner_events_per_active_wallet_median": _median(events_per_wallet_winners),
        "non_winner_events_per_active_wallet_median": _median(events_per_wallet_non),
        "low_flow_with_enough_breadth_count": len(low_flow_with_breadth),
        "refined_pattern": _wallet_refinement(winners, non, events_per_wallet_winners, events_per_wallet_non),
    }


def _wallet_refinement(winners: list[dict[str, Any]], non: list[dict[str, Any]], winner_epw: list[Any], non_epw: list[Any]) -> str:
    w_events = _median([row.get("event_count_at_20k") for row in winners])
    n_events = _median([row.get("event_count_at_20k") for row in non])
    w_wallets = _median([row.get("active_wallets_at_20k") for row in winners])
    n_wallets = _median([row.get("active_wallets_at_20k") for row in non])
    if w_events is not None and n_events is not None and w_wallets is not None and n_wallets is not None:
        if w_events < n_events and w_wallets >= n_wallets:
            return "fewer_events_but_enough_distinct_wallets"
        if w_events < n_events and w_wallets < n_wallets and (_median(winner_epw) or 0) <= (_median(non_epw) or 0):
            return "low_total_flow_and_lower_event_density_per_wallet"
    return "no_clear_active_wallet_refinement"


def _overlay_robustness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "holder_count_at_20k",
        "fdv_per_holder_at_20k",
        "holders_per_10k_fdv_at_20k",
        "repeated_actor_overlap_proxy",
        "synchronized_participation_proxy",
        "churn_proxy",
        "funding_source_available",
        "repeated_funder_flag",
    ]
    return {
        field: {
            "coverage": _coverage(rows, field),
            "winner_median": _median([row.get(field) for row in rows if _bool(row.get("crossed_100k_after_20k"))]),
            "non_winner_median": _median([row.get(field) for row in rows if not _bool(row.get("crossed_100k_after_20k"))]),
            "context_only": True,
        }
        for field in fields
    }


def _classify(
    rows: list[dict[str, Any]],
    chronological: dict[str, Any],
    triggers: dict[str, Any],
    outliers: dict[str, Any],
    dominance: dict[str, Any],
) -> str:
    if len(rows) < 100:
        return "data_limited"
    checks = [
        chronological["halves"].get("direction_matches_full_sample"),
        chronological["thirds"].get("direction_matches_full_sample"),
        triggers.get("15k", {}).get("direction_matches_full_sample"),
        triggers.get("20k", {}).get("direction_matches_full_sample"),
        triggers.get("30k", {}).get("direction_matches_full_sample"),
        outliers["exclude_top_1pct_peak_fdv_proxy"]["direction_matches_full_sample"],
        outliers["exclude_top_5pct_peak_fdv_proxy"]["direction_matches_full_sample"],
        dominance["exclude_dominant_creator"]["direction_matches_full_sample"],
        dominance["exclude_top_date"]["direction_matches_full_sample"],
    ]
    valid = [bool(check) for check in checks]
    if sum(valid) >= 8:
        return "robust_descriptive_signal"
    if sum(valid) >= 4:
        return "unstable_descriptive_signal"
    return "no_robust_signal"


def _split_review(
    family: str,
    groups: list[list[dict[str, Any]]],
    full_direction: dict[str, Any],
    split_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if any(len(group) < 2 for group in groups):
        return {"available": False, "reason": "too_few_rows"}
    payload = {}
    matches = []
    for index, group in enumerate(groups, start=1):
        direction = _direction(group)
        match = _direction_matches(direction, full_direction)
        matches.append(match)
        label = f"{family}_{index}"
        payload[label] = {"rows_analyzed": len(group), "direction": direction, "direction_matches_full_sample": match}
        _append_split_row(split_rows, family, label, group, direction, match)
    payload["available"] = True
    payload["direction_matches_full_sample"] = all(matches)
    return payload


def _named_group_review(
    family: str,
    groups: dict[str, list[dict[str, Any]]],
    full_direction: dict[str, Any],
    split_rows: list[dict[str, Any]],
    *,
    min_group_size: int,
) -> dict[str, Any]:
    eligible = {name: rows for name, rows in groups.items() if len(rows) >= min_group_size}
    output = {"available": bool(eligible), "bucket_counts": {name: len(rows) for name, rows in groups.items()}, "buckets": {}}
    matches = []
    for name, members in sorted(eligible.items()):
        direction = _direction(members)
        match = _direction_matches(direction, full_direction)
        matches.append(match)
        output["buckets"][name] = {"rows_analyzed": len(members), "direction": direction, "direction_matches_full_sample": match}
        _append_split_row(split_rows, family, name, members, direction, match)
    output["direction_matches_full_sample"] = all(matches) if matches else False
    return output


def _direction(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners_100 = [row for row in rows if _bool(row.get("crossed_100k_after_20k")) or row.get("milestone_tier") in {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}]
    sub_100 = [row for row in rows if row not in winners_100]
    winners_500 = [row for row in rows if _bool(row.get("crossed_500k_after_20k")) or row.get("milestone_tier") in {"reached_500k_but_never_1m", "reached_1m_plus"}]
    mid_100_500 = [row for row in rows if row.get("milestone_tier") in {"reached_100k_but_never_200k", "reached_200k_but_never_500k"}]
    return {
        "rows_analyzed": len(rows),
        "event_count_delta_100k_plus_vs_sub_100k": _median_delta(winners_100, sub_100, "event_count_at_20k"),
        "buy_count_delta_100k_plus_vs_sub_100k": _median_delta(winners_100, sub_100, "buy_count_at_20k"),
        "active_wallet_delta_100k_plus_vs_sub_100k": _median_delta(winners_100, sub_100, "active_wallets_at_20k"),
        "event_count_delta_500k_plus_vs_100k_to_500k": _median_delta(winners_500, mid_100_500, "event_count_at_20k"),
        "buy_count_delta_500k_plus_vs_100k_to_500k": _median_delta(winners_500, mid_100_500, "buy_count_at_20k"),
        "lower_flow_100k_plus": _delta_is_negative(winners_100, sub_100, "event_count_at_20k"),
        "lower_buy_count_100k_plus": _delta_is_negative(winners_100, sub_100, "buy_count_at_20k"),
        "lower_flow_500k_plus": _delta_is_negative(winners_500, mid_100_500, "event_count_at_20k"),
    }


def _direction_matches(direction: dict[str, Any], full_direction: dict[str, Any]) -> bool:
    if direction.get("rows_analyzed", 0) < 2:
        return False
    keys = ["lower_flow_100k_plus", "lower_buy_count_100k_plus"]
    return all(direction.get(key) == full_direction.get(key) for key in keys if full_direction.get(key) is not None)


def _append_split_row(
    split_rows: list[dict[str, Any]],
    family: str,
    name: str,
    rows: list[dict[str, Any]],
    direction: dict[str, Any],
    matches: bool,
) -> None:
    split_rows.append(
        {
            "split_family": family,
            "split_name": name,
            "rows_analyzed": len(rows),
            "tier_counts": json.dumps(dict(Counter(row.get("milestone_tier") for row in rows)), sort_keys=True),
            "median_event_count_100k_plus_delta": direction.get("event_count_delta_100k_plus_vs_sub_100k"),
            "median_buy_count_100k_plus_delta": direction.get("buy_count_delta_100k_plus_vs_sub_100k"),
            "median_active_wallet_100k_plus_delta": direction.get("active_wallet_delta_100k_plus_vs_sub_100k"),
            "direction_matches_full_sample": matches,
        }
    )


def _trigger_row_for_mint(mint: str, rows: list[dict[str, Any]], trigger_name: str, threshold: float) -> dict[str, Any] | None:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    trigger = next((row for row in priced if (_value(row) or 0) >= threshold), None)
    if not trigger:
        return None
    crossings = {name: next((row for row in priced if (_value(row) or 0) >= value), None) for name, value in MILESTONES.items()}
    tier = _tier(crossings)
    return {
        "token_mint": mint,
        "launch_id": trigger.get("launch_id"),
        "launch_ts": _int_or_none(trigger.get("launch_ts")),
        "trigger_age_seconds": _age(trigger),
        "trigger_fdv_proxy": _value(trigger),
        "peak_fdv_proxy": max((_value(row) or 0) for row in priced) if priced else None,
        "milestone_tier": tier,
        "event_count_at_20k": _event_count(trigger),
        "buy_count_at_20k": _float_or_none(trigger.get("buy_count")),
        "sell_count_at_20k": _float_or_none(trigger.get("sell_count")),
        "active_wallets_at_20k": _float_or_none(trigger.get("active_wallets")),
        "unique_actors_at_20k": _float_or_none(trigger.get("unique_actors")),
        "crossed_100k_after_20k": bool(crossings.get("100k")),
        "crossed_500k_after_20k": bool(crossings.get("500k")),
        "trigger_name": trigger_name,
    }


def _median_by_tier(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for tier in TIER_ORDER:
        members = [row for row in rows if row.get("milestone_tier") == tier]
        output[tier] = {
            "launch_count": len(members),
            "median_event_count_at_trigger": _median([row.get("event_count_at_20k") for row in members]),
            "median_buy_count_at_trigger": _median([row.get("buy_count_at_20k") for row in members]),
            "median_active_wallets_at_trigger": _median([row.get("active_wallets_at_20k") for row in members]),
        }
    return output


def _chunks(rows: list[dict[str, Any]], count: int) -> list[list[dict[str, Any]]]:
    return [rows[(len(rows) * index) // count : (len(rows) * (index + 1)) // count] for index in range(count)]


def _date_buckets(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[_date_key(row)].append(row)
    return dict(grouped)


def _date_key(row: dict[str, Any]) -> str:
    ts = _int_or_none(row.get("launch_ts"))
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _top_dates(rows: list[dict[str, Any]], n: int) -> list[str]:
    return [key for key, _ in Counter(_date_key(row) for row in rows).most_common(n)]


def _top_keys(rows: list[dict[str, Any]], key: str, n: int, winner_only: bool) -> list[str]:
    usable = [row for row in rows if row.get(key)]
    return [value for value, _ in Counter(str(row.get(key)) for row in usable).most_common(n)]


def _exclude_values(rows: list[dict[str, Any]], key: str, values: list[str]) -> list[dict[str, Any]]:
    excluded = set(values)
    return [row for row in rows if str(row.get(key)) not in excluded]


def _exclude_dates(rows: list[dict[str, Any]], dates: list[str]) -> list[dict[str, Any]]:
    excluded = set(dates)
    return [row for row in rows if _date_key(row) not in excluded]


def _exclude_top_pct(rows: list[dict[str, Any]], pct: float) -> list[dict[str, Any]]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda row: _float_or_none(row.get("peak_fdv_proxy")) or 0)
    keep = max(0, int(len(ordered) * (1 - pct)))
    return ordered[:keep]


def _coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if _float_or_none(row.get(field)) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _median_delta(a: list[dict[str, Any]], b: list[dict[str, Any]], field: str) -> float | None:
    av = _median([row.get(field) for row in a])
    bv = _median([row.get(field) for row in b])
    if av is None or bv is None:
        return None
    return av - bv


def _delta_is_negative(a: list[dict[str, Any]], b: list[dict[str, Any]], field: str) -> bool | None:
    delta = _median_delta(a, b, field)
    return delta < 0 if delta is not None else None


def _tier(crossings: dict[str, dict[str, Any] | None]) -> str:
    if crossings.get("1m"):
        return "reached_1m_plus"
    if crossings.get("500k"):
        return "reached_500k_but_never_1m"
    if crossings.get("200k"):
        return "reached_200k_but_never_500k"
    if crossings.get("100k"):
        return "reached_100k_but_never_200k"
    if crossings.get("50k"):
        return "reached_50k_but_never_100k"
    return "reached_20k_but_never_50k"


def _normalize_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    for key, value in row.items():
        if key in {"token_mint", "launch_id", "creator", "milestone_tier"}:
            continue
        if value in {"True", "true"}:
            output[key] = True
        elif value in {"False", "false"}:
            output[key] = False
        else:
            parsed = _float_or_none(value)
            output[key] = parsed if parsed is not None else value
    if output.get("net_buy_count_at_20k") is None:
        buy = _float_or_none(output.get("buy_count_at_20k"))
        sell = _float_or_none(output.get("sell_count_at_20k"))
        output["net_buy_count_at_20k"] = buy - sell if buy is not None and sell is not None else None
    return output


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "split_table_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# T011 Raw-Flow Robustness Review",
            "",
            f"- Original classification: `{report['original_t011_classification']}`",
            f"- Robustness classification: `{report['robustness_classification']}`",
            f"- $20k trigger rows analyzed: `{report['trigger_20k_count_analyzed']}`",
            f"- Chronological halves stable: `{report['chronological_robustness']['halves'].get('direction_matches_full_sample')}`",
            f"- Trigger sensitivity 15k/20k/30k: `{_trigger_stability_text(report)}`",
            f"- Low-flow interpretation: `{report['flow_interpretation']['refined_pattern']}`",
            f"- Validation design recommended: `{report['validation_design_recommended']}`",
            "",
            "No validation was run.",
            "",
        ]
    )


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path, split_csv: Path) -> str:
    return "\n".join(
        [
            "# T011 Explosive Runner Raw-Flow Robustness Status",
            "",
            f"- Original T011 classification: `{report['original_t011_classification']}`",
            f"- Robustness classification: `{report['robustness_classification']}`",
            f"- $20k trigger count analyzed: `{report['trigger_20k_count_analyzed']}`",
            "",
            "## Chronological Result",
            "",
            f"- Halves direction stable: `{report['chronological_robustness']['halves'].get('direction_matches_full_sample')}`",
            f"- Thirds direction stable: `{report['chronological_robustness']['thirds'].get('direction_matches_full_sample')}`",
            "",
            "## Trigger Sensitivity Result",
            "",
            f"- {_trigger_stability_text(report)}",
            "",
            "## Outlier Sensitivity Result",
            "",
            f"- Top 1% exclusion stable: `{report['outlier_sensitivity']['exclude_top_1pct_peak_fdv_proxy']['direction_matches_full_sample']}`",
            f"- Top 5% exclusion stable: `{report['outlier_sensitivity']['exclude_top_5pct_peak_fdv_proxy']['direction_matches_full_sample']}`",
            f"- $1M+ exclusion stable: `{report['outlier_sensitivity']['exclude_1m_plus']['direction_matches_full_sample']}`",
            "",
            "## Creator / Date Dominance Result",
            "",
            f"- Dominant creator exclusion stable: `{report['dominance_checks']['exclude_dominant_creator']['direction_matches_full_sample']}`",
            f"- Top date exclusion stable: `{report['dominance_checks']['exclude_top_date']['direction_matches_full_sample']}`",
            "",
            "## Low-Flow Interpretation",
            "",
            f"- Refined pattern: `{report['flow_interpretation']['refined_pattern']}`",
            f"- Active-wallet refinement: `{report['active_wallet_breadth_reconciliation']['refined_pattern']}`",
            "",
            "## Validation Recommendation",
            "",
            f"- Validation design recommended: `{report['validation_design_recommended']}`",
            "- No validation was run.",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Outputs",
            "",
            f"- JSON summary: `{json_path}`",
            f"- Markdown summary: `{md_path}`",
            f"- Split table: `{split_csv}`",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
        ]
    )


def _trigger_stability_text(report: dict[str, Any]) -> str:
    parts = []
    for trigger in ["15k", "20k", "30k"]:
        payload = report["trigger_sensitivity"].get(trigger, {})
        parts.append(f"{trigger}: {payload.get('direction_matches_full_sample')} ({payload.get('trigger_count', 0)} rows)")
    return ", ".join(parts)


def _warning_flags(classification: str, rows: list[dict[str, Any]], overlays: dict[str, Any]) -> list[str]:
    warnings = {"fdv_proxy_not_true_market_cap", "no_thesis_promotion", "no_validation_run"}
    if classification != "robust_descriptive_signal":
        warnings.add("not_ready_for_validation_design")
    if overlays["holder_count_at_20k"]["coverage"]["coverage_pct"] < 50:
        warnings.add("holder_overlay_partial_coverage")
    if overlays["funding_source_available"]["coverage"]["coverage_pct"] < 50:
        warnings.add("funding_overlay_partial_coverage")
    if len(rows) < 100:
        warnings.add("small_trigger_sample")
    return sorted(warnings)


def _limitations() -> list[str]:
    return [
        "FDV/valuation proxy is used; true market-cap claims remain blocked.",
        "This is a robustness review only, not validation or thesis promotion.",
        "Trigger sensitivity uses fixed $15k/$20k/$30k thresholds and does not optimize trigger choice.",
        "Holder/entity/funding overlays are partial-coverage context only.",
        "Snapshot timing around fast crossings may still compress the apparent trigger path.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification == "robust_descriptive_signal":
        return "Design a formal validation plan for T011, but do not run validation in this sprint."
    if classification == "unstable_descriptive_signal":
        return "Run a current-market DexScreener/Axiom observation pilot before validation."
    if classification == "no_robust_signal":
        return "Stop raw-flow thesis work and shift to live observation or exit-side drawdown research."
    return "Improve sample/coverage before interpreting T011 robustness."


def _read_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _read_csv(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint") or row.get("mint")
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else None)


def _event_count(row: dict[str, Any]) -> float | None:
    meta = row.get("metadata_json") or {}
    return _first_float(meta.get("event_count"), row.get("event_count"), row.get("tx_count"))


def _age(row: dict[str, Any]) -> int:
    return int(row.get("launch_age_seconds") or 0)


def _median(values: list[Any]) -> float | None:
    vals = [_float_or_none(value) for value in values]
    vals = [value for value in vals if value is not None]
    return median(vals) if vals else None


def _ratio(a: Any, b: Any) -> float | None:
    av = _float_or_none(a)
    bv = _float_or_none(b)
    if av is None or bv in (None, 0):
        return None
    return av / bv


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 6) if total else 0.0
