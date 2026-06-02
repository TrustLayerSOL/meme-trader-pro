"""Broad descriptive winner-anatomy report for explosive FDV-proxy runners."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.t011_expanded_rerun import (
    DEFAULT_ENTITY_PROXY_PATH,
    DEFAULT_FUNDING_LINK_PATH,
    DEFAULT_HOLDER_STATE_PATH,
    DEFAULT_MIGRATION_LABELS_PATH,
    DEFAULT_SNAPSHOT_PATHS,
    write_combined_expanded_snapshots,
)


REPORT_ID = "explosive_runner_winner_anatomy_report_v0"
REPORT_JSON = "explosive_runner_winner_anatomy_report_summary.json"
REPORT_MD = "explosive_runner_winner_anatomy_report_summary.md"
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "explosive_runner_winner_anatomy_report"
)
DEFAULT_STATUS_PATH = Path("theses/EXPLOSIVE_RUNNER_WINNER_ANATOMY_REPORT_STATUS.md")

MILESTONES = {
    "15k": 15_000.0,
    "20k": 20_000.0,
    "30k": 30_000.0,
    "50k": 50_000.0,
    "100k": 100_000.0,
    "200k": 200_000.0,
    "500k": 500_000.0,
    "1m": 1_000_000.0,
}
TIER_ORDER = [
    "never_reached_20k",
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
FIXED_TIME_CONTEXTS = {
    "launch_30s": 30,
    "launch_1m": 60,
    "launch_2m": 120,
    "launch_3m": 180,
    "launch_5m": 300,
    "launch_10m": 600,
}
PRE_MILESTONE_OFFSETS = {
    "30s_before": 30,
    "60s_before": 60,
    "2m_before": 120,
    "5m_before": 300,
}
FEATURE_FIELDS = [
    "event_count",
    "buy_count",
    "sell_count",
    "net_buy_count",
    "buy_sell_ratio",
    "event_count_growth",
    "buy_count_growth",
    "sell_count_growth",
    "fdv_per_event",
    "fdv_per_buy",
    "fdv_per_active_wallet",
    "fdv_per_holder",
    "valuation_growth_per_event",
    "valuation_growth_per_buy",
    "active_wallets",
    "unique_actors",
    "active_wallet_growth",
    "unique_actor_growth",
    "events_per_active_wallet",
    "buys_per_active_wallet",
    "holder_count",
    "holder_count_growth",
    "holders_per_10k_fdv",
    "top_holder_share",
    "top_10_holder_share",
    "creator_holder_share",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
    "creator_prior_migration_or_graduation_count",
    "creator_prior_migration_or_graduation_rate",
    "creator_has_prior_migration_or_graduation",
    "creator_has_2plus_prior_migrations_or_graduations",
    "creator_has_4plus_prior_migrations_or_graduations",
    "funding_source_available",
    "repeated_funder_flag",
    "creator_funder_reuse_count",
    "launches_sharing_funder",
    "funding_age_seconds",
    "funding_amount_sol",
    "time_to_15k",
    "time_to_20k",
    "time_to_30k",
    "time_to_50k",
    "time_from_20k_to_50k",
    "time_from_20k_to_100k",
    "time_from_50k_to_100k",
    "time_to_peak",
]


def build_explosive_runner_winner_anatomy_report(
    *,
    snapshot_paths: list[Path | str],
    output_dir: Path | str,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    funding_link_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    combined_path = output / "combined_expanded_lifecycle_snapshots.jsonl"
    combine_summary = write_combined_expanded_snapshots(snapshot_paths, combined_path)
    snapshots = _read_jsonl(combined_path)
    holder_by_mint = _group_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    entity_by_mint = _group_by_mint(_read_jsonl(entity_proxy_path)) if entity_proxy_path else {}
    migration_by_mint = _migration_by_mint(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    funding_by_mint = _group_by_mint(_read_table(funding_link_path)) if funding_link_path else {}
    grouped = _group_by_mint(snapshots)
    launch_rows = [
        _launch_profile(
            mint,
            rows,
            holder_by_mint.get(mint, []),
            entity_by_mint.get(mint, []),
            migration_by_mint.get(mint, {}),
            funding_by_mint.get(mint, []),
        )
        for mint, rows in sorted(grouped.items())
    ]
    feature_rows = [feature for row in launch_rows for feature in row["feature_snapshots"]]
    coverage = _coverage_report(launch_rows, snapshots, holder_by_mint, entity_by_mint, migration_by_mint, funding_by_mint)
    tier_summary = _tier_summary(launch_rows)
    comparison_rows = _tier_feature_comparison(feature_rows)
    holder_fdv_rows, holder_fdv_summary = _holder_fdv_deep_dive(feature_rows, snapshots)
    pattern_summary = _pattern_discovery(feature_rows)
    archetype_rows = _runner_archetypes(launch_rows)
    recommended = _recommended_theses(pattern_summary, holder_fdv_summary, archetype_rows, coverage)
    readiness = _readiness(coverage, pattern_summary, recommended)
    report = {
        "report_id": REPORT_ID,
        "report_type": "broad_descriptive_winner_anatomy",
        "readiness_classification": readiness,
        "methodology_flags": [
            "research_only",
            "descriptive_report_only",
            "not_a_thesis",
            "no_thesis_promotion",
            "no_validation_run",
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
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "fdv_proxy_not_true_market_cap",
        ],
        "dataset": {
            "snapshot_paths": [str(path) for path in snapshot_paths],
            "combined_snapshot_path": str(combined_path),
            "combine_summary": combine_summary,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "coverage_report": coverage,
        "milestone_tier_summary": tier_summary,
        "feature_context_counts": dict(Counter(row["feature_context"] for row in feature_rows)),
        "pattern_discovery_summary": pattern_summary,
        "holder_fdv_relationship_conclusion": holder_fdv_summary,
        "runner_archetypes": archetype_rows,
        "recommended_next_theses": recommended,
        "strongest_descriptive_commonalities": pattern_summary[:8],
        "limitations": _limitations(coverage),
        "next_action": _next_action(readiness, recommended),
    }
    paths = write_explosive_runner_winner_anatomy_outputs(
        report,
        comparison_rows=comparison_rows,
        holder_fdv_rows=holder_fdv_rows,
        archetype_rows=archetype_rows,
        recommended_rows=recommended,
        output_dir=output,
        status_path=status_path,
    )
    return report, paths


def write_explosive_runner_winner_anatomy_outputs(
    report: dict[str, Any],
    *,
    comparison_rows: list[dict[str, Any]],
    holder_fdv_rows: list[dict[str, Any]],
    archetype_rows: list[dict[str, Any]],
    recommended_rows: list[dict[str, Any]],
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    md_path = output / REPORT_MD
    comparison_csv = output / "milestone_tier_feature_comparison.csv"
    holder_csv = output / "holder_fdv_relationship_deep_dive.csv"
    archetype_csv = output / "runner_archetype_summary.csv"
    recommended_csv = output / "recommended_next_theses.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    _write_csv(comparison_rows, comparison_csv)
    _write_csv(holder_fdv_rows, holder_csv)
    _write_csv(archetype_rows, archetype_csv)
    _write_csv(recommended_rows, recommended_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, comparison_csv, holder_csv, archetype_csv, recommended_csv), encoding="utf-8")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": md_path,
        "milestone_tier_feature_comparison_path": comparison_csv,
        "holder_fdv_relationship_deep_dive_path": holder_csv,
        "runner_archetype_summary_path": archetype_csv,
        "recommended_next_theses_path": recommended_csv,
        "status_path": status,
    }


def _launch_profile(
    mint: str,
    rows: list[dict[str, Any]],
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any]:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    crossings = {name: _first_crossing(priced, value) for name, value in MILESTONES.items()}
    peak = max(priced, key=lambda row: _value(row) or 0) if priced else None
    tier = _highest_tier(crossings)
    creator = _first_present(*(row.get("creator") or row.get("creator_deployer") for row in rows), migration.get("creator"))
    launch_ts = _int_or_none(_first_present(*(row.get("launch_ts") for row in rows)))
    profile = {
        "mint": mint,
        "launch_id": _first_present(*(row.get("launch_id") for row in rows)),
        "creator": creator,
        "launch_ts": launch_ts,
        "launch_date": _launch_date(launch_ts),
        "milestone_tier": tier,
        "crossings": {name: _snapshot_view(row) if row else None for name, row in crossings.items()},
        "peak_fdv_proxy": _value(peak) if peak else None,
        "time_to_peak": _age(peak) if peak else None,
    }
    profile["feature_snapshots"] = _feature_snapshots(profile, priced, holders, entities, migration, funding)
    return profile


def _feature_snapshots(
    profile: dict[str, Any],
    priced: list[dict[str, Any]],
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for name, crossed in profile["crossings"].items():
        if name in {"15k", "20k", "30k", "50k", "100k"} and crossed:
            raw = _snapshot_before(priced, crossed["age_seconds"])
            if raw:
                rows.append(_feature_row(profile, raw, f"first_crossing_{name}", 0, holders, entities, migration, funding))
    for context, age in FIXED_TIME_CONTEXTS.items():
        raw = _snapshot_before(priced, age)
        if raw:
            rows.append(_feature_row(profile, raw, context, age - _age(raw), holders, entities, migration, funding))
    for milestone in ["100k", "200k", "500k", "1m"]:
        crossed = profile["crossings"].get(milestone)
        if not crossed:
            continue
        for label, offset in PRE_MILESTONE_OFFSETS.items():
            target_age = max(0, crossed["age_seconds"] - offset)
            raw = _snapshot_before(priced, target_age)
            if raw:
                rows.append(
                    _feature_row(
                        profile,
                        raw,
                        f"{label}_{milestone}",
                        target_age - _age(raw),
                        holders,
                        entities,
                        migration,
                        funding,
                    )
                )
    if not rows and priced:
        rows.append(_feature_row(profile, priced[-1], "peak_or_last_available", 0, holders, entities, migration, funding))
    return rows


def _feature_row(
    profile: dict[str, Any],
    row: dict[str, Any],
    context: str,
    timing_gap_seconds: int,
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any]:
    prior = row.get("_prior_snapshot") or {}
    holder = _nearest_holder(holders, _age(row))
    entity = entities[0] if entities else {}
    funding_row = funding[0] if funding else {}
    fdv = _value(row)
    event_count = _event_count(row)
    buy_count = _float_or_none(row.get("buy_count"))
    sell_count = _float_or_none(row.get("sell_count"))
    active = _float_or_none(row.get("active_wallets"))
    unique = _float_or_none(row.get("unique_actors"))
    holder_count = _first_float(row.get("holder_count"), holder.get("holder_count") if holder else None)
    out = {
        "launch_id": profile.get("launch_id"),
        "mint": profile["mint"],
        "token_mint": profile["mint"],
        "creator": profile.get("creator"),
        "launch_ts": profile.get("launch_ts"),
        "launch_date": profile.get("launch_date"),
        "milestone_tier": profile["milestone_tier"],
        "feature_context": context,
        "snapshot_age_seconds": _age(row),
        "nearest_prior_timing_gap_seconds": timing_gap_seconds,
        "valuation_proxy_usd": fdv,
        "event_count": event_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_buy_count": buy_count - sell_count if buy_count is not None and sell_count is not None else None,
        "buy_sell_ratio": _ratio(buy_count, sell_count),
        "event_count_growth": event_count - _event_count(prior) if event_count is not None and prior else None,
        "buy_count_growth": _delta(row, prior, "buy_count") if prior else None,
        "sell_count_growth": _delta(row, prior, "sell_count") if prior else None,
        "fdv_per_event": _ratio(fdv, event_count),
        "fdv_per_buy": _ratio(fdv, buy_count),
        "fdv_per_active_wallet": _ratio(fdv, active),
        "fdv_per_holder": _ratio(fdv, holder_count),
        "valuation_growth_per_event": _ratio(_delta_value(row, prior), event_count) if prior else None,
        "valuation_growth_per_buy": _ratio(_delta_value(row, prior), buy_count) if prior else None,
        "active_wallets": active,
        "unique_actors": unique,
        "active_wallet_growth": _delta(row, prior, "active_wallets") if prior else None,
        "unique_actor_growth": _delta(row, prior, "unique_actors") if prior else None,
        "events_per_active_wallet": _ratio(event_count, active),
        "buys_per_active_wallet": _ratio(buy_count, active),
        "holder_count": holder_count,
        "holder_count_growth": _holder_growth(holders, _age(row), 60),
        "holders_per_10k_fdv": _ratio(holder_count, (fdv or 0) / 10_000 if fdv else None),
        "top_holder_share": _float_or_none(holder.get("top_holder_share")) if holder else None,
        "top_10_holder_share": _float_or_none(holder.get("top_10_holder_share")) if holder else None,
        "creator_holder_share": _float_or_none(holder.get("creator_holder_share")) if holder else None,
        "repeated_actor_overlap_proxy": _float_or_none(entity.get("repeated_actor_overlap_proxy")),
        "repeated_buyer_overlap_proxy": _float_or_none(entity.get("repeated_buyer_overlap_proxy")),
        "synchronized_participation_proxy": _float_or_none(entity.get("synchronized_participation_proxy")),
        "circularity_proxy": _float_or_none(entity.get("circularity_proxy")),
        "churn_proxy": _float_or_none(entity.get("churn_proxy")),
        "creator_prior_launch_count": _float_or_none(migration.get("creator_prior_launch_count")),
        "creator_prior_migration_or_graduation_count": _float_or_none(migration.get("creator_prior_migration_or_graduation_count")),
        "creator_prior_migration_or_graduation_rate": _float_or_none(migration.get("creator_prior_migration_or_graduation_rate")),
        "funding_source_available": bool(funding_row.get("candidate_funding_wallet")) if funding_row else None,
        "repeated_funder_flag": bool((_float_or_none(funding_row.get("launches_sharing_funder")) or 0) > 1) if funding_row else None,
        "creator_funder_reuse_count": _float_or_none(funding_row.get("creator_funder_reuse_count")),
        "launches_sharing_funder": _float_or_none(funding_row.get("launches_sharing_funder")),
        "funding_age_seconds": _float_or_none(funding_row.get("funding_age_seconds")),
        "funding_amount_sol": _float_or_none(funding_row.get("funding_amount_sol")),
        "time_to_peak": profile.get("time_to_peak"),
    }
    mig_count = out["creator_prior_migration_or_graduation_count"]
    out["creator_has_prior_migration_or_graduation"] = bool(mig_count and mig_count >= 1) if mig_count is not None else None
    out["creator_has_2plus_prior_migrations_or_graduations"] = bool(mig_count and mig_count >= 2) if mig_count is not None else None
    out["creator_has_4plus_prior_migrations_or_graduations"] = bool(mig_count and mig_count >= 4) if mig_count is not None else None
    for name in ["15k", "20k", "30k", "50k"]:
        cross = profile["crossings"].get(name)
        out[f"time_to_{name}"] = cross["age_seconds"] if cross else None
    out["time_from_20k_to_50k"] = _time_between(profile, "20k", "50k")
    out["time_from_20k_to_100k"] = _time_between(profile, "20k", "100k")
    out["time_from_50k_to_100k"] = _time_between(profile, "50k", "100k")
    return out


def _coverage_report(
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, list[dict[str, Any]]],
    migration_by_mint: dict[str, dict[str, Any]],
    funding_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    dates_by_milestone = {name: Counter() for name in MILESTONES}
    for row in launch_rows:
        for name, crossed in row["crossings"].items():
            if crossed and row.get("launch_date"):
                dates_by_milestone[name][row["launch_date"]] += 1
    return {
        "total_launches": len(launch_rows),
        "snapshot_count": len(snapshots),
        "date_range": _date_range(row.get("launch_date") for row in launch_rows),
        "unique_launch_dates": len({row.get("launch_date") for row in launch_rows if row.get("launch_date")}),
        "trigger_counts": {name: sum(1 for row in launch_rows if row["crossings"].get(name)) for name in MILESTONES},
        "unique_dates_by_milestone": {name: len(counter) for name, counter in dates_by_milestone.items()},
        "rows_per_date_by_milestone": {name: dict(sorted(counter.items())) for name, counter in dates_by_milestone.items()},
        "forward_path_coverage": _forward_path_coverage(launch_rows),
        "missing_reason_counts": _missing_reasons(launch_rows),
        "data_source_coverage": {
            "holder_state_launches": len(holder_by_mint),
            "entity_proxy_launches": len(entity_by_mint),
            "creator_migration_label_launches": len(migration_by_mint),
            "funding_link_launches": len(funding_by_mint),
            "holder_state_coverage_pct": _pct(len(holder_by_mint), len(launch_rows)),
            "entity_proxy_coverage_pct": _pct(len(entity_by_mint), len(launch_rows)),
            "funding_link_coverage_pct": _pct(len(funding_by_mint), len(launch_rows)),
        },
    }


def _tier_summary(launch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for tier in TIER_ORDER:
        rows = [row for row in launch_rows if row["milestone_tier"] == tier]
        dates = Counter(row.get("launch_date") for row in rows if row.get("launch_date"))
        creators = Counter(row.get("creator") or "unknown" for row in rows)
        output[tier] = {
            "launch_count": len(rows),
            "unique_creator_count": len(creators),
            "unique_date_count": len(dates),
            "top_date_share": _top_share(dates, len(rows), 1),
            "top3_date_share": _top_share(dates, len(rows), 3),
            "top_creator_share": _top_share(creators, len(rows), 1),
            "top3_creator_share": _top_share(creators, len(rows), 3),
        }
    return output


def _tier_feature_comparison(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for context in sorted({row["feature_context"] for row in feature_rows}):
        context_rows = [row for row in feature_rows if row["feature_context"] == context]
        for tier in TIER_ORDER:
            tier_rows = [row for row in context_rows if row["milestone_tier"] == tier]
            for feature in FEATURE_FIELDS:
                values = [_float_or_none(row.get(feature)) for row in tier_rows]
                numeric = [value for value in values if value is not None]
                rows.append(
                    {
                        "feature_context": context,
                        "milestone_tier": tier,
                        "feature": feature,
                        **_distribution(numeric),
                        "missing_count": len(tier_rows) - len(numeric),
                        "coverage_pct": _pct(len(numeric), len(tier_rows)),
                    }
                )
    return rows


def _holder_fdv_deep_dive(feature_rows: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paired = [
        row for row in feature_rows
        if row["feature_context"] in {"launch_30s", "launch_3m", "launch_10m", "first_crossing_20k"}
        and _float_or_none(row.get("holder_count")) is not None
        and _float_or_none(row.get("valuation_proxy_usd")) is not None
    ]
    rows = []
    for bucket, lo, hi in [
        ("0_to_9", 0, 9),
        ("10_to_49", 10, 49),
        ("50_to_99", 50, 99),
        ("100_to_249", 100, 249),
        ("250_to_499", 250, 499),
        ("500_plus", 500, None),
    ]:
        members = [row for row in paired if _in_bucket(_float_or_none(row.get("holder_count")), lo, hi)]
        rows.append({"table": "median_fdv_by_holder_bucket", "bucket": bucket, **_distribution([row["valuation_proxy_usd"] for row in members])})
    for bucket, lo, hi in [
        ("under_20k", None, 20_000),
        ("20k_to_50k", 20_000, 50_000),
        ("50k_to_100k", 50_000, 100_000),
        ("100k_to_500k", 100_000, 500_000),
        ("500k_to_1m", 500_000, 1_000_000),
        ("1m_plus", 1_000_000, None),
    ]:
        members = [row for row in paired if _in_bucket(_float_or_none(row.get("valuation_proxy_usd")), lo, hi)]
        rows.append({"table": "median_holder_count_by_fdv_bucket", "bucket": bucket, **_distribution([row["holder_count"] for row in members])})
    for tier in TIER_ORDER:
        members = [row for row in paired if row["milestone_tier"] == tier]
        rows.append(
            {
                "table": "relationship_by_milestone_tier",
                "bucket": tier,
                "sample_count": len(members),
                "median_fdv_per_holder": _median([_float_or_none(row.get("fdv_per_holder")) for row in members]),
                "median_holders_per_10k_fdv": _median([_float_or_none(row.get("holders_per_10k_fdv")) for row in members]),
            }
        )
    conclusion = {
        "paired_rows": len(paired),
        "holder_count_tracks_fdv_as_proxy": len(paired) >= 500,
        "relationship_conclusion": "useful_partial_proxy" if len(paired) >= 500 else "data_limited_partial_proxy",
        "fdv_outruns_holders_observed": any(
            (_float_or_none(row.get("fdv_per_holder")) or 0) > 100_000 for row in paired
        ),
        "lead_lag_conclusion": "not_proven_from_snapshot_spacing",
    }
    return rows, conclusion


def _pattern_discovery(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = [row for row in feature_rows if row["feature_context"] == "first_crossing_20k"]
    comparisons = [
        ("100k_plus_vs_sub_100k", lambda r: r["milestone_tier"] in {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}),
        ("500k_plus_vs_sub_500k", lambda r: r["milestone_tier"] in {"reached_500k_but_never_1m", "reached_1m_plus"}),
        ("1m_plus_vs_sub_1m", lambda r: r["milestone_tier"] == "reached_1m_plus"),
        ("500k_1m_vs_100k_only", lambda r: r["milestone_tier"] in {"reached_500k_but_never_1m", "reached_1m_plus"}),
    ]
    output = []
    for name, predicate in comparisons:
        positives = [row for row in base if predicate(row)]
        if name == "500k_1m_vs_100k_only":
            negatives = [row for row in base if row["milestone_tier"] == "reached_100k_but_never_200k"]
        else:
            negatives = [row for row in base if not predicate(row)]
        for feature in FEATURE_FIELDS:
            pos = _median([_float_or_none(row.get(feature)) for row in positives])
            neg = _median([_float_or_none(row.get(feature)) for row in negatives])
            if pos is None or neg is None:
                continue
            delta = pos - neg
            score = abs(delta) / (abs(neg) + 1.0)
            output.append(
                {
                    "comparison": name,
                    "feature": feature,
                    "positive_count": len(positives),
                    "comparison_count": len(negatives),
                    "positive_median": pos,
                    "comparison_median": neg,
                    "delta": delta,
                    "direction": "higher" if delta > 0 else "lower" if delta < 0 else "flat",
                    "descriptive_score": score,
                    "classification": _difference_classification(score, len(positives), len(negatives)),
                }
            )
    return sorted(output, key=lambda row: (row["classification"] != "data_limited", row["descriptive_score"]), reverse=True)[:60]


def _runner_archetypes(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    high = [row for row in launch_rows if row["milestone_tier"] in {"reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_but_never_1m", "reached_1m_plus"}]
    features = [next((item for item in row["feature_snapshots"] if item["feature_context"] == "first_crossing_20k"), None) for row in high]
    features = [row for row in features if row]
    med_events = _median([row.get("event_count") for row in features]) or 0
    med_eff = _median([row.get("fdv_per_event") for row in features]) or 0
    med_wallets = _median([row.get("active_wallets") for row in features]) or 0
    specs = [
        ("low_flow_high_efficiency_runners", lambda r: (_float_or_none(r.get("event_count")) or 0) <= med_events and (_float_or_none(r.get("fdv_per_event")) or 0) >= med_eff),
        ("high_flow_broad_participation_runners", lambda r: (_float_or_none(r.get("event_count")) or 0) > med_events and (_float_or_none(r.get("active_wallets")) or 0) >= med_wallets),
        ("holder_acceleration_runners", lambda r: (_float_or_none(r.get("holder_count_growth")) or 0) > 0),
        ("creator_reputation_runners", lambda r: bool(r.get("creator_has_prior_migration_or_graduation"))),
        ("funding_linked_runners", lambda r: bool(r.get("repeated_funder_flag"))),
        ("concentrated_fast_runners", lambda r: (_float_or_none(r.get("top_holder_share")) or 0) >= 0.5 and (_float_or_none(r.get("time_to_20k")) or 999999) <= 300),
        ("slow_build_runners", lambda r: (_float_or_none(r.get("time_to_20k")) or 0) >= 600),
    ]
    rows = []
    by_mint = {row["mint"]: row for row in high}
    for name, predicate in specs:
        members = [row for row in features if predicate(row)]
        tier_counts = Counter(by_mint[row["mint"]]["milestone_tier"] for row in members if row["mint"] in by_mint)
        rows.append(
            {
                "archetype": name,
                "definition": _archetype_definition(name),
                "example_count": len(members),
                "representative_mints": ";".join(row["mint"] for row in members[:10]),
                "milestone_distribution": json.dumps(dict(sorted(tier_counts.items())), sort_keys=True),
                "limitations": "descriptive_median_based_not_optimized",
            }
        )
    return rows


def _recommended_theses(
    patterns: list[dict[str, Any]],
    holder_summary: dict[str, Any],
    archetypes: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for pattern in patterns[:3]:
        rows.append(
            {
                "thesis_name": f"Explosive Runner {pattern['feature'].replace('_', ' ').title()} Separation",
                "measurable_feature_family": pattern["feature"],
                "why_promising": f"{pattern['comparison']} shows {pattern['direction']} median separation",
                "outcome_to_test": "crossed_100k_or_500k_after_20k_fdv_proxy",
                "data_coverage": f"{pattern['positive_count']} positive / {pattern['comparison_count']} comparison rows",
                "would_invalidate": "direction reverses or disappears under chronological/date-balanced robustness",
                "recommended_type": "formal_historical_thesis" if pattern["classification"] in {"strong_descriptive_difference", "moderate_descriptive_difference"} else "data_enrichment_first",
            }
        )
    if holder_summary["holder_count_tracks_fdv_as_proxy"]:
        rows.append(
            {
                "thesis_name": "Holder FDV Proxy Lead Lag",
                "measurable_feature_family": "holder_count_and_fdv_per_holder",
                "why_promising": "holder/FDV paired rows are large enough for descriptive follow-up",
                "outcome_to_test": "whether holder growth leads later FDV-proxy milestones",
                "data_coverage": f"{holder_summary['paired_rows']} paired rows",
                "would_invalidate": "holder growth only lags FDV or coverage collapses by date",
                "recommended_type": "formal_historical_thesis",
            }
        )
    return rows[:3]


def _readiness(coverage: dict[str, Any], patterns: list[dict[str, Any]], recommended: list[dict[str, Any]]) -> str:
    if coverage["trigger_counts"]["100k"] < 100 or coverage["trigger_counts"]["20k"] < 1000:
        return "winner_anatomy_report_needs_more_data"
    if not recommended or not any(row["recommended_type"] == "formal_historical_thesis" for row in recommended):
        return "winner_anatomy_report_inconclusive"
    if not any(row["classification"] in {"strong_descriptive_difference", "moderate_descriptive_difference"} for row in patterns[:10]):
        return "winner_anatomy_report_inconclusive"
    return "winner_anatomy_report_ready_for_next_thesis"


def _next_action(readiness: str, recommended: list[dict[str, Any]]) -> str:
    if readiness == "winner_anatomy_report_ready_for_next_thesis" and recommended:
        return f"Review and design the next formal historical thesis around `{recommended[0]['measurable_feature_family']}`. Do not validate or promote yet."
    if readiness == "winner_anatomy_report_needs_more_data":
        return "Improve milestone/date coverage before formal thesis testing."
    return "Park broad winner anatomy until stronger descriptive differences or better holder/entity/funding coverage exist."


def _markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage_report"]
    tiers = report["milestone_tier_summary"]
    return "\n".join(
        [
            "# Explosive Runner Winner Anatomy Report",
            "",
            "This is a broad descriptive report only. It does not run validation, backtests, paper/live trading, optimization, or strategy logic.",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Launches analyzed: `{coverage['total_launches']}`",
            f"- $100k trigger count: `{coverage['trigger_counts']['100k']}`",
            f"- $500k trigger count: `{coverage['trigger_counts']['500k']}`",
            f"- $1M trigger count: `{coverage['trigger_counts']['1m']}`",
            f"- Holder/FDV conclusion: `{report['holder_fdv_relationship_conclusion']['relationship_conclusion']}`",
            "",
            "## Tier Counts",
            "",
            *[f"- `{tier}`: `{values['launch_count']}`" for tier, values in tiers.items()],
            "",
            "## Strongest Descriptive Commonalities",
            "",
            *[f"- `{row['comparison']}` `{row['feature']}`: `{row['direction']}` ({row['classification']})" for row in report["strongest_descriptive_commonalities"][:8]],
            "",
            "## Recommended Next Theses",
            "",
            *[f"- `{row['thesis_name']}`: `{row['recommended_type']}`" for row in report["recommended_next_theses"]],
        ]
    )


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path, comparison_csv: Path, holder_csv: Path, archetype_csv: Path, recommended_csv: Path) -> str:
    return "\n".join(
        [
            "# Explosive Runner Winner Anatomy Report Status",
            "",
            "## Why This Report Was Created",
            "",
            "The expanded T011 rerun showed a weak but unstable low-flow/high-FDV-efficiency pattern. This report broadens the question from proving T011 to describing what explosive winners had in common before major FDV-proxy milestones.",
            "",
            "## Dataset Used",
            "",
            f"- Launches analyzed: `{report['coverage_report']['total_launches']}`",
            f"- Date range: `{report['coverage_report']['date_range']}`",
            f"- Valuation semantics: `FDV proxy only`",
            "",
            "## Coverage Summary",
            "",
            f"- Trigger counts: `{report['coverage_report']['trigger_counts']}`",
            f"- Unique dates by milestone: `{report['coverage_report']['unique_dates_by_milestone']}`",
            "",
            "## Milestone Tier Counts",
            "",
            *[f"- `{tier}`: `{values['launch_count']}`" for tier, values in report["milestone_tier_summary"].items()],
            "",
            "## Strongest Descriptive Commonalities",
            "",
            *[f"- `{row['comparison']}` / `{row['feature']}`: `{row['direction']}` `{row['classification']}`" for row in report["strongest_descriptive_commonalities"][:8]],
            "",
            "## Holder/FDV Relationship",
            "",
            f"- Conclusion: `{report['holder_fdv_relationship_conclusion']['relationship_conclusion']}`",
            f"- Paired rows: `{report['holder_fdv_relationship_conclusion']['paired_rows']}`",
            "",
            "## Runner Archetypes",
            "",
            *[f"- `{row['archetype']}`: `{row['example_count']}` examples" for row in report["runner_archetypes"]],
            "",
            "## Recommended Next Theses",
            "",
            *[f"- `{row['thesis_name']}`: `{row['recommended_type']}`" for row in report["recommended_next_theses"]],
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Next Action",
            "",
            report["next_action"],
            "",
            "## Report Paths",
            "",
            f"- JSON: `{json_path}`",
            f"- Markdown: `{md_path}`",
            f"- Tier comparison CSV: `{comparison_csv}`",
            f"- Holder/FDV CSV: `{holder_csv}`",
            f"- Archetype CSV: `{archetype_csv}`",
            f"- Recommended theses CSV: `{recommended_csv}`",
        ]
    )


def _limitations(coverage: dict[str, Any]) -> list[str]:
    return [
        "True market-cap claims remain blocked; this report uses FDV/valuation proxy only.",
        "This is descriptive discovery, not validation or thesis promotion.",
        "No entry, exit, profitability, trading, or strategy claims are made.",
        "Holder, entity, migration, and funding overlays are partial and should not be over-interpreted.",
        "Pre-milestone rows use nearest prior snapshots and report timing gaps.",
        f"Holder-state coverage is {coverage['data_source_coverage']['holder_state_coverage_pct']:.2f}%.",
    ]


def _highest_tier(crossings: dict[str, dict[str, Any] | None]) -> str:
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
    if crossings.get("20k"):
        return "reached_20k_but_never_50k"
    return "never_reached_20k"


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0) >= threshold:
            return row
    return None


def _snapshot_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _age(row) <= age]
    if not eligible:
        return None
    selected = max(eligible, key=_age)
    prior_candidates = [row for row in rows if _age(row) < _age(selected)]
    if prior_candidates:
        selected = dict(selected)
        selected["_prior_snapshot"] = max(prior_candidates, key=_age)
    return selected


def _snapshot_view(row: dict[str, Any]) -> dict[str, Any]:
    return {"age_seconds": _age(row), "valuation_proxy_usd": _value(row), "snapshot_ts": row.get("snapshot_ts")}


def _forward_path_coverage(launch_rows: list[dict[str, Any]]) -> dict[str, float]:
    output = {}
    for name in ["20k", "50k", "100k", "200k", "500k", "1m"]:
        crossed = [row for row in launch_rows if row["crossings"].get(name)]
        covered = [row for row in crossed if (row.get("time_to_peak") or 0) > row["crossings"][name]["age_seconds"]]
        output[name] = _pct(len(covered), len(crossed))
    return output


def _missing_reasons(launch_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in launch_rows:
        if not row["crossings"].get("20k"):
            counts["missing_20k_trigger"] += 1
        if row["crossings"].get("20k") and (row.get("time_to_peak") or 0) <= row["crossings"]["20k"]["age_seconds"]:
            counts["missing_forward_path_after_20k"] += 1
    return dict(sorted(counts.items()))


def _time_between(profile: dict[str, Any], start: str, end: str) -> float | None:
    a = profile["crossings"].get(start)
    b = profile["crossings"].get(end)
    if not a or not b:
        return None
    return b["age_seconds"] - a["age_seconds"]


def _difference_classification(score: float, pos: int, neg: int) -> str:
    if pos < 30 or neg < 30:
        return "data_limited"
    if score >= 1.0:
        return "strong_descriptive_difference"
    if score >= 0.35:
        return "moderate_descriptive_difference"
    if score >= 0.1:
        return "weak_descriptive_difference"
    return "no_clear_difference"


def _archetype_definition(name: str) -> str:
    return {
        "low_flow_high_efficiency_runners": "Above-median FDV per event with at-or-below-median event count at first $20k.",
        "high_flow_broad_participation_runners": "Above-median event count and active-wallet breadth at first $20k.",
        "holder_acceleration_runners": "Observed positive holder-count growth near first $20k.",
        "creator_reputation_runners": "Creator has prior observed migration/graduation evidence.",
        "funding_linked_runners": "Funding pilot shows repeated/common funder evidence.",
        "concentrated_fast_runners": "High observed top-holder share and fast first $20k crossing.",
        "slow_build_runners": "First $20k crossing occurs at or after 10 minutes.",
    }[name]


def _read_table(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    if value.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(value).to_dict(orient="records")
    if value.suffix == ".csv":
        with value.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return _read_jsonl(value)


def _read_jsonl(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    value = Path(path)
    if not value.exists():
        return []
    rows = []
    with value.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _migration_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(_mint(row)): row for row in rows if _mint(row)}


def _nearest_holder(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    return min(rows, key=lambda row: abs(_age_holder(row) - age)) if rows else None


def _holder_growth(rows: list[dict[str, Any]], age: int, window: int) -> float | None:
    now = _nearest_holder(rows, age)
    before = _nearest_holder(rows, max(0, age - window))
    if not now or not before:
        return None
    return _delta(now, before, "holder_count")


def _distribution(values: list[float | None]) -> dict[str, Any]:
    vals = sorted(value for value in values if value is not None)
    if not vals:
        return {"sample_count": 0, "median": None, "iqr": None, "p10": None, "p90": None}
    return {
        "sample_count": len(vals),
        "median": median(vals),
        "iqr": [vals[len(vals) // 4], vals[(len(vals) * 3) // 4]],
        "p10": vals[int((len(vals) - 1) * 0.1)],
        "p90": vals[int((len(vals) - 1) * 0.9)],
    }


def _median(values: list[Any]) -> float | None:
    vals = [_float_or_none(value) for value in values]
    vals = [value for value in vals if value is not None]
    return median(vals) if vals else None


def _date_range(values: Any) -> dict[str, str | None]:
    dates = sorted(value for value in values if value)
    return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None}


def _top_share(counter: Counter, total: int, n: int) -> float:
    if not total:
        return 0.0
    return sum(count for _, count in counter.most_common(n)) / total


def _pct(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def _in_bucket(value: float | None, lo: float | None, hi: float | None) -> bool:
    if value is None:
        return False
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _event_count(row: dict[str, Any]) -> float | None:
    return _first_float(row.get("event_count"), row.get("tx_count"), (row.get("metadata_json") or {}).get("event_count"))


def _delta(row: dict[str, Any], prior: dict[str, Any], field: str) -> float | None:
    a = _float_or_none(row.get(field))
    b = _float_or_none(prior.get(field))
    if a is None or b is None:
        return None
    return a - b


def _delta_value(row: dict[str, Any], prior: dict[str, Any]) -> float | None:
    a = _value(row)
    b = _value(prior)
    if a is None or b is None:
        return None
    return a - b


def _ratio(a: Any, b: Any) -> float | None:
    num = _float_or_none(a)
    den = _float_or_none(b)
    if num is None or den in (None, 0):
        return None
    return num / den


def _value(row: dict[str, Any]) -> float | None:
    return _first_float(row.get("valuation_proxy_usd"), row.get("fdv_usd"))


def _age(row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    return _int_or_none(row.get("launch_age_seconds") or row.get("snapshot_age_seconds")) or 0


def _age_holder(row: dict[str, Any]) -> int:
    return _int_or_none(row.get("snapshot_age_seconds") or row.get("launch_age_seconds")) or 0


def _mint(row: dict[str, Any]) -> str | None:
    value = row.get("token_mint") or row.get("mint")
    return str(value) if value else None


def _launch_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
