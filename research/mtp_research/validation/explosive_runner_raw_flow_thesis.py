"""Descriptive T011 explosive-runner raw-flow continuation thesis."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


THESIS_ID = "T011"
THESIS_NAME = "EXPLOSIVE RUNNER RAW-FLOW CONTINUATION"
REPORT_ID = "t011_explosive_runner_raw_flow_v0"
REPORT_JSON = "T011_explosive_runner_raw_flow_summary.json"
REPORT_MD = "T011_explosive_runner_raw_flow_summary.md"
TRIGGER_THRESHOLDS = {"15k": 15_000.0, "20k": 20_000.0, "30k": 30_000.0}
PRIMARY_TRIGGER = "20k"
MILESTONES = {"50k": 50_000.0, "100k": 100_000.0, "200k": 200_000.0, "500k": 500_000.0, "1m": 1_000_000.0}
TIER_ORDER = [
    "reached_20k_but_never_50k",
    "reached_50k_but_never_100k",
    "reached_100k_but_never_200k",
    "reached_200k_but_never_500k",
    "reached_500k_but_never_1m",
    "reached_1m_plus",
]
FEATURE_FIELDS = [
    "buy_count_at_20k",
    "sell_count_at_20k",
    "event_count_at_20k",
    "active_wallets_at_20k",
    "unique_actors_at_20k",
    "buy_sell_ratio_at_20k",
    "net_buy_count_at_20k",
    "buys_per_active_wallet_at_20k",
    "events_per_active_wallet_at_20k",
    "buy_count_growth_before_20k",
    "sell_count_growth_before_20k",
    "event_count_growth_before_20k",
    "active_wallet_growth_before_20k",
    "flow_acceleration_30s_to_20k",
    "flow_acceleration_60s_to_20k",
    "holder_count_at_20k",
    "holder_growth_before_20k",
    "fdv_per_holder_at_20k",
    "holders_per_10k_fdv_at_20k",
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
    "creator_prior_migration_or_graduation_count",
    "funding_source_available",
    "repeated_funder_flag",
    "top_holder_share_at_20k",
    "top_10_holder_share_at_20k",
    "creator_holder_share_at_20k",
]
CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}


def build_t011_explosive_runner_raw_flow_report(
    *,
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    funding_link_path: Path | str | None = None,
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    grouped = _group_by_mint(snapshots)
    holder_by_mint = _sidecar_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    entity_by_mint = _sidecar_by_mint(_read_jsonl(entity_proxy_path)) if entity_proxy_path else {}
    migration_by_mint = _migration_by_mint(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    funding_by_mint = _sidecar_by_mint(_read_table(funding_link_path)) if funding_link_path else {}
    launch_rows = [
        _build_trigger_row(
            mint,
            rows,
            holder_by_mint.get(mint, []),
            entity_by_mint.get(mint, []),
            migration_by_mint.get(mint, {}),
            funding_by_mint.get(mint, []),
        )
        for mint, rows in sorted(grouped.items())
    ]
    launch_rows = [row for row in launch_rows if row is not None]
    launch_rows.sort(key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    tier_table = _milestone_tier_feature_table(launch_rows)
    primary = _primary_comparisons(launch_rows)
    quantiles = _quantile_bucket_tables(launch_rows)
    robustness = _robustness_checks(launch_rows)
    diagnostics = _diagnostics(primary, launch_rows)
    coverage = _feature_coverage_audit(
        launch_rows=launch_rows,
        all_launch_count=len(grouped),
        holder_by_mint=holder_by_mint,
        entity_by_mint=entity_by_mint,
        migration_by_mint=migration_by_mint,
        funding_by_mint=funding_by_mint,
    )
    classification = _classify(launch_rows, primary, robustness)
    return {
        "report_id": REPORT_ID,
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "After a token reaches an observable $20k FDV-proxy trigger, do raw flow and "
            "participation features distinguish continuations into higher explosive-runner tiers?"
        ),
        "dataset": {
            "dataset_scope": "all_collected_fdv_proxy_lifecycle",
            "snapshots_path": str(snapshots_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path) if holder_state_snapshots_path else None,
            "entity_proxy_path": str(entity_proxy_path) if entity_proxy_path else None,
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "funding_link_path": str(funding_link_path) if funding_link_path else None,
            "launches_analyzed": len(grouped),
            "snapshot_count": len(snapshots),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "primary_trigger": "$20k FDV proxy first crossing",
            "secondary_triggers_diagnostic_only": ["$15k", "$30k"],
            "fixed_thresholds": {**TRIGGER_THRESHOLDS, **MILESTONES},
            "classification_options": sorted(CLASSIFICATIONS),
            "quantile_bucket_method": "fixed quintiles where enough non-missing values exist",
        },
        "methodology_flags": [
            "research_only",
            "descriptive_historical_thesis",
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
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "trigger_summary": _trigger_summary(grouped),
        "milestone_tier_counts": dict(Counter(row["milestone_tier"] for row in launch_rows)),
        "feature_coverage_audit": coverage,
        "milestone_tier_feature_table": tier_table,
        "primary_comparisons": primary,
        "quantile_bucket_tables": quantiles,
        "diagnostics": diagnostics,
        "robustness_checks": robustness,
        "trigger_rows": launch_rows,
        "final_classification": classification,
        "chronological_robustness_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "warning_flags": _warning_flags(classification, coverage),
        "limitations": _limitations(coverage),
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(
            snapshots_path,
            holder_state_snapshots_path,
            entity_proxy_path,
            migration_labels_path,
            funding_link_path,
        ),
    }


def write_t011_explosive_runner_raw_flow_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    markdown_path = output / REPORT_MD
    tier_csv = output / "milestone_tier_feature_table.csv"
    feature_csv = output / "trigger_20k_feature_rows.csv"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    _write_csv(_tier_csv_rows(report["milestone_tier_feature_table"]), tier_csv)
    _write_csv(_feature_csv_rows(report["trigger_rows"]), feature_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, markdown_path, tier_csv, feature_csv), encoding="utf-8")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": markdown_path,
        "milestone_tier_feature_table_path": tier_csv,
        "trigger_20k_feature_rows_path": feature_csv,
        "status_path": status,
    }


def _build_trigger_row(
    mint: str,
    rows: list[dict[str, Any]],
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any] | None:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    trigger = _first_crossing(priced, TRIGGER_THRESHOLDS[PRIMARY_TRIGGER])
    if not trigger:
        return None
    crossings = {name: _first_crossing(priced, threshold) for name, threshold in MILESTONES.items()}
    peak = max((_value(row) or 0 for row in priced), default=None)
    features = _features_at_trigger(trigger, priced, holders, entities, migration, funding)
    tier = _milestone_tier(crossings)
    return {
        "launch_id": _first_present(*(row.get("launch_id") for row in rows)),
        "token_mint": mint,
        "mint": mint,
        "creator": _creator(rows, migration, funding),
        "launch_ts": _int_or_none(_first_present(*(row.get("launch_ts") for row in rows))),
        "trigger_age_seconds": _age(trigger),
        "trigger_snapshot_ts": trigger.get("snapshot_ts"),
        "trigger_fdv_proxy": _value(trigger),
        "peak_fdv_proxy": peak,
        "crossings": {f"first_crossed_{name}": _snapshot_view(row) if row else None for name, row in crossings.items()},
        "milestone_tier": tier,
        "outcomes": _outcomes_after_20k(trigger, priced, crossings, tier),
        "features": features,
        "metadata_json": {
            "feature_leakage_rule": "features use only snapshots at or before first $20k FDV-proxy crossing",
            "holder_state_semantics": "observed_delta_replay_not_full_chain_snapshot",
        },
    }


def _features_at_trigger(
    trigger: dict[str, Any],
    priced: list[dict[str, Any]],
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any]:
    age = _age(trigger)
    first_prior = _snapshot_before(priced, max(0, age - 1)) or trigger
    prior_30 = _snapshot_before(priced, max(0, age - 30)) or first_prior
    prior_60 = _snapshot_before(priced, max(0, age - 60)) or first_prior
    holder = _nearest_holder(holders, age)
    holder_prior = _nearest_holder_before(holders, max(0, age - 60))
    entity = entities[0] if entities else {}
    funding_row = funding[0] if funding else None
    buys = _float_or_none(trigger.get("buy_count"))
    sells = _float_or_none(trigger.get("sell_count"))
    events = _event_count(trigger)
    active = _float_or_none(trigger.get("active_wallets"))
    holders_now = _first_float(trigger.get("holder_count"), holder.get("holder_count") if holder else None)
    fdv = _value(trigger)
    return {
        "buy_count_at_20k": buys,
        "sell_count_at_20k": sells,
        "event_count_at_20k": events,
        "active_wallets_at_20k": active,
        "unique_actors_at_20k": _float_or_none(trigger.get("unique_actors")),
        "buy_sell_ratio_at_20k": _ratio(buys, sells),
        "net_buy_count_at_20k": buys - sells if buys is not None and sells is not None else None,
        "buys_per_active_wallet_at_20k": _ratio(buys, active),
        "events_per_active_wallet_at_20k": _ratio(events, active),
        "buy_count_growth_before_20k": _delta(trigger, first_prior, "buy_count"),
        "sell_count_growth_before_20k": _delta(trigger, first_prior, "sell_count"),
        "event_count_growth_before_20k": (_event_count(trigger) or 0) - (_event_count(first_prior) or 0),
        "active_wallet_growth_before_20k": _delta(trigger, first_prior, "active_wallets"),
        "flow_acceleration_30s_to_20k": (_event_count(trigger) or 0) - (_event_count(prior_30) or 0),
        "flow_acceleration_60s_to_20k": (_event_count(trigger) or 0) - (_event_count(prior_60) or 0),
        "holder_count_at_20k": holders_now,
        "holder_growth_before_20k": (
            holders_now - _float_or_none(holder_prior.get("holder_count"))
            if holders_now is not None and holder_prior and _float_or_none(holder_prior.get("holder_count")) is not None
            else None
        ),
        "fdv_per_holder_at_20k": _ratio(fdv, holders_now),
        "holders_per_10k_fdv_at_20k": _ratio(holders_now, (fdv or 0) / 10_000 if fdv else None),
        "repeated_actor_overlap_proxy": _float_or_none(entity.get("repeated_actor_overlap_proxy")),
        "repeated_buyer_overlap_proxy": _float_or_none(entity.get("repeated_buyer_overlap_proxy")),
        "synchronized_participation_proxy": _float_or_none(entity.get("synchronized_participation_proxy")),
        "circularity_proxy": _float_or_none(entity.get("circularity_proxy")),
        "churn_proxy": _float_or_none(entity.get("churn_proxy")),
        "creator_prior_migration_or_graduation_count": _float_or_none(
            migration.get("creator_prior_migration_or_graduation_count")
        ),
        "funding_source_available": bool(funding_row.get("candidate_funding_wallet")) if funding_row else None,
        "repeated_funder_flag": (
            bool((_float_or_none(funding_row.get("launches_sharing_funder")) or 0) > 1)
            if funding_row
            else None
        ),
        "top_holder_share_at_20k": _float_or_none(holder.get("top_holder_share")) if holder else None,
        "top_10_holder_share_at_20k": _float_or_none(holder.get("top_10_holder_share")) if holder else None,
        "creator_holder_share_at_20k": _float_or_none(holder.get("creator_holder_share")) if holder else None,
    }


def _outcomes_after_20k(
    trigger: dict[str, Any],
    priced: list[dict[str, Any]],
    crossings: dict[str, dict[str, Any] | None],
    tier: str,
) -> dict[str, Any]:
    trigger_age = _age(trigger)
    outcomes = {
        f"crossed_{name}_after_20k": bool(row and _age(row) >= trigger_age)
        for name, row in crossings.items()
    }
    outcomes.update(
        {
            "crossed_50k_within_1m_from_20k": _crossed_within(priced, trigger_age, 60, 50_000),
            "crossed_50k_within_5m_from_20k": _crossed_within(priced, trigger_age, 300, 50_000),
            "crossed_100k_within_5m_from_20k": _crossed_within(priced, trigger_age, 300, 100_000),
            "crossed_100k_within_10m_from_20k": _crossed_within(priced, trigger_age, 600, 100_000),
            "crossed_200k_within_30m_from_20k": _crossed_within(priced, trigger_age, 1800, 200_000),
            "crossed_500k_within_60m_from_20k": _crossed_within(priced, trigger_age, 3600, 500_000),
            "reached_20k_but_never_50k": tier == "reached_20k_but_never_50k",
            "reached_50k_but_never_100k": tier == "reached_50k_but_never_100k",
            "reached_100k_but_never_200k": tier == "reached_100k_but_never_200k",
            "reached_200k_but_never_500k": tier == "reached_200k_but_never_500k",
            "reached_500k_but_never_1m": tier == "reached_500k_but_never_1m",
        }
    )
    return outcomes


def _trigger_summary(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    output = {}
    for name, threshold in TRIGGER_THRESHOLDS.items():
        output[f"trigger_{name}_count"] = sum(
            1 for rows in grouped.values() if _first_crossing(sorted([row for row in rows if _value(row) is not None], key=_age), threshold)
        )
    return output


def _milestone_tier(crossings: dict[str, dict[str, Any] | None]) -> str:
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


def _milestone_tier_feature_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for tier in TIER_ORDER:
        members = [row for row in rows if row["milestone_tier"] == tier]
        output[tier] = {
            "launch_count": len(members),
            "feature_distributions": {field: _distribution(_feature_values(members, field)) for field in FEATURE_FIELDS},
        }
    return output


def _primary_comparisons(rows: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = {
        "100k_plus_vs_sub_100k": (
            [row for row in rows if row["outcomes"]["crossed_100k_after_20k"]],
            [row for row in rows if not row["outcomes"]["crossed_100k_after_20k"]],
        ),
        "200k_plus_vs_100k_only": (
            [row for row in rows if row["outcomes"]["crossed_200k_after_20k"]],
            [row for row in rows if row["milestone_tier"] == "reached_100k_but_never_200k"],
        ),
        "500k_plus_vs_100k_to_500k": (
            [row for row in rows if row["outcomes"]["crossed_500k_after_20k"]],
            [row for row in rows if row["milestone_tier"] in {"reached_100k_but_never_200k", "reached_200k_but_never_500k"}],
        ),
        "1m_plus_vs_sub_1m": (
            [row for row in rows if row["outcomes"]["crossed_1m_after_20k"]],
            [row for row in rows if not row["outcomes"]["crossed_1m_after_20k"]],
        ),
    }
    return {name: _comparison_table(pos, neg) for name, (pos, neg) in comparisons.items()}


def _comparison_table(positive: list[dict[str, Any]], negative: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "event_count_at_20k",
        "buy_count_at_20k",
        "active_wallets_at_20k",
        "holder_count_at_20k",
        "fdv_per_holder_at_20k",
        "repeated_actor_overlap_proxy",
        "funding_source_available",
    ]
    return {
        "positive_count": len(positive),
        "comparison_count": len(negative),
        "feature_median_deltas": {
            field: {
                "positive_median": _median(_feature_values(positive, field)),
                "comparison_median": _median(_feature_values(negative, field)),
                "delta": _median_delta(positive, negative, field),
            }
            for field in fields
        },
    }


def _quantile_bucket_tables(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for field in [
        "event_count_at_20k",
        "buy_count_at_20k",
        "active_wallets_at_20k",
        "holder_count_at_20k",
        "fdv_per_holder_at_20k",
    ]:
        output[field] = _quintiles(rows, field)
    return output


def _quintiles(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    valued = [(row, _float_or_none(row["features"].get(field))) for row in rows]
    valued = [(row, value) for row, value in valued if value is not None]
    if len(valued) < 10:
        return []
    valued.sort(key=lambda item: item[1])
    buckets = []
    for index in range(5):
        start = (len(valued) * index) // 5
        end = (len(valued) * (index + 1)) // 5
        chunk = valued[start:end]
        members = [row for row, _ in chunk]
        values = [value for _, value in chunk]
        buckets.append(
            {
                "bucket": f"q{index + 1}",
                "sample_count": len(members),
                "min_value": min(values) if values else None,
                "max_value": max(values) if values else None,
                "crossed_100k_rate": _pct(sum(1 for row in members if row["outcomes"]["crossed_100k_after_20k"]), len(members)),
                "crossed_500k_rate": _pct(sum(1 for row in members if row["outcomes"]["crossed_500k_after_20k"]), len(members)),
            }
        )
    return buckets


def _robustness_checks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "exclude_top_1pct_fdv_proxy_runups": _trimmed_signal(rows, pct=0.01),
        "exclude_top_5pct_fdv_proxy_runups": _trimmed_signal(rows, pct=0.05),
        "chronological_halves": _chronological_halves(rows),
        "creator_concentration_check": _creator_concentration(rows),
        "dominant_creator_exclusion": _dominant_creator_exclusion(rows),
        "source_sensitivity": {
            "migration_labels_used": any(row["features"].get("creator_prior_migration_or_graduation_count") is not None for row in rows),
            "dexscreener_migration_source_not_used_for_primary_classification": True,
        },
        "holder_state_confidence_sensitivity": {
            "holder_state_used": any(row["features"].get("holder_count_at_20k") is not None for row in rows),
            "observed_delta_replay_not_full_chain_state": True,
        },
        "strict_subset_possible": any(row["features"].get("holder_count_at_20k") is not None for row in rows),
    }


def _trimmed_signal(rows: list[dict[str, Any]], pct: float) -> dict[str, Any]:
    if not rows:
        return {"available": False}
    ordered = sorted(rows, key=lambda row: row.get("peak_fdv_proxy") or 0)
    keep = ordered[: max(0, int(len(ordered) * (1 - pct)))]
    table = _comparison_table(
        [row for row in keep if row["outcomes"]["crossed_100k_after_20k"]],
        [row for row in keep if not row["outcomes"]["crossed_100k_after_20k"]],
    )
    return {"available": bool(keep), "rows_after_exclusion": len(keep), "100k_plus_comparison": table}


def _chronological_halves(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 20:
        return {"available": False, "reason": "too_few_trigger_rows"}
    ordered = sorted(rows, key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    mid = len(ordered) // 2
    return {
        "available": True,
        "first_half": _comparison_table(
            [row for row in ordered[:mid] if row["outcomes"]["crossed_100k_after_20k"]],
            [row for row in ordered[:mid] if not row["outcomes"]["crossed_100k_after_20k"]],
        ),
        "second_half": _comparison_table(
            [row for row in ordered[mid:] if row["outcomes"]["crossed_100k_after_20k"]],
            [row for row in ordered[mid:] if not row["outcomes"]["crossed_100k_after_20k"]],
        ),
    }


def _creator_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("creator") or "unknown" for row in rows)
    total = len(rows)
    top = counts.most_common(5)
    return {
        "unique_creators": len(counts),
        "top_creators": [{"creator": creator, "launch_count": count, "share_pct": _pct(count, total)} for creator, count in top],
    }


def _dominant_creator_exclusion(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("creator") or "unknown" for row in rows)
    if not counts:
        return {"available": False}
    dominant, count = counts.most_common(1)[0]
    reduced = [row for row in rows if (row.get("creator") or "unknown") != dominant]
    return {
        "available": True,
        "dominant_creator": dominant,
        "excluded_launch_count": count,
        "rows_after_exclusion": len(reduced),
        "100k_plus_comparison": _comparison_table(
            [row for row in reduced if row["outcomes"]["crossed_100k_after_20k"]],
            [row for row in reduced if not row["outcomes"]["crossed_100k_after_20k"]],
        ),
    }


def _diagnostics(primary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "raw_flow_separates_100k_plus_from_failures": _field_has_delta(primary, "100k_plus_vs_sub_100k", "event_count_at_20k"),
        "raw_flow_separates_500k_plus_from_100k_only": _field_has_delta(primary, "500k_plus_vs_100k_to_500k", "event_count_at_20k"),
        "active_wallet_breadth_adds_information": _field_has_delta(primary, "100k_plus_vs_sub_100k", "active_wallets_at_20k"),
        "holder_count_adds_information": _field_has_delta(primary, "100k_plus_vs_sub_100k", "holder_count_at_20k"),
        "fdv_per_holder_differs_for_higher_tiers": _field_has_delta(primary, "500k_plus_vs_100k_to_500k", "fdv_per_holder_at_20k"),
        "entity_proxy_adds_information": _field_has_delta(primary, "100k_plus_vs_sub_100k", "repeated_actor_overlap_proxy"),
        "funding_link_information_adds_information_where_available": _field_has_delta(primary, "100k_plus_vs_sub_100k", "funding_source_available"),
        "trigger_row_count": len(rows),
    }


def _field_has_delta(primary: dict[str, Any], comparison: str, field: str) -> bool:
    delta = primary.get(comparison, {}).get("feature_median_deltas", {}).get(field, {}).get("delta")
    return delta is not None and abs(delta) > 0


def _feature_coverage_audit(
    *,
    launch_rows: list[dict[str, Any]],
    all_launch_count: int,
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, list[dict[str, Any]]],
    migration_by_mint: dict[str, dict[str, Any]],
    funding_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    output = {}
    for field in FEATURE_FIELDS:
        source_type = _source_type(field, holder_by_mint, entity_by_mint, migration_by_mint, funding_by_mint)
        available = sum(1 for row in launch_rows if row["features"].get(field) is not None)
        output[field] = {
            "available_rows": available,
            "missing_rows": len(launch_rows) - available,
            "coverage_pct": _pct(available, len(launch_rows)),
            "scope": "all_collected" if available == len(launch_rows) else "partial_sidecar_or_missing",
            "source_type": source_type,
        }
    output["sidecar_launch_coverage"] = {
        "all_launch_count": all_launch_count,
        "trigger_20k_launch_count": len(launch_rows),
        "holder_state_mints": len(holder_by_mint),
        "entity_proxy_mints": len(entity_by_mint),
        "migration_label_mints": len(migration_by_mint),
        "funding_link_mints": len(funding_by_mint),
    }
    return output


def _source_type(
    field: str,
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, list[dict[str, Any]]],
    migration_by_mint: dict[str, dict[str, Any]],
    funding_by_mint: dict[str, list[dict[str, Any]]],
) -> str:
    if field.startswith("holder") or field.startswith("top_") or field.startswith("creator_holder") or field.startswith("fdv_per_holder"):
        return "observed_delta_replay" if holder_by_mint else "missing_sidecar"
    if field in {"repeated_actor_overlap_proxy", "repeated_buyer_overlap_proxy", "synchronized_participation_proxy", "circularity_proxy", "churn_proxy"}:
        return "entity_proxy_sidecar" if entity_by_mint else "missing_sidecar"
    if field == "creator_prior_migration_or_graduation_count":
        return "migration_label_sidecar" if migration_by_mint else "missing_sidecar"
    if field in {"funding_source_available", "repeated_funder_flag"}:
        return "funding_link_sidecar" if funding_by_mint else "missing_sidecar"
    return "all_collected_lifecycle_snapshot"


def _classify(rows: list[dict[str, Any]], primary: dict[str, Any], robustness: dict[str, Any]) -> str:
    if len(rows) < 100:
        return "data_limited"
    raw_delta = abs(primary["100k_plus_vs_sub_100k"]["feature_median_deltas"]["event_count_at_20k"]["delta"] or 0)
    active_delta = abs(primary["100k_plus_vs_sub_100k"]["feature_median_deltas"]["active_wallets_at_20k"]["delta"] or 0)
    high_tier_delta = abs(primary["500k_plus_vs_100k_to_500k"]["feature_median_deltas"]["event_count_at_20k"]["delta"] or 0)
    robust = robustness["chronological_halves"].get("available") and raw_delta > 0
    if raw_delta >= 5 and high_tier_delta >= 2 and active_delta > 0 and robust:
        return "descriptive_signal_present"
    if raw_delta > 0 or high_tier_delta > 0 or active_delta > 0:
        return "weak_signal"
    return "no_signal"


def _warning_flags(classification: str, coverage: dict[str, Any]) -> list[str]:
    warnings = {"fdv_proxy_not_true_market_cap", "no_thesis_promotion", "no_trading_claims"}
    if classification == "data_limited":
        warnings.add("data_limited_trigger_sample")
    sidecar = coverage.get("sidecar_launch_coverage", {})
    if sidecar.get("holder_state_mints", 0) < sidecar.get("all_launch_count", 0):
        warnings.add("holder_state_sidecar_partial_for_all_collected")
    if sidecar.get("funding_link_mints", 0) < sidecar.get("all_launch_count", 0):
        warnings.add("funding_link_sidecar_partial_for_all_collected")
    return sorted(warnings)


def _limitations(coverage: dict[str, Any]) -> list[str]:
    return [
        "FDV/valuation proxy is used; true market-cap claims remain blocked.",
        "Features are descriptive at the first $20k FDV-proxy crossing and are not entry/exit rules.",
        "Holder state is observed-delta replay, not confirmed full-chain account state.",
        "Entity, migration, and funding overlays may have sidecar-limited coverage.",
        f"Holder coverage at trigger: {coverage.get('holder_count_at_20k', {}).get('coverage_pct', 0)}%.",
    ]


def _next_recommendation(classification: str) -> str:
    if classification == "descriptive_signal_present":
        return "Run a separate robustness-only review before any validation; do not promote this thesis from one descriptive result."
    if classification == "weak_signal":
        return "Run chronological and source-sensitivity robustness review for T011 before considering any validation work."
    if classification == "no_signal":
        return "Park raw-flow continuation as a primary thesis and inspect whether data granularity around crossings is too coarse."
    return "Do not interpret T011 yet; improve trigger sample and sidecar coverage first."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "trigger_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    counts = report["milestone_tier_counts"]
    return "\n".join(
        [
            "# T011 Explosive Runner Raw-Flow Continuation",
            "",
            f"- Classification: `{report['final_classification']}`",
            f"- Launches analyzed: `{report['dataset']['launches_analyzed']}`",
            f"- $20k trigger count: `{report['trigger_summary']['trigger_20k_count']}`",
            f"- Milestone tiers: `{counts}`",
            f"- Raw flow separates $100k+: `{report['diagnostics']['raw_flow_separates_100k_plus_from_failures']}`",
            f"- Raw flow separates $500k+: `{report['diagnostics']['raw_flow_separates_500k_plus_from_100k_only']}`",
            f"- Active-wallet breadth helped: `{report['diagnostics']['active_wallet_breadth_adds_information']}`",
            f"- Holder count helped: `{report['diagnostics']['holder_count_adds_information']}`",
            f"- Entity proxy helped: `{report['diagnostics']['entity_proxy_adds_information']}`",
            f"- Funding link helped: `{report['diagnostics']['funding_link_information_adds_information_where_available']}`",
            "",
            "No trading rules were generated.",
            "",
        ]
    )


def _status_markdown(report: dict[str, Any], json_path: Path, markdown_path: Path, tier_csv: Path, feature_csv: Path) -> str:
    coverage = report["feature_coverage_audit"]
    strongest = _strongest_differences(report["primary_comparisons"])
    return "\n".join(
        [
            "# T011 EXPLOSIVE RUNNER RAW-FLOW CONTINUATION STATUS",
            "",
            "## Thesis Description",
            "",
            "T011 tests whether raw flow and participation features at the first observable $20k FDV-proxy crossing distinguish tokens that continue into higher explosive-runner tiers.",
            "",
            "## Why Explosive Runner Continuation",
            "",
            "Prior descriptive cycles exhausted several health, entity, and funding hypotheses. Winner anatomy showed enough higher-tier runner examples to formalize a continuation-focused descriptive thesis.",
            "",
            "## Dataset Used",
            "",
            f"- Scope: `{report['dataset']['dataset_scope']}`",
            f"- Launches analyzed: `{report['dataset']['launches_analyzed']}`",
            f"- Snapshots: `{report['dataset']['snapshot_count']}`",
            "- Valuation semantics: `fdv_proxy_only`; true market-cap claims remain blocked.",
            "",
            "## Trigger And Tier Counts",
            "",
            f"- $20k trigger count: `{report['trigger_summary']['trigger_20k_count']}`",
            *[f"- `{tier}`: `{report['milestone_tier_counts'].get(tier, 0)}`" for tier in TIER_ORDER],
            "",
            "## Feature Coverage",
            "",
            f"- `event_count_at_20k`: `{coverage['event_count_at_20k']['coverage_pct']}%`",
            f"- `buy_count_at_20k`: `{coverage['buy_count_at_20k']['coverage_pct']}%`",
            f"- `active_wallets_at_20k`: `{coverage['active_wallets_at_20k']['coverage_pct']}%`",
            f"- `holder_count_at_20k`: `{coverage['holder_count_at_20k']['coverage_pct']}%`",
            f"- `repeated_actor_overlap_proxy`: `{coverage['repeated_actor_overlap_proxy']['coverage_pct']}%`",
            f"- `funding_source_available`: `{coverage['funding_source_available']['coverage_pct']}%`",
            "",
            "## Strongest Feature Differences",
            "",
            *[f"- `{row['comparison']}` / `{row['feature']}` delta `{row['delta']}`" for row in strongest],
            "",
            "## Interpretive Checks",
            "",
            f"- Raw flow separates $100k+ / sub-$100k: `{report['diagnostics']['raw_flow_separates_100k_plus_from_failures']}`",
            f"- Raw flow separates $500k+ / $100k-$500k: `{report['diagnostics']['raw_flow_separates_500k_plus_from_100k_only']}`",
            f"- Active-wallet breadth helped: `{report['diagnostics']['active_wallet_breadth_adds_information']}`",
            f"- Holder count helped: `{report['diagnostics']['holder_count_adds_information']}`",
            f"- Holder/FDV relationship helped: `{report['diagnostics']['fdv_per_holder_differs_for_higher_tiers']}`",
            f"- Entity overlays helped: `{report['diagnostics']['entity_proxy_adds_information']}`",
            f"- Funding overlays helped where available: `{report['diagnostics']['funding_link_information_adds_information_where_available']}`",
            "",
            "## Classification",
            "",
            f"- Final classification: `{report['final_classification']}`",
            f"- Chronological robustness recommended: `{report['chronological_robustness_recommended']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Outputs",
            "",
            f"- JSON summary: `{json_path}`",
            f"- Markdown summary: `{markdown_path}`",
            f"- Tier feature table: `{tier_csv}`",
            f"- Trigger feature rows: `{feature_csv}`",
            "",
            "## Guardrails",
            "",
            "- No trading rules were generated.",
            "- No thesis promotion, validation, backtest, walk-forward, paper/live trading, optimization, grid search, or ML was run.",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
        ]
    )


def _strongest_differences(primary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for comparison, payload in primary.items():
        for feature, values in payload["feature_median_deltas"].items():
            delta = values.get("delta")
            if delta is not None:
                rows.append({"comparison": comparison, "feature": feature, "delta": delta})
    return sorted(rows, key=lambda row: abs(row["delta"]), reverse=True)[:6]


def _tier_csv_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for tier, payload in table.items():
        row = {"milestone_tier": tier, "launch_count": payload["launch_count"]}
        for field, dist in payload["feature_distributions"].items():
            row[f"{field}_median"] = dist["median"]
            row[f"{field}_sample_count"] = dist["sample_count"]
            row[f"{field}_iqr"] = dist["iqr"]
        rows.append(row)
    return rows


def _feature_csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        flat = {
            "launch_id": row["launch_id"],
            "token_mint": row["token_mint"],
            "creator": row.get("creator"),
            "launch_ts": row.get("launch_ts"),
            "trigger_age_seconds": row["trigger_age_seconds"],
            "trigger_fdv_proxy": row["trigger_fdv_proxy"],
            "peak_fdv_proxy": row["peak_fdv_proxy"],
            "milestone_tier": row["milestone_tier"],
        }
        flat.update(row["features"])
        flat.update(row["outcomes"])
        output.append(flat)
    return output


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_table(path: Path | str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(p).to_dict(orient="records")
    return _read_jsonl(p)


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


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _sidecar_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return _group_by_mint(rows)


def _migration_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _mint(row): {
            "creator": row.get("creator"),
            "creator_prior_migration_or_graduation_count": row.get("creator_prior_migration_or_graduation_count"),
        }
        for row in rows
        if _mint(row)
    }


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0) >= threshold:
            return row
    return None


def _snapshot_view(row: dict[str, Any]) -> dict[str, Any]:
    return {"age_seconds": _age(row), "snapshot_ts": row.get("snapshot_ts"), "valuation_proxy_usd": _value(row)}


def _snapshot_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _age(row) <= age]
    return max(eligible, key=_age) if eligible else None


def _nearest_holder(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    return min(rows, key=lambda row: abs(_holder_age(row) - age)) if rows else None


def _nearest_holder_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _holder_age(row) <= age]
    return max(eligible, key=_holder_age) if eligible else None


def _crossed_within(rows: list[dict[str, Any]], trigger_age: int, window: int, threshold: float) -> bool:
    return any(trigger_age <= _age(row) <= trigger_age + window and (_value(row) or 0) >= threshold for row in rows)


def _creator(rows: list[dict[str, Any]], migration: dict[str, Any], funding: list[dict[str, Any]]) -> str | None:
    if migration.get("creator"):
        return migration.get("creator")
    if funding and funding[0].get("creator"):
        return funding[0].get("creator")
    for row in rows:
        meta = row.get("metadata_json") or {}
        if meta.get("creator_deployer"):
            return meta.get("creator_deployer")
    return None


def _distribution(values: list[Any]) -> dict[str, Any]:
    vals = sorted(value for value in (_float_or_none(value) for value in values) if value is not None)
    if not vals:
        return {"sample_count": 0, "median": None, "iqr": None, "min": None, "max": None}
    return {
        "sample_count": len(vals),
        "median": median(vals),
        "iqr": [vals[len(vals) // 4], vals[(len(vals) * 3) // 4]],
        "min": vals[0],
        "max": vals[-1],
    }


def _feature_values(rows: list[dict[str, Any]], field: str) -> list[Any]:
    return [row["features"].get(field) for row in rows if row["features"].get(field) is not None]


def _median(values: list[Any]) -> float | None:
    vals = [_float_or_none(value) for value in values]
    vals = [value for value in vals if value is not None]
    return median(vals) if vals else None


def _median_delta(positive: list[dict[str, Any]], negative: list[dict[str, Any]], field: str) -> float | None:
    pos = _median(_feature_values(positive, field))
    neg = _median(_feature_values(negative, field))
    if pos is None or neg is None:
        return None
    return pos - neg


def _delta(a: dict[str, Any], b: dict[str, Any], field: str) -> float | None:
    aval = _float_or_none(a.get(field))
    bval = _float_or_none(b.get(field))
    if aval is None or bval is None:
        return None
    return aval - bval


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else None)


def _event_count(row: dict[str, Any]) -> float | None:
    meta = row.get("metadata_json") or {}
    return _first_float(meta.get("event_count"), row.get("event_count"), row.get("tx_count"))


def _age(row: dict[str, Any]) -> int:
    return int(row.get("launch_age_seconds") or row.get("snapshot_age_seconds") or 0)


def _holder_age(row: dict[str, Any]) -> int:
    return int(row.get("snapshot_age_seconds") or row.get("launch_age_seconds") or 0)


def _ratio(a: Any, b: Any) -> float | None:
    aval = _float_or_none(a)
    bval = _float_or_none(b)
    if aval is None or bval in (None, 0):
        return None
    return aval / bval


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


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


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 6) if total else 0.0


def _reproducible_command(
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str | None,
    entity_proxy_path: Path | str | None,
    migration_labels_path: Path | str | None,
    funding_link_path: Path | str | None,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.validation.run_explosive_runner_raw_flow_thesis",
        f'--snapshots-path "{snapshots_path}"',
    ]
    if holder_state_snapshots_path:
        parts.append(f'--holder-state-snapshots-path "{holder_state_snapshots_path}"')
    if entity_proxy_path:
        parts.append(f'--entity-proxy-path "{entity_proxy_path}"')
    if migration_labels_path:
        parts.append(f'--migration-labels-path "{migration_labels_path}"')
    if funding_link_path:
        parts.append(f'--funding-link-path "{funding_link_path}"')
    return " ".join(parts)
